"""Envelope encryption: per-user data keys wrapped by a master key.

Each user gets their own Fernet data key. The data key encrypts credential
values. The master key (from ENCRYPTION_KEY env var) wraps (encrypts) each
user's data key so it can be stored safely in the database.

Two-level Fernet scheme:
    master_key  --wraps-->  data_key  --encrypts-->  credential plaintext
"""

import os
import uuid
import warnings
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken

from backend.config import db, logger


class EnvelopeEncryption:
    """Envelope encryption manager with per-user data keys."""

    def __init__(self, master_key: Optional[str] = None):
        raw = master_key or os.environ.get("ENCRYPTION_KEY")
        if not raw:
            raw = Fernet.generate_key().decode()
            warnings.warn(
                "ENCRYPTION_KEY not set — generated a temporary master key. "
                "Data encrypted in this session will NOT be recoverable after restart. "
                "Set the ENCRYPTION_KEY environment variable for persistence.",
                RuntimeWarning,
                stacklevel=2,
            )
        self._master_key = raw if isinstance(raw, bytes) else raw.encode()
        self._master_fernet = Fernet(self._master_key)

    # ── Data key lifecycle ────────────────────────────────────────────────

    def generate_data_key(self) -> Tuple[bytes, str]:
        """Generate a new Fernet data key.

        Returns:
            (plaintext_data_key, encrypted_data_key) where the data key is
            a raw Fernet key and the encrypted form is the master-wrapped
            version safe for storage.
        """
        plaintext_data_key = Fernet.generate_key()
        encrypted_data_key = self.wrap_data_key(plaintext_data_key)
        return plaintext_data_key, encrypted_data_key

    def wrap_data_key(self, data_key: bytes) -> str:
        """Encrypt a data key with the master key for safe storage."""
        return self._master_fernet.encrypt(data_key).decode()

    def unwrap_data_key(self, wrapped_key: str) -> bytes:
        """Decrypt a wrapped data key using the master key."""
        return self._master_fernet.decrypt(wrapped_key.encode())

    # ── Value encryption / decryption using a data key ────────────────────

    @staticmethod
    def encrypt_with_data_key(plaintext: str, data_key: bytes) -> str:
        """Encrypt a plaintext string using the given data key."""
        f = Fernet(data_key)
        return f.encrypt(plaintext.encode()).decode()

    @staticmethod
    def decrypt_with_data_key(ciphertext: str, data_key: bytes) -> str:
        """Decrypt a ciphertext string using the given data key."""
        f = Fernet(data_key)
        return f.decrypt(ciphertext.encode()).decode()

    # ── High-level helpers (user-aware) ──────────────────────────────────

    async def _get_or_create_user_key(self, user_id: str) -> dict:
        """Look up the active data key for *user_id*, creating one if needed.

        Stored document shape in ``user_data_keys`` collection::

            {
                "key_id": "<uuid>",
                "user_id": "<user-id>",
                "wrapped_data_key": "<master-encrypted data key>",
                "created_at": <datetime>,
                "is_active": true
            }
        """
        doc = await db.user_data_keys.find_one(
            {"user_id": user_id, "is_active": True}
        )
        if doc:
            return doc

        plaintext_key, wrapped_key = self.generate_data_key()
        now = datetime.now(timezone.utc)
        doc = {
            "key_id": str(uuid.uuid4()),
            "user_id": user_id,
            "wrapped_data_key": wrapped_key,
            "created_at": now,
            "is_active": True,
        }
        await db.user_data_keys.insert_one(doc)
        logger.info("Created new data key %s for user %s", doc["key_id"], user_id)
        return doc

    async def encrypt_value(self, plaintext: str, user_id: str) -> dict:
        """Encrypt *plaintext* under the user's data key (envelope style).

        Returns a dict suitable for storage::

            {
                "ciphertext": "<Fernet token>",
                "wrapped_data_key": "<master-wrapped data key>",
                "key_id": "<uuid of the data key record>"
            }
        """
        key_doc = await self._get_or_create_user_key(user_id)
        data_key = self.unwrap_data_key(key_doc["wrapped_data_key"])
        ciphertext = self.encrypt_with_data_key(plaintext, data_key)
        return {
            "ciphertext": ciphertext,
            "wrapped_data_key": key_doc["wrapped_data_key"],
            "key_id": key_doc["key_id"],
        }

    async def decrypt_value(self, envelope: dict) -> str:
        """Decrypt an envelope-encrypted value.

        *envelope* must contain ``ciphertext`` and ``wrapped_data_key``.
        """
        wrapped_key = envelope["wrapped_data_key"]
        ciphertext = envelope["ciphertext"]
        data_key = self.unwrap_data_key(wrapped_key)
        return self.decrypt_with_data_key(ciphertext, data_key)

    # ── Key rotation helpers ─────────────────────────────────────────────

    async def rotate_user_data_key(self, user_id: str) -> dict:
        """Rotate the data key for *user_id*.

        1. Generate a new data key.
        2. Re-encrypt all credentials that used the old key.
        3. Deactivate the old key and store the new one.

        Returns summary info about the rotation.
        """
        old_key_doc = await db.user_data_keys.find_one(
            {"user_id": user_id, "is_active": True}
        )

        # Generate a new data key
        new_plaintext_key, new_wrapped_key = self.generate_data_key()
        new_key_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        re_encrypted_count = 0

        if old_key_doc:
            old_data_key = self.unwrap_data_key(old_key_doc["wrapped_data_key"])

            # Find credentials that reference this key
            credentials = await db.credentials.find(
                {"user_id": user_id}
            ).to_list(length=10_000)

            for cred in credentials:
                envelope_data = cred.get("envelope_encryption")
                if not envelope_data:
                    continue
                if envelope_data.get("key_id") != old_key_doc["key_id"]:
                    continue

                try:
                    plaintext = self.decrypt_with_data_key(
                        envelope_data["ciphertext"], old_data_key
                    )
                    new_ciphertext = self.encrypt_with_data_key(
                        plaintext, new_plaintext_key
                    )

                    await db.credentials.update_one(
                        {"id": cred["id"]},
                        {
                            "$set": {
                                "envelope_encryption": {
                                    "ciphertext": new_ciphertext,
                                    "wrapped_data_key": new_wrapped_key,
                                    "key_id": new_key_id,
                                }
                            }
                        },
                    )
                    re_encrypted_count += 1
                except (InvalidToken, Exception) as exc:
                    logger.warning(
                        "Failed to re-encrypt credential %s during key rotation: %s",
                        cred.get("id"),
                        exc,
                    )

            # Deactivate old key
            await db.user_data_keys.update_one(
                {"key_id": old_key_doc["key_id"]},
                {"$set": {"is_active": False, "deactivated_at": now}},
            )

        # Store new key
        new_key_doc = {
            "key_id": new_key_id,
            "user_id": user_id,
            "wrapped_data_key": new_wrapped_key,
            "created_at": now,
            "is_active": True,
        }
        await db.user_data_keys.insert_one(new_key_doc)

        logger.info(
            "Rotated data key for user %s: new key_id=%s, re-encrypted %d credentials",
            user_id,
            new_key_id,
            re_encrypted_count,
        )

        return {
            "new_key_id": new_key_id,
            "old_key_id": old_key_doc["key_id"] if old_key_doc else None,
            "credentials_re_encrypted": re_encrypted_count,
            "rotated_at": now,
        }

    async def rotate_master_key(self, new_master_key: str) -> dict:
        """Rotate the master key: re-wrap all user data keys.

        This does NOT re-encrypt credential values — only the wrapping layer
        changes, since data keys themselves remain the same.

        Returns summary info about the rotation.
        """
        new_master_fernet = Fernet(
            new_master_key if isinstance(new_master_key, bytes) else new_master_key.encode()
        )

        all_keys = await db.user_data_keys.find(
            {"is_active": True}
        ).to_list(length=100_000)

        re_wrapped_count = 0
        now = datetime.now(timezone.utc)

        for key_doc in all_keys:
            try:
                # Unwrap with current master
                plaintext_data_key = self.unwrap_data_key(key_doc["wrapped_data_key"])
                # Re-wrap with new master
                new_wrapped = new_master_fernet.encrypt(plaintext_data_key).decode()

                await db.user_data_keys.update_one(
                    {"key_id": key_doc["key_id"]},
                    {"$set": {"wrapped_data_key": new_wrapped}},
                )

                # Also update any credential envelopes that store the wrapped key
                await db.credentials.update_many(
                    {"envelope_encryption.key_id": key_doc["key_id"]},
                    {"$set": {"envelope_encryption.wrapped_data_key": new_wrapped}},
                )

                re_wrapped_count += 1
            except (InvalidToken, Exception) as exc:
                logger.warning(
                    "Failed to re-wrap data key %s during master rotation: %s",
                    key_doc["key_id"],
                    exc,
                )

        # Update instance to use new master
        self._master_key = (
            new_master_key if isinstance(new_master_key, bytes) else new_master_key.encode()
        )
        self._master_fernet = Fernet(self._master_key)

        logger.info(
            "Master key rotated — re-wrapped %d user data keys", re_wrapped_count
        )

        return {
            "data_keys_re_wrapped": re_wrapped_count,
            "rotated_at": now,
        }


# Module-level singleton
envelope_encryption = EnvelopeEncryption()

"""
MongoDB field-level encryption for sensitive fields beyond credential values.

Provides Fernet-based encryption/decryption for individual document fields,
with HMAC-SHA256 hashing for searchable encrypted fields.
"""

import hashlib
import hmac
import os
import copy
from typing import Any

from cryptography.fernet import Fernet

# ---------------------------------------------------------------------------
# Sensitive-fields configuration: collection name -> list of field paths
# Dot notation indicates nested keys (e.g. "details.ip_address").
# ---------------------------------------------------------------------------

SENSITIVE_FIELDS: dict[str, list[str]] = {
    "users": ["email"],
    "audit_log": ["details.ip_address", "details.user_agent"],
    "teams": ["members.email"],
    "webhooks": ["secret", "url"],
    "sessions": ["ip_address", "user_agent"],
}


class FieldEncryptor:
    """Encrypt / decrypt individual document fields using Fernet.

    The symmetric key is read from the ``ENCRYPTION_KEY`` environment variable
    (must be a valid Fernet key, i.e. 32 url-safe base64-encoded bytes).
    """

    def __init__(self) -> None:
        key = os.environ.get("ENCRYPTION_KEY")
        if not key:
            raise RuntimeError(
                "ENCRYPTION_KEY environment variable is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        self._key = key.encode() if isinstance(key, str) else key
        self._fernet = Fernet(self._key)

    # ── single-field helpers ────────────────────────────────────────────

    def encrypt_field(self, value: str) -> str:
        """Encrypt a single string value and return the ciphertext as a string."""
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt_field(self, encrypted: str) -> str:
        """Decrypt a single Fernet-encrypted string value."""
        return self._fernet.decrypt(encrypted.encode()).decode()

    # ── document-level helpers ──────────────────────────────────────────

    @staticmethod
    def _get_nested(doc: dict, path: str) -> Any:
        """Retrieve a value from *doc* following a dot-separated *path*."""
        keys = path.split(".")
        current: Any = doc
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        return current

    @staticmethod
    def _set_nested(doc: dict, path: str, value: Any) -> None:
        """Set a value in *doc* following a dot-separated *path*.

        Intermediate dicts are created when they do not exist.
        """
        keys = path.split(".")
        current = doc
        for k in keys[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value

    def encrypt_document(self, doc: dict, fields: list[str]) -> dict:
        """Return a copy of *doc* with the specified *fields* encrypted.

        Fields that are missing from the document are silently skipped.
        Supports dot-notation for nested keys (e.g. ``"profile.email"``).
        """
        result = copy.deepcopy(doc)
        for field_path in fields:
            value = self._get_nested(result, field_path)
            if value is not None and isinstance(value, str):
                self._set_nested(result, field_path, self.encrypt_field(value))
        return result

    def decrypt_document(self, doc: dict, fields: list[str]) -> dict:
        """Return a copy of *doc* with the specified *fields* decrypted.

        Fields that are missing from the document are silently skipped.
        Supports dot-notation for nested keys.
        """
        result = copy.deepcopy(doc)
        for field_path in fields:
            value = self._get_nested(result, field_path)
            if value is not None and isinstance(value, str):
                try:
                    self._set_nested(result, field_path, self.decrypt_field(value))
                except Exception:
                    # Field may not actually be encrypted — leave it as-is.
                    pass
        return result

    # ── searchable hash ─────────────────────────────────────────────────

    def encrypt_search_hash(self, value: str) -> str:
        """Create a deterministic HMAC-SHA256 hash for exact-match queries.

        The hash allows searching on encrypted fields without decrypting
        every document — store the hash alongside the ciphertext and query
        against it.
        """
        return hmac.new(self._key, value.encode(), hashlib.sha256).hexdigest()

"""KMS (Key Management Service) abstraction layer for master key protection.

Solves the "secret zero" problem by supporting pluggable KMS backends:
- local  : Fernet key from ENCRYPTION_KEY env var (default, backward compatible)
- aws    : AWS KMS via boto3
- vault  : HashiCorp Vault Transit backend via HTTP
"""

from __future__ import annotations

import base64
import os
import time
from abc import ABC, abstractmethod
from typing import Tuple

from cryptography.fernet import Fernet

from backend.config import logger

# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class KMSProvider(ABC):
    """Abstract KMS provider interface."""

    @abstractmethod
    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt *plaintext* and return the ciphertext."""

    @abstractmethod
    def decrypt(self, ciphertext: bytes) -> bytes:
        """Decrypt *ciphertext* and return the original plaintext."""

    @abstractmethod
    def generate_data_key(self) -> Tuple[bytes, bytes]:
        """Generate a new data encryption key.

        Returns:
            A tuple of (plaintext_key, encrypted_key).
        """

    @abstractmethod
    def get_status(self) -> dict:
        """Return provider health / metadata as a dict."""


# ---------------------------------------------------------------------------
# Local provider (Fernet, backward-compatible default)
# ---------------------------------------------------------------------------


class LocalKMSProvider(KMSProvider):
    """Uses a local Fernet key sourced from the ENCRYPTION_KEY env var."""

    def __init__(self) -> None:
        key = os.environ.get("ENCRYPTION_KEY")
        if not key:
            key = Fernet.generate_key().decode()
            logger.warning(
                "ENCRYPTION_KEY not set — generated a temporary Fernet key. "
                "Data encrypted in this session will NOT survive a restart."
            )
        self._key = key if isinstance(key, bytes) else key.encode()
        self._fernet = Fernet(self._key)
        self._created_at = time.time()

    # -- public API --

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._fernet.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self._fernet.decrypt(ciphertext)

    def generate_data_key(self) -> Tuple[bytes, bytes]:
        """Generate a Fernet key and return (plaintext_key, encrypted_key)."""
        new_key = Fernet.generate_key()
        encrypted = self._fernet.encrypt(new_key)
        return new_key, encrypted

    def get_status(self) -> dict:
        return {
            "provider": "local",
            "algorithm": "Fernet (AES-128-CBC + HMAC-SHA256)",
            "key_source": "ENCRYPTION_KEY env var",
            "key_set": bool(os.environ.get("ENCRYPTION_KEY")),
            "initialized_at": self._created_at,
        }


# ---------------------------------------------------------------------------
# AWS KMS provider
# ---------------------------------------------------------------------------


class AWSKMSProvider(KMSProvider):
    """Delegates encryption to AWS KMS using boto3.

    Requires the ``AWS_KMS_KEY_ID`` environment variable (a KMS key ARN or
    alias).  Standard AWS credential resolution (env vars, instance profile,
    etc.) is used by boto3.
    """

    def __init__(self) -> None:
        try:
            import boto3  # noqa: F811
        except ImportError:
            raise RuntimeError(
                "boto3 is required for the AWS KMS provider. "
                "Install it with: pip install boto3"
            )

        self._key_id = os.environ.get("AWS_KMS_KEY_ID")
        if not self._key_id:
            raise RuntimeError("AWS_KMS_KEY_ID environment variable is not set")

        region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
        self._client = boto3.client("kms", region_name=region)
        self._region = region
        self._created_at = time.time()

    # -- public API --

    def encrypt(self, plaintext: bytes) -> bytes:
        resp = self._client.encrypt(KeyId=self._key_id, Plaintext=plaintext)
        return resp["CiphertextBlob"]

    def decrypt(self, ciphertext: bytes) -> bytes:
        resp = self._client.decrypt(CiphertextBlob=ciphertext)
        return resp["Plaintext"]

    def generate_data_key(self) -> Tuple[bytes, bytes]:
        resp = self._client.generate_data_key(KeyId=self._key_id, KeySpec="AES_256")
        return resp["Plaintext"], resp["CiphertextBlob"]

    def get_status(self) -> dict:
        return {
            "provider": "aws",
            "key_id": self._key_id,
            "region": self._region,
            "algorithm": "AWS KMS (AES-256-GCM)",
            "initialized_at": self._created_at,
        }


# ---------------------------------------------------------------------------
# HashiCorp Vault Transit provider
# ---------------------------------------------------------------------------


class VaultKMSProvider(KMSProvider):
    """Uses the HashiCorp Vault Transit secrets engine via HTTP (httpx).

    Requires:
        VAULT_ADDR  — e.g. ``https://vault.example.com:8200``
        VAULT_TOKEN — a valid Vault authentication token

    Optional:
        VAULT_TRANSIT_KEY — name of the transit key (default ``keyforge``)
    """

    def __init__(self) -> None:
        try:
            import httpx  # noqa: F811
        except ImportError:
            raise RuntimeError(
                "httpx is required for the Vault KMS provider. "
                "Install it with: pip install httpx"
            )

        self._addr = os.environ.get("VAULT_ADDR")
        self._token = os.environ.get("VAULT_TOKEN")
        if not self._addr or not self._token:
            raise RuntimeError(
                "VAULT_ADDR and VAULT_TOKEN environment variables are required "
                "for the Vault KMS provider"
            )

        self._key_name = os.environ.get("VAULT_TRANSIT_KEY", "keyforge")
        self._client = httpx.Client(
            base_url=self._addr.rstrip("/"),
            headers={"X-Vault-Token": self._token},
            timeout=10.0,
        )
        self._created_at = time.time()

    # -- helpers --

    def _transit_url(self, action: str) -> str:
        return f"/v1/transit/{action}/{self._key_name}"

    # -- public API --

    def encrypt(self, plaintext: bytes) -> bytes:
        b64 = base64.b64encode(plaintext).decode()
        resp = self._client.post(
            self._transit_url("encrypt"),
            json={"plaintext": b64},
        )
        resp.raise_for_status()
        ciphertext = resp.json()["data"]["ciphertext"]
        return ciphertext.encode()

    def decrypt(self, ciphertext: bytes) -> bytes:
        resp = self._client.post(
            self._transit_url("decrypt"),
            json={"ciphertext": ciphertext.decode()},
        )
        resp.raise_for_status()
        b64_plain = resp.json()["data"]["plaintext"]
        return base64.b64decode(b64_plain)

    def generate_data_key(self) -> Tuple[bytes, bytes]:
        resp = self._client.post(
            self._transit_url("datakey") + "/plaintext",
            json={},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        plaintext_key = base64.b64decode(data["plaintext"])
        encrypted_key = data["ciphertext"].encode()
        return plaintext_key, encrypted_key

    def get_status(self) -> dict:
        return {
            "provider": "vault",
            "vault_addr": self._addr,
            "transit_key": self._key_name,
            "algorithm": "Vault Transit (AES-256-GCM)",
            "initialized_at": self._created_at,
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PROVIDERS = {
    "local": LocalKMSProvider,
    "aws": AWSKMSProvider,
    "vault": VaultKMSProvider,
}

_instance: KMSProvider | None = None


def get_kms_provider() -> KMSProvider:
    """Return a KMS provider instance based on the KMS_PROVIDER env var.

    Supported values: ``local`` (default), ``aws``, ``vault``.
    The instance is created once and cached for the lifetime of the process.
    """
    global _instance
    if _instance is not None:
        return _instance

    name = os.environ.get("KMS_PROVIDER", "local").lower().strip()
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise RuntimeError(
            f"Unknown KMS_PROVIDER '{name}'. "
            f"Supported values: {', '.join(_PROVIDERS)}"
        )

    logger.info("Initializing KMS provider: %s", name)
    _instance = cls()
    return _instance

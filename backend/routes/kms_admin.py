"""KMS administration routes for KeyForge.

Provides endpoints to inspect the active KMS provider, test connectivity,
and list available providers with their configuration requirements.
"""

from __future__ import annotations

import os
import time
from typing import List

from fastapi import APIRouter, HTTPException

from backend.encryption.kms import get_kms_provider
from backend.models_kms import KMSProviderInfo, KMSStatus, KMSTestResult

router = APIRouter(prefix="/api/kms", tags=["kms"])

# ---------------------------------------------------------------------------
# GET /status — active provider info
# ---------------------------------------------------------------------------


@router.get("/status", response_model=KMSStatus)
async def kms_status():
    """Return metadata about the currently active KMS provider."""
    try:
        provider = get_kms_provider()
        return KMSStatus(**provider.get_status())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"KMS provider error: {exc}")


# ---------------------------------------------------------------------------
# POST /test — round-trip encrypt/decrypt test
# ---------------------------------------------------------------------------

_TEST_PAYLOAD = b"keyforge-kms-connectivity-test"


@router.post("/test", response_model=KMSTestResult)
async def kms_test():
    """Perform an encrypt/decrypt round-trip and a data-key generation test."""
    start = time.perf_counter()
    provider_name = os.environ.get("KMS_PROVIDER", "local")
    encrypt_ok = decrypt_ok = round_trip_ok = data_key_ok = False
    error = None

    try:
        provider = get_kms_provider()
        provider_name = provider.get_status().get("provider", provider_name)

        # Encrypt
        ciphertext = provider.encrypt(_TEST_PAYLOAD)
        encrypt_ok = True

        # Decrypt
        plaintext = provider.decrypt(ciphertext)
        decrypt_ok = True

        # Round-trip check
        round_trip_ok = plaintext == _TEST_PAYLOAD

        # Data key generation
        plain_key, encrypted_key = provider.generate_data_key()
        data_key_ok = len(plain_key) > 0 and len(encrypted_key) > 0

    except Exception as exc:
        error = str(exc)

    elapsed_ms = (time.perf_counter() - start) * 1000
    success = encrypt_ok and decrypt_ok and round_trip_ok and data_key_ok

    return KMSTestResult(
        success=success,
        provider=provider_name,
        encrypt_ok=encrypt_ok,
        decrypt_ok=decrypt_ok,
        round_trip_ok=round_trip_ok,
        data_key_ok=data_key_ok,
        elapsed_ms=round(elapsed_ms, 2),
        error=error,
    )


# ---------------------------------------------------------------------------
# GET /providers — list available providers
# ---------------------------------------------------------------------------


@router.get("/providers", response_model=List[KMSProviderInfo])
async def kms_providers():
    """List all supported KMS providers and their configuration requirements."""

    # Check optional dependency availability
    boto3_available = False
    try:
        import boto3  # noqa: F401
        boto3_available = True
    except ImportError:
        pass

    httpx_available = False
    try:
        import httpx  # noqa: F401
        httpx_available = True
    except ImportError:
        pass

    return [
        KMSProviderInfo(
            name="local",
            description="Local Fernet encryption using ENCRYPTION_KEY env var. "
                        "Default provider, backward compatible.",
            available=True,
            env_vars=[
                {
                    "name": "ENCRYPTION_KEY",
                    "required": False,
                    "description": "Base64-encoded Fernet key. A temporary key is generated if not set.",
                },
            ],
        ),
        KMSProviderInfo(
            name="aws",
            description="AWS Key Management Service via boto3. "
                        "Supports envelope encryption with data keys.",
            available=boto3_available,
            env_vars=[
                {
                    "name": "AWS_KMS_KEY_ID",
                    "required": True,
                    "description": "ARN or alias of the AWS KMS key.",
                },
                {
                    "name": "AWS_REGION",
                    "required": False,
                    "description": "AWS region (defaults to us-east-1).",
                },
                {
                    "name": "AWS_ACCESS_KEY_ID",
                    "required": False,
                    "description": "AWS access key (or use instance profile / IAM role).",
                },
                {
                    "name": "AWS_SECRET_ACCESS_KEY",
                    "required": False,
                    "description": "AWS secret key.",
                },
            ],
        ),
        KMSProviderInfo(
            name="vault",
            description="HashiCorp Vault Transit secrets engine via HTTP. "
                        "Encryption-as-a-service with full audit logging.",
            available=httpx_available,
            env_vars=[
                {
                    "name": "VAULT_ADDR",
                    "required": True,
                    "description": "Vault server URL (e.g. https://vault.example.com:8200).",
                },
                {
                    "name": "VAULT_TOKEN",
                    "required": True,
                    "description": "Vault authentication token.",
                },
                {
                    "name": "VAULT_TRANSIT_KEY",
                    "required": False,
                    "description": "Transit key name (defaults to 'keyforge').",
                },
            ],
        ),
    ]

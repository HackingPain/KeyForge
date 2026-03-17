"""Envelope encryption routes: per-user data key management and master key rotation."""

from datetime import datetime, timezone

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException

from backend.config import db, logger
from backend.encryption.envelope import envelope_encryption
from backend.models_envelope import (
    KeyRotationResponse,
    KeyStatusResponse,
    MasterKeyRotationResponse,
)
from backend.security import get_current_user

router = APIRouter(
    prefix="/api/encryption/envelope",
    tags=["envelope-encryption"],
)


@router.post("/keys/rotate-user", response_model=KeyRotationResponse)
async def rotate_user_data_key(
    current_user: dict = Depends(get_current_user),
):
    """Rotate the current user's data key.

    Generates a new per-user data key, re-encrypts all credentials that were
    protected by the old key, and deactivates the old key.
    """
    user_id = current_user["id"]

    try:
        result = await envelope_encryption.rotate_user_data_key(user_id)
    except Exception as exc:
        logger.error("User data key rotation failed for %s: %s", user_id, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Data key rotation failed: {exc}",
        )

    # Audit log
    await db.audit_log.insert_one(
        {
            "user_id": user_id,
            "action": "envelope_user_key_rotation",
            "details": {
                "new_key_id": result["new_key_id"],
                "old_key_id": result["old_key_id"],
                "credentials_re_encrypted": result["credentials_re_encrypted"],
            },
            "timestamp": result["rotated_at"],
        }
    )

    return KeyRotationResponse(
        message="User data key rotated successfully",
        new_key_id=result["new_key_id"],
        old_key_id=result["old_key_id"],
        credentials_re_encrypted=result["credentials_re_encrypted"],
        rotated_at=result["rotated_at"],
    )


@router.get("/keys/status", response_model=KeyStatusResponse)
async def get_key_status(
    current_user: dict = Depends(get_current_user),
):
    """Show the current user's envelope encryption key status.

    Returns the active key ID, when it was created, and how many credentials
    are encrypted with it.
    """
    user_id = current_user["id"]

    key_doc = await db.user_data_keys.find_one(
        {"user_id": user_id, "is_active": True}
    )

    if not key_doc:
        return KeyStatusResponse(
            key_id=None,
            created_at=None,
            credential_count=0,
            is_active=False,
        )

    # Count credentials using this key
    credential_count = await db.credentials.count_documents(
        {"user_id": user_id, "envelope_encryption.key_id": key_doc["key_id"]}
    )

    return KeyStatusResponse(
        key_id=key_doc["key_id"],
        created_at=key_doc["created_at"],
        credential_count=credential_count,
        is_active=True,
    )


@router.post("/keys/rotate-master", response_model=MasterKeyRotationResponse)
async def rotate_master_key(
    current_user: dict = Depends(get_current_user),
):
    """Rotate the master encryption key (admin only).

    Generates a new master Fernet key and re-wraps all active user data keys.
    The credential ciphertexts themselves are NOT re-encrypted — only the
    wrapping layer changes.

    NOTE: The new master key is returned in the audit log only. The server
    must be restarted with the new ENCRYPTION_KEY env var for persistence.
    """
    # Admin check — only the first registered user or users with admin role
    is_admin = current_user.get("role") == "admin"
    if not is_admin:
        # Fallback: check if this is the first user (owner)
        first_user = await db.users.find_one(sort=[("created_at", 1)])
        if not first_user or first_user.get("id") != current_user["id"]:
            raise HTTPException(
                status_code=403,
                detail="Only administrators can rotate the master key",
            )

    # Generate new master key
    new_master_key = Fernet.generate_key().decode()

    try:
        result = await envelope_encryption.rotate_master_key(new_master_key)
    except Exception as exc:
        logger.error("Master key rotation failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Master key rotation failed: {exc}",
        )

    # Audit log (do NOT store the new key itself)
    await db.audit_log.insert_one(
        {
            "user_id": current_user["id"],
            "action": "envelope_master_key_rotation",
            "details": {
                "data_keys_re_wrapped": result["data_keys_re_wrapped"],
            },
            "timestamp": result["rotated_at"],
        }
    )

    logger.warning(
        "Master key rotated by user %s. Update ENCRYPTION_KEY env var to: %s",
        current_user["username"],
        new_master_key,
    )

    return MasterKeyRotationResponse(
        message=(
            "Master key rotated successfully. "
            "Update the ENCRYPTION_KEY environment variable and restart the server."
        ),
        data_keys_re_wrapped=result["data_keys_re_wrapped"],
        rotated_at=result["rotated_at"],
    )

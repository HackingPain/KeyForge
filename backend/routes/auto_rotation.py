"""Auto-rotation configuration routes for KeyForge.

The trigger endpoint (POST /api/auto-rotation/{id}/trigger) drives a real call
into the configured ``CredentialIssuer`` for the credential. Legacy credentials
without a registered issuer are skipped, not failed; transient upstream errors
are surfaced as ``failed_upstream`` so the next scheduled rotation can retry.
See ``RotationStatus`` for the full set of outcomes.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

try:
    from ..audit import AuditIntegrity
    from ..config import db
    from ..issuers import (
        IssuerAuthError,
        IssuerError,
        IssuerNotSupported,
        IssuerUpstreamError,
        get_issuer,
    )
    from ..models_lifecycle import (
        AutoRotationConfig,
        AutoRotationConfigCreate,
        RotationStatus,
    )
    from ..security import decrypt_api_key, get_current_user
except ImportError:
    from backend.audit import AuditIntegrity
    from backend.config import db
    from backend.issuers import (
        IssuerAuthError,
        IssuerError,
        IssuerNotSupported,
        IssuerUpstreamError,
        get_issuer,
    )
    from backend.models_lifecycle import (
        AutoRotationConfig,
        AutoRotationConfigCreate,
        RotationStatus,
    )
    from backend.security import decrypt_api_key, get_current_user

router = APIRouter(prefix="/api", tags=["auto-rotation"])

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = {
    "aws": {
        "name": "AWS",
        "description": "Amazon Web Services IAM access keys",
        "default_interval_days": 90,
        "min_interval_days": 1,
        "max_interval_days": 365,
    },
    "github": {
        "name": "GitHub",
        "description": "GitHub personal access tokens and app tokens",
        "default_interval_days": 90,
        "min_interval_days": 1,
        "max_interval_days": 365,
    },
    "stripe": {
        "name": "Stripe",
        "description": "Stripe API keys (secret and publishable)",
        "default_interval_days": 90,
        "min_interval_days": 30,
        "max_interval_days": 365,
    },
}


class AutoRotationConfigUpdate(BaseModel):
    rotation_interval_days: Optional[int] = None
    enabled: Optional[bool] = None


@router.post("/auto-rotation", response_model=dict)
async def configure_auto_rotation(
    data: AutoRotationConfigCreate,
    current_user: dict = Depends(get_current_user),
):
    """Configure auto-rotation for a credential."""
    # Verify credential belongs to user
    credential = await db.credentials.find_one(
        {
            "id": data.credential_id,
            "user_id": current_user["id"],
        }
    )
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    # Check provider is supported
    provider = credential.get("api_name", "").lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Auto-rotation is not supported for provider '{provider}'. "
            f"Supported providers: {', '.join(SUPPORTED_PROVIDERS.keys())}",
        )

    # Check if config already exists
    existing = await db.auto_rotation_configs.find_one(
        {
            "credential_id": data.credential_id,
            "user_id": current_user["id"],
        }
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Auto-rotation config already exists for this credential",
        )

    now = datetime.now(timezone.utc)
    next_rotation = now + timedelta(days=data.rotation_interval_days)

    config = AutoRotationConfig(
        credential_id=data.credential_id,
        user_id=current_user["id"],
        provider=provider,
        rotation_interval_days=data.rotation_interval_days,
        last_rotated=None,
        next_rotation=next_rotation,
        enabled=data.enabled,
    )

    config_doc = config.model_dump()
    await db.auto_rotation_configs.insert_one(config_doc)

    return {
        "id": config_doc["id"],
        "credential_id": config_doc["credential_id"],
        "provider": config_doc["provider"],
        "rotation_interval_days": config_doc["rotation_interval_days"],
        "last_rotated": config_doc["last_rotated"],
        "next_rotation": config_doc["next_rotation"],
        "enabled": config_doc["enabled"],
        "created_at": config_doc["created_at"],
    }


@router.get("/auto-rotation", response_model=list[dict])
async def list_auto_rotation_configs(
    current_user: dict = Depends(get_current_user),
):
    """List all auto-rotation configs for the authenticated user."""
    configs = await db.auto_rotation_configs.find({"user_id": current_user["id"]}).to_list(1000)

    results = []
    for config_doc in configs:
        credential = await db.credentials.find_one({"id": config_doc["credential_id"]})
        api_name = credential.get("api_name", "") if credential else ""
        results.append(
            {
                "id": config_doc["id"],
                "credential_id": config_doc["credential_id"],
                "api_name": api_name,
                "provider": config_doc["provider"],
                "rotation_interval_days": config_doc["rotation_interval_days"],
                "last_rotated": config_doc.get("last_rotated"),
                "next_rotation": config_doc.get("next_rotation"),
                "enabled": config_doc.get("enabled", True),
                "created_at": config_doc["created_at"],
            }
        )

    return results


@router.put("/auto-rotation/{config_id}", response_model=dict)
async def update_auto_rotation_config(
    config_id: str,
    data: AutoRotationConfigUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update auto-rotation config (interval, enabled)."""
    config_doc = await db.auto_rotation_configs.find_one(
        {
            "id": config_id,
            "user_id": current_user["id"],
        }
    )
    if not config_doc:
        raise HTTPException(status_code=404, detail="Auto-rotation config not found")

    update_data = {}
    if data.rotation_interval_days is not None:
        update_data["rotation_interval_days"] = data.rotation_interval_days
        # Recalculate next_rotation based on last_rotated or now
        base_time = config_doc.get("last_rotated") or datetime.now(timezone.utc)
        if isinstance(base_time, str):
            base_time = datetime.fromisoformat(base_time)
        update_data["next_rotation"] = base_time + timedelta(days=data.rotation_interval_days)

    if data.enabled is not None:
        update_data["enabled"] = data.enabled

    if update_data:
        await db.auto_rotation_configs.update_one(
            {"id": config_id, "user_id": current_user["id"]},
            {"$set": update_data},
        )

    updated = await db.auto_rotation_configs.find_one({"id": config_id})
    return {
        "id": updated["id"],
        "credential_id": updated["credential_id"],
        "provider": updated["provider"],
        "rotation_interval_days": updated["rotation_interval_days"],
        "last_rotated": updated.get("last_rotated"),
        "next_rotation": updated.get("next_rotation"),
        "enabled": updated.get("enabled", True),
        "created_at": updated["created_at"],
    }


@router.delete("/auto-rotation/{config_id}", response_model=dict)
async def delete_auto_rotation_config(
    config_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Disable and remove auto-rotation config."""
    result = await db.auto_rotation_configs.delete_one(
        {
            "id": config_id,
            "user_id": current_user["id"],
        }
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Auto-rotation config not found")
    return {"message": "Auto-rotation config removed successfully"}


def _resolve_scope(credential: Dict[str, Any]) -> Dict[str, Any]:
    """Return the scope dict to hand to ``mint_scoped_credential``.

    Prefers the credential's stored ``metadata`` (if present and non-empty);
    falls back to a single-key ``{"scope": credential.scope}`` dict so an
    issuer's mint method always receives something it can branch on.
    """
    metadata = credential.get("metadata")
    if isinstance(metadata, dict) and metadata:
        return metadata
    return {"scope": credential.get("scope")}


async def _next_version_number(credential_id: str, user_id: str) -> int:
    """Return the next sequential version number for a credential."""
    existing_versions = (
        await db.credential_versions.find({"credential_id": credential_id, "user_id": user_id})
        .sort("version_number", -1)
        .to_list(1)
    )
    if existing_versions:
        return existing_versions[0]["version_number"] + 1
    return 1


async def _record_audit(
    user_id: str,
    action: str,
    credential_id: str,
    details: Dict[str, Any],
) -> None:
    """Append a hash-chained audit log entry; swallow logging failures.

    Audit-log integrity is best-effort from this code path: a Mongo hiccup
    while writing the audit entry must not fail the rotation itself, since
    the credential value has already been updated. We log and move on.
    """
    try:
        await AuditIntegrity.create_audit_entry(
            db=db,
            user_id=user_id,
            action=action,
            details=details,
            resource_type="credential",
            resource_id=credential_id,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to write audit-log entry for action %s: %s", action, exc)


def _build_response(
    config_id: str,
    config_doc: Dict[str, Any],
    credential_id: str,
    status: RotationStatus,
    message: str,
    last_rotated: Optional[datetime],
    next_rotation: Optional[datetime],
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the standard rotation-trigger response payload."""
    body: Dict[str, Any] = {
        "config_id": config_id,
        "provider": config_doc.get("provider"),
        "credential_id": credential_id,
        "status": status.value,
        "message": message,
        "last_rotated": last_rotated,
        "next_rotation": next_rotation,
    }
    if extra:
        body.update(extra)
    return body


@router.post("/auto-rotation/{config_id}/trigger", response_model=dict)
async def trigger_rotation(
    config_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Trigger a rotation for ``config_id`` by invoking the credential's issuer.

    Outcomes are enumerated by ``RotationStatus``. Skip outcomes are not
    failures (the response is HTTP 200 with a ``skipped_*`` status); only
    upstream/auth/unexpected errors land in a ``failed_*`` bucket. The
    response shape is stable across all outcomes so the dashboard can
    render a consistent badge.
    """
    config_doc = await db.auto_rotation_configs.find_one(
        {
            "id": config_id,
            "user_id": current_user["id"],
        }
    )
    if not config_doc:
        raise HTTPException(status_code=404, detail="Auto-rotation config not found")

    if not config_doc.get("enabled", True):
        raise HTTPException(status_code=400, detail="Auto-rotation is disabled for this config")

    credential = await db.credentials.find_one({"id": config_doc["credential_id"]})
    if not credential:
        raise HTTPException(status_code=404, detail="Associated credential not found")

    credential_id = credential["id"]
    user_id = current_user["id"]
    provider = config_doc["provider"]
    provider_name = SUPPORTED_PROVIDERS.get(provider, {}).get("name", provider)

    # Validate the existing key still decrypts. This is informational only; it
    # never blocks a rotation because the whole point of rotating is to replace
    # the stored value with something fresh.
    current_key = decrypt_api_key(credential.get("api_key", ""))
    key_valid = current_key != "[decryption failed]"
    last_rotated = config_doc.get("last_rotated")
    next_rotation = config_doc.get("next_rotation")

    # -- 1. Legacy credential without an issuer: skip-noop ------------------
    issuer_name = credential.get("issuer")
    if not issuer_name:
        await _record_audit(
            user_id=user_id,
            action="credential_auto_rotation_skipped",
            credential_id=credential_id,
            details={
                "config_id": config_id,
                "status": RotationStatus.SKIPPED_NO_ISSUER.value,
                "reason": "legacy credential without registered issuer; manual rotation required",
            },
        )
        return _build_response(
            config_id=config_id,
            config_doc=config_doc,
            credential_id=credential_id,
            status=RotationStatus.SKIPPED_NO_ISSUER,
            message=(
                "Credential predates the issuer system; rotate it manually or "
                "re-issue via a supported provider to enable auto-rotation."
            ),
            last_rotated=last_rotated,
            next_rotation=next_rotation,
            extra={
                "current_key_valid": key_valid,
                "reason": "legacy credential without registered issuer; manual rotation required",
            },
        )

    # -- 2. Issuer was deregistered since the credential was minted ---------
    try:
        issuer = get_issuer(issuer_name)
    except IssuerNotSupported:
        await _record_audit(
            user_id=user_id,
            action="credential_auto_rotation_skipped",
            credential_id=credential_id,
            details={
                "config_id": config_id,
                "status": RotationStatus.SKIPPED_ISSUER_NOT_REGISTERED.value,
                "issuer": issuer_name,
            },
        )
        return _build_response(
            config_id=config_id,
            config_doc=config_doc,
            credential_id=credential_id,
            status=RotationStatus.SKIPPED_ISSUER_NOT_REGISTERED,
            message=(
                f"Issuer '{issuer_name}' is not registered. Re-install the "
                f"{provider_name} integration to resume auto-rotation."
            ),
            last_rotated=last_rotated,
            next_rotation=next_rotation,
            extra={"current_key_valid": key_valid, "issuer": issuer_name},
        )

    # -- 3. Issuer registered but cannot mint (e.g. OAuth-only) -------------
    if "mint_scoped_credential" not in issuer.supports:
        await _record_audit(
            user_id=user_id,
            action="credential_auto_rotation_skipped",
            credential_id=credential_id,
            details={
                "config_id": config_id,
                "status": RotationStatus.SKIPPED_UNSUPPORTED.value,
                "issuer": issuer_name,
            },
        )
        return _build_response(
            config_id=config_id,
            config_doc=config_doc,
            credential_id=credential_id,
            status=RotationStatus.SKIPPED_UNSUPPORTED,
            message=(
                f"Issuer '{issuer_name}' does not support minting new credentials; "
                f"auto-rotation is unavailable for this provider."
            ),
            last_rotated=last_rotated,
            next_rotation=next_rotation,
            extra={"current_key_valid": key_valid, "issuer": issuer_name},
        )

    # -- 4. Try to mint -----------------------------------------------------
    scope_arg = _resolve_scope(credential)
    try:
        new_issued = await issuer.mint_scoped_credential(user_id=user_id, scope=scope_arg)
    except IssuerAuthError as exc:
        await _record_audit(
            user_id=user_id,
            action="credential_auto_rotation_failed",
            credential_id=credential_id,
            details={
                "config_id": config_id,
                "status": RotationStatus.FAILED_AUTH.value,
                "issuer": issuer_name,
                "error": str(exc),
            },
        )
        return _build_response(
            config_id=config_id,
            config_doc=config_doc,
            credential_id=credential_id,
            status=RotationStatus.FAILED_AUTH,
            message=(
                f"Upstream authentication with {provider_name} failed. The user "
                f"must re-grant access; auto-rotation will not retry on its own."
            ),
            last_rotated=last_rotated,
            next_rotation=next_rotation,
            extra={"current_key_valid": key_valid, "issuer": issuer_name, "error": str(exc)},
        )
    except IssuerUpstreamError as exc:
        await _record_audit(
            user_id=user_id,
            action="credential_auto_rotation_failed",
            credential_id=credential_id,
            details={
                "config_id": config_id,
                "status": RotationStatus.FAILED_UPSTREAM.value,
                "issuer": issuer_name,
                "error": str(exc),
            },
        )
        return _build_response(
            config_id=config_id,
            config_doc=config_doc,
            credential_id=credential_id,
            status=RotationStatus.FAILED_UPSTREAM,
            message=(
                f"{provider_name} returned an upstream error. The next scheduled " f"rotation will retry automatically."
            ),
            last_rotated=last_rotated,
            next_rotation=next_rotation,
            extra={"current_key_valid": key_valid, "issuer": issuer_name, "error": str(exc)},
        )
    except IssuerError as exc:
        await _record_audit(
            user_id=user_id,
            action="credential_auto_rotation_failed",
            credential_id=credential_id,
            details={
                "config_id": config_id,
                "status": RotationStatus.FAILED.value,
                "issuer": issuer_name,
                "error": str(exc),
            },
        )
        return _build_response(
            config_id=config_id,
            config_doc=config_doc,
            credential_id=credential_id,
            status=RotationStatus.FAILED,
            message=f"Auto-rotation failed: {exc}",
            last_rotated=last_rotated,
            next_rotation=next_rotation,
            extra={"current_key_valid": key_valid, "issuer": issuer_name, "error": str(exc)},
        )
    except Exception as exc:
        # An issuer bug must not crash the rotation worker.
        logger.exception(
            "Unexpected error while minting credential via issuer '%s' for credential %s",
            issuer_name,
            credential_id,
        )
        await _record_audit(
            user_id=user_id,
            action="credential_auto_rotation_failed",
            credential_id=credential_id,
            details={
                "config_id": config_id,
                "status": RotationStatus.FAILED.value,
                "issuer": issuer_name,
                "error": str(exc),
            },
        )
        return _build_response(
            config_id=config_id,
            config_doc=config_doc,
            credential_id=credential_id,
            status=RotationStatus.FAILED,
            message=f"Auto-rotation failed: unexpected error from issuer '{issuer_name}'",
            last_rotated=last_rotated,
            next_rotation=next_rotation,
            extra={"current_key_valid": key_valid, "issuer": issuer_name, "error": str(exc)},
        )

    # -- 5. Success: persist new value, version snapshot, schedule, audit ---
    now = datetime.now(timezone.utc)
    new_next_rotation = now + timedelta(days=config_doc["rotation_interval_days"])

    # Snapshot the new value as a credential_version. Mark prior versions stale
    # so the rolled-up "current" version stays accurate.
    next_version = await _next_version_number(credential_id, user_id)
    await db.credential_versions.update_many(
        {"credential_id": credential_id, "user_id": user_id},
        {"$set": {"is_current": False}},
    )
    version_doc = {
        "id": str(uuid.uuid4()),
        "credential_id": credential_id,
        "user_id": user_id,
        "version_number": next_version,
        "api_key_encrypted": new_issued.encrypted_value,
        "change_reason": f"auto-rotated via issuer '{issuer_name}'",
        "created_at": now,
        "is_current": True,
    }
    await db.credential_versions.insert_one(version_doc)

    # Update the credential record itself.
    credential_update: Dict[str, Any] = {
        "api_key": new_issued.encrypted_value,
        "issued_at": new_issued.issued_at,
        "status": "active",
    }
    if new_issued.expires_at is not None:
        credential_update["expires_at"] = new_issued.expires_at
    await db.credentials.update_one(
        {"id": credential_id, "user_id": user_id},
        {
            "$set": credential_update,
            "$inc": {"rotation_count": 1},
        },
    )

    # Update the rotation-config schedule.
    await db.auto_rotation_configs.update_one(
        {"id": config_id},
        {
            "$set": {
                "last_rotated": now,
                "next_rotation": new_next_rotation,
            }
        },
    )

    await _record_audit(
        user_id=user_id,
        action="credential_auto_rotated",
        credential_id=credential_id,
        details={
            "config_id": config_id,
            "status": RotationStatus.ROTATED.value,
            "issuer": issuer_name,
            "version_number": next_version,
            "expires_at": new_issued.expires_at.isoformat() if new_issued.expires_at else None,
        },
    )

    return _build_response(
        config_id=config_id,
        config_doc=config_doc,
        credential_id=credential_id,
        status=RotationStatus.ROTATED,
        message=(
            f"Rotated via issuer '{issuer_name}' ({provider_name}). "
            f"Next rotation scheduled for {new_next_rotation.isoformat()}."
        ),
        last_rotated=now,
        next_rotation=new_next_rotation,
        extra={
            "current_key_valid": key_valid,
            "issuer": issuer_name,
            "version_number": next_version,
            "expires_at": new_issued.expires_at,
        },
    )


@router.get("/auto-rotation/supported-providers", response_model=dict)
async def get_supported_providers(current_user: dict = Depends(get_current_user)):
    """Return list of providers that support auto-rotation with details."""
    return {"providers": [{"key": key, **details} for key, details in SUPPORTED_PROVIDERS.items()]}

"""Expiration enforcement policy routes for KeyForge."""

from fastapi import APIRouter, HTTPException, Depends
from typing import List
from datetime import datetime, timezone

try:
    from ..config import db
    from ..security import get_current_user
    from ..policies.expiration_policy import ExpirationPolicy
    from ..models_policy import (
        ExpirationPolicyUpdate,
        PolicyCheckResult,
        PolicyViolation,
        PolicyExemptionCreate,
        PolicySummary,
        EnforceRotationRequest,
    )
except ImportError:
    from backend.config import db
    from backend.security import get_current_user
    from backend.policies.expiration_policy import ExpirationPolicy
    from backend.models_policy import (
        ExpirationPolicyUpdate,
        PolicyCheckResult,
        PolicyViolation,
        PolicyExemptionCreate,
        PolicySummary,
        EnforceRotationRequest,
    )

import uuid

router = APIRouter(prefix="/api/policies/expiration", tags=["expiration-policy"])


@router.get("/policy")
async def get_policy(
    current_user: dict = Depends(get_current_user),
):
    """Get the current user's expiration enforcement policy."""
    policy = await ExpirationPolicy.get_user_policy(db, current_user["id"])
    return policy


@router.put("/policy")
async def update_policy(
    update: ExpirationPolicyUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update the current user's expiration enforcement policy."""
    try:
        policy = await ExpirationPolicy.set_user_policy(
            db, current_user["id"], update.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return policy


@router.post("/check/{credential_id}", response_model=PolicyCheckResult)
async def check_credential(
    credential_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Check whether access to a credential is allowed under the current policy."""
    result = await ExpirationPolicy.check_credential_access(
        db, credential_id, current_user["id"],
    )
    if result.get("reason") == "Credential not found":
        raise HTTPException(status_code=404, detail="Credential not found")
    return result


@router.get("/violations")
async def list_violations(
    current_user: dict = Depends(get_current_user),
):
    """List all current policy violations for the authenticated user."""
    violations = await ExpirationPolicy.get_policy_violations(
        db, current_user["id"],
    )
    return violations


@router.post("/enforce/{credential_id}")
async def enforce_credential(
    credential_id: str,
    body: EnforceRotationRequest = EnforceRotationRequest(),
    current_user: dict = Depends(get_current_user),
):
    """Force-expire a credential and require rotation."""
    try:
        result = await ExpirationPolicy.enforce_rotation(
            db,
            credential_id,
            current_user["id"],
            disable_until_rotated=body.disable_until_rotated,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result


@router.post("/exempt/{credential_id}")
async def exempt_credential(
    credential_id: str,
    body: PolicyExemptionCreate,
    current_user: dict = Depends(get_current_user),
):
    """Exempt a credential from the expiration enforcement policy."""
    # Verify credential belongs to user
    credential = await db.credentials.find_one({
        "id": credential_id,
        "user_id": current_user["id"],
    })
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    # Check if already exempt
    existing = await db.policy_exemptions.find_one({
        "credential_id": credential_id,
        "user_id": current_user["id"],
    })
    if existing:
        # Update existing exemption
        await db.policy_exemptions.update_one(
            {"id": existing["id"]},
            {"$set": {
                "reason": body.reason,
                "expires_at": body.expires_at,
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        return {
            "credential_id": credential_id,
            "api_name": credential.get("api_name", ""),
            "exempt": True,
            "reason": body.reason,
            "expires_at": body.expires_at.isoformat() if body.expires_at else None,
            "message": "Exemption updated",
        }

    exemption_doc = {
        "id": str(uuid.uuid4()),
        "credential_id": credential_id,
        "user_id": current_user["id"],
        "reason": body.reason,
        "exempted_by": current_user["id"],
        "created_at": datetime.now(timezone.utc),
        "expires_at": body.expires_at,
    }
    await db.policy_exemptions.insert_one(exemption_doc)

    return {
        "credential_id": credential_id,
        "api_name": credential.get("api_name", ""),
        "exempt": True,
        "reason": body.reason,
        "expires_at": body.expires_at.isoformat() if body.expires_at else None,
        "message": "Credential exempted from expiration policy",
    }


@router.get("/summary", response_model=PolicySummary)
async def policy_summary(
    current_user: dict = Depends(get_current_user),
):
    """Get a summary of expiration policy enforcement for the current user."""
    user_id = current_user["id"]
    policy = await ExpirationPolicy.get_user_policy(db, user_id)
    mode = policy.get("mode", "warn")
    grace_days = policy.get("grace_period_days", 7)

    # Total credentials
    total_credentials = await db.credentials.count_documents({"user_id": user_id})

    # All expirations
    expirations = await db.expirations.find({"user_id": user_id}).to_list(1000)
    total_with_expiration = len(expirations)

    now = datetime.now(timezone.utc)
    total_expired = 0
    total_blocked = 0
    total_in_grace = 0

    for exp_doc in expirations:
        expires_at = exp_doc["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        delta = expires_at - now
        days_until = delta.days

        if days_until >= 0:
            continue

        days_expired = abs(days_until)
        total_expired += 1

        # Check exemption
        exemption = await db.policy_exemptions.find_one({
            "credential_id": exp_doc["credential_id"],
            "user_id": user_id,
        })
        if exemption:
            continue  # Exempt credentials are not blocked or in grace

        if mode == "block":
            total_blocked += 1
        elif mode == "grace":
            if days_expired <= grace_days:
                total_in_grace += 1
            else:
                total_blocked += 1

    # Exemptions
    total_exempt = await db.policy_exemptions.count_documents({"user_id": user_id})

    # Rotation requirements
    total_requiring_rotation = await db.rotation_requirements.count_documents({
        "user_id": user_id,
        "resolved": False,
    })

    return PolicySummary(
        total_credentials=total_credentials,
        total_with_expiration=total_with_expiration,
        total_expired=total_expired,
        total_blocked=total_blocked,
        total_in_grace_period=total_in_grace,
        total_exempt=total_exempt,
        total_requiring_rotation=total_requiring_rotation,
        policy_mode=mode,
    )

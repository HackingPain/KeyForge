"""Key rotation tracking routes for KeyForge."""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from backend.config import db
from backend.security import get_current_user
from backend.models_extended import RotationPolicy, RotationPolicyCreate

router = APIRouter(prefix="/api", tags=["rotation"])


@router.post("/rotation-policies", response_model=dict)
async def create_rotation_policy(
    policy: RotationPolicyCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a rotation policy for a credential owned by the current user."""
    # Verify the credential belongs to the user
    credential = await db.credentials.find_one({
        "id": policy.credential_id,
        "user_id": current_user["id"],
    })
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    # Check if a policy already exists for this credential
    existing = await db.rotation_policies.find_one({
        "credential_id": policy.credential_id,
        "user_id": current_user["id"],
    })
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A rotation policy already exists for this credential",
        )

    now = datetime.now(timezone.utc)
    next_due = now + timedelta(days=policy.rotation_interval_days)

    rotation_policy = RotationPolicy(
        credential_id=policy.credential_id,
        user_id=current_user["id"],
        rotation_interval_days=policy.rotation_interval_days,
        auto_notify=policy.auto_notify,
        last_rotated=None,
        next_rotation_due=next_due,
    )

    doc = rotation_policy.model_dump()
    await db.rotation_policies.insert_one(doc)

    # Remove MongoDB _id for response
    doc.pop("_id", None)
    return doc


@router.get("/rotation-policies", response_model=List[dict])
async def list_rotation_policies(
    current_user: dict = Depends(get_current_user),
):
    """List all rotation policies for the authenticated user with credential details."""
    policies = await (
        db.rotation_policies
        .find({"user_id": current_user["id"]})
        .to_list(100)
    )

    results = []
    for policy in policies:
        policy.pop("_id", None)
        # Attach credential details
        credential = await db.credentials.find_one({"id": policy["credential_id"]})
        if credential:
            policy["credential_name"] = credential.get("api_name", "unknown")
            policy["credential_environment"] = credential.get("environment", "unknown")
        results.append(policy)

    return results


@router.put("/rotation-policies/{policy_id}", response_model=dict)
async def update_rotation_policy(
    policy_id: str,
    update: RotationPolicyCreate,
    current_user: dict = Depends(get_current_user),
):
    """Update a rotation policy's settings."""
    policy = await db.rotation_policies.find_one({
        "id": policy_id,
        "user_id": current_user["id"],
    })
    if not policy:
        raise HTTPException(status_code=404, detail="Rotation policy not found")

    # Recalculate next_rotation_due based on last_rotated or created_at
    base_time = policy.get("last_rotated") or policy.get("created_at") or datetime.now(timezone.utc)
    next_due = base_time + timedelta(days=update.rotation_interval_days)

    update_data = {
        "rotation_interval_days": update.rotation_interval_days,
        "auto_notify": update.auto_notify,
        "next_rotation_due": next_due,
    }

    await db.rotation_policies.update_one(
        {"id": policy_id, "user_id": current_user["id"]},
        {"$set": update_data},
    )

    updated = await db.rotation_policies.find_one({"id": policy_id})
    updated.pop("_id", None)
    return updated


@router.delete("/rotation-policies/{policy_id}")
async def delete_rotation_policy(
    policy_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a rotation policy."""
    result = await db.rotation_policies.delete_one({
        "id": policy_id,
        "user_id": current_user["id"],
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rotation policy not found")
    return {"message": "Rotation policy deleted successfully"}


@router.post("/rotation-policies/{policy_id}/mark-rotated", response_model=dict)
async def mark_rotated(
    policy_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Mark a credential as rotated, updating last_rotated and next_rotation_due."""
    policy = await db.rotation_policies.find_one({
        "id": policy_id,
        "user_id": current_user["id"],
    })
    if not policy:
        raise HTTPException(status_code=404, detail="Rotation policy not found")

    now = datetime.now(timezone.utc)
    next_due = now + timedelta(days=policy["rotation_interval_days"])

    await db.rotation_policies.update_one(
        {"id": policy_id, "user_id": current_user["id"]},
        {"$set": {
            "last_rotated": now,
            "next_rotation_due": next_due,
        }},
    )

    updated = await db.rotation_policies.find_one({"id": policy_id})
    updated.pop("_id", None)
    return updated


@router.get("/rotation-policies/overdue", response_model=List[dict])
async def get_overdue_policies(
    current_user: dict = Depends(get_current_user),
):
    """Get all overdue rotation policies for the authenticated user."""
    now = datetime.now(timezone.utc)

    policies = await (
        db.rotation_policies
        .find({
            "user_id": current_user["id"],
            "next_rotation_due": {"$lte": now},
        })
        .to_list(100)
    )

    results = []
    for policy in policies:
        policy.pop("_id", None)
        # Attach credential details
        credential = await db.credentials.find_one({"id": policy["credential_id"]})
        if credential:
            policy["credential_name"] = credential.get("api_name", "unknown")
            policy["credential_environment"] = credential.get("environment", "unknown")
        results.append(policy)

    return results

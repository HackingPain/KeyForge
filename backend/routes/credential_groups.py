"""Credential group management routes for KeyForge."""

from fastapi import APIRouter, HTTPException, Depends
from typing import List
from datetime import datetime, timezone
import uuid

from backend.config import db
from backend.models_teams import (
    CredentialGroup,
    CredentialGroupCreate,
    CredentialGroupResponse,
)
from backend.security import get_current_user

router = APIRouter(prefix="/api", tags=["credential-groups"])


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_group_or_404(group_id: str) -> dict:
    """Fetch a credential group by id or raise 404."""
    group = await db.credential_groups.find_one({"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Credential group not found")
    return group


async def _check_group_access(group: dict, user_id: str) -> None:
    """Verify the user owns the group or is a member of its team. Raises 403."""
    if group["user_id"] == user_id:
        return

    team_id = group.get("team_id")
    if team_id:
        member = await db.team_members.find_one({"team_id": team_id, "user_id": user_id})
        if member:
            return

    raise HTTPException(status_code=403, detail="Access denied to this credential group")


async def _check_group_owner(group: dict, user_id: str) -> None:
    """Verify the user owns the group. Raises 403."""
    if group["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Only the group owner can perform this action")


# ── Group CRUD ───────────────────────────────────────────────────────────────

@router.post("/credential-groups", response_model=CredentialGroupResponse, status_code=201)
async def create_group(
    body: CredentialGroupCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a new credential group."""
    # If team_id is provided, verify user is a member
    if body.team_id:
        member = await db.team_members.find_one({
            "team_id": body.team_id,
            "user_id": current_user["id"],
        })
        if not member:
            raise HTTPException(status_code=403, detail="Not a member of this team")

    group = CredentialGroup(
        name=body.name,
        description=body.description,
        user_id=current_user["id"],
        team_id=body.team_id,
        credential_ids=body.credential_ids,
    )
    await db.credential_groups.insert_one(group.model_dump())

    return CredentialGroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        user_id=group.user_id,
        team_id=group.team_id,
        credential_count=len(group.credential_ids),
        created_at=group.created_at,
    )


@router.get("/credential-groups", response_model=List[CredentialGroupResponse])
async def list_groups(
    current_user: dict = Depends(get_current_user),
):
    """List credential groups: personal groups + team groups the user has access to."""
    # Personal groups owned by this user
    personal = await db.credential_groups.find(
        {"user_id": current_user["id"]}
    ).to_list(None)

    # Team groups: find all teams the user belongs to, then find team groups
    memberships = await db.team_members.find(
        {"user_id": current_user["id"]}
    ).to_list(None)
    team_ids = [m["team_id"] for m in memberships]

    team_groups = []
    if team_ids:
        team_groups = await db.credential_groups.find({
            "team_id": {"$in": team_ids},
            "user_id": {"$ne": current_user["id"]},  # avoid duplicates
        }).to_list(None)

    all_groups = personal + team_groups

    return [
        CredentialGroupResponse(
            id=g["id"],
            name=g["name"],
            description=g.get("description", ""),
            user_id=g["user_id"],
            team_id=g.get("team_id"),
            credential_count=len(g.get("credential_ids", [])),
            created_at=g["created_at"],
        )
        for g in all_groups
    ]


@router.get("/credential-groups/{group_id}", response_model=CredentialGroupResponse)
async def get_group(
    group_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a credential group with credential details. Requires access."""
    group = await _get_group_or_404(group_id)
    await _check_group_access(group, current_user["id"])

    return CredentialGroupResponse(
        id=group["id"],
        name=group["name"],
        description=group.get("description", ""),
        user_id=group["user_id"],
        team_id=group.get("team_id"),
        credential_count=len(group.get("credential_ids", [])),
        created_at=group["created_at"],
    )


@router.put("/credential-groups/{group_id}", response_model=CredentialGroupResponse)
async def update_group(
    group_id: str,
    body: CredentialGroupCreate,
    current_user: dict = Depends(get_current_user),
):
    """Update a credential group (name, description). Owner only."""
    group = await _get_group_or_404(group_id)
    await _check_group_owner(group, current_user["id"])

    update_data = {"name": body.name, "description": body.description}
    await db.credential_groups.update_one({"id": group_id}, {"$set": update_data})

    updated = await db.credential_groups.find_one({"id": group_id})
    return CredentialGroupResponse(
        id=updated["id"],
        name=updated["name"],
        description=updated.get("description", ""),
        user_id=updated["user_id"],
        team_id=updated.get("team_id"),
        credential_count=len(updated.get("credential_ids", [])),
        created_at=updated["created_at"],
    )


@router.delete("/credential-groups/{group_id}")
async def delete_group(
    group_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a credential group (does not delete the credentials themselves). Owner only."""
    group = await _get_group_or_404(group_id)
    await _check_group_owner(group, current_user["id"])

    await db.credential_groups.delete_one({"id": group_id})
    return {"message": "Credential group deleted successfully"}


# ── Credential membership within groups ──────────────────────────────────────

@router.post("/credential-groups/{group_id}/credentials", status_code=201)
async def add_credential_to_group(
    group_id: str,
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    """Add a credential to a group."""
    group = await _get_group_or_404(group_id)
    await _check_group_access(group, current_user["id"])

    credential_id = body.get("credential_id")
    if not credential_id:
        raise HTTPException(status_code=422, detail="credential_id is required")

    # Verify the credential exists and belongs to the user
    credential = await db.credentials.find_one({
        "id": credential_id,
        "user_id": current_user["id"],
    })
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found or not owned by you")

    # Check if already in the group
    existing_ids = group.get("credential_ids", [])
    if credential_id in existing_ids:
        raise HTTPException(status_code=409, detail="Credential already in this group")

    await db.credential_groups.update_one(
        {"id": group_id},
        {"$push": {"credential_ids": credential_id}},
    )

    return {"message": "Credential added to group", "credential_id": credential_id, "group_id": group_id}


@router.delete("/credential-groups/{group_id}/credentials/{credential_id}")
async def remove_credential_from_group(
    group_id: str,
    credential_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove a credential from a group (does not delete the credential)."""
    group = await _get_group_or_404(group_id)
    await _check_group_access(group, current_user["id"])

    existing_ids = group.get("credential_ids", [])
    if credential_id not in existing_ids:
        raise HTTPException(status_code=404, detail="Credential not found in this group")

    await db.credential_groups.update_one(
        {"id": group_id},
        {"$pull": {"credential_ids": credential_id}},
    )

    return {"message": "Credential removed from group"}

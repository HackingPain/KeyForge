"""Team management routes for KeyForge."""

from fastapi import APIRouter, HTTPException, Depends
from typing import List
from datetime import datetime, timezone
import uuid

from backend.config import db
from backend.models_teams import (
    Team,
    TeamCreate,
    TeamResponse,
    TeamMember,
    TeamMemberAdd,
    TeamMemberResponse,
    SharedCredential,
)
from backend.security import get_current_user

router = APIRouter(prefix="/api", tags=["teams"])


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_team_or_404(team_id: str) -> dict:
    """Fetch a team by id or raise 404."""
    team = await db.teams.find_one({"id": team_id})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


async def _require_membership(team_id: str, user_id: str) -> dict:
    """Return the membership document or raise 403."""
    member = await db.team_members.find_one({"team_id": team_id, "user_id": user_id})
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this team")
    return member


async def _require_admin(team_id: str, user_id: str) -> dict:
    """Return the membership document if the user is owner or admin, else 403."""
    member = await _require_membership(team_id, user_id)
    if member["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin or owner role required")
    return member


# ── Team CRUD ────────────────────────────────────────────────────────────────

@router.post("/teams", response_model=TeamResponse, status_code=201)
async def create_team(
    body: TeamCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a new team. The creator becomes the owner."""
    team = Team(name=body.name, owner_id=current_user["id"])
    team_doc = team.model_dump()
    await db.teams.insert_one(team_doc)

    # Add creator as owner member
    owner_member = TeamMember(
        team_id=team.id,
        user_id=current_user["id"],
        role="owner",
    )
    await db.team_members.insert_one(owner_member.model_dump())

    return TeamResponse(
        id=team.id,
        name=team.name,
        owner_id=team.owner_id,
        member_count=1,
        created_at=team.created_at,
    )


@router.get("/teams", response_model=List[TeamResponse])
async def list_teams(
    current_user: dict = Depends(get_current_user),
):
    """List all teams the current user belongs to (owned + member)."""
    memberships = await db.team_members.find(
        {"user_id": current_user["id"]}
    ).to_list(None)

    team_ids = [m["team_id"] for m in memberships]
    if not team_ids:
        return []

    teams = await db.teams.find({"id": {"$in": team_ids}}).to_list(None)

    results = []
    for t in teams:
        member_count = await db.team_members.count_documents({"team_id": t["id"]})
        results.append(
            TeamResponse(
                id=t["id"],
                name=t["name"],
                owner_id=t["owner_id"],
                member_count=member_count,
                created_at=t["created_at"],
            )
        )
    return results


@router.get("/teams/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get team details. Requires membership."""
    team = await _get_team_or_404(team_id)
    await _require_membership(team_id, current_user["id"])

    member_count = await db.team_members.count_documents({"team_id": team_id})
    return TeamResponse(
        id=team["id"],
        name=team["name"],
        owner_id=team["owner_id"],
        member_count=member_count,
        created_at=team["created_at"],
    )


@router.put("/teams/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: str,
    body: TeamCreate,
    current_user: dict = Depends(get_current_user),
):
    """Update team name. Owner or admin only."""
    team = await _get_team_or_404(team_id)
    await _require_admin(team_id, current_user["id"])

    await db.teams.update_one({"id": team_id}, {"$set": {"name": body.name}})

    member_count = await db.team_members.count_documents({"team_id": team_id})
    return TeamResponse(
        id=team["id"],
        name=body.name,
        owner_id=team["owner_id"],
        member_count=member_count,
        created_at=team["created_at"],
    )


@router.delete("/teams/{team_id}")
async def delete_team(
    team_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a team. Owner only."""
    team = await _get_team_or_404(team_id)
    if team["owner_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Only the team owner can delete the team")

    await db.teams.delete_one({"id": team_id})
    await db.team_members.delete_many({"team_id": team_id})
    await db.shared_credentials.delete_many({"team_id": team_id})

    return {"message": "Team deleted successfully"}


# ── Member management ────────────────────────────────────────────────────────

@router.post("/teams/{team_id}/members", response_model=TeamMemberResponse, status_code=201)
async def add_member(
    team_id: str,
    body: TeamMemberAdd,
    current_user: dict = Depends(get_current_user),
):
    """Add a member to the team by username. Owner or admin only."""
    await _get_team_or_404(team_id)
    await _require_admin(team_id, current_user["id"])

    # Look up target user by username
    target_user = await db.users.find_one({"username": body.username})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_user_id = target_user.get("id", str(target_user["_id"]))

    # Check if already a member
    existing = await db.team_members.find_one({"team_id": team_id, "user_id": target_user_id})
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member of this team")

    member = TeamMember(
        team_id=team_id,
        user_id=target_user_id,
        role=body.role,
    )
    await db.team_members.insert_one(member.model_dump())

    return TeamMemberResponse(
        id=member.id,
        user_id=target_user_id,
        username=body.username,
        role=member.role,
        added_at=member.added_at,
    )


@router.get("/teams/{team_id}/members", response_model=List[TeamMemberResponse])
async def list_members(
    team_id: str,
    current_user: dict = Depends(get_current_user),
):
    """List all members of a team. Requires membership."""
    await _get_team_or_404(team_id)
    await _require_membership(team_id, current_user["id"])

    members = await db.team_members.find({"team_id": team_id}).to_list(None)

    results = []
    for m in members:
        user = await db.users.find_one({"id": m["user_id"]})
        username = user["username"] if user else "unknown"
        results.append(
            TeamMemberResponse(
                id=m["id"],
                user_id=m["user_id"],
                username=username,
                role=m["role"],
                added_at=m["added_at"],
            )
        )
    return results


@router.delete("/teams/{team_id}/members/{user_id}")
async def remove_member(
    team_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove a member from the team. Owner or admin only. Cannot remove the owner."""
    team = await _get_team_or_404(team_id)
    await _require_admin(team_id, current_user["id"])

    if user_id == team["owner_id"]:
        raise HTTPException(status_code=400, detail="Cannot remove the team owner")

    result = await db.team_members.delete_one({"team_id": team_id, "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Member not found")

    return {"message": "Member removed successfully"}


# ── Credential sharing ───────────────────────────────────────────────────────

@router.post("/teams/{team_id}/share-credential", status_code=201)
async def share_credential(
    team_id: str,
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    """Share a credential with the team. Requires membership."""
    await _get_team_or_404(team_id)
    await _require_membership(team_id, current_user["id"])

    credential_id = body.get("credential_id")
    permission = body.get("permission", "read")

    if not credential_id:
        raise HTTPException(status_code=422, detail="credential_id is required")

    if permission not in ("read", "use", "manage"):
        raise HTTPException(status_code=422, detail="permission must be one of: read, use, manage")

    # Verify the credential belongs to the current user
    credential = await db.credentials.find_one({
        "id": credential_id,
        "user_id": current_user["id"],
    })
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found or not owned by you")

    # Check if already shared
    existing = await db.shared_credentials.find_one({
        "credential_id": credential_id,
        "team_id": team_id,
    })
    if existing:
        raise HTTPException(status_code=409, detail="Credential already shared with this team")

    shared = SharedCredential(
        credential_id=credential_id,
        team_id=team_id,
        shared_by=current_user["id"],
        permission=permission,
    )
    await db.shared_credentials.insert_one(shared.model_dump())

    return {
        "id": shared.id,
        "credential_id": credential_id,
        "team_id": team_id,
        "shared_by": current_user["id"],
        "permission": permission,
        "shared_at": shared.shared_at.isoformat(),
    }


@router.get("/teams/{team_id}/credentials")
async def list_team_credentials(
    team_id: str,
    current_user: dict = Depends(get_current_user),
):
    """List credentials shared with the team. Requires membership."""
    await _get_team_or_404(team_id)
    await _require_membership(team_id, current_user["id"])

    shared_docs = await db.shared_credentials.find({"team_id": team_id}).to_list(None)

    results = []
    for sc in shared_docs:
        cred = await db.credentials.find_one({"id": sc["credential_id"]})
        if not cred:
            continue

        # Mask the api key
        api_key_raw = cred.get("api_key", "")
        preview = "****" + api_key_raw[-4:] if len(api_key_raw) > 4 else "****"

        results.append({
            "shared_id": sc["id"],
            "credential_id": cred["id"],
            "api_name": cred["api_name"],
            "api_key_preview": preview,
            "environment": cred.get("environment", "development"),
            "status": cred.get("status", "unknown"),
            "permission": sc["permission"],
            "shared_by": sc["shared_by"],
            "shared_at": sc["shared_at"],
        })

    return results

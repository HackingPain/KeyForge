"""Pydantic models for KeyForge teams, credential groups, and shared credentials."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid


# ── Team models ─────────────────────────────────────────────────────────────

class Team(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    owner_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class TeamResponse(BaseModel):
    id: str
    name: str
    owner_id: str
    member_count: int = 0
    created_at: datetime


class TeamMember(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    team_id: str
    user_id: str
    role: str = "member"  # "owner", "admin", "member", "readonly"
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TeamMemberAdd(BaseModel):
    username: str
    role: str = "member"


class TeamMemberResponse(BaseModel):
    id: str
    user_id: str
    username: str
    role: str
    added_at: datetime


# ── Credential group models ─────────────────────────────────────────────────

class CredentialGroup(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    user_id: str
    team_id: Optional[str] = None  # None = personal group
    credential_ids: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CredentialGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    team_id: Optional[str] = None
    credential_ids: List[str] = []


class CredentialGroupResponse(BaseModel):
    id: str
    name: str
    description: str
    user_id: str
    team_id: Optional[str] = None
    credential_count: int = 0
    created_at: datetime


# ── Shared credential models ────────────────────────────────────────────────

class SharedCredential(BaseModel):
    """Links a credential to a team so team members can access it."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    credential_id: str
    team_id: str
    shared_by: str  # user_id who shared it
    permission: str = "read"  # "read", "use", "manage"
    shared_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

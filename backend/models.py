"""Pydantic models for KeyForge: users, projects, credentials."""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# ── User models ──────────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    created_at: datetime


# ── Project models ───────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=200)


class ProjectAnalysis(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_name: str
    detected_apis: List[Dict]
    file_count: int
    analysis_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    recommendations: List[str] = []


# ── Credential models ────────────────────────────────────────────────────────

ALLOWED_API_NAMES = [
    # Core API providers
    "openai",
    "stripe",
    "github",
    "supabase",
    "firebase",
    "vercel",
    # SSH & Signing
    "ssh",
    "gpg",
    "jwt_signing",
    # Database
    "postgresql",
    "mysql",
    "redis",
    "mongodb_cred",
    # Cloud IAM
    "aws",
    "gcp",
    "azure",
    # Infrastructure & Container Registries
    "tls_ssl",
    "docker_hub",
    "aws_ecr",
    "ghcr",
    # CI/CD
    "github_actions",
    "circleci",
    "gitlab_ci",
    # Encryption & OAuth
    "encryption",
    "oauth_generic",
    # Communication
    "twilio",
    "sendgrid",
]
ALLOWED_ENVIRONMENTS = ["development", "staging", "production"]


class CredentialCreate(BaseModel):
    api_name: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    environment: str = "development"

    @field_validator("api_name")
    @classmethod
    def validate_api_name(cls, v: str) -> str:
        if v.lower() not in ALLOWED_API_NAMES:
            raise ValueError(f"api_name must be one of: {', '.join(ALLOWED_API_NAMES)}")
        return v.lower()

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        if v not in ALLOWED_ENVIRONMENTS:
            raise ValueError(f"environment must be one of: {', '.join(ALLOWED_ENVIRONMENTS)}")
        return v


class CredentialUpdate(BaseModel):
    api_key: Optional[str] = None
    environment: Optional[str] = None


class CredentialResponse(BaseModel):
    id: str
    api_name: str
    api_key_preview: str  # Only show last 4 chars
    status: str
    last_tested: Optional[datetime] = None
    environment: str
    created_at: datetime


class Credential(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    api_name: str
    api_key_encrypted: str = ""  # Fernet-encrypted ciphertext
    status: str = "unknown"  # active, inactive, expired, invalid
    last_tested: Optional[datetime] = None
    environment: str = "development"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str = ""  # Owner
    # Issuer fields (Tier 2): set when KeyForge minted/issued the credential
    # itself rather than receiving a pre-existing key from the user. All four
    # default to None/False so legacy and manually-added credentials remain
    # valid without migration of in-memory objects.
    issuer: Optional[str] = None  # Registered issuer name, e.g. "github"
    issued_at: Optional[datetime] = None
    revocable: bool = False
    scope: Optional[str] = None  # Provider-specific scope identifier

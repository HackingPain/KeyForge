"""Pydantic models for credential lifecycle: expiration, permissions, versioning, auto-rotation."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RotationStatus(str, Enum):
    """Enumerates the outcome of a single auto-rotation execution.

    Used in the response from POST /api/auto-rotation/{id}/trigger and as the
    canonical action-suffix when writing audit-log entries for rotation events.
    """

    # Issuer was invoked and produced a fresh credential; the stored value was updated.
    ROTATED = "rotated"
    # Credential predates the issuer system (no issuer registered); manual rotation required.
    SKIPPED_NO_ISSUER = "skipped_no_issuer"
    # Issuer name on the credential is no longer registered with the app.
    SKIPPED_ISSUER_NOT_REGISTERED = "skipped_issuer_not_registered"
    # Issuer is registered but does not implement mint_scoped_credential.
    SKIPPED_UNSUPPORTED = "skipped_unsupported"
    # Upstream rejected the auth grant (revoked, expired, bad token); needs user attention.
    FAILED_AUTH = "failed_auth"
    # Upstream 5xx or network failure; the next scheduled rotation will retry automatically.
    FAILED_UPSTREAM = "failed_upstream"
    # Generic issuer or unexpected failure; the rotation worker stays alive.
    FAILED = "failed"


# -- Expiration models ---------------------------------------------------------


class CredentialExpiration(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    credential_id: str
    user_id: str
    expires_at: datetime
    alert_days_before: int = 7  # Days before expiry to alert
    alert_sent: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CredentialExpirationCreate(BaseModel):
    credential_id: str
    expires_at: datetime
    alert_days_before: int = 7


class CredentialExpirationResponse(BaseModel):
    id: str
    credential_id: str
    api_name: str = ""
    expires_at: datetime
    days_until_expiry: int = 0
    alert_days_before: int
    is_expired: bool = False
    alert_sent: bool = False


# -- Permission models ---------------------------------------------------------


class CredentialPermission(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    credential_id: str
    user_id: str  # The user being granted access
    granted_by: str  # The owner
    permission: str = "read"  # "read", "use", "manage", "admin"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CredentialPermissionCreate(BaseModel):
    credential_id: str
    username: str  # Look up user_id from username
    permission: str = "read"


class CredentialPermissionResponse(BaseModel):
    id: str
    credential_id: str
    api_name: str = ""
    user_id: str
    username: str = ""
    permission: str
    granted_by: str
    created_at: datetime


# -- Versioning models ---------------------------------------------------------


class CredentialVersion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    credential_id: str
    user_id: str
    version_number: int
    api_key_encrypted: str
    change_reason: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_current: bool = True


class CredentialVersionResponse(BaseModel):
    id: str
    credential_id: str
    version_number: int
    api_key_preview: str  # Masked
    change_reason: str
    created_at: datetime
    is_current: bool


# -- Auto-rotation models -----------------------------------------------------


class AutoRotationConfig(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    credential_id: str
    user_id: str
    provider: str  # "aws", "github", "stripe"
    rotation_interval_days: int = 90
    last_rotated: Optional[datetime] = None
    next_rotation: Optional[datetime] = None
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AutoRotationConfigCreate(BaseModel):
    credential_id: str
    rotation_interval_days: int = 90
    enabled: bool = True

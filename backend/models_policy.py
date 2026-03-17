"""Pydantic models for expiration enforcement policies."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid


class ExpirationPolicyConfig(BaseModel):
    """User-level expiration enforcement policy configuration."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    mode: str = "warn"  # "warn", "block", "grace"
    grace_period_days: int = 7
    notify_on_block: bool = True
    notify_on_warning: bool = True
    auto_disable_on_expiry: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExpirationPolicyUpdate(BaseModel):
    """Request body for updating an expiration policy."""
    mode: Optional[str] = None  # "warn", "block", "grace"
    grace_period_days: Optional[int] = None
    notify_on_block: Optional[bool] = None
    notify_on_warning: Optional[bool] = None
    auto_disable_on_expiry: Optional[bool] = None


class PolicyCheckResult(BaseModel):
    """Result of checking whether credential access is allowed."""
    allowed: bool
    reason: str
    days_expired: int = 0
    policy_mode: str = "warn"
    grace_period_remaining: int = 0
    credential_id: str = ""
    api_name: str = ""


class PolicyViolation(BaseModel):
    """A single policy violation record."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    credential_id: str
    api_name: str = ""
    user_id: str
    violation_type: str  # "expired", "grace_exceeded", "rotation_required"
    days_expired: int = 0
    policy_mode: str = "warn"
    is_blocked: bool = False
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PolicyExemption(BaseModel):
    """Exemption record for a credential excluded from expiration policy."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    credential_id: str
    user_id: str
    reason: str
    exempted_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None  # Exemption itself can expire


class PolicyExemptionCreate(BaseModel):
    """Request body for creating a policy exemption."""
    reason: str = Field(..., min_length=1)
    expires_at: Optional[datetime] = None


class PolicySummary(BaseModel):
    """Summary of policy enforcement status for a user."""
    total_credentials: int = 0
    total_with_expiration: int = 0
    total_expired: int = 0
    total_blocked: int = 0
    total_in_grace_period: int = 0
    total_exempt: int = 0
    total_requiring_rotation: int = 0
    policy_mode: str = "warn"


class EnforceRotationRequest(BaseModel):
    """Request body for enforcing credential rotation."""
    disable_until_rotated: bool = False
    reason: str = ""

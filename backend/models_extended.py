"""Extended Pydantic models for KeyForge: rotation policies, audit logs, health checks."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid


# -- Rotation Policy models --------------------------------------------------

class RotationPolicy(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    credential_id: str
    user_id: str
    rotation_interval_days: int = 90  # Default 90 days
    last_rotated: Optional[datetime] = None
    next_rotation_due: Optional[datetime] = None
    auto_notify: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RotationPolicyCreate(BaseModel):
    credential_id: str
    rotation_interval_days: int = 90
    auto_notify: bool = True


# -- Audit Log models --------------------------------------------------------

class AuditLogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    action: str  # "create", "read", "update", "delete", "test", "rotate", "export", "import", "login"
    resource_type: str  # "credential", "project", "user", "rotation_policy"
    resource_id: Optional[str] = None
    details: str = ""
    ip_address: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# -- Health Check models -----------------------------------------------------

class HealthCheckResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    credential_id: str
    user_id: str
    status: str
    message: str
    response_time: int = 0
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HealthCheckSchedule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    interval_hours: int = 24  # Default daily
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HealthCheckScheduleCreate(BaseModel):
    interval_hours: int = 24
    enabled: bool = True

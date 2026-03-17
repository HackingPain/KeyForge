"""Pydantic models for encrypted backup and disaster recovery."""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
import uuid


class BackupCreate(BaseModel):
    collections: Optional[List[str]] = Field(
        None, description="Specific collections to back up; None means all"
    )
    description: Optional[str] = Field(
        None, max_length=500, description="Human-readable backup description"
    )


class BackupMetadata(BaseModel):
    backup_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    size_bytes: int = Field(..., ge=0)
    collections: List[str]
    checksum: str
    description: Optional[str] = None
    user_id: Optional[str] = None
    status: str = Field(default="completed", pattern="^(completed|failed|in_progress)$")


class BackupRestore(BaseModel):
    encryption_key: str = Field(..., min_length=1, description="Fernet key used to decrypt")
    target_collections: Optional[List[str]] = Field(
        None, description="Restore only these collections; None means all in backup"
    )
    mode: str = Field(
        default="merge",
        pattern="^(merge|replace)$",
        description="'merge' adds missing docs, 'replace' drops and recreates",
    )


class BackupVerification(BaseModel):
    backup_id: str
    is_valid: bool
    checksum_match: bool
    collections: List[str]
    total_documents: int
    verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    errors: Optional[List[str]] = None


class BackupSchedule(BaseModel):
    cron_expression: str = Field(
        ..., min_length=5, description="Cron expression, e.g. '0 2 * * *'"
    )
    collections: Optional[List[str]] = Field(
        None, description="Collections to include; None means all"
    )
    enabled: bool = Field(default=True)
    retention_days: int = Field(default=30, ge=1, le=365)
    description: Optional[str] = None


class BackupListResponse(BaseModel):
    backups: List[BackupMetadata]
    total: int

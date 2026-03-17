"""Pydantic models for tamper-proof audit log integrity endpoints."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class AuditEntryWithHash(BaseModel):
    """An audit log entry that includes hash-chain integrity fields."""

    id: str
    user_id: str
    action: str
    resource_type: Optional[str] = ""
    resource_id: Optional[str] = None
    details: str = ""
    ip_address: Optional[str] = None
    timestamp: str  # ISO-8601 string
    previous_hash: str
    integrity_hash: str


class ChainVerificationResult(BaseModel):
    """Result of verifying the audit log hash chain."""

    valid: bool
    entries_checked: int
    first_broken_at: Optional[int] = None
    gaps_detected: List[int] = Field(default_factory=list)


class AuditExportRequest(BaseModel):
    """Request parameters for exporting a tamper-evident audit log."""

    start_date: datetime
    end_date: datetime


class AuditExportResponse(BaseModel):
    """Response containing exported audit entries with integrity proofs."""

    user_id: str
    start_date: str
    end_date: str
    total_entries: int
    entries: List[AuditEntryWithHash]


class AuditChainStats(BaseModel):
    """Statistics about a user's audit log hash chain."""

    total_entries: int
    chain_length: int
    last_verified: Optional[str] = None
    oldest_entry: Optional[str] = None
    newest_entry: Optional[str] = None

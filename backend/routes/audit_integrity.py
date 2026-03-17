"""Audit integrity routes for tamper-proof hash-chained audit logs."""

from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import datetime, timezone
from typing import Optional

from backend.config import db
from backend.security import get_current_user
from backend.audit.integrity import AuditIntegrity
from backend.models_audit import (
    ChainVerificationResult,
    AuditExportResponse,
    AuditChainStats,
)

router = APIRouter(prefix="/api/audit/integrity", tags=["audit-integrity"])


@router.post("/verify", response_model=ChainVerificationResult)
async def verify_audit_chain(
    limit: int = Query(1000, ge=1, le=10000, description="Max entries to verify"),
    current_user: dict = Depends(get_current_user),
):
    """Verify audit chain integrity for the current user.

    Walks the hash chain for the authenticated user and checks that every
    entry's computed hash matches its stored integrity_hash, and that the
    previous_hash links are consistent.
    """
    result = await AuditIntegrity.verify_chain(
        db, user_id=current_user["id"], limit=limit
    )
    return ChainVerificationResult(**result)


@router.post("/verify/all", response_model=ChainVerificationResult)
async def verify_all_chains(
    limit: int = Query(1000, ge=1, le=10000, description="Max entries to verify"),
    current_user: dict = Depends(get_current_user),
):
    """Admin endpoint to verify the entire audit chain across all users.

    Requires the requesting user to have admin role. Walks the global chain
    and reports any integrity violations.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await AuditIntegrity.verify_chain(db, user_id=None, limit=limit)
    return ChainVerificationResult(**result)


@router.get("/export", response_model=AuditExportResponse)
async def export_audit_log(
    start_date: datetime = Query(..., description="Start date for export range"),
    end_date: datetime = Query(..., description="End date for export range"),
    current_user: dict = Depends(get_current_user),
):
    """Export a tamper-evident audit log with hashes for a date range.

    Returns all hash-chained audit entries for the current user within the
    specified date range, including integrity hashes for independent verification.
    """
    entries = await AuditIntegrity.export_audit_log(
        db,
        user_id=current_user["id"],
        start_date=start_date,
        end_date=end_date,
    )

    return AuditExportResponse(
        user_id=current_user["id"],
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        total_entries=len(entries),
        entries=entries,
    )


@router.get("/stats", response_model=AuditChainStats)
async def get_chain_stats(
    current_user: dict = Depends(get_current_user),
):
    """Get chain statistics for the current user.

    Returns total entries, chain length, and timestamps of the oldest
    and newest entries in the hash chain.
    """
    user_id = current_user["id"]
    query = {"user_id": user_id, "integrity_hash": {"$exists": True}}

    # Total entries in the audit log (including non-chained)
    total_entries = await db.audit_log.count_documents({"user_id": user_id})

    # Chain length (only hash-chained entries)
    chain_length = await db.audit_log.count_documents(query)

    # Oldest chained entry
    oldest = await db.audit_log.find_one(query, sort=[("timestamp", 1)])
    oldest_entry = None
    if oldest and isinstance(oldest.get("timestamp"), datetime):
        oldest_entry = oldest["timestamp"].isoformat()

    # Newest chained entry
    newest = await db.audit_log.find_one(query, sort=[("timestamp", -1)])
    newest_entry = None
    if newest and isinstance(newest.get("timestamp"), datetime):
        newest_entry = newest["timestamp"].isoformat()

    # Last verified timestamp
    last_verified = datetime.now(timezone.utc).isoformat()

    return AuditChainStats(
        total_entries=total_entries,
        chain_length=chain_length,
        last_verified=last_verified,
        oldest_entry=oldest_entry,
        newest_entry=newest_entry,
    )

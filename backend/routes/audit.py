"""Audit log routes for KeyForge."""

from fastapi import APIRouter, Depends, Query
from typing import Optional, List
from datetime import datetime, timedelta, timezone

from backend.config import db
from backend.security import get_current_user
from backend.models_extended import AuditLogEntry

router = APIRouter(prefix="/api", tags=["audit"])


async def log_audit_event(
    db_instance,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: str = "",
    ip_address: Optional[str] = None,
):
    """Helper function to log an audit event. Can be imported by other routes.

    Args:
        db_instance: The MongoDB database instance.
        user_id: ID of the user performing the action.
        action: The action performed (create, read, update, delete, test, rotate, etc.).
        resource_type: The type of resource acted upon (credential, project, user, etc.).
        resource_id: Optional ID of the specific resource.
        details: Optional human-readable details about the event.
        ip_address: Optional IP address of the request origin.
    """
    entry = AuditLogEntry(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    await db_instance.audit_log.insert_one(entry.model_dump())


@router.get("/audit-log", response_model=List[dict])
async def get_audit_log(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    action: Optional[str] = Query(None, description="Filter by action type"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    start_date: Optional[datetime] = Query(None, description="Filter events from this date"),
    end_date: Optional[datetime] = Query(None, description="Filter events until this date"),
    current_user: dict = Depends(get_current_user),
):
    """Get audit log entries for the authenticated user with pagination and filters."""
    query = {"user_id": current_user["id"]}

    if action:
        query["action"] = action

    if resource_type:
        query["resource_type"] = resource_type

    if start_date or end_date:
        query["timestamp"] = {}
        if start_date:
            query["timestamp"]["$gte"] = start_date
        if end_date:
            query["timestamp"]["$lte"] = end_date

    entries = await (
        db.audit_log
        .find(query)
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    for entry in entries:
        entry.pop("_id", None)

    return entries


@router.get("/audit-log/summary", response_model=dict)
async def get_audit_summary(
    days: int = Query(7, ge=1, le=90, description="Number of days to summarize (7 or 30)"),
    current_user: dict = Depends(get_current_user),
):
    """Get summary counts of audit events by action type for the last N days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    pipeline = [
        {
            "$match": {
                "user_id": current_user["id"],
                "timestamp": {"$gte": since},
            }
        },
        {
            "$group": {
                "_id": "$action",
                "count": {"$sum": 1},
            }
        },
    ]

    results = await db.audit_log.aggregate(pipeline).to_list(100)

    summary = {item["_id"]: item["count"] for item in results}

    # Also get total count
    total = sum(summary.values())

    return {
        "period_days": days,
        "since": since.isoformat(),
        "total_events": total,
        "by_action": summary,
    }

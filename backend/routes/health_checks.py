"""Scheduled health check routes for KeyForge."""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import time

from backend.config import db
from backend.security import get_current_user, decrypt_api_key
from backend.validators import validate_credential
from backend.models_extended import (
    HealthCheckResult,
    HealthCheckSchedule,
    HealthCheckScheduleCreate,
)

router = APIRouter(prefix="/api", tags=["health-checks"])


@router.post("/health-checks/schedule", response_model=dict)
async def create_or_update_schedule(
    schedule: HealthCheckScheduleCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create or update the health check schedule for the authenticated user."""
    existing = await db.health_check_schedules.find_one({
        "user_id": current_user["id"],
    })

    now = datetime.now(timezone.utc)
    next_run = now + timedelta(hours=schedule.interval_hours)

    if existing:
        # Update existing schedule
        await db.health_check_schedules.update_one(
            {"user_id": current_user["id"]},
            {"$set": {
                "interval_hours": schedule.interval_hours,
                "enabled": schedule.enabled,
                "next_run": next_run,
            }},
        )
        updated = await db.health_check_schedules.find_one({
            "user_id": current_user["id"],
        })
        updated.pop("_id", None)
        return updated
    else:
        # Create new schedule
        new_schedule = HealthCheckSchedule(
            user_id=current_user["id"],
            interval_hours=schedule.interval_hours,
            enabled=schedule.enabled,
            next_run=next_run,
        )
        doc = new_schedule.model_dump()
        await db.health_check_schedules.insert_one(doc)
        doc.pop("_id", None)
        return doc


@router.get("/health-checks/schedule", response_model=dict)
async def get_schedule(
    current_user: dict = Depends(get_current_user),
):
    """Get the current health check schedule for the authenticated user."""
    schedule = await db.health_check_schedules.find_one({
        "user_id": current_user["id"],
    })
    if not schedule:
        raise HTTPException(status_code=404, detail="No health check schedule found")

    schedule.pop("_id", None)
    return schedule


@router.post("/health-checks/run", response_model=dict)
async def run_health_checks(
    current_user: dict = Depends(get_current_user),
):
    """Manually trigger health checks for all of the user's credentials."""
    credentials = await (
        db.credentials
        .find({"user_id": current_user["id"]})
        .to_list(200)
    )

    if not credentials:
        raise HTTPException(status_code=404, detail="No credentials found")

    results = []
    now = datetime.now(timezone.utc)

    for cred in credentials:
        # Decrypt the stored key
        decrypted_key = decrypt_api_key(cred.get("api_key", ""))

        if decrypted_key == "[decryption failed]":
            result = HealthCheckResult(
                credential_id=cred["id"],
                user_id=current_user["id"],
                status="error",
                message="Failed to decrypt credential",
                response_time=0,
            )
        else:
            # Run validation
            start_time = time.time()
            validation = validate_credential(cred["api_name"], decrypted_key)
            elapsed_ms = int((time.time() - start_time) * 1000)

            result = HealthCheckResult(
                credential_id=cred["id"],
                user_id=current_user["id"],
                status=validation.get("status", "unknown"),
                message=validation.get("message", ""),
                response_time=validation.get("response_time", elapsed_ms),
            )

        doc = result.model_dump()
        await db.health_check_results.insert_one(doc)

        # Update credential status in the credentials collection
        await db.credentials.update_one(
            {"id": cred["id"], "user_id": current_user["id"]},
            {"$set": {
                "status": result.status,
                "last_tested": now,
            }},
        )

        doc.pop("_id", None)
        results.append(doc)

    # Update the schedule's last_run and next_run if a schedule exists
    schedule = await db.health_check_schedules.find_one({
        "user_id": current_user["id"],
    })
    if schedule:
        next_run = now + timedelta(hours=schedule.get("interval_hours", 24))
        await db.health_check_schedules.update_one(
            {"user_id": current_user["id"]},
            {"$set": {
                "last_run": now,
                "next_run": next_run,
            }},
        )

    return {
        "checked_at": now.isoformat(),
        "total_credentials": len(credentials),
        "results": results,
    }


@router.get("/health-checks/results", response_model=List[dict])
async def get_health_check_results(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Get recent health check results for the authenticated user with pagination."""
    results = await (
        db.health_check_results
        .find({"user_id": current_user["id"]})
        .sort("checked_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    for result in results:
        result.pop("_id", None)

    return results


@router.get("/health-checks/results/{credential_id}", response_model=List[dict])
async def get_credential_health_history(
    credential_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Get health check history for a specific credential."""
    # Verify credential belongs to user
    credential = await db.credentials.find_one({
        "id": credential_id,
        "user_id": current_user["id"],
    })
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    results = await (
        db.health_check_results
        .find({
            "credential_id": credential_id,
            "user_id": current_user["id"],
        })
        .sort("checked_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    for result in results:
        result.pop("_id", None)

    return results

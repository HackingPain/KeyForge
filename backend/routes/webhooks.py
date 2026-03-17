"""Webhook and notification management routes for KeyForge."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime, timezone
import uuid
import threading

import requests as http_requests

from backend.config import db, logger
from backend.security import get_current_user

router = APIRouter(prefix="/api", tags=["webhooks"])

# ── Pydantic models ───────────────────────────────────────────────────────

VALID_EVENTS = [
    "credential.expired",
    "credential.test_failed",
    "rotation.overdue",
    "health_check.failed",
]


class WebhookCreate(BaseModel):
    url: str = Field(..., min_length=10)
    events: List[str]
    enabled: bool = True


class WebhookUpdate(BaseModel):
    url: Optional[str] = None
    events: Optional[List[str]] = None
    enabled: Optional[bool] = None


class WebhookResponse(BaseModel):
    id: str
    url: str
    events: List[str]
    enabled: bool
    last_triggered: Optional[datetime] = None
    created_at: datetime


# ── Helper: fire-and-forget webhook delivery ──────────────────────────────

def _send_webhook(url: str, payload: dict, webhook_id: str) -> None:
    """Send a POST request to the webhook URL. Runs in a background thread."""
    try:
        resp = http_requests.post(url, json=payload, timeout=5)
        logger.info(
            "Webhook %s delivered to %s — status %s",
            webhook_id, url, resp.status_code,
        )
    except Exception as exc:
        logger.error("Webhook %s delivery failed for %s: %s", webhook_id, url, exc)


async def trigger_webhooks(
    db_ref,
    user_id: str,
    event: str,
    payload: dict,
) -> None:
    """Find all enabled webhooks for *user_id* matching *event* and fire them.

    Delivery is fire-and-forget: errors are logged but never propagated.
    """
    webhooks = await (
        db_ref.webhooks
        .find({"user_id": user_id, "enabled": True, "events": event})
        .to_list(100)
    )

    now = datetime.now(timezone.utc)
    full_payload = {
        "event": event,
        "timestamp": now.isoformat(),
        "data": payload,
    }

    for wh in webhooks:
        # Update last_triggered timestamp
        await db_ref.webhooks.update_one(
            {"id": wh["id"]},
            {"$set": {"last_triggered": now}},
        )
        # Fire in a background thread so we don't block the event loop
        thread = threading.Thread(
            target=_send_webhook,
            args=(wh["url"], full_payload, wh["id"]),
            daemon=True,
        )
        thread.start()


# ── Routes ────────────────────────────────────────────────────────────────

@router.post("/webhooks", response_model=WebhookResponse)
async def create_webhook(
    webhook: WebhookCreate,
    current_user: dict = Depends(get_current_user),
):
    """Register a new webhook endpoint for the authenticated user."""
    # Validate events
    invalid = [e for e in webhook.events if e not in VALID_EVENTS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event(s): {', '.join(invalid)}. "
                   f"Valid events: {', '.join(VALID_EVENTS)}",
        )

    doc = {
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "url": webhook.url,
        "events": webhook.events,
        "enabled": webhook.enabled,
        "last_triggered": None,
        "created_at": datetime.now(timezone.utc),
    }
    await db.webhooks.insert_one(doc)

    return WebhookResponse(
        id=doc["id"],
        url=doc["url"],
        events=doc["events"],
        enabled=doc["enabled"],
        last_triggered=doc["last_triggered"],
        created_at=doc["created_at"],
    )


@router.get("/webhooks", response_model=List[WebhookResponse])
async def list_webhooks(
    current_user: dict = Depends(get_current_user),
):
    """List all webhooks belonging to the authenticated user."""
    webhooks = await (
        db.webhooks
        .find({"user_id": current_user["id"]})
        .to_list(100)
    )
    return [
        WebhookResponse(
            id=wh["id"],
            url=wh["url"],
            events=wh["events"],
            enabled=wh["enabled"],
            last_triggered=wh.get("last_triggered"),
            created_at=wh["created_at"],
        )
        for wh in webhooks
    ]


@router.put("/webhooks/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: str,
    update: WebhookUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update an existing webhook."""
    existing = await db.webhooks.find_one({
        "id": webhook_id,
        "user_id": current_user["id"],
    })
    if not existing:
        raise HTTPException(status_code=404, detail="Webhook not found")

    update_data = {k: v for k, v in update.dict().items() if v is not None}

    # Validate events if provided
    if "events" in update_data:
        invalid = [e for e in update_data["events"] if e not in VALID_EVENTS]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid event(s): {', '.join(invalid)}. "
                       f"Valid events: {', '.join(VALID_EVENTS)}",
            )

    if update_data:
        await db.webhooks.update_one(
            {"id": webhook_id, "user_id": current_user["id"]},
            {"$set": update_data},
        )

    updated = await db.webhooks.find_one({"id": webhook_id})
    return WebhookResponse(
        id=updated["id"],
        url=updated["url"],
        events=updated["events"],
        enabled=updated["enabled"],
        last_triggered=updated.get("last_triggered"),
        created_at=updated["created_at"],
    )


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a webhook."""
    result = await db.webhooks.delete_one({
        "id": webhook_id,
        "user_id": current_user["id"],
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"message": "Webhook deleted successfully"}


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(
    webhook_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Send a test payload to a webhook URL and report the outcome."""
    webhook = await db.webhooks.find_one({
        "id": webhook_id,
        "user_id": current_user["id"],
    })
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    test_payload = {
        "event": "webhook.test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "message": "This is a test payload from KeyForge.",
            "webhook_id": webhook_id,
        },
    }

    try:
        resp = http_requests.post(webhook["url"], json=test_payload, timeout=5)
        return {
            "message": "Test payload sent",
            "webhook_id": webhook_id,
            "url": webhook["url"],
            "response_status": resp.status_code,
        }
    except http_requests.RequestException as exc:
        return {
            "message": "Test payload delivery failed",
            "webhook_id": webhook_id,
            "url": webhook["url"],
            "error": str(exc),
        }

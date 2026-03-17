"""Import/export routes for KeyForge credentials."""

from fastapi import APIRouter, HTTPException, Depends, Body, Response
from typing import List, Dict, Optional
from datetime import datetime, timezone
import uuid

from backend.config import db, logger
from backend.models import ALLOWED_API_NAMES, ALLOWED_ENVIRONMENTS
from backend.security import get_current_user, encrypt_api_key, decrypt_api_key

router = APIRouter(prefix="/api", tags=["import-export"])

# ── Mapping from .env variable names to KeyForge api_name ─────────────────

ENV_KEY_TO_API_NAME = {
    "OPENAI_API_KEY": "openai",
    "STRIPE_SECRET_KEY": "stripe",
    "STRIPE_PUBLISHABLE_KEY": "stripe",
    "GITHUB_TOKEN": "github",
    "GITHUB_CLIENT_SECRET": "github",
    "SUPABASE_ANON_KEY": "supabase",
    "FIREBASE_API_KEY": "firebase",
    "VERCEL_TOKEN": "vercel",
    "AWS_ACCESS_KEY_ID": "aws",
    "AWS_SECRET_ACCESS_KEY": "aws",
    "DATABASE_URL": "postgresql",
    "POSTGRES_PASSWORD": "postgresql",
    "MYSQL_PASSWORD": "mysql",
    "REDIS_URL": "redis",
    "MONGO_URI": "mongodb_cred",
    "TWILIO_AUTH_TOKEN": "twilio",
    "SENDGRID_API_KEY": "sendgrid",
    "DOCKER_TOKEN": "docker_hub",
    "AZURE_CLIENT_SECRET": "azure",
    "GCP_SERVICE_ACCOUNT_KEY": "gcp",
    "ENCRYPTION_KEY": "encryption",
    "JWT_SECRET": "jwt_signing",
    "SSH_PRIVATE_KEY": "ssh",
}

# Reverse mapping: api_name -> preferred env variable name (first match)
API_NAME_TO_ENV_KEY: Dict[str, str] = {}
for env_key, api_name in ENV_KEY_TO_API_NAME.items():
    if api_name not in API_NAME_TO_ENV_KEY:
        API_NAME_TO_ENV_KEY[api_name] = env_key


def _parse_env_content(content: str) -> List[Dict[str, str]]:
    """Parse .env file content into a list of {key, value, api_name} dicts."""
    entries = []
    for line in content.splitlines():
        line = line.strip()
        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue
        # Split on first '='
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Remove surrounding quotes if present
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        # Detect api_name from key
        api_name = ENV_KEY_TO_API_NAME.get(key)
        if api_name:
            entries.append({"key": key, "value": value, "api_name": api_name})
    return entries


@router.post("/import/env")
async def import_env(
    content: str = Body(..., media_type="text/plain"),
    current_user: dict = Depends(get_current_user),
):
    """Import credentials from .env file content.

    Parses KEY=VALUE lines, skips comments, and detects the api_name for each
    recognised environment variable.  Returns a summary of what was imported.
    """
    entries = _parse_env_content(content)
    if not entries:
        raise HTTPException(
            status_code=400,
            detail="No recognised credential keys found in the provided content.",
        )

    imported = []
    skipped = []
    for entry in entries:
        api_name = entry["api_name"]
        raw_key = entry["value"]
        if not raw_key:
            skipped.append({"key": entry["key"], "reason": "empty value"})
            continue

        encrypted_key = encrypt_api_key(raw_key)
        cred_doc = {
            "id": str(uuid.uuid4()),
            "user_id": current_user["id"],
            "api_name": api_name,
            "api_key": encrypted_key,
            "status": "unknown",
            "last_tested": None,
            "environment": "development",
            "created_at": datetime.now(timezone.utc),
        }
        await db.credentials.insert_one(cred_doc)
        imported.append({
            "id": cred_doc["id"],
            "env_key": entry["key"],
            "api_name": api_name,
        })

    return {
        "message": f"Imported {len(imported)} credential(s)",
        "imported": imported,
        "skipped": skipped,
    }


@router.post("/import/json")
async def import_json(
    entries: List[Dict] = Body(...),
    current_user: dict = Depends(get_current_user),
):
    """Import credentials from a JSON array.

    Expected format: [{"api_name": "...", "api_key": "...", "environment": "..."}]
    """
    imported = []
    errors = []

    for idx, entry in enumerate(entries):
        api_name = entry.get("api_name", "").lower()
        api_key = entry.get("api_key", "")
        environment = entry.get("environment", "development")

        # Validate
        if api_name not in ALLOWED_API_NAMES:
            errors.append({
                "index": idx,
                "reason": f"Invalid api_name: {api_name}",
            })
            continue
        if not api_key:
            errors.append({"index": idx, "reason": "Missing or empty api_key"})
            continue
        if environment not in ALLOWED_ENVIRONMENTS:
            errors.append({
                "index": idx,
                "reason": f"Invalid environment: {environment}",
            })
            continue

        encrypted_key = encrypt_api_key(api_key)
        cred_doc = {
            "id": str(uuid.uuid4()),
            "user_id": current_user["id"],
            "api_name": api_name,
            "api_key": encrypted_key,
            "status": "unknown",
            "last_tested": None,
            "environment": environment,
            "created_at": datetime.now(timezone.utc),
        }
        await db.credentials.insert_one(cred_doc)
        imported.append({
            "id": cred_doc["id"],
            "api_name": api_name,
            "environment": environment,
        })

    return {
        "message": f"Imported {len(imported)} credential(s)",
        "imported": imported,
        "errors": errors,
    }


@router.get("/export/env")
async def export_env(
    current_user: dict = Depends(get_current_user),
):
    """Export all credentials for the current user as a .env file.

    Returns text/plain with KEY=VALUE lines.  A warning header is included
    because the response contains decrypted secrets.
    """
    credentials = await (
        db.credentials
        .find({"user_id": current_user["id"]})
        .to_list(1000)
    )

    lines = ["# KeyForge credential export", f"# User: {current_user['username']}"]
    for cred in credentials:
        api_name = cred.get("api_name", "")
        env_key = API_NAME_TO_ENV_KEY.get(api_name, api_name.upper() + "_KEY")
        decrypted = decrypt_api_key(cred.get("api_key", ""))
        lines.append(f"{env_key}={decrypted}")

    content = "\n".join(lines) + "\n"
    return Response(
        content=content,
        media_type="text/plain",
        headers={
            "X-Warning": "This response contains decrypted secrets. Handle with care.",
            "Content-Disposition": "attachment; filename=credentials.env",
        },
    )


@router.get("/export/json")
async def export_json(
    include_keys: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """Export credentials as a JSON array.

    By default only metadata is included.  Pass ?include_keys=true to include
    the decrypted API keys (use with caution).
    """
    credentials = await (
        db.credentials
        .find({"user_id": current_user["id"]})
        .to_list(1000)
    )

    result = []
    for cred in credentials:
        entry = {
            "id": cred.get("id"),
            "api_name": cred.get("api_name"),
            "environment": cred.get("environment", "development"),
            "status": cred.get("status", "unknown"),
            "created_at": cred.get("created_at", "").isoformat()
            if isinstance(cred.get("created_at"), datetime)
            else str(cred.get("created_at", "")),
        }
        if include_keys:
            entry["api_key"] = decrypt_api_key(cred.get("api_key", ""))
        result.append(entry)

    headers = {}
    if include_keys:
        headers["X-Warning"] = (
            "This response contains decrypted secrets. Handle with care."
        )

    return Response(
        content=__import__("json").dumps(result, indent=2),
        media_type="application/json",
        headers=headers,
    )

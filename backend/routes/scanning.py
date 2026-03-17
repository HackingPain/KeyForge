"""Scanning routes for KeyForge: secret detection, key masking, and dependency analysis."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from typing import List, Dict
from datetime import datetime, timezone
import uuid

from backend.config import db
from backend.security import get_current_user
from backend.scanners import (
    scan_content_for_secrets,
    suggest_key_masking,
    analyze_dependencies,
)

router = APIRouter(prefix="/api", tags=["scanning"])

# Maximum upload size (2 MB) to prevent abuse
MAX_FILE_SIZE = 2 * 1024 * 1024


async def _read_upload(file: UploadFile) -> str:
    """Read an uploaded file and return its text content."""
    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE // 1024} KB",
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a valid UTF-8 text file",
        )


# ── POST /api/scan/secrets ─────────────────────────────────────────────────────


@router.post("/scan/secrets")
async def scan_secrets(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload one or more files and scan them for hardcoded secrets.

    Returns detected secrets with severity levels and remediation suggestions.
    """
    all_findings: List[Dict] = []

    for upload in files:
        content = await _read_upload(upload)
        filename = upload.filename or "unknown"
        findings = scan_content_for_secrets(content, filename)
        for f in findings:
            f["filename"] = filename
        all_findings.extend(findings)

    # Persist scan result
    scan_record = {
        "_id": str(uuid.uuid4()),
        "user_id": current_user["_id"],
        "scan_type": "secrets",
        "file_count": len(files),
        "filenames": [f.filename or "unknown" for f in files],
        "total_findings": len(all_findings),
        "severity_summary": _severity_summary(all_findings),
        "timestamp": datetime.now(timezone.utc),
    }
    await db.scan_results.insert_one(scan_record)

    return {
        "scan_id": scan_record["_id"],
        "file_count": len(files),
        "total_findings": len(all_findings),
        "severity_summary": scan_record["severity_summary"],
        "findings": all_findings,
    }


# ── POST /api/scan/mask-suggestions ───────────────────────────────────────────


@router.post("/scan/mask-suggestions")
async def mask_suggestions(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a single file and receive key-masking suggestions.

    Each suggestion includes the original code snippet, a language-appropriate
    replacement using an environment variable, and the recommended env-var name.
    """
    content = await _read_upload(file)
    filename = file.filename or "unknown"
    suggestions = suggest_key_masking(content, filename)

    # Persist scan result
    scan_record = {
        "_id": str(uuid.uuid4()),
        "user_id": current_user["_id"],
        "scan_type": "mask_suggestions",
        "file_count": 1,
        "filenames": [filename],
        "total_suggestions": len(suggestions),
        "timestamp": datetime.now(timezone.utc),
    }
    await db.scan_results.insert_one(scan_record)

    return {
        "scan_id": scan_record["_id"],
        "filename": filename,
        "total_suggestions": len(suggestions),
        "suggestions": suggestions,
    }


# ── POST /api/scan/dependencies ───────────────────────────────────────────────


@router.post("/scan/dependencies")
async def scan_dependencies(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload dependency files and detect expected APIs.

    Cross-references detected APIs with the user's stored credentials to flag
    which ones are missing.
    """
    all_deps: List[Dict] = []

    for upload in files:
        content = await _read_upload(upload)
        filename = upload.filename or "unknown"
        deps = analyze_dependencies(content, filename)
        for d in deps:
            d["source_file"] = filename
        all_deps.extend(deps)

    # Cross-reference with user's stored credentials
    user_credentials = await db.credentials.find(
        {"user_id": current_user["_id"]}
    ).to_list(length=500)

    stored_apis = {cred.get("api_name", "").lower() for cred in user_credentials}

    for dep in all_deps:
        dep["has_credential"] = dep["expected_api"].lower() in stored_apis

    missing = [d for d in all_deps if not d["has_credential"]]

    # Persist scan result
    scan_record = {
        "_id": str(uuid.uuid4()),
        "user_id": current_user["_id"],
        "scan_type": "dependencies",
        "file_count": len(files),
        "filenames": [f.filename or "unknown" for f in files],
        "total_detected": len(all_deps),
        "missing_credentials": len(missing),
        "timestamp": datetime.now(timezone.utc),
    }
    await db.scan_results.insert_one(scan_record)

    return {
        "scan_id": scan_record["_id"],
        "file_count": len(files),
        "total_detected": len(all_deps),
        "missing_credentials": len(missing),
        "dependencies": all_deps,
    }


# ── GET /api/scan/history ─────────────────────────────────────────────────────


@router.get("/scan/history")
async def scan_history(
    current_user: dict = Depends(get_current_user),
):
    """Return the authenticated user's scan history, newest first."""
    records = (
        await db.scan_results.find({"user_id": current_user["_id"]})
        .sort("timestamp", -1)
        .to_list(length=100)
    )

    # Ensure _id is serialisable
    for record in records:
        record["_id"] = str(record["_id"])

    return {"total": len(records), "scans": records}


# ── Helpers ────────────────────────────────────────────────────────────────────


def _severity_summary(findings: List[Dict]) -> Dict[str, int]:
    """Count findings by severity level."""
    summary: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0}
    for f in findings:
        sev = f.get("severity", "medium")
        summary[sev] = summary.get(sev, 0) + 1
    return summary

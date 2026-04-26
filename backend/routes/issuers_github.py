"""HTTP routes for the GitHub credential issuer.

The router is wired into ``backend.server`` by the orchestrator pass; do
not import or register it from this module's import side.

Routes:

* ``POST /api/issuers/github/start``           Auth required. Returns the
                                               install URL the browser
                                               should open in a new tab.
* ``GET  /api/issuers/github/callback``        Public (GitHub redirect
                                               target). Verifies the
                                               state JWT, registers the
                                               installation, and bounces
                                               the browser back to the
                                               KeyForge frontend with a
                                               success/error flag.
* ``POST /api/issuers/github/mint``            Auth required. Mints a
                                               fine-grained installation
                                               token, encrypts it, and
                                               persists it as a normal
                                               KeyForge credential.
* ``POST /api/issuers/github/revoke/{id}``     Auth required. Marks the
                                               credential revoked and
                                               best-effort revokes
                                               upstream.
* ``GET  /api/issuers/github/installations``   Auth required. Returns the
                                               list of installation ids
                                               associated with the user.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from backend.config import db
from backend.issuers import IssuerAuthError, IssuerNotSupported, IssuerUpstreamError
from backend.issuers.base import IssuedCredential
from backend.issuers.registry import get_issuer
from backend.security import (
    JWT_ALGORITHM,
    JWT_SECRET,
    decrypt_api_key,
    get_current_user,
)

logger = logging.getLogger("keyforge.routes.issuers_github")

router = APIRouter(prefix="/api/issuers/github", tags=["issuers", "github"])


def _frontend_url() -> str:
    return os.environ.get("KEYFORGE_FRONTEND_URL", "http://localhost:3000")


def _redirect_back(status_value: str, reason: Optional[str] = None) -> HTMLResponse:
    """Return a tiny HTML page that bounces the browser back to the frontend.

    A 302 would also work, but the install round-trip happens in a popup
    or new tab opened from the frontend, and a small auto-submitting page
    works equally well across browsers (and lets us avoid CORS quirks
    around third-party redirects).
    """
    params = {"github": status_value}
    if reason:
        params["reason"] = reason
    target = f"{_frontend_url()}/?{urlencode(params)}"
    safe_target = quote(target, safe=":/?&=")
    body = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta http-equiv='refresh' content='0;url={safe_target}'>"
        "<title>GitHub install complete</title></head>"
        "<body><p>Returning you to KeyForge"
        f"<script>window.location.replace({safe_target!r});</script>"
        "</p></body></html>"
    )
    return HTMLResponse(body)


# ── Request/response models ─────────────────────────────────────────────


class StartResponse(BaseModel):
    install_url: str


class MintRequest(BaseModel):
    repo: str = Field(..., description="GitHub repository in 'owner/name' form")
    permissions: Dict[str, str] = Field(
        default_factory=lambda: {"contents": "read"},
        description="Fine-grained permission map per the GitHub API",
    )
    environment: str = Field(default="development")


class MintResponse(BaseModel):
    id: str
    api_name: str
    issuer: str
    scope: Optional[str] = None
    revocable: bool
    issued_at: datetime
    expires_at: Optional[datetime] = None
    environment: str
    plaintext_value: Optional[str] = None


class InstallationsResponse(BaseModel):
    installations: List[str]


# ── Helpers ─────────────────────────────────────────────────────────────


def _is_bearer_request(request: Request) -> bool:
    """Return True if the JWT came in via Authorization header (CLI/SDK)."""
    auth = request.headers.get("Authorization", "")
    return auth.lower().startswith("bearer ")


async def _persist_minted_credential(user_id: str, issued: IssuedCredential, environment: str) -> Dict[str, Any]:
    """Insert the minted credential into ``db.credentials`` and return the doc."""
    cred_doc: Dict[str, Any] = {
        "id": issued.id or str(uuid.uuid4()),
        "user_id": user_id,
        "api_name": issued.api_name,
        "api_key": issued.encrypted_value,
        "status": "active",
        "last_tested": datetime.now(timezone.utc),
        "environment": environment,
        "created_at": datetime.now(timezone.utc),
        # Issuer metadata (Tier 2 fields on the Credential model)
        "issuer": issued.issuer,
        "issued_at": issued.issued_at,
        "expires_at": issued.expires_at,
        "revocable": issued.revocable,
        "scope": issued.scope,
        "issuer_metadata": issued.metadata,
    }
    await db.credentials.insert_one(cred_doc)
    return cred_doc


# ── Routes ──────────────────────────────────────────────────────────────


@router.post("/start", response_model=StartResponse)
async def start_install(current_user: dict = Depends(get_current_user)) -> StartResponse:
    """Return the GitHub App installation URL for this user."""
    issuer = get_issuer("github")
    try:
        install_url = await issuer.start_oauth(current_user["id"])
    except IssuerNotSupported as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return StartResponse(install_url=install_url)


@router.get("/callback")
async def install_callback(
    installation_id: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    setup_action: Optional[str] = Query(default=None),  # noqa: ARG001 - GitHub passes this
):
    """GitHub redirect target after the user installs (or updates) the app."""
    if not installation_id or not state:
        return _redirect_back("error", reason="missing_parameters")

    # Decode the state ourselves to recover the user_id; the issuer's
    # complete_oauth re-verifies it against the same user_id, which is
    # the binding we care about.
    try:
        payload = jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        logger.warning("GitHub callback: invalid state token: %s", exc)
        return _redirect_back("error", reason="invalid_state")

    user_id = payload.get("user_id")
    if not user_id or payload.get("purpose") != "github_install":
        return _redirect_back("error", reason="invalid_state")

    issuer = get_issuer("github")
    try:
        await issuer.complete_oauth(user_id=str(user_id), code=str(installation_id), state=state)
    except IssuerAuthError as exc:
        logger.warning("GitHub callback: auth error: %s", exc)
        return _redirect_back("error", reason="auth_failed")
    except IssuerNotSupported as exc:
        logger.warning("GitHub callback: not configured: %s", exc)
        return _redirect_back("error", reason="not_configured")
    except IssuerUpstreamError as exc:
        logger.warning("GitHub callback: upstream error: %s", exc)
        return _redirect_back("error", reason="upstream_error")

    return _redirect_back("connected")


@router.post("/mint", response_model=MintResponse)
async def mint_credential(
    body: MintRequest,
    request: Request,
    include_value: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
) -> MintResponse:
    """Mint a fine-grained PAT for *body.repo* and persist it."""
    issuer = get_issuer("github")
    try:
        issued = await issuer.mint_scoped_credential(
            user_id=current_user["id"],
            scope={"repo": body.repo, "permissions": body.permissions},
        )
    except IssuerNotSupported as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except IssuerAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IssuerUpstreamError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    cred_doc = await _persist_minted_credential(current_user["id"], issued, body.environment)

    plaintext: Optional[str] = None
    if include_value:
        # Only honour include_value for Bearer-auth callers (CLI/SDK), to
        # avoid handing the raw token back to a browser session that might
        # log it. Same gating philosophy as the proxy token surface.
        if not _is_bearer_request(request):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="include_value=true requires Bearer authentication",
            )
        plaintext = decrypt_api_key(issued.encrypted_value)

    return MintResponse(
        id=cred_doc["id"],
        api_name=cred_doc["api_name"],
        issuer=cred_doc["issuer"],
        scope=cred_doc.get("scope"),
        revocable=cred_doc.get("revocable", True),
        issued_at=cred_doc["issued_at"],
        expires_at=cred_doc.get("expires_at"),
        environment=cred_doc["environment"],
        plaintext_value=plaintext,
    )


@router.post("/revoke/{credential_id}")
async def revoke_credential(
    credential_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Revoke a previously minted GitHub credential.

    The credential's status is flipped to ``"revoked"`` regardless of
    whether the upstream call succeeds; per the ABC contract, the issuer
    swallows expected upstream failures (already-revoked, 404, ...).
    """
    cred = await db.credentials.find_one({"id": credential_id, "user_id": current_user["id"]})
    if not cred:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")

    issuer = get_issuer("github")
    try:
        await issuer.revoke(credential_id)
    except IssuerNotSupported as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except IssuerUpstreamError as exc:
        # Mark revoked locally even on a 5xx; the operator can retry.
        await db.credentials.update_one(
            {"id": credential_id, "user_id": current_user["id"]},
            {"$set": {"status": "revoked", "revoked_at": datetime.now(timezone.utc)}},
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    await db.credentials.update_one(
        {"id": credential_id, "user_id": current_user["id"]},
        {"$set": {"status": "revoked", "revoked_at": datetime.now(timezone.utc)}},
    )
    return {"id": credential_id, "status": "revoked"}


@router.get("/installations", response_model=InstallationsResponse)
async def list_installations(
    current_user: dict = Depends(get_current_user),
) -> InstallationsResponse:
    """Return the user's stored GitHub App installation ids."""
    user = await db.users.find_one({"id": current_user["id"]})
    installations: List[str] = []
    if user:
        installations = list(user.get("github_installations") or [])
    return InstallationsResponse(installations=installations)

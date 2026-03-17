"""Proxy routes — create short-lived tokens and proxy API requests."""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone

try:
    from ..config import db, logger
    from ..security import get_current_user
    from ..models_proxy import (
        ProxyTokenCreate,
        ProxyTokenResponse,
        ProxyTokenList,
        ProxyRequest,
        ProxyResponse,
    )
    from ..proxy.credential_proxy import ProxyTokenManager, ProxyRequestHandler
except ImportError:
    from backend.config import db, logger
    from backend.security import get_current_user
    from backend.models_proxy import (
        ProxyTokenCreate,
        ProxyTokenResponse,
        ProxyTokenList,
        ProxyRequest,
        ProxyResponse,
    )
    from backend.proxy.credential_proxy import ProxyTokenManager, ProxyRequestHandler

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

_token_mgr = ProxyTokenManager()
_request_handler = ProxyRequestHandler()


@router.post("/tokens", response_model=ProxyTokenResponse)
async def create_proxy_token(
    body: ProxyTokenCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a short-lived proxy token for a credential owned by the current user."""
    # Verify the credential belongs to the user
    credential = await db.credentials.find_one({
        "id": body.credential_id,
        "user_id": current_user["id"],
    })
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    result = await _token_mgr.create_proxy_token(
        user_id=current_user["id"],
        credential_id=body.credential_id,
        ttl_seconds=body.ttl_seconds,
        allowed_endpoints=body.allowed_endpoints,
    )

    return ProxyTokenResponse(
        proxy_token=result["proxy_token"],
        token_id=result["token_id"],
        credential_id=result["credential_id"],
        expires_at=result["expires_at"],
        allowed_endpoints=result["allowed_endpoints"],
        created_at=result["created_at"],
    )


@router.get("/tokens", response_model=ProxyTokenList)
async def list_proxy_tokens(
    current_user: dict = Depends(get_current_user),
):
    """List all active (non-expired, non-revoked) proxy tokens for the current user."""
    tokens = await _token_mgr.list_user_tokens(current_user["id"])

    items = [
        ProxyTokenResponse(
            proxy_token="[redacted]",
            token_id=t["token_id"],
            credential_id=t["credential_id"],
            expires_at=t["expires_at"],
            allowed_endpoints=t.get("allowed_endpoints"),
            created_at=t["created_at"],
        )
        for t in tokens
    ]

    return ProxyTokenList(tokens=items, total=len(items))


@router.delete("/tokens/{token_id}")
async def revoke_proxy_token(
    token_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Revoke a proxy token immediately."""
    # Verify ownership
    record = await db.proxy_tokens.find_one({
        "token_id": token_id,
        "user_id": current_user["id"],
    })
    if not record:
        raise HTTPException(status_code=404, detail="Proxy token not found")

    try:
        await _token_mgr.revoke_proxy_token(token_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {"message": "Proxy token revoked", "token_id": token_id}


@router.post("/request", response_model=ProxyResponse)
async def proxy_request(body: ProxyRequest):
    """Execute a proxied API request using a short-lived proxy token.

    The real API credential is injected server-side and never exposed.
    """
    try:
        result = await _request_handler.proxy_request(
            proxy_token=body.proxy_token,
            target_url=body.url,
            method=body.method,
            headers=body.headers,
            body=body.body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    return ProxyResponse(
        status_code=result["status_code"],
        headers=result["headers"],
        body=result["body"],
        elapsed_ms=result["elapsed_ms"],
        proxied_at=result["proxied_at"],
    )


@router.post("/cleanup")
async def cleanup_expired_tokens(
    current_user: dict = Depends(get_current_user),
):
    """Remove expired proxy tokens from the database."""
    deleted = await _token_mgr.cleanup_expired()
    return {"message": f"Cleaned up {deleted} expired proxy tokens", "deleted": deleted}

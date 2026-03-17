"""Core proxy logic: token management and proxied request handling."""

import uuid
import base64
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

import httpx
from jose import JWTError, jwt

try:
    from ..config import db, logger
    from ..security import decrypt_api_key, JWT_SECRET, JWT_ALGORITHM
except ImportError:
    from backend.config import db, logger
    from backend.security import decrypt_api_key, JWT_SECRET, JWT_ALGORITHM

# ── Provider-specific credential injection rules ────────────────────────────

PROVIDER_INJECTION_RULES: Dict[str, Dict[str, str]] = {
    # Bearer token providers
    "openai": {"method": "bearer"},
    "github": {"method": "bearer"},
    "vercel": {"method": "bearer"},
    "supabase": {"method": "bearer"},
    "firebase": {"method": "bearer"},
    "twilio": {"method": "basic"},
    "sendgrid": {"method": "bearer"},
    # Basic auth providers
    "stripe": {"method": "basic", "username_is_key": "true"},
    # API key header providers
    "aws": {"method": "header", "header_name": "X-API-Key"},
    "gcp": {"method": "header", "header_name": "X-API-Key"},
    "azure": {"method": "header", "header_name": "api-key"},
    # Query parameter providers
    "redis": {"method": "query", "param_name": "api_key"},
}

# Default injection method when the provider is not in the map
_DEFAULT_INJECTION = {"method": "bearer"}


class ProxyTokenManager:
    """Create, validate, revoke, and clean up short-lived proxy tokens."""

    PROXY_TOKEN_COLLECTION = "proxy_tokens"

    # ── create ──────────────────────────────────────────────────────────────

    async def create_proxy_token(
        self,
        user_id: str,
        credential_id: str,
        ttl_seconds: int = 300,
        allowed_endpoints: Optional[List[str]] = None,
    ) -> dict:
        """Generate a short-lived JWT proxy token and persist its metadata."""
        token_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)

        # Build JWT payload
        payload = {
            "sub": user_id,
            "tid": token_id,
            "cid": credential_id,
            "exp": expires_at,
            "iat": now,
            "type": "proxy",
        }
        if allowed_endpoints:
            payload["eps"] = allowed_endpoints

        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        # Persist to MongoDB for revocation / listing
        doc = {
            "token_id": token_id,
            "user_id": user_id,
            "credential_id": credential_id,
            "token_hash": _hash_token(token),
            "expires_at": expires_at,
            "created_at": now,
            "revoked": False,
            "allowed_endpoints": allowed_endpoints,
        }
        await db[self.PROXY_TOKEN_COLLECTION].insert_one(doc)

        logger.info(
            "Proxy token created: token_id=%s credential_id=%s ttl=%ds",
            token_id, credential_id, ttl_seconds,
        )

        return {
            "proxy_token": token,
            "token_id": token_id,
            "credential_id": credential_id,
            "expires_at": expires_at,
            "allowed_endpoints": allowed_endpoints,
            "created_at": now,
        }

    # ── validate ────────────────────────────────────────────────────────────

    async def validate_proxy_token(self, token: str) -> dict:
        """Validate a proxy token and return credential info.

        Raises ValueError when the token is invalid, expired, or revoked.
        """
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except JWTError as exc:
            raise ValueError(f"Invalid or expired proxy token: {exc}") from exc

        if payload.get("type") != "proxy":
            raise ValueError("Token is not a proxy token")

        token_id = payload.get("tid")
        if not token_id:
            raise ValueError("Token missing token-id claim")

        # Check revocation in DB
        record = await db[self.PROXY_TOKEN_COLLECTION].find_one(
            {"token_id": token_id}
        )
        if record is None:
            raise ValueError("Proxy token not found")
        if record.get("revoked"):
            raise ValueError("Proxy token has been revoked")

        return {
            "token_id": token_id,
            "user_id": payload["sub"],
            "credential_id": payload["cid"],
            "allowed_endpoints": payload.get("eps"),
            "expires_at": datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        }

    # ── revoke ──────────────────────────────────────────────────────────────

    async def revoke_proxy_token(self, token_id: str) -> None:
        """Immediately invalidate a proxy token by its ID."""
        result = await db[self.PROXY_TOKEN_COLLECTION].update_one(
            {"token_id": token_id},
            {"$set": {"revoked": True}},
        )
        if result.matched_count == 0:
            raise ValueError("Proxy token not found")
        logger.info("Proxy token revoked: token_id=%s", token_id)

    # ── cleanup ─────────────────────────────────────────────────────────────

    async def cleanup_expired(self) -> int:
        """Remove expired tokens from the database. Returns count deleted."""
        now = datetime.now(timezone.utc)
        result = await db[self.PROXY_TOKEN_COLLECTION].delete_many(
            {"expires_at": {"$lt": now}},
        )
        if result.deleted_count:
            logger.info("Cleaned up %d expired proxy tokens", result.deleted_count)
        return result.deleted_count

    # ── list ────────────────────────────────────────────────────────────────

    async def list_user_tokens(self, user_id: str) -> List[dict]:
        """Return all non-expired, non-revoked proxy tokens for a user."""
        now = datetime.now(timezone.utc)
        cursor = db[self.PROXY_TOKEN_COLLECTION].find({
            "user_id": user_id,
            "revoked": False,
            "expires_at": {"$gte": now},
        })
        tokens = await cursor.to_list(length=200)
        for t in tokens:
            t.pop("_id", None)
            t.pop("token_hash", None)
        return tokens


class ProxyRequestHandler:
    """Execute proxied HTTP requests, injecting the real credential transparently."""

    def __init__(self) -> None:
        self._token_mgr = ProxyTokenManager()

    async def proxy_request(
        self,
        proxy_token: str,
        target_url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Any] = None,
    ) -> dict:
        """Validate the proxy token, inject the real credential, and make the call.

        Returns a dict with status_code, headers, body, elapsed_ms, and proxied_at.
        The real API key is NEVER included in the response.
        """
        # 1. Validate token
        token_info = await self._token_mgr.validate_proxy_token(proxy_token)

        # 2. Check endpoint allowlist
        allowed = token_info.get("allowed_endpoints")
        if allowed:
            if not _url_matches_any(target_url, allowed):
                raise ValueError(
                    f"Target URL is not in the allowed endpoints for this proxy token"
                )

        # 3. Look up credential from DB
        credential = await db.credentials.find_one({
            "id": token_info["credential_id"],
            "user_id": token_info["user_id"],
        })
        if credential is None:
            raise ValueError("Credential not found or access denied")

        # 4. Decrypt the real API key
        real_key = decrypt_api_key(credential["api_key"])
        if real_key == "[decryption failed]":
            raise ValueError("Failed to decrypt the stored credential")

        # 5. Build outgoing request with injected credentials
        provider = credential.get("api_name", "").lower()
        out_headers = dict(headers or {})
        out_params: Dict[str, str] = {}
        _inject_credential(provider, real_key, out_headers, out_params)

        # 6. Execute the HTTP request
        method = method.upper()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=target_url,
                headers=out_headers,
                params=out_params if out_params else None,
                json=body if body is not None else None,
            )

        # 7. Build sanitised response
        resp_headers = dict(response.headers)
        try:
            resp_body = response.json()
        except Exception:
            resp_body = response.text

        elapsed_ms = response.elapsed.total_seconds() * 1000

        logger.info(
            "Proxied %s %s -> %d (%.1fms) via token_id=%s",
            method, target_url, response.status_code, elapsed_ms,
            token_info["token_id"],
        )

        return {
            "status_code": response.status_code,
            "headers": resp_headers,
            "body": resp_body,
            "elapsed_ms": round(elapsed_ms, 2),
            "proxied_at": datetime.now(timezone.utc),
        }


# ── Helpers ─────────────────────────────────────────────────────────────────

def _hash_token(token: str) -> str:
    """Return a simple hash for token lookup (not security-critical)."""
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


def _inject_credential(
    provider: str,
    api_key: str,
    headers: Dict[str, str],
    params: Dict[str, str],
) -> None:
    """Inject the real credential into request headers or query params."""
    rule = PROVIDER_INJECTION_RULES.get(provider, _DEFAULT_INJECTION)
    method = rule["method"]

    if method == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    elif method == "basic":
        # Some providers use the key as username with empty password
        if rule.get("username_is_key"):
            encoded = base64.b64encode(f"{api_key}:".encode()).decode()
        else:
            encoded = base64.b64encode(f":{api_key}".encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    elif method == "header":
        header_name = rule.get("header_name", "X-API-Key")
        headers[header_name] = api_key
    elif method == "query":
        param_name = rule.get("param_name", "api_key")
        params[param_name] = api_key
    else:
        # Fallback to Bearer
        headers["Authorization"] = f"Bearer {api_key}"


def _url_matches_any(url: str, patterns: List[str]) -> bool:
    """Check whether *url* matches any of the allowed endpoint patterns.

    Patterns can be exact prefixes (e.g. ``https://api.openai.com/``) or
    contain a ``*`` wildcard for simple glob matching.
    """
    for pattern in patterns:
        if "*" in pattern:
            # Simple wildcard: split on '*' and check prefix/suffix
            parts = pattern.split("*", 1)
            if url.startswith(parts[0]) and url.endswith(parts[1]):
                return True
        else:
            if url.startswith(pattern):
                return True
    return False

"""GitHub credential issuer.

Implements the ``CredentialIssuer`` interface against a GitHub App so a
non-technical user can click "Connect GitHub", install the app on the
repos they care about, and have KeyForge mint fine-grained installation
access tokens scoped to a single repository on demand.

Environment variables (read at instantiation time, validated lazily so
the FastAPI app boots even when no GitHub App is configured):

* ``GITHUB_APP_ID``                Numeric GitHub App ID.
* ``GITHUB_APP_PRIVATE_KEY``       PEM-encoded RSA private key; either the
                                   key text itself (must start with
                                   ``-----BEGIN``) or a filesystem path.
* ``GITHUB_APP_CLIENT_ID``         OAuth client id used as fallback slug.
* ``GITHUB_APP_CLIENT_SECRET``     OAuth client secret (reserved for
                                   user-to-server flows; not used by the
                                   installation token mint path).
* ``GITHUB_APP_SLUG``              Public app slug; used to build the
                                   installation URL. Falls back to
                                   ``GITHUB_APP_CLIENT_ID``.
* ``GITHUB_APP_INSTALL_REDIRECT_URL``  Where GitHub redirects after the
                                   user installs the app. Defaults to
                                   ``http://localhost:3000/integrations/github/callback``.

If any of the four required values (``app_id``, ``private_key``,
``client_id``, ``client_secret``) are missing at call time, every method
raises ``IssuerNotSupported`` with a clear message; the app does not
crash at import.

Security notes:

* The private key is never logged. ``__repr__`` is overridden to scrub
  it. We only ever read the key, never echo or persist it.
* Minted installation tokens are encrypted with the project Fernet key
  via ``encrypt_api_key`` before they leave this module. The plaintext
  token is held in process memory only long enough to encrypt it.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from jose import JWTError, jwt

from backend.config import db
from backend.issuers.base import (
    CredentialIssuer,
    IssuedCredential,
    IssuerAuthError,
    IssuerNotSupported,
    IssuerUpstreamError,
)
from backend.issuers.registry import register_issuer
from backend.security import JWT_ALGORITHM, JWT_SECRET, encrypt_api_key

logger = logging.getLogger("keyforge.issuers.github")

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_REDIRECT_URL = "http://localhost:3000/integrations/github/callback"

# State token lifetime for the install round-trip (10 minutes is plenty for
# the user to click Install and be redirected back).
_STATE_TTL_SECONDS = 600

# GitHub App JWTs expire in <=10 minutes; use 9 minutes for safety.
_APP_JWT_TTL_SECONDS = 540


def _load_private_key(value: Optional[str]) -> Optional[str]:
    """Return the PEM-encoded RSA key, reading from disk if needed.

    If ``value`` starts with ``-----BEGIN`` it is treated as the literal
    key. Otherwise it is treated as a path to a PEM file. Returns ``None``
    if ``value`` is empty.
    """
    if not value:
        return None
    if value.lstrip().startswith("-----BEGIN"):
        return value
    try:
        with open(value, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        logger.warning("Could not read GITHUB_APP_PRIVATE_KEY from path: %s", exc)
        return None


class GitHubIssuer(CredentialIssuer):
    """Issuer backed by a GitHub App."""

    name = "github"
    supports = {"start_oauth", "complete_oauth", "mint_scoped_credential", "revoke"}

    def __init__(self) -> None:
        self.app_id = os.environ.get("GITHUB_APP_ID")
        self.private_key = _load_private_key(os.environ.get("GITHUB_APP_PRIVATE_KEY"))
        self.client_id = os.environ.get("GITHUB_APP_CLIENT_ID")
        self.client_secret = os.environ.get("GITHUB_APP_CLIENT_SECRET")
        self.app_slug = os.environ.get("GITHUB_APP_SLUG") or self.client_id
        self.redirect_url = os.environ.get("GITHUB_APP_INSTALL_REDIRECT_URL", DEFAULT_REDIRECT_URL)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<GitHubIssuer app_id={self.app_id!r} slug={self.app_slug!r} "
            f"private_key={'set' if self.private_key else 'unset'}>"
        )

    # ── Configuration guards ────────────────────────────────────────────

    def _require_configured(self) -> None:
        """Raise IssuerNotSupported if any required env value is missing."""
        missing: List[str] = []
        if not self.app_id:
            missing.append("GITHUB_APP_ID")
        if not self.private_key:
            missing.append("GITHUB_APP_PRIVATE_KEY")
        if not self.client_id:
            missing.append("GITHUB_APP_CLIENT_ID")
        if not self.client_secret:
            missing.append("GITHUB_APP_CLIENT_SECRET")
        if missing:
            raise IssuerNotSupported("GitHub App is not configured; missing env vars: " + ", ".join(missing))

    # ── App JWT helpers ─────────────────────────────────────────────────

    def _build_app_jwt(self) -> str:
        """Return a short-lived RS256 JWT for the configured GitHub App."""
        now = int(time.time())
        payload = {
            # iat back-dated 60s to absorb clock skew (per GitHub docs).
            "iat": now - 60,
            "exp": now + _APP_JWT_TTL_SECONDS,
            "iss": self.app_id,
        }
        try:
            return jwt.encode(payload, self.private_key, algorithm="RS256")
        except JWTError as exc:
            raise IssuerUpstreamError(f"Failed to sign GitHub App JWT: {exc}") from exc

    def _build_state(self, user_id: str) -> str:
        """Return a signed state token that binds an install round-trip to a user."""
        now = int(time.time())
        payload = {
            "user_id": user_id,
            "iat": now,
            "exp": now + _STATE_TTL_SECONDS,
            "purpose": "github_install",
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    def _verify_state(self, state: str, user_id: str) -> None:
        """Decode the state JWT and ensure it matches *user_id* and is unexpired."""
        try:
            payload = jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except JWTError as exc:
            raise IssuerAuthError(f"Invalid GitHub install state: {exc}") from exc
        if payload.get("purpose") != "github_install":
            raise IssuerAuthError("State token has wrong purpose")
        if payload.get("user_id") != user_id:
            raise IssuerAuthError("State token user mismatch")

    # ── Public CredentialIssuer methods ─────────────────────────────────

    async def start_oauth(self, user_id: str, scope: Optional[str] = None) -> str:
        """Return the GitHub App installation URL for *user_id*."""
        self._require_configured()
        state = self._build_state(user_id)
        slug = quote(str(self.app_slug), safe="")
        return f"https://github.com/apps/{slug}/installations/new?state={state}"

    async def complete_oauth(self, user_id: str, code: str, state: Optional[str] = None) -> IssuedCredential:
        """Verify the install round-trip and persist the installation_id.

        ``code`` is the ``installation_id`` GitHub passes back on the
        post-install redirect. We verify the signed state, mint a one-shot
        installation token to confirm GitHub recognises the installation,
        and append the installation id to the user's
        ``github_installations`` array.

        The returned ``IssuedCredential`` represents the *connection*: it
        carries no usable token (per-repo tokens are minted separately
        via ``mint_scoped_credential``) and ``encrypted_value`` is empty.
        """
        self._require_configured()
        if not state:
            raise IssuerAuthError("Missing state parameter on GitHub install callback")
        self._verify_state(state, user_id)

        if not code:
            raise IssuerAuthError("Missing installation_id on GitHub install callback")

        # Confirm the installation exists by minting (and immediately
        # discarding) an installation token for it.
        app_jwt = self._build_app_jwt()
        url = f"{GITHUB_API_BASE}/app/installations/{code}/access_tokens"
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                resp = await http.post(url, headers=headers, json={})
        except httpx.HTTPError as exc:
            raise IssuerUpstreamError(f"GitHub API request failed: {exc}") from exc

        if resp.status_code in (401, 403, 404):
            raise IssuerAuthError(f"GitHub rejected installation_id={code}: {resp.status_code}")
        if resp.status_code >= 400:
            raise IssuerUpstreamError(f"GitHub returned {resp.status_code} for installation lookup")

        # Persist the installation id on the user document. We append-only
        # so a user can install the app on multiple orgs/accounts.
        try:
            await db.users.update_one(
                {"id": user_id},
                {"$addToSet": {"github_installations": str(code)}},
            )
        except Exception as exc:  # noqa: BLE001 - log and continue
            logger.warning("Could not persist github installation id: %s", exc)

        return IssuedCredential(
            issuer=self.name,
            user_id=user_id,
            api_name="github",
            encrypted_value="",
            revocable=False,
            scope="installation",
            metadata={"installation_id": str(code), "kind": "connection"},
        )

    async def mint_scoped_credential(self, user_id: str, scope: Dict[str, Any]) -> IssuedCredential:
        """Mint a fine-grained installation token scoped to a single repo.

        ``scope`` shape::

            {
              "repo": "owner/name",
              "permissions": {"contents": "read", ...},
              "installation_id": "12345"   # optional override
            }

        If ``installation_id`` is not supplied we use the user's most
        recently registered installation.
        """
        self._require_configured()
        repo = scope.get("repo") if isinstance(scope, dict) else None
        if not repo or "/" not in repo:
            raise IssuerAuthError("scope.repo must be 'owner/name'")
        owner, repo_name = repo.split("/", 1)
        if not owner or not repo_name:
            raise IssuerAuthError("scope.repo must be 'owner/name'")

        permissions = scope.get("permissions") or {"contents": "read"}
        if not isinstance(permissions, dict):
            raise IssuerAuthError("scope.permissions must be an object")

        installation_id = scope.get("installation_id")
        if not installation_id:
            user = await db.users.find_one({"id": user_id})
            if not user:
                raise IssuerAuthError(f"User {user_id} not found")
            installations = user.get("github_installations") or []
            if not installations:
                raise IssuerAuthError("User has no GitHub App installations; connect GitHub first")
            installation_id = installations[-1]

        app_jwt = self._build_app_jwt()
        url = f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        body = {
            "repositories": [repo_name],
            "permissions": permissions,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                resp = await http.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise IssuerUpstreamError(f"GitHub API request failed: {exc}") from exc

        if resp.status_code in (401, 403, 404):
            raise IssuerAuthError(f"GitHub rejected token mint for {repo}: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise IssuerUpstreamError(f"GitHub returned {resp.status_code} on token mint")

        try:
            payload = resp.json()
        except ValueError as exc:
            raise IssuerUpstreamError("GitHub returned a non-JSON token response") from exc

        token = payload.get("token")
        if not token:
            raise IssuerUpstreamError("GitHub response missing 'token' field")

        expires_at: Optional[datetime] = None
        expires_at_str = payload.get("expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            except ValueError:
                expires_at = None

        encrypted = encrypt_api_key(token)
        # Best-effort: drop the plaintext reference so it isn't lingering.
        token = None  # noqa: F841 - intentional clear

        return IssuedCredential(
            issuer=self.name,
            user_id=user_id,
            api_name="github",
            encrypted_value=encrypted,
            expires_at=expires_at,
            revocable=True,
            scope=f"repo:{repo}",
            metadata={
                "installation_id": str(installation_id),
                "repo": repo,
                "permissions": permissions,
            },
        )

    async def revoke(self, credential_id: str) -> None:
        """Best-effort revocation of a previously minted installation token.

        Looks up the credential, decrypts its token, and calls
        ``DELETE /installation/token`` against the GitHub API. Per the
        ABC contract, expected upstream failures (already revoked, 401)
        are logged and swallowed; only catastrophic problems propagate
        as ``IssuerUpstreamError``.
        """
        self._require_configured()
        from backend.security import decrypt_api_key  # local import to avoid cycles

        cred = await db.credentials.find_one({"id": credential_id})
        if not cred:
            logger.info("Revoke skipped: credential %s not found", credential_id)
            return
        encrypted = cred.get("api_key") or cred.get("api_key_encrypted")
        if not encrypted:
            logger.info("Revoke skipped: credential %s has no token", credential_id)
            return

        token = decrypt_api_key(encrypted)
        if not token or token == "[decryption failed]":
            logger.info("Revoke skipped: credential %s could not be decrypted", credential_id)
            return

        url = f"{GITHUB_API_BASE}/installation/token"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                resp = await http.delete(url, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("GitHub revoke request failed: %s", exc)
            return
        finally:
            token = None  # noqa: F841 - intentional clear

        if resp.status_code in (204, 401, 403, 404):
            # 204 = revoked; 401/403/404 = already invalid. All terminal,
            # all fine; swallow per the ABC contract.
            return
        if resp.status_code >= 500:
            raise IssuerUpstreamError(f"GitHub returned {resp.status_code} on revoke")
        # Any other 4xx is logged but not raised; the upstream told us no.
        logger.warning(
            "GitHub revoke for credential %s returned %s",
            credential_id,
            resp.status_code,
        )


# Register a singleton instance at import time. The instance is built
# even when env is unset; methods raise IssuerNotSupported lazily.
register_issuer("github", GitHubIssuer())

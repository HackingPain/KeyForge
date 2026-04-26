"""Tests for the GitHub credential issuer (backend.issuers.github) and its
HTTP route surface (backend.routes.issuers_github).

The orchestrator wires the GitHub router into ``backend.server`` in a
final pass to avoid merge conflicts. Until that lands, the HTTP-level
tests in this file mount the router onto the shared test ``app``
themselves.
"""

from __future__ import annotations

# Shared test helpers must be imported FIRST so ENCRYPTION_KEY / JWT_SECRET
# are set before any backend module loads. Order is load-bearing.
from tests._test_helpers import MOCK_DB, app, make_token  # isort: skip

import importlib  # isort: skip
import os  # isort: skip
import time  # isort: skip
from datetime import datetime, timezone  # isort: skip
from typing import Any, Dict, Optional  # isort: skip
from unittest.mock import AsyncMock, MagicMock, patch  # isort: skip

import pytest  # isort: skip
from fastapi.testclient import TestClient  # isort: skip
from jose import jwt as jose_jwt  # isort: skip


# Generate a fresh 2048-bit RSA key per test session. The key never leaves the
# test process; httpx is mocked in every path that would hit GitHub.
def _generate_test_rsa_key() -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode()


TEST_RSA_PRIVATE_KEY = _generate_test_rsa_key()


@pytest.fixture
def github_env(monkeypatch):
    """Configure GitHub App env vars for tests that need them."""
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", TEST_RSA_PRIVATE_KEY)
    monkeypatch.setenv("GITHUB_APP_CLIENT_ID", "Iv1.fake_client_id")
    monkeypatch.setenv("GITHUB_APP_CLIENT_SECRET", "fake_secret")
    monkeypatch.setenv("GITHUB_APP_SLUG", "keyforge-test")
    yield


@pytest.fixture
def issuer(github_env):
    """Return a freshly configured GitHubIssuer instance."""
    # Re-import so __init__ picks up the env vars set above.
    from backend.issuers import github as gh_module

    importlib.reload(gh_module)
    instance = gh_module.GitHubIssuer()
    yield instance
    # Restore the module-level singleton for downstream tests.
    importlib.reload(gh_module)


@pytest.fixture
def unconfigured_issuer(monkeypatch):
    """Return a GitHubIssuer with no env configured."""
    for name in (
        "GITHUB_APP_ID",
        "GITHUB_APP_PRIVATE_KEY",
        "GITHUB_APP_CLIENT_ID",
        "GITHUB_APP_CLIENT_SECRET",
        "GITHUB_APP_SLUG",
    ):
        monkeypatch.delenv(name, raising=False)
    from backend.issuers import github as gh_module

    importlib.reload(gh_module)
    instance = gh_module.GitHubIssuer()
    yield instance
    importlib.reload(gh_module)


def _make_response(status_code: int = 200, json_body: Optional[Dict[str, Any]] = None):
    """Return a MagicMock that walks like an httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_body or {})
    return resp


class _FakeAsyncClient:
    """Minimal async-context-manager stand-in for httpx.AsyncClient."""

    def __init__(self, response, capture: Dict[str, Any]):
        self._response = response
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, headers=None, json=None):
        self._capture["method"] = "POST"
        self._capture["url"] = url
        self._capture["headers"] = headers or {}
        self._capture["json"] = json
        return self._response

    async def delete(self, url, headers=None):
        self._capture["method"] = "DELETE"
        self._capture["url"] = url
        self._capture["headers"] = headers or {}
        return self._response


def _client_factory(response, capture: Dict[str, Any]):
    """Return a callable that ignores its kwargs and yields _FakeAsyncClient."""

    def _factory(*args, **kwargs):
        return _FakeAsyncClient(response, capture)

    return _factory


# ── Issuer-level tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unconfigured_raises_IssuerNotSupported(unconfigured_issuer):
    """Every method must raise IssuerNotSupported when env is missing."""
    from backend.issuers import IssuerNotSupported

    with pytest.raises(IssuerNotSupported):
        await unconfigured_issuer.start_oauth(user_id="u1")
    with pytest.raises(IssuerNotSupported):
        await unconfigured_issuer.complete_oauth(user_id="u1", code="123", state="x")
    with pytest.raises(IssuerNotSupported):
        await unconfigured_issuer.mint_scoped_credential(user_id="u1", scope={"repo": "a/b"})
    with pytest.raises(IssuerNotSupported):
        await unconfigured_issuer.revoke(credential_id="c1")


@pytest.mark.asyncio
async def test_start_oauth_returns_install_url_with_state(issuer):
    url = await issuer.start_oauth(user_id="u1")
    assert url.startswith("https://github.com/apps/keyforge-test/installations/new?state=")
    state = url.split("state=", 1)[1]
    payload = jose_jwt.decode(state, os.environ["JWT_SECRET"], algorithms=["HS256"])
    assert payload["user_id"] == "u1"
    assert payload["purpose"] == "github_install"
    assert payload["exp"] > int(time.time())


@pytest.mark.asyncio
async def test_complete_oauth_invalid_state_raises_IssuerAuthError(issuer):
    from backend.issuers import IssuerAuthError

    bad_state = jose_jwt.encode(
        {"user_id": "someone-else", "exp": int(time.time()) + 600, "purpose": "github_install"},
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )
    with pytest.raises(IssuerAuthError):
        await issuer.complete_oauth(user_id="u1", code="42", state=bad_state)


@pytest.mark.asyncio
async def test_complete_oauth_stores_installation(issuer):
    """complete_oauth confirms the installation upstream and persists the id."""
    state = await issuer.start_oauth(user_id="u1")
    state_token = state.split("state=", 1)[1]

    captured: Dict[str, Any] = {}
    response = _make_response(201, {"token": "ghs_fake", "expires_at": "2026-01-01T00:00:00Z"})
    MOCK_DB.users.update_one = AsyncMock()

    with patch("backend.issuers.github.httpx.AsyncClient", side_effect=_client_factory(response, captured)):
        cred = await issuer.complete_oauth(user_id="u1", code="555", state=state_token)

    # The installation_id was upserted onto the user document.
    assert MOCK_DB.users.update_one.await_count == 1
    args, kwargs = MOCK_DB.users.update_one.await_args
    assert args[0] == {"id": "u1"}
    assert args[1] == {"$addToSet": {"github_installations": "555"}}

    # The returned IssuedCredential is a connection marker, not a token.
    assert cred.issuer == "github"
    assert cred.user_id == "u1"
    assert cred.encrypted_value == ""
    assert cred.metadata["installation_id"] == "555"
    assert "555" in captured["url"]


@pytest.mark.asyncio
async def test_mint_returns_IssuedCredential(issuer):
    """mint_scoped_credential calls GitHub, encrypts the token, returns it."""
    MOCK_DB.users.find_one = AsyncMock(return_value={"id": "u1", "github_installations": ["999"]})
    captured: Dict[str, Any] = {}
    response = _make_response(
        201,
        {
            "token": "ghs_super_secret_token",
            "expires_at": "2030-01-01T00:00:00Z",
            "permissions": {"contents": "read"},
        },
    )

    with patch("backend.issuers.github.httpx.AsyncClient", side_effect=_client_factory(response, captured)):
        cred = await issuer.mint_scoped_credential(
            user_id="u1",
            scope={"repo": "acme/widgets", "permissions": {"contents": "read"}},
        )

    assert cred.issuer == "github"
    assert cred.user_id == "u1"
    assert cred.scope == "repo:acme/widgets"
    assert cred.revocable is True
    # Encrypted value present, plaintext NOT present anywhere on the model.
    assert cred.encrypted_value
    assert "ghs_super_secret_token" not in cred.encrypted_value

    # Decrypts back to the plaintext via the project's Fernet helper.
    from backend.security import decrypt_api_key

    assert decrypt_api_key(cred.encrypted_value) == "ghs_super_secret_token"

    # Body sent to GitHub had the right shape.
    assert captured["json"]["repositories"] == ["widgets"]
    assert captured["json"]["permissions"] == {"contents": "read"}
    assert "999" in captured["url"]


@pytest.mark.asyncio
async def test_revoke_calls_delete_token(issuer):
    """revoke decrypts the credential and DELETEs against GitHub."""
    from backend.security import encrypt_api_key

    cred_doc = {
        "id": "cred-1",
        "api_key": encrypt_api_key("ghs_token_to_revoke"),
        "user_id": "u1",
    }
    MOCK_DB.credentials.find_one = AsyncMock(return_value=cred_doc)

    captured: Dict[str, Any] = {}
    response = _make_response(204)
    with patch("backend.issuers.github.httpx.AsyncClient", side_effect=_client_factory(response, captured)):
        await issuer.revoke(credential_id="cred-1")

    assert captured["method"] == "DELETE"
    assert captured["url"].endswith("/installation/token")
    assert captured["headers"]["Authorization"].startswith("token ")


# ── Route-level tests ───────────────────────────────────────────────────


_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_ROUTE_USER = {
    "_id": "mongo-oid",
    "id": "user-gh-1",
    "username": "ghuser",
    "hashed_password": "irrelevant",
    "created_at": _NOW,
}


def _bearer_headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {make_token('ghuser')}"}


@pytest.fixture
def wired_app(github_env):
    """Mount the issuers_github router onto the shared test app once."""
    import backend.routes.issuers_github as gh_routes_mod

    importlib.reload(gh_routes_mod)
    # Avoid double-mounting if the test session imports the module twice.
    already_mounted = any(getattr(r, "path", "") == "/api/issuers/github/start" for r in app.router.routes)
    if not already_mounted:
        app.include_router(gh_routes_mod.router)
    yield gh_routes_mod
    # Patch db reference on the route module to use MOCK_DB regardless.


@pytest.fixture
def auth_setup():
    MOCK_DB.users.find_one = AsyncMock(return_value=_ROUTE_USER)
    yield


def test_route_post_start_returns_install_url(wired_app, auth_setup):
    """POST /api/issuers/github/start returns the install URL when authenticated."""
    # Patch the route's db reference to MOCK_DB in case it bound to the real one.
    wired_app.db = MOCK_DB

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/issuers/github/start", headers=_bearer_headers())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["install_url"].startswith("https://github.com/apps/keyforge-test/installations/new")
    assert "state=" in body["install_url"]


def test_route_post_start_requires_auth(wired_app):
    """Bearer-only requests bypass CSRF; an invalid bearer must yield 401."""
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/issuers/github/start",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


def test_route_post_mint_persists_credential(wired_app, auth_setup):
    """POST /api/issuers/github/mint persists the minted credential."""
    wired_app.db = MOCK_DB

    # Stub the issuer so we don't hit the live GitHub API path.
    from backend.issuers import github as gh_module
    from backend.issuers.base import IssuedCredential

    fake_issued = IssuedCredential(
        issuer="github",
        user_id=_ROUTE_USER["id"],
        api_name="github",
        encrypted_value="ZW5jcnlwdGVkLWZha2U=",
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        revocable=True,
        scope="repo:acme/widgets",
        metadata={"repo": "acme/widgets", "installation_id": "999"},
    )

    insert_calls = []

    async def fake_insert_one(doc):
        insert_calls.append(doc)
        return MagicMock(inserted_id="ignored")

    MOCK_DB.credentials.insert_one = fake_insert_one

    async def fake_mint(self, user_id, scope):
        assert user_id == _ROUTE_USER["id"]
        assert scope["repo"] == "acme/widgets"
        return fake_issued

    with patch.object(gh_module.GitHubIssuer, "mint_scoped_credential", new=fake_mint):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/issuers/github/mint",
            headers=_bearer_headers(),
            json={"repo": "acme/widgets", "permissions": {"contents": "read"}},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["issuer"] == "github"
    assert body["scope"] == "repo:acme/widgets"
    assert body["revocable"] is True
    # Plaintext is NOT returned by default.
    assert body.get("plaintext_value") is None

    assert len(insert_calls) == 1
    inserted = insert_calls[0]
    assert inserted["user_id"] == _ROUTE_USER["id"]
    assert inserted["api_name"] == "github"
    assert inserted["issuer"] == "github"
    assert inserted["scope"] == "repo:acme/widgets"
    assert inserted["revocable"] is True

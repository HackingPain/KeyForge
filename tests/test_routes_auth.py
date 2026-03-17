"""Integration tests for authentication routes (/api/auth/*)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from tests._test_helpers import MOCK_DB, app, make_token


# Stored user document returned by find_one for login / me
_FAKE_USER_DOC = {
    "_id": "mongo-object-id",
    "id": "test-user-id",
    "username": "testuser",
    "hashed_password": "",  # replaced per-test where needed
    "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
}


# ── Registration tests ────────────────────────────────────────────────────


class TestRegister:
    """POST /api/auth/register"""

    def test_register_success(self):
        """Successful registration returns 200 with user data."""
        MOCK_DB.users.find_one = AsyncMock(return_value=None)
        MOCK_DB.users.insert_one = AsyncMock()

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/auth/register",
            json={"username": "newuser", "password": "strongpassword"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "newuser"
        assert "id" in body
        assert "created_at" in body
        MOCK_DB.users.insert_one.assert_called_once()

    def test_register_duplicate_username(self):
        """Duplicate username returns 400."""
        MOCK_DB.users.find_one = AsyncMock(return_value=_FAKE_USER_DOC)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/auth/register",
            json={"username": "testuser", "password": "strongpassword"},
        )
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"].lower()

    def test_register_short_username(self):
        """Username shorter than 3 characters returns 422 validation error."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/auth/register",
            json={"username": "ab", "password": "strongpassword"},
        )
        assert resp.status_code == 422

    def test_register_short_password(self):
        """Password shorter than 8 characters returns 422 validation error."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/auth/register",
            json={"username": "validuser", "password": "short"},
        )
        assert resp.status_code == 422


# ── Login tests ───────────────────────────────────────────────────────────


class TestLogin:
    """POST /api/auth/login"""

    def test_login_success(self):
        """Successful login returns an access_token."""
        from backend.security import hash_password
        hashed = hash_password("correctpassword")
        user_doc = {**_FAKE_USER_DOC, "hashed_password": hashed}
        MOCK_DB.users.find_one = AsyncMock(return_value=user_doc)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/auth/login",
            data={"username": "testuser", "password": "correctpassword"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_wrong_password(self):
        """Wrong password returns 401."""
        from backend.security import hash_password
        hashed = hash_password("correctpassword")
        user_doc = {**_FAKE_USER_DOC, "hashed_password": hashed}
        MOCK_DB.users.find_one = AsyncMock(return_value=user_doc)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/auth/login",
            data={"username": "testuser", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self):
        """Non-existent user returns 401."""
        MOCK_DB.users.find_one = AsyncMock(return_value=None)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/auth/login",
            data={"username": "ghost", "password": "anypassword"},
        )
        assert resp.status_code == 401


# ── /me tests ─────────────────────────────────────────────────────────────


class TestMe:
    """GET /api/auth/me"""

    def test_me_valid_token(self):
        """Valid token returns current user info."""
        user_doc = {**_FAKE_USER_DOC}
        MOCK_DB.users.find_one = AsyncMock(return_value=user_doc)

        token = make_token("testuser")
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "testuser"
        assert body["id"] == "test-user-id"

    def test_me_no_token(self):
        """Missing token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self):
        """Invalid / garbage token returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer not-a-real-jwt-token"},
        )
        assert resp.status_code == 401

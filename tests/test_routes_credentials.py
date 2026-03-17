"""Integration tests for credential management routes (/api/credentials/*)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from tests._test_helpers import MOCK_DB, app, make_token

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)

_AUTH_USER = {
    "_id": "mongo-oid",
    "id": "user-123",
    "username": "creduser",
    "hashed_password": "irrelevant-for-bearer",
    "created_at": _NOW,
}


def _auth_headers():
    token = make_token("creduser")
    return {"Authorization": f"Bearer {token}"}


def _setup_auth():
    """Configure mock so that get_current_user succeeds."""
    MOCK_DB.users.find_one = AsyncMock(return_value=_AUTH_USER)


# ---------------------------------------------------------------------------
# Fake credential documents
# ---------------------------------------------------------------------------

def _fake_cred_doc(cred_id="cred-1", user_id="user-123", api_name="openai"):
    from backend.security import encrypt_api_key
    encrypted = encrypt_api_key("sk-testapikey1234567890abcdefghijklmnopqrst")
    return {
        "id": cred_id,
        "user_id": user_id,
        "api_name": api_name,
        "api_key": encrypted,
        "status": "format_valid",
        "last_tested": _NOW,
        "environment": "development",
        "created_at": _NOW,
    }


# ── Create credential ─────────────────────────────────────────────────────


class TestCreateCredential:
    """POST /api/credentials"""

    def test_create_credential_success(self):
        _setup_auth()
        MOCK_DB.credentials.insert_one = AsyncMock()

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/credentials",
            json={
                "api_name": "openai",
                "api_key": "sk-testapikey1234567890abcdefghijklmnopqrst",
                "environment": "development",
            },
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["api_name"] == "openai"
        assert "id" in body
        assert body["environment"] == "development"
        # The preview should be masked
        assert body["api_key_preview"].startswith("****")
        assert len(body["api_key_preview"]) <= 8
        MOCK_DB.credentials.insert_one.assert_called_once()

    def test_create_credential_invalid_api_name(self):
        """Invalid api_name returns 422 validation error."""
        _setup_auth()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/credentials",
            json={
                "api_name": "not_a_real_provider",
                "api_key": "some-key-value-here",
                "environment": "development",
            },
            headers=_auth_headers(),
        )
        assert resp.status_code == 422


# ── List credentials ──────────────────────────────────────────────────────


class TestListCredentials:
    """GET /api/credentials"""

    def test_list_returns_own_credentials(self):
        """Returns only the authenticated user's credentials."""
        _setup_auth()
        cred = _fake_cred_doc(cred_id="cred-1", user_id="user-123")

        # Mock the chained .find().skip().limit().to_list() call
        cursor = MagicMock()
        cursor.skip = MagicMock(return_value=cursor)
        cursor.limit = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=[cred])
        MOCK_DB.credentials.find = MagicMock(return_value=cursor)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/credentials", headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["api_name"] == "openai"

        # Verify the query filtered by user_id
        MOCK_DB.credentials.find.assert_called_once_with({"user_id": "user-123"})


# ── Get single credential ────────────────────────────────────────────────


class TestGetCredential:
    """GET /api/credentials/{id}"""

    def test_get_existing_credential(self):
        _setup_auth()
        cred = _fake_cred_doc()
        MOCK_DB.credentials.find_one = AsyncMock(return_value=cred)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/credentials/cred-1", headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "cred-1"
        assert body["api_name"] == "openai"

    def test_get_nonexistent_credential(self):
        _setup_auth()
        MOCK_DB.credentials.find_one = AsyncMock(return_value=None)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/credentials/does-not-exist", headers=_auth_headers())
        assert resp.status_code == 404


# ── Delete credential ─────────────────────────────────────────────────────


class TestDeleteCredential:
    """DELETE /api/credentials/{id}"""

    def test_delete_success(self):
        _setup_auth()
        delete_result = MagicMock()
        delete_result.deleted_count = 1
        MOCK_DB.credentials.delete_one = AsyncMock(return_value=delete_result)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.delete("/api/credentials/cred-1", headers=_auth_headers())
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()


# ── Test credential ───────────────────────────────────────────────────────


class TestTestCredential:
    """POST /api/credentials/{id}/test"""

    def test_returns_validation_result(self):
        _setup_auth()
        cred = _fake_cred_doc()
        MOCK_DB.credentials.find_one = AsyncMock(return_value=cred)
        MOCK_DB.credentials.update_one = AsyncMock()

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/credentials/cred-1/test", headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert "credential_id" in body
        assert "test_result" in body
        assert "status" in body["test_result"]


# ── Masking / security assertions ─────────────────────────────────────────


class TestCredentialSecurity:
    """Verify that API keys are properly masked and encrypted keys never leak."""

    def test_preview_shows_only_last_four(self):
        """api_key_preview must show at most the last 4 characters after ****."""
        _setup_auth()
        MOCK_DB.credentials.insert_one = AsyncMock()

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/credentials",
            json={
                "api_name": "stripe",
                "api_key": "sk_test_abcdefghijklmnopqrstuvwx",
                "environment": "production",
            },
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        preview = resp.json()["api_key_preview"]
        # Preview format: "****" + last 4 chars
        assert preview.startswith("****")
        visible_part = preview.replace("****", "")
        assert len(visible_part) == 4
        assert visible_part == "uvwx"

    def test_encrypted_key_never_in_response(self):
        """The raw encrypted key must never appear in any credential response."""
        _setup_auth()
        cred = _fake_cred_doc()
        encrypted_value = cred["api_key"]  # the Fernet token
        MOCK_DB.credentials.find_one = AsyncMock(return_value=cred)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/credentials/cred-1", headers=_auth_headers())
        assert resp.status_code == 200
        raw_text = resp.text
        # The Fernet-encrypted key (starts with 'gAAAAA') must not appear
        assert encrypted_value not in raw_text
        # Nor should the plaintext key
        assert "sk-testapikey1234567890abcdefghijklmnopqrst" not in raw_text

    def test_list_does_not_leak_encrypted_keys(self):
        """Listing credentials must not include raw encrypted keys."""
        _setup_auth()
        cred = _fake_cred_doc()
        encrypted_value = cred["api_key"]

        cursor = MagicMock()
        cursor.skip = MagicMock(return_value=cursor)
        cursor.limit = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=[cred])
        MOCK_DB.credentials.find = MagicMock(return_value=cursor)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/credentials", headers=_auth_headers())
        assert resp.status_code == 200
        raw_text = resp.text
        assert encrypted_value not in raw_text

"""Integration tests for dashboard routes (/api/dashboard/*, /api/api-catalog)."""

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
    "id": "user-dash-1",
    "username": "dashuser",
    "hashed_password": "x",
    "created_at": _NOW,
}


def _auth_headers():
    token = make_token("dashuser")
    return {"Authorization": f"Bearer {token}"}


def _setup_auth():
    MOCK_DB.users.find_one = AsyncMock(return_value=_AUTH_USER)


# ── Dashboard overview ────────────────────────────────────────────────────


class TestDashboardOverview:
    """GET /api/dashboard/overview"""

    def test_returns_stats_structure(self):
        """Overview returns expected keys: total_credentials, status_breakdown,
        health_score, recent_analyses, recommendations."""
        _setup_auth()

        # Mock credentials.find().to_list()
        creds_cursor = MagicMock()
        creds_cursor.to_list = AsyncMock(return_value=[
            {"status": "active", "user_id": "user-dash-1"},
            {"status": "active", "user_id": "user-dash-1"},
            {"status": "invalid", "user_id": "user-dash-1"},
        ])
        MOCK_DB.credentials.find = MagicMock(return_value=creds_cursor)

        # Mock project_analyses.find().sort().limit().to_list()
        analyses_cursor = MagicMock()
        analyses_cursor.sort = MagicMock(return_value=analyses_cursor)
        analyses_cursor.limit = MagicMock(return_value=analyses_cursor)
        analyses_cursor.to_list = AsyncMock(return_value=[])
        MOCK_DB.project_analyses.find = MagicMock(return_value=analyses_cursor)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/dashboard/overview", headers=_auth_headers())
        assert resp.status_code == 200

        body = resp.json()
        assert "total_credentials" in body
        assert body["total_credentials"] == 3
        assert "status_breakdown" in body
        assert body["status_breakdown"]["active"] == 2
        assert body["status_breakdown"]["invalid"] == 1
        assert "health_score" in body
        assert isinstance(body["health_score"], (int, float))
        assert "recent_analyses" in body
        assert isinstance(body["recent_analyses"], list)
        assert "recommendations" in body
        assert isinstance(body["recommendations"], list)

    def test_overview_requires_auth(self):
        """Unauthenticated request returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/dashboard/overview")
        assert resp.status_code == 401


# ── API Catalog ───────────────────────────────────────────────────────────


class TestAPICatalog:
    """GET /api/api-catalog"""

    def test_returns_catalog_list(self):
        """Catalog returns a list of APIs with expected fields."""
        _setup_auth()

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/api-catalog", headers=_auth_headers())
        assert resp.status_code == 200

        body = resp.json()
        assert "apis" in body
        assert "total" in body
        assert isinstance(body["apis"], list)
        assert body["total"] > 0

        # Each catalog entry should have required fields
        first = body["apis"][0]
        assert "id" in first
        assert "name" in first
        assert "category" in first
        assert "auth_type" in first

    def test_catalog_requires_auth(self):
        """Unauthenticated request returns 401."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/api-catalog")
        assert resp.status_code == 401

"""Integration tests for health and root endpoints."""

import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from tests._test_helpers import MOCK_DB, app


# ── Root endpoint ─────────────────────────────────────────────────────────


class TestRoot:
    """GET /api/"""

    def test_root_returns_version_info(self):
        """Root endpoint returns message and version."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/")
        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body
        assert "version" in body
        assert "KeyForge" in body["message"]
        assert body["version"] == "4.0.0"


# ── Health check endpoint ────────────────────────────────────────────────


class TestHealthCheck:
    """GET /api/health"""

    def test_health_healthy(self):
        """When DB ping succeeds, status is healthy."""
        MOCK_DB.command = AsyncMock(return_value={"ok": 1})

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["database"] == "connected"

    def test_health_degraded(self):
        """When DB ping fails, status is degraded."""
        MOCK_DB.command = AsyncMock(side_effect=Exception("connection refused"))

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["database"] == "disconnected"

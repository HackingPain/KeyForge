"""Shared test helpers: mock database, app instance, auth utilities.

All integration test modules should import from here to ensure a single
MOCK_DB is used across the entire test run, avoiding conflicts when
multiple test files patch the same route modules.
"""

import os

# Force-set env vars before any backend module is imported.
# The existing conftest.py uses setdefault with an invalid Fernet key,
# so we must override it.
os.environ["MONGO_URL"] = "mongodb://localhost:27017"
os.environ["DB_NAME"] = "keyforge_test"
os.environ["ENCRYPTION_KEY"] = "Sx_Zd9AEzXhJz22Qzq5fSPb2KYXjnIJ2ZdIjk1aiQyY="
os.environ["JWT_SECRET"] = "test-jwt-secret-for-unit-tests"

from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone


def _make_mock_db():
    """Return a MagicMock that mimics the Motor database interface."""
    mock_db = MagicMock()
    for coll_name in [
        "users", "credentials", "project_analyses", "rotation_policies",
        "audit_log", "health_check_results", "health_check_schedules",
        "teams", "team_members", "credential_groups", "scan_results",
        "webhooks", "ip_allowlist", "sessions", "credential_expirations",
        "credential_permissions", "credential_versions",
        "auto_rotation_configs", "breach_checks", "usage_events",
        "compliance_reports", "lifecycle_events",
    ]:
        coll = MagicMock()
        coll.find_one = AsyncMock(return_value=None)
        coll.insert_one = AsyncMock()
        coll.update_one = AsyncMock()
        coll.delete_one = AsyncMock()
        coll.create_index = AsyncMock()
        setattr(mock_db, coll_name, coll)
    mock_db.command = AsyncMock(return_value={"ok": 1})
    return mock_db


# Single shared mock — every test module uses this same instance.
MOCK_DB = _make_mock_db()


def patch_all_db_refs():
    """Replace the `db` attribute on every module that imported it from config."""
    import backend.config
    import backend.security
    import backend.routes.auth
    import backend.routes.credentials
    import backend.routes.dashboard
    import backend.routes.projects
    backend.config.db = MOCK_DB
    backend.security.db = MOCK_DB
    backend.routes.auth.db = MOCK_DB
    backend.routes.credentials.db = MOCK_DB
    backend.routes.dashboard.db = MOCK_DB
    backend.routes.projects.db = MOCK_DB


patch_all_db_refs()

# Import app AFTER patching so the lifespan uses our mock
from backend.server import app  # noqa: E402


def make_token(username="testuser"):
    """Create a valid JWT for testing authenticated endpoints."""
    from backend.security import create_access_token
    return create_access_token({"sub": username})

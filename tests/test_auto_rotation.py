"""Integration tests for auto-rotation trigger via the issuer interface.

These tests drive POST /api/auto-rotation/{config_id}/trigger end to end,
substituting an in-memory FakeIssuer for the real provider integrations so
no upstream call is ever made. The trigger route is the load-bearing piece
of Tier 2.5: it replaces the prior ``status="simulated"`` stub with a real
call into ``CredentialIssuer.mint_scoped_credential``.
"""

# tests/_test_helpers.py sets ENCRYPTION_KEY/JWT_SECRET to valid values and
# patches the global db; it must be imported BEFORE any backend module so the
# Fernet/JWT singletons in backend.security pick up the test values.
from tests._test_helpers import MOCK_DB, app, make_token  # isort: skip  # noqa: I001,E402

from datetime import datetime, timedelta, timezone  # noqa: E402
from typing import Any, Dict, Optional  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend import audit as audit_module  # noqa: E402
from backend.audit import integrity as integrity_module  # noqa: E402
from backend.issuers import (  # noqa: E402
    CredentialIssuer,
    IssuedCredential,
    IssuerAuthError,
    IssuerUpstreamError,
    register_issuer,
)
from backend.issuers import registry as registry_module  # noqa: E402
from backend.routes import auto_rotation as auto_rotation_module  # noqa: E402

# -- Auth fixtures ----------------------------------------------------------

_NOW = datetime(2026, 1, 15, tzinfo=timezone.utc)

_AUTH_USER = {
    "_id": "mongo-oid",
    "id": "user-123",
    "username": "rotuser",
    "hashed_password": "irrelevant-for-bearer",
    "created_at": _NOW,
}


def _auth_headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {make_token('rotuser')}"}


# -- Fake issuers -----------------------------------------------------------


class _DeterministicIssuer(CredentialIssuer):
    """Mints a deterministic IssuedCredential. Mirrors the FakeIssuer in
    tests/test_issuers_interface.py but lives here so the auto-rotation tests
    are self-contained.
    """

    name = "fake_rotator"
    supports = {"mint_scoped_credential"}

    async def mint_scoped_credential(self, user_id: str, scope: Dict[str, Any]) -> IssuedCredential:
        return IssuedCredential(
            issuer=self.name,
            user_id=user_id,
            api_name="fake_rotator_cred",
            encrypted_value="enc::rotated::value",
            issued_at=datetime(2026, 1, 16, tzinfo=timezone.utc),
            expires_at=datetime(2026, 4, 16, tzinfo=timezone.utc),
            revocable=True,
            scope=str(scope.get("repo", "default")),
            metadata={"flow": "mint", "scope": scope},
        )


class _OAuthOnlyIssuer(CredentialIssuer):
    """Implements only start_oauth/complete_oauth, no mint."""

    name = "fake_oauth_only"
    supports = {"start_oauth"}

    async def start_oauth(self, user_id: str, scope: Optional[str] = None) -> str:
        return "https://example.invalid/oauth"


class _AuthErrorIssuer(CredentialIssuer):
    name = "fake_auth_error"
    supports = {"mint_scoped_credential"}

    async def mint_scoped_credential(self, user_id: str, scope: Dict[str, Any]) -> IssuedCredential:
        raise IssuerAuthError("upstream rejected the grant")


class _UpstreamErrorIssuer(CredentialIssuer):
    name = "fake_upstream_error"
    supports = {"mint_scoped_credential"}

    async def mint_scoped_credential(self, user_id: str, scope: Dict[str, Any]) -> IssuedCredential:
        raise IssuerUpstreamError("upstream 503")


# -- Helpers ----------------------------------------------------------------


def _config_doc(
    config_id: str = "cfg-1",
    credential_id: str = "cred-1",
    user_id: str = "user-123",
    provider: str = "github",
    enabled: bool = True,
) -> Dict[str, Any]:
    return {
        "id": config_id,
        "credential_id": credential_id,
        "user_id": user_id,
        "provider": provider,
        "rotation_interval_days": 7,
        "last_rotated": None,
        "next_rotation": _NOW + timedelta(days=7),
        "enabled": enabled,
        "created_at": _NOW,
    }


def _credential_doc(
    cred_id: str = "cred-1",
    user_id: str = "user-123",
    api_name: str = "github",
    issuer: Optional[str] = "fake_rotator",
    encrypted_value: str = "enc::original::value",
) -> Dict[str, Any]:
    return {
        "id": cred_id,
        "user_id": user_id,
        "api_name": api_name,
        "api_key": encrypted_value,
        "status": "active",
        "environment": "development",
        "created_at": _NOW,
        "issuer": issuer,
        "issued_at": _NOW,
        "revocable": True,
        "scope": "owner/repo",
    }


def _wire_mongo_for_trigger(
    config: Dict[str, Any],
    credential: Dict[str, Any],
    existing_versions: Optional[list] = None,
) -> None:
    """Configure MOCK_DB so a single trigger call sees a clean state.

    Each call to find_one / find returns the same documents the test set up,
    and the various write methods are AsyncMocks the test can introspect.
    """
    MOCK_DB.users.find_one = AsyncMock(return_value=_AUTH_USER)

    auto_rotation_module.db = MOCK_DB
    integrity_module_db_target = integrity_module
    # AuditIntegrity.create_audit_entry takes db as a parameter and the route
    # passes ``backend.routes.auto_rotation.db`` in. Patching that module's
    # ``db`` attribute is what test_helpers does at import time.
    del integrity_module_db_target  # silence unused-warning

    async def _config_find_one(query):
        if query.get("id") == config["id"] and query.get("user_id") == config["user_id"]:
            return config
        return None

    MOCK_DB.auto_rotation_configs.find_one = AsyncMock(side_effect=_config_find_one)
    MOCK_DB.auto_rotation_configs.update_one = AsyncMock()

    async def _cred_find_one(query):
        if query.get("id") == credential["id"]:
            return credential
        return None

    MOCK_DB.credentials.find_one = AsyncMock(side_effect=_cred_find_one)
    MOCK_DB.credentials.update_one = AsyncMock()

    versions = existing_versions or []
    versions_cursor = MagicMock()
    versions_cursor.sort = MagicMock(return_value=versions_cursor)
    versions_cursor.to_list = AsyncMock(return_value=versions)
    MOCK_DB.credential_versions.find = MagicMock(return_value=versions_cursor)
    MOCK_DB.credential_versions.update_many = AsyncMock()
    MOCK_DB.credential_versions.insert_one = AsyncMock()

    # Audit log: the integrity helper looks up the most recent entry to chain
    # from. Returning None makes the entry chain off the genesis hash.
    MOCK_DB.audit_log.find_one = AsyncMock(return_value=None)
    MOCK_DB.audit_log.insert_one = AsyncMock()


@pytest.fixture(autouse=True)
def _reset_issuer_registry():
    """Issuer registry is a process-global; clear it between tests."""
    registry_module._REGISTRY.clear()
    yield
    registry_module._REGISTRY.clear()


# -- Tests ------------------------------------------------------------------


class TestRotationLegacyCredential:
    def test_rotation_skips_legacy_credential_without_issuer(self):
        """A credential with issuer=None is a legacy paste-key record; skip it."""
        cfg = _config_doc()
        cred = _credential_doc(issuer=None)
        _wire_mongo_for_trigger(cfg, cred)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(f"/api/auto-rotation/{cfg['id']}/trigger", headers=_auth_headers())

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "skipped_no_issuer"
        assert "manual rotation required" in body["reason"]

        # Encrypted value untouched.
        MOCK_DB.credentials.update_one.assert_not_called()
        MOCK_DB.credential_versions.insert_one.assert_not_called()


class TestRotationCallsIssuer:
    def test_rotation_calls_issuer_mint_and_updates_credential(self):
        """Happy path: registered issuer mints a new value, credential is updated."""
        register_issuer("fake_rotator", _DeterministicIssuer())

        cfg = _config_doc()
        cred = _credential_doc(issuer="fake_rotator")
        _wire_mongo_for_trigger(cfg, cred)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(f"/api/auto-rotation/{cfg['id']}/trigger", headers=_auth_headers())

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "rotated"
        assert body["issuer"] == "fake_rotator"
        assert body["version_number"] == 1

        # Credential record updated with the new encrypted value and rotation_count incremented.
        MOCK_DB.credentials.update_one.assert_called_once()
        update_args, update_kwargs = MOCK_DB.credentials.update_one.call_args
        update_query, update_op = update_args
        assert update_query == {"id": cred["id"], "user_id": cred["user_id"]}
        assert update_op["$set"]["api_key"] == "enc::rotated::value"
        assert update_op["$inc"] == {"rotation_count": 1}

        # A new version snapshot was written.
        MOCK_DB.credential_versions.insert_one.assert_called_once()
        version_doc = MOCK_DB.credential_versions.insert_one.call_args.args[0]
        assert version_doc["api_key_encrypted"] == "enc::rotated::value"
        assert version_doc["is_current"] is True

        # Schedule advanced.
        MOCK_DB.auto_rotation_configs.update_one.assert_called_once()


class TestRotationUnsupportedIssuer:
    def test_rotation_skipped_when_issuer_does_not_support_mint(self):
        """An OAuth-only issuer cannot mint; the response is a skip, not a fail."""
        register_issuer("fake_oauth_only", _OAuthOnlyIssuer())

        cfg = _config_doc()
        cred = _credential_doc(issuer="fake_oauth_only")
        _wire_mongo_for_trigger(cfg, cred)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(f"/api/auto-rotation/{cfg['id']}/trigger", headers=_auth_headers())

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "skipped_unsupported"
        assert body["issuer"] == "fake_oauth_only"
        MOCK_DB.credentials.update_one.assert_not_called()
        MOCK_DB.credential_versions.insert_one.assert_not_called()


class TestRotationIssuerNotRegistered:
    def test_rotation_skipped_when_issuer_not_registered(self):
        """If the issuer name on the credential isn't registered, skip with that status."""
        # Note: we deliberately do NOT register the issuer here.
        cfg = _config_doc()
        cred = _credential_doc(issuer="vanished_issuer")
        _wire_mongo_for_trigger(cfg, cred)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(f"/api/auto-rotation/{cfg['id']}/trigger", headers=_auth_headers())

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "skipped_issuer_not_registered"
        MOCK_DB.credentials.update_one.assert_not_called()


class TestRotationUpstreamFailure:
    def test_rotation_failed_when_issuer_raises_IssuerUpstreamError(self):
        """Upstream 5xx surfaces as failed_upstream; encrypted value untouched."""
        register_issuer("fake_upstream_error", _UpstreamErrorIssuer())

        cfg = _config_doc()
        cred = _credential_doc(issuer="fake_upstream_error")
        _wire_mongo_for_trigger(cfg, cred)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(f"/api/auto-rotation/{cfg['id']}/trigger", headers=_auth_headers())

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed_upstream"
        MOCK_DB.credentials.update_one.assert_not_called()
        MOCK_DB.credential_versions.insert_one.assert_not_called()


class TestRotationAuthFailure:
    def test_rotation_failed_when_issuer_raises_IssuerAuthError(self):
        """Auth error surfaces as failed_auth; user must intervene."""
        register_issuer("fake_auth_error", _AuthErrorIssuer())

        cfg = _config_doc()
        cred = _credential_doc(issuer="fake_auth_error")
        _wire_mongo_for_trigger(cfg, cred)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(f"/api/auto-rotation/{cfg['id']}/trigger", headers=_auth_headers())

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed_auth"
        MOCK_DB.credentials.update_one.assert_not_called()


class TestRotationAuditLog:
    def test_rotation_writes_audit_log_entry_on_success(self):
        """A successful rotation appends a hash-chained audit entry."""
        register_issuer("fake_rotator", _DeterministicIssuer())

        cfg = _config_doc()
        cred = _credential_doc(issuer="fake_rotator")
        _wire_mongo_for_trigger(cfg, cred)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(f"/api/auto-rotation/{cfg['id']}/trigger", headers=_auth_headers())
        assert resp.status_code == 200

        # The integrity-chained collection in this codebase is db.audit_log;
        # AuditIntegrity.create_audit_entry writes to it. Spec phrased it as
        # "audit_chain" generically.
        MOCK_DB.audit_log.insert_one.assert_called_once()
        entry = MOCK_DB.audit_log.insert_one.call_args.args[0]
        assert entry["action"] == "credential_auto_rotated"
        assert entry["resource_type"] == "credential"
        assert entry["resource_id"] == cred["id"]
        # Hash chain fields are populated.
        assert "integrity_hash" in entry
        assert "previous_hash" in entry


# Make sure the audit module imports stay live (used implicitly by AuditIntegrity).
_ = audit_module

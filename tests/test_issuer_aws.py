"""Tests for the AWS credential issuer (Tier 2.3).

The issuer's ``mint_scoped_credential`` is exercised with a stubbed
``boto3.client("sts").assume_role`` so the suite never makes a real AWS call
(boto3 is not even installed in CI). The route layer is mounted on a fresh
FastAPI app per test class to avoid depending on the orchestrator wiring
``backend/server.py`` first.
"""

from __future__ import annotations

# Import the shared test helpers FIRST: it pins ENCRYPTION_KEY/JWT_SECRET
# before any backend module is imported. Order is load-bearing.
from tests._test_helpers import MOCK_DB, make_token  # isort: skip
import json  # isort: skip
import sys  # isort: skip
from datetime import datetime, timedelta, timezone  # isort: skip
from unittest.mock import AsyncMock, MagicMock, patch  # isort: skip

import pytest  # isort: skip
from fastapi import FastAPI  # isort: skip
from fastapi.testclient import TestClient  # isort: skip

import backend.routes.issuers_aws as aws_route_mod  # isort: skip
from backend.issuers.aws import AWSIssuer  # isort: skip
from backend.issuers.base import IssuerNotSupported  # isort: skip
from backend.issuers.registry import get_issuer  # isort: skip
from backend.routes.issuers_aws import router as aws_router  # isort: skip
from backend.security import decrypt_api_key  # isort: skip

# ── Auth fixtures ─────────────────────────────────────────────────────────

_NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)
_USER_ID = "user-aws-1"
_AUTH_USER = {
    "_id": "mongo-oid",
    "id": _USER_ID,
    "username": "awsuser",
    "hashed_password": "irrelevant",
    "created_at": _NOW,
}


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {make_token('awsuser')}"}


def _setup_auth(role_arn: str | None = None) -> None:
    user = dict(_AUTH_USER)
    if role_arn is not None:
        user["aws_role_arn"] = role_arn
    MOCK_DB.users.find_one = AsyncMock(return_value=user)


def _make_app() -> FastAPI:
    """Build a fresh FastAPI app with just the AWS issuer router mounted."""
    app = FastAPI()
    app.include_router(aws_router)
    return app


def _patch_route_db():
    """Replace the ``db`` reference inside the route module with the mock DB.

    The route imports ``db`` at module load; the helper rebinds it to MOCK_DB
    every test so all collection writes go through the mock.
    """
    aws_route_mod.db = MOCK_DB


# Always rebind the route's db to MOCK_DB before each test.
@pytest.fixture(autouse=True)
def _rebind_db():
    _patch_route_db()
    yield


# ── Fake boto3 module ─────────────────────────────────────────────────────


def _fake_assume_role_response(expiration: datetime | None = None):
    return {
        "Credentials": {
            "AccessKeyId": "ASIATESTACCESSKEY1234",
            "SecretAccessKey": "fakesecretfakesecretfakesecretfakesecre",
            "SessionToken": "FakeSessionTokenForTestsOnlyDoNotUseInProd",
            "Expiration": expiration or (datetime.now(timezone.utc) + timedelta(hours=1)),
        },
        "AssumedRoleUser": {
            "AssumedRoleId": "AROATESTROLEID:keyforge-test",
            "Arn": "arn:aws:sts::123456789012:assumed-role/Test/keyforge-test",
        },
    }


class _FakeStsClient:
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise_exc = raise_exc
        self.assume_role_calls = []

    def assume_role(self, **kwargs):
        self.assume_role_calls.append(kwargs)
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response


def _install_fake_boto3(sts_client):
    """Insert a fake ``boto3`` and ``botocore.exceptions`` into sys.modules."""
    fake_boto3 = MagicMock()
    fake_boto3.client = MagicMock(return_value=sts_client)

    fake_botocore = MagicMock()
    fake_botocore_exc = MagicMock()

    class _BotoCoreError(Exception):
        pass

    class _ClientError(Exception):
        def __init__(self, response, operation):
            super().__init__(str(response))
            self.response = response
            self.operation_name = operation

    fake_botocore_exc.BotoCoreError = _BotoCoreError
    fake_botocore_exc.ClientError = _ClientError
    fake_botocore.exceptions = fake_botocore_exc

    return {
        "boto3": fake_boto3,
        "botocore": fake_botocore,
        "botocore.exceptions": fake_botocore_exc,
    }


# ── Issuer-level unit tests ───────────────────────────────────────────────


class TestSupportsAndDefaults:
    def test_supports_mint_and_revoke_only(self):
        issuer = AWSIssuer()
        assert issuer.name == "aws"
        assert issuer.supports == {"mint_scoped_credential", "revoke"}

    @pytest.mark.asyncio
    async def test_start_oauth_raises_IssuerNotSupported(self):
        issuer = AWSIssuer()
        with pytest.raises(IssuerNotSupported):
            await issuer.start_oauth(user_id=_USER_ID)

    @pytest.mark.asyncio
    async def test_complete_oauth_raises_IssuerNotSupported(self):
        issuer = AWSIssuer()
        with pytest.raises(IssuerNotSupported):
            await issuer.complete_oauth(user_id=_USER_ID, code="abc")

    def test_issuer_registered_under_aws(self):
        # Importing backend.issuers.aws registers the singleton at import time.
        # Other test files (notably test_issuers_interface) have an autouse
        # fixture that clears the registry on teardown, so re-register here
        # to make the test order-independent.
        from backend.issuers.registry import register_issuer

        register_issuer("aws", AWSIssuer())
        assert isinstance(get_issuer("aws"), AWSIssuer)


class TestMint:
    @pytest.mark.asyncio
    async def test_mint_calls_sts_assume_role_and_returns_IssuedCredential(self):
        expiration = datetime(2025, 6, 1, 1, 0, tzinfo=timezone.utc)
        fake_sts = _FakeStsClient(response=_fake_assume_role_response(expiration=expiration))
        fake_modules = _install_fake_boto3(fake_sts)

        with patch.dict(sys.modules, fake_modules):
            issuer = AWSIssuer()
            cred = await issuer.mint_scoped_credential(
                user_id=_USER_ID,
                scope={
                    "role_arn": "arn:aws:iam::123456789012:role/MyRole",
                    "session_policy": {"Version": "2012-10-17", "Statement": []},
                    "duration_seconds": 1800,
                    "session_name": "keyforge-test-session",
                },
            )

        # AssumeRole was called with the right args.
        assert len(fake_sts.assume_role_calls) == 1
        call = fake_sts.assume_role_calls[0]
        assert call["RoleArn"] == "arn:aws:iam::123456789012:role/MyRole"
        assert call["RoleSessionName"] == "keyforge-test-session"
        assert call["DurationSeconds"] == 1800
        # Session policy must be passed as a JSON string per the boto3 contract.
        assert isinstance(call["Policy"], str)
        assert json.loads(call["Policy"]) == {"Version": "2012-10-17", "Statement": []}

        # Returned IssuedCredential shape.
        assert cred.issuer == "aws"
        assert cred.user_id == _USER_ID
        assert cred.api_name == "aws_sts_keyforge-test-session"
        assert cred.expires_at == expiration
        assert cred.revocable is False
        assert cred.scope == "role:arn:aws:iam::123456789012:role/MyRole"
        assert cred.metadata["role_arn"] == "arn:aws:iam::123456789012:role/MyRole"
        assert cred.metadata["duration_seconds"] == 1800
        assert cred.metadata["session_name"] == "keyforge-test-session"

    @pytest.mark.asyncio
    async def test_mint_encrypts_returned_credentials(self):
        fake_sts = _FakeStsClient(response=_fake_assume_role_response())
        fake_modules = _install_fake_boto3(fake_sts)

        with patch.dict(sys.modules, fake_modules):
            issuer = AWSIssuer()
            cred = await issuer.mint_scoped_credential(
                user_id=_USER_ID,
                scope={
                    "role_arn": "arn:aws:iam::123456789012:role/MyRole",
                    "duration_seconds": 3600,
                    "session_name": "keyforge-enc-test",
                },
            )

        # The encrypted_value is NOT plaintext: must not contain the access key id.
        assert "ASIATESTACCESSKEY1234" not in cred.encrypted_value
        assert "fakesecretfakesecret" not in cred.encrypted_value

        # But round-tripping through the same Fernet key must yield the JSON blob.
        decrypted = decrypt_api_key(cred.encrypted_value)
        payload = json.loads(decrypted)
        assert payload["AccessKeyId"] == "ASIATESTACCESSKEY1234"
        assert payload["SecretAccessKey"].startswith("fakesecret")
        assert payload["SessionToken"].startswith("FakeSession")
        assert "Expiration" in payload

    @pytest.mark.asyncio
    async def test_mint_without_boto3_raises_IssuerNotSupported(self):
        # Force the lazy import to fail by stubbing boto3 = None in sys.modules.
        with patch.dict(sys.modules, {"boto3": None}):
            issuer = AWSIssuer()
            with pytest.raises(IssuerNotSupported) as exc_info:
                await issuer.mint_scoped_credential(
                    user_id=_USER_ID,
                    scope={"role_arn": "arn:aws:iam::123456789012:role/MyRole"},
                )
            assert "boto3" in str(exc_info.value).lower()


class TestRevoke:
    @pytest.mark.asyncio
    async def test_revoke_marks_credential_revoked_in_db_only(self):
        # Mock update_one to report a matched document.
        result = MagicMock()
        result.matched_count = 1
        MOCK_DB.credentials.update_one = AsyncMock(return_value=result)

        issuer = AWSIssuer()
        await issuer.revoke("cred-aws-123")  # must not raise

        MOCK_DB.credentials.update_one.assert_awaited_once()
        args, kwargs = MOCK_DB.credentials.update_one.call_args
        # Filter targets the credential id.
        assert args[0] == {"id": "cred-aws-123"}
        # Update sets status=revoked and a revoked_at timestamp.
        update = args[1]
        assert update["$set"]["status"] == "revoked"
        assert isinstance(update["$set"]["revoked_at"], datetime)

    @pytest.mark.asyncio
    async def test_revoke_unknown_credential_does_not_raise(self):
        result = MagicMock()
        result.matched_count = 0
        MOCK_DB.credentials.update_one = AsyncMock(return_value=result)

        issuer = AWSIssuer()
        # Even when the DB has no matching record, revoke must not raise.
        await issuer.revoke("cred-does-not-exist")
        MOCK_DB.credentials.update_one.assert_awaited_once()


# ── Route-level tests ─────────────────────────────────────────────────────


class TestConfigureRoute:
    def test_route_post_configure_validates_arn_format(self):
        _setup_auth()
        MOCK_DB.users.update_one = AsyncMock()

        client = TestClient(_make_app(), raise_server_exceptions=False)

        # Bad ARN: missing role/ segment.
        resp = client.post(
            "/api/issuers/aws/configure",
            json={"role_arn": "not-an-arn"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
        assert "Invalid IAM role ARN" in resp.json()["detail"]

        # Bad ARN: account id is not 12 digits.
        resp = client.post(
            "/api/issuers/aws/configure",
            json={"role_arn": "arn:aws:iam::1234:role/Foo"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400

        # Good ARN.
        resp = client.post(
            "/api/issuers/aws/configure",
            json={"role_arn": "arn:aws:iam::123456789012:role/KeyForgeAssumableRole"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["role_arn"] == "arn:aws:iam::123456789012:role/KeyForgeAssumableRole"
        assert body["trust_policy_template_url"].endswith("/trust-policy-template")
        MOCK_DB.users.update_one.assert_awaited()


class TestTrustPolicyTemplateRoute:
    def test_route_get_trust_policy_template_includes_account_placeholder_when_unset(self, monkeypatch):
        _setup_auth()
        # Ensure KEYFORGE_AWS_ACCOUNT_ID is unset for this test.
        monkeypatch.delenv("KEYFORGE_AWS_ACCOUNT_ID", raising=False)

        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/api/issuers/aws/trust-policy-template", headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.json()

        assert body["keyforge_aws_account_id_set"] is False
        assert body["user_id"] == _USER_ID
        # User id placeholder always rendered.
        assert "<YOUR_USER_ID>" not in body["template"]
        assert _USER_ID in body["template"]
        # Account id placeholder still present because env var is unset.
        assert "<KEYFORGE_AWS_ACCOUNT_ID>" in body["template"]

    def test_route_get_trust_policy_template_substitutes_account_when_set(self, monkeypatch):
        _setup_auth()
        monkeypatch.setenv("KEYFORGE_AWS_ACCOUNT_ID", "999988887777")

        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/api/issuers/aws/trust-policy-template", headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["keyforge_aws_account_id_set"] is True
        assert "<KEYFORGE_AWS_ACCOUNT_ID>" not in body["template"]
        assert "999988887777" in body["template"]


class TestStatusRoute:
    def test_route_get_status_reports_readiness(self, monkeypatch):
        _setup_auth(role_arn="arn:aws:iam::123456789012:role/MyRole")
        monkeypatch.setenv("KEYFORGE_AWS_ACCOUNT_ID", "123456789012")
        monkeypatch.setenv("AWS_REGION", "us-west-2")

        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/api/issuers/aws/status", headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        # boto3 may or may not be installed in the test env; we only check the field is bool.
        assert isinstance(body["boto3_installed"], bool)
        assert body["keyforge_aws_account_id_set"] is True
        assert body["user_role_arn_configured"] is True
        assert body["aws_region"] == "us-west-2"

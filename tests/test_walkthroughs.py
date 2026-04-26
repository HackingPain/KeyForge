"""Tests for the walkthrough engine (loader + route).

These tests cover three layers:

1. ``backend.walkthroughs.loader`` directly: shipped JSON files load and
   validate, the summary list contains both shipped providers, malformed
   regexes fail fast, and unknown providers raise.

2. The validation helper: well-formed credentials pass, malformed ones fail
   with a useful reason.

3. The HTTP route: GET list, GET detail, POST validate, and the 404 path for
   unknown providers. The walkthroughs router is not yet wired into
   ``backend.server`` (that happens in a final pass by the orchestrator), so
   these tests register it onto the shared test app themselves.
"""

from __future__ import annotations

# Import the shared test helpers FIRST: it sets ENCRYPTION_KEY and JWT_SECRET
# before any backend module is imported. Order is load-bearing here, so the
# isort: skip directives below pin it.
from tests._test_helpers import MOCK_DB, app, make_token  # isort: skip
from datetime import datetime, timezone  # isort: skip
from unittest.mock import AsyncMock  # isort: skip

import pytest  # isort: skip
from fastapi.testclient import TestClient  # isort: skip

from backend.walkthroughs.loader import (  # isort: skip
    WalkthroughNotFoundError,
    _reset_caches_for_tests,
    list_walkthroughs,
    load_walkthrough,
    validate_credential_format,
)
from backend.walkthroughs.schema import Walkthrough  # isort: skip


# ── Auth fixtures ─────────────────────────────────────────────────────────

_NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)
_AUTH_USER = {
    "_id": "mongo-oid",
    "id": "user-walk-1",
    "username": "walkuser",
    "hashed_password": "irrelevant",
    "created_at": _NOW,
}


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {make_token('walkuser')}"}


def _setup_auth() -> None:
    MOCK_DB.users.find_one = AsyncMock(return_value=_AUTH_USER)


# ── Loader / schema unit tests ────────────────────────────────────────────


class TestLoadWalkthrough:
    """Direct loader tests; bypass the router."""

    def setup_method(self) -> None:
        _reset_caches_for_tests()

    def test_stripe_walkthrough_loads(self) -> None:
        wt = load_walkthrough("stripe")
        assert isinstance(wt, Walkthrough)
        assert wt.provider == "stripe"
        assert wt.display_name == "Stripe"
        assert len(wt.steps) >= 3
        # Final step must be the paste step.
        assert wt.steps[-1].action is not None
        assert wt.steps[-1].action.type == "paste_credential"
        # First step opens the dashboard.
        assert wt.steps[0].action is not None
        assert wt.steps[0].action.type == "external_link"
        assert wt.steps[0].action.url.startswith("https://dashboard.stripe.com/")

    def test_openai_walkthrough_loads(self) -> None:
        wt = load_walkthrough("openai")
        assert wt.provider == "openai"
        assert wt.display_name == "OpenAI"
        assert wt.validation.regex == "^sk-[A-Za-z0-9_-]{32,}$"
        # Walkthrough URL is the OpenAI API keys page.
        assert wt.steps[0].action is not None
        assert wt.steps[0].action.url.startswith("https://platform.openai.com/")

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(WalkthroughNotFoundError):
            load_walkthrough("definitely-not-a-provider")

    def test_provider_slug_must_be_safe(self) -> None:
        # Path-traversal-shaped slug must never be loaded from disk.
        with pytest.raises(WalkthroughNotFoundError):
            load_walkthrough("../etc/passwd")

    def test_loader_caches(self) -> None:
        first = load_walkthrough("stripe")
        second = load_walkthrough("stripe")
        assert first is second


class TestListWalkthroughs:
    def setup_method(self) -> None:
        _reset_caches_for_tests()

    def test_list_includes_shipped_providers(self) -> None:
        summaries = list_walkthroughs()
        slugs = {s.provider for s in summaries}
        assert "stripe" in slugs
        assert "openai" in slugs

    def test_summary_shape(self) -> None:
        summaries = list_walkthroughs()
        for s in summaries:
            assert s.provider
            assert s.display_name
            # icon may be None but must not be missing on the model.
            assert hasattr(s, "icon")


class TestValidateCredentialFormat:
    def setup_method(self) -> None:
        _reset_caches_for_tests()

    def test_valid_stripe_test_key(self) -> None:
        # Synthetic key that matches the regex; never seen by the real Stripe API.
        result = validate_credential_format("stripe", "rk_test_" + "A" * 30)
        assert result.valid is True
        assert result.reason is None

    def test_valid_stripe_live_key(self) -> None:
        result = validate_credential_format("stripe", "rk_live_" + "Z" * 28)
        assert result.valid is True

    def test_invalid_stripe_prefix(self) -> None:
        result = validate_credential_format("stripe", "sk_test_" + "A" * 30)
        assert result.valid is False
        assert "Stripe" in (result.reason or "")

    def test_too_short_credential(self) -> None:
        result = validate_credential_format("stripe", "rk_test_short")
        assert result.valid is False
        assert "short" in (result.reason or "").lower()

    def test_valid_openai_classic_key(self) -> None:
        result = validate_credential_format("openai", "sk-" + "A" * 40)
        assert result.valid is True

    def test_valid_openai_project_key(self) -> None:
        # sk-proj- prefix is covered by the same regex because '-' is in the
        # character class. Use 40 trailing chars to clear the {32,} floor.
        result = validate_credential_format("openai", "sk-proj-" + "B" * 40)
        assert result.valid is True

    def test_invalid_openai_prefix(self) -> None:
        result = validate_credential_format("openai", "pk-" + "A" * 40)
        assert result.valid is False

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(WalkthroughNotFoundError):
            validate_credential_format("nope", "anything")


# ── Route tests ───────────────────────────────────────────────────────────


class TestListEndpoint:
    """GET /api/walkthroughs"""

    def test_returns_summaries(self) -> None:
        _setup_auth()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/walkthroughs", headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        slugs = {item["provider"] for item in body}
        assert "stripe" in slugs
        assert "openai" in slugs
        for item in body:
            assert "provider" in item
            assert "display_name" in item

    def test_requires_auth(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/walkthroughs")
        assert resp.status_code == 401


class TestDetailEndpoint:
    """GET /api/walkthroughs/{provider}"""

    def test_returns_full_walkthrough(self) -> None:
        _setup_auth()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/walkthroughs/stripe", headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "stripe"
        assert body["display_name"] == "Stripe"
        assert isinstance(body["steps"], list)
        assert len(body["steps"]) >= 3
        assert body["validation"]["regex"]

    def test_unknown_provider_404(self) -> None:
        _setup_auth()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/walkthroughs/no-such-provider", headers=_auth_headers())
        assert resp.status_code == 404


class TestValidateEndpoint:
    """POST /api/walkthroughs/{provider}/validate"""

    def test_valid_credential(self) -> None:
        _setup_auth()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/walkthroughs/stripe/validate",
            json={"credential": "rk_test_" + "A" * 32},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["reason"] is None

    def test_invalid_credential(self) -> None:
        _setup_auth()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/walkthroughs/stripe/validate",
            json={"credential": "this-is-not-a-stripe-key"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert body["reason"]

    def test_unknown_provider_404(self) -> None:
        _setup_auth()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/walkthroughs/nope/validate",
            json={"credential": "anything"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    def test_requires_auth(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/walkthroughs/stripe/validate",
            json={"credential": "rk_test_" + "A" * 32},
        )
        # CSRF middleware rejects unauthenticated mutating browser requests
        # with 403 before the route's get_current_user dep can return 401.
        # Either is acceptable: the endpoint must not succeed without auth.
        assert resp.status_code in (401, 403)

"""Backwards-compat tests for the new issuer-related fields on Credential.

Tier 2.1 added four optional fields to ``Credential``: ``issuer``,
``issued_at``, ``revocable``, and ``scope``. Existing routes and tests
construct ``Credential`` without these fields, so they must default safely.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.models import Credential


def test_credential_constructible_without_new_issuer_fields():
    """Pre-Tier-2 callers omit the four new fields; the model still validates."""
    cred = Credential(api_name="openai")

    assert cred.issuer is None
    assert cred.issued_at is None
    assert cred.revocable is False
    assert cred.scope is None
    # Pre-existing defaults still hold.
    assert cred.api_key_encrypted == ""
    assert cred.status == "unknown"
    assert cred.environment == "development"


def test_credential_constructible_with_new_issuer_fields():
    """Tier-2 issuer flow sets all four fields explicitly."""
    issued_at = datetime.now(timezone.utc)
    cred = Credential(
        api_name="github",
        api_key_encrypted="enc::pat::abc",
        status="active",
        environment="production",
        user_id="u1",
        issuer="github",
        issued_at=issued_at,
        revocable=True,
        scope="repo:acme/thing",
    )

    assert cred.issuer == "github"
    assert cred.issued_at == issued_at
    assert cred.revocable is True
    assert cred.scope == "repo:acme/thing"
    assert cred.user_id == "u1"
    assert cred.api_key_encrypted == "enc::pat::abc"

"""Tests for the CredentialIssuer interface, registry, and contract.

A FakeIssuer that implements all four methods deterministically is used to
verify the contract: returns the right shapes, registers correctly, and
unsupported methods on a partially-implemented issuer fall through to the
ABC default which raises IssuerNotSupported.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pytest

from backend.issuers import (
    CredentialIssuer,
    IssuedCredential,
    IssuerNotSupported,
    get_issuer,
    list_issuers,
    register_issuer,
)
from backend.issuers import registry as registry_module


class FakeIssuer(CredentialIssuer):
    """Deterministic in-memory issuer used for contract tests."""

    name = "fake"
    supports = {"start_oauth", "complete_oauth", "mint_scoped_credential", "revoke"}

    def __init__(self) -> None:
        self.revoked_ids: list[str] = []

    async def start_oauth(self, user_id: str, scope: Optional[str] = None) -> str:
        return f"https://fake.example.com/oauth/authorize?user={user_id}&scope={scope or ''}"

    async def complete_oauth(self, user_id: str, code: str, state: Optional[str] = None) -> IssuedCredential:
        return IssuedCredential(
            issuer=self.name,
            user_id=user_id,
            api_name=f"fake_oauth_{user_id}",
            encrypted_value=f"enc::oauth::{code}",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revocable=True,
            scope=state,
            metadata={"flow": "oauth", "code": code},
        )

    async def mint_scoped_credential(self, user_id: str, scope: Dict[str, Any]) -> IssuedCredential:
        scope_id = scope.get("id", "default")
        return IssuedCredential(
            issuer=self.name,
            user_id=user_id,
            api_name=f"fake_minted_{scope_id}",
            encrypted_value=f"enc::mint::{user_id}::{scope_id}",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revocable=True,
            scope=str(scope_id),
            metadata={"flow": "mint", "scope": scope},
        )

    async def revoke(self, credential_id: str) -> None:
        self.revoked_ids.append(credential_id)


class MintOnlyIssuer(CredentialIssuer):
    """Partial issuer: implements mint_scoped_credential only.

    start_oauth, complete_oauth, and revoke fall through to the ABC defaults
    (which raise IssuerNotSupported), exactly as the AWS issuer will look in
    Tier 2.3.
    """

    name = "mint_only"
    supports = {"mint_scoped_credential"}

    async def mint_scoped_credential(self, user_id: str, scope: Dict[str, Any]) -> IssuedCredential:
        return IssuedCredential(
            issuer=self.name,
            user_id=user_id,
            api_name="mint_only_cred",
            encrypted_value="enc::mint_only",
            scope=str(scope.get("id", "default")),
        )


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Clear the registry between tests so registrations don't leak."""
    registry_module._REGISTRY.clear()
    yield
    registry_module._REGISTRY.clear()


# ── FakeIssuer behavior ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fake_issuer_start_oauth_returns_url():
    issuer = FakeIssuer()
    url = await issuer.start_oauth(user_id="u1", scope="repo:acme/thing")
    assert isinstance(url, str)
    assert "u1" in url
    assert url.startswith("https://")


@pytest.mark.asyncio
async def test_fake_issuer_complete_oauth_returns_issued_credential():
    issuer = FakeIssuer()
    cred = await issuer.complete_oauth(user_id="u1", code="abc123", state="state-xyz")
    assert isinstance(cred, IssuedCredential)
    assert cred.issuer == "fake"
    assert cred.user_id == "u1"
    assert cred.encrypted_value
    assert cred.encrypted_value.startswith("enc::")
    assert cred.revocable is True
    assert cred.scope == "state-xyz"


@pytest.mark.asyncio
async def test_fake_issuer_mint_returns_issued_credential():
    issuer = FakeIssuer()
    cred = await issuer.mint_scoped_credential(user_id="u2", scope={"id": "acme/thing", "permissions": ["repo"]})
    assert isinstance(cred, IssuedCredential)
    assert cred.issuer == "fake"
    assert cred.user_id == "u2"
    assert cred.api_name == "fake_minted_acme/thing"
    assert cred.encrypted_value
    assert cred.scope == "acme/thing"
    assert cred.metadata["flow"] == "mint"


@pytest.mark.asyncio
async def test_fake_issuer_revoke_succeeds():
    issuer = FakeIssuer()
    await issuer.revoke("cred-123")
    assert "cred-123" in issuer.revoked_ids


# ── ABC default behavior on partial issuers ─────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_method_raises_IssuerNotSupported():
    issuer = MintOnlyIssuer()

    # The one method it does support works.
    cred = await issuer.mint_scoped_credential(user_id="u1", scope={"id": "x"})
    assert cred.issuer == "mint_only"

    # The three methods it does not support inherit the ABC default and raise.
    with pytest.raises(IssuerNotSupported):
        await issuer.start_oauth(user_id="u1")

    with pytest.raises(IssuerNotSupported):
        await issuer.complete_oauth(user_id="u1", code="abc")

    with pytest.raises(IssuerNotSupported):
        await issuer.revoke(credential_id="cred-123")


# ── Registry ────────────────────────────────────────────────────────────────


def test_registry_register_and_get():
    fake = FakeIssuer()
    register_issuer("fake", fake)
    assert get_issuer("fake") is fake


def test_registry_list_includes_supports_metadata():
    register_issuer("fake", FakeIssuer())
    register_issuer("mint_only", MintOnlyIssuer())

    listing = list_issuers()
    assert isinstance(listing, list)
    by_name = {entry["name"]: entry for entry in listing}

    assert "fake" in by_name
    assert "mint_only" in by_name

    # supports comes back as a sorted list so it's JSON-serialisable.
    assert by_name["fake"]["supports"] == sorted(["start_oauth", "complete_oauth", "mint_scoped_credential", "revoke"])
    assert by_name["mint_only"]["supports"] == ["mint_scoped_credential"]


def test_get_unknown_issuer_raises_IssuerNotSupported():
    with pytest.raises(IssuerNotSupported):
        get_issuer("does_not_exist")


def test_register_issuer_rejects_non_issuer_instance():
    with pytest.raises(TypeError):
        register_issuer("bogus", object())  # type: ignore[arg-type]

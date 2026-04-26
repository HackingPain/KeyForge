"""Provider-agnostic credential issuer interface.

Every concrete issuer (GitHub, AWS, ...) is a subclass of ``CredentialIssuer``
and implements only the subset of methods that make sense for its provider.
Methods the issuer does not implement should be left at the ABC default,
which raises ``IssuerNotSupported``. The ``supports`` class attribute is the
machine-readable version of that capability set; the dashboard uses it to
decide which buttons to render for a given issuer.

Method semantics:

* ``start_oauth(user_id, scope=None) -> auth_url``
    Returns a URL the user must visit to grant consent. OAuth issuers only.

* ``complete_oauth(user_id, code, state=None) -> IssuedCredential``
    Exchanges an OAuth callback ``code`` for a stored credential.

* ``mint_scoped_credential(user_id, scope) -> IssuedCredential``
    Mints a fresh credential (e.g. a fine-grained PAT, a short-lived STS
    token). ``scope`` semantics are provider-specific.

* ``revoke(credential_id) -> None``
    Best-effort revocation against the upstream provider. If the upstream
    rejects the request (already-revoked, unknown id, ...) the implementation
    should log and swallow; only catastrophic failures should raise
    ``IssuerUpstreamError``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, Optional, Set

from pydantic import BaseModel, Field


class IssuerError(Exception):
    """Base class for all issuer-layer errors."""


class IssuerNotSupported(IssuerError):
    """Raised when a method or named issuer is not available."""


class IssuerAuthError(IssuerError):
    """Raised when upstream auth fails (bad token, revoked grant, expired)."""


class IssuerUpstreamError(IssuerError):
    """Raised on upstream 5xx / network failures we cannot handle locally."""


class IssuedCredential(BaseModel):
    """The result of a successful issue/mint operation.

    The returned credential has already been encrypted and is ready to be
    persisted alongside other KeyForge credentials. The plaintext value is
    intentionally never carried on this object; callers receive only the
    Fernet ciphertext in ``encrypted_value``.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    issuer: str
    user_id: str
    api_name: str
    encrypted_value: str
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    revocable: bool = False
    scope: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CredentialIssuer:
    """Abstract base class for provider-specific credential issuers.

    Subclasses set ``name`` to the registry key (e.g. ``"github"``) and
    ``supports`` to the set of method names they actually implement. Methods
    the subclass does not list in ``supports`` should be left to the ABC
    defaults, which raise ``IssuerNotSupported``.
    """

    # Registry key used by ``register_issuer`` / ``get_issuer``.
    name: ClassVar[str] = ""

    # Machine-readable capability set. Frontend reads this to decide which
    # actions to expose. Concrete subclasses override.
    supports: ClassVar[Set[str]] = set()

    async def start_oauth(self, user_id: str, scope: Optional[str] = None) -> str:
        """Return an authorization URL for the user to grant consent.

        Default implementation raises ``IssuerNotSupported``. OAuth-capable
        issuers override this method and add ``"start_oauth"`` to ``supports``.
        """
        raise IssuerNotSupported(f"Issuer '{self.name or type(self).__name__}' does not support start_oauth")

    async def complete_oauth(self, user_id: str, code: str, state: Optional[str] = None) -> IssuedCredential:
        """Exchange an OAuth callback ``code`` for an ``IssuedCredential``.

        Default implementation raises ``IssuerNotSupported``.
        """
        raise IssuerNotSupported(f"Issuer '{self.name or type(self).__name__}' does not support complete_oauth")

    async def mint_scoped_credential(self, user_id: str, scope: Dict[str, Any]) -> IssuedCredential:
        """Mint a fresh credential for the given scope.

        Default implementation raises ``IssuerNotSupported``. Fixed-credential
        providers (Stripe, OpenAI, ...) leave this unimplemented and rely on
        the inline guided walkthrough flow instead.
        """
        raise IssuerNotSupported(f"Issuer '{self.name or type(self).__name__}' does not support mint_scoped_credential")

    async def revoke(self, credential_id: str) -> None:
        """Best-effort revocation of a previously issued credential.

        Default implementation raises ``IssuerNotSupported``. Concrete issuers
        override and should log-and-swallow expected failures (already-revoked,
        unknown id) and only raise ``IssuerUpstreamError`` for catastrophic
        problems the caller cannot recover from.
        """
        raise IssuerNotSupported(f"Issuer '{self.name or type(self).__name__}' does not support revoke")

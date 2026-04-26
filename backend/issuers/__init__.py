"""Credential issuer abstraction for KeyForge.

KeyForge is shifting from a credential vault (stores keys you already have)
to a credential issuer (clicks a button, gets a credential). This package
defines the provider-agnostic interface that GitHub, AWS, and future issuers
implement, plus a registry the rest of the app uses to look them up by name.
"""

from backend.issuers.base import (
    CredentialIssuer,
    IssuedCredential,
    IssuerAuthError,
    IssuerError,
    IssuerNotSupported,
    IssuerUpstreamError,
)
from backend.issuers.registry import (
    get_issuer,
    list_issuers,
    register_issuer,
)

__all__ = [
    "CredentialIssuer",
    "IssuedCredential",
    "IssuerError",
    "IssuerNotSupported",
    "IssuerAuthError",
    "IssuerUpstreamError",
    "register_issuer",
    "get_issuer",
    "list_issuers",
]

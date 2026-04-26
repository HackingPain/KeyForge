"""Registry of installed credential issuers.

Concrete issuer instances register themselves at import time. Routes and the
dashboard look them up by name (``get_issuer``) or enumerate them
(``list_issuers``) to render provider-specific UI.
"""

from __future__ import annotations

from typing import Dict, List

from backend.issuers.base import CredentialIssuer, IssuerNotSupported

_REGISTRY: Dict[str, CredentialIssuer] = {}


def register_issuer(name: str, instance: CredentialIssuer) -> None:
    """Register a concrete issuer under ``name``.

    Re-registering an existing name overwrites the previous instance. This is
    intentional: it lets tests swap in a fake without bookkeeping.
    """
    if not isinstance(instance, CredentialIssuer):
        raise TypeError(f"register_issuer expected a CredentialIssuer, got {type(instance).__name__}")
    _REGISTRY[name] = instance


def get_issuer(name: str) -> CredentialIssuer:
    """Return the issuer registered under ``name``.

    Raises ``IssuerNotSupported`` if no issuer has been registered for that
    name. Callers should treat this the same as a method-level
    ``IssuerNotSupported``: the requested issuer simply is not available.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        raise IssuerNotSupported(f"No issuer registered under name '{name}'")


def list_issuers() -> List[Dict[str, object]]:
    """Return ``[{name, supports}, ...]`` for every registered issuer.

    ``supports`` is returned as a sorted list (not a set) so the result is
    JSON-serialisable for direct return from a route.
    """
    return [{"name": name, "supports": sorted(instance.supports)} for name, instance in _REGISTRY.items()]

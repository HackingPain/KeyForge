"""Load and validate walkthrough JSON files.

Walkthroughs live next to this module as ``<provider>.json``. Each file is
parsed exactly once and cached, both because the JSON is shipped with the
codebase (so it cannot change at runtime) and because the loader is invoked
on every authenticated GET. The cache is module-level rather than per-process
because the FastAPI app instance is shared across the test suite.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from threading import RLock
from typing import Dict, List

from backend.walkthroughs.schema import (
    Walkthrough,
    WalkthroughSummary,
    WalkthroughValidationResponse,
)


class WalkthroughNotFoundError(LookupError):
    """Raised when no walkthrough JSON file exists for the requested provider."""


_WALKTHROUGH_DIR = Path(__file__).parent
_CACHE: Dict[str, Walkthrough] = {}
_SUMMARY_CACHE: List[WalkthroughSummary] | None = None
_LOCK = RLock()


def _slug_is_safe(provider: str) -> bool:
    """Reject anything that could resolve outside the walkthroughs directory."""
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", provider))


def _load_from_disk(provider: str) -> Walkthrough:
    """Read and parse one walkthrough JSON file. Validates via the schema."""
    if not _slug_is_safe(provider):
        raise WalkthroughNotFoundError(f"invalid provider slug: {provider!r}")

    path = _WALKTHROUGH_DIR / f"{provider}.json"
    if not path.is_file():
        raise WalkthroughNotFoundError(f"no walkthrough JSON found for provider {provider!r} at {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"walkthrough {provider!r} is not valid JSON: {exc}") from exc

    walkthrough = Walkthrough.model_validate(raw)
    if walkthrough.provider != provider:
        raise ValueError(
            f"walkthrough provider field {walkthrough.provider!r} does not match " f"filename {provider!r}"
        )
    return walkthrough


def load_walkthrough(provider: str) -> Walkthrough:
    """Return the walkthrough for *provider*, loading and caching as needed."""
    cached = _CACHE.get(provider)
    if cached is not None:
        return cached

    with _LOCK:
        cached = _CACHE.get(provider)
        if cached is not None:
            return cached
        walkthrough = _load_from_disk(provider)
        _CACHE[provider] = walkthrough
        # Summary cache must be rebuilt on next call so list reflects this load.
        global _SUMMARY_CACHE
        _SUMMARY_CACHE = None
        return walkthrough


def list_walkthroughs() -> List[WalkthroughSummary]:
    """Return one summary per shipped walkthrough JSON file."""
    global _SUMMARY_CACHE
    if _SUMMARY_CACHE is not None:
        return list(_SUMMARY_CACHE)

    with _LOCK:
        if _SUMMARY_CACHE is not None:
            return list(_SUMMARY_CACHE)

        summaries: List[WalkthroughSummary] = []
        for path in sorted(_WALKTHROUGH_DIR.glob("*.json")):
            provider = path.stem
            try:
                walkthrough = load_walkthrough(provider)
            except (WalkthroughNotFoundError, ValueError):
                # A malformed file should not poison the whole list; the loader
                # will surface the error when the specific provider is queried.
                continue
            summaries.append(
                WalkthroughSummary(
                    provider=walkthrough.provider,
                    display_name=walkthrough.display_name,
                    icon=walkthrough.icon,
                )
            )
        _SUMMARY_CACHE = summaries
        return list(summaries)


def validate_credential_format(provider: str, credential: str) -> WalkthroughValidationResponse:
    """Apply the provider's validation regex and length bounds to *credential*."""
    walkthrough = load_walkthrough(provider)
    rules = walkthrough.validation

    if len(credential) < rules.min_length:
        return WalkthroughValidationResponse(
            valid=False,
            reason=(f"Credential is too short: must be at least {rules.min_length} characters."),
        )
    if len(credential) > rules.max_length:
        return WalkthroughValidationResponse(
            valid=False,
            reason=(f"Credential is too long: must be at most {rules.max_length} characters."),
        )
    if not re.fullmatch(rules.regex, credential):
        return WalkthroughValidationResponse(
            valid=False,
            reason=(f"Credential does not match the expected format for " f"{walkthrough.display_name}."),
        )
    return WalkthroughValidationResponse(valid=True, reason=None)


def _reset_caches_for_tests() -> None:
    """Test-only: drop the module caches so a fresh-load path is exercised."""
    global _SUMMARY_CACHE
    with _LOCK:
        _CACHE.clear()
        _SUMMARY_CACHE = None

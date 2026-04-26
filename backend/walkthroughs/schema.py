"""Pydantic models describing the walkthrough JSON schema.

A walkthrough JSON file is loaded into a ``Walkthrough`` instance and
validated by Pydantic at import time (see ``loader.load_walkthrough``).
Anything that does not match these models is rejected with a clear error
rather than silently rendered as a broken stepper in the UI.
"""

from __future__ import annotations

import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Step action types -----------------------------------------------------------


class ExternalLinkAction(BaseModel):
    """A step that opens an external URL (e.g. the provider dashboard)."""

    type: Literal["external_link"]
    url: str = Field(..., min_length=1, max_length=2048)
    label: str = Field(..., min_length=1, max_length=120)

    @field_validator("url")
    @classmethod
    def _url_is_http(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("external_link url must start with http:// or https://")
        return v


class PasteCredentialAction(BaseModel):
    """The terminal step on every walkthrough: paste, validate, save."""

    type: Literal["paste_credential"]


WalkthroughStepAction = ExternalLinkAction | PasteCredentialAction


# Walkthrough body ------------------------------------------------------------


class WalkthroughStep(BaseModel):
    """A single instruction shown to the user in the stepper UI."""

    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    action: Optional[WalkthroughStepAction] = None
    screenshot: Optional[str] = Field(default=None, max_length=2048)


class WalkthroughValidation(BaseModel):
    """Format checks applied to the pasted credential server-side."""

    regex: str = Field(..., min_length=1, max_length=512)
    min_length: int = Field(..., ge=1, le=4096)
    max_length: int = Field(..., ge=1, le=4096)

    @field_validator("regex")
    @classmethod
    def _regex_compiles(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"invalid regex: {exc}") from exc
        return v

    @model_validator(mode="after")
    def _length_bounds_make_sense(self) -> "WalkthroughValidation":
        if self.min_length > self.max_length:
            raise ValueError("min_length must be <= max_length")
        return self


class WalkthroughSuggestedScope(BaseModel):
    """A scope choice presented to the user at the paste step."""

    value: str = Field(..., min_length=1, max_length=120)
    label: str = Field(..., min_length=1, max_length=200)


class Walkthrough(BaseModel):
    """Full walkthrough definition for one provider."""

    provider: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1, max_length=2000)
    icon: Optional[str] = Field(default=None, max_length=120)
    credential_label: str = Field(..., min_length=1, max_length=120)
    validation: WalkthroughValidation
    suggested_scopes: List[WalkthroughSuggestedScope] = Field(default_factory=list)
    steps: List[WalkthroughStep] = Field(..., min_length=1)

    @field_validator("provider")
    @classmethod
    def _provider_is_slug(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", v):
            raise ValueError("provider must be a lowercase slug (a-z0-9, '-' or '_'; cannot start with separator)")
        return v

    @model_validator(mode="after")
    def _terminal_step_pastes(self) -> "Walkthrough":
        last = self.steps[-1]
        if last.action is None or last.action.type != "paste_credential":
            raise ValueError("the final walkthrough step must have action.type == 'paste_credential'")
        return self


# Public summary and response shapes -----------------------------------------


class WalkthroughSummary(BaseModel):
    """The lightweight shape returned by ``GET /api/walkthroughs``."""

    provider: str
    display_name: str
    icon: Optional[str] = None


class WalkthroughValidationRequest(BaseModel):
    """Body of ``POST /api/walkthroughs/{provider}/validate``."""

    credential: str = Field(..., min_length=1, max_length=4096)


class WalkthroughValidationResponse(BaseModel):
    """Result of validating a pasted credential against the walkthrough regex."""

    valid: bool
    reason: Optional[str] = None

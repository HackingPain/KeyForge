"""Walkthrough engine API routes.

Exposes the JSON-driven walkthrough definitions consumed by the
``CredentialWalkthrough`` React component. All endpoints require
authentication: the walkthroughs themselves are public knowledge but the
endpoints sit behind ``get_current_user`` to prevent unauthenticated probing
and to keep the surface uniform with the rest of the credential flow.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from backend.security import get_current_user
from backend.walkthroughs.loader import (
    WalkthroughNotFoundError,
    list_walkthroughs,
    load_walkthrough,
    validate_credential_format,
)
from backend.walkthroughs.schema import (
    Walkthrough,
    WalkthroughSummary,
    WalkthroughValidationRequest,
    WalkthroughValidationResponse,
)

router = APIRouter(prefix="/api", tags=["walkthroughs"])


@router.get("/walkthroughs", response_model=List[WalkthroughSummary])
async def list_available_walkthroughs(
    current_user: dict = Depends(get_current_user),
) -> List[WalkthroughSummary]:
    """List every provider that has a guided walkthrough defined."""
    return list_walkthroughs()


@router.get("/walkthroughs/{provider}", response_model=Walkthrough)
async def get_walkthrough(
    provider: str,
    current_user: dict = Depends(get_current_user),
) -> Walkthrough:
    """Return the full walkthrough definition for *provider*."""
    try:
        return load_walkthrough(provider)
    except WalkthroughNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No walkthrough defined for provider '{provider}'",
        ) from exc


@router.post(
    "/walkthroughs/{provider}/validate",
    response_model=WalkthroughValidationResponse,
)
async def validate_walkthrough_credential(
    provider: str,
    body: WalkthroughValidationRequest,
    current_user: dict = Depends(get_current_user),
) -> WalkthroughValidationResponse:
    """Run the walkthrough's regex + length checks on a pasted credential."""
    try:
        return validate_credential_format(provider, body.credential)
    except WalkthroughNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No walkthrough defined for provider '{provider}'",
        ) from exc

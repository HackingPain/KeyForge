"""HTTP routes for the AWS credential issuer.

Surfaces:
    POST /api/issuers/aws/configure         set the user's role ARN
    GET  /api/issuers/aws/trust-policy-template  render the CFN template
    POST /api/issuers/aws/mint              mint short-lived STS credentials
    GET  /api/issuers/aws/status            boto3 + config readiness probe

KeyForge's own AWS auth is whatever boto3's default credential chain
resolves at runtime (instance profile on EC2, env vars locally). This is
documented here rather than hard-coded so operators can pick whichever
mechanism their deployment supports.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

try:
    from ..config import db, logger
    from ..issuers import (
        IssuerAuthError,
        IssuerNotSupported,
        IssuerUpstreamError,
        get_issuer,
    )
    from ..issuers.trust_policy_template import AWS_TRUST_POLICY_CFN_TEMPLATE
    from ..security import get_current_user
except ImportError:
    from backend.config import db, logger
    from backend.issuers import (
        IssuerAuthError,
        IssuerNotSupported,
        IssuerUpstreamError,
        get_issuer,
    )
    from backend.issuers.trust_policy_template import AWS_TRUST_POLICY_CFN_TEMPLATE
    from backend.security import get_current_user

router = APIRouter(prefix="/api/issuers/aws", tags=["issuers", "aws"])

# Matches IAM role ARNs. The account id is 12 digits; partition handles
# aws / aws-cn / aws-us-gov; the resource path after role/ allows the
# AWS-permitted character set including slashes for role paths.
_ROLE_ARN_RE = re.compile(r"^arn:aws[a-zA-Z\-]*:iam::\d{12}:role/[A-Za-z0-9+=,.@_/-]+$")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ConfigureRequest(BaseModel):
    role_arn: str = Field(..., description="IAM role ARN KeyForge should assume on the user's behalf")


class ConfigureResponse(BaseModel):
    role_arn: str
    trust_policy_template_url: str


class MintRequest(BaseModel):
    session_policy: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional session policy to scope down the assumed role"
    )
    duration_seconds: int = Field(default=3600, ge=900, le=43200)
    session_name: Optional[str] = None


class MintResponse(BaseModel):
    """Response from /mint. Plaintext credentials are NEVER returned."""

    id: str
    issuer: str
    api_name: str
    issued_at: datetime
    expires_at: Optional[datetime]
    revocable: bool
    scope: Optional[str]
    metadata: Dict[str, Any]


class StatusResponse(BaseModel):
    boto3_installed: bool
    keyforge_aws_account_id_set: bool
    user_role_arn_configured: bool
    aws_region: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_trust_policy_template(user_id: str) -> str:
    """Substitute placeholders in the CFN template for the requesting user."""
    keyforge_account_id = os.environ.get("KEYFORGE_AWS_ACCOUNT_ID")
    rendered = AWS_TRUST_POLICY_CFN_TEMPLATE.replace("<YOUR_USER_ID>", user_id)
    if keyforge_account_id:
        rendered = rendered.replace("<KEYFORGE_AWS_ACCOUNT_ID>", keyforge_account_id)
    return rendered


# ---------------------------------------------------------------------------
# POST /configure
# ---------------------------------------------------------------------------


@router.post("/configure", response_model=ConfigureResponse)
async def configure_aws(
    body: ConfigureRequest,
    current_user: dict = Depends(get_current_user),
):
    """Persist the user's IAM role ARN. Validates ARN format up-front."""
    if not _ROLE_ARN_RE.match(body.role_arn):
        raise HTTPException(
            status_code=400,
            detail="Invalid IAM role ARN. Expected arn:aws:iam::<account-id>:role/<role-name>.",
        )

    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"aws_role_arn": body.role_arn}},
    )

    return ConfigureResponse(
        role_arn=body.role_arn,
        trust_policy_template_url="/api/issuers/aws/trust-policy-template",
    )


# ---------------------------------------------------------------------------
# GET /trust-policy-template
# ---------------------------------------------------------------------------


@router.get("/trust-policy-template")
async def get_trust_policy_template(current_user: dict = Depends(get_current_user)):
    """Return the CloudFormation template the user pastes into AWS.

    The template references ``<KEYFORGE_AWS_ACCOUNT_ID>`` (left as-is when
    the operator has not set the env var, so the user knows to ask) and
    ``<YOUR_USER_ID>``, which is always substituted with the requesting
    user's id so each role's trust policy is tenant-specific.
    """
    rendered = _render_trust_policy_template(current_user["id"])
    return {
        "template": rendered,
        "format": "yaml",
        "keyforge_aws_account_id_set": bool(os.environ.get("KEYFORGE_AWS_ACCOUNT_ID")),
        "user_id": current_user["id"],
    }


# ---------------------------------------------------------------------------
# POST /mint
# ---------------------------------------------------------------------------


@router.post("/mint", response_model=MintResponse)
async def mint_aws_credential(
    body: MintRequest,
    current_user: dict = Depends(get_current_user),
):
    """Mint a short-lived STS credential for the user's configured role.

    Plaintext credentials are intentionally never returned. Callers retrieve
    them later via the proxy or the /credentials decryption flow, exactly
    like every other KeyForge credential.
    """
    role_arn = current_user.get("aws_role_arn")
    if not role_arn:
        raise HTTPException(
            status_code=400,
            detail="No AWS role ARN configured. POST /api/issuers/aws/configure first.",
        )

    issuer = get_issuer("aws")

    scope: Dict[str, Any] = {
        "role_arn": role_arn,
        "duration_seconds": body.duration_seconds,
        "session_name": body.session_name or f"keyforge-{uuid.uuid4().hex[:16]}",
    }
    if body.session_policy is not None:
        scope["session_policy"] = body.session_policy

    try:
        issued = await issuer.mint_scoped_credential(user_id=current_user["id"], scope=scope)
    except IssuerNotSupported as exc:
        # Most likely cause: boto3 not installed.
        logger.warning("AWS issuer mint not supported: %s", exc)
        raise HTTPException(status_code=501, detail=str(exc))
    except IssuerAuthError as exc:
        logger.warning("AWS issuer mint denied for user %s: %s", current_user["id"], exc)
        raise HTTPException(status_code=401, detail=str(exc))
    except IssuerUpstreamError as exc:
        logger.error("AWS issuer mint upstream failure for user %s: %s", current_user["id"], exc)
        raise HTTPException(status_code=502, detail=str(exc))

    cred_doc = {
        "id": issued.id,
        "user_id": issued.user_id,
        "api_name": issued.api_name,
        "api_key": issued.encrypted_value,
        "status": "active",
        "environment": "production",
        "created_at": datetime.now(timezone.utc),
        "issuer": issued.issuer,
        "issued_at": issued.issued_at,
        "expires_at": issued.expires_at,
        "revocable": issued.revocable,
        "scope": issued.scope,
        "metadata": issued.metadata,
    }
    await db.credentials.insert_one(cred_doc)

    return MintResponse(
        id=issued.id,
        issuer=issued.issuer,
        api_name=issued.api_name,
        issued_at=issued.issued_at,
        expires_at=issued.expires_at,
        revocable=issued.revocable,
        scope=issued.scope,
        metadata=issued.metadata,
    )


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------


@router.get("/status", response_model=StatusResponse)
async def aws_issuer_status(current_user: dict = Depends(get_current_user)):
    """Report readiness of the AWS issuer for this user and this server."""
    boto3_installed = False
    try:
        import boto3  # noqa: F401

        boto3_installed = True
    except ImportError:
        boto3_installed = False

    return StatusResponse(
        boto3_installed=boto3_installed,
        keyforge_aws_account_id_set=bool(os.environ.get("KEYFORGE_AWS_ACCOUNT_ID")),
        user_role_arn_configured=bool(current_user.get("aws_role_arn")),
        aws_region=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")),
    )

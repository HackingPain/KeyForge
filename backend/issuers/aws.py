"""AWS credential issuer for KeyForge.

Mints short-lived credentials by calling ``sts:AssumeRole`` against an IAM
role the user has set up in their own AWS account. The trust policy on that
role names the KeyForge service AWS account as the principal, so KeyForge's
own boto3 default credential chain (env vars locally, instance profile on
EC2) is used to perform the AssumeRole call.

Why no OAuth: AWS does not have an OAuth flow for service-to-service auth.
The user's one-time setup is creating an IAM role with the correct trust
policy (see ``trust_policy_template.py``), then telling KeyForge the role
ARN. Every subsequent ``mint_scoped_credential`` call just re-runs
AssumeRole against that role.

Why ``revocable=False``: STS-issued temporary credentials cannot be
invalidated early via the STS API. They expire on their own at
``Expiration`` (typically 1 hour). ``revoke`` therefore only marks the
KeyForge-side record as revoked and logs a warning that the upstream token
remains valid until natural expiry.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.config import logger
from backend.issuers.base import (
    CredentialIssuer,
    IssuedCredential,
    IssuerAuthError,
    IssuerNotSupported,
    IssuerUpstreamError,
)
from backend.issuers.registry import register_issuer
from backend.security import encrypt_api_key

# Default STS session duration if the caller does not specify one.
_DEFAULT_DURATION_SECONDS = 3600

# Default region used when neither AWS_REGION nor AWS_DEFAULT_REGION is set.
_DEFAULT_REGION = "us-east-1"


def _aws_region() -> str:
    """Resolve the AWS region from env, falling back to a sensible default."""
    return os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", _DEFAULT_REGION))


class AWSIssuer(CredentialIssuer):
    """Issuer that mints short-lived STS-assumed-role credentials.

    KeyForge does NOT manage long-lived AWS keys on the user's behalf. The
    user creates an IAM role in their own AWS account with a trust policy
    pointing at the KeyForge service account; KeyForge's boto3 default
    credential chain authenticates the AssumeRole call.
    """

    name = "aws"
    supports = {"mint_scoped_credential", "revoke"}

    # ------------------------------------------------------------------
    # mint_scoped_credential
    # ------------------------------------------------------------------

    async def mint_scoped_credential(self, user_id: str, scope: Dict[str, Any]) -> IssuedCredential:
        """Mint a short-lived STS-assumed-role credential.

        ``scope`` keys:
            role_arn         : required, the IAM role to assume
            session_policy   : optional dict, scopes the session to a subset
                               of the role's permissions
            duration_seconds : optional int, default 3600
            session_name     : optional str, default ``keyforge-<uuid>``

        Returns an ``IssuedCredential`` whose ``encrypted_value`` is a
        Fernet-encrypted JSON blob containing AccessKeyId, SecretAccessKey,
        SessionToken, and Expiration. ``revocable=False`` because STS
        temporary credentials cannot be invalidated early via the API.
        """
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
        except ImportError as exc:
            raise IssuerNotSupported("boto3 is not installed; pip install boto3 to use the AWS issuer") from exc

        role_arn = scope.get("role_arn")
        if not role_arn:
            raise IssuerAuthError("scope.role_arn is required to mint an AWS credential")

        duration_seconds = int(scope.get("duration_seconds") or _DEFAULT_DURATION_SECONDS)
        session_name = scope.get("session_name") or f"keyforge-{uuid.uuid4().hex[:16]}"
        session_policy = scope.get("session_policy")

        assume_kwargs: Dict[str, Any] = {
            "RoleArn": role_arn,
            "RoleSessionName": session_name,
            "DurationSeconds": duration_seconds,
        }
        if session_policy is not None:
            assume_kwargs["Policy"] = json.dumps(session_policy)

        sts_client = boto3.client("sts", region_name=_aws_region())

        try:
            resp = sts_client.assume_role(**assume_kwargs)
        except ClientError as exc:
            # Auth-shaped errors from AWS (AccessDenied, InvalidIdentityToken,
            # ExpiredToken, ...) are propagated as IssuerAuthError so the
            # caller can render a 401-flavoured response. Everything else is
            # an upstream failure.
            err_code = exc.response.get("Error", {}).get("Code", "")
            logger.warning("STS AssumeRole failed for user %s role %s: %s", user_id, role_arn, err_code)
            if err_code in {"AccessDenied", "InvalidIdentityToken", "ExpiredToken", "ExpiredTokenException"}:
                raise IssuerAuthError(f"STS AssumeRole denied: {err_code}") from exc
            raise IssuerUpstreamError(f"STS AssumeRole failed: {err_code or exc}") from exc
        except BotoCoreError as exc:
            logger.warning("STS AssumeRole network/boto error for user %s: %s", user_id, exc)
            raise IssuerUpstreamError(f"STS AssumeRole network error: {exc}") from exc

        creds = resp.get("Credentials") or {}
        expiration = creds.get("Expiration")

        # Normalise Expiration to an aware UTC datetime. boto3 returns it as
        # an aware datetime already, but defensive parsing covers stubs and
        # mocks that may return a string.
        expires_at: Optional[datetime]
        if isinstance(expiration, datetime):
            expires_at = expiration if expiration.tzinfo else expiration.replace(tzinfo=timezone.utc)
        elif isinstance(expiration, str):
            try:
                expires_at = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
            except ValueError:
                expires_at = None
        else:
            expires_at = None

        # Pack the assumed-role credentials as a JSON blob, then Fernet-encrypt.
        # We never carry plaintext through the IssuedCredential model.
        payload = {
            "AccessKeyId": creds.get("AccessKeyId"),
            "SecretAccessKey": creds.get("SecretAccessKey"),
            "SessionToken": creds.get("SessionToken"),
            "Expiration": expires_at.isoformat() if expires_at else None,
        }
        encrypted = encrypt_api_key(json.dumps(payload))

        return IssuedCredential(
            issuer=self.name,
            user_id=user_id,
            api_name=f"aws_sts_{session_name}",
            encrypted_value=encrypted,
            expires_at=expires_at,
            revocable=False,
            scope=f"role:{role_arn}",
            metadata={
                "role_arn": role_arn,
                "duration_seconds": duration_seconds,
                "session_name": session_name,
            },
        )

    # ------------------------------------------------------------------
    # revoke
    # ------------------------------------------------------------------

    async def revoke(self, credential_id: str) -> None:
        """Mark a previously issued AWS credential as revoked locally.

        STS-assumed-role credentials cannot be invalidated early. This method
        flips the KeyForge-side ``status`` to ``revoked`` and logs a warning.
        The upstream session continues to work until its natural expiry.
        """
        from backend.config import db

        result = await db.credentials.update_one(
            {"id": credential_id},
            {"$set": {"status": "revoked", "revoked_at": datetime.now(timezone.utc)}},
        )

        if getattr(result, "matched_count", 0) == 0:
            logger.warning("AWS issuer revoke called for unknown credential id=%s; no DB record updated", credential_id)

        logger.warning(
            "AWS credential id=%s marked revoked locally. STS temporary credentials "
            "cannot be invalidated early; the upstream session will continue to work "
            "until its natural Expiration.",
            credential_id,
        )


register_issuer("aws", AWSIssuer())

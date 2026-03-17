"""Expiration enforcement policy engine for KeyForge.

Moves from passive expiration tracking to active enforcement:
credentials can be warned, blocked, or given a grace period.
"""

from datetime import datetime, timezone
from typing import Optional
import uuid

try:
    from ..models_policy import (
        ExpirationPolicyConfig,
        PolicyCheckResult,
        PolicyViolation,
    )
except ImportError:
    from backend.models_policy import (
        ExpirationPolicyConfig,
        PolicyCheckResult,
        PolicyViolation,
    )

VALID_MODES = ("warn", "block", "grace")

DEFAULT_POLICY = {
    "mode": "warn",
    "grace_period_days": 7,
    "notify_on_block": True,
    "notify_on_warning": True,
    "auto_disable_on_expiry": False,
}


def _parse_dt(value) -> datetime:
    """Normalise a datetime value to a timezone-aware UTC datetime."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


class ExpirationPolicy:
    """Stateless helper that evaluates expiration enforcement rules."""

    # ── check_credential_access ───────────────────────────────────────────

    @staticmethod
    async def check_credential_access(db, credential_id: str, user_id: str) -> dict:
        """Check if a credential is allowed to be accessed under the user's policy.

        Returns a dict matching PolicyCheckResult fields.
        """
        # 1. Verify credential exists and belongs to user
        credential = await db.credentials.find_one({
            "id": credential_id,
            "user_id": user_id,
        })
        if not credential:
            return PolicyCheckResult(
                allowed=False,
                reason="Credential not found",
                credential_id=credential_id,
            ).model_dump()

        api_name = credential.get("api_name", "")

        # 2. Check for exemption
        exemption = await db.policy_exemptions.find_one({
            "credential_id": credential_id,
            "user_id": user_id,
        })
        if exemption:
            # Check if exemption itself has expired
            if exemption.get("expires_at"):
                exempt_expires = _parse_dt(exemption["expires_at"])
                if datetime.now(timezone.utc) > exempt_expires:
                    # Exemption expired, remove it
                    await db.policy_exemptions.delete_one({"id": exemption["id"]})
                else:
                    return PolicyCheckResult(
                        allowed=True,
                        reason="Credential is exempt from expiration policy",
                        policy_mode="exempt",
                        credential_id=credential_id,
                        api_name=api_name,
                    ).model_dump()
            else:
                return PolicyCheckResult(
                    allowed=True,
                    reason="Credential is exempt from expiration policy",
                    policy_mode="exempt",
                    credential_id=credential_id,
                    api_name=api_name,
                ).model_dump()

        # 3. Check if credential is marked as requiring rotation
        rotation_req = await db.rotation_requirements.find_one({
            "credential_id": credential_id,
            "user_id": user_id,
            "resolved": False,
        })
        if rotation_req and rotation_req.get("disabled_until_rotated", False):
            return PolicyCheckResult(
                allowed=False,
                reason="Credential is disabled until rotated",
                policy_mode="block",
                credential_id=credential_id,
                api_name=api_name,
            ).model_dump()

        # 4. Look up expiration record
        expiration = await db.expirations.find_one({
            "credential_id": credential_id,
            "user_id": user_id,
        })
        if not expiration:
            # No expiration set — always allowed
            return PolicyCheckResult(
                allowed=True,
                reason="No expiration set for this credential",
                credential_id=credential_id,
                api_name=api_name,
            ).model_dump()

        expires_at = _parse_dt(expiration["expires_at"])
        now = datetime.now(timezone.utc)
        delta = expires_at - now
        days_until = delta.days

        if days_until >= 0:
            # Not expired yet
            return PolicyCheckResult(
                allowed=True,
                reason="Credential is not expired",
                credential_id=credential_id,
                api_name=api_name,
            ).model_dump()

        # Credential IS expired
        days_expired = abs(days_until)

        # 5. Get user policy
        policy = await ExpirationPolicy.get_user_policy(db, user_id)
        mode = policy.get("mode", "warn")
        grace_days = policy.get("grace_period_days", 7)

        if mode == "warn":
            return PolicyCheckResult(
                allowed=True,
                reason=f"Credential expired {days_expired} day(s) ago — warning only",
                days_expired=days_expired,
                policy_mode="warn",
                credential_id=credential_id,
                api_name=api_name,
            ).model_dump()

        if mode == "block":
            return PolicyCheckResult(
                allowed=False,
                reason=f"Credential expired {days_expired} day(s) ago — access blocked by policy",
                days_expired=days_expired,
                policy_mode="block",
                credential_id=credential_id,
                api_name=api_name,
            ).model_dump()

        if mode == "grace":
            grace_remaining = max(grace_days - days_expired, 0)
            if days_expired <= grace_days:
                return PolicyCheckResult(
                    allowed=True,
                    reason=f"Credential expired {days_expired} day(s) ago — grace period active ({grace_remaining} day(s) remaining)",
                    days_expired=days_expired,
                    policy_mode="grace",
                    grace_period_remaining=grace_remaining,
                    credential_id=credential_id,
                    api_name=api_name,
                ).model_dump()
            else:
                return PolicyCheckResult(
                    allowed=False,
                    reason=f"Credential expired {days_expired} day(s) ago — grace period of {grace_days} day(s) exceeded",
                    days_expired=days_expired,
                    policy_mode="grace",
                    grace_period_remaining=0,
                    credential_id=credential_id,
                    api_name=api_name,
                ).model_dump()

        # Fallback
        return PolicyCheckResult(
            allowed=True,
            reason="Unknown policy mode — defaulting to allow",
            policy_mode=mode,
            credential_id=credential_id,
            api_name=api_name,
        ).model_dump()

    # ── get_user_policy ───────────────────────────────────────────────────

    @staticmethod
    async def get_user_policy(db, user_id: str) -> dict:
        """Return the user's expiration enforcement policy, or the default."""
        policy = await db.expiration_policies.find_one({"user_id": user_id})
        if policy:
            policy.pop("_id", None)
            return policy
        # Return default policy (not persisted until explicitly set)
        return {
            **DEFAULT_POLICY,
            "user_id": user_id,
            "id": None,
        }

    # ── set_user_policy ───────────────────────────────────────────────────

    @staticmethod
    async def set_user_policy(db, user_id: str, policy: dict) -> dict:
        """Create or update the user's expiration enforcement policy."""
        mode = policy.get("mode")
        if mode and mode not in VALID_MODES:
            raise ValueError(f"Invalid policy mode '{mode}'. Must be one of: {VALID_MODES}")

        existing = await db.expiration_policies.find_one({"user_id": user_id})

        now = datetime.now(timezone.utc)
        if existing:
            update_fields = {k: v for k, v in policy.items() if v is not None}
            update_fields["updated_at"] = now
            await db.expiration_policies.update_one(
                {"user_id": user_id},
                {"$set": update_fields},
            )
        else:
            new_policy = {
                **DEFAULT_POLICY,
                **{k: v for k, v in policy.items() if v is not None},
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "created_at": now,
                "updated_at": now,
            }
            await db.expiration_policies.insert_one(new_policy)

        return await ExpirationPolicy.get_user_policy(db, user_id)

    # ── get_expired_credentials ───────────────────────────────────────────

    @staticmethod
    async def get_expired_credentials(db, user_id: str) -> list:
        """Return all expired credentials with their policy status."""
        expirations = await db.expirations.find(
            {"user_id": user_id}
        ).to_list(1000)

        now = datetime.now(timezone.utc)
        policy = await ExpirationPolicy.get_user_policy(db, user_id)
        mode = policy.get("mode", "warn")
        grace_days = policy.get("grace_period_days", 7)
        expired_list = []

        for exp_doc in expirations:
            expires_at = _parse_dt(exp_doc["expires_at"])
            delta = expires_at - now
            days_until = delta.days

            if days_until >= 0:
                continue  # Not expired

            days_expired = abs(days_until)
            credential = await db.credentials.find_one({"id": exp_doc["credential_id"]})
            api_name = credential.get("api_name", "") if credential else ""

            # Determine if blocked
            is_blocked = False
            grace_remaining = 0
            if mode == "block":
                is_blocked = True
            elif mode == "grace":
                grace_remaining = max(grace_days - days_expired, 0)
                is_blocked = days_expired > grace_days

            # Check exemption
            exemption = await db.policy_exemptions.find_one({
                "credential_id": exp_doc["credential_id"],
                "user_id": user_id,
            })
            is_exempt = bool(exemption)
            if is_exempt:
                is_blocked = False

            expired_list.append({
                "credential_id": exp_doc["credential_id"],
                "api_name": api_name,
                "expires_at": expires_at.isoformat(),
                "days_expired": days_expired,
                "policy_mode": mode,
                "is_blocked": is_blocked,
                "is_exempt": is_exempt,
                "grace_period_remaining": grace_remaining,
            })

        return expired_list

    # ── enforce_rotation ──────────────────────────────────────────────────

    @staticmethod
    async def enforce_rotation(
        db,
        credential_id: str,
        user_id: str,
        disable_until_rotated: bool = False,
        reason: str = "",
    ) -> dict:
        """Mark a credential as requiring rotation, optionally disabling it."""
        credential = await db.credentials.find_one({
            "id": credential_id,
            "user_id": user_id,
        })
        if not credential:
            raise ValueError("Credential not found")

        now = datetime.now(timezone.utc)
        rotation_doc = {
            "id": str(uuid.uuid4()),
            "credential_id": credential_id,
            "user_id": user_id,
            "reason": reason or "Credential expired — rotation required",
            "disabled_until_rotated": disable_until_rotated,
            "resolved": False,
            "created_at": now,
        }

        # Upsert: only one active rotation requirement per credential
        existing = await db.rotation_requirements.find_one({
            "credential_id": credential_id,
            "user_id": user_id,
            "resolved": False,
        })
        if existing:
            await db.rotation_requirements.update_one(
                {"id": existing["id"]},
                {"$set": {
                    "disabled_until_rotated": disable_until_rotated,
                    "reason": rotation_doc["reason"],
                    "updated_at": now,
                }},
            )
            rotation_doc["id"] = existing["id"]
        else:
            await db.rotation_requirements.insert_one(rotation_doc)

        return {
            "credential_id": credential_id,
            "api_name": credential.get("api_name", ""),
            "rotation_required": True,
            "disabled_until_rotated": disable_until_rotated,
            "reason": rotation_doc["reason"],
        }

    # ── get_policy_violations ─────────────────────────────────────────────

    @staticmethod
    async def get_policy_violations(db, user_id: str) -> list:
        """Return all current policy violations for the user."""
        expirations = await db.expirations.find(
            {"user_id": user_id}
        ).to_list(1000)

        now = datetime.now(timezone.utc)
        policy = await ExpirationPolicy.get_user_policy(db, user_id)
        mode = policy.get("mode", "warn")
        grace_days = policy.get("grace_period_days", 7)
        violations = []

        for exp_doc in expirations:
            expires_at = _parse_dt(exp_doc["expires_at"])
            delta = expires_at - now
            days_until = delta.days

            if days_until >= 0:
                continue

            days_expired = abs(days_until)
            credential = await db.credentials.find_one({"id": exp_doc["credential_id"]})
            api_name = credential.get("api_name", "") if credential else ""

            # Skip exempt credentials
            exemption = await db.policy_exemptions.find_one({
                "credential_id": exp_doc["credential_id"],
                "user_id": user_id,
            })
            if exemption:
                continue

            # Determine violation type and blocked status
            if mode == "block":
                violation_type = "expired"
                is_blocked = True
            elif mode == "grace":
                if days_expired > grace_days:
                    violation_type = "grace_exceeded"
                    is_blocked = True
                else:
                    violation_type = "expired"
                    is_blocked = False
            else:
                violation_type = "expired"
                is_blocked = False

            violations.append(PolicyViolation(
                credential_id=exp_doc["credential_id"],
                api_name=api_name,
                user_id=user_id,
                violation_type=violation_type,
                days_expired=days_expired,
                policy_mode=mode,
                is_blocked=is_blocked,
            ).model_dump())

        # Also include rotation-required violations
        rotation_reqs = await db.rotation_requirements.find({
            "user_id": user_id,
            "resolved": False,
        }).to_list(1000)

        for req in rotation_reqs:
            credential = await db.credentials.find_one({"id": req["credential_id"]})
            api_name = credential.get("api_name", "") if credential else ""
            violations.append(PolicyViolation(
                credential_id=req["credential_id"],
                api_name=api_name,
                user_id=user_id,
                violation_type="rotation_required",
                is_blocked=req.get("disabled_until_rotated", False),
                policy_mode=mode,
            ).model_dump())

        return violations

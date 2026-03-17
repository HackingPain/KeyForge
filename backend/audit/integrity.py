"""Tamper-proof audit log integrity with SHA-256 hash chaining."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional


class AuditIntegrity:
    """Provides hash-chained audit log entries for tamper detection.

    Each audit entry includes a SHA-256 hash computed from the previous entry's
    hash concatenated with the current entry's fields, forming an immutable chain.
    """

    GENESIS_HASH = "0" * 64  # Genesis hash for the first entry in any chain

    @staticmethod
    def compute_entry_hash(entry: dict, previous_hash: str) -> str:
        """Compute SHA-256 hash for an audit entry using hash chaining.

        The hash is computed over: previous_hash + action + user_id + timestamp + details_json.
        This ensures any modification to an entry or reordering breaks the chain.

        Args:
            entry: Dictionary containing action, user_id, timestamp, and details fields.
            previous_hash: The integrity_hash of the preceding entry in the chain.

        Returns:
            Hex digest of the SHA-256 hash.
        """
        # Serialize details deterministically
        details = entry.get("details", "")
        if isinstance(details, dict):
            details_json = json.dumps(details, sort_keys=True, default=str)
        else:
            details_json = json.dumps(str(details), sort_keys=True)

        # Normalize timestamp to ISO string
        timestamp = entry.get("timestamp", "")
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        hash_input = (
            str(previous_hash)
            + str(entry.get("action", ""))
            + str(entry.get("user_id", ""))
            + str(timestamp)
            + details_json
        )

        return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

    @classmethod
    async def create_audit_entry(
        cls,
        db,
        user_id: str,
        action: str,
        details: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> dict:
        """Create a new hash-chained audit log entry.

        Fetches the last entry's hash to chain from, computes the new hash,
        and stores the entry with integrity_hash and previous_hash fields.

        Args:
            db: The MongoDB database instance.
            user_id: ID of the user performing the action.
            action: The action performed.
            details: Human-readable details or structured data about the event.
            resource_type: Optional type of resource acted upon.
            resource_id: Optional ID of the specific resource.

        Returns:
            The created audit entry as a dictionary.
        """
        # Fetch the last entry for this user to get the chain tail
        last_entry = await db.audit_log.find_one(
            {"user_id": user_id, "integrity_hash": {"$exists": True}},
            sort=[("timestamp", -1)],
        )

        previous_hash = (
            last_entry["integrity_hash"] if last_entry else cls.GENESIS_HASH
        )

        now = datetime.now(timezone.utc)

        entry = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type or "",
            "resource_id": resource_id,
            "details": details,
            "ip_address": None,
            "timestamp": now,
            "previous_hash": previous_hash,
        }

        # Compute the integrity hash
        entry["integrity_hash"] = cls.compute_entry_hash(entry, previous_hash)

        await db.audit_log.insert_one(entry)

        # Remove MongoDB internal _id before returning
        entry.pop("_id", None)
        return entry

    @classmethod
    async def verify_chain(
        cls,
        db,
        user_id: Optional[str] = None,
        limit: int = 1000,
    ) -> dict:
        """Walk the hash chain and verify each entry's hash matches.

        Args:
            db: The MongoDB database instance.
            user_id: Optional user ID to filter chain verification to one user.
            limit: Maximum number of entries to check.

        Returns:
            Dictionary with verification results:
                - valid: Whether the entire chain is intact.
                - entries_checked: Number of entries verified.
                - first_broken_at: Index of first broken link, or None.
                - gaps_detected: List of indices where gaps were found.
        """
        query = {"integrity_hash": {"$exists": True}}
        if user_id:
            query["user_id"] = user_id

        entries = await (
            db.audit_log
            .find(query)
            .sort("timestamp", 1)
            .limit(limit)
            .to_list(limit)
        )

        if not entries:
            return {
                "valid": True,
                "entries_checked": 0,
                "first_broken_at": None,
                "gaps_detected": [],
            }

        first_broken_at = None
        gaps_detected = []

        for i, entry in enumerate(entries):
            stored_hash = entry.get("integrity_hash", "")
            stored_previous = entry.get("previous_hash", "")

            # Determine what the previous hash should be
            if i == 0:
                expected_previous = cls.GENESIS_HASH
            else:
                expected_previous = entries[i - 1].get("integrity_hash", "")

            # Check for gaps: previous_hash should match the prior entry's hash
            if stored_previous != expected_previous:
                gaps_detected.append(i)

            # Recompute the hash and compare
            expected_hash = cls.compute_entry_hash(entry, stored_previous)
            if expected_hash != stored_hash:
                if first_broken_at is None:
                    first_broken_at = i

        valid = first_broken_at is None and len(gaps_detected) == 0

        return {
            "valid": valid,
            "entries_checked": len(entries),
            "first_broken_at": first_broken_at,
            "gaps_detected": gaps_detected,
        }

    @classmethod
    async def export_audit_log(
        cls,
        db,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list:
        """Export audit log entries with integrity proofs for a date range.

        Args:
            db: The MongoDB database instance.
            user_id: The user whose audit log to export.
            start_date: Start of the export range (inclusive).
            end_date: End of the export range (inclusive).

        Returns:
            List of audit entries with integrity hashes for independent verification.
        """
        query = {
            "user_id": user_id,
            "integrity_hash": {"$exists": True},
            "timestamp": {"$gte": start_date, "$lte": end_date},
        }

        entries = await (
            db.audit_log
            .find(query)
            .sort("timestamp", 1)
            .to_list(10000)
        )

        result = []
        for entry in entries:
            entry.pop("_id", None)
            # Convert datetime for JSON serialization
            if isinstance(entry.get("timestamp"), datetime):
                entry["timestamp"] = entry["timestamp"].isoformat()
            result.append(entry)

        return result

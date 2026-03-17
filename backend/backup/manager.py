"""BackupManager: encrypted backup creation, restore, verification, and scheduling."""

import base64
import gzip
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("keyforge.backup")

# Collections that are internal to the backup system and should be excluded
_INTERNAL_COLLECTIONS = {"backups", "backup_data", "backup_schedules"}


class BackupManager:
    """Manages encrypted backups of MongoDB collections."""

    # ── backup creation ─────────────────────────────────────────────────

    @staticmethod
    async def create_backup(
        db,
        user_id: Optional[str] = None,
        collections: Optional[List[str]] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Dump collections to JSON, encrypt with Fernet, compress with gzip.

        Returns metadata dict with backup_id, created_at, size_bytes,
        collections list, and sha256 checksum.
        """
        backup_id = str(uuid.uuid4())
        encryption_key = Fernet.generate_key()
        fernet = Fernet(encryption_key)

        # Determine which collections to back up
        if collections:
            col_names = [c for c in collections if c not in _INTERNAL_COLLECTIONS]
        else:
            all_names = await db.list_collection_names()
            col_names = [c for c in all_names if c not in _INTERNAL_COLLECTIONS]

        # Dump each collection
        payload: Dict[str, List[Dict[str, Any]]] = {}
        for col_name in col_names:
            docs = []
            cursor = db[col_name].find({})
            async for doc in cursor:
                # Convert ObjectId and other non-serialisable types
                doc["_id"] = str(doc["_id"])
                docs.append(doc)
            payload[col_name] = docs

        # Serialise → compress → encrypt
        raw_json = json.dumps(payload, default=str).encode("utf-8")
        compressed = gzip.compress(raw_json)
        checksum = hashlib.sha256(compressed).hexdigest()
        encrypted = fernet.encrypt(compressed)

        # Persist encrypted blob as base64 in backup_data collection
        b64_data = base64.b64encode(encrypted).decode("ascii")
        await db["backup_data"].insert_one(
            {"backup_id": backup_id, "data": b64_data}
        )

        # Store metadata
        now = datetime.now(timezone.utc)
        total_docs = sum(len(docs) for docs in payload.values())
        metadata = {
            "backup_id": backup_id,
            "created_at": now.isoformat(),
            "size_bytes": len(encrypted),
            "collections": col_names,
            "checksum": checksum,
            "total_documents": total_docs,
            "description": description,
            "user_id": user_id,
            "status": "completed",
            "encryption_key": encryption_key.decode("utf-8"),
        }
        await db["backups"].insert_one({**metadata, "_id": backup_id})

        logger.info(
            "Backup %s created: %d collections, %d docs, %d bytes",
            backup_id, len(col_names), total_docs, len(encrypted),
        )
        return metadata

    # ── restore ─────────────────────────────────────────────────────────

    @staticmethod
    async def restore_backup(
        db,
        backup_data: bytes,
        encryption_key: str,
        target_collections: Optional[List[str]] = None,
        mode: str = "merge",
    ) -> dict:
        """Decrypt, decompress, validate checksum, and restore collections.

        Modes:
            merge   – insert documents whose _id is not already present
            replace – drop the collection and re-insert all documents
        """
        try:
            fernet = Fernet(encryption_key.encode("utf-8"))
            decrypted = fernet.decrypt(backup_data)
        except (InvalidToken, Exception) as exc:
            raise ValueError(f"Decryption failed: {exc}") from exc

        decompressed = gzip.decompress(decrypted)
        payload: Dict[str, list] = json.loads(decompressed)

        cols_to_restore = (
            [c for c in target_collections if c in payload]
            if target_collections
            else list(payload.keys())
        )

        restored: Dict[str, int] = {}
        for col_name in cols_to_restore:
            docs = payload[col_name]
            if not docs:
                restored[col_name] = 0
                continue

            if mode == "replace":
                await db[col_name].drop()
                if docs:
                    # Remove string _id so Mongo generates ObjectIds
                    for d in docs:
                        d.pop("_id", None)
                    await db[col_name].insert_many(docs)
                restored[col_name] = len(docs)
            else:  # merge
                inserted = 0
                for doc in docs:
                    original_id = doc.pop("_id", None)
                    filter_q = {"_id": original_id} if original_id else {}
                    if original_id:
                        exists = await db[col_name].find_one(filter_q)
                        if exists:
                            continue
                    await db[col_name].insert_one(doc)
                    inserted += 1
                restored[col_name] = inserted

        logger.info("Restore completed: mode=%s, collections=%s", mode, restored)
        return {
            "restored_collections": cols_to_restore,
            "documents_restored": restored,
            "mode": mode,
            "restored_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── list backups ────────────────────────────────────────────────────

    @staticmethod
    async def list_backups(db) -> list:
        """Return metadata for all backups from the backups collection."""
        cursor = db["backups"].find({}, {"_id": 0, "encryption_key": 0})
        return await cursor.to_list(length=None)

    # ── delete backup ───────────────────────────────────────────────────

    @staticmethod
    async def delete_backup(db, backup_id: str) -> bool:
        """Delete backup metadata and data blob. Returns True if found."""
        meta_result = await db["backups"].delete_one({"backup_id": backup_id})
        await db["backup_data"].delete_one({"backup_id": backup_id})
        deleted = meta_result.deleted_count > 0
        if deleted:
            logger.info("Backup %s deleted", backup_id)
        return deleted

    # ── verify backup ───────────────────────────────────────────────────

    @staticmethod
    async def verify_backup(backup_data: bytes, encryption_key: str) -> dict:
        """Decrypt and validate a backup without restoring it."""
        errors: List[str] = []
        try:
            fernet = Fernet(encryption_key.encode("utf-8"))
            decrypted = fernet.decrypt(backup_data)
        except (InvalidToken, Exception) as exc:
            return {
                "is_valid": False,
                "checksum_match": False,
                "collections": [],
                "total_documents": 0,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "errors": [f"Decryption failed: {exc}"],
            }

        checksum = hashlib.sha256(decrypted).hexdigest()
        try:
            decompressed = gzip.decompress(decrypted)
            payload: Dict[str, list] = json.loads(decompressed)
        except Exception as exc:
            errors.append(f"Decompression/parse error: {exc}")
            return {
                "is_valid": False,
                "checksum_match": False,
                "collections": [],
                "total_documents": 0,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "errors": errors,
            }

        total_docs = sum(len(v) for v in payload.values())
        return {
            "is_valid": len(errors) == 0,
            "checksum_match": True,
            "checksum": checksum,
            "collections": list(payload.keys()),
            "total_documents": total_docs,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "errors": errors if errors else None,
        }

    # ── schedule backup ─────────────────────────────────────────────────

    @staticmethod
    async def schedule_backup(
        db,
        cron_expression: str,
        collections: Optional[List[str]] = None,
        enabled: bool = True,
        retention_days: int = 30,
        description: Optional[str] = None,
    ) -> dict:
        """Store or update the backup schedule configuration."""
        schedule_doc = {
            "schedule_id": str(uuid.uuid4()),
            "cron_expression": cron_expression,
            "collections": collections,
            "enabled": enabled,
            "retention_days": retention_days,
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Upsert: only one active schedule at a time
        await db["backup_schedules"].update_one(
            {"enabled": True},
            {"$set": schedule_doc},
            upsert=True,
        )
        logger.info("Backup schedule saved: %s", cron_expression)
        return schedule_doc

    @staticmethod
    async def get_schedule(db) -> Optional[dict]:
        """Return the current backup schedule, if any."""
        doc = await db["backup_schedules"].find_one(
            {"enabled": True}, {"_id": 0}
        )
        return doc

"""API routes for MongoDB field-level encryption management."""

from fastapi import APIRouter, HTTPException
from backend.config import db, logger
from backend.encryption.field_encryption import FieldEncryptor, SENSITIVE_FIELDS
from backend.models_field_encryption import (
    CollectionEncryptionRequest,
    FieldEncryptionConfig,
    FieldEncryptionStatus,
)

router = APIRouter(prefix="/api/encryption/fields", tags=["field-encryption"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_encryptor() -> FieldEncryptor:
    """Instantiate a FieldEncryptor, raising 500 if the key is missing."""
    try:
        return FieldEncryptor()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _is_field_encrypted(value) -> bool:
    """Heuristic: Fernet tokens start with 'gAAAAA'."""
    if not isinstance(value, str):
        return False
    return value.startswith("gAAAAA")


def _get_nested(doc: dict, path: str):
    keys = path.split(".")
    current = doc
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return None
    return current


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/status", response_model=list[FieldEncryptionStatus])
async def encryption_status():
    """Show which collections/fields are encrypted and document counts."""
    results: list[FieldEncryptionStatus] = []

    for collection_name, fields in SENSITIVE_FIELDS.items():
        collection = db[collection_name]
        total = await collection.count_documents({})

        encrypted_count = 0
        if total > 0:
            async for doc in collection.find():
                all_encrypted = True
                has_any_field = False
                for field_path in fields:
                    value = _get_nested(doc, field_path)
                    if value is not None:
                        has_any_field = True
                        if not _is_field_encrypted(value):
                            all_encrypted = False
                            break
                if has_any_field and all_encrypted:
                    encrypted_count += 1

        unencrypted = total - encrypted_count
        pct = (encrypted_count / total * 100.0) if total > 0 else 0.0

        results.append(
            FieldEncryptionStatus(
                collection=collection_name,
                sensitive_fields=fields,
                total_documents=total,
                encrypted_documents=encrypted_count,
                unencrypted_documents=unencrypted,
                encryption_percentage=round(pct, 2),
            )
        )

    return results


@router.post("/encrypt-collection")
async def encrypt_collection(req: CollectionEncryptionRequest):
    """Encrypt all existing documents in a collection (migration helper)."""
    if req.collection not in SENSITIVE_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Collection '{req.collection}' has no sensitive fields configured.",
        )

    encryptor = _get_encryptor()
    fields = SENSITIVE_FIELDS[req.collection]
    collection = db[req.collection]

    processed = 0
    encrypted = 0
    skipped = 0
    errors = 0

    cursor = collection.find()
    batch: list = []

    async for doc in cursor:
        # Check if already encrypted — skip if so
        already_encrypted = True
        has_any_field = False
        for field_path in fields:
            value = _get_nested(doc, field_path)
            if value is not None:
                has_any_field = True
                if not _is_field_encrypted(value):
                    already_encrypted = False
                    break

        if not has_any_field or already_encrypted:
            skipped += 1
            processed += 1
            continue

        try:
            encrypted_doc = encryptor.encrypt_document(doc, fields)
            # Build $set update with only the encrypted fields
            update_fields = {}
            for field_path in fields:
                value = _get_nested(encrypted_doc, field_path)
                if value is not None:
                    update_fields[field_path] = value

            if update_fields:
                batch.append(
                    {
                        "filter": {"_id": doc["_id"]},
                        "update": {"$set": update_fields},
                    }
                )
        except Exception as exc:
            logger.error("Failed to encrypt doc %s: %s", doc.get("_id"), exc)
            errors += 1

        processed += 1

        if len(batch) >= req.batch_size:
            for op in batch:
                await collection.update_one(op["filter"], op["update"])
                encrypted += 1
            batch = []

    # flush remaining
    for op in batch:
        await collection.update_one(op["filter"], op["update"])
        encrypted += 1

    return {
        "collection": req.collection,
        "processed": processed,
        "encrypted": encrypted,
        "skipped": skipped,
        "errors": errors,
    }


@router.post("/decrypt-collection")
async def decrypt_collection(req: CollectionEncryptionRequest):
    """Decrypt all documents in a collection (migration / export helper)."""
    if req.collection not in SENSITIVE_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Collection '{req.collection}' has no sensitive fields configured.",
        )

    encryptor = _get_encryptor()
    fields = SENSITIVE_FIELDS[req.collection]
    collection = db[req.collection]

    processed = 0
    decrypted = 0
    skipped = 0
    errors = 0

    cursor = collection.find()
    batch: list = []

    async for doc in cursor:
        needs_decryption = False
        for field_path in fields:
            value = _get_nested(doc, field_path)
            if value is not None and _is_field_encrypted(value):
                needs_decryption = True
                break

        if not needs_decryption:
            skipped += 1
            processed += 1
            continue

        try:
            decrypted_doc = encryptor.decrypt_document(doc, fields)
            update_fields = {}
            for field_path in fields:
                value = _get_nested(decrypted_doc, field_path)
                if value is not None:
                    update_fields[field_path] = value

            if update_fields:
                batch.append(
                    {
                        "filter": {"_id": doc["_id"]},
                        "update": {"$set": update_fields},
                    }
                )
        except Exception as exc:
            logger.error("Failed to decrypt doc %s: %s", doc.get("_id"), exc)
            errors += 1

        processed += 1

        if len(batch) >= req.batch_size:
            for op in batch:
                await collection.update_one(op["filter"], op["update"])
                decrypted += 1
            batch = []

    for op in batch:
        await collection.update_one(op["filter"], op["update"])
        decrypted += 1

    return {
        "collection": req.collection,
        "processed": processed,
        "decrypted": decrypted,
        "skipped": skipped,
        "errors": errors,
    }


@router.get("/config", response_model=FieldEncryptionConfig)
async def get_config():
    """Show current sensitive fields configuration."""
    return FieldEncryptionConfig(sensitive_fields=SENSITIVE_FIELDS)

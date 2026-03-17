"""Pydantic models for field-level encryption endpoints."""

from pydantic import BaseModel, Field
from typing import Optional


class FieldEncryptionStatus(BaseModel):
    """Response model for GET /status."""
    collection: str
    sensitive_fields: list[str]
    total_documents: int
    encrypted_documents: int
    unencrypted_documents: int
    encryption_percentage: float = Field(
        ..., ge=0.0, le=100.0,
        description="Percentage of documents with encrypted sensitive fields",
    )


class CollectionEncryptionRequest(BaseModel):
    """Request body for POST /encrypt-collection and /decrypt-collection."""
    collection: str = Field(
        ..., min_length=1,
        description="Name of the MongoDB collection to process",
    )
    batch_size: int = Field(
        default=100, ge=1, le=5000,
        description="Number of documents to process per batch",
    )


class FieldEncryptionConfig(BaseModel):
    """Response model for GET /config."""
    sensitive_fields: dict[str, list[str]] = Field(
        ...,
        description="Mapping of collection names to their sensitive field paths",
    )
    encryption_algorithm: str = Field(
        default="Fernet (AES-128-CBC + HMAC-SHA256)",
        description="Symmetric encryption algorithm in use",
    )
    search_hash_algorithm: str = Field(
        default="HMAC-SHA256",
        description="Hash algorithm used for searchable encrypted fields",
    )

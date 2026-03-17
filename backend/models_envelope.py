"""Pydantic models for envelope encryption: data keys, encrypted values, rotation."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid


# ── Data key models ──────────────────────────────────────────────────────────

class UserDataKey(BaseModel):
    """A per-user data key record stored in the database."""
    key_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    wrapped_data_key: str  # Master-key-encrypted data key
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    deactivated_at: Optional[datetime] = None


# ── Encrypted value models ──────────────────────────────────────────────────

class EnvelopeEncryptedValue(BaseModel):
    """The result of envelope-encrypting a plaintext value."""
    ciphertext: str  # Data-key-encrypted value
    wrapped_data_key: str  # Master-key-encrypted data key
    key_id: str  # Reference to the UserDataKey record


# ── API response models ─────────────────────────────────────────────────────

class KeyRotationResponse(BaseModel):
    """Response after rotating a user's data key."""
    message: str
    new_key_id: str
    old_key_id: Optional[str] = None
    credentials_re_encrypted: int
    rotated_at: datetime


class MasterKeyRotationResponse(BaseModel):
    """Response after rotating the master key."""
    message: str
    data_keys_re_wrapped: int
    rotated_at: datetime


class KeyStatusResponse(BaseModel):
    """Status information about a user's envelope encryption key."""
    key_id: Optional[str] = None
    created_at: Optional[datetime] = None
    credential_count: int = 0
    is_active: bool = False
    encryption_scheme: str = "envelope (Fernet two-level)"

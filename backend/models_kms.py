"""Pydantic models for KMS administration endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class KMSStatus(BaseModel):
    """Current KMS provider status and metadata."""

    provider: str = Field(..., description="Active KMS provider name")
    algorithm: str = Field(..., description="Encryption algorithm in use")
    key_source: Optional[str] = Field(None, description="Where the key is sourced from")
    key_set: Optional[bool] = Field(None, description="Whether the key env var is set (local only)")
    key_id: Optional[str] = Field(None, description="KMS key identifier (AWS only)")
    region: Optional[str] = Field(None, description="AWS region (AWS only)")
    vault_addr: Optional[str] = Field(None, description="Vault server address (Vault only)")
    transit_key: Optional[str] = Field(None, description="Vault transit key name (Vault only)")
    initialized_at: Optional[float] = Field(None, description="Unix timestamp when provider was initialized")


class KMSTestResult(BaseModel):
    """Result of a KMS encrypt/decrypt round-trip test."""

    success: bool = Field(..., description="Whether the round-trip test passed")
    provider: str = Field(..., description="KMS provider that was tested")
    encrypt_ok: bool = Field(False, description="Encryption step succeeded")
    decrypt_ok: bool = Field(False, description="Decryption step succeeded")
    round_trip_ok: bool = Field(False, description="Decrypted value matches original")
    data_key_ok: bool = Field(False, description="Data key generation succeeded")
    elapsed_ms: float = Field(..., description="Total test duration in milliseconds")
    error: Optional[str] = Field(None, description="Error message if the test failed")


class KMSProviderInfo(BaseModel):
    """Describes an available KMS provider and its configuration requirements."""

    name: str = Field(..., description="Provider identifier")
    description: str = Field(..., description="Human-readable description")
    available: bool = Field(..., description="Whether required dependencies are installed")
    env_vars: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Required and optional environment variables",
    )

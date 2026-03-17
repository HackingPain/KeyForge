"""Pydantic models for the credential proxy system."""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime


class ProxyTokenCreate(BaseModel):
    """Request body for creating a proxy token."""
    credential_id: str = Field(..., description="ID of the credential to proxy")
    ttl_seconds: int = Field(
        default=300,
        ge=30,
        le=86400,
        description="Token time-to-live in seconds (30s to 24h)",
    )
    allowed_endpoints: Optional[List[str]] = Field(
        default=None,
        description="Optional list of allowed target URL patterns",
    )


class ProxyTokenResponse(BaseModel):
    """Response after creating or validating a proxy token."""
    proxy_token: str
    token_id: str
    credential_id: str
    expires_at: datetime
    allowed_endpoints: Optional[List[str]] = None
    created_at: datetime


class ProxyTokenList(BaseModel):
    """List of active proxy tokens for the current user."""
    tokens: List[ProxyTokenResponse]
    total: int


class ProxyRequest(BaseModel):
    """Request body for making a proxied API call."""
    proxy_token: str = Field(..., description="Short-lived proxy token")
    url: str = Field(..., description="Target API URL")
    method: str = Field(
        default="GET",
        description="HTTP method (GET, POST, PUT, DELETE, PATCH)",
    )
    headers: Optional[Dict[str, str]] = Field(
        default=None,
        description="Additional headers to include in the request",
    )
    body: Optional[Any] = Field(
        default=None,
        description="Request body (JSON)",
    )


class ProxyResponse(BaseModel):
    """Response from a proxied API call."""
    status_code: int
    headers: Dict[str, str]
    body: Any
    elapsed_ms: float
    proxied_at: datetime

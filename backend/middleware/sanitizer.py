"""
Input sanitization utilities for preventing NoSQL injection and XSS.
"""
import re
from typing import Any
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import logging
import json

logger = logging.getLogger("keyforge.sanitizer")

# MongoDB operator patterns that should never appear in user input
NOSQL_OPERATORS = re.compile(
    r'\$(?:gt|gte|lt|lte|ne|in|nin|and|or|not|nor|exists|type|regex|where|expr|jsonSchema|mod|text|all|elemMatch|size|slice)'
)

# XSS patterns
XSS_PATTERNS = [
    re.compile(r'<script', re.IGNORECASE),
    re.compile(r'javascript:', re.IGNORECASE),
    re.compile(r'on\w+\s*=', re.IGNORECASE),  # onclick=, onerror=, etc.
]


def sanitize_string(value: str) -> str:
    """Remove potentially dangerous characters from a string."""
    # Strip null bytes
    value = value.replace('\x00', '')
    return value


def check_nosql_injection(data: Any, path: str = "") -> None:
    """
    Recursively check a data structure for NoSQL injection attempts.
    Raises HTTPException if suspicious patterns are found.
    """
    if isinstance(data, str):
        if NOSQL_OPERATORS.search(data):
            logger.warning("Potential NoSQL injection detected at %s: %s", path, data[:100])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid input: potentially dangerous characters detected.",
            )
    elif isinstance(data, dict):
        for key, value in data.items():
            # Check keys for $ operators
            if key.startswith('$'):
                logger.warning("NoSQL operator in key at %s: %s", path, key)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid input: potentially dangerous characters detected.",
                )
            check_nosql_injection(value, f"{path}.{key}")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            check_nosql_injection(item, f"{path}[{i}]")


def check_xss(data: Any, path: str = "") -> None:
    """Check for XSS patterns in string data."""
    if isinstance(data, str):
        for pattern in XSS_PATTERNS:
            if pattern.search(data):
                logger.warning("Potential XSS detected at %s", path)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid input: potentially dangerous content detected.",
                )
    elif isinstance(data, dict):
        for key, value in data.items():
            check_xss(value, f"{path}.{key}")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            check_xss(item, f"{path}[{i}]")


class SanitizationMiddleware(BaseHTTPMiddleware):
    """
    Middleware that checks request bodies for NoSQL injection and XSS patterns.
    Only applies to POST/PUT/PATCH requests with JSON bodies.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body = await request.body()
                    if body:
                        data = json.loads(body)
                        check_nosql_injection(data)
                        check_xss(data)
                except json.JSONDecodeError:
                    pass  # Let FastAPI handle invalid JSON
                except HTTPException:
                    raise
                except Exception:
                    pass  # Don't block on sanitization errors

        return await call_next(request)

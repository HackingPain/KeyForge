"""
Global error handling middleware for consistent API responses.
"""
from typing import Any
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import traceback
from datetime import datetime, timezone

logger = logging.getLogger("keyforge.errors")


class ErrorResponse:
    """Standardized error response format."""

    @staticmethod
    def create(status_code: int, message: str, details: Any = None, error_code: str = None) -> dict:
        response = {
            "error": True,
            "status_code": status_code,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if details:
            response["details"] = details
        if error_code:
            response["error_code"] = error_code
        return response


# Exception handlers to register with the FastAPI app
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTPException with standardized format."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse.create(
            status_code=exc.status_code,
            message=str(exc.detail),
        ),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors with standardized format."""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": " -> ".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        })

    return JSONResponse(
        status_code=422,
        content=ErrorResponse.create(
            status_code=422,
            message="Validation error",
            details=errors,
            error_code="VALIDATION_ERROR",
        ),
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(
        "Unhandled exception on %s %s: %s\n%s",
        request.method,
        request.url.path,
        str(exc),
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content=ErrorResponse.create(
            status_code=500,
            message="Internal server error",
            error_code="INTERNAL_ERROR",
        ),
    )

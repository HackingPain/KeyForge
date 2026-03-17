"""
Token bucket rate limiter for FastAPI.
Tracks requests per IP address with configurable limits.
"""
import time
from collections import defaultdict
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import logging

logger = logging.getLogger("keyforge.rate_limiter")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using token bucket algorithm.

    Args:
        app: FastAPI application
        requests_per_minute: Max requests per minute per IP (default 60)
        burst_size: Max burst size (default 10)
        auth_requests_per_minute: Stricter limit for auth endpoints (default 10)
    """

    def __init__(self, app, requests_per_minute=60, burst_size=10, auth_requests_per_minute=10):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.auth_requests_per_minute = auth_requests_per_minute
        self._buckets = defaultdict(lambda: {"tokens": burst_size, "last_refill": time.time()})
        self._auth_buckets = defaultdict(lambda: {"tokens": 5, "last_refill": time.time()})

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # Stricter limits for auth endpoints
        is_auth = path.startswith("/api/auth/login") or path.startswith("/api/auth/register")

        if is_auth:
            bucket = self._auth_buckets[client_ip]
            rate = self.auth_requests_per_minute
        else:
            bucket = self._buckets[client_ip]
            rate = self.requests_per_minute

        # Refill tokens
        now = time.time()
        elapsed = now - bucket["last_refill"]
        refill = elapsed * (rate / 60.0)
        max_tokens = self.burst_size if not is_auth else 5
        bucket["tokens"] = min(max_tokens, bucket["tokens"] + refill)
        bucket["last_refill"] = now

        # Check if request is allowed
        if bucket["tokens"] < 1:
            logger.warning("Rate limit exceeded for IP %s on %s", client_ip, path)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please try again later.",
                    "retry_after_seconds": int(60 / rate),
                },
                headers={"Retry-After": str(int(60 / rate))},
            )

        bucket["tokens"] -= 1
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(rate)
        response.headers["X-RateLimit-Remaining"] = str(int(bucket["tokens"]))

        return response


class RateLimiter:
    """
    Dependency-based rate limiter for granular control on specific routes.

    Usage:
        @router.post("/sensitive-endpoint")
        async def endpoint(request: Request, _=Depends(RateLimiter(max_requests=5, window_seconds=60))):
            ...
    """

    _store = defaultdict(list)

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def __call__(self, request: Request):
        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{request.url.path}"
        now = time.time()

        # Clean old entries
        RateLimiter._store[key] = [
            t for t in RateLimiter._store[key] if now - t < self.window_seconds
        ]

        if len(RateLimiter._store[key]) >= self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Max {self.max_requests} requests per {self.window_seconds}s.",
            )

        RateLimiter._store[key].append(now)

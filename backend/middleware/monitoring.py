"""
Monitoring middleware for KeyForge.
Provides structured logging, request metrics, and health indicators.
"""
import time
import logging
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("keyforge.monitoring")


class RequestMetrics:
    """In-memory metrics collector for request monitoring."""

    def __init__(self):
        self.request_count = defaultdict(int)  # {method:path: count}
        self.error_count = defaultdict(int)     # {status_code: count}
        self.response_times = []                # Last N response times
        self.max_response_times = 1000
        self._start_time = time.time()

    def record_request(self, method: str, path: str, status_code: int, duration_ms: float):
        key = f"{method} {path}"
        self.request_count[key] += 1

        if status_code >= 400:
            self.error_count[status_code] += 1

        self.response_times.append({
            "path": key,
            "status": status_code,
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Keep only last N entries
        if len(self.response_times) > self.max_response_times:
            self.response_times = self.response_times[-self.max_response_times:]

    def get_summary(self) -> Dict:
        """Get metrics summary."""
        uptime = time.time() - self._start_time
        total_requests = sum(self.request_count.values())
        total_errors = sum(self.error_count.values())

        avg_response_time = 0
        if self.response_times:
            avg_response_time = sum(
                r["duration_ms"] for r in self.response_times
            ) / len(self.response_times)

        # Top 10 endpoints by request count
        top_endpoints = sorted(
            self.request_count.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        return {
            "uptime_seconds": round(uptime, 1),
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": round(total_errors / max(total_requests, 1) * 100, 2),
            "avg_response_time_ms": round(avg_response_time, 2),
            "top_endpoints": [
                {"endpoint": ep, "count": count} for ep, count in top_endpoints
            ],
            "error_breakdown": dict(self.error_count),
        }

    def get_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []
        lines.append("# HELP keyforge_requests_total Total HTTP requests")
        lines.append("# TYPE keyforge_requests_total counter")
        for endpoint, count in self.request_count.items():
            method, path = endpoint.split(" ", 1)
            lines.append(
                f'keyforge_requests_total{{method="{method}",path="{path}"}} {count}'
            )

        lines.append("# HELP keyforge_errors_total Total HTTP errors by status code")
        lines.append("# TYPE keyforge_errors_total counter")
        for code, count in self.error_count.items():
            lines.append(f'keyforge_errors_total{{status_code="{code}"}} {count}')

        uptime = time.time() - self._start_time
        lines.append("# HELP keyforge_uptime_seconds Server uptime in seconds")
        lines.append("# TYPE keyforge_uptime_seconds gauge")
        lines.append(f"keyforge_uptime_seconds {round(uptime, 1)}")

        return "\n".join(lines) + "\n"


# Global metrics instance
metrics = RequestMetrics()


class MonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware that logs requests and collects metrics."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Normalize path (replace UUIDs with placeholder)
        path = request.url.path

        # Record metrics
        metrics.record_request(
            method=request.method,
            path=path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        # Structured log for non-health requests
        if path != "/api/health" and path != "/api/metrics":
            log_data = {
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "client_ip": request.client.host if request.client else "unknown",
            }

            if response.status_code >= 500:
                logger.error("Request failed: %s", json.dumps(log_data))
            elif response.status_code >= 400:
                logger.warning("Client error: %s", json.dumps(log_data))
            else:
                logger.info("Request: %s", json.dumps(log_data))

        # Add timing header
        response.headers["X-Response-Time"] = f"{duration_ms:.0f}ms"

        return response

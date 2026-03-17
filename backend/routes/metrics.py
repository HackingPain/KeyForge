"""Metrics and monitoring endpoints for KeyForge."""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from backend.middleware.monitoring import metrics

router = APIRouter(tags=["monitoring"])


@router.get("/api/metrics")
async def get_metrics():
    """Get application metrics summary (JSON)."""
    return metrics.get_summary()


@router.get("/api/metrics/prometheus", response_class=PlainTextResponse)
async def get_prometheus_metrics():
    """Get metrics in Prometheus text exposition format."""
    return metrics.get_prometheus_metrics()

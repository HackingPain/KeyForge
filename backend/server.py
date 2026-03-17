"""KeyForge API — Universal API Infrastructure Assistant (v5.0)"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware
import logging
import sys
from pathlib import Path

# Ensure the backend package is importable when running via `uvicorn server:app`
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import client, db

# Middleware
from backend.middleware.rate_limiter import RateLimitMiddleware
from backend.middleware.sanitizer import SanitizationMiddleware
from backend.middleware.monitoring import MonitoringMiddleware
from backend.middleware.error_handler import (
    http_exception_handler,
    validation_exception_handler,
    generic_exception_handler,
)

# API documentation metadata
from backend.utils.api_docs import TAGS_METADATA, API_DESCRIPTION

# Migrations
from backend.migrations.runner import run_migrations
import backend.migrations.versions  # noqa: F401 — register migrations

# Core routers
from backend.routes.auth import router as auth_router
from backend.routes.credentials import router as credentials_router
from backend.routes.projects import router as projects_router
from backend.routes.dashboard import router as dashboard_router

# Phase 4 routers
from backend.routes.rotation import router as rotation_router
from backend.routes.audit import router as audit_router
from backend.routes.health_checks import router as health_checks_router
from backend.routes.teams import router as teams_router
from backend.routes.credential_groups import router as credential_groups_router
from backend.routes.scanning import router as scanning_router
from backend.routes.import_export import router as import_export_router
from backend.routes.webhooks import router as webhooks_router
from backend.routes.cost_estimation import router as cost_estimation_router

# Phase 5 routers — Security
from backend.routes.mfa import router as mfa_router
from backend.routes.ip_allowlist import router as ip_allowlist_router
from backend.routes.sessions import router as sessions_router
from backend.routes.encryption_admin import router as encryption_admin_router

# Phase 5 routers — Credential Lifecycle
from backend.routes.expiration import router as expiration_router
from backend.routes.credential_permissions import router as credential_permissions_router
from backend.routes.versioning import router as versioning_router
from backend.routes.auto_rotation import router as auto_rotation_router

# Phase 5 routers — Analytics & Compliance
from backend.routes.breach_detection import router as breach_detection_router
from backend.routes.usage_analytics import router as usage_analytics_router
from backend.routes.compliance import router as compliance_router
from backend.routes.lifecycle import router as lifecycle_router

# Monitoring router
from backend.routes.metrics import router as metrics_router

# Phase 7 routers — Security Hardening
from backend.routes.envelope_encryption import router as envelope_encryption_router
from backend.routes.kms_admin import router as kms_admin_router
from backend.routes.audit_integrity import router as audit_integrity_router
from backend.routes.proxy import router as proxy_router
from backend.routes.field_encryption import router as field_encryption_router
from backend.routes.backup import router as backup_router
from backend.routes.expiration_policy import router as expiration_policy_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("keyforge")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan handler: create indexes on startup, close DB on shutdown."""
    logger.info("KeyForge starting up...")
    await create_indexes()
    await run_migrations(db)
    yield
    logger.info("KeyForge shutting down...")
    client.close()


async def create_indexes():
    """Create MongoDB indexes for performance."""
    try:
        # Users
        await db.users.create_index("username", unique=True)
        await db.users.create_index("id", unique=True)

        # Credentials
        await db.credentials.create_index("id", unique=True)
        await db.credentials.create_index("user_id")
        await db.credentials.create_index([("user_id", 1), ("api_name", 1)])

        # Project analyses
        await db.project_analyses.create_index("id", unique=True)
        await db.project_analyses.create_index("user_id")
        await db.project_analyses.create_index(
            [("user_id", 1), ("analysis_timestamp", -1)]
        )

        # Rotation policies
        await db.rotation_policies.create_index("id", unique=True)
        await db.rotation_policies.create_index("user_id")
        await db.rotation_policies.create_index("credential_id")

        # Audit log
        await db.audit_log.create_index([("user_id", 1), ("timestamp", -1)])
        await db.audit_log.create_index("action")

        # Health checks
        await db.health_check_results.create_index(
            [("user_id", 1), ("checked_at", -1)]
        )
        await db.health_check_results.create_index("credential_id")
        await db.health_check_schedules.create_index("user_id", unique=True)

        # Teams
        await db.teams.create_index("id", unique=True)
        await db.teams.create_index("owner_id")
        await db.team_members.create_index([("team_id", 1), ("user_id", 1)])

        # Credential groups
        await db.credential_groups.create_index("id", unique=True)
        await db.credential_groups.create_index("user_id")

        # Scan results
        await db.scan_results.create_index([("user_id", 1), ("timestamp", -1)])

        # Webhooks
        await db.webhooks.create_index("id", unique=True)
        await db.webhooks.create_index("user_id")

        # IP Allowlist
        await db.ip_allowlist.create_index([("user_id", 1), ("ip_address", 1)])

        # Sessions
        await db.sessions.create_index("user_id")
        await db.sessions.create_index("token_hash", unique=True)

        # Expirations
        await db.credential_expirations.create_index("user_id")
        await db.credential_expirations.create_index("credential_id")
        await db.credential_expirations.create_index(
            [("user_id", 1), ("expires_at", 1)]
        )

        # Credential permissions
        await db.credential_permissions.create_index(
            [("credential_id", 1), ("user_id", 1)]
        )
        await db.credential_permissions.create_index("granted_by")

        # Credential versions
        await db.credential_versions.create_index(
            [("credential_id", 1), ("version_number", -1)]
        )

        # Auto-rotation configs
        await db.auto_rotation_configs.create_index("user_id")
        await db.auto_rotation_configs.create_index("credential_id")

        # Breach checks
        await db.breach_checks.create_index([("user_id", 1), ("check_timestamp", -1)])

        # Usage events
        await db.usage_events.create_index([("user_id", 1), ("timestamp", -1)])
        await db.usage_events.create_index("credential_id")

        # Compliance reports
        await db.compliance_reports.create_index(
            [("user_id", 1), ("generated_at", -1)]
        )

        # Lifecycle events
        await db.lifecycle_events.create_index(
            [("credential_id", 1), ("timestamp", 1)]
        )
        await db.lifecycle_events.create_index([("user_id", 1), ("timestamp", -1)])

        # Phase 7 — Envelope encryption
        await db.user_data_keys.create_index("user_id")
        await db.user_data_keys.create_index("key_id", unique=True)

        # Proxy tokens
        await db.proxy_tokens.create_index("user_id")
        await db.proxy_tokens.create_index("token_id", unique=True)
        await db.proxy_tokens.create_index("expires_at")

        # Backups
        await db.backups.create_index("backup_id", unique=True)
        await db.backups.create_index("user_id")

        # Expiration policies
        await db.expiration_policies.create_index("user_id", unique=True)
        await db.policy_exemptions.create_index([("credential_id", 1), ("user_id", 1)])
        await db.rotation_requirements.create_index("credential_id")

        # Audit integrity (chained entries)
        await db.audit_chain.create_index([("user_id", 1), ("timestamp", 1)])

        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.warning("Index creation warning: %s", e)


app = FastAPI(
    title="KeyForge API",
    description=API_DESCRIPTION,
    version="5.0.0",
    lifespan=lifespan,
    openapi_tags=TAGS_METADATA,
)

# Exception handlers — standardized error responses
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Core routers
app.include_router(auth_router)
app.include_router(credentials_router)
app.include_router(projects_router)
app.include_router(dashboard_router)

# Phase 4 routers
app.include_router(rotation_router)
app.include_router(audit_router)
app.include_router(health_checks_router)
app.include_router(teams_router)
app.include_router(credential_groups_router)
app.include_router(scanning_router)
app.include_router(import_export_router)
app.include_router(webhooks_router)
app.include_router(cost_estimation_router)

# Phase 5 routers — Security
app.include_router(mfa_router)
app.include_router(ip_allowlist_router)
app.include_router(sessions_router)
app.include_router(encryption_admin_router)

# Phase 5 routers — Credential Lifecycle
app.include_router(expiration_router)
app.include_router(credential_permissions_router)
app.include_router(versioning_router)
app.include_router(auto_rotation_router)

# Phase 5 routers — Analytics & Compliance
app.include_router(breach_detection_router)
app.include_router(usage_analytics_router)
app.include_router(compliance_router)
app.include_router(lifecycle_router)

# Monitoring
app.include_router(metrics_router)

# Phase 7 routers — Security Hardening
app.include_router(envelope_encryption_router)
app.include_router(kms_admin_router)
app.include_router(audit_integrity_router)
app.include_router(proxy_router)
app.include_router(field_encryption_router)
app.include_router(backup_router)
app.include_router(expiration_policy_router)

# Middleware stack (order matters — outermost first)
# Monitoring wraps everything to capture timing
app.add_middleware(MonitoringMiddleware)
# Rate limiting before request processing
app.add_middleware(RateLimitMiddleware)
# Input sanitization for JSON bodies
app.add_middleware(SanitizationMiddleware)

# CORS — allow the frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/")
async def root():
    return {"message": "KeyForge API Infrastructure Assistant", "version": "5.0.0"}


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    try:
        await db.command("ping")
        return {"status": "healthy", "database": "connected"}
    except Exception:
        return {"status": "degraded", "database": "disconnected"}

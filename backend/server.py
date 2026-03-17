"""KeyForge API — Universal API Infrastructure Assistant (v3.0)"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
import logging
import sys
from pathlib import Path

# Ensure the backend package is importable when running via `uvicorn server:app`
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import client, db

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

        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.warning("Index creation warning: %s", e)


app = FastAPI(
    title="KeyForge API",
    description="Universal API Infrastructure Assistant",
    version="3.0.0",
    lifespan=lifespan,
)

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
    return {"message": "KeyForge API Infrastructure Assistant", "version": "3.0.0"}


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    try:
        await db.command("ping")
        return {"status": "healthy", "database": "connected"}
    except Exception:
        return {"status": "degraded", "database": "disconnected"}

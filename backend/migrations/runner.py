"""
Simple database migration runner for KeyForge.

Migrations are stored in the `migrations` collection with their version number.
Each migration runs once and is recorded after successful execution.

Usage:
    from backend.migrations.runner import run_migrations
    await run_migrations(db)  # Call during app startup
"""
import logging
from datetime import datetime, timezone
from typing import List, Callable, Awaitable
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger("keyforge.migrations")


class Migration:
    """Represents a single database migration."""

    def __init__(self, version: int, name: str, up: Callable[[AsyncIOMotorDatabase], Awaitable[None]]):
        self.version = version
        self.name = name
        self.up = up

    def __repr__(self):
        return f"Migration(v{self.version}: {self.name})"


# Migration registry
_migrations: List[Migration] = []


def migration(version: int, name: str):
    """Decorator to register a migration function."""
    def decorator(func: Callable[[AsyncIOMotorDatabase], Awaitable[None]]):
        _migrations.append(Migration(version=version, name=name, up=func))
        return func
    return decorator


async def get_current_version(db: AsyncIOMotorDatabase) -> int:
    """Get the current migration version from the database."""
    latest = await db.migrations.find_one(
        sort=[("version", -1)]
    )
    return latest["version"] if latest else 0


async def run_migrations(db: AsyncIOMotorDatabase) -> int:
    """
    Run all pending migrations in order.
    Returns the number of migrations applied.
    """
    current = await get_current_version(db)
    pending = sorted(
        [m for m in _migrations if m.version > current],
        key=lambda m: m.version,
    )

    if not pending:
        logger.info("Database is up to date (version %d)", current)
        return 0

    logger.info(
        "Running %d migration(s) from v%d to v%d",
        len(pending), current, pending[-1].version,
    )

    applied = 0
    for m in pending:
        try:
            logger.info("Applying migration v%d: %s", m.version, m.name)
            await m.up(db)
            await db.migrations.insert_one({
                "version": m.version,
                "name": m.name,
                "applied_at": datetime.now(timezone.utc),
            })
            applied += 1
            logger.info("Migration v%d applied successfully", m.version)
        except Exception:
            logger.exception("Migration v%d failed: %s", m.version, m.name)
            raise

    return applied

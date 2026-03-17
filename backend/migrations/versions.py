"""
Migration versions for KeyForge database.

Each migration is registered with @migration(version, name) decorator.
Migrations run in version order and are idempotent where possible.
"""
from backend.migrations.runner import migration


@migration(1, "create_initial_indexes")
async def create_initial_indexes(db):
    """Create all initial database indexes."""
    # Users
    await db.users.create_index("username", unique=True)
    await db.users.create_index("id", unique=True)

    # Credentials
    await db.credentials.create_index("id", unique=True)
    await db.credentials.create_index("user_id")
    await db.credentials.create_index([("user_id", 1), ("api_name", 1)])


@migration(2, "add_phase4_indexes")
async def add_phase4_indexes(db):
    """Add indexes for Phase 4 features."""
    await db.rotation_policies.create_index("id", unique=True)
    await db.rotation_policies.create_index("user_id")
    await db.audit_log.create_index([("user_id", 1), ("timestamp", -1)])
    await db.health_check_results.create_index([("user_id", 1), ("checked_at", -1)])
    await db.teams.create_index("id", unique=True)
    await db.credential_groups.create_index("id", unique=True)
    await db.scan_results.create_index([("user_id", 1), ("timestamp", -1)])
    await db.webhooks.create_index("id", unique=True)


@migration(3, "add_phase5_indexes")
async def add_phase5_indexes(db):
    """Add indexes for Phase 5 features."""
    await db.ip_allowlist.create_index([("user_id", 1), ("ip_address", 1)])
    await db.sessions.create_index("user_id")
    await db.sessions.create_index("token_hash", unique=True)
    await db.credential_expirations.create_index([("user_id", 1), ("expires_at", 1)])
    await db.credential_permissions.create_index([("credential_id", 1), ("user_id", 1)])
    await db.credential_versions.create_index([("credential_id", 1), ("version_number", -1)])
    await db.auto_rotation_configs.create_index("credential_id")
    await db.breach_checks.create_index([("user_id", 1), ("check_timestamp", -1)])
    await db.usage_events.create_index([("user_id", 1), ("timestamp", -1)])
    await db.compliance_reports.create_index([("user_id", 1), ("generated_at", -1)])
    await db.lifecycle_events.create_index([("credential_id", 1), ("timestamp", 1)])


@migration(4, "add_mfa_fields_to_users")
async def add_mfa_fields(db):
    """Ensure user documents have MFA-related fields."""
    await db.users.update_many(
        {"mfa_secret": {"$exists": False}},
        {"$set": {"mfa_secret": None, "mfa_backup_codes": [], "mfa_enabled": False}},
    )


@migration(5, "add_encryption_metadata")
async def add_encryption_metadata(db):
    """Create encryption metadata collection for tracking key rotation."""
    await db.encryption_metadata.insert_one({
        "type": "key_info",
        "algorithm": "Fernet (AES-128-CBC + HMAC-SHA256)",
        "last_rotation": None,
        "total_rotations": 0,
    })

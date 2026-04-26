"""
API documentation configuration and metadata for KeyForge.

Provides OpenAPI tags, descriptions, and example responses for all route groups.
"""

# Tag metadata for OpenAPI documentation
TAGS_METADATA = [
    {
        "name": "auth",
        "description": "User authentication: registration, login, and token management.",
    },
    {
        "name": "credentials",
        "description": "CRUD operations for API credentials. All keys are encrypted at rest using Fernet symmetric encryption.",
    },
    {
        "name": "projects",
        "description": "Project analysis: detect API usage patterns in source code.",
    },
    {
        "name": "dashboard",
        "description": "Dashboard overview statistics and API catalog.",
    },
    {
        "name": "rotation",
        "description": "Key rotation policy management. Track when credentials need to be rotated.",
    },
    {
        "name": "audit",
        "description": "Audit log: track all user actions for compliance and security monitoring.",
    },
    {
        "name": "health-checks",
        "description": "Scheduled and manual health checks for credential validation.",
    },
    {
        "name": "teams",
        "description": "Team/organization management with role-based access control.",
    },
    {
        "name": "credential-groups",
        "description": "Organize credentials into logical groups.",
    },
    {
        "name": "scanning",
        "description": "Secret scanning: detect hardcoded credentials, suggest masking, analyze dependencies.",
    },
    {
        "name": "import-export",
        "description": "Import credentials from .env/JSON files. Export for backup or migration.",
    },
    {
        "name": "webhooks",
        "description": "Webhook notifications for credential events (expiration, test failure, etc).",
    },
    {
        "name": "mfa",
        "description": "Multi-factor authentication (TOTP) setup and management.",
    },
    {
        "name": "ip-allowlist",
        "description": "IP address allowlisting for additional access control.",
    },
    {
        "name": "sessions",
        "description": "Active session management and token revocation.",
    },
    {
        "name": "encryption-admin",
        "description": "Encryption key management and credential re-encryption.",
    },
    {
        "name": "expiration",
        "description": "Credential expiration tracking with configurable alert windows.",
    },
    {
        "name": "credential-permissions",
        "description": "Per-credential role-based access control (read/use/manage/admin).",
    },
    {
        "name": "versioning",
        "description": "Credential version history with rollback capability.",
    },
    {
        "name": "auto-rotation",
        "description": "Automatic credential rotation configuration for supported providers.",
    },
    {
        "name": "usage-analytics",
        "description": "Credential usage tracking, idle detection, and analytics.",
    },
    {
        "name": "compliance",
        "description": "Compliance scoring and report generation (SOC2, GDPR, general).",
    },
    {
        "name": "lifecycle",
        "description": "Credential lifecycle event tracking and timeline visualization.",
    },
]

# Common response examples for documentation
COMMON_RESPONSES = {
    401: {
        "description": "Unauthorized - Invalid or missing authentication token",
        "content": {
            "application/json": {
                "example": {
                    "error": True,
                    "status_code": 401,
                    "message": "Could not validate credentials",
                }
            }
        },
    },
    422: {
        "description": "Validation Error - Invalid request body",
        "content": {
            "application/json": {
                "example": {
                    "error": True,
                    "status_code": 422,
                    "message": "Validation error",
                    "details": [
                        {
                            "field": "body -> api_name",
                            "message": "field required",
                            "type": "missing",
                        }
                    ],
                }
            }
        },
    },
    429: {
        "description": "Too Many Requests - Rate limit exceeded",
        "content": {
            "application/json": {
                "example": {
                    "detail": "Too many requests. Please try again later.",
                    "retry_after_seconds": 6,
                }
            }
        },
    },
}


# API description for the OpenAPI docs page
API_DESCRIPTION = """
# KeyForge API

**Universal API Infrastructure Assistant** - Securely manage, validate, and monitor all your API credentials in one place.

## Features

- **Credential Management**: Store API keys encrypted at rest (Fernet). Support for 27+ providers.
- **Real Validation**: Format checks + live API calls for OpenAI, Stripe, GitHub, and more.
- **Security**: MFA/TOTP, IP allowlisting, session management, audit logging.
- **Team Collaboration**: Teams with RBAC, credential sharing, per-credential permissions.
- **Lifecycle Management**: Expiration tracking, version history, auto-rotation.
- **Analytics**: Usage tracking, breach detection, compliance scoring (SOC2/GDPR).
- **Developer Tools**: CLI, Python SDK, VS Code extension, GitHub App.

## Authentication

All endpoints (except `/api/auth/register` and `/api/auth/login`) require a Bearer token:

```
Authorization: Bearer <your-jwt-token>
```

Get a token by calling `POST /api/auth/login` with your username and password.
"""

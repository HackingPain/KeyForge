"""Repo scanning, secret detection, and dependency analysis for KeyForge."""

import re
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger("keyforge.scanners")

# ── Secret detection patterns ─────────────────────────────────────────────────

# Regex patterns for known API key formats with severity levels
SECRET_PATTERNS = [
    {
        "name": "OpenAI API Key",
        "regex": r"sk-[a-zA-Z0-9]{40,}",
        "type": "openai_api_key",
        "severity": "critical",
        "env_var": "OPENAI_API_KEY",
    },
    {
        "name": "AWS Access Key ID",
        "regex": r"AKIA[0-9A-Z]{16}",
        "type": "aws_access_key",
        "severity": "critical",
        "env_var": "AWS_ACCESS_KEY_ID",
    },
    {
        "name": "GitHub Personal Access Token",
        "regex": r"ghp_[a-zA-Z0-9]{36}",
        "type": "github_pat",
        "severity": "critical",
        "env_var": "GITHUB_TOKEN",
    },
    {
        "name": "Stripe Test Key",
        "regex": r"sk_test_[a-zA-Z0-9]{20,}",
        "type": "stripe_test_key",
        "severity": "high",
        "env_var": "STRIPE_SECRET_KEY",
    },
    {
        "name": "Stripe Live Key",
        "regex": r"sk_live_[a-zA-Z0-9]{20,}",
        "type": "stripe_live_key",
        "severity": "critical",
        "env_var": "STRIPE_SECRET_KEY",
    },
    {
        "name": "SendGrid API Key",
        "regex": r"SG\.[a-zA-Z0-9_\-]{22,}\.[a-zA-Z0-9_\-]{22,}",
        "type": "sendgrid_api_key",
        "severity": "critical",
        "env_var": "SENDGRID_API_KEY",
    },
    {
        "name": "Twilio API Key",
        "regex": r"SK[0-9a-fA-F]{32}",
        "type": "twilio_api_key",
        "severity": "critical",
        "env_var": "TWILIO_API_KEY",
    },
    {
        "name": "Slack Token",
        "regex": r"xox[bpors]-[0-9a-zA-Z\-]{10,}",
        "type": "slack_token",
        "severity": "critical",
        "env_var": "SLACK_TOKEN",
    },
    {
        "name": "Google API Key",
        "regex": r"AIza[0-9A-Za-z_\-]{35}",
        "type": "google_api_key",
        "severity": "high",
        "env_var": "GOOGLE_API_KEY",
    },
    {
        "name": "GitHub OAuth Client Secret",
        "regex": r"gho_[a-zA-Z0-9]{36}",
        "type": "github_oauth",
        "severity": "critical",
        "env_var": "GITHUB_CLIENT_SECRET",
    },
    {
        "name": "Supabase Anon/Service Key",
        "regex": r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[a-zA-Z0-9_\-]{50,}",
        "type": "supabase_key",
        "severity": "high",
        "env_var": "SUPABASE_ANON_KEY",
    },
]

# Patterns for variable assignments containing secrets
ASSIGNMENT_PATTERNS = [
    {
        "regex": r"""(?:api_key|apikey|api_secret|apisecret)\s*=\s*["']([^"']{8,})["']""",
        "type": "hardcoded_api_key",
        "severity": "critical",
        "env_var": "API_KEY",
    },
    {
        "regex": r"""(?:password|passwd|pwd)\s*=\s*["']([^"']{4,})["']""",
        "type": "hardcoded_password",
        "severity": "critical",
        "env_var": "PASSWORD",
    },
    {
        "regex": r"""(?:secret|secret_key|secretkey)\s*=\s*["']([^"']{8,})["']""",
        "type": "hardcoded_secret",
        "severity": "critical",
        "env_var": "SECRET_KEY",
    },
    {
        "regex": r"""(?:token|access_token|auth_token)\s*=\s*["']([^"']{8,})["']""",
        "type": "hardcoded_token",
        "severity": "high",
        "env_var": "AUTH_TOKEN",
    },
    {
        "regex": r"""(?:database_url|db_url|mongo_url|mongo_uri)\s*=\s*["']([^"']{10,})["']""",
        "type": "hardcoded_database_url",
        "severity": "critical",
        "env_var": "DATABASE_URL",
    },
]

# Environment-style variable assignments (not referencing env vars)
ENV_ASSIGNMENT_PATTERNS = [
    {
        "regex": r"""^(?:export\s+)?([A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL)[A-Z0-9_]*)=(?!.*(?:\$\{|\$[A-Z]|os\.environ|process\.env))["']?([^\s"']{8,})["']?\s*$""",
        "type": "env_variable_secret",
        "severity": "high",
    },
]

# Connection string with embedded password
CONNECTION_STRING_PATTERNS = [
    {
        "regex": r"""(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:\s]+:([^@\s]{3,})@[^\s]+""",
        "type": "connection_string_password",
        "severity": "critical",
        "env_var": "DATABASE_URL",
    },
]

# PEM private key detection
PEM_PATTERN = {
    "regex": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
    "type": "private_key",
    "severity": "critical",
    "env_var": "PRIVATE_KEY",
}


# ── Language detection ─────────────────────────────────────────────────────────

LANG_ENV_SYNTAX = {
    ".py": 'os.environ["{var}"]',
    ".js": "process.env.{var}",
    ".ts": "process.env.{var}",
    ".jsx": "process.env.{var}",
    ".tsx": "process.env.{var}",
    ".rb": 'ENV["{var}"]',
    ".go": 'os.Getenv("{var}")',
    ".java": 'System.getenv("{var}")',
    ".rs": 'std::env::var("{var}")',
    ".php": '$_ENV["{var}"]',
    ".sh": '"${var}"',
    ".bash": '"${var}"',
    ".yml": '"${var}"',
    ".yaml": '"${var}"',
}


def _get_env_replacement(ext: str, env_var: str) -> str:
    """Return the language-appropriate env var access snippet."""
    template = LANG_ENV_SYNTAX.get(ext, 'os.environ["{var}"]')
    return template.format(var=env_var)


def _truncate_match(value: str, max_len: int = 8) -> str:
    """Show at most the first *max_len* characters of a matched value."""
    if len(value) <= max_len:
        return value
    return value[:max_len] + "..."


# ── Public API ─────────────────────────────────────────────────────────────────


def scan_content_for_secrets(content: str, filename: str) -> List[Dict]:
    """Scan file content for hardcoded secrets and embedded keys.

    Returns a list of findings, each containing line number, type, a
    truncated matched value, severity, and a remediation suggestion.
    """
    findings: List[Dict] = []
    lines = content.splitlines()

    for line_no, line in enumerate(lines, start=1):
        # 1. Known API key format patterns
        for sp in SECRET_PATTERNS:
            match = re.search(sp["regex"], line)
            if match:
                matched_value = match.group(0)
                findings.append({
                    "line": line_no,
                    "type": sp["type"],
                    "matched_value": _truncate_match(matched_value),
                    "severity": sp["severity"],
                    "suggestion": (
                        f"Replace hardcoded {sp['name']} with environment variable "
                        f"{sp['env_var']}."
                    ),
                })

        # 2. Assignment patterns (api_key = "...", password = "...", etc.)
        for ap in ASSIGNMENT_PATTERNS:
            match = re.search(ap["regex"], line, re.IGNORECASE)
            if match:
                secret_value = match.group(1) if match.lastindex else match.group(0)
                # Skip placeholder / example values
                if secret_value.lower() in (
                    "your_api_key_here",
                    "changeme",
                    "xxx",
                    "todo",
                    "replace_me",
                    "placeholder",
                ):
                    continue
                findings.append({
                    "line": line_no,
                    "type": ap["type"],
                    "matched_value": _truncate_match(secret_value),
                    "severity": ap["severity"],
                    "suggestion": (
                        f"Move this value to an environment variable "
                        f"(e.g. {ap['env_var']}) and load it at runtime."
                    ),
                })

        # 3. Env-style assignments with real values (not references)
        for ep in ENV_ASSIGNMENT_PATTERNS:
            match = re.search(ep["regex"], line, re.MULTILINE)
            if match:
                var_name = match.group(1)
                var_value = match.group(2)
                findings.append({
                    "line": line_no,
                    "type": ep["type"],
                    "matched_value": _truncate_match(var_value),
                    "severity": ep["severity"],
                    "suggestion": (
                        f"Do not commit {var_name} with a real value. "
                        f"Use a .env file (excluded via .gitignore) or a secrets manager."
                    ),
                })

        # 4. Connection strings with embedded passwords
        for cp in CONNECTION_STRING_PATTERNS:
            match = re.search(cp["regex"], line)
            if match:
                password_part = match.group(1)
                findings.append({
                    "line": line_no,
                    "type": cp["type"],
                    "matched_value": _truncate_match(password_part),
                    "severity": cp["severity"],
                    "suggestion": (
                        f"Move the connection string to an environment variable "
                        f"(e.g. {cp['env_var']}) so the password is never in code."
                    ),
                })

        # 5. PEM private keys
        if re.search(PEM_PATTERN["regex"], line):
            findings.append({
                "line": line_no,
                "type": PEM_PATTERN["type"],
                "matched_value": "-----BEG...",
                "severity": PEM_PATTERN["severity"],
                "suggestion": (
                    "Never embed private keys in source code. "
                    "Store them in a secure vault or load via a file path "
                    "referenced by an environment variable."
                ),
            })

    logger.info(
        "Scanned %s: found %d potential secret(s) across %d lines",
        filename,
        len(findings),
        len(lines),
    )
    return findings


def suggest_key_masking(content: str, filename: str) -> List[Dict]:
    """For each detected secret, suggest how to replace it in code.

    Returns replacement snippets appropriate for the file's language.
    """
    secrets = scan_content_for_secrets(content, filename)
    ext = Path(filename).suffix.lower()
    lines = content.splitlines()
    suggestions: List[Dict] = []

    for secret in secrets:
        line_no = secret["line"]
        original_line = lines[line_no - 1] if line_no <= len(lines) else ""

        # Determine env var name
        env_var = _derive_env_var_name(secret)
        replacement_snippet = _get_env_replacement(ext, env_var)

        # Build a truncated original snippet (max 80 chars)
        original_snippet = original_line.strip()
        if len(original_snippet) > 80:
            original_snippet = original_snippet[:77] + "..."

        suggestions.append({
            "line": line_no,
            "original_snippet": original_snippet,
            "suggested_replacement": replacement_snippet,
            "env_var_name": env_var,
        })

    return suggestions


def _derive_env_var_name(secret: Dict) -> str:
    """Pick a meaningful env-var name based on the secret type."""
    type_to_env: Dict[str, str] = {
        "openai_api_key": "OPENAI_API_KEY",
        "aws_access_key": "AWS_ACCESS_KEY_ID",
        "github_pat": "GITHUB_TOKEN",
        "stripe_test_key": "STRIPE_SECRET_KEY",
        "stripe_live_key": "STRIPE_SECRET_KEY",
        "sendgrid_api_key": "SENDGRID_API_KEY",
        "twilio_api_key": "TWILIO_API_KEY",
        "slack_token": "SLACK_TOKEN",
        "google_api_key": "GOOGLE_API_KEY",
        "github_oauth": "GITHUB_CLIENT_SECRET",
        "supabase_key": "SUPABASE_ANON_KEY",
        "hardcoded_api_key": "API_KEY",
        "hardcoded_password": "PASSWORD",
        "hardcoded_secret": "SECRET_KEY",
        "hardcoded_token": "AUTH_TOKEN",
        "hardcoded_database_url": "DATABASE_URL",
        "connection_string_password": "DATABASE_URL",
        "private_key": "PRIVATE_KEY_PATH",
        "env_variable_secret": "SECRET",
    }
    return type_to_env.get(secret.get("type", ""), "SECRET_VALUE")


# ── Dependency analysis ────────────────────────────────────────────────────────

# Maps package names (as they appear in dependency files) to API metadata.
PACKAGE_TO_API = {
    # Python packages
    "openai": {"api": "openai", "credential_type": "api_key"},
    "stripe": {"api": "stripe", "credential_type": "api_key"},
    "boto3": {"api": "aws", "credential_type": "access_key"},
    "botocore": {"api": "aws", "credential_type": "access_key"},
    "google-cloud-storage": {"api": "gcp", "credential_type": "service_account"},
    "google-cloud-bigquery": {"api": "gcp", "credential_type": "service_account"},
    "google-cloud-pubsub": {"api": "gcp", "credential_type": "service_account"},
    "google-cloud-firestore": {"api": "firebase", "credential_type": "service_account"},
    "firebase-admin": {"api": "firebase", "credential_type": "service_account"},
    "pymongo": {"api": "mongodb_cred", "credential_type": "connection_string"},
    "psycopg2": {"api": "postgresql", "credential_type": "connection_string"},
    "psycopg2-binary": {"api": "postgresql", "credential_type": "connection_string"},
    "asyncpg": {"api": "postgresql", "credential_type": "connection_string"},
    "mysql-connector-python": {"api": "mysql", "credential_type": "connection_string"},
    "mysqlclient": {"api": "mysql", "credential_type": "connection_string"},
    "redis": {"api": "redis", "credential_type": "connection_string"},
    "sendgrid": {"api": "sendgrid", "credential_type": "api_key"},
    "twilio": {"api": "twilio", "credential_type": "api_key"},
    "PyGithub": {"api": "github", "credential_type": "token"},
    "azure-identity": {"api": "azure", "credential_type": "client_credentials"},
    "azure-storage-blob": {"api": "azure", "credential_type": "client_credentials"},
    "supabase": {"api": "supabase", "credential_type": "api_key"},
    # JavaScript / Node packages
    "@supabase/supabase-js": {"api": "supabase", "credential_type": "api_key"},
    "@sendgrid/mail": {"api": "sendgrid", "credential_type": "api_key"},
    "@octokit/rest": {"api": "github", "credential_type": "token"},
    "firebase": {"api": "firebase", "credential_type": "config"},
    "firebase-admin": {"api": "firebase", "credential_type": "service_account"},
    "aws-sdk": {"api": "aws", "credential_type": "access_key"},
    "@aws-sdk/client-s3": {"api": "aws", "credential_type": "access_key"},
    "@aws-sdk/client-dynamodb": {"api": "aws", "credential_type": "access_key"},
    "@stripe/stripe-js": {"api": "stripe", "credential_type": "api_key"},
    "ioredis": {"api": "redis", "credential_type": "connection_string"},
    "pg": {"api": "postgresql", "credential_type": "connection_string"},
    "mongodb": {"api": "mongodb_cred", "credential_type": "connection_string"},
    "mongoose": {"api": "mongodb_cred", "credential_type": "connection_string"},
    "mysql2": {"api": "mysql", "credential_type": "connection_string"},
    "@azure/identity": {"api": "azure", "credential_type": "client_credentials"},
    "@google-cloud/storage": {"api": "gcp", "credential_type": "service_account"},
    # Go modules
    "github.com/stripe/stripe-go": {"api": "stripe", "credential_type": "api_key"},
    "github.com/aws/aws-sdk-go": {"api": "aws", "credential_type": "access_key"},
    "github.com/sashabaranov/go-openai": {"api": "openai", "credential_type": "api_key"},
    "go.mongodb.org/mongo-driver": {"api": "mongodb_cred", "credential_type": "connection_string"},
    "github.com/lib/pq": {"api": "postgresql", "credential_type": "connection_string"},
    "github.com/go-redis/redis": {"api": "redis", "credential_type": "connection_string"},
    "github.com/google/go-github": {"api": "github", "credential_type": "token"},
}


def analyze_dependencies(content: str, filename: str) -> List[Dict]:
    """Parse a dependency file and detect which APIs the project expects.

    Supports package.json, requirements.txt, pyproject.toml, and go.mod.

    Returns a list of dicts with package_name, expected_api, credential_type,
    and has_credential (always False here; checked at the route level).
    """
    basename = Path(filename).name.lower()
    detected: List[Dict] = []
    seen_apis: set = set()

    if basename == "package.json":
        detected = _parse_package_json(content, seen_apis)
    elif basename in ("requirements.txt",):
        detected = _parse_requirements_txt(content, seen_apis)
    elif basename == "pyproject.toml":
        detected = _parse_pyproject_toml(content, seen_apis)
    elif basename == "go.mod":
        detected = _parse_go_mod(content, seen_apis)
    else:
        logger.warning("Unsupported dependency file: %s", filename)

    logger.info(
        "Analyzed dependencies in %s: found %d known API package(s)",
        filename,
        len(detected),
    )
    return detected


def _parse_package_json(content: str, seen: set) -> List[Dict]:
    """Extract known packages from a package.json file."""
    results: List[Dict] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.error("Failed to parse package.json")
        return results

    all_deps: Dict[str, str] = {}
    all_deps.update(data.get("dependencies", {}))
    all_deps.update(data.get("devDependencies", {}))

    for pkg_name in all_deps:
        if pkg_name in PACKAGE_TO_API and pkg_name not in seen:
            info = PACKAGE_TO_API[pkg_name]
            seen.add(pkg_name)
            results.append({
                "package_name": pkg_name,
                "expected_api": info["api"],
                "credential_type": info["credential_type"],
                "has_credential": False,
            })
    return results


def _parse_requirements_txt(content: str, seen: set) -> List[Dict]:
    """Extract known packages from a requirements.txt file."""
    results: List[Dict] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Strip version specifiers and extras
        pkg_name = re.split(r"[><=!~;\[\]]", line)[0].strip()
        if pkg_name in PACKAGE_TO_API and pkg_name not in seen:
            info = PACKAGE_TO_API[pkg_name]
            seen.add(pkg_name)
            results.append({
                "package_name": pkg_name,
                "expected_api": info["api"],
                "credential_type": info["credential_type"],
                "has_credential": False,
            })
    return results


def _parse_pyproject_toml(content: str, seen: set) -> List[Dict]:
    """Best-effort extraction of dependencies from pyproject.toml via regex."""
    results: List[Dict] = []
    # Match items in dependencies list blocks
    dep_matches = re.findall(
        r"""["']([a-zA-Z0-9_\-]+)(?:[><=!~\[\];].*)?["']""", content
    )
    for pkg_name in dep_matches:
        if pkg_name in PACKAGE_TO_API and pkg_name not in seen:
            info = PACKAGE_TO_API[pkg_name]
            seen.add(pkg_name)
            results.append({
                "package_name": pkg_name,
                "expected_api": info["api"],
                "credential_type": info["credential_type"],
                "has_credential": False,
            })
    return results


def _parse_go_mod(content: str, seen: set) -> List[Dict]:
    """Extract known Go modules from go.mod."""
    results: List[Dict] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith("module"):
            continue
        # go.mod lines look like: github.com/foo/bar v1.2.3
        parts = line.split()
        if parts:
            module_path = parts[0]
            for pkg_prefix, info in PACKAGE_TO_API.items():
                if module_path.startswith(pkg_prefix) and pkg_prefix not in seen:
                    seen.add(pkg_prefix)
                    results.append({
                        "package_name": pkg_prefix,
                        "expected_api": info["api"],
                        "credential_type": info["credential_type"],
                        "has_credential": False,
                    })
    return results

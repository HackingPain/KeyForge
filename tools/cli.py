#!/usr/bin/env python3
"""KeyForge CLI - manage API keys and credentials from the command line."""

import argparse
import base64
import json
import os
import secrets
import sys
from pathlib import Path

import requests

# ── ANSI colour helpers ───────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
DIM = "\033[2m"

CONFIG_DIR = Path.home() / ".keyforge"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_API_URL = "http://localhost:8001"


# ── Config helpers ────────────────────────────────────────────────────────────

def _load_config() -> dict:
    """Load saved configuration from ~/.keyforge/config.json."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_config(config: dict) -> None:
    """Persist configuration to ~/.keyforge/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n")


def _get_token(args) -> str:
    """Return the auth token from CLI args or saved config."""
    config = _load_config()
    token = getattr(args, "token", None) or config.get("token")
    if not token:
        print(f"{RED}Error:{RESET} Not logged in. Run {BOLD}keyforge login{RESET} first.")
        sys.exit(1)
    return token


def _get_api_url(args) -> str:
    """Return the API URL from CLI args or saved config or default."""
    config = _load_config()
    return getattr(args, "api_url", None) or config.get("api_url") or DEFAULT_API_URL


def _headers(token: str) -> dict:
    """Return authorization headers."""
    return {"Authorization": f"Bearer {token}"}


def _handle_response(resp: requests.Response) -> dict | str:
    """Check response status and return parsed JSON or text."""
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        print(f"{RED}Error ({resp.status_code}):{RESET} {detail}")
        sys.exit(1)
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        return resp.json()
    return resp.text


# ── backend/.env management (used by `init`) ──────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ENV_PATH = REPO_ROOT / "backend" / ".env"
MANAGED_ENV_KEYS = ("MONGO_URL", "DB_NAME", "ENCRYPTION_KEY", "JWT_SECRET")


def _parse_env_file(env_path: Path) -> dict:
    """Parse a simple KEY=VALUE .env file. Quotes around values are stripped."""
    if not env_path.exists():
        return {}
    parsed = {}
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        parsed[key] = value
    return parsed


def _generate_fernet_key() -> str:
    """Return a 32-byte URL-safe base64 key suitable for cryptography.fernet.Fernet."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def _generate_jwt_secret() -> str:
    """Return a 64-byte URL-safe random secret for HS256 JWT signing."""
    return secrets.token_urlsafe(64)


def _write_env_file(env_path: Path, merged: dict) -> None:
    """Write *merged* back to *env_path* with managed keys first, then the rest."""
    lines = []
    for key in MANAGED_ENV_KEYS:
        if key in merged:
            lines.append(f'{key}="{merged[key]}"')
    for key in sorted(merged):
        if key in MANAGED_ENV_KEYS:
            continue
        lines.append(f'{key}="{merged[key]}"')
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_init(args):
    """Generate ENCRYPTION_KEY + JWT_SECRET and write backend/.env."""
    env_path = BACKEND_ENV_PATH
    existing = _parse_env_file(env_path)

    has_encryption_key = bool(existing.get("ENCRYPTION_KEY"))
    has_jwt_secret = bool(existing.get("JWT_SECRET"))

    if (has_encryption_key or has_jwt_secret) and not args.force:
        print(f"{RED}Refusing to overwrite existing keys in {env_path}.{RESET}")
        if has_encryption_key:
            print(f"  {DIM}ENCRYPTION_KEY is already set.{RESET}")
        if has_jwt_secret:
            print(f"  {DIM}JWT_SECRET is already set.{RESET}")
        print()
        print(f"To regenerate, re-run with {BOLD}--force{RESET}.")
        print(
            f"{YELLOW}WARNING:{RESET} regenerating ENCRYPTION_KEY makes every credential "
            f"already stored in KeyForge permanently unreadable. There is no recovery."
        )
        sys.exit(1)

    if args.force and (has_encryption_key or has_jwt_secret):
        banner = "=" * 64
        print(f"{RED}{BOLD}{banner}{RESET}")
        print(f"{RED}{BOLD}--force: replacing existing encryption keys.{RESET}")
        print(f"{RED}{BOLD}All credentials encrypted under the old ENCRYPTION_KEY{RESET}")
        print(f"{RED}{BOLD}will be permanently unreadable. There is no recovery.{RESET}")
        print(f"{RED}{BOLD}{banner}{RESET}")
        print()

    merged = dict(existing)
    merged.setdefault("MONGO_URL", "mongodb://localhost:27017")
    if merged.get("DB_NAME", "") in ("", "test_database"):
        merged["DB_NAME"] = "keyforge"
    merged["ENCRYPTION_KEY"] = _generate_fernet_key()
    merged["JWT_SECRET"] = _generate_jwt_secret()

    _write_env_file(env_path, merged)

    print(f"{GREEN}KeyForge initialised.{RESET}")
    print(f"  {BOLD}Wrote:{RESET}        {DIM}{env_path}{RESET}")
    print(f"  {BOLD}MONGO_URL:{RESET}    {merged['MONGO_URL']}")
    print(f"  {BOLD}DB_NAME:{RESET}      {merged['DB_NAME']}")
    print(f"  {BOLD}ENCRYPTION_KEY:{RESET} {DIM}<{len(merged['ENCRYPTION_KEY'])} chars, generated>{RESET}")
    print(f"  {BOLD}JWT_SECRET:{RESET}     {DIM}<{len(merged['JWT_SECRET'])} chars, generated>{RESET}")
    print()
    print(f"Next: {BOLD}docker compose up --build{RESET}")
    print(f"Then open {BLUE}http://localhost:3000{RESET} and register your first user.")


def cmd_login(args):
    """Authenticate and store the JWT token."""
    api_url = _get_api_url(args)
    print(f"{CYAN}Logging in to {api_url}...{RESET}")

    resp = requests.post(
        f"{api_url}/api/auth/login",
        data={"username": args.username, "password": args.password},
    )
    data = _handle_response(resp)

    token = data["access_token"]
    config = _load_config()
    config["token"] = token
    config["api_url"] = api_url
    config["username"] = args.username
    _save_config(config)

    print(f"{GREEN}Login successful!{RESET} Token saved to {DIM}{CONFIG_FILE}{RESET}")


def cmd_pull(args):
    """Pull credentials as a .env file."""
    api_url = _get_api_url(args)
    token = _get_token(args)
    env_file = args.env_file

    print(f"{CYAN}Pulling credentials from {api_url}...{RESET}")

    resp = requests.get(f"{api_url}/api/export/env", headers=_headers(token))
    content = _handle_response(resp)

    Path(env_file).write_text(content)
    print(f"{GREEN}Credentials written to {BOLD}{env_file}{RESET}")


def cmd_push(args):
    """Push credentials from a .env file."""
    api_url = _get_api_url(args)
    token = _get_token(args)
    env_file = args.env_file

    if not Path(env_file).exists():
        print(f"{RED}Error:{RESET} File not found: {env_file}")
        sys.exit(1)

    content = Path(env_file).read_text()
    print(f"{CYAN}Pushing credentials from {env_file} to {api_url}...{RESET}")

    resp = requests.post(
        f"{api_url}/api/import/env",
        headers={**_headers(token), "Content-Type": "text/plain"},
        data=content,
    )
    data = _handle_response(resp)

    imported = data.get("imported", [])
    skipped = data.get("skipped", [])
    print(f"{GREEN}Imported {len(imported)} credential(s){RESET}")
    for item in imported:
        print(f"  {BLUE}+{RESET} {item.get('env_key', '')} -> {item.get('api_name', '')}")
    if skipped:
        print(f"{YELLOW}Skipped {len(skipped)} entry(ies):{RESET}")
        for item in skipped:
            print(f"  {DIM}- {item.get('key', '')}: {item.get('reason', '')}{RESET}")


def cmd_list(args):
    """List all credentials."""
    api_url = _get_api_url(args)
    token = _get_token(args)

    print(f"{CYAN}Fetching credentials...{RESET}\n")

    skip = 0
    limit = 50
    all_creds = []

    while True:
        resp = requests.get(
            f"{api_url}/api/credentials",
            headers=_headers(token),
            params={"skip": skip, "limit": limit},
        )
        batch = _handle_response(resp)
        if not batch:
            break
        all_creds.extend(batch)
        if len(batch) < limit:
            break
        skip += limit

    if not all_creds:
        print(f"{YELLOW}No credentials found.{RESET}")
        return

    print(f"{BOLD}{'API Name':<20} {'Status':<12} {'Environment':<15} {'Preview':<16} {'ID'}{RESET}")
    print("-" * 85)
    for cred in all_creds:
        status = cred.get("status", "unknown")
        status_color = GREEN if status == "active" else (RED if status in ("expired", "invalid") else YELLOW)
        print(
            f"  {cred.get('api_name', ''):<18} "
            f"{status_color}{status:<12}{RESET} "
            f"{cred.get('environment', ''):<15} "
            f"{DIM}{cred.get('api_key_preview', ''):<16}{RESET} "
            f"{DIM}{cred.get('id', '')}{RESET}"
        )
    print(f"\n{DIM}Total: {len(all_creds)} credential(s){RESET}")


def cmd_test(args):
    """Test credentials."""
    api_url = _get_api_url(args)
    token = _get_token(args)

    # First, fetch all credentials
    resp = requests.get(
        f"{api_url}/api/credentials",
        headers=_headers(token),
        params={"skip": 0, "limit": 200},
    )
    credentials = _handle_response(resp)

    if args.api_name:
        credentials = [c for c in credentials if c.get("api_name") == args.api_name]

    if not credentials:
        print(f"{YELLOW}No credentials found to test.{RESET}")
        return

    print(f"{CYAN}Testing {len(credentials)} credential(s)...{RESET}\n")

    for cred in credentials:
        cred_id = cred.get("id", "")
        api_name = cred.get("api_name", "")
        print(f"  Testing {BOLD}{api_name}{RESET} ({DIM}{cred_id}{RESET})... ", end="", flush=True)

        resp = requests.post(
            f"{api_url}/api/credentials/{cred_id}/test",
            headers=_headers(token),
        )
        if resp.status_code >= 400:
            print(f"{RED}FAILED{RESET}")
            continue

        result = resp.json()
        test_result = result.get("test_result", {})
        status = test_result.get("status", "unknown")
        if status == "active":
            print(f"{GREEN}ACTIVE{RESET}")
        elif status in ("expired", "invalid"):
            print(f"{RED}{status.upper()}{RESET}")
        else:
            print(f"{YELLOW}{status.upper()}{RESET}")

    print()


def cmd_status(args):
    """Show account status."""
    api_url = _get_api_url(args)
    token = _get_token(args)

    print(f"{CYAN}Fetching account status...{RESET}\n")

    # Get user info
    resp = requests.get(f"{api_url}/api/auth/me", headers=_headers(token))
    user = _handle_response(resp)

    print(f"  {BOLD}User:{RESET}       {user.get('username', 'N/A')}")
    print(f"  {BOLD}User ID:{RESET}    {user.get('id', 'N/A')}")
    print(f"  {BOLD}Created:{RESET}    {user.get('created_at', 'N/A')}")

    # Get credential count
    resp = requests.get(
        f"{api_url}/api/credentials",
        headers=_headers(token),
        params={"skip": 0, "limit": 200},
    )
    credentials = _handle_response(resp)
    total = len(credentials)
    active = sum(1 for c in credentials if c.get("status") == "active")

    print(f"  {BOLD}Credentials:{RESET} {total} total, {GREEN}{active} active{RESET}")

    # Get API health
    resp = requests.get(f"{api_url}/api/health")
    health = _handle_response(resp)
    health_status = health.get("status", "unknown")
    health_color = GREEN if health_status == "healthy" else RED
    print(f"  {BOLD}API Status:{RESET}  {health_color}{health_status}{RESET}")

    config = _load_config()
    print(f"  {BOLD}API URL:{RESET}    {config.get('api_url', DEFAULT_API_URL)}")
    print(f"  {BOLD}Config:{RESET}     {DIM}{CONFIG_FILE}{RESET}")
    print()


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="keyforge",
        description="KeyForge CLI - manage API keys and credentials",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help=f"KeyForge API URL (default: {DEFAULT_API_URL})",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    init_parser = subparsers.add_parser(
        "init",
        help="Generate ENCRYPTION_KEY and JWT_SECRET, write backend/.env",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing keys (DESTRUCTIVE: makes existing credentials unreadable)",
    )

    # login
    login_parser = subparsers.add_parser("login", help="Login and store token")
    login_parser.add_argument("--username", required=True, help="Username")
    login_parser.add_argument("--password", required=True, help="Password")

    # pull
    pull_parser = subparsers.add_parser("pull", help="Pull credentials as .env file")
    pull_parser.add_argument("--env-file", default=".env", help="Output file (default: .env)")

    # push
    push_parser = subparsers.add_parser("push", help="Push credentials from .env")
    push_parser.add_argument("--env-file", required=True, help="Input .env file")

    # list
    subparsers.add_parser("list", help="List all credentials")

    # test
    test_parser = subparsers.add_parser("test", help="Test credentials")
    test_parser.add_argument("--api-name", default=None, help="Filter by API name")

    # status
    subparsers.add_parser("status", help="Show account status")

    return parser


def main():
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "init": cmd_init,
        "login": cmd_login,
        "pull": cmd_pull,
        "push": cmd_push,
        "list": cmd_list,
        "test": cmd_test,
        "status": cmd_status,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

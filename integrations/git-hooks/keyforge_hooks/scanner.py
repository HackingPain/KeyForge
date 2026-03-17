"""SecretScanner — detect hardcoded secrets in files and git staged content.

Reuses and extends the pattern catalogue from the KeyForge backend while
remaining fully self-contained (no backend imports required at runtime).
"""

from __future__ import annotations

import fnmatch
import math
import os
import re
import subprocess
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """A single secret-detection finding."""

    file: str
    line_number: int
    pattern_name: str
    matched_text: str          # masked version of the matched value
    severity: str              # "high", "medium", or "low"
    suggestion: str

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line_number": self.line_number,
            "pattern_name": self.pattern_name,
            "matched_text": self.matched_text,
            "severity": self.severity,
            "suggestion": self.suggestion,
        }


# ---------------------------------------------------------------------------
# Pattern definitions — mirrors / extends backend.scanners.SECRET_PATTERNS
# ---------------------------------------------------------------------------

# Each entry: (name, regex, severity, suggestion)
# Severity mapping: backend "critical" -> hook "high"
_API_KEY_PATTERNS: list[tuple[str, str, str, str]] = [
    # ── OpenAI ────────────────────────────────────────────────────────────
    ("OpenAI API Key", r"sk-[a-zA-Z0-9]{40,}", "high",
     "Replace hardcoded OpenAI key with env var OPENAI_API_KEY."),
    # ── AWS ───────────────────────────────────────────────────────────────
    ("AWS Access Key ID", r"AKIA[0-9A-Z]{16}", "high",
     "Replace hardcoded AWS access key with env var AWS_ACCESS_KEY_ID."),
    ("AWS Secret Access Key", r"""(?:aws_secret_access_key|AWS_SECRET_ACCESS_KEY)\s*[=:]\s*["']?([A-Za-z0-9/+=]{40})["']?""", "high",
     "Replace hardcoded AWS secret key with env var AWS_SECRET_ACCESS_KEY."),
    # ── GitHub ────────────────────────────────────────────────────────────
    ("GitHub Personal Access Token", r"ghp_[a-zA-Z0-9]{36}", "high",
     "Replace hardcoded GitHub PAT with env var GITHUB_TOKEN."),
    ("GitHub OAuth Token", r"gho_[a-zA-Z0-9]{36}", "high",
     "Replace hardcoded GitHub OAuth token with env var GITHUB_CLIENT_SECRET."),
    ("GitHub App Token", r"ghu_[a-zA-Z0-9]{36}", "high",
     "Replace hardcoded GitHub App token with env var GITHUB_APP_TOKEN."),
    ("GitHub App Installation Token", r"ghs_[a-zA-Z0-9]{36}", "high",
     "Replace hardcoded GitHub installation token with env var GITHUB_APP_TOKEN."),
    ("GitHub Fine-Grained PAT", r"github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}", "high",
     "Replace hardcoded GitHub fine-grained PAT with env var GITHUB_TOKEN."),
    # ── Stripe ────────────────────────────────────────────────────────────
    ("Stripe Test Key", r"sk_test_[a-zA-Z0-9]{20,}", "medium",
     "Replace hardcoded Stripe test key with env var STRIPE_SECRET_KEY."),
    ("Stripe Live Key", r"sk_live_[a-zA-Z0-9]{20,}", "high",
     "Replace hardcoded Stripe live key with env var STRIPE_SECRET_KEY."),
    ("Stripe Publishable Live Key", r"pk_live_[a-zA-Z0-9]{20,}", "medium",
     "Stripe publishable keys are less sensitive but should still use env vars."),
    ("Stripe Restricted Key", r"rk_live_[a-zA-Z0-9]{20,}", "high",
     "Replace hardcoded Stripe restricted key with env var STRIPE_RESTRICTED_KEY."),
    # ── Slack ─────────────────────────────────────────────────────────────
    ("Slack Token", r"xox[bpors]-[0-9a-zA-Z\-]{10,}", "high",
     "Replace hardcoded Slack token with env var SLACK_TOKEN."),
    ("Slack Webhook URL", r"https://hooks\.slack\.com/services/T[a-zA-Z0-9_]{8,}/B[a-zA-Z0-9_]{8,}/[a-zA-Z0-9_]{24,}", "medium",
     "Move Slack webhook URL to env var SLACK_WEBHOOK_URL."),
    # ── Google / GCP ──────────────────────────────────────────────────────
    ("Google API Key", r"AIza[0-9A-Za-z_\-]{35}", "high",
     "Replace hardcoded Google API key with env var GOOGLE_API_KEY."),
    ("Google OAuth Client Secret", r"""("client_secret"\s*:\s*"[a-zA-Z0-9_\-]{24,}")""", "high",
     "Do not embed Google OAuth client secrets in code."),
    # ── Azure ─────────────────────────────────────────────────────────────
    ("Azure Storage Account Key", r"DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[A-Za-z0-9+/=]{86,}", "high",
     "Replace hardcoded Azure storage key with env var AZURE_STORAGE_CONNECTION_STRING."),
    ("Azure AD Client Secret", r"""(?:client_secret|AZURE_CLIENT_SECRET)\s*[=:]\s*["']([a-zA-Z0-9~._\-]{34,})["']""", "high",
     "Replace hardcoded Azure client secret with env var AZURE_CLIENT_SECRET."),
    # ── SendGrid ──────────────────────────────────────────────────────────
    ("SendGrid API Key", r"SG\.[a-zA-Z0-9_\-]{22,}\.[a-zA-Z0-9_\-]{22,}", "high",
     "Replace hardcoded SendGrid key with env var SENDGRID_API_KEY."),
    # ── Twilio ────────────────────────────────────────────────────────────
    ("Twilio API Key", r"SK[0-9a-fA-F]{32}", "high",
     "Replace hardcoded Twilio key with env var TWILIO_API_KEY."),
    ("Twilio Account SID", r"AC[0-9a-fA-F]{32}", "medium",
     "Replace hardcoded Twilio Account SID with env var TWILIO_ACCOUNT_SID."),
    # ── Supabase ──────────────────────────────────────────────────────────
    ("Supabase Key (JWT)", r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[a-zA-Z0-9_\-]{50,}", "high",
     "Replace hardcoded Supabase key with env var SUPABASE_ANON_KEY."),
    # ── Mailgun ───────────────────────────────────────────────────────────
    ("Mailgun API Key", r"key-[0-9a-zA-Z]{32}", "high",
     "Replace hardcoded Mailgun key with env var MAILGUN_API_KEY."),
    # ── Heroku ────────────────────────────────────────────────────────────
    ("Heroku API Key", r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "low",
     "If this UUID is a Heroku API key, move it to env var HEROKU_API_KEY."),
    # ── Datadog ───────────────────────────────────────────────────────────
    ("Datadog API Key", r"""(?:DD_API_KEY|datadog_api_key)\s*[=:]\s*["']?([a-f0-9]{32})["']?""", "high",
     "Replace hardcoded Datadog API key with env var DD_API_KEY."),
    # ── NPM ───────────────────────────────────────────────────────────────
    ("NPM Access Token", r"npm_[a-zA-Z0-9]{36}", "high",
     "Replace hardcoded npm token with env var NPM_TOKEN."),
    # ── PyPI ──────────────────────────────────────────────────────────────
    ("PyPI API Token", r"pypi-[a-zA-Z0-9_\-]{50,}", "high",
     "Replace hardcoded PyPI token with env var PYPI_TOKEN."),
    # ── Discord ───────────────────────────────────────────────────────────
    ("Discord Bot Token", r"[MN][a-zA-Z0-9]{23,}\.[a-zA-Z0-9_\-]{6}\.[a-zA-Z0-9_\-]{27,}", "high",
     "Replace hardcoded Discord token with env var DISCORD_BOT_TOKEN."),
    # ── Telegram ──────────────────────────────────────────────────────────
    ("Telegram Bot Token", r"[0-9]{8,10}:[a-zA-Z0-9_\-]{35}", "high",
     "Replace hardcoded Telegram token with env var TELEGRAM_BOT_TOKEN."),
]

# ── Generic / structural patterns ────────────────────────────────────────────

_GENERIC_PATTERNS: list[tuple[str, str, str, str]] = [
    # Private keys (PEM)
    ("RSA Private Key", r"-----BEGIN RSA PRIVATE KEY-----", "high",
     "Never embed private keys in source. Use a secrets manager or env var."),
    ("EC Private Key", r"-----BEGIN EC PRIVATE KEY-----", "high",
     "Never embed private keys in source. Use a secrets manager or env var."),
    ("DSA Private Key", r"-----BEGIN DSA PRIVATE KEY-----", "high",
     "Never embed private keys in source. Use a secrets manager or env var."),
    ("OpenSSH Private Key", r"-----BEGIN OPENSSH PRIVATE KEY-----", "high",
     "Never embed private keys in source. Use a secrets manager or env var."),
    ("Generic Private Key", r"-----BEGIN PRIVATE KEY-----", "high",
     "Never embed private keys in source. Use a secrets manager or env var."),

    # Connection strings with embedded passwords
    ("Database Connection String", r"(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:\s]+:([^@\s]{3,})@[^\s]+", "high",
     "Move connection string to env var DATABASE_URL so passwords stay out of code."),

    # Hardcoded assignment patterns
    ("Hardcoded API Key Assignment",
     r"""(?:api_key|apikey|api_secret|apisecret)\s*=\s*["']([^"']{8,})["']""", "high",
     "Move this API key to an environment variable and load at runtime."),
    ("Hardcoded Password Assignment",
     r"""(?:password|passwd|pwd)\s*=\s*["']([^"']{4,})["']""", "high",
     "Move this password to an environment variable."),
    ("Hardcoded Secret Assignment",
     r"""(?:secret|secret_key|secretkey)\s*=\s*["']([^"']{8,})["']""", "high",
     "Move this secret to an environment variable."),
    ("Hardcoded Token Assignment",
     r"""(?:token|access_token|auth_token)\s*=\s*["']([^"']{8,})["']""", "medium",
     "Move this token to an environment variable."),
    ("Hardcoded Database URL Assignment",
     r"""(?:database_url|db_url|mongo_url|mongo_uri)\s*=\s*["']([^"']{10,})["']""", "high",
     "Move this database URL to env var DATABASE_URL."),

    # Env-file style assignments with real values
    ("Env File Secret",
     r"""^(?:export\s+)?([A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL)[A-Z0-9_]*)=(?!.*(?:\$\{|\$[A-Z]|os\.environ|process\.env))["']?([^\s"']{8,})["']?\s*$""",
     "medium",
     "Do not commit .env files with real values. Add to .gitignore and use a secrets manager."),

    # Password in config / YAML / JSON
    ("Password in Config",
     r"""["']?(?:password|passwd|pwd)["']?\s*[:=]\s*["']([^"'\s]{4,})["']""", "medium",
     "Replace inline password with an env var or secrets reference."),
]

# Placeholder values that should not be flagged
_PLACEHOLDER_VALUES = frozenset({
    "your_api_key_here", "changeme", "xxx", "todo",
    "replace_me", "placeholder", "your-api-key",
    "insert-key-here", "xxxxxxxx", "test",
    "example", "dummy", "none", "null",
})

# Binary file extensions to skip
_BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".pyc", ".pyo", ".class", ".o", ".obj",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".sqlite", ".db", ".lock",
})


# ---------------------------------------------------------------------------
# Entropy helpers
# ---------------------------------------------------------------------------

def _shannon_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string."""
    if not s:
        return 0.0
    length = len(s)
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    return -sum(
        (count / length) * math.log2(count / length)
        for count in freq.values()
    )


def _has_high_entropy(token: str, threshold: float = 4.5) -> bool:
    """Return True if *token* has high Shannon entropy (likely a secret)."""
    if len(token) < 16:
        return False
    charset = set(token)
    # Must use a mix of character classes
    classes = sum([
        bool(charset & set(string.ascii_lowercase)),
        bool(charset & set(string.ascii_uppercase)),
        bool(charset & set(string.digits)),
        bool(charset & set(string.punctuation)),
    ])
    if classes < 2:
        return False
    return _shannon_entropy(token) >= threshold


# ---------------------------------------------------------------------------
# Masking helper
# ---------------------------------------------------------------------------

def _mask(value: str, visible: int = 4) -> str:
    """Mask a secret value, keeping only the first *visible* characters."""
    if len(value) <= visible:
        return "*" * len(value)
    return value[:visible] + "*" * (len(value) - visible)


# ---------------------------------------------------------------------------
# SecretScanner
# ---------------------------------------------------------------------------

class SecretScanner:
    """Scan files and content for hardcoded secrets.

    Parameters
    ----------
    allowlist_path : str | None
        Path to a ``.keyforge-allowlist`` file with glob patterns for files
        to skip (one per line, ``#`` comments allowed).
    """

    def __init__(self, allowlist_path: Optional[str] = None) -> None:
        self._patterns = _API_KEY_PATTERNS + _GENERIC_PATTERNS
        self._compiled = [
            (name, re.compile(regex), sev, sug)
            for name, regex, sev, sug in self._patterns
        ]
        self._allowlist_globs: list[str] = []
        if allowlist_path:
            self._load_allowlist(allowlist_path)
        else:
            # Try default location
            default = os.path.join(self._git_root() or ".", ".keyforge-allowlist")
            if os.path.isfile(default):
                self._load_allowlist(default)

    # -- allowlist ----------------------------------------------------------

    def _load_allowlist(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for raw in fh:
                    line = raw.strip()
                    if line and not line.startswith("#"):
                        self._allowlist_globs.append(line)
        except OSError:
            pass

    def _is_allowlisted(self, filepath: str) -> bool:
        for pattern in self._allowlist_globs:
            if fnmatch.fnmatch(filepath, pattern):
                return True
        return False

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _git_root() -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    @staticmethod
    def _is_binary(filepath: str) -> bool:
        ext = Path(filepath).suffix.lower()
        return ext in _BINARY_EXTENSIONS

    def _line_is_allowed(self, line: str) -> bool:
        """Check for inline allowlist comment ``# keyforge:allow``."""
        return "keyforge:allow" in line

    def _is_placeholder(self, value: str) -> bool:
        return value.lower().strip("\"'") in _PLACEHOLDER_VALUES

    # -- scanning -----------------------------------------------------------

    def scan_content(self, content: str, filename: str) -> list[Finding]:
        """Scan string *content* for secrets, returning a list of Findings."""
        if self._is_allowlisted(filename):
            return []

        findings: list[Finding] = []
        lines = content.splitlines()

        for line_no, line in enumerate(lines, start=1):
            if self._line_is_allowed(line):
                continue

            for name, compiled, severity, suggestion in self._compiled:
                match = compiled.search(line)
                if match:
                    # Grab the most specific group or the whole match
                    matched_value = (
                        match.group(1)
                        if match.lastindex and match.lastindex >= 1
                        else match.group(0)
                    )
                    if self._is_placeholder(matched_value):
                        continue
                    findings.append(Finding(
                        file=filename,
                        line_number=line_no,
                        pattern_name=name,
                        matched_text=_mask(matched_value),
                        severity=severity,
                        suggestion=suggestion,
                    ))

            # High-entropy string detection
            # Look for quoted strings that look like secrets
            for qs_match in re.finditer(r"""["']([A-Za-z0-9+/=_\-]{20,})["']""", line):
                token = qs_match.group(1)
                if self._is_placeholder(token):
                    continue
                if _has_high_entropy(token):
                    # Avoid duplicate if already caught by a named pattern
                    already = any(
                        f.line_number == line_no and f.file == filename
                        for f in findings
                    )
                    if not already:
                        findings.append(Finding(
                            file=filename,
                            line_number=line_no,
                            pattern_name="High Entropy String",
                            matched_text=_mask(token),
                            severity="medium",
                            suggestion="This string has high entropy and may be a secret. Use an env var instead.",
                        ))

        return findings

    def scan_file(self, filepath: str) -> list[Finding]:
        """Scan a single file on disk for secrets."""
        if self._is_binary(filepath):
            return []
        if self._is_allowlisted(filepath):
            return []
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            return []
        return self.scan_content(content, filepath)

    def scan_staged_files(self) -> list[Finding]:
        """Scan all git-staged files for secrets.

        Uses ``git diff --cached --name-only`` to discover staged files,
        then reads and scans each one.
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return []
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        root = self._git_root() or "."
        findings: list[Finding] = []

        for raw_path in result.stdout.strip().splitlines():
            raw_path = raw_path.strip()
            if not raw_path:
                continue
            full_path = os.path.join(root, raw_path)
            findings.extend(self.scan_file(full_path))

        return findings

    def scan_directory(self, directory: str) -> list[Finding]:
        """Recursively scan all files in *directory* for secrets."""
        findings: list[Finding] = []
        for root, dirs, files in os.walk(directory):
            # Skip hidden and common non-source dirs
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".") and d not in (
                    "node_modules", "__pycache__", "venv", ".venv",
                    "dist", "build", ".git",
                )
            ]
            for fname in files:
                fpath = os.path.join(root, fname)
                findings.extend(self.scan_file(fpath))
        return findings

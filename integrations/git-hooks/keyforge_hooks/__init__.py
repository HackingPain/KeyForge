"""KeyForge Git Hooks — pre-commit secret scanner.

Scans staged files for hardcoded secrets, API keys, private keys, and other
sensitive material before they reach your repository history.
"""

__version__ = "0.1.0"
__author__ = "KeyForge Team"

from keyforge_hooks.scanner import SecretScanner, Finding  # noqa: F401

__all__ = ["SecretScanner", "Finding", "__version__"]

"""CLI entry point for keyforge-scan — the KeyForge pre-commit secret scanner."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional

from keyforge_hooks import __version__
from keyforge_hooks.scanner import SecretScanner, Finding


# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}


def _meets_threshold(finding_severity: str, min_severity: str) -> bool:
    return _SEVERITY_RANK.get(finding_severity, 0) >= _SEVERITY_RANK.get(min_severity, 0)


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _format_text(findings: list[Finding]) -> str:
    if not findings:
        return "No secrets detected."
    lines: list[str] = []
    lines.append(f"Found {len(findings)} potential secret(s):\n")
    for f in findings:
        sev_label = f.severity.upper()
        lines.append(f"  [{sev_label}] {f.file}:{f.line_number}")
        lines.append(f"         Pattern : {f.pattern_name}")
        lines.append(f"         Match   : {f.matched_text}")
        lines.append(f"         Hint    : {f.suggestion}")
        lines.append("")
    return "\n".join(lines)


def _format_json(findings: list[Finding]) -> str:
    return json.dumps(
        {"findings": [f.to_dict() for f in findings], "count": len(findings)},
        indent=2,
    )


def _format_sarif(findings: list[Finding]) -> str:
    """Produce a minimal SARIF v2.1.0 log."""
    rules: list[dict] = []
    results: list[dict] = []
    rule_index: dict[str, int] = {}

    for f in findings:
        if f.pattern_name not in rule_index:
            idx = len(rules)
            rule_index[f.pattern_name] = idx
            rules.append({
                "id": f.pattern_name.lower().replace(" ", "-"),
                "name": f.pattern_name,
                "shortDescription": {"text": f.pattern_name},
                "defaultConfiguration": {
                    "level": "error" if f.severity == "high" else "warning",
                },
                "helpUri": "https://keyforge.dev/docs/secret-scanning",
            })

        results.append({
            "ruleId": rules[rule_index[f.pattern_name]]["id"],
            "ruleIndex": rule_index[f.pattern_name],
            "level": "error" if f.severity == "high" else "warning",
            "message": {"text": f.suggestion},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": f.file},
                    "region": {"startLine": f.line_number},
                },
            }],
        })

    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "keyforge-scan",
                    "version": __version__,
                    "informationUri": "https://keyforge.dev",
                    "rules": rules,
                },
            },
            "results": results,
            "invocations": [{
                "executionSuccessful": True,
                "endTimeUtc": datetime.now(timezone.utc).isoformat(),
            }],
        }],
    }
    return json.dumps(sarif, indent=2)


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="keyforge-scan",
        description="KeyForge Secret Scanner — detect hardcoded secrets before they reach your repo.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--format", choices=["text", "json", "sarif"], default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--severity", choices=["low", "medium", "high"], default="low",
        help="Minimum severity to report (default: low).",
    )
    parser.add_argument(
        "--allowlist", default=None, metavar="FILE",
        help="Path to allowlist file (default: .keyforge-allowlist in repo root).",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # scan (staged files — default for pre-commit)
    subparsers.add_parser("scan", help="Scan git-staged files for secrets.")

    # scan-all (entire repo)
    subparsers.add_parser("scan-all", help="Scan the entire repository for secrets.")

    # scan-file <path>
    sf = subparsers.add_parser("scan-file", help="Scan a specific file for secrets.")
    sf.add_argument("path", help="Path to the file to scan.")

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        # Default to scanning staged files (natural pre-commit behaviour)
        args.command = "scan"

    scanner = SecretScanner(allowlist_path=args.allowlist)

    # Run the requested scan
    if args.command == "scan":
        findings = scanner.scan_staged_files()
    elif args.command == "scan-all":
        root = scanner._git_root() or "."
        findings = scanner.scan_directory(root)
    elif args.command == "scan-file":
        findings = scanner.scan_file(args.path)
    else:
        parser.print_help()
        return 0

    # Filter by severity threshold
    findings = [f for f in findings if _meets_threshold(f.severity, args.severity)]

    # Format output
    if args.format == "json":
        output = _format_json(findings)
    elif args.format == "sarif":
        output = _format_sarif(findings)
    else:
        output = _format_text(findings)

    print(output)

    # Exit code: 1 if any high-severity findings, 0 otherwise
    has_high = any(f.severity == "high" for f in findings)
    return 1 if has_high else 0


def cli_entry() -> None:
    """Setuptools console_scripts entry point."""
    sys.exit(main())


if __name__ == "__main__":
    cli_entry()

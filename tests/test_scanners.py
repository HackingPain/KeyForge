"""Comprehensive tests for backend.scanners — secret detection, masking, dependencies."""

import json
import pytest

from backend.scanners import (
    scan_content_for_secrets,
    suggest_key_masking,
    analyze_dependencies,
    SECRET_PATTERNS,
    ASSIGNMENT_PATTERNS,
)


# ── scan_content_for_secrets ────────────────────────────────────────────────


class TestScanContentForSecrets:
    def test_detects_openai_key(self):
        content = 'api_key = "sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABCD"'
        findings = scan_content_for_secrets(content, "app.py")
        types = [f["type"] for f in findings]
        assert "openai_api_key" in types

    def test_detects_aws_access_key(self):
        content = "AWS_KEY = AKIAIOSFODNN7EXAMPLE"
        findings = scan_content_for_secrets(content, "config.py")
        types = [f["type"] for f in findings]
        assert "aws_access_key" in types

    def test_detects_github_token(self):
        content = "token = ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        findings = scan_content_for_secrets(content, "deploy.sh")
        types = [f["type"] for f in findings]
        assert "github_pat" in types

    def test_detects_generic_password_assignment(self):
        content = 'password = "supersecretpassword123"'
        findings = scan_content_for_secrets(content, "config.py")
        types = [f["type"] for f in findings]
        assert "hardcoded_password" in types

    def test_detects_api_key_assignment(self):
        content = 'api_key = "my-very-secret-api-key-value"'
        findings = scan_content_for_secrets(content, "app.py")
        types = [f["type"] for f in findings]
        assert "hardcoded_api_key" in types

    def test_detects_stripe_test_key(self):
        content = 'STRIPE_KEY = "sk_test_aBcDeFgHiJkLmNoPqRsTuV"'
        findings = scan_content_for_secrets(content, "billing.py")
        types = [f["type"] for f in findings]
        assert "stripe_test_key" in types

    def test_detects_stripe_live_key(self):
        content = 'key = "sk_live_aBcDeFgHiJkLmNoPqRsTuV"'
        findings = scan_content_for_secrets(content, "billing.py")
        types = [f["type"] for f in findings]
        assert "stripe_live_key" in types

    def test_detects_pem_private_key(self):
        content = "-----BEGIN RSA PRIVATE KEY-----\nMIIBogIBAAJ...\n-----END RSA PRIVATE KEY-----"
        findings = scan_content_for_secrets(content, "keys.py")
        types = [f["type"] for f in findings]
        assert "private_key" in types

    def test_detects_connection_string_password(self):
        content = 'db_url = "postgresql://admin:s3cretP@ss@db.example.com:5432/mydb"'
        findings = scan_content_for_secrets(content, "config.py")
        types = [f["type"] for f in findings]
        assert "connection_string_password" in types

    def test_returns_empty_for_clean_code(self):
        content = """
def add(a, b):
    return a + b

class Calculator:
    def multiply(self, x, y):
        return x * y

# This is clean code with no secrets
result = add(1, 2)
"""
        findings = scan_content_for_secrets(content, "math.py")
        assert len(findings) == 0

    def test_skips_placeholder_values(self):
        content = 'api_key = "your_api_key_here"'
        findings = scan_content_for_secrets(content, "app.py")
        # Should not flag placeholder values
        api_key_findings = [f for f in findings if f["type"] == "hardcoded_api_key"]
        assert len(api_key_findings) == 0

    def test_finding_structure(self):
        content = 'password = "mysecretpass123"'
        findings = scan_content_for_secrets(content, "test.py")
        assert len(findings) > 0
        finding = findings[0]
        assert "line" in finding
        assert "type" in finding
        assert "matched_value" in finding
        assert "severity" in finding
        assert "suggestion" in finding

    def test_line_number_is_correct(self):
        content = "line1\nline2\npassword = \"secret1234\"\nline4"
        findings = scan_content_for_secrets(content, "test.py")
        pwd_findings = [f for f in findings if f["type"] == "hardcoded_password"]
        assert len(pwd_findings) > 0
        assert pwd_findings[0]["line"] == 3

    def test_matched_value_is_truncated(self):
        content = 'password = "averyverylongpasswordthatshouldbetruncat"'
        findings = scan_content_for_secrets(content, "test.py")
        pwd_findings = [f for f in findings if f["type"] == "hardcoded_password"]
        assert len(pwd_findings) > 0
        matched = pwd_findings[0]["matched_value"]
        # Should be truncated (max 8 chars + "...")
        assert len(matched) <= 11

    def test_multiple_secrets_on_different_lines(self):
        content = (
            'api_key = "mysuperlongsecretapikey1"\n'
            'password = "anothersecretpassword"\n'
        )
        findings = scan_content_for_secrets(content, "test.py")
        types = [f["type"] for f in findings]
        assert "hardcoded_api_key" in types
        assert "hardcoded_password" in types


# ── suggest_key_masking ─────────────────────────────────────────────────────


class TestSuggestKeyMasking:
    def test_returns_suggestions_with_env_var(self):
        content = 'api_key = "my-long-secret-api-key-value"'
        suggestions = suggest_key_masking(content, "app.py")
        assert len(suggestions) > 0
        s = suggestions[0]
        assert "env_var_name" in s
        assert "suggested_replacement" in s
        assert "original_snippet" in s
        assert "line" in s

    def test_python_file_gets_os_environ(self):
        content = 'api_key = "my-long-secret-api-key-value"'
        suggestions = suggest_key_masking(content, "app.py")
        assert len(suggestions) > 0
        assert "os.environ" in suggestions[0]["suggested_replacement"]

    def test_js_file_gets_process_env(self):
        content = 'const api_key = "my-long-secret-api-key-value"'
        suggestions = suggest_key_masking(content, "app.js")
        assert len(suggestions) > 0
        assert "process.env" in suggestions[0]["suggested_replacement"]

    def test_ts_file_gets_process_env(self):
        content = 'const api_key = "my-long-secret-api-key-value"'
        suggestions = suggest_key_masking(content, "app.ts")
        assert len(suggestions) > 0
        assert "process.env" in suggestions[0]["suggested_replacement"]

    def test_env_var_name_for_openai(self):
        content = 'key = "sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABCDEFGHIJ"'
        suggestions = suggest_key_masking(content, "app.py")
        env_vars = [s["env_var_name"] for s in suggestions]
        assert "OPENAI_API_KEY" in env_vars

    def test_no_suggestions_for_clean_code(self):
        content = """
def clean_function():
    return 42
"""
        suggestions = suggest_key_masking(content, "app.py")
        assert len(suggestions) == 0

    def test_original_snippet_truncated(self):
        long_line = 'api_key = "' + "x" * 100 + '"'
        suggestions = suggest_key_masking(long_line, "app.py")
        if suggestions:
            assert len(suggestions[0]["original_snippet"]) <= 80


# ── analyze_dependencies ────────────────────────────────────────────────────


class TestAnalyzeDependencies:
    def test_parses_package_json(self):
        content = json.dumps({
            "dependencies": {
                "openai": "^4.0.0",
                "stripe": "^12.0.0",
                "express": "^4.18.0",
            },
            "devDependencies": {
                "@octokit/rest": "^20.0.0",
            },
        })
        results = analyze_dependencies(content, "package.json")
        apis = [r["expected_api"] for r in results]
        assert "openai" in apis
        assert "stripe" in apis
        assert "github" in apis

    def test_parses_package_json_structure(self):
        content = json.dumps({
            "dependencies": {"openai": "^4.0.0"},
        })
        results = analyze_dependencies(content, "package.json")
        assert len(results) > 0
        r = results[0]
        assert "package_name" in r
        assert "expected_api" in r
        assert "credential_type" in r
        assert "has_credential" in r
        assert r["has_credential"] is False

    def test_parses_requirements_txt(self):
        content = """
openai>=1.0.0
stripe==5.0.0
boto3
flask
psycopg2-binary>=3.0
# A comment
"""
        results = analyze_dependencies(content, "requirements.txt")
        apis = [r["expected_api"] for r in results]
        assert "openai" in apis
        assert "stripe" in apis
        assert "aws" in apis
        assert "postgresql" in apis

    def test_requirements_txt_skips_comments(self):
        content = "# openai\nstripe==5.0.0\n"
        results = analyze_dependencies(content, "requirements.txt")
        apis = [r["expected_api"] for r in results]
        assert "stripe" in apis

    def test_returns_empty_for_unknown_file(self):
        results = analyze_dependencies("some content", "Makefile")
        assert len(results) == 0

    def test_returns_empty_for_unrecognized_packages(self):
        content = json.dumps({
            "dependencies": {
                "express": "^4.18.0",
                "lodash": "^4.17.0",
            },
        })
        results = analyze_dependencies(content, "package.json")
        assert len(results) == 0

    def test_package_json_invalid_json(self):
        results = analyze_dependencies("not valid json {{{", "package.json")
        assert len(results) == 0

    def test_package_json_with_dev_dependencies(self):
        content = json.dumps({
            "devDependencies": {
                "pg": "^8.0.0",
                "mongoose": "^7.0.0",
            },
        })
        results = analyze_dependencies(content, "package.json")
        apis = [r["expected_api"] for r in results]
        assert "postgresql" in apis
        assert "mongodb_cred" in apis

    def test_requirements_txt_strips_version_specifiers(self):
        content = "redis>=4.0.0,<5.0\n"
        results = analyze_dependencies(content, "requirements.txt")
        apis = [r["expected_api"] for r in results]
        assert "redis" in apis

    def test_no_duplicate_apis(self):
        content = json.dumps({
            "dependencies": {
                "openai": "^4.0.0",
            },
            "devDependencies": {
                "openai": "^4.0.0",
            },
        })
        results = analyze_dependencies(content, "package.json")
        openai_results = [r for r in results if r["expected_api"] == "openai"]
        assert len(openai_results) == 1

    def test_parses_go_mod(self):
        content = """
module myproject

go 1.21

require (
    github.com/stripe/stripe-go/v76 v76.0.0
    github.com/aws/aws-sdk-go v1.50.0
    github.com/lib/pq v1.10.0
)
"""
        results = analyze_dependencies(content, "go.mod")
        apis = [r["expected_api"] for r in results]
        assert "stripe" in apis
        assert "aws" in apis
        assert "postgresql" in apis

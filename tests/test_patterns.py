"""Comprehensive tests for backend.patterns — API detection and code analysis."""

import pytest

from backend.patterns import API_PATTERNS, analyze_code_content


# ── API_PATTERNS registry ───────────────────────────────────────────────────


class TestAPIPatterns:
    def test_contains_at_least_15_providers(self):
        assert len(API_PATTERNS) >= 15, (
            f"Expected at least 15 providers, found {len(API_PATTERNS)}"
        )

    @pytest.mark.parametrize(
        "provider",
        [
            "openai", "stripe", "github", "supabase", "firebase", "vercel",
            "ssh", "gpg", "jwt_signing",
            "postgresql", "mysql", "redis", "mongodb_cred",
            "aws", "gcp", "azure",
        ],
    )
    def test_expected_providers_present(self, provider):
        assert provider in API_PATTERNS, f"Provider '{provider}' missing from API_PATTERNS"

    def test_each_provider_has_required_keys(self):
        required_keys = {"name", "category", "patterns", "files", "auth_type", "scopes"}
        for provider, config in API_PATTERNS.items():
            missing = required_keys - set(config.keys())
            assert not missing, (
                f"Provider '{provider}' missing keys: {missing}"
            )

    def test_patterns_are_nonempty_lists(self):
        for provider, config in API_PATTERNS.items():
            assert isinstance(config["patterns"], list), (
                f"Provider '{provider}' patterns should be a list"
            )
            assert len(config["patterns"]) > 0, (
                f"Provider '{provider}' should have at least one pattern"
            )

    def test_files_are_nonempty_lists(self):
        for provider, config in API_PATTERNS.items():
            assert isinstance(config["files"], list)
            assert len(config["files"]) > 0

    def test_scopes_are_lists(self):
        for provider, config in API_PATTERNS.items():
            assert isinstance(config["scopes"], list)


# ── analyze_code_content ────────────────────────────────────────────────────


class TestAnalyzeCodeContent:
    def test_detects_openai_in_python(self):
        content = """
import openai
client = openai.OpenAI()
response = client.chat.completions.create(model="gpt-4")
"""
        results = analyze_code_content(content, "app.py")
        api_ids = [r["api_id"] for r in results]
        assert "openai" in api_ids

    def test_detects_stripe_in_javascript(self):
        content = """
const stripe = require('stripe');
const paymentIntent = stripe.PaymentIntent.create({amount: 1000});
const key = 'sk_test_1234567890';
"""
        results = analyze_code_content(content, "payment.js")
        api_ids = [r["api_id"] for r in results]
        assert "stripe" in api_ids

    def test_detects_github_in_yml(self):
        content = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy
        env:
          GITHUB_CLIENT_ID: ${{ secrets.GITHUB_CLIENT_ID }}
"""
        results = analyze_code_content(content, ".github/workflows/ci.yml")
        api_ids = [r["api_id"] for r in results]
        assert "github" in api_ids

    def test_returns_empty_for_nonmatching_extension(self):
        content = "import openai\nopenai.api_key = 'test'"
        results = analyze_code_content(content, "README.md")
        # .md is not in openai's file list
        # Filter to check openai specifically is not detected
        openai_results = [r for r in results if r["api_id"] == "openai"]
        assert len(openai_results) == 0

    def test_returns_empty_for_nonmatching_content(self):
        content = """
def hello():
    print("Hello, World!")
"""
        results = analyze_code_content(content, "app.py")
        assert len(results) == 0

    def test_confidence_caps_at_1(self):
        """Even with many matches, confidence should not exceed 1.0."""
        content = """
import openai
from openai import OpenAI
openai.api_key = "test"
OPENAI_API_KEY = "test"
model = "gpt-4"
model2 = "gpt-3.5"
text = "text-davinci"
"""
        results = analyze_code_content(content, "app.py")
        openai_results = [r for r in results if r["api_id"] == "openai"]
        assert len(openai_results) > 0
        assert openai_results[0]["confidence"] <= 1.0

    def test_result_structure(self):
        content = "import openai\n"
        results = analyze_code_content(content, "test.py")
        assert len(results) > 0
        result = results[0]
        assert "api_id" in result
        assert "name" in result
        assert "category" in result
        assert "auth_type" in result
        assert "scopes" in result
        assert "confidence" in result
        assert "matched_patterns" in result
        assert "file" in result

    def test_matched_patterns_max_3(self):
        """matched_patterns should show at most 3 entries."""
        content = """
import openai
from openai import OpenAI
openai.api_key = "test"
OPENAI_API_KEY = "test"
model = "gpt-4"
model2 = "gpt-3.5"
text = "text-davinci"
"""
        results = analyze_code_content(content, "app.py")
        openai_results = [r for r in results if r["api_id"] == "openai"]
        assert len(openai_results) > 0
        assert len(openai_results[0]["matched_patterns"]) <= 3

    def test_file_field_matches_input(self):
        content = "import openai\n"
        results = analyze_code_content(content, "myfile.py")
        for r in results:
            assert r["file"] == "myfile.py"

    def test_detects_supabase_in_tsx(self):
        content = """
import { createClient } from '@supabase/supabase-js';
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
"""
        results = analyze_code_content(content, "client.tsx")
        api_ids = [r["api_id"] for r in results]
        assert "supabase" in api_ids

    def test_detects_aws_in_env(self):
        content = """
AWS_ACCESS_KEY_ID=AKIA1234567890123456
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
"""
        results = analyze_code_content(content, "config.env")
        api_ids = [r["api_id"] for r in results]
        assert "aws" in api_ids

    def test_detects_multiple_apis_in_single_file(self):
        content = """
import openai
import stripe
OPENAI_API_KEY = "test"
stripe.api_key = "sk_test_123"
"""
        results = analyze_code_content(content, "app.py")
        api_ids = [r["api_id"] for r in results]
        assert "openai" in api_ids
        assert "stripe" in api_ids

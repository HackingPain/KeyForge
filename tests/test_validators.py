"""Comprehensive tests for backend.validators — format validation for all providers."""

import json
import pytest
from unittest.mock import patch

from backend.validators import (
    validate_credential,
    _validate_format_openai,
    _validate_format_stripe,
    _validate_format_github,
    _validate_format_supabase,
    _validate_format_firebase,
    _validate_format_vercel,
    FORMAT_VALIDATORS,
    _DIRECT_VALIDATORS,
)


# ── OpenAI ───────────────────────────────────────────────────────────────────


class TestOpenAIValidator:
    def test_valid_openai_key(self):
        key = "sk-" + "a" * 45
        assert _validate_format_openai(key) is None

    def test_valid_openai_key_exact_40(self):
        key = "sk-" + "x" * 37  # total 40
        assert _validate_format_openai(key) is None

    def test_invalid_openai_wrong_prefix(self):
        key = "pk-" + "a" * 45
        err = _validate_format_openai(key)
        assert err is not None
        assert "sk-" in err

    def test_invalid_openai_too_short(self):
        key = "sk-abc"
        err = _validate_format_openai(key)
        assert err is not None
        assert "40" in err

    def test_invalid_openai_empty(self):
        err = _validate_format_openai("")
        assert err is not None


# ── Stripe ───────────────────────────────────────────────────────────────────


class TestStripeValidator:
    @pytest.mark.parametrize("prefix", ["sk_test_", "sk_live_", "pk_test_", "pk_live_"])
    def test_valid_stripe_key(self, prefix):
        key = prefix + "a" * 20
        assert _validate_format_stripe(key) is None

    def test_invalid_stripe_wrong_prefix(self):
        key = "invalid_prefix_" + "a" * 20
        err = _validate_format_stripe(key)
        assert err is not None
        assert "sk_test_" in err

    def test_invalid_stripe_too_short(self):
        key = "sk_test_abc"
        err = _validate_format_stripe(key)
        assert err is not None
        assert "20" in err

    def test_invalid_stripe_empty(self):
        err = _validate_format_stripe("")
        assert err is not None


# ── GitHub ───────────────────────────────────────────────────────────────────


class TestGitHubValidator:
    @pytest.mark.parametrize("prefix", ["ghp_", "gho_", "ghs_", "github_pat_"])
    def test_valid_github_key(self, prefix):
        key = prefix + "a" * 30
        assert _validate_format_github(key) is None

    def test_invalid_github_wrong_prefix(self):
        key = "invalid_" + "a" * 30
        err = _validate_format_github(key)
        assert err is not None
        assert "ghp_" in err

    def test_invalid_github_too_short(self):
        key = "ghp_abc"
        err = _validate_format_github(key)
        assert err is not None
        assert "20" in err

    def test_invalid_github_empty(self):
        err = _validate_format_github("")
        assert err is not None


# ── Supabase ─────────────────────────────────────────────────────────────────


class TestSupabaseValidator:
    def test_valid_supabase_jwt(self):
        key = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghij1234567890"
        assert _validate_format_supabase(key) is None

    def test_valid_supabase_long_alphanumeric(self):
        key = "A" * 25
        assert _validate_format_supabase(key) is None

    def test_invalid_supabase_short(self):
        err = _validate_format_supabase("short")
        assert err is not None
        assert "JWT" in err or "alphanumeric" in err

    def test_invalid_supabase_special_chars(self):
        err = _validate_format_supabase("abc!@#$%^")
        assert err is not None

    def test_invalid_supabase_empty(self):
        err = _validate_format_supabase("")
        assert err is not None


# ── Firebase ─────────────────────────────────────────────────────────────────


class TestFirebaseValidator:
    def test_valid_firebase_key(self):
        key = "A" * 35
        assert _validate_format_firebase(key) is None

    def test_valid_firebase_with_dashes_underscores(self):
        key = "A" * 15 + "-" + "B" * 15
        assert _validate_format_firebase(key) is None

    def test_invalid_firebase_too_short(self):
        err = _validate_format_firebase("abc")
        assert err is not None
        assert "30" in err

    def test_invalid_firebase_special_chars(self):
        key = "A" * 30 + "!@#"
        err = _validate_format_firebase(key)
        assert err is not None
        assert "alphanumeric" in err

    def test_invalid_firebase_empty(self):
        err = _validate_format_firebase("")
        assert err is not None


# ── Vercel ───────────────────────────────────────────────────────────────────


class TestVercelValidator:
    def test_valid_vercel_key(self):
        key = "x" * 25
        assert _validate_format_vercel(key) is None

    def test_valid_vercel_exact_20(self):
        key = "x" * 20
        assert _validate_format_vercel(key) is None

    def test_invalid_vercel_too_short(self):
        err = _validate_format_vercel("short")
        assert err is not None
        assert "20" in err

    def test_invalid_vercel_empty(self):
        err = _validate_format_vercel("")
        assert err is not None


# ── SSH (direct validator) ───────────────────────────────────────────────────


class TestSSHValidator:
    def test_valid_pem_private_key(self):
        key = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIBogIBAAJBALRiMLAHudeSA/x3hB2f+2NRkJLA\n"
            "-----END RSA PRIVATE KEY-----"
        )
        result = validate_credential("ssh", key)
        assert result["status"] == "format_valid"

    def test_invalid_ssh_random_string(self):
        result = validate_credential("ssh", "just-a-random-string")
        assert result["status"] == "invalid"

    def test_invalid_ssh_empty_pem_body(self):
        key = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "\n"
            "-----END RSA PRIVATE KEY-----"
        )
        result = validate_credential("ssh", key)
        assert result["status"] == "invalid"

    def test_invalid_ssh_missing_end_marker(self):
        key = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIBogIBAAJBALRiMLAHudeSA/x3hB2f\n"
        )
        result = validate_credential("ssh", key)
        assert result["status"] == "invalid"


# ── GPG (direct validator) ───────────────────────────────────────────────────


class TestGPGValidator:
    def test_valid_gpg_private_key(self):
        key = (
            "-----BEGIN PGP PRIVATE KEY BLOCK-----\n"
            "lQOYBGJhY2UCEACn3m7x2AAAA\n"
            "-----END PGP PRIVATE KEY BLOCK-----"
        )
        result = validate_credential("gpg", key)
        assert result["status"] == "format_valid"

    def test_valid_gpg_public_key(self):
        key = (
            "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
            "mQENBGJhY2UCEACn3m7x2AAAA\n"
            "-----END PGP PUBLIC KEY BLOCK-----"
        )
        result = validate_credential("gpg", key)
        assert result["status"] == "format_valid"

    def test_invalid_gpg_no_begin_marker(self):
        result = validate_credential("gpg", "not-a-pgp-key")
        assert result["status"] == "invalid"

    def test_invalid_gpg_wrong_type(self):
        key = (
            "-----BEGIN SOMETHING ELSE-----\n"
            "data\n"
            "-----END SOMETHING ELSE-----"
        )
        result = validate_credential("gpg", key)
        assert result["status"] == "invalid"


# ── JWT Signing (direct validator) ──────────────────────────────────────────


class TestJWTSigningValidator:
    def test_valid_jwt_pem_rsa(self):
        key = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIBogIBAAJBALRiMLAHudeSA/x3hB2f+2NRkJLA\n"
            "-----END RSA PRIVATE KEY-----"
        )
        result = validate_credential("jwt_signing", key)
        assert result["status"] == "format_valid"

    def test_valid_jwt_shared_secret(self):
        key = "a" * 40  # 40-char secret
        result = validate_credential("jwt_signing", key)
        assert result["status"] == "format_valid"

    def test_invalid_jwt_short_secret(self):
        result = validate_credential("jwt_signing", "short")
        assert result["status"] == "invalid"
        assert "32" in result["message"]


# ── PostgreSQL (direct validator) ───────────────────────────────────────────


class TestPostgreSQLValidator:
    def test_valid_postgresql_connection_string(self):
        key = "postgresql://user:pass@localhost:5432/mydb"
        result = validate_credential("postgresql", key)
        assert result["status"] == "format_valid"

    def test_valid_postgres_scheme(self):
        key = "postgres://user:pass@host/db"
        result = validate_credential("postgresql", key)
        assert result["status"] == "format_valid"

    def test_invalid_postgresql_short_password(self):
        result = validate_credential("postgresql", "short")
        assert result["status"] == "invalid"

    def test_valid_postgresql_password(self):
        result = validate_credential("postgresql", "a-long-secure-password-here")
        assert result["status"] == "format_valid"


# ── MySQL (direct validator) ────────────────────────────────────────────────


class TestMySQLValidator:
    def test_valid_mysql_connection_string(self):
        key = "mysql://user:pass@localhost:3306/mydb"
        result = validate_credential("mysql", key)
        assert result["status"] == "format_valid"

    def test_invalid_mysql_short_password(self):
        result = validate_credential("mysql", "abc")
        assert result["status"] == "invalid"

    def test_valid_mysql_password(self):
        result = validate_credential("mysql", "secure-password-123")
        assert result["status"] == "format_valid"


# ── Redis (direct validator) ────────────────────────────────────────────────


class TestRedisValidator:
    def test_valid_redis_url(self):
        key = "redis://user:pass@localhost:6379/0"
        result = validate_credential("redis", key)
        assert result["status"] == "format_valid"

    def test_valid_rediss_url(self):
        key = "rediss://user:pass@localhost:6379/0"
        result = validate_credential("redis", key)
        assert result["status"] == "format_valid"

    def test_invalid_redis_short_password(self):
        result = validate_credential("redis", "abc")
        assert result["status"] == "invalid"

    def test_valid_redis_password(self):
        result = validate_credential("redis", "longredispassword1")
        assert result["status"] == "format_valid"


# ── MongoDB (direct validator) ──────────────────────────────────────────────


class TestMongoDBValidator:
    def test_valid_mongodb_connection_string(self):
        key = "mongodb://user:pass@localhost:27017/mydb"
        result = validate_credential("mongodb_cred", key)
        assert result["status"] == "format_valid"

    def test_valid_mongodb_srv(self):
        key = "mongodb+srv://user:pass@cluster0.abc.mongodb.net/mydb"
        result = validate_credential("mongodb_cred", key)
        assert result["status"] == "format_valid"

    def test_invalid_mongodb_short_password(self):
        result = validate_credential("mongodb_cred", "abc")
        assert result["status"] == "invalid"

    def test_valid_mongodb_password(self):
        result = validate_credential("mongodb_cred", "longmongopassword")
        assert result["status"] == "format_valid"


# ── AWS (direct validator) ──────────────────────────────────────────────────


class TestAWSValidator:
    def test_valid_aws_access_key_id(self):
        key = "AKIA" + "A" * 16
        result = validate_credential("aws", key)
        assert result["status"] == "format_valid"

    def test_invalid_aws_wrong_prefix(self):
        key = "XXXX" + "A" * 16
        result = validate_credential("aws", key)
        assert result["status"] == "invalid"

    def test_invalid_aws_access_key_short(self):
        result = validate_credential("aws", "AKIA1234")
        assert result["status"] == "invalid"

    def test_valid_aws_combined_format(self):
        access = "AKIA" + "A" * 16
        secret = "A" * 40
        key = f"{access}:{secret}"
        result = validate_credential("aws", key)
        assert result["status"] == "format_valid"

    def test_invalid_aws_combined_bad_secret(self):
        access = "AKIA" + "A" * 16
        key = f"{access}:short"
        result = validate_credential("aws", key)
        assert result["status"] == "invalid"


# ── GCP (direct validator) ──────────────────────────────────────────────────


class TestGCPValidator:
    def test_valid_gcp_service_account_json(self):
        sa = json.dumps({
            "type": "service_account",
            "project_id": "my-project",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
            "client_email": "test@test.iam.gserviceaccount.com",
        })
        result = validate_credential("gcp", sa)
        assert result["status"] == "format_valid"

    def test_invalid_gcp_json_wrong_type(self):
        sa = json.dumps({"type": "user", "project_id": "x"})
        result = validate_credential("gcp", sa)
        assert result["status"] == "invalid"

    def test_invalid_gcp_json_missing_fields(self):
        sa = json.dumps({"type": "service_account"})
        result = validate_credential("gcp", sa)
        assert result["status"] == "invalid"
        assert "missing" in result["message"].lower()

    def test_invalid_gcp_short_string(self):
        result = validate_credential("gcp", "short")
        assert result["status"] == "invalid"

    def test_valid_gcp_opaque_key(self):
        result = validate_credential("gcp", "x" * 15)
        assert result["status"] == "format_valid"


# ── Azure (direct validator) ────────────────────────────────────────────────


class TestAzureValidator:
    def test_valid_azure_guid(self):
        key = "12345678-1234-1234-1234-123456789abc"
        result = validate_credential("azure", key)
        assert result["status"] == "format_valid"
        assert "GUID" in result["message"]

    def test_valid_azure_client_secret(self):
        key = "x" * 35
        result = validate_credential("azure", key)
        assert result["status"] == "format_valid"

    def test_invalid_azure_too_short(self):
        result = validate_credential("azure", "short")
        assert result["status"] == "invalid"

    def test_invalid_azure_bad_guid(self):
        result = validate_credential("azure", "1234-5678-not-a-guid")
        assert result["status"] == "invalid"


# ── TLS/SSL (direct validator) ──────────────────────────────────────────────


class TestTLSSSLValidator:
    def test_valid_tls_certificate(self):
        key = (
            "-----BEGIN CERTIFICATE-----\n"
            "MIIBkTCB+wIJALmqKwQ+2AAAMA0GCSqGSIb3DQ==\n"
            "-----END CERTIFICATE-----"
        )
        result = validate_credential("tls_ssl", key)
        assert result["status"] == "format_valid"
        assert "certificate" in result["message"]

    def test_valid_tls_private_key(self):
        key = (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIBVQIBADANBgkqhkiG9w0BAQEFAASCAT8wgg==\n"
            "-----END PRIVATE KEY-----"
        )
        result = validate_credential("tls_ssl", key)
        assert result["status"] == "format_valid"
        assert "private_key" in result["message"]

    def test_invalid_tls_no_markers(self):
        result = validate_credential("tls_ssl", "not a certificate")
        assert result["status"] == "invalid"

    def test_invalid_tls_missing_end(self):
        key = "-----BEGIN CERTIFICATE-----\ndata\n"
        result = validate_credential("tls_ssl", key)
        assert result["status"] == "invalid"


# ── Docker Hub (direct validator) ───────────────────────────────────────────


class TestDockerHubValidator:
    @patch("backend.key_types.infra_keys.requests.get", side_effect=Exception("no network"))
    def test_valid_docker_hub_token_format(self, mock_get):
        key = "x" * 40
        result = validate_credential("docker_hub", key)
        assert result["status"] == "format_valid"

    def test_invalid_docker_hub_too_short(self):
        result = validate_credential("docker_hub", "short")
        assert result["status"] == "invalid"
        assert "36" in result["message"]


# ── GitHub Actions (direct validator) ───────────────────────────────────────


class TestGitHubActionsValidator:
    def test_valid_ghp_prefix(self):
        key = "ghp_" + "a" * 20
        result = validate_credential("github_actions", key)
        assert result["status"] == "format_valid"

    def test_valid_v1_prefix(self):
        key = "v1." + "a" * 20
        result = validate_credential("github_actions", key)
        assert result["status"] == "format_valid"

    def test_invalid_too_short(self):
        result = validate_credential("github_actions", "ghp_short")
        assert result["status"] == "invalid"
        assert "20" in result["message"]

    def test_invalid_wrong_prefix(self):
        key = "wrong_" + "a" * 20
        result = validate_credential("github_actions", key)
        assert result["status"] == "invalid"


# ── CircleCI (direct validator) ─────────────────────────────────────────────


class TestCircleCIValidator:
    def test_valid_circleci_token(self):
        key = "a" * 45
        result = validate_credential("circleci", key)
        assert result["status"] == "format_valid"

    def test_invalid_circleci_too_short(self):
        result = validate_credential("circleci", "a" * 10)
        assert result["status"] == "invalid"
        assert "40" in result["message"]


# ── GitLab CI (direct validator) ────────────────────────────────────────────


class TestGitLabCIValidator:
    def test_valid_glpat_prefix(self):
        result = validate_credential("gitlab_ci", "glpat-abcdef1234567890")
        assert result["status"] == "format_valid"
        assert "glpat-" in result["message"]

    def test_valid_long_token(self):
        key = "a" * 25
        result = validate_credential("gitlab_ci", key)
        assert result["status"] == "format_valid"

    def test_invalid_short_token(self):
        result = validate_credential("gitlab_ci", "short")
        assert result["status"] == "invalid"


# ── Encryption (direct validator) ───────────────────────────────────────────


class TestEncryptionValidator:
    def test_valid_hex_key(self):
        key = "a" * 64  # 64 hex chars
        result = validate_credential("encryption", key)
        assert result["status"] == "format_valid"
        assert "hex" in result["message"].lower()

    def test_valid_base64_key(self):
        # A valid base64 string that roundtrips
        import base64
        raw = b"A" * 24
        key = base64.b64encode(raw).decode()
        result = validate_credential("encryption", key)
        assert result["status"] == "format_valid"

    def test_valid_vault_token_hvs(self):
        result = validate_credential("encryption", "hvs.CAESIGL0MDB4Y2dSS3hkZVVXbGpVQ")
        assert result["status"] == "format_valid"
        assert "Vault" in result["message"]

    def test_valid_vault_token_s(self):
        result = validate_credential("encryption", "s.abcdefghijklmnopqrstuvwx")
        assert result["status"] == "format_valid"
        assert "Vault" in result["message"]

    def test_invalid_encryption_short(self):
        result = validate_credential("encryption", "short")
        assert result["status"] == "invalid"


# ── OAuth Generic (direct validator) ────────────────────────────────────────


class TestOAuthGenericValidator:
    def test_valid_oauth_token(self):
        key = "x" * 15
        result = validate_credential("oauth_generic", key)
        assert result["status"] == "format_valid"

    def test_invalid_oauth_too_short(self):
        result = validate_credential("oauth_generic", "short")
        assert result["status"] == "invalid"
        assert "10" in result["message"]


# ── Twilio (direct validator) ───────────────────────────────────────────────


class TestTwilioValidator:
    @patch("backend.key_types.service_keys.requests.get", side_effect=Exception("no network"))
    def test_valid_twilio_account_sid(self, mock_get):
        key = "AC" + "a" * 32
        result = validate_credential("twilio", key)
        assert result["status"] == "format_valid"

    def test_valid_twilio_auth_token(self):
        key = "a" * 32  # 32 hex chars
        result = validate_credential("twilio", key)
        assert result["status"] == "format_valid"
        assert "Auth Token" in result["message"]

    def test_invalid_twilio_short(self):
        result = validate_credential("twilio", "short")
        assert result["status"] == "invalid"

    def test_invalid_twilio_ac_non_hex(self):
        key = "AC" + "z" * 32  # 'z' is not hex
        result = validate_credential("twilio", key)
        assert result["status"] == "invalid"


# ── SendGrid (direct validator) ─────────────────────────────────────────────


class TestSendGridValidator:
    @patch("backend.key_types.service_keys.requests.get", side_effect=Exception("no network"))
    def test_valid_sendgrid_key(self, mock_get):
        key = "SG." + "a" * 50
        result = validate_credential("sendgrid", key)
        assert result["status"] == "format_valid"

    def test_invalid_sendgrid_wrong_prefix(self):
        result = validate_credential("sendgrid", "XX." + "a" * 50)
        assert result["status"] == "invalid"
        assert "SG." in result["message"]

    def test_invalid_sendgrid_too_short(self):
        result = validate_credential("sendgrid", "SG.short")
        assert result["status"] == "invalid"
        assert "50" in result["message"]


# ── Main validate_credential function ───────────────────────────────────────


class TestValidateCredential:
    def test_known_core_provider_valid_format(self):
        """A valid OpenAI key with no network should still yield a result."""
        key = "sk-" + "a" * 45
        with patch("backend.validators._live_validate_openai", side_effect=Exception("no network")):
            result = validate_credential("openai", key)
        assert result["status"] in ("format_valid", "active", "invalid", "timeout")
        assert "message" in result

    def test_known_core_provider_invalid_format(self):
        result = validate_credential("openai", "bad")
        assert result["status"] == "invalid"
        assert "Invalid key format" in result["message"]

    def test_unknown_provider_valid_length(self):
        result = validate_credential("unknown_provider_xyz", "a" * 20)
        assert result["status"] == "format_valid"
        assert "No specific validator" in result["message"]

    def test_unknown_provider_too_short(self):
        result = validate_credential("unknown_provider_xyz", "abc")
        assert result["status"] == "invalid"
        assert "too short" in result["message"]

    def test_case_insensitive_provider(self):
        """Provider lookup should be case-insensitive."""
        result = validate_credential("OPENAI", "bad")
        assert result["status"] == "invalid"

    def test_result_has_required_keys(self):
        result = validate_credential("openai", "sk-" + "a" * 45)
        assert "status" in result
        assert "response_time" in result
        assert "message" in result

    def test_direct_validator_provider_returns_dict(self):
        """Direct validators (e.g. ssh) should return a full dict result."""
        key = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIBogIBAAJBALRiMLAHudeSA/x3hB2f+2NRkJLA\n"
            "-----END RSA PRIVATE KEY-----"
        )
        result = validate_credential("ssh", key)
        assert isinstance(result, dict)
        assert "status" in result

    def test_stripe_valid_format_no_live(self):
        """Stripe format-valid key with mocked live validation failing gracefully."""
        key = "sk_test_" + "a" * 30
        with patch("backend.validators._live_validate_stripe", side_effect=Exception("offline")):
            result = validate_credential("stripe", key)
        assert result["status"] in ("format_valid", "active", "invalid", "timeout")

    def test_firebase_format_valid(self):
        key = "A" * 40
        result = validate_credential("firebase", key)
        assert result["status"] == "format_valid"

    def test_vercel_format_valid(self):
        key = "verceltoken" + "A" * 20
        result = validate_credential("vercel", key)
        assert result["status"] == "format_valid"

    def test_supabase_jwt_format_valid(self):
        key = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdef1234567890ABCD"
        result = validate_credential("supabase", key)
        assert result["status"] == "format_valid"

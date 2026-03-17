"""Comprehensive tests for Pydantic models: core, security, lifecycle, analytics."""

import uuid
import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from backend.models import (
    UserCreate,
    UserLogin,
    UserResponse,
    ProjectCreate,
    ProjectAnalysis,
    CredentialCreate,
    CredentialUpdate,
    CredentialResponse,
    Credential,
    ALLOWED_API_NAMES,
    ALLOWED_ENVIRONMENTS,
)
from backend.models_security import (
    MFASetup,
    MFAVerify,
    MFAStatusResponse,
    IPAllowlistEntry,
    IPAllowlistCreate,
    SessionInfo,
    SessionResponse,
    EncryptionKeyRotationRequest,
    EncryptionKeyRotationResponse,
)
from backend.models_lifecycle import (
    CredentialExpiration,
    CredentialExpirationCreate,
    CredentialExpirationResponse,
    CredentialPermission,
    CredentialPermissionCreate,
    CredentialPermissionResponse,
    CredentialVersion,
    CredentialVersionResponse,
    AutoRotationConfig,
    AutoRotationConfigCreate,
)
from backend.models_analytics import (
    BreachCheckResult,
    BreachCheckResponse,
    UsageEvent,
    UsageAnalytics,
    ComplianceReport,
    LifecycleEvent,
    LifecycleTimelineResponse,
)


# ── UserCreate ───────────────────────────────────────────────────────────────


class TestUserCreate:
    def test_valid_user_create(self):
        user = UserCreate(username="testuser", password="securepass123")
        assert user.username == "testuser"
        assert user.password == "securepass123"

    def test_username_too_short(self):
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(username="ab", password="securepass123")
        assert "username" in str(exc_info.value).lower() or "min_length" in str(exc_info.value).lower()

    def test_password_too_short(self):
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(username="testuser", password="short")
        assert "password" in str(exc_info.value).lower() or "min_length" in str(exc_info.value).lower()

    def test_username_at_min_length(self):
        user = UserCreate(username="abc", password="securepass123")
        assert user.username == "abc"

    def test_username_at_max_length(self):
        user = UserCreate(username="a" * 50, password="securepass123")
        assert len(user.username) == 50

    def test_username_exceeds_max_length(self):
        with pytest.raises(ValidationError):
            UserCreate(username="a" * 51, password="securepass123")

    def test_missing_username(self):
        with pytest.raises(ValidationError):
            UserCreate(password="securepass123")

    def test_missing_password(self):
        with pytest.raises(ValidationError):
            UserCreate(username="testuser")


# ── UserLogin ────────────────────────────────────────────────────────────────


class TestUserLogin:
    def test_valid_login(self):
        login = UserLogin(username="user", password="pass")
        assert login.username == "user"

    def test_missing_fields(self):
        with pytest.raises(ValidationError):
            UserLogin()


# ── ProjectCreate ────────────────────────────────────────────────────────────


class TestProjectCreate:
    def test_valid_project_create(self):
        proj = ProjectCreate(project_name="MyProject")
        assert proj.project_name == "MyProject"

    def test_empty_name_fails(self):
        with pytest.raises(ValidationError):
            ProjectCreate(project_name="")

    def test_name_at_max_length(self):
        proj = ProjectCreate(project_name="x" * 200)
        assert len(proj.project_name) == 200

    def test_name_exceeds_max_length(self):
        with pytest.raises(ValidationError):
            ProjectCreate(project_name="x" * 201)

    def test_missing_project_name(self):
        with pytest.raises(ValidationError):
            ProjectCreate()


# ── ProjectAnalysis ──────────────────────────────────────────────────────────


class TestProjectAnalysis:
    def test_default_values(self):
        pa = ProjectAnalysis(
            project_name="test",
            detected_apis=[],
            file_count=5,
        )
        assert pa.id  # auto-generated UUID
        assert pa.analysis_timestamp is not None
        assert pa.recommendations == []

    def test_uuid_is_generated(self):
        pa1 = ProjectAnalysis(project_name="a", detected_apis=[], file_count=0)
        pa2 = ProjectAnalysis(project_name="b", detected_apis=[], file_count=0)
        assert pa1.id != pa2.id


# ── CredentialCreate ─────────────────────────────────────────────────────────


class TestCredentialCreate:
    def test_valid_credential_create(self):
        cred = CredentialCreate(api_name="openai", api_key="sk-test-key-123")
        assert cred.api_name == "openai"
        assert cred.environment == "development"

    @pytest.mark.parametrize("api_name", ALLOWED_API_NAMES)
    def test_all_allowed_api_names(self, api_name):
        cred = CredentialCreate(api_name=api_name, api_key="test-key-value")
        assert cred.api_name == api_name

    def test_invalid_api_name_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            CredentialCreate(api_name="not_allowed_api", api_key="key123")
        assert "api_name" in str(exc_info.value).lower()

    @pytest.mark.parametrize("env", ALLOWED_ENVIRONMENTS)
    def test_valid_environments(self, env):
        cred = CredentialCreate(api_name="openai", api_key="key123", environment=env)
        assert cred.environment == env

    def test_invalid_environment_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            CredentialCreate(api_name="openai", api_key="key123", environment="invalid_env")
        assert "environment" in str(exc_info.value).lower()

    def test_api_name_case_insensitive(self):
        cred = CredentialCreate(api_name="OPENAI", api_key="key123")
        assert cred.api_name == "openai"

    def test_empty_api_key_fails(self):
        with pytest.raises(ValidationError):
            CredentialCreate(api_name="openai", api_key="")


# ── Credential ───────────────────────────────────────────────────────────────


class TestCredential:
    def test_default_values(self):
        cred = Credential(api_name="openai")
        assert cred.api_key_encrypted == ""
        assert cred.status == "unknown"
        assert cred.last_tested is None
        assert cred.environment == "development"
        assert cred.user_id == ""
        assert cred.created_at is not None

    def test_uuid_generation(self):
        c1 = Credential(api_name="openai")
        c2 = Credential(api_name="openai")
        assert c1.id != c2.id
        # Verify it's a valid UUID
        uuid.UUID(c1.id)

    def test_custom_values(self):
        cred = Credential(
            api_name="stripe",
            api_key_encrypted="encrypted_data",
            status="active",
            environment="production",
            user_id="user-123",
        )
        assert cred.api_name == "stripe"
        assert cred.api_key_encrypted == "encrypted_data"
        assert cred.status == "active"
        assert cred.environment == "production"
        assert cred.user_id == "user-123"


# ── CredentialUpdate ─────────────────────────────────────────────────────────


class TestCredentialUpdate:
    def test_all_none_by_default(self):
        cu = CredentialUpdate()
        assert cu.api_key is None
        assert cu.environment is None

    def test_partial_update(self):
        cu = CredentialUpdate(api_key="new-key")
        assert cu.api_key == "new-key"
        assert cu.environment is None


# ── models_security.py ──────────────────────────────────────────────────────


class TestSecurityModels:
    def test_mfa_setup_defaults(self):
        mfa = MFASetup(secret="JBSWY3DPEHPK3PXP", provisioning_uri="otpauth://totp/test")
        assert mfa.backup_codes == []

    def test_mfa_verify_code_length(self):
        mv = MFAVerify(code="123456")
        assert mv.code == "123456"

    def test_mfa_verify_code_too_short(self):
        with pytest.raises(ValidationError):
            MFAVerify(code="123")

    def test_mfa_verify_code_too_long(self):
        with pytest.raises(ValidationError):
            MFAVerify(code="1234567")

    def test_mfa_status_response_defaults(self):
        ms = MFAStatusResponse(enabled=False)
        assert ms.created_at is None

    def test_ip_allowlist_entry_defaults(self):
        entry = IPAllowlistEntry(user_id="u1", ip_address="192.168.1.1")
        assert entry.description == ""
        assert entry.created_at is not None
        uuid.UUID(entry.id)

    def test_ip_allowlist_create_min_length(self):
        with pytest.raises(ValidationError):
            IPAllowlistCreate(ip_address="1.1")

    def test_ip_allowlist_create_valid(self):
        iac = IPAllowlistCreate(ip_address="192.168.1.1")
        assert iac.description == ""

    def test_session_info_defaults(self):
        si = SessionInfo(user_id="u1", token_hash="abc123")
        assert si.is_active is True
        assert si.ip_address is None
        assert si.user_agent is None
        uuid.UUID(si.id)

    def test_session_response_defaults(self):
        sr = SessionResponse(
            id="id1",
            created_at=datetime.now(timezone.utc),
            last_active=datetime.now(timezone.utc),
        )
        assert sr.is_current is False

    def test_encryption_key_rotation_request_defaults(self):
        req = EncryptionKeyRotationRequest()
        assert req.new_key is None

    def test_encryption_key_rotation_response(self):
        resp = EncryptionKeyRotationResponse(
            message="done",
            credentials_re_encrypted=5,
            timestamp=datetime.now(timezone.utc),
        )
        assert resp.credentials_re_encrypted == 5


# ── models_lifecycle.py ─────────────────────────────────────────────────────


class TestLifecycleModels:
    def test_credential_expiration_defaults(self):
        ce = CredentialExpiration(
            credential_id="c1",
            user_id="u1",
            expires_at=datetime.now(timezone.utc),
        )
        assert ce.alert_days_before == 7
        assert ce.alert_sent is False
        uuid.UUID(ce.id)

    def test_credential_expiration_create_defaults(self):
        cec = CredentialExpirationCreate(
            credential_id="c1",
            expires_at=datetime.now(timezone.utc),
        )
        assert cec.alert_days_before == 7

    def test_credential_expiration_response_defaults(self):
        cer = CredentialExpirationResponse(
            id="id1",
            credential_id="c1",
            expires_at=datetime.now(timezone.utc),
            alert_days_before=7,
        )
        assert cer.api_name == ""
        assert cer.days_until_expiry == 0
        assert cer.is_expired is False
        assert cer.alert_sent is False

    def test_credential_permission_defaults(self):
        cp = CredentialPermission(
            credential_id="c1",
            user_id="u1",
            granted_by="u2",
        )
        assert cp.permission == "read"
        uuid.UUID(cp.id)

    def test_credential_permission_create(self):
        cpc = CredentialPermissionCreate(
            credential_id="c1",
            username="testuser",
        )
        assert cpc.permission == "read"

    def test_credential_permission_response(self):
        cpr = CredentialPermissionResponse(
            id="id1",
            credential_id="c1",
            user_id="u1",
            permission="admin",
            granted_by="u2",
            created_at=datetime.now(timezone.utc),
        )
        assert cpr.api_name == ""
        assert cpr.username == ""

    def test_credential_version_defaults(self):
        cv = CredentialVersion(
            credential_id="c1",
            user_id="u1",
            version_number=1,
            api_key_encrypted="enc123",
        )
        assert cv.change_reason == ""
        assert cv.is_current is True
        uuid.UUID(cv.id)

    def test_credential_version_response(self):
        cvr = CredentialVersionResponse(
            id="id1",
            credential_id="c1",
            version_number=2,
            api_key_preview="****xyz",
            change_reason="rotated",
            created_at=datetime.now(timezone.utc),
            is_current=False,
        )
        assert cvr.is_current is False

    def test_auto_rotation_config_defaults(self):
        arc = AutoRotationConfig(
            credential_id="c1",
            user_id="u1",
            provider="aws",
        )
        assert arc.rotation_interval_days == 90
        assert arc.last_rotated is None
        assert arc.next_rotation is None
        assert arc.enabled is True
        uuid.UUID(arc.id)

    def test_auto_rotation_config_create_defaults(self):
        arcc = AutoRotationConfigCreate(credential_id="c1")
        assert arcc.rotation_interval_days == 90
        assert arcc.enabled is True


# ── models_analytics.py ─────────────────────────────────────────────────────


class TestAnalyticsModels:
    def test_breach_check_result_defaults(self):
        bcr = BreachCheckResult(
            credential_id="c1",
            user_id="u1",
        )
        assert bcr.is_compromised is False
        assert bcr.source == ""
        assert bcr.details == ""
        assert bcr.check_timestamp is not None
        uuid.UUID(bcr.id)

    def test_breach_check_response(self):
        resp = BreachCheckResponse(
            credential_id="c1",
            api_name="openai",
            is_compromised=True,
            sources_checked=["haveibeenpwned"],
            last_checked=datetime.now(timezone.utc),
        )
        assert resp.recommendation == ""

    def test_usage_event_defaults(self):
        ue = UsageEvent(
            credential_id="c1",
            user_id="u1",
            action="tested",
        )
        assert ue.timestamp is not None
        uuid.UUID(ue.id)

    def test_usage_analytics_defaults(self):
        ua = UsageAnalytics(
            credential_id="c1",
            api_name="stripe",
        )
        assert ua.total_uses == 0
        assert ua.last_used is None
        assert ua.uses_last_7_days == 0
        assert ua.uses_last_30_days == 0
        assert ua.is_idle is False

    def test_compliance_report_defaults(self):
        cr = ComplianceReport(
            user_id="u1",
            report_type="soc2",
        )
        assert cr.summary == {}
        assert cr.findings == []
        assert cr.generated_at is not None
        uuid.UUID(cr.id)

    def test_lifecycle_event_defaults(self):
        le = LifecycleEvent(
            credential_id="c1",
            user_id="u1",
            event_type="created",
        )
        assert le.details == ""
        assert le.timestamp is not None
        uuid.UUID(le.id)

    def test_lifecycle_timeline_response_defaults(self):
        ltr = LifecycleTimelineResponse(
            credential_id="c1",
            api_name="github",
        )
        assert ltr.events == []
        assert ltr.created_at is None
        assert ltr.current_status == "unknown"

"""Comprehensive tests for backend.security — encryption, password hashing, JWT."""

import pytest
from datetime import timedelta
from fastapi import HTTPException

from backend.security import (
    encrypt_api_key,
    decrypt_api_key,
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


# ── Fernet encryption / decryption ──────────────────────────────────────────


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "sk-test1234567890abcdefghijklmnop"
        encrypted = encrypt_api_key(plaintext)
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == plaintext

    def test_encrypted_is_not_plaintext(self):
        plaintext = "my-secret-api-key"
        encrypted = encrypt_api_key(plaintext)
        assert encrypted != plaintext

    def test_different_plaintexts_produce_different_ciphertexts(self):
        enc1 = encrypt_api_key("key-one-value")
        enc2 = encrypt_api_key("key-two-value")
        assert enc1 != enc2

    def test_decrypt_garbage_returns_placeholder(self):
        result = decrypt_api_key("not-a-valid-fernet-token")
        assert result == "[decryption failed]"

    def test_decrypt_empty_string_returns_placeholder(self):
        result = decrypt_api_key("")
        assert result == "[decryption failed]"

    def test_encrypt_empty_string_roundtrip(self):
        encrypted = encrypt_api_key("")
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == ""

    def test_encrypt_unicode_roundtrip(self):
        plaintext = "api-key-with-unicode-\u00e9\u00e8\u00ea"
        encrypted = encrypt_api_key(plaintext)
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == plaintext

    def test_encrypt_long_key_roundtrip(self):
        plaintext = "x" * 1000
        encrypted = encrypt_api_key(plaintext)
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == plaintext


# ── Password hashing ────────────────────────────────────────────────────────


class TestPasswordHashing:
    def test_hash_verify_roundtrip(self):
        password = "my-secure-password-123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_hash_is_not_plaintext(self):
        password = "test-password"
        hashed = hash_password(password)
        assert hashed != password

    def test_wrong_password_fails(self):
        password = "correct-password"
        hashed = hash_password(password)
        assert verify_password("wrong-password", hashed) is False

    def test_different_passwords_produce_different_hashes(self):
        h1 = hash_password("password1")
        h2 = hash_password("password2")
        assert h1 != h2

    def test_same_password_produces_different_hashes(self):
        """bcrypt salting should produce different hashes for the same input."""
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        assert h1 != h2
        # Both should still verify
        assert verify_password("same-password", h1)
        assert verify_password("same-password", h2)

    def test_hash_empty_password(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False


# ── JWT tokens ───────────────────────────────────────────────────────────────


class TestJWT:
    def test_create_decode_roundtrip(self):
        data = {"sub": "testuser", "role": "admin"}
        token = create_access_token(data)
        payload = decode_access_token(token)
        assert payload["sub"] == "testuser"
        assert payload["role"] == "admin"
        assert "exp" in payload

    def test_token_contains_exp_claim(self):
        token = create_access_token({"sub": "user1"})
        payload = decode_access_token(token)
        assert "exp" in payload

    def test_custom_expiry(self):
        data = {"sub": "user1"}
        token = create_access_token(data, expires_delta=timedelta(minutes=5))
        payload = decode_access_token(token)
        assert payload["sub"] == "user1"

    def test_expired_token_raises_401(self):
        data = {"sub": "user1"}
        token = create_access_token(data, expires_delta=timedelta(seconds=-10))
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(token)
        assert exc_info.value.status_code == 401

    def test_invalid_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token("this.is.not.a.valid.jwt")
        assert exc_info.value.status_code == 401

    def test_tampered_token_raises_401(self):
        token = create_access_token({"sub": "user1"})
        # Tamper with the token by modifying a character
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(tampered)
        assert exc_info.value.status_code == 401

    def test_empty_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token("")
        assert exc_info.value.status_code == 401

    def test_original_data_not_mutated(self):
        data = {"sub": "user1"}
        original = data.copy()
        create_access_token(data)
        assert data == original  # Should not have been modified

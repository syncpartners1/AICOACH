"""Unit tests for auth.py — password hashing and verification."""
import pytest
from autogpt.coaching.auth import hash_password, verify_password


class TestHashPassword:
    def test_returns_string(self):
        h = hash_password("secret123")
        assert isinstance(h, str)

    def test_contains_separator(self):
        h = hash_password("secret123")
        assert ":" in h

    def test_salt_and_digest_present(self):
        h = hash_password("secret123")
        parts = h.split(":")
        assert len(parts) == 2
        salt_hex, dk_hex = parts
        assert len(salt_hex) == 32   # 16 bytes → 32 hex chars
        assert len(dk_hex) == 64     # SHA-256 → 32 bytes → 64 hex chars

    def test_two_hashes_differ(self):
        # Different salts → different hashes
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2


class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        password = "MyStr0ngP@ss!"
        stored = hash_password(password)
        assert verify_password(password, stored) is True

    def test_wrong_password_returns_false(self):
        stored = hash_password("correct_password")
        assert verify_password("wrong_password", stored) is False

    def test_empty_password_hashes_and_verifies(self):
        h = hash_password("")
        assert verify_password("", h) is True
        assert verify_password("not_empty", h) is False

    def test_malformed_stored_returns_false(self):
        assert verify_password("anything", "not_a_valid_hash") is False
        assert verify_password("anything", "") is False
        assert verify_password("anything", ":") is False

    def test_unicode_password(self):
        password = "שלום🔐"
        stored = hash_password(password)
        assert verify_password(password, stored) is True
        assert verify_password("wrong", stored) is False

"""Unit tests for Encryption utility."""

import pytest
from security.encryption import Encryption


@pytest.fixture
def enc():
    return Encryption()


@pytest.fixture
def fernet_key():
    ok, key = Encryption.keyGenerator("test-secret-string")
    assert ok
    return key


# ── keyGenerator ──────────────────────────────────────────────────────────────

def test_keyGenerator_returns_bytes(fernet_key):
    assert isinstance(fernet_key, bytes)


def test_keyGenerator_deterministic():
    _, key1 = Encryption.keyGenerator("same-input")
    _, key2 = Encryption.keyGenerator("same-input")
    assert key1 == key2


def test_keyGenerator_different_inputs_produce_different_keys():
    _, key1 = Encryption.keyGenerator("input-a")
    _, key2 = Encryption.keyGenerator("input-b")
    assert key1 != key2


# ── encryptSentence / decryptSentence ─────────────────────────────────────────

def test_encrypt_decrypt_roundtrip(fernet_key):
    plaintext = "hello world"
    ok, ciphertext = Encryption.encryptSentence(plaintext, fernet_key)
    assert ok

    ok2, result = Encryption.decryptSentence(ciphertext, fernet_key)
    assert ok2
    assert result == plaintext


def test_encrypt_produces_different_ciphertext_each_time(fernet_key):
    """Fernet uses a random IV — same input yields different ciphertext."""
    _, ct1 = Encryption.encryptSentence("same", fernet_key)
    _, ct2 = Encryption.encryptSentence("same", fernet_key)
    assert ct1 != ct2


def test_decrypt_with_wrong_key_fails():
    _, key1 = Encryption.keyGenerator("key-one")
    _, key2 = Encryption.keyGenerator("key-two")
    _, ciphertext = Encryption.encryptSentence("secret", key1)
    ok, _ = Encryption.decryptSentence(ciphertext, key2)
    assert not ok


def test_encrypt_static_alias(fernet_key):
    ok, ct = Encryption.encrypt("msg", fernet_key)
    assert ok
    ok2, plain = Encryption.decrypt(ct, fernet_key)
    assert ok2
    assert plain == "msg"


# ── hash ──────────────────────────────────────────────────────────────────────

def test_hash_deterministic():
    h1 = Encryption.hash("username")
    h2 = Encryption.hash("username")
    assert h1 == h2


def test_hash_different_inputs_produce_different_hashes():
    assert Encryption.hash("alice") != Encryption.hash("bob")


def test_hash_returns_64_char_hex():
    h = Encryption.hash("test")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ── encryptPass / isValidPass (Argon2) ────────────────────────────────────────

def test_encryptPass_returns_string(enc):
    hashed = enc.encryptPass("my-password")
    assert isinstance(hashed, str)


def test_isValidPass_correct_password(enc):
    hashed = enc.encryptPass("correct-password")
    valid, _ = enc.isValidPass(hashed, "correct-password")
    assert valid


def test_isValidPass_wrong_password(enc):
    hashed = enc.encryptPass("correct-password")
    valid, _ = enc.isValidPass(hashed, "wrong-password")
    assert not valid


def test_encryptPass_different_hashes_same_input(enc):
    """Argon2 uses random salt — same password yields different hashes."""
    h1 = enc.encryptPass("password")
    h2 = enc.encryptPass("password")
    assert h1 != h2

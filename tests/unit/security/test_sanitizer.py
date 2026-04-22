"""Unit tests for Sanitizer utility."""

import pytest
from security.sanitizer import Sanitizer


# ── cleanHtml ─────────────────────────────────────────────────────────────────

def test_removes_script_tag():
    result = Sanitizer.cleanHtml("<script>alert('xss')</script>hello")
    assert "<script>" not in result
    assert "hello" in result


def test_removes_onclick_attribute():
    result = Sanitizer.cleanHtml('<a onclick="evil()">click</a>')
    assert "onclick" not in result


def test_removes_onerror_attribute():
    result = Sanitizer.cleanHtml('<img src="x" onerror="evil()">')
    assert "onerror" not in result


def test_preserves_plain_text():
    text = "Hello, I am clean text."
    assert Sanitizer.cleanHtml(text) == text


def test_removes_all_html_tags():
    """NoHarm allows zero HTML tags."""
    result = Sanitizer.cleanHtml("<b>bold</b> and <i>italic</i>")
    assert "<b>" not in result
    assert "<i>" not in result
    assert "bold" in result
    assert "italic" in result


def test_non_string_input_returned_unchanged():
    assert Sanitizer.cleanHtml(None) is None
    assert Sanitizer.cleanHtml(42) == 42


def test_empty_string_stays_empty():
    assert Sanitizer.cleanHtml("") == ""


# ── isValidUsername ───────────────────────────────────────────────────────────

def test_valid_username_alphanumeric():
    assert Sanitizer.isValidUsername("alice123") is True


def test_valid_username_with_underscore():
    assert Sanitizer.isValidUsername("alice_bob") is True


def test_valid_username_with_hyphen():
    assert Sanitizer.isValidUsername("alice-bob") is True


def test_valid_username_min_length():
    assert Sanitizer.isValidUsername("abc") is True


def test_valid_username_max_length():
    assert Sanitizer.isValidUsername("a" * 30) is True


def test_invalid_username_too_short():
    assert Sanitizer.isValidUsername("ab") is False


def test_invalid_username_too_long():
    assert Sanitizer.isValidUsername("a" * 31) is False


def test_invalid_username_space():
    assert Sanitizer.isValidUsername("alice bob") is False


def test_invalid_username_special_chars():
    assert Sanitizer.isValidUsername("alice@bob") is False


def test_invalid_username_empty():
    assert Sanitizer.isValidUsername("") is False

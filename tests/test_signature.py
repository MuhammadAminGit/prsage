"""Webhook signature verification tests."""

import pytest

from app.webhooks.signature import (
    InvalidSignatureError,
    compute_signature,
    verify_signature,
)


SECRET = "topsecret"
BODY = b'{"action":"opened","number":1}'


def test_compute_signature_is_deterministic():
    a = compute_signature(SECRET, BODY)
    b = compute_signature(SECRET, BODY)
    assert a == b
    assert a.startswith("sha256=")


def test_verify_accepts_valid_signature():
    sig = compute_signature(SECRET, BODY)
    verify_signature(SECRET, BODY, sig)  # does not raise


def test_verify_rejects_wrong_signature():
    with pytest.raises(InvalidSignatureError):
        verify_signature(SECRET, BODY, "sha256=" + "0" * 64)


def test_verify_rejects_missing_signature():
    with pytest.raises(InvalidSignatureError, match="Missing"):
        verify_signature(SECRET, BODY, None)


def test_verify_rejects_wrong_prefix():
    with pytest.raises(InvalidSignatureError, match="prefix"):
        verify_signature(SECRET, BODY, "sha1=abc")


def test_verify_rejects_tampered_body():
    sig = compute_signature(SECRET, BODY)
    tampered = BODY + b" "
    with pytest.raises(InvalidSignatureError):
        verify_signature(SECRET, tampered, sig)


def test_verify_rejects_wrong_secret():
    sig = compute_signature(SECRET, BODY)
    with pytest.raises(InvalidSignatureError):
        verify_signature("different-secret", BODY, sig)

"""GitHub App JWT generation tests."""

import jwt as pyjwt

from app.github.auth import (
    JWT_LIFETIME_SECONDS,
    generate_app_jwt,
    reset_jwt_cache,
)


def test_jwt_contains_expected_claims(rsa_private_key_pem):
    reset_jwt_cache()
    now = 1_700_000_000
    token = generate_app_jwt("12345", rsa_private_key_pem, now=now)

    decoded = pyjwt.decode(token, options={"verify_signature": False})
    assert decoded["iss"] == "12345"
    assert decoded["iat"] == now - 30  # back-dated 30s for clock skew
    assert decoded["exp"] == now + JWT_LIFETIME_SECONDS


def test_jwt_is_cached_within_freshness_window(rsa_private_key_pem):
    reset_jwt_cache()
    now = 1_700_000_000
    a = generate_app_jwt("12345", rsa_private_key_pem, now=now)
    b = generate_app_jwt("12345", rsa_private_key_pem, now=now + 60)
    assert a == b


def test_jwt_regenerates_after_expiry(rsa_private_key_pem):
    reset_jwt_cache()
    now = 1_700_000_000
    a = generate_app_jwt("12345", rsa_private_key_pem, now=now)
    later = now + JWT_LIFETIME_SECONDS + 10
    b = generate_app_jwt("12345", rsa_private_key_pem, now=later)
    assert a != b


def test_jwt_signature_verifies_with_public_key(rsa_private_key_pem):
    reset_jwt_cache()
    token = generate_app_jwt("12345", rsa_private_key_pem)

    private_pem = rsa_private_key_pem.read_bytes()
    private_key = pyjwt.algorithms.RSAAlgorithm.from_jwk  # noqa: F841 — sanity import
    # Decode with the matching public key derived from the private key.
    from cryptography.hazmat.primitives import serialization

    private_obj = serialization.load_pem_private_key(private_pem, password=None)
    public_pem = private_obj.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    decoded = pyjwt.decode(token, public_pem, algorithms=["RS256"])
    assert decoded["iss"] == "12345"

"""HMAC-SHA256 verification for GitHub webhook payloads.

GitHub signs every webhook with the secret we configured on the App. The
signature lands in the ``X-Hub-Signature-256`` header as ``sha256=<hex>``.

We compute HMAC-SHA256 over the raw request body and compare in
constant time. Any payload that doesn't match is rejected before we
touch its content.
"""

from __future__ import annotations

import hashlib
import hmac

SIGNATURE_HEADER = "X-Hub-Signature-256"
SIGNATURE_PREFIX = "sha256="


class InvalidSignatureError(Exception):
    """Raised when a webhook payload's signature doesn't verify."""


def compute_signature(secret: str, body: bytes) -> str:
    """Compute the expected signature header value for a given body.

    Mostly useful for tests and for signing outbound payloads.
    """
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{digest}"


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> None:
    """Raise InvalidSignatureError unless the signature header matches the body.

    The signature header should be the exact value of ``X-Hub-Signature-256``,
    e.g. ``"sha256=abcd..."``.
    """
    if not signature_header:
        raise InvalidSignatureError("Missing signature header")

    if not signature_header.startswith(SIGNATURE_PREFIX):
        raise InvalidSignatureError("Signature header has wrong prefix")

    expected = compute_signature(secret, body)
    if not hmac.compare_digest(expected, signature_header):
        raise InvalidSignatureError("Signature does not match payload")

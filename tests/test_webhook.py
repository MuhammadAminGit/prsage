"""Webhook endpoint tests."""

import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.webhooks.signature import compute_signature

client = TestClient(app)


@pytest.fixture(autouse=True)
def stable_secret(monkeypatch):
    """Force a known webhook secret so tests don't depend on the .env file."""
    secret = "test-secret"
    monkeypatch.setenv("GITHUB_APP_WEBHOOK_SECRET", secret)
    get_settings.cache_clear()
    yield secret
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def stub_run_review(monkeypatch):
    """Replace the real review runner with a no-op so the webhook test
    doesn't try to hit GitHub or the database in the background task."""

    async def _noop(**kwargs):
        return None

    monkeypatch.setattr("app.webhooks.github.run_review", _noop)
    yield


def _post(body: bytes, secret: str, event: str, sign: bool = True):
    headers = {
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": "test-delivery",
    }
    if sign:
        headers["X-Hub-Signature-256"] = compute_signature(secret, body)
    return client.post("/webhooks/github", content=body, headers=headers)


def test_rejects_unsigned_request(stable_secret):
    body = b'{"action":"opened"}'
    r = _post(body, stable_secret, "pull_request", sign=False)
    assert r.status_code == 401


def test_rejects_bad_signature(stable_secret):
    body = b'{"action":"opened"}'
    r = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=" + "0" * 64,
        },
    )
    assert r.status_code == 401


def test_ping_event_returns_pong(stable_secret):
    body = b'{"zen":"hello"}'
    r = _post(body, stable_secret, "ping")
    assert r.status_code == 202
    assert r.json() == {"status": "pong"}


def test_pull_request_opened_is_queued(stable_secret):
    body = json.dumps({
        "action": "opened",
        "pull_request": {"number": 5},
        "repository": {"full_name": "amin/demo"},
        "installation": {"id": 1},
    }).encode()
    r = _post(body, stable_secret, "pull_request")
    assert r.status_code == 202
    assert r.json() == {"status": "queued"}


def test_pull_request_closed_is_ignored(stable_secret):
    body = json.dumps({
        "action": "closed",
        "pull_request": {"number": 5},
        "repository": {"full_name": "amin/demo"},
    }).encode()
    r = _post(body, stable_secret, "pull_request")
    assert r.status_code == 202
    assert r.json() == {"status": "ignored"}


def test_unknown_event_is_ignored(stable_secret):
    body = b'{"foo":"bar"}'
    r = _post(body, stable_secret, "issues")
    assert r.status_code == 202
    assert r.json() == {"status": "ignored"}


def test_invalid_json_is_400(stable_secret):
    body = b"this is not json"
    r = _post(body, stable_secret, "pull_request")
    assert r.status_code == 400

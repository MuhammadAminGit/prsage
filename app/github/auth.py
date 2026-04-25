"""GitHub App authentication.

Two layers:
- The App JWT: short-lived (10 min max) RS256 token signed with our private key.
  Used to identify the app itself to the GitHub API.
- The installation access token: bearer token tied to a specific installation
  (i.e. a repo or org that installed the app). Used for almost every real call.

We cache the App JWT for ~9 minutes so we don't regenerate it on every webhook.
Installation tokens are fetched per-installation and cached separately.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import jwt

GITHUB_API_BASE = "https://api.github.com"

# GitHub allows max 10 minutes; we use 9 to leave clock-skew margin.
JWT_LIFETIME_SECONDS = 9 * 60
# Refresh slightly before expiry.
JWT_REFRESH_MARGIN_SECONDS = 60


@dataclass
class _CachedJWT:
    token: str
    expires_at: float

    def is_fresh(self, now: float) -> bool:
        return now < self.expires_at - JWT_REFRESH_MARGIN_SECONDS


_jwt_cache: _CachedJWT | None = None


def _read_private_key(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"GitHub App private key not found at {path}")
    return path.read_text()


def generate_app_jwt(app_id: str, private_key_path: Path, now: float | None = None) -> str:
    """Generate (or return a cached) App-level JWT.

    The JWT identifies the GitHub App itself, not any specific installation.
    Use it to fetch installation access tokens, list installations, etc.
    """
    global _jwt_cache

    now = now if now is not None else time.time()

    if _jwt_cache is not None and _jwt_cache.is_fresh(now):
        return _jwt_cache.token

    private_key = _read_private_key(private_key_path)
    payload = {
        "iat": int(now) - 30,  # back-dated 30s for clock skew
        "exp": int(now) + JWT_LIFETIME_SECONDS,
        "iss": str(app_id),
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")
    _jwt_cache = _CachedJWT(token=token, expires_at=now + JWT_LIFETIME_SECONDS)
    return token


def reset_jwt_cache() -> None:
    """Drop the cached App JWT. Useful in tests."""
    global _jwt_cache
    _jwt_cache = None


# ---------------------------------------------------------------------------
# Installation access tokens
# ---------------------------------------------------------------------------

# Installation tokens last ~1 hour; refresh a couple minutes early.
INSTALLATION_TOKEN_REFRESH_MARGIN_SECONDS = 120


@dataclass
class InstallationToken:
    token: str
    expires_at: float

    def is_fresh(self, now: float) -> bool:
        return now < self.expires_at - INSTALLATION_TOKEN_REFRESH_MARGIN_SECONDS


_installation_token_cache: dict[int, InstallationToken] = {}


async def get_installation_token(
    installation_id: int,
    app_id: str,
    private_key_path: Path,
    *,
    client: httpx.AsyncClient | None = None,
    now: float | None = None,
) -> str:
    """Fetch (or return a cached) installation access token.

    Tokens are scoped to a single installation. They expire after about an hour
    and are cached in-process.
    """
    now = now if now is not None else time.time()
    cached = _installation_token_cache.get(installation_id)
    if cached and cached.is_fresh(now):
        return cached.token

    app_jwt = generate_app_jwt(app_id, private_key_path, now=now)
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"

    if client is None:
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.post(url, headers=headers)
    else:
        resp = await client.post(url, headers=headers)

    resp.raise_for_status()
    body = resp.json()

    expires_at_iso = body["expires_at"]  # e.g. "2026-04-25T16:30:00Z"
    expires_at = datetime.fromisoformat(expires_at_iso.replace("Z", "+00:00")).timestamp()

    token = InstallationToken(token=body["token"], expires_at=expires_at)
    _installation_token_cache[installation_id] = token
    return token.token


def reset_installation_token_cache() -> None:
    """Drop all cached installation tokens. Useful in tests."""
    _installation_token_cache.clear()

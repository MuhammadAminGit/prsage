"""Thin async client for the GitHub REST API.

Scoped to what prsage needs: read PR metadata, fetch the changed files (with
patches), and post review comments. Authentication is handled per-installation
through ``app.github.auth.get_installation_token``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.github.auth import GITHUB_API_BASE, get_installation_token

DEFAULT_TIMEOUT = 15.0


@dataclass
class PRFile:
    """A single file changed in a PR, plus its patch (unified diff hunks)."""

    filename: str
    status: str  # added, modified, removed, renamed
    additions: int
    deletions: int
    changes: int
    patch: str | None  # may be None for binary or very large files
    sha: str  # blob sha at the head commit


@dataclass
class PullRequest:
    number: int
    title: str
    body: str
    head_sha: str
    base_sha: str
    repo_full_name: str
    user_login: str
    html_url: str
    draft: bool


class GitHubClient:
    """Async GitHub API client scoped to a single App installation."""

    def __init__(
        self,
        installation_id: int,
        app_id: str,
        private_key_path: Path,
        *,
        client: httpx.AsyncClient | None = None,
    ):
        self.installation_id = installation_id
        self.app_id = app_id
        self.private_key_path = private_key_path
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "GitHubClient":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _headers(self, *, accept: str = "application/vnd.github+json") -> dict[str, str]:
        token = await get_installation_token(
            self.installation_id,
            self.app_id,
            self.private_key_path,
            client=self._client,
        )
        return {
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _get(self, path: str, *, accept: str = "application/vnd.github+json") -> Any:
        assert self._client is not None
        headers = await self._headers(accept=accept)
        resp = await self._client.get(f"{GITHUB_API_BASE}{path}", headers=headers)
        resp.raise_for_status()
        return resp.json() if accept.endswith("+json") else resp.text

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        assert self._client is not None
        headers = await self._headers()
        resp = await self._client.post(
            f"{GITHUB_API_BASE}{path}", headers=headers, json=body
        )
        resp.raise_for_status()
        return resp.json()

    # -- PR metadata --------------------------------------------------------

    async def get_pull_request(self, repo_full_name: str, pr_number: int) -> PullRequest:
        data = await self._get(f"/repos/{repo_full_name}/pulls/{pr_number}")
        return PullRequest(
            number=data["number"],
            title=data["title"],
            body=data.get("body") or "",
            head_sha=data["head"]["sha"],
            base_sha=data["base"]["sha"],
            repo_full_name=repo_full_name,
            user_login=data["user"]["login"],
            html_url=data["html_url"],
            draft=data.get("draft", False),
        )

    async def get_pull_request_files(
        self, repo_full_name: str, pr_number: int
    ) -> list[PRFile]:
        """Return the list of files in the PR with their patch hunks.

        Pagination: GitHub returns up to 30 files per page by default. For MVP
        we cap at one page (300 files max with per_page=300) which covers most
        real PRs.
        """
        data = await self._get(
            f"/repos/{repo_full_name}/pulls/{pr_number}/files?per_page=300"
        )
        return [
            PRFile(
                filename=f["filename"],
                status=f["status"],
                additions=f["additions"],
                deletions=f["deletions"],
                changes=f["changes"],
                patch=f.get("patch"),
                sha=f["sha"],
            )
            for f in data
        ]

    # -- Posting reviews ----------------------------------------------------

    async def post_review_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        *,
        commit_sha: str,
        path: str,
        line: int,
        side: str,
        body: str,
    ) -> Any:
        """Post a single inline review comment.

        ``side`` is ``"RIGHT"`` for added lines, ``"LEFT"`` for removed lines.
        """
        return await self._post(
            f"/repos/{repo_full_name}/pulls/{pr_number}/comments",
            {
                "commit_id": commit_sha,
                "path": path,
                "line": line,
                "side": side,
                "body": body,
            },
        )

    async def post_review(
        self,
        repo_full_name: str,
        pr_number: int,
        *,
        commit_sha: str,
        body: str,
        comments: list[dict[str, Any]],
        event: str = "COMMENT",
    ) -> Any:
        """Submit a full review with multiple inline comments at once.

        Each comment dict needs at minimum ``path``, ``line``, ``side``, ``body``.
        ``event`` is one of ``COMMENT``, ``APPROVE``, ``REQUEST_CHANGES``. We
        always use ``COMMENT`` so prsage never blocks a merge.
        """
        return await self._post(
            f"/repos/{repo_full_name}/pulls/{pr_number}/reviews",
            {
                "commit_id": commit_sha,
                "body": body,
                "event": event,
                "comments": comments,
            },
        )

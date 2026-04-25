"""Plain data types returned by the GitHub client.

Kept separate from ``client.py`` so other modules (the reviewer, persistence
layer, tests) can import them without pulling in the HTTP client.
"""

from __future__ import annotations

from dataclasses import dataclass


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
    """Pull request metadata we care about for review."""

    number: int
    title: str
    body: str
    head_sha: str
    base_sha: str
    repo_full_name: str
    user_login: str
    html_url: str
    draft: bool

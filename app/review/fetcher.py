"""Fetch the data we need to review a PR.

This module is the bridge between the webhook and the review pipeline. Given
an installation and a PR, it returns the metadata + file diffs in the shape
the reviewer expects, plus light filtering of files we won't review.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.github.client import GitHubClient, PRFile, PullRequest

# Files we skip outright; reviewing these usually wastes tokens.
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg",
    ".pdf", ".mp3", ".mp4", ".wav",
    ".lock",  # package-lock.json, poetry.lock, etc.
    ".min.js", ".min.css",
    ".woff", ".woff2", ".ttf", ".otf",
}

SKIP_FILES = {
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "Pipfile.lock",
    "pnpm-lock.yaml",
    "uv.lock",
    "Cargo.lock",
    "composer.lock",
    "Gemfile.lock",
    "go.sum",
}

# Don't bother sending files larger than this to the LLM.
MAX_PATCH_BYTES = 30_000


@dataclass
class ReviewablePR:
    pr: PullRequest
    files: list[PRFile]
    skipped: list[tuple[str, str]]  # (filename, reason)


def _should_skip(file: PRFile) -> str | None:
    if file.status == "removed":
        return "file removed"
    if file.patch is None:
        return "binary or too large"
    if file.filename in SKIP_FILES:
        return "lockfile or generated"
    for ext in SKIP_EXTENSIONS:
        if file.filename.endswith(ext):
            return f"skipped extension {ext}"
    if len(file.patch.encode("utf-8")) > MAX_PATCH_BYTES:
        return f"patch over {MAX_PATCH_BYTES} bytes"
    return None


async def fetch_reviewable_pr(
    *,
    installation_id: int,
    app_id: str,
    private_key_path: Path,
    repo_full_name: str,
    pr_number: int,
) -> ReviewablePR:
    """Pull the PR + its files, filter out non-reviewable files, return both."""
    async with GitHubClient(
        installation_id=installation_id,
        app_id=app_id,
        private_key_path=private_key_path,
    ) as gh:
        pr = await gh.get_pull_request(repo_full_name, pr_number)
        files = await gh.get_pull_request_files(repo_full_name, pr_number)

    keep: list[PRFile] = []
    skipped: list[tuple[str, str]] = []
    for f in files:
        reason = _should_skip(f)
        if reason:
            skipped.append((f.filename, reason))
        else:
            keep.append(f)

    return ReviewablePR(pr=pr, files=keep, skipped=skipped)

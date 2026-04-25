"""Top-level review runner.

This is the function the webhook hands off to. It does the full loop:

1. Fetch the PR + reviewable files via the GitHub client.
2. Run the reviewer (LLM call, parsing, filtering).
3. Post the resulting comments back to the PR as a single review.

It's safe to call in the background. All errors are logged with enough
context to diagnose, and we never raise into the caller.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.db import SessionLocal
from app.github.client import GitHubClient
from app.llm.groq_client import GroqClient
from app.models import Review, ReviewComment
from app.review.fetcher import fetch_reviewable_pr
from app.review.output import ReviewResult
from app.review.reviewer import review_pr

log = logging.getLogger("prsage.runner")

SEVERITY_PREFIX = {
    "critical": "🛑 **critical**",
    "warning": "⚠️ **warning**",
    "info": "💡 **info**",
}


def _format_comment_body(severity: str, body: str) -> str:
    prefix = SEVERITY_PREFIX.get(severity, "")
    return f"{prefix}\n\n{body}" if prefix else body


def _format_review_summary(result: ReviewResult) -> str:
    if not result.comments:
        return result.summary or "prsage looked at this PR and didn't see anything to flag."
    counts: dict[str, int] = {}
    for c in result.comments:
        counts[c.severity] = counts.get(c.severity, 0) + 1
    parts = [f"{n} {sev}" for sev, n in counts.items()]
    base = result.summary or ""
    tail = f"\n\n_Found: {', '.join(parts)}._"
    return (base + tail).strip()


async def _record_review(
    *,
    installation_id: int,
    repo_full_name: str,
    pr_number: int,
) -> int:
    """Insert a queued Review row and return its id."""
    async with SessionLocal() as session:
        review = Review(
            installation_id=installation_id,
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            status="running",
        )
        session.add(review)
        await session.commit()
        await session.refresh(review)
        return review.id


async def _finalize_review(
    review_id: int,
    *,
    status: str,
    pr_title: str = "",
    pr_url: str = "",
    model: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    duration_ms: int = 0,
    summary: str = "",
    error: str | None = None,
    comments: list[ReviewComment] | None = None,
) -> None:
    async with SessionLocal() as session:
        review = await session.get(Review, review_id)
        if review is None:
            return
        review.status = status
        review.pr_title = pr_title
        review.pr_url = pr_url
        review.model = model
        review.prompt_tokens = prompt_tokens
        review.completion_tokens = completion_tokens
        review.total_tokens = total_tokens
        review.duration_ms = duration_ms
        review.summary = summary
        review.error = error
        review.completed_at = datetime.now(timezone.utc)
        if comments:
            for c in comments:
                c.review_id = review_id
                session.add(c)
        await session.commit()


async def run_review(
    *,
    installation_id: int,
    repo_full_name: str,
    pr_number: int,
) -> None:
    """Run a full review pass for a single PR and post the result to GitHub.

    Errors are logged but never re-raised. The webhook caller has already
    returned 202 by the time this runs. Every attempt is persisted: a
    ``Review`` row is created up front and updated with the outcome.
    """
    settings = get_settings()
    review_id = await _record_review(
        installation_id=installation_id,
        repo_full_name=repo_full_name,
        pr_number=pr_number,
    )

    try:
        reviewable = await fetch_reviewable_pr(
            installation_id=installation_id,
            app_id=settings.github_app_id,
            private_key_path=Path(settings.github_app_private_key_path),
            repo_full_name=repo_full_name,
            pr_number=pr_number,
        )
    except Exception as e:
        log.exception("fetch failed for %s#%d: %s", repo_full_name, pr_number, e)
        await _finalize_review(review_id, status="failed", error=f"fetch: {e}")
        return

    if reviewable.pr.draft:
        log.info("skipping draft PR %s#%d", repo_full_name, pr_number)
        await _finalize_review(
            review_id,
            status="skipped",
            pr_title=reviewable.pr.title,
            pr_url=reviewable.pr.html_url,
            summary="Draft PR; not reviewed.",
        )
        return

    try:
        async with GroqClient(api_key=settings.groq_api_key, model=settings.groq_model) as g:
            run = await review_pr(reviewable, g)
    except Exception as e:
        log.exception("review failed for %s#%d: %s", repo_full_name, pr_number, e)
        await _finalize_review(
            review_id,
            status="failed",
            pr_title=reviewable.pr.title,
            pr_url=reviewable.pr.html_url,
            error=f"review: {e}",
        )
        return

    result = run.result

    if not result.comments and not result.summary:
        log.info("nothing to post for %s#%d", repo_full_name, pr_number)
        await _finalize_review(
            review_id,
            status="posted",
            pr_title=reviewable.pr.title,
            pr_url=reviewable.pr.html_url,
            model=run.model,
            prompt_tokens=run.prompt_tokens,
            completion_tokens=run.completion_tokens,
            total_tokens=run.total_tokens,
            duration_ms=run.duration_ms,
            summary="",
        )
        return

    review_body = _format_review_summary(result)
    comments_payload = [
        {
            "path": c.file,
            "line": c.line,
            "side": "RIGHT",
            "body": _format_comment_body(c.severity, c.body),
        }
        for c in result.comments
    ]
    db_comments = [
        ReviewComment(
            file_path=c.file,
            line_number=c.line,
            severity=c.severity,
            body=c.body,
        )
        for c in result.comments
    ]

    try:
        async with GitHubClient(
            installation_id=installation_id,
            app_id=settings.github_app_id,
            private_key_path=Path(settings.github_app_private_key_path),
        ) as gh:
            await gh.post_review(
                repo_full_name,
                pr_number,
                commit_sha=reviewable.pr.head_sha,
                body=review_body,
                comments=comments_payload,
            )
    except Exception as e:
        log.exception("post failed for %s#%d: %s", repo_full_name, pr_number, e)
        await _finalize_review(
            review_id,
            status="failed",
            pr_title=reviewable.pr.title,
            pr_url=reviewable.pr.html_url,
            model=run.model,
            prompt_tokens=run.prompt_tokens,
            completion_tokens=run.completion_tokens,
            total_tokens=run.total_tokens,
            duration_ms=run.duration_ms,
            summary=result.summary,
            error=f"post: {e}",
        )
        return

    posted_at = datetime.now(timezone.utc)
    for c in db_comments:
        c.posted_at = posted_at

    await _finalize_review(
        review_id,
        status="posted",
        pr_title=reviewable.pr.title,
        pr_url=reviewable.pr.html_url,
        model=run.model,
        prompt_tokens=run.prompt_tokens,
        completion_tokens=run.completion_tokens,
        total_tokens=run.total_tokens,
        duration_ms=run.duration_ms,
        summary=result.summary,
        comments=db_comments,
    )

    log.info(
        "posted review pr=%s#%d comments=%d tokens=%d duration_ms=%d",
        repo_full_name,
        pr_number,
        len(result.comments),
        run.total_tokens,
        run.duration_ms,
    )

"""Orchestrates a single review: PR data + prompt + LLM + parsing + filter.

The high-level function is ``review_pr``. Given a ``ReviewablePR`` and a
configured ``GroqClient``, it returns a clean ``ReviewResult`` with comments
that are safe to post (each line has been verified to be a real added line
in the PR).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.llm.groq_client import ChatMessage, GroqClient
from app.review.fetcher import ReviewablePR
from app.review.output import (
    ReviewParseError,
    ReviewResult,
    filter_to_reviewable_lines,
    parse_llm_output,
)
from app.review.prompts import build_system_prompt, build_user_prompt

log = logging.getLogger("prsage.review")


@dataclass
class ReviewRun:
    """Everything we want to record about a single review pass."""

    result: ReviewResult
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    duration_ms: int


async def review_pr(reviewable: ReviewablePR, groq: GroqClient) -> ReviewRun:
    """Run an LLM review pass on a fetched PR.

    Note: this does not post anything to GitHub. The caller decides what to
    do with the result (post a review, store it, log it).
    """
    start = time.monotonic()

    if not reviewable.files:
        log.info(
            "no reviewable files for pr=%s/%s, skipping LLM call",
            reviewable.pr.repo_full_name,
            reviewable.pr.number,
        )
        return ReviewRun(
            result=ReviewResult(summary="No reviewable changes.", comments=[]),
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            model=groq.model,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    user_prompt = build_user_prompt(reviewable.pr, reviewable.files)
    messages = [
        ChatMessage(role="system", content=build_system_prompt()),
        ChatMessage(role="user", content=user_prompt),
    ]

    completion = await groq.chat(messages, json_object=True, temperature=0.2)
    try:
        parsed = parse_llm_output(completion.content)
    except ReviewParseError as e:
        log.warning(
            "could not parse LLM output for pr=%s/%s: %s",
            reviewable.pr.repo_full_name,
            reviewable.pr.number,
            e,
        )
        parsed = ReviewResult(summary="", comments=[])
    filtered = filter_to_reviewable_lines(parsed, reviewable.files)

    duration_ms = int((time.monotonic() - start) * 1000)
    log.info(
        "review pr=%s/%s comments=%d/%d tokens=%d duration_ms=%d",
        reviewable.pr.repo_full_name,
        reviewable.pr.number,
        len(filtered.comments),
        len(parsed.comments),
        completion.total_tokens,
        duration_ms,
    )

    return ReviewRun(
        result=filtered,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        total_tokens=completion.total_tokens,
        model=completion.model,
        duration_ms=duration_ms,
    )

"""End-to-end reviewer test with a stubbed LLM."""

import json
from dataclasses import dataclass

import pytest

from app.github.types import PRFile, PullRequest
from app.llm.groq_client import ChatCompletion, GroqClient
from app.review.fetcher import ReviewablePR
from app.review.reviewer import review_pr


@dataclass
class StubGroq:
    """Stand-in for GroqClient that returns a canned response."""

    response_content: str
    model: str = "stub-model"
    last_messages: list = None  # type: ignore[assignment]

    async def chat(self, messages, *, json_object=False, temperature=0.2, max_tokens=None):
        self.last_messages = messages
        return ChatCompletion(
            content=self.response_content,
            model=self.model,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )


def _make_reviewable(patch: str = "@@ -1,1 +1,2 @@\n existing\n+added line\n") -> ReviewablePR:
    pr = PullRequest(
        number=1,
        title="Test PR",
        body="A test pull request.",
        head_sha="abc123",
        base_sha="def456",
        repo_full_name="amin/test",
        user_login="amin",
        html_url="https://github.com/amin/test/pull/1",
        draft=False,
    )
    files = [PRFile("app/main.py", "modified", 1, 0, 1, patch, "sha1")]
    return ReviewablePR(pr=pr, files=files, skipped=[])


@pytest.mark.asyncio
async def test_review_pr_returns_filtered_comments():
    reviewable = _make_reviewable()
    canned = json.dumps({
        "summary": "One issue found.",
        "comments": [
            {"file": "app/main.py", "line": 2, "severity": "warning", "body": "Use a clearer name."},
            # This one points at a context line and should be filtered out:
            {"file": "app/main.py", "line": 1, "severity": "info", "body": "Existing code."},
            # This file doesn't exist; should be filtered out:
            {"file": "fake.py", "line": 1, "severity": "info", "body": "Fake."},
        ],
    })
    stub = StubGroq(response_content=canned)
    run = await review_pr(reviewable, stub)  # type: ignore[arg-type]

    assert run.result.summary == "One issue found."
    assert len(run.result.comments) == 1
    assert run.result.comments[0].file == "app/main.py"
    assert run.result.comments[0].line == 2
    assert run.result.comments[0].severity == "warning"


@pytest.mark.asyncio
async def test_review_pr_with_no_files_skips_llm():
    pr = PullRequest(
        number=1, title="t", body="", head_sha="a", base_sha="b",
        repo_full_name="amin/test", user_login="amin", html_url="", draft=False,
    )
    reviewable = ReviewablePR(pr=pr, files=[], skipped=[])
    stub = StubGroq(response_content='{"summary":"","comments":[]}')
    run = await review_pr(reviewable, stub)  # type: ignore[arg-type]

    assert run.total_tokens == 0
    assert stub.last_messages is None  # never called


@pytest.mark.asyncio
async def test_review_pr_handles_empty_review():
    reviewable = _make_reviewable()
    canned = json.dumps({"summary": "", "comments": []})
    stub = StubGroq(response_content=canned)
    run = await review_pr(reviewable, stub)  # type: ignore[arg-type]

    assert run.result.summary == ""
    assert run.result.comments == []
    assert run.total_tokens == 150

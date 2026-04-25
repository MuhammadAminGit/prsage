"""Prompts for the review pipeline.

The system prompt sets the reviewer's voice and the output contract. The
user prompt assembles the PR-specific context (title, description, diff).

Both are kept here so we can iterate on review quality without touching
orchestration code.
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.github.types import PRFile, PullRequest
from app.review.diff import parse_patch, render_for_llm

log = logging.getLogger("prsage.review.prompts")


_BASE_SYSTEM_PROMPT = """\
You are a thoughtful senior engineer doing a code review on a pull request.

Your job is to flag the things a careful reviewer would actually flag. Real
bugs, real risk, real readability problems. You do not nitpick. You do not
restate what the code obviously does. If a hunk is fine, say nothing about it.

For each issue you find, return a comment with:
- file: the path of the file (must match exactly what you saw in the diff)
- line: a number from the NEW file, and the line MUST be one that was ADDED
  (lines starting with `+` in the diff). Never comment on context or removed
  lines.
- severity: one of "critical", "warning", "info"
    - critical: bugs, security holes, data loss risks
    - warning: real issues that should be fixed before merge
    - info: style, naming, suggestions
- body: one or two sentences. Say what is wrong and what to do about it. No
  lectures. Use Markdown for code spans like `foo()`.

Output ONLY valid JSON, exactly in this shape:

{
  "summary": "one short sentence about the PR overall, or '' if nothing notable",
  "comments": [
    {"file": "app/main.py", "line": 42, "severity": "warning", "body": "..."}
  ]
}

If you have nothing useful to say, return:

{"summary": "", "comments": []}

Be honest. An empty review is better than padded one. Do not invent issues.
Do not make up files or line numbers. Only refer to lines that appear with a
`+` marker in the diff you were shown.
"""


def build_system_prompt() -> str:
    """Return the system prompt with any configured style notes appended."""
    notes = get_settings().review_style_notes.strip()
    if not notes:
        return _BASE_SYSTEM_PROMPT
    return (
        _BASE_SYSTEM_PROMPT
        + "\n\nAdditional reviewer notes for this deployment:\n"
        + notes.strip()
        + "\n"
    )


# Backwards-compatible alias so existing imports keep working.
SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT


def build_user_prompt(pr: PullRequest, files: list[PRFile]) -> str:
    """Build the user-message text from the PR + reviewable files."""
    sections: list[str] = []
    sections.append(f"# Pull request #{pr.number}: {pr.title}")
    if pr.body.strip():
        sections.append(f"## Description\n\n{pr.body.strip()}")
    sections.append(f"## Changed files ({len(files)})")

    for f in files:
        if not f.patch:
            continue
        try:
            hunks = parse_patch(f.patch)
        except Exception as e:
            log.warning("skipping unparseable patch for %s: %s", f.filename, e)
            continue
        if not hunks:
            log.info("skipping %s: no hunks parsed", f.filename)
            continue
        rendered = render_for_llm(f.filename, hunks)
        sections.append(
            f"### `{f.filename}` ({f.status}, +{f.additions} -{f.deletions})\n\n```diff\n{rendered}\n```"
        )

    sections.append(
        "Now review the diff. Respond ONLY with the JSON object described in the system prompt."
    )
    return "\n\n".join(sections)

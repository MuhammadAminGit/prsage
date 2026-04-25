"""Parse and validate the LLM's review output.

The LLM is asked to return strict JSON. In practice it sometimes wraps the
JSON in markdown fences, adds a preamble, or hallucinates files / line
numbers that aren't actually in the diff. We:

1. Strip noise around the JSON
2. Parse what's left
3. Drop any comment that doesn't refer to a line that was actually added
4. Normalize severity strings
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal

from app.github.types import PRFile
from app.review.diff import added_line_numbers, parse_patch

log = logging.getLogger("prsage.review.output")

Severity = Literal["critical", "warning", "info"]
ALLOWED_SEVERITIES: set[str] = {"critical", "warning", "info"}


@dataclass
class ReviewComment:
    file: str
    line: int
    severity: Severity
    body: str


@dataclass
class ReviewResult:
    summary: str
    comments: list[ReviewComment]


class ReviewParseError(Exception):
    """Raised when the LLM output can't be parsed as a review at all."""


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = _FENCE_RE.match(text)
    return m.group(1).strip() if m else text


def _extract_json_object(text: str) -> str:
    """Find the outermost balanced ``{...}`` substring."""
    start = text.find("{")
    if start == -1:
        raise ReviewParseError("No JSON object found in LLM output")
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ReviewParseError("Unbalanced JSON braces in LLM output")


def parse_llm_output(text: str) -> ReviewResult:
    """Parse the LLM's raw text response into a ReviewResult.

    Tolerates markdown fences and trailing prose around the JSON.
    """
    cleaned = _strip_fences(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Last-resort: try to extract a JSON object from the text.
        data = json.loads(_extract_json_object(cleaned))

    if not isinstance(data, dict):
        raise ReviewParseError("LLM output is not a JSON object")

    summary = str(data.get("summary", "") or "").strip()
    raw_comments = data.get("comments") or []
    if not isinstance(raw_comments, list):
        raise ReviewParseError("'comments' is not a list")

    comments: list[ReviewComment] = []
    for c in raw_comments:
        if not isinstance(c, dict):
            continue
        file = str(c.get("file", "")).strip()
        line = c.get("line")
        body = str(c.get("body", "")).strip()
        severity = str(c.get("severity", "info")).strip().lower()

        if not file or not body or not isinstance(line, int):
            continue
        if severity not in ALLOWED_SEVERITIES:
            severity = "info"

        comments.append(
            ReviewComment(file=file, line=line, severity=severity, body=body)  # type: ignore[arg-type]
        )

    return ReviewResult(summary=summary, comments=comments)


def filter_to_reviewable_lines(
    result: ReviewResult, files: list[PRFile]
) -> ReviewResult:
    """Drop comments that don't point at a line that was actually added.

    Helps catch cases where the LLM hallucinates files or line numbers.
    """
    added_by_file: dict[str, set[int]] = {}
    for f in files:
        if not f.patch:
            continue
        added_by_file[f.filename] = added_line_numbers(parse_patch(f.patch))

    kept: list[ReviewComment] = []
    dropped = 0
    for c in result.comments:
        added = added_by_file.get(c.file)
        if added is None or c.line not in added:
            dropped += 1
            log.info("dropped comment file=%s line=%s (not a reviewable added line)", c.file, c.line)
            continue
        kept.append(c)

    return ReviewResult(summary=result.summary, comments=kept)

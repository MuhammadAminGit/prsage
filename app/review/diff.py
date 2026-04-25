"""Parse GitHub's unified diff patches into structured hunks with line numbers.

GitHub returns each changed file's patch as a ``patch`` string in the
``GET /pulls/{n}/files`` response. The format looks like:

    @@ -10,7 +10,8 @@ def hello():
         print("hello")
    -    print("old")
    +    print("new")
    +    return None

We need to know, per line:

- whether it was added, removed, or context
- its line number in the OLD file (for removed/context lines)
- its line number in the NEW file (for added/context lines)

This is required so the LLM can refer to specific lines and we can post
inline comments at the right ``line + side``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

LineKind = Literal["add", "remove", "context"]

HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?P<context>.*)$"
)


@dataclass
class DiffLine:
    kind: LineKind
    content: str
    old_lineno: int | None
    new_lineno: int | None


@dataclass
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header_context: str
    lines: list[DiffLine] = field(default_factory=list)


def parse_patch(patch: str) -> list[DiffHunk]:
    """Parse a unified diff patch into a list of hunks with line numbers."""
    hunks: list[DiffHunk] = []
    current: DiffHunk | None = None
    old_lineno = 0
    new_lineno = 0

    for raw_line in patch.splitlines():
        header = HUNK_HEADER_RE.match(raw_line)
        if header:
            old_start = int(header["old_start"])
            old_count = int(header["old_count"] or 1)
            new_start = int(header["new_start"])
            new_count = int(header["new_count"] or 1)
            current = DiffHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                header_context=header["context"].strip(),
            )
            hunks.append(current)
            old_lineno = old_start
            new_lineno = new_start
            continue

        if current is None:
            # Lines outside any hunk header (e.g. ``\ No newline at end of file``).
            continue

        if not raw_line:
            # Empty lines inside hunks are unusual; treat as context.
            current.lines.append(
                DiffLine(
                    kind="context",
                    content="",
                    old_lineno=old_lineno,
                    new_lineno=new_lineno,
                )
            )
            old_lineno += 1
            new_lineno += 1
            continue

        marker, content = raw_line[0], raw_line[1:]

        if marker == "+":
            current.lines.append(
                DiffLine(kind="add", content=content, old_lineno=None, new_lineno=new_lineno)
            )
            new_lineno += 1
        elif marker == "-":
            current.lines.append(
                DiffLine(kind="remove", content=content, old_lineno=old_lineno, new_lineno=None)
            )
            old_lineno += 1
        elif marker == " ":
            current.lines.append(
                DiffLine(
                    kind="context",
                    content=content,
                    old_lineno=old_lineno,
                    new_lineno=new_lineno,
                )
            )
            old_lineno += 1
            new_lineno += 1
        elif marker == "\\":
            # ``\ No newline at end of file`` — informational only.
            continue


    return hunks


def added_line_numbers(hunks: list[DiffHunk]) -> set[int]:
    """All line numbers in the NEW file that were added in this patch."""
    return {ln.new_lineno for h in hunks for ln in h.lines if ln.kind == "add" and ln.new_lineno}


def is_reviewable_line(hunks: list[DiffHunk], new_lineno: int) -> bool:
    """A line is safe to comment on inline iff it was added (RIGHT side) in the diff."""
    return new_lineno in added_line_numbers(hunks)


def render_for_llm(filename: str, hunks: list[DiffHunk]) -> str:
    """Render hunks as numbered text the LLM can reason about.

    Format:

        --- a/{filename}
        +++ b/{filename}
        @@ context @@
          12  context line
        + 13  added line
        - --  removed line

    The number column is always the NEW file line for context/added lines.
    Removed lines get ``--`` so the LLM doesn't try to comment on them.
    """
    out: list[str] = [f"--- a/{filename}", f"+++ b/{filename}"]
    for h in hunks:
        out.append(f"@@ {h.header_context} @@" if h.header_context else "@@")
        for ln in h.lines:
            if ln.kind == "add":
                out.append(f"+ {ln.new_lineno:>4}  {ln.content}")
            elif ln.kind == "remove":
                out.append(f"-   --  {ln.content}")
            else:
                out.append(f"  {ln.new_lineno:>4}  {ln.content}")
    return "\n".join(out)

"""Diff parser tests."""

from pathlib import Path

from app.review.diff import (
    added_line_numbers,
    is_reviewable_line,
    parse_patch,
    render_for_llm,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_patch.diff"


def test_parses_two_hunks():
    hunks = parse_patch(FIXTURE.read_text())
    assert len(hunks) == 2


def test_first_hunk_header_values():
    hunks = parse_patch(FIXTURE.read_text())
    h = hunks[0]
    assert h.old_start == 1 and h.old_count == 5
    assert h.new_start == 1 and h.new_count == 6


def test_second_hunk_header_includes_context():
    hunks = parse_patch(FIXTURE.read_text())
    h = hunks[1]
    assert h.old_start == 42 and h.old_count == 7
    assert h.new_start == 43 and h.new_count == 9
    assert "class Server" in h.header_context


def test_added_lines_have_new_lineno_only():
    hunks = parse_patch(FIXTURE.read_text())
    additions = [ln for h in hunks for ln in h.lines if ln.kind == "add"]
    assert all(ln.new_lineno is not None for ln in additions)
    assert all(ln.old_lineno is None for ln in additions)


def test_removed_lines_have_old_lineno_only():
    hunks = parse_patch(FIXTURE.read_text())
    removals = [ln for h in hunks for ln in h.lines if ln.kind == "remove"]
    assert all(ln.old_lineno is not None for ln in removals)
    assert all(ln.new_lineno is None for ln in removals)


def test_context_lines_have_both_linenos():
    hunks = parse_patch(FIXTURE.read_text())
    contexts = [ln for h in hunks for ln in h.lines if ln.kind == "context"]
    assert all(ln.old_lineno is not None and ln.new_lineno is not None for ln in contexts)


def test_added_line_numbers_match_expected():
    hunks = parse_patch(FIXTURE.read_text())
    # First hunk adds line 3 (`import logging`).
    # Second hunk adds 4 lines starting where the removed lines were.
    added = added_line_numbers(hunks)
    assert 3 in added  # `import logging`
    assert all(ln >= 1 for ln in added)
    assert len(added) == 5  # 1 from h1 + 4 from h2


def test_is_reviewable_line():
    hunks = parse_patch(FIXTURE.read_text())
    assert is_reviewable_line(hunks, 3) is True  # added line
    assert is_reviewable_line(hunks, 1) is False  # context line, not added


def test_count_omitted_means_one_line():
    """When ``,N`` is omitted in the header, the count defaults to 1."""
    hunks = parse_patch("@@ -10 +10 @@\n-old\n+new\n")
    assert len(hunks) == 1
    assert hunks[0].old_count == 1 and hunks[0].new_count == 1


def test_lines_outside_hunk_are_ignored():
    """Trailing ``\\ No newline at end of file`` markers should not break parsing."""
    patch = "@@ -1,1 +1,1 @@\n-old\n+new\n\\ No newline at end of file\n"
    hunks = parse_patch(patch)
    assert len(hunks) == 1
    assert len(hunks[0].lines) == 2


def test_render_for_llm_shows_line_numbers():
    hunks = parse_patch(FIXTURE.read_text())
    rendered = render_for_llm("app/server.py", hunks)
    assert "--- a/app/server.py" in rendered
    assert "+++ b/app/server.py" in rendered
    assert "import logging" in rendered
    # Removed lines should show `--` placeholder, not a real line number.
    for line in rendered.splitlines():
        if line.startswith("-"):
            assert "--" in line

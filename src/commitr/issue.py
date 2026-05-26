"""Pull issue/PR context from `gh` and the current git branch into the prompt.

Strategy:
    1. If the user passes --issue N, fetch issue N.
    2. Otherwise, look at the current branch name. If it matches a common
       pattern like `feat/123-foo`, `fix-issue-42-bar`, `refs/42`, etc., use
       the extracted number.
    3. Use the `gh` CLI to fetch — it handles auth, repo detection, and
       enterprise hosts for free. If `gh` is missing or fails, return None
       silently (this is an enhancement, never a blocker).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess


# Match an issue-looking number in branch patterns like `feat/123-foo`,
# `fix-42`, `issue/777`, `gh-42-bar`. Must be at a word boundary; we
# anchor with non-digit context to avoid grabbing version-y suffixes.
_BRANCH_ISSUE_RE = re.compile(
    r"(?:^|[/_-])"                # boundary
    r"(?:issue[-_]?|gh[-_]?|#)?"  # optional prefix word
    r"(\d{2,6})"                  # the number itself
    r"(?:$|[/_-])"
)


def detect_issue_from_branch(branch: str | None = None) -> int | None:
    """Extract an issue number from the current branch, or None."""
    if branch is None:
        branch = _current_branch()
    if not branch:
        return None
    match = _BRANCH_ISSUE_RE.search(branch)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def fetch_issue_context(issue_number: int) -> str | None:
    """Use `gh issue view` to render a compact context block, or None on failure.

    Output format (whitespace-stable for prompt-cache friendliness):

        Issue #42: Title here
        Labels: bug, p1
        Body:
        <first ~800 chars of body, stripped>
    """
    if not _gh_available():
        return None
    try:
        result = subprocess.run(
            [
                "gh", "issue", "view", str(issue_number),
                "--json", "number,title,body,labels,state",
            ],
            capture_output=True, text=True, check=False, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return _format_context(data)


def _format_context(data: dict) -> str:
    number = data.get("number", "?")
    title = (data.get("title") or "").strip()
    state = (data.get("state") or "").strip().lower()
    labels = data.get("labels") or []
    label_names = ", ".join(
        l.get("name", "") for l in labels if isinstance(l, dict) and l.get("name")
    )
    body = (data.get("body") or "").strip()
    if len(body) > 800:
        body = body[:800].rstrip() + "…"
    lines = [f"Issue #{number}: {title}"]
    if state and state != "open":
        lines.append(f"State: {state}")
    if label_names:
        lines.append(f"Labels: {label_names}")
    if body:
        lines.append("Body:")
        lines.append(body)
    return "\n".join(lines)


def _current_branch() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=False, timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch if branch and branch != "HEAD" else None


def _gh_available() -> bool:
    return shutil.which("gh") is not None

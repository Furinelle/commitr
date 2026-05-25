"""Thin wrappers around git subcommands."""
from __future__ import annotations

import subprocess


def _run(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout


def in_repo() -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def staged_diff() -> str:
    return _run(["diff", "--staged", "--no-color"])


def has_staged_changes() -> bool:
    result = subprocess.run(
        ["git", "diff", "--staged", "--quiet"],
        check=False,
    )
    return result.returncode != 0


def recent_commits(limit: int = 20) -> list[str]:
    """Recent commit subjects (one-liners), for broad style scanning."""
    try:
        out = _run(["log", f"-{limit}", "--pretty=format:%s"])
    except RuntimeError:
        return []
    return [line for line in out.splitlines() if line.strip()]


def recent_commit_samples(limit: int = 5) -> list[str]:
    """Recent full commit messages (subject + body) for few-shot style cues."""
    try:
        out = _run(["log", f"-{limit}", "--pretty=format:%s%n%b%x00"])
    except RuntimeError:
        return []
    return [c.strip() for c in out.split("\x00") if c.strip()]


def commit(message: str) -> str:
    return _run(["commit", "-m", message])

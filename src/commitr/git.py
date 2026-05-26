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


def staged_diff_for_llm() -> str:
    """Staged diff meant for prompt input.

    Keep this human-readable and relatively small. In particular, do not include
    binary patch payloads; the model only needs to know binary files changed.
    """
    return _run(["diff", "--staged", "--no-color"])


def staged_diff_for_patch() -> str:
    """Staged diff meant for exact index reconstruction."""
    return _run(["diff", "--staged", "--no-color", "--binary", "--full-index"])


def staged_diff() -> str:
    """Backward-compatible alias for the prompt-friendly staged diff."""
    return staged_diff_for_llm()


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


def staged_files() -> list[str]:
    """Files in the index (relative to repo root)."""
    out = _run(["diff", "--staged", "--name-only"])
    return [f for f in out.splitlines() if f.strip()]


def unstage_all() -> None:
    """Unstage every change (safe — does not touch the working tree)."""
    subprocess.run(["git", "reset", "--quiet"], check=False)


def stage_only(files: list[str]) -> None:
    """Reset the index, then stage exactly these files."""
    if not files:
        raise ValueError("stage_only requires at least one file")
    unstage_all()
    _run(["add", "--", *files])


def apply_patch_cached(patch_text: str) -> None:
    """Apply a unified patch to the index only (no worktree mutation).

    Used by hunk-level splitting: we unstage everything, then re-stage one
    group's hunks via `git apply --cached`. Raises RuntimeError on failure
    with git's stderr attached so the caller can recover (e.g. fall back to
    staging the whole file).
    """
    if not patch_text:
        raise ValueError("apply_patch_cached requires a non-empty patch")
    result = subprocess.run(
        ["git", "apply", "--cached", "--whitespace=nowarn", "-"],
        input=patch_text, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git apply --cached failed")


def current_branch() -> str | None:
    """Current branch name, or None on detached HEAD / non-repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch if branch and branch != "HEAD" else None

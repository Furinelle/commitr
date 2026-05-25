"""prepare-commit-msg hook installation and message-file filling."""
from __future__ import annotations

import subprocess
from pathlib import Path

HOOK_NAME = "prepare-commit-msg"

HOOK_SCRIPT = """#!/bin/sh
# commitr prepare-commit-msg hook — auto-fill commit message via AI.
# Skip when the user already provided a message, or for special commit types.
case "${2:-}" in
  message|template|merge|squash|commit)
    exit 0 ;;
esac
if command -v commitr >/dev/null 2>&1; then
  commitr hook-fill "$1" >/dev/null 2>&1 || true
fi
"""


def find_hooks_dir() -> Path:
    """Resolve the git hooks directory for the current repo (respects core.hooksPath)."""
    out = subprocess.run(
        ["git", "config", "core.hooksPath"],
        capture_output=True, text=True, check=False,
    )
    if out.returncode == 0 and out.stdout.strip():
        return Path(out.stdout.strip()).expanduser()
    out = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks"],
        capture_output=True, text=True, check=False,
    )
    if out.returncode == 0 and out.stdout.strip():
        return Path(out.stdout.strip())
    return Path(".git/hooks")


def install(force: bool = False) -> tuple[Path, bool]:
    """Install the prepare-commit-msg hook. Returns (path, overwrote_existing)."""
    hooks_dir = find_hooks_dir()
    hook_path = hooks_dir / HOOK_NAME
    overwrote = hook_path.exists()
    if overwrote and not force:
        raise FileExistsError(hook_path)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(HOOK_SCRIPT)
    hook_path.chmod(0o755)
    return hook_path, overwrote


def uninstall() -> Path | None:
    """Remove our hook. Returns the path removed, or None if absent.

    Refuses to delete if the file doesn't look like our hook (safety check).
    """
    hooks_dir = find_hooks_dir()
    hook_path = hooks_dir / HOOK_NAME
    if not hook_path.exists():
        return None
    content = hook_path.read_text()
    if "commitr hook-fill" not in content:
        raise RuntimeError(
            f"{hook_path} doesn't look like a commitr hook; refusing to delete."
        )
    hook_path.unlink()
    return hook_path


def fill_message_file(msg_file_path: str, generated: str) -> bool:
    """Write `generated` into the commit-msg file unless the user already
    wrote content there. Returns True if we wrote, False if we left it alone.
    """
    p = Path(msg_file_path)
    if not p.exists():
        return False
    existing = p.read_text()
    # Lines not starting with '#' (git's auto-comment marker) constitute
    # any pre-existing user input.
    user_lines = [ln for ln in existing.splitlines() if not ln.lstrip().startswith("#")]
    if "\n".join(user_lines).strip():
        return False
    new_content = (
        f"{generated}\n\n{existing}" if existing.strip() else f"{generated}\n"
    )
    p.write_text(new_content)
    return True

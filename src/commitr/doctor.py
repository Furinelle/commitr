"""Local health checks for staged changes before asking an LLM."""
from __future__ import annotations

from dataclasses import dataclass


LOCKFILE_NAMES = {
    "bun.lockb",
    "Cargo.lock",
    "composer.lock",
    "go.sum",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "yarn.lock",
}


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str


def analyze_staged_changes(
    diff: str,
    files: list[str],
    *,
    max_diff_chars: int = 12000,
    model_error: str | None = None,
) -> list[Finding]:
    """Return deterministic findings for the staged diff."""
    findings: list[Finding] = []
    if model_error:
        findings.append(Finding("error", "no_model", model_error))

    if not files:
        findings.append(
            Finding(
                "error",
                "no_staged_changes",
                "No staged changes found. Run `git add` before generating a commit.",
            )
        )
        return findings

    if len(diff) > max_diff_chars:
        findings.append(
            Finding(
                "warning",
                "large_diff",
                f"Staged diff is {len(diff)} characters; generation may omit details.",
            )
        )

    if "Binary files " in diff or "GIT binary patch" in diff:
        findings.append(
            Finding(
                "warning",
                "binary_diff",
                "Binary changes are staged; the model can only see file names, not content.",
            )
        )

    if files and all(_is_lockfile(path) for path in files):
        findings.append(
            Finding(
                "warning",
                "lockfile_only",
                "Only lockfiles are staged; consider pairing them with the dependency change.",
            )
        )

    return findings


def overall_status(findings: list[Finding]) -> str:
    if any(f.level == "error" for f in findings):
        return "error"
    if any(f.level == "warning" for f in findings):
        return "warning"
    return "ok"


def _is_lockfile(path: str) -> bool:
    return path.rsplit("/", 1)[-1] in LOCKFILE_NAMES

"""Generate a pull-request title and body from the diff against a base branch.

Reuses the same style-learning + LLM pipeline as `commitr` for commits — so
the PR description matches the project's existing PR voice (terse vs verbose,
English vs Chinese, bullet-listed vs prose).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass

import litellm

from commitr import cache
from commitr import prompt_safety


@dataclass(frozen=True)
class PullRequest:
    title: str
    body: str


SYSTEM_PROMPT = """You write pull-request descriptions for engineers.

Inputs you receive:
- A short list of recent merged PR titles from the same repo (style scan).
- The list of commits going into THIS PR.
- The full diff against the base branch.

Output strict JSON, no prose, no code fences:

{
  "title": "<one-line PR title>",
  "body": "<markdown body — sections only if relevant>"
}

Rules:
- Title: imperative, under 70 chars, match the casing/style of the sample titles.
- Body: at most three sections — Summary, Why, Test plan. Drop a section that
  isn't useful for this PR. Keep it tight; engineers skim PRs.
- Use the same NATURAL LANGUAGE as the sample titles (English / Chinese / etc).
- If the diff is trivial (typo fix, lockfile bump), the body can be one line.
- DO NOT echo the diff. DO NOT invent issues that aren't in the commits.

""" + prompt_safety.UNTRUSTED_DATA_INSTRUCTION


USER_TEMPLATE = """Sample recent PR titles from this repo (style guide):
{pr_samples}

Commits on this branch (oldest → newest):
{commits}

Base ref:
{base_ref}

Diff against base:
{diff}

Produce the JSON now."""


def detect_base_branch(candidates: list[str] | None = None) -> str | None:
    """Return the most likely base branch name (origin/main, main, master, …)."""
    if candidates is None:
        candidates = [
            "origin/main", "origin/master",
            "main", "master", "develop",
        ]
    for ref in candidates:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", ref],
                capture_output=True, text=True, check=False, timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.strip():
            return ref
    return None


def commits_since(base_ref: str, limit: int = 50) -> list[str]:
    """Commit subjects on HEAD not in base."""
    try:
        result = subprocess.run(
            ["git", "log", f"{base_ref}..HEAD", f"-{limit}", "--reverse", "--pretty=format:%s"],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def diff_against(base_ref: str) -> str:
    """Full diff of HEAD vs base. Uses three-dot to ignore unrelated base changes."""
    try:
        result = subprocess.run(
            ["git", "diff", f"{base_ref}...HEAD", "--no-color"],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout if result.returncode == 0 else ""


def recent_pr_titles(limit: int = 10) -> list[str]:
    """Use `gh pr list` to get recent merged PR titles for style learning."""
    if not shutil.which("gh"):
        return []
    try:
        result = subprocess.run(
            [
                "gh", "pr", "list",
                "--state", "merged",
                "--limit", str(limit),
                "--json", "title",
            ],
            capture_output=True, text=True, check=False, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError):
        return []
    return [d.get("title", "").strip() for d in data if d.get("title")]


def _truncate(text: str, limit: int = 16000) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return f"{head}\n\n... [{len(text) - limit} chars truncated] ...\n\n{tail}"


def generate(
    base_ref: str,
    commits: list[str],
    diff: str,
    pr_samples: list[str],
    model: str,
    *,
    use_cache: bool = True,
) -> PullRequest:
    """Single LLM call → (title, body). Cached like commit messages."""
    user = USER_TEMPLATE.format(
        pr_samples=prompt_safety.tagged(
            "pr_samples",
            "\n".join(f"- {s}" for s in pr_samples) or "(no prior PRs)",
        ),
        commits=prompt_safety.tagged(
            "commits",
            "\n".join(f"- {c}" for c in commits) or "(no commits)",
        ),
        base_ref=prompt_safety.tagged("base_ref", base_ref),
        diff=prompt_safety.tagged("diff", _truncate(diff)),
    )

    style_sig = "pr:" + "|".join(pr_samples[:3])
    if use_cache:
        hit = cache.lookup(diff=diff, model=model, style_signature=style_sig)
        if hit and hit.message:
            return _parse_pr(hit.message)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    try:
        response = litellm.completion(
            model=model, messages=messages,
            temperature=0.2, max_tokens=1500,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        if not _looks_like_response_format_rejection(exc):
            raise
        response = litellm.completion(
            model=model, messages=messages,
            temperature=0.2, max_tokens=1500,
        )
    raw = response.choices[0].message.content or ""
    pr = _parse_pr(raw)
    if use_cache and (pr.title or pr.body):
        cache.store(diff=diff, model=model, message=raw, style_signature=style_sig)
    return pr


def _parse_pr(raw: str) -> PullRequest:
    """Parse the JSON response, robust to fences and surrounding prose."""
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", s, re.DOTALL)
        if not match:
            return PullRequest(title="", body=s)
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return PullRequest(title="", body=s)
    return PullRequest(
        title=str(data.get("title", "")).strip(),
        body=str(data.get("body", "")).strip(),
    )


def _looks_like_response_format_rejection(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status not in (400, 422):
        return False
    message = str(exc).lower()
    return "response_format" in message or "json" in message

"""LLM-driven analysis: should this diff be split into multiple commits?"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import litellm

from commitr import prompt_safety


@dataclass
class CommitGroup:
    message: str
    files: list[str] = field(default_factory=list)
    rationale: str = ""


SPLIT_SYSTEM_PROMPT = """You analyze a staged git diff and decide whether it represents
ONE coherent logical change or SEVERAL independent logical changes that should be
committed separately.

Rules:
- Only split when changes are clearly INDEPENDENT (e.g. a feature + an unrelated
  bugfix, or code + unrelated docs). Tightly coupled changes stay together.
- Splitting is FILE-LEVEL: each file belongs to exactly one group.
- EVERY staged file must appear in exactly one group.
- Commit messages must match the project's existing style (use the samples).

Output STRICT JSON only. No prose, no code fences. Schema:

{
  "groups": [
    {
      "message": "<full commit message — subject + optional body>",
      "files": ["path/one.py", "path/two.py"],
      "rationale": "<one-sentence why these belong together>"
    }
  ]
}

If the diff is one coherent change, return a single-item groups array.

""" + prompt_safety.UNTRUSTED_DATA_INSTRUCTION


SPLIT_USER_TEMPLATE = """Recent commit subjects (style scan):
{subjects}

Full sample commits from this repo:
{samples}

Staged files:
{files}

Staged diff:
{diff}

Analyze and return the JSON."""


def _truncate(text: str, limit: int = 15000) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return f"{head}\n\n... [{len(text) - limit} chars truncated] ...\n\n{tail}"


def analyze_splits(
    diff: str,
    files: list[str],
    subjects: list[str],
    samples: list[str],
    model: str,
) -> list[CommitGroup]:
    """Ask the LLM whether/how to split.

    Always returns at least one group covering all files. If parsing or
    validation fails, returns a single group with an empty message — the
    caller is expected to fall back to the normal single-commit flow.
    """
    user = SPLIT_USER_TEMPLATE.format(
        subjects=prompt_safety.tagged(
            "recent_subjects",
            "\n".join(f"- {s}" for s in subjects) or "(none)",
        ),
        samples=prompt_safety.tagged(
            "commit_samples",
            "\n\n---\n\n".join(samples) or "(none)",
        ),
        files=prompt_safety.tagged(
            "staged_files",
            "\n".join(f"- {f}" for f in files),
        ),
        diff=prompt_safety.tagged("staged_diff", _truncate(diff)),
    )
    messages = [
        {"role": "system", "content": SPLIT_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    try:
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=0.1,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        # Re-raise hard errors (auth, rate-limit, server, network). Only retry
        # when the provider explicitly rejects response_format.
        if not _looks_like_response_format_rejection(exc):
            raise
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=0.1,
            max_tokens=2000,
        )

    raw = response.choices[0].message.content or ""
    parsed = _parse_json(raw)
    if not parsed:
        return [CommitGroup(message="", files=list(files), rationale="(parsing failed)")]

    groups_raw = parsed.get("groups", [])
    if not isinstance(groups_raw, list) or not groups_raw:
        return [CommitGroup(message="", files=list(files), rationale="(no groups returned)")]

    groups: list[CommitGroup] = []
    seen: set[str] = set()
    for g in groups_raw:
        if not isinstance(g, dict):
            continue
        msg = (g.get("message") or "").strip()
        fls_raw = g.get("files") or []
        rationale = (g.get("rationale") or "").strip()
        if not isinstance(fls_raw, list):
            continue
        # Only keep files that are actually staged, and dedupe across groups.
        fls = [f for f in fls_raw if isinstance(f, str) and f in files and f not in seen]
        if not fls:
            continue
        groups.append(CommitGroup(message=msg, files=fls, rationale=rationale))
        seen.update(fls)

    # Coverage check: if the model missed some files, append a catch-all group.
    missing = [f for f in files if f not in seen]
    if missing:
        groups.append(
            CommitGroup(
                message="",
                files=missing,
                rationale="(files not covered by the model's grouping)",
            )
        )

    return groups or [CommitGroup(message="", files=list(files), rationale="(empty groups)")]


def _parse_json(raw: str) -> dict | None:
    """Robust JSON extraction: direct parse, then first {...} block."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _looks_like_response_format_rejection(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status not in (400, 422):
        return False
    message = str(exc).lower()
    return "response_format" in message or "json" in message

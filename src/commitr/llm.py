"""LLM call: turn a staged diff into a commit message."""
from __future__ import annotations

import os

import litellm

SYSTEM_PROMPT = """You are an expert software engineer writing a git commit message.

Defaults (use only when no contrary pattern appears in the samples below):
- Conventional Commits format: <type>(<optional scope>): <subject>
- Types: feat, fix, refactor, docs, test, chore, perf, style, ci, build
- Subject under 72 chars, imperative mood, no trailing period
- Add a body (blank line, wrapped at 72) only for non-trivial changes

CRITICAL — match the project's existing style. From the samples, detect:
- LANGUAGE: do they write in English, Chinese, Japanese, …? Match it.
- SCOPE: do they use (scope) in parentheses? Match the convention.
- EMOJI / GITMOJI: if samples have emoji prefixes, use them; if not, don't.
- BODY USAGE: do they typically write a body, or just a subject?
- TYPE VOCABULARY: stick to the types the samples actually use.

If the samples contradict the defaults above, follow the samples.

Output ONLY the commit message. No explanation, no code fences, no quotes."""

USER_TEMPLATE = """Recent commit subjects (broad style scan):
{subjects}

A few full commit messages from this repo (use as few-shot style examples):
{samples}

Staged diff to summarize:
```diff
{diff}
```

Write the commit message now, matching the project's style."""


def _truncate_diff(diff: str, max_chars: int = 12000) -> str:
    if len(diff) <= max_chars:
        return diff
    head = diff[: max_chars // 2]
    tail = diff[-max_chars // 2 :]
    return (
        f"{head}\n\n... [diff truncated, "
        f"{len(diff) - max_chars} chars omitted] ...\n\n{tail}"
    )


def generate_commit_message(
    diff: str,
    subjects: list[str] | None = None,
    samples: list[str] | None = None,
    model: str | None = None,
) -> str:
    model = model or os.environ.get("COMMITR_MODEL", "gpt-4o-mini")
    subjects_block = (
        "\n".join(f"- {s}" for s in (subjects or [])) or "(no prior commits)"
    )
    samples_block = (
        "\n\n---\n\n".join(samples or []) or "(no prior commits)"
    )

    user = USER_TEMPLATE.format(
        subjects=subjects_block,
        samples=samples_block,
        diff=_truncate_diff(diff),
    )

    response = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=300,
    )
    content = response.choices[0].message.content or ""
    return _clean(content)


def _clean(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [ln for ln in lines if not ln.startswith("```")]
        text = "\n".join(lines).strip()
    return text

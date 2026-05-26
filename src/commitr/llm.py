"""LLM call: turn a staged diff into a commit message."""
from __future__ import annotations

import hashlib
import os

import litellm

from commitr import cache
from commitr import prompt_safety

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

{untrusted_data_instruction}

Output ONLY the commit message. No explanation, no code fences, no quotes."""

USER_TEMPLATE = """Recent commit subjects (broad style scan):
{subjects}

A few full commit messages from this repo (use as few-shot style examples):
{samples}
{extra_context}
Staged diff to summarize:
{diff}

Write the commit message now, matching the project's style."""


CONTEXT_TEMPLATE = """
Additional context about WHY this change is being made (use it to inform the
body and any issue references, but do not quote it verbatim):
{context}
"""


SYSTEM_PROMPT = SYSTEM_PROMPT.format(
    untrusted_data_instruction=prompt_safety.UNTRUSTED_DATA_INSTRUCTION
)


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
    *,
    context: str | None = None,
    use_cache: bool = True,
) -> str:
    model = model or os.environ.get("COMMITR_MODEL")
    if not model:
        raise RuntimeError(
            "No model configured. Set COMMITR_MODEL or pass model=... "
            "(e.g. `commitr --provider deepseek`)."
        )
    subjects_block = (
        "\n".join(f"- {s}" for s in (subjects or [])) or "(no prior commits)"
    )
    samples_block = (
        "\n\n---\n\n".join(samples or []) or "(no prior commits)"
    )
    safe_context = context.strip() if context and context.strip() else ""
    context_block = (
        CONTEXT_TEMPLATE.format(context=prompt_safety.tagged("issue_context", safe_context))
        if safe_context
        else ""
    )

    user = USER_TEMPLATE.format(
        subjects=prompt_safety.tagged("recent_subjects", subjects_block),
        samples=prompt_safety.tagged("commit_samples", samples_block),
        extra_context=context_block,
        diff=prompt_safety.tagged("staged_diff", _truncate_diff(diff)),
    )

    # Cache key includes style + context so changing either invalidates.
    style_sig = _style_signature(subjects or [], samples or [], context or "")
    if use_cache:
        hit = cache.lookup(diff=diff, model=model, style_signature=style_sig)
        if hit and hit.message:
            return hit.message

    response = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=1000,
    )
    content = response.choices[0].message.content or ""
    message = _clean(content)

    if use_cache and message:
        cache.store(diff=diff, model=model, message=message, style_signature=style_sig)
    return message


def _style_signature(subjects: list[str], samples: list[str], context: str) -> str:
    """Compact hash of style-influencing inputs for cache keying."""
    h = hashlib.sha256()
    for s in subjects[:5]:  # only top of history matters for style
        h.update(s.encode("utf-8"))
        h.update(b"\x00")
    h.update(b"\x01")
    for s in samples[:2]:
        h.update(s.encode("utf-8"))
        h.update(b"\x00")
    h.update(b"\x02")
    h.update(context.encode("utf-8"))
    return h.hexdigest()[:16]


def _clean(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [ln for ln in lines if not ln.startswith("```")]
        text = "\n".join(lines).strip()
    return text


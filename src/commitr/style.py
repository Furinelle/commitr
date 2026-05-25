"""Infer a repository's commit-message style from recent history."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field


CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-z][a-z0-9-]*)(?:\((?P<scope>[^)]+)\))?!?:"
)
EMOJI_PREFIX_RE = re.compile(r"^\s*[^\w\s:()]+(?:\ufe0f)?\s+")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class StyleProfile:
    language: str = "unknown"
    uses_conventional_commits: bool = False
    uses_emoji_prefix: bool = False
    body_usage: str = "unknown"
    types: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)


def infer_profile(subjects: list[str], samples: list[str]) -> StyleProfile:
    """Infer lightweight style cues from git history."""
    cleaned_subjects = [s.strip() for s in subjects if s.strip()]
    normalized = [_strip_emoji_prefix(s) for s in cleaned_subjects]
    type_counter: Counter[str] = Counter()
    scope_counter: Counter[str] = Counter()
    type_order: dict[str, int] = {}
    scope_order: dict[str, int] = {}

    for index, subject in enumerate(normalized):
        match = CONVENTIONAL_RE.match(subject)
        if not match:
            continue
        typ = match.group("type")
        scope = match.group("scope")
        type_counter[typ] += 1
        type_order.setdefault(typ, index)
        if scope:
            scope_counter[scope] += 1
            scope_order.setdefault(scope, index)

    conventional_ratio = (
        sum(type_counter.values()) / len(cleaned_subjects)
        if cleaned_subjects else 0
    )

    return StyleProfile(
        language=_detect_language(cleaned_subjects + samples),
        uses_conventional_commits=conventional_ratio >= 0.5,
        uses_emoji_prefix=any(_has_emoji_prefix(s) for s in cleaned_subjects),
        body_usage=_detect_body_usage(samples),
        types=_rank(type_counter, type_order),
        scopes=_rank(scope_counter, scope_order),
    )


def render_profile(profile: StyleProfile) -> str:
    """Render a stable plain-text summary for CLI output and tests."""
    lines = [
        f"Language: {profile.language}",
        f"Conventional commits: {'yes' if profile.uses_conventional_commits else 'no'}",
        f"Emoji prefix: {'yes' if profile.uses_emoji_prefix else 'no'}",
        f"Body usage: {profile.body_usage}",
        f"Types: {', '.join(profile.types) if profile.types else '-'}",
        f"Scopes: {', '.join(profile.scopes) if profile.scopes else '-'}",
    ]
    return "\n".join(lines)


def _rank(counter: Counter[str], first_seen: dict[str, int]) -> list[str]:
    return [
        key for key, _ in sorted(
            counter.items(),
            key=lambda item: (-item[1], first_seen[item[0]], item[0]),
        )
    ]


def _detect_language(texts: list[str]) -> str:
    text = "\n".join(texts)
    if CJK_RE.search(text):
        return "Chinese"
    if LATIN_RE.search(text):
        return "English"
    return "unknown"


def _detect_body_usage(samples: list[str]) -> str:
    non_empty = [s.strip() for s in samples if s.strip()]
    if not non_empty:
        return "unknown"
    body_count = sum(1 for s in non_empty if "\n\n" in s and s.split("\n\n", 1)[1].strip())
    if body_count == 0:
        return "rare"
    ratio = body_count / len(non_empty)
    if ratio >= 0.67:
        return "common"
    return "occasional"


def _has_emoji_prefix(subject: str) -> bool:
    return bool(EMOJI_PREFIX_RE.match(subject))


def _strip_emoji_prefix(subject: str) -> str:
    return EMOJI_PREFIX_RE.sub("", subject, count=1).strip()

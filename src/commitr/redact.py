"""Secret redaction before diffs are sent to an LLM provider."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Redaction:
    kind: str
    count: int


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "openai_key",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
        "<REDACTED-OPENAI-KEY>",
    ),
    (
        "aws_access_key",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
        "<REDACTED-AWS-ACCESS-KEY>",
    ),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
        ),
        "<REDACTED-JWT>",
    ),
)


def redact_secrets(text: str) -> tuple[str, list[Redaction]]:
    """Replace common secret shapes with stable placeholders."""
    redacted = text
    findings: list[Redaction] = []
    for kind, pattern, replacement in SECRET_PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            findings.append(Redaction(kind=kind, count=count))
    return redacted, findings

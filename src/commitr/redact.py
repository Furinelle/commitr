"""Secret-pattern based redaction.

ORDERING CONTRACT: patterns whose match space overlaps a later pattern's MUST
appear first (e.g. anthropic_key before openai_key — both start with `sk-`).
Tuple order is part of the API; don't sort it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Redaction:
    kind: str
    count: int


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    # Must precede openai_key — sk-ant-... is also a valid sk-... prefix.
    (
        "anthropic_key",
        re.compile(r"\bsk-ant-(?:api03-)?[A-Za-z0-9_-]{20,}\b"),
        "<REDACTED-ANTHROPIC-KEY>",
    ),
    (
        "openai_key",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
        "<REDACTED-OPENAI-KEY>",
    ),
    # AWS prefixes per the official "Identifiers for IAM" reference:
    # AKIA=access key, ASIA=STS temp credential, AGPA=user group,
    # AIDA=IAM user, AIPA=EC2 instance profile, AROA=role, ANPA=managed policy,
    # ANVA=managed policy version, APKA=public key, ABIA=STS bearer token,
    # ACCA=context-specific credential, ASCA=certificate.
    (
        "aws_access_key",
        re.compile(
            r"\b(?:AKIA|ASIA|AGPA|AIDA|AIPA|AROA|ANPA|ANVA|APKA|ABIA|ACCA|ASCA)[A-Z0-9]{16}\b"
        ),
        "<REDACTED-AWS-ACCESS-KEY>",
    ),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
        ),
        "<REDACTED-JWT>",
    ),
    (
        "github_pat",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
        "<REDACTED-GITHUB-PAT>",
    ),
    (
        "slack_token",
        re.compile(r"\bxox[bpoars]-[A-Za-z0-9-]{10,}\b"),
        "<REDACTED-SLACK-TOKEN>",
    ),
    # Full PEM block first; falls back to header-only if END marker is absent
    # or truncated (e.g. diff context cut off the trailer).
    (
        "private_key_block",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED |PGP |)?PRIVATE KEY-----"
            r"[\s\S]*?"
            r"-----END (?:RSA |EC |OPENSSH |DSA |ENCRYPTED |PGP |)?PRIVATE KEY-----"
        ),
        "<REDACTED-PRIVATE-KEY-BLOCK>",
    ),
    (
        "private_key_header",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED |PGP |)?PRIVATE KEY-----"
        ),
        "<REDACTED-PRIVATE-KEY>",
    ),
    # Spec proposed [:=] but `:` matches YAML/JSON keys far too aggressively
    # (`name: foo`, `port: 8080`). Restrict to `=` to keep false positives low.
    (
        "generic_secret_assign",
        re.compile(
            r"(?i)(?:password|passwd|secret|api[_-]?key|token)\s*=\s*"
            r"[\'\"]?(?!<REDACTED-)([^\s\'\"\n,;]{8,})[\'\"]?"
        ),
        "<REDACTED-SECRET>",
    ),
    (
        "db_connection_string",
        re.compile(r"(?:postgres|postgresql|mysql|mongodb|redis)://[^:]+:[^@/\s]+@[^\s/]+"),
        "<REDACTED-DB-URI>",
    ),
)


def redact_secrets(text: str) -> tuple[str, list[Redaction]]:
    """Replace common secret shapes with stable placeholders."""
    redacted = text
    findings: list[Redaction] = []
    for kind, pattern, replacement in SECRET_PATTERNS:
        if kind == "generic_secret_assign":
            # Replace only the captured value (group 1); preserve the
            # `password=` prefix and any quote chars so the diff stays readable.
            redacted, count = pattern.subn(
                lambda match: (
                    f"{match.group(0)[: match.start(1) - match.start(0)]}"
                    f"{replacement}"
                    f"{match.group(0)[match.end(1) - match.start(0):]}"
                ),
                redacted,
            )
        else:
            redacted, count = pattern.subn(replacement, redacted)
        if count:
            findings.append(Redaction(kind=kind, count=count))
    return redacted, findings

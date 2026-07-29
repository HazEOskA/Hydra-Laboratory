"""Secret redaction shared by the worker, the ledger and the evidence bundler.

One implementation, used everywhere output can reach disk or a report. Masking
follows the format required by the mission spec: `abcd...wxyz`.
"""

from __future__ import annotations

import re

PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"nvapi-[A-Za-z0-9_-]{8,}"), "[REDACTED-NVIDIA-KEY]"),
    (re.compile(r"tskey-(auth|client|api)-[A-Za-z0-9_-]{8,}"), "[REDACTED-TAILSCALE-KEY]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{16,}"), "[REDACTED-GITHUB-TOKEN]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED-AWS-KEY]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "[REDACTED-PRIVATE-KEY]"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b(?<!127\.0\.0\.1)"), "[REDACTED-IP]"),
    (
        re.compile(
            r"(authorization|bearer|api[_-]?key|apikey|token|secret|password)"
            r"(\s*[:=]\s*|\s+)([A-Za-z0-9._/+-]{8,})",
            re.IGNORECASE,
        ),
        r"\1\2[REDACTED]",
    ),
]


def redact(text: str) -> str:
    """Replace credential-shaped material. Safe to run on anything before storing."""
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def mask(value: str, keep: int = 4) -> str:
    """Mask a known secret for inventories: `abcd...wxyz`."""
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"


def excerpt(text: str, limit: int = 240) -> str:
    """Redacted, whitespace-collapsed, length-bounded — the only form stored."""
    return re.sub(r"\s+", " ", redact(text)).strip()[:limit]

"""Constitution loading.

SOUL.md is only meaningful if it is actually in front of the model. This module is
the single place that reads it, hashes it and turns it into the preamble the duty
cycle prepends to every prompt — so "is the constitution loaded?" is a question
with a testable answer rather than an assumption.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from . import config as config_module

REQUIRED_SECTIONS = (
    "## Identity",
    "## Primary Mission",
    "## Operating Principles",
    "## Permission Model",
    "### GREEN — Execute Autonomously",
    "### YELLOW — Execute and Log",
    "### RED — OSA Approval Required",
    "## Execution Loop",
    "## Anti-Drift Rules",
    "## Failure Handling",
    "## Monetization Rule",
    "## Definition of Done",
    "## Communication",
)


@dataclass(frozen=True)
class Soul:
    path: Path
    text: str
    sha256: str
    version: str

    @property
    def loaded(self) -> bool:
        return bool(self.text.strip())


def load(path: str | Path | None = None) -> Soul:
    soul_path = Path(path) if path else config_module.soul_path()
    if not soul_path.is_file():
        raise FileNotFoundError(f"constitution not found: {soul_path}")
    text = soul_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Soul(path=soul_path, text=text, sha256=digest, version=digest[:12])


def verify(soul: Soul) -> tuple[bool, list[str]]:
    """Structural check: every constitutional section must still be present."""
    missing = [section for section in REQUIRED_SECTIONS if section not in soul.text]
    return (not missing), missing


def preamble(soul: Soul, max_chars: int = 6000) -> str:
    """The system preamble injected ahead of every duty-cycle prompt.

    Truncation is explicit and always keeps the permission model, because that is
    the part that governs what Hermes may do without asking.
    """
    header = (
        f"[HERMES CONSTITUTION {soul.version} — sha256:{soul.sha256[:16]}]\n"
        "The following is your operational constitution. It governs this and every "
        "task. Follow it exactly.\n\n"
    )
    body = soul.text
    if len(header) + len(body) > max_chars:
        keep = max_chars - len(header) - 80
        marker = "## Permission Model"
        index = body.find(marker)
        if index > 0:
            identity = body[: min(index, keep // 3)]
            permissions = body[index : index + (keep - len(identity))]
            body = f"{identity}\n[...]\n{permissions}"
        else:
            body = body[:keep]
        body += "\n[constitution truncated for prompt budget; full text on the host]"
    return header + body

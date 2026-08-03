"""Zgredek — context packet preparation and approval.

Zgredek sits between OSA and Hydra. It prepares and approves the context a
coding mission is allowed to rely on, and it detects drift against the recorded
architecture locks. It does **not** implement, deploy, trade, or run a worker.

That boundary is enforced structurally, not by convention: this module performs
no subprocess execution, opens no socket, and writes nothing outside the packet
it returns. It only reads declared repository files and computes a hash. The
refusal it makes possible is executed by Hydra (`MissionService`), which is the
layer that owns dispatch — Zgredek supplies the verdict, never the action.

The first adapter is deterministic and local. It does not claim to have called
a separate Zgredek product; that contract remains UNKNOWN.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


PACKET_SCHEMA_VERSION = "zgredek-context-packet/0.1"
ADAPTER_ID = "zgredek-local-contract-v0.1"

# Files treated as repository instructions, in priority order. Missing files are
# reported as absent rather than silently skipped.
INSTRUCTION_FILES = ("SOUL.md", "README.md", "CLAUDE.md", "AGENTS.md")

# Architecture locks are discovered by filename so a new lock is picked up
# without editing this module.
LOCK_GLOBS = ("docs/*LOCK*.md", "docs/*lock*.md")

DECISIONS_FILE = "docs/DECISIONS.md"
DECISION_HEADING = re.compile(r"^##\s+(?P<id>D-\d+):\s*(?P<title>.+?)\s*$")

CODEOWNERS_CANDIDATES = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")

# Canonical statements a mission may not drift from. Each is bound to the source
# that established it, so a reviewer can trace the rule rather than trust it.
FORBIDDEN_DRIFT = (
    ("zgredek-does-not-implement", "Zgredek nie implementuje, nie traduje i nie wdraża.", "canon"),
    ("minions-are-not-a-control-plane", "Minions są workerami wewnątrz Michael Angelo, a nie nowym top-level control plane.", "canon"),
    ("production-merge-is-red", "Produkcyjny merge pozostaje RED; brak automatycznego merge bez jawnej polityki OSA.", "canon"),
    ("web3-lab-isolated", "Web3 Lab pozostaje odseparowany od standardowego execution plane.", "canon"),
    ("no-host-paths", "Repozytorium wejściowe nie może być ścieżką hosta ani URL-em.", "MINION_CONTROL_PLANE_ARCHITECTURE_LOCK_v0.1"),
    ("no-production-credentials", "Worker nie otrzymuje credentiali produkcyjnych i nie dziedziczy całego env hosta.", "MINION_CONTROL_PLANE_ARCHITECTURE_LOCK_v0.1"),
    ("loopback-only", "Control plane binduje się wyłącznie do loopbacku.", "MINION_CONTROL_PLANE_ARCHITECTURE_LOCK_v0.1"),
    ("no-unknown-gate-pass", "UNKNOWN nigdy nie spełnia bramki.", "MINION_CONTROL_PLANE_ARCHITECTURE_LOCK_v0.1"),
)

# Evidence a mission must produce before it may complete. Mirrors the gates
# enforced in MissionService.evidence(); Zgredek states them up front so the
# requirement is known before execution rather than discovered after it.
REQUIRED_EVIDENCE = (
    "git-diff",
    "rollback-plan",
    "acceptance-criteria",
    "required-tests",
    "evidence-reference",
    "commit-binding",
    "event-chain",
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_sha256(payload: dict[str, Any]) -> str:
    """Hash a packet payload independently of key order and whitespace."""
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


@dataclass(frozen=True)
class ContextPacket:
    schema_version: str
    adapter: str
    mission_id: str
    repository: str
    base_branch: str
    repository_instructions: tuple[dict[str, Any], ...]
    architecture_locks: tuple[dict[str, Any], ...]
    accepted_decisions: tuple[dict[str, Any], ...]
    ownership: dict[str, Any]
    forbidden_drift: tuple[dict[str, Any], ...]
    required_evidence: tuple[str, ...]
    prepared_at: str
    approved_by: str
    approved_at: str
    sha256: str = ""

    def payload(self) -> dict[str, Any]:
        """Everything the hash covers. The hash itself is excluded."""
        return {
            "schemaVersion": self.schema_version,
            "adapter": self.adapter,
            "missionId": self.mission_id,
            "repository": self.repository,
            "baseBranch": self.base_branch,
            "repositoryInstructions": list(self.repository_instructions),
            "architectureLocks": list(self.architecture_locks),
            "acceptedDecisions": list(self.accepted_decisions),
            "ownership": self.ownership,
            "forbiddenDrift": list(self.forbidden_drift),
            "requiredEvidence": list(self.required_evidence),
            "preparedAt": self.prepared_at,
            "approvedBy": self.approved_by,
            "approvedAt": self.approved_at,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload()
        payload["sha256"] = self.sha256
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextPacket":
        return cls(
            schema_version=data.get("schemaVersion", ""),
            adapter=data.get("adapter", ""),
            mission_id=data.get("missionId", ""),
            repository=data.get("repository", ""),
            base_branch=data.get("baseBranch", ""),
            repository_instructions=tuple(data.get("repositoryInstructions", [])),
            architecture_locks=tuple(data.get("architectureLocks", [])),
            accepted_decisions=tuple(data.get("acceptedDecisions", [])),
            ownership=data.get("ownership", {}),
            forbidden_drift=tuple(data.get("forbiddenDrift", [])),
            required_evidence=tuple(data.get("requiredEvidence", [])),
            prepared_at=data.get("preparedAt", ""),
            approved_by=data.get("approvedBy", ""),
            approved_at=data.get("approvedAt", ""),
            sha256=data.get("sha256", ""),
        )


class ContextAuthority(Protocol):
    """Production boundary for Zgredek context preparation and approval."""

    adapter_id: str

    def prepare(
        self, *, mission_id: str, repository: str, base_branch: str, now: str
    ) -> ContextPacket: ...

    def verify(
        self, packet: ContextPacket, *, mission_id: str, repository: str, base_branch: str
    ) -> list[str]: ...


class DeterministicZgredek:
    """Local deterministic Zgredek adapter.

    Reads only declared repository files. Performs no execution of any kind.
    """

    adapter_id = ADAPTER_ID

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve(strict=True)

    # -- preparation --------------------------------------------------

    def _read(self, relative: str) -> str | None:
        candidate = (self.repo_root / relative).resolve()
        try:
            candidate.relative_to(self.repo_root)
        except ValueError:
            # A traversal attempt never reads outside the repository root.
            return None
        if not candidate.is_file():
            return None
        return candidate.read_text(encoding="utf-8", errors="replace")

    def _instructions(self) -> tuple[dict[str, Any], ...]:
        entries = []
        for name in INSTRUCTION_FILES:
            text = self._read(name)
            entries.append(
                {
                    "path": name,
                    "present": text is not None,
                    "sha256": _sha256_text(text) if text is not None else "",
                    "bytes": len(text.encode("utf-8")) if text is not None else 0,
                }
            )
        return tuple(entries)

    def _locks(self) -> tuple[dict[str, Any], ...]:
        seen: dict[str, dict[str, Any]] = {}
        for pattern in LOCK_GLOBS:
            for path in sorted(self.repo_root.glob(pattern)):
                if not path.is_file():
                    continue
                relative = path.relative_to(self.repo_root).as_posix()
                if relative in seen:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                title = ""
                for line in text.splitlines():
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
                seen[relative] = {
                    "path": relative,
                    "title": title,
                    "sha256": _sha256_text(text),
                    "bytes": len(text.encode("utf-8")),
                }
        return tuple(seen[key] for key in sorted(seen))

    def _decisions(self) -> tuple[dict[str, Any], ...]:
        text = self._read(DECISIONS_FILE)
        if text is None:
            return ()
        decisions: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        body: list[str] = []
        for line in text.splitlines():
            match = DECISION_HEADING.match(line)
            if match:
                if current is not None:
                    current["statement"] = " ".join(body).strip()[:600]
                    decisions.append(current)
                current = {"id": match["id"], "title": match["title"], "statement": ""}
                body = []
            elif current is not None and line.strip():
                body.append(line.strip())
        if current is not None:
            current["statement"] = " ".join(body).strip()[:600]
            decisions.append(current)
        return tuple(decisions)

    def _ownership(self) -> dict[str, Any]:
        for candidate in CODEOWNERS_CANDIDATES:
            text = self._read(candidate)
            if text is None:
                continue
            rules = []
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                parts = stripped.split()
                if len(parts) >= 2:
                    rules.append({"pattern": parts[0], "owners": parts[1:]})
            return {
                "rootAuthority": "OSA",
                "source": candidate,
                "perPath": rules,
                "status": "RESOLVED",
            }
        # No CODEOWNERS exists. Ownership beyond the root authority is genuinely
        # unknown, and inventing reviewers would be worse than saying so.
        return {
            "rootAuthority": "OSA",
            "source": "",
            "perPath": [],
            "status": "UNKNOWN",
            "reason": "brak pliku CODEOWNERS; ownership per-ścieżka nieznane",
        }

    def prepare(
        self, *, mission_id: str, repository: str, base_branch: str, now: str
    ) -> ContextPacket:
        packet = ContextPacket(
            schema_version=PACKET_SCHEMA_VERSION,
            adapter=self.adapter_id,
            mission_id=mission_id,
            repository=repository,
            base_branch=base_branch,
            repository_instructions=self._instructions(),
            architecture_locks=self._locks(),
            accepted_decisions=self._decisions(),
            ownership=self._ownership(),
            forbidden_drift=tuple(
                {"id": item, "statement": statement, "source": source}
                for item, statement, source in FORBIDDEN_DRIFT
            ),
            required_evidence=REQUIRED_EVIDENCE,
            prepared_at=now,
            # Approval is what makes a packet usable. The local adapter approves
            # its own deterministic output and says so plainly; a real Zgredek
            # would record a human or upstream approver here instead.
            approved_by=self.adapter_id,
            approved_at=now,
        )
        digest = canonical_sha256(packet.payload())
        return ContextPacket(**{**packet.__dict__, "sha256": digest})

    # -- verification -------------------------------------------------

    def verify(
        self,
        packet: ContextPacket,
        *,
        mission_id: str,
        repository: str,
        base_branch: str,
    ) -> list[str]:
        """Return the reasons this packet may not be used. Empty means usable."""
        reasons: list[str] = []
        if packet.schema_version != PACKET_SCHEMA_VERSION:
            reasons.append(
                f"nieobsługiwana wersja packetu: {packet.schema_version or 'BRAK'}"
            )
        if not packet.sha256:
            reasons.append("packet nie ma sumy SHA-256")
        elif packet.sha256 != canonical_sha256(packet.payload()):
            reasons.append("suma SHA-256 packetu nie zgadza się z jego treścią")
        if not packet.approved_by or not packet.approved_at:
            reasons.append("packet nie został zatwierdzony przez Zgredka")
        if packet.mission_id != mission_id:
            reasons.append(
                f"packet dotyczy innej misji: {packet.mission_id or 'BRAK'} != {mission_id}"
            )
        if packet.repository != repository:
            reasons.append(
                f"packet dotyczy innego repozytorium: {packet.repository or 'BRAK'} != {repository}"
            )
        if packet.base_branch != base_branch:
            reasons.append(
                f"packet dotyczy innego brancha bazowego: {packet.base_branch or 'BRAK'} != {base_branch}"
            )
        if not packet.architecture_locks:
            reasons.append("packet nie zawiera żadnego architecture locka")
        if not packet.required_evidence:
            reasons.append("packet nie deklaruje wymaganych dowodów")
        return reasons

    def drift_report(self, packet: ContextPacket) -> dict[str, Any]:
        """Classify drift as PASS / DRIFT / UNKNOWN.

        UNKNOWN is returned when the packet carries nothing to compare against —
        an unevaluable packet must never be reported as clean.
        """
        if not packet.architecture_locks and not packet.repository_instructions:
            return {
                "status": "UNKNOWN",
                "findings": [],
                "reason": "packet nie zawiera locków ani instrukcji do porównania",
            }
        findings = self.detect_drift(packet)
        return {
            "status": "DRIFT" if findings else "PASS",
            "findings": findings,
            "reason": "" if not findings else f"{len(findings)} rozbieżności względem zatwierdzonego packetu",
        }

    def detect_drift(self, packet: ContextPacket) -> list[dict[str, Any]]:
        """Report locks whose on-disk content no longer matches the packet.

        This is drift detection, not enforcement: it states what changed since
        the packet was approved and leaves the decision to Hydra and OSA.
        """
        drift: list[dict[str, Any]] = []
        for lock in packet.architecture_locks:
            text = self._read(lock["path"])
            if text is None:
                drift.append({"path": lock["path"], "kind": "MISSING", "recorded": lock["sha256"], "current": ""})
                continue
            current = _sha256_text(text)
            if current != lock["sha256"]:
                drift.append({"path": lock["path"], "kind": "CHANGED", "recorded": lock["sha256"], "current": current})
        for entry in packet.repository_instructions:
            if not entry.get("present"):
                continue
            text = self._read(entry["path"])
            current = _sha256_text(text) if text is not None else ""
            if current != entry["sha256"]:
                drift.append(
                    {
                        "path": entry["path"],
                        "kind": "MISSING" if text is None else "CHANGED",
                        "recorded": entry["sha256"],
                        "current": current,
                    }
                )
        return drift

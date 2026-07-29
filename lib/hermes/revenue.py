"""Revenue operations: leads, audits, drafts, follow-ups and the ledger.

Everything here is build-side and local. Nothing in this module can contact a
prospect: drafting is GREEN, sending is RED and lives behind the permission
classifier, so a draft is a file on disk until OSA approves a scoped send.

Money is never overstated. Projected and realised amounts are separate columns —
`estimated_value` and `pipeline_value` are forecasts, `received_value` is cash.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LEAD_STATES = (
    "new",
    "researched",
    "audit_ready",
    "draft_ready",
    "approved_to_send",
    "sent",
    "replied",
    "qualified",
    "proposal",
    "won",
    "lost",
    "follow_up_due",
)

# Only OSA can move a lead into a state that implies external contact.
RED_STATES = frozenset({"approved_to_send", "sent"})

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    company_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    website TEXT DEFAULT '',
    industry TEXT DEFAULT '',
    team_size TEXT DEFAULT '',
    source TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    contact_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(company_id),
    contact_name TEXT DEFAULT '',
    email TEXT DEFAULT '',
    role TEXT DEFAULT '',
    consent INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    lead_id TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    contact_name TEXT DEFAULT '',
    email TEXT DEFAULT '',
    website TEXT DEFAULT '',
    industry TEXT DEFAULT '',
    problem TEXT DEFAULT '',
    team_size TEXT DEFAULT '',
    current_tools TEXT NOT NULL DEFAULT '[]',
    urgency TEXT DEFAULT '',
    estimated_value REAL NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    consent INTEGER NOT NULL DEFAULT 0,
    source TEXT DEFAULT '',
    state TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_contact TEXT,
    follow_up_date TEXT
);

CREATE TABLE IF NOT EXISTS audits (
    audit_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(lead_id),
    track TEXT NOT NULL,
    body TEXT NOT NULL,
    opportunity_score INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS offers (
    offer_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(lead_id),
    tier TEXT NOT NULL,
    assumptions TEXT NOT NULL DEFAULT '[]',
    estimated_value REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(lead_id),
    kind TEXT NOT NULL,
    subject TEXT DEFAULT '',
    body TEXT NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outreach_events (
    event_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(lead_id),
    draft_id TEXT REFERENCES drafts(draft_id),
    channel TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approval_ref TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS followups (
    followup_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(lead_id),
    due_date TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opportunities (
    opportunity_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(lead_id),
    source TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '[]',
    estimated_value REAL NOT NULL DEFAULT 0,
    pipeline_value REAL NOT NULL DEFAULT 0,
    contracted_value REAL NOT NULL DEFAULT 0,
    invoiced_value REAL NOT NULL DEFAULT 0,
    received_value REAL NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0,
    next_action TEXT DEFAULT '',
    owner TEXT DEFAULT 'OSA',
    status TEXT NOT NULL DEFAULT 'open',
    last_contact TEXT,
    follow_up_date TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL REFERENCES opportunities(opportunity_id),
    tier TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL REFERENCES opportunities(opportunity_id),
    amount REAL NOT NULL DEFAULT 0,
    issued_at TEXT,
    paid_at TEXT,
    status TEXT NOT NULL DEFAULT 'draft'
);

CREATE TABLE IF NOT EXISTS revenue_events (
    revenue_event_id TEXT PRIMARY KEY,
    opportunity_id TEXT REFERENCES opportunities(opportunity_id),
    kind TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'EUR',
    evidence TEXT NOT NULL DEFAULT '[]',
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS costs (
    cost_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'EUR',
    period TEXT DEFAULT '',
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    track TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    ref TEXT NOT NULL,
    sha256 TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

-- Sending is a RED action; the ledger refuses to record a send without an
-- approval reference, so a draft cannot become a "sent" row by accident.
CREATE TRIGGER IF NOT EXISTS outreach_requires_approval
BEFORE INSERT ON outreach_events
WHEN NEW.approval_ref = '' OR NEW.approved_by = ''
BEGIN
    SELECT RAISE(ABORT, 'outreach requires a scoped OSA approval reference');
END;
"""

URGENCY_SCORE = {"immediate": 30, "high": 24, "medium": 15, "low": 6, "": 0}
TEAM_SCORE = {"1-9": 6, "10-49": 16, "50-199": 24, "200+": 20, "": 0}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Lead:
    lead_id: str
    company: str
    contact_name: str = ""
    email: str = ""
    website: str = ""
    industry: str = ""
    problem: str = ""
    team_size: str = ""
    current_tools: list[str] | None = None
    urgency: str = ""
    estimated_value: float = 0.0
    score: int = 0
    consent: bool = False
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "company": self.company,
            "contact_name": self.contact_name,
            "email": self.email,
            "website": self.website,
            "industry": self.industry,
            "problem": self.problem,
            "team_size": self.team_size,
            "current_tools": self.current_tools or [],
            "urgency": self.urgency,
            "estimated_value": self.estimated_value,
            "score": self.score,
            "consent": self.consent,
            "source": self.source,
            "created_at": utc_now(),
        }


def score_lead(lead: Lead) -> int:
    """Deterministic 0-100 score. No model call, so it is reproducible and auditable."""
    score = URGENCY_SCORE.get(lead.urgency.lower(), 0)
    score += TEAM_SCORE.get(lead.team_size, 0)
    if lead.problem.strip():
        score += 12
    if lead.website.strip():
        score += 8
    if lead.current_tools:
        score += min(10, 3 * len(lead.current_tools))
    if lead.consent:
        score += 10
    if lead.email.strip():
        score += 4
    return max(0, min(100, score))


def estimate_value(lead: Lead, score: int) -> float:
    """A forecast, explicitly labelled as such wherever it is stored or shown."""
    base = {"1-9": 1500.0, "10-49": 6000.0, "50-199": 15000.0, "200+": 30000.0}
    return round(base.get(lead.team_size, 2000.0) * (0.5 + score / 100.0), 2)


def generate_audit(lead: Lead, score: int, findings: list[str]) -> str:
    """Deterministic mini-audit skeleton, built from stored facts only."""
    lines = [
        f"# AI Operations & Automation Audit — {lead.company}",
        "",
        f"- Prepared: {utc_now()}",
        f"- Industry: {lead.industry or 'not stated'}",
        f"- Team size: {lead.team_size or 'not stated'}",
        f"- Stated problem: {lead.problem or 'not stated'}",
        f"- Opportunity score: {score}/100",
        "",
        "## Observed problem map",
        "",
    ]
    lines += [f"- {finding}" for finding in findings] or ["- No findings recorded yet."]
    lines += [
        "",
        "## Automation opportunities",
        "",
        "- Candidate workflows are derived from the stated problem and current tools.",
        f"- Current tools on record: {', '.join(lead.current_tools or []) or 'none recorded'}",
        "",
        "## Risk assessment",
        "",
        "- Estimates in this document are forecasts, not commitments.",
        "- No system was accessed to produce this audit; it uses supplied and public data only.",
        "",
        "## Next step",
        "",
        "- A scoped diagnostic sprint, quoted after a short call.",
    ]
    return "\n".join(lines)


def generate_outreach_draft(lead: Lead, audit_summary: str) -> tuple[str, str]:
    """Returns (subject, body). This is a draft on disk — sending stays RED."""
    subject = f"{lead.company}: automation findings from a short operations review"
    body = "\n".join(
        [
            f"Hello {lead.contact_name or 'there'},",
            "",
            f"I looked at {lead.company} from public information and put together a short",
            "operations review focused on where automation would actually pay for itself.",
            "",
            audit_summary,
            "",
            "If it is useful I can walk through it in 20 minutes and leave you the",
            "written version either way.",
            "",
            "— Bartosz Osiński, OsaTechGPT",
            "",
            "[DRAFT — not sent. Sending requires scoped OSA approval.]",
        ]
    )
    return subject, body


class RevenueLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "RevenueLedger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def add_lead(self, lead: Lead) -> dict[str, Any]:
        score = score_lead(lead)
        estimated = lead.estimated_value or estimate_value(lead, score)
        now = utc_now()
        self.conn.execute(
            "INSERT INTO leads (lead_id, company, contact_name, email, website, industry,"
            " problem, team_size, current_tools, urgency, estimated_value, score, consent,"
            " source, state, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)",
            (
                lead.lead_id,
                lead.company,
                lead.contact_name,
                lead.email,
                lead.website,
                lead.industry,
                lead.problem,
                lead.team_size,
                json.dumps(lead.current_tools or []),
                lead.urgency,
                estimated,
                score,
                int(lead.consent),
                lead.source,
                now,
                now,
            ),
        )
        return {"lead_id": lead.lead_id, "score": score, "estimated_value": estimated}

    def set_state(self, lead_id: str, state: str, *, approval_ref: str = "") -> None:
        if state not in LEAD_STATES:
            raise ValueError(f"unknown lead state: {state}")
        if state in RED_STATES and not approval_ref:
            raise PermissionError(
                f"state {state!r} implies external contact and requires a scoped OSA approval"
            )
        self.conn.execute(
            "UPDATE leads SET state = ?, updated_at = ? WHERE lead_id = ?",
            (state, utc_now(), lead_id),
        )

    def get_lead(self, lead_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
        return dict(row) if row else None

    def add_audit(self, audit_id: str, lead_id: str, track: str, body: str, score: int) -> None:
        self.conn.execute(
            "INSERT INTO audits (audit_id, lead_id, track, body, opportunity_score, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (audit_id, lead_id, track, body, score, utc_now()),
        )

    def add_draft(self, draft_id: str, lead_id: str, kind: str, subject: str, body: str) -> None:
        self.conn.execute(
            "INSERT INTO drafts (draft_id, lead_id, kind, subject, body, sent, created_at)"
            " VALUES (?, ?, ?, ?, ?, 0, ?)",
            (draft_id, lead_id, kind, subject, body, utc_now()),
        )

    def schedule_followup(self, followup_id: str, lead_id: str, days: int, body: str = "") -> str:
        due = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")
        self.conn.execute(
            "INSERT INTO followups (followup_id, lead_id, due_date, body, done, created_at)"
            " VALUES (?, ?, ?, ?, 0, ?)",
            (followup_id, lead_id, due, body, utc_now()),
        )
        return due

    def record_outreach(
        self, event_id: str, lead_id: str, draft_id: str, channel: str, approved_by: str,
        approval_ref: str,
    ) -> None:
        """Only callable with a real approval reference; the DB trigger enforces it."""
        self.conn.execute(
            "INSERT INTO outreach_events (event_id, lead_id, draft_id, channel, approved_by,"
            " approval_ref, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_id, lead_id, draft_id, channel, approved_by, approval_ref, utc_now()),
        )
        self.conn.execute("UPDATE drafts SET sent = 1 WHERE draft_id = ?", (draft_id,))

    def add_opportunity(
        self, opportunity_id: str, lead_id: str, source: str, estimated_value: float,
        confidence: float, next_action: str, evidence: list[str] | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO opportunities (opportunity_id, lead_id, source, evidence,"
            " estimated_value, pipeline_value, confidence, next_action, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                opportunity_id,
                lead_id,
                source,
                json.dumps(evidence or []),
                estimated_value,
                round(estimated_value * confidence, 2),
                confidence,
                next_action,
                utc_now(),
            ),
        )

    def totals(self) -> dict[str, float]:
        """Forecast and realised amounts stay in separate buckets, always."""
        row = self.conn.execute(
            "SELECT COALESCE(SUM(estimated_value), 0) AS estimated,"
            " COALESCE(SUM(pipeline_value), 0) AS pipeline,"
            " COALESCE(SUM(contracted_value), 0) AS contracted,"
            " COALESCE(SUM(invoiced_value), 0) AS invoiced,"
            " COALESCE(SUM(received_value), 0) AS received FROM opportunities"
        ).fetchone()
        return {
            "estimated_value": float(row["estimated"]),
            "pipeline_value": float(row["pipeline"]),
            "contracted_value": float(row["contracted"]),
            "invoiced_value": float(row["invoiced"]),
            "received_value": float(row["received"]),
        }

    def counts(self) -> dict[str, int]:
        counts = {"leads": 0, "audits": 0, "drafts": 0, "drafts_sent": 0, "followups_due": 0}
        counts["leads"] = int(self.conn.execute("SELECT COUNT(*) n FROM leads").fetchone()["n"])
        counts["audits"] = int(self.conn.execute("SELECT COUNT(*) n FROM audits").fetchone()["n"])
        counts["drafts"] = int(self.conn.execute("SELECT COUNT(*) n FROM drafts").fetchone()["n"])
        counts["drafts_sent"] = int(
            self.conn.execute("SELECT COUNT(*) n FROM drafts WHERE sent = 1").fetchone()["n"]
        )
        counts["followups_due"] = int(
            self.conn.execute(
                "SELECT COUNT(*) n FROM followups WHERE done = 0 AND due_date <= ?",
                (datetime.now(timezone.utc).strftime("%Y-%m-%d"),),
            ).fetchone()["n"]
        )
        return counts

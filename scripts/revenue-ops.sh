#!/usr/bin/env bash
# Automation C: daily revenue operations (08:00).
#
# Scores stored leads, generates mini-audits and outreach drafts, and schedules
# follow-ups. It cannot send anything: drafting is GREEN, sending is RED and is
# refused by both the permission classifier and the ledger itself.
# shellcheck disable=SC2016
set -Eeuo pipefail
umask 077

STATE_DIR="${HERMES_WORKER_STATE_DIR:-/var/lib/hydra-hermes/worker}"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}"
out_dir="$STATE_DIR/reports"
mkdir -p "$out_dir"

ledger_db="${HERMES_REVENUE_DB:-$STATE_DIR/revenue-ledger.db}"

processed="$(HERMES_REVENUE_DB="$ledger_db" python3 - <<'PY'
import os, sys, uuid
sys.path.insert(0, os.path.join(os.environ["PWD"], "lib"))
from hermes.revenue import (Lead, RevenueLedger, generate_audit,
                            generate_outreach_draft, score_lead)

processed = 0
with RevenueLedger(os.environ["HERMES_REVENUE_DB"]) as ledger:
    rows = ledger.conn.execute(
        "SELECT * FROM leads WHERE state IN ('new', 'researched') ORDER BY score DESC"
    ).fetchall()
    for row in rows:
        import json
        lead = Lead(
            lead_id=row["lead_id"], company=row["company"], contact_name=row["contact_name"],
            email=row["email"], website=row["website"], industry=row["industry"],
            problem=row["problem"], team_size=row["team_size"],
            current_tools=json.loads(row["current_tools"]), urgency=row["urgency"],
            consent=bool(row["consent"]), source=row["source"],
        )
        score = score_lead(lead)
        suffix = uuid.uuid4().hex[:8]
        ledger.add_audit(f"audit-{suffix}", lead.lead_id, "TRACK_1_AI_SYSTEM_AUDITS",
                         generate_audit(lead, score, []), score)
        ledger.set_state(lead.lead_id, "audit_ready")
        subject, body = generate_outreach_draft(lead, f"Opportunity score: {score}/100")
        ledger.add_draft(f"draft-{suffix}", lead.lead_id, "outreach", subject, body)
        ledger.set_state(lead.lead_id, "draft_ready")
        ledger.schedule_followup(f"fu-{suffix}", lead.lead_id, 4)
        processed += 1
print(processed)
PY
)"

status="$(HERMES_WORKER_STATE_DIR="$STATE_DIR" python3 -m hermes.cli --db "$ledger_db" revenue status)"

{
  printf '# Daily Revenue Operations\n\n- generated: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf -- '- leads processed into audits and drafts: %s\n\n' "$processed"
  printf '## Ledger\n\n```json\n%s\n```\n\n' "$status"
  printf 'Nothing was sent. Drafts stay local until OSA approves a scoped send.\n'
} >"$out_dir/revenue-$(date -u +%Y-%m-%d).md"

printf 'REVENUE OPS: processed=%s sent=0 report=%s\n' "$processed" \
  "$out_dir/revenue-$(date -u +%Y-%m-%d).md"

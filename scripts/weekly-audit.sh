#!/usr/bin/env bash
# Automation E: weekly system audit (Sun 18:00).
#
# Looks for drift between what the repository claims and what the host does, and
# for the quiet failures — stale tasks, dead letters, unverifiable evidence.
set -Eeuo pipefail
umask 077

STATE_DIR="${HERMES_WORKER_STATE_DIR:-/var/lib/hydra-hermes/worker}"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}"
out_dir="$STATE_DIR/reports"
mkdir -p "$out_dir"
report="$out_dir/weekly-audit-$(date -u +%Y-%m-%d).md"

issues=0
issue() { printf -- '- [ ] %s\n' "$*"; issues=$((issues + 1)); }

{
  printf '# Weekly System Audit — %s\n\n' "$(date -u +%Y-%m-%d)"

  printf '## Static contract\n\n'
  if ( cd "$repo_root" && make static-check >/dev/null 2>&1 ); then
    printf -- '- Static checks pass.\n'
  else
    issue "make static-check FAILS — the repository contract is broken"
  fi

  printf '\n## Evidence integrity\n\n'
  if [[ -f "$STATE_DIR/missions.db" ]]; then
    if python3 -m hermes.cli ledger verify >/dev/null 2>&1; then
      printf -- '- Evidence ledger chain verifies.\n'
    else
      issue "evidence ledger chain does NOT verify"
    fi
  else
    printf -- '- No mission ledger yet.\n'
  fi

  printf '\n## Queue hygiene\n\n'
  if [[ -f "$STATE_DIR/queue.db" ]]; then
    dead="$(python3 -m hermes.cli queue list --status DEAD_LETTER 2>/dev/null \
      | python3 -c 'import json,sys
try: print(len(json.load(sys.stdin)))
except Exception: print(0)')"
    (( dead > 0 )) && issue "$dead task(s) in the dead-letter queue" \
      || printf -- '- Dead-letter queue is empty.\n'
    lag="$(python3 -m hermes.cli queue stats 2>/dev/null \
      | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("queue_lag_seconds", 0))
except Exception: print(0)')"
    (( lag > 86400 )) && issue "queue lag exceeds 24h (${lag}s)" \
      || printf -- '- Queue lag: %ss.\n' "$lag"
  else
    printf -- '- No queue yet.\n'
  fi

  printf '\n## Backup integrity\n\n'
  backup_root="${HERMES_BACKUP_ROOT:-${HYDRA_BASE_PATH:-/opt/hydra}/backups}"
  if [[ -e "$backup_root/latest/rollback-manifest.json" ]]; then
    age=$(( ( $(date -u +%s) - $(stat -c %Y "$backup_root/latest/rollback-manifest.json") ) / 86400 ))
    (( age > 14 )) && issue "newest rollback manifest is $age days old" \
      || printf -- '- Rollback manifest is %s days old.\n' "$age"
  else
    issue "no rollback manifest found under $backup_root"
  fi

  printf '\n## Constitution\n\n'
  python3 -m hermes.cli soul status 2>/dev/null | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print("- Constitution " + d["version"] + ", structure_ok=" + str(d["structure_ok"]))
except Exception:
    print("- Constitution status unavailable")' || true

  printf '\n## Revenue pipeline\n\n'
  python3 -m hermes.cli --db "${HERMES_REVENUE_DB:-$STATE_DIR/revenue-ledger.db}" \
    revenue status 2>/dev/null | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print("- Leads: " + str(d["counts"]["leads"]) + ", drafts: " + str(d["counts"]["drafts"]) +
          ", sent: " + str(d["counts"]["drafts_sent"]))
    print("- Pipeline (forecast): " + str(d["totals"]["pipeline_value"]) +
          "; received (cash): " + str(d["totals"]["received_value"]))
except Exception:
    print("- Revenue ledger unavailable")' || true

  printf '\n**Open issues: %d**\n' "$issues"
} >"$report"

printf 'WEEKLY AUDIT: issues=%d report=%s\n' "$issues" "$report"

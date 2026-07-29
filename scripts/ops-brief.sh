#!/usr/bin/env bash
# Automation D: daily OsaTechGPT operations brief (19:00).
#
# One page, composed only from recorded state. If a section has nothing to say it
# says so — an empty status message is worse than none.
set -Eeuo pipefail
umask 077

STATE_DIR="${HERMES_WORKER_STATE_DIR:-/var/lib/hydra-hermes/worker}"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}"
out_dir="$STATE_DIR/reports"
mkdir -p "$out_dir"
brief="$out_dir/brief-$(date -u +%Y-%m-%d).md"

jq_or_raw() { python3 -c 'import json,sys
try:
    print(json.dumps(json.load(sys.stdin), indent=2, sort_keys=True))
except Exception:
    print("(unavailable)")'; }

{
  printf '# OsaTechGPT Operations Brief — %s\n\n' "$(date -u +%Y-%m-%d)"

  printf '## Runtime health\n\n```\n'
  "$repo_root/scripts/health-watch.sh" --report-only 2>&1 | tail -n 20 || true
  printf '```\n\n'

  printf '## Duty cycle (last 24h)\n\n'
  if [[ -d "$STATE_DIR/journal" ]]; then
    "$repo_root/scripts/hermes-report.sh" --stdout --hours 24 2>/dev/null \
      | sed -n '3,12p' || printf '(no journal yet)\n'
  else
    printf '(no journal yet)\n'
  fi
  printf '\n'

  printf '## Queue\n\n```json\n'
  python3 -m hermes.cli queue stats 2>/dev/null | jq_or_raw || printf '(unavailable)\n'
  printf '```\n\n'

  printf '## Revenue pipeline\n\n```json\n'
  python3 -m hermes.cli --db "${HERMES_REVENUE_DB:-$STATE_DIR/revenue-ledger.db}" \
    revenue status 2>/dev/null | jq_or_raw || printf '(unavailable)\n'
  printf '```\n\n'

  printf '## Blockers requiring OSA\n\n'
  blocked="$(python3 -m hermes.cli queue list --status WAITING_FOR_APPROVAL 2>/dev/null \
    | python3 -c 'import json,sys
try:
    tasks = json.load(sys.stdin)
except Exception:
    tasks = []
for task in tasks:
    print("- RED: " + task["task_id"] + " (" + task["type"] + ")")' || true)"
  if [[ -n "$blocked" ]]; then printf '%s\n' "$blocked"; else printf -- '- None.\n'; fi
  printf '\n'

  printf '## Evidence\n\n'
  printf -- '- duty-cycle journal: %s/journal/\n' "$STATE_DIR"
  printf -- '- reports: %s\n' "$out_dir"
  printf -- '- health audit trail: %s/health/\n\n' "$STATE_DIR"

  printf '## Next recommended action\n\n'
  if [[ -e "$STATE_DIR/HALTED" ]]; then
    printf -- '- Clear the tripped circuit breaker after diagnosing: scripts/hermes-worker.sh --resume\n'
  elif [[ -n "$blocked" ]]; then
    printf -- '- Approve or reject the RED task(s) above: scripts/hermesctl queue approve <task_id>\n'
  else
    printf -- '- No blocker. Continue the current mission queue.\n'
  fi
} >"$brief"

ln -sfn "$brief" "$out_dir/brief-latest.md"
printf 'OPS BRIEF: %s\n' "$brief"

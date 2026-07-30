#!/usr/bin/env bash
# Automation A: Hermes health watch (*/5).
#
# Checks the runtime, auto-recovers GREEN failures, logs YELLOW recovery actions,
# and notifies OSA only when something critical is still broken after recovery.
# Silence is the goal: a healthy run says nothing to anyone.
# shellcheck disable=SC2015
set -Eeuo pipefail
umask 077

STATE_DIR="${HERMES_WORKER_STATE_DIR:-/var/lib/hydra-hermes/worker}"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
API_HEALTH_URL="${HERMES_API_HEALTH_URL:-http://127.0.0.1:8642/health}"
DASHBOARD_URL="${HERMES_DASHBOARD_URL:-http://127.0.0.1:18789/}"
DISK_WARN_PERCENT="${HERMES_DISK_WARN_PERCENT:-85}"
MEM_WARN_PERCENT="${HERMES_MEM_WARN_PERCENT:-90}"

report_only=0
[[ "${1:-}" == "--report-only" ]] && report_only=1

health_log="$STATE_DIR/health"
mkdir -p "$health_log" 2>/dev/null || true

critical=0
warnings=0
declare -a findings=() actions=()

ok()   { printf 'OK    %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; warnings=$((warnings + 1)); findings+=("WARN: $*"); }
crit() { printf 'CRIT  %s\n' "$*"; critical=$((critical + 1)); findings+=("CRIT: $*"); }
acted(){ printf 'ACT   %s\n' "$*"; actions+=("$*"); }

# YELLOW recovery: allowed without approval, but it must leave an audit trail.
audit() {
  local entry
  entry="$(TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)" PURPOSE="$1" CMD="$2" RESULT="$3" \
    ROLLBACK="$4" python3 -c '
import json, os
print(json.dumps({
    "ts": os.environ["TS"],
    "actor": "health-watch",
    "permission": "YELLOW",
    "purpose": os.environ["PURPOSE"],
    "command": os.environ["CMD"],
    "result": os.environ["RESULT"],
    "validation": "re-checked after the action",
    "rollback": os.environ["ROLLBACK"],
}, sort_keys=True))')"
  printf '%s\n' "$entry" >>"$health_log/audit-$(date -u +%Y-%m-%d).jsonl"
}

probe_http() {
  curl -fsS --max-time 5 -o /dev/null "$1" 2>/dev/null
}

# -- 1. control-plane self-check -----------------------------------------
if PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}" \
   python3 -m hermes.cli health >"$health_log/control-plane.json" 2>&1; then
  ok "control plane: soul, tools, models, queue and ledger all report ok"
else
  warn "control plane reports degraded; see $health_log/control-plane.json"
fi

# -- 2. Hermes API --------------------------------------------------------
if probe_http "$API_HEALTH_URL"; then
  ok "Hermes API health responds"
else
  if [[ $report_only -eq 0 ]] && systemctl list-unit-files 2>/dev/null | grep -q '^hermes'; then
    systemctl restart hermes 2>/dev/null && acted "restarted hermes service" || true
    audit "recover unresponsive Hermes API" "systemctl restart hermes" "attempted" \
      "systemctl stop hermes; restore previous image from the rollback manifest"
    sleep 5
    probe_http "$API_HEALTH_URL" && ok "Hermes API recovered after restart" \
      || crit "Hermes API still unreachable after restart"
  else
    crit "Hermes API health did not respond at $API_HEALTH_URL"
  fi
fi

# -- 3. dashboard ---------------------------------------------------------
if probe_http "$DASHBOARD_URL"; then
  ok "dashboard responds"
else
  warn "dashboard did not respond at $DASHBOARD_URL"
fi

# -- 4. queue -------------------------------------------------------------
if [[ -f "$STATE_DIR/queue.db" ]]; then
  queue_json="$(PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -m hermes.cli queue stats 2>/dev/null || printf '{}')"
  queue_json="${queue_json:-\{\}}"
  lag="$(printf '%s' "$queue_json" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("queue_lag_seconds", 0))
except Exception: print(0)')"
  if (( lag > 3600 )); then
    warn "queue lag is ${lag}s; the oldest ready task has been waiting over an hour"
  else
    ok "queue lag ${lag}s"
  fi
  if [[ $report_only -eq 0 ]]; then
    # Recovering a crashed worker's lease is GREEN: idempotent and reversible.
    recovered="$( { PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}" \
      python3 -m hermes.cli queue recover 2>/dev/null || printf '{}'; } \
      | python3 -c 'import json,sys
try: print(len(json.load(sys.stdin).get("recovered", [])))
except Exception: print(0)')"
    (( recovered > 0 )) && acted "requeued $recovered stale task(s)" || true
  fi
else
  ok "queue not yet initialised"
fi

# -- 5. evidence ledger ---------------------------------------------------
if [[ -f "$STATE_DIR/missions.db" ]]; then
  if PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}" \
     python3 -m hermes.cli ledger verify >/dev/null 2>&1; then
    ok "evidence ledger chain verifies"
  else
    crit "evidence ledger chain does NOT verify; treat records as suspect"
  fi
else
  ok "evidence ledger not yet initialised"
fi

# -- 6. duty cycle --------------------------------------------------------
if [[ -e "$STATE_DIR/HALTED" ]]; then
  crit "duty cycle circuit breaker is tripped: $(head -n1 "$STATE_DIR/HALTED" 2>/dev/null)"
elif [[ -e "$STATE_DIR/STOP" ]]; then
  ok "duty cycle paused by operator STOP file"
else
  ok "duty cycle is not halted"
fi

# -- 7. host resources ----------------------------------------------------
disk_used="$(df --output=pcent / 2>/dev/null | tail -n1 | tr -dc '0-9' || printf 0)"
if [[ -n "$disk_used" ]] && (( disk_used >= DISK_WARN_PERCENT )); then
  warn "root filesystem is ${disk_used}% full"
else
  ok "disk ${disk_used:-0}% used"
fi

mem_used="$(free 2>/dev/null | awk '/^Mem:/{if ($2>0) printf "%d", $3*100/$2}' || printf 0)"
if [[ -n "$mem_used" ]] && (( mem_used >= MEM_WARN_PERCENT )); then
  warn "memory pressure at ${mem_used}%"
else
  ok "memory ${mem_used:-0}% used"
fi

# -- 8. containers and services ------------------------------------------
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  restarting="$(docker ps --filter 'status=restarting' --format '{{.Names}}' 2>/dev/null | tr '\n' ' ' || true)"
  [[ -n "$restarting" ]] && crit "containers stuck restarting: $restarting" \
    || ok "no containers stuck restarting"
else
  ok "docker not in use on this host"
fi

if command -v systemctl >/dev/null 2>&1; then
  failed="$( { systemctl --failed --no-legend --plain 2>/dev/null || true; } \
    | awk '{print $1}' | tr '\n' ' ')"
  [[ -n "$failed" ]] && warn "failed systemd units: $failed" || ok "no failed systemd units"
fi

# -- 9. model route -------------------------------------------------------
# Refresh provider health from the live sandbox first. Without this the table
# stays empty, every model reads as DOWN, and the router blocks forever.
probe_json="$(PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m hermes.cli models probe 2>/dev/null || true)"
probe_phase="$(printf '%s' "${probe_json:-{\}}" | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print(d.get("phase") or d.get("error") or "unknown")
except Exception: print("unreadable")')"
case "$probe_phase" in
  Ready|ready|Running|running) ok "sandbox phase: $probe_phase" ;;
  probe_failed|unreadable) warn "could not read sandbox status (probe: $probe_phase)" ;;
  *) crit "sandbox is not serving; phase: $probe_phase" ;;
esac

# `models route` exits non-zero when it BLOCKS, and that verdict is the thing we
# need — so capture stdout first and neutralise only the exit status.
route_json="$(PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m hermes.cli models route FALLBACK 2>/dev/null || true)"
route_status="$(printf '%s' "${route_json:-{\}}" | python3 -c 'import json,sys
try: print(json.load(sys.stdin)["status"])
except Exception: print("UNKNOWN")')"
[[ "$route_status" == "BLOCKED" ]] \
  && crit "model router cannot route the FALLBACK class" \
  || ok "model router status: $route_status"

# -- summary --------------------------------------------------------------
summary="critical=$critical warnings=$warnings actions=${#actions[@]}"
printf '\nHEALTH WATCH: %s\n' "$summary"

{
  printf '{"ts":"%s","critical":%d,"warnings":%d,"actions":%d}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$critical" "$warnings" "${#actions[@]}"
} >>"$health_log/watch-$(date -u +%Y-%m-%d).jsonl" 2>/dev/null || true

# OSA is notified only when something critical survived recovery.
if (( critical > 0 )) && [[ $report_only -eq 0 ]]; then
  notice="Hermes health watch: $critical unresolved critical finding(s)"
  printf '%s\n' "$notice" >"$health_log/ALERT"
  for finding in "${findings[@]}"; do printf '  %s\n' "$finding" >>"$health_log/ALERT"; done
  if [[ -x "$repo_root/scripts/notify-osa.sh" ]]; then
    "$repo_root/scripts/notify-osa.sh" "$notice" || true
  fi
  exit 1
fi

rm -f "$health_log/ALERT" 2>/dev/null || true
exit 0

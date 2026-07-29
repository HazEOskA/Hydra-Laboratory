#!/usr/bin/env bash
# Controlled recovery of the hydra-hermes-lab sandbox.
#
# Executes the sequence OSA authorised on 2026-07-29 as one unattended run:
# preserve evidence, audit hydra-direct, back up, rebuild, then validate — with
# the security invariant that a provider credential visible inside the sandbox
# fails the run outright.
#
# Ordering is deliberate. Every piece of evidence that a rebuild destroys is
# captured before the rebuild, because a rebuild you cannot explain afterwards
# is a restart, not a repair.
# shellcheck disable=SC2015
# SC2016: the in-sandbox probe and the markdown fences are literal on purpose —
# expanding them on the host would defeat the check.
# shellcheck disable=SC2016
set -Eeuo pipefail
umask 077

SANDBOX="${NEMOCLAW_SANDBOX_NAME:-hydra-hermes-lab}"
LOCKED_HOST="${HERMES_LOCKED_HOST:-hydra-hermes-runtime-01}"
STATE_DIR="${HERMES_WORKER_STATE_DIR:-/var/lib/hydra-hermes/worker}"
BACKUP_ROOT="${HERMES_BACKUP_ROOT:-${HYDRA_BASE_PATH:-/opt/hydra}/backups}"
API_URL="${HERMES_API_HEALTH_URL:-http://127.0.0.1:8642/health}"
DASHBOARD_URL="${HERMES_DASHBOARD_URL:-http://127.0.0.1:18789/}"
READY_TIMEOUT="${HERMES_READY_TIMEOUT:-600}"
READY_POLL="${HERMES_READY_POLL:-10}"
RESTART_TIMEOUT="${HERMES_RESTART_TIMEOUT:-180}"

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_dir="$STATE_DIR/recovery/$stamp"
attempts_file="$STATE_DIR/recovery/rebuild-attempts.jsonl"

execute=0
hypothesis=""
skip_rebuild=0
while (( $# > 0 )); do
  case "$1" in
    --execute) execute=1 ;;
    --hypothesis) shift; hypothesis="${1:-}" ;;
    --skip-rebuild) skip_rebuild=1 ;;
    -h|--help)
      cat <<'USAGE'
Usage: scripts/recover-hermes.sh --execute --hypothesis "<why this attempt differs>"

  --execute        perform the recovery (without it, prints the plan and exits)
  --hypothesis S   required for a rebuild; a repeat of the previous hypothesis
                   is refused, per the rebuild failure policy
  --skip-rebuild   run evidence capture and validation only
USAGE
      exit 0
      ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

pass_count=0; fail_count=0
declare -a checklist=()
log()  { printf '%s recover %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
ok()   { printf 'PASS  %s\n' "$*"; checklist+=("PASS  $*"); pass_count=$((pass_count + 1)); }
bad()  { printf 'FAIL  %s\n' "$*" >&2; checklist+=("FAIL  $*"); fail_count=$((fail_count + 1)); }
info() { printf 'INFO  %s\n' "$*"; checklist+=("INFO  $*"); }

capture() {
  local file="$1"; shift
  { printf '$ %s\n' "$*"; "$@" 2>&1 || printf '(exit %d)\n' "$?"; printf '\n'; } \
    >>"$run_dir/$file"
}

# `nemohermes` prints a human banner before the JSON payload, so both helpers go
# through hermes.probe.extract_json — the same scanner the probe uses and the
# tests cover. A second, weaker parser here silently returned "unreadable" and
# made every wait loop run to its full timeout.
sandbox_phase() {
  { nemohermes "$SANDBOX" status --json 2>/dev/null || printf '{}'; } \
    | python3 -c '
import sys
sys.path.insert(0, sys.argv[1])
from hermes.probe import extract_json
try:
    print(extract_json(sys.stdin.read()).get("phase", "unknown"))
except Exception:
    print("unreadable")' "$repo_root/lib" 2>/dev/null || printf 'unreadable'
}

status_json() {
  { nemohermes "$SANDBOX" status --json 2>/dev/null || printf '{}'; } \
    | python3 -c '
import json, sys
sys.path.insert(0, sys.argv[1])
from hermes.probe import extract_json
try:
    print(json.dumps(extract_json(sys.stdin.read()), indent=2, sort_keys=True))
except Exception:
    print("{}")' "$repo_root/lib" 2>/dev/null || printf '{}'
}

if (( execute == 0 )); then
  cat <<PLAN
Recovery plan for $SANDBOX (dry run; nothing is changed)

  1. capture doctor, logs, metadata and configuration      [read-only]
  2. audit hydra-direct provenance, quarantine if unproven [OSA Decision 2]
  3. host-backup.sh --execute + verify rollback manifest   [reversible]
  4. rebuild the sandbox                                   [DESTRUCTIVE]
  5. wait for Ready, then validate ports, API, dashboard
  6. probe the model route and record provider health
  7. prove NVIDIA_INFERENCE_API_KEY is absent in-sandbox   [OSA Decision 1]
  8. one real inference request
  9. GREEN / YELLOW / RED execution tests
 10. restart recovery + queue and ledger persistence
 11. evidence bundle

Re-run with --execute --hypothesis "<reason>" to perform it.
PLAN
  exit 0
fi

# -- gates ----------------------------------------------------------------
[[ "$(hostname -s)" == "$LOCKED_HOST" ]] || {
  printf 'Refusing: this is %s, not %s.\n' "$(hostname -s)" "$LOCKED_HOST" >&2
  exit 2
}
command -v nemohermes >/dev/null 2>&1 || { printf 'nemohermes unavailable.\n' >&2; exit 3; }
command -v nemoclaw   >/dev/null 2>&1 || { printf 'nemoclaw unavailable.\n' >&2; exit 3; }

mkdir -p "$run_dir" "$(dirname "$attempts_file")"
ln -sfn "$run_dir" "$STATE_DIR/recovery/latest"
log "recovery run $stamp -> $run_dir"

# =========================================================================
# 1. Pre-rebuild evidence. This is the only chance to capture the crash.
# =========================================================================
log "phase 1: preserving pre-rebuild evidence"
phase_before="$(sandbox_phase)"
info "sandbox phase before recovery: $phase_before"
status_json >"$run_dir/status-pre-rebuild.json"
capture "doctor-pre-rebuild.txt" nemohermes "$SANDBOX" doctor --json
capture "logs-pre-rebuild.txt"   nemoclaw "$SANDBOX" logs
capture "logs-pre-rebuild.txt"   nemohermes "$SANDBOX" logs
capture "metadata-pre-rebuild.txt" nemoclaw list --json
capture "metadata-pre-rebuild.txt" nemoclaw inference get --json
capture "ports-pre-rebuild.txt" ss -tulpn
cp -a "$HOME/.nemoclaw/sandboxes.json" "$run_dir/sandboxes.json" 2>/dev/null || true

if [[ -s "$run_dir/doctor-pre-rebuild.txt" ]]; then
  ok "pre-rebuild doctor output preserved"
else
  bad "pre-rebuild doctor output is empty"
fi
[[ -s "$run_dir/logs-pre-rebuild.txt" ]] && ok "pre-rebuild logs preserved" \
  || bad "pre-rebuild logs are empty"

# =========================================================================
# 2. hydra-direct (OSA Decision 2)
# =========================================================================
log "phase 2: hydra-direct provenance audit"
if "$repo_root/scripts/audit-hydra-direct.sh" --enforce >"$run_dir/hydra-direct.txt" 2>&1; then
  ok "hydra-direct provenance verified"
else
  info "hydra-direct provenance NOT established; quarantined and excluded from the trust boundary"
fi

# =========================================================================
# 3. Backup and rollback manifest
# =========================================================================
log "phase 3: backup"
if HERMES_BACKUP_ROOT="$BACKUP_ROOT" "$repo_root/scripts/host-backup.sh" --execute \
    >"$run_dir/backup.txt" 2>&1; then
  ok "backup completed"
else
  bad "backup failed; see $run_dir/backup.txt"
fi

manifest="$BACKUP_ROOT/latest/rollback-manifest.json"
if [[ -f "$manifest" ]] && python3 -c '
import json, sys
data = json.load(open(sys.argv[1]))
assert data.get("rollback_commands"), "no rollback commands"
assert data.get("timestamp"), "no timestamp"
' "$manifest" 2>/dev/null; then
  ok "rollback manifest verified with executable rollback commands"
  cp -a "$manifest" "$run_dir/rollback-manifest.json"
else
  bad "rollback manifest missing or unusable — refusing to rebuild without a rollback path"
fi

# A rebuild without a verified rollback is not a controlled recovery.
if (( fail_count > 0 )) && (( skip_rebuild == 0 )); then
  bad "pre-rebuild phase had failures; not rebuilding"
  printf '\nRECOVERY: aborted before rebuild. pass=%d fail=%d\n' "$pass_count" "$fail_count"
  printf '%s\n' "${checklist[@]}" >"$run_dir/checklist.txt"
  exit 4
fi

# =========================================================================
# 4. Rebuild — bounded by the failure policy
# =========================================================================
if (( skip_rebuild == 1 )); then
  info "rebuild skipped by request"
else
  [[ -n "$hypothesis" ]] || {
    printf 'A rebuild requires --hypothesis explaining why this attempt differs.\n' >&2
    exit 2
  }
  last_hypothesis="$(tail -n1 "$attempts_file" 2>/dev/null | python3 -c '
import json, sys
try: print(json.loads(sys.stdin.read() or "{}").get("hypothesis", ""))
except Exception: print("")' 2>/dev/null || printf '')"
  if [[ -n "$last_hypothesis" && "$last_hypothesis" == "$hypothesis" ]]; then
    printf 'Refusing: the previous rebuild used the same hypothesis.\n' >&2
    printf 'Repeating a failed action without changing the method is prohibited.\n' >&2
    exit 5
  fi
  printf '{"ts":"%s","hypothesis":%s,"phase_before":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$hypothesis")" \
    "$phase_before" >>"$attempts_file"

  log "phase 4: rebuilding $SANDBOX"
  if nemoclaw "$SANDBOX" rebuild --yes >"$run_dir/rebuild.txt" 2>&1; then
    ok "rebuild command completed"
  else
    bad "rebuild command failed; see $run_dir/rebuild.txt"
    capture "logs-post-failure.txt" nemoclaw "$SANDBOX" logs
    capture "doctor-post-failure.txt" nemohermes "$SANDBOX" doctor --json
    {
      printf '# Rebuild failure comparison\n\n## Pre-rebuild phase\n%s\n\n' "$phase_before"
      printf '## Post-failure phase\n%s\n\n' "$(sandbox_phase)"
      printf '## Log delta\n```\n'
      diff <(tail -n 200 "$run_dir/logs-pre-rebuild.txt" 2>/dev/null) \
           <(tail -n 200 "$run_dir/logs-post-failure.txt" 2>/dev/null) || true
      printf '```\n'
    } >"$run_dir/rebuild-failure-analysis.md"
    printf '\nRECOVERY: rebuild failed. Evidence: %s\n' "$run_dir"
    printf 'Do not rebuild again without a new hypothesis.\n'
    printf '%s\n' "${checklist[@]}" >"$run_dir/checklist.txt"
    exit 6
  fi

  # 5. Wait for Provisioning to resolve, bounded.
  log "phase 5: waiting for $SANDBOX to become Ready (timeout ${READY_TIMEOUT}s)"
  waited=0
  phase="$(sandbox_phase)"
  while (( waited < READY_TIMEOUT )); do
    case "${phase,,}" in
      ready|running) break ;;
    esac
    sleep "$READY_POLL"
    waited=$(( waited + READY_POLL ))
    phase="$(sandbox_phase)"
  done
  if [[ "${phase,,}" == "ready" || "${phase,,}" == "running" ]]; then
    ok "sandbox reached phase $phase after ${waited}s"
  else
    bad "sandbox did not become Ready within ${READY_TIMEOUT}s (phase: $phase)"
    capture "logs-not-ready.txt" nemoclaw "$SANDBOX" logs
  fi
fi

status_json >"$run_dir/status-post-rebuild.json"

# =========================================================================
# 6. Process, ports and gateway
# =========================================================================
log "phase 6: process and listener validation"
capture "ports-post-rebuild.txt" ss -tulpn

api_listeners="$(ss -ltnH 'sport = :8642' 2>/dev/null | awk '{print $4}' || true)"
if [[ -z "$api_listeners" ]]; then
  bad "no listener on 8642"
elif grep -Evq '^(127\.0\.0\.1|\[::1\]):' <<<"$api_listeners"; then
  bad "port 8642 has a non-loopback listener"
else
  ok "port 8642 is bound loopback-only"
fi

dash_listeners="$(ss -ltnH 'sport = :18789' 2>/dev/null | awk '{print $4}' || true)"
if [[ -z "$dash_listeners" ]]; then
  info "port 18789 has no listener (dashboard optional)"
elif grep -Evq '^(127\.0\.0\.1|\[::1\]):' <<<"$dash_listeners"; then
  bad "port 18789 has a non-loopback listener"
else
  ok "port 18789 is bound loopback-only"
fi

pgrep -af 'hermes' >>"$run_dir/processes.txt" 2>/dev/null \
  && ok "a Hermes process exists" || bad "no Hermes process found"

curl -fsS --max-time 10 "$API_URL" >"$run_dir/api-health.txt" 2>&1 \
  && ok "Hermes API responds on 8642" || bad "Hermes API did not respond on 8642"
curl -fsS --max-time 10 "$DASHBOARD_URL" -o /dev/null 2>/dev/null \
  && ok "dashboard responds on 18789" || info "dashboard did not respond on 18789"

if [[ -e "$HOME/.nemoclaw/hermes-tool-gateway-broker.pid" ]] \
  && kill -0 "$(cat "$HOME/.nemoclaw/hermes-tool-gateway-broker.pid" 2>/dev/null)" 2>/dev/null; then
  ok "Hermes tool-gateway broker is running"
else
  bad "Hermes tool-gateway broker is not running"
fi

# =========================================================================
# 7. Provider route and the credential boundary (OSA Decision 1)
# =========================================================================
log "phase 7: model probe, routing and secret isolation"
if python3 -m hermes.cli models probe >"$run_dir/model-probe.json" 2>&1; then
  ok "model probe recorded HEALTHY provider health"
else
  bad "model probe did not report a healthy route (see model-probe.json)"
fi

route_provider="$(python3 -c '
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    print(data.get("provider", "unknown"))
except Exception:
    print("unknown")' "$run_dir/model-probe.json" 2>/dev/null || printf unknown)"
info "active provider route: $route_provider"

# The endpoint Hermes actually sees from inside the sandbox.
nemohermes "$SANDBOX" exec --no-stdin -- sh -lc \
  'printf "OPENAI_BASE_URL=%s\n" "${OPENAI_BASE_URL:-unset}"; printf "endpoint reachable: "; curl -fsS -o /dev/null -w "%{http_code}\n" https://inference.local/v1/models 2>&1 || echo unreachable' \
  >"$run_dir/in-sandbox-endpoint.txt" 2>&1 || true
if grep -q 'inference.local' "$run_dir/in-sandbox-endpoint.txt" 2>/dev/null; then
  ok "sandbox sees the host-side gateway endpoint"
else
  info "in-sandbox endpoint did not resolve to inference.local; see in-sandbox-endpoint.txt"
fi

# THE invariant. A visible provider credential fails the run outright.
# shellcheck disable=SC2016
key_probe="$(nemohermes "$SANDBOX" exec --no-stdin -- sh -lc \
  'if [ -z "${NVIDIA_INFERENCE_API_KEY:-}" ]; then echo ABSENT; else echo PRESENT; fi' 2>&1 || printf 'UNREADABLE')"
printf '%s\n' "$key_probe" >"$run_dir/secret-isolation.txt"

if grep -q 'ABSENT' <<<"$key_probe"; then
  ok "NVIDIA_INFERENCE_API_KEY is absent inside the sandbox"
elif grep -q 'PRESENT' <<<"$key_probe"; then
  bad "SECURITY FAILURE: NVIDIA_INFERENCE_API_KEY is present inside the sandbox"
  log "stopping the runtime per OSA Decision 1; Hermes is NOT healthy"
  nemoclaw "$SANDBOX" stop >>"$run_dir/secret-isolation.txt" 2>&1 || \
    nemohermes "$SANDBOX" stop >>"$run_dir/secret-isolation.txt" 2>&1 || true
  {
    printf '# VALIDATION FAILED — credential exposed inside the sandbox\n\n'
    printf -- '- provider route: %s\n' "$route_provider"
    printf -- '- runtime stopped: yes\n'
    printf -- '- required: restore the host-side Model Router or credential gateway\n'
    printf -- '- Hermes must NOT be marked healthy until the key is absent in-sandbox\n'
  } >"$run_dir/SECURITY-FAILURE.md"
  printf '\nRECOVERY: FAILED on the credential boundary. Evidence: %s\n' "$run_dir"
  printf '%s\n' "${checklist[@]}" >"$run_dir/checklist.txt"
  exit 7
else
  bad "could not determine whether the provider key is visible in-sandbox"
fi

# =========================================================================
# 8. A real inference request
# =========================================================================
log "phase 8: real inference request"
if nemohermes "$SANDBOX" exec --no-stdin -- hermes chat -q \
    'Reply with exactly: RECOVERY_PROBE_OK. Do not modify files or call external tools.' \
    >"$run_dir/inference-probe.txt" 2>&1; then
  if grep -q 'RECOVERY_PROBE_OK' "$run_dir/inference-probe.txt"; then
    ok "a real inference request succeeded"
  else
    bad "inference returned without the expected marker; see inference-probe.txt"
  fi
else
  bad "the real inference request failed"
fi

# Web/research tool health, reported truthfully either way.
nemohermes "$SANDBOX" exec --no-stdin -- hermes chat -q \
  'List only the tool names available to you right now, one per line. If none, reply NONE.' \
  >"$run_dir/tool-inventory.txt" 2>&1 || true
if grep -qiE 'web|search|research|browse' "$run_dir/tool-inventory.txt" 2>/dev/null; then
  ok "web/research tooling reports as available in-sandbox"
else
  info "web/research tooling is NOT available in-sandbox (recorded as unavailable, not assumed)"
fi

# =========================================================================
# 9. GREEN / YELLOW / RED execution tests
# =========================================================================
log "phase 9: permission execution tests"
green_plan="$(python3 -m hermes.cli permissions classify shell inspect \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["dispatch_plan"])')"
[[ "$green_plan" == "DISPATCH" ]] && ok "GREEN dispatches without approval" \
  || bad "GREEN did not dispatch (plan: $green_plan)"

yellow_plan="$(python3 -m hermes.cli permissions classify git push --rollback \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["dispatch_plan"])')"
[[ "$yellow_plan" == "CHECKPOINT_AUDIT_DISPATCH" ]] \
  && ok "YELLOW checkpoints, audits and dispatches" \
  || bad "YELLOW did not follow the audit path (plan: $yellow_plan)"

python3 -m hermes.cli queue enqueue "recovery-red-$stamp" "recovery-$stamp" email send \
  --payload '{"to":"prospect@example.invalid"}' >"$run_dir/red-task.json" 2>&1 || true
red_status="$(python3 -c '
import json, sys
try: print(json.load(open(sys.argv[1]))["task"]["status"])
except Exception: print("unknown")' "$run_dir/red-task.json")"
[[ "$red_status" == "WAITING_FOR_APPROVAL" ]] && ok "RED blocks for scoped approval" \
  || bad "RED did not block (status: $red_status)"

python3 -m hermes.cli queue approve "recovery-red-$stamp" --approver OSA --expires-minutes 15 \
  >"$run_dir/red-approval.json" 2>&1 || true
approved_status="$(python3 -c '
import json, sys
try: print(json.load(open(sys.argv[1]))["approved"]["status"])
except Exception: print("unknown")' "$run_dir/red-approval.json")"
[[ "$approved_status" == "QUEUED" ]] && ok "RED resumes only after scoped approval" \
  || bad "scoped approval did not resume the RED task (status: $approved_status)"
python3 -m hermes.cli queue cancel "recovery-red-$stamp" --reason "recovery test complete" \
  >/dev/null 2>&1 || true

# =========================================================================
# 10. Restart recovery and persistence
# =========================================================================
log "phase 10: controlled restart and persistence"
queue_before="$(python3 -m hermes.cli queue stats 2>/dev/null | sha256sum | cut -d' ' -f1)"
ledger_before="$(python3 -m hermes.cli ledger verify 2>/dev/null | head -c 200 || printf '')"

nemoclaw "$SANDBOX" restart >"$run_dir/restart.txt" 2>&1 || \
  nemohermes "$SANDBOX" restart >>"$run_dir/restart.txt" 2>&1 || true
waited=0
while (( waited < RESTART_TIMEOUT )); do
  phase="$(sandbox_phase)"
  case "${phase,,}" in ready|running) break ;; esac
  sleep 5; waited=$(( waited + 5 ))
done
[[ "${phase,,}" == "ready" || "${phase,,}" == "running" ]] \
  && ok "sandbox recovered after a controlled restart (${waited}s)" \
  || bad "sandbox did not recover after restart (phase: $phase)"

queue_after="$(python3 -m hermes.cli queue stats 2>/dev/null | sha256sum | cut -d' ' -f1)"
[[ "$queue_before" == "$queue_after" ]] && ok "queue state survived the restart" \
  || bad "queue state changed across the restart"

if python3 -m hermes.cli ledger verify >/dev/null 2>&1; then
  ok "evidence ledger chain verifies after the restart"
else
  [[ -z "$ledger_before" ]] && info "ledger not initialised; nothing to verify" \
    || bad "evidence ledger chain broke across the restart"
fi

# =========================================================================
# 11. Evidence bundle
# =========================================================================
log "phase 11: evidence bundle"
if HERMES_EVIDENCE_ROOT="${HERMES_EVIDENCE_ROOT:-${HYDRA_BASE_PATH:-/opt/hydra}/evidence}" \
   "$repo_root/scripts/evidence-bundle.sh" >"$run_dir/evidence.txt" 2>&1; then
  ok "evidence bundle generated"
else
  bad "evidence bundle generation failed"
fi
cp -a "$run_dir"/*.md "$run_dir"/*.json "$run_dir"/*.txt \
  "${HERMES_EVIDENCE_ROOT:-${HYDRA_BASE_PATH:-/opt/hydra}/evidence}/latest/" 2>/dev/null || true

printf '%s\n' "${checklist[@]}" >"$run_dir/checklist.txt"
{
  printf '# Recovery Result — %s\n\n' "$stamp"
  printf -- '- sandbox: %s\n' "$SANDBOX"
  printf -- '- phase before: %s\n' "$phase_before"
  printf -- '- phase after: %s\n' "$(sandbox_phase)"
  printf -- '- provider route: %s\n' "$route_provider"
  printf -- '- checks passed: %d, failed: %d\n\n' "$pass_count" "$fail_count"
  printf '## Checklist\n\n```\n%s\n```\n' "$(printf '%s\n' "${checklist[@]}")"
} >"$run_dir/RESULT.md"

printf '\nRECOVERY: pass=%d fail=%d evidence=%s\n' "$pass_count" "$fail_count" "$run_dir"
(( fail_count == 0 ))

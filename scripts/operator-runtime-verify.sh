#!/usr/bin/env bash
# Read-only verification of the runtime. Every check prints PASS, FAIL, UNKNOWN
# or N/A. Nothing is inferred from configuration alone: a recorded dashboardPort
# is not a listening dashboard, and a registered route is not a working one.
set -Eeuo pipefail
umask 077

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/operator-lib.sh
source "$HERE/operator-lib.sh"

require_host
RUN_DIR="$(new_run_dir runtime-verify)"
exec > >(tee -a "$RUN_DIR/verify.txt") 2>&1

FAILURES=0
say() {
  case "$1" in
    PASS) ok "$2" "${3:-}" ;;
    FAIL) bad "$2" "${3:-}"; FAILURES=$((FAILURES + 1)) ;;
    UNKNOWN) unk "$2" "${3:-}" ;;
    *) na "$2" "${3:-}" ;;
  esac
}
listening() { ss -tulpn 2>/dev/null | grep -qE "[:.]$1\b"; }
json_field() { grep -oE "\"$2\"[[:space:]]*:[[:space:]]*\"?[^,\"}]+\"?" <<<"$1" | head -1 | sed -E 's/.*:[[:space:]]*"?([^"]*)"?$/\1/'; }

printf 'HYDRA RUNTIME VERIFY  utc=%s\n\n' "$(utc)"

# -- host and CLI ----------------------------------------------------------
say PASS HOST_IDENTITY "$(hostname -s) / $(id -un)"
command -v nemoclaw >/dev/null && command -v nemohermes >/dev/null \
  && say PASS NEMOCLAW_CLI || say FAIL NEMOCLAW_CLI "nemoclaw or nemohermes not in PATH"

listening 8080 && say PASS OPENSHELL_GATEWAY "port 8080" || say FAIL OPENSHELL_GATEWAY "8080 not listening"
listening 4000 && say PASS MODEL_ROUTER "port 4000" || say FAIL MODEL_ROUTER "4000 not listening"
listening 8787 && say PASS HYDRA_CONTROL_PLANE "port 8787" || say FAIL HYDRA_CONTROL_PLANE "8787 not listening"

# -- sandbox ---------------------------------------------------------------
STATUS_JSON="$(nemohermes "$SANDBOX" status --json 2>/dev/null || true)"
if [[ -z "$STATUS_JSON" ]]; then
  say UNKNOWN SANDBOX_FOUND "status --json returned nothing"
  say UNKNOWN SANDBOX_READY
else
  printf '%s' "$STATUS_JSON" | redact >"$RUN_DIR/sandbox-status.json"
  [[ "$(json_field "$STATUS_JSON" found)" == "true" ]] \
    && say PASS SANDBOX_FOUND || say FAIL SANDBOX_FOUND
  PHASE="$(json_field "$STATUS_JSON" phase)"
  case "${PHASE,,}" in
    ready|running) say PASS SANDBOX_READY "phase=$PHASE" ;;
    "") say UNKNOWN SANDBOX_READY "phase field absent" ;;
    *) say FAIL SANDBOX_READY "phase=$PHASE" ;;
  esac
fi

# -- route and model -------------------------------------------------------
ROUTE_JSON="$(nemoclaw inference get --json 2>/dev/null || true)"
if [[ -z "$ROUTE_JSON" ]]; then
  say UNKNOWN PROVIDER_MATCH; say UNKNOWN MODEL_MATCH; say UNKNOWN INFERENCE_ENDPOINT
else
  printf '%s' "$ROUTE_JSON" | redact >"$RUN_DIR/inference-route.json"
  [[ "$ROUTE_JSON" == *"$EXPECTED_PROVIDER"* ]] \
    && say PASS PROVIDER_MATCH "$EXPECTED_PROVIDER" \
    || say FAIL PROVIDER_MATCH "expected $EXPECTED_PROVIDER"
  [[ "$ROUTE_JSON" == *"$EXPECTED_MODEL"* ]] \
    && say PASS MODEL_MATCH "$EXPECTED_MODEL" \
    || say FAIL MODEL_MATCH "expected $EXPECTED_MODEL"

  HTTP="$(nemohermes "$SANDBOX" exec --no-stdin -- sh -lc \
    'curl -fsS --max-time 15 -o /dev/null -w "%{http_code}" https://inference.local/v1/models' 2>/dev/null || true)"
  [[ "$HTTP" == "200" ]] \
    && say PASS INFERENCE_ENDPOINT "HTTP $HTTP" \
    || say FAIL INFERENCE_ENDPOINT "HTTP ${HTTP:-no-response}"
fi

# -- credential isolation --------------------------------------------------
# The value is never printed; only presence or absence is reported.
ISO="$(nemohermes "$SANDBOX" exec --no-stdin -- sh -lc \
  'if [ -z "${NVIDIA_INFERENCE_API_KEY:-}" ]; then echo ABSENT; else echo PRESENT; fi' 2>/dev/null || true)"
case "$ISO" in
  ABSENT)  say PASS CREDENTIAL_ISOLATION "key ABSENT in sandbox" ;;
  PRESENT) say FAIL CREDENTIAL_ISOLATION "SECURITY FAILURE: key PRESENT in sandbox — stop and escalate to OSA" ;;
  *)       say UNKNOWN CREDENTIAL_ISOLATION "probe did not answer; isolation is NOT demonstrated" ;;
esac

# -- real inference --------------------------------------------------------
REPLY="$(nemohermes "$SANDBOX" exec --no-stdin -- \
  hermes chat -q 'Reply exactly: HERMES_RUNTIME_OK' 2>/dev/null | tr -d '\r' | redact || true)"
printf '%s\n' "$REPLY" >"$RUN_DIR/inference-reply.txt"
if grep -qx 'HERMES_RUNTIME_OK' <<<"$REPLY"; then
  say PASS REAL_INFERENCE
elif [[ -z "$REPLY" ]]; then
  say UNKNOWN REAL_INFERENCE "no reply"
else
  say FAIL REAL_INFERENCE "reply did not match exactly"
fi

# -- APIs ------------------------------------------------------------------
if listening 8642; then
  curl -fsS --max-time 10 -o /dev/null http://127.0.0.1:8642/health 2>/dev/null \
    && say PASS HERMES_API "8642 /health" || say FAIL HERMES_API "8642 listening, /health failed"
else
  say FAIL HERMES_API "8642 not listening"
fi

# A recorded dashboardPort is not evidence. Both the listener and an HTTP answer
# are required.
if listening 18789; then
  curl -fsS --max-time 10 -o /dev/null http://127.0.0.1:18789/ 2>/dev/null \
    && say PASS HERMES_DASHBOARD "18789 answers HTTP" \
    || say FAIL HERMES_DASHBOARD "18789 listening but no HTTP answer"
else
  say FAIL HERMES_DASHBOARD "18789 not listening (config value alone is not proof)"
fi

# -- worker ----------------------------------------------------------------
if systemctl list-unit-files --no-pager --no-legend 2>/dev/null | grep -q '^hydra-hermes-worker\.service'; then
  ACTIVE="$(systemctl is-active hydra-hermes-worker.service 2>/dev/null || true)"
  [[ "$ACTIVE" == "active" ]] && say PASS WORKER_SERVICE "active" || say FAIL WORKER_SERVICE "is-active=$ACTIVE"
  ENABLED="$(systemctl is-enabled hydra-hermes-worker.service 2>/dev/null || true)"
  [[ "$ENABLED" == "enabled" ]] && say PASS WORKER_ENABLED || say FAIL WORKER_ENABLED "is-enabled=$ENABLED"
  say PASS REBOOT_PERSISTENCE_CONFIG "WantedBy=multi-user.target, is-enabled=$ENABLED"

  HB="$(journalctl -u hydra-hermes-worker.service --since '15 minutes ago' --no-pager 2>/dev/null \
        | grep -Ec 'HEALTHY_IDLE|cycle|heartbeat' || true)"
  [[ "${HB:-0}" -gt 0 ]] && say PASS WORKER_HEARTBEAT "$HB entries/15min" \
    || say UNKNOWN WORKER_HEARTBEAT "no heartbeat lines in the last 15 minutes"
  journalctl -u hydra-hermes-worker.service --no-pager --lines=50 2>/dev/null | redact >"$RUN_DIR/worker-journal.txt" || true
  say PASS JOURNAL "captured"
else
  say FAIL WORKER_SERVICE "unit not installed"
  say FAIL WORKER_ENABLED "unit not installed"
  say UNKNOWN WORKER_HEARTBEAT
  say UNKNOWN JOURNAL
  say FAIL REBOOT_PERSISTENCE_CONFIG "unit not installed"
fi

# -- circuit breaker -------------------------------------------------------
BREAKER="${HERMES_WORKER_STATE_DIR:-/var/lib/hydra-hermes}/circuit-breaker"
if [[ -e "$BREAKER" ]]; then
  say FAIL CIRCUIT_BREAKER "breaker is TRIPPED ($BREAKER)"
elif [[ -d "${HERMES_WORKER_STATE_DIR:-/var/lib/hydra-hermes}" ]]; then
  say PASS CIRCUIT_BREAKER "not tripped"
else
  say UNKNOWN CIRCUIT_BREAKER "state directory absent"
fi

printf '\nfailures=%s evidence=%s\n' "$FAILURES" "$RUN_DIR"
[[ $FAILURES -eq 0 ]] || exit 1

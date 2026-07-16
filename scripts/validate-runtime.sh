#!/usr/bin/env bash
# shellcheck disable=SC2015
set -Eeuo pipefail

SANDBOX="hydra-hermes-lab"
failures=0
pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; failures=$((failures + 1)); }

for cli in nemoclaw nemohermes openshell; do
  if command -v "$cli" >/dev/null 2>&1; then pass "$cli: $($cli --version 2>/dev/null | head -n1 || printf installed)"; else fail "$cli unavailable"; fi
done
(( failures == 0 )) || exit 1

status_json="$(nemohermes "$SANDBOX" status --json)" || { fail "sandbox status"; exit 1; }
python3 -c '
import json, sys
d=json.load(sys.stdin)
assert d.get("name") == sys.argv[1]
assert d.get("agent") == "hermes"
assert str(d.get("phase", "")).lower() in {"ready", "running"}
route=d.get("liveRoute") or d.get("recordedRoute") or {}
provider=route.get("provider") or d.get("provider")
assert provider in {"nvidia-router", "routed"}
' "$SANDBOX" <<<"$status_json" || { fail "sandbox identity/readiness/provider"; exit 1; }
pass "sandbox identity, readiness, and routed provider"

[[ "$(hostname -s)" == hydra-hermes-runtime-01 ]] && pass "runtime host identity" || fail "unexpected runtime hostname"

nemohermes "$SANDBOX" doctor --json >/dev/null && pass "doctor" || fail "doctor"

route_json="$(nemoclaw inference get --json)" || { fail "active inference route"; route_json='{}'; }
python3 -c '
import json, sys
d=json.load(sys.stdin)
assert d.get("provider") in {"nvidia-router", "routed"}
' <<<"$route_json" && pass "active route: nvidia-router" || fail "active route is not nvidia-router"

nemohermes "$SANDBOX" exec --no-stdin -- sh -lc \
  'curl -fsS https://inference.local/v1/models >/dev/null' \
  && pass "inference.local route responds inside sandbox" \
  || fail "inference.local route did not respond inside sandbox"

# The expression must expand inside the sandbox, not in this host shell.
# shellcheck disable=SC2016
nemohermes "$SANDBOX" exec --no-stdin -- sh -lc 'test -z "${NVIDIA_INFERENCE_API_KEY:-}"' \
  && pass "raw NVIDIA key unavailable inside sandbox" \
  || fail "raw NVIDIA key appears available inside sandbox"

dashboard="$(nemohermes "$SANDBOX" dashboard-url --quiet)" || { fail "dashboard URL"; dashboard=""; }
[[ "$dashboard" == http://127.0.0.1:* || "$dashboard" == https://127.0.0.1:* ]] \
  && pass "dashboard URL available on loopback" \
  || fail "dashboard URL is missing or not loopback-bound"

if command -v ss >/dev/null 2>&1; then
  for port in 4000 8642 18789; do
    listeners="$(ss -ltnH "sport = :$port" 2>/dev/null | awk '{print $4}' || true)"
    [[ -n "$listeners" ]] || { fail "expected runtime listener missing on port $port"; continue; }
    if grep -Evq '^(127\.0\.0\.1|\[::1\]):' <<<"$listeners"; then
      fail "port $port has a non-loopback listener"
    else
      pass "port $port: loopback-only"
    fi
  done
else
  fail "ss unavailable; cannot validate listener exposure"
fi

printf 'MANUAL GATE: run the controlled first prompt from docs/VALIDATION_PLAN.md.\n'
printf 'Result: failures=%d; first-prompt=PENDING\n' "$failures"
(( failures == 0 ))

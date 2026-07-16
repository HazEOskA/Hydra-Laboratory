#!/usr/bin/env bash
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

nemohermes "$SANDBOX" doctor --json >/dev/null && pass "doctor" || fail "doctor"

route_json="$(nemoclaw inference get --json)" || { fail "active inference route"; route_json='{}'; }
python3 -c '
import json, sys
d=json.load(sys.stdin)
assert d.get("provider") in {"nvidia-router", "routed"}
' <<<"$route_json" && pass "active route: nvidia-router" || fail "active route is not nvidia-router"

nemohermes "$SANDBOX" exec --no-stdin -- sh -lc 'test -z "${NVIDIA_INFERENCE_API_KEY:-}"' \
  && pass "raw NVIDIA key unavailable inside sandbox" \
  || fail "raw NVIDIA key appears available inside sandbox"

dashboard="$(nemohermes "$SANDBOX" dashboard-url --quiet)" || { fail "dashboard URL"; dashboard=""; }
[[ "$dashboard" == http://127.0.0.1:* || "$dashboard" == https://127.0.0.1:* ]] \
  && pass "dashboard URL available on loopback" \
  || fail "dashboard URL is missing or not loopback-bound"

printf 'MANUAL GATE: run the controlled first prompt from docs/VALIDATION_PLAN.md.\n'
printf 'Result: failures=%d; first-prompt=PENDING\n' "$failures"
(( failures == 0 ))

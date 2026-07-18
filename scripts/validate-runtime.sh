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

curl -fsS http://127.0.0.1:8642/health >/dev/null \
  && pass "Hermes API health responds on loopback port 8642" \
  || fail "Hermes API health did not respond on loopback port 8642"

if command -v ss >/dev/null 2>&1; then
  router_listeners="$(ss -ltnH "sport = :4000" 2>/dev/null | awk '{print $4}' || true)"
  [[ -n "$router_listeners" ]] && pass "Model Router listener present on port 4000" || fail "Model Router listener missing on port 4000"

  api_listeners="$(ss -ltnH "sport = :8642" 2>/dev/null | awk '{print $4}' || true)"
  if [[ -z "$api_listeners" ]]; then
    fail "Hermes API listener missing on port 8642"
  elif grep -Evq '^(127\\.0\\.0\\.1|\\[::1\\]):' <<<"$api_listeners"; then
    fail "Hermes API port 8642 has a non-loopback listener"
  else
    pass "Hermes API port 8642: loopback-only"
  fi

  dashboard_listeners="$(ss -ltnH "sport = :18789" 2>/dev/null | awk '{print $4}' || true)"
  if [[ -z "$dashboard_listeners" ]]; then
    pass "OpenClaw dashboard port 18789 unused by Hermes"
  elif grep -Evq '^(127\\.0\\.0\\.1|\\[::1\\]):' <<<"$dashboard_listeners"; then
    fail "optional port 18789 has a non-loopback listener"
  else
    pass "optional port 18789: loopback-only"
  fi
else
  fail "ss unavailable; cannot validate listener exposure"
fi

ufw_status="$(sudo -n ufw status 2>/dev/null || true)"
grep -Eq '^172\\.18\\.0\\.1[[:space:]]+4000/tcp[[:space:]]+ALLOW[[:space:]]+172\\.18\\.0\\.0/16' <<<"$ufw_status" \
  && pass "UFW restricts Model Router 4000 to OpenShell Docker bridge" \
  || fail "missing scoped UFW rule for Model Router 4000"
grep -Eq '^172\\.18\\.0\\.1[[:space:]]+8080/tcp[[:space:]]+ALLOW[[:space:]]+172\\.18\\.0\\.0/16' <<<"$ufw_status" \
  && pass "UFW restricts OpenShell gateway 8080 to Docker bridge" \
  || fail "missing scoped UFW rule for OpenShell gateway 8080"

printf 'MANUAL GATE: run the controlled first prompt from docs/VALIDATION_PLAN.md.\n'
printf 'Result: failures=%d; first-prompt=PENDING\n' "$failures"
(( failures == 0 ))

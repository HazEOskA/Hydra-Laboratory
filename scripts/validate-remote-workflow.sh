#!/usr/bin/env bash
set -Eeuo pipefail

workflow=".github/workflows/remote-preflight.yml"
preflight="scripts/remote-preflight.sh"
failures=0

pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*" >&2; failures=$((failures + 1)); }
require_text() {
  if grep -Fq -- "$2" "$1"; then pass "$1 contains $2"; else fail "$1 missing $2"; fi
}

if [[ -s "$workflow" ]]; then pass "$workflow exists"; else fail "$workflow is missing"; fi
require_text "$workflow" "workflow_dispatch:"
require_text "$workflow" "contents: read"
require_text "$workflow" "id-token: write"
require_text "$workflow" "if: github.ref == 'refs/heads/main'"

if grep -Eq '^[[:space:]]+(push|pull_request|schedule|workflow_call):' "$workflow"; then
  fail "remote workflow contains a forbidden automatic trigger"
else
  pass "remote workflow uses no automatic trigger"
fi

permission_block="$(awk '/^permissions:/{capture=1; next} capture && /^[^ ]/{exit} capture{print}' "$workflow")"
if [[ "$(grep -Ec '^[[:space:]]+[a-z-]+:' <<<"$permission_block")" -eq 2 ]] \
  && grep -Eq '^[[:space:]]+contents:[[:space:]]+read$' <<<"$permission_block" \
  && grep -Eq '^[[:space:]]+id-token:[[:space:]]+write$' <<<"$permission_block"; then
  pass "workflow permissions are minimal"
else
  fail "workflow permissions must be exactly contents: read and id-token: write"
fi

for secret in HYDRA_SSH_HOST HYDRA_SSH_USER HYDRA_SSH_PRIVATE_KEY HYDRA_SSH_KNOWN_HOSTS TS_OAUTH_CLIENT_ID; do
  require_text "$workflow" "secrets.$secret"
done
require_text "$workflow" "vars.HYDRA_SSH_PORT || '22'"
require_text "$workflow" "vars.TS_AUDIENCE"
require_text "$workflow" "vars.TS_TAGS"
require_text "$workflow" "tailscale/github-action@780049a30b6ff5c378a9e7b389d15ece7a204888"

if grep -Eq '^[[:space:]]+environment:' "$workflow"; then
  fail "private-repository workflow must not depend on a GitHub Environment"
else
  pass "workflow uses private-repository-compatible repository secrets"
fi

if grep -Eq 'oauth-secret:|TS_OAUTH_SECRET|authkey:' "$workflow"; then
  fail "Tailscale must use OIDC without a reusable OAuth secret or auth key"
else
  pass "Tailscale authentication is OIDC-only"
fi

for option in \
  'BatchMode=yes' \
  'StrictHostKeyChecking=yes' \
  'IdentitiesOnly=yes' \
  'IdentityAgent=none' \
  'ForwardAgent=no' \
  'ClearAllForwardings=yes' \
  'PasswordAuthentication=no' \
  'KbdInteractiveAuthentication=no'; do
  require_text "$workflow" "$option"
done

if grep -Eq 'ssh-keyscan|set[[:space:]]+-x|appleboy/|webfactory/ssh-agent' "$workflow"; then
  fail "workflow contains a forbidden SSH trust or logging pattern"
else
  pass "workflow contains no forbidden SSH trust or logging pattern"
fi

if grep -Eq '(^|[[:space:]])sudo([[:space:]]|$)|apt(-get)?[[:space:]]|nemoclaw[[:space:]]+install|nemohermes[[:space:]]+onboard' "$workflow"; then
  fail "workflow contains a mutation or elevation command"
else
  pass "workflow contains no mutation or elevation command"
fi

report_mode="$(awk '/^github_report\(\)/,/^if \[\[ .*--github-report/' "$preflight")"
if grep -Eq '(^|[[:space:]])sudo([[:space:]]|$)|systemctl[[:space:]]+(start|stop|restart|reload|enable|disable)|apt(-get)?[[:space:]]|git[[:space:]]+(clone|pull|fetch|checkout|switch|reset)' <<<"$report_mode"; then
  fail "GitHub report mode contains mutation, elevation, or repository writes"
else
  pass "GitHub report mode is read-only"
fi

for field in 'REMOTE SSH' HOSTNAME 'PUBLIC IP' OS ARCHITECTURE CPU RAM DISK FIREWALL DOCKER 'USER HYDRA' 'REPOSITORY ACCESS' NEMOCLAW NEMOHERMES OPENSHELL 'PORT 4000' 'PORT 8642' 'PORT 18789' 'APR UNTOUCHED' OVERALL; do
  require_text "$preflight" "printf '$field:"
done

printf 'REMOTE WORKFLOW VALIDATION: failures=%d\n' "$failures"
(( failures == 0 ))

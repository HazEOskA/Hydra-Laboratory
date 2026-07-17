#!/usr/bin/env bash
# shellcheck disable=SC2015
set -Eeuo pipefail

cloud_init="infra/cloud-init.yaml"
workflow=".github/workflows/remote-preflight.yml"
failures=0

pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*" >&2; failures=$((failures + 1)); }
line_of() { grep -nF -- "$2" "$1" | head -n1 | cut -d: -f1; }

install_line="$(line_of "$cloud_init" 'apt-get install -y tailscale')"
daemon_line="$(line_of "$cloud_init" 'systemctl enable --now tailscaled')"
enroll_line="$(line_of "$cloud_init" 'tailscale up \')"
interface_line="$(line_of "$cloud_init" 'ip link show tailscale0')"
online_line="$(line_of "$cloud_init" '.BackendState == "Running"')"
ufw_line="$(line_of "$cloud_init" 'ufw --force enable')"
docker_line="$(line_of "$cloud_init" 'systemctl enable --now docker')"

if [[ -n "$install_line" && -n "$daemon_line" && -n "$enroll_line" \
  && -n "$interface_line" && -n "$online_line" && -n "$ufw_line" && -n "$docker_line" ]] \
  && (( install_line < daemon_line \
        && daemon_line < enroll_line \
        && enroll_line < interface_line \
        && interface_line < online_line \
        && online_line < ufw_line \
        && ufw_line < docker_line )); then
  pass 'Tailscale enrollment and validation strictly precede UFW and runtime setup'
else
  fail 'bootstrap ordering contract is broken'
fi

if [[ "$(grep -Fc 'ufw --force enable' "$cloud_init")" -eq 1 ]]; then
  pass 'UFW has exactly one activation point behind the validation gates'
else
  fail 'UFW activation count changed'
fi

for required in \
  'https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg' \
  'https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list' \
  '--auth-key="file:${auth_file}"' \
  '--hostname="$expected_hostname"' \
  '--advertise-tags="$expected_tag"' \
  '--ssh=false' \
  'expected_tag="tag:hydra-runtime"' \
  'test -s /var/lib/tailscale/tailscaled.state' \
  'redact_cloud_cache' \
  '[REDACTED-ONE-OFF-AUTH-KEY]' \
  "ufw allow in on tailscale0 to any port 22 proto tcp"; do
  grep -Fq -- "$required" "$cloud_init" && pass "cloud-init contains $required" || fail "missing $required"
done

if grep -Eq -- '--ephemeral([=[:space:]]|$)|tailscale[[:space:]]+set[[:space:]]+--ssh([^=]|$)' "$cloud_init"; then
  fail 'persistent host contract or Tailscale SSH policy violated'
else
  pass 'no ephemeral enrollment and no Tailscale SSH enablement'
fi

if grep -Eq 'ufw[[:space:]]+allow([[:space:]]+in)?[[:space:]]+(22|ssh)|ufw[[:space:]]+allow[[:space:]]+from[[:space:]]+any.*(22|ssh)' "$cloud_init"; then
  fail 'public SSH UFW rule detected'
else
  pass 'no public SSH UFW rule'
fi

if [[ "$(grep -Foc '__TS_RUNTIME_AUTH_KEY_B64__' "$cloud_init")" -eq 1 ]]; then
  pass 'secret-free rendering marker is intact'
else
  fail 'secret-free rendering marker count changed'
fi

printf -v key_prefix '%s%s' 'ts' 'key-'
if git grep -nF -- "$key_prefix" -- . ':(exclude)scripts/secret-scan.sh' ':(exclude)tests/test-tailscale-bootstrap.sh' >/dev/null; then
  fail 'possible real Tailscale credential prefix committed'
else
  pass 'no Tailscale auth-key material committed'
fi

if [[ "$(grep -Ec '^[[:space:]]+workflow_dispatch:' "$workflow")" -eq 1 ]] \
  && ! grep -Eq '^[[:space:]]+(push|pull_request|schedule|workflow_call):' "$workflow"; then
  pass 'remote workflow remains workflow_dispatch-only'
else
  fail 'remote workflow trigger contract changed'
fi

grep -Fq 'tailscale/github-action@780049a30b6ff5c378a9e7b389d15ece7a204888' "$workflow" \
  && pass 'Tailscale GitHub Action remains pinned' \
  || fail 'Tailscale GitHub Action pin changed'

rendered="/tmp/hydra-cloud-init-render-test.$$"
rm -f -- "$rendered"
printf -v TS_RUNTIME_AUTH_KEY '%s' 'unit-test-placeholder-not-a-real-key'
export TS_RUNTIME_AUTH_KEY
if scripts/render-cloud-init.sh --output "$rendered" >/dev/null \
  && [[ -s "$rendered" ]] \
  && [[ "$(stat -c '%a' "$rendered")" == 600 ]] \
  && ! grep -Fq '__TS_RUNTIME_AUTH_KEY_B64__' "$rendered"; then
  pass 'renderer produces only a protected out-of-repository artifact'
else
  fail 'renderer contract failed'
fi

repo_rendered="$PWD/cloud-init.test.rendered.yaml"
rm -f -- "$repo_rendered"
if ! scripts/render-cloud-init.sh --output "$repo_rendered" >/dev/null 2>&1 \
  && [[ ! -e "$repo_rendered" ]]; then
  pass 'renderer refuses to place secret-bearing output in the repository'
else
  fail 'renderer accepted repository-local output'
fi
unset TS_RUNTIME_AUTH_KEY
rm -f -- "$rendered"

printf 'TAILSCALE BOOTSTRAP TEST: failures=%d\n' "$failures"
(( failures == 0 ))

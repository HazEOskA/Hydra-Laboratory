#!/usr/bin/env bash
# shellcheck disable=SC2015
set -Eeuo pipefail

readonly expected_hostname="hydra-hermes-runtime-01"
readonly expected_tag="tag:hydra-runtime"
failures=0

pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'BLOCK %s\n' "$*" >&2; failures=$((failures + 1)); }

command -v tailscale >/dev/null 2>&1 && pass 'tailscale CLI installed' || fail 'tailscale CLI missing'
command -v jq >/dev/null 2>&1 && pass 'jq installed' || fail 'jq missing'
systemctl is-enabled --quiet tailscaled && pass 'tailscaled enabled' || fail 'tailscaled not enabled'
systemctl is-active --quiet tailscaled && pass 'tailscaled active' || fail 'tailscaled not active'
ip link show tailscale0 >/dev/null 2>&1 && pass 'tailscale0 exists' || fail 'tailscale0 missing'

if command -v tailscale >/dev/null 2>&1 && [[ -n "$(tailscale ip 2>/dev/null)" ]]; then
  pass 'Tailscale address assigned'
else
  fail 'Tailscale address missing'
fi

status_file="$(mktemp)"
trap 'rm -f -- "$status_file"' EXIT
if tailscale status --json > "$status_file" 2>/dev/null \
  && jq -e \
    --arg host "$expected_hostname" \
    --arg tag "$expected_tag" \
    '.BackendState == "Running"
     and .Self.Online == true
     and .Self.HostName == $host
     and ((.Self.TailscaleIPs // []) | length > 0)
     and ((.Self.Tags // []) == [$tag])' \
    "$status_file" >/dev/null; then
  pass 'persistent runtime node is online with exact hostname and tag'
else
  fail 'online hostname/tag/address contract not satisfied'
fi

if [[ -s /var/lib/tailscale/tailscaled.state ]]; then
  pass 'persistent tailscaled state exists'
else
  fail 'persistent tailscaled state is missing or unreadable'
fi

if tailscale status --json 2>/dev/null | grep -Fq '"RunSSH": true'; then
  fail 'Tailscale SSH must remain disabled'
else
  pass 'Tailscale SSH is not enabled'
fi

printf 'TAILSCALE HOST VALIDATION: failures=%d\n' "$failures"
(( failures == 0 ))

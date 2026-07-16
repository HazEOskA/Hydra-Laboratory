#!/usr/bin/env bash
# shellcheck disable=SC2015
set -Eeuo pipefail

failures=0
pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; failures=$((failures + 1)); }
require_text() { grep -Fq -- "$2" "$1" && pass "$1 contains $2" || fail "$1 missing $2"; }

spec="infra/hetzner/server-spec.yaml"
firewall="infra/hetzner/firewall-rules.yaml"
cloud_init="infra/cloud-init.yaml"

for file in "$spec" "$firewall" "$cloud_init"; do
  [[ -s "$file" ]] && pass "$file exists" || fail "$file is missing or empty"
done

require_text "$spec" "server_type: cx43"
require_text "$spec" "architecture: x86_64"
require_text "$spec" "image: ubuntu-24.04"
require_text "$spec" "shared_vcpu: 8"
require_text "$spec" "ram_gb: 16"
require_text "$spec" "disk_gb: 160"
require_text "$spec" "- nbg1"
require_text "$spec" "- fsn1"
require_text "$spec" "gpu_required: false"
require_text "$spec" "sandbox: hydra-hermes-lab"
require_text "$spec" "inference_provider: routed"

if awk '/^inbound:/,/^outbound:/' "$firewall" | grep -Eq 'port:[[:space:]]*22'; then
  fail "public provider firewall must not allow SSH"
else
  pass "public provider firewall has no SSH allow rule"
fi
for port in 22 4000 8642 18789; do
  require_text "$firewall" "- $port"
  if awk '/^inbound:/,/^outbound:/' "$firewall" | grep -Eq "port:[[:space:]]*$port"; then
    fail "port $port must not have an inbound allow rule"
  else
    pass "port $port has no inbound allow rule"
  fi
done

require_text "$cloud_init" "hostname: hydra-hermes-runtime-01"
require_text "$cloud_init" "PermitRootLogin no"
require_text "$cloud_init" "PasswordAuthentication no"
require_text "$cloud_init" "AuthenticationMethods publickey"
require_text "$cloud_init" "AllowTcpForwarding local"
require_text "$cloud_init" "ufw default deny incoming"
require_text "$cloud_init" "ufw allow in on tailscale0 to any port 22 proto tcp"
require_text "$cloud_init" "systemctl enable --now docker"

bytes="$(wc -c < "$cloud_init")"
(( bytes <= 32768 )) && pass "cloud-init size: $bytes bytes" || fail "cloud-init exceeds Hetzner 32 KiB limit: $bytes bytes"

printf 'INFRA VALIDATION: failures=%d\n' "$failures"
(( failures == 0 ))

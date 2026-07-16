#!/usr/bin/env bash
set -Eeuo pipefail

SANDBOX="hydra-hermes-lab"
MIN_CPU=4
MIN_RAM_KIB=$((8 * 1024 * 1024))
MIN_DISK_KIB=$((20 * 1024 * 1024))
blocks=0
warnings=0

pass() { printf 'PASS  %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; warnings=$((warnings + 1)); }
block() { printf 'BLOCK %s\n' "$*"; blocks=$((blocks + 1)); }
have() { command -v "$1" >/dev/null 2>&1; }

printf 'Hydra Hermes remote preflight (read-only)\n'

os="$(uname -s)"
arch="$(uname -m)"
[[ "$os" == Linux ]] && pass "OS: Linux" || block "OS must be Linux; detected $os"
case "$arch" in x86_64|aarch64|arm64) pass "Architecture: $arch" ;; *) block "Unsupported architecture: $arch" ;; esac

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  [[ "${ID:-}" == ubuntu ]] && pass "Distribution: ${PRETTY_NAME:-Ubuntu}" || warn "Ubuntu is the validated target; detected ${PRETTY_NAME:-unknown}"
else
  warn "Cannot read /etc/os-release"
fi

cpu="$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf 0)"
(( cpu >= MIN_CPU )) && pass "CPU: ${cpu} vCPU" || block "CPU: ${cpu} vCPU; minimum is ${MIN_CPU}"

ram_kib="$(awk '/MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || printf 0)"
(( ram_kib >= MIN_RAM_KIB )) && pass "RAM: $((ram_kib / 1024 / 1024)) GiB" || block "RAM below 8 GiB"

disk_kib="$(df -Pk "$HOME" | awk 'NR==2 {print $4}')"
(( disk_kib >= MIN_DISK_KIB )) && pass "Disk free: $((disk_kib / 1024 / 1024)) GiB" || block "Free disk below 20 GiB"

for tool in bash curl git tar; do
  have "$tool" && pass "$tool: $(command -v "$tool")" || block "$tool is missing"
done

if have node; then
  node_version="$(node -p 'process.versions.node')"
  if node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22 || (a===22 && b>=19) ? 0 : 1)'; then
    pass "Node.js: $node_version"
  else
    block "Node.js $node_version; require >=22.19"
  fi
else
  block "Node.js is missing; require >=22.19"
fi

if have npm; then
  npm_major="$(npm --version | cut -d. -f1)"
  (( npm_major >= 10 )) && pass "npm: $(npm --version)" || block "npm major version must be >=10"
else
  block "npm is missing"
fi

if have docker; then
  pass "Docker CLI: $(docker --version)"
  docker info >/dev/null 2>&1 && pass "Docker daemon: reachable" || block "Docker daemon is not reachable by current user"
else
  block "Docker is missing"
fi

selected_python=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  have "$candidate" || continue
  if path="$($candidate -c 'import os,sys,ensurepip,pyexpat,ssl,venv; v=sys.version_info; assert (3,10)<=v[:2]<(3,14); print(os.path.realpath(sys.executable))' 2>/dev/null)"; then
    selected_python="$path"
    pass "Model Router Python: $path ($($candidate -c 'import platform; print(platform.python_version())'))"
    break
  else
    warn "Rejected Python candidate: $candidate"
  fi
done
[[ -n "$selected_python" ]] || block "No Python >=3.10,<3.14 with ensurepip, pyexpat, ssl, and venv"

if have ss; then
  if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)4000$'; then block "Port 4000 is occupied"; else pass "Port 4000: available"; fi
elif have lsof; then
  lsof -nP -iTCP:4000 -sTCP:LISTEN >/dev/null 2>&1 && block "Port 4000 is occupied" || pass "Port 4000: available"
else
  warn "Cannot inspect port 4000; install ss or lsof"
fi

for cli in nemoclaw nemohermes openshell; do
  if have "$cli"; then pass "$cli: $($cli --version 2>/dev/null | head -n1 || printf installed)"; else warn "$cli: not installed"; fi
done

if have nemoclaw; then
  list_json="$(nemoclaw list --json 2>/dev/null || true)"
  if [[ -n "$list_json" ]] && python3 -c '
import json, sys
name = sys.argv[1]
data = json.load(sys.stdin)
items = data if isinstance(data, list) else data.get("sandboxes", [])
raise SystemExit(0 if any(item.get("name") == name for item in items) else 1)
' "$SANDBOX" <<<"$list_json" >/dev/null 2>&1
  then
    block "Sandbox name collision: $SANDBOX already exists"
  else
    pass "Sandbox name: available"
  fi
else
  pass "Sandbox collision check deferred until NemoClaw is installed"
fi

printf 'Selected Python: %s\n' "${selected_python:-NONE}"
printf 'Result: blocks=%d warnings=%d\n' "$blocks" "$warnings"
(( blocks == 0 ))

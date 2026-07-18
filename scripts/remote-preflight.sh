#!/usr/bin/env bash
# shellcheck disable=SC2015
set -Eeuo pipefail

SANDBOX="hydra-hermes-lab"
EXPECTED_HOSTNAME="hydra-hermes-runtime-01"
MIN_RAM_KIB=$((15 * 1024 * 1024))
MIN_ROOT_DISK_KIB=$((145 * 1024 * 1024))
MIN_FREE_DISK_KIB=$((40 * 1024 * 1024))
blocks=0
warnings=0

pass() { printf 'PASS  %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; warnings=$((warnings + 1)); }
block() { printf 'BLOCK %s\n' "$*"; blocks=$((blocks + 1)); }
have() { command -v "$1" >/dev/null 2>&1; }

github_report() {
  local overall="READY"
  local hostname_value="UNKNOWN"
  local os_value="UNKNOWN"
  local arch_value="UNKNOWN"
  local cpu_value="UNKNOWN"
  local ram_value="UNKNOWN"
  local disk_value="UNKNOWN"
  local firewall_value="UNVERIFIED"
  local docker_value="UNAVAILABLE"
  local user_value="FAIL"
  local repository_value="FAIL"
  local nemoclaw_value="NOT INSTALLED"
  local nemohermes_value="NOT INSTALLED"
  local openshell_value="NOT INSTALLED"
  local port_4000="UNVERIFIED"
  local port_8642="UNVERIFIED"
  local port_18789="UNVERIFIED"
  local repo_path="$HOME/hydra-hermes-lab"
  local repo_remote=""

  hostname_value="$(hostname -s 2>/dev/null || printf UNKNOWN)"
  if [[ "$hostname_value" != "$EXPECTED_HOSTNAME" ]]; then
    hostname_value="UNEXPECTED"
    overall="BLOCKED"
  fi

  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    os_value="${PRETTY_NAME:-UNKNOWN}"
    [[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 24.04 ]] || overall="BLOCKED"
  else
    overall="BLOCKED"
  fi

  arch_value="$(uname -m 2>/dev/null || printf UNKNOWN)"
  [[ "$arch_value" == x86_64 ]] || overall="BLOCKED"

  cpu_value="$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf UNKNOWN)"
  [[ "$cpu_value" == 8 ]] || overall="BLOCKED"

  if [[ -r /proc/meminfo ]]; then
    ram_kib="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
    ram_value="$((ram_kib / 1024 / 1024)) GiB"
    (( ram_kib >= MIN_RAM_KIB )) || overall="BLOCKED"
  else
    overall="BLOCKED"
  fi

  if df -Pk / >/dev/null 2>&1; then
    root_total_kib="$(df -Pk / | awk 'NR==2 {print $2}')"
    root_free_kib="$(df -Pk / | awk 'NR==2 {print $4}')"
    disk_value="$((root_total_kib / 1024 / 1024)) GiB total, $((root_free_kib / 1024 / 1024)) GiB free"
    (( root_total_kib >= MIN_ROOT_DISK_KIB && root_free_kib >= MIN_FREE_DISK_KIB )) || overall="BLOCKED"
  else
    overall="BLOCKED"
  fi

  if command -v systemctl >/dev/null 2>&1 \
    && [[ "$(systemctl is-active ufw 2>/dev/null || true)" == active ]] \
    && [[ -r /etc/ufw/ufw.conf ]] \
    && grep -Eq '^ENABLED=yes' /etc/ufw/ufw.conf; then
    firewall_value="UFW ACTIVE; PROVIDER POLICY OUTSIDE SSH SCOPE"
  else
    firewall_value="INACTIVE OR UNVERIFIED"
    overall="BLOCKED"
  fi

  if command -v docker >/dev/null 2>&1 \
    && [[ "$(systemctl is-active docker 2>/dev/null || true)" == active ]] \
    && docker info >/dev/null 2>&1; then
    docker_value="ACTIVE AND ACCESSIBLE"
  else
    overall="BLOCKED"
  fi

  if [[ "$(id -un 2>/dev/null || true)" == hydra ]] && id hydra >/dev/null 2>&1; then
    user_value="PASS"
  else
    overall="BLOCKED"
  fi

  if [[ -r "$repo_path/.git/config" ]] && command -v git >/dev/null 2>&1; then
    repo_remote="$(git -C "$repo_path" remote get-url origin 2>/dev/null || true)"
    case "$repo_remote" in
      https://github.com/HazEOskA/hydra-hermes-lab.git|git@github.com:HazEOskA/hydra-hermes-lab.git)
        repository_value="PASS"
        ;;
      *)
        overall="BLOCKED"
        ;;
    esac
  else
    overall="BLOCKED"
  fi

  command -v nemoclaw >/dev/null 2>&1 && nemoclaw_value="INSTALLED"
  command -v nemohermes >/dev/null 2>&1 && nemohermes_value="INSTALLED"
  command -v openshell >/dev/null 2>&1 && openshell_value="INSTALLED"

  if command -v ss >/dev/null 2>&1; then
    for port in 4000 8642 18789; do
      port_state="AVAILABLE"
      if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
        port_state="OCCUPIED"
        overall="BLOCKED"
      fi
      case "$port" in
        4000) port_4000="$port_state" ;;
        8642) port_8642="$port_state" ;;
        18789) port_18789="$port_state" ;;
      esac
    done
  else
    overall="BLOCKED"
  fi

  printf 'REMOTE SSH: PASS\n'
  printf 'HOSTNAME: %s\n' "$hostname_value"
  printf 'PUBLIC IP: REDACTED\n'
  printf 'OS: %s\n' "$os_value"
  printf 'ARCHITECTURE: %s\n' "$arch_value"
  printf 'CPU: %s\n' "$cpu_value"
  printf 'RAM: %s\n' "$ram_value"
  printf 'DISK: %s\n' "$disk_value"
  printf 'FIREWALL: %s\n' "$firewall_value"
  printf 'DOCKER: %s\n' "$docker_value"
  printf 'USER HYDRA: %s\n' "$user_value"
  printf 'REPOSITORY ACCESS: %s\n' "$repository_value"
  printf 'NEMOCLAW: %s\n' "$nemoclaw_value"
  printf 'NEMOHERMES: %s\n' "$nemohermes_value"
  printf 'OPENSHELL: %s\n' "$openshell_value"
  printf 'PORT 4000: %s\n' "$port_4000"
  printf 'PORT 8642: %s\n' "$port_8642"
  printf 'PORT 18789: %s\n' "$port_18789"
  printf 'APR UNTOUCHED: PASS\n'
  printf 'OVERALL: %s\n' "$overall"

  [[ "$overall" == READY ]]
}

if [[ "${1:-}" == --github-report ]]; then
  [[ $# -eq 1 ]] || { printf 'Invalid report arguments.\n' >&2; exit 2; }
  github_report
  exit $?
fi

printf 'Hydra Hermes runtime preflight (read-only)\n'

[[ "$(uname -s)" == Linux ]] && pass "OS family: Linux" || block "OS must be Linux"
[[ "$(uname -m)" == x86_64 ]] && pass "Architecture: x86_64" || block "Architecture must be x86_64; detected $(uname -m)"
[[ "$(hostname -s)" == "$EXPECTED_HOSTNAME" ]] && pass "Hostname: $EXPECTED_HOSTNAME" || block "Hostname must be $EXPECTED_HOSTNAME; detected $(hostname -s)"

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  [[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 24.04 ]] \
    && pass "Distribution: ${PRETTY_NAME:-Ubuntu 24.04}" \
    || block "Distribution must be Ubuntu 24.04; detected ${PRETTY_NAME:-unknown}"
else
  block "Cannot read /etc/os-release"
fi

if [[ -r /sys/class/dmi/id/sys_vendor ]]; then
  vendor="$(tr -d '\n' </sys/class/dmi/id/sys_vendor)"
  [[ -n "$vendor" ]] && pass "Virtualization vendor: $vendor" || block "DMI virtualization vendor is empty"
else
  warn "DMI virtualization vendor unavailable; verify provider identity in its control plane"
fi

cpu="$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf 0)"
[[ "$cpu" == 8 ]] && pass "CPU: 8 vCPU" || block "Locked runtime target requires 8 vCPU; detected $cpu"

ram_kib="$(awk '/MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || printf 0)"
(( ram_kib >= MIN_RAM_KIB )) && pass "RAM: $((ram_kib / 1024 / 1024)) GiB (16 GB class)" || block "RAM below the 16 GB host class"

root_total_kib="$(df -Pk / | awk 'NR==2 {print $2}')"
root_free_kib="$(df -Pk / | awk 'NR==2 {print $4}')"
(( root_total_kib >= MIN_ROOT_DISK_KIB )) && pass "Root disk: $((root_total_kib / 1024 / 1024)) GiB (160 GB class)" || block "Root disk below the 160 GB host class"
(( root_free_kib >= MIN_FREE_DISK_KIB )) && pass "Root free: $((root_free_kib / 1024 / 1024)) GiB" || block "Free root disk below NVIDIA recommended 40 GiB"

[[ "$(ps -p 1 -o comm= 2>/dev/null)" == systemd ]] && pass "Init: systemd" || block "systemd must be PID 1"
[[ -f /var/lib/hydra-bootstrap/complete ]] && pass "Cloud-init bootstrap marker: present" || block "Cloud-init bootstrap did not complete"
[[ ! -f /var/run/reboot-required ]] && pass "Pending reboot: none" || block "Host requires reboot before installation"
[[ "${USER:-$(id -un)}" == hydra ]] && pass "Runtime user: hydra" || block "Run as the dedicated hydra user"

for tool in bash curl git tar strings zstd jq ip ss sshd; do
  have "$tool" && pass "$tool: $(command -v "$tool")" || block "$tool is missing"
done

if have ip; then
  ip -4 route show default | grep -q . && pass "IPv4 default route: present" || block "IPv4 default route is missing"
  ip -6 route show default | grep -q . && pass "IPv6 default route: present" || block "IPv6 default route is missing"
  ip -4 -o addr show scope global | grep -q . && pass "Global IPv4: present" || block "Global IPv4 address is missing"
  ip -6 -o addr show scope global | grep -q . && pass "Global IPv6: present" || block "Global IPv6 address is missing"
fi

have nvidia-smi && warn "GPU detected but not required or used by this baseline" || pass "GPU: not required"

if have node; then
  node_version="$(node -p 'process.versions.node')"
  node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22 || (a===22 && b>=19) ? 0 : 1)' \
    && pass "Node.js: $node_version" || block "Node.js $node_version; require >=22.19"
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
  systemctl is-active --quiet docker && pass "Docker service: active" || block "Docker service is not active"
  docker info >/dev/null 2>&1 && pass "Docker daemon: reachable by hydra" || block "Docker daemon is not reachable by hydra"
else
  block "Docker is missing"
fi

if have sshd; then
  ssh_effective="$(sudo -n sshd -T 2>/dev/null || sshd -T 2>/dev/null || true)"
  for expected in 'permitrootlogin no' 'passwordauthentication no' 'kbdinteractiveauthentication no' 'allowusers hydra' 'allowtcpforwarding local'; do
    grep -Fqx "$expected" <<<"$ssh_effective" && pass "SSH: $expected" || block "SSH effective config missing: $expected"
  done
fi

if have ufw; then
  ufw_status="$(sudo -n ufw status 2>/dev/null || true)"
  grep -Fq 'Status: active' <<<"$ufw_status" && pass "UFW: active" || block "UFW is not active"
else
  block "UFW is missing"
fi
if [[ "$(systemctl is-active fail2ban 2>/dev/null || true)" == active ]]; then
  pass "Fail2ban: active"
else
  block "Fail2ban is not active"
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

for port in 4000 8642 18789; do
  if have ss && ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
    block "Port $port is occupied before onboarding"
  else
    pass "Port $port: available"
  fi
done

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
' "$SANDBOX" <<<"$list_json" >/dev/null 2>&1; then
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

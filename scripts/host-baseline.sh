#!/usr/bin/env bash
# Fact load. Records what the runtime host actually is, before anything changes it.
#
# Read-only by construction: it inspects, it never repairs. Secret values are
# masked as abcd...wxyz and never written in full.
# shellcheck disable=SC1091
set -Eeuo pipefail
umask 077

BASE_PATH="${HYDRA_BASE_PATH:-/opt/hydra}"
OUT_ROOT="${HERMES_BASELINE_DIR:-$BASE_PATH/recovery/hermes-baseline}"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$OUT_ROOT/$stamp"

mkdir -p "$out"
ln -sfn "$out" "$OUT_ROOT/latest"

log() { printf '%s baseline %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# Capture a command's output without letting a missing tool abort the run: an
# absent tool is itself a finding worth recording.
capture() {
  local label="$1" file="$2"
  shift 2
  {
    printf '### %s\n$ %s\n' "$label" "$*"
    if command -v "$1" >/dev/null 2>&1; then
      "$@" 2>&1 || printf '(exit %d)\n' "$?"
    else
      printf '(tool not installed: %s)\n' "$1"
    fi
    printf '\n'
  } >>"$out/$file"
}

log "writing baseline to $out"

# -- system ---------------------------------------------------------------
{
  printf '# System Inventory\n\n'
  printf -- '- collected: %s\n' "$(date -Is)"
  printf -- '- hostname: %s\n' "$(hostname)"
  printf -- '- user: %s\n' "$(id -un)"
  printf -- '- kernel: %s\n' "$(uname -sr)"
  printf -- '- arch: %s\n' "$(uname -m)"
  printf -- '- os: %s\n' "$(. /etc/os-release 2>/dev/null && printf '%s' "${PRETTY_NAME:-unknown}")"
  printf -- '- uptime: %s\n' "$(uptime -p 2>/dev/null || uptime)"
  printf -- '- vcpu: %s\n' "$(nproc 2>/dev/null || printf unknown)"
  printf -- '- memory: %s\n' "$(free -h 2>/dev/null | awk '/^Mem:/{print $2}' || printf unknown)"
  printf -- '- disk: %s\n' "$(df -h / 2>/dev/null | awk 'NR==2{print $2" total, "$4" free"}')"
  printf -- '- virtualization: %s\n' "$(systemd-detect-virt 2>/dev/null || printf unknown)"
  printf -- '- pending reboot: %s\n' "$([[ -e /var/run/reboot-required ]] && printf yes || printf no)"
} >"$out/01-system.md"

capture "disk" "01-system.md" df -h
capture "memory" "01-system.md" free -h

# -- services and containers ---------------------------------------------
capture "failed units" "service-status.txt" systemctl --failed
capture "running services" "service-status.txt" systemctl list-units --type=service --state=running --no-pager
capture "timers" "service-status.txt" systemctl list-timers --all --no-pager

capture "docker version" "docker-status.txt" docker version
capture "compose version" "docker-status.txt" docker compose version
capture "containers" "docker-status.txt" docker ps -a
capture "networks" "docker-status.txt" docker network ls
capture "volumes" "docker-status.txt" docker volume ls
capture "images" "docker-status.txt" docker images --digests

capture "listening sockets" "port-map.txt" ss -tulpn
capture "user cron" "port-map.txt" crontab -l

# -- Hermes runtime -------------------------------------------------------
{
  printf '# Hermes Runtime\n\n'
  for cli in nemoclaw nemohermes openshell hermes; do
    if command -v "$cli" >/dev/null 2>&1; then
      printf -- '- %s: %s\n' "$cli" "$("$cli" --version 2>/dev/null | head -n1 || printf installed)"
    else
      printf -- '- %s: NOT INSTALLED\n' "$cli"
    fi
  done
  printf '\n## Application tree (%s)\n\n```\n' "$BASE_PATH"
  if [[ -d "$BASE_PATH" ]]; then
    find "$BASE_PATH" -maxdepth 3 -type f 2>/dev/null | sort | head -n 200
  else
    printf '(%s does not exist)\n' "$BASE_PATH"
  fi
  printf '```\n'
} >"$out/02-hermes.md"

# -- repositories ---------------------------------------------------------
{
  printf '# Repositories\n\n'
  while IFS= read -r gitdir; do
    repo="$(dirname "$gitdir")"
    printf '## %s\n\n' "$repo"
    printf -- '- commit: %s\n' "$(git -C "$repo" rev-parse HEAD 2>/dev/null || printf unknown)"
    printf -- '- branch: %s\n' "$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null || printf unknown)"
    printf -- '- dirty files: %s\n' "$(git -C "$repo" status --porcelain 2>/dev/null | wc -l)"
    printf -- '- unpushed commits: %s\n' \
      "$(git -C "$repo" log --oneline '@{upstream}..HEAD' 2>/dev/null | wc -l)"
    printf '\n'
  done < <(find "$BASE_PATH" "$HOME" -maxdepth 4 -type d -name .git 2>/dev/null | sort -u)
} >"$out/03-repositories.md"

# -- environment (redacted) ----------------------------------------------
# Names and masked values only. A raw value never reaches this file.
{
  printf '# Environment Inventory (redacted)\n\n'
  printf '| variable | masked value |\n| --- | --- |\n'
  while IFS='=' read -r name value; do
    case "$name" in
      *KEY*|*TOKEN*|*SECRET*|*PASSWORD*|*CREDENTIAL*|*AUTH*)
        printf '| %s | %s |\n' "$name" \
          "$(printf '%s' "$value" | sed -E 's/^(.{0,4}).*(.{4})$/\1...\2/')"
        ;;
      PATH|LS_COLORS|HOME|PWD|SHLVL|_) : ;;
      *) printf '| %s | %s |\n' "$name" "(non-secret, length ${#value})" ;;
    esac
  done < <(env | sort)
} >"$out/04-environment.md"

# -- health ---------------------------------------------------------------
if [[ -x "$repo_root/scripts/health-watch.sh" ]]; then
  "$repo_root/scripts/health-watch.sh" --report-only >"$out/05-health.txt" 2>&1 || true
else
  printf 'health-watch.sh not present\n' >"$out/05-health.txt"
fi

# -- gaps -----------------------------------------------------------------
{
  printf '# Identified Gaps\n\n'
  gap() { printf -- '- [ ] %s\n' "$*"; }
  [[ "$(hostname -s)" == hydra-hermes-runtime-01 ]] \
    || gap "hostname is $(hostname -s), expected hydra-hermes-runtime-01"
  command -v nemohermes >/dev/null 2>&1 || gap "nemohermes CLI is missing"
  command -v docker >/dev/null 2>&1 || gap "docker is missing"
  docker info >/dev/null 2>&1 || gap "docker daemon is not reachable"
  systemctl is-system-running >/dev/null 2>&1 || gap "systemd is not managing this host"
  [[ -d "$BASE_PATH" ]] || gap "$BASE_PATH does not exist"
  [[ -f "$repo_root/SOUL.md" ]] || gap "SOUL.md is not present in the control repository"
  curl -fsS --max-time 5 http://127.0.0.1:8642/health >/dev/null 2>&1 \
    || gap "Hermes API health on 127.0.0.1:8642 did not respond"
  printf '\nGaps are recorded, not repaired. Repair runs behind its own execution gate.\n'
} >"$out/06-gaps.md"

printf '%s\n' "$stamp" >"$out/TIMESTAMP"
log "baseline complete: $out"
log "latest symlink: $OUT_ROOT/latest"

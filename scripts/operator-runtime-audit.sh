#!/usr/bin/env bash
# Read-only runtime audit for hydra-hermes-runtime-01.
#
# Collects the full pre-repair state. Mutates nothing: there is no --execute,
# no write outside the evidence directory, and no command that starts, stops or
# reconfigures anything.
set -Eeuo pipefail
umask 077

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/operator-lib.sh
source "$HERE/operator-lib.sh"

require_host
RUN_DIR="$(new_run_dir runtime-audit)"
SUMMARY="$RUN_DIR/runtime-audit-summary.txt"

exec > >(tee -a "$RUN_DIR/audit-console.txt") 2>&1

log "runtime audit started (read-only)"
log "evidence: $RUN_DIR"

# -- host ------------------------------------------------------------------
capture host.txt hostname -f
capture host.txt id -un
capture host.txt uptime
capture host.txt free -m
capture host.txt df -h
capture host.txt sh -c 'cat /proc/loadavg'

# Zombies and the parents that own them.
{
  printf '### %s :: zombie processes\n' "$(utc)"
  ps -eo pid,ppid,stat,comm --no-headers | awk '$3 ~ /^Z/ {print}' || true
  printf 'zombie_count=%s\n' "$(ps -eo stat --no-headers | grep -c '^Z' || true)"
} >>"$RUN_DIR/host.txt"

# -- systemd ---------------------------------------------------------------
UNITS=(
  nemoclaw-hermes-recover nemoclaw-hermes-watchdog nemoclaw-model-router
  nemoclaw-openshell-gateway hydra-direct hydra-genkit-ui
  hydra-hermes-worker
)
for unit in "${UNITS[@]}"; do
  capture systemd-units.txt systemctl status --no-pager --lines=0 "$unit"
  capture systemd-units.txt systemctl is-enabled "$unit"
done
capture systemd-all.txt sh -c \
  "systemctl list-units --all --no-pager --plain --no-legend | grep -Ei 'hydra|hermes|nemo|openshell|zgredek|minion|genkit|buzz|policy|cofounder|claude|codex|openhands'"
capture systemd-all.txt sh -c "systemctl list-unit-files --no-pager --no-legend | grep -Ei 'hydra|hermes|nemo|openshell'"

# -- nemoclaw / nemohermes -------------------------------------------------
capture nemo.txt nemohermes "$SANDBOX" status --json
capture nemo.txt nemohermes "$SANDBOX" doctor --json
capture nemo.txt nemoclaw list --json
capture nemo.txt nemoclaw inference get --json

# -- docker ----------------------------------------------------------------
capture docker.txt docker ps -a
CID="$(sandbox_container_id || true)"
if [[ -n "${CID:-}" ]]; then
  printf 'sandbox_container_id=%s\n' "$CID" >>"$RUN_DIR/docker.txt"
  capture docker-inspect.txt docker inspect "$CID"
  # The specific fields the root-cause analysis needs.
  capture docker-state.txt docker inspect -f \
    'Status={{.State.Status}} ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}} Error={{.State.Error}} FinishedAt={{.State.FinishedAt}} RestartCount={{.RestartCount}}' "$CID"
  # Mount targets only; sources may contain host paths and are not needed here.
  capture docker-mounts.txt docker inspect -f '{{range .Mounts}}{{.Type}} -> {{.Destination}} rw={{.RW}}{{"\n"}}{{end}}' "$CID"
  capture docker-logs.txt docker logs --tail 200 "$CID"
else
  printf 'sandbox_container_id=NOT_FOUND\n' >>"$RUN_DIR/docker.txt"
fi

# -- listeners and processes ----------------------------------------------
capture ports.txt sh -c "ss -tulpn 2>/dev/null | grep -E ':(4000|8080|8642|18789|8787)\b' || echo '(no matching listener)'"
capture ports.txt ss -tulpn
capture processes.txt sh -c "ps -eo pid,ppid,etime,rss,stat,cmd --no-headers | grep -Ei 'nemo|hermes|openshell|hydra|genkit|zgredek|minion' | grep -v grep || echo '(none)'"

# -- journals (24h) --------------------------------------------------------
for unit in "${UNITS[@]}"; do
  capture journals.txt journalctl -u "$unit" --since '24 hours ago' --no-pager --lines=200
done

# -- repositories ----------------------------------------------------------
REPO_PATHS=(
  /opt/hydra/apps/hydra-hermes-lab /opt/hydra/apps/hydra-dashboard
  /opt/hydra/apps/hydra-minion /opt/hydra/apps/hydra-genkit-lab
  /home/hydra/hermes-godlayer /home/hydra/hermes-baseline /home/hydra/hydra-recovery
)
{
  printf '### %s :: repositories\n' "$(utc)"
  for p in "${REPO_PATHS[@]}"; do
    if [[ -d "$p/.git" ]]; then
      printf '%s origin=%s branch=%s head=%s dirty=%s\n' "$p" \
        "$(git -C "$p" remote get-url origin 2>/dev/null || echo none)" \
        "$(git -C "$p" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)" \
        "$(git -C "$p" rev-parse HEAD 2>/dev/null || echo unknown)" \
        "$([[ -n "$(git -C "$p" status --porcelain 2>/dev/null)" ]] && echo yes || echo no)"
    elif [[ -d "$p" ]]; then
      printf '%s (directory, not a git repository)\n' "$p"
    else
      printf '%s ABSENT\n' "$p"
    fi
  done
} | redact >>"$RUN_DIR/repositories.txt"

# -- summary ---------------------------------------------------------------
{
  printf 'HYDRA RUNTIME AUDIT\n'
  printf 'utc=%s host=%s user=%s\n' "$(utc)" "$(hostname -s)" "$(id -un)"
  printf 'evidence=%s\n\n' "$RUN_DIR"
  printf -- '-- sandbox --\n'
  grep -E '"phase"|"failureLayer"|"found"' "$RUN_DIR/nemo.txt" 2>/dev/null | head -10 || printf '(no phase field captured)\n'
  printf -- '\n-- container --\n'
  cat "$RUN_DIR/docker-state.txt" 2>/dev/null | grep -v '^###' | grep -v '^$' || printf '(container not identified)\n'
  printf -- '\n-- listeners of interest --\n'
  grep -E ':(4000|8080|8642|18789|8787)\b' "$RUN_DIR/ports.txt" 2>/dev/null | head -12 || printf '(none)\n'
  printf -- '\n-- units --\n'
  grep -E '^\s*(Active|Loaded):|^(enabled|disabled|not-found|masked|static)$' "$RUN_DIR/systemd-units.txt" 2>/dev/null | head -40 || true
  printf -- '\n-- repositories --\n'
  grep -v '^###' "$RUN_DIR/repositories.txt" 2>/dev/null || true
  printf -- '\n-- zombies --\n'
  grep -E '^zombie_count=' "$RUN_DIR/host.txt" 2>/dev/null || printf 'zombie_count=UNKNOWN\n'
} >"$SUMMARY"

chmod -R go-rwx "$RUN_DIR"
log "audit complete. summary: $SUMMARY"
printf '\nRead the summary, then run the recovery dry-run:\n  scripts/operator-hermes-recover.sh\n'

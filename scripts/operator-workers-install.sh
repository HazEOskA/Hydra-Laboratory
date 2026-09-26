#!/usr/bin/env bash
# Install the systemd units that already exist in this repository.
#
# It creates no unit, no scheduler and no worker. It resolves the canonical
# repository path, refuses to install on a path conflict (DRIFT), and refuses to
# start the Hermes worker until the runtime gates actually pass.
set -Eeuo pipefail
umask 077

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/operator-lib.sh
source "$HERE/operator-lib.sh"

EXECUTE=0
REPO_PATH=""
for arg in "$@"; do
  case "$arg" in
    --execute) EXECUTE=1 ;;
    --dry-run) EXECUTE=0 ;;
    --repo-path=*) REPO_PATH="${arg#*=}" ;;
    -h|--help)
      cat <<'USAGE'
usage: operator-workers-install.sh [--dry-run|--execute] [--repo-path=/abs/path]

  --dry-run     (default) resolve, compare and report; install nothing
  --execute     back up existing units, install, enable and start eligible units
  --repo-path   state the canonical repository explicitly when detection is
                ambiguous. /home/hydra/hydra-hermes-lab is never assumed.

The Hermes worker is started only when all four gates PASS:
  HERMES_SANDBOX_READY  NVIDIA_ROUTE  REAL_INFERENCE  CREDENTIAL_ISOLATION
USAGE
      exit 0 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

require_host
RUN_DIR="$(new_run_dir workers-install)"
exec > >(tee -a "$RUN_DIR/install-console.txt") 2>&1

log "worker install ($([[ $EXECUTE -eq 1 ]] && echo EXECUTE || echo DRY-RUN))"

# -- resolve the canonical repository -------------------------------------
log "resolving the canonical repository path"
CANDIDATES=("${REPO_CANDIDATES[@]}")
[[ -n "$REPO_PATH" ]] && CANDIDATES=("$REPO_PATH")

FOUND=()
for p in "${CANDIDATES[@]}"; do
  [[ -d "$p/.git" ]] || { printf '  skip    %s (not a git repository)\n' "$p"; continue; }
  [[ -f "$p/scripts/hermes-worker.sh" && -d "$p/infra/systemd" ]] \
    || { printf '  skip    %s (missing scripts/hermes-worker.sh or infra/systemd)\n' "$p"; continue; }
  printf '  found   %s origin=%s branch=%s head=%s\n' "$p" \
    "$(git -C "$p" remote get-url origin 2>/dev/null || echo none)" \
    "$(git -C "$p" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)" \
    "$(git -C "$p" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  FOUND+=("$p")
done

[[ ${#FOUND[@]} -gt 0 ]] || die "no candidate repository satisfies the requirements (status=BLOCKED)"
if [[ ${#FOUND[@]} -gt 1 ]]; then
  printf '\n  DRIFT   %s candidate repositories satisfy the requirements:\n' "${#FOUND[@]}"
  printf '            %s\n' "${FOUND[@]}"
  printf '          Stopping before install. Re-run with --repo-path=<the canonical one>.\n'
  exit 4
fi
REPO="${FOUND[0]}"
printf '  canonical repository: %s\n' "$REPO"

# -- compare the unit against the resolved path ---------------------------
UNIT_SRC="$REPO/infra/systemd/hydra-hermes-worker.service"
[[ -f "$UNIT_SRC" ]] || die "missing $UNIT_SRC"

UNIT_WD="$(sed -nE 's/^WorkingDirectory=(.*)$/\1/p' "$UNIT_SRC" | head -1)"
UNIT_EXEC="$(sed -nE 's/^ExecStart=([^ ]+).*$/\1/p' "$UNIT_SRC" | head -1)"
printf '\n  BEFORE  unit WorkingDirectory=%s\n' "$UNIT_WD"
printf '  BEFORE  unit ExecStart=%s\n' "$UNIT_EXEC"

PATCH_UNITS=0
if [[ "$UNIT_WD" != "$REPO" ]]; then
  printf '  DRIFT   the shipped unit points at %s but the canonical repository is %s\n' "$UNIT_WD" "$REPO"
  if [[ -z "$REPO_PATH" ]]; then
    printf '          Stopping before install. Confirm the canonical path with\n'
    printf '          --repo-path=%s to install a path-corrected copy of the same unit.\n' "$REPO"
    exit 4
  fi
  printf '          --repo-path was given explicitly: installing a path-corrected copy.\n'
  PATCH_UNITS=1
fi

# -- backup existing units -------------------------------------------------
BACKUP="$RUN_DIR/systemd-backup"; mkdir -p "$BACKUP"
for f in /etc/systemd/system/hydra-hermes-*.service /etc/systemd/system/hydra-hermes-*.timer; do
  [[ -e "$f" ]] || continue
  cp -a "$f" "$BACKUP/" && printf '  backup  %s\n' "$f"
done
printf '  backup directory: %s\n' "$BACKUP"

# -- stage the units -------------------------------------------------------
STAGE="$RUN_DIR/units"; mkdir -p "$STAGE"
for f in "$REPO"/infra/systemd/*.service "$REPO"/infra/systemd/*.timer; do
  [[ -e "$f" ]] || continue
  if [[ $PATCH_UNITS -eq 1 ]]; then
    sed -E "s#(WorkingDirectory=|ExecStart=)/home/hydra/hydra-hermes-lab#\1${REPO}#g" "$f" >"$STAGE/$(basename "$f")"
  else
    cp -a "$f" "$STAGE/"
  fi
done
printf '  staged  %s unit files in %s\n' "$(find "$STAGE" -type f | wc -l)" "$STAGE"

# -- state directory and worker.env ---------------------------------------
STATE_DIR="/var/lib/hydra-hermes"
ENV_DIR="/etc/hydra-hermes"
act "create $STATE_DIR owned by $REQUIRED_USER, mode 0700" \
  sh -c "install -d -o $REQUIRED_USER -g $REQUIRED_USER -m 0700 '$STATE_DIR'"
act "create $ENV_DIR, mode 0750" \
  sh -c "sudo install -d -o root -g $REQUIRED_USER -m 0750 '$ENV_DIR'"

if [[ -f "$ENV_DIR/worker.env" ]]; then
  printf '  BEFORE  %s/worker.env already present — left untouched (reviewed by OSA)\n' "$ENV_DIR"
else
  printf '  ACTION  %s/worker.env is ABSENT.\n' "$ENV_DIR"
  printf '          Copy %s/config/worker.env.example there, review it, then re-run.\n' "$REPO"
  printf '          It must contain no credential values.\n'
  [[ $EXECUTE -eq 1 ]] && die "worker.env missing; refusing to install a unit that cannot start"
fi

# -- install ---------------------------------------------------------------
for f in "$STAGE"/*; do
  [[ -e "$f" ]] || continue
  act "install $(basename "$f") into /etc/systemd/system" \
    sudo install -o root -g root -m 0644 "$f" "/etc/systemd/system/$(basename "$f")"
done
act "systemctl daemon-reload" sudo systemctl daemon-reload

# -- gates before starting the Hermes worker ------------------------------
log "checking the four gates before enabling the Hermes worker"
GATES_PASS=1
gate() {
  local name="$1" result="$2"
  if [[ "$result" == "PASS" ]]; then ok "$name"; else bad "$name" "$result"; GATES_PASS=0; fi
}
VERIFY_OUT="$RUN_DIR/verify.txt"
if "$HERE/operator-runtime-verify.sh" >"$VERIFY_OUT" 2>&1; then :; else printf '  (verify reported failures)\n'; fi
for g in HERMES_SANDBOX_READY NVIDIA_ROUTE REAL_INFERENCE CREDENTIAL_ISOLATION; do
  gate "$g" "$(grep -E "^\s*(PASS|FAIL|UNKNOWN|N/A)\s+$g\b" "$VERIFY_OUT" | awk '{print $1}' | head -1 || echo UNKNOWN)"
done

# Timers that do not depend on live inference can be enabled regardless.
for unit in hydra-hermes-healthwatch.timer hydra-hermes-report.timer hydra-hermes-repowatch.timer; do
  [[ -f "$STAGE/$unit" ]] || continue
  act "enable --now $unit" sudo systemctl enable --now "$unit"
done

if [[ $GATES_PASS -eq 1 ]]; then
  act "enable --now hydra-hermes-worker.service" \
    sudo systemctl enable --now hydra-hermes-worker.service
  if [[ $EXECUTE -eq 1 ]]; then
    sleep 10
    printf '  AFTER   %s\n' "$(systemctl is-active hydra-hermes-worker.service || true)"
    printf '  AFTER   %s\n' "$(systemctl is-enabled hydra-hermes-worker.service || true)"
    journalctl -u hydra-hermes-worker.service --no-pager --lines=20 | redact || true
  fi
else
  printf '\n  HOLD    the Hermes worker was NOT enabled: one or more gates did not PASS.\n'
  printf '          Fix the runtime first, then re-run. "configured" is not "running".\n'
  exit 5
fi

log "install complete. Run operator-runtime-verify.sh to confirm."

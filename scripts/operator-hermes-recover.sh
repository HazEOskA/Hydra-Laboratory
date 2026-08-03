#!/usr/bin/env bash
# Smallest reversible repair for sandbox_container_stopped.
#
# Default is --dry-run: it prints the plan and changes nothing. Mutations happen
# only with --execute, and only along the allowed ladder. Rebuild, destroy,
# onboard, reinstall, provider/model/credential changes, state wipes, prune,
# host reboot, UFW and Tailscale are refused outright — they need separate OSA
# approval and are not reachable from this script at all.
set -Eeuo pipefail
umask 077

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/operator-lib.sh
source "$HERE/operator-lib.sh"

EXECUTE=0
SKIP_AUDIT=0
REBUILD_APPROVED_BY=""
for arg in "$@"; do
  case "$arg" in
    --execute) EXECUTE=1 ;;
    --dry-run) EXECUTE=0 ;;
    --skip-audit) SKIP_AUDIT=1 ;;
    --rebuild-approved-by=*) REBUILD_APPROVED_BY="${arg#*=}" ;;
    -h|--help)
      cat <<'USAGE'
usage: operator-hermes-recover.sh [--dry-run|--execute] [--skip-audit]

  --dry-run     (default) print the plan and the chosen repair; change nothing
  --execute     perform the chosen repair
  --skip-audit  reuse the most recent audit instead of running a fresh one

Refused without separate OSA approval, in every mode:
  sandbox destroy / rebuild / onboard, NemoClaw reinstall, provider or model
  change, NVIDIA credential change, persistent state wipe, docker system prune,
  host reboot, UFW change, Tailscale change.
USAGE
      exit 0 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

require_host
RUN_DIR="$(new_run_dir hermes-recover)"
exec > >(tee -a "$RUN_DIR/recover-console.txt") 2>&1

log "hermes recovery ($([[ $EXECUTE -eq 1 ]] && echo EXECUTE || echo DRY-RUN))"
log "evidence: $RUN_DIR"

# -- A. audit --------------------------------------------------------------
if [[ $SKIP_AUDIT -eq 0 ]]; then
  log "phase A: running read-only audit first"
  "$HERE/operator-runtime-audit.sh" >"$RUN_DIR/audit.log" 2>&1 \
    || die "audit failed; refusing to continue (see $RUN_DIR/audit.log)"
else
  log "phase A: skipped by request"
fi

# -- B. identify the exact container --------------------------------------
log "phase B: identifying the sandbox container"
CID="$(sandbox_container_id || true)"
[[ -n "${CID:-}" ]] || die "no container matching sandbox '$SANDBOX'; cannot proceed (status=BLOCKED)"
printf '  container=%s\n' "$CID"

read -r STATUS EXITCODE OOM ERRMSG FINISHED RESTARTS < <(
  docker inspect -f '{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}} {{if .State.Error}}{{.State.Error}}{{else}}none{{end}} {{.State.FinishedAt}} {{.RestartCount}}' "$CID"
)

# -- C. root cause ---------------------------------------------------------
log "phase C: root cause"
printf '  BEFORE  status=%s exit=%s oomKilled=%s restarts=%s finishedAt=%s\n' \
  "$STATUS" "$EXITCODE" "$OOM" "$RESTARTS" "$FINISHED"
printf '  BEFORE  error=%s\n' "$ERRMSG"
{
  printf 'container=%s\nstatus=%s\nexit_code=%s\noom_killed=%s\nrestart_count=%s\nfinished_at=%s\nerror=%s\n' \
    "$CID" "$STATUS" "$EXITCODE" "$OOM" "$RESTARTS" "$FINISHED" "$ERRMSG"
} | redact >"$RUN_DIR/root-cause.txt"

if [[ "$OOM" == "true" ]]; then
  printf '  NOTE    OOMKilled=true — starting the container again without addressing memory\n'
  printf '          will most likely reproduce the crash. Capture this for OSA.\n'
fi

# -- D. backup -------------------------------------------------------------
log "phase D: backup (metadata only, no credentials)"
BACKUP="$RUN_DIR/backup"; mkdir -p "$BACKUP"
docker inspect "$CID" 2>/dev/null | redact >"$BACKUP/container-inspect.json" || true
nemoclaw list --json 2>/dev/null | redact >"$BACKUP/nemoclaw-list.json" || true
nemoclaw inference get --json 2>/dev/null | redact >"$BACKUP/inference-route.json" || true
nemohermes "$SANDBOX" status --json 2>/dev/null | redact >"$BACKUP/sandbox-status.json" || true
for unit in nemoclaw-hermes-recover nemoclaw-hermes-watchdog nemoclaw-model-router \
            nemoclaw-openshell-gateway hydra-direct hydra-hermes-worker; do
  systemctl cat "$unit" 2>/dev/null | redact >"$BACKUP/unit-$unit.txt" || true
done
printf '  backup=%s\n' "$BACKUP"

# -- E. smallest repair ----------------------------------------------------
log "phase E: choosing the smallest reversible repair"

verify_phase() {
  nemohermes "$SANDBOX" status --json 2>/dev/null \
    | grep -oE '"phase"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"([^"]+)"$/\1/'
}

PHASE_BEFORE="$(verify_phase || true)"
printf '  BEFORE  sandbox phase=%s\n' "${PHASE_BEFORE:-UNKNOWN}"

REPAIR="none"
if [[ "$STATUS" == "exited" || "$STATUS" == "created" ]]; then
  REPAIR="docker-start"
  act "start the existing stopped container $CID (no config change)" \
    docker start "$CID"
elif [[ "$STATUS" == "running" ]]; then
  printf '  NOTE    container already running; the failure is above the container layer\n'
  REPAIR="none-container-running"
elif [[ "$STATUS" == "restarting" ]]; then
  # A crash loop. Starting it again is pointless — docker is already doing that,
  # 19 times over in the observed case. What the operator needs is the reason
  # the process exits, so capture it here rather than sending them back for it.
  printf '  NOTE    container status=restarting: docker is already restarting it (%s restarts).\n' "$RESTARTS"
  printf '  NOTE    the start ladder cannot help a crash loop; capturing the crash instead.\n'
  REPAIR="none-crash-loop"
  docker logs --tail 200 "$CID" >"$RUN_DIR/crash-logs.txt" 2>&1 || true
  redact <"$RUN_DIR/crash-logs.txt" >"$RUN_DIR/crash-logs.redacted.txt" || true
  printf '\n  ---- last 30 log lines from the crashing container ----\n'
  tail -30 "$RUN_DIR/crash-logs.redacted.txt" 2>/dev/null | sed 's/^/  | /' \
    || printf '  | (no logs captured)\n'
  printf '  ------------------------------------------------------\n\n'

  # Most of a crashing sandbox's log is OPA symlink noise. The lines that decide
  # what to do are few and named, so classify them instead of leaving the
  # operator to read past the noise.
  if grep -q 'HERMES_MCP_CONFIG_DRIFT' "$RUN_DIR/crash-logs.redacted.txt" 2>/dev/null; then
    REPAIR="none-config-drift"
    printf '  ROOT CAUSE  HERMES_MCP_CONFIG_DRIFT\n'
    printf '              The sandbox is not crashing: it is refusing to start. Hermes\n'
    printf '              hashes the MCP/gateway intent, compares it against the persisted\n'
    printf '              state, and terminates with exit 1 when they disagree. Docker then\n'
    printf '              restarts it, which is the loop you are seeing.\n'
    printf '              Starting it again cannot help — the refusal is deterministic.\n'
    printf '              Vendor remedy: rebuild the sandbox from its NemoClaw registry\n'
    printf '              state. That is DESTRUCTIVE and needs explicit OSA approval; this\n'
    printf '              bundle will not do it for you.\n\n'
    grep -n '\[SECURITY\]' "$RUN_DIR/crash-logs.redacted.txt" 2>/dev/null \
      | tail -5 | sed 's/^/  | /'
    printf '\n'
  elif grep -q '\[SECURITY\]' "$RUN_DIR/crash-logs.redacted.txt" 2>/dev/null; then
    printf '  ROOT CAUSE  a [SECURITY] check terminated the sandbox; see the lines above\n\n'
  fi

  printf '  Restart policy (a loop keeps the state moving while you read it):\n'
  docker inspect -f '  | RestartPolicy={{.HostConfig.RestartPolicy.Name}} MaxRetry={{.HostConfig.RestartPolicy.MaximumRetryCount}}' "$CID" 2>/dev/null || true
  printf '\n'

  # -- OSA-approved rebuild -------------------------------------------------
  # The one destructive path in this bundle. It is reachable only when all four
  # hold: the drift marker was actually found, --execute was given, an approver
  # was named, and this is the config-drift branch. Any other failure mode still
  # exits BLOCKED — this flag is not a general "rebuild whenever" escape hatch.
  if [[ "$REPAIR" == "none-config-drift" && -n "$REBUILD_APPROVED_BY" && $EXECUTE -eq 1 ]]; then
    printf '  OSA APPROVAL recorded: rebuild authorised by "%s"\n' "$REBUILD_APPROVED_BY"
    {
      printf 'approved_by=%s\napproved_at=%s\nroot_cause=HERMES_MCP_CONFIG_DRIFT\ncontainer=%s\nrestarts_before=%s\n' \
        "$REBUILD_APPROVED_BY" "$(utc)" "$CID" "$RESTARTS"
    } >"$RUN_DIR/REBUILD-APPROVAL.txt"

    # Pre-rebuild capture. After the rebuild this evidence cannot be recreated.
    nemohermes "$SANDBOX" doctor --json 2>&1 | redact >"$RUN_DIR/pre-rebuild-doctor.json" || true
    nemoclaw list --json 2>&1 | redact >"$RUN_DIR/pre-rebuild-nemoclaw-list.json" || true
    docker inspect "$CID" 2>&1 | redact >"$RUN_DIR/pre-rebuild-inspect.json" || true

    # The sandbox must be RUNNING for the rebuild, not stopped. `rebuild` raises
    # the shields lock and takes its own backup through the live OpenShell
    # container; with the sandbox down it fails at "Failed to auto-unlock
    # shields" and does nothing. An earlier version of this script stopped it
    # first, which guaranteed that failure.
    printf '  BEFORE  restarts=%s status=%s\n' "$RESTARTS" "$STATUS"
    act "start the sandbox so rebuild can unlock shields and back it up" \
      nemohermes "$SANDBOX" start

    # Wait for the OpenShell-labelled container to actually be running. The
    # sandbox crash-loops, so this catches a live window rather than assuming one.
    if [[ $EXECUTE -eq 1 ]]; then
      for _ in $(seq 1 24); do
        if docker ps --filter "label=openshell.ai/sandbox-name=$SANDBOX" \
             --filter status=running --format '{{.ID}}' 2>/dev/null | grep -q .; then
          printf '  READY   OpenShell container is running; proceeding to rebuild\n'
          break
        fi
        sleep 5
      done
    fi

    act "rebuild the sandbox from its NemoClaw registry state" \
      nemohermes "$SANDBOX" rebuild --yes
    REPAIR="osa-approved-rebuild"

    # Rebuild returns before the sandbox settles; wait rather than judging early.
    for _ in $(seq 1 30); do
      case "$(verify_phase | tr '[:upper:]' '[:lower:]')" in
        ready|running) break ;;
      esac
      sleep 10
    done
  elif [[ "$REPAIR" == "none-config-drift" && -z "$REBUILD_APPROVED_BY" ]]; then
    printf '  HOLD    rebuild is the vendor remedy for this cause but needs approval.\n'
    printf '          Re-run with --execute --rebuild-approved-by=OSA to authorise it.\n\n'
  fi
else
  printf '  NOTE    container status=%s is outside the start ladder\n' "$STATUS"
fi

# Ladder step 2: NemoClaw's own start/recover for this sandbox only.
if [[ "$REPAIR" == "none-container-running" || "$STATUS" == "exited" ]]; then
  if [[ $EXECUTE -eq 1 ]]; then
    sleep 5
    PHASE_MID="$(verify_phase || true)"
    if [[ "${PHASE_MID,,}" != "ready" && "${PHASE_MID,,}" != "running" ]]; then
      REPAIR="nemohermes-start"
      act "ask NemoClaw to start this sandbox only" \
        nemohermes "$SANDBOX" start
    fi
  else
    printf '  ACTION  (dry-run) if still not Ready: nemohermes %s start\n' "$SANDBOX"
  fi
fi

# Ladder step 4: the existing recovery script, restricted to its non-destructive
# half. Phase 4 of recover-hermes.sh is a DESTRUCTIVE rebuild and is skipped by
# --skip-rebuild; this script never calls it without that flag.
printf '\n  Ladder step 4 (only if the above did not help), evidence + validation only:\n'
printf '    scripts/recover-hermes.sh --skip-rebuild --execute\n'
printf '    SKIPPED ACTIONS: phase 4 sandbox rebuild [DESTRUCTIVE], and every action\n'
printf '                     it performs after a rebuild. Never run recover-hermes.sh\n'
printf '                     without --skip-rebuild from this bundle.\n\n'

# -- AFTER -----------------------------------------------------------------
if [[ $EXECUTE -eq 1 ]]; then
  sleep 5
  PHASE_AFTER="$(verify_phase || true)"
  STATUS_AFTER="$(docker inspect -f '{{.State.Status}}' "$CID" 2>/dev/null || echo unknown)"
  printf '  AFTER   container status=%s sandbox phase=%s (repair=%s)\n' \
    "$STATUS_AFTER" "${PHASE_AFTER:-UNKNOWN}" "$REPAIR"
  {
    printf 'repair=%s\nphase_before=%s\nphase_after=%s\nstatus_after=%s\n' \
      "$REPAIR" "${PHASE_BEFORE:-UNKNOWN}" "${PHASE_AFTER:-UNKNOWN}" "$STATUS_AFTER"
  } >"$RUN_DIR/repair-result.txt"

  case "${PHASE_AFTER,,}" in
    ready|running)
      log "RESULT: sandbox reports ${PHASE_AFTER}. Run operator-runtime-verify.sh next."
      ;;
    *)
      log "RESULT: BLOCKED — smallest repair did not reach Ready/Running."
      printf '  Do NOT escalate to rebuild. Hand %s to OSA.\n' "$RUN_DIR"
      exit 3
      ;;
  esac
else
  printf '  AFTER   (dry-run: nothing changed)\n'
  log "dry-run complete. Re-run with --execute when OSA accepts the plan."
fi

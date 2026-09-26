#!/usr/bin/env bash
# Restore the existing Michael Angelo stack. It creates no replacement service,
# writes no unit of its own and starts no second scheduler: every artifact comes
# from HazEOskA/Da-Vinci-Agent-the-Ideal- at a pinned commit.
#
# Dry-run by default. It works out what is missing on this host and applies only
# the smallest restore for each gap.
set -Eeuo pipefail
umask 077

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/operator-lib.sh
source "$HERE/operator-lib.sh"

CANON_REPO="https://github.com/HazEOskA/Da-Vinci-Agent-the-Ideal-"
CANON_BRANCH="deploy/vps-michael-angelo-v0.2"
CANON_SHA="${MICHAEL_ANGELO_SHA:-4eddbff}"
ZGREDEK_BRANCH="feature/zgredek-runtime-v0.1"
ZGREDEK_SHA="${ZGREDEK_SHA:-be879fc}"

MA_ROOT="${MICHAEL_ANGELO_ROOT:-/opt/hydra/apps/michael-angelo-v0.2}"
MA_SECRET="/opt/hydra/secrets/michael-angelo/hermes-api-key"
COMPOSE_PROJECT="michael-angelo-v02"
UNIT="zgredek-tool-broker.service"

EXECUTE=0
for arg in "$@"; do
  case "$arg" in
    --execute) EXECUTE=1 ;;
    --dry-run) EXECUTE=0 ;;
    -h|--help)
      cat <<'USAGE'
usage: operator-stack-restore.sh [--dry-run|--execute]

Restores only what is missing, from the canonical repository at a pinned commit:
  checkout of /opt/hydra/apps/michael-angelo-v0.2
  zgredek-tool-broker.service, installed from the repo's own deploy/systemd
  compose images and the michael-angelo-v02 project (core-api + frontend)

Never done here: writing a credential, starting `michael-angelo daemon`,
creating a second control plane, or authoring a replacement unit or UI.
USAGE
      exit 0 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

require_host
RUN_DIR="$(new_run_dir stack-restore)"
exec > >(tee -a "$RUN_DIR/stack-restore.txt") 2>&1

log "stack restore ($([[ $EXECUTE -eq 1 ]] && echo EXECUTE || echo DRY-RUN))"
printf '  canonical: %s @ %s (%s)\n\n' "$CANON_REPO" "$CANON_SHA" "$CANON_BRANCH"

restored=0
blocked=0

# -- 1. canonical checkout -------------------------------------------------
printf -- '-- 1. checkout %s --\n' "$MA_ROOT"
if [[ -d "$MA_ROOT/.git" ]]; then
  printf '  BEFORE  present, head=%s\n' "$(git -C "$MA_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  act "fetch and pin $MA_ROOT to $CANON_SHA" \
    git -C "$MA_ROOT" fetch origin "$CANON_BRANCH"
  act "checkout $CANON_SHA" git -C "$MA_ROOT" checkout "$CANON_SHA"
else
  printf '  BEFORE  absent — the zgredek unit WorkingDirectory does not exist\n'
  if [[ ! -w "$(dirname "$MA_ROOT")" ]]; then
    printf '  BLOCKED %s is not writable by %s; ask OSA to create it or run this step with sudo\n' \
      "$(dirname "$MA_ROOT")" "$(id -un)"
    blocked=$((blocked + 1))
  else
    act "clone the canonical repository into $MA_ROOT" \
      git clone --branch "$CANON_BRANCH" "$CANON_REPO" "$MA_ROOT"
    act "pin to $CANON_SHA" git -C "$MA_ROOT" checkout "$CANON_SHA"
    restored=$((restored + 1))
  fi
fi
[[ -d "$MA_ROOT/.git" ]] && printf '  AFTER   head=%s\n\n' \
  "$(git -C "$MA_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)" || printf '\n'

# -- 2. compose secret -----------------------------------------------------
# A missing credential is reported, never written. This script does not create,
# copy or generate secret material under any flag.
printf -- '-- 2. compose secret --\n'
if [[ -f "$MA_SECRET" ]]; then
  printf '  BEFORE  present, mode=%s owner=%s (value not read)\n\n' \
    "$(stat -c '%a' "$MA_SECRET")" "$(stat -c '%U' "$MA_SECRET")"
else
  printf '  BLOCKED %s is absent.\n' "$MA_SECRET"
  printf '          core-api mounts it as the hermes_api_key compose secret and will not\n'
  printf '          start without it. This script will not create credential material —\n'
  printf '          OSA must place the existing key there, mode 0400, owner hydra.\n\n'
  blocked=$((blocked + 1))
fi

# -- 3. zgredek broker unit ------------------------------------------------
printf -- '-- 3. %s --\n' "$UNIT"
UNIT_SRC="$MA_ROOT/deploy/systemd/$UNIT"
if [[ "$(systemctl is-enabled "$UNIT" 2>/dev/null || echo not-found)" != "not-found" ]]; then
  printf '  BEFORE  installed, is-active=%s\n\n' "$(systemctl is-active "$UNIT" 2>/dev/null || echo inactive)"
elif [[ -f "$UNIT_SRC" ]]; then
  printf '  BEFORE  not installed; the repository ships it at %s\n' "$UNIT_SRC"
  act "install the repository's own unit (not a new one)" \
    sudo install -o root -g root -m 0644 "$UNIT_SRC" "/etc/systemd/system/$UNIT"
  act "systemctl daemon-reload" sudo systemctl daemon-reload
  act "enable --now $UNIT" sudo systemctl enable --now "$UNIT"
  restored=$((restored + 1))
  [[ $EXECUTE -eq 1 ]] && printf '  AFTER   is-active=%s is-enabled=%s\n\n' \
    "$(systemctl is-active "$UNIT" 2>/dev/null || echo inactive)" \
    "$(systemctl is-enabled "$UNIT" 2>/dev/null || echo unknown)" || printf '\n'
else
  printf '  BLOCKED unit source missing: %s (restore the checkout first)\n\n' "$UNIT_SRC"
  blocked=$((blocked + 1))
fi

# -- 4. compose images and project ----------------------------------------
printf -- '-- 4. compose project %s --\n' "$COMPOSE_PROJECT"
if [[ ! -f "$MA_ROOT/compose.yaml" ]]; then
  printf '  BLOCKED %s/compose.yaml missing (restore the checkout first)\n\n' "$MA_ROOT"
  blocked=$((blocked + 1))
elif [[ ! -f "$MA_SECRET" ]]; then
  printf '  HOLD    not starting compose: the hermes_api_key secret is absent, so core-api\n'
  printf '          would fail to start. Resolve step 2 first.\n\n'
else
  printf '  BEFORE  %s\n' "$(docker compose -p "$COMPOSE_PROJECT" ps --format '{{.Service}}={{.State}}' 2>/dev/null | tr '\n' ' ' || echo 'not deployed')"
  # Only core-api and frontend are defined here. `michael-angelo daemon` is not
  # a compose service, so nothing in this step starts a second scheduler.
  act "build the canonical images" \
    docker compose -f "$MA_ROOT/compose.yaml" -p "$COMPOSE_PROJECT" build
  act "start core-api and frontend only" \
    docker compose -f "$MA_ROOT/compose.yaml" -p "$COMPOSE_PROJECT" up -d
  restored=$((restored + 1))
  if [[ $EXECUTE -eq 1 ]]; then
    for _ in $(seq 1 24); do
      curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:18101/health" 2>/dev/null && break
      sleep 5
    done
    printf '  AFTER   %s\n\n' "$(docker compose -p "$COMPOSE_PROJECT" ps --format '{{.Service}}={{.State}}' 2>/dev/null | tr '\n' ' ')"
  else
    printf '\n'
  fi
fi

# -- verdict ---------------------------------------------------------------
printf -- '-- verdict --\n'
printf '  restored=%s blocked=%s\n' "$restored" "$blocked"
hermes_ok=0
curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:8642/health" 2>/dev/null && hermes_ok=1
if (( hermes_ok == 0 )); then
  printf '\n  Hermes API on 8642 is not answering. core-api targets it and its healthcheck\n'
  printf '  asserts status=="ok", and the frontend waits on core-api being healthy, so\n'
  printf '  the preview on 18100 cannot come up until the Hermes sandbox is repaired.\n'
fi
printf '\n  preview URL (once the chain is healthy): http://127.0.0.1:18100\n'
printf '  evidence: %s\n' "$RUN_DIR"
(( blocked == 0 ))

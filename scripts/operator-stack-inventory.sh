#!/usr/bin/env bash
# Read-only comparison of the runtime host against the canonical Michael Angelo
# stack in HazEOskA/Da-Vinci-Agent-the-Ideal-.
#
# It restores nothing and creates nothing. It answers one question: which parts
# of the existing stack are present on this host, and which are missing.
#
# Canonical branches (pinned):
#   deploy/vps-michael-angelo-v0.2       4eddbff  core-api + frontend
#   feature/zgredek-runtime-v0.1         be879fc  zgredek-tool-broker
#   fix/hermes-api-runtime-20260727      6645baa  Hermes API runtime
set -Eeuo pipefail
umask 077

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/operator-lib.sh
source "$HERE/operator-lib.sh"

MA_ROOT="${MICHAEL_ANGELO_ROOT:-/opt/hydra/apps/michael-angelo-v0.2}"
MA_SECRET="/opt/hydra/secrets/michael-angelo/hermes-api-key"
COMPOSE_PROJECT="michael-angelo-v02"

# port:name:what-it-serves — taken from the canonical compose and Dockerfile,
# not guessed.
declare -a EXPECTED_PORTS=(
  "8642:hermes-api:NemoClaw Hermes sandbox API (core-api depends on it)"
  "18101:ma-core-api:Michael Angelo core API, /health must report status ok"
  "18100:ma-frontend:Atelier UI served by nginx-unprivileged"
  "8787:hydra-control-plane:Hydra, the only top-level scheduler"
  "4000:model-router:NVIDIA model router"
  "8080:openshell-gateway:OpenShell gateway"
)

require_host
RUN_DIR="$(new_run_dir stack-inventory)"
exec > >(tee -a "$RUN_DIR/stack-inventory.txt") 2>&1

printf 'MICHAEL ANGELO STACK INVENTORY  utc=%s host=%s\n' "$(utc)" "$(hostname -s)"
printf 'canonical repo: HazEOskA/Da-Vinci-Agent-the-Ideal-\n'
printf 'evidence: %s\n\n' "$RUN_DIR"

missing=0
present=0
note() { printf '  %-9s %-22s %s\n' "$1" "$2" "${3:-}"; }
found()  { note PRESENT "$1" "${2:-}"; present=$((present + 1)); }
absent() { note MISSING "$1" "${2:-}"; missing=$((missing + 1)); }

# -- code checkout ---------------------------------------------------------
printf -- '-- canonical checkout --\n'
if [[ -d "$MA_ROOT/.git" ]]; then
  found "$MA_ROOT" "origin=$(git -C "$MA_ROOT" remote get-url origin 2>/dev/null || echo none)"
  printf '  %-9s %-22s branch=%s head=%s dirty=%s\n' "" "" \
    "$(git -C "$MA_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)" \
    "$(git -C "$MA_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)" \
    "$([[ -n "$(git -C "$MA_ROOT" status --porcelain 2>/dev/null)" ]] && echo yes || echo no)"
elif [[ -d "$MA_ROOT" ]]; then
  absent "$MA_ROOT" "directory exists but is not a git checkout"
else
  absent "$MA_ROOT" "the zgredek unit's WorkingDirectory does not exist"
fi

# -- systemd ---------------------------------------------------------------
printf -- '\n-- systemd units --\n'
for unit in zgredek-tool-broker.service hydra-hermes-worker.service; do
  state="$(systemctl is-enabled "$unit" 2>/dev/null || echo not-found)"
  active="$(systemctl is-active "$unit" 2>/dev/null || echo inactive)"
  if [[ "$state" == "not-found" ]]; then
    absent "$unit" "not installed"
  else
    found "$unit" "is-enabled=$state is-active=$active"
  fi
done

# -- compose ---------------------------------------------------------------
printf -- '\n-- compose project %s --\n' "$COMPOSE_PROJECT"
if docker compose ls --all --format json 2>/dev/null | grep -q "$COMPOSE_PROJECT"; then
  found "compose project" "declared"
  docker compose -p "$COMPOSE_PROJECT" ps --format '  {{.Service}} {{.State}} {{.Status}}' 2>/dev/null || true
else
  absent "compose project" "$COMPOSE_PROJECT is not deployed"
fi
for image in michael-angelo-core:runtime-seam-v0.2 michael-angelo-ui:runtime-seam-v0.2; do
  if docker image inspect "$image" >/dev/null 2>&1; then found "image $image"; else absent "image $image" "not built"; fi
done

# -- secret ----------------------------------------------------------------
# Presence and mode only. The value is never read, printed or copied.
printf -- '\n-- compose secret --\n'
if [[ -f "$MA_SECRET" ]]; then
  found "hermes-api-key" "mode=$(stat -c '%a' "$MA_SECRET" 2>/dev/null) owner=$(stat -c '%U' "$MA_SECRET" 2>/dev/null) (value not read)"
else
  absent "hermes-api-key" "$MA_SECRET"
fi

# -- listeners -------------------------------------------------------------
printf -- '\n-- listeners --\n'
for entry in "${EXPECTED_PORTS[@]}"; do
  port="${entry%%:*}"; rest="${entry#*:}"; name="${rest%%:*}"; desc="${rest#*:}"
  if ss -tulpn 2>/dev/null | grep -qE "[:.]$port\b"; then
    found "$name" "port $port"
  else
    absent "$name" "port $port — $desc"
  fi
done

# -- health ----------------------------------------------------------------
printf -- '\n-- health probes --\n'
probe() {
  local name="$1" url="$2"
  local code; code="$(curl -fsS --max-time 8 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo none)"
  [[ "$code" == "200" ]] && found "$name" "HTTP $code" || absent "$name" "HTTP $code at $url"
}
probe "hermes-api /health"   "http://127.0.0.1:8642/health"
probe "ma-core-api /health"  "http://127.0.0.1:18101/health"
probe "ma-frontend"          "http://127.0.0.1:18100/"

# -- verdict ---------------------------------------------------------------
printf -- '\n-- verdict --\n'
printf '  present=%s missing=%s\n' "$present" "$missing"
printf '\n  Dependency order is fixed by the canonical compose:\n'
printf '    Hermes API :8642  ->  ma-core-api :18101  ->  ma-frontend :18100\n'
printf '    core-api healthcheck asserts status=="ok"; the frontend has\n'
printf '    depends_on: core-api service_healthy, so the preview cannot come up\n'
printf '    while the Hermes sandbox is down.\n'
printf '\n  The canonical compose starts core-api and frontend only. It does NOT\n'
printf '  start `michael-angelo daemon`, so restoring it as-is keeps Hydra the\n'
printf '  single top-level scheduler.\n'
printf '\n  evidence: %s\n' "$RUN_DIR"
[[ $missing -eq 0 ]]

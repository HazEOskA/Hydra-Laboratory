#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ "${1:-}" != "--execute" || $# -ne 1 ]]; then
  printf 'Refusing to install. Review docs/DEPLOYMENT_PLAN.md, then run with --execute after explicit approval.\n' >&2
  exit 2
fi

: "${NVIDIA_INFERENCE_API_KEY:?NVIDIA_INFERENCE_API_KEY must be supplied by the approved host secret mechanism}"
[[ -n "${NEMOCLAW_MODEL_ROUTER_PYTHON:-}" ]] || { printf 'Run remote-preflight.sh and export the validated absolute NEMOCLAW_MODEL_ROUTER_PYTHON path.\n' >&2; exit 2; }
[[ "$NEMOCLAW_MODEL_ROUTER_PYTHON" = /* ]] || { printf 'NEMOCLAW_MODEL_ROUTER_PYTHON must be absolute.\n' >&2; exit 2; }

"$(dirname "$0")/remote-preflight.sh"
command -v nemoclaw >/dev/null 2>&1 && { printf 'NemoClaw already exists; use onboard-hermes.sh instead of reinstalling.\n' >&2; exit 3; }

export NEMOCLAW_AGENT=hermes
export NEMOCLAW_PROVIDER=routed
export NEMOCLAW_SANDBOX_NAME=hydra-hermes-lab
export NEMOCLAW_NON_INTERACTIVE=1
export NEMOCLAW_ACCEPT_THIRD_PARTY_SOFTWARE=1
export NEMOCLAW_WEB_SEARCH_PROVIDER=none
export NEMOCLAW_POLICY_TIER=balanced

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
installer="$tmpdir/nemoclaw.sh"
curl -fsSL --proto '=https' --tlsv1.2 https://www.nvidia.com/nemoclaw.sh -o "$installer"
test -s "$installer"
chmod 700 "$installer"
bash "$installer"

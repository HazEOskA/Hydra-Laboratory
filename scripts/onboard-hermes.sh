#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

[[ "$(id -un)" == hydra ]] || { printf 'Run as the dedicated hydra user.\n' >&2; exit 2; }
[[ "$(hostname -s)" == hydra-hermes-runtime-01 ]] || { printf 'Unexpected host. Refusing outside hydra-hermes-runtime-01.\n' >&2; exit 2; }

if [[ "${1:-}" != "--execute" || $# -ne 1 ]]; then
  printf 'Refusing to onboard. Run with --execute only after explicit approval.\n' >&2
  exit 2
fi

: "${NVIDIA_INFERENCE_API_KEY:?NVIDIA_INFERENCE_API_KEY must be supplied by the approved host secret mechanism}"
: "${NEMOCLAW_MODEL_ROUTER_PYTHON:?Export the validated absolute Model Router Python path}"
[[ "$NEMOCLAW_MODEL_ROUTER_PYTHON" = /* ]] || { printf 'NEMOCLAW_MODEL_ROUTER_PYTHON must be absolute.\n' >&2; exit 2; }
command -v nemoclaw >/dev/null 2>&1 || { printf 'NemoClaw is not installed; use install-nemoclaw.sh.\n' >&2; exit 3; }
command -v nemohermes >/dev/null 2>&1 || { printf 'nemohermes is unavailable.\n' >&2; exit 3; }

if nemoclaw list --json 2>/dev/null | grep -Fq '"hydra-hermes-lab"'; then
  printf 'Sandbox collision: hydra-hermes-lab already exists. Refusing to reuse or destroy it.\n' >&2
  exit 4
fi

export NEMOCLAW_AGENT=hermes
export NEMOCLAW_PROVIDER=routed
export NEMOCLAW_SANDBOX_NAME=hydra-hermes-lab
export NEMOCLAW_NON_INTERACTIVE=1
export NEMOCLAW_ACCEPT_THIRD_PARTY_SOFTWARE=1
export NEMOCLAW_WEB_SEARCH_PROVIDER=none
export NEMOCLAW_POLICY_TIER=balanced
unset TAVILY_API_KEY BRAVE_API_KEY TELEGRAM_BOT_TOKEN DISCORD_BOT_TOKEN
unset SLACK_BOT_TOKEN SLACK_APP_TOKEN WHATSAPP_TOKEN WECHAT_BOT_TOKEN
unset NEMOCLAW_HERMES_TOOL_GATEWAYS NEMOCLAW_HERMES_TOOL_GATEWAY_PRESETS
unset NEMOCLAW_EXTRA_PLACEHOLDER_KEYS

nemohermes onboard --non-interactive

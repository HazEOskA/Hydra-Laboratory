#!/usr/bin/env bash
set -Eeuo pipefail

LOCKED="hydra-hermes-lab"
sandbox=""
confirmation=""

while (( $# )); do
  case "$1" in
    --sandbox) sandbox="${2:-}"; shift 2 ;;
    --confirm-destroy) confirmation="${2:-}"; shift 2 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

[[ "$sandbox" == "$LOCKED" ]] || { printf 'Refusing: only sandbox %s may be targeted.\n' "$LOCKED" >&2; exit 3; }
[[ "$confirmation" == "$LOCKED" ]] || { printf 'Refusing: exact confirmation is required.\n' >&2; exit 3; }
command -v nemohermes >/dev/null 2>&1 || { printf 'nemohermes unavailable.\n' >&2; exit 4; }

nemohermes "$LOCKED" status
printf 'Destructive operation approved for exactly: %s\n' "$LOCKED"
nemohermes "$LOCKED" destroy --yes

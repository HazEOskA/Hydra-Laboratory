#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  printf 'Usage: TS_RUNTIME_AUTH_KEY=<secret> %s --output /absolute/path/cloud-init.rendered.yaml\n' "${0##*/}" >&2
  exit 2
}

[[ $# -eq 2 && "$1" == --output ]] || usage
output="$2"
[[ "$output" == /* ]] || { printf 'BLOCKED: output path must be absolute.\n' >&2; exit 1; }

root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$root" ]] || { printf 'BLOCKED: repository root is unavailable.\n' >&2; exit 1; }
template="$root/infra/cloud-init.yaml"

case "$output" in
  "$root"|"$root"/*)
    printf 'BLOCKED: rendered cloud-init must be written outside the repository.\n' >&2
    exit 1
    ;;
esac

: "${TS_RUNTIME_AUTH_KEY:?TS_RUNTIME_AUTH_KEY must be supplied by an approved external secret flow}"
[[ "$TS_RUNTIME_AUTH_KEY" != *$'\n'* && "$TS_RUNTIME_AUTH_KEY" != *$'\r'* ]] \
  || { printf 'BLOCKED: auth key contains a line break.\n' >&2; exit 1; }
[[ ! -e "$output" ]] || { printf 'BLOCKED: refusing to overwrite output.\n' >&2; exit 1; }
[[ "$(grep -Foc '__TS_RUNTIME_AUTH_KEY_B64__' "$template")" -eq 1 ]] \
  || { printf 'BLOCKED: template marker contract changed.\n' >&2; exit 1; }

umask 077
encoded="$(printf '%s' "$TS_RUNTIME_AUTH_KEY" | base64 | tr -d '\n')"
export HYDRA_RENDERED_TS_AUTH_KEY_B64="$encoded"
unset encoded

tmp="${output}.tmp.$$"
cleanup() {
  unset HYDRA_RENDERED_TS_AUTH_KEY_B64 TS_RUNTIME_AUTH_KEY
  rm -f -- "$tmp"
}
trap cleanup EXIT

awk '
  {
    gsub(/__TS_RUNTIME_AUTH_KEY_B64__/, ENVIRON["HYDRA_RENDERED_TS_AUTH_KEY_B64"])
    print
  }
' "$template" > "$tmp"
chmod 0600 "$tmp"
! grep -Fq '__TS_RUNTIME_AUTH_KEY_B64__' "$tmp"
mv -- "$tmp" "$output"
printf 'Rendered cloud-init created outside the repository with mode 0600.\n'

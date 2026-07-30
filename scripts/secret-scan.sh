#!/usr/bin/env bash
set -Eeuo pipefail

root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$root"

mapfile -t files < <(git ls-files --cached --others --exclude-standard | grep -v '^scripts/secret-scan\.sh$' || true)
(( ${#files[@]} > 0 )) || { printf 'SECRET SCAN: PASS (no files)\n'; exit 0; }

bad_names=0
for file in "${files[@]}"; do
  case "$file" in
    .env|.env.*|*.key|*.pem|*.token|secrets/*|.private/*)
      printf 'Forbidden secret-bearing path: %s\n' "$file" >&2
      bad_names=1
      ;;
  esac
done

patterns='BEGIN [A-Z ]*PRIVATE KEY|gh[pousr]_[A-Za-z0-9_]{20,}|NVIDIA_INFERENCE_API_KEY[[:space:]]*=[[:space:]]*[^<[:space:]#][^[:space:]]*|TS_RUNTIME_AUTH_KEY[[:space:]]*=[[:space:]]*[^<[:space:]#][^[:space:]]*|tskey-(auth|client|api)-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}'

# Redaction tests must contain credential-shaped strings to prove anything.
# Such a line has to carry the marker below, so every exemption stays greppable.
allowlist_marker='secret-scan: synthetic fixture'
matches="$(grep -nEI "$patterns" "${files[@]}" 2>/dev/null | grep -Fv "$allowlist_marker" || true)"
if [[ -n "$matches" ]]; then
  printf 'Potential secret material detected:\n%s\n' "$matches" >&2
  exit 1
fi
(( bad_names == 0 )) || exit 1
printf 'SECRET SCAN: PASS (%d files)\n' "${#files[@]}"

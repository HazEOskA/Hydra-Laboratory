#!/usr/bin/env bash
# Automation B: repository watch (*/30).
#
# Read-only. It reports; it does not commit, push or clean. It also never leaves
# the configured roots, so an unrelated repository on the host is never touched.
# shellcheck disable=SC2015
set -Eeuo pipefail
umask 077

STATE_DIR="${HERMES_WORKER_STATE_DIR:-/var/lib/hydra-hermes/worker}"
ROOTS="${HERMES_REPO_ROOTS:-${HYDRA_BASE_PATH:-/opt/hydra}:$HOME}"
out_dir="$STATE_DIR/reports"
mkdir -p "$out_dir"

findings=0
note() { printf -- '- %s\n' "$*"; findings=$((findings + 1)); }

{
  printf '# Repository Watch\n\n- generated: %s\n\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  while IFS= read -r gitdir; do
    repo="$(dirname "$gitdir")"
    printf '## %s\n\n' "$repo"
    branch="$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null || printf unknown)"
    commit="$(git -C "$repo" rev-parse --short HEAD 2>/dev/null || printf unknown)"
    printf -- '- branch: %s @ %s\n' "$branch" "$commit"

    dirty="$(git -C "$repo" status --porcelain 2>/dev/null | wc -l)"
    (( dirty > 0 )) && note "$dirty uncommitted change(s)" || printf -- '- working tree clean\n'

    unpushed="$(git -C "$repo" log --oneline '@{upstream}..HEAD' 2>/dev/null | wc -l)"
    (( unpushed > 0 )) && note "$unpushed unpushed commit(s) on $branch" || true

    last="$(git -C "$repo" log -1 --format=%ct 2>/dev/null || printf 0)"
    if (( last > 0 )); then
      age_days=$(( ( $(date -u +%s) - last ) / 86400 ))
      (( age_days > 30 )) && note "no commit in $age_days days" || true
    fi

    # A committed secret is the one finding that must never wait for a human to notice.
    if [[ -x "$repo/scripts/secret-scan.sh" ]]; then
      ( cd "$repo" && ./scripts/secret-scan.sh >/dev/null 2>&1 ) \
        || note "SECRET SCAN FAILED — inspect immediately"
    fi
    printf '\n'
  done < <(
    IFS=':' read -ra roots <<<"$ROOTS"
    find "${roots[@]}" -maxdepth 4 -type d -name .git 2>/dev/null | sort -u
  )
  printf '\n**Findings: %d**\n' "$findings"
  printf '\nRead-only report. No repository was modified.\n'
} >"$out_dir/repo-watch-$(date -u +%Y-%m-%d).md"

printf 'REPO WATCH: findings=%d report=%s\n' "$findings" \
  "$out_dir/repo-watch-$(date -u +%Y-%m-%d).md"

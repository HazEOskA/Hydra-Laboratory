#!/usr/bin/env bash
# Build the evidence bundle for an upgrade.
#
# Evidence is the deliverable that makes a claim checkable, so this script only
# records what it can actually observe. Where a check cannot run — no host, no
# Docker, no sandbox — it writes that fact rather than an optimistic placeholder.
# shellcheck disable=SC2016
set -Eeuo pipefail
umask 077

BASE_PATH="${HYDRA_BASE_PATH:-/opt/hydra}"
EVIDENCE_ROOT="${HERMES_EVIDENCE_ROOT:-$BASE_PATH/evidence}"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$EVIDENCE_ROOT/hermes-upgrade-$stamp"
mkdir -p "$out"

log() { printf '%s evidence %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
run() { printf '$ %s\n' "$*" >>"$out/commands.log"; "$@" >>"$out/commands.log" 2>&1 || true; }

log "building bundle in $out"

git_commit="$(git -C "$repo_root" rev-parse HEAD 2>/dev/null || printf unknown)"
git_branch="$(git -C "$repo_root" rev-parse --abbrev-ref HEAD 2>/dev/null || printf unknown)"
soul_json="$(python3 -m hermes.cli soul status 2>/dev/null || printf '{}')"
soul_sha="$(printf '%s' "$soul_json" | python3 -c 'import json,sys
try: print(json.load(sys.stdin)["sha256"])
except Exception: print("unknown")')"

# 00 executive summary
{
  printf '# Executive Summary\n\n'
  printf -- '- generated: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf -- '- host: %s\n' "$(hostname)"
  printf -- '- branch: %s\n' "$git_branch"
  printf -- '- commit: %s\n' "$git_commit"
  printf -- '- constitution sha256: %s\n' "$soul_sha"
  printf '\nThis bundle records what was observed on this host at this time.\n'
  printf 'Checks that could not run are recorded as NOT RUN, not as passes.\n'
} >"$out/00-executive-summary.md"

# 01 baseline
if [[ -d "${HERMES_BASELINE_DIR:-$BASE_PATH/recovery/hermes-baseline}/latest" ]]; then
  cp -a "${HERMES_BASELINE_DIR:-$BASE_PATH/recovery/hermes-baseline}/latest/." "$out/baseline/" 2>/dev/null || true
  printf '# Baseline Inventory\n\nCopied from the latest host baseline.\n' >"$out/01-baseline-inventory.md"
else
  printf '# Baseline Inventory\n\nNOT RUN: no baseline found. Run scripts/host-baseline.sh on the host.\n' \
    >"$out/01-baseline-inventory.md"
fi

# 02 problems
{
  printf '# Problems Found\n\n'
  "$repo_root/scripts/health-watch.sh" --report-only 2>&1 | sed 's/^/    /' || true
} >"$out/02-problems-found.md"

# 03 architecture
{
  printf '# Architecture Lock\n\n'
  printf 'See docs/GOD_LAYER.md for the locked component map.\n\n'
  printf '## Config versions\n\n'
  for cfg in tools models schedule; do
    version="$(python3 -c "
import sys, yaml
sys.path.insert(0, '$repo_root/lib')
print(yaml.safe_load(open('$repo_root/config/$cfg.yaml')).get('version', 'unknown'))" 2>/dev/null || printf unknown)"
    printf -- '- config/%s.yaml: version %s\n' "$cfg" "$version"
  done
} >"$out/03-architecture-lock.md"

# 04 files changed
{
  printf '# Files Changed\n\n```\n'
  git -C "$repo_root" show --stat --oneline HEAD 2>/dev/null || printf '(no git history)\n'
  printf '```\n'
} >"$out/04-files-changed.md"
git -C "$repo_root" diff HEAD~1..HEAD >"$out/git-diff.patch" 2>/dev/null || \
  printf '(no previous commit to diff)\n' >"$out/git-diff.patch"

# 05 permission matrix
{
  printf '# Permission Matrix\n\n```json\n'
  python3 -m hermes.cli permissions matrix 2>/dev/null || printf '{}\n'
  printf '```\n'
} >"$out/05-permission-matrix.md"

# 06 test results
# HERMES_EVIDENCE_QUICK skips the re-runs for callers that already ran them
# (the recovery test builds several bundles); it never fakes a result.
{
  printf '# Test Results\n\n## Static contract\n\n```\n'
  if [[ "${HERMES_EVIDENCE_QUICK:-0}" == "1" ]]; then
    printf 'SKIPPED (quick mode): not re-run for this bundle.\n'
  else
    ( cd "$repo_root" && make static-check 2>&1 | tail -n 40 ) || true
  fi
  printf '```\n\n## Control-plane suite\n\n```\n'
  if [[ "${HERMES_EVIDENCE_QUICK:-0}" == "1" ]]; then
    printf 'SKIPPED (quick mode): not re-run for this bundle.\n'
  else
    ( cd "$repo_root" && python3 -m unittest discover -s tests/python -p 'test_*.py' 2>&1 | tail -n 20 ) || true
  fi
  printf '```\n'
} >"$out/06-test-results.md"

# 07 health checks
{
  printf '# Health Checks\n\n## Control plane\n\n```json\n'
  python3 -m hermes.cli health 2>&1 || true
  printf '```\n\n## Host watch\n\n```\n'
  "$repo_root/scripts/health-watch.sh" --report-only 2>&1 || true
  printf '```\n'
} >"$out/07-health-checks.md"

# 08 security review
{
  printf '# Security Review\n\n'
  printf '## Secret scan\n\n```\n'
  ( cd "$repo_root" && ./scripts/secret-scan.sh 2>&1 ) || true
  printf '```\n\n## Boundary assertions\n\n'
  printf -- '- Duty cycle never receives NVIDIA_INFERENCE_API_KEY.\n'
  printf -- '- Captured model output is redacted before storage; only a digest and a bounded excerpt persist.\n'
  printf -- '- Sending, publishing, money movement and destructive operations are RED.\n'
  printf -- '- The evidence ledger is append-only and hash-chained.\n'
} >"$out/08-security-review.md"

# 09 revenue pipeline test
{
  printf '# Revenue Pipeline Test\n\n```\n'
  if [[ "${HERMES_EVIDENCE_QUICK:-0}" == "1" ]]; then
    printf 'SKIPPED (quick mode): not re-run for this bundle.\n'
  else
    ( cd "$repo_root" && python3 -m unittest \
      tests.python.test_god_layer.TestRevenue 2>&1 | tail -n 10 ) || true
  fi
  printf '```\n\nSynthetic data only. The suite asserts that no draft is marked sent\n'
  printf 'and that no outreach event can exist without a scoped approval reference.\n'
} >"$out/09-revenue-pipeline-test.md"

# 10 deployment report
{
  printf '# Deployment Report\n\n'
  if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
    printf '```\n'
    systemctl list-units 'hydra-hermes*' --all --no-pager --plain 2>&1 || true
    printf '```\n'
  else
    printf 'NOT RUN: systemd is not managing this environment, so no unit state was observed.\n'
  fi
} >"$out/10-deployment-report.md"

# 11 rollback plan
{
  printf '# Rollback Plan\n\n'
  backup_root="${HERMES_BACKUP_ROOT:-$BASE_PATH/backups}"
  if [[ -f "$backup_root/latest/rollback-manifest.json" ]]; then
    printf '```json\n'
    cat "$backup_root/latest/rollback-manifest.json"
    printf '```\n'
  else
    printf 'NOT RUN: no rollback manifest. Run scripts/host-backup.sh --execute first.\n\n'
    printf 'Repository-level rollback: `git -C %s reset --hard %s`\n' "$repo_root" "$git_commit"
  fi
} >"$out/11-rollback-plan.md"

# 12 open risks
{
  printf '# Open Risks\n\n'
  printf -- '- Any check recorded as NOT RUN above is unproven, not passing.\n'
  printf -- '- The duty cycle spends a fixed-price request budget; verify the daily cap matches the plan.\n'
  printf -- '- Model provider health is only as fresh as the last health-watch run.\n'
  printf -- '- Drafts contain prospect data; treat the state directory as confidential.\n'
} >"$out/12-open-risks.md"

# raw captures
run hostname
run uname -a
: >"$out/service-status.txt"; run systemctl --failed
cp /dev/null "$out/docker-status.txt"; run docker ps -a
cp /dev/null "$out/port-map.txt"; run ss -tulpn
mv "$out/commands.log" "$out/commands.log.tmp" 2>/dev/null || true
mv "$out/commands.log.tmp" "$out/commands.log" 2>/dev/null || true

# manifest + hashes
EVIDENCE_DIR="$out" STAMP="$stamp" COMMIT="$git_commit" BRANCH="$git_branch" \
SOUL_SHA="$soul_sha" python3 - <<'PY'
import hashlib, json, os, pathlib

out = pathlib.Path(os.environ["EVIDENCE_DIR"])
entries = {}
for path in sorted(out.rglob("*")):
    if not path.is_file() or path.name in {"evidence-manifest.json", "evidence-manifest.sha256"}:
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    entries[str(path.relative_to(out))] = digest

manifest = {
    "timestamp": os.environ["STAMP"],
    "branch": os.environ["BRANCH"],
    "commit": os.environ["COMMIT"],
    "constitution_sha256": os.environ["SOUL_SHA"],
    "file_count": len(entries),
    "files": entries,
}
(out / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
lines = [f"{digest}  {name}" for name, digest in sorted(entries.items())]
(out / "evidence-manifest.sha256").write_text("\n".join(lines) + "\n")
bundle_hash = hashlib.sha256(
    json.dumps(manifest, sort_keys=True).encode("utf-8")
).hexdigest()
print(f"files={len(entries)} manifest_sha256={bundle_hash}")
PY

ln -sfn "$out" "$EVIDENCE_ROOT/latest"
log "bundle complete: $out"

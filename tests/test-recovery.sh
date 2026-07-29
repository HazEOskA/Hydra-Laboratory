#!/usr/bin/env bash
# Offline proof for scripts/recover-hermes.sh.
#
# The recovery script rebuilds a production sandbox, so its guard rails cannot be
# tested for the first time in production. Stub CLIs on PATH stand in for
# nemoclaw/nemohermes and friends, and the three paths that matter are exercised:
# a credential visible in-sandbox fails the run, a repeated hypothesis is
# refused, and a healthy runtime passes.
# shellcheck disable=SC2015
set -Eeuo pipefail

failures=0
pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*" >&2; failures=$((failures + 1)); }

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
recover="$repo_root/scripts/recover-hermes.sh"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
stub_bin="$workdir/bin"
mkdir -p "$stub_bin"

# Build a stub CLI set. KEY_STATE decides what the in-sandbox credential probe
# reports, which is the invariant under test.
make_stubs() {
  local phase="$1" key_state="$2" rebuild_exit="${3:-0}"

  cat >"$stub_bin/nemohermes" <<STUB
#!/usr/bin/env bash
case "\$*" in
  *"status --json"*)
    printf '%s\n' "✓ Active gateway set to 'nemoclaw'"
    printf '{"schemaVersion":1,"name":"hydra-hermes-lab","found":true,"agent":"hermes","phase":"$phase","model":"nvidia/nemotron-3-super-120b-a12b","provider":"nvidia-prod","liveRoute":{"provider":"nvidia-prod","model":"nvidia/nemotron-3-super-120b-a12b"},"routeDrift":null}\n'
    ;;
  *"doctor"*) printf '{"ok":true,"checks":[]}\n' ;;
  *"logs"*) printf 'stub sandbox log line\n' ;;
  *NVIDIA_INFERENCE_API_KEY*) printf '$key_state\n' ;;
  *OPENAI_BASE_URL*) printf 'OPENAI_BASE_URL=https://inference.local/v1\nendpoint reachable: 200\n' ;;
  *"RECOVERY_PROBE_OK"*) printf 'RECOVERY_PROBE_OK\n' ;;
  *"tool names"*) printf 'NONE\n' ;;
  *restart*|*stop*) printf 'ok\n' ;;
  *) printf 'stub nemohermes: \$*\n' ;;
esac
exit 0
STUB

  cat >"$stub_bin/nemoclaw" <<STUB
#!/usr/bin/env bash
case "\$*" in
  *rebuild*) printf 'rebuild output\n'; exit $rebuild_exit ;;
  *"inference get"*) printf '{"provider":"nvidia-prod"}\n' ;;
  *"list --json"*) printf '["hydra-hermes-lab"]\n' ;;
  *logs*) printf 'stub nemoclaw log line\n' ;;
  *) printf 'stub nemoclaw: \$*\n' ;;
esac
exit 0
STUB

  cat >"$stub_bin/ss" <<'STUB'
#!/usr/bin/env bash
case "$*" in
  *8642*) printf '127.0.0.1:8642\n' ;;
  *18789*) printf '127.0.0.1:18789\n' ;;
  *) printf 'stub ss\n' ;;
esac
exit 0
STUB

  cat >"$stub_bin/curl" <<'STUB'
#!/usr/bin/env bash
for arg in "$@"; do
  case "$arg" in
    *8642*|*18789*) printf '{"status":"ok"}\n'; exit 0 ;;
  esac
done
exit 0
STUB

  cat >"$stub_bin/pgrep" <<'STUB'
#!/usr/bin/env bash
printf '1234 hermes-agent\n'
exit 0
STUB

  cat >"$stub_bin/tailscale" <<'STUB'
#!/usr/bin/env bash
printf 'stub tailscale\n'
exit 0
STUB

  chmod +x "$stub_bin"/*
}

run_recovery() {
  local state_dir="$1"; shift
  PATH="$stub_bin:$PATH" \
  HERMES_LOCKED_HOST="$(hostname -s)" \
  HERMES_WORKER_STATE_DIR="$state_dir" \
  HERMES_BACKUP_ROOT="$workdir/backups" \
  HYDRA_BASE_PATH="$workdir/hydra" \
  HERMES_EVIDENCE_ROOT="$workdir/evidence" \
  HERMES_EVIDENCE_QUICK=1 \
  HYDRA_DIRECT_INSTALL_URL="https://example.invalid/installer.sh" \
  HERMES_READY_TIMEOUT=10 HERMES_READY_POLL=1 HERMES_RESTART_TIMEOUT=10 \
  "$recover" "$@"
}

# 1. Dry run is the default and changes nothing.
state="$workdir/dry"
make_stubs Ready ABSENT
if out="$(run_recovery "$state" 2>&1)"; then
  if grep -q 'dry run; nothing is changed' <<<"$out" && [[ ! -d "$state/recovery" ]]; then
    pass 'default invocation is a dry run that changes nothing'
  else
    fail 'dry run altered state or printed the wrong plan'
  fi
else
  fail 'dry run exited non-zero'
fi

# 2. THE invariant: a credential visible inside the sandbox fails the run.
state="$workdir/leak"
make_stubs Ready PRESENT
set +e
run_recovery "$state" --execute --hypothesis "first attempt" >"$workdir/leak.out" 2>&1
leak_exit=$?
set -e
if (( leak_exit == 7 )); then
  pass 'an exposed provider credential fails the run with the reserved exit code'
else
  fail "credential exposure did not fail the run (exit $leak_exit)"
fi
if [[ -f "$state/recovery/latest/SECURITY-FAILURE.md" ]] \
  && grep -q 'NOT be marked healthy' "$state/recovery/latest/SECURITY-FAILURE.md"; then
  pass 'credential exposure writes the security-failure record'
else
  fail 'no security-failure record was written'
fi
if grep -q 'SECURITY FAILURE' "$workdir/leak.out"; then
  pass 'credential exposure is reported, not swallowed'
else
  fail 'credential exposure was not reported'
fi
# Everything after the credential check must be skipped.
if ! grep -q 'RECOVERY_PROBE_OK' "$workdir/leak.out"; then
  pass 'validation stops at the credential boundary instead of continuing'
else
  fail 'the run continued past an exposed credential'
fi

# 3. Evidence is captured before the rebuild, never after it.
if [[ -s "$state/recovery/latest/doctor-pre-rebuild.txt" \
   && -s "$state/recovery/latest/logs-pre-rebuild.txt" ]]; then
  pass 'pre-rebuild doctor output and logs are preserved'
else
  fail 'pre-rebuild evidence is missing'
fi

# 4. The rebuild failure policy: the same hypothesis twice is refused.
state="$workdir/policy"
make_stubs Ready ABSENT
run_recovery "$state" --execute --hypothesis "upgrade to 0.0.93 broke startup" \
  >/dev/null 2>&1 || true
set +e
run_recovery "$state" --execute --hypothesis "upgrade to 0.0.93 broke startup" \
  >"$workdir/policy.out" 2>&1
repeat_exit=$?
set -e
if (( repeat_exit == 5 )) && grep -q 'same hypothesis' "$workdir/policy.out"; then
  pass 'a repeated hypothesis is refused rather than rebuilt again'
else
  fail "repeated-hypothesis guard did not hold (exit $repeat_exit)"
fi
set +e
run_recovery "$state" --execute --hypothesis "different: tool-gateway broker" >/dev/null 2>&1
new_exit=$?
set -e
attempts="$(grep -c . "$state/recovery/rebuild-attempts.jsonl" 2>/dev/null || printf 0)"
if (( new_exit != 5 )) && (( attempts >= 2 )); then
  pass 'a new hypothesis is allowed to proceed and is recorded'
else
  fail "a new hypothesis was refused (exit $new_exit, attempts $attempts)"
fi

# 5. A failing rebuild preserves logs and writes the comparison, without retrying.
state="$workdir/rebuildfail"
make_stubs Ready ABSENT 1
set +e
run_recovery "$state" --execute --hypothesis "rebuild failure path" \
  >"$workdir/rebuildfail.out" 2>&1
rebuild_exit=$?
set -e
if (( rebuild_exit == 6 )) \
  && [[ -f "$state/recovery/latest/rebuild-failure-analysis.md" ]] \
  && grep -q 'Do not rebuild again without a new hypothesis' "$workdir/rebuildfail.out"; then
  pass 'a failed rebuild preserves evidence and refuses to loop'
else
  fail "rebuild failure path is wrong (exit $rebuild_exit)"
fi

# 6. Healthy runtime: the run completes and records the checklist.
state="$workdir/healthy"
make_stubs Ready ABSENT
run_recovery "$state" --execute --hypothesis "healthy path check" \
  >"$workdir/healthy.out" 2>&1 || true
if [[ -f "$state/recovery/latest/RESULT.md" ]] \
  && grep -q 'checks passed' "$state/recovery/latest/RESULT.md"; then
  pass 'a completed run writes RESULT.md with the checklist'
else
  fail 'RESULT.md was not written'
fi
for expected in \
  'NVIDIA_INFERENCE_API_KEY is absent inside the sandbox' \
  'GREEN dispatches without approval' \
  'YELLOW checkpoints, audits and dispatches' \
  'RED blocks for scoped approval' \
  'RED resumes only after scoped approval'; do
  if grep -qF "$expected" "$state/recovery/latest/checklist.txt" 2>/dev/null; then
    pass "checklist records: $expected"
  else
    fail "checklist missing: $expected"
  fi
done

# 7. Unavailable web tooling is recorded as unavailable, never assumed present.
if grep -q 'web/research tooling is NOT available' "$state/recovery/latest/checklist.txt"; then
  pass 'absent web tooling is reported truthfully'
else
  fail 'web tooling availability was not reported truthfully'
fi

# 8. The host lock still refuses a foreign host.
set +e
PATH="$stub_bin:$PATH" HERMES_LOCKED_HOST="some-other-host" \
  HERMES_WORKER_STATE_DIR="$workdir/lock" "$recover" --execute --hypothesis x \
  >/dev/null 2>&1
lock_exit=$?
set -e
if (( lock_exit == 2 )); then
  pass 'recovery refuses to run on the wrong host'
else
  fail "host lock did not hold (exit $lock_exit)"
fi

printf 'RECOVERY TEST: failures=%d\n' "$failures"
(( failures == 0 ))

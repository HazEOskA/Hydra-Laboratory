#!/usr/bin/env bash
# Offline behaviour test for the continuous duty cycle. No sandbox, no network:
# the worker runs in simulation mode against a stub command and a scratch state
# directory, so pacing, budget, redaction, journaling, and the circuit breaker
# are proven without spending a single real prompt.
set -Eeuo pipefail

failures=0
pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*" >&2; failures=$((failures + 1)); }

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
worker="$repo_root/scripts/hermes-worker.sh"
reporter="$repo_root/scripts/hermes-report.sh"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

task_dir="$workdir/tasks"
mkdir -p "$task_dir"

write_task() {
  local prefix="$1" id="$2" priority="$3" cadence="$4"
  cat >"$task_dir/$prefix-$id.task.json" <<JSON
{
  "id": "$id",
  "title": "test $id",
  "category": "practice",
  "enabled": true,
  "priority": $priority,
  "cadence_minutes": $cadence,
  "max_runtime_seconds": 30,
  "prompt": ["test prompt for $id", "counters: {{CYCLE_SUMMARY}}"]
}
JSON
}

write_task 010 alpha 10 60
write_task 020 beta 20 60

# The stub stands in for the sandbox call. It echoes credential-shaped text so
# the redaction path is exercised on every capture. The values are invented and
# marked for scripts/secret-scan.sh.
leaky_stub='cat >/dev/null; printf "ok route=inference.local key=nvapi-AAAABBBBCCCCDDDD token: ghp_0123456789abcdefghij\n"'  # secret-scan: synthetic fixture
failing_stub='cat >/dev/null; printf "boom\n" >&2; exit 1'

run_worker() {
  local state_dir="$1"; shift
  HERMES_WORKER_SIMULATE=1 \
  HERMES_WORKER_EXEC_CMD="${STUB:-$leaky_stub}" \
  HERMES_WORKER_TASK_DIR="$task_dir" \
  HERMES_WORKER_STATE_DIR="$state_dir" \
  HERMES_WORKER_MIN_PROMPT_INTERVAL_SECONDS="${INTERVAL:-0}" \
  HERMES_WORKER_IDLE_SLEEP_SECONDS=0 \
  HERMES_WORKER_DAILY_PROMPT_CAP="${CAP:-240}" \
  HERMES_WORKER_FAILURE_THRESHOLD="${THRESHOLD:-5}" \
  "$worker" "$@"
}

journal_lines() {
  cat "$1"/journal/*.jsonl 2>/dev/null | grep -c . || true
}

# 1. Default mode is a dry run that never records anything.
state="$workdir/dry"
if run_worker "$state" >"$workdir/dry.out" 2>&1; then
  if grep -q 'dry run; no prompt is sent' "$workdir/dry.out" \
    && grep -q 'alpha' "$workdir/dry.out" \
    && [[ "$(journal_lines "$state")" == "0" ]]; then
    pass 'default invocation dry-runs and records nothing'
  else
    fail 'dry run output or journal is wrong'
  fi
else
  fail 'dry run exited non-zero'
fi

# 2. A bounded execute run journals one record per due task.
state="$workdir/run"
if run_worker "$state" --execute --cycles 4 >"$workdir/run.out" 2>&1; then
  if [[ "$(journal_lines "$state")" == "2" ]]; then
    pass 'each due task ran exactly once inside the cycle limit'
  else
    fail "expected 2 journal records, found $(journal_lines "$state")"
  fi
else
  fail 'bounded execute run exited non-zero'
fi

# 3. Captured output is redacted before it is written anywhere.
if grep -rqE 'nvapi-AAAA|ghp_0123456789' "$state"; then
  fail 'credential-shaped output reached the state directory'
else
  pass 'credential-shaped output never reached the state directory'
fi
if grep -q 'REDACTED-NVIDIA-KEY' "$state"/journal/*.jsonl; then
  pass 'redaction markers are present in the journal'
else
  fail 'redaction markers missing from the journal'
fi

# 4. Records are valid JSON, carry the simulation stamp, and store a digest.
if python3 - "$state" <<'PY'
import glob, json, os, sys
records = []
for path in glob.glob(os.path.join(sys.argv[1], "journal", "*.jsonl")):
    with open(path, encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
assert records, "no records"
for record in records:
    assert record["simulated"] is True, "missing simulation stamp"
    assert record["status"] == "pass", record["status"]
    assert len(record["output_sha256"]) == 64, "missing digest"
    assert record["sandbox"] == "hydra-hermes-lab"
    assert "nvapi-" not in record["excerpt"]
assert {record["task"] for record in records} == {"alpha", "beta"}
PY
then
  pass 'journal records are well formed and stamped as simulated'
else
  fail 'journal records failed the schema check'
fi

# 5. Budget counters advance and are per day.
if [[ "$(cat "$state"/budget/* 2>/dev/null)" == "2" ]]; then
  pass 'budget counter matches the number of prompts spent'
else
  fail "budget counter is $(cat "$state"/budget/* 2>/dev/null)"
fi

# 6. Per-task state records the run and resets the failure streak.
if python3 - "$state" <<'PY'
import json, os, sys
path = os.path.join(sys.argv[1], "state", "alpha.json")
with open(path, encoding="utf-8") as handle:
    state = json.load(handle)
assert state["runs"] == 1, state
assert state["consecutive_failures"] == 0, state
assert state["last_run"] > 0, state
PY
then
  pass 'per-task state tracks runs and streaks'
else
  fail 'per-task state is wrong'
fi

# 7. A task is not re-run before its cadence elapses.
if run_worker "$state" --execute --cycles 3 >/dev/null 2>&1; then
  if [[ "$(journal_lines "$state")" == "2" ]]; then
    pass 'cadence prevents re-running a task that is not due'
  else
    fail 'a task ran again before its cadence elapsed'
  fi
else
  fail 'second bounded run exited non-zero'
fi

# 8. The daily cap stops spending even when tasks are due.
state="$workdir/cap"
if CAP=1 run_worker "$state" --execute --cycles 4 >/dev/null 2>&1; then
  if [[ "$(journal_lines "$state")" == "1" ]]; then
    pass 'daily prompt cap bounds the spend'
  else
    fail "daily cap allowed $(journal_lines "$state") prompts"
  fi
else
  fail 'capped run exited non-zero'
fi

# 9. The STOP file halts the loop cleanly without spending a prompt.
state="$workdir/stop"
mkdir -p "$state"
touch "$state/STOP"
if run_worker "$state" --execute --cycles 4 >"$workdir/stop.out" 2>&1; then
  if grep -q 'STOP file present' "$workdir/stop.out" && [[ "$(journal_lines "$state")" == "0" ]]; then
    pass 'STOP file halts the loop before any prompt is sent'
  else
    fail 'STOP file did not halt the loop'
  fi
else
  fail 'STOP halt exited non-zero'
fi

# 10. Repeated failures trip the circuit breaker, and --resume clears it.
state="$workdir/breaker"
set +e
STUB="$failing_stub" THRESHOLD=1 run_worker "$state" --execute --cycles 4 >"$workdir/breaker.out" 2>&1
breaker_exit=$?
set -e
if (( breaker_exit == 3 )) && [[ -e "$state/HALTED" ]]; then
  pass 'circuit breaker trips on the failure threshold'
else
  fail "circuit breaker did not trip (exit $breaker_exit)"
fi
set +e
STUB="$failing_stub" THRESHOLD=1 run_worker "$state" --execute --cycles 1 >/dev/null 2>&1
restart_exit=$?
set -e
if (( restart_exit == 3 )); then
  pass 'a tripped breaker refuses to restart the loop'
else
  fail "a tripped breaker restarted the loop (exit $restart_exit)"
fi
if run_worker "$state" --resume >/dev/null 2>&1 && [[ ! -e "$state/HALTED" ]]; then
  pass '--resume clears the circuit breaker'
else
  fail '--resume did not clear the circuit breaker'
fi

# 11. Simulation cannot run without an explicit stub, and the stub hook is
#     rejected outside simulation.
set +e
HERMES_WORKER_SIMULATE=1 HERMES_WORKER_STATE_DIR="$workdir/guard" \
  "$worker" --execute --cycles 1 >/dev/null 2>&1
missing_stub_exit=$?
HERMES_WORKER_EXEC_CMD='true' HERMES_WORKER_STATE_DIR="$workdir/guard" \
  "$worker" --execute --cycles 1 >/dev/null 2>&1
stray_stub_exit=$?
set -e
if (( missing_stub_exit == 2 && stray_stub_exit == 2 )); then
  pass 'simulation hooks are gated in both directions'
else
  fail "simulation hooks are not gated ($missing_stub_exit, $stray_stub_exit)"
fi

# 12. The reporter renders the journal without leaking and flags simulated data.
state="$workdir/run"
if HERMES_WORKER_STATE_DIR="$state" "$reporter" --stdout --hours 24 >"$workdir/report.md" 2>&1; then
  if grep -q 'Hermes Duty-Cycle Report' "$workdir/report.md" \
    && grep -q 'alpha' "$workdir/report.md" \
    && grep -q 'Simulated records in window' "$workdir/report.md" \
    && ! grep -qE 'nvapi-AAAA|ghp_0123456789' "$workdir/report.md"; then
    pass 'report renders sanitized counters and marks simulated data'
  else
    fail 'report content is wrong'
  fi
else
  fail 'report generation exited non-zero'
fi

# 13. The report also lands in the state directory with a stable pointer.
if HERMES_WORKER_STATE_DIR="$state" "$reporter" --hours 24 >/dev/null 2>&1 \
  && [[ -e "$state/reports/latest.md" ]]; then
  pass 'report is written with a latest.md pointer'
else
  fail 'report file or latest.md pointer is missing'
fi

printf 'WORKER LOOP TEST: failures=%d\n' "$failures"
(( failures == 0 ))

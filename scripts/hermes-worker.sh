#!/usr/bin/env bash
# Continuous Hermes duty cycle: select a due task, run one controlled prompt
# through the sandbox boundary, record a sanitized journal entry, repeat.
set -Eeuo pipefail
umask 077

SANDBOX="${NEMOCLAW_SANDBOX_NAME:-hydra-hermes-lab}"
LOCKED_HOST="hydra-hermes-runtime-01"
LOCKED_USER="hydra"

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_DIR="${HERMES_WORKER_TASK_DIR:-$repo_root/tasks}"
STATE_DIR="${HERMES_WORKER_STATE_DIR:-/var/lib/hydra-hermes/worker}"

DAILY_PROMPT_CAP="${HERMES_WORKER_DAILY_PROMPT_CAP:-240}"
MIN_PROMPT_INTERVAL_SECONDS="${HERMES_WORKER_MIN_PROMPT_INTERVAL_SECONDS:-60}"
IDLE_SLEEP_SECONDS="${HERMES_WORKER_IDLE_SLEEP_SECONDS:-30}"
FAILURE_THRESHOLD="${HERMES_WORKER_FAILURE_THRESHOLD:-5}"
MAX_PROMPT_CHARS="${HERMES_WORKER_MAX_PROMPT_CHARS:-1200}"
SIMULATE="${HERMES_WORKER_SIMULATE:-0}"

PROMPT_GUARD='Constraints: answer in at most 12 short lines; do not modify, create, or delete any file; do not call external tools, networks, or web search; if you cannot answer inside the sandbox, reply exactly UNAVAILABLE.'

SOUL_FILE="${HERMES_SOUL_FILE:-$repo_root/SOUL.md}"
SOUL_PREAMBLE_CHARS="${HERMES_SOUL_PREAMBLE_CHARS:-4000}"
soul_sha=""
soul_preamble=""

mode="dry-run"
max_cycles=0

log() { printf '%s worker %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { printf '%s\n' "$*" >&2; exit "${2:-2}"; }

usage() {
  cat <<'USAGE'
Usage: scripts/hermes-worker.sh [--dry-run | --execute | --status | --resume] [--cycles N]

  --dry-run   (default) print the resolved schedule and exit without prompting Hermes
  --execute   run the continuous duty cycle
  --status    print counters for the current state directory and exit
  --resume    clear a tripped circuit breaker and exit
  --cycles N  stop after N scheduling cycles (0 = run until stopped)

Stop a running loop by creating the STOP file in the state directory:
  touch "$HERMES_WORKER_STATE_DIR/STOP"
USAGE
}

while (( $# > 0 )); do
  case "$1" in
    --dry-run) mode="dry-run" ;;
    --execute) mode="execute" ;;
    --status) mode="status" ;;
    --resume) mode="resume" ;;
    --cycles)
      shift
      [[ "${1:-}" =~ ^[0-9]+$ ]] || die 'Usage: --cycles N (non-negative integer)'
      max_cycles="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "Unknown argument: $1" ;;
  esac
  shift
done

# Simulation never reaches the real sandbox: it requires an explicit command
# override and stamps every record it writes, so it cannot forge runtime evidence.
if [[ "$SIMULATE" == "1" ]]; then
  [[ -n "${HERMES_WORKER_EXEC_CMD:-}" ]] || die 'Simulation requires HERMES_WORKER_EXEC_CMD.' 2
  exec_cmd="$HERMES_WORKER_EXEC_CMD"
else
  [[ -z "${HERMES_WORKER_EXEC_CMD:-}" ]] || die 'HERMES_WORKER_EXEC_CMD is only accepted in simulation mode.' 2
  exec_cmd=""
fi

require_locked_host() {
  [[ "$SIMULATE" == "1" ]] && return 0
  [[ "$(id -un)" == "$LOCKED_USER" ]] || die "Run as the dedicated $LOCKED_USER user."
  [[ "$(hostname -s)" == "$LOCKED_HOST" ]] || die "Unexpected host. Refusing outside $LOCKED_HOST."
  command -v nemohermes >/dev/null 2>&1 || die 'nemohermes is unavailable.' 3
}

journal_dir="$STATE_DIR/journal"
task_state_dir="$STATE_DIR/state"
budget_dir="$STATE_DIR/budget"
report_dir="$STATE_DIR/reports"
stop_file="$STATE_DIR/STOP"
halt_file="$STATE_DIR/HALTED"
lock_file="$STATE_DIR/worker.lock"

# Read-only modes still work when the state directory is absent or unwritable,
# so an operator can inspect the plan from a workstation.
if ! mkdir -p "$journal_dir" "$task_state_dir" "$budget_dir" "$report_dir" 2>/dev/null; then
  if [[ "$mode" == "execute" ]]; then
    die "Cannot create the state directory: $STATE_DIR"
  fi
fi

redact() {
  sed -E \
    -e 's/nvapi-[A-Za-z0-9_-]{8,}/[REDACTED-NVIDIA-KEY]/g' \
    -e 's/tskey-(auth|client|api)-[A-Za-z0-9_-]{8,}/[REDACTED-TAILSCALE-KEY]/g' \
    -e 's/gh[pousr]_[A-Za-z0-9_]{16,}/[REDACTED-GITHUB-TOKEN]/g' \
    -e 's/AKIA[0-9A-Z]{16}/[REDACTED-AWS-KEY]/g' \
    -e 's/-----BEGIN [A-Z ]*PRIVATE KEY-----/[REDACTED-PRIVATE-KEY]/g' \
    -e 's/(authorization|bearer|api[_-]?key|apikey|token|secret|password)([[:space:]]*[:=][[:space:]]*|[[:space:]]+)[A-Za-z0-9._\/+-]{8,}/\1\2[REDACTED]/gI'
}

today() { date -u +%Y-%m-%d; }
now_epoch() { date -u +%s; }

# The constitution is only real if it reaches the model. Load it once per run,
# verify its structure, and refuse to prompt without it.
load_soul() {
  local status
  status="$(PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}" \
    HERMES_SOUL_FILE="$SOUL_FILE" python3 -m hermes.cli soul status)" \
    || die "Constitution could not be loaded from $SOUL_FILE" 5
  soul_sha="$(printf '%s' "$status" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha256"])')"
  local structure_ok
  structure_ok="$(printf '%s' "$status" | python3 -c 'import json,sys; print(json.load(sys.stdin)["structure_ok"])')"
  [[ "$structure_ok" == "True" ]] || die "Constitution is missing required sections: $SOUL_FILE" 5
  soul_preamble="$(PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}" \
    HERMES_SOUL_FILE="$SOUL_FILE" python3 -m hermes.cli soul preamble \
    --max-chars "$SOUL_PREAMBLE_CHARS")"
  [[ -n "$soul_preamble" ]] || die "Constitution preamble is empty: $SOUL_FILE" 5
}

budget_used() {
  local file
  file="$budget_dir/$(today)"
  if [[ -s "$file" ]]; then cat "$file"; else printf '0\n'; fi
}

marker() { if [[ -e "$1" ]]; then printf '%s' "$2"; else printf '%s' "$3"; fi; }

budget_consume() {
  local file used
  file="$budget_dir/$(today)"
  used="$(budget_used)"
  printf '%d\n' "$(( used + 1 ))" >"$file"
}

# Sanitized counters for the last 24h, safe to hand back to Hermes as prompt input.
cycle_summary() {
  local since
  since="$(( $(now_epoch) - 86400 ))"
  python3 - "$journal_dir" "$since" <<'PY'
import glob, json, os, sys
journal_dir, since = sys.argv[1], int(sys.argv[2])
total = passed = failed = 0
categories = {}
for path in sorted(glob.glob(os.path.join(journal_dir, "*.jsonl"))):
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if int(record.get("epoch", 0)) < since:
                continue
            total += 1
            if record.get("status") == "pass":
                passed += 1
            else:
                failed += 1
            categories[record.get("category", "unknown")] = categories.get(record.get("category", "unknown"), 0) + 1
parts = ", ".join(f"{name}={count}" for name, count in sorted(categories.items())) or "none"
print(f"last 24h: runs={total} pass={passed} fail={failed}; by category: {parts}")
PY
}

# Emits KEY=VALUE lines for the highest-priority due task, or nothing when idle.
select_task() {
  python3 - "$TASK_DIR" "$task_state_dir" "$(now_epoch)" "$MAX_PROMPT_CHARS" <<'PY'
import base64, glob, json, os, sys

task_dir, state_dir, now, max_chars = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
candidates = []
for path in sorted(glob.glob(os.path.join(task_dir, "*.task.json"))):
    try:
        with open(path, encoding="utf-8") as handle:
            task = json.load(handle)
        task_id = task["id"]
        cadence = int(task["cadence_minutes"])
        int(task["max_runtime_seconds"])
        prompt_lines = list(task["prompt"])
        category = task["category"]
    except (ValueError, KeyError, TypeError, OSError) as error:
        print("ERROR=unreadable task file " + os.path.basename(path) + ": " + str(error))
        sys.exit(0)
    if not task.get("enabled", False):
        continue
    last_run = 0
    state_path = os.path.join(state_dir, task_id + ".json")
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as handle:
            last_run = int(json.load(handle).get("last_run", 0))
    if last_run + cadence * 60 > now:
        continue
    candidates.append((int(task.get("priority", 50)), last_run, task_id, task, prompt_lines, category))

if not candidates:
    sys.exit(0)

candidates.sort(key=lambda item: (item[0], item[1]))
_, _, task_id, task, prompt_lines, category = candidates[0]
prompt = "\n".join(prompt_lines)
if len(prompt) > max_chars:
    print("ERROR=prompt exceeds max length: " + task_id)
    sys.exit(0)
print("TASK_ID=" + task_id)
print("CATEGORY=" + category)
print("MAX_RUNTIME=" + str(int(task["max_runtime_seconds"])))
print("PROMPT_B64=" + base64.b64encode(prompt.encode("utf-8")).decode("ascii"))
PY
}

record_run() {
  local task_id="$1" category="$2" status="$3" exit_code="$4" duration="$5" digest="$6" excerpt="$7"
  local record
  record="$(
    TASK_ID="$task_id" CATEGORY="$category" STATUS="$status" EXIT_CODE="$exit_code" \
    DURATION="$duration" DIGEST="$digest" EXCERPT="$excerpt" SIMULATED="$SIMULATE" \
    SANDBOX="$SANDBOX" SOUL_SHA="$soul_sha" python3 - <<'PY'
import datetime, json, os
now = datetime.datetime.now(datetime.timezone.utc)
print(json.dumps({
    "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "epoch": int(now.timestamp()),
    "sandbox": os.environ["SANDBOX"],
    "task": os.environ["TASK_ID"],
    "category": os.environ["CATEGORY"],
    "status": os.environ["STATUS"],
    "exit": int(os.environ["EXIT_CODE"]),
    "duration_s": int(os.environ["DURATION"]),
    "output_sha256": os.environ["DIGEST"],
    "excerpt": os.environ["EXCERPT"],
    "simulated": os.environ["SIMULATED"] == "1",
    "soul_sha256": os.environ.get("SOUL_SHA", ""),
}, sort_keys=True))
PY
  )"
  printf '%s\n' "$record" >>"$journal_dir/$(today).jsonl"
}

update_task_state() {
  local task_id="$1" status="$2"
  local state_path="$task_state_dir/$task_id.json"
  TASK_STATE_PATH="$state_path" STATUS="$status" EPOCH="$(now_epoch)" python3 - <<'PY'
import json, os
path = os.environ["TASK_STATE_PATH"]
state = {"runs": 0, "failures": 0, "consecutive_failures": 0, "last_run": 0, "last_status": ""}
if os.path.exists(path):
    with open(path, encoding="utf-8") as handle:
        state.update(json.load(handle))
status = os.environ["STATUS"]
state["runs"] += 1
state["last_run"] = int(os.environ["EPOCH"])
state["last_status"] = status
if status == "pass":
    state["consecutive_failures"] = 0
else:
    state["failures"] += 1
    state["consecutive_failures"] += 1
with open(path, "w", encoding="utf-8") as handle:
    json.dump(state, handle, sort_keys=True)
    handle.write("\n")
PY
}

run_task() {
  local task_id="$1" category="$2" max_runtime="$3" prompt="$4"
  local started ended duration exit_code status output digest excerpt

  prompt="${soul_preamble}"$'\n\n---\n\n'"${prompt}"$'\n'"${PROMPT_GUARD}"

  budget_consume
  started="$(now_epoch)"
  set +e
  if [[ "$SIMULATE" == "1" ]]; then
    output="$(printf '%s' "$prompt" | timeout "$max_runtime" bash -c "$exec_cmd" 2>&1)"
  else
    output="$(timeout "$max_runtime" nemohermes "$SANDBOX" exec --no-stdin -- \
      hermes chat -q "$prompt" 2>&1)"
  fi
  exit_code=$?
  set -e
  ended="$(now_epoch)"
  duration=$(( ended - started ))

  case "$exit_code" in
    0) status="pass" ;;
    124|137) status="timeout" ;;
    *) status="fail" ;;
  esac

  digest="$(printf '%s' "$output" | sha256sum | cut -d' ' -f1)"
  excerpt="$(printf '%s' "$output" | redact | tr '\n\t' '  ' | tr -s ' ' | cut -c1-240)"
  if [[ "$status" == "pass" && "$output" == *UNAVAILABLE* ]]; then
    status="fail"
  fi

  record_run "$task_id" "$category" "$status" "$exit_code" "$duration" "$digest" "$excerpt"
  update_task_state "$task_id" "$status"
  log "task=$task_id status=$status exit=$exit_code duration=${duration}s budget=$(budget_used)/$DAILY_PROMPT_CAP"
  [[ "$status" == "pass" ]]
}

consecutive_failures() {
  python3 - "$task_state_dir" <<'PY'
import glob, json, os, sys
worst = 0
for path in glob.glob(os.path.join(sys.argv[1], "*.json")):
    with open(path, encoding="utf-8") as handle:
        worst = max(worst, int(json.load(handle).get("consecutive_failures", 0)))
print(worst)
PY
}

soul_summary() {
  PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}" HERMES_SOUL_FILE="$SOUL_FILE" \
    python3 -m hermes.cli soul status 2>/dev/null \
    | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("NOT LOADED")
    raise SystemExit(0)
state = "structure ok" if data["structure_ok"] else "SECTIONS MISSING"
print(data["version"] + " (" + state + ")")' \
    || printf 'NOT LOADED'
}

print_status() {
  printf 'constitution:     %s\n' "$(soul_summary)"
  printf 'state dir:        %s\n' "$STATE_DIR"
  printf 'task dir:         %s\n' "$TASK_DIR"
  printf 'prompts today:    %s/%s\n' "$(budget_used)" "$DAILY_PROMPT_CAP"
  printf 'stop file:        %s\n' "$(marker "$stop_file" present absent)"
  printf 'circuit breaker:  %s\n' "$(marker "$halt_file" TRIPPED clear)"
  printf 'worst streak:     %s consecutive failures (threshold %s)\n' "$(consecutive_failures)" "$FAILURE_THRESHOLD"
  printf '%s\n' "$(cycle_summary)"
}

print_plan() {
  printf 'Duty-cycle plan (dry run; no prompt is sent)\n'
  print_status
  printf '\nRegistered tasks:\n'
  python3 - "$TASK_DIR" "$task_state_dir" "$(now_epoch)" <<'PY'
import glob, json, os, sys
task_dir, state_dir, now = sys.argv[1], sys.argv[2], int(sys.argv[3])
rows = []
for path in sorted(glob.glob(os.path.join(task_dir, "*.task.json"))):
    with open(path, encoding="utf-8") as handle:
        task = json.load(handle)
    state_path = os.path.join(state_dir, task["id"] + ".json")
    last_run = 0
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as handle:
            last_run = int(json.load(handle).get("last_run", 0))
    due_in = max(0, last_run + int(task["cadence_minutes"]) * 60 - now)
    rows.append((task["id"], task["category"], task["cadence_minutes"], task.get("priority", 50),
                 "enabled" if task.get("enabled") else "disabled",
                 "due now" if due_in == 0 else f"due in {due_in // 60}m"))
width = max((len(row[0]) for row in rows), default=4)
for row in rows:
    print(f"  {row[0]:<{width}}  {row[1]:<11}  every {row[2]:>5}m  prio {row[3]:>3}  {row[4]:<8}  {row[5]}")
if not rows:
    print("  (no tasks registered)")
PY
}

case "$mode" in
  status) print_status; exit 0 ;;
  resume)
    if [[ -e "$halt_file" ]]; then
      rm -f "$halt_file"
      log 'circuit breaker cleared'
    else
      log 'circuit breaker was not tripped'
    fi
    exit 0
    ;;
  dry-run) print_plan; exit 0 ;;
esac

require_locked_host

exec 9>"$lock_file"
flock -n 9 || die 'Another duty cycle already holds the worker lock.' 4

if [[ -e "$halt_file" ]]; then
  die "Circuit breaker tripped: $(cat "$halt_file"). Clear with --resume." 3
fi

trap 'log "stopping on signal"; exit 0' INT TERM

load_soul
log "constitution loaded sha256=${soul_sha:0:16} chars=${#soul_preamble}"
log "duty cycle starting sandbox=$SANDBOX tasks=$TASK_DIR state=$STATE_DIR cap=$DAILY_PROMPT_CAP/day"

cycles=0
last_prompt_epoch=0
global_failures=0
while :; do
  if [[ -e "$stop_file" ]]; then
    log 'STOP file present; halting cleanly'
    exit 0
  fi

  cycles=$(( cycles + 1 ))
  if (( max_cycles > 0 && cycles > max_cycles )); then
    log "cycle limit reached ($max_cycles); halting cleanly"
    exit 0
  fi

  if (( $(budget_used) >= DAILY_PROMPT_CAP )); then
    log "daily prompt cap reached ($DAILY_PROMPT_CAP); idling"
    sleep "$IDLE_SLEEP_SECONDS"
    continue
  fi

  since_last=$(( $(now_epoch) - last_prompt_epoch ))
  if (( last_prompt_epoch > 0 && since_last < MIN_PROMPT_INTERVAL_SECONDS )); then
    sleep $(( MIN_PROMPT_INTERVAL_SECONDS - since_last ))
    continue
  fi

  selection="$(select_task)"
  if [[ -z "$selection" ]]; then
    sleep "$IDLE_SLEEP_SECONDS"
    continue
  fi
  if [[ "$selection" == ERROR=* ]]; then
    log "scheduler rejected a task: ${selection#ERROR=}"
    sleep "$IDLE_SLEEP_SECONDS"
    continue
  fi

  TASK_ID=""; CATEGORY=""; MAX_RUNTIME=""; PROMPT_B64=""
  while read -r line; do
    case "${line%%=*}" in
      TASK_ID) TASK_ID="${line#*=}" ;;
      CATEGORY) CATEGORY="${line#*=}" ;;
      MAX_RUNTIME) MAX_RUNTIME="${line#*=}" ;;
      PROMPT_B64) PROMPT_B64="${line#*=}" ;;
      *) : ;;
    esac
  done <<<"$selection"
  if [[ -z "$TASK_ID" || -z "$PROMPT_B64" || ! "$MAX_RUNTIME" =~ ^[0-9]+$ ]]; then
    log 'scheduler returned an incomplete selection; idling'
    sleep "$IDLE_SLEEP_SECONDS"
    continue
  fi

  prompt_text="$(printf '%s' "$PROMPT_B64" | base64 -d)"
  prompt_text="${prompt_text//\{\{CYCLE_SUMMARY\}\}/$(cycle_summary)}"

  last_prompt_epoch="$(now_epoch)"
  if run_task "$TASK_ID" "$CATEGORY" "$MAX_RUNTIME" "$prompt_text"; then
    global_failures=0
  else
    global_failures=$(( global_failures + 1 ))
  fi

  # Trip on a run of failures across tasks (route or host trouble) or on one
  # task failing repeatedly (a broken task definition).
  streak="$(consecutive_failures)"
  if (( streak >= FAILURE_THRESHOLD || global_failures >= FAILURE_THRESHOLD )); then
    printf 'task streak=%s cycle streak=%s threshold=%s at %s\n' \
      "$streak" "$global_failures" "$FAILURE_THRESHOLD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$halt_file"
    log "circuit breaker tripped (task streak=$streak, cycle streak=$global_failures); halting"
    exit 3
  fi
done

#!/usr/bin/env bash
# Static contract for the continuous duty cycle: task manifests, worker gates,
# systemd units, and non-secret configuration.
# shellcheck disable=SC2015
set -Eeuo pipefail

failures=0
pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*" >&2; failures=$((failures + 1)); }
require_text() { grep -Fq -- "$2" "$1" && pass "$1 contains $2" || fail "$1 missing $2"; }

worker="scripts/hermes-worker.sh"
reporter="scripts/hermes-report.sh"
service="infra/systemd/hydra-hermes-worker.service"
report_service="infra/systemd/hydra-hermes-report.service"
report_timer="infra/systemd/hydra-hermes-report.timer"
env_example="config/worker.env.example"

for file in "$worker" "$reporter" "$service" "$report_service" "$report_timer" "$env_example" tasks/README.md; do
  [[ -s "$file" ]] && pass "$file exists" || fail "$file is missing or empty"
done

mapfile -t task_files < <(find tasks -maxdepth 1 -name '*.task.json' -print | sort)
(( ${#task_files[@]} > 0 )) && pass "task manifests present: ${#task_files[@]}" || fail "no task manifests found"

if (( ${#task_files[@]} > 0 )); then
  if python3 - "${task_files[@]}" <<'PY'
import json, os, re, sys

ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,39}$")
CATEGORIES = {"maintenance", "practice", "report"}
PLACEHOLDERS = {"{{CYCLE_SUMMARY}}"}
FORBIDDEN = ("http://", "https://", "rm -rf", "curl ", "wget ", "sudo ", "chmod ", "ssh ",
             "nvapi-", "tskey-", "BEGIN RSA", "PRIVATE KEY", "api_key", "password")
MAX_PROMPT_CHARS = 1200

problems = []
seen = {}
for path in sys.argv[1:]:
    name = os.path.basename(path)
    try:
        with open(path, encoding="utf-8") as handle:
            task = json.load(handle)
    except ValueError as error:
        problems.append(f"{name}: invalid JSON: {error}")
        continue

    required = {"id", "title", "category", "enabled", "priority",
                "cadence_minutes", "max_runtime_seconds", "prompt"}
    missing = required - set(task)
    if missing:
        problems.append(f"{name}: missing fields: {', '.join(sorted(missing))}")
        continue
    extra = set(task) - required
    if extra:
        problems.append(f"{name}: unknown fields: {', '.join(sorted(extra))}")

    task_id = task["id"]
    if not isinstance(task_id, str) or not ID_PATTERN.match(task_id):
        problems.append(f"{name}: id must match ^[a-z][a-z0-9-]{{2,39}}$")
    if task_id in seen:
        problems.append(f"{name}: duplicate id also used by {seen[task_id]}")
    seen[task_id] = name
    stem = name[: -len(".task.json")]
    if not re.match(r"^\d{3}-", stem):
        problems.append(f"{name}: filename needs a three-digit sort prefix")
    elif stem[4:] != task_id:
        problems.append(f"{name}: filename stem '{stem[4:]}' does not match id '{task_id}'")

    if task["category"] not in CATEGORIES:
        problems.append(f"{name}: category must be one of {sorted(CATEGORIES)}")
    if not isinstance(task["enabled"], bool):
        problems.append(f"{name}: enabled must be a boolean")
    if not isinstance(task["title"], str) or not task["title"].strip():
        problems.append(f"{name}: title must be a non-empty string")
    if not isinstance(task["priority"], int) or not 1 <= task["priority"] <= 100:
        problems.append(f"{name}: priority must be an integer in 1..100")
    if not isinstance(task["cadence_minutes"], int) or not 5 <= task["cadence_minutes"] <= 10080:
        problems.append(f"{name}: cadence_minutes must be an integer in 5..10080")
    if not isinstance(task["max_runtime_seconds"], int) or not 10 <= task["max_runtime_seconds"] <= 900:
        problems.append(f"{name}: max_runtime_seconds must be an integer in 10..900")

    prompt = task["prompt"]
    if not isinstance(prompt, list) or not prompt or not all(isinstance(line, str) for line in prompt):
        problems.append(f"{name}: prompt must be a non-empty array of strings")
        continue
    joined = "\n".join(prompt)
    if len(joined) > MAX_PROMPT_CHARS:
        problems.append(f"{name}: prompt is {len(joined)} chars, limit {MAX_PROMPT_CHARS}")
    lowered = joined.lower()
    for needle in FORBIDDEN:
        if needle.lower() in lowered:
            problems.append(f"{name}: prompt contains forbidden text {needle!r}")
    for found in re.findall(r"\{\{[A-Z_]+\}\}", joined):
        if found not in PLACEHOLDERS:
            problems.append(f"{name}: unknown placeholder {found}")

for problem in problems:
    print(problem)
sys.exit(1 if problems else 0)
PY
  then
    pass "task manifests satisfy the queue contract"
  else
    fail "task manifests violate the queue contract"
  fi
fi

require_text "$worker" '--execute'
require_text "$worker" 'hydra-hermes-runtime-01'
require_text "$worker" 'HERMES_WORKER_DAILY_PROMPT_CAP'
require_text "$worker" 'HERMES_WORKER_FAILURE_THRESHOLD'
require_text "$worker" 'flock -n 9'
require_text "$worker" 'REDACTED-NVIDIA-KEY'
require_text "$worker" 'do not modify, create, or delete any file'

if grep -Eq 'NVIDIA_INFERENCE_API_KEY' "$worker" "$reporter"; then
  fail "duty-cycle scripts must never reference the raw provider key"
else
  pass "duty-cycle scripts never reference the raw provider key"
fi

if grep -Eq '^[[:space:]]*set[[:space:]]+-x|set[[:space:]]+-[a-zA-Z]*x' "$worker" "$reporter"; then
  fail "shell tracing must stay disabled in duty-cycle scripts"
else
  pass "no shell tracing in duty-cycle scripts"
fi

# The default dry run must not be able to reach the sandbox.
if grep -q 'dry-run) print_plan; exit 0 ;;' "$worker"; then
  pass "dry run is the default and exits before the execution gate"
else
  fail "dry-run gate is missing or reordered"
fi

for unit in "$service" "$report_service"; do
  require_text "$unit" 'User=hydra'
  require_text "$unit" 'NoNewPrivileges=true'
  require_text "$unit" 'PrivateTmp=true'
  require_text "$unit" 'ProtectSystem=strict'
  require_text "$unit" 'ProtectHome=read-only'
  require_text "$unit" 'ReadWritePaths=/var/lib/hydra-hermes'
done

require_text "$service" 'Restart=always'
require_text "$service" '--execute'
require_text "$report_timer" 'OnCalendar='
require_text "$report_timer" 'Persistent=true'

if grep -q 'HERMES_WORKER_SIMULATE' "$service" "$report_service" "$report_timer" "$env_example"; then
  fail "simulation must never be enabled by units or example configuration"
else
  pass "units and example configuration never enable simulation"
fi

for key in HERMES_WORKER_STATE_DIR HERMES_WORKER_DAILY_PROMPT_CAP \
  HERMES_WORKER_MIN_PROMPT_INTERVAL_SECONDS HERMES_WORKER_IDLE_SLEEP_SECONDS \
  HERMES_WORKER_FAILURE_THRESHOLD; do
  require_text "$env_example" "$key="
done

if grep -Eq '^[A-Z_]*(KEY|TOKEN|SECRET|PASSWORD)=[^[:space:]#]' "$env_example"; then
  fail "$env_example assigns credential-shaped values"
else
  pass "$env_example assigns no credential-shaped values"
fi

printf 'WORKER VALIDATION: failures=%d\n' "$failures"
(( failures == 0 ))

#!/usr/bin/env bash
# Static contract for the God-Layer control plane.
#
# Checks the things that must be true before the runtime is trusted: the
# constitution is complete, the permission model is not accidentally paralysing
# or accidentally permissive, the schedule matches the installed timers, and no
# automation can send or spend.
# shellcheck disable=SC2015
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export PYTHONPATH="$repo_root/lib${PYTHONPATH:+:$PYTHONPATH}"

failures=0
pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*" >&2; failures=$((failures + 1)); }

# -- files ----------------------------------------------------------------
for file in SOUL.md config/tools.yaml config/models.yaml config/schedule.yaml \
  lib/hermes/permissions.py lib/hermes/ledger.py lib/hermes/queue.py \
  lib/hermes/router.py lib/hermes/revenue.py lib/hermes/soul.py lib/hermes/cli.py \
  scripts/hermesctl scripts/host-baseline.sh scripts/host-backup.sh \
  scripts/health-watch.sh scripts/evidence-bundle.sh lib/hermes/probe.py \
  docs/GOD_LAYER.md docs/RUNTIME_FINDINGS.md; do
  [[ -s "$file" ]] && pass "$file exists" || fail "$file is missing or empty"
done

# -- constitution ---------------------------------------------------------
if python3 -m hermes.cli soul status >/tmp/soul-status.$$ 2>/dev/null; then
  if python3 -c '
import json, sys
data = json.load(open(sys.argv[1]))
assert data["loaded"], "constitution is empty"
assert data["structure_ok"], "missing sections: " + ", ".join(data["missing_sections"])
assert len(data["sha256"]) == 64
' /tmp/soul-status.$$; then
    pass "constitution loads and contains every required section"
  else
    fail "constitution structure check failed"
  fi
else
  fail "constitution could not be loaded"
fi
rm -f /tmp/soul-status.$$

# The worker must actually inject it, not merely ship it.
grep -q 'load_soul' scripts/hermes-worker.sh \
  && grep -q 'soul_preamble' scripts/hermes-worker.sh \
  && pass "duty cycle loads the constitution into every prompt" \
  || fail "duty cycle does not load the constitution"

# -- permission model -----------------------------------------------------
if python3 - <<'PY'
import sys
sys.path.insert(0, "lib")
from hermes.permissions import PermissionClassifier, PermissionLevel

classifier = PermissionClassifier()
problems = []

# Anti-paralysis: routine operational work must not need approval.
must_be_green = [
    ("shell", "inspect"), ("shell", "test"), ("docker", "ps"), ("docker", "logs"),
    ("git", "commit"), ("git", "diff"), ("database", "read"), ("filesystem", "write"),
    ("browser", "smoke_test"), ("research", "search"), ("email", "draft"),
    ("crypto", "analysis"), ("scheduler", "inspect"),
]
for tool, action in must_be_green:
    level = classifier.classify(tool, action).permission
    if level is not PermissionLevel.GREEN:
        problems.append(f"{tool}.{action} should be GREEN, got {level}")

# Anti-overreach: irreversible or outward-facing work must stop for OSA.
must_be_red = [
    ("email", "send"), ("deployment", "production"), ("crypto", "transaction"),
    ("github", "delete_repo"), ("database", "drop_production"),
    ("docker", "delete_volume"), ("shell", "expose_public_port"),
]
for tool, action in must_be_red:
    decision = classifier.classify(tool, action)
    if decision.permission is not PermissionLevel.RED or not decision.requires_approval:
        problems.append(f"{tool}.{action} must be RED and require approval, got {decision.permission}")

# A GREEN tool must not be a smuggling route for a RED action.
smuggle = classifier.classify("shell", "run", {"cmd": "delete production database"})
if smuggle.permission is not PermissionLevel.RED:
    problems.append("RED patterns do not escalate a GREEN tool")

if not classifier.tools.get("payments", {}).get("enabled", True) is False:
    problems.append("payments tool must remain disabled in this baseline")

for name in classifier.enabled_tools():
    if not classifier.tool_spec(name).get("health_check"):
        problems.append(f"enabled tool {name} declares no health check")

for problem in problems:
    print(problem)
sys.exit(1 if problems else 0)
PY
then
  pass "permission model is neither paralysing nor over-permissive"
else
  fail "permission model violates the GREEN/YELLOW/RED contract"
fi

# -- schedule vs installed timers ----------------------------------------
if python3 - <<'PY'
import pathlib, re, sys
import yaml

schedule = yaml.safe_load(open("config/schedule.yaml"))
problems = []
CRON_TO_CALENDAR = {
    "*/5 * * * *": "*:0/5",
    "*/30 * * * *": "*:0/30",
    "0 8 * * *": "*-*-* 08:00:00 UTC",
    "0 19 * * *": "*-*-* 19:00:00 UTC",
    "0 18 * * 0": "Sun *-*-* 18:00:00 UTC",
    "0 5 * * *": "*-*-* 05:00:00 UTC",
}
for name, job in schedule["jobs"].items():
    script = pathlib.Path(job["script"])
    if not script.is_file():
        problems.append(f"{name}: script {script} does not exist")
    unit = pathlib.Path("infra/systemd") / f"{job['unit']}.service"
    timer = pathlib.Path("infra/systemd") / f"{job['unit']}.timer"
    if not unit.is_file():
        problems.append(f"{name}: missing unit {unit}")
        continue
    if not timer.is_file():
        problems.append(f"{name}: missing timer {timer}")
        continue
    unit_text = unit.read_text()
    if script.name not in unit_text:
        problems.append(f"{name}: unit does not run {script.name}")
    for directive in ("User=hydra", "NoNewPrivileges=true", "ProtectSystem=strict"):
        if directive not in unit_text:
            problems.append(f"{name}: unit missing {directive}")
    expected = CRON_TO_CALENDAR.get(job["cron"])
    calendar = re.search(r"OnCalendar=(.+)", timer.read_text())
    if expected and (not calendar or calendar.group(1).strip() != expected):
        got = calendar.group(1).strip() if calendar else "none"
        problems.append(f"{name}: cron {job['cron']} expects OnCalendar={expected}, got {got}")
    if job["permission"] == "RED":
        problems.append(f"{name}: no scheduled job may be RED")

for problem in problems:
    print(problem)
sys.exit(1 if problems else 0)
PY
then
  pass "schedule, scripts and systemd timers agree"
else
  fail "schedule does not match the installed units and timers"
fi

# -- automations cannot send or spend -------------------------------------
if grep -nE '\b(curl|wget)\b[^|]*https?://(?!127\.0\.0\.1|localhost)' \
  scripts/revenue-ops.sh scripts/ops-brief.sh scripts/repo-watch.sh 2>/dev/null | grep -q .; then
  fail "an automation makes an outbound request"
else
  pass "no automation makes an outbound request"
fi

# The validator states the patterns it forbids, so it excludes itself the same
# way scripts/secret-scan.sh does.
mail_users="$(grep -lE 'sendmail|smtplib|msmtp|mail -s' scripts/*.sh 2>/dev/null \
  | grep -v '^scripts/validate-godlayer\.sh$' || true)"
if [[ -n "$mail_users" ]]; then
  fail "an automation can send mail directly: $mail_users"
else
  pass "no automation can send mail directly"
fi

grep -q 'sent=0' scripts/revenue-ops.sh \
  && pass "revenue automation reports its send count explicitly" \
  || fail "revenue automation does not report a send count"

# -- ledger and queue invariants -----------------------------------------
grep -q "RAISE(ABORT, 'evidence ledger is append-only')" lib/hermes/ledger.py \
  && pass "evidence ledger is append-only at the storage layer" \
  || fail "evidence ledger append-only trigger is missing"

grep -q 'COMPLETED is reachable only from VALIDATING' lib/hermes/ledger.py \
  && pass "no mission can skip validation on the way to COMPLETED" \
  || fail "validation gate is missing from the state machine"

grep -q "RAISE(ABORT, 'outreach requires a scoped OSA approval reference')" lib/hermes/revenue.py \
  && pass "outreach cannot be recorded without a scoped approval" \
  || fail "outreach approval trigger is missing"

grep -q 'MAX_ACTIVE_TASKS' lib/hermes/queue.py \
  && pass "queue concurrency is bounded" \
  || fail "queue concurrency limit is missing"

# A health table that nobody populates blocks every route forever.
grep -q 'models probe' scripts/health-watch.sh \
  && pass "health watch refreshes provider health before judging the route" \
  || fail "nothing populates the model health table"

# -- no secrets in the control plane -------------------------------------
if grep -rnE 'nvapi-[A-Za-z0-9_-]{8,}|tskey-(auth|client|api)-' lib/ config/ SOUL.md 2>/dev/null; then
  fail "credential-shaped material in the control plane"
else
  pass "no credential-shaped material in the control plane"
fi

printf 'GOD LAYER VALIDATION: failures=%d\n' "$failures"
(( failures == 0 ))

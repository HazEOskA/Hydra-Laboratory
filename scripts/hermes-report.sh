#!/usr/bin/env bash
# Aggregate the duty-cycle journal into a sanitized Markdown report.
set -Eeuo pipefail
umask 077

STATE_DIR="${HERMES_WORKER_STATE_DIR:-/var/lib/hydra-hermes/worker}"
DAILY_PROMPT_CAP="${HERMES_WORKER_DAILY_PROMPT_CAP:-240}"

window_hours=24
to_stdout=0

usage() {
  cat <<'USAGE'
Usage: scripts/hermes-report.sh [--hours N] [--stdout]

  --hours N  reporting window in hours (default 24, max 720)
  --stdout   print the report without writing it to the state directory
USAGE
}

while (( $# > 0 )); do
  case "$1" in
    --hours)
      shift
      if [[ ! "${1:-}" =~ ^[0-9]+$ ]] || (( $1 < 1 || $1 > 720 )); then
        usage >&2
        exit 2
      fi
      window_hours="$1"
      ;;
    --stdout) to_stdout=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

journal_dir="$STATE_DIR/journal"
report_dir="$STATE_DIR/reports"
[[ -d "$journal_dir" ]] || { printf 'No journal at %s; nothing to report.\n' "$journal_dir" >&2; exit 1; }
mkdir -p "$report_dir"

report="$(
  python3 - "$journal_dir" "$window_hours" "$DAILY_PROMPT_CAP" <<'PY'
import datetime, glob, json, os, sys

journal_dir, window_hours, cap = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
now = datetime.datetime.now(datetime.timezone.utc)
since = int(now.timestamp()) - window_hours * 3600

records = []
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
            if int(record.get("epoch", 0)) >= since:
                records.append(record)

records.sort(key=lambda item: item.get("epoch", 0))
total = len(records)
by_status = {}
by_task = {}
for record in records:
    status = record.get("status", "unknown")
    by_status[status] = by_status.get(status, 0) + 1
    task = record.get("task", "unknown")
    entry = by_task.setdefault(task, {"category": record.get("category", "unknown"), "runs": 0,
                                      "pass": 0, "other": 0, "seconds": 0, "last": ""})
    entry["runs"] += 1
    entry["pass" if status == "pass" else "other"] += 1
    entry["seconds"] += int(record.get("duration_s", 0))
    entry["last"] = record.get("ts", "")

simulated = sum(1 for record in records if record.get("simulated"))
passed = by_status.get("pass", 0)
rate = f"{(passed / total * 100):.1f}%" if total else "n/a"

out = []
out.append("# Hermes Duty-Cycle Report")
out.append("")
out.append(f"- Generated: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}")
out.append(f"- Window: last {window_hours}h")
out.append(f"- Runs: {total} (pass {passed}, other {total - passed}, success rate {rate})")
out.append(f"- Daily prompt cap: {cap}")
if simulated:
    out.append(f"- **Simulated records in window: {simulated} — not runtime evidence**")
out.append("")
out.append("## Per Task")
out.append("")
out.append("| Task | Category | Runs | Pass | Other | Avg s | Last run |")
out.append("| --- | --- | ---: | ---: | ---: | ---: | --- |")
for task in sorted(by_task):
    entry = by_task[task]
    avg = entry["seconds"] // entry["runs"] if entry["runs"] else 0
    out.append(f"| {task} | {entry['category']} | {entry['runs']} | {entry['pass']} | "
               f"{entry['other']} | {avg} | {entry['last']} |")
if not by_task:
    out.append("| (none) | | 0 | 0 | 0 | 0 | |")
out.append("")

failures = [record for record in records if record.get("status") != "pass"]
out.append("## Failures")
out.append("")
if not failures:
    out.append("None in window.")
else:
    out.append("| Time | Task | Status | Exit | Redacted excerpt |")
    out.append("| --- | --- | --- | ---: | --- |")
    for record in failures[-20:]:
        excerpt = str(record.get("excerpt", "")).replace("|", "\\|")[:160]
        out.append(f"| {record.get('ts', '')} | {record.get('task', '')} | {record.get('status', '')} | "
                   f"{record.get('exit', '')} | {excerpt} |")
out.append("")
out.append("Excerpts are redacted and truncated at capture time. Full model output is never stored.")
print("\n".join(out))
PY
)"

if (( to_stdout == 1 )); then
  printf '%s\n' "$report"
  exit 0
fi

target="$report_dir/report-$(date -u +%Y-%m-%dT%H%M%SZ).md"
printf '%s\n' "$report" >"$target"
ln -sfn "$target" "$report_dir/latest.md"
printf 'Report written: %s\n' "$target"

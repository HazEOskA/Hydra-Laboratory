# Task Queue

Each `*.task.json` file is one recurring unit of work for the continuous duty
cycle in `scripts/hermes-worker.sh`. Files are plain data: the worker reads the
directory on every scheduling cycle, so tasks can be added, edited, or disabled
while the loop is running.

## Format

```json
{
  "id": "runtime-heartbeat",
  "title": "Runtime heartbeat",
  "category": "maintenance",
  "enabled": true,
  "priority": 10,
  "cadence_minutes": 30,
  "max_runtime_seconds": 120,
  "prompt": ["first line", "second line"]
}
```

| Field | Contract |
| --- | --- |
| `id` | `^[a-z][a-z0-9-]{2,39}$`, unique, must match the filename after the numeric sort prefix |
| `title` | short human label |
| `category` | `maintenance`, `practice`, or `report` |
| `enabled` | `false` parks a task without deleting it |
| `priority` | 1–100; lower runs first when several tasks are due |
| `cadence_minutes` | 5–10080; minimum spacing between two runs of this task |
| `max_runtime_seconds` | 10–900; hard `timeout` on the prompt |
| `prompt` | non-empty array of lines, 1200 characters total after joining |

`scripts/validate-worker.sh` enforces every constraint above; `make worker-check`
runs it, and CI runs it on each push.

## Prompt Rules

Prompts are read-only by contract. The worker appends a fixed guard clause to
every prompt that forbids file changes and external tool calls and caps the
answer length, so task text only needs to describe the work.

Validation rejects prompts that contain external URLs, shell mutation verbs, or
credential-looking material. Keep prompts inside the sandbox boundary described
in [SECURITY_MODEL.md](../docs/SECURITY_MODEL.md).

## Placeholders

`{{CYCLE_SUMMARY}}` expands to sanitized 24-hour counters computed locally from
the journal — run totals, pass/fail counts, and per-category counts. It is the
only placeholder the worker substitutes, and it never carries raw output.

## Scheduling

On each cycle the worker takes the due task with the lowest `priority`, breaking
ties by oldest `last_run`. A task that is not due is skipped without cost. When
nothing is due, the worker idles rather than inventing work.

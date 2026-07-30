# Continuous Operation

The validated baseline proves Hermes answers one controlled prompt. This
document defines the layer that keeps it working continuously: a supervised duty
cycle that selects a due task, sends one controlled prompt through the sandbox
boundary, records a sanitized result, and repeats — 24/7, under explicit spend
and failure limits.

## Components

| Path | Role |
| --- | --- |
| `tasks/*.task.json` | the recurring work queue, one file per task |
| `scripts/hermes-worker.sh` | the loop: schedule, prompt, redact, journal, pace |
| `scripts/hermes-report.sh` | sanitized Markdown reports from the journal |
| `scripts/validate-worker.sh` | static contract for tasks, gates, and units |
| `tests/test-worker-loop.sh` | offline proof of loop behaviour, no sandbox needed |
| `infra/systemd/*` | supervision: always-restart worker, daily report timer |
| `config/worker.env.example` | non-secret pacing and budget configuration |

## Duty Cycle

Each cycle:

1. Halt if the `STOP` file exists in the state directory.
2. Idle if the daily prompt cap is spent.
3. Idle until the minimum interval since the last prompt has elapsed.
4. Select the due task with the lowest `priority`, ties broken by oldest run.
5. Substitute `{{CYCLE_SUMMARY}}`, append the fixed read-only guard clause, and
   run `nemohermes hydra-hermes-lab exec --no-stdin -- hermes chat -q "<prompt>"`
   under a per-task `timeout`.
6. Redact the captured output, then append one JSON line to the journal and
   update per-task state.
7. Trip the circuit breaker if failures have piled up; otherwise continue.

Nothing is invented when the queue is idle: the worker sleeps rather than
generating filler prompts.

## Spend Control

A fixed-price subscription is not unmetered capacity, so pacing is part of the
contract rather than an afterthought:

- `HERMES_WORKER_DAILY_PROMPT_CAP` (default 240) is a hard per-UTC-day ceiling.
  The counter is incremented **before** the prompt is sent, so a crash mid-prompt
  costs budget rather than silently un-counting it.
- `HERMES_WORKER_MIN_PROMPT_INTERVAL_SECONDS` (default 60) is a floor between
  any two prompts, independent of how many tasks are due.
- Each task's `cadence_minutes` bounds how often that specific task can recur.
- `max_runtime_seconds` bounds a single prompt; a hung call is a `timeout`
  record, not a stalled loop.

At the defaults, the ceiling is 240 prompts/day — roughly one every six minutes.
Lower the cap first if the subscription's request budget is tighter than that.

## Failure Handling

Per-task state tracks `consecutive_failures`; the loop also tracks a run of
failures across tasks. Either reaching `HERMES_WORKER_FAILURE_THRESHOLD`
(default 5) writes `HALTED` into the state directory and exits 3.

A tripped breaker is sticky: the worker refuses to start while `HALTED` exists,
so systemd's restart loop cannot hammer a broken route. Clear it deliberately:

```bash
scripts/hermes-worker.sh --resume
```

Timeouts and non-zero exits are failures. A reply containing `UNAVAILABLE` — the
guard clause's escape hatch — is also recorded as a failure, because a sandbox
that cannot answer is a runtime problem, not a successful run.

## State Layout

Runtime state lives outside Git, under `HERMES_WORKER_STATE_DIR`
(default `/var/lib/hydra-hermes/worker`):

```text
journal/YYYY-MM-DD.jsonl   one redacted record per run
state/<task-id>.json       runs, failures, consecutive_failures, last_run
budget/YYYY-MM-DD          prompts spent that UTC day
reports/report-*.md        generated reports, latest.md points at the newest
STOP                       operator kill switch, halts the loop cleanly
HALTED                     circuit-breaker marker, written by the worker
worker.lock                flock target; a second loop cannot start
```

A journal record stores the timestamp, task, category, status, exit code,
duration, a SHA-256 digest of the raw output, and a redacted 240-character
excerpt. Full model output is never written to disk, which keeps
[SECURITY_MODEL.md](SECURITY_MODEL.md) evidence rules intact by construction.

## Reporting

`scripts/hermes-report.sh --hours 24` writes a Markdown report into
`reports/` and refreshes `reports/latest.md`. `--stdout` prints without writing.
The report covers run totals, success rate, per-task counts and average
duration, and the most recent failures with their redacted excerpts.

Reports are host artifacts. Copy a report into
[RUNTIME_EVIDENCE.md](RUNTIME_EVIDENCE.md) only after reading it, and only in
the sanitized form the evidence rules already require.

Hermes also reports on itself: the `self-report` task receives the locally
computed 24-hour counters through `{{CYCLE_SUMMARY}}` and is asked to summarize
its own run rate and reliability.

## Installation

The duty cycle runs on the locked runtime host, not in CI and not in the cloud
workspace. As `hydra` on `hydra-hermes-runtime-01`, after the baseline gates in
[VALIDATION_PLAN.md](VALIDATION_PLAN.md) are green:

```bash
scripts/hermes-worker.sh --dry-run          # show the schedule, send nothing
sudo install -d -m 0750 -o hydra -g hydra /var/lib/hydra-hermes/worker
sudo install -d -m 0755 /etc/hydra-hermes
sudo install -m 0640 -o root -g hydra config/worker.env.example /etc/hydra-hermes/worker.env
sudoedit /etc/hydra-hermes/worker.env      # review paths and budget before enabling
sudo install -m 0644 infra/systemd/hydra-hermes-*.service infra/systemd/hydra-hermes-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hydra-hermes-worker.service hydra-hermes-report.timer
```

Verify before walking away:

```bash
systemctl status hydra-hermes-worker.service
scripts/hermes-worker.sh --status
scripts/hermes-report.sh --stdout --hours 1
```

## Operator Controls

| Action | Command |
| --- | --- |
| Pause without uninstalling | `touch /var/lib/hydra-hermes/worker/STOP` |
| Resume after a pause | `rm /var/lib/hydra-hermes/worker/STOP && sudo systemctl restart hydra-hermes-worker` |
| Stop supervision entirely | `sudo systemctl disable --now hydra-hermes-worker.service` |
| Clear a tripped breaker | `scripts/hermes-worker.sh --resume` |
| Inspect counters | `scripts/hermes-worker.sh --status` |
| Park one task | set `"enabled": false` in its manifest; the loop picks it up next cycle |

## Boundaries

- The worker never handles `NVIDIA_INFERENCE_API_KEY`. It prompts through
  `nemohermes … exec`; the credential stays host-side with the Model Router,
  exactly as in the baseline.
- Every prompt carries a fixed guard clause forbidding file changes and external
  tool calls, and `scripts/validate-worker.sh` rejects task text containing
  external URLs, mutation verbs, or credential-shaped material. This keeps the
  duty cycle inside the read-only posture of the controlled first prompt and does
  not reopen the integrations deferred by D-005.
- Simulation mode (`HERMES_WORKER_SIMULATE=1`) exists only for
  `tests/test-worker-loop.sh`. It requires an explicit stub command, never calls
  the sandbox, and stamps `"simulated": true` on every record it writes, so
  simulated runs cannot be mistaken for runtime evidence. The systemd units never
  set it, and `scripts/validate-worker.sh` enforces that.
- CI validates the contract statically. It does not run the duty cycle against a
  sandbox, and no green CI run implies a working runtime.

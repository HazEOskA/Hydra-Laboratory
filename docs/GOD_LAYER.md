# OSA God Layer — Hermes Control Plane

The duty cycle in [CONTINUOUS_OPERATION.md](CONTINUOUS_OPERATION.md) keeps Hermes
running. This document describes the layer above it: the constitution, the
permission model, the mission state machine, the durable queue, model routing,
the automations and the revenue pipeline.

Everything here is a modular library plus operator scripts — not a microservice
fleet. One store per concern, one CLI, one scheduler.

## Scope Boundary

This repository is the control plane. It is checked out on the runtime host and
executed there; GitHub remains the source of truth. Repair of the live runtime
happens by running these scripts **on** `hydra-hermes-runtime-01`, never from CI
and never from a cloud workspace, which has no route to the host by design.

## Components

| Path | Role |
| --- | --- |
| `SOUL.md` | the operational constitution, injected into every prompt |
| `lib/hermes/soul.py` | loads, hashes and verifies the constitution |
| `lib/hermes/permissions.py` | GREEN/YELLOW/RED classifier and dispatch plan |
| `lib/hermes/ledger.py` | mission state machine + append-only hash-chained events |
| `lib/hermes/queue.py` | durable SQLite task queue with recovery and dead letters |
| `lib/hermes/router.py` | capability-aware model routing with fallback |
| `lib/hermes/revenue.py` | leads, audits, drafts, follow-ups, revenue ledger |
| `lib/hermes/redact.py` | shared secret redaction |
| `scripts/hermesctl` | the operator CLI over all of the above |
| `config/tools.yaml` | tool registry and permission defaults |
| `config/models.yaml` | model catalogue and routing chains |
| `config/schedule.yaml` | the automation schedule |

## Permission Model

Three levels, from SOUL.md:

- **GREEN** — dispatch immediately. Inspection, tests, builds, drafts, local
  commits, backups, health checks, preview validation.
- **YELLOW** — dispatch, but checkpoint and audit first. Pushes, PRs, service
  restarts, container rebuilds, preview deploys, schedule changes.
- **RED** — block this task and request scoped approval. Production deploys,
  external contact, publication, money, secret rotation, destructive deletes.

Two failure modes are guarded explicitly, because both are fatal in practice:

1. **Paralysis.** `scripts/validate-godlayer.sh` asserts that routine work stays
   GREEN. If someone reclassifies `shell.inspect` or `email.draft` as RED, the
   contract fails and CI goes red.
2. **Smuggling.** A GREEN tool cannot be used to perform a RED action. SOUL.md's
   RED list is compiled into `red_patterns` in `config/tools.yaml` and escalates
   any matching call regardless of the tool's default level.

```bash
scripts/hermesctl permissions classify shell run --payload '{"cmd":"drop production database"}'
# -> RED, matched_rule red.destructive_delete, dispatch_plan REQUEST_APPROVAL_BLOCK_TASK
```

A RED task blocks only itself. GREEN work in the same mission keeps running —
proven by `TestMissionIntegration.test_red_task_blocks_and_resumes_only_its_own_scope`.

Approvals are scoped to one task and expire:

```bash
scripts/hermesctl queue approve <task_id> --approver OSA --expires-minutes 30
```

## Mission State Machine

```
CREATED → INTAKE_VALIDATED → PLANNED → [WAITING_FOR_APPROVAL] → QUEUED
        → DISPATCHED → RUNNING → VALIDATING → COMPLETED
```

`RUNNING → COMPLETED` is **not** a legal transition. Completion requires passing
through `VALIDATING` and supplying at least one evidence reference; the ledger
raises rather than record an unevidenced success. `FAILED`, `BLOCKED`,
`CANCELLED` and `ROLLED_BACK` are reachable where they make sense.

Every event carries `previous_event_hash` and `event_hash`. The table has
`BEFORE UPDATE` and `BEFORE DELETE` triggers, so the log is append-only at the
storage layer, and `hermesctl ledger verify` recomputes the whole chain.

## Durable Queue

SQLite with WAL, so it survives a crash, a restart and a reboot without a broker.
Per task: attempts, exponential backoff (30s → capped at 1h), dead-letter after
`max_attempts`, idempotency key (unique across live tasks), dependencies,
cancellation, replay, worker lease with heartbeat, and stale-lease recovery.

`MAX_ACTIVE_TASKS` defaults to **1**. Raise it only after the safety tests still
pass at the higher value.

```bash
scripts/hermesctl queue stats
scripts/hermesctl queue list --status WAITING_FOR_APPROVAL
scripts/hermesctl queue recover
```

## Model Routing

Task classes map to a chain: preferred → fallback(s) → local. The router walks it
and applies capability, context-window, privacy and health filters.

The rule that matters: **a model is never silently substituted when it lacks a
required capability.** If nothing in the chain qualifies, the decision is
`BLOCKED` with the exact per-model rejection reason attached, and the task waits
instead of receiving confident nonsense from a model that cannot do the job.

```bash
scripts/hermesctl models route VISION --require vision
scripts/hermesctl models health
```

Health is runtime state under the worker state directory, refreshed by
`scripts/health-watch.sh`. An unknown model reads as `DOWN`, so an empty health
table blocks rather than assuming availability.

## Automations

| Job | Schedule | Script | Level |
| --- | --- | --- | --- |
| Health watch | `*/5 * * * *` | `scripts/health-watch.sh` | YELLOW |
| Repository watch | `*/30 * * * *` | `scripts/repo-watch.sh` | GREEN |
| Daily revenue ops | `0 8 * * *` | `scripts/revenue-ops.sh` | GREEN |
| Daily operations brief | `0 19 * * *` | `scripts/ops-brief.sh` | GREEN |
| Weekly system audit | `0 18 * * 0` | `scripts/weekly-audit.sh` | GREEN |
| Duty-cycle report | `0 5 * * *` | `scripts/hermes-report.sh` | GREEN |

`config/schedule.yaml` is the contract; the `infra/systemd/*.timer` files are the
implementation, and `validate-godlayer.sh` fails if the two disagree. No
scheduled job may be RED — nothing on a timer can contact anyone or spend money.

The health watch auto-recovers GREEN failures, logs YELLOW recovery with a
rollback command, and notifies OSA only when something critical survives
recovery. A healthy run is silent.

## Revenue Pipeline

Six tracks are supported by one ledger. What Hermes does autonomously: find and
score leads from lawful public sources, enrich records, generate mini-audits,
draft outreach and follow-ups, maintain the pipeline.

What it cannot do: contact anyone. Sending is RED in three independent places —
the tool registry, the RED patterns, and a database trigger that refuses an
`outreach_events` row without a scoped approval reference. `set_state(..., 'sent')`
raises `PermissionError` without one.

Money is never overstated. `estimated_value` and `pipeline_value` are forecasts;
`contracted_value`, `invoiced_value` and `received_value` are separate columns.
A forecast can never appear as cash.

```bash
scripts/hermesctl revenue add-lead lead-1 "Company" --team-size 10-49 --urgency high --consent
scripts/hermesctl revenue status
```

## Health and Observability

```bash
scripts/hermesctl health          # soul, tools, models, queue, ledger
scripts/health-watch.sh           # full host watch with recovery
```

The aggregate check backs `/health/live`, `/health/ready`, `/health/dependencies`,
`/health/queue`, `/health/models`, `/health/tools` and `/health/storage` when an
HTTP surface is wired to it. Journal records carry the constitution hash, so
every run is attributable to a specific constitution version.

## Operator Runbook

On `hydra-hermes-runtime-01`, as `hydra`:

```bash
scripts/host-baseline.sh                  # fact load, read-only
scripts/host-backup.sh                    # dry run: shows what it would capture
scripts/host-backup.sh --execute          # backup + rollback-manifest.json
scripts/hermesctl health                  # control-plane readiness
scripts/hermes-worker.sh --dry-run        # schedule, sends nothing
sudo systemctl enable --now hydra-hermes-worker.service
sudo systemctl enable --now hydra-hermes-healthwatch.timer hydra-hermes-repowatch.timer \
  hydra-hermes-revenue.timer hydra-hermes-brief.timer hydra-hermes-weekly-audit.timer \
  hydra-hermes-report.timer
scripts/evidence-bundle.sh                # evidence + manifest + sha256
```

Rollback is `rollback-manifest.json` in the newest backup directory: it lists the
git commits, checkpoint tags, image ids, services and exact restore commands.

## What This Layer Does Not Claim

- It does not prove the live runtime is healthy. Only a run on the host does that,
  and `scripts/health-watch.sh` reports honestly when a component is unreachable.
- It does not provide a dashboard. Every control listed in the mission brief maps
  to a `hermesctl` subcommand, so a UI can be wired to real capability instead of
  a mock — but the UI itself is not built here.
- It does not enable web research. `config/tools.yaml` declares a `research` tool
  with a health check; until that check passes on the host with valid credentials,
  the capability is unavailable and must be reported as unavailable.

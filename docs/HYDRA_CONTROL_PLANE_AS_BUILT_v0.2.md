# Hydra Control Plane — As-Built v0.2

Status: **WORKING** for the local vertical slice. Verified by a live end-to-end
run driven through the browser UI, not by tests alone.

This document describes what exists and runs. Anything not verified at runtime
is marked `UNKNOWN`. Anything that diverges from the canon is marked `DRIFT`.

## Canonical position

```text
OSA — ROOT AUTHORITY
  └─ ZGREDEK  (context, drift, policies, handoffs, memory)     → UNKNOWN, not implemented
       └─ HYDRA — CONTROL PLANE                                 → WORKING (this document)
            └─ MICHAEL ANGELO — CODING MISSIONS                 → WORKING (deterministic worker)
                 └─ APR CHECKPOINT after each transition        → WORKING (hash-chained ledger)
```

Zgredek does not implement, trade or deploy. Hydra does not code. Michael
Angelo codes. Minions are single-task workers *inside* Michael Angelo — never a
new top-level control plane.

## Runtime topology

```text
Browser (operator dashboard, PL)
  → Hydra loopback HTTP API           lib/hydra_control/server.py
     → MissionScheduler               lib/hydra_control/scheduler.py   durable-queue pump
     → MissionService                 lib/hydra_control/service.py     orchestration + gates
        → MissionCompiler             lib/hydra_control/compiler.py    Michael Angelo contract
        → Worker adapter registry     lib/hydra_control/adapters.py    AVAILABLE / UNAVAILABLE
        → ExecutionBackend            lib/hydra_control/backend.py     deterministic local worker
        → ControlPlaneStore           lib/hydra_control/store.py       SQLite, schema v1 + v2
```

The existing Hermes worker, `hermesctl`, systemd units and NemoClaw runtime are
**unchanged**. `lib/hermes` is a dependency (redaction, config), not a target.

## Control-plane capabilities

| Capability | State | Where |
|---|---|---|
| Project registry | WORKING | `control_projects`; 4 surfaces seeded |
| Repository registry | WORKING | `control_repositories`; `executable` flag gates workers |
| Runtime / worker registry | WORKING | `control_workers` + `adapters.py` host probes |
| Mission intake | WORKING | repo, base branch, task, acceptance criteria, required tests, risk, budget, worker, timeout, blueprint, priority |
| Mission graph | WORKING | 14 dependency-ordered nodes |
| Durable queue | WORKING | `control_queue`, SQLite-backed, lease + recovery |
| Scheduler | WORKING | bounded concurrency, auto-dispatch |
| Budgets and limits | WORKING | `control_budgets` + ledger; checked before each node |
| Model routing | WORKING | `control_models`; UNAVAILABLE never substituted |
| Sandbox lifecycle | WORKING | one workspace per mission, cleanup, kill switch |
| GREEN / YELLOW / RED | WORKING | per project, repository and approval |
| Approvals | WORKING | scoped, actor- and time-stamped |
| Retries | WORKING | single-node retry, downstream not restarted |
| Cancellation | WORKING | per mission + emergency stop |
| Recovery | WORKING | RUNNING→READY, LEASED→WAITING on boot |
| Health | WORKING | `/api/health/full`, degradation reasons |
| Logs | WORKING | redacted through the Hermes redactor |
| Artifacts | WORKING | opaque IDs, SHA-256 verified |
| Evidence | WORKING | bundle v1.1, commit-bound |
| Rollback | WORKING | commit-bound plan, required for COMPLETED |
| APR checkpoints | WORKING | append-only hash-chained event ledger |

## Michael Angelo execution plane

**Worker adapters.** Five declared. Availability is probed from the live host on
every read; a worker whose runtime is unreachable reports `UNAVAILABLE` and
*refuses* to execute. `UnavailableBackend` raises on every operation — it never
fabricates a session, commit or result. `AUTO` picks the first AVAILABLE
adapter; an explicitly requested worker is **never** substituted.

| Worker | Kind | Probe |
|---|---|---|
| `deterministic-local` | local | always available |
| `codex` | external CLI | `codex` on PATH + `HYDRA_CODEX_TOKEN` |
| `openhands` | external service | `HYDRA_OPENHANDS_URL` |
| `claude-worker` | external CLI | `claude` on PATH + `HYDRA_CLAUDE_WORKER_TOKEN` |
| `generic-minion` | ephemeral minion | never available until a concrete adapter binds |

**Blueprint.** Deterministic steps are scripted, never left to a model:
checkout → dependency setup → code generation → format → lint → typecheck →
unit tests → runtime verification → review → git diff → commit → local PR
descriptor.

**Sandbox.** One isolated workspace per mission under `control-workspaces/`,
real `git init`, checkout of a specific commit, bounded runtime and output, no
network, no production credentials, containment checked before every file
operation, symlinks refused.

## Completion gates

A mission **cannot** reach `COMPLETED` unless all of the following hold. Each is
enforced in `MissionService.evidence()` and re-checked at read time:

1. it passed `VALIDATING`;
2. every acceptance criterion is recorded and not `UNKNOWN`/`FAIL`;
3. every blueprint-required test has a result;
4. an evidence reference exists;
5. a git diff was recorded (`changedFiles` non-empty);
6. a **verified, commit-bound rollback plan** exists;
7. no required check is `FAIL` or `UNKNOWN`;
8. workspace `HEAD` still equals `resultCommit`;
9. every artifact still matches its recorded SHA-256;
10. the event chain verifies.

A later commit invalidates the bundle at read time, so stale evidence cannot
carry a mission to `PR_READY` or `COMPLETED`.

## Security posture

- Loopback bind only; remote exposure is refused at `create_server`.
- Repository input restricted to the built-in fixture; host paths and URLs refused.
- API values never become commands, executables, env keys or paths — node IDs
  select fixed argv arrays.
- Logs and artifacts pass through the Hermes redactor; secret scan is part of
  `make static-check`.
- Workers receive no production credentials and no network.
- Shell commands are recorded with argv, exit code and bounded output.
- A RED task blocks only itself; other missions keep running.
- Web3 Lab is registered as `RED` and isolated from the standard execution plane.
- CSP `default-src 'self'`, `X-Frame-Options: DENY`, `nosniff`, no `innerHTML`.

## Known DRIFT and UNKNOWN

| Item | Status | Note |
|---|---|---|
| Zgredek context packet / drift detection | **UNKNOWN** | No contract exists. UI and `/api/health/full` report `UNKNOWN`, not "ok". |
| Michael Angelo chat runtime | **UNKNOWN** | No callable endpoint. UI shows OFFLINE and fabricates no reply. |
| Real branch push + GitHub PR | **DRIFT (accepted)** | Deliberate: worker holds no credentials and no network. PR is a `LOCAL_DESCRIPTOR`. |
| Codex / OpenHands / Claude workers | **UNAVAILABLE** | Declared and probed; refuse to run. Not simulated. |
| Genkit Lab, Windows/RTX execution | **UNKNOWN** | Registered as projects only; no execution surface in this repo. |
| Host telemetry (CPU/RAM/disk) | **UNKNOWN** | No data source; dashboard says so rather than inventing numbers. |
| API key casing | **DRIFT (minor)** | Mission payloads mix `snake_case` and `camelCase`. Cosmetic; not changed to avoid breaking the existing v1 contract. |

## Data and configuration migration

Schema v2 is **strictly additive**. No v1 table is altered or dropped, so an
existing `missions.db` keeps every legacy Hermes and `control_*` contract.
Applying it is automatic on first open and idempotent; `schema_versions()`
returns `[1, 2]`.

New tables: `control_projects`, `control_repositories`, `control_workers`,
`control_models`, `control_budgets`, `control_budget_entries`, `control_queue`.

Registry seeding (`seed_registries()`) runs on every boot and is idempotent.

Optional environment variables — absence only causes `UNAVAILABLE`, never a
failure: `HYDRA_CODEX_TOKEN`, `HYDRA_OPENHANDS_URL`,
`HYDRA_CLAUDE_WORKER_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.

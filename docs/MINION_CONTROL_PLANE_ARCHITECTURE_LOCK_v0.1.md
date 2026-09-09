# Minion Control Plane Architecture Lock v0.1

Status: LOCKED for the local deterministic vertical slice.

This lock is additive. It does not replace `ARCHITECTURE_LOCK_v0.1.md`, change
the NemoClaw/OpenShell/Hermes deployment, or authorize a production rollout.

## Fact Boundary

- GitHub repository: `HazEOskA/hydra-hermes-lab`
- Existing runtime: Python 3, Bash, systemd, NemoClaw/OpenShell, YAML and SQLite
- Existing control code: `lib/hermes`, `scripts/hermesctl`, `scripts/hermes-worker.sh`
- Existing persistence: SQLite files beneath `HERMES_WORKER_STATE_DIR`
- Existing browser application or HTTP API: none
- Existing Michael Angelo integration: none
- Existing APR integration: none; APR is explicitly isolated by the baseline
- Existing frontend design system: none

Unavailable facts remain `UNKNOWN`. In particular, no callable Michael Angelo
service contract or isolated production execution backend exists in this repo.

## Minimal Vertical Slice

The slice adds a local Hydra mission service and command-center UI without
changing the Hermes worker. A deterministic mission compiler implements the
Michael Angelo contract locally until a real adapter is supplied. A deterministic
execution backend operates only on a built-in fixture repository inside a
dedicated state root. It creates a real Git repository, makes a controlled change,
runs allowlisted checks, captures exit codes and artifacts, and builds commit-bound
APR evidence.

```text
Browser
  -> Hydra loopback HTTP API
     -> MissionService / Orchestrator
        -> MissionCompiler protocol
           -> Deterministic Michael Angelo contract adapter
        -> ExecutionBackend protocol
           -> DeterministicLocalBackend
        -> ControlPlaneStore
           -> existing missions.db SQLite boundary
        -> dedicated workspaces and artifact files

Existing hermesctl / Hermes worker / NemoClaw runtime remain unchanged.
```

## State Models

Mission states:

```text
DRAFT
QUEUED
FACT_LOADING
PLANNING
AWAITING_ARCHITECTURE_APPROVAL
PROVISIONING
RUNNING
VALIDATING
REVIEWING
BUILDING_EVIDENCE
AWAITING_HUMAN_APPROVAL
PR_READY
COMPLETED
FAILED
BLOCKED
CANCELLED
```

Pipeline node states:

```text
PENDING
READY
RUNNING
PASSED
FAILED
BLOCKED
SKIPPED
CANCELLED
UNKNOWN
```

Risk levels:

```text
LOW
MEDIUM
HIGH
CRITICAL
```

Normal mission progression is:

```text
DRAFT -> QUEUED -> FACT_LOADING -> PLANNING
-> AWAITING_ARCHITECTURE_APPROVAL -> PROVISIONING -> RUNNING
-> VALIDATING -> REVIEWING -> BUILDING_EVIDENCE
-> AWAITING_HUMAN_APPROVAL -> PR_READY -> COMPLETED
```

`FAILED`, `BLOCKED`, and `CANCELLED` are explicit non-success states. A failed
node may transition back to `READY` for a scoped retry; downstream passed nodes
are not restarted. A recovered `RUNNING` node becomes `READY`, and its mission is
queued for an explicit resume event. `UNKNOWN` never satisfies a gate.

## Pipeline Contract

The compiler deterministically emits these dependency-ordered nodes:

1. Mission Intake
2. Repository Fact Load
3. Feasibility Analysis
4. Implementation Plan
5. Architecture Gate
6. Sandbox Provisioning
7. Agent Execution
8. Formatting / Lint / Typecheck
9. Targeted Tests
10. Runtime Verification
11. Independent Review
12. APR Evidence Bundle
13. Human Approval
14. Draft Pull Request

Architecture Gate and Human Approval block progression until a scoped approval
records actor, timestamp, gate and mission. The final node creates a local draft
PR descriptor only. This task does not push a branch or call the GitHub PR API.

## Event Contract

Every transition appends an immutable, hash-chained event containing:

- event ID
- mission ID
- node ID
- event type
- previous state
- next state
- timestamp
- actor
- backend
- optional message
- optional artifact references
- optional command result
- optional commit SHA
- previous event hash and event hash

SQLite triggers reject event update and delete. The hash covers every event field,
so command or commit metadata cannot be changed without breaking verification.

## Persistence Lock

Use the existing `missions.db` SQLite file. New `control_*` tables are namespaced
to avoid changing the legacy Hermes `missions` and `events` contracts:

- `control_schema_migrations`
- `control_missions`
- `control_pipeline_nodes`
- `control_events`
- `control_logs`
- `control_artifacts`
- `control_approvals`
- `control_command_results`
- `control_evidence_bundles`

Artifacts and worktrees live beneath the same configured state root in dedicated
`control-artifacts/` and `control-workspaces/` directories. The database stores
only canonical paths verified to remain beneath those roots. Reopening the same
state root is the restart-recovery contract.

## Compiler and Backend Contracts

`MissionCompiler` accepts validated intake and returns a typed mission manifest,
risk classification, execution contract, validation requirements and pipeline
nodes. The first adapter is deterministic and local; it does not claim to have
called the separate Michael Angelo product.

`ExecutionBackend` exposes the production-shaped operations:

```text
create_session(input) -> ExecutionSession
execute_task(input) -> ExecutionResult
get_status(session_id) -> ExecutionStatus
stream_events(session_id) -> AsyncIterable[ExecutionEvent]
cancel(session_id) -> None
collect_artifacts(session_id) -> list[ExecutionArtifact]
```

The UI and orchestrator depend on this protocol, never on the local backend
implementation. Future Codex, Claude Code, OpenHands, Ona, CLI and Hydra worker
backends register through backend discovery without changing mission storage.

## API Lock

The loopback service follows one JSON convention and never exposes a shell:

- `GET/POST /api/missions`
- `GET /api/missions/{missionId}`
- `POST /api/missions/{missionId}/start`
- `POST /api/missions/{missionId}/approvals`
- `POST /api/missions/{missionId}/nodes/{nodeId}/retry`
- `POST /api/missions/{missionId}/cancel`
- `GET /api/missions/{missionId}/events`
- `GET /api/missions/{missionId}/logs`
- `GET /api/missions/{missionId}/artifacts`
- `GET /api/missions/{missionId}/evidence`
- `GET /api/backends`

Unknown fields, invalid enum values, unbounded strings, path-like repository
values and unsupported backends return explicit 4xx error codes. Unhandled server
failures return a redacted 500 response and are logged without secrets.

## Security Lock

- Initial repository input is exactly `fixture://hydra-safe-demo`; host paths and
  URLs are refused.
- Backend actions are internal identifiers mapped to fixed argv arrays. No API
  field becomes a command, executable, environment key or filesystem path.
- Workspaces resolve beneath `control-workspaces/`; containment is checked before
  every file operation. Symlinks and reparse points in the fixture are refused.
- Subprocesses receive a minimal environment, bounded runtime and bounded output.
- Artifact and log output is redacted through the existing Hermes redactor.
- The worker receives no production credentials and never inherits all host env.
- High and critical missions cannot run without architecture approval. All
  missions require final human approval before PR-ready state.
- Deployment, infrastructure, destructive Git, migration, authentication,
  payment and secret operations are absent from the allowlist.
- The HTTP service binds to loopback by default. Production authentication and
  stronger OS/container isolation are required before any remote exposure.

## APR Lock

APR evidence stores the base and result commit SHA, exact changed files, diff
summary, command argv display, timestamps, exit codes, stdout/stderr artifacts,
check outcomes, risks and generated artifacts. Evidence is valid only when:

1. every required check is `PASS` or explicitly `NOT_REQUIRED`;
2. no required check is `UNKNOWN`;
3. the current workspace `HEAD` equals `resultCommit`;
4. every referenced artifact still matches its recorded SHA-256;
5. the event chain verifies.

A changed commit invalidates the bundle at read time and prevents PR-ready or
completed progression with stale evidence.

## Validation Lock

Validation must include:

- existing Linux/WSL Python suite
- existing Bash syntax and static checks where the host toolchain supports them
- control-plane unit and API tests
- state-transition and immutable-event tests
- failure and single-node retry test
- cancellation test
- restart-recovery test
- APR commit and artifact binding tests
- Python compile check
- browser UI live test against the loopback service
- secret scan and `git diff --check`

The native Windows baseline has five known probe-test errors because Unix `printf`
fixtures are executed by `cmd.exe`; the intended Linux/WSL suite is the acceptance
environment and passed before this slice was added.

## Rollback Lock

Rollback is repository-local and additive:

1. Stop the local Hydra HTTP process.
2. Revert only the files listed in the implementation report.
3. Delete only the dedicated test state directory after resolving and inspecting
   its exact path; never remove the shared Hermes state root.
4. Do not touch the Hermes sandbox, VPS, systemd units, credentials or production
   databases.

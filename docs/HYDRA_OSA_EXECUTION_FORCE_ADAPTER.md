# Hydra → OSA Execution Force adapter

## Authority boundary

- Hydra remains the only mission scheduler, queue and control-plane state
  owner.
- OSA Execution Force RuntimeV2 remains the execution governance and execution
  authority.
- Hermes, Claude, Codex and other hosts are workers selected below RuntimeV2;
  Hydra does not invoke them directly.
- APR/evidence verification does not schedule or execute work.

The adapter is `lib/hydra_control/osa_execution_force.py`. It implements the
existing Hydra `ExecutionBackend` contract and uses the official API v2
boundary:

- `POST /api/v2/missions/run`
- `GET /api/v2/missions/{mission_id}`
- `GET /health`

It does not contain RuntimeV2, a scheduler, a worker resolver, or an execution
engine.

## Required configuration

```text
HYDRA_EXECUTION_BACKEND=osa-execution-force
HYDRA_OSA_EXECUTION_FORCE_URL=https://reviewed-runtime.example
OSA_ACTIONS_API_KEY=<host-injected secret>
```

Only HTTPS is accepted, except loopback HTTP for tests. Configuration alone is
not reported as health: the live `/health` response must be `ok`, `healthy` or
`pass`.

Mission intake additionally requires:

```json
{
  "backend": "osa-execution-force",
  "repository": "github://owner/repository",
  "baseCommit": "0123456789abcdef0123456789abcdef01234567",
  "allowedScope": ["src/bounded_file.py"],
  "testCommand": ["pytest", "tests/test_bounded_file.py", "-q"],
  "environment": "development"
}
```

The Zgredek packet must be separately approved by an authorized OSA actor. The
adapter receives the approved packet SHA, approving actor and exact Hydra
mission ID as RuntimeV2 context facts.

## Fail-closed rules

- No token, endpoint or live health: `UNAVAILABLE`; no local fallback.
- `HostActionRequest`, approval wait or non-terminal RuntimeV2 state: Hydra
  `BLOCKED`; never success.
- Runtime state `FAILED`, `CANCELLED` or `REJECTED`: Hydra failure.
- Evidence authority `CLAIMED`: never satisfies a required check.
- Missing or duplicate evidence identity, broken provenance, event-chain
  mismatch, unknown required check, missing worker/command identity, unchanged
  commit, empty diff, failed tests or out-of-scope file: verification failure.
- RuntimeV2 cancellation is reported `UNSUPPORTED` because the verified API
  boundary has no cancellation operation. Hydra does not fabricate a remote
  cancellation.

The adapter persists only the Hydra↔RuntimeV2 mission correlation ID so a Hydra
process restart polls the same mission instead of submitting duplicate work.
Runtime snapshots and evidence are retained as redacted Hydra artifacts.

## Acceptance status

Unit/contract tests use a fake transport and prove translation and refusal
semantics. They are not a real worker acceptance test. A real `SYSTEM_WORKS`
verdict remains `BLOCKED` until a live authorized RuntimeV2, a real worker and a
safe fixture repository complete the full chain.

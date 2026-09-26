# Hydra Control Plane — Runbook

How to start the control plane, drive a coding mission, and roll it back.

## Requirements

- Python 3.11+ (`StrEnum` is required; verified on 3.11.15)
- `git` on PATH
- No third-party Python packages. Standard library only.

## 1. Local run

```bash
cd /path/to/hydra-hermes-lab

# Dedicated state root. Never point this at the shared Hermes state root
# while testing.
export HYDRA_STATE=/tmp/hydra-local-state
mkdir -p "$HYDRA_STATE"

PYTHONPATH=lib python3 -m hydra_control.server \
  --host 127.0.0.1 \
  --port 8787 \
  --state-dir "$HYDRA_STATE"
```

Expected first line:

```text
Hydra control plane listening on http://127.0.0.1:8787 state=... recovered=0 requeued=0 scheduler=on
```

Open <http://127.0.0.1:8787/> — the operator dashboard loads on
**Centrum dowodzenia**.

Serve the API without the queue pump (manual dispatch only):

```bash
PYTHONPATH=lib python3 -m hydra_control.server --state-dir "$HYDRA_STATE" --no-scheduler
```

The server binds to loopback only. `create_server` refuses any other host — do
not work around it. Remote exposure needs authentication and stronger OS or
container isolation first, and that is a separate, reviewed change.

## 2. Run a coding mission from the UI

1. Open **Michael Angelo**.
2. Fill *Nowa misja kodowa*: name, task description, repository, base branch,
   acceptance criteria (one per line), required tests (one per line), worker
   (`AUTO` or an explicit one), blueprint, risk, budget, timeout, priority.
3. Press **Zleć misję**. The mission is created and enqueued.
4. The scheduler leases it within ~1s and runs to the architecture gate.
5. Open **Zatwierdzenia** → **Zatwierdź** on the architecture gate.
6. Execution runs: sandbox → change → format/lint → tests → runtime
   verification → review → APR evidence.
7. Approve the human gate. The mission reaches **COMPLETED**.
8. From **Misje** use **Otwórz diff**, **Otwórz PR**, **Pobierz dowody**,
   **Rollback**.

An unavailable worker is refused at intake with an explicit reason. It is never
silently swapped for another worker.

## 3. Run a mission from the API

```bash
B=http://127.0.0.1:8787

MID=$(curl -s -X POST $B/api/missions \
  -H 'Content-Type: application/json' \
  -H 'X-Hydra-Actor: OSA' \
  -d '{
    "title": "Przykładowa misja",
    "request": "Add a deterministic helper to the demo app",
    "repository": "fixture://hydra-safe-demo",
    "baseBranch": "main",
    "acceptanceCriteria": ["Helper jest deterministyczny"],
    "requiredTests": ["test_app.py"],
    "worker": "AUTO",
    "budgetLimit": 5.0,
    "timeoutSeconds": 600,
    "priority": 10
  }' | python3 -c 'import sys,json;print(json.load(sys.stdin)["mission_id"])')

curl -s -X POST $B/api/missions/$MID/approvals \
  -H 'Content-Type: application/json' -H 'X-Hydra-Actor: OSA' \
  -d '{"gate":"architecture"}'

# after execution parks on the human gate
curl -s -X POST $B/api/missions/$MID/approvals \
  -H 'Content-Type: application/json' -H 'X-Hydra-Actor: OSA' \
  -d '{"gate":"human"}'

curl -s $B/api/missions/$MID/evidence | python3 -m json.tool
curl -s $B/api/missions/$MID/rollback | python3 -m json.tool
```

### Endpoints

| Method | Path |
|---|---|
| GET | `/api/health`, `/api/health/full` |
| GET | `/api/projects`, `/api/repositories`, `/api/workers`, `/api/models` |
| GET | `/api/registry`, `/api/budgets`, `/api/queue`, `/api/sandboxes`, `/api/approvals` |
| GET/POST | `/api/missions` |
| GET | `/api/missions/{id}` and `/events`, `/logs`, `/artifacts`, `/evidence`, `/diff`, `/rollback`, `/pull-request` |
| POST | `/api/missions/{id}/start`, `/approvals`, `/cancel`, `/nodes/{nodeId}/retry` |
| GET | `/api/artifacts/{id}/content` |

## 4. Validation

```bash
# Full repository gate: bash syntax, infra, worker, god-layer, recovery,
# python tests, docs and secret scan.
make static-check

# Control-plane tests only.
PYTHONPATH=lib python3 -m unittest discover -s tests/python -p 'test_*.py'
```

Green offline tests do **not** prove runtime. Confirm a real mission reaches
`COMPLETED` with `evidence.valid == true` before calling a change good.

## 5. Enabling a real external worker

Workers are declared in `lib/hydra_control/adapters.py` and probed from the
host. A worker becomes AVAILABLE only when its probe passes:

| Worker | Requirement |
|---|---|
| `osa-execution-force` | `HYDRA_OSA_EXECUTION_FORCE_URL`, `OSA_ACTIONS_API_KEY`, and live `/health` PASS |
| `codex` | `codex` on PATH **and** `HYDRA_CODEX_TOKEN` set |
| `openhands` | `HYDRA_OPENHANDS_URL` set |
| `claude-worker` | `claude` on PATH **and** `HYDRA_CLAUDE_WORKER_TOKEN` set |

`osa-execution-force` has a concrete `ExecutionBackend` implementation. It is
the only external execution authority wired into Hydra. The other declared
workers remain unavailable until they run behind OSA Execution Force; they are
not alternate Hydra backends. Select the canonical adapter when starting Hydra:

```bash
export HYDRA_EXECUTION_BACKEND=osa-execution-force
export HYDRA_OSA_EXECUTION_FORCE_URL=https://your-reviewed-runtime.example
# Inject from the host secret manager. Never commit this value.
export OSA_ACTIONS_API_KEY=...
PYTHONPATH=lib python3 -m hydra_control.server --state-dir "$HYDRA_STATE"
```

An OSA Execution Force mission must provide an exact lowercase `baseCommit`, a
non-empty repository-relative `allowedScope`, a non-empty argv `testCommand`,
and `repository=github://owner/repository`. Hydra sends these through the
official `/api/v2/missions/run` contract. A RuntimeV2 host-action request pauses
Hydra as `BLOCKED`; retry polls the same correlated RuntimeV2 mission. Hydra
accepts `COMPLETED` only with distinct base/result commits, worker identity,
executed command evidence, mechanically verified diff scope and tests, and a
valid RuntimeV2 event hash chain.

See `docs/HYDRA_OSA_EXECUTION_FORCE_ADAPTER.md` for the exact boundary and
failure semantics.

## 6. Rollback

See `docs/HYDRA_ROLLBACK_MANIFEST_v0.2.md`. Every mission with evidence also
carries its own commit-bound plan, downloadable from **Recovery** or
`GET /api/missions/{id}/rollback`.

## 7. Deployment status

`UNKNOWN` for any non-local runtime. This slice has been verified only on a
local loopback host. Deploying it to the Contabo/Hetzner runtime, the Hermes
sandbox or any production host is **not** authorized by this change and needs a
separate reviewed deployment plan.

# Hydra Control Plane v0.2 — Rollback Manifest

Rollback is repository-local and additive. It never touches the Hermes sandbox,
a VPS, systemd units, credentials or production databases.

## Scope of the change

Two commits on `claude/hydra-michael-angelo-launch-bizcvn`, on top of the merge
of `feat/hydra-ui-from-design-files-v0.1`:

| Commit | Content |
|---|---|
| `feat: add Hydra control-plane registries, durable queue, budgets and canonical mission gates` | backend |
| `feat: rebuild the operator dashboard in Polish with the canonical view set` | UI |
| `test/docs` commit | canon tests + as-built, runbook, this manifest |

### Files added

```text
lib/hydra_control/adapters.py
lib/hydra_control/scheduler.py
tests/python/test_hydra_canon.py
docs/HYDRA_CONTROL_PLANE_AS_BUILT_v0.2.md
docs/HYDRA_RUNBOOK.md
docs/HYDRA_ROLLBACK_MANIFEST_v0.2.md
```

### Files modified

```text
lib/hydra_control/store.py      schema v2 + registry/queue/budget accessors
lib/hydra_control/service.py    intake, gates, budgets, health, registries
lib/hydra_control/server.py     new endpoints, scheduler wiring
lib/hydra_control/models.py     manifest fields
lib/hydra_control/compiler.py   canonical intake, risk override, rollback requirement
lib/hydra_control/backend.py    unified git diff captured into evidence
web/app.js                      Polish rewrite + canonical views
web/index.html                  Polish shell
tests/python/test_hydra_ui.py   updated UI contract
```

No file was deleted.

## Level 1 — revert the code

```bash
git log --oneline -4
git revert --no-edit <ui-commit> <backend-commit>
make static-check
```

Or drop the branch entirely and return to the merged feature baseline:

```bash
git checkout claude/hydra-michael-angelo-launch-bizcvn
git reset --hard 0005f28   # feat: implement Hydra command center from design assets
```

`0005f28` is the last commit before this change. It is a working state: the
control plane and English UI run, without registries, queue, scheduler,
budgets, worker adapters or the new completion gates.

## Level 2 — revert the database

Schema v2 is additive, so **reverting the code needs no database change**. The
v2 tables are simply unread by older code.

To remove them anyway, against a stopped server and a backed-up file:

```sql
DROP TABLE IF EXISTS control_queue;
DROP TABLE IF EXISTS control_budget_entries;
DROP TABLE IF EXISTS control_budgets;
DROP TABLE IF EXISTS control_models;
DROP TABLE IF EXISTS control_workers;
DROP TABLE IF EXISTS control_repositories;
DROP TABLE IF EXISTS control_projects;
DELETE FROM control_schema_migrations WHERE version = 2;
```

Never run this against the shared Hermes state root without an inspected backup.
`control_events` is append-only and protected by triggers; do not attempt to
delete from it.

## Level 3 — per-mission rollback

Every mission with a valid evidence bundle carries its own commit-bound plan.
Get it from **Recovery** in the UI or:

```bash
curl -s http://127.0.0.1:8787/api/missions/<missionId>/rollback | python3 -m json.tool
```

The plan is:

1. Stop the local Hydra process.
2. In the mission workspace: `git reset --hard <baseCommit>`.
3. Verify `HEAD == baseCommit`.
4. Delete only that mission's dedicated state directory, after resolving and
   inspecting its exact path.
5. Do not touch the shared Hermes state root.

Mission workspaces live under `<state-dir>/control-workspaces/<missionId>` and
artifacts under `<state-dir>/control-artifacts/<missionId>`.

## Verification after rollback

```bash
make static-check
PYTHONPATH=lib python3 -m hydra_control.server --state-dir "$HYDRA_STATE"
curl -s http://127.0.0.1:8787/api/health
```

## Blast radius

| Surface | Affected |
|---|---|
| Hermes worker, `hermesctl`, systemd units | No |
| NemoClaw / OpenShell runtime | No |
| VPS, Tailscale, firewall | No |
| Production credentials | No |
| Legacy `missions`/`events` tables | No |
| `control_*` v1 tables | No — additive only |
| Local Hydra HTTP process | Yes — restart required |

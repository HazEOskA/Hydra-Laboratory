# Zgredek Context Packet v0.1 — rollback manifest

Repository-local and additive. Does not touch the Hermes sandbox, a VPS,
systemd units, credentials or production databases.

## Scope

One commit on `claude/hydra-michael-angelo-launch-bizcvn`.

### Added

```text
lib/hydra_control/zgredek.py
tests/python/test_zgredek_context.py
docs/evidence/zgredek-context-packet-v0.1/evidence-bundle.json
docs/evidence/zgredek-context-packet-v0.1/ROLLBACK.md
docs/evidence/zgredek-context-packet-v0.1/SHA256SUMS
```

### Modified

```text
lib/hydra_control/store.py       schema v3 + packet persistence + append_context_event
lib/hydra_control/service.py     packet preparation, refusal gate, retry on BLOCKED
lib/hydra_control/server.py      GET /api/context-packet/{missionId}
web/app.js                       packet status in the Zgredek card only
tests/python/test_hydra_canon.py two assertions updated to the new truth
```

No file deleted. No mission state, node or pipeline shape changed.

## Level 1 — revert the code

```bash
git revert --no-edit <this-commit>
make static-check
```

Or return to the previous commit:

```bash
git reset --hard 8ad6b08   # evidence: commit sanitized Hydra v0.2 E2E bundle
```

`8ad6b08` is a working state: the full control plane runs without the context
packet, and `repository-fact-load` executes unconditionally as it did before.

## Level 2 — revert the database

Schema v3 is additive, so **reverting the code needs no database change**. The
`control_context_packets` table is simply unread by older code.

To remove it anyway, against a stopped server and a backed-up file:

```sql
DROP TABLE IF EXISTS control_context_packets;
DELETE FROM control_schema_migrations WHERE version = 3;
```

`control_events` is append-only and trigger-protected. The
`CONTEXT_PACKET_PREPARED` and `CONTEXT_PACKET_VALIDATED` events **cannot and
must not** be deleted; they stay in the ledger as historical APR checkpoints
and do not affect a rolled-back runtime, which simply stops writing new ones.

## Level 3 — disable the gate without reverting

If the gate must be lifted urgently while keeping the rest, the single point of
enforcement is `CONTEXT_GATED_NODE` in `lib/hydra_control/service.py`. Setting
it to a node id that does not exist in the pipeline disables the refusal while
preserving packet preparation and the endpoint.

This is a deliberate reduction in safety: missions would then load repository
facts without approved context. Treat it as an incident action, not a
configuration option, and restore the gate before the next mission.

## Recovering a mission refused by the gate

A refused mission is `BLOCKED`, not `FAILED`, and keeps its full ledger. After
Zgredek re-approves the packet:

```bash
curl -s -X POST http://127.0.0.1:8787/api/missions/<missionId>/nodes/repository-fact-load/retry \
  -H 'X-Hydra-Actor: OSA'
```

Retry accepts `BLOCKED` as well as `FAILED` nodes, so no mission is stranded by
a gate. Passed nodes are not restarted.

## Blast radius

| Surface | Affected |
|---|---|
| Hermes worker, `hermesctl`, systemd units | No |
| NemoClaw / OpenShell runtime | No |
| VPS, Tailscale, firewall | No |
| Production credentials | No |
| Legacy `missions`/`events` tables | No |
| `control_*` v1 and v2 tables | No — additive only |
| Mission state machine / pipeline shape | No |
| `repository-fact-load` execution | Yes — now gated on an approved packet |
| Local Hydra HTTP process | Yes — restart required |

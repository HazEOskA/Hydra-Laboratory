# Policy AI / Cofounder — adapter boundary

Documentation only. No code, no deployment, no dependency added.

## Upstream

| Field | Value |
|---|---|
| Repository | `PolsiaAI/Polsia` (public) |
| **Pinned commit** | **`9cd1521b428933db1394b793549be23ac9ad7620`** |
| Commit date | 2026-03-18 |
| Language | Python + Next.js 14 |
| **License file** | **ABSENT** |

## The license blocks copying

There is no `LICENSE` in the pinned tree. Absent a license, the work is "all
rights reserved" by default: we may read it, but we may not copy it into this
repository or redistribute it. Any integration is therefore an **adapter over a
boundary we define**, never an import of upstream code. Obtaining an explicit
licence grant from the author is the only thing that changes this.

## Position in the stack

```text
OSA                         goal, and the only approval that matters
  └─ Policy AI / Cofounder  plans: missions, priorities, cost, risk, value
       └─ Zgredek           validates the context packet, detects drift
            └─ Hydra        creates and runs missions
                 └─ execution planes
```

Cofounder **plans**. Zgredek **validates**. OSA **approves**. Hydra **executes**.

Cofounder does not execute code, does not deploy, does not approve its own plan,
does not move money, and does not bypass Hydra.

## Architectural conflicts with Hydra

Four, each of which rules out adopting the upstream application wholesale:

1. **It has its own orchestrator agent.** Adopting it creates a second control
   plane. The canon has exactly one: Hydra.
2. **It ships email-outreach and finance agents.** Those are precisely what
   `D-005` defers and what `config/tools.yaml` disables — `payments:
   enabled: false`, enforced by `scripts/validate-godlayer.sh:91`.
3. **It requires Postgres, Redis, Celery (worker + beat) and Chroma.** The Hydra
   baseline is SQLite plus systemd. Adding four stateful services widens the
   blast radius and the credential surface for a planning capability.
4. **It ships a Next.js frontend behind nginx**, which implies an exposed port.
   The runtime rule is loopback only.

None of these services will be added.

## The boundary

Hydra accepts one artifact from Cofounder: a **plan proposal**. Nothing else
crosses.

```text
POST /api/plan-proposals        (not implemented)
  {
    "source": "policy-ai-cofounder",
    "upstreamCommit": "9cd1521b...",
    "goal": "<OSA goal, verbatim>",
    "missions": [
      { "title": ..., "request": ..., "acceptanceCriteria": [...],
        "requiredTests": [...], "riskLevel": ..., "estimatedCost": ...,
        "estimatedValue": ..., "priority": ... }
    ]
  }
```

Rules the adapter enforces:

- A proposal is **inert** until OSA approves it. It creates no mission by itself.
- Each mission still passes the existing intake, which is the only path that
  creates work: worker resolution, budget, Zgredek context packet, architecture
  gate, human gate.
- Cofounder may **read** mission status. It receives no execution capability, no
  worker, no sandbox, no credential.
- `estimatedCost` and `estimatedValue` are forecasts and are stored as such —
  the same separation `lib/hermes/revenue.py` already keeps between projected and
  received amounts.
- The adapter is stateless. Plans live in Hydra's existing store or nowhere.

## Test sequence, once the adapter exists

1. OSA states a test goal.
2. Cofounder returns a plan proposal.
3. Zgredek validates the context packet for each proposed mission.
4. The plan waits for OSA approval; nothing runs.
5. After approval Hydra creates the missions through normal intake.
6. Cofounder observes status and executes nothing.

**Status: NOT IMPLEMENTED.** No endpoint, no adapter, no dependency exists. This
document is the boundary contract, agreed before any code is written.

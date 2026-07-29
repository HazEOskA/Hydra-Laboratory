# Runtime Findings — 2026-07-29

Observed on `hydra-hermes-runtime-01` by the operator. Recorded because two of
these contradict the architecture lock, and a contradiction that stays undocumented
becomes a wrong assumption later.

## F-001: Sandbox stuck in `Provisioning` — root cause of the outage

`nemoclaw sandbox recover hydra-hermes-lab` reported:

```
Sandbox 'hydra-hermes-lab' is stuck in 'Provisioning' phase.
This usually happens when a process crash inside the sandbox prevented clean startup.
Run `nemoclaw hydra-hermes-lab rebuild --yes` to recreate the sandbox
(workspace state will be preserved).
```

Consistent with the rest of the evidence:

- `curl http://127.0.0.1:8642/health` → exit 7, connection refused. The Hermes API
  never bound its port.
- `nemohermes hydra-hermes-lab status --json` → `found: true`, `agent: hermes`,
  `agentRuntime: gateway`, and a recorded route. Metadata exists; the workload does not.

This single fault explains the API being down, the dashboard being unreachable and
the reported "Web tools: not currently available" — tools are served through the
Hermes tool gateway inside a sandbox that never finished starting.

**Status: diagnosed, not repaired.** Rebuild is destructive to the running
container and destroys the crash evidence, so it is gated on an operator decision.

## F-002: Live provider is `nvidia-prod`, not `nvidia-router`

```json
"model": "nvidia/nemotron-3-super-120b-a12b",
"provider": "nvidia-prod",
"liveRoute": {"provider": "nvidia-prod", "model": "nvidia/nemotron-3-super-120b-a12b"},
"routeDrift": null
```

D-002 and D-014 record a validated **routed** baseline through the NVIDIA Model
Router, and `scripts/validate-runtime.sh` asserts `provider ∈ {nvidia-router, routed}`.
The live value satisfies neither, so that gate would fail against the current runtime.

Three explanations are possible and the evidence does not yet separate them:

1. The sandbox was deliberately moved to a direct NVIDIA production provider.
2. NemoClaw `0.0.93` renamed the provider identifier.
3. The route drifted during one of the recorded recovery attempts.

This matters beyond naming. D-004 requires the provider credential to stay
host-side with the Model Router while Hermes sees only `inference.local`. If the
sandbox now talks to NVIDIA directly, that boundary needs re-verification —
specifically that `NVIDIA_INFERENCE_API_KEY` is still unset inside the sandbox.

**Status: open. Not normalised in code.** `config/models.yaml` records the live
model so routing works today; the architecture lock is left untouched pending a
decision.

## F-003: Recovery history in `~/.nemoclaw/`

```
onboard-failures/
onboard-session.json.before-endpoint-fix-20260724-004102
onboard-session.json.before-final-recovery-20260724-030638
sandboxes.json.before-nous-tools-1784844750162
source-pre-0.0.93-20260728T155445Z
rebuild-backups/hydra-hermes-lab
hermes-tool-gateway/, hermes-tool-gateway-broker.pid
```

NemoClaw was upgraded to `0.0.93` on 2026-07-28, one day before the outage, and a
`sandboxes.json` snapshot was taken before a tool-gateway change. An upgrade plus a
tool-gateway change immediately preceding a crash-on-startup is the strongest
available hypothesis for F-001, and the pre-upgrade source tree is still on disk,
so a downgrade path exists if the rebuild does not hold.

## F-004: Empty model health table blocked all routing

`hermesctl health` reported `models: ok=false`, `BLOCKED`. The cause was in this
repository, not on the host: nothing populated the provider health table, an
unknown model reads as `DOWN`, and so every route blocked permanently.

**Status: fixed.** `hermesctl models probe` reads the live route via
`nemohermes … status --json` and records it, and `health-watch.sh` runs it before
judging the route. A `Provisioning` sandbox records `DOWN`, so routing correctly
stays blocked while the runtime is broken — verified by
`TestProbe.test_provisioning_sandbox_is_down_not_healthy`.

## F-005: `hydra-direct` installed from an unpinned remote script

The operator ran, twice:

```
curl -fsSL https://2ec2a020e505dbabb5.v2.appdeploy.ai/install-hydra-direct.sh | sudo bash
```

This created `hydra-direct.service` and published port `19001` on the tailnet via
`tailscale serve`. Recorded as fact, with three properties worth noting: the script
is fetched from a host outside the repository's supply chain and is unpinned, so it
is not the reviewed-and-pinned installer path `docs/SECURITY_MODEL.md` describes;
it executed as root; and it added a listener that the port inventory in
`infra/hetzner/firewall-rules.yaml` does not account for.

**Status: open.** No action taken — it is the owner's host and the change was
deliberate. If it stays, port 19001 belongs in the documented port map.

## Control Plane Verified On The Host

Not everything was broken. From `hermesctl health` on `hydra-hermes-runtime-01`:

- `soul: ok`, sha256 `04410a6d7afe6eb084ac8e5cc50ef7bf8d94594c179566a43baa631ddc80f572` —
  byte-identical to the constitution built in CI, so the file that governs the
  runtime is the file in Git.
- `tools: ok`, 14 registered, 13 enabled.
- `queue` / `ledger`: not yet initialised, as expected before first use.
- The worktree at `~/hermes-godlayer` left the deployed checkout at
  `/opt/hydra/apps/hydra-hermes-lab` untouched.

## Next Actions

1. **Before any rebuild**, capture the crash evidence — it is destroyed by the
   rebuild: `nemohermes hydra-hermes-lab doctor --json`, sandbox logs, and
   `scripts/host-backup.sh --execute`.
2. Then `nemoclaw hydra-hermes-lab rebuild --yes` (operator decision; workspace
   state is preserved per the tool's own message).
3. After the rebuild, re-verify the credential boundary: prove
   `NVIDIA_INFERENCE_API_KEY` is unset inside the sandbox.
4. Resolve F-002 — decide whether `nvidia-prod` is the intended provider, then
   either update D-002 or restore the routed configuration.

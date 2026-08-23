# Hydra Hermes Lab

<div align="center">
  <img src="assets/hydra.png" alt="Hydra" width="400" />
</div>

GitHub-first operational control repository for running Hermes inside an NVIDIA NemoClaw/OpenShell sandbox on a dedicated Contabo VPS.

## Status

- Repository scaffold: ready
- Remote runtime: active Contabo/QEMU host connected privately through Tailscale; host baseline ready
- NemoClaw/Hermes baseline: validated — runtime PASS and controlled first prompt PASS
- Continuous duty cycle: defined and statically validated; enable on the runtime host per [CONTINUOUS_OPERATION.md](docs/CONTINUOUS_OPERATION.md)
- God-Layer control plane: constitution, permission engine, mission ledger, durable queue, model routing, automations and revenue pipeline — implemented and tested offline; see [GOD_LAYER.md](docs/GOD_LAYER.md)
- Baseline target: Hermes + NVIDIA Model Router
- Sandbox: `hydra-hermes-lab`
- Provider selector: `routed`
- Policy: `balanced`
- Web search, messaging, MCP servers, and custom plugins: disabled for baseline

## Architecture

```text
Cloud coding agent
  -> GitHub repository
  -> Contabo VPS / Ubuntu 24.04 host
  -> NemoClaw host CLI
  -> OpenShell
     -> host-side credentials
     -> balanced network policy
     -> Model Router :4000
        -> NVIDIA hosted models
  -> Hermes sandbox: hydra-hermes-lab
     -> https://inference.local/v1
```

The Model Router and provider credential remain host-side. Hermes receives a managed `inference.local` route and must never receive the raw `NVIDIA_INFERENCE_API_KEY`.

## Repository Boundary

This repository contains infrastructure definitions, safe operator scripts, validation contracts, and sanitized evidence. It is not a NemoClaw fork and contains no generated sandbox state or account secrets.

`HazEOskA/agent-proof-runtime` is a separate frozen competition artifact. It is not read, modified, copied, or integrated by this project.

## Remote Host Flow

1. Maintain the active locked Contabo runtime; `infra/hetzner/` is retained only as historical provisioning reference.
2. Run `make static-check` locally or in CI.
3. Run `scripts/remote-preflight.sh` on the selected host.
4. Supply `NVIDIA_INFERENCE_API_KEY` through the approved host secret mechanism.
5. After explicit approval, run `scripts/install-nemoclaw.sh --execute` for a fresh host or `scripts/onboard-hermes.sh --execute` when NemoClaw is already installed.
6. Run `scripts/validate-runtime.sh` and complete the controlled one-shot Hermes prompt in [VALIDATION_PLAN.md](docs/VALIDATION_PLAN.md).

No command in this repository should be run against an unreviewed host. Installation and destructive operations have explicit execution gates.

## Continuous Operation

After the baseline gates are green, the runtime host runs a supervised 24/7 duty
cycle: `scripts/hermes-worker.sh` picks the next due task from `tasks/`, sends one
controlled prompt through the sandbox boundary, records a redacted journal entry,
and repeats under a daily prompt cap, a minimum interval between prompts, and a
circuit breaker. `scripts/hermes-report.sh` turns the journal into sanitized
Markdown reports, and Hermes summarizes its own counters through the `self-report`
task.

```bash
scripts/hermes-worker.sh --dry-run     # show the schedule, send nothing
scripts/hermes-worker.sh --status      # counters, budget, breaker state
scripts/hermes-report.sh --stdout      # sanitized report for the last 24h
```

The loop never handles `NVIDIA_INFERENCE_API_KEY`, every prompt carries a fixed
read-only guard clause, and full model output is never written to disk. Pausing is
a single file: `touch $HERMES_WORKER_STATE_DIR/STOP`. See
[CONTINUOUS_OPERATION.md](docs/CONTINUOUS_OPERATION.md) for installation,
spend control, and operator commands.

## Control Plane

`SOUL.md` is the operational constitution and is injected into every duty-cycle
prompt; its SHA-256 is stamped on every journal record. `scripts/hermesctl` is the
operator surface over the whole control plane.

```bash
scripts/hermesctl health                              # soul, tools, models, queue, ledger
scripts/hermesctl permissions classify email send     # GREEN / YELLOW / RED decision
scripts/hermesctl queue list --status WAITING_FOR_APPROVAL
scripts/hermesctl queue approve <task_id> --approver OSA --expires-minutes 30
scripts/hermesctl models route VISION --require vision
scripts/hermesctl ledger verify                       # hash-chain integrity
scripts/hermesctl revenue status
```

Actions are classified GREEN (dispatch), YELLOW (checkpoint, audit, dispatch) or
RED (block this task, request scoped approval). A RED task blocks only itself.
Sending, publishing, production deploys and money movement are RED in the tool
registry, in the escalation patterns, and — for outreach — in the database itself.

Host operations live in `scripts/host-baseline.sh`, `scripts/host-backup.sh`,
`scripts/health-watch.sh` and `scripts/evidence-bundle.sh`. They run on
`hydra-hermes-runtime-01`, never in CI.

## Validation Commands

```bash
make static-check
scripts/remote-preflight.sh
scripts/validate-runtime.sh
make worker-check worker-loop-check
make godlayer-check python-tests
```

Real runtime checks require the remote host. GitHub Actions intentionally does not simulate a passing NemoClaw runtime.

The only repository-defined remote bridge is the manually dispatched [remote preflight workflow](docs/REMOTE_PREFLIGHT_BRIDGE.md). The private repository uses repository secrets, Tailscale workload identity, and approval gates on the host dispatch step.

## Locked Host

`hydra-hermes-runtime-01` is the active Contabo VPS, identified by DMI as `QEMU`: x86_64, 8 vCPU, approximately 24 GB RAM, 300 GB disk, Ubuntu 24.04, public IPv4 and IPv6, and no GPU requirement. The final manifest is statically validated in the CI.

## Official Sources

- [Hermes prerequisites](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/get-started/prerequisites.md)
- [Hermes quickstart](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/get-started/quickstart.md)
- [Model Router setup](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/inference/hosted-inference/set-up-model-router.md)
- [Command reference](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/reference/commands.md)
- [Credential storage](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/security/credential-storage.md)

## Future Hydra Work

The default routed baseline is validated and the duty cycle keeps it exercised. Custom router pools, additional tools, MCP servers, messaging, web search, and multi-agent Hydra orchestration remain deferred and feature-gated.

Sanitized final results are recorded in [RUNTIME_EVIDENCE.md](docs/RUNTIME_EVIDENCE.md).

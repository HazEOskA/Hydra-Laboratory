# Hydra Hermes Lab

GitHub-first operational control repository for evaluating Hermes inside an NVIDIA NemoClaw/OpenShell sandbox on a dedicated Hetzner Cloud host.

## Status

- Repository scaffold: ready
- Remote runtime: Hetzner CX43 target locked; not yet provisioned or connected
- NemoClaw installation: not started
- Baseline target: Hermes + NVIDIA Model Router
- Sandbox: `hydra-hermes-lab`
- Provider selector: `routed`
- Policy: `balanced`
- Web search, messaging, MCP servers, and custom plugins: disabled for baseline

## Architecture

```text
Cloud coding agent
  -> GitHub repository
  -> Hetzner CX43 / Ubuntu 24.04 host
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

This repository contains infrastructure definitions, safe operator scripts, validation contracts, and sanitized evidence. It is not a NemoClaw fork and contains no generated sandbox state or account state.

`HazEOskA/agent-proof-runtime` is a separate frozen competition artifact. It is not read, modified, copied, or integrated by this project.

## Remote Host Flow

1. Provision the locked Hetzner CX43 target using [the provisioning checklist](infra/hetzner/PROVISIONING_CHECKLIST.md).
2. Run `make static-check` locally or in CI.
3. Run `scripts/remote-preflight.sh` on the selected host.
4. Supply `NVIDIA_INFERENCE_API_KEY` through the approved host secret mechanism.
5. After explicit approval, run `scripts/install-nemoclaw.sh --execute` for a fresh host or `scripts/onboard-hermes.sh --execute` when NemoClaw is already installed.
6. Run `scripts/validate-runtime.sh` and complete the controlled dashboard prompt in [VALIDATION_PLAN.md](docs/VALIDATION_PLAN.md).

No command in this repository should be run against an unreviewed host. Installation and destructive operations have explicit execution gates.

## Validation Commands

```bash
make static-check
scripts/remote-preflight.sh
scripts/validate-runtime.sh
```

Real runtime checks require the remote host. GitHub Actions intentionally does not simulate a passing NemoClaw runtime.

The only repository-defined remote bridge is the manually dispatched [remote preflight workflow](docs/REMOTE_PREFLIGHT_BRIDGE.md). It is protected by the `hydra-runtime` GitHub Environment and performs read-only inspection over strict host-key-verified SSH. It is never triggered by a push or pull request.

## Locked Host

`hydra-hermes-runtime-01` is a Hetzner Cloud CX43 in Nuremberg (`nbg1`), with Falkenstein (`fsn1`) as fallback: x86_64, 8 shared vCPU, 16 GB RAM, 160 GB disk, Ubuntu 24.04, public IPv4 and IPv6, and no GPU requirement. Provider firewall input permits SSH only from approved operator CIDRs; ports 4000, 8642, and 18789 remain private and loopback-bound.

## Official Sources

- [Hermes prerequisites](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/get-started/prerequisites.md)
- [Hermes quickstart](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/get-started/quickstart.md)
- [Model Router setup](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/inference/hosted-inference/set-up-model-router.md)
- [Command reference](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/reference/commands.md)
- [Credential storage](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/security/credential-storage.md)

## Future Hydra Work

Baseline validation comes first. Custom router pools, additional tools, MCP servers, messaging, web search, and multi-agent Hydra orchestration remain deferred until the default routed pool has produced clean evidence.

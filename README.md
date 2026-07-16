# Hydra Hermes Lab

GitHub-first operational control repository for evaluating Hermes inside an NVIDIA NemoClaw/OpenShell sandbox on a separate Ubuntu Linux host.

## Status

- Repository scaffold: ready
- Remote runtime: not connected
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
  -> remote Ubuntu host
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

1. Provision a single-user Ubuntu 24.04 host meeting [host requirements](infra/host-requirements.md).
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

## Official Sources

- [Hermes prerequisites](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/get-started/prerequisites.md)
- [Hermes quickstart](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/get-started/quickstart.md)
- [Model Router setup](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/inference/hosted-inference/set-up-model-router.md)
- [Command reference](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/reference/commands.md)
- [Credential storage](https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/security/credential-storage.md)

## Future Hydra Work

Baseline validation comes first. Custom router pools, additional tools, MCP servers, messaging, web search, and multi-agent Hydra orchestration remain deferred until the default routed pool has produced clean evidence.

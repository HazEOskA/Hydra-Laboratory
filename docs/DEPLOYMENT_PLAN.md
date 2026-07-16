# Deployment Plan

## Target

A dedicated, single-user Ubuntu 24.04 host with Docker. The cloud Work container and GitHub Actions are control-plane environments, not runtime hosts.

## Phases

1. Provision the host using an approved provider and account.
2. Apply the baseline packages from `infra/cloud-init.yaml` or an equivalent reviewed image.
3. Install a supported Node.js version (`>=22.19`) through the operator's approved package source.
4. Run `scripts/remote-preflight.sh`; do not continue on a BLOCK.
5. Review host writes: `~/.nemoclaw/`, `~/.local/state/nemoclaw/`, OpenShell state, Docker images/volumes, and host Model Router virtual environment/state created by NemoClaw.
6. Make the NVIDIA credential available only to the approved process environment.
7. For a new host, run `scripts/install-nemoclaw.sh --execute`. The official hosted installer may install/start Docker and may require passwordless sudo or an interactive operator-approved elevation path.
8. If NemoClaw already exists and the name is free, run `scripts/onboard-hermes.sh --execute`.
9. Run `scripts/validate-runtime.sh`, then the controlled dashboard prompt.
10. Add sanitized facts to `INSTALL_EVIDENCE.md` and results to the validation record; never commit raw logs.

## Locked Runtime Configuration

| Setting | Value |
|---|---|
| Agent | `hermes` |
| CLI | `nemohermes` |
| Provider selector | `routed` |
| Sandbox | `hydra-hermes-lab` |
| Policy | `balanced` |
| Web search | disabled |
| Messaging | disabled |
| MCP / plugins | none |

## Remote Access

Hermes uses dashboard port 18789 and API port 8642. Keep both on loopback and use SSH forwarding during baseline validation. Do not publish these ports directly to the internet.

## Official References

- https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/get-started/quickstart.md
- https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/get-started/prerequisites.md
- https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/inference/hosted-inference/set-up-model-router.md

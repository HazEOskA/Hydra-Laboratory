# Deployment Plan

## Target

Hetzner Cloud CX43 `hydra-hermes-runtime-01`: x86_64, 8 shared vCPU, 16 GB RAM, 160 GB disk, Ubuntu 24.04, public IPv4 and IPv6, no GPU. Prefer `nbg1`; use `fsn1` only when capacity requires fallback. The cloud Work container and GitHub Actions are control-plane environments, not runtime hosts.

## Phases

1. In the operator's authenticated Hetzner Cloud session, create the exact server from `infra/hetzner/server-spec.yaml`, select an already-approved public SSH key, attach the reviewed firewall, and supply `infra/cloud-init.yaml` as user data. Do not put private keys or API tokens in user data.
2. Wait for cloud-init completion and any required reboot. Establish the separately approved host-side Tailscale membership, then confirm the `hydra` account accepts the selected public key through the private path.
3. Keep the provider firewall attached. It has no public ingress for ports 22, 4000, 8642, or 18789.
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

SSH is key-only as `hydra`; root login, password login, keyboard-interactive login, agent/X11 forwarding, tunnels, and remote forwarding are disabled. Local forwarding remains available for loopback management access. Hermes uses dashboard port 18789 and API port 8642. Keep both, and Model Router 4000, on loopback. Never publish them directly to the internet.

## Provisioning Boundary

Repository preparation does not create the server. Provisioning requires an authenticated Hetzner control-plane session and an already-approved SSH public key plus operator IPv4/IPv6 CIDRs. No Hetzner API token, private key, NVIDIA key, or password belongs in chat, Git, cloud-init, or command arguments.

The approved CI bridge is `.github/workflows/remote-preflight.yml`. It can be started only with `workflow_dispatch` from `main`, joins the private tailnet through GitHub OIDC, and runs only the read-only report mode. Private-repository compatibility uses repository secrets; no required-reviewer protection is claimed. A green report does not authorize installation or onboarding; those remain separate approval gates.

## Official References

- https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/get-started/quickstart.md
- https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/get-started/prerequisites.md
- https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/inference/hosted-inference/set-up-model-router.md

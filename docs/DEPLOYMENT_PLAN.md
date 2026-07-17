# Deployment Plan

## Target

Hetzner Cloud CX43 `hydra-hermes-runtime-01`: x86_64, 8 shared vCPU, 16 GB RAM, 160 GB disk, Ubuntu 24.04, public IPv4 and IPv6, no GPU. Prefer `nbg1`; use `fsn1` only when capacity requires fallback. The cloud Work container and GitHub Actions are control-plane environments, not runtime hosts.

## Phases

1. Outside Git and chat, create a one-off, non-reusable, non-ephemeral, short-lived Tailscale auth key tagged exactly `tag:hydra-runtime`; make it pre-approved when device approval is enabled. Do not enable Tailscale SSH.
2. Supply that value as `TS_RUNTIME_AUTH_KEY` to an approved local control process and run `scripts/render-cloud-init.sh --output /absolute/private/path/cloud-init.rendered.yaml`. The script refuses repository-local output and creates a mode-`0600` file. Do not commit, upload as a GitHub artifact, or retain this rendered file.
3. In the operator's authenticated Hetzner Cloud session, create the exact server from `infra/hetzner/server-spec.yaml`, select the approved Hydra public SSH key, attach the reviewed firewall, and submit the private rendered user data. Delete the rendered file immediately after the control plane accepts it.
4. Cloud-init validates `hydra` and key-only OpenSSH, installs Tailscale from the official Ubuntu `noble` repository, enables `tailscaled`, enrolls the persistent host using `--auth-key=file:…`, validates `tailscale0`, address, online state, hostname, and exact tag, and only then enables UFW. Docker, Node.js, and other runtime prerequisites follow the firewall gate.
5. If any Tailscale gate fails, cloud-init fails without enabling restrictive UFW. Do not add public TCP/22; use Hetzner Console to inspect `/var/log/cloud-init-output.log`, rotate the failed one-off auth key if needed, and rebuild only after explicit approval.
6. Keep the provider firewall attached. It has no public ingress for ports 22, 4000, 8642, or 18789. Confirm the persistent node is visible in the Tailscale admin console and that Tailscale SSH is disabled.
7. Wait for cloud-init completion and any required reboot. Through the private tailnet, confirm the `hydra` account accepts only its selected public key. Run `scripts/validate-tailscale-host.sh` with read-only root access during bootstrap acceptance, then run `scripts/remote-preflight.sh`; do not continue on a BLOCK.
8. Review host writes: `~/.nemoclaw/`, `~/.local/state/nemoclaw/`, OpenShell state, Docker images/volumes, and host Model Router virtual environment/state created by NemoClaw.
9. Make the NVIDIA credential available only to the approved process environment.
10. For a new host, run `scripts/install-nemoclaw.sh --execute`. The official hosted installer may install/start Docker and may require passwordless sudo or an interactive operator-approved elevation path.
11. If NemoClaw already exists and the name is free, run `scripts/onboard-hermes.sh --execute`.
12. Run `scripts/validate-runtime.sh`, then the controlled dashboard prompt.
13. Add sanitized facts to `INSTALL_EVIDENCE.md` and results to the validation record; never commit raw logs.

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

SSH is key-only as `hydra`; root login, password login, keyboard-interactive login, agent/X11 forwarding, tunnels, and remote forwarding are disabled. Local forwarding remains available for loopback management access. Tailscale SSH is disabled; OpenSSH listens behind both the Hetzner no-ingress firewall and UFW's interface-bound `tailscale0` rule. Hermes uses dashboard port 18789 and API port 8642. Keep both, and Model Router 4000, on loopback. Never publish them directly to the internet.

## Provisioning Boundary

Repository preparation does not create the server. Provisioning requires an authenticated Hetzner control-plane session, an approved Hydra public SSH key, and the external `TS_RUNTIME_AUTH_KEY` rendering flow. No Hetzner API token, private key, NVIDIA key, Tailscale key, or password belongs in chat, Git, argv, logs, or committed cloud-init. Only a protected, temporary rendered copy may carry the bootstrap credential, and it must stay outside the repository and be deleted after submission.

The approved CI bridge is `.github/workflows/remote-preflight.yml`. It can be started only with `workflow_dispatch` from `main`, joins the private tailnet through GitHub OIDC, and runs only the read-only report mode. Private-repository compatibility uses repository secrets; no required-reviewer protection is claimed. A green report does not authorize installation or onboarding; those remain separate approval gates.

## Official References

- https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/get-started/quickstart.md
- https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/get-started/prerequisites.md
- https://docs.nvidia.com/nemoclaw/latest/user-guide/hermes/inference/hosted-inference/set-up-model-router.md
- https://tailscale.com/docs/install/linux
- https://tailscale.com/docs/features/access-control/auth-keys
- https://tailscale.com/docs/reference/tailscale-cli/up

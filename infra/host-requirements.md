# Remote Host Requirements

Source: current NVIDIA NemoClaw Hermes documentation, reviewed at NVIDIA/NemoClaw commit `24c73341394b84b887fbcfa9ec5028a7e6fadfb8`.

| Resource | Minimum | Recommended |
|---|---:|---:|
| CPU | 4 vCPU | 4+ vCPU |
| RAM | 8 GB | 16 GB |
| Free disk | 20 GB | 40 GB |

## Locked Hetzner Target

| Property | Required value |
|---|---|
| Provider / plan | Hetzner Cloud CX43 |
| Location | `nbg1`, fallback `fsn1` |
| Hostname | `hydra-hermes-runtime-01` |
| Architecture | x86_64 |
| CPU / RAM / disk | 8 shared vCPU / 16 GB / 160 GB |
| Image | Ubuntu 24.04 |
| Network | public IPv4 and IPv6 |
| GPU | not required |

## Platform

- Ubuntu 24.04 Linux is the primary host-level validated path.
- Docker Engine is required and must be reachable by the runtime user.
- Node.js 22.19+ and npm 10+ are required.
- Required utilities: bash, curl, git, tar, binutils (`strings`), and zstd.
- Use the dedicated `hydra` account. Docker access has root-level impact and must not be shared with untrusted users.
- `systemd`, active UFW, fail2ban, unattended security upgrades, and key-only SSH are mandatory.
- Root SSH, password authentication, keyboard-interactive authentication, agent forwarding, X11 forwarding, and remote TCP forwarding are disabled.

## Private Management Plane

- Install Tailscale from the official stable Ubuntu 24.04 (`noble`) APT repository before enabling UFW.
- Enable and start `tailscaled`, then enroll the server as `hydra-hermes-runtime-01` with exactly `tag:hydra-runtime`.
- The server node is persistent. Do not use an ephemeral auth key or an ephemeral node; the on-disk `tailscaled` state and enabled systemd service must survive reboot.
- Tailscale SSH remains disabled. Hardened OpenSSH is transported over `tailscale0`.
- Before UFW can be enabled, validation must prove that `tailscale0` exists, Tailscale assigned an address, the backend is `Running`, the node is online, and the expected hostname and sole tag are visible.
- UFW permits TCP/22 only when the packet arrives on `tailscale0`. The Hetzner firewall has no public TCP/22 rule.

The production `TS_RUNTIME_AUTH_KEY` is an external bootstrap secret. It must be one-off, non-reusable, non-ephemeral, short-lived, tagged with `tag:hydra-runtime`, and pre-approved when device approval is active. Never place its value in Git, chat, command arguments, logs, evidence, or artifacts.

Render `infra/cloud-init.yaml` only through `scripts/render-cloud-init.sh` into a mode-`0600` absolute path outside the repository. The renderer reads `TS_RUNTIME_AUTH_KEY` from the approved process environment, inserts only its encoded bootstrap payload into the private rendered file, and never prints it. Cloud-init decodes the payload into a protected `/run` file, invokes `tailscale up` with the documented `file:` form, deletes both temporary files, and redacts the payload from its local cached user-data/config copies on both success and failure. Delete the rendered file immediately after the Hetzner control plane accepts it.

If repository installation, enrollment, service, interface, address, online-state, hostname, or tag validation fails, cloud-init exits unsuccessfully before UFW activation. Do not open public SSH as a fallback; use Hetzner Console for recovery.

## Model Router Python

NemoClaw probes `python3.13`, `python3.12`, `python3.11`, `python3.10`, then `python3`. A candidate must be `>=3.10,<3.14` and import `ensurepip`, `pyexpat`, `ssl`, and `venv`. The selected absolute path is supplied through `NEMOCLAW_MODEL_ROUTER_PYTHON` when pinning is needed.

## Ports

- 4000: host-side Model Router; must be free before onboarding and not public
- 18789: Hermes dashboard; loopback/tunnel only
- 8642: Hermes OpenAI-compatible API; loopback/tunnel only

## Capacity Caveat

The sandbox image is approximately 2.4 GB compressed. NVIDIA warns that low-memory hosts can hit the OOM killer during build/export; if RAM cannot be increased, at least 8 GB swap is a slower fallback.

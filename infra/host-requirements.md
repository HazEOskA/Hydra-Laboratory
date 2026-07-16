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

## Model Router Python

NemoClaw probes `python3.13`, `python3.12`, `python3.11`, `python3.10`, then `python3`. A candidate must be `>=3.10,<3.14` and import `ensurepip`, `pyexpat`, `ssl`, and `venv`. The selected absolute path is supplied through `NEMOCLAW_MODEL_ROUTER_PYTHON` when pinning is needed.

## Ports

- 4000: host-side Model Router; must be free before onboarding and not public
- 18789: Hermes dashboard; loopback/tunnel only
- 8642: Hermes OpenAI-compatible API; loopback/tunnel only

## Capacity Caveat

The sandbox image is approximately 2.4 GB compressed. NVIDIA warns that low-memory hosts can hit the OOM killer during build/export; if RAM cannot be increased, at least 8 GB swap is a slower fallback.

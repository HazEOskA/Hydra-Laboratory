# Hetzner Runtime Target

This directory is the locked infrastructure contract for `hydra-hermes-runtime-01`.

## Locked Server

| Field | Value |
|---|---|
| Provider | Hetzner Cloud |
| Type | CX43 |
| Architecture | x86_64 |
| CPU | 8 shared vCPU |
| RAM | 16 GB |
| Disk | 160 GB |
| Image | Ubuntu 24.04 |
| Preferred location | Nuremberg (`nbg1`) |
| Fallback | Falkenstein (`fsn1`) |
| Networking | Public IPv4 + IPv6 |
| Hostname | `hydra-hermes-runtime-01` |
| GPU | Not required |

The server must be created with an existing Hydra SSH public key selected from the Hetzner project. No private key, API token, password, or real credential belongs in this repository or the secret-free cloud-init template.

## Firewall

Create and attach a Hetzner Cloud Firewall from `firewall-rules.yaml` before treating the host as ready. The final-state policy contains no public SSH rule. GitHub Actions reaches the host through a separately approved private Tailscale path.

ICMP and ICMPv6 remain available for diagnostics and path MTU operation. No public inbound rule exists for SSH 22, Model Router 4000, Hermes API 8642, or dashboard 18789.

Hetzner Cloud Firewalls are stateful. With no outbound rules, outbound traffic remains allowed; response traffic to host-originated connections is admitted automatically.

## Cloud-init Boundary

Hetzner accepts cloud-init user data up to 32 KiB. `../cloud-init.yaml` is a secret-free template that must be rendered outside Git with `scripts/render-cloud-init.sh`. Its gated flow:

- creates the `hydra` operator,
- transfers only the Hetzner-injected SSH public key,
- disables root and password authentication after key validation,
- permits local SSH forwarding for the Hermes dashboard/API,
- installs Tailscale from the official stable Ubuntu `noble` repository,
- enrolls a persistent node as `hydra-hermes-runtime-01` with exactly `tag:hydra-runtime` and Tailscale SSH disabled,
- requires `tailscaled`, `tailscale0`, a Tailscale address, online control-plane status, hostname, and tag validation before UFW activation,
- enables UFW with TCP/22 accepted only on `tailscale0`,
- installs Docker from Ubuntu packages and enables bounded Docker logs,
- installs Node.js from the maintained Snap channel 22 and enforces `>=22.19`,
- enables fail2ban and unattended upgrades,
- does not install NemoClaw.

The production `TS_RUNTIME_AUTH_KEY` is supplied only to the external renderer. It must be one-off, non-reusable, non-ephemeral, short-lived, tagged `tag:hydra-runtime`, and pre-approved when device approval is active. The rendered file is mode `0600`, remains outside Git, and is deleted after submission. Cloud-init passes the key by protected temporary file using `--auth-key=file:…`, removes it, and redacts its cached payload. A Tailscale failure stops cloud-init before UFW is enabled; use Hetzner Console rather than public SSH for recovery.

## External Boundary

This repository intentionally does not contain executable Hetzner API calls. Provisioning begins only through an approved Hetzner Console session or an approved connection that keeps the Hetzner API token outside chat, Git, argv, and logs.

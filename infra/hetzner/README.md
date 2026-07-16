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

The server must be created with an existing SSH public key selected from the Hetzner project. No private key, API token, password, or provider credential belongs in this repository or cloud-init.

## Firewall

Create and attach a Hetzner Cloud Firewall from `firewall-rules.yaml` before treating the host as ready. Replace both `REQUIRED_OPERATOR_*_CIDR` markers through the Hetzner control plane with the operator's current trusted public networks. Do not replace them in Git.

Inbound TCP is limited to SSH port 22 from those CIDRs. ICMP and ICMPv6 remain available for diagnostics and path MTU operation. No inbound rule exists for Model Router 4000, Hermes API 8642, or dashboard 18789.

Hetzner Cloud Firewalls are stateful. With no outbound rules, outbound traffic remains allowed; response traffic to host-originated connections is admitted automatically.

## Cloud-init Boundary

Hetzner accepts cloud-init user data up to 32 KiB. `../cloud-init.yaml`:

- creates the `hydra` operator,
- transfers only the Hetzner-injected SSH public key,
- disables root and password authentication after key validation,
- permits local SSH forwarding for the Hermes dashboard/API,
- installs Docker from Ubuntu packages and enables bounded Docker logs,
- installs Node.js from the maintained Snap channel 22 and enforces `>=22.19`,
- enables UFW, fail2ban, and unattended upgrades,
- does not install NemoClaw or receive any secret.

## External Boundary

This repository intentionally does not contain executable Hetzner API calls. Provisioning begins only through an approved Hetzner Console session or an approved connection that keeps the Hetzner API token outside chat, Git, argv, and logs.

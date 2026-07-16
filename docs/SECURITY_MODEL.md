# Security Model

## Trust Boundaries

1. GitHub contains no runtime credentials or generated state.
2. The remote host owns NemoClaw, OpenShell, Docker, Model Router, and persistent sandbox state.
3. OpenShell owns provider credential registration and request rewriting.
4. Hermes sees `inference.local`, not the upstream NVIDIA credential or host port 4000.

## Secret Rules

- `NVIDIA_INFERENCE_API_KEY` must come from the remote process environment or an approved secret store.
- Never place it in argv, repository files, shell history, debug archives, screenshots, raw logs, or documentation.
- Never enable shell tracing (`set -x`) in credential-bearing scripts.
- Never copy `~/.nemoclaw/`, OpenShell state, generated Hermes environment, or Docker volumes into Git.
- Treat dashboard/API authentication material and one-time URLs as secrets.
- Run `scripts/secret-scan.sh` before every commit.

## Host Model

Use the dedicated Hetzner single-user host and `hydra` account. Docker group membership carries root-equivalent impact. Cloud-init enables unattended security upgrades, UFW, fail2ban, bounded Docker logs, and key-only SSH. Root/password/keyboard-interactive SSH and agent/X11/remote forwarding are disabled; local forwarding is retained only for loopback management access.

## Network Controls

- The Hetzner stateful firewall permits inbound TCP/22 only from separately approved operator IPv4 and IPv6 CIDRs.
- ICMP/ICMPv6 remains allowed for network operation and diagnostics.
- No provider outbound rules means outbound traffic follows Hetzner's default allow behavior; OpenShell `balanced` policy separately constrains sandbox traffic.
- Ports 4000, 8642, and 18789 must bind only to `127.0.0.1` or `::1`; UFW is defense in depth, not a substitute for correct Docker port binding.

## Host Provisioning Secrets

Only a public SSH key may be selected during provisioning. Hetzner API tokens, SSH private keys, account passwords, `NVIDIA_INFERENCE_API_KEY`, rendered user data, and generated server state are excluded from Git and chat. Required firewall CIDRs are applied in the provider control plane and are not committed as personal network data.

## Sandbox Proof

Validation must prove that `NVIDIA_INFERENCE_API_KEY` is unset inside `hydra-hermes-lab`. It must also prove that the active route is `routed`/`nvidia-router` and that inference flows through `https://inference.local/v1`.

## Evidence Handling

Commit versions, timestamps, exit classifications, redacted routes, and PASS/WARN/BLOCK results. Do not commit full sessions, raw environment dumps, provider payloads, or unrestricted diagnostic archives.

Before a destructive runtime change, take both a NemoClaw sandbox snapshot and, when appropriate, a Hetzner server snapshot. Hetzner server snapshots contain the server disk and can contain secrets; keep them private in the operator account. Attached volumes, if ever added, require separate backup treatment.

## Supply Chain

The install script uses NVIDIA's documented hosted installer URL. It downloads to a private temporary file and executes only after an explicit `--execute` gate. The installed last-known-good release must be recorded in sanitized evidence.

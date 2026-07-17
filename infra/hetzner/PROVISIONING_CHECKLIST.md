# Hetzner Provisioning Checklist

## Before Create

- [ ] Hetzner project selected through an approved authenticated session.
- [ ] Existing operator SSH public key selected; no password-only server creation.
- [ ] Cloud Firewall created from `firewall-rules.yaml`.
- [ ] Final-state provider firewall has no public TCP/22 rule.
- [ ] Firewall attached by labels or explicitly to the new server.
- [ ] One-off, non-reusable, non-ephemeral, short-lived Tailscale key created with exactly `tag:hydra-runtime`; pre-approved if device approval is active.
- [ ] `TS_RUNTIME_AUTH_KEY` supplied outside Git/chat to `scripts/render-cloud-init.sh`; mode-`0600` output is outside the repository.
- [ ] Private rendered cloud-init supplied as user data and deleted locally immediately after Hetzner accepts it.

## Create Contract

- Name: `hydra-hermes-runtime-01`
- Type: `CX43`
- Image: Ubuntu 24.04
- Location: `nbg1`; use `fsn1` only when CX43 capacity is unavailable
- Network: IPv4 and IPv6 enabled
- SSH key: existing selected Hetzner project key
- GPU: none
- User data: temporary output rendered from `infra/cloud-init.yaml` outside Git

## First-Boot Gate

- [ ] Wait for cloud-init completion.
- [ ] Confirm the Tailscale admin console shows online persistent host `hydra-hermes-runtime-01` with exactly `tag:hydra-runtime`.
- [ ] Confirm Tailscale SSH is disabled and UFW accepts TCP/22 only on `tailscale0`.
- [ ] If Tailscale/bootstrap failed, use Hetzner Console; do not add public SSH and do not reuse the auth key.
- [ ] If `/var/run/reboot-required` exists, reboot once before runtime installation.
- [ ] Connect as `hydra` through the approved private Tailscale path, never as root.
- [ ] Verify the host fingerprint using the Hetzner Console before trusting the first connection.
- [ ] Enable server delete and rebuild protection before installing runtime software.
- [ ] Run `scripts/remote-preflight.sh` from a clean checkout of this repository.
- [ ] Do not supply `NVIDIA_INFERENCE_API_KEY` until preflight is green and installation is explicitly approved.

## After Baseline Validation

- [ ] Confirm delete and rebuild protection remain enabled.
- [ ] Create a Hetzner Snapshot only after credential handling has been reviewed; snapshots capture the host disk.
- [ ] Record only sanitized server facts in `docs/INSTALL_EVIDENCE.md`.

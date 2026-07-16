# Hetzner Provisioning Checklist

## Before Create

- [ ] Hetzner project selected through an approved authenticated session.
- [ ] Existing operator SSH public key selected; no password-only server creation.
- [ ] Cloud Firewall created from `firewall-rules.yaml`.
- [ ] SSH source markers replaced in the Hetzner control plane with trusted IPv4 and IPv6 CIDRs.
- [ ] Firewall attached by labels or explicitly to the new server.
- [ ] `infra/cloud-init.yaml` supplied as cloud-init user data.

## Create Contract

- Name: `hydra-hermes-runtime-01`
- Type: `CX43`
- Image: Ubuntu 24.04
- Location: `nbg1`; use `fsn1` only when CX43 capacity is unavailable
- Network: IPv4 and IPv6 enabled
- SSH key: existing selected Hetzner project key
- GPU: none
- User data: `infra/cloud-init.yaml`

## First-Boot Gate

- [ ] Wait for cloud-init completion.
- [ ] If `/var/run/reboot-required` exists, reboot once before runtime installation.
- [ ] Connect as `hydra`, never as root.
- [ ] Verify the host fingerprint using the Hetzner Console before trusting the first connection.
- [ ] Enable server delete and rebuild protection before installing runtime software.
- [ ] Run `scripts/remote-preflight.sh` from a clean checkout of this repository.
- [ ] Do not supply `NVIDIA_INFERENCE_API_KEY` until preflight is green and installation is explicitly approved.

## After Baseline Validation

- [ ] Confirm delete and rebuild protection remain enabled.
- [ ] Create a Hetzner Snapshot only after credential handling has been reviewed; snapshots capture the host disk.
- [ ] Record only sanitized server facts in `docs/INSTALL_EVIDENCE.md`.

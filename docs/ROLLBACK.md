# Rollback

All commands run on the remote host. Inspect first; destructive steps require separate approval.

The Hetzner server itself is a separate rollback layer. Provider-console operations require an authenticated operator session and are never automated from CI.

## Failed Bootstrap Before Private Access

If Tailscale installation, enrollment, or `tailscale0` validation fails, cloud-init deliberately stops before `ufw --force enable`. Do not add a public TCP/22 rule and do not enable Tailscale SSH.

1. Use Hetzner Console, the designated recovery path, to inspect cloud-init status and the redacted error context. Never copy raw user data or credential-bearing logs into Git or chat.
2. Confirm UFW was not activated by the failed bootstrap. Do not weaken the provider firewall.
3. Revoke or confirm automatic consumption of the failed one-off Tailscale auth key. Never reuse it.
4. Fix the template or external tailnet policy in the repository/control plane. Run static tests again.
5. Rebuild the fresh host only after explicit approval, using a new one-off, non-ephemeral, tagged, short-lived key and a newly rendered private cloud-init file.

The source template is safe to retain. Any rendered cloud-init file is secret-bearing and must be deleted after submission or failure; it must never enter Git, GitHub Actions artifacts, diagnostics, or evidence.

## Inspect

```bash
nemohermes hydra-hermes-lab status
nemohermes hydra-hermes-lab doctor --json
nemohermes hydra-hermes-lab logs --since 10m --tail 200
nemoclaw inference get --json
```

## Stop / Start

```bash
nemohermes hydra-hermes-lab stop
nemohermes hydra-hermes-lab start
```

Stopping preserves workspace files, policies, credentials, registry state, and the OpenShell record.

## Snapshot

```bash
nemohermes hydra-hermes-lab snapshot create --name before-change
nemohermes hydra-hermes-lab snapshot list
```

If Hermes shields prevent a snapshot, follow the installed release's documented timed shields workflow; do not bypass it manually.

For host-level rollback, take a private Hetzner server snapshot only after reviewing data sensitivity. A server snapshot captures the server disk but not separately attached volumes. Record only the non-secret snapshot identifier in evidence; never export snapshot contents to Git.

## Diagnostics

```bash
nemoclaw debug --quick --sandbox hydra-hermes-lab
```

Full debug archives can contain sensitive operational context. Keep them outside Git and redact before sharing.

## Rebuild

After a successful snapshot and explicit approval:

```bash
nemohermes hydra-hermes-lab rebuild --yes
```

Rebuild preserves supported state and strips credentials from backups, but it still replaces the sandbox image and must not be automated casually.

## Remove Only This Sandbox

Use the guarded wrapper only after explicit approval:

```bash
scripts/destroy-sandbox.sh --sandbox hydra-hermes-lab --confirm-destroy hydra-hermes-lab
```

## Uninstall NemoClaw

Documentation only; requires separate destructive approval:

```bash
nemoclaw uninstall
```

Do not add `--destroy-user-data` unless losing registry metadata and backups is explicitly approved. Host directories such as `~/.nemoclaw/`, `~/.local/state/nemoclaw/`, backups, Docker images/volumes, and OpenShell state may remain depending on selected flags.

## Hetzner Host Rollback

1. Preserve the provider firewall and private OpenSSH-over-Tailscale path while diagnosing; do not open public SSH or enable Tailscale SSH.
2. Stop the Hermes sandbox and collect redacted diagnostics.
3. Create a NemoClaw snapshot; optionally create a private Hetzner server snapshot.
4. Rebuild only after explicit approval and only with the same Ubuntu 24.04 image, public key, firewall, and reviewed cloud-init.
5. Deleting `hydra-hermes-runtime-01`, its public IPs, snapshots, firewall, or account resources is outside the destroy script and always requires a separate explicit approval after exact resource identifiers are reviewed.

Removing the persistent host from the tailnet or running `tailscale logout` is a separate destructive network action. It can sever the only SSH management path and requires explicit approval plus confirmed Hetzner Console access. Do not automate it in `destroy-sandbox.sh`.

Do not disable deletion protection merely to make an automated workflow pass. Removal of the NemoClaw sandbox does not authorize deleting the Hetzner server, and deletion of the server does not authorize deleting private snapshots.

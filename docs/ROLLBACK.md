# Rollback

All commands run on the remote host. Inspect first; destructive steps require separate approval.

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

#!/usr/bin/env bash
# Protect the current state before an upgrade, and write the manifest that makes
# the upgrade reversible.
#
# Nothing here deletes or replaces anything. The output is a backup directory and
# a rollback-manifest.json whose commands restore exactly what was captured.
set -Eeuo pipefail
umask 077

BASE_PATH="${HYDRA_BASE_PATH:-/opt/hydra}"
BACKUP_ROOT="${HERMES_BACKUP_ROOT:-$BASE_PATH/backups}"
STATE_DIR="${HERMES_WORKER_STATE_DIR:-/var/lib/hydra-hermes/worker}"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$BACKUP_ROOT/hermes-pre-upgrade-$stamp"

log() { printf '%s backup %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

if [[ "${1:-}" != "--execute" ]]; then
  printf 'Dry run. Would back up into: %s\n' "$out"
  printf 'Sources: %s, %s, systemd units, docker image ids, git checkpoints.\n' \
    "$BASE_PATH" "$STATE_DIR"
  printf 'Re-run with --execute to write the backup and rollback manifest.\n'
  exit 0
fi

mkdir -p "$out/config" "$out/state" "$out/db"
log "backing up into $out"

# -- git checkpoints ------------------------------------------------------
declare -a repos=() commits=()
while IFS= read -r gitdir; do
  repo="$(dirname "$gitdir")"
  commit="$(git -C "$repo" rev-parse HEAD 2>/dev/null || printf unknown)"
  repos+=("$repo")
  commits+=("$commit")
  # A tag is a cheap, non-destructive checkpoint that survives a bad upgrade.
  git -C "$repo" tag -f "hermes-pre-upgrade-$stamp" >/dev/null 2>&1 || true
done < <(find "$BASE_PATH" "$HOME" -maxdepth 4 -type d -name .git 2>/dev/null | sort -u)

# -- configuration --------------------------------------------------------
for candidate in /etc/hydra-hermes "$BASE_PATH/config" "$BASE_PATH/.env" "$repo_root/config"; do
  [[ -e "$candidate" ]] || continue
  cp -a "$candidate" "$out/config/" 2>/dev/null || true
done
# .env files are copied for restore, then locked down. They stay out of Git.
find "$out/config" -name '.env*' -exec chmod 600 {} + 2>/dev/null || true

# -- runtime state and databases -----------------------------------------
if [[ -d "$STATE_DIR" ]]; then
  cp -a "$STATE_DIR" "$out/state/worker" 2>/dev/null || true
fi
while IFS= read -r db; do
  name="$(basename "$db")"
  # .backup is consistent under concurrent writers; a file copy is not.
  sqlite3 "$db" ".backup '$out/db/$name'" 2>/dev/null \
    || cp -a "$db" "$out/db/$name" 2>/dev/null || true
  sqlite3 "$db" .schema >"$out/db/$name.schema.sql" 2>/dev/null || true
done < <(find "$STATE_DIR" "$BASE_PATH" -maxdepth 3 -name '*.db' 2>/dev/null | sort -u)

# -- docker and systemd ---------------------------------------------------
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.ID}}\t{{.Status}}' \
  >"$out/containers.txt" 2>/dev/null || printf '(docker unavailable)\n' >"$out/containers.txt"
docker images --format '{{.Repository}}:{{.Tag}}\t{{.ID}}' \
  >"$out/images.txt" 2>/dev/null || printf '(docker unavailable)\n' >"$out/images.txt"
docker volume ls --format '{{.Name}}' \
  >"$out/volumes.txt" 2>/dev/null || printf '(docker unavailable)\n' >"$out/volumes.txt"
systemctl list-units --type=service --state=running --no-pager --plain \
  >"$out/services.txt" 2>/dev/null || printf '(systemd unavailable)\n' >"$out/services.txt"
ss -tulpn >"$out/ports.txt" 2>/dev/null || printf '(ss unavailable)\n' >"$out/ports.txt"

# -- manifest -------------------------------------------------------------
BACKUP_DIR="$out" STAMP="$stamp" REPOS="$(printf '%s\n' "${repos[@]:-}")" \
COMMITS="$(printf '%s\n' "${commits[@]:-}")" python3 - <<'PY'
import json, os, pathlib, subprocess

out = pathlib.Path(os.environ["BACKUP_DIR"])
repos = [line for line in os.environ.get("REPOS", "").splitlines() if line]
commits = [line for line in os.environ.get("COMMITS", "").splitlines() if line]
stamp = os.environ["STAMP"]


def lines(name):
    path = out / name
    if not path.is_file():
        return []
    return [line for line in path.read_text(errors="replace").splitlines() if line.strip()]


def host():
    try:
        return subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


containers = [line.split("\t")[0] for line in lines("containers.txt") if "\t" in line]
images = [line.split("\t")[-1] for line in lines("images.txt") if "\t" in line]
volumes = [line for line in lines("volumes.txt") if not line.startswith("(")]
services = [line.split()[0] for line in lines("services.txt") if line.split()]

rollback = [
    f"# Restore configuration: cp -a {out}/config/. /etc/hydra-hermes/",
    f"# Restore worker state: cp -a {out}/state/worker/. "
    f"{os.environ.get('HERMES_WORKER_STATE_DIR', '/var/lib/hydra-hermes/worker')}/",
    f"# Restore a database: cp -a {out}/db/<name>.db <original path>",
]
for repo, commit in zip(repos, commits):
    rollback.append(f"git -C {repo} reset --hard {commit}")
    rollback.append(f"# or: git -C {repo} checkout hermes-pre-upgrade-{stamp}")
for service in services:
    if "hydra" in service or "hermes" in service:
        rollback.append(f"sudo systemctl restart {service}")

manifest = {
    "timestamp": stamp,
    "host": host(),
    "repositories": repos,
    "git_commits": dict(zip(repos, commits)),
    "containers": containers,
    "images": images,
    "volumes": volumes,
    "services": services,
    "ports": lines("ports.txt")[:50],
    "config_backups": sorted(str(p.relative_to(out)) for p in (out / "config").rglob("*") if p.is_file()),
    "database_backups": sorted(str(p.relative_to(out)) for p in (out / "db").glob("*.db")),
    "rollback_commands": rollback,
}
(out / "rollback-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(f"manifest entries: repos={len(repos)} containers={len(containers)} "
      f"images={len(images)} services={len(services)}")
PY

ln -sfn "$out" "$BACKUP_ROOT/latest"
log "backup complete: $out"
log "rollback manifest: $out/rollback-manifest.json"

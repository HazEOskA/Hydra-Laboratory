#!/usr/bin/env bash
# Provenance audit for hydra-direct (OSA Decision 2).
#
# Do not delete it. Record everything about it, and if provenance cannot be
# established, keep it disabled and outside the Hermes trust boundary.
#
# Audit-only by default. `--enforce` applies the quarantine when provenance is
# unproven, and records the exact rollback command for undoing that.
# shellcheck disable=SC2015
set -Eeuo pipefail
umask 077

STATE_DIR="${HERMES_WORKER_STATE_DIR:-/var/lib/hydra-hermes/worker}"
OUT_DIR="${HYDRA_DIRECT_AUDIT_DIR:-$STATE_DIR/audit}"
UNIT="${HYDRA_DIRECT_UNIT:-hydra-direct}"
PORT="${HYDRA_DIRECT_PORT:-19001}"
INSTALL_URL="${HYDRA_DIRECT_INSTALL_URL:-https://2ec2a020e505dbabb5.v2.appdeploy.ai/install-hydra-direct.sh}"

enforce=0
fetch_installer=0
for arg in "$@"; do
  case "$arg" in
    --enforce) enforce=1 ;;
    --fetch-installer) fetch_installer=1 ;;
    -h|--help)
      printf 'Usage: audit-hydra-direct.sh [--enforce] [--fetch-installer]\n'
      exit 0
      ;;
    *) printf 'Unknown argument: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

mkdir -p "$OUT_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
report="$OUT_DIR/hydra-direct-$stamp.md"

provenance_verified=0
findings=0
note() { printf -- '- %s\n' "$*"; }
gap()  { printf -- '- [ ] UNVERIFIED: %s\n' "$*"; findings=$((findings + 1)); }

{
  printf '# hydra-direct Provenance Audit\n\n'
  printf -- '- collected: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf -- '- host: %s\n' "$(hostname)"
  printf -- '- declared install source: %s\n\n' "$INSTALL_URL"

  printf '## Installer provenance\n\n'
  if (( fetch_installer == 1 )); then
    tmp="$(mktemp)"
    if curl -fsSL --max-time 20 "$INSTALL_URL" -o "$tmp" 2>/dev/null; then
      note "installer sha256: $(sha256sum "$tmp" | cut -d' ' -f1)"
      note "installer bytes: $(wc -c <"$tmp")"
      note "fetched for hashing only; it was not executed"
    else
      gap "installer could not be re-fetched from $INSTALL_URL"
    fi
    rm -f "$tmp"
  else
    gap "installer not re-fetched (pass --fetch-installer to hash it)"
  fi
  gap "installer is unpinned: the URL carries no version, digest or signature"

  printf '\n## systemd units\n\n```\n'
  systemctl cat "$UNIT" 2>&1 | sed -E 's/(token|key|secret|password)=[^[:space:]]+/\1=[REDACTED]/gI' || \
    printf '(unit %s not found)\n' "$UNIT"
  printf '```\n\n'

  printf '### Unit state\n\n```\n'
  systemctl show "$UNIT" -p LoadState -p ActiveState -p UnitFileState -p FragmentPath \
    -p User -p ExecStart -p Restart 2>&1 || printf '(unavailable)\n'
  printf '```\n\n'

  printf '## Installed files and hashes\n\n```\n'
  exec_path="$(systemctl show "$UNIT" -p ExecStart --value 2>/dev/null \
    | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -n1)"
  if [[ -n "$exec_path" && -e "$exec_path" ]]; then
    printf '%s\n' "$(sha256sum "$exec_path" 2>/dev/null || printf '(unhashable) %s' "$exec_path")"
    stat -c '%A %U:%G %n' "$exec_path" 2>/dev/null || true
  else
    printf '(ExecStart binary not resolved)\n'
  fi
  for candidate in /opt/hydra-direct /usr/local/bin/hydra-direct /etc/hydra-direct \
    /opt/hydra/hydra-direct; do
    [[ -e "$candidate" ]] || continue
    printf '\n%s:\n' "$candidate"
    find "$candidate" -maxdepth 2 -type f -exec sha256sum {} + 2>/dev/null | head -n 40
    find "$candidate" -maxdepth 2 \( -perm -o+w -o -perm -u+s \) -printf 'PERMISSION RISK: %M %p\n' 2>/dev/null
  done
  printf '```\n\n'

  printf '## Running processes\n\n```\n'
  pgrep -af 'hydra-direct' 2>/dev/null || printf '(no matching process)\n'
  printf '```\n\n'

  printf '## Listening ports\n\n```\n'
  ss -tulpn 2>/dev/null | grep -E "(:$PORT|hydra-direct)" || printf '(no listener on %s)\n' "$PORT"
  printf '```\n\n'

  printf '## Outbound connections\n\n```\n'
  ss -tnp state established 2>/dev/null | grep -i 'hydra-direct' || printf '(none attributable)\n'
  printf '```\n\n'

  printf '## Tailscale exposure\n\n```\n'
  tailscale serve status 2>/dev/null || printf '(tailscale serve status unavailable)\n'
  printf '```\n\n'

  printf '## Privilege surface\n\n'
  if [[ -n "$exec_path" ]]; then
    runs_as="$(systemctl show "$UNIT" -p User --value 2>/dev/null)"
    note "service user: ${runs_as:-root (User= unset)}"
    [[ -z "$runs_as" || "$runs_as" == "root" ]] && gap "service runs as root" || true
  fi
  grep -rl 'hydra-direct' /etc/sudoers /etc/sudoers.d 2>/dev/null \
    && gap "hydra-direct appears in sudoers" || note "no sudoers entry references hydra-direct"

  printf '\n## Update and uninstall\n\n'
  gap "update mechanism undocumented; the installer is re-run manually from an unpinned URL"
  note "uninstall: sudo systemctl disable --now $UNIT; sudo rm -f /etc/systemd/system/$UNIT.service; sudo systemctl daemon-reload"
  note "close exposure: tailscale serve --https=$PORT off"

  printf '\n## Verdict\n\n'
  if (( findings == 0 )); then
    printf 'PROVENANCE VERIFIED: %d unverified items.\n' "$findings"
  else
    printf 'PROVENANCE NOT ESTABLISHED: %d unverified item(s).\n' "$findings"
    printf 'Per OSA Decision 2, hydra-direct stays outside the Hermes trust boundary.\n'
  fi
} >"$report"

(( findings == 0 )) && provenance_verified=1 || provenance_verified=0

# Quarantine, only when asked and only when provenance is unproven.
if (( enforce == 1 && provenance_verified == 0 )); then
  {
    printf '\n## Quarantine applied\n\n'
    if systemctl is-active --quiet "$UNIT" 2>/dev/null; then
      if sudo -n systemctl disable --now "$UNIT" 2>/dev/null; then
        printf -- '- stopped and disabled %s\n' "$UNIT"
        printf -- '- rollback: sudo systemctl enable --now %s\n' "$UNIT"
      else
        printf -- '- [ ] could not disable %s (needs sudo); still ACTIVE\n' "$UNIT"
      fi
    else
      printf -- '- %s was already inactive\n' "$UNIT"
    fi
    if tailscale serve --https="$PORT" off 2>/dev/null; then
      printf -- '- closed tailnet exposure on %s\n' "$PORT"
      printf -- '- rollback: re-run the installer or re-add the serve rule\n'
    else
      printf -- '- [ ] could not close tailnet exposure on %s\n' "$PORT"
    fi
    printf -- '- files were NOT deleted, per OSA Decision 2\n'
  } >>"$report"
fi

ln -sfn "$report" "$OUT_DIR/hydra-direct-latest.md"
printf 'HYDRA-DIRECT AUDIT: provenance_verified=%d unverified_items=%d report=%s\n' \
  "$provenance_verified" "$findings" "$report"
(( provenance_verified == 1 ))

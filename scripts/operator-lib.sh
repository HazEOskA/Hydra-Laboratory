# shellcheck shell=bash
# Shared guards for the operator bundle. Sourced, never executed directly.
#
# Every operator script runs on exactly one host as exactly one user, writes
# timestamped evidence, and redacts credential material on the way out. Nothing
# here mutates the host.

REQUIRED_HOST="hydra-hermes-runtime-01"
REQUIRED_USER="hydra"
EVIDENCE_ROOT="${HYDRA_EVIDENCE_ROOT:-/var/lib/hydra-hermes/evidence}"

# Confirmed sandbox and route. These are assertions to verify, never values to
# write: no script in this bundle changes provider, model or credentials.
SANDBOX="${NEMOCLAW_SANDBOX_NAME:-hydra-hermes-lab}"
EXPECTED_PROVIDER="nvidia-prod"
EXPECTED_MODEL="nvidia/nemotron-3-super-120b-a12b"

# Canonical repository candidates, in preference order. /home/hydra/hydra-hermes-lab
# is deliberately absent: OSA states it must not be assumed.
REPO_CANDIDATES=(
  "/opt/hydra/apps/hydra-hermes-lab"
  "/home/hydra/hermes-godlayer"
)

utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }
stamp() { date -u +%Y%m%dT%H%M%SZ; }

log()  { printf '%s %s\n' "$(utc)" "$*"; }
ok()   { printf '  PASS    %-26s %s\n' "$1" "${2:-}"; }
bad()  { printf '  FAIL    %-26s %s\n' "$1" "${2:-}"; }
unk()  { printf '  UNKNOWN %-26s %s\n' "$1" "${2:-}"; }
na()   { printf '  N/A     %-26s %s\n' "$1" "${2:-}"; }
die()  { printf '%s FATAL %s\n' "$(utc)" "$*" >&2; exit 1; }

# --- redaction -------------------------------------------------------------
# Applied to every captured stream. Values never reach evidence files: only the
# fact that a name was present.
redact() {
  sed -E \
    -e 's/(NVIDIA_INFERENCE_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|[A-Z_]*(API_KEY|TOKEN|SECRET|PASSWORD)[A-Z_]*)[[:space:]]*[=:][[:space:]]*[^[:space:]"]*/\1=<REDACTED>/g' \
    -e 's/(Authorization:[[:space:]]*)(Bearer[[:space:]]+)?[A-Za-z0-9._~+\/-]+=*/\1<REDACTED>/gI' \
    -e 's/\b(sk|ghp|gho|github_pat|xox[abps])[-_][A-Za-z0-9_-]{10,}\b/<REDACTED_TOKEN>/g' \
    -e 's/(-----BEGIN[A-Z ]*PRIVATE KEY-----).*/\1<REDACTED>/g'
}

# Run a command, capture stdout+stderr redacted into the evidence dir. A missing
# command is recorded as such rather than aborting the audit; a command that
# exists but fails records its exit code. Neither is masked.
capture() {
  local file="$1"; shift
  local dest="$RUN_DIR/$file"
  {
    printf '### %s :: %s\n' "$(utc)" "$*"
    if ! command -v "${1%% *}" >/dev/null 2>&1 && [[ "$1" != */* ]]; then
      printf '(command not found: %s)\n' "$1"
    else
      local rc=0
      "$@" 2>&1 | redact || rc=$?
      printf '(exit=%s)\n' "${rc:-0}"
    fi
    printf '\n'
  } >>"$dest"
}

require_host() {
  local h; h="$(hostname -s 2>/dev/null || echo unknown)"
  [[ "$h" == "$REQUIRED_HOST" ]] \
    || die "host gate: this bundle runs only on $REQUIRED_HOST (this host is '$h')"
  local u; u="$(id -un)"
  [[ "$u" == "$REQUIRED_USER" ]] \
    || die "user gate: this bundle runs only as $REQUIRED_USER (current user is '$u')"
}

# Pick an evidence root this user can actually write to.
#
# /var/lib/hydra-hermes belongs to root, but the bundle runs as hydra, so the
# old default aborted the whole run on a permission error. The state directory
# is still preferred when it is writable — the systemd units use it — and the
# operator's home is the fallback, which is where earlier runs already wrote.
resolve_evidence_root() {
  local candidates=() dir
  [[ -n "${HYDRA_EVIDENCE_ROOT:-}" ]] && candidates+=("$HYDRA_EVIDENCE_ROOT")
  candidates+=("/var/lib/hydra-hermes/evidence" "$HOME/hydra-operator-evidence")
  for dir in "${candidates[@]}"; do
    if mkdir -p "$dir" 2>/dev/null && [[ -w "$dir" ]]; then
      printf '%s\n' "$dir"
      return 0
    fi
  done
  return 1
}

new_run_dir() {
  local kind="$1" root
  root="$(resolve_evidence_root)" \
    || die "no writable evidence root (tried \$HYDRA_EVIDENCE_ROOT, /var/lib/hydra-hermes/evidence, \$HOME/hydra-operator-evidence)"
  EVIDENCE_ROOT="$root"
  RUN_DIR="$root/${kind}-$(stamp)"
  mkdir -p "$RUN_DIR" || die "cannot create evidence directory $RUN_DIR"
  chmod 700 "$RUN_DIR"
  printf '%s\n' "$RUN_DIR"
}

# Resolve the NemoClaw configuration directory deterministically.
#
# $HOME is not trustworthy here: under systemd, sudo or a login shell it can
# differ, and a miss silently degrades to "broker is not running". The gateway
# refuses a config directory it considers unsafe, so this also rejects a
# group/world-writable directory rather than handing the gateway a path it will
# reject with GATEWAY_UNSAFE_CONFIG_PATH.
#
# Prints the path on success; prints nothing and returns non-zero otherwise.
nemoclaw_config_dir() {
  local candidates=()
  if [[ -n "${NEMOCLAW_CONFIG_CANDIDATES:-}" ]]; then
    # Explicit probe order. Set by the regression tests so the outcome does not
    # depend on whether /home/hydra/.nemoclaw happens to exist on the machine
    # running them.
    read -r -a candidates <<<"$NEMOCLAW_CONFIG_CANDIDATES"
  else
    [[ -n "${NEMOCLAW_HOME:-}" ]] && candidates+=("$NEMOCLAW_HOME")
    candidates+=("/home/$REQUIRED_USER/.nemoclaw")
    [[ -n "${HOME:-}" ]] && candidates+=("$HOME/.nemoclaw")
  fi

  local dir perms
  for dir in "${candidates[@]}"; do
    [[ -d "$dir" ]] || continue
    # Octal mode; the gateway treats group- or world-writable config as unsafe.
    perms="$(stat -c '%a' "$dir" 2>/dev/null || echo 777)"
    if (( 8#$perms & 8#022 )); then
      printf 'nemoclaw config dir %s is group/world-writable (mode %s)\n' "$dir" "$perms" >&2
      return 2
    fi
    printf '%s\n' "$dir"
    return 0
  done
  printf 'no nemoclaw config directory found (tried: %s)\n' "${candidates[*]}" >&2
  return 1
}

# Classify the in-sandbox credential probe. Fail-closed by construction.
#
# The probe's stdout must be exactly ABSENT or PRESENT. Anything else — a
# gateway refusal such as GATEWAY_UNSAFE_CONFIG_PATH, an empty reply, a stopped
# sandbox — is UNKNOWN, never "safe". Matching is whole-string, so error text
# that happens to contain the word ABSENT can never be read as the safe branch.
classify_key_probe() {
  local raw="${1-}"
  # Trim whitespace and any trailing newline; keep the value otherwise intact.
  raw="$(printf '%s' "$raw" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  case "$raw" in
    ABSENT)  printf 'ABSENT\n' ;;
    PRESENT) printf 'PRESENT\n' ;;
    *)       printf 'UNKNOWN\n' ;;
  esac
}

# Resolve the sandbox's container id without assuming a naming scheme.
#
# More than one container can carry the sandbox name — an orphan alongside the
# live openshell-<sandbox>-<uuid> one. Taking the first match silently targeted
# whichever docker listed first. A live container (running or restarting) now
# wins, and an ambiguous set is reported on stderr instead of being guessed at.
sandbox_container_id() {
  local rows live
  # The OpenShell label is authoritative — it is what the vendor tooling itself
  # looks for. Name matching is only a fallback, and it can pick an unrelated
  # container that merely has the sandbox name in it.
  rows="$(docker ps -a --no-trunc --filter "label=openshell.ai/sandbox-name=$SANDBOX" \
          --format '{{.ID}} {{.State}} {{.Names}}' 2>/dev/null || true)"
  [[ -n "$rows" ]] || rows="$(docker ps -a --no-trunc --format '{{.ID}} {{.State}} {{.Names}}' 2>/dev/null \
          | grep -F "$SANDBOX" || true)"
  [[ -n "$rows" ]] || return 1

  if [[ "$(wc -l <<<"$rows")" -gt 1 ]]; then
    printf 'multiple containers match sandbox %s:\n%s\n' "$SANDBOX" "$rows" >&2
  fi
  live="$(awk '$2=="running" || $2=="restarting" {print $1; exit}' <<<"$rows")"
  [[ -n "$live" ]] && { printf '%s\n' "$live"; return 0; }
  awk 'NR==1{print $1}' <<<"$rows"
}

# Report a change without performing it unless --execute was given.
# Usage: act "<description>" cmd args...
# ACT_RC holds the exit code of the last executed action so callers can branch
# on it. A failed action is reported with its code and does not abort the run:
# under `set -e` a non-zero `nemohermes start` previously killed the script
# before it reached its AFTER section, so the operator got no verdict at all.
# This is not error masking — the code is printed and available to the caller.
ACT_RC=0
act() {
  local desc="$1"; shift
  printf '  ACTION  %s\n' "$desc"
  ACT_RC=0
  if [[ "${EXECUTE:-0}" -eq 1 ]]; then
    "$@" || ACT_RC=$?
    (( ACT_RC != 0 )) && printf '          (exit=%s) action failed; run continues to its verdict\n' "$ACT_RC"
    return 0
  fi
  printf '          (dry-run: not executed) %s\n' "$*"
}

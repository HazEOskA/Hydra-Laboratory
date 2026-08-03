#!/usr/bin/env bash
# Regression tests for the secret boundary and the nemoclaw config path.
#
# The invariant under test: the credential probe fails closed. Only an exact
# ABSENT means the boundary held. A gateway refusal — GATEWAY_UNSAFE_CONFIG_PATH
# among them — must never be classified as safe, not even when its text contains
# the word ABSENT.
set -Eeuo pipefail
umask 077

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/operator-lib.sh
source "$REPO_ROOT/scripts/operator-lib.sh"

pass=0; fail=0
check() {
  local name="$1" want="$2" got="$3"
  if [[ "$want" == "$got" ]]; then
    printf 'PASS  %-58s %s\n' "$name" "$got"; pass=$((pass + 1))
  else
    printf 'FAIL  %-58s want=%s got=%s\n' "$name" "$want" "$got" >&2; fail=$((fail + 1))
  fi
}

echo "-- classify_key_probe: the safe branch is exact-match only --"
check "exact ABSENT is safe"                 ABSENT  "$(classify_key_probe 'ABSENT')"
check "ABSENT with trailing newline"         ABSENT  "$(classify_key_probe 'ABSENT
')"
check "ABSENT with CR and spaces"            ABSENT  "$(classify_key_probe '  ABSENT
')"
check "exact PRESENT is a breach"            PRESENT "$(classify_key_probe 'PRESENT')"

echo
echo "-- the regression: refusal text must never read as safe --"
check "GATEWAY_UNSAFE_CONFIG_PATH" UNKNOWN \
  "$(classify_key_probe 'GATEWAY_UNSAFE_CONFIG_PATH: secret-boundary check did not complete cleanly')"
# The exact fail-open shape the old substring match allowed through.
check "refusal containing the word ABSENT" UNKNOWN \
  "$(classify_key_probe 'GATEWAY_UNSAFE_CONFIG_PATH: variable ABSENT from allowlist')"
check "refusal containing the word PRESENT" UNKNOWN \
  "$(classify_key_probe 'error: config PRESENT but unreadable')"
check "both words present"                  UNKNOWN \
  "$(classify_key_probe 'ABSENT or PRESENT could not be determined')"
check "empty reply (sandbox stopped)"       UNKNOWN "$(classify_key_probe '')"
check "whitespace only"                     UNKNOWN "$(classify_key_probe '   ')"
check "legacy UNREADABLE sentinel"          UNKNOWN "$(classify_key_probe 'UNREADABLE')"
check "lowercase is not the safe branch"    UNKNOWN "$(classify_key_probe 'absent')"
check "multi-line with ABSENT on line 2"    UNKNOWN "$(classify_key_probe 'warning: gateway
ABSENT')"

echo
echo "-- nemoclaw_config_dir: correct and incorrect paths --"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

safe="$TMP/safe/.nemoclaw"
mkdir -p "$safe" && chmod 700 "$safe"
got="$(NEMOCLAW_HOME="$safe" nemoclaw_config_dir 2>/dev/null || echo RESOLVE_FAILED)"
check "0700 directory resolves"              "$safe" "$got"

mkdir -p "$TMP/g/.nemoclaw" && chmod 770 "$TMP/g/.nemoclaw"
got="$(NEMOCLAW_HOME="$TMP/g/.nemoclaw" nemoclaw_config_dir 2>/dev/null || echo REFUSED)"
check "group-writable is refused"            REFUSED "$got"

mkdir -p "$TMP/w/.nemoclaw" && chmod 707 "$TMP/w/.nemoclaw"
got="$(NEMOCLAW_HOME="$TMP/w/.nemoclaw" nemoclaw_config_dir 2>/dev/null || echo REFUSED)"
check "world-writable is refused"            REFUSED "$got"

# Every path case below pins the probe order explicitly. Without that the
# outcome depends on whether /home/hydra/.nemoclaw exists on the machine running
# the tests — which made this suite pass in a container and fail on the runtime
# host for no real defect.
got="$(NEMOCLAW_CONFIG_CANDIDATES="$TMP/does-not-exist $TMP/also-missing" \
       nemoclaw_config_dir 2>/dev/null || echo REFUSED)"
check "no candidate exists is refused"       REFUSED "$got"

# Ordering: the canonical operator path must win over $HOME when both exist. A
# wrong $HOME under systemd or sudo previously produced a silent miss.
canon="$TMP/canonical/.nemoclaw"; mkdir -p "$canon" && chmod 700 "$canon"
decoy="$TMP/decoy/.nemoclaw";     mkdir -p "$decoy" && chmod 700 "$decoy"
got="$(NEMOCLAW_CONFIG_CANDIDATES="$canon $decoy" nemoclaw_config_dir 2>/dev/null || echo REFUSED)"
check "canonical path wins over \$HOME"      "$canon" "$got"

# Falling through: an absent earlier candidate must not stop the search.
got="$(NEMOCLAW_CONFIG_CANDIDATES="$TMP/missing $canon" nemoclaw_config_dir 2>/dev/null || echo REFUSED)"
check "absent candidate falls through"       "$canon" "$got"

# An unsafe candidate is refused outright rather than skipped: silently moving on
# would hand the gateway a directory it has already rejected.
got="$(NEMOCLAW_CONFIG_CANDIDATES="$TMP/g/.nemoclaw $canon" nemoclaw_config_dir 2>/dev/null || echo REFUSED)"
check "unsafe candidate refuses, not skips"  REFUSED "$got"

# The default probe order is still the operator one when nothing is injected.
got="$(NEMOCLAW_CONFIG_CANDIDATES= NEMOCLAW_HOME="$canon" nemoclaw_config_dir 2>/dev/null || echo REFUSED)"
check "NEMOCLAW_HOME honoured by default"    "$canon" "$got"

echo
echo "-- the boundary is not weakened: no path writes the key into the sandbox --"
if grep -rn 'NVIDIA_INFERENCE_API_KEY' "$REPO_ROOT/scripts" \
     | grep -vE '\-z \$\{NVIDIA_INFERENCE_API_KEY|#|ABSENT|PRESENT|REDACTED' \
     | grep -qE 'export|--env|-e +NVIDIA_INFERENCE_API_KEY|ENV'; then
  printf 'FAIL  %-58s\n' "a script exports the provider key toward the sandbox" >&2
  fail=$((fail + 1))
else
  printf 'PASS  %-58s\n' "no script exports the provider key toward the sandbox"
  pass=$((pass + 1))
fi

printf '\nsecret-boundary tests: pass=%d fail=%d\n' "$pass" "$fail"
[[ $fail -eq 0 ]]

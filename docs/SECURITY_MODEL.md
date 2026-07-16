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

Use a dedicated single-user host. Docker group membership carries root-equivalent impact. Restrict SSH, patch the host, bind management ports to loopback, and use operator-controlled tunneling.

## Sandbox Proof

Validation must prove that `NVIDIA_INFERENCE_API_KEY` is unset inside `hydra-hermes-lab`. It must also prove that the active route is `routed`/`nvidia-router` and that inference flows through `https://inference.local/v1`.

## Evidence Handling

Commit versions, timestamps, exit classifications, redacted routes, and PASS/WARN/BLOCK results. Do not commit full sessions, raw environment dumps, provider payloads, or unrestricted diagnostic archives.

## Supply Chain

The install script uses NVIDIA's documented hosted installer URL. It downloads to a private temporary file and executes only after an explicit `--execute` gate. The installed last-known-good release must be recorded in sanitized evidence.

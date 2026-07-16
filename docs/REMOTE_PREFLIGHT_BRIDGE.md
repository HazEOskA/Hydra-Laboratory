# Approved Remote Preflight Bridge

## Purpose

The manually dispatched GitHub Actions workflow `.github/workflows/remote-preflight.yml` is the only repository-defined remote bridge. It streams `scripts/remote-preflight.sh` to `hydra-hermes-runtime-01` and executes the `--github-report` read-only mode. It never installs software, changes services or firewall rules, starts onboarding, creates a sandbox, or writes to the remote repository.

## GitHub Environment

Create a GitHub Environment named `hydra-runtime` in repository settings. Configure:

1. Required reviewers and manual deployment approval. Enable prevention of self-review where the repository plan supports it.
2. Deployment branches restricted to `main`.
3. Environment secrets:
   - `HYDRA_SSH_HOST`
   - `HYDRA_SSH_USER` — must resolve to `hydra`
   - `HYDRA_SSH_PRIVATE_KEY`
   - `HYDRA_SSH_KNOWN_HOSTS`
4. Optional environment variable `HYDRA_SSH_PORT`; omit it to use port `22`.

Do not configure these values as repository variables, workflow inputs, command arguments, artifacts, or committed files.

## Dedicated SSH Identity

The private key must belong only to this Hydra runtime bridge. It must not be a personal key and must not be reused by another host, repository, CI workflow, or project. Store it only as the protected `hydra-runtime` environment secret. Install only its public half for the `hydra` account on the target host.

The private key must be non-interactive for the approved automation flow. GitHub Environment protection and required review are the human approval gate before the key becomes available to a job.

## Host-Key Trust

Verify the server host-key fingerprint outside the workflow using the authenticated Hetzner control plane and a separately trusted channel. Store the reviewed OpenSSH `known_hosts` record in `HYDRA_SSH_KNOWN_HOSTS`.

The workflow uses `StrictHostKeyChecking=yes` and never calls `ssh-keyscan`. A missing, changed, or mismatched host key blocks execution.

## Firewall Boundary

Do not open SSH to `0.0.0.0/0` or `::/0`. A standard GitHub-hosted runner does not provide one permanent egress address. Before dispatch, the Hetzner firewall must admit port 22 only from a separately reviewed runner source. If a controlled source cannot be established, do not run the workflow; use a dedicated fixed-egress runner design first.

Ports 4000, 8642, and 18789 remain non-public under all circumstances.

## Manual Execution

Open the repository Actions page, select **remote preflight**, choose **Run workflow** on `main`, then approve the `hydra-runtime` environment deployment. Do not run it until all four secrets, the reviewed host key, the firewall source, and required reviewer are configured.

The workflow publishes only a redacted job summary and a seven-day sanitized report artifact. SSH errors, IP addresses, private keys, host-key contents, and credential paths are not included.

## Read-Only Contract

The report mode reads only host identity and capacity, UFW state, Docker health, the `hydra` identity, the expected repository checkout, CLI presence, and listener state for ports 4000, 8642, and 18789. It does not use `sudo`. Any prerequisite requiring elevation or mutation is reported as `BLOCKED`.

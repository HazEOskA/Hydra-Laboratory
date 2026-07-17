# Approved Remote Preflight Bridge

## Purpose

The manually dispatched GitHub Actions workflow `.github/workflows/remote-preflight.yml` is the only repository-defined remote bridge. It uses a GitHub-hosted ephemeral runner, joins the private tailnet with OIDC, then streams `scripts/remote-preflight.sh` to the already-enrolled persistent node `hydra-hermes-runtime-01` over strict OpenSSH. The `--github-report` mode never installs software, changes Tailscale, services or firewall rules, starts onboarding, creates a sandbox, or writes to the remote repository.

## Private-Repository Compatibility

The repository is private. GitHub Environment secrets in private repositories require GitHub Pro, GitHub Team, or GitHub Enterprise. Required reviewers for private environments are not available on the ordinary Free, Pro, or Team feature tiers. Because the available account metadata does not prove an eligible paid environment tier, this workflow uses repository secrets and does not declare the `hydra-runtime` Environment or an active required-reviewer gate.

Manual `workflow_dispatch` is the operator gate. The job additionally refuses execution unless the selected ref is `main`.

## Repository Secrets

Configure these under **Settings → Secrets and variables → Actions → Secrets**:

- `HYDRA_SSH_HOST`
- `HYDRA_SSH_USER` — must resolve to `hydra`
- `HYDRA_SSH_PRIVATE_KEY`
- `HYDRA_SSH_KNOWN_HOSTS`
- `TS_OAUTH_CLIENT_ID`

Do not configure them as workflow inputs, command arguments, artifacts, or committed files. Do not place a Tailscale OAuth client secret or reusable auth key in this workflow.

## Repository Variables

Configure non-secret values under **Settings → Secrets and variables → Actions → Variables**:

- `HYDRA_SSH_PORT` — optional; defaults to `22`
- `TS_AUDIENCE`
- `TS_TAGS` — the tag or comma-separated tags authorized by the federated Tailscale identity

Values are intentionally not supplied by this repository.

## Tailscale Workload Identity

Configure a Tailscale workload identity federation credential restricted to this GitHub repository, the intended workflow/ref claims, and the required `auth_keys` capability. Its permitted tags must exactly cover `TS_TAGS`. The workflow grants only `id-token: write` in addition to read-only repository contents.

The official Tailscale action is pinned to the reviewed v4.1.3 commit. It creates an ephemeral tailnet node and removes it after the job. Public SSH is not part of this transport.

The ephemeral runner identity is distinct from the server bootstrap identity. `TS_RUNTIME_AUTH_KEY` must never be added to GitHub Actions secrets or used by this workflow. The server is enrolled once as a persistent, non-ephemeral node tagged exactly `tag:hydra-runtime`; the runner continues to use OIDC. Tailscale SSH remains disabled on the server.

## Dedicated SSH Identity

The private key must belong only to this Hydra runtime bridge. It must not be a personal key and must not be reused by another host, repository, workflow, or project. Store it only as the repository secret. Install only its public half for the `hydra` account on the target host.

The key must be non-interactive for the approved automation flow. It exists on the ephemeral runner only in a mode-`600` temporary file and is deleted before artifact upload.

## Host-Key Trust

Verify the server host-key fingerprint outside the workflow using the authenticated Hetzner control plane and a separately trusted channel. Store the reviewed OpenSSH record in `HYDRA_SSH_KNOWN_HOSTS`.

The workflow uses `StrictHostKeyChecking=yes` and never calls `ssh-keyscan`. A missing, changed, or mismatched host key blocks execution.

## Firewall Boundary

Public SSH must remain closed. The Hetzner firewall must not expose TCP/22, 4000, 8642, or 18789. Host UFW accepts TCP/22 only on `tailscale0`. The runner reaches hardened OpenSSH through the private Tailscale interface; tailnet ACLs or grants must restrict access to the Hydra host and port 22. Tailscale SSH is not used.

The workflow cannot install Tailscale on the host, enroll it, modify provider firewall, or change tailnet policy. If `scripts/validate-tailscale-host.sh` and independent admin-console visibility have not established the persistent server path, do not configure bridge secrets and do not dispatch the workflow.

## Manual Execution

Open the repository Actions page, select **remote preflight**, select `main`, and choose **Run workflow**. Do not run it until all repository secrets, variables, the federated identity, the reviewed host key, and the private tailnet policy are configured.

The workflow publishes only a redacted job summary and a seven-day sanitized report artifact. SSH errors, IP addresses, private keys, host-key contents, and credential paths are not included.

## Read-Only Contract

The report mode reads only host identity and capacity, UFW state, Docker health, the `hydra` identity, the expected repository checkout, CLI presence, and listener state for ports 4000, 8642, and 18789. It does not use `sudo`. Any prerequisite requiring elevation or mutation is reported as `BLOCKED`.

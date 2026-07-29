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
- Treat `TS_RUNTIME_AUTH_KEY` and every rendered cloud-init copy as bootstrap secrets. The key must be one-off, non-reusable, non-ephemeral, short-lived, tagged exactly `tag:hydra-runtime`, and pre-approved when device approval is active.
- Pass the Tailscale key to `tailscale up` only through a mode-`0600` temporary file and `--auth-key=file:…`; delete it immediately after enrollment. Never expose its value in argv, tracing, logs, artifacts, evidence, or the repository.
- Run `scripts/secret-scan.sh` before every commit.
- A line may carry the `secret-scan: synthetic fixture` marker only when it holds invented credential-shaped text needed to prove redaction, as in `tests/test-worker-loop.sh`. Every exemption stays greppable and must be reviewed like any other change.

## Host Model

Use the dedicated Hetzner single-user host and `hydra` account. Docker group membership carries root-equivalent impact. Cloud-init enables unattended security upgrades, UFW, fail2ban, bounded Docker logs, and key-only SSH. Root/password/keyboard-interactive SSH and agent/X11/remote forwarding are disabled; local forwarding is retained only for loopback management access. Tailscale SSH is explicitly disabled.

The lockout-prevention invariant is fail-closed for provisioning but fail-open for console recovery: restrictive UFW activation is unreachable until `tailscaled` is enabled and active, `tailscale0` exists, a Tailscale address is assigned, and the control-plane status proves the expected online hostname and sole tag. A Tailscale failure terminates cloud-init without adding public SSH or enabling the restrictive UFW rules. Hetzner Console remains the recovery channel.

## Network Controls

- The Hetzner stateful firewall has no public inbound TCP/22 rule; workflow SSH travels through Tailscale.
- UFW allows TCP/22 only on `tailscale0`. There is no generic `ufw allow 22` or `ufw allow ssh` rule.
- ICMP/ICMPv6 remains allowed for network operation and diagnostics.
- No provider outbound rules means outbound traffic follows Hetzner's default allow behavior; OpenShell `balanced` policy separately constrains sandbox traffic.
- Ports 4000, 8642, and 18789 must bind only to `127.0.0.1` or `::1`; UFW is defense in depth, not a substitute for correct Docker port binding.

## Host Provisioning Secrets

Only a public SSH key may be selected during provisioning. Hetzner API tokens, SSH private keys, account passwords, `NVIDIA_INFERENCE_API_KEY`, `TS_RUNTIME_AUTH_KEY`, rendered user data, and generated server state are excluded from Git and chat. Provider firewall and Tailscale policy are configured outside the repository without committing private network data.

`infra/cloud-init.yaml` is a secret-free template. `scripts/render-cloud-init.sh` accepts the production auth key only from its process environment, requires an absolute output path outside the Git tree, refuses overwrite, and writes mode `0600`. The rendered copy is submitted through the authenticated Hetzner control plane and deleted immediately afterward. The template decodes the credential into `/run`, passes only its file path to Tailscale, removes temporary credential files, and redacts the encoded payload from the host's cached cloud-init user-data/config copies on success or failure. Provider-side user-data handling remains inside the authenticated Hetzner trust boundary, which is why the key must also be one-off and short-lived.

## GitHub Actions SSH Bridge

The private repository stores a dedicated, non-reused Hydra SSH identity and reviewed `known_hosts` record as repository secrets. Tailscale uses GitHub workload identity federation with `id-token: write`, a federated client ID, repository-configured audience, and no reusable OAuth client secret. The workflow uses the system SSH client with strict host-key checking, batch-only public-key authentication, no agent, and no forwarding. Ephemeral key material is mode `600` and is removed under `always()`.

The GitHub-hosted runner is ephemeral and reaches the host only through the private tailnet. Public SSH remains closed; ports 22, 4000, 8642, and 18789 must not receive public Hetzner firewall rules. The bridge cannot change either the Hetzner firewall or tailnet policy.

Repository secrets are used because they work for private repositories across current non-legacy GitHub plans. GitHub Environment secrets for private repositories require Pro, Team, or Enterprise. Required reviewers for private-repository environments must not be represented as active without a plan that actually supplies that protection; this baseline makes no such claim.

## Continuous Duty Cycle

`scripts/hermes-worker.sh` prompts Hermes through `nemohermes … exec` and never receives `NVIDIA_INFERENCE_API_KEY`. Captured output is redacted before it reaches disk, and only a SHA-256 digest plus a 240-character redacted excerpt is journaled; full model output is never stored. The loop runs as `hydra` under a hardened systemd unit whose only writable path is `/var/lib/hydra-hermes`. Spending is bounded by a daily prompt cap, a minimum interval, per-task cadence, and per-prompt timeouts; an operator `STOP` file and a sticky circuit breaker stop it without uninstalling anything. Simulation mode is test-only: it requires an explicit stub command, never calls the sandbox, and stamps every record it writes, so simulated runs cannot be presented as runtime evidence.

## Sandbox Proof

Validation must prove that `NVIDIA_INFERENCE_API_KEY` is unset inside `hydra-hermes-lab`. It must also prove that the active route is `routed`/`nvidia-router` and that inference flows through `https://inference.local/v1`.

## Evidence Handling

Commit versions, timestamps, exit classifications, redacted routes, and PASS/WARN/BLOCK results. Do not commit full sessions, raw environment dumps, provider payloads, or unrestricted diagnostic archives.

Before a destructive runtime change, take both a NemoClaw sandbox snapshot and, when appropriate, a Hetzner server snapshot. Hetzner server snapshots contain the server disk and can contain secrets; keep them private in the operator account. Attached volumes, if ever added, require separate backup treatment.

## Supply Chain

The install script uses NVIDIA's documented hosted installer URL. It downloads to a private temporary file and executes only after an explicit `--execute` gate. The installed last-known-good release must be recorded in sanitized evidence.

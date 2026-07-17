# Architecture Lock v0.1

Status: LOCKED for baseline evaluation.

## Tools

- GitHub: source of truth and change history
- GitHub Actions: static checks only
- Hetzner Cloud CX43 (`hydra-hermes-runtime-01`): persistent Ubuntu 24.04 runtime target
- Docker: supported container runtime
- NVIDIA NemoClaw / `nemohermes`: Hermes lifecycle CLI
- NVIDIA OpenShell: sandbox, policy, credential, and inference boundary
- NVIDIA Model Router: host-side routed inference on port 4000
- Bash: repeatable host automation

## Architecture

```text
GitHub
  -> Tailscale private management plane
  -> Hetzner CX43 / Ubuntu 24.04 / x86_64
  -> NemoClaw Host CLI
  -> OpenShell
     + host-side credentials
     + balanced network policy
     + NVIDIA Model Router :4000
       -> NVIDIA hosted models
  -> Hermes sandbox: hydra-hermes-lab
     -> inference.local
     -> Hermes runtime and tools
```

The host is exactly 8 shared vCPU, 16 GB RAM and 160 GB disk in `nbg1` (fallback `fsn1`), with public IPv4 and IPv6 and no GPU requirement. The sandbox never calls port 4000 directly. OpenShell maps the sandbox's managed `inference.local` route to the host-side Model Router. The raw NVIDIA key never enters the sandbox.

## Repository Structure

- `config/`: non-secret examples only
- `docs/`: architecture, security, validation, decisions, evidence, and rollback
- `infra/`: locked Hetzner target, cloud-init, provider-firewall controls, and requirements
- `scripts/`: preflight, install, onboard, validation, scan, and guarded destroy
- `.github/workflows/`: static validation, never persistent runtime hosting

## Execution Flow

1. Validate repository statically.
2. Render cloud-init outside Git with a one-off, non-ephemeral, tagged `TS_RUNTIME_AUTH_KEY` supplied by an approved secret flow.
3. Provision the reviewed Hetzner CX43 with the Hydra public SSH key and provider firewall. Cloud-init must enroll and validate the persistent Tailscale host before enabling UFW; delete the rendered file after submission.
4. Run remote preflight without mutation through hardened OpenSSH on `tailscale0`.
5. Review exact write paths and elevation needs.
6. Inject `NVIDIA_INFERENCE_API_KEY` through the host environment or approved secret store.
7. Run the explicitly gated installer/onboard script.
8. Validate status, doctor, route, credential boundary, dashboard, and a real first prompt.
9. Record only sanitized evidence.

## Validation Flow

Static CI proves script syntax, required documentation, YAML parseability, Tailscale-before-UFW ordering, pinned workflow transport, and absence of obvious secrets. Host bootstrap validation proves the persistent online Tailscale identity before UFW. Runtime validation proves Docker/OpenShell/NemoClaw health, registered Hermes identity, `routed` provider, `inference.local`, real inference, dashboard reachability, and absence of the raw NVIDIA key inside the sandbox.

## Deployment / Runtime Flow

There is no web deployment. The remote host runs one sandbox named `hydra-hermes-lab`. The provider firewall exposes no SSH rule; UFW accepts SSH only on `tailscale0`, and automation reaches hardened OpenSSH through Tailscale. Tailscale SSH is disabled. Model Router 4000, API 8642, and dashboard 18789 remain loopback-bound and are accessed only through an operator-controlled private tunnel where applicable.

## Rollback / Safety Plan

- Stop before destroy and inspect status/logs.
- Snapshot before rebuild or removal.
- Preserve `~/.nemoclaw/` registry and backups unless a later destructive approval explicitly includes them.
- `destroy-sandbox.sh` accepts only the locked sandbox name and requires a second exact confirmation value.
- NemoClaw uninstall is documentation-only until separately approved.
- No operation may target or inspect Agent Proof Runtime.

## Baseline Exclusions

No web search, messaging, MCP servers, custom Hermes plugins, custom router pool, public dashboard exposure, or Hydra multi-agent orchestration.

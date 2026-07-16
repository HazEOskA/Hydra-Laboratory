# Decisions

## D-001: Hermes First

Hermes is the first evaluated Hydra agent. Status: accepted.

## D-002: NVIDIA Model Router

The initial inference provider is NVIDIA Model Router using onboarding selector `routed`. Status: accepted.

## D-003: Isolation

`hydra-hermes-lab` is independent from Agent Proof Runtime. APR remains frozen and out of scope. Status: accepted.

## D-004: Host-Side Credentials

Credentials remain in the remote host/OpenShell boundary and never enter the sandbox or Git. Status: accepted.

## D-005: Deferred Integrations

Messaging, web search, MCP servers, and custom Hermes plugins are deferred until baseline validation. Status: accepted.

## D-006: Default Router Pool First

No live router-pool modification is allowed before default routed-pool validation is green. Status: accepted.

## D-007: GitHub-First Control Plane

GitHub is the source of truth. The persistent runtime is a separate remote Ubuntu host; neither GitHub Actions nor the cloud coding workspace is the host. Status: accepted.

## D-008: Locked Hetzner Runtime

The baseline host is Hetzner Cloud CX43, x86_64, 8 shared vCPU, 16 GB RAM, 160 GB disk, Ubuntu 24.04, hostname `hydra-hermes-runtime-01`, preferred in `nbg1` with `fsn1` fallback, public IPv4 and IPv6, and no GPU. Status: accepted.

## D-009: Private Management Plane

The final-state provider firewall exposes no SSH rule. GitHub Actions reaches the host through Tailscale; ports 4000, 8642, and 18789 are never public during baseline validation. Status: accepted.

## D-010: Private Repository Credential Scope

The private repository uses repository secrets rather than GitHub Environment secrets so the bridge remains compatible without assuming GitHub Pro, Team, or Enterprise features. Required-reviewer protection is not claimed. Status: accepted.

## D-011: Tailscale OIDC Transport

GitHub-hosted ephemeral runners join the private tailnet through workload identity federation. The bridge uses `TS_OAUTH_CLIENT_ID`, `TS_AUDIENCE`, and an operator-configured tag set without a reusable Tailscale OAuth secret or auth key. Public SSH remains closed. Status: accepted.

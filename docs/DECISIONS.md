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

## D-012: Persistent Tailscale Host Before Firewall Lockdown

The Hetzner server enrolls as persistent `hydra-hermes-runtime-01` with exactly `tag:hydra-runtime` before restrictive UFW is enabled. Its one-off, non-reusable, non-ephemeral, short-lived auth key is supplied only through an external rendering flow and the documented `file:` mechanism. Tailscale SSH remains disabled; hardened OpenSSH is transported on `tailscale0`. Failure leaves UFW unenabled and Hetzner Console as recovery. Status: accepted.

## D-013: Active Runtime Provider

The active baseline host is the provisioned Contabo VPS identified by DMI as `QEMU`: x86_64, 8 vCPU, approximately 24 GB RAM, 300 GB disk, Ubuntu 24.04, hostname `hydra-hermes-runtime-01`, and no GPU requirement. D-008 and the Hetzner-specific recovery wording in D-012 are superseded for the active runtime; the provider-specific Hetzner files remain historical provisioning references only. Runtime admission is based on the locked capacity, OS, private Tailscale management plane, hardened OpenSSH, firewall, and service gates—not a provider brand string. Status: accepted.

## D-014: Validated Routed Baseline

The Contabo runtime, Hermes sandbox, NVIDIA Model Router route, credential boundary, listener exposure controls, scoped Docker-bridge firewall rules, and one real controlled inference prompt completed the baseline gates on 2026-07-18. Further integrations are a separate follow-up milestone. Status: accepted.

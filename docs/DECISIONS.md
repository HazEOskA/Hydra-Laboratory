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

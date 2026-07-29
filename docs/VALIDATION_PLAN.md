# Validation Plan

## Static Repository Gate

Run `make static-check`. CI repeats shell syntax checks, YAML parsing, documentation presence checks, and secret scanning. CI does not claim runtime success.

## Remote Preflight Gate

`scripts/remote-preflight.sh` requires a non-empty virtualization identity when DMI is available, hostname `hydra-hermes-runtime-01`, x86_64, Ubuntu 24.04, exactly 8 online vCPU, at least a 16 GB RAM class, at least a 160 GB root-disk class, public IPv4 and IPv6 routes, completed bootstrap marker, no pending reboot, the dedicated `hydra` user, systemd, active Docker/UFW/fail2ban, hardened effective SSH settings, required tools, Node.js, compatible Python, free ports 4000/8642/18789, NemoClaw/OpenShell presence, and sandbox-name collision. Provider identity is verified separately in the authenticated provider control plane and is not inferred from a brand-specific DMI string.

Before that remote preflight can be dispatched, `scripts/validate-tailscale-host.sh` must prove that `tailscaled` is enabled and active, `tailscale0` and assigned addresses exist, the backend is online, the hostname is `hydra-hermes-runtime-01`, the sole tag is `tag:hydra-runtime`, and persistent state exists. Repository test `tests/test-tailscale-bootstrap.sh` proves that these gates occur before UFW activation, runtime installation follows UFW, no public SSH rule or ephemeral host flag exists, the cloud-init renderer stays outside Git, the remote workflow remains manual-only, and the official Tailscale action remains pinned.

Official minimum: 4 vCPU, 8 GB RAM, 20 GB free. Recommended: 4+ vCPU, 16 GB RAM, 40 GB free. Node.js must be 22.19 or later. Model Router Python must be `>=3.10,<3.14` and import `ensurepip`, `pyexpat`, `ssl`, and `venv`.

## Runtime Contract

Run `scripts/validate-runtime.sh` and require:

1. `nemoclaw` installed and versioned.
2. `nemohermes` installed and versioned.
3. OpenShell CLI available.
4. `hydra-hermes-lab` registered as Hermes.
5. Sandbox ready/running.
6. `nemohermes hydra-hermes-lab doctor --json` succeeds.
7. Active route identifies the Model Router provider (`nvidia-router`) selected through onboarding value `routed`.
8. Authoritative in-sandbox inference health uses `https://inference.local/v1/models`.
9. Raw `NVIDIA_INFERENCE_API_KEY` is unset inside the sandbox.
10. Hermes API health responds on host loopback port 8642; optional dashboard port 18789 is loopback-only when present.
11. One real prompt succeeds.
12. Sanitized logs and Git contain no secrets.
13. Host listeners on 4000, 8642, and 18789 are loopback-only.
14. Host capacity, OS, hostname, private management plane, and security controls still match the active locked runtime target.

## Controlled First Prompt

Run one real, non-interactive prompt through the managed sandbox boundary with `nemohermes hydra-hermes-lab exec` and `hermes chat -q`. The prompt must request only agent identity, runtime, host-filesystem visibility, inference route, available tools, and sandbox boundaries, and must explicitly prohibit file changes and external tool calls.

Record only a redacted outcome summary and PASS/FAIL. A status/doctor result alone is not a substitute for this real inference test.

Final baseline outcome on 2026-07-18: **PASS**. See [RUNTIME_EVIDENCE.md](RUNTIME_EVIDENCE.md).

## Continuous Duty-Cycle Gate

`make worker-check` runs `scripts/validate-worker.sh`: every task manifest satisfies the queue contract in [tasks/README.md](../tasks/README.md); ids are unique and match their filenames; prompts stay inside the size limit and contain no external URLs, mutation verbs, credential-shaped material, or unknown placeholders; the worker keeps its `--execute` gate, host lock, budget knobs, single-instance lock, and redaction markers; the systemd units are hardened, run as `hydra`, and never enable simulation; and `config/worker.env.example` assigns no credential-shaped values.

`make worker-loop-check` runs `tests/test-worker-loop.sh` offline against a stub command and a scratch state directory. It proves that the default invocation is a dry run that records nothing, that each due task runs once per cadence, that credential-shaped output never reaches the state directory, that journal records are well formed and stamped as simulated, that the daily cap and `STOP` file bound spending, that the circuit breaker trips and stays tripped until `--resume`, that the simulation hooks are gated in both directions, and that reports render sanitized and flag simulated data.

Neither gate claims a working runtime. Continuous operation is only proven on the host, by `scripts/hermes-worker.sh --status` and a report covering real, non-simulated records.

## APR Isolation

APR validation is declarative: this repository contains no reference that executes against, imports from, or connects to Agent Proof Runtime. No APR checkout is needed or permitted.

## Provider-Control Gate

Before runtime installation, verify in the authenticated Contabo control plane that no public SSH rule is enabled, both public IP families exist, and available deletion/rebuild safeguards are enabled. In the Tailscale admin console, separately verify that the server is online, persistent, tagged exactly `tag:hydra-runtime`, and not using Tailscale SSH. Do not export provider or tailnet account data into repository evidence. The files under `infra/hetzner/` are retained as historical provisioning references and are not the active provider contract.

# Validation Plan

## Static Repository Gate

Run `make static-check`. CI repeats shell syntax checks, YAML parsing, documentation presence checks, and secret scanning. CI does not claim runtime success.

## Remote Preflight Gate

`scripts/remote-preflight.sh` requires Hetzner DMI identity, hostname `hydra-hermes-runtime-01`, x86_64, Ubuntu 24.04, exactly 8 online vCPU, a 16 GB RAM class, a 160 GB root-disk class, public IPv4 and IPv6 routes, completed cloud-init, no pending reboot, the dedicated `hydra` user, systemd, active Docker/UFW/fail2ban, hardened effective SSH settings, required tools, Node.js, compatible Python, free ports 4000/8642/18789, NemoClaw/OpenShell presence, and sandbox-name collision.

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
10. `nemohermes hydra-hermes-lab dashboard-url --quiet` returns a loopback management URL.
11. One real prompt succeeds.
12. Sanitized logs and Git contain no secrets.
13. Host listeners on 4000, 8642, and 18789 are loopback-only.
14. Host provider and capacity still match the locked Hetzner CX43 target.

## Controlled First Prompt

Open the URL returned by `nemohermes hydra-hermes-lab dashboard-url --quiet` through an operator-controlled tunnel and send exactly:

```text
You are running inside the sandbox named hydra-hermes-lab.

Report:
1. your agent identity,
2. your runtime,
3. whether you can access the host filesystem directly,
4. the inference route you see,
5. the tools currently available,
6. the boundaries imposed by the sandbox.

Do not modify files or call external tools.
```

Record only a redacted outcome summary and PASS/FAIL. A status/doctor result alone is not a substitute for this real inference test.

## APR Isolation

APR validation is declarative: this repository contains no reference that executes against, imports from, or connects to Agent Proof Runtime. No APR checkout is needed or permitted.

## Provider-Control Gate

Before runtime installation, verify in the Hetzner control plane that the exact firewall is attached, no public SSH rule exists, both public IP families exist, deletion protection is enabled for the server, and the selected image/location/plan match `infra/hetzner/server-spec.yaml`. Separately verify private Tailscale reachability and policy. Do not export provider or tailnet account data into repository evidence.

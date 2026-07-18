# Runtime Evidence

## Final Baseline — 2026-07-18

Status: **PASS**

This file records only sanitized operational outcomes. It contains no provider credential, gateway token, authenticated URL, public address, or raw agent response.

### Runtime

- Host: `hydra-hermes-runtime-01`
- Active provider: Contabo VPS / QEMU
- OS: Ubuntu 24.04
- Agent: Hermes
- Sandbox: `hydra-hermes-lab`
- Provider selector: `routed`
- Active route: `nvidia-router`
- Policy tier: `balanced`
- NemoClaw: `v0.0.83`
- NemoHermes: `v0.0.83`
- OpenShell: `0.0.72`

### Automated Runtime Gate

`scripts/validate-runtime.sh` completed with:

- `failures=0`
- sandbox identity, readiness, and routed provider: PASS
- runtime host identity and doctor: PASS
- `inference.local` route from inside the sandbox: PASS
- raw `NVIDIA_INFERENCE_API_KEY` unavailable inside the sandbox: PASS
- Hermes API health on host loopback port 8642: PASS
- Model Router listener on port 4000: PASS
- ports 8642 and 18789 loopback-only: PASS
- UFW scope for Model Router 4000 and OpenShell gateway 8080 restricted to `172.18.0.0/16`: PASS

### Controlled First Prompt

A real, non-interactive Hermes inference request was executed through `nemohermes hydra-hermes-lab exec` using `hermes chat -q`.

The prompt requested only agent identity, runtime, host-filesystem visibility, inference route, available tools, and sandbox boundaries, and explicitly prohibited file changes and external tool calls.

Outcome: **PASS**

Only the redacted PASS outcome is recorded. The raw response remains outside Git.

### Security Outcome

- Git and repository secret scan: PASS
- Provider credential remained host-side: PASS
- Raw NVIDIA key unavailable inside sandbox: PASS
- Hermes API and optional dashboard not publicly exposed: PASS
- Model Router and OpenShell gateway limited to the Docker bridge by UFW: PASS
- Public SSH remained closed; management uses Tailscale: PASS

## Final Result

`REMOTE WORKFLOW VALIDATION: failures=0`

`RUNTIME VALIDATION: failures=0`

`CONTROLLED FIRST PROMPT: PASS`

Baseline Hydra/Hermes validation is complete.

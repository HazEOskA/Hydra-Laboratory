# Hermes God-Layer v1 — Code Complete Lock

Date: 2026-07-31  
Owner: OSA / Bartosz Osiński  
Repository: `HazEOskA/hydra-hermes-lab`  
Status: **CODE_COMPLETE / RUNTIME_REVALIDATION_REQUIRED**

## Decision

Hermes God-Layer v1 is closed as a code and control-plane milestone.

This lock does **not** claim that the current runtime host is production-verified or that Hermes is currently operating continuously. Runtime status must be proven again with current host evidence after the merged control-plane baseline is deployed.

## Locked Scope

The v1 code milestone includes:

- `SOUL.md` operational constitution and ownership boundary;
- GREEN / YELLOW / RED permission classification;
- durable SQLite queue, mission state and hash-chained evidence ledger;
- capability-aware model routing and live provider health probing;
- supervised duty-cycle worker with budget, pacing, STOP file and circuit breaker;
- recovery, backup, host-baseline and evidence-bundle tooling;
- revenue preparation pipeline with external sending held behind RED approval;
- static contracts, shell tests, Python tests and repository CI gates.

## Repository Evidence

- Merge commit: `561a1c8e5042b84bf5acc65cc2790f2d82039f28`
- Merge title: `Restore Hermes God-Layer control plane (#1)`
- Default branch: `main`
- CI workflow: `.github/workflows/validate.yml`
- CI triggers: pushes to `main` and pull requests
- CI gates:
  - shell syntax and ShellCheck;
  - YAML parsing;
  - infrastructure and remote-workflow contracts;
  - continuous duty-cycle validation;
  - God-Layer and recovery validation;
  - Python control-plane tests;
  - documentation validation;
  - secret scanning.

## Runtime Evidence Boundary

`docs/RUNTIME_EVIDENCE.md` records a sanitized baseline PASS from 2026-07-18.

`docs/RUNTIME_FINDINGS.md` records newer host observations from 2026-07-29, including:

- a sandbox that was observed stuck in `Provisioning` at that time;
- an unresolved provider-identity difference: `nvidia-prod` versus the locked routed baseline;
- an unpinned `hydra-direct` installation and undocumented port `19001`;
- a fixed model-health population defect;
- a fixed recovery JSON parsing defect.

Therefore the 2026-07-18 PASS is historical evidence, not sufficient proof of the current production state.

## Explicit Non-Claims

This milestone does not claim:

- current 24/7 worker operation on the host;
- current API, dashboard or tool-gateway availability;
- current model-route conformity;
- current credential-boundary verification;
- resolved findings F-001, F-002 or F-005;
- production readiness without a new runtime evidence bundle.

## Production Verification Exit Gate

The next status may become **PRODUCTION_VERIFIED** only after all of the following are evidenced against the current host and current `main`:

1. repository CI passes for this closure branch;
2. the merged God-Layer baseline is deployed or confirmed byte-equivalent on the runtime host;
3. sandbox phase is `Ready`;
4. Hermes API and dashboard health checks pass;
5. the active model route is recorded and the provider decision is resolved;
6. `NVIDIA_INFERENCE_API_KEY` is proven unavailable inside the sandbox;
7. worker status shows real, non-simulated operation within configured limits;
8. queue and ledger persistence survive a controlled restart;
9. a current sanitized evidence bundle is committed;
10. rollback instructions are confirmed against the deployed version.

## Change Lock

Until the Production Verification Exit Gate passes:

- no new Hermes feature family is added;
- no multi-agent expansion is started;
- no public production-readiness claim is made;
- work is limited to validation, evidence, defect correction and rollback safety.

## Rollback

This file is documentation-only and changes no runtime behavior.

Rollback options:

- close the pull request without merging; or
- after merge, revert the documentation commit.

No host, service, secret, database, queue or network state is modified by this lock.

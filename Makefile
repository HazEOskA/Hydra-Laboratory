SHELL := /usr/bin/env bash

# hermesctl surfaces every control plane capability; see docs/GOD_LAYER.md
.PHONY: static-check secret-boundary-check syntax-check infra-check tailscale-bootstrap-check remote-workflow-check worker-check worker-loop-check godlayer-check recovery-check python-tests docs-check secret-scan preflight validate worker-plan worker-status report health baseline evidence recover

static-check: syntax-check secret-boundary-check infra-check tailscale-bootstrap-check remote-workflow-check worker-check worker-loop-check godlayer-check recovery-check python-tests docs-check secret-scan

syntax-check:
	@for script in scripts/*.sh tests/*.sh; do bash -n "$$script"; done

secret-boundary-check:
	@./tests/test-secret-boundary.sh

infra-check:
	@./scripts/validate-infra.sh

tailscale-bootstrap-check:
	@./tests/test-tailscale-bootstrap.sh

remote-workflow-check:
	@./scripts/validate-remote-workflow.sh

worker-check:
	@./scripts/validate-worker.sh

worker-loop-check:
	@./tests/test-worker-loop.sh

godlayer-check:
	@./scripts/validate-godlayer.sh

recovery-check:
	@./tests/test-recovery.sh

python-tests:
	@python3 -m unittest discover -s tests/python -p 'test_*.py'

docs-check:
	@for file in README.md docs/ARCHITECTURE_LOCK_v0.1.md docs/DEPLOYMENT_PLAN.md docs/REMOTE_PREFLIGHT_BRIDGE.md docs/SECURITY_MODEL.md docs/VALIDATION_PLAN.md docs/CONTINUOUS_OPERATION.md docs/GOD_LAYER.md docs/RUNTIME_FINDINGS.md docs/DECISIONS.md docs/INSTALL_EVIDENCE.md docs/ROLLBACK.md docs/HYDRA_OSA_EXECUTION_FORCE_ADAPTER.md infra/README.md infra/host-requirements.md infra/hetzner/README.md infra/hetzner/PROVISIONING_CHECKLIST.md infra/hetzner/server-spec.yaml infra/hetzner/firewall-rules.yaml tasks/README.md config/worker.env.example SOUL.md config/tools.yaml config/models.yaml config/schedule.yaml; do test -s "$$file" || { echo "Missing or empty: $$file"; exit 1; }; done
	@grep -q 'hydra-hermes-lab' README.md
	@grep -q 'NVIDIA Model Router' docs/ARCHITECTURE_LOCK_v0.1.md

secret-scan:
	@./scripts/secret-scan.sh

preflight:
	@./scripts/remote-preflight.sh

validate:
	@./scripts/validate-runtime.sh

worker-plan:
	@./scripts/hermes-worker.sh --dry-run

worker-status:
	@./scripts/hermes-worker.sh --status

report:
	@./scripts/hermes-report.sh --stdout

health:
	@./scripts/hermesctl health

baseline:
	@./scripts/host-baseline.sh

evidence:
	@./scripts/evidence-bundle.sh

recover:
	@./scripts/recover-hermes.sh

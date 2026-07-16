SHELL := /usr/bin/env bash

.PHONY: static-check syntax-check infra-check remote-workflow-check docs-check secret-scan preflight validate

static-check: syntax-check infra-check remote-workflow-check docs-check secret-scan

syntax-check:
	@for script in scripts/*.sh; do bash -n "$$script"; done

infra-check:
	@./scripts/validate-infra.sh

remote-workflow-check:
	@./scripts/validate-remote-workflow.sh

docs-check:
	@for file in README.md docs/ARCHITECTURE_LOCK_v0.1.md docs/DEPLOYMENT_PLAN.md docs/REMOTE_PREFLIGHT_BRIDGE.md docs/SECURITY_MODEL.md docs/VALIDATION_PLAN.md docs/DECISIONS.md docs/INSTALL_EVIDENCE.md docs/ROLLBACK.md infra/README.md infra/host-requirements.md infra/hetzner/README.md infra/hetzner/PROVISIONING_CHECKLIST.md infra/hetzner/server-spec.yaml infra/hetzner/firewall-rules.yaml; do test -s "$$file" || { echo "Missing or empty: $$file"; exit 1; }; done
	@grep -q 'hydra-hermes-lab' README.md
	@grep -q 'NVIDIA Model Router' docs/ARCHITECTURE_LOCK_v0.1.md

secret-scan:
	@./scripts/secret-scan.sh

preflight:
	@./scripts/remote-preflight.sh

validate:
	@./scripts/validate-runtime.sh

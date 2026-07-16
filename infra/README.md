# Infrastructure

This directory defines the locked baseline for Hetzner Cloud CX43 `hydra-hermes-runtime-01` on Ubuntu 24.04. The preferred location is Nuremberg (`nbg1`), with Falkenstein (`fsn1`) as fallback.

`cloud-init.yaml` creates the dedicated `hydra` operator, transfers the public key injected by Hetzner, hardens SSH, enables unattended security upgrades, UFW and fail2ban, installs Docker and Node.js 22, and adds `hydra` to the Docker group. Docker membership is root-equivalent and is accepted only for this dedicated single-user runtime. Cloud-init does not install NemoClaw, collect credentials, create the sandbox, or expose management ports.

`hetzner/server-spec.yaml` records the immutable target. `hetzner/firewall-rules.yaml` is a reviewed control manifest; its required operator CIDR markers must be resolved in the Hetzner control plane and must never be replaced with `0.0.0.0/0` or `::/0`. Keep ports 18789, 8642, and 4000 off the public internet.

# Infrastructure

This directory defines the locked baseline for Hetzner Cloud CX43 `hydra-hermes-runtime-01` on Ubuntu 24.04. The preferred location is Nuremberg (`nbg1`), with Falkenstein (`fsn1`) as fallback.

`cloud-init.yaml` is a secret-free template. Its gated bootstrap creates `hydra`, transfers the Hetzner-injected public key, hardens OpenSSH, installs and enrolls a persistent Tailscale node, proves the private interface is online, then enables UFW with SSH accepted only on `tailscale0`. Docker, Node.js 22, fail2ban, and unattended upgrades are installed only after that gate. Docker membership is root-equivalent and is accepted only for this dedicated single-user runtime. Cloud-init does not install NemoClaw, create the sandbox, enable Tailscale SSH, or expose management ports.

`scripts/render-cloud-init.sh` reads the one-off `TS_RUNTIME_AUTH_KEY` only from an approved external process environment and writes a mode-`0600` rendered copy outside the repository. That transient file is the only cloud-init artifact permitted to contain the bootstrap secret and must be deleted after provider submission.

`hetzner/server-spec.yaml` records the immutable target. `hetzner/firewall-rules.yaml` is the final-state provider control manifest: no public SSH rule and no public ports 4000, 8642, or 18789. Workflow access uses hardened OpenSSH over the independently validated private Tailscale path.

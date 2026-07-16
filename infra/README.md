# Infrastructure

This directory defines a generic baseline for a dedicated Ubuntu 24.04 runtime host.

`cloud-init.yaml` installs baseline Ubuntu packages and Docker. It intentionally does not grant Docker-group membership, install NemoClaw, collect credentials, create the sandbox, or expose dashboard ports. Docker access and Node.js `>=22.19` must be configured through operator-approved paths before preflight can pass.

The host should be single-user, reachable through SSH, and protected by provider firewall rules. Keep ports 18789, 8642, and 4000 off the public internet during baseline testing.

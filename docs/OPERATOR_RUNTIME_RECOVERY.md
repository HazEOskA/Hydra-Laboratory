# Operator runbook — runtime recovery on `hydra-hermes-runtime-01`

Copy-paste sequence for OSA. Every script gates on host `hydra-hermes-runtime-01`
and user `hydra`, is read-only or dry-run by default, and needs an explicit
`--execute` before it changes anything.

**Status: NOT EXECUTED.** Nothing in this bundle has been run against the
runtime host. It was authored in a session with no access to it.

## What each script may and may not do

| Script | Default | Mutates |
|---|---|---|
| `operator-runtime-audit.sh` | read-only | never — there is no `--execute` |
| `operator-hermes-recover.sh` | `--dry-run` | only with `--execute`, only along the ladder below |
| `operator-workers-install.sh` | `--dry-run` | only with `--execute` |
| `operator-runtime-verify.sh` | read-only | never |

Refused in every mode, unreachable from these scripts: sandbox destroy, rebuild,
onboard, NemoClaw reinstall, provider or model change, NVIDIA credential change,
persistent state wipe, `docker system prune`, host reboot, UFW change, Tailscale
change.

## 0. Check out the exact commit

```bash
cd /opt/hydra/apps/hydra-hermes-lab   # or the path you confirm in step 2
git fetch origin claude/hydra-michael-angelo-launch-bizcvn
git checkout <COMMIT_SHA_FROM_THE_REPORT>
git rev-parse HEAD
```

## 1. Audit — read-only

```bash
./scripts/operator-runtime-audit.sh
```

Writes to `/var/lib/hydra-hermes/evidence/runtime-audit-<UTC>/`.

## 2. Read the summary

```bash
ls -1dt /var/lib/hydra-hermes/evidence/runtime-audit-* | head -1
cat "$(ls -1dt /var/lib/hydra-hermes/evidence/runtime-audit-* | head -1)/runtime-audit-summary.txt"
```

Confirm: the sandbox container id, `State.ExitCode`, `State.OOMKilled`, the
listeners on 4000/8080/8642/18789/8787, and which of the candidate repository
paths is canonical.

**If `OOMKilled=true`:** starting the container again will most likely reproduce
the crash. Raise it with OSA before step 4 rather than restarting in a loop.

## 3. Recovery — dry-run

```bash
./scripts/operator-hermes-recover.sh
```

Prints root cause, the backup it would take, and the exact repair it would
attempt. Changes nothing.

## 4. Recovery — execute

Only after reading step 3's output.

```bash
./scripts/operator-hermes-recover.sh --execute
```

Repair ladder, smallest first — it stops at the first one that works:

1. `docker start` the existing stopped container, no config change
2. `nemohermes <sandbox> start` for this sandbox only
3. restart of the specific sandbox service, never the host
4. `scripts/recover-hermes.sh --skip-rebuild --execute` — evidence capture and
   validation only

**Step 4 skips phase 4 of `recover-hermes.sh`, which is a `[DESTRUCTIVE]`
sandbox rebuild, and everything that script does after it.** Never run
`recover-hermes.sh` without `--skip-rebuild` from this bundle.

If the ladder does not reach `Ready`/`Running`, the script exits `3` with
status **BLOCKED**. Do not escalate to rebuild; hand the evidence directory to
OSA.

## 5. Verify

```bash
./scripts/operator-runtime-verify.sh
```

Twenty-one checks, each `PASS` / `FAIL` / `UNKNOWN` / `N/A`. Exit `0` only when
there are no failures.

`REAL_INFERENCE` passes only when the reply is exactly `HERMES_RUNTIME_OK`.
`CREDENTIAL_ISOLATION` passes only when `NVIDIA_INFERENCE_API_KEY` is `ABSENT`
inside the sandbox; the value is never printed. `HERMES_DASHBOARD` passes only
when 18789 both listens and answers HTTP — a `dashboardPort` in `sandboxes.json`
is not evidence.

**If `CREDENTIAL_ISOLATION` reports PRESENT:** stop. Do not fix it automatically,
do not restart the runtime. Escalate to OSA with a remediation plan and rotate
the key, because a credential readable inside a workload sandbox is disclosed.

## 6. Worker install — dry-run

```bash
./scripts/operator-workers-install.sh
```

Resolves the canonical repository from `/opt/hydra/apps/hydra-hermes-lab` and
`/home/hydra/hermes-godlayer`. `/home/hydra/hydra-hermes-lab` is never assumed.

**Known DRIFT:** `infra/systemd/hydra-hermes-worker.service` ships with
`WorkingDirectory=/home/hydra/hydra-hermes-lab` and an `ExecStart` under the
same path — a path OSA has said not to assume. The script detects the mismatch,
reports `DRIFT`, and **stops before installing** (exit `4`). Confirm the real
path and pass it explicitly:

```bash
./scripts/operator-workers-install.sh --repo-path=/opt/hydra/apps/hydra-hermes-lab
```

With `--repo-path` it installs a path-corrected copy of the same units and backs
up whatever is already in `/etc/systemd/system`.

### worker.env

```bash
sudo install -d -o root -g hydra -m 0750 /etc/hydra-hermes
sudo install -o root -g hydra -m 0640 config/worker.env.example /etc/hydra-hermes/worker.env
sudoedit /etc/hydra-hermes/worker.env      # review; it must hold no credential values
```

## 7. Worker install — execute

```bash
./scripts/operator-workers-install.sh --execute --repo-path=/opt/hydra/apps/hydra-hermes-lab
```

The Hermes worker is enabled only when all four gates pass:
`HERMES_SANDBOX_READY`, `NVIDIA_ROUTE`, `REAL_INFERENCE`, `CREDENTIAL_ISOLATION`.
Otherwise it exits `5` without enabling anything. Health-watch, report and
repo-watch timers do not depend on live inference and are enabled regardless.

## 8. Verify again

```bash
./scripts/operator-runtime-verify.sh
systemctl status hydra-hermes-worker.service --no-pager
systemctl is-enabled hydra-hermes-worker.service
journalctl -u hydra-hermes-worker.service --no-pager --lines=40
```

The worker must report `ACTIVE` or `HEALTHY_IDLE`. "Configured" is not running.

### Reboot persistence

`hydra-hermes-worker.service` declares `WantedBy=multi-user.target` with
`Restart=always` and `RestartSec=60`, so `systemctl is-enabled` returning
`enabled` is what makes it survive a reboot. Confirm with a scheduled reboot
window agreed with OSA — this bundle never reboots the host.

## 9. Rollback

```bash
RUN=$(ls -1dt /var/lib/hydra-hermes/evidence/workers-install-* | head -1)

sudo systemctl disable --now hydra-hermes-worker.service
sudo systemctl disable --now hydra-hermes-healthwatch.timer \
                              hydra-hermes-report.timer \
                              hydra-hermes-repowatch.timer

# Restore the units that were there before, or remove the ones this bundle added.
sudo cp -a "$RUN/systemd-backup/." /etc/systemd/system/ 2>/dev/null || true
for u in $(ls "$RUN/units"); do
  [ -e "$RUN/systemd-backup/$u" ] || sudo rm -f "/etc/systemd/system/$u"
done
sudo systemctl daemon-reload
```

The container repair is rolled back by stopping the container that was started:

```bash
CID=$(docker ps -a --no-trunc --format '{{.ID}} {{.Names}}' | grep -F hydra-hermes-lab | awk 'NR==1{print $1}')
docker stop "$CID"
```

Nothing else needs undoing: no configuration, provider, model, credential,
firewall or Tailscale setting was modified. Evidence directories under
`/var/lib/hydra-hermes/evidence/` are additive and safe to keep.

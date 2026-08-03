# NVIDIA / NemoClaw read-only audit — runbook

**Status: NOT EXECUTED.** Every verdict is `UNKNOWN`.

The audit is scoped to the locked host `hydra-hermes-runtime-01`. The session
that produced this file ran on an ephemeral repository container (`vm`) where
`nemohermes`, `nemoclaw` and `hermes` do not exist. Running the audit there
would have described the wrong machine, so nothing was run.

`UNKNOWN` is not reassurance. In particular, credential isolation is
**unverified**, not confirmed.

## Prohibitions this audit operates under

No rebuild, restart, stop or deploy. No credential writes, no printing of key
values, no provider or endpoint change, no package installation, no
GREEN/YELLOW/RED tests, no enqueue or cancel.

## Run on `hydra-hermes-runtime-01`

Confirm the host before anything else. If this prints anything other than
`hydra-hermes-runtime-01`, stop.

```bash
hostname -s
command -v nemohermes
command -v nemoclaw
```

### 1. Sandbox state

```bash
nemohermes hydra-hermes-lab status --json
nemoclaw list --json
```

### 2. Configured inference route

```bash
nemoclaw inference get --json
```

### 3. Model Router

```bash
PYTHONPATH=lib python3 -m hermes.cli models probe
```

> This command records provider health into the health table — it is the one
> step of the audit that writes. It is in scope on the locked host and must not
> be run anywhere else.

### 4. Endpoint as seen inside the sandbox

```bash
nemohermes hydra-hermes-lab exec --no-stdin -- sh -lc '
printf "OPENAI_BASE_URL=%s\n" "${OPENAI_BASE_URL:-unset}"
curl -fsS --max-time 15 -o /tmp/models-response.json \
  -w "HTTP_STATUS=%{http_code}\n" \
  https://inference.local/v1/models
python3 - <<PY
import json
p="/tmp/models-response.json"
try:
    data=json.load(open(p))
    models=data.get("data", [])
    print("MODEL_COUNT=" + str(len(models)))
    for model in models[:10]:
        print("MODEL=" + str(model.get("id", "unknown")))
except Exception as exc:
    print("MODELS_JSON_INVALID=" + type(exc).__name__)
PY
rm -f /tmp/models-response.json
'
```

### 5. Credential boundary — never print values

```bash
nemohermes hydra-hermes-lab exec --no-stdin -- sh -lc '
if [ -z "${NVIDIA_INFERENCE_API_KEY:-}" ]; then
  echo NVIDIA_KEY_IN_SANDBOX=ABSENT
else
  echo NVIDIA_KEY_IN_SANDBOX=PRESENT
fi
'
```

Required outcome: `NVIDIA_KEY_IN_SANDBOX=ABSENT`.

**If the result is `PRESENT`:** do not fix it automatically, do not stop the
runtime. Mark `SECURITY FAILURE`, end the audit at this step, and escalate to
OSA with a remediation plan only. Step 6 must not be run.

### 6. Real inference

```bash
nemohermes hydra-hermes-lab exec --no-stdin -- \
  hermes chat -q \
  'Reply with exactly: NVIDIA_NEMOCLAW_PROBE_OK. Do not modify files or call tools.'
```

`PASS` only when the reply contains exactly `NVIDIA_NEMOCLAW_PROBE_OK`.

## Recording the result

Update `audit-bundle.json` with: UTC timestamp, hostname, sandbox phase,
provider, endpoint without secrets, `/v1/models` HTTP status, model identifier
list, key isolation result, real inference result, SHA-256 of every evidence
file, and the branch HEAD SHA.

Never record: API keys, `Authorization` headers, the full environment, tokens,
or credential storage files.

## Safe remediation plan if isolation fails

Stated in advance so nobody improvises during an incident. All steps are
proposals for OSA, not actions to take unilaterally:

1. Confirm the finding by re-running **only** step 5. Do not print the value.
2. Determine where the variable enters the sandbox — image layer, sandbox
   profile, or host environment inheritance — by reading configuration, not by
   dumping the environment.
3. Prepare the scoped fix: remove the variable from the sandbox profile so the
   key stays host-side, reachable by the inference proxy but never by the
   workload.
4. Rotate the exposed key on the NVIDIA side before the fix ships, because any
   key readable inside a workload sandbox must be treated as disclosed.
5. Apply the change through the normal reviewed path with OSA approval. Do not
   rebuild, restart or redeploy as an ad-hoc reaction.
6. Re-run steps 5 and 6 to confirm `ABSENT` and that inference still works.

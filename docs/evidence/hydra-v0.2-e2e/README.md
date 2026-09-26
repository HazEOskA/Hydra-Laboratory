# Hydra v0.2 — sanitized E2E evidence bundle

Point-in-time record of one real end-to-end coding mission, pinned to an exact
commit.

## Pinned to

| Field | Value |
|---|---|
| Repository | `HazEOskA/hydra-hermes-lab` |
| Branch | `claude/hydra-michael-angelo-launch-bizcvn` |
| Commit SHA | `a255cba3a1339656abe3666f31af92ed633599cf` |
| `lib/hydra_control` tree | `3cd567aa5e21a2003c14a79f4a693856bfe6a1ef` |
| `web` tree | `78b96a531c304c29275cb861f227241e2880638a` |

The pinned commit is this file's **parent**, because a commit cannot contain its
own SHA. `lib/hydra_control` and `web/` are byte-identical from `b4b43f6`
through `a255cba`, so the captured run reflects exactly the code at the pinned
commit. Verify with:

```bash
git diff --stat b4b43f6 a255cba -- lib web   # expected: empty
```

## What the run did

Driven through the browser UI, not the API — an operator filling the real
intake form:

```text
formularz intake → kolejka → scheduler → bramka architektury (zatwierdzona w UI)
  → sandbox → zmiana → format/lint → testy → weryfikacja runtime → review
  → dowody APR → bramka ludzka (zatwierdzona w UI) → COMPLETED
```

| Fact | Value |
|---|---|
| Mission | `2b7eefa6-c365-4ead-8fd3-bb1ff5c81435` |
| Worker | `deterministic-local` |
| Base → result commit | `ff23548849` → `291474fbb8` |
| Changed files | `app.py` (+5) |
| Checks | format, lint, tests, review, runtimeVerification = **PASS** |
| Acceptance criteria | 2/2 PASS |
| Required tests | 1/1 PASS |
| Rollback plan | verified, commit-bound |
| Artifacts | 48 |
| Commands | 21 |
| Event chain | verified over 67 events |
| `evidence.valid` | **true**, no invalidation reasons |

## Sanitization

The scrubber strips host filesystem paths, external e-mail addresses,
token-like strings and key/secret assignments. **Zero replacements were
required** — the control-plane API never emits host paths, and logs and
artifacts already pass through the Hermes redactor. The scrubber ran anyway and
its result is recorded in the envelope, so a future capture path that starts
leaking cannot land here unnoticed.

## Integrity

```bash
cd docs/evidence/hydra-v0.2-e2e
sha256sum -c SHA256SUMS
```

`bundleSha256` inside the envelope covers the inner evidence bundle
independently of the envelope wrapper:

```bash
python3 -c "
import json,hashlib
d=json.load(open('evidence-bundle.json'))
b=d['evidence']['bundle']
print(hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':')).encode()).hexdigest())
print(d['bundleSha256'])"
```

## What this does NOT claim

- **No branch push and no GitHub PR.** The pull request is a
  `LOCAL_DESCRIPTOR`; the worker holds no credentials and has no network.
- **Only `deterministic-local` executed.** Codex, OpenHands, Claude worker and
  the generic Minion slot were `UNAVAILABLE` and refused to run.
- **Nothing here attests to any non-local runtime.** Deployment status stays
  `UNKNOWN`.
- Commit binding was re-verified against the live workspace at capture time
  (workspace `HEAD` == `resultCommit`). That state root is ephemeral, so
  repeating that specific check later needs a fresh E2E run. The SHA-256 values
  above stay checkable against these files indefinitely.

## Reproduce

See `docs/HYDRA_RUNBOOK.md`. Rollback for the change itself is in
`docs/HYDRA_ROLLBACK_MANIFEST_v0.2.md`; `rollback-manifest.json` here is the
per-mission plan emitted by `GET /api/missions/{id}/rollback`.

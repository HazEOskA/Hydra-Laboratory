# HYDRA Exact Recovery Preview v1

Status: PREVIEW RECOVERY

## Sources

- Current backend/control repository baseline: `main@25ec03fc648e1c6f46ce430ca90842c527a1f554`
- Binding visual implementation: `feat/hydra-ui-from-design-files-v0.1@0005f286d92021d75034aabcecebf92aae003f74`
- Preserved React recovery snapshot: `recovery/hydra-ui-11a7e538@db8652f3123adf87cae19c2831e284a4b3061de6`

## Preview rule

The Vercel preview serves the recovered command-center UI exactly from the locked design-assets implementation. Runtime-backed controls are enabled only when `window.HYDRA_CONFIG.apiEnabled === true`.

The initial Vercel preview intentionally sets the runtime API to disconnected. Navigation, layouts, responsive UI, local dialogs, and read-only surfaces work. Runtime mutations are disabled or expose explicit OFFLINE / NOT CONNECTED / UNKNOWN states instead of fabricated data.

The current Hydra/Hermes backend files from `main` remain unchanged. The recovered deterministic control-plane adapter under `lib/hydra_control/` is included for later reviewed wiring on GCP/VPS; Vercel does not claim durable runtime execution.

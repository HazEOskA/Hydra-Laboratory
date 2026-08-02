# HYDRA UI Asset Manifest v0.1

Status: LOCKED for `feat/hydra-ui-from-design-files-v0.1`.

The supplied PNG files are the binding visual source for this iteration. The
original files remain unchanged at their source locations. Web copies are
offline, local, and optimized to 900 px WebP at quality 88. Composite reference
boards are preserved byte-for-byte under `docs/ui-references/`.

## Supplied Files

| Original filename | Type / size | Intended component | Repository destination | Directly used | Optimization | UI state | Hi-density |
|---|---|---|---|---|---|---|---|
| `ChatGPT Image 2 sie 2026, 05_43_36.png` | PNG, 1672x941 | Binding full dashboard composition | `docs/ui-references/hydra-dashboard-reference.png` | Reference only | No; preserved | Composite | Yes |
| `ChatGPT Image 2 sie 2026, 05_44_51.png` | PNG, 1254x1254 | OpenShell / sandbox illustration | `web/assets/illustrations/openshell-claw.webp` | Yes | 900x900 WebP | Static | Yes |
| `ChatGPT Image 2 sie 2026, 05_44_57.png` | PNG, 1254x1254 | Monitoring and no-history state | `web/assets/illustrations/monitoring-hydra.webp` | Yes | 900x900 WebP | Static | Yes |
| `ChatGPT Image 2 sie 2026, 05_45_01.png` | PNG, 1254x1254 | Michael Angelo primary identity | `web/assets/illustrations/michael-angelo-lens.webp` | Yes | 900x900 WebP | Static | Yes |
| `ChatGPT Image 2 sie 2026, 05_45_06.png` | PNG, 1254x1254 | Model router / infrastructure | `web/assets/illustrations/model-router-core.webp` | Yes | 900x900 WebP | Static | Yes |
| `ChatGPT Image 2 sie 2026, 05_45_11.png` | PNG, 1254x1254 | Zgredek Drift Guard | `web/assets/illustrations/zgredek-observatory.webp` | Yes | 900x900 WebP | Static | Yes |
| `ChatGPT Image 2 sie 2026, 05_45_15.png` | PNG, 1254x1254 | Night Watch / audit identity | `web/assets/illustrations/night-watch.webp` | Yes | 900x900 WebP | Static | Yes |
| `ChatGPT Image 2 sie 2026, 05_45_19.png` | PNG, 1254x1254 | APR evidence identity | `web/assets/illustrations/apr-evidence.webp` | Yes | 900x900 WebP | Static | Yes |
| `ChatGPT Image 2 sie 2026, 05_45_24.png` | PNG, 1254x1254 | Policies AI / governance identity | `web/assets/illustrations/policies-ai.webp` | Yes | 900x900 WebP | Static | Yes |
| `ChatGPT Image 2 sie 2026, 05_45_31.png` | PNG, 1491x1055 | Binding service-icon composition | `docs/ui-references/hydra-service-icons-reference.png` | Reference only | No; preserved | Composite | Yes |
| `ChatGPT Image 2 sie 2026, 05_45_40.png` | PNG, 1672x941 | Binding product-layout composition | `docs/ui-references/hydra-product-layouts-reference.png` | Reference only | No; preserved | Composite | Yes |
| `ChatGPT Image 2 sie 2026, 05_45_45.png` | PNG, 1536x1024 | Binding design-system board | `docs/ui-references/hydra-design-system-reference.png` | Reference only | No; preserved | Composite | Yes |
| `codex-clipboard-b844affc-1893-4bbe-8af9-285c9c1c4aba.png` | PNG, 1254x1254 | Duplicate of the Michael Angelo lens | No duplicate copy | No | Identical SHA-256 to `05_45_01` | Static | Yes |

## Missing Original Asset Files

The supplied design-system board depicts individual files, but those original
files were not supplied. They remain explicitly `UNKNOWN` and are not silently
replaced:

- SVG logos and service icons
- display, interface, and terminal font files
- idle, hover, and active button raster states
- panel, card, terminal, modal, input, and bottom frames
- background tiles, patterns, grid, noise, glow, lightning, and particle files
- terminal cursors, chart primitives, toggles, badges, locks, audio, and misc UI files

Structural borders, glows, focus rings, navigation markers, charts, and status
badges are recreated with CSS because their original individual files are
missing. No illustrative asset is recreated with CSS.

## Safety and Serving

The runtime brand file `web/assets/brand/hydra-wordmark.webp` is a derived crop
from the supplied dashboard reference. It removes surrounding dashboard chrome
while keeping the supplied HYDRA HERMES LAB wordmark intact. The complete source
reference remains byte-preserved in
`docs/ui-references/hydra-dashboard-reference.png`.

- No external CDN or hotlink is used.
- No image is embedded as base64.
- Web assets contain no metadata required by the application and no executable
  content.
- Accessible labels are supplied by the consuming HTML; decorative images use
  empty alternative text.
- `/assets/` is served through a containment-checked, extension-allowlisted
  static path.

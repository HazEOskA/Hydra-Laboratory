# HYDRA UI Design Lock v0.1

Status: LOCKED for the local command-center iteration.

This lock extends `MINION_CONTROL_PLANE_ARCHITECTURE_LOCK_v0.1.md`. It does not
authorize a remote deployment, production authentication, Michael Angelo or
Policies AI runtime integration, or changes to the Hermes sandbox.

## Visual Direction

HYDRA is an antique-gold, mythological cyber command center: black layered
surfaces, thin engraved borders, restrained purple energy, dense operator data,
and explicit state. It must not become a generic SaaS admin template.

The memorable signature is the tension between museum-grade Greek ornament and
precise modern control-plane telemetry. Illustrations occupy bounded identity
zones; operational data remains readable and primary.

## Token Contract

```css
--canvas: #08090c;
--canvas-deep: #030406;
--surface-1: #0e1015;
--surface-2: #12151c;
--surface-3: #181b24;
--gold: #d4af37;
--gold-bright: #efc86b;
--gold-dim: #826321;
--purple: #a855f7;
--purple-deep: #6b21a8;
--purple-ink: #2a0b47;
--green: #22c55e;
--amber: #f59e0b;
--red: #ef4444;
--blue: #60a5fa;
--text: #e5e7eb;
--text-soft: #a7aab4;
--text-dim: #6f7480;
--border: rgba(212, 175, 55, 0.28);
--border-strong: rgba(212, 175, 55, 0.58);
--focus: #c267ff;
```

## Typography

- Display: `Georgia`, `Times New Roman`, serif; uppercase, tracked 0.18-0.28em.
- Interface: `Bahnschrift`, `Arial Narrow`, sans-serif; compact and legible.
- Terminal: `Cascadia Code`, `Consolas`, monospace.
- Exact supplied font files are `UNKNOWN`; no external font network request is
  permitted.
- Scale: 10 / 11 / 12 / 14 / 18 / 24 / 32 px.

## Layout and Spacing

- Primary canvas: 1440x900; also validate 1920x1080 and 1280x800.
- Sidebar: 228 px desktop; header: 68 px.
- Dashboard content: 12-column grid with 12 px gaps.
- Spacing scale: 4, 6, 8, 12, 16, 20, 24, 32 px.
- Panel padding: 14-18 px; dense table rows: 36-42 px.
- Corners: 2 px controls, 4 px cards, 6 px major panels. Ornament is expressed
  through clipped corners and double borders, not large SaaS radii.

## Surface Hierarchy

1. Near-black canvas with subtle radial purple/gold energy.
2. Noise and circuit-line overlays below all interactive content.
3. Primary panels with one-pixel gold border and inset black shadow.
4. Selected/active surfaces with purple inner light and gold outer edge.
5. Critical actions use red border and text without decorative ambiguity.

Gold glow is subtle (`0 0 18px rgba(212,175,55,.10)`). Purple glow may be
stronger only on active navigation, focus, and live execution.

## Navigation and Controls

- Required order: Dashboard, Policies AI, Michael Angelo, Missions, Agent Fleet,
  Repositories, Sandboxes, Approvals, APR Evidence, Artifacts, Infrastructure,
  Audit Log, Settings.
- Michael Angelo is the default route. Policies AI remains above it.
- Selected navigation has a purple translucent fill, purple leading rail, gold
  icon, and visible text label.
- Buttons have idle, hover, active, disabled, and focus-visible states. No
  success action is represented by color alone.
- Inputs use dark fill, gold idle border, purple focus border, and persistent
  semantic labels.

## Data and State Rules

- Real API data is rendered as returned.
- Missing integrations display `UNKNOWN`, `NOT CONNECTED`, `NOT CONFIGURED`,
  `NO DATA`, or named `OFFLINE` states.
- No fabricated metrics, conversations, decisions, workers, costs, or health.
- `COMPLETED` does not imply valid evidence; evidence validity is checked and
  presented independently.
- Zgredek is a Drift Guard contract, never an execution worker. Without a real
  backend it displays `ZGREDEK NOT CONNECTED`.

## Charts, Terminal, and Evidence

- Charts use only real points. With no history, render an axis/grid and a clear
  `NO HISTORICAL DATA` label.
- Terminal content is inserted with `textContent`; user/runtime strings never
  use `innerHTML`.
- Evidence displays exact commits, checks, artifacts, invalidation reasons, and
  an explicit valid/invalid/unknown banner.

## Motion

- Hover/focus transitions: 140-180 ms.
- View entrance: 220 ms opacity/translate, one restrained stagger per surface.
- Live pulse: 1.8 s, only for real running states.
- Respect `prefers-reduced-motion: reduce`; disable transform and looping glow.
- Never animate a fake pipeline transition.

## Responsive Lock

- `>= 1440`: full dense command-center composition.
- `1280-1439`: preserve sidebar and priority grid; compress secondary panels.
- `900-1279`: two-column content and reduced top metrics.
- `< 900`: sidebar becomes an accessible drawer; emergency controls remain in
  the sticky header.
- `< 640`: single-column panels, horizontally scrollable pipeline/tables,
  Michael composer and approvals remain reachable.

## Accessibility and Security

- Semantic `nav`, `main`, `section`, headings, tables, labels, and live regions.
- Keyboard-operable navigation and controls; visible `:focus-visible` ring.
- Status text always accompanies color.
- CSP-compatible local assets and scripts only.
- No unsafe HTML insertion, direct shell controls, unrestricted paths, or
  frontend-held credentials.

## Drift Guard Checks

The reusable Zgredek component reports:

- alignment state
- architecture lock version
- design lock version
- drift count
- last verification time
- blocked mission and evidence references when real data exists

Until a drift backend exists, all analysis fields are `UNKNOWN`, drift count is
not invented, and the visible state is `ZGREDEK NOT CONNECTED`.

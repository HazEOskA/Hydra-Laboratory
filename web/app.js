"use strict";

const NAV_ITEMS = [
  ["dashboard", "Dashboard", "◇"],
  ["policies-ai", "Policies AI", "⚖"],
  ["michael-angelo", "Michael Angelo", "Ψ"],
  ["missions", "Missions", "⌬"],
  ["agent-fleet", "Agent Fleet", "⎈"],
  ["repositories", "Repositories", "▱"],
  ["sandboxes", "Sandboxes", "⬡"],
  ["approvals", "Approvals", "✓"],
  ["apr-evidence", "APR Evidence", "◎"],
  ["artifacts", "Artifacts", "▦"],
  ["infrastructure", "Infrastructure", "⌘"],
  ["audit-log", "Audit Log", "≋"],
  ["settings", "Settings", "⚙"],
];

const ROUTE_TITLES = Object.fromEntries(NAV_ITEMS.map(([id, label]) => [id, label]));
const TERMINAL_STATES = new Set(["COMPLETED", "CANCELLED"]);
const ACTIVE_STATES = new Set([
  "QUEUED", "FACT_LOADING", "PLANNING", "PROVISIONING", "RUNNING",
  "VALIDATING", "REVIEWING", "BUILDING_EVIDENCE", "PR_READY",
]);
const APPROVAL_STATES = new Map([
  ["AWAITING_ARCHITECTURE_APPROVAL", "architecture"],
  ["AWAITING_HUMAN_APPROVAL", "human"],
]);

const dom = {
  nav: document.querySelector("#primary-nav"),
  main: document.querySelector("#main-content"),
  title: document.querySelector("#route-title"),
  metrics: document.querySelector("#header-metrics"),
  error: document.querySelector("#error-banner"),
  sidebar: document.querySelector("#sidebar"),
  scrim: document.querySelector("#sidebar-scrim"),
  menu: document.querySelector("#menu-button"),
  emergency: document.querySelector("#emergency-button"),
  emergencyDialog: document.querySelector("#emergency-dialog"),
  emergencyScope: document.querySelector("#emergency-scope"),
  confirmEmergency: document.querySelector("#confirm-emergency"),
};

const state = {
  route: "michael-angelo",
  health: null,
  backends: [],
  missions: [],
  details: new Map(),
  selectedMissionId: null,
  selectedNodeId: null,
  busy: false,
  loadedAt: null,
};

function el(tag, className, text, attrs = {}) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === false || value === null || value === undefined) continue;
    if (name === "disabled") node.disabled = Boolean(value);
    else if (name === "checked") node.checked = Boolean(value);
    else node.setAttribute(name, String(value));
  }
  return node;
}

function append(parent, ...children) {
  for (const child of children.flat(Infinity)) {
    if (child !== null && child !== undefined) parent.append(child);
  }
  return parent;
}

function iconText(glyph, label) {
  const wrap = el("span", "nav-icon", glyph, { "aria-hidden": "true" });
  wrap.title = label;
  return wrap;
}

function button(label, className, handler, options = {}) {
  const control = el("button", className, label, {
    type: options.type || "button",
    disabled: options.disabled,
    title: options.title,
    "aria-label": options.ariaLabel || label,
  });
  if (handler) control.addEventListener("click", handler);
  return control;
}

function statusTone(value) {
  const normalized = String(value || "UNKNOWN").toUpperCase().replaceAll("_", "-");
  if (["ONLINE", "PASS", "PASSED", "COMPLETED", "VALID", "READY"].includes(normalized)) return "ok";
  if (["RUNNING", "QUEUED", "FACT-LOADING", "PLANNING", "PROVISIONING", "VALIDATING", "REVIEWING", "BUILDING-EVIDENCE"].includes(normalized)) return "live";
  if (["FAILED", "INVALID", "OFFLINE", "BLOCKED", "CANCELLED"].includes(normalized)) return "danger";
  if (normalized.includes("AWAITING") || normalized === "MEDIUM" || normalized === "HIGH") return "warn";
  return "unknown";
}

function statusLabel(value, extra = "") {
  const text = value || "UNKNOWN";
  return el("span", `status-label status-${statusTone(text)} ${extra}`.trim(), String(text).replaceAll("_", " "));
}

function microLabel(text, tone = "") {
  return el("p", `micro-label ${tone}`.trim(), text);
}

function panel(title, content, options = {}) {
  const section = el(options.tag || "section", `panel ${options.className || ""}`.trim());
  const header = el("header", "panel-header");
  const headingWrap = el("div", "panel-heading");
  if (options.index) headingWrap.append(el("span", "panel-index", options.index));
  headingWrap.append(el(options.headingTag || "h2", "panel-title", title));
  if (options.subtitle) headingWrap.append(el("p", "panel-subtitle", options.subtitle));
  header.append(headingWrap);
  if (options.action) header.append(options.action);
  section.append(header);
  const body = el("div", `panel-body ${options.bodyClass || ""}`.trim());
  append(body, content);
  section.append(body);
  return section;
}

function art(path, alt, className = "module-art") {
  return el("img", className, null, { src: `/assets/illustrations/${path}`, alt, loading: "lazy" });
}

function unavailable(title, copy, code = "NOT CONNECTED") {
  const wrap = el("div", "unavailable-state");
  append(wrap, statusLabel(code), el("h3", "unavailable-title", title), el("p", "muted-copy", copy));
  return wrap;
}

function formatDate(value, includeTime = true) {
  if (!value) return "UNKNOWN";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "UNKNOWN";
  return new Intl.DateTimeFormat(undefined, includeTime
    ? { dateStyle: "medium", timeStyle: "short" }
    : { dateStyle: "medium" }).format(date);
}

function elapsed(startedAt, finishedAt) {
  if (!startedAt) return "NOT STARTED";
  const end = finishedAt ? new Date(finishedAt) : new Date();
  const ms = end - new Date(startedAt);
  if (!Number.isFinite(ms) || ms < 0) return "UNKNOWN";
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function shortSha(value) {
  return value ? String(value).slice(0, 10) : "UNKNOWN";
}

function missionProgress(mission) {
  const nodes = mission?.nodes || [];
  if (!nodes.length) return 0;
  const passed = nodes.filter((node) => ["PASSED", "SKIPPED"].includes(node.state)).length;
  return Math.round((passed / nodes.length) * 100);
}

async function api(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  const type = response.headers.get("content-type") || "";
  const payload = type.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    throw new Error(payload?.error?.message || `${response.status} ${response.statusText}`);
  }
  return payload;
}

function showError(error) {
  dom.error.textContent = error instanceof Error ? error.message : String(error);
  dom.error.hidden = false;
  window.setTimeout(() => { dom.error.hidden = true; }, 9000);
}

async function loadMissionDetails(missionId, force = false) {
  if (!missionId) return null;
  if (!force && state.details.has(missionId)) return state.details.get(missionId);
  const [mission, events, logs, artifacts, evidence] = await Promise.all([
    api(`/api/missions/${missionId}`),
    api(`/api/missions/${missionId}/events`),
    api(`/api/missions/${missionId}/logs`),
    api(`/api/missions/${missionId}/artifacts`),
    api(`/api/missions/${missionId}/evidence`),
  ]);
  const detail = {
    mission,
    events: events.events || [],
    logs: logs.logs || [],
    artifacts: artifacts.artifacts || [],
    evidence,
  };
  state.details.set(missionId, detail);
  const index = state.missions.findIndex((item) => item.mission_id === missionId);
  if (index >= 0) state.missions[index] = mission;
  return detail;
}

async function refreshData(options = {}) {
  if (state.busy) return;
  state.busy = true;
  try {
    const [health, backends, missions] = await Promise.all([
      api("/api/health"), api("/api/backends"), api("/api/missions"),
    ]);
    state.health = health;
    state.backends = backends.backends || [];
    state.missions = missions.missions || [];
    if (!state.selectedMissionId && state.missions[0]) state.selectedMissionId = state.missions[0].mission_id;
    if (state.selectedMissionId && !state.missions.some((item) => item.mission_id === state.selectedMissionId)) {
      state.selectedMissionId = state.missions[0]?.mission_id || null;
    }
    const visible = state.missions.slice(0, options.deep ? 12 : 4).map((mission) => mission.mission_id);
    await Promise.all(visible.map((id) => loadMissionDetails(id, true)));
    state.loadedAt = new Date().toISOString();
    render();
  } catch (error) {
    state.health = null;
    showError(error);
    render();
  } finally {
    state.busy = false;
  }
}

function buildNavigation() {
  dom.nav.replaceChildren();
  for (const [id, label, glyph] of NAV_ITEMS) {
    const link = el("a", "nav-link", null, { href: `#${id}`, "data-route": id });
    append(link, iconText(glyph, label), el("span", "nav-label", label));
    if (id === "approvals") {
      const count = state.missions.filter((mission) => APPROVAL_STATES.has(mission.state)).length;
      if (count) link.append(el("span", "nav-count", count, { "aria-label": `${count} pending approvals` }));
    }
    if (id === state.route) link.setAttribute("aria-current", "page");
    link.addEventListener("click", closeSidebar);
    dom.nav.append(link);
  }
}

function headerMetric(label, value, tone = "unknown") {
  const item = el("div", "header-metric");
  append(item, el("span", "header-metric-label", label), el("strong", `header-metric-value tone-${tone}`, value));
  return item;
}

function renderHeader() {
  dom.title.textContent = ROUTE_TITLES[state.route] || "Command Center";
  const active = state.missions.filter((mission) => ACTIVE_STATES.has(mission.state)).length;
  const queued = state.missions.filter((mission) => mission.state === "QUEUED").length;
  const approvals = state.missions.filter((mission) => APPROVAL_STATES.has(mission.state)).length;
  dom.metrics.replaceChildren(
    headerMetric("SYSTEM", state.health?.status === "ok" ? "ONLINE" : "OFFLINE", state.health?.status === "ok" ? "ok" : "danger"),
    headerMetric("ACTIVE", String(active), active ? "live" : "unknown"),
    headerMetric("QUEUED", String(queued), queued ? "warn" : "unknown"),
    headerMetric("AGENTS", state.backends.length ? String(state.backends.length) : "UNKNOWN", state.backends.length ? "ok" : "unknown"),
    headerMetric("APPROVALS", String(approvals), approvals ? "warn" : "unknown"),
    headerMetric("COST TODAY", "UNKNOWN", "unknown"),
  );
}

function pageIntro(kicker, title, copy, status) {
  const intro = el("header", "page-intro");
  const text = el("div", "page-intro-copy");
  append(text, microLabel(kicker), el("h2", "page-title", title), el("p", "page-summary", copy));
  append(intro, text, status || null);
  return intro;
}

function dataField(label, value, tone = "") {
  const field = el("div", "data-field");
  append(field, el("span", "data-label", label), el("strong", `data-value ${tone}`.trim(), value ?? "UNKNOWN"));
  return field;
}

function renderMichaelAngelo() {
  const view = el("div", "view michael-view");
  view.append(pageIntro(
    "PRIMARY ARCHITECT · MISSION COMPILER",
    "Michael Angelo",
    "The main conversational surface. Runtime messages are never simulated; this local slice exposes the connection contract and real mission context only.",
    statusLabel("MICHAEL ANGELO OFFLINE"),
  ));

  const layout = el("div", "michael-layout");
  const history = el("div", "conversation-list");
  append(history,
    button("New conversation", "primary-button full-width", null, { disabled: true, title: "Runtime not connected" }),
    microLabel("CONVERSATION HISTORY"),
    unavailable("No runtime history", "Conversation persistence is not connected to the local control-plane API.", "NO DATA"),
  );

  const chat = el("section", "chat-surface panel", null, { "aria-labelledby": "chat-title" });
  const chatHeader = el("header", "chat-header");
  const identity = el("div", "chat-identity");
  identity.append(art("michael-angelo-lens.webp", "Michael Angelo cybernetic Hydra lens", "chat-avatar"));
  const identityText = el("div");
  append(identityText, el("h2", null, "Michael Angelo", { id: "chat-title" }), el("p", null, "Architect · Planner · Primary interface"));
  append(identity, identityText);
  const runtime = el("div", "runtime-pills");
  append(runtime, statusLabel("OFFLINE"), statusLabel("MODEL UNKNOWN"));
  append(chatHeader, identity, runtime);

  const thread = el("div", "chat-thread", null, { role: "log", "aria-live": "polite" });
  const offline = el("div", "chat-offline-state");
  append(offline,
    art("michael-angelo-lens.webp", "", "chat-hero-art"),
    microLabel("CONNECTION STATE", "danger-text"),
    el("h3", null, "MICHAEL ANGELO OFFLINE"),
    el("p", null, "No callable Michael Angelo chat endpoint exists in this repository. Connect a reviewed runtime adapter before messages can be sent."),
    statusLabel("NO RESPONSE FABRICATED"),
  );
  thread.append(offline);

  const composer = el("form", "chat-composer");
  const label = el("label", "sr-only", "Message Michael Angelo", { for: "michael-composer" });
  const input = el("textarea", null, null, { id: "michael-composer", rows: "3", placeholder: "Michael Angelo runtime is not connected…", disabled: true });
  const actions = el("div", "composer-actions");
  append(actions, el("span", "composer-state", "NOT CONNECTED · INPUT DISABLED"), button("Stop", "danger-button", null, { disabled: true }), button("Send", "primary-button", null, { disabled: true }));
  append(composer, label, input, actions);
  append(chat, chatHeader, thread, composer);

  const context = el("aside", "michael-context");
  const selected = state.selectedMissionId ? state.details.get(state.selectedMissionId) : null;
  context.append(renderZgredekCard());
  const missionBody = selected
    ? [dataField("Mission", selected.mission.title), dataField("State", selected.mission.state), dataField("Repository", selected.mission.repository), button("Open mission", "secondary-button full-width", () => navigate("missions"))]
    : unavailable("No associated mission", "Compile or select a mission to expose real context here.", "NO DATA");
  context.append(panel("Mission context", missionBody, { index: "02" }));
  const eventBody = selected?.events?.length
    ? selected.events.slice(-4).reverse().map(renderCompactEvent)
    : unavailable("No mission events", "The event ledger will appear when a mission is selected.", "NO DATA");
  context.append(panel("Recent mission events", eventBody, { index: "03" }));

  append(layout, history, chat, context);
  append(view, layout);
  return view;
}

function renderZgredekCard() {
  const body = el("div", "zgredek-card");
  const hero = el("div", "zgredek-identity");
  append(hero, art("zgredek-observatory.webp", "Purple observatory eye representing Zgredek Drift Guard", "zgredek-art"), el("div", null, null));
  append(hero.lastChild, microLabel("DRIFT GUARD · DECISION KEEPER"), el("h3", null, "Zgredek"), statusLabel("ZGREDEK NOT CONNECTED"));
  append(body, hero,
    dataField("Alignment", "UNKNOWN"),
    dataField("Architecture lock", "MINION v0.1"),
    dataField("Design lock", "HYDRA UI v0.1"),
    dataField("Detected drift", "UNKNOWN"),
    dataField("Last verification", "NOT AVAILABLE"),
    el("p", "muted-copy", "No AI drift analysis is fabricated. This component is the reviewed UI contract only."),
  );
  return panel("Alignment watch", body, { className: "zgredek-panel", index: "01" });
}

function renderMetricCard(label, value, detail, tone = "unknown") {
  const card = el("article", "metric-card");
  append(card, el("span", "metric-label", label), el("strong", `metric-value tone-${tone}`, value), el("small", "metric-detail", detail));
  const plot = el("div", "empty-sparkline", null, { "aria-label": `${label}: no historical data` });
  plot.append(el("span", null, "NO HISTORY"));
  card.append(plot);
  return card;
}

function renderDashboard() {
  const view = el("div", "view dashboard-view");
  view.append(pageIntro("AUTONOMOUS ENGINEERING OPERATIONS", "HYDRA Command Center", "Real local mission orchestration with explicit integration boundaries. Unknown data remains unknown.", statusLabel(state.health?.status === "ok" ? "CONTROL PLANE ONLINE" : "CONTROL PLANE OFFLINE")));
  const grid = el("div", "dashboard-grid");

  const overview = el("div", "metric-grid");
  append(overview,
    renderMetricCard("CPU", "UNKNOWN", "HOST METRICS NOT CONNECTED"),
    renderMetricCard("RAM", "UNKNOWN", "HOST METRICS NOT CONNECTED"),
    renderMetricCard("DISK", "UNKNOWN", "HOST METRICS NOT CONNECTED"),
    renderMetricCard("NETWORK I/O", "UNKNOWN", "NO DATA SOURCE"),
  );
  grid.append(panel("System overview", overview, { className: "dash-overview", index: "01", subtitle: "Real host telemetry unavailable" }));

  grid.append(panel("Active missions", renderMissionTable(state.missions.slice(0, 6)), {
    className: "dash-missions", index: "02", action: button("View missions", "link-button", () => navigate("missions")),
  }));

  const maBody = el("div", "dashboard-michael");
  append(maBody, art("michael-angelo-lens.webp", "", "dashboard-michael-art"), statusLabel("MICHAEL ANGELO OFFLINE"), el("p", "muted-copy", "Primary architect runtime is not connected. No assistant response is simulated."), button("Open interface", "primary-button full-width", () => navigate("michael-angelo")));
  grid.append(panel("Michael Angelo", maBody, { className: "dash-michael", index: "03" }));

  const policies = el("div", "governance-summary");
  append(policies, art("policies-ai.webp", "", "panel-watermark"), statusLabel("POLICIES AI NOT CONNECTED"), el("h3", null, "Agent Co-Founder"), el("p", "muted-copy", "Strategy, budgets, risk thresholds and autonomy decisions have no runtime data source."), dataField("Latest decision", "NO DATA"), dataField("Risk policy", "UNKNOWN"), dataField("Budget limit", "NOT CONFIGURED"), button("Open governance", "secondary-button full-width", () => navigate("policies-ai")));
  grid.append(panel("Policies AI · Co-Founder", policies, { className: "dash-policies", index: "04" }));

  grid.append(panel("Agent fleet", renderFleetCompact(), { className: "dash-fleet", index: "05", action: button("View fleet", "link-button", () => navigate("agent-fleet")) }));
  grid.append(panel("Pending approvals", renderApprovalList(true), { className: "dash-approvals", index: "06", action: button("All approvals", "link-button", () => navigate("approvals")) }));
  grid.append(panel("APR evidence", renderAprSummary(), { className: "dash-apr", index: "07", action: button("Open evidence", "link-button", () => navigate("apr-evidence")) }));
  grid.append(panel("Recent events", renderRecentEvents(), { className: "dash-events", index: "08", action: button("Audit log", "link-button", () => navigate("audit-log")) }));
  grid.append(panel("Infrastructure", renderInfrastructureCompact(), { className: "dash-infra", index: "09", action: button("Inspect", "link-button", () => navigate("infrastructure")) }));

  const cost = el("div", "cost-empty");
  append(cost, dataField("Cost today", "UNKNOWN"), dataField("Tokens", "UNKNOWN"), dataField("Tracked missions", String(state.missions.length)), el("p", "muted-copy", "No usage or billing endpoint is configured."));
  grid.append(panel("Cost & usage", cost, { className: "dash-cost", index: "10" }));
  append(view, grid);
  return view;
}

function renderMissionTable(missions) {
  if (!missions.length) return unavailable("No missions", "Compile a mission from the Missions view.", "NO DATA");
  const table = el("div", "data-table mission-table", null, { role: "table", "aria-label": "Missions" });
  const head = el("div", "data-row data-head", null, { role: "row" });
  ["Mission", "State", "Progress", "Current stage", "Backend", "Elapsed"].forEach((label) => head.append(el("span", null, label, { role: "columnheader" })));
  table.append(head);
  for (const summary of missions) {
    const detail = state.details.get(summary.mission_id);
    const mission = detail?.mission || summary;
    const row = el("button", "data-row data-row-button", null, { type: "button", role: "row" });
    append(row,
      el("span", "mono", shortSha(mission.mission_id), { role: "cell" }),
      statusLabel(mission.state),
      el("span", "progress-cell", `${missionProgress(mission)}%`, { role: "cell" }),
      el("span", null, mission.current_node_id || "NOT STARTED", { role: "cell" }),
      el("span", null, mission.backend || "UNKNOWN", { role: "cell" }),
      el("span", null, elapsed(mission.started_at, mission.finished_at), { role: "cell" }),
    );
    row.addEventListener("click", () => selectMission(mission.mission_id));
    table.append(row);
  }
  return table;
}

function renderPoliciesAi() {
  const view = el("div", "view governance-view");
  view.append(pageIntro("AGENT CO-FOUNDER · GOVERNANCE", "Policies AI", "Strategy, prioritization, budgets, autonomy and risk must come from a reviewed Policies AI integration. This UI does not manufacture policy decisions.", statusLabel("POLICIES AI NOT CONNECTED")));
  const hero = el("section", "governance-hero panel");
  const artWrap = el("div", "governance-art");
  artWrap.append(art("policies-ai.webp", "Classical bust and cyber-serpents representing Policies AI governance"));
  const copy = el("div", "governance-hero-copy");
  append(copy, microLabel("STRATEGIC AUTHORITY"), el("h2", null, "Governance without fabricated certainty"), el("p", null, "Connect a real policy decision store before decisions, rationale, confidence, alternatives, budgets or thresholds can be displayed."), statusLabel("NO POLICY DATA"));
  append(hero, artWrap, copy);

  const grid = el("div", "governance-grid");
  const fields = [
    ["Strategic decisions", "NO DATA", "Decision history endpoint is not configured."],
    ["Autonomy policy", "UNKNOWN", "No policy source is connected."],
    ["Risk rules", "UNKNOWN", "Mission risk is classified, but global risk policy is absent."],
    ["Approval thresholds", "NOT CONFIGURED", "Existing mission gates remain authoritative."],
    ["Model routing", "UNKNOWN", "No Policies AI routing decision is exposed."],
    ["Budget limits", "NOT CONFIGURED", "No billing or budget contract exists."],
  ];
  for (const [title, value, copyText] of fields) {
    const body = el("div", "governance-module");
    append(body, statusLabel(value), el("p", "muted-copy", copyText), dataField("Rationale", "UNKNOWN"), dataField("Confidence", "UNKNOWN"), dataField("Rejected alternatives", "NO DATA"));
    grid.append(panel(title, body));
  }
  append(view, hero, grid, renderZgredekCard());
  return view;
}

function selectMission(missionId) {
  state.selectedMissionId = missionId;
  state.selectedNodeId = null;
  navigate("missions");
  loadMissionDetails(missionId, true).then(render).catch(showError);
}

function renderMissions() {
  const view = el("div", "view missions-view");
  view.append(pageIntro("MISSION ORCHESTRATION", "Missions", "Compile, gate, execute, validate and verify deterministic local missions through the existing control-plane API.", statusLabel(`${state.missions.length} RECORDED`)));
  const workbench = el("div", "mission-workbench");
  workbench.append(renderMissionRail());
  workbench.append(renderMissionDetail());
  append(view, workbench);
  return view;
}

function renderMissionRail() {
  const rail = el("aside", "mission-rail");
  const form = el("form", "mission-create-form panel", null, { id: "mission-create-form" });
  append(form,
    microLabel("NEW LOCAL MISSION"),
    el("h2", null, "Mission intake"),
    labelledInput("Mission name", "title", "Verify Hydra vertical slice", 120),
    labelledTextarea("Execution request", "request", "Implement and verify a controlled typed change in the safe fixture repository.", 5000),
    labelledInput("Repository", "repository", "fixture://hydra-safe-demo", 80, true),
  );
  const failure = el("label", "field-label", "Failure drill");
  const select = el("select", "field-control", null, { name: "failureMode" });
  select.append(el("option", null, "None", { value: "none" }), el("option", null, "Tests fail once", { value: "tests_once" }));
  failure.append(select);
  append(form, failure, button("Compile mission", "primary-button full-width", null, { ariaLabel: "Compile local mission", type: "submit" }));
  form.addEventListener("submit", handleCreateMission);
  rail.append(form);
  const list = el("div", "mission-rail-list panel");
  append(list, microLabel("MISSION LEDGER"));
  if (!state.missions.length) list.append(unavailable("No missions", "Compile the first deterministic mission.", "NO DATA"));
  for (const mission of state.missions) {
    const card = button("", `mission-list-card ${mission.mission_id === state.selectedMissionId ? "selected" : ""}`, () => selectMission(mission.mission_id), { ariaLabel: `Open mission ${mission.title}` });
    append(card, el("strong", null, mission.title), statusLabel(mission.state), el("small", "mono", shortSha(mission.mission_id)));
    list.append(card);
  }
  rail.append(list);
  return rail;
}

function labelledInput(labelText, name, value, maxLength, readOnly = false) {
  const label = el("label", "field-label", labelText);
  label.append(el("input", "field-control", null, { name, value, maxlength: maxLength, required: true, readonly: readOnly }));
  return label;
}

function labelledTextarea(labelText, name, value, maxLength) {
  const label = el("label", "field-label", labelText);
  const input = el("textarea", "field-control", null, { name, maxlength: maxLength, rows: "4", required: true });
  input.value = value;
  label.append(input);
  return label;
}

async function handleCreateMission(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    const mission = await api("/api/missions", {
      method: "POST",
      body: JSON.stringify({
        title: form.get("title"), request: form.get("request"), repository: form.get("repository"),
        backend: "deterministic-local", failureMode: form.get("failureMode"),
      }),
    });
    state.selectedMissionId = mission.mission_id;
    await refreshData({ deep: true });
  } catch (error) { showError(error); }
}

function renderMissionDetail() {
  if (!state.selectedMissionId) return panel("Mission detail", unavailable("No mission selected", "Choose or compile a mission.", "NO DATA"), { className: "mission-detail-empty" });
  const detail = state.details.get(state.selectedMissionId);
  if (!detail) {
    loadMissionDetails(state.selectedMissionId, true).then(render).catch(showError);
    return panel("Mission detail", unavailable("Loading mission", "Reading the durable mission ledger.", "LOADING"));
  }
  const mission = detail.mission;
  const wrap = el("section", "mission-detail");
  const hero = el("header", "mission-detail-hero panel");
  const copy = el("div");
  append(copy, microLabel(`MISSION ${shortSha(mission.mission_id)}`), el("h2", null, mission.title), el("p", "muted-copy", mission.request));
  const actions = el("div", "mission-actions");
  append(actions, ...missionActions(mission));
  append(hero, copy, actions);
  const facts = el("div", "mission-facts");
  append(facts,
    dataField("State", mission.state), dataField("Risk", mission.risk), dataField("Repository", mission.repository),
    dataField("Branch", mission.branch), dataField("Backend", mission.backend), dataField("Current node", mission.current_node_id || "NOT STARTED"),
    dataField("Base commit", shortSha(mission.base_commit)), dataField("Result commit", shortSha(mission.result_commit)),
  );
  wrap.append(hero, facts, renderPipeline(detail), renderMissionLower(detail));
  return wrap;
}

function missionActions(mission) {
  const actions = [];
  if (mission.state === "DRAFT") actions.push(button("Start execution", "primary-button", () => missionCommand(mission.mission_id, "start")));
  if (mission.state === "AWAITING_ARCHITECTURE_APPROVAL") actions.push(button("Approve architecture", "approval-button", () => missionApproval(mission.mission_id, "architecture")));
  if (mission.state === "AWAITING_HUMAN_APPROVAL") actions.push(button("Approve PR readiness", "approval-button", () => missionApproval(mission.mission_id, "human")));
  const failed = mission.nodes?.find((node) => node.state === "FAILED");
  if (mission.state === "FAILED" && failed) actions.push(button(`Retry ${failed.name}`, "primary-button", () => retryMissionNode(mission.mission_id, failed.node_id)));
  if (!TERMINAL_STATES.has(mission.state)) actions.push(button("Cancel", "danger-button", () => missionCommand(mission.mission_id, "cancel")));
  return actions;
}

async function missionCommand(missionId, command) {
  try {
    await api(`/api/missions/${missionId}/${command}`, { method: "POST" });
    state.details.delete(missionId);
    await refreshData({ deep: true });
  } catch (error) { showError(error); }
}

async function missionApproval(missionId, gate) {
  try {
    await api(`/api/missions/${missionId}/approvals`, { method: "POST", body: JSON.stringify({ gate }) });
    state.details.delete(missionId);
    await refreshData({ deep: true });
  } catch (error) { showError(error); }
}

async function retryMissionNode(missionId, nodeId) {
  try {
    await api(`/api/missions/${missionId}/nodes/${nodeId}/retry`, { method: "POST" });
    state.details.delete(missionId);
    await refreshData({ deep: true });
  } catch (error) { showError(error); }
}

function renderPipeline(detail) {
  const pipeline = el("div", "pipeline-track", null, { role: "list", "aria-label": "Mission pipeline" });
  for (const [index, node] of detail.mission.nodes.entries()) {
    const card = button("", `pipeline-node state-${statusTone(node.state)} ${node.node_id === (state.selectedNodeId || detail.mission.current_node_id) ? "current" : ""}`, () => {
      state.selectedNodeId = node.node_id;
      render();
    }, { ariaLabel: `${node.name}: ${node.state}` });
    append(card, el("span", "node-index", String(index + 1).padStart(2, "0")), el("strong", null, node.name), statusLabel(node.state), el("small", null, `Attempt ${node.attempt}`));
    pipeline.append(card);
  }
  return panel("Execution pipeline", pipeline, { className: "pipeline-panel", index: "01", subtitle: "Durable state · real transitions only" });
}

function renderMissionLower(detail) {
  const grid = el("div", "mission-lower-grid");
  const node = detail.mission.nodes.find((item) => item.node_id === (state.selectedNodeId || detail.mission.current_node_id)) || detail.mission.nodes[0];
  const nodeBody = node ? [
    dataField("State", node.state), dataField("Backend", node.backend), dataField("Dependencies", node.dependencies?.join(", ") || "NONE"),
    dataField("Started", formatDate(node.started_at)), dataField("Finished", formatDate(node.finished_at)), dataField("Validation", node.validation_result || "UNKNOWN"),
    el("p", "node-summary", node.summary || "No summary recorded."),
  ] : unavailable("No node", "Pipeline is unavailable.");
  grid.append(panel("Node inspector", nodeBody, { index: "02" }));
  grid.append(panel("Execution logs", renderLogs(detail.logs), { index: "03", className: "terminal-panel" }));
  grid.append(panel("Artifacts", renderArtifacts(detail.artifacts), { index: "04" }));
  grid.append(panel("APR evidence", renderEvidence(detail.evidence), { index: "05" }));
  return grid;
}

function renderLogs(logs) {
  if (!logs.length) return unavailable("No logs", "Execution output will appear here.", "NO DATA");
  const terminal = el("div", "terminal", null, { role: "log", "aria-label": "Execution logs" });
  for (const log of logs.slice(-80)) {
    const line = el("div", `terminal-line stream-${log.stream || "system"}`);
    append(line, el("time", null, formatDate(log.timestamp)), el("span", "mono terminal-node", log.node_id || "system"), el("pre", null, log.message));
    terminal.append(line);
  }
  return terminal;
}

function renderArtifacts(artifacts) {
  if (!artifacts.length) return unavailable("No artifacts", "Validated output will appear after execution.", "NO DATA");
  const list = el("div", "artifact-list");
  for (const artifact of artifacts) {
    const link = el("a", "artifact-card", null, { href: `/api/artifacts/${artifact.artifact_id}/content`, target: "_blank", rel: "noreferrer" });
    append(link, el("span", "artifact-icon", "▦", { "aria-hidden": "true" }), el("strong", null, artifact.name), el("small", null, artifact.kind), el("code", null, shortSha(artifact.sha256)));
    list.append(link);
  }
  return list;
}

function renderEvidence(evidence) {
  if (!evidence?.available) return unavailable("Evidence unavailable", "APR has not generated a bundle for this mission.", "NO DATA");
  const wrap = el("div", "evidence-card");
  const verdict = evidence.valid ? "COMMIT BINDING VALID" : "EVIDENCE INVALIDATED";
  append(wrap, statusLabel(verdict), dataField("Result commit", evidence.bundle?.resultCommit || "UNKNOWN"), dataField("Base commit", evidence.bundle?.baseCommit || "UNKNOWN"), dataField("Generated", formatDate(evidence.bundle?.generatedAt)));
  const checks = el("div", "check-grid");
  for (const [name, value] of Object.entries(evidence.bundle?.checks || {})) {
    const check = el("div", "check-item");
    append(check, el("span", null, name), statusLabel(value));
    checks.append(check);
  }
  wrap.append(checks);
  if (evidence.invalidReasons?.length) {
    const reasons = el("ul", "risk-list");
    evidence.invalidReasons.forEach((reason) => reasons.append(el("li", null, reason)));
    wrap.append(reasons);
  }
  return wrap;
}

function renderCompactEvent(event) {
  const item = el("article", "event-card");
  append(item, el("time", null, formatDate(event.timestamp)), el("strong", null, event.event_type || "EVENT"), el("p", null, event.message || `${event.previous_state || "UNKNOWN"} → ${event.next_state || "UNKNOWN"}`), el("code", null, event.commit_sha ? shortSha(event.commit_sha) : "NO COMMIT"));
  return item;
}

function renderFleetCompact() {
  if (!state.backends.length) return unavailable("No backends", "No execution backend is registered.", "NO DATA");
  const list = el("div", "compact-list");
  for (const backend of state.backends) {
    const row = el("div", "compact-row");
    append(row, el("span", "row-icon", "⎈"), el("div", "row-copy", null), statusLabel(backend.available ? "READY" : "UNKNOWN"));
    append(row.children[1], el("strong", null, backend.name || backend.id), el("small", null, backend.id || "UNKNOWN"));
    list.append(row);
  }
  return list;
}

function renderApprovalList(compact = false) {
  const pending = state.missions.filter((mission) => APPROVAL_STATES.has(mission.state));
  if (!pending.length) return unavailable("No pending approvals", "No mission gate currently requires OSA action.", "CLEAR");
  const list = el("div", "approval-list");
  for (const mission of pending.slice(0, compact ? 3 : 20)) {
    const gate = APPROVAL_STATES.get(mission.state);
    const card = el("article", "approval-card");
    const copy = el("div", "approval-copy");
    append(copy, microLabel(`${gate.toUpperCase()} GATE`), el("h3", null, mission.title), dataField("Mission", shortSha(mission.mission_id)), dataField("Risk", mission.risk || "UNKNOWN"), dataField("Evidence", gate === "human" ? "REQUIRED" : "NOT YET GENERATED"));
    const actions = el("div", "approval-actions");
    append(actions,
      button("Approve", "approval-button", () => missionApproval(mission.mission_id, gate)),
      button("Reject", "danger-button", null, { disabled: true, title: "Reject endpoint is not implemented" }),
      button("Request changes", "secondary-button", null, { disabled: true, title: "Request-changes endpoint is not implemented" }),
    );
    append(card, copy, actions);
    list.append(card);
  }
  return list;
}

function renderAprSummary() {
  const details = [...state.details.values()].filter((detail) => detail.evidence?.available);
  if (!details.length) return unavailable("No APR evidence", "Run a mission through evidence generation.", "NO DATA");
  const detail = details[0];
  const wrap = el("div", "apr-summary");
  append(wrap, art("apr-evidence.webp", "", "apr-emblem"), statusLabel(detail.evidence.valid ? "VALID" : "INVALID"), dataField("Mission", shortSha(detail.mission.mission_id)), dataField("Result commit", shortSha(detail.evidence.bundle?.resultCommit)), dataField("Event chain", detail.evidence.eventChain || "UNKNOWN"));
  return wrap;
}

function allRecentEvents() {
  return [...state.details.values()].flatMap((detail) => detail.events.map((event) => ({ ...event, missionTitle: detail.mission.title }))).sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)));
}

function renderRecentEvents(limit = 5) {
  const events = allRecentEvents().slice(0, limit);
  if (!events.length) return unavailable("No events", "Mission events will appear from the durable ledger.", "NO DATA");
  return events.map(renderCompactEvent);
}

function serviceRow(name, value, detail) {
  const row = el("div", "service-row");
  append(row, el("span", "service-sigil", "◉"), el("div", "row-copy", null), statusLabel(value));
  append(row.children[1], el("strong", null, name), el("small", null, detail));
  return row;
}

function renderInfrastructureCompact() {
  const list = el("div", "compact-list");
  append(list,
    serviceRow("Hydra Control Plane", state.health?.status === "ok" ? "ONLINE" : "OFFLINE", "Loopback HTTP API"),
    serviceRow("Policies AI", "NOT CONNECTED", "No governance endpoint"),
    serviceRow("Michael Angelo", "OFFLINE", "No chat runtime endpoint"),
    serviceRow("Zgredek Drift Guard", "NOT CONNECTED", "UI contract only"),
    serviceRow("Execution Backends", state.backends.length ? "READY" : "UNKNOWN", `${state.backends.length || 0} registered`),
    serviceRow("Event Store", state.health?.status === "ok" ? "ONLINE" : "UNKNOWN", "SQLite mission boundary"),
  );
  return list;
}

function renderAgentFleet() {
  const view = el("div", "view");
  view.append(pageIntro("EXECUTION WORKERS", "Agent Fleet", "Only execution backends registered by the real local API are shown.", statusLabel(state.backends.length ? `${state.backends.length} REGISTERED` : "NO BACKENDS")));
  const grid = el("div", "fleet-grid");
  if (!state.backends.length) grid.append(unavailable("No execution backend", "Backend discovery returned no workers.", "NO DATA"));
  for (const backend of state.backends) {
    const body = el("div", "fleet-card-body");
    append(body, art("openshell-claw.webp", "", "fleet-art"), statusLabel(backend.available ? "READY" : "UNKNOWN"), dataField("Identity", backend.name || backend.id), dataField("Backend", backend.id || "UNKNOWN"), dataField("Model", "UNKNOWN"), dataField("Current mission", "NO ACTIVE CLAIM"), dataField("Cost", "UNKNOWN"), dataField("Heartbeat", "NOT EXPOSED"), dataField("Capabilities", (backend.capabilities || []).join(", ") || "UNKNOWN"));
    grid.append(panel(backend.name || "Execution backend", body));
  }
  append(view, grid);
  return view;
}

function renderRepositories() {
  const view = el("div", "view");
  view.append(pageIntro("SOURCE CONTROL BOUNDARY", "Repositories", "Repositories are derived from recorded missions; there is no unrestricted repository browser.", statusLabel("SCOPED")));
  const repositories = [...new Set(state.missions.map((mission) => mission.repository).filter(Boolean))];
  const grid = el("div", "module-grid");
  if (!repositories.length) grid.append(unavailable("No repositories", "No mission has recorded a repository contract.", "NO DATA"));
  for (const repository of repositories) {
    const body = el("div");
    append(body, dataField("Repository", repository), dataField("Access", repository.startsWith("fixture://") ? "FIXTURE ONLY" : "UNKNOWN"), dataField("Host path", "NOT EXPOSED"), dataField("Remote", "UNKNOWN"));
    grid.append(panel(repository, body));
  }
  append(view, grid);
  return view;
}

function renderSandboxes() {
  const view = el("div", "view");
  view.append(pageIntro("ISOLATED EXECUTION", "Sandboxes", "The browser receives no host paths and no shell. Workspace status is visible only through mission state and artifacts.", statusLabel("PATHS PROTECTED")));
  const body = el("div", "feature-split");
  append(body, art("openshell-claw.webp", "Cybernetic claw representing isolated OpenShell execution"), el("div", null, null));
  append(body.lastChild, microLabel("SAFE EXECUTION CONTRACT"), el("h2", null, "Deterministic local fixture"), dataField("Repository input", "fixture://hydra-safe-demo"), dataField("Shell access", "NOT EXPOSED"), dataField("Host paths", "REJECTED"), dataField("Production credentials", "NOT PROVIDED"), el("p", "muted-copy", "Real session details remain server-side and artifacts are served by opaque IDs."));
  append(view, panel("Sandbox boundary", body));
  return view;
}

function renderApprovals() {
  const view = el("div", "view");
  const count = state.missions.filter((mission) => APPROVAL_STATES.has(mission.state)).length;
  view.append(pageIntro("OSA GATES · ACTOR ATTRIBUTED", "Approvals", "Architecture and human gates use the existing scoped approval endpoint. Unsupported reject/change actions remain disabled.", statusLabel(`${count} PENDING`)));
  append(view, renderApprovalList(false));
  return view;
}

function renderAprEvidenceView() {
  const view = el("div", "view");
  view.append(pageIntro("INDEPENDENT VERIFICATION", "APR Evidence", "Evidence validity is evaluated independently from mission completion and bound to exact commits and artifacts.", statusLabel("COMMIT BOUND")));
  const grid = el("div", "evidence-grid-view");
  const details = [...state.details.values()];
  if (!details.length) grid.append(unavailable("No mission evidence", "No mission details are loaded.", "NO DATA"));
  for (const detail of details) {
    grid.append(panel(detail.mission.title, renderEvidence(detail.evidence), { subtitle: shortSha(detail.mission.mission_id) }));
  }
  append(view, grid);
  return view;
}

function renderArtifactsView() {
  const view = el("div", "view");
  const artifacts = [...state.details.values()].flatMap((detail) => detail.artifacts);
  view.append(pageIntro("GENERATED OUTPUT", "Artifacts", "Artifact bytes are read through opaque IDs and verified against stored SHA-256 metadata.", statusLabel(`${artifacts.length} AVAILABLE`)));
  append(view, panel("Artifact registry", renderArtifacts(artifacts), { className: "artifact-registry" }));
  return view;
}

function renderInfrastructure() {
  const view = el("div", "view");
  view.append(pageIntro("LOCAL TRUST BOUNDARY", "Infrastructure", "This view reports only service states supported by the local API. It does not inspect or mutate the running Hydra installation.", statusLabel("LOOPBACK ONLY")));
  const split = el("div", "feature-split infra-feature");
  append(split, art("model-router-core.webp", "Gold and purple model-router core"), renderInfrastructureCompact());
  append(view, panel("Service topology", split), renderZgredekCard());
  return view;
}

function renderAuditLog() {
  const view = el("div", "view");
  const events = allRecentEvents();
  view.append(pageIntro("IMMUTABLE EVENT LEDGER", "Audit Log", "Hash-chained mission transitions with actor, state, artifacts and commit references.", statusLabel(`${events.length} LOADED`)));
  const list = el("div", "audit-list");
  if (!events.length) list.append(unavailable("No audit events", "Run a mission to populate the event ledger.", "NO DATA"));
  for (const event of events) {
    const row = el("article", "audit-row");
    append(row, el("time", null, formatDate(event.timestamp)), el("strong", null, event.event_type || "EVENT"), el("span", null, event.actor || "UNKNOWN"), el("span", null, event.missionTitle || shortSha(event.mission_id)), el("span", "mono", `${event.previous_state || "—"} → ${event.next_state || "—"}`), el("code", null, event.commit_sha ? shortSha(event.commit_sha) : "NO COMMIT"));
    list.append(row);
  }
  append(view, list);
  return view;
}

function renderSettings() {
  const view = el("div", "view");
  view.append(pageIntro("READ-ONLY LOCAL CONFIGURATION", "Settings", "This iteration exposes configuration facts but no production mutation controls.", statusLabel("LOCAL")));
  const grid = el("div", "module-grid");
  const runtime = el("div");
  append(runtime, dataField("Serving mode", "LOOPBACK HTTP"), dataField("Polling", "4 SECONDS"), dataField("Static assets", "LOCAL ONLY"), dataField("CSP", "SELF ONLY"), dataField("Actor", "OSA"));
  grid.append(panel("Runtime", runtime));
  const locks = el("div");
  append(locks, dataField("Architecture", "MINION CONTROL PLANE v0.1"), dataField("Design", "HYDRA UI v0.1"), dataField("Production deployment", "NOT AUTHORIZED"), dataField("Hermes runtime changes", "OUT OF SCOPE"));
  grid.append(panel("Locks", locks));
  append(view, grid);
  return view;
}

function renderRoute() {
  switch (state.route) {
    case "dashboard": return renderDashboard();
    case "policies-ai": return renderPoliciesAi();
    case "michael-angelo": return renderMichaelAngelo();
    case "missions": return renderMissions();
    case "agent-fleet": return renderAgentFleet();
    case "repositories": return renderRepositories();
    case "sandboxes": return renderSandboxes();
    case "approvals": return renderApprovals();
    case "apr-evidence": return renderAprEvidenceView();
    case "artifacts": return renderArtifactsView();
    case "infrastructure": return renderInfrastructure();
    case "audit-log": return renderAuditLog();
    case "settings": return renderSettings();
    default: return renderMichaelAngelo();
  }
}

function render() {
  buildNavigation();
  renderHeader();
  dom.main.replaceChildren(renderRoute());
}

function navigate(route) {
  window.location.hash = route;
  if (state.route === route) render();
}

function syncRoute() {
  const requested = window.location.hash.replace(/^#/, "");
  state.route = ROUTE_TITLES[requested] ? requested : "michael-angelo";
  if (!requested) history.replaceState(null, "", "#michael-angelo");
  render();
}

function openSidebar() {
  dom.sidebar.classList.add("open");
  dom.scrim.hidden = false;
  dom.menu.setAttribute("aria-expanded", "true");
}

function closeSidebar() {
  dom.sidebar.classList.remove("open");
  dom.scrim.hidden = true;
  dom.menu.setAttribute("aria-expanded", "false");
}

function prepareEmergencyDialog() {
  const cancellable = state.missions.filter((mission) => !TERMINAL_STATES.has(mission.state));
  dom.emergencyScope.replaceChildren();
  if (!cancellable.length) dom.emergencyScope.append(el("p", "muted-copy", "No cancellable local missions."));
  for (const mission of cancellable) dom.emergencyScope.append(el("div", "dialog-mission", `${shortSha(mission.mission_id)} · ${mission.title} · ${mission.state}`));
  dom.confirmEmergency.disabled = !cancellable.length;
  dom.emergencyDialog.showModal();
}

async function executeEmergencyStop() {
  const cancellable = state.missions.filter((mission) => !TERMINAL_STATES.has(mission.state));
  if (!cancellable.length) return;
  try {
    await Promise.all(cancellable.map((mission) => api(`/api/missions/${mission.mission_id}/cancel`, { method: "POST" })));
    state.details.clear();
    await refreshData({ deep: true });
  } catch (error) { showError(error); }
}

dom.menu.addEventListener("click", () => dom.sidebar.classList.contains("open") ? closeSidebar() : openSidebar());
dom.scrim.addEventListener("click", closeSidebar);
dom.emergency.addEventListener("click", prepareEmergencyDialog);
dom.emergencyDialog.addEventListener("close", () => {
  if (dom.emergencyDialog.returnValue === "confirm") executeEmergencyStop();
});
window.addEventListener("hashchange", syncRoute);
window.addEventListener("keydown", (event) => { if (event.key === "Escape") closeSidebar(); });

syncRoute();
refreshData({ deep: true });
window.setInterval(() => refreshData({ deep: false }), 4000);

"use strict";

// Operator dashboard (PL). Every control here calls a real control-plane
// endpoint. Anything without a backing endpoint renders as UNKNOWN /
// NIEPODŁĄCZONE and stays disabled — nothing on this surface is simulated.
// Features the canon requires but this build does not contain are declared
// here as first-class views. They render a MISSING FROM CURRENT BUILD card with
// the forensic result, never a fabricated status and never a working control.
const MISSING_FEATURES = {
  wallet: {
    title: "Portfel agentów / MoonPay",
    kicker: "ŚRODKI AGENTA · FUNDING · PŁATNOŚCI",
    scope: ["portfel / środki agenta", "funding", "płatności", "saldo", "historia transakcji", "limity i approvals"],
    lastSource: "config/tools.yaml → narzędzie `payments`",
    sourceDetail: "enabled: false · permission_default: RED · secrets: [] · health_check: \"false\"",
    quote: "Disabled. No payment capability is wired in this baseline.",
    branch: "obecny branch i main — identycznie",
    commit: "2e0ab66 (i cała historia wstecz)",
    recovery: "NIE DO ODZYSKANIA — nigdy nie zaimplementowane",
    blocker: "scripts/validate-godlayer.sh:91 wymusza, by narzędzie payments pozostało wyłączone. Zmiana wymaga jawnej decyzji OSA i nowelizacji D-005.",
    related: "Pokrewne: lib/hermes/revenue.py rozdziela kwoty prognozowane od otrzymanych, ale nie przechowuje środków ani nie wykonuje przelewów.",
  },
  mailbox: {
    title: "Skrzynka mailowa agentów",
    kicker: "INBOX · DRAFTY · WYSYŁKA ZA APPROVALEM",
    scope: ["inbox", "wiadomości", "drafty", "załączniki", "statusy", "wysyłka za approvalem OSA", "audit trail"],
    lastSource: "config/tools.yaml → narzędzie `email`",
    sourceDetail: "enabled: true · draft: GREEN · send: RED · secrets: [SMTP_URL] · health_check: \"hermes_email_probe\"",
    quote: "Outreach drafting. Sending always requires scoped OSA approval.",
    branch: "obecny branch i main — identycznie",
    commit: "f705340 (kontrakt narzędzia) — bez implementacji",
    recovery: "KONTRAKT ISTNIEJE, IMPLEMENTACJI BRAK",
    blocker: "Brak `hermes_email_probe`, zero użyć smtplib/imaplib. D-005 odracza messaging. validate-godlayer.sh sprawdza, że żadna automatyzacja nie może wysłać maila.",
    related: "Repozytorium HazEOskA/Inbox-worker-ai istnieje, ale jest PUSTE — zero commitów.",
  },
};

const NAV_ITEMS = [
  ["dashboard", "Centrum dowodzenia", "◇"],
  ["zgredek", "Zgredek", "◉"],
  ["projects", "Projekty", "▤"],
  ["missions", "Misje", "⌬"],
  ["queue", "Kolejka", "⋮"],
  ["michael-angelo", "Michael Angelo", "Ψ"],
  ["workers", "Workery / Minions", "⎈"],
  ["nvidia", "NVIDIA / NemoClaw", "▷"],
  ["wallet", "Portfel / MoonPay", "$"],
  ["mailbox", "Skrzynka mailowa", "✉"],
  ["sandboxes", "Sandboksy", "⬡"],
  ["models", "Modele", "◈"],
  ["budgets", "Budżety", "$"],
  ["approvals", "Zatwierdzenia", "✓"],
  ["health", "Zdrowie systemu", "♥"],
  ["logs", "Logi", "≡"],
  ["artifacts", "Artefakty", "▦"],
  ["evidence", "Dowody", "◎"],
  ["recovery", "Recovery", "↺"],
  ["genkit-lab", "Genkit Lab", "⚗"],
  ["windows-rtx", "Windows / RTX", "▣"],
  ["web3-lab", "Web3 Lab", "◈"],
  ["repositories", "Repozytoria", "▱"],
  ["policies-ai", "Polityki AI", "⚖"],
  ["audit-log", "Dziennik audytu", "≋"],
  ["settings", "Ustawienia", "⚙"],
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
const GATE_LABELS = { architecture: "BRAMKA ARCHITEKTURY", human: "BRAMKA LUDZKA" };

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
  route: "dashboard",
  health: null,
  fullHealth: null,
  backends: [],
  missions: [],
  projects: [],
  repositories: [],
  workers: [],
  models: [],
  budgets: { budgets: [], entries: [] },
  queue: { queue: [], scheduler: null },
  sandboxes: [],
  approvals: [],
  details: new Map(),
  diffs: new Map(),
  selectedMissionId: null,
  selectedNodeId: null,
  busy: false,
  loadedAt: null,
};

function el(tag, className, text, attrs = {}) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === false || value === null || value === undefined) continue;
    if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  return node;
}

function append(parent, ...children) {
  for (const child of children) {
    if (child === null || child === undefined) continue;
    if (Array.isArray(child)) parent.append(...child.filter(Boolean));
    else parent.append(child);
  }
  return parent;
}

function iconText(glyph, label) {
  const wrap = el("span", "nav-icon", glyph, { "aria-hidden": "true" });
  wrap.title = label;
  return wrap;
}

function button(label, className, handler, options = {}) {
  const node = el("button", className, label, {
    type: options.type || "button",
    disabled: options.disabled,
    title: options.title,
    "aria-label": options.ariaLabel,
  });
  if (handler) node.addEventListener("click", handler);
  return node;
}

function statusTone(value) {
  const text = String(value || "").toUpperCase();
  if (["PASSED", "COMPLETED", "PASS", "OK", "VALID", "AVAILABLE", "READY", "DONE", "GREEN"].includes(text)) return "ok";
  if (["RUNNING", "VALIDATING", "REVIEWING", "BUILDING_EVIDENCE", "PROVISIONING", "LEASED"].includes(text)) return "live";
  if (["BLOCKED", "PENDING", "QUEUED", "WAITING", "AWAITING_ARCHITECTURE_APPROVAL", "AWAITING_HUMAN_APPROVAL", "DEGRADED", "YELLOW"].includes(text)) return "warn";
  if (["FAILED", "FAIL", "CANCELLED", "INVALID", "UNAVAILABLE", "RED", "OFFLINE"].includes(text)) return "danger";
  return "unknown";
}

function statusLabel(value, extra = "") {
  return el("span", `status-label status-${statusTone(value)} ${extra}`.trim(), value ?? "UNKNOWN");
}

function microLabel(text, tone = "") {
  return el("p", `micro-label ${tone}`.trim(), text);
}

function panel(title, content, options = {}) {
  const section = el("section", `panel ${options.className || ""}`.trim());
  const header = el("header", "panel-header");
  const heading = el("div", "panel-heading");
  if (options.index) heading.append(el("span", "panel-index", options.index));
  heading.append(el("h2", "panel-title", title));
  header.append(heading);
  if (options.subtitle) header.append(el("small", "panel-subtitle", options.subtitle));
  if (options.action) header.append(options.action);
  section.append(header);
  const body = el("div", "panel-body");
  append(body, content);
  section.append(body);
  return section;
}

function art(path, alt, className = "module-art") {
  return el("img", className, null, { src: `/assets/illustrations/${path}`, alt, loading: "lazy" });
}

function unavailable(title, copy, code = "NIEPODŁĄCZONE") {
  const box = el("div", "unavailable-block");
  append(box, statusLabel(code), el("h3", null, title), el("p", "muted-copy", copy));
  return box;
}

function formatDate(value, includeTime = true) {
  if (!value) return "BRAK DANYCH";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "NIEZNANY";
  return includeTime ? date.toLocaleString("pl-PL") : date.toLocaleDateString("pl-PL");
}

function elapsed(startedAt, finishedAt) {
  if (!startedAt) return "NIE URUCHOMIONO";
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end)) return "NIEZNANY";
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

function shortSha(value) {
  if (!value) return "BRAK";
  return String(value).slice(0, 10);
}

function money(value, currency = "USD") {
  if (value === null || value === undefined) return "NIEZNANY";
  return `${Number(value).toFixed(4)} ${currency}`;
}

function missionProgress(mission) {
  const nodes = mission.nodes || [];
  if (!nodes.length) return 0;
  const done = nodes.filter((node) => node.state === "PASSED" || node.state === "SKIPPED").length;
  return Math.round((done / nodes.length) * 100);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", "X-Hydra-Actor": "OSA", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch { payload = null; }
  if (!response.ok) {
    const message = payload?.error?.message || `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return payload;
}

function showError(error) {
  dom.error.textContent = `BŁĄD: ${error.message || error}`;
  dom.error.hidden = false;
  window.setTimeout(() => { dom.error.hidden = true; }, 8000);
}

async function loadMissionDetails(missionId, force = false) {
  if (!force && state.details.has(missionId)) return state.details.get(missionId);
  const [mission, events, logs, artifacts, evidence, context] = await Promise.all([
    api(`/api/missions/${missionId}`),
    api(`/api/missions/${missionId}/events`).then((r) => r.events || []).catch(() => []),
    api(`/api/missions/${missionId}/logs`).then((r) => r.logs || []).catch(() => []),
    api(`/api/missions/${missionId}/artifacts`).then((r) => r.artifacts || []).catch(() => []),
    api(`/api/missions/${missionId}/evidence`).catch(() => null),
    api(`/api/context-packet/${missionId}`).catch(() => null),
  ]);
  const detail = { mission, events, logs, artifacts, evidence, context };
  state.details.set(missionId, detail);
  return detail;
}

async function refreshData(options = {}) {
  if (state.busy) return;
  state.busy = true;
  try {
    const safe = (promise, fallback) => promise.catch(() => fallback);
    const [health, fullHealth, backends, missions, registry, budgets, queue, sandboxes, approvals] = await Promise.all([
      api("/api/health"),
      safe(api("/api/health/full"), null),
      safe(api("/api/backends"), { backends: [] }),
      api("/api/missions"),
      safe(api("/api/registry"), { projects: [], repositories: [], workers: [], models: [] }),
      safe(api("/api/budgets"), { budgets: [], entries: [] }),
      safe(api("/api/queue"), { queue: [], scheduler: null }),
      safe(api("/api/sandboxes"), { sandboxes: [] }),
      safe(api("/api/approvals"), { approvals: [] }),
    ]);
    state.health = health;
    state.fullHealth = fullHealth;
    state.backends = backends.backends || [];
    state.missions = missions.missions || [];
    state.projects = registry.projects || [];
    state.repositories = registry.repositories || [];
    state.workers = registry.workers || [];
    state.models = registry.models || [];
    state.budgets = budgets;
    state.queue = queue;
    state.sandboxes = sandboxes.sandboxes || [];
    state.approvals = approvals.approvals || [];
    if (!state.selectedMissionId && state.missions[0]) state.selectedMissionId = state.missions[0].mission_id;
    if (state.selectedMissionId && !state.missions.some((item) => item.mission_id === state.selectedMissionId)) {
      state.selectedMissionId = state.missions[0]?.mission_id || null;
    }
    const visible = state.missions.slice(0, options.deep ? 12 : 4).map((mission) => mission.mission_id);
    await Promise.all(visible.map((id) => loadMissionDetails(id, true).catch(() => null)));
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
      if (count) link.append(el("span", "nav-count", count, { "aria-label": `${count} oczekujących zatwierdzeń` }));
    }
    if (id === "queue") {
      const waiting = (state.queue.queue || []).filter((entry) => entry.status === "WAITING").length;
      if (waiting) link.append(el("span", "nav-count", waiting, { "aria-label": `${waiting} w kolejce` }));
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
  dom.title.textContent = ROUTE_TITLES[state.route] || "Centrum dowodzenia";
  const active = state.missions.filter((mission) => ACTIVE_STATES.has(mission.state)).length;
  const waiting = (state.queue.queue || []).filter((entry) => entry.status === "WAITING").length;
  const approvals = state.missions.filter((mission) => APPROVAL_STATES.has(mission.state)).length;
  const availableWorkers = state.workers.filter((w) => w.availability === "AVAILABLE").length;
  const budget = (state.budgets.budgets || [])[0];
  dom.metrics.replaceChildren(
    headerMetric("SYSTEM", state.health?.status === "ok" ? "ONLINE" : "OFFLINE", state.health?.status === "ok" ? "ok" : "danger"),
    headerMetric("AKTYWNE", String(active), active ? "live" : "unknown"),
    headerMetric("W KOLEJCE", String(waiting), waiting ? "warn" : "unknown"),
    headerMetric("WORKERY", availableWorkers ? `${availableWorkers}/${state.workers.length}` : "0", availableWorkers ? "ok" : "danger"),
    headerMetric("ZATWIERDZENIA", String(approvals), approvals ? "warn" : "unknown"),
    headerMetric("KOSZT", budget ? money(budget.spent_amount, budget.currency) : "NIEZNANY", budget ? "ok" : "unknown"),
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
  append(field, el("span", "data-label", label), el("strong", `data-value ${tone}`.trim(), value ?? "NIEZNANY"));
  return field;
}

function simpleTable(headers, rows, ariaLabel) {
  const table = el("div", "data-table", null, { role: "table", "aria-label": ariaLabel });
  const head = el("div", "data-row data-head", null, { role: "row" });
  headers.forEach((label) => head.append(el("span", null, label, { role: "columnheader" })));
  table.append(head);
  for (const cells of rows) {
    const row = el("div", "data-row", null, { role: "row" });
    for (const cell of cells) {
      if (cell instanceof Node) row.append(cell);
      else row.append(el("span", null, cell ?? "—", { role: "cell" }));
    }
    table.append(row);
  }
  return table;
}

// ---------------------------------------------------------------- Michael Angelo

function renderMichaelAngelo() {
  const view = el("div", "view michael-view");
  view.append(pageIntro(
    "GŁÓWNY ARCHITEKT · KOMPILATOR MISJI",
    "Michael Angelo",
    "Execution plane misji kodowych. Warstwa czatu nie jest podłączona do żadnego runtime'u i nie symuluje odpowiedzi — realne jest zlecanie i wykonanie misji poniżej.",
    statusLabel("CZAT NIEPODŁĄCZONY"),
  ));

  const layout = el("div", "michael-layout");

  const history = el("div", "conversation-list");
  append(history,
    microLabel("ZLECENIE MISJI KODOWEJ"),
    renderMissionIntakeForm(),
  );

  const chat = el("section", "chat-surface panel", null, { "aria-labelledby": "chat-title" });
  const chatHeader = el("header", "chat-header");
  const identity = el("div", "chat-identity");
  identity.append(art("michael-angelo-lens.webp", "Cybernetyczna soczewka Hydry — Michael Angelo", "chat-avatar"));
  const identityText = el("div");
  append(identityText, el("h2", null, "Michael Angelo", { id: "chat-title" }), el("p", null, "Architekt · Planista · Interfejs główny"));
  append(identity, identityText);
  const runtime = el("div", "runtime-pills");
  const route = state.models.find((m) => m.availability === "AVAILABLE");
  append(runtime, statusLabel("CZAT OFFLINE"), statusLabel(route ? `MODEL ${route.model_id}` : "MODEL NIEZNANY"));
  append(chatHeader, identity, runtime);

  const thread = el("div", "chat-thread", null, { role: "log", "aria-live": "polite" });
  const selected = state.selectedMissionId ? state.details.get(state.selectedMissionId) : null;
  if (selected) {
    thread.append(renderMissionExecutionPanel(selected));
  } else {
    const offline = el("div", "chat-offline-state");
    append(offline,
      art("michael-angelo-lens.webp", "", "chat-hero-art"),
      microLabel("STAN POŁĄCZENIA", "danger-text"),
      el("h3", null, "BRAK WYBRANEJ MISJI"),
      el("p", null, "Zleć misję kodową po lewej stronie albo wybierz istniejącą, aby zobaczyć realne wykonanie."),
      statusLabel("ŻADNA ODPOWIEDŹ NIE JEST FABRYKOWANA"),
    );
    thread.append(offline);
  }

  const composer = el("form", "chat-composer");
  const label = el("label", "sr-only", "Wiadomość do Michael Angelo", { for: "michael-composer" });
  const input = el("textarea", null, null, { id: "michael-composer", rows: "3", placeholder: "Runtime czatu Michael Angelo nie jest podłączony…", disabled: true });
  const actions = el("div", "composer-actions");
  append(actions,
    el("span", "composer-state", "NIEPODŁĄCZONE · WEJŚCIE ZABLOKOWANE"),
    button("Zatrzymaj", "danger-button", null,
      { disabled: true, title: "Brak runtime'u czatu Michael Angelo — nie ma czego zatrzymać" }),
    button("Wyślij", "primary-button", null,
      { disabled: true, title: "Brak wywoływalnego endpointu czatu; żadna odpowiedź nie jest fabrykowana" }));
  append(composer, label, input, actions);
  append(chat, chatHeader, thread, composer);

  const context = el("aside", "michael-context");
  context.append(renderZgredekCard());
  const missionBody = selected
    ? [
      dataField("Misja", selected.mission.title),
      dataField("Stan", selected.mission.state),
      dataField("Repozytorium", selected.mission.repository),
      dataField("Worker", selected.mission.backend),
      button("Otwórz w Misjach", "secondary-button full-width", () => navigate("missions")),
    ]
    : unavailable("Brak powiązanej misji", "Zleć lub wybierz misję, aby zobaczyć realny kontekst.", "BRAK DANYCH");
  context.append(panel("Kontekst misji", missionBody, { index: "02" }));
  const eventBody = selected?.events?.length
    ? selected.events.slice(-4).reverse().map(renderCompactEvent)
    : unavailable("Brak zdarzeń misji", "Rejestr zdarzeń pojawi się po wybraniu misji.", "BRAK DANYCH");
  context.append(panel("Ostatnie zdarzenia misji", eventBody, { index: "03" }));

  append(layout, history, chat, context);
  append(view, layout);
  return view;
}

function renderMissionIntakeForm() {
  const form = el("form", "mission-create-form panel", null, { id: "mission-create-form" });
  append(form,
    el("h2", null, "Nowa misja kodowa"),
    labelledInput("Nazwa misji", "title", "Weryfikacja pionowego wycinka Hydry", 120),
    labelledTextarea("Opis zadania", "request", "Zaimplementuj i zweryfikuj kontrolowaną zmianę w bezpiecznym repozytorium fixture.", 5000),
  );

  const repoLabel = el("label", "field-label", "Repozytorium");
  const repoSelect = el("select", "field-control", null, { name: "repository" });
  const executable = state.repositories.filter((r) => r.executable);
  if (!executable.length) {
    repoSelect.append(el("option", null, "fixture://hydra-safe-demo", { value: "fixture://hydra-safe-demo" }));
  }
  for (const repo of executable) {
    repoSelect.append(el("option", null, `${repo.slug} (${repo.uri})`, { value: repo.uri }));
  }
  repoLabel.append(repoSelect);
  append(form, repoLabel);

  append(form, labelledInput("Branch bazowy", "baseBranch", "main", 100));
  append(form, labelledTextarea("Kryteria akceptacji (jedno na linię)", "acceptanceCriteria", "Zmiana jest deterministyczna\nIstniejące API pozostaje bez zmian", 2000, false));
  append(form, labelledTextarea("Wymagane testy (jeden na linię)", "requiredTests", "test_app.py", 1000, false));

  const workerLabel = el("label", "field-label", "Worker");
  const workerSelect = el("select", "field-control", null, { name: "worker" });
  workerSelect.append(el("option", null, "AUTO (pierwszy dostępny)", { value: "AUTO" }));
  for (const worker of state.workers) {
    const disabled = worker.availability !== "AVAILABLE";
    workerSelect.append(el("option", null, `${worker.name} — ${worker.availability}`, { value: worker.workerId, disabled }));
  }
  workerLabel.append(workerSelect);
  append(form, workerLabel);

  const blueprintLabel = el("label", "field-label", "Blueprint");
  const blueprintSelect = el("select", "field-control", null, { name: "blueprint" });
  blueprintSelect.append(
    el("option", null, "Standardowa misja kodowa", { value: "standard-coding-mission" }),
    el("option", null, "Tylko jakość", { value: "quality-only" }),
  );
  blueprintLabel.append(blueprintSelect);
  append(form, blueprintLabel);

  const riskLabel = el("label", "field-label", "Poziom ryzyka (może tylko podnieść)");
  const riskSelect = el("select", "field-control", null, { name: "riskLevel" });
  ["LOW", "MEDIUM", "HIGH", "CRITICAL"].forEach((level) => riskSelect.append(el("option", null, level, { value: level })));
  riskSelect.value = "LOW";
  riskLabel.append(riskSelect);
  append(form, riskLabel);

  append(form, labelledInput("Budżet misji (USD)", "budgetLimit", "5", 10));
  append(form, labelledInput("Timeout (sekundy)", "timeoutSeconds", "600", 10));
  append(form, labelledInput("Priorytet kolejki (1 = najwyższy)", "priority", "100", 10));

  const failure = el("label", "field-label", "Próba awarii (drill)");
  const select = el("select", "field-control", null, { name: "failureMode" });
  select.append(el("option", null, "Brak", { value: "none" }), el("option", null, "Testy padają raz", { value: "tests_once" }));
  failure.append(select);
  append(form, failure, button("Zleć misję", "primary-button full-width", null, { ariaLabel: "Zleć misję kodową", type: "submit" }));
  form.addEventListener("submit", handleCreateMission);
  return form;
}

function renderMissionExecutionPanel(detail) {
  const mission = detail.mission;
  const wrap = el("div", "mission-execution");
  const header = el("div", "mission-execution-header");
  append(header, el("h3", null, mission.title), statusLabel(mission.state));
  wrap.append(header);

  const facts = el("div", "mission-facts");
  append(facts,
    dataField("Worker", mission.backend),
    dataField("Sandbox", mission.workspace ? "IZOLOWANY" : "NIEUTWORZONY"),
    dataField("Postęp", `${missionProgress(mission)}%`),
    dataField("Czas", elapsed(mission.started_at, mission.finished_at)),
    dataField("Commit bazowy", shortSha(mission.base_commit)),
    dataField("Commit wynikowy", shortSha(mission.result_commit)),
  );
  wrap.append(facts);

  const actions = el("div", "mission-actions");
  append(actions, ...missionActions(mission));
  wrap.append(actions);

  wrap.append(renderPipeline(detail));
  const diff = state.diffs.get(mission.mission_id);
  if (diff) {
    const pre = el("pre", "terminal diff-view", diff.diff || "BRAK DIFFU");
    wrap.append(panel("Git diff", pre, { index: "06" }));
  }
  return wrap;
}

function renderZgredekCard() {
  const zg = state.fullHealth?.zgredek;
  const ctx = state.selectedMissionId ? state.details.get(state.selectedMissionId)?.context : null;
  const packet = ctx?.packet;
  const body = el("div", "zgredek-card");
  const hero = el("div", "zgredek-identity");
  append(hero, art("zgredek-observatory.webp", "Purpurowe oko obserwatorium — Zgredek Drift Guard", "zgredek-art"), el("div", null, null));
  append(hero.lastChild, microLabel("DRIFT GUARD · STRAŻNIK DECYZJI"), el("h3", null, "Zgredek"), statusLabel(zg?.connected ? "PODŁĄCZONY" : "ZGREDEK NIEPODŁĄCZONY"));
  append(body, hero,
    dataField("Adapter", zg?.adapter || "UNKNOWN"),
    dataField("Context packet", ctx ? (ctx.available ? (ctx.valid ? "WAŻNY" : "NIEWAŻNY") : "BRAK") : (zg?.contextPacket || "UNKNOWN")),
    dataField("Wykrywanie driftu", ctx?.drift?.status || zg?.driftDetection || "UNKNOWN"),
    dataField("Schemat packetu", packet?.schemaVersion || "—"),
    dataField("SHA-256 packetu", packet?.sha256 ? shortSha(packet.sha256) : "—"),
    dataField("Architecture locks", packet ? String((packet.architectureLocks || []).length) : "—"),
    dataField("Zatwierdzone decyzje", packet ? String((packet.acceptedDecisions || []).length) : "—"),
    dataField("Ownership", packet?.ownership?.status || "UNKNOWN"),
    dataField("Zatwierdzenie", ctx?.approval?.status || "—"),
    dataField("Zatwierdził", ctx?.approval?.approvedBy || "—"),
  );
  if (ctx?.available && ctx.valid && !ctx.approval?.approved) {
    body.append(button("Zatwierdź context packet (OSA)", "approval-button full-width",
      () => approveContextPacket(state.selectedMissionId, packet?.sha256)));
  }
  if (ctx?.invalidReasons?.length) {
    const reasons = el("ul", "risk-list");
    ctx.invalidReasons.forEach((r) => reasons.append(el("li", null, r)));
    append(body, microLabel("POWODY ODMOWY", "danger-text"), reasons);
  }
  if (ctx?.drift?.findings?.length) {
    const findings = el("ul", "risk-list");
    ctx.drift.findings.forEach((f) => findings.append(el("li", null, `${f.kind}: ${f.path}`)));
    append(body, microLabel("WYKRYTY DRIFT", "danger-text"), findings);
  }
  body.append(el("p", "muted-copy", zg?.reason || "Zgredek przygotowuje i zatwierdza kontekst oraz wykrywa drift. Nie koduje, nie uruchamia workera i nie wdraża."));
  return panel("Nadzór zgodności", body, { className: "zgredek-panel", index: "01" });
}

function renderMetricCard(label, value, detail, tone = "unknown") {
  const card = el("article", "metric-card");
  append(card, el("span", "metric-label", label), el("strong", `metric-value tone-${tone}`, value), el("small", "metric-detail", detail));
  const plot = el("div", "empty-sparkline", null, { "aria-label": `${label}: brak danych historycznych` });
  plot.append(el("span", null, "BRAK HISTORII"));
  card.append(plot);
  return card;
}

// ---------------------------------------------------------------- Centrum dowodzenia

function renderDashboard() {
  const view = el("div", "view dashboard-view");
  const health = state.fullHealth;
  view.append(pageIntro(
    "AUTONOMICZNE OPERACJE INŻYNIERYJNE",
    "Centrum dowodzenia HYDRA",
    "Realna lokalna orkiestracja misji z jawnymi granicami integracji. To, co nieznane, pozostaje nieznane.",
    statusLabel(health?.status === "OK" ? "CONTROL PLANE OK" : health?.status || "CONTROL PLANE OFFLINE"),
  ));
  const grid = el("div", "dashboard-grid");

  const overview = el("div", "metric-grid");
  const missions = health?.missions;
  append(overview,
    renderMetricCard("MISJE AKTYWNE", missions ? String(missions.active) : "NIEZNANE", "Z rejestru control plane", missions?.active ? "live" : "unknown"),
    renderMetricCard("ZAKOŃCZONE", missions ? String(missions.completed) : "NIEZNANE", "Stan COMPLETED", "ok"),
    renderMetricCard("NIEUDANE", missions ? String(missions.failed) : "NIEZNANE", "Stan FAILED", missions?.failed ? "danger" : "unknown"),
    renderMetricCard("WORKERY", `${state.workers.filter((w) => w.availability === "AVAILABLE").length}/${state.workers.length}`, "Dostępne / zadeklarowane", "ok"),
  );
  grid.append(panel("Przegląd systemu", overview, { className: "dash-overview", index: "01", subtitle: "Telemetria hosta niepodłączona" }));

  grid.append(panel("Aktywne misje", renderMissionTable(state.missions.slice(0, 6)), {
    className: "dash-missions", index: "02", action: button("Zobacz misje", "link-button", () => navigate("missions")),
  }));

  const maBody = el("div", "dashboard-michael");
  append(maBody, art("michael-angelo-lens.webp", "", "dashboard-michael-art"), statusLabel("EXECUTION PLANE AKTYWNY"), el("p", "muted-copy", "Warstwa czatu nie jest podłączona, ale zlecanie i wykonanie misji kodowych działa realnie."), button("Otwórz interfejs", "primary-button full-width", () => navigate("michael-angelo")));
  grid.append(panel("Michael Angelo", maBody, { className: "dash-michael", index: "03" }));

  const queueBody = el("div");
  const sched = state.queue.scheduler;
  append(queueBody,
    dataField("Scheduler", sched?.running ? "DZIAŁA" : "ZATRZYMANY"),
    dataField("Oczekujące", String(sched?.waiting ?? 0)),
    dataField("Wydzierżawione", String(sched?.leased ?? 0)),
    dataField("Równoległość", String(sched?.maxConcurrent ?? "NIEZNANA")),
    button("Otwórz kolejkę", "secondary-button full-width", () => navigate("queue")),
  );
  grid.append(panel("Kolejka i scheduler", queueBody, { className: "dash-policies", index: "04" }));

  grid.append(panel("Workery / Minions", renderFleetCompact(), { className: "dash-fleet", index: "05", action: button("Zobacz flotę", "link-button", () => navigate("workers")) }));
  grid.append(panel("Oczekujące zatwierdzenia", renderApprovalList(true), { className: "dash-approvals", index: "06", action: button("Wszystkie", "link-button", () => navigate("approvals")) }));
  grid.append(panel("Dowody APR", renderAprSummary(), { className: "dash-apr", index: "07", action: button("Otwórz dowody", "link-button", () => navigate("evidence")) }));
  grid.append(panel("Ostatnie zdarzenia", renderRecentEvents(), { className: "dash-events", index: "08", action: button("Dziennik audytu", "link-button", () => navigate("audit-log")) }));
  grid.append(panel("Infrastruktura", renderInfrastructureCompact(), { className: "dash-infra", index: "09", action: button("Sprawdź", "link-button", () => navigate("health")) }));

  const cost = el("div", "cost-empty");
  const budget = (state.budgets.budgets || [])[0];
  append(cost,
    dataField("Wydano", budget ? money(budget.spent_amount, budget.currency) : "NIEZNANE"),
    dataField("Limit", budget ? money(budget.limit_amount, budget.currency) : "NIESKONFIGUROWANY"),
    dataField("Pozostało", budget ? money(budget.remaining_amount, budget.currency) : "NIEZNANE"),
    dataField("Śledzone misje", String(state.missions.length)),
    button("Otwórz budżety", "secondary-button full-width", () => navigate("budgets")),
  );
  grid.append(panel("Koszty i zużycie", cost, { className: "dash-cost", index: "10" }));
  append(view, grid);
  return view;
}

function renderMissionTable(missions) {
  if (!missions.length) return unavailable("Brak misji", "Zleć misję w widoku Michael Angelo.", "BRAK DANYCH");
  const table = el("div", "data-table mission-table", null, { role: "table", "aria-label": "Misje" });
  const head = el("div", "data-row data-head", null, { role: "row" });
  ["Misja", "Stan", "Postęp", "Bieżący etap", "Worker", "Czas"].forEach((label) => head.append(el("span", null, label, { role: "columnheader" })));
  table.append(head);
  for (const summary of missions) {
    const detail = state.details.get(summary.mission_id);
    const mission = detail?.mission || summary;
    const row = el("button", "data-row data-row-button", null, { type: "button", role: "row" });
    append(row,
      el("span", "mono", shortSha(mission.mission_id), { role: "cell" }),
      statusLabel(mission.state),
      el("span", "progress-cell", `${missionProgress(mission)}%`, { role: "cell" }),
      el("span", null, mission.current_node_id || "NIE URUCHOMIONO", { role: "cell" }),
      el("span", null, mission.backend || "NIEZNANY", { role: "cell" }),
      el("span", null, elapsed(mission.started_at, mission.finished_at), { role: "cell" }),
    );
    row.addEventListener("click", () => selectMission(mission.mission_id));
    table.append(row);
  }
  return table;
}

// ---------------------------------------------------------------- Projekty

function renderProjects() {
  const view = el("div", "view");
  view.append(pageIntro(
    "REJESTR PROJEKTÓW · POWIERZCHNIE WYKONAWCZE",
    "Projekty",
    "Kanoniczne powierzchnie wykonawcze wraz z uprawnieniami GREEN / YELLOW / RED. Web3 Lab pozostaje odseparowany od standardowego execution plane.",
    statusLabel(`${state.projects.length} ZAREJESTROWANYCH`),
  ));
  const grid = el("div", "module-grid");
  if (!state.projects.length) grid.append(unavailable("Brak projektów", "Rejestr projektów jest pusty.", "BRAK DANYCH"));
  for (const project of state.projects) {
    const repos = state.repositories.filter((r) => r.project_key === project.key);
    const body = el("div");
    append(body,
      statusLabel(project.permission),
      el("p", "muted-copy", project.description || "Brak opisu."),
      dataField("Klucz", project.key),
      dataField("Powierzchnia", project.surface),
      dataField("Uprawnienie", project.permission),
      dataField("Repozytoria", String(repos.length)),
      dataField("Wykonywalne", String(repos.filter((r) => r.executable).length)),
    );
    if (project.surface === "WEB3_LAB") {
      body.append(el("p", "muted-copy", "IZOLACJA: brak dostępu ze standardowego execution plane."));
    }
    grid.append(panel(project.name, body));
  }
  append(view, grid);
  return view;
}

// ---------------------------------------------------------------- Kolejka

function renderQueue() {
  const view = el("div", "view");
  const sched = state.queue.scheduler;
  view.append(pageIntro(
    "TRWAŁA KOLEJKA · SCHEDULER",
    "Kolejka",
    "Kolejka żyje w SQLite, nie w pamięci. Restart nie gubi zamiaru misji — wydzierżawione wpisy wracają do stanu WAITING.",
    statusLabel(sched?.running ? "SCHEDULER DZIAŁA" : "SCHEDULER ZATRZYMANY"),
  ));

  const status = el("div", "mission-facts");
  append(status,
    dataField("Stan", sched?.running ? "DZIAŁA" : "ZATRZYMANY"),
    dataField("Interwał", sched ? `${sched.intervalSeconds}s` : "NIEZNANY"),
    dataField("Maks. równolegle", String(sched?.maxConcurrent ?? "NIEZNANE")),
    dataField("Oczekujące", String(sched?.waiting ?? 0)),
    dataField("Wydzierżawione", String(sched?.leased ?? 0)),
    dataField("Zakończone", String(sched?.done ?? 0)),
    dataField("Nieudane", String(sched?.failed ?? 0)),
  );
  view.append(panel("Stan schedulera", status, { index: "01" }));

  const entries = state.queue.queue || [];
  const rows = entries.map((entry) => [
    el("span", "mono", shortSha(entry.mission_id), { role: "cell" }),
    entry.title || "—",
    statusLabel(entry.status),
    String(entry.priority),
    statusLabel(entry.mission_state),
    String(entry.attempts),
    formatDate(entry.enqueued_at),
    entry.last_error || "—",
  ]);
  const body = entries.length
    ? simpleTable(["Misja", "Tytuł", "Kolejka", "Priorytet", "Stan misji", "Próby", "Dodano", "Ostatni błąd"], rows, "Kolejka misji")
    : unavailable("Kolejka pusta", "Żadna misja nie oczekuje na wykonanie.", "PUSTA");
  view.append(panel("Wpisy kolejki", body, { index: "02" }));
  return view;
}

// ---------------------------------------------------------------- Workery / Minions

function renderWorkers() {
  const view = el("div", "view");
  const available = state.workers.filter((w) => w.availability === "AVAILABLE").length;
  view.append(pageIntro(
    "WORKERY WYKONAWCZE · JEDNORAZOWE MINIONS",
    "Workery / Minions",
    "Worker, którego runtime nie jest osiągalny, ma status UNAVAILABLE i odmawia wykonania. Nie jest symulowany ani podmieniany na inny. Minions są workerami wewnątrz Michael Angelo — nie osobnym control plane.",
    statusLabel(`${available}/${state.workers.length} DOSTĘPNYCH`),
  ));
  const grid = el("div", "fleet-grid");
  if (!state.workers.length) grid.append(unavailable("Brak workerów", "Rejestr adapterów jest pusty.", "BRAK DANYCH"));
  for (const worker of state.workers) {
    const body = el("div", "fleet-card-body");
    append(body,
      art("openshell-claw.webp", "", "fleet-art"),
      statusLabel(worker.availability),
      dataField("Identyfikator", worker.workerId),
      dataField("Rodzaj", worker.kind),
      dataField("Jednorazowy (Minion)", worker.ephemeral ? "TAK" : "NIE"),
      dataField("Powód statusu", worker.reason || "—"),
      dataField("Możliwości", (worker.capabilities || []).join(", ") || "NIEZNANE"),
      dataField("Bieżąca misja", state.missions.find((m) => m.backend === worker.workerId && ACTIVE_STATES.has(m.state))?.title || "BRAK"),
    );
    grid.append(panel(worker.name, body));
  }
  append(view, grid);
  return view;
}

// ---------------------------------------------------------------- Modele

function renderModels() {
  const view = el("div", "view");
  const available = state.models.filter((m) => m.availability === "AVAILABLE").length;
  view.append(pageIntro(
    "ROUTING MODELI",
    "Modele",
    "Dostępność modelu jest sondowana z hosta, nigdy zakładana. Brak klucza dostawcy oznacza UNAVAILABLE, a nie ciche przełączenie na inny model.",
    statusLabel(`${available}/${state.models.length} DOSTĘPNYCH`),
  ));
  const rows = state.models.map((model) => [
    el("span", "mono", model.model_id, { role: "cell" }),
    model.provider,
    model.role,
    statusLabel(model.availability),
    model.reason || "—",
  ]);
  const body = state.models.length
    ? simpleTable(["Model", "Dostawca", "Rola", "Dostępność", "Powód"], rows, "Rejestr modeli")
    : unavailable("Brak modeli", "Rejestr modeli jest pusty.", "BRAK DANYCH");
  view.append(panel("Rejestr modeli", body, { index: "01" }));

  const routing = el("div");
  for (const role of [...new Set(state.models.map((m) => m.role))]) {
    const chosen = state.models.find((m) => m.role === role && m.availability === "AVAILABLE");
    append(routing, dataField(`Rola: ${role}`, chosen ? chosen.model_id : "UNAVAILABLE", chosen ? "" : "danger-text"));
  }
  view.append(panel("Rozstrzygnięcie routingu", routing, { index: "02", subtitle: "Pierwszy dostępny model dla roli" }));
  return view;
}

// ---------------------------------------------------------------- Budżety

function renderBudgets() {
  const view = el("div", "view");
  const budgets = state.budgets.budgets || [];
  const entries = state.budgets.entries || [];
  view.append(pageIntro(
    "BUDŻETY I LIMITY",
    "Budżety",
    "Budżet jest sprawdzany przed każdym node'em, nie po fakcie. Worker deterministyczny nie zużywa tokenów, więc rozliczany jest zmierzony czas compute — rozliczanie tokenów byłoby fikcją.",
    statusLabel(budgets.length ? "AKTYWNE" : "NIESKONFIGUROWANE"),
  ));

  const grid = el("div", "module-grid");
  if (!budgets.length) grid.append(unavailable("Brak budżetów", "Żaden zakres budżetowy nie jest zdefiniowany.", "BRAK DANYCH"));
  for (const budget of budgets) {
    const used = budget.limit_amount ? (budget.spent_amount / budget.limit_amount) * 100 : 0;
    const body = el("div");
    append(body,
      statusLabel(budget.remaining_amount > 0 ? "W LIMICIE" : "WYCZERPANY"),
      dataField("Limit", money(budget.limit_amount, budget.currency)),
      dataField("Wydano", money(budget.spent_amount, budget.currency)),
      dataField("Pozostało", money(budget.remaining_amount, budget.currency)),
      dataField("Wykorzystanie", `${used.toFixed(2)}%`),
      dataField("Aktualizacja", formatDate(budget.updated_at)),
    );
    grid.append(panel(`Zakres: ${budget.scope}`, body));
  }
  view.append(grid);

  const rows = entries.slice(0, 40).map((entry) => [
    formatDate(entry.created_at),
    entry.scope,
    el("span", "mono", shortSha(entry.mission_id), { role: "cell" }),
    money(entry.amount),
    entry.reason || "—",
  ]);
  const ledger = entries.length
    ? simpleTable(["Czas", "Zakres", "Misja", "Kwota", "Powód"], rows, "Księga budżetu")
    : unavailable("Brak wpisów", "Żadne wykonanie nie obciążyło jeszcze budżetu.", "BRAK DANYCH");
  view.append(panel("Księga obciążeń", ledger, { index: "02" }));
  return view;
}

// ---------------------------------------------------------------- Zdrowie systemu

function renderHealth() {
  const view = el("div", "view");
  const health = state.fullHealth;
  view.append(pageIntro(
    "ZDROWIE SYSTEMU",
    "Zdrowie systemu",
    "Stan raportowany wyłącznie z realnych danych control plane. Brak dowodu jest raportowany jako UNKNOWN.",
    statusLabel(health?.status || "NIEZNANY"),
  ));

  if (!health) {
    view.append(unavailable("Brak danych zdrowia", "Endpoint /api/health/full nie odpowiedział.", "NIEPODŁĄCZONE"));
    return view;
  }

  const summary = el("div", "mission-facts");
  append(summary,
    dataField("Status", health.status),
    dataField("Wersje schematu", (health.schemaVersions || []).join(", ")),
    dataField("Misje ogółem", String(health.missions.total)),
    dataField("Aktywne", String(health.missions.active)),
    dataField("Zakończone", String(health.missions.completed)),
    dataField("Nieudane", String(health.missions.failed)),
    dataField("Kolejka: oczekujące", String(health.queue.waiting)),
    dataField("Workery dostępne", String(health.workers.available)),
  );
  view.append(panel("Podsumowanie", summary, { index: "01" }));

  const issues = el("div");
  if (!health.issues.length) issues.append(el("p", "muted-copy", "Brak wykrytych problemów."));
  else {
    const list = el("ul", "risk-list");
    health.issues.forEach((issue) => list.append(el("li", null, issue)));
    issues.append(list);
  }
  view.append(panel("Wykryte problemy", issues, { index: "02" }));

  view.append(panel("Topologia usług", renderInfrastructureCompact(), { index: "03" }));
  view.append(renderZgredekCard());
  return view;
}

// ---------------------------------------------------------------- Logi

function renderLogsView() {
  const view = el("div", "view");
  const allLogs = [...state.details.values()].flatMap((detail) =>
    detail.logs.map((log) => ({ ...log, missionTitle: detail.mission.title })),
  ).sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)));
  view.append(pageIntro(
    "STRUMIEŃ WYKONANIA",
    "Logi",
    "Wyjście wykonania przechodzi przez redaktor sekretów Hermesa. Surowe sekrety nie trafiają do logów ani artefaktów.",
    statusLabel(`${allLogs.length} WPISÓW`),
  ));
  if (!allLogs.length) {
    view.append(panel("Strumień logów", unavailable("Brak logów", "Uruchom misję, aby zobaczyć strumień wykonania.", "BRAK DANYCH")));
    return view;
  }
  const terminal = el("div", "terminal", null, { role: "log", "aria-label": "Logi wykonania" });
  for (const log of allLogs.slice(0, 200)) {
    const line = el("div", `terminal-line stream-${log.stream || "system"}`);
    append(line,
      el("time", null, formatDate(log.timestamp)),
      el("span", "mono terminal-node", log.node_id || "system"),
      el("pre", null, log.message),
    );
    terminal.append(line);
  }
  view.append(panel("Strumień logów", terminal, { className: "terminal-panel", index: "01" }));
  return view;
}

// ---------------------------------------------------------------- Recovery

function renderRecovery() {
  const view = el("div", "view");
  view.append(pageIntro(
    "ODZYSKIWANIE I ROLLBACK",
    "Recovery",
    "Kontrakt restart-recovery: przerwane node'y wracają do READY, a wydzierżawione wpisy kolejki do WAITING. Każda misja z dowodami ma commit-bound plan rollbacku.",
    statusLabel("KONTRAKT AKTYWNY"),
  ));

  const contract = el("div");
  append(contract,
    dataField("Odzyskiwanie node'ów", "RUNNING → READY przy starcie"),
    dataField("Odzyskiwanie kolejki", "LEASED → WAITING przy starcie"),
    dataField("Trwałość stanu", "SQLite w state root"),
    dataField("Rejestr zdarzeń", "Append-only, hash-chained"),
    el("p", "muted-copy", "Rollback jest lokalny dla repozytorium i addytywny. Nigdy nie dotyka sandboxu Hermesa, VPS-a, jednostek systemd ani baz produkcyjnych."),
  );
  view.append(panel("Kontrakt odzyskiwania", contract, { index: "01" }));

  const grid = el("div", "module-grid");
  const withEvidence = [...state.details.values()].filter((d) => d.evidence?.available);
  if (!withEvidence.length) grid.append(unavailable("Brak planów rollback", "Żadna misja nie wygenerowała jeszcze dowodów.", "BRAK DANYCH"));
  for (const detail of withEvidence) {
    const plan = detail.evidence.bundle?.rollbackPlan;
    const body = el("div");
    if (!plan) {
      body.append(unavailable("Brak planu", "Bundle nie zawiera planu rollback.", "BRAK DANYCH"));
    } else {
      append(body,
        statusLabel(plan.verified ? "PLAN ZWERYFIKOWANY" : "PLAN NIEZWERYFIKOWANY"),
        dataField("Strategia", plan.strategy),
        dataField("Commit bazowy", shortSha(plan.baseCommit)),
        dataField("Commit wynikowy", shortSha(plan.resultCommit)),
        dataField("Zmienione pliki", (plan.changedFiles || []).join(", ") || "BRAK"),
        dataField("Wpływ na produkcję", plan.productionImpact ? "TAK" : "NIE"),
      );
      const steps = el("ol", "risk-list");
      (plan.steps || []).forEach((step) => steps.append(el("li", null, step)));
      body.append(steps);
      body.append(button("Pobierz manifest rollback", "secondary-button full-width", () => downloadRollback(detail.mission.mission_id)));
    }
    grid.append(panel(detail.mission.title, body, { subtitle: shortSha(detail.mission.mission_id) }));
  }
  view.append(grid);
  return view;
}

async function approveContextPacket(missionId, packetSha256) {
  if (!missionId || !packetSha256) return;
  try {
    // The approval is granted for this exact hash; a stale page cannot approve
    // content the operator did not see.
    await api(`/api/context-packet/${missionId}/approve`, {
      method: "POST",
      body: JSON.stringify({ packetSha256 }),
    });
    state.details.delete(missionId);
    await refreshData({ deep: true });
  } catch (error) { showError(error); }
}

async function downloadRollback(missionId) {
  try {
    const data = await api(`/api/missions/${missionId}/rollback`);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = el("a", null, null, { href: url, download: `rollback-${shortSha(missionId)}.json` });
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) { showError(error); }
}

// ---------------------------------------------------------------- Polityki AI

function renderPoliciesAi() {
  const view = el("div", "view governance-view");
  view.append(pageIntro("AGENT WSPÓŁZAŁOŻYCIEL · NADZÓR", "Polityki AI", "Strategia, priorytety, autonomia i progi ryzyka muszą pochodzić z przeglądniętej integracji Policies AI. Ten interfejs nie wytwarza decyzji politycznych.", statusLabel("POLICIES AI NIEPODŁĄCZONE")));
  const hero = el("section", "governance-hero panel");
  const artWrap = el("div", "governance-art");
  artWrap.append(art("policies-ai.webp", "Klasyczne popiersie i cyber-węże — nadzór Policies AI"));
  const copy = el("div", "governance-hero-copy");
  append(copy, microLabel("AUTORYTET STRATEGICZNY"), el("h2", null, "Nadzór bez fabrykowanej pewności"), el("p", null, "Podłącz realny magazyn decyzji politycznych, zanim pojawią się decyzje, uzasadnienia, poziom pewności i alternatywy."), statusLabel("BRAK DANYCH POLITYK"));
  append(hero, artWrap, copy);

  const grid = el("div", "governance-grid");
  const budget = (state.budgets.budgets || [])[0];
  const fields = [
    ["Decyzje strategiczne", "BRAK DANYCH", "Endpoint historii decyzji nie jest skonfigurowany."],
    ["Polityka autonomii", "UNKNOWN", "Brak podłączonego źródła polityk."],
    ["Reguły ryzyka", "AKTYWNE", "Ryzyko misji jest klasyfikowane przez kompilator; globalna polityka ryzyka nie istnieje."],
    ["Progi zatwierdzeń", "AKTYWNE", "Bramki architektury i ludzka są egzekwowane przez control plane."],
    ["Routing modeli", state.models.some((m) => m.availability === "AVAILABLE") ? "AKTYWNY" : "UNAVAILABLE", "Routing rozstrzyga pierwszy dostępny model dla roli."],
    ["Limity budżetu", budget ? "SKONFIGUROWANE" : "NIESKONFIGUROWANE", budget ? `Limit ${money(budget.limit_amount, budget.currency)} dla zakresu '${budget.scope}'.` : "Brak zakresu budżetowego."],
  ];
  for (const [title, value, copyText] of fields) {
    const body = el("div", "governance-module");
    append(body, statusLabel(value), el("p", "muted-copy", copyText));
    grid.append(panel(title, body));
  }
  append(view, hero, grid, renderZgredekCard());
  return view;
}

// ---------------------------------------------------------------- Misje

function selectMission(missionId) {
  state.selectedMissionId = missionId;
  state.selectedNodeId = null;
  navigate("missions");
  loadMissionDetails(missionId, true).then(render).catch(showError);
}

function renderMissions() {
  const view = el("div", "view missions-view");
  view.append(pageIntro("ORKIESTRACJA MISJI", "Misje", "Kompilacja, bramki, wykonanie, walidacja i weryfikacja misji przez realne API control plane.", statusLabel(`${state.missions.length} ZAREJESTROWANYCH`)));
  const workbench = el("div", "mission-workbench");
  workbench.append(renderMissionRail());
  workbench.append(renderMissionDetail());
  append(view, workbench);
  return view;
}

function renderMissionRail() {
  const rail = el("aside", "mission-rail");
  rail.append(renderMissionIntakeForm());
  const list = el("div", "mission-rail-list panel");
  append(list, microLabel("REJESTR MISJI"));
  if (!state.missions.length) list.append(unavailable("Brak misji", "Zleć pierwszą misję deterministyczną.", "BRAK DANYCH"));
  for (const mission of state.missions) {
    const card = button("", `mission-list-card ${mission.mission_id === state.selectedMissionId ? "selected" : ""}`, () => selectMission(mission.mission_id), { ariaLabel: `Otwórz misję ${mission.title}` });
    append(card, el("strong", null, mission.title), statusLabel(mission.state), el("small", "mono", shortSha(mission.mission_id)));
    list.append(card);
  }
  rail.append(list);
  return rail;
}

function labelledInput(labelText, name, value, maxLength, required = true) {
  const label = el("label", "field-label", labelText);
  label.append(el("input", "field-control", null, { name, value, maxlength: maxLength, required }));
  return label;
}

function labelledTextarea(labelText, name, value, maxLength, required = true) {
  const label = el("label", "field-label", labelText);
  const input = el("textarea", "field-control", null, { name, maxlength: maxLength, rows: "3", required });
  input.value = value;
  label.append(input);
  return label;
}

function splitLines(value) {
  return String(value || "").split("\n").map((line) => line.trim()).filter(Boolean);
}

async function handleCreateMission(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    const payload = {
      title: form.get("title"),
      request: form.get("request"),
      repository: form.get("repository") || "fixture://hydra-safe-demo",
      backend: "deterministic-local",
      failureMode: form.get("failureMode"),
      baseBranch: form.get("baseBranch") || "main",
      acceptanceCriteria: splitLines(form.get("acceptanceCriteria")),
      requiredTests: splitLines(form.get("requiredTests")),
      worker: form.get("worker") || "AUTO",
      blueprint: form.get("blueprint") || "standard-coding-mission",
      riskLevel: form.get("riskLevel") || "LOW",
      budgetLimit: Number(form.get("budgetLimit") || 0),
      timeoutSeconds: Number(form.get("timeoutSeconds") || 900),
      priority: Number(form.get("priority") || 100),
    };
    const mission = await api("/api/missions", { method: "POST", body: JSON.stringify(payload) });
    state.selectedMissionId = mission.mission_id;
    await refreshData({ deep: true });
  } catch (error) { showError(error); }
}

function renderMissionDetail() {
  if (!state.selectedMissionId) return panel("Szczegóły misji", unavailable("Nie wybrano misji", "Wybierz lub zleć misję.", "BRAK DANYCH"), { className: "mission-detail-empty" });
  const detail = state.details.get(state.selectedMissionId);
  if (!detail) {
    loadMissionDetails(state.selectedMissionId, true).then(render).catch(showError);
    return panel("Szczegóły misji", unavailable("Wczytywanie misji", "Odczyt trwałego rejestru misji.", "WCZYTYWANIE"));
  }
  const mission = detail.mission;
  const manifest = mission.manifest || {};
  const wrap = el("section", "mission-detail");
  const hero = el("header", "mission-detail-hero panel");
  const copy = el("div");
  append(copy, microLabel(`MISJA ${shortSha(mission.mission_id)}`), el("h2", null, mission.title), el("p", "muted-copy", mission.request));
  const actions = el("div", "mission-actions");
  append(actions, ...missionActions(mission));
  append(hero, copy, actions);
  const facts = el("div", "mission-facts");
  append(facts,
    dataField("Stan", mission.state), dataField("Ryzyko", mission.risk_level), dataField("Repozytorium", mission.repository),
    dataField("Branch bazowy", manifest.base_branch || "main"), dataField("Branch misji", mission.branch),
    dataField("Worker", mission.backend), dataField("Blueprint", manifest.blueprint || "—"),
    dataField("Bieżący node", mission.current_node_id || "NIE URUCHOMIONO"),
    dataField("Commit bazowy", shortSha(mission.base_commit)), dataField("Commit wynikowy", shortSha(mission.result_commit)),
    dataField("Budżet misji", manifest.budget_limit ? money(manifest.budget_limit) : "BRAK LIMITU"),
    dataField("Timeout", manifest.timeout_seconds ? `${manifest.timeout_seconds}s` : "—"),
  );

  const criteria = el("div");
  const accepted = manifest.acceptance_criteria || [];
  if (accepted.length) {
    const list = el("ul", "risk-list");
    accepted.forEach((c) => list.append(el("li", null, c)));
    criteria.append(list);
  } else criteria.append(el("p", "muted-copy", "Nie podano kryteriów akceptacji."));

  wrap.append(hero, facts, panel("Kryteria akceptacji", criteria, { index: "00" }), renderPipeline(detail), renderMissionLower(detail));
  return wrap;
}

function missionActions(mission) {
  const actions = [];
  if (mission.state === "DRAFT") actions.push(button("Uruchom", "primary-button", () => missionCommand(mission.mission_id, "start")));
  if (mission.state === "AWAITING_ARCHITECTURE_APPROVAL") actions.push(button("Zatwierdź architekturę", "approval-button", () => missionApproval(mission.mission_id, "architecture")));
  if (mission.state === "AWAITING_HUMAN_APPROVAL") actions.push(button("Zatwierdź gotowość PR", "approval-button", () => missionApproval(mission.mission_id, "human")));
  const failed = mission.nodes?.find((node) => node.state === "FAILED");
  if (failed) actions.push(button(`Ponów: ${failed.name}`, "primary-button", () => retryMissionNode(mission.mission_id, failed.node_id)));
  if (!TERMINAL_STATES.has(mission.state)) actions.push(button("Zatrzymaj", "danger-button", () => missionCommand(mission.mission_id, "cancel")));
  if (mission.result_commit) {
    actions.push(button("Otwórz diff", "secondary-button", () => openDiff(mission.mission_id)));
    actions.push(button("Otwórz PR", "secondary-button", () => openPullRequest(mission.mission_id)));
    actions.push(button("Pobierz dowody", "secondary-button", () => downloadEvidence(mission.mission_id)));
    actions.push(button("Rollback", "danger-button", () => downloadRollback(mission.mission_id)));
  }
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

async function openDiff(missionId) {
  try {
    const diff = await api(`/api/missions/${missionId}/diff`);
    if (!diff.available) { showError(new Error(diff.reason || "Brak diffu")); return; }
    state.diffs.set(missionId, diff);
    render();
  } catch (error) { showError(error); }
}

async function openPullRequest(missionId) {
  try {
    const pr = await api(`/api/missions/${missionId}/pull-request`);
    if (!pr.available) { showError(new Error(pr.reason || "Brak deskryptora PR")); return; }
    showPullRequestDialog(pr);
  } catch (error) { showError(error); }
}

function showPullRequestDialog(pr) {
  const existing = document.querySelector("#pr-dialog");
  if (existing) existing.remove();
  const dialog = el("dialog", "command-dialog", null, { id: "pr-dialog" });
  const body = el("div");
  append(body,
    microLabel("DESKRYPTOR PULL REQUEST · LOKALNY"),
    el("h2", null, pr.title),
    statusLabel(pr.status),
    dataField("Repozytorium", pr.repository),
    dataField("Branch źródłowy", pr.sourceBranch),
    dataField("Branch docelowy", pr.targetBranch),
    dataField("Ryzyko", pr.riskLevel),
    dataField("Zmienione pliki", (pr.changedFiles || []).join(", ")),
    dataField("Merge produkcyjny", pr.productionMerge),
    dataField("Recenzenci", (pr.reviewers || []).join(", ")),
    el("p", "muted-copy", pr.note),
  );
  const form = el("form", null, null, { method: "dialog" });
  const actions = el("div", "dialog-actions");
  actions.append(button("Zamknij", "secondary-button", null, { type: "submit" }));
  append(form, body, actions);
  dialog.append(form);
  document.body.append(dialog);
  dialog.showModal();
  dialog.addEventListener("close", () => dialog.remove());
}

async function downloadEvidence(missionId) {
  try {
    const evidence = await api(`/api/missions/${missionId}/evidence`);
    const blob = new Blob([JSON.stringify(evidence, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = el("a", null, null, { href: url, download: `evidence-${shortSha(missionId)}.json` });
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) { showError(error); }
}

function renderPipeline(detail) {
  const pipeline = el("div", "pipeline-track", null, { role: "list", "aria-label": "Pipeline misji" });
  for (const [index, node] of detail.mission.nodes.entries()) {
    const card = button("", `pipeline-node state-${statusTone(node.state)} ${node.node_id === (state.selectedNodeId || detail.mission.current_node_id) ? "current" : ""}`, () => {
      state.selectedNodeId = node.node_id;
      render();
    }, { ariaLabel: `${node.name}: ${node.state}` });
    append(card, el("span", "node-index", String(index + 1).padStart(2, "0")), el("strong", null, node.name), statusLabel(node.state), el("small", null, `Próba ${node.attempt}`));
    pipeline.append(card);
  }
  return panel("Pipeline wykonania", pipeline, { className: "pipeline-panel", index: "01", subtitle: "Trwały stan · wyłącznie realne przejścia" });
}

function renderMissionLower(detail) {
  const grid = el("div", "mission-lower-grid");
  const node = detail.mission.nodes.find((item) => item.node_id === (state.selectedNodeId || detail.mission.current_node_id)) || detail.mission.nodes[0];
  const nodeBody = node ? [
    dataField("Stan", node.state), dataField("Worker", node.backend), dataField("Zależności", node.dependencies?.join(", ") || "BRAK"),
    dataField("Start", formatDate(node.started_at)), dataField("Koniec", formatDate(node.finished_at)), dataField("Walidacja", node.validation_result || "UNKNOWN"),
    el("p", "node-summary", node.summary || "Brak zapisanego podsumowania."),
  ] : unavailable("Brak node'a", "Pipeline jest niedostępny.");
  grid.append(panel("Inspektor node'a", nodeBody, { index: "02" }));
  grid.append(panel("Logi wykonania", renderLogs(detail.logs), { index: "03", className: "terminal-panel" }));
  grid.append(panel("Artefakty", renderArtifacts(detail.artifacts), { index: "04" }));
  grid.append(panel("Dowody APR", renderEvidence(detail.evidence), { index: "05" }));
  return grid;
}

function renderLogs(logs) {
  if (!logs.length) return unavailable("Brak logów", "Wyjście wykonania pojawi się tutaj.", "BRAK DANYCH");
  const terminal = el("div", "terminal", null, { role: "log", "aria-label": "Logi wykonania" });
  for (const log of logs.slice(-80)) {
    const line = el("div", `terminal-line stream-${log.stream || "system"}`);
    append(line, el("time", null, formatDate(log.timestamp)), el("span", "mono terminal-node", log.node_id || "system"), el("pre", null, log.message));
    terminal.append(line);
  }
  return terminal;
}

function renderArtifacts(artifacts) {
  if (!artifacts.length) return unavailable("Brak artefaktów", "Zwalidowane wyjście pojawi się po wykonaniu.", "BRAK DANYCH");
  const list = el("div", "artifact-list");
  for (const artifact of artifacts) {
    const link = el("a", "artifact-card", null, { href: `/api/artifacts/${artifact.artifact_id}/content`, target: "_blank", rel: "noreferrer" });
    append(link, el("span", "artifact-icon", "▦", { "aria-hidden": "true" }), el("strong", null, artifact.name), el("small", null, artifact.kind), el("code", null, shortSha(artifact.sha256)));
    list.append(link);
  }
  return list;
}

function renderEvidence(evidence) {
  if (!evidence?.available) return unavailable("Dowody niedostępne", "APR nie wygenerował bundla dla tej misji.", "BRAK DANYCH");
  const wrap = el("div", "evidence-card");
  const verdict = evidence.valid ? "POWIĄZANIE Z COMMITEM WAŻNE" : "DOWODY UNIEWAŻNIONE";
  append(wrap, statusLabel(evidence.valid ? "VALID" : "INVALID"), el("strong", null, verdict),
    dataField("Commit wynikowy", evidence.bundle?.resultCommit || "NIEZNANY"),
    dataField("Commit bazowy", evidence.bundle?.baseCommit || "NIEZNANY"),
    dataField("Wygenerowano", formatDate(evidence.bundle?.generatedAt)),
    dataField("Zmienione pliki", (evidence.bundle?.changedFiles || []).join(", ") || "BRAK"),
  );
  const checks = el("div", "check-grid");
  for (const [name, value] of Object.entries(evidence.bundle?.checks || {})) {
    const check = el("div", "check-item");
    append(check, el("span", null, name), statusLabel(value));
    checks.append(check);
  }
  wrap.append(checks);

  const criteria = evidence.bundle?.acceptanceCriteria || [];
  if (criteria.length) {
    const list = el("div", "check-grid");
    criteria.forEach((c) => {
      const item = el("div", "check-item");
      append(item, el("span", null, c.criterion), statusLabel(c.status));
      list.append(item);
    });
    wrap.append(microLabel("KRYTERIA AKCEPTACJI"), list);
  }
  const tests = evidence.bundle?.requiredTests || [];
  if (tests.length) {
    const list = el("div", "check-grid");
    tests.forEach((t) => {
      const item = el("div", "check-item");
      append(item, el("span", null, t.test), statusLabel(t.status));
      list.append(item);
    });
    wrap.append(microLabel("WYMAGANE TESTY"), list);
  }
  const plan = evidence.bundle?.rollbackPlan;
  if (plan) wrap.append(microLabel("ROLLBACK"), dataField("Plan", plan.verified ? "ZWERYFIKOWANY" : "NIEZWERYFIKOWANY"));

  if (evidence.invalidReasons?.length) {
    const reasons = el("ul", "risk-list");
    evidence.invalidReasons.forEach((reason) => reasons.append(el("li", null, reason)));
    wrap.append(microLabel("POWODY UNIEWAŻNIENIA", "danger-text"), reasons);
  }
  return wrap;
}

function renderCompactEvent(event) {
  const item = el("article", "event-card");
  append(item, el("time", null, formatDate(event.timestamp)), el("strong", null, event.event_type || "ZDARZENIE"), el("p", null, event.message || `${event.previous_state || "UNKNOWN"} → ${event.next_state || "UNKNOWN"}`), el("code", null, event.commit_sha ? shortSha(event.commit_sha) : "BRAK COMMITU"));
  return item;
}

function renderFleetCompact() {
  if (!state.workers.length) return unavailable("Brak workerów", "Nie zarejestrowano adaptera wykonawczego.", "BRAK DANYCH");
  const list = el("div", "compact-list");
  for (const worker of state.workers) {
    const row = el("div", "compact-row");
    append(row, el("span", "row-icon", worker.ephemeral ? "◈" : "⎈"), el("div", "row-copy", null), statusLabel(worker.availability));
    append(row.children[1], el("strong", null, worker.name), el("small", null, worker.reason || worker.workerId));
    list.append(row);
  }
  return list;
}

function renderApprovalList(compact = false) {
  const pending = state.approvals.length
    ? state.approvals
    : state.missions.filter((mission) => APPROVAL_STATES.has(mission.state)).map((mission) => ({
      missionId: mission.mission_id, title: mission.title, gate: APPROVAL_STATES.get(mission.state),
      state: mission.state, riskLevel: mission.risk_level, permission: "YELLOW",
    }));
  if (!pending.length) return unavailable("Brak oczekujących zatwierdzeń", "Żadna bramka nie wymaga obecnie działania OSA.", "CZYSTO");
  const list = el("div", "approval-list");
  for (const item of pending.slice(0, compact ? 3 : 20)) {
    const card = el("article", "approval-card");
    const copy = el("div", "approval-copy");
    append(copy,
      microLabel(GATE_LABELS[item.gate] || item.gate),
      el("h3", null, item.title),
      dataField("Misja", shortSha(item.missionId)),
      dataField("Ryzyko", item.riskLevel || "NIEZNANE"),
      dataField("Uprawnienie", item.permission || "YELLOW"),
      dataField("Dowody", item.gate === "human" ? "WYMAGANE" : "JESZCZE NIEWYGENEROWANE"),
    );
    const actions = el("div", "approval-actions");
    append(actions,
      button("Zatwierdź", "approval-button", () => missionApproval(item.missionId, item.gate)),
      button("Odrzuć", "danger-button", null, { disabled: true, title: "Endpoint odrzucenia nie jest zaimplementowany" }),
      button("Zażądaj zmian", "secondary-button", null, { disabled: true, title: "Endpoint żądania zmian nie jest zaimplementowany" }),
    );
    append(card, copy, actions);
    list.append(card);
  }
  return list;
}

function renderAprSummary() {
  const details = [...state.details.values()].filter((detail) => detail.evidence?.available);
  if (!details.length) return unavailable("Brak dowodów APR", "Przeprowadź misję przez generowanie dowodów.", "BRAK DANYCH");
  const detail = details[0];
  const wrap = el("div", "apr-summary");
  append(wrap, art("apr-evidence.webp", "", "apr-emblem"), statusLabel(detail.evidence.valid ? "VALID" : "INVALID"), dataField("Misja", shortSha(detail.mission.mission_id)), dataField("Commit wynikowy", shortSha(detail.evidence.bundle?.resultCommit)), dataField("Łańcuch zdarzeń", detail.evidence.eventChain || "NIEZNANY"));
  return wrap;
}

function allRecentEvents() {
  return [...state.details.values()].flatMap((detail) => detail.events.map((event) => ({ ...event, missionTitle: detail.mission.title }))).sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)));
}

function renderRecentEvents(limit = 5) {
  const events = allRecentEvents().slice(0, limit);
  if (!events.length) return unavailable("Brak zdarzeń", "Zdarzenia misji pojawią się z trwałego rejestru.", "BRAK DANYCH");
  return events.map(renderCompactEvent);
}

function serviceRow(name, value, detail) {
  const row = el("div", "service-row");
  append(row, el("span", "service-sigil", "◉"), el("div", "row-copy", null), statusLabel(value));
  append(row.children[1], el("strong", null, name), el("small", null, detail));
  return row;
}

function renderInfrastructureCompact() {
  const sched = state.queue.scheduler;
  const list = el("div", "compact-list");
  append(list,
    serviceRow("Hydra Control Plane", state.health?.status === "ok" ? "ONLINE" : "OFFLINE", "Loopback HTTP API"),
    serviceRow("Scheduler kolejki", sched?.running ? "DZIAŁA" : "ZATRZYMANY", `Równoległość ${sched?.maxConcurrent ?? "?"}`),
    serviceRow("Michael Angelo (czat)", "OFFLINE", "Brak endpointu runtime czatu"),
    serviceRow("Zgredek Drift Guard", "NIEPODŁĄCZONY", "Brak kontraktu context packet"),
    serviceRow("Workery wykonawcze", state.workers.some((w) => w.availability === "AVAILABLE") ? "GOTOWE" : "BRAK", `${state.workers.length} zadeklarowanych`),
    serviceRow("Magazyn zdarzeń", state.health?.status === "ok" ? "ONLINE" : "NIEZNANY", "Granica SQLite misji"),
  );
  return list;
}

function renderRepositories() {
  const view = el("div", "view");
  view.append(pageIntro("GRANICA KONTROLI ŹRÓDEŁ", "Repozytoria", "Rejestr repozytoriów z jawnym oznaczeniem, które są wykonywalne przez workery. Brak nieograniczonej przeglądarki repozytoriów.", statusLabel(`${state.repositories.length} ZAREJESTROWANYCH`)));
  const grid = el("div", "module-grid");
  if (!state.repositories.length) grid.append(unavailable("Brak repozytoriów", "Rejestr repozytoriów jest pusty.", "BRAK DANYCH"));
  for (const repo of state.repositories) {
    const body = el("div");
    append(body,
      statusLabel(repo.executable ? "WYKONYWALNE" : "TYLKO ODCZYT"),
      dataField("Slug", repo.slug),
      dataField("URI", repo.uri),
      dataField("Projekt", repo.project_key),
      dataField("Branch domyślny", repo.default_branch),
      dataField("Uprawnienie", repo.permission),
      dataField("Ścieżka hosta", "NIEUJAWNIANA"),
    );
    grid.append(panel(repo.slug, body));
  }
  append(view, grid);
  return view;
}

function renderSandboxes() {
  const view = el("div", "view");
  view.append(pageIntro("IZOLOWANE WYKONANIE", "Sandboksy", "Jeden izolowany sandbox na misję. Przeglądarka nie otrzymuje ścieżek hosta ani powłoki.", statusLabel(`${state.sandboxes.length} ŚLEDZONYCH`)));

  const boundary = el("div", "feature-split");
  append(boundary, art("openshell-claw.webp", "Cybernetyczny szpon — izolowane wykonanie"), el("div", null, null));
  append(boundary.lastChild,
    microLabel("KONTRAKT BEZPIECZNEGO WYKONANIA"),
    el("h2", null, "Deterministyczny fixture lokalny"),
    dataField("Dostęp do powłoki", "NIEUJAWNIONY"),
    dataField("Ścieżki hosta", "ODRZUCANE"),
    dataField("Credentiale produkcyjne", "NIEPRZEKAZYWANE"),
    dataField("Sieć", "WYŁĄCZONA"),
    el("p", "muted-copy", "Szczegóły sesji pozostają po stronie serwera, a artefakty są serwowane przez nieprzezroczyste ID."),
  );
  view.append(panel("Granica sandboxu", boundary, { index: "01" }));

  const rows = state.sandboxes.map((sb) => [
    el("span", "mono", shortSha(sb.missionId), { role: "cell" }),
    sb.title,
    statusLabel(sb.state),
    sb.worker,
    statusLabel(sb.exists ? "ISTNIEJE" : "USUNIĘTY"),
    sb.network ? "TAK" : "NIE",
    sb.productionCredentials ? "TAK" : "NIE",
  ]);
  const body = state.sandboxes.length
    ? simpleTable(["Misja", "Tytuł", "Stan", "Worker", "Workspace", "Sieć", "Credentiale"], rows, "Sandboksy")
    : unavailable("Brak sandboksów", "Żadna misja nie utworzyła jeszcze workspace'u.", "BRAK DANYCH");
  view.append(panel("Sandboksy per misja", body, { index: "02" }));
  return view;
}

function renderApprovals() {
  const view = el("div", "view");
  const count = state.approvals.length;
  view.append(pageIntro("BRAMKI OSA · Z ATRYBUCJĄ AKTORA", "Zatwierdzenia", "Bramki architektury i ludzka używają istniejącego endpointu zatwierdzeń z zapisem aktora i czasu. Zadanie RED blokuje tylko siebie.", statusLabel(`${count} OCZEKUJĄCYCH`)));
  append(view, renderApprovalList(false));
  return view;
}

function renderEvidenceView() {
  const view = el("div", "view");
  view.append(pageIntro("NIEZALEŻNA WERYFIKACJA", "Dowody", "Ważność dowodów jest oceniana niezależnie od zakończenia misji i powiązana z dokładnymi commitami oraz artefaktami.", statusLabel("POWIĄZANE Z COMMITEM")));
  const grid = el("div", "evidence-grid-view");
  const details = [...state.details.values()];
  if (!details.length) grid.append(unavailable("Brak dowodów misji", "Nie wczytano szczegółów żadnej misji.", "BRAK DANYCH"));
  for (const detail of details) {
    const body = el("div");
    body.append(renderEvidence(detail.evidence));
    if (detail.evidence?.available) {
      body.append(button("Pobierz bundle dowodów", "secondary-button full-width", () => downloadEvidence(detail.mission.mission_id)));
    }
    grid.append(panel(detail.mission.title, body, { subtitle: shortSha(detail.mission.mission_id) }));
  }
  append(view, grid);
  return view;
}

function renderArtifactsView() {
  const view = el("div", "view");
  const artifacts = [...state.details.values()].flatMap((detail) => detail.artifacts);
  view.append(pageIntro("WYGENEROWANE WYJŚCIE", "Artefakty", "Bajty artefaktów są odczytywane przez nieprzezroczyste ID i weryfikowane względem zapisanego SHA-256.", statusLabel(`${artifacts.length} DOSTĘPNYCH`)));
  append(view, panel("Rejestr artefaktów", renderArtifacts(artifacts), { className: "artifact-registry" }));
  return view;
}

function renderAuditLog() {
  const view = el("div", "view");
  const events = allRecentEvents();
  view.append(pageIntro("NIEZMIENNY REJESTR ZDARZEŃ", "Dziennik audytu", "Przejścia misji powiązane łańcuchem hashy, z aktorem, stanem, artefaktami i referencjami commitów.", statusLabel(`${events.length} WCZYTANYCH`)));
  const list = el("div", "audit-list");
  if (!events.length) list.append(unavailable("Brak zdarzeń audytu", "Uruchom misję, aby zapełnić rejestr zdarzeń.", "BRAK DANYCH"));
  for (const event of events) {
    const row = el("article", "audit-row");
    append(row, el("time", null, formatDate(event.timestamp)), el("strong", null, event.event_type || "ZDARZENIE"), el("span", null, event.actor || "NIEZNANY"), el("span", null, event.missionTitle || shortSha(event.mission_id)), el("span", "mono", `${event.previous_state || "—"} → ${event.next_state || "—"}`), el("code", null, event.commit_sha ? shortSha(event.commit_sha) : "BRAK COMMITU"));
    list.append(row);
  }
  append(view, list);
  return view;
}

function renderSettings() {
  const view = el("div", "view");
  view.append(pageIntro("KONFIGURACJA LOKALNA TYLKO DO ODCZYTU", "Ustawienia", "Ta iteracja ujawnia fakty konfiguracyjne, ale nie udostępnia kontrolek mutacji produkcyjnych.", statusLabel("LOKALNE")));
  const grid = el("div", "module-grid");
  const runtime = el("div");
  append(runtime, dataField("Tryb serwowania", "LOOPBACK HTTP"), dataField("Odświeżanie", "4 SEKUNDY"), dataField("Zasoby statyczne", "TYLKO LOKALNE"), dataField("CSP", "TYLKO SELF"), dataField("Aktor", "OSA"), dataField("Wersje schematu", (state.fullHealth?.schemaVersions || []).join(", ") || "NIEZNANE"));
  grid.append(panel("Runtime", runtime));
  const locks = el("div");
  append(locks, dataField("Architektura", "MINION CONTROL PLANE v0.1"), dataField("Design", "HYDRA UI v0.1"), dataField("Wdrożenie produkcyjne", "NIEAUTORYZOWANE"), dataField("Zmiany runtime Hermesa", "POZA ZAKRESEM"), dataField("Web3 Lab", "ODSEPAROWANY"));
  grid.append(panel("Locki", locks));
  append(view, grid);
  return view;
}

// ---------------------------------------------------------------- Disclosure

function renderMissingFeature(key) {
  const f = MISSING_FEATURES[key];
  const view = el("div", "view");
  view.append(pageIntro(f.kicker, f.title,
    "Ta funkcja nie występuje w obecnym buildzie. Poniżej wynik inwentaryzacji forensycznej, a nie zastępczy interfejs.",
    statusLabel("MISSING FROM CURRENT BUILD")));

  const found = el("div");
  append(found,
    statusLabel("MISSING FROM CURRENT BUILD"),
    dataField("Ostatnie odnalezione źródło", f.lastSource),
    dataField("Szczegóły źródła", f.sourceDetail),
    dataField("Branch", f.branch),
    dataField("Commit", f.commit),
    dataField("Status recovery", f.recovery),
    el("p", "muted-copy", `„${f.quote}”`),
  );
  view.append(panel("Wynik inwentaryzacji", found, { index: "01" }));

  const blocked = el("div");
  append(blocked, statusLabel("ZABLOKOWANE"), el("p", "muted-copy", f.blocker));
  if (f.related) blocked.append(el("p", "muted-copy", f.related));
  view.append(panel("Blokada", blocked, { index: "02" }));

  const scope = el("ul", "risk-list");
  f.scope.forEach((item) => scope.append(el("li", null, item)));
  view.append(panel("Zakres oczekiwany przez kanon — nieobecny", scope, { index: "03" }));

  const controls = el("div", "mission-actions");
  append(controls,
    button("Utwórz portfel", "primary-button", null,
      { disabled: true, title: "Brak backendu: funkcja nieobecna w tym buildzie" }),
    button("Wykonaj płatność", "danger-button", null,
      { disabled: true, title: "Brak backendu: funkcja nieobecna w tym buildzie" }),
  );
  if (key === "mailbox") {
    controls.replaceChildren(
      button("Nowa wiadomość", "primary-button", null,
        { disabled: true, title: "Brak backendu: implementacja nie istnieje" }),
      button("Wyślij (wymaga OSA)", "danger-button", null,
        { disabled: true, title: "Brak backendu: implementacja nie istnieje" }),
    );
  }
  view.append(panel("Kontrolki", controls, { index: "04", subtitle: "Wyłączone z podaną przyczyną" }));
  return view;
}

function renderNvidia() {
  const view = el("div", "view");
  view.append(pageIntro("INFERENCE · AUDYT READ-ONLY", "NVIDIA / NemoClaw",
    "Audyt jest przypisany do zablokowanego hosta hydra-hermes-runtime-01. Ta sesja działa gdzie indziej, więc wszystkie werdykty pozostają UNKNOWN.",
    statusLabel("AUDYT NIEWYKONANY")));

  const verdicts = el("div");
  [
    ["ENDPOINT_CONFIGURED", "UNKNOWN"],
    ["ENDPOINT_REACHABLE", "UNKNOWN"],
    ["MODEL_ROUTE_HEALTHY", "UNKNOWN"],
    ["REAL_INFERENCE", "UNKNOWN"],
    ["CREDENTIAL_ISOLATION", "UNKNOWN"],
    ["NVIDIA_FREE_ENTITLEMENT", "UNKNOWN"],
  ].forEach(([k, v]) => append(verdicts, dataField(k, v)));
  verdicts.append(el("p", "muted-copy",
    "UNKNOWN nie jest uspokojeniem. Wymagany wynik NVIDIA_KEY_IN_SANDBOX=ABSENT nie został wykazany — izolację credentiali należy traktować jako niezweryfikowaną."));
  view.append(panel("Werdykty audytu", verdicts, { index: "01" }));

  const why = el("div");
  append(why,
    dataField("Wymagany host", "hydra-hermes-runtime-01"),
    dataField("Host tej sesji", "vm"),
    dataField("nemohermes / nemoclaw", "BRAK W PATH"),
    dataField("Wykonanych komend", "0"),
    el("p", "muted-copy", "Runbook z komendami w kolejności: docs/evidence/nvidia-nemoclaw-audit/RUNBOOK.md"),
  );
  view.append(panel("Dlaczego nie wykonano", why, { index: "02" }));

  const routing = el("div");
  for (const model of state.models) {
    append(routing, dataField(`${model.model_id} (${model.role})`, model.availability));
  }
  if (!state.models.length) routing.append(unavailable("Brak modeli", "Rejestr modeli jest pusty.", "BRAK DANYCH"));
  view.append(panel("Model Router — stan lokalny (nie runtime)", routing,
    { index: "03", subtitle: "Sondowane z tego hosta, nie z hydra-hermes-runtime-01" }));
  return view;
}

function renderSurface(projectKey, title, kicker, copy) {
  const view = el("div", "view");
  const project = state.projects.find((p) => p.key === projectKey);
  view.append(pageIntro(kicker, title, copy,
    statusLabel(project ? `ZAREJESTROWANY · ${project.permission}` : "BRAK W REJESTRZE")));
  const body = el("div");
  if (!project) {
    body.append(unavailable("Brak w rejestrze projektów", "Ta powierzchnia nie jest zarejestrowana.", "BRAK DANYCH"));
  } else {
    const repos = state.repositories.filter((r) => r.project_key === project.key);
    append(body,
      statusLabel(project.permission),
      el("p", "muted-copy", project.description || "Brak opisu."),
      dataField("Klucz", project.key),
      dataField("Powierzchnia", project.surface),
      dataField("Uprawnienie", project.permission),
      dataField("Repozytoria", String(repos.length)),
      dataField("Wykonywalne repozytoria", String(repos.filter((r) => r.executable).length)),
      dataField("Execution plane", "BRAK — powierzchnia zarejestrowana, nie uruchamialna"),
      el("p", "muted-copy",
        "Ta powierzchnia jest widoczna i objęta nadzorem uprawnień, ale nie ma w tym repozytorium żadnego runtime'u wykonawczego. Status wykonania: UNKNOWN."),
    );
    if (project.surface === "WEB3_LAB") {
      body.append(el("p", "muted-copy", "IZOLACJA: odseparowany od standardowego execution plane."));
    }
  }
  view.append(panel("Stan powierzchni", body, { index: "01" }));
  return view;
}

function renderZgredekView() {
  const view = el("div", "view");
  view.append(pageIntro("STRAŻNIK KONTEKSTU I DRIFTU", "Zgredek",
    "Zgredek przygotowuje i zatwierdza context packet oraz wykrywa drift. Nie koduje, nie uruchamia workera i nie wdraża.",
    statusLabel(state.fullHealth?.zgredek?.connected ? "ADAPTER PODŁĄCZONY" : "NIEPODŁĄCZONY")));
  view.append(renderZgredekCard());
  const boundary = el("div");
  append(boundary,
    dataField("Adapter", state.fullHealth?.zgredek?.adapter || "UNKNOWN"),
    dataField("Zewnętrzny produkt Zgredek", "UNKNOWN"),
    dataField("Bramkowany node", "repository-fact-load"),
    dataField("Packety w bazie", String(state.fullHealth?.zgredek?.packets ?? 0)),
    el("p", "muted-copy",
      "Granica jest strukturalna: moduł nie wykonuje podprocesów, nie otwiera gniazd i nie zapisuje niczego poza zwracanym packetem. Odmowę wykonuje Hydra."),
  );
  view.append(panel("Granica warstwy", boundary, { index: "02" }));
  return view;
}

function renderRoute() {
  switch (state.route) {
    case "dashboard": return renderDashboard();
    case "zgredek": return renderZgredekView();
    case "nvidia": return renderNvidia();
    case "wallet": return renderMissingFeature("wallet");
    case "mailbox": return renderMissingFeature("mailbox");
    case "genkit-lab": return renderSurface("genkit-lab", "Genkit Lab",
      "EKSPERYMENTY AI · PROTOTYPY", "Powierzchnia zarejestrowana w control plane. Brak runtime'u wykonawczego w tym repozytorium.");
    case "windows-rtx": return renderSurface("windows-rtx", "Windows / RTX",
      "RTX · BLENDER · OBRAZ · WIDEO · 3D", "Powierzchnia zarejestrowana w control plane. Brak runtime'u wykonawczego w tym repozytorium.");
    case "web3-lab": return renderSurface("web3-lab", "Web3 Lab",
      "ODSEPAROWANY RESEARCH · PAPER TRADING", "Powierzchnia zarejestrowana i odseparowana od standardowego execution plane.");
    case "projects": return renderProjects();
    case "missions": return renderMissions();
    case "queue": return renderQueue();
    case "michael-angelo": return renderMichaelAngelo();
    case "workers": return renderWorkers();
    case "sandboxes": return renderSandboxes();
    case "models": return renderModels();
    case "budgets": return renderBudgets();
    case "approvals": return renderApprovals();
    case "health": return renderHealth();
    case "logs": return renderLogsView();
    case "artifacts": return renderArtifactsView();
    case "evidence": return renderEvidenceView();
    case "recovery": return renderRecovery();
    case "repositories": return renderRepositories();
    case "policies-ai": return renderPoliciesAi();
    case "audit-log": return renderAuditLog();
    case "settings": return renderSettings();
    default: return renderDashboard();
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
  state.route = ROUTE_TITLES[requested] ? requested : "dashboard";
  if (!requested) history.replaceState(null, "", "#dashboard");
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
  if (!cancellable.length) dom.emergencyScope.append(el("p", "muted-copy", "Brak lokalnych misji do zatrzymania."));
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

"use strict";

const ui = {
  form: document.querySelector("#mission-form"),
  list: document.querySelector("#mission-list"),
  empty: document.querySelector("#empty-state"),
  view: document.querySelector("#mission-view"),
  title: document.querySelector("#mission-title"),
  request: document.querySelector("#mission-request"),
  actions: document.querySelector("#mission-actions"),
  metrics: document.querySelector("#mission-metrics"),
  pipeline: document.querySelector("#pipeline"),
  node: document.querySelector("#node-detail"),
  logs: document.querySelector("#logs"),
  artifacts: document.querySelector("#artifacts"),
  evidence: document.querySelector("#evidence"),
  error: document.querySelector("#error-banner"),
};

let selectedMission = null;
let selectedNodeId = null;
let busy = false;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      "X-Hydra-Actor": "OSA",
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error?.message || `Request failed with ${response.status}`);
  }
  return payload;
}

function showError(error) {
  ui.error.textContent = error instanceof Error ? error.message : String(error);
  ui.error.hidden = false;
  window.setTimeout(() => { ui.error.hidden = true; }, 7000);
}

function displayState(value) {
  return String(value || "UNKNOWN").replaceAll("_", " ");
}

function statusClass(value) {
  return `status-${String(value || "UNKNOWN").toLowerCase().replaceAll("_", "-")}`;
}

function duration(start, end) {
  if (!start) return "—";
  const milliseconds = new Date(end || Date.now()) - new Date(start);
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return "—";
  if (milliseconds < 1000) return `${milliseconds} ms`;
  if (milliseconds < 60000) return `${(milliseconds / 1000).toFixed(1)} s`;
  return `${Math.floor(milliseconds / 60000)}m ${Math.floor((milliseconds % 60000) / 1000)}s`;
}

function metric(label, value, extraClass = "") {
  const card = element("div", `metric ${extraClass}`);
  card.append(element("span", "metric-label", label), element("strong", "", value || "UNKNOWN"));
  return card;
}

async function refreshList() {
  const payload = await api("/api/missions");
  ui.list.replaceChildren();
  if (!payload.missions.length) {
    ui.list.append(element("p", "muted", "No missions compiled yet."));
    return;
  }
  for (const mission of payload.missions) {
    const button = element("button", `mission-item ${mission.mission_id === selectedMission?.mission_id ? "selected" : ""}`);
    button.type = "button";
    button.append(
      element("span", "mission-item-title", mission.title),
      element("span", `status-pill ${statusClass(mission.state)}`, displayState(mission.state)),
      element("small", "", `${mission.risk_level} · ${mission.mission_id.slice(0, 8)}`),
    );
    button.addEventListener("click", () => loadMission(mission.mission_id));
    ui.list.append(button);
  }
}

async function loadMission(missionId) {
  const [mission, logs, artifacts, evidence] = await Promise.all([
    api(`/api/missions/${missionId}`),
    api(`/api/missions/${missionId}/logs`),
    api(`/api/missions/${missionId}/artifacts`),
    api(`/api/missions/${missionId}/evidence`),
  ]);
  selectedMission = mission;
  if (!selectedNodeId || !mission.nodes.some((node) => node.node_id === selectedNodeId)) {
    selectedNodeId = mission.current_node_id || mission.nodes[0]?.node_id;
  }
  ui.empty.hidden = true;
  ui.view.hidden = false;
  renderMission(mission, logs.logs, artifacts.artifacts, evidence);
  await refreshList();
}

function renderMission(mission, logs, artifacts, evidence) {
  ui.title.textContent = mission.title;
  ui.request.textContent = mission.request;
  ui.metrics.replaceChildren(
    metric("State", displayState(mission.state), statusClass(mission.state)),
    metric("Risk", mission.risk_level, `risk-${mission.risk_level.toLowerCase()}`),
    metric("Repository", mission.repository),
    metric("Branch", mission.branch),
    metric("Backend", mission.backend),
    metric("Started", mission.started_at ? new Date(mission.started_at).toLocaleTimeString() : "Not started"),
    metric("Duration", duration(mission.started_at, mission.finished_at)),
    metric("Tokens / cost", mission.token_usage == null ? "UNKNOWN" : `${mission.token_usage} / ${mission.cost_amount ?? "UNKNOWN"}`),
  );
  renderActions(mission);
  renderPipeline(mission.nodes, mission.current_node_id);
  renderNode(mission.nodes.find((node) => node.node_id === selectedNodeId) || mission.nodes[0], logs, artifacts);
  renderLogs(logs);
  renderArtifacts(artifacts);
  renderEvidence(evidence);
}

function actionButton(label, className, handler) {
  const button = element("button", className, label);
  button.type = "button";
  button.disabled = busy;
  button.addEventListener("click", async () => {
    if (busy) return;
    busy = true;
    try { await handler(); } catch (error) { showError(error); }
    finally { busy = false; }
  });
  return button;
}

function renderActions(mission) {
  ui.actions.replaceChildren();
  if (mission.state === "DRAFT") {
    ui.actions.append(actionButton("Start execution", "primary", async () => {
      await api(`/api/missions/${mission.mission_id}/start`, { method: "POST" });
      await loadMission(mission.mission_id);
    }));
  }
  if (mission.state === "AWAITING_ARCHITECTURE_APPROVAL") {
    ui.actions.append(actionButton("Approve architecture", "approval", async () => {
      await api(`/api/missions/${mission.mission_id}/approvals`, { method: "POST", body: JSON.stringify({ gate: "architecture" }) });
      await loadMission(mission.mission_id);
    }));
  }
  if (mission.state === "AWAITING_HUMAN_APPROVAL") {
    ui.actions.append(actionButton("Approve PR readiness", "approval", async () => {
      await api(`/api/missions/${mission.mission_id}/approvals`, { method: "POST", body: JSON.stringify({ gate: "human" }) });
      await loadMission(mission.mission_id);
    }));
  }
  const failed = mission.nodes.find((node) => node.state === "FAILED");
  if (mission.state === "FAILED" && failed) {
    ui.actions.append(actionButton(`Retry ${failed.name}`, "retry", async () => {
      await api(`/api/missions/${mission.mission_id}/nodes/${failed.node_id}/retry`, { method: "POST" });
      await loadMission(mission.mission_id);
    }));
  }
  if (!["COMPLETED", "CANCELLED"].includes(mission.state)) {
    ui.actions.append(actionButton("Cancel mission", "danger", async () => {
      await api(`/api/missions/${mission.mission_id}/cancel`, { method: "POST" });
      await loadMission(mission.mission_id);
    }));
  }
}

function renderPipeline(nodes, currentNodeId) {
  ui.pipeline.replaceChildren();
  for (const node of nodes) {
    const card = element("button", `node-card ${statusClass(node.state)} ${node.node_id === currentNodeId ? "current" : ""}`);
    card.type = "button";
    card.setAttribute("role", "listitem");
    const ordinal = String(node.ordinal + 1).padStart(2, "0");
    card.append(
      element("span", "node-ordinal", ordinal),
      element("strong", "node-name", node.name),
      element("span", "node-state", displayState(node.state)),
      element("small", "node-attempt", `Attempt ${node.attempt}`),
    );
    card.addEventListener("click", () => {
      selectedNodeId = node.node_id;
      loadMission(selectedMission.mission_id).catch(showError);
    });
    ui.pipeline.append(card);
  }
}

function renderNode(node, logs, artifacts) {
  ui.node.replaceChildren();
  if (!node) return;
  const facts = element("dl", "node-facts");
  const rows = [
    ["Status", displayState(node.state)],
    ["Backend", node.backend],
    ["Dependencies", node.dependencies.length ? node.dependencies.join(", ") : "None"],
    ["Started", node.started_at || "—"],
    ["Finished", node.finished_at || "—"],
    ["Duration", duration(node.started_at, node.finished_at)],
    ["Attempt", String(node.attempt)],
    ["Validation", node.validation_result],
  ];
  for (const [label, value] of rows) {
    facts.append(element("dt", "", label), element("dd", "", value));
  }
  ui.node.append(
    element("div", `node-heading ${statusClass(node.state)}`, node.name),
    facts,
    element("p", "node-summary", node.summary || "No summary recorded yet."),
    element("p", "node-counts", `${logs.filter((item) => item.node_id === node.node_id).length} logs · ${artifacts.filter((item) => item.node_id === node.node_id).length} artifacts`),
  );
}

function renderLogs(logs) {
  ui.logs.replaceChildren();
  if (!logs.length) {
    ui.logs.append(element("p", "muted", "Waiting for execution output…"));
    return;
  }
  for (const log of logs.slice(-120)) {
    const line = element("div", `log-line stream-${log.stream}`);
    line.append(
      element("time", "", new Date(log.timestamp).toLocaleTimeString()),
      element("span", "log-node", log.node_id),
      element("pre", "", log.message),
    );
    ui.logs.append(line);
  }
  ui.logs.scrollTop = ui.logs.scrollHeight;
}

function renderArtifacts(artifacts) {
  ui.artifacts.replaceChildren();
  if (!artifacts.length) {
    ui.artifacts.append(element("p", "muted", "Artifacts will appear after real work completes."));
    return;
  }
  for (const artifact of artifacts.slice().reverse()) {
    const link = element("a", "artifact-item");
    link.href = `/api/artifacts/${artifact.artifact_id}/content`;
    link.target = "_blank";
    link.rel = "noopener";
    link.append(
      element("span", "artifact-kind", artifact.kind),
      element("strong", "", artifact.name),
      element("small", "", `${artifact.size} B · ${artifact.sha256.slice(0, 12)}`),
    );
    ui.artifacts.append(link);
  }
}

function renderEvidence(evidence) {
  ui.evidence.replaceChildren();
  if (!evidence.available) {
    ui.evidence.append(element("p", "muted", "Evidence has not been generated."));
    return;
  }
  const validity = element("div", `evidence-validity ${evidence.valid ? "valid" : "invalid"}`, evidence.valid ? "COMMIT BINDING VALID" : "EVIDENCE INVALID");
  const commit = element("code", "commit", evidence.bundle.resultCommit);
  const checks = element("div", "check-grid");
  for (const [name, result] of Object.entries(evidence.bundle.checks)) {
    checks.append(element("span", `check ${statusClass(result === "PASS" || result === "NOT_REQUIRED" ? "PASSED" : result)}`, `${name}: ${result}`));
  }
  ui.evidence.append(validity, commit, checks);
  if (evidence.invalidReasons.length) {
    const list = element("ul", "risk-list");
    for (const reason of evidence.invalidReasons) list.append(element("li", "", reason));
    ui.evidence.append(list);
  }
  const details = document.createElement("details");
  details.append(element("summary", "", "Machine-readable bundle"));
  const pre = element("pre", "evidence-json", JSON.stringify(evidence.bundle, null, 2));
  details.append(pre);
  ui.evidence.append(details);
}

ui.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  busy = true;
  const form = new FormData(ui.form);
  try {
    const mission = await api("/api/missions", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(form.entries())),
    });
    selectedNodeId = null;
    await loadMission(mission.mission_id);
  } catch (error) {
    showError(error);
  } finally {
    busy = false;
  }
});

async function poll() {
  try {
    if (selectedMission && !busy) await loadMission(selectedMission.mission_id);
    else await refreshList();
  } catch (error) {
    showError(error);
  }
}

refreshList().catch(showError);
window.setInterval(poll, 1200);

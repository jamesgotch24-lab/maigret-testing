const state = {
  view: "dashboard",
  pollers: new Map(),
  graphSelections: { investigations: new Set(), searches: new Set() },
  activeInvestigationId: null,
};
const $ = (selector) => document.querySelector(selector);
const setTheme = (theme) => {
  document.body.dataset.theme = theme;
  const toggle = $("#theme-toggle");
  if (!toggle) return;
  const isDark = theme === "dark";
  toggle.textContent = isDark ? "☀" : "☾";
  toggle.setAttribute(
    "aria-label",
    isDark ? "Switch to light mode" : "Switch to dark mode",
  );
  toggle.title = isDark ? "Switch to light mode" : "Switch to dark mode";
  localStorage.setItem("maigret-theme", theme);
};
const api = async (path, options = {}) => {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
};
const escapeHtml = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      })[char],
  );
const date = (value) =>
  value
    ? new Date(value).toLocaleString([], {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";
const toast = (message) => {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  $("#toast-region").append(node);
  setTimeout(() => node.remove(), 3500);
};
const openModal = (id) => {
  const modal = $(`#${id}`);
  if (!modal) return;
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  modal.querySelector("input")?.focus();
};
const closeModal = (id) => {
  const modal = $(`#${id}`);
  if (!modal) return;
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
};

function setView(view) {
  state.view = view;
  if (view !== "searches") {
    state.activeInvestigationId = null;
  }
  document
    .querySelectorAll(".nav-item")
    .forEach((item) =>
      item.classList.toggle("active", item.dataset.view === view),
    );
  document
    .querySelectorAll(".view")
    .forEach((item) =>
      item.classList.toggle("active-view", item.id === `view-${view}`),
    );
  const titles = {
    dashboard: ["FIELD NOTES / 01", "Investigation overview"],
    investigations: ["CASE MANAGEMENT / 02", "Investigations"],
    searches: ["COLLECTION HISTORY / 03", "Search history"],
    terminal: ["COMMAND CONSOLE / 04", "Terminal"],
  };
  $("#view-kicker").textContent = titles[view][0];
  if (view === "searches" && state.activeInvestigationId) {
    $("#view-title").textContent = "Investigation search history";
  } else {
    $("#view-title").textContent = titles[view][1];
  }
  if (view === "dashboard") loadDashboard();
  if (view === "investigations") loadInvestigations();
  if (view === "searches") loadSearches();
  if (view === "terminal") loadTerminal();
  if (view === "terminal") {
    setTimeout(() => $("#terminal-input")?.focus(), 80);
  }
}

async function loadDashboard() {
  try {
    const data = await api("/dashboard");
    const metrics = [
      ["Investigations", data.metrics.investigations],
      ["Searches run", data.metrics.searches],
      ["Accounts found", data.metrics.accounts],
      ["Sites checked", data.metrics.sites_checked],
    ];
    $("#metrics").innerHTML = metrics
      .map(
        ([label, value]) =>
          `<div class="metric"><div class="metric-label">${label}</div><div class="metric-value">${value.toLocaleString()}</div></div>`,
      )
      .join("");
    $("#recent-searches").innerHTML = data.recent_searches.length
      ? data.recent_searches.map(searchRow).join("")
      : '<div class="empty">No searches yet. Start your first collection.</div>';
    const total =
      Object.values(data.status_distribution).reduce((a, b) => a + b, 0) || 1;
    $("#distribution").innerHTML = Object.entries(data.status_distribution)
      .map(
        ([key, value]) =>
          `<div class="bar-row"><div class="bar-label"><span>${escapeHtml(key)}</span><strong>${value}</strong></div><div class="bar"><i style="width:${(value / total) * 100}%"></i></div></div>`,
      )
      .join("");
  } catch (error) {
    toast(error.message);
  }
}
function searchRow(search) {
  return `<div class="ledger-row" data-search-id="${search.id}"><div><div class="ledger-main">${escapeHtml(search.username)}</div><div class="ledger-meta">${date(search.created_at)} · ${search.sites_checked}/${search.total_sites || "—"} sites</div></div><span class="badge ${search.status.toLowerCase()}">${escapeHtml(search.status)}</span><strong>${search.positive_count} found</strong></div>`;
}

async function loadInvestigations() {
  try {
    const values = await api("/investigations");
    const select = $('select[name="investigation_id"]');
    if (select) {
      select.innerHTML =
        '<option value="">Create a new investigation</option>' +
        values
          .map(
            (item) =>
              `<option value="${item.id}">${escapeHtml(item.title)}</option>`,
          )
          .join("");
    }
    $("#investigation-list").innerHTML = values.length
      ? values
          .map(
            (item) =>
              `<article class="case-card"><p class="eyebrow">CASE ${String(item.id).padStart(4, "0")}</p><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.primary_username || "No primary username")}</p><p>${item.search_count} searches · ${item.result_count} findings</p><div class="case-actions"><button class="text-button" data-case-id="${item.id}">Open case →</button><button class="text-button danger" data-delete-investigation="${item.id}">Remove case</button></div></article>`,
          )
          .join("")
      : '<div class="empty">No investigations have been created.</div>';
    const investigationSelector = $("#graph-investigation-select");
    if (investigationSelector) {
      const selected = Array.from(state.graphSelections.investigations);
      investigationSelector.innerHTML = values
        .map(
          (item) =>
            `<option value="${item.id}" ${selected.includes(String(item.id)) ? "selected" : ""}>${escapeHtml(item.title)}</option>`,
        )
        .join("");
    }
  } catch (error) {
    toast(error.message);
  }
}
async function loadSearches() {
  try {
    const values = await api("/searches");
    const filteredValues = state.activeInvestigationId
      ? values.filter(
          (item) =>
            Number(item.investigation_id) ===
            Number(state.activeInvestigationId),
        )
      : values;
    $("#search-list").innerHTML = filteredValues.length
      ? `<table class="data-table"><thead><tr><th>Target</th><th>Status</th><th>Progress</th><th>Found</th><th>Created</th></tr></thead><tbody>${filteredValues.map((search) => `<tr class="search-link" data-search-id="${search.id}"><td><strong>${escapeHtml(search.username)}</strong></td><td><span class="badge ${search.status.toLowerCase()}">${escapeHtml(search.status)}</span></td><td>${search.sites_checked}/${search.total_sites || "—"} (${search.progress}%)</td><td>${search.positive_count}</td><td>${date(search.created_at)}</td></tr>`).join("")}</tbody></table>`
      : '<div class="empty">No search history yet.</div>';
    const emptyState =
      filteredValues.length === 0 && state.activeInvestigationId
        ? '<div class="empty">No searches exist for this investigation yet.</div>'
        : null;
    if (emptyState) $("#search-list").innerHTML = emptyState;
    const searchSelector = $("#graph-search-select");
    if (searchSelector) {
      const selected = Array.from(state.graphSelections.searches);
      searchSelector.innerHTML = values
        .map(
          (search) =>
            `<option value="${search.id}" ${selected.includes(String(search.id)) ? "selected" : ""}>${escapeHtml(search.username)} · ${escapeHtml(search.status)}</option>`,
        )
        .join("");
    }
  } catch (error) {
    toast(error.message);
  }
}

async function showSearch(searchId) {
  try {
    const [search, results] = await Promise.all([
      api(`/searches/${searchId}`),
      api(`/searches/${searchId}/results?status=Claimed`),
    ]);
    const container = $("#detail-content");
    container.dataset.searchId = String(searchId);
    container.innerHTML = `<div class="detail-header"><div><p class="eyebrow">SEARCH ${String(search.id).padStart(4, "0")}</p><h2>${escapeHtml(search.username)}</h2></div><button class="modal-close small-close" data-close="detail-modal" aria-label="Close search">×</button></div><div class="detail-grid"><div><dt>Status</dt><dd>${escapeHtml(search.status)}</dd></div><div><dt>Progress</dt><dd>${search.sites_checked}/${search.total_sites || "—"} sites (${search.progress}%)</dd></div><div><dt>Found</dt><dd>${search.positive_count}</dd></div><div><dt>Started</dt><dd>${date(search.started_at)}</dd></div></div><h3>Site results (${results.length})</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>Site</th><th>Status</th><th>Profile</th></tr></thead><tbody>${results.map((result) => `<tr class="result-link" data-result-id="${result.id}"><td>${escapeHtml(result.site)}</td><td><span class="badge ${result.status.toLowerCase()}">${escapeHtml(result.status)}</span></td><td>${result.url ? "Open evidence ↗" : "—"}</td></tr>`).join("")}</tbody></table></div><div class="detail-actions"><a class="text-button" href="/api/searches/${search.id}/report?format=json&preview=true" target="_blank" rel="noopener">Preview JSON ↗</a><a class="text-button" href="/api/searches/${search.id}/report?format=csv&preview=true" target="_blank" rel="noopener">Preview CSV ↗</a><a class="text-button" href="/api/searches/${search.id}/report?format=pdf&preview=true" target="_blank" rel="noopener">Preview PDF ↗</a><a class="text-button" href="/api/searches/${search.id}/report?format=txt&preview=true" target="_blank" rel="noopener">Preview TXT ↗</a><a class="text-button" href="/api/searches/${search.id}/report?format=json">Download JSON report ↗</a><a class="text-button" href="/api/searches/${search.id}/report?format=csv">Download CSV report ↗</a><a class="text-button" href="/api/searches/${search.id}/report?format=pdf">Download PDF report ↗</a></div><p class="muted">CLI command: <code>${escapeHtml(search.command || "maigret " + search.username)}</code></p>`;
    openModal("detail-modal");
    if (search.status === "running" || search.status === "queued")
      watchSearch(search.id);
  } catch (error) {
    toast(error.message);
  }
}
async function showResult(resultId) {
  try {
    const result = await api(`/results/${resultId}`);
    const profile = Object.entries(result.profile || {});
    $("#detail-content").innerHTML =
      `<p class="eyebrow">EVIDENCE RECORD</p><h2>${escapeHtml(result.site)}</h2><div class="detail-grid"><div><dt>Username</dt><dd>${escapeHtml(result.username)}</dd></div><div><dt>Status</dt><dd><span class="badge ${result.status.toLowerCase()}">${escapeHtml(result.status)}</span></dd></div><div><dt>Source</dt><dd><a href="${escapeHtml(result.url)}" target="_blank" rel="noopener">${escapeHtml(result.url || "Unavailable")}</a></dd></div><div><dt>HTTP response</dt><dd>${result.http_status || "—"}</dd></div></div><h3>Extracted profile data</h3>${profile.length ? `<dl class="detail-grid">${profile.map(([key, value]) => `<div><dt>${escapeHtml(key.replaceAll("_", " "))}</dt><dd>${escapeHtml(Array.isArray(value) ? value.join(", ") : value)}</dd></div>`).join("")}</dl>` : '<p class="muted">No structured profile data was extracted.</p>'}<h3>Analyst note</h3><form id="note-form"><label><textarea name="body" required placeholder="Record an observation..." rows="3"></textarea></label><button class="button button-primary">Save note</button></form><div>${(result.notes || []).map((note) => `<p class="ledger-meta">${escapeHtml(note.body)} · ${date(note.created_at)}</p>`).join("")}</div>`;
    openModal("detail-modal");
    $("#note-form").onsubmit = async (event) => {
      event.preventDefault();
      const body = new FormData(event.target).get("body");
      await api(`/results/${result.id}/notes`, {
        method: "POST",
        body: JSON.stringify({ body }),
      });
      toast("Note saved");
      showResult(result.id);
    };
  } catch (error) {
    toast(error.message);
  }
}

function watchSearch(searchId) {
  if (state.pollers.has(searchId)) return;
  const poll = async () => {
    try {
      const search = await api(`/searches/${searchId}/status`);
      const detailModal = $("#detail-modal");
      if (detailModal && detailModal.classList.contains("open")) {
        const openSearch = Number(
          $("#detail-content")?.dataset?.searchId || searchId,
        );
        if (openSearch === Number(searchId)) {
          showSearch(searchId);
        }
      }
      if (search.status === "completed") {
        toast(`Scan complete: ${search.positive_count} accounts found`);
        clearInterval(timer);
        state.pollers.delete(searchId);
        loadDashboard();
        loadSearches();
      } else if (search.status === "failed") {
        toast(`Scan failed: ${search.error_message}`);
        clearInterval(timer);
        state.pollers.delete(searchId);
        loadDashboard();
        loadSearches();
      } else {
        loadDashboard();
        loadSearches();
      }
    } catch (_) {}
  };
  const timer = setInterval(poll, 1800);
  state.pollers.set(searchId, timer);
  poll();
}
async function loadGraph() {
  try {
    const graph = await api("/graph");
    const investigationSelect = $("#graph-investigation-select");
    const searchSelect = $("#graph-search-select");
    if (investigationSelect && !investigationSelect.dataset.ready) {
      const investigations = await api("/investigations");
      investigationSelect.innerHTML = investigations
        .map(
          (item) =>
            `<option value="${item.id}">${escapeHtml(item.title)}</option>`,
        )
        .join("");
      investigationSelect.dataset.ready = "true";
    }
    if (searchSelect && !searchSelect.dataset.ready) {
      const searches = await api("/searches");
      searchSelect.innerHTML = searches
        .map(
          (item) =>
            `<option value="${item.id}">${escapeHtml(item.username)} · ${escapeHtml(item.status)}</option>`,
        )
        .join("");
      searchSelect.dataset.ready = "true";
    }
    const canvas = $("#graph-canvas");
    const selectedInvestigations = Array.from(
      (investigationSelect || {}).selectedOptions || [],
    ).map((option) => Number(option.value));
    const selectedSearches = Array.from(
      (searchSelect || {}).selectedOptions || [],
    ).map((option) => Number(option.value));
    const filteredNodes = graph.nodes.filter((node) => {
      if (!selectedInvestigations.length && !selectedSearches.length)
        return true;
      if (selectedSearches.length)
        return node.searchId && selectedSearches.includes(node.searchId);
      if (selectedInvestigations.length)
        return (
          node.investigationId &&
          selectedInvestigations.includes(node.investigationId)
        );
      return true;
    });
    const filteredEdges = graph.edges.filter(
      (edge) =>
        filteredNodes.some((node) => node.id === edge.source) ||
        filteredNodes.some((node) => node.id === edge.target),
    );
    if (!filteredNodes.length) {
      canvas.innerHTML =
        '<div class="empty" style="color:#b4c9c1">Select one or more investigations or searches to plot the identity graph.</div>';
      return;
    }
    const nodes = filteredNodes.slice(0, 32);
    const initialPositions = new Map(
      nodes.map((node, index) => [
        node.id,
        {
          x: 50 + ((index % 5) - 2) * 17 + (index % 3) * 9,
          y: 50 + (Math.floor(index / 5) - 2) * 18 + (index % 2) * 11,
        },
      ]),
    );
    canvas.dataset.graphNodes = JSON.stringify(
      nodes.map((node) => ({ ...node, ...initialPositions.get(node.id) })),
    );
    canvas.dataset.graphEdges = JSON.stringify(
      filteredEdges.filter(
        (edge) =>
          initialPositions.has(edge.source) &&
          initialPositions.has(edge.target),
      ),
    );
    canvas.dataset.scale = "1";
    canvas.dataset.panX = "0";
    canvas.dataset.panY = "0";
    renderGraphCanvas(canvas, nodes, filteredEdges);
  } catch (error) {
    toast(error.message);
  }
}

function renderGraphCanvas(canvas, nodes, edges) {
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const basePositions = new Map(
    (canvas.dataset.graphNodes
      ? JSON.parse(canvas.dataset.graphNodes)
      : []
    ).map((node) => [node.id, { x: node.x, y: node.y }]),
  );
  const scale = Number(canvas.dataset.scale || 1);
  const panX = Number(canvas.dataset.panX || 0);
  const panY = Number(canvas.dataset.panY || 0);
  const graphNodes = nodes.map((node) => {
    const position = basePositions.get(node.id) || { x: 50, y: 50 };
    return { ...node, x: position.x, y: position.y };
  });
  const graphEdges = (
    canvas.dataset.graphEdges ? JSON.parse(canvas.dataset.graphEdges) : []
  ).filter((edge) => nodeMap.has(edge.source) && nodeMap.has(edge.target));
  const lines = graphEdges
    .map((edge) => {
      const from = graphNodes.find((node) => node.id === edge.source);
      const to = graphNodes.find((node) => node.id === edge.target);
      if (!from || !to) return "";
      const x1 = (from.x + panX) * scale;
      const y1 = (from.y + panY) * scale;
      const x2 = (to.x + panX) * scale;
      const y2 = (to.y + panY) * scale;
      const length = Math.hypot(x2 - x1, y2 - y1);
      const angle = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;
      return `<i class="graph-line" style="left:${Math.min(x1, x2)}%;top:${Math.min(y1, y2)}%;width:${length}%;transform:rotate(${angle}deg)"></i>`;
    })
    .join("");
  canvas.innerHTML =
    lines +
    graphNodes
      .map((node) => {
        const left = (node.x + panX) * scale;
        const top = (node.y + panY) * scale;
        const hue =
          { username: "#f0d896", site: "#f8f7f2", identity: "#d6d6d6" }[
            node.type
          ] || "#f8f7f2";
        return `<div class="graph-node" data-node-id="${node.id}" style="left:${left}%;top:${top}%;border-color:${hue};background:${node.type === "username" ? "#111214" : "#1b1b1d"};color:${node.type === "username" ? "#f4d27a" : "#fff"}"><span>${escapeHtml(node.label)}</span><small>${escapeHtml(node.type)}${node.status ? ` · ${escapeHtml(node.status)}` : ""}</small></div>`;
      })
      .join("");
  canvas.querySelectorAll(".graph-node").forEach((element) => {
    element.addEventListener("click", () => {
      const nodeId = element.dataset.nodeId;
      const node = graphNodes.find((item) => item.id === nodeId);
      if (!node) return;
      element.classList.toggle("selected");
      showGraphNode(node);
    });
  });
}

async function showGraphNode(node) {
  if (!node) return;
  if (node.resultId) {
    showResult(node.resultId);
    return;
  }
  if (node.searchId) {
    showSearch(node.searchId);
    return;
  }
  if (node.investigationId) {
    const investigation = await api(`/investigations/${node.investigationId}`);
    const content = $("#detail-content");
    content.innerHTML = `<div class="detail-header"><div><p class="eyebrow">CASE OVERVIEW</p><h2>${escapeHtml(investigation.title)}</h2></div></div><div class="detail-grid"><div><dt>Primary username</dt><dd>${escapeHtml(investigation.primary_username || "Not set")}</dd></div><div><dt>Searches</dt><dd>${investigation.searches?.length ?? 0}</dd></div></div><p class="muted">${escapeHtml(investigation.description || "No description recorded for this case.")}</p>`;
    openModal("detail-modal");
    return;
  }
  const content = $("#detail-content");
  content.innerHTML = `<div class="detail-header"><div><p class="eyebrow">GRAPH NODE</p><h2>${escapeHtml(node.label || "Unknown")}</h2></div></div><div class="detail-grid"><div><dt>Type</dt><dd>${escapeHtml(node.type || "entity")}</dd></div><div><dt>Source</dt><dd>${escapeHtml(node.source_site || "Not recorded")}</dd></div></div>${node.source_url ? `<p><a href="${escapeHtml(node.source_url)}" target="_blank" rel="noopener">Open source link →</a></p>` : '<p class="muted">No source link is attached to this node.</p>'}`;
  openModal("detail-modal");
}

const graphInteraction = {
  dragging: false,
  startX: 0,
  startY: 0,
  panX: 0,
  panY: 0,
};

function bindGraphInteraction() {
  const canvas = $("#graph-canvas");
  if (!canvas) return;
  canvas.onwheel = (event) => {
    event.preventDefault();
    const currentScale = Number(canvas.dataset.scale || 1);
    const nextScale = Math.min(
      2.2,
      Math.max(0.6, currentScale + (event.deltaY < 0 ? 0.12 : -0.12)),
    );
    canvas.dataset.scale = String(nextScale);
    const graphNodes = canvas.dataset.graphNodes
      ? JSON.parse(canvas.dataset.graphNodes)
      : [];
    const renderNodes = graphNodes.length ? graphNodes : [];
    const renderEdges = canvas.dataset.graphEdges
      ? JSON.parse(canvas.dataset.graphEdges)
      : [];
    renderGraphCanvas(canvas, renderNodes, renderEdges);
  };
  canvas.onpointerdown = (event) => {
    graphInteraction.dragging = true;
    graphInteraction.startX = event.clientX;
    graphInteraction.startY = event.clientY;
    graphInteraction.panX = Number(canvas.dataset.panX || 0);
    graphInteraction.panY = Number(canvas.dataset.panY || 0);
    canvas.setPointerCapture(event.pointerId);
  };
  canvas.onpointermove = (event) => {
    if (!graphInteraction.dragging) return;
    const deltaX = (event.clientX - graphInteraction.startX) / 60;
    const deltaY = (event.clientY - graphInteraction.startY) / 60;
    canvas.dataset.panX = String(graphInteraction.panX + deltaX);
    canvas.dataset.panY = String(graphInteraction.panY + deltaY);
    const graphNodes = canvas.dataset.graphNodes
      ? JSON.parse(canvas.dataset.graphNodes)
      : [];
    const renderEdges = canvas.dataset.graphEdges
      ? JSON.parse(canvas.dataset.graphEdges)
      : [];
    renderGraphCanvas(canvas, graphNodes, renderEdges);
  };
  canvas.onpointerup = () => {
    graphInteraction.dragging = false;
  };
  canvas.onpointerleave = () => {
    graphInteraction.dragging = false;
  };
}

bindGraphInteraction();

function loadTerminal() {
  const output = $("#terminal-output");
  if (!output) return;
  if (!output.dataset.initialized) {
    output.innerHTML =
      '<div class="terminal-line"><span class="terminal-prompt">$</span><span class="terminal-command">python -m maigret --help</span></div>';
    output.dataset.initialized = "true";
  }
  output.scrollTop = output.scrollHeight;
  setTimeout(() => $("#terminal-input")?.focus(), 50);
}

function appendTerminalEntry(command, output, exitCode) {
  const outputNode = $("#terminal-output");
  if (!outputNode) return;
  const line = document.createElement("div");
  line.className = "terminal-line terminal-entry";
  line.innerHTML = `<span class="terminal-prompt">$</span><span class="terminal-command">${escapeHtml(command)}</span>`;
  outputNode.appendChild(line);
  if (output) {
    const outputBlock = document.createElement("pre");
    outputBlock.className = "terminal-output-block";
    outputBlock.textContent = output.trimEnd() || "(no output)";
    outputNode.appendChild(outputBlock);
  }
  const status = document.createElement("div");
  status.className = `terminal-status ${exitCode === 0 ? "success" : "error"}`;
  status.textContent = `Exit code ${exitCode}`;
  outputNode.appendChild(status);
  outputNode.scrollTop = outputNode.scrollHeight;
}

$("#terminal-form").onsubmit = async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const command = String(form.get("command") || "").trim();
  if (!command) return;
  const input = $("#terminal-input");
  input.value = "";
  try {
    const result = await api("/terminal/execute", {
      method: "POST",
      body: JSON.stringify({ command }),
    });
    appendTerminalEntry(result.command, result.output, result.exit_code);
  } catch (error) {
    appendTerminalEntry(command, error.message, 1);
  }
};

$("#search-form").onsubmit = async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const payload = {
    username: form.get("username"),
    title: form.get("title") || null,
    investigation_id: form.get("investigation_id")
      ? Number(form.get("investigation_id"))
      : null,
    timeout: Number(form.get("timeout")),
    top_sites: Number(form.get("top_sites")),
    recursive: form.has("recursive"),
    extract: form.has("extract"),
    permute: form.has("permute"),
    check_domains: form.has("check_domains"),
    all_sites: form.has("all_sites"),
    report_format: form.get("report_format") || "json",
    print_not_found: form.has("print_not_found"),
    print_errors: form.has("print_errors"),
    verbose: form.has("verbose"),
    no_progressbar: form.has("no_progressbar"),
    use_disabled_sites: form.has("use_disabled_sites"),
    tags: (form.get("tags") || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
    excluded_tags: (form.get("excluded_tags") || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
    site_list: (form.get("site_list") || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
    keywords: (form.get("keywords") || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
    proxy: (form.get("proxy") || "").trim() || null,
    tor_proxy: (form.get("tor_proxy") || "").trim() || null,
    i2p_proxy: (form.get("i2p_proxy") || "").trim() || null,
  };
  try {
    const search = await api("/search", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    closeModal("search-modal");
    toast("Investigation started");
    watchSearch(search.id);
    setView("searches");
  } catch (error) {
    toast(error.message);
  }
};
$("#sidebar-toggle").onclick = () =>
  document.getElementById("sidebar").classList.toggle("collapsed");
$("#theme-toggle").onclick = () => {
  const nextTheme = document.body.dataset.theme === "dark" ? "light" : "dark";
  setTheme(nextTheme);
};
const savedTheme = localStorage.getItem("maigret-theme") || "light";
setTheme(savedTheme);
const graphInvestigationsSelect = $("#graph-investigation-select");
if (graphInvestigationsSelect)
  graphInvestigationsSelect.onchange = () => loadGraph();
const graphSearchSelect = $("#graph-search-select");
if (graphSearchSelect) graphSearchSelect.onchange = () => loadGraph();
document.addEventListener("click", (event) => {
  const view = event.target.closest("[data-view]")?.dataset.view;
  if (view) {
    event.preventDefault();
    setView(view);
  }
  const searchId = event.target.closest("[data-search-id]")?.dataset.searchId;
  if (searchId) showSearch(searchId);
  const resultId = event.target.closest("[data-result-id]")?.dataset.resultId;
  if (resultId) showResult(resultId);
  const investigationId = event.target.closest("[data-delete-investigation]")
    ?.dataset.deleteInvestigation;
  if (investigationId) {
    if (!confirm("Remove this investigation and all its saved searches?"))
      return;
    api(`/investigations/${investigationId}`, { method: "DELETE" })
      .then(() => {
        toast("Investigation removed");
        loadInvestigations();
      })
      .catch((error) => toast(error.message));
  }
  const caseId = event.target.closest("[data-case-id]")?.dataset.caseId;
  if (caseId) {
    state.activeInvestigationId = Number(caseId);
    setView("searches");
    toast("Opening investigation search history");
  }
  const close = event.target.closest("[data-close]")?.dataset.close;
  if (close) closeModal(close);
});
$("#new-search-button").onclick = () => {
  loadInvestigations();
  openModal("search-modal");
};
$("#new-case-button").onclick = () => {
  loadInvestigations();
  openModal("search-modal");
};
$("#refresh-button").onclick = () => setView(state.view);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    const openModalId = document.querySelector(".modal.open")?.id;
    if (openModalId) closeModal(openModalId);
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    const terminalInput = $("#terminal-input");
    if (terminalInput) {
      setView("terminal");
      terminalInput.focus();
    }
  }
});
loadDashboard();
loadInvestigations();
loadSearches();

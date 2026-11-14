(() => {
  "use strict";

  const API_BASE = window.OPENDSS_API_BASE || window.location.origin;
  const WS_BASE = window.OPENDSS_WS_BASE
    || API_BASE.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
  const state = {
    models: [], selectedModel: null, originalDss: "", sessionId: null,
    socket: null, result: null, sessionDetail: null, qstsRows: [], events: [],
    qstsSort: { key: "step", direction: 1 }, voltageRows: [],
    customModel: null,
    token: sessionStorage.getItem("opendss_token"),
    currentUser: null,
  };
  const $ = (selector) => document.querySelector(selector);
  const elements = {
    apiDot: $("#apiDot"), wsDot: $("#wsDot"), globalState: $("#globalState"),
    modelSelect: $("#modelSelect"), masterSelect: $("#masterSelect"), modelName: $("#modelName"), modelSource: $("#modelSource"),
    editor: $("#dssEditor"), lineNumbers: $("#lineNumbers"), lineCount: $("#lineCount"),
    validation: $("#validationMessage"), simulationType: $("#simulationType"),
    snapshotOptions: $("#snapshotOptions"), loadMultiplier: $("#loadMultiplier"),
    qstsOptions: document.querySelectorAll(".qsts-option"), durationHours: $("#durationHours"),
    stepMinutes: $("#stepMinutes"), profileSource: $("#profileSource"),
    qstsLoadMultiplier: $("#qstsLoadMultiplier"), valuesInput: $("#valuesInput"),
    valuesCount: $("#valuesCount"), createButton: $("#createBtn"), solveButton: $("#solveBtn"),
    sessionState: $("#sessionStateBadge"), sessionId: $("#sessionId"), copySession: $("#copySessionBtn"),
    resultState: $("#resultState"), progressLabel: $("#progressLabel"), progressPercent: $("#progressPercent"),
    progressBar: $("#progressBar"), progressStep: $("#progressStep"), progressHour: $("#progressHour"),
    progressLoad: $("#progressLoad"), progressDetails: $("#progressDetails"), summaryEmpty: $("#summaryEmpty"),
    summaryJson: $("#summaryJson"), kpiConverged: $("#kpiConverged"), kpiBuses: $("#kpiBuses"),
    kpiNodes: $("#kpiNodes"), kpiEngine: $("#kpiEngine"), kpiTotal: $("#kpiTotal"),
    voltageSearch: $("#voltageSearch"), voltageBody: $("#voltageTableBody"), powersBody: $("#powersTableBody"),
    qstsSearch: $("#qstsSearch"), qstsBody: $("#qstsTableBody"), metricsContent: $("#metricsContent"),
    eventLog: $("#eventLog"), toast: $("#toast"), sessionInput: $("#sessionIdInput"),
    joinButton: $("#joinSessionBtn"), refreshSessions: $("#refreshSessionsBtn"), sessionsList: $("#sessionsList"),
    sessionsMessage: $("#sessionsMessage"), fileInput: $("#fileInput"), uploadButton: $("#uploadBtn"),
    restoreButton: $("#restoreBtn"), validateButton: $("#validateBtn"), refreshMetrics: $("#refreshMetricsBtn"),
    loginPanel: $("#loginPanel"), loginForm: $("#loginForm"), loginUsername: $("#loginUsername"),
    loginPassword: $("#loginPassword"), loginMessage: $("#loginMessage"), workspace: $("#workspace"),
    userStatus: $("#userStatus"), currentUserLabel: $("#currentUserLabel"), logoutButton: $("#logoutBtn"),
  };

  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    const response = await fetch(`${API_BASE}${path}`, {
      ...options, headers,
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) {
      logout(false);
      throw new Error("La sesión expiró o no es válida.");
    }
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    return data;
  }
  function showWorkspace() {
    elements.loginPanel.hidden = true;
    elements.workspace.hidden = false;
    elements.userStatus.hidden = false;
    const user = state.currentUser;
    elements.currentUserLabel.textContent = user ? `${user.username} · ${user.role}` : "";
    const isAdmin = user?.role === "admin";
    elements.uploadButton.hidden = !isAdmin;
    elements.validateButton.hidden = !isAdmin;
    elements.restoreButton.hidden = !isAdmin;
    document.querySelectorAll('[data-panel="metrics"], .tab[data-tab="metrics"]').forEach((item) => {
      item.hidden = !isAdmin;
    });
  }
  function showLogin(message = "") {
    elements.loginPanel.hidden = false;
    elements.workspace.hidden = true;
    elements.userStatus.hidden = true;
    elements.loginMessage.textContent = message;
  }
  function logout(show = true) {
    state.token = null;
    state.currentUser = null;
    sessionStorage.removeItem("opendss_token");
    if (state.socket) state.socket.close();
    if (show) showLogin("Sesión cerrada.");
  }
  async function login(event) {
    event.preventDefault();
    const body = new URLSearchParams({
      username: elements.loginUsername.value,
      password: elements.loginPassword.value,
    });
    try {
      const response = await fetch(`${API_BASE}/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Credenciales inválidas.");
      state.token = data.access_token;
      sessionStorage.setItem("opendss_token", state.token);
      state.currentUser = await api("/auth/me");
      showWorkspace();
      await loadModels();
      await loadSessions();
    } catch (error) {
      logout(false);
      showLogin(error.message);
    }
  }
  async function authenticate() {
    try {
      state.currentUser = await api("/auth/me");
      showWorkspace();
      return true;
    } catch {
      showLogin();
      return false;
    }
  }
  function toast(message) {
    elements.toast.textContent = message; elements.toast.classList.add("show");
    clearTimeout(toast.timer); toast.timer = setTimeout(() => elements.toast.classList.remove("show"), 3500);
  }
  function logEvent(type, detail = "") {
    state.events.unshift({ time: new Date(), type, detail });
    state.events = state.events.slice(0, 100);
    elements.eventLog.replaceChildren(...state.events.map((event) => {
      const item = document.createElement("li");
      item.textContent = `${event.time.toLocaleTimeString()} · ${event.type}${event.detail ? ` · ${event.detail}` : ""}`;
      return item;
    }));
  }
  function setDot(dot, status, title) {
    dot.className = `status-dot status-${status}`; dot.title = title || status;
  }
  function statusText(status) { return String(status || "").toLowerCase(); }
  function setProgress(percent, label) {
    const value = Math.max(0, Math.min(100, Number(percent) || 0));
    elements.progressBar.style.width = `${value}%`; elements.progressPercent.textContent = `${value.toFixed(1)} %`;
    elements.progressLabel.textContent = label;
  }
  function setLine(name, status, elapsed = null) {
    const line = document.querySelector(`.status-line[data-state="${name}"]`);
    if (!line) return;
    line.classList.remove("done", "running", "error"); if (status) line.classList.add(status);
    if (elapsed !== null) line.querySelector("small").textContent = `${Number(elapsed).toFixed(1)} ms`;
  }
  function encode(id) { return encodeURIComponent(id); }
  function expectedSteps() {
    const duration = Number(elements.durationHours.value); const step = Number(elements.stepMinutes.value);
    return duration > 0 && step > 0 && Number.isInteger(duration * 60 / step) ? duration * 60 / step : null;
  }
  function parseValues() {
    return elements.valuesInput.value.split(/[\s,]+/).map(Number).filter((value) => Number.isFinite(value));
  }
  function updateProfileControls() {
    const qsts = elements.simulationType.value === "qsts";
    elements.snapshotOptions.hidden = qsts;
    elements.qstsOptions.forEach((element) => { element.hidden = !qsts; });
    document.querySelectorAll(".profile-option").forEach((element) => {
      element.hidden = !qsts || element.dataset.profile !== elements.profileSource.value;
    });
    const expected = expectedSteps();
    elements.valuesCount.textContent = `Valores esperados: ${expected ?? "—"} · Valores ingresados: ${parseValues().length}`;
  }
  function validateConfiguration() {
    if (elements.simulationType.value === "snapshot") return Number(elements.loadMultiplier.value) > 0;
    const expected = expectedSteps();
    if (!expected) { toast("duration_hours debe ser divisible entre step_minutes."); return false; }
    if (elements.profileSource.value === "values") {
      const count = parseValues().length;
      if (count !== expected) { toast(`Debe ingresar ${expected} multiplicadores; actualmente hay ${count}.`); return false; }
    }
    return true;
  }
  async function loadModels() {
    const models = await api("/models"); state.models = models.filter((model) => model.available);
    elements.modelSelect.replaceChildren(...state.models.map((model) => new Option(model.name, model.id)));
    if (state.models.length) await selectModel(state.models[0].id);
  }
  async function selectModel(id) {
    state.customModel = null;
    elements.masterSelect.hidden = true;
    state.selectedModel = state.models.find((model) => model.id === id); if (!state.selectedModel) return;
    elements.modelName.textContent = state.selectedModel.name; elements.modelSource.textContent = "Modelo disponible en el catálogo.";
    state.originalDss = `// Modelo seleccionado: ${state.selectedModel.id}\n`;
    elements.editor.value = state.originalDss; updateLineNumbers();
    elements.restoreButton.disabled = false;
    elements.validateButton.disabled = false;
    elements.validation.className = "validation-message neutral";
    elements.validation.textContent = "El modelo todavía no ha sido validado.";
  }
  async function selectCustomMaster(master) {
    if (!state.customModel || !master) return;
    state.customModel.master = master;
    const data = await api(`/models/custom/${encode(state.customModel.model_id)}/files/${encode(master)}`);
    state.originalDss = data.content;
    elements.editor.value = data.content;
    elements.modelName.textContent = `custom:${state.customModel.model_id}:${master}`;
    elements.modelSource.textContent = "Modelo personalizado cargado desde la API.";
    elements.restoreButton.disabled = false;
    elements.validateButton.disabled = false;
    elements.validation.className = "validation-message neutral";
    elements.validation.textContent = "El modelo todavía no ha sido validado.";
    updateLineNumbers();
  }
  function updateLineNumbers() {
    const count = Math.max(1, elements.editor.value.split("\n").length);
    elements.lineNumbers.textContent = Array.from({ length: count }, (_, index) => index + 1).join("\n");
    elements.lineCount.textContent = `${count} línea(s)`;
  }
  async function validateModel() {
    if (!elements.editor.value.trim()) {
      elements.validation.className = "validation-message error"; elements.validation.textContent = "El editor está vacío."; return false;
    }
    if (!state.customModel) {
      elements.validation.className = "validation-message valid";
      elements.validation.textContent = "Modelo válido para continuar.";
      return true;
    }
    try {
      await api(`/models/custom/${encode(state.customModel.model_id)}/files/${encode(state.customModel.master)}`, {
        method: "PUT",
        body: JSON.stringify({ content: elements.editor.value }),
      });
      const result = await api(
        `/models/custom/${encode(state.customModel.model_id)}/validate?master=${encode(state.customModel.master)}`,
        { method: "POST" },
      );
      if (!result.valid) throw new Error(result.message || "El backend rechazó el modelo.");
      state.selectedModel = {
        id: `custom:${state.customModel.model_id}:${state.customModel.master}`,
        name: `custom:${state.customModel.model_id}:${state.customModel.master}`,
        source: "custom",
        available: true,
      };
      elements.validation.className = "validation-message valid";
      elements.validation.textContent = "Modelo válido.";
      return true;
    } catch (error) {
      elements.validation.className = "validation-message error";
      elements.validation.textContent = `Modelo inválido: ${error.message}`;
      return false;
    }
  }
  async function uploadCustomModel(file) {
    const form = new FormData();
    form.append("file", file);
    const metadata = await api("/models/upload", { method: "POST", body: form });
    if (!metadata.masters?.length) throw new Error("La API no devolvió masters DSS.");
    state.customModel = {
      model_id: metadata.model_id,
      masters: metadata.masters,
      master: metadata.masters[0],
    };
    const customOption = new Option(`custom:${metadata.model_id}`, `custom:${metadata.model_id}`);
    elements.modelSelect.add(customOption);
    elements.modelSelect.value = customOption.value;
    elements.masterSelect.replaceChildren(...metadata.masters.map((master) => new Option(master, master)));
    elements.masterSelect.hidden = metadata.masters.length <= 1;
    await selectCustomMaster(metadata.masters[0]);
  }
  async function loadSessions() {
    elements.sessionsMessage.textContent = "Cargando simulaciones..."; elements.sessionsList.replaceChildren();
    try {
      const sessions = await api("/simulations");
      elements.sessionsMessage.textContent = sessions.length ? `${sessions.length} simulación(es) activa(s).` : "No hay simulaciones activas.";
      sessions.forEach((session) => {
        const card = document.createElement("article"); card.className = "session-card";
        const title = document.createElement("strong"); title.textContent = session.topology;
        const detail = document.createElement("span"); detail.textContent = `${session.session_id} · ${statusText(session.status)} · ${session.task_count} ejecución(es)`;
        const button = document.createElement("button"); button.className = "button button-secondary"; button.textContent = "Unirse";
        button.type = "button"; button.onclick = () => joinSession(session.session_id); card.append(title, detail, button); elements.sessionsList.append(card);
      });
    } catch (error) { elements.sessionsMessage.textContent = "No se pudo cargar la lista de simulaciones."; logEvent("Lista de simulaciones", error.message); }
  }
  async function joinSession(id) {
    const sessionId = id.trim(); if (!sessionId) { toast("Introduzca un session_id válido."); return; }
    try {
      const session = await api(`/simulations/${encode(sessionId)}`); state.sessionDetail = session; state.sessionId = session.session_id;
      elements.sessionId.textContent = session.session_id; elements.sessionState.textContent = `Sesión ${statusText(session.status)}`;
      elements.copySession.disabled = false; elements.solveButton.disabled = session.status === "CLOSED";
      elements.modelName.textContent = session.topology; elements.modelSource.textContent = "Sesión existente";
      setLine("session", "done"); connectWebSocket();
      if (session.last_result) renderResult(session.last_result); if (session.current_step) updateProgress(session);
      logEvent("Sesión", `unido a ${session.session_id}`);
    } catch (error) { toast(`No fue posible unirse: ${error.message}`); logEvent("Unión rechazada", error.message); }
  }
  function connectWebSocket() {
    if (state.socket) state.socket.close();
    setDot(elements.wsDot, "waiting", "Conectando WebSocket");
    const protocols = state.token ? ["opendss.jwt", state.token] : undefined;
    state.socket = new WebSocket(`${WS_BASE}/ws/simulations/${encode(state.sessionId)}`, protocols);
    state.socket.onopen = () => { setDot(elements.wsDot, "online", "WebSocket conectado"); setLine("ws", "done"); logEvent("WebSocket", "conectado"); };
    state.socket.onclose = () => { setDot(elements.wsDot, "offline", "WebSocket desconectado"); logEvent("WebSocket", "conexión cerrada"); };
    state.socket.onerror = () => { setDot(elements.wsDot, "offline", "Error WebSocket"); toast("El WebSocket perdió la conexión."); };
    state.socket.onmessage = (event) => { try { handleEvent(JSON.parse(event.data)); } catch { logEvent("WebSocket", "evento inválido"); } };
  }
  function updateProgress(data) {
    const step = data.last_qsts_step || data; const total = data.total_steps || state.result?.total_steps || "—";
    const percent = data.progress_pct ?? (step.step && total !== "—" ? step.step / total * 100 : 0);
    setProgress(percent, step.step ? `Paso ${step.step} / ${total}` : "Simulación en ejecución");
    elements.progressStep.textContent = `Paso ${step.step || data.current_step || "—"} / ${total}`;
    elements.progressHour.textContent = `Hora simulada ${step.simulated_hour == null ? "—" : Number(step.simulated_hour).toFixed(2)}`;
    elements.progressLoad.textContent = `LoadMult ${step.load_multiplier == null ? "—" : Number(step.load_multiplier).toFixed(3)}`;
    elements.progressDetails.textContent = `Potencia ${step.total_kw == null ? "—" : `${Number(step.total_kw).toFixed(2)} kW`} · Vmin ${step.min_voltage_pu == null ? "—" : Number(step.min_voltage_pu).toFixed(3)} · Vmax ${step.max_voltage_pu == null ? "—" : Number(step.max_voltage_pu).toFixed(3)} · solve ${step.solve_ms == null ? "—" : `${Number(step.solve_ms).toFixed(2)} ms`}`;
  }
  function handleEvent(message) {
    logEvent(message.type || "evento", message.type === "error" ? (message.error || "Error de simulación") : "");
    if (message.simulation) elements.sessionState.textContent = `Sesión ${statusText(message.simulation.status)}`;
    if (message.type === "snapshot") { updateProgress(message); if (message.last_result) renderResult(message.last_result); }
    if (message.type === "simulation_started") { setLine("solve", "running"); setProgress(message.progress_pct || 0, "Iniciando simulación"); }
    if (message.type === "model_loaded") { setLine("model", "done"); }
    if (message.type === "solving") { setDot(elements.wsDot, "running", "Simulación ejecutándose"); setLine("solve", "running"); }
    if (message.type === "qsts_progress") updateProgress(message);
    if (message.type === "result" && message.result) {
      renderResult(message);
      elements.resultState.textContent = "Resultado recibido";
    }
    if (message.type === "error") { setLine("solve", "error"); toast("La simulación no pudo completarse."); }
    if (message.type === "completed") { setDot(elements.wsDot, "online", "WebSocket conectado"); setLine("solve", "done"); setLine("result", "done"); setProgress(100, "Simulación completada"); loadResults(); }
  }
  async function createSimulation() {
    if (!state.selectedModel || !(await validateModel())) return;
    try {
      const session = await api("/simulations", { method: "POST", body: JSON.stringify({ topology: state.selectedModel.id, load_multiplier: Number(elements.loadMultiplier.value || 1) }) });
      await joinSession(session.session_id); await loadSessions();
    } catch (error) { toast("No fue posible crear la sesión."); logEvent("Creación fallida", error.message); }
  }
  function solvePayload() {
    if (elements.simulationType.value === "snapshot") return { simulation_type: "snapshot", load_multiplier: Number(elements.loadMultiplier.value || 1) };
    const profile = elements.profileSource.value; const qsts = {
      duration_hours: Number(elements.durationHours.value), step_minutes: Number(elements.stepMinutes.value),
      profile_source: profile,
    };
    if (profile === "constant") qsts.load_multiplier = Number(elements.qstsLoadMultiplier.value || 1);
    if (profile === "values") qsts.load_multipliers = parseValues();
    return { simulation_type: "qsts", qsts };
  }
  async function solveSimulation() {
    if (!state.sessionId) { toast("Primero cree o seleccione una simulación."); return; }
    if (!validateConfiguration()) return;
    elements.solveButton.disabled = true; setDot(elements.wsDot, "running", "Simulación ejecutándose"); setLine("solve", "running");
    try {
      await api(`/simulations/${encode(state.sessionId)}/solve`, { method: "POST", body: JSON.stringify(solvePayload()) });
      await loadResults(); await loadSessions();
    } catch (error) { toast("La simulación no pudo completarse."); logEvent("Resolución fallida", error.message); setLine("solve", "error"); }
    finally { elements.solveButton.disabled = false; }
  }
  function normalizeSnapshotResult(payload) {
    const result = payload && payload.result && payload.simulation_type === "snapshot"
      ? payload.result
      : payload;
    return {
      ...result,
      simulation_type: "snapshot",
      model_summary: result?.model_summary || state.sessionDetail?.model_summary || null,
    };
  }
  function normalizeQSTSResult(payload) {
    const result = payload && payload.result && payload.simulation_type === "qsts"
      ? payload.result
      : payload;
    return {
      ...result,
      simulation_type: "qsts",
      model_summary: result?.model_summary || state.sessionDetail?.model_summary || null,
    };
  }
  function normalizeResult(payload) {
    const simulationType = payload?.simulation_type
      || (payload?.result?.config ? "qsts" : "snapshot");
    return simulationType === "qsts"
      ? normalizeQSTSResult(payload)
      : normalizeSnapshotResult(payload);
  }
  async function loadResults() {
    if (!state.sessionId) return;
    try { renderResult(await api(`/simulations/${encode(state.sessionId)}/results`)); }
    catch (error) { logEvent("Resultados", error.message); }
  }
  function cell(value) { const td = document.createElement("td"); td.textContent = value == null ? "—" : value; return td; }
  function rows(body, data, columns, empty) {
    if (!data.length) { body.innerHTML = `<tr><td colspan="${columns.length}" class="table-empty">${empty}</td></tr>`; return; }
    body.replaceChildren(...data.map((item) => { const tr = document.createElement("tr"); tr.append(...columns.map((key) => cell(item[key]))); return tr; }));
  }
  function buildVoltageRows(voltages) {
    return Object.entries(voltages).map(([node, value]) => {
      const [bus, phase] = node.split(".");
      return { node, bus, phase: phase || "—", voltage: Number(value.magnitude).toFixed(4), pu: Number(value.magnitude).toFixed(4), angle: Number(value.angle_deg).toFixed(2) };
    });
  }
  function renderResult(result) {
    const normalizedResult = normalizeResult(result);
    const qsts = normalizedResult.simulation_type === "qsts";
    const normalized = qsts && result.summary
      ? { ...normalizedResult.summary, ...normalizedResult, ...(normalizedResult.summary || {}) }
      : normalizedResult;
    state.result = normalized; elements.summaryEmpty.hidden = true; elements.summaryJson.hidden = false;
    elements.summaryJson.textContent = JSON.stringify(result, null, 2);
    elements.resultState.textContent = qsts ? "QSTS completado" : (normalized.converged ? "Convergente" : "No convergente");
    elements.kpiConverged.textContent = qsts ? `${normalized.converged_steps}/${normalized.total_steps}` : (normalized.converged ? "Sí" : "No");
    elements.kpiBuses.textContent = normalized.model_summary?.num_buses ?? "—"; elements.kpiNodes.textContent = normalized.model_summary?.num_nodes ?? Object.keys(normalized.voltages || {}).length;
    elements.kpiEngine.textContent = `${Number(normalized.elapsed_ms || 0).toFixed(2)} ms`; elements.kpiTotal.textContent = `${Number(normalized.elapsed_ms || 0).toFixed(2)} ms`;
    if (qsts) { state.qstsRows = result.steps || normalized.steps || []; renderQstsRows(); elements.progressStep.textContent = `Paso ${normalized.total_steps} / ${normalized.total_steps}`; setProgress(100, "Simulación completada"); }
    else { state.voltageRows = buildVoltageRows(normalized.voltages || {}); renderVoltageRows(); rows(elements.powersBody, [["Potencia activa total (kW)", normalized.total_power_kw], ["Potencia reactiva total (kvar)", normalized.total_power_kvar], ["Load multiplier", normalized.load_multiplier]].map(([concept, value]) => ({ concept, value })), ["concept", "value"], "Sin resultados."); }
    setLine("result", "done", normalized.elapsed_ms);
  }
  function renderVoltageRows() {
    const query = elements.voltageSearch.value.toLowerCase(); const filtered = state.voltageRows.filter((row) => Object.values(row).join(" ").toLowerCase().includes(query));
    rows(elements.voltageBody, filtered, ["node", "bus", "phase", "voltage", "pu", "angle"], "Sin resultados.");
  }
  function renderQstsRows() {
    const query = elements.qstsSearch.value.toLowerCase(); const sorted = [...state.qstsRows].sort((a, b) => {
      const key = state.qstsSort.key; return (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : 0) * state.qstsSort.direction;
    }).filter((row) => Object.values(row).join(" ").toLowerCase().includes(query));
    rows(elements.qstsBody, sorted, ["simulated_hour", "step", "load_multiplier", "total_kw", "total_kvar", "min_voltage_pu", "max_voltage_pu", "solve_ms", "converged"], "Ejecute un QSTS.");
  }
  function metricStats(value) { return value ? `p50 ${value.p50 ?? "—"} · p95 ${value.p95 ?? "—"} · p99 ${value.p99 ?? "—"} · max ${value.max ?? "—"}` : "—"; }
  function metricCard(title, values) {
    const article = document.createElement("article"); article.className = "metric-card"; const heading = document.createElement("strong"); heading.textContent = title; article.append(heading);
    Object.entries(values).forEach(([key, value]) => { const line = document.createElement("div"); line.innerHTML = `<span>${key}</span><b>${value}</b>`; article.append(line); }); return article;
  }
  async function loadMetrics() {
    try {
      const data = await api("/metrics"); const snapshot = data.snapshot || {}; const qsts = data.qsts || {};
      elements.metricsContent.replaceChildren(
        metricCard("Process", { "RSS MB": data.process?.rss_mb ?? "—", "CPU %": data.process?.cpu_percent ?? "—", threads: data.process?.threads ?? "—" }),
        metricCard("Sessions", data.sessions || {}),
        metricCard("Snapshot", { count: snapshot.solve_count ?? 0, stats: metricStats(snapshot.solve) }),
        metricCard("QSTS", { runs: qsts.runs ?? 0, steps: qsts.total_steps ?? 0, stats: metricStats(qsts.step) }),
      );
    } catch (error) { toast("No fue posible cargar las métricas."); logEvent("Métricas", error.message); }
  }
  function registerEvents() {
    elements.modelSelect.onchange = (event) => selectModel(event.target.value);
    elements.masterSelect.onchange = (event) => selectCustomMaster(event.target.value);
    elements.editor.oninput = updateLineNumbers; elements.validateButton.onclick = () => validateModel();
    elements.restoreButton.onclick = () => { elements.editor.value = state.originalDss; updateLineNumbers(); };
    elements.simulationType.onchange = updateProfileControls; elements.profileSource.onchange = updateProfileControls;
    elements.durationHours.oninput = updateProfileControls; elements.stepMinutes.oninput = updateProfileControls; elements.valuesInput.oninput = updateProfileControls;
    elements.createButton.onclick = createSimulation; elements.solveButton.onclick = solveSimulation; elements.copySession.onclick = () => navigator.clipboard.writeText(state.sessionId).then(() => toast("session_id copiado."));
    elements.joinButton.onclick = () => joinSession(elements.sessionInput.value); elements.sessionInput.onkeydown = (event) => { if (event.key === "Enter") joinSession(elements.sessionInput.value); };
    elements.refreshSessions.onclick = loadSessions; elements.voltageSearch.oninput = renderVoltageRows; elements.qstsSearch.oninput = renderQstsRows; elements.refreshMetrics.onclick = loadMetrics;
    document.querySelectorAll("[data-qsts-sort]").forEach((header) => header.onclick = () => { const key = header.dataset.qstsSort; state.qstsSort = { key, direction: state.qstsSort.key === key ? -state.qstsSort.direction : 1 }; renderQstsRows(); });
    document.querySelectorAll(".tab").forEach((tab) => tab.onclick = () => { document.querySelectorAll(".tab,.tab-panel").forEach((item) => item.classList.remove("is-active", "is-visible")); tab.classList.add("is-active"); $(`[data-panel="${tab.dataset.tab}"]`)?.classList.add("is-visible"); });
    elements.uploadButton.onclick = () => elements.fileInput.click();
    elements.fileInput.onchange = async (event) => {
      const file = event.target.files[0];
      if (!file) return;
      try {
        await uploadCustomModel(file);
        logEvent("Modelo personalizado", "cargado en la API");
      } catch (error) {
        toast(`No fue posible cargar el modelo: ${error.message}`);
        logEvent("Modelo personalizado", error.message);
      }
    };
    elements.loginForm.onsubmit = login;
    elements.logoutButton.onclick = () => logout();
  }
  async function initialize() {
    registerEvents(); updateProfileControls(); setDot(elements.apiDot, "waiting", "Comprobando API");
    try {
      if (!(await authenticate())) return;
      await loadModels(); setDot(elements.apiDot, "online", "API disponible"); elements.globalState.textContent = "API disponible"; await loadSessions();
    }
    catch (error) { setDot(elements.apiDot, "offline", "API no disponible"); elements.globalState.textContent = "API no disponible"; toast("No fue posible conectar con la API."); logEvent("API", error.message); }
  }
  initialize();
})();

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
    sessionListVersion: 0, joinVersion: 0, sharingVersion: 0, modelVersion: 0,
    masterChoices: new Map(), modelChecking: false, creatingSimulation: false,
    requestSessionId: null, invitationPending: false,
    batchSolving: null, interactiveRunId: null, reconnectTimer: null,
    currentUser: null,
  };
  const $ = (selector) => document.querySelector(selector);
  const authChannel =
  typeof BroadcastChannel !== "undefined"
    ? new BroadcastChannel(
        "opendss-auth"
      )
    : null;
  authChannel?.addEventListener(
    "message",
    (event) => {
      if (
        event.data?.type === "logout"
      ) {
        resetAuthenticatedUi(
          "Sesión cerrada en otra pestaña."
        );
      }
    }
  );
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
    invitationsList: $("#invitationsList"), invitationsMessage: $("#invitationsMessage"),
    requestAccessButton: $("#requestAccessBtn"), sessionTopology: $("#sessionTopology"),
    restoreButton: $("#restoreBtn"), validateButton: $("#validateBtn"), refreshMetrics: $("#refreshMetricsBtn"),
    loginPanel: $("#loginPanel"), loginForm: $("#loginForm"), loginUsername: $("#loginUsername"),
    loginPassword: $("#loginPassword"), loginMessage: $("#loginMessage"), workspace: $("#workspace"),
    userStatus: $("#userStatus"), currentUserLabel: $("#currentUserLabel"), logoutButton: $("#logoutBtn"),
    sharingPanel: $("#sharingPanel"),
    inviteUserSelect: $("#inviteUserSelect"),
    inviteRoleSelect: $("#inviteRoleSelect"),
    inviteUserButton: $("#inviteUserBtn"),
    refreshSharing: $("#refreshSharingBtn"), sharingMessage: $("#sharingMessage"),
    viewersList: $("#viewersList"),
    accessRequestsList: $("#accessRequestsList"),
  };
  const interactive = window.createInteractiveControls({
    api, getSession: () => state.sessionDetail, toast, onUpdate: renderInteractiveResults, showTab,
  });
  function resetAuthenticatedUi(message = "") {
    if (state.currentUser) {
      try {
        sessionStorage.removeItem(modelPreferenceKey());
      } catch {
        // The workspace also works when browser storage is disabled.
      }
    }
    state.currentUser = null;
    state.joinVersion += 1;
    state.sessionListVersion += 1;
    state.modelVersion += 1;
    state.masterChoices.clear();
    state.models = [];
    state.selectedModel = null;
    state.customModel = null;
    state.originalDss = "";
    state.events = [];
    elements.editor.value = "";
    elements.modelSelect.replaceChildren();
    elements.masterSelect.replaceChildren();
    elements.sessionInput.value = "";
    elements.eventLog.replaceChildren();
    elements.sessionsList.replaceChildren();
    elements.invitationsList.replaceChildren();
    showAccessRequest(null);
    clearSession();
    elements.loginPassword.value = "";
    showLogin(message);
  }
  async function api(path, options = {}) {
    const user = state.currentUser;
    const headers = { ...(options.headers || {}) };
    if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
    const response = await fetch(`${API_BASE}${path}`, {
      ...options, headers, credentials: "same-origin",
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && user === state.currentUser) {
      authChannel?.postMessage({
        type: "logout",
      });

      resetAuthenticatedUi(
        "La sesión expiró o no es válida."
      );
    }
    if (!response.ok) {
      const message = response.status === 401
        ? "La sesión expiró o no es válida."
        : (typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
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
  async function logout(
    show = true,
    broadcast = true
  ) {
    try {
      await fetch(
        `${API_BASE}/auth/logout`,
        {
          method: "POST",
          credentials: "same-origin",
        }
      );
    } catch {
    } finally {
      if (broadcast) {
        authChannel?.postMessage({
          type: "logout",
        });
      }

      resetAuthenticatedUi(
        show
          ? "Sesión cerrada."
          : ""
      );
    }
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
    else if (!status) line.querySelector("small").textContent = "—";
  }
  function encode(id) { return encodeURIComponent(id); }
  function expectedSteps() {
    const duration = Number(elements.durationHours.value); const step = Number(elements.stepMinutes.value);
    const ratio = duration * 60 / step;
    return duration > 0 && step > 0 && Math.abs(ratio - Math.round(ratio)) < 1e-9 ? Math.round(ratio) : null;
  }
  function parseValues() {
    return elements.valuesInput.value.trim().split(/[\s,]+/).filter(Boolean).map(Number);
  }
  function updateProfileControls() {
    const qsts = elements.simulationType.value.startsWith("qsts");
    $("#interactiveSetup").hidden = elements.simulationType.value !== "qsts_interactive";
    elements.snapshotOptions.hidden = qsts;
    elements.qstsOptions.forEach((element) => { element.hidden = !qsts; });
    document.querySelectorAll(".profile-option").forEach((element) => {
      element.hidden = !qsts || element.dataset.profile !== elements.profileSource.value;
    });
    const expected = expectedSteps();
    elements.valuesCount.textContent = `Valores esperados: ${expected ?? "—"} · Valores ingresados: ${parseValues().length}`;
    updateSolveControl();
  }
  function validateConfiguration() {
    if (elements.simulationType.value === "snapshot") return Number(elements.loadMultiplier.value) > 0;
    const expected = expectedSteps();
    if (!expected) { toast("duration_hours debe ser divisible entre step_minutes."); return false; }
    if (elements.profileSource.value === "values") {
      const values = parseValues();
      const count = values.length;
      if (count !== expected) { toast(`Debe ingresar ${expected} multiplicadores; actualmente hay ${count}.`); return false; }
      if (values.some((value) => !Number.isFinite(value) || value <= 0)) {
        toast("Cada multiplicador debe ser un número positivo.");
        return false;
      }
    }
    return true;
  }
  function customCatalogEntry(model) {
    return { ...model, id: `custom:${model.model_id}`, available: true };
  }

  function renderModelOptions() {
    elements.modelSelect.replaceChildren(...state.models.map((model) => new Option(model.name, model.id)));
  }

  function modelPreferenceKey() {
    return `opendss-model:${state.currentUser.username}`;
  }

  function rememberModelSelection() {
    if (!state.currentUser || !state.selectedModel) return;
    try {
      sessionStorage.setItem(modelPreferenceKey(), JSON.stringify({
        id: state.selectedModel.id,
        master: state.customModel?.master ?? null,
      }));
    } catch {
      // The catalog still works when browser storage is disabled.
    }
  }

  async function loadModels(preferredId = state.selectedModel?.id) {
    const user = state.currentUser;
    const standardModels = await api("/models");
    if (user !== state.currentUser) return;

    let customModels = [];
    if (user?.role === "admin") {
      try {
        customModels = await api("/models/custom");
      } catch (error) {
        if (user === state.currentUser) {
          toast("No fue posible cargar el catálogo personalizado.");
          logEvent("Catálogo personalizado", error.message);
        }
      }
    }
    if (user !== state.currentUser) return;

    state.models = [...standardModels, ...customModels.map(customCatalogEntry)].filter((model) => model.available);
    renderModelOptions();
    try {
      const preference = JSON.parse(sessionStorage.getItem(modelPreferenceKey()));
      const stored = state.models.find((model) => model.id === preference?.id);
      if (stored) {
        preferredId ??= stored.id;
        if (stored.masters?.includes(preference.master)) {
          state.masterChoices.set(stored.model_id, preference.master);
        }
      }
    } catch {
      // A stale or unavailable preference leaves the catalog defaults in place.
    }
    await selectModel(state.models.find((model) => model.id === preferredId)?.id ?? state.models[0]?.id);
  }

  function showValidation(status, message) {
    elements.validation.className = `validation-message ${status}`;
    elements.validation.textContent = message;
  }

  function updateModelButtons() {
    const ready = state.selectedModel && (!state.customModel || state.customModel.master);
    elements.createButton.disabled = !ready || state.creatingSimulation || state.modelChecking;
    elements.validateButton.disabled = !ready || state.modelChecking;
    elements.restoreButton.disabled = !ready;
  }

  async function selectModel(id) {
    state.modelVersion += 1;
    state.selectedModel = state.models.find((model) => model.id === id) ?? null;
    state.customModel = null;
    elements.masterSelect.hidden = true;
    elements.masterSelect.replaceChildren();
    elements.modelSelect.value = state.selectedModel?.id ?? "";
    elements.editor.readOnly = false;
    const model = state.selectedModel;
    if (model?.source === "custom") {
      state.customModel = { model_id: model.model_id, master: null };
      const master = state.masterChoices.get(model.model_id) ?? model.recommended_master ?? "";
      elements.masterSelect.replaceChildren(
        new Option("Seleccione el archivo master DSS", ""),
        ...model.masters.map((candidate) => new Option(candidate, candidate)),
      );
      elements.masterSelect.hidden = model.masters.length <= 1;
      elements.masterSelect.value = master;
      await selectCustomMaster(master);
      return;
    }

    elements.modelName.textContent = model?.name ?? "Sin modelo seleccionado";
    elements.modelSource.textContent = model ? "Modelo disponible en el catálogo." : "Seleccione un modelo disponible.";
    state.originalDss = model ? `// Modelo seleccionado: ${model.id}\n` : "";
    elements.editor.value = state.originalDss;
    showValidation("neutral", "El modelo todavía no ha sido validado.");
    updateLineNumbers();
    updateModelButtons();
    rememberModelSelection();
  }

  function customFileUrl(modelId, master) {
    const path = master.split("/").map(encode).join("/");
    return `/models/custom/${encode(modelId)}/files/${path}`;
  }

  async function selectCustomMaster(master) {
    const model = state.customModel;
    if (!model) return;
    const version = ++state.modelVersion;
    model.master = null;
    state.originalDss = "";
    elements.editor.value = "";
    elements.editor.readOnly = true;
    elements.modelName.textContent = state.selectedModel.name;
    elements.modelSource.textContent = "Modelo personalizado";
    showValidation("neutral", master ? "Cargando archivo master…" : "Seleccione el archivo master DSS.");
    updateLineNumbers();
    updateModelButtons();
    if (!master) {
      rememberModelSelection();
      return;
    }
    try {
      const data = await api(customFileUrl(model.model_id, master));
      if (version !== state.modelVersion) return;
      model.master = master;
      state.masterChoices.set(model.model_id, master);
      state.originalDss = data.content;
      elements.editor.value = data.content;
      elements.editor.readOnly = false;
      elements.modelSource.textContent = master;
      showValidation("neutral", "El modelo todavía no ha sido validado.");
      updateLineNumbers();
      updateModelButtons();
      rememberModelSelection();
    } catch (error) {
      if (version === state.modelVersion) {
        elements.masterSelect.hidden = false;
        elements.masterSelect.value = "";
        showValidation("error", `No fue posible leer el master: ${error.message}`);
      }
    }
  }

  function updateLineNumbers() {
    const count = Math.max(1, elements.editor.value.split("\n").length);
    elements.lineNumbers.textContent = Array.from({ length: count }, (_, index) => index + 1).join("\n");
    elements.lineCount.textContent = `${count} línea(s)`;
  }

  async function validateModel() {
    const model = state.selectedModel;
    const custom = state.customModel;
    if (!model || (custom && !custom.master) || state.modelChecking) return null;
    const content = elements.editor.value;
    if (!content.trim()) {
      showValidation("error", "El editor está vacío.");
      return null;
    }
    if (!custom) {
      showValidation("valid", "Modelo válido para continuar.");
      return model.id;
    }

    const version = state.modelVersion;
    const master = custom.master;
    state.modelChecking = true;
    updateModelButtons();
    showValidation("neutral", "Validando circuito con el worker…");
    try {
      if (content !== state.originalDss) {
        await api(customFileUrl(custom.model_id, master), {
          method: "PUT",
          body: JSON.stringify({ content }),
        });
      } else {
        const result = await api(`/models/custom/${encode(custom.model_id)}/validate?master=${encode(master)}`, {
          method: "POST",
        });
        if (!result.valid) throw new Error(result.message || "El worker rechazó el modelo.");
      }
      if (version !== state.modelVersion) return null;
      state.originalDss = content;
      showValidation("valid", "Modelo válido.");
      return `${model.id}:${master}`;
    } catch (error) {
      if (version === state.modelVersion) {
        showValidation("error", `No fue posible validar el modelo: ${error.message}`);
      }
      return null;
    } finally {
      state.modelChecking = false;
      updateModelButtons();
    }
  }

  async function uploadCustomModel(file) {
    const user = state.currentUser;
    const form = new FormData();
    form.append("file", file);
    const metadata = await api("/models/upload", { method: "POST", body: form });
    if (user !== state.currentUser) return;
    const model = customCatalogEntry(metadata);
    state.models.push(model);
    renderModelOptions();
    await selectModel(model.id);
  }
  function actionButton(label, action) {
    const button = document.createElement("button");
    button.className = "button button-secondary";
    button.type = "button";
    button.textContent = label;
    button.onclick = () => action(button);
    return button;
  }

  function sessionCard(session, invited) {
    const accessLabels = {
      owner: "Propietario", viewer: "Espectador", operator: "Operador", admin: "Administrador",
      requestable: "Acceso por solicitud", requested: "Solicitud pendiente",
    };
    const card = document.createElement("article");
    card.className = "session-card";
    const title = document.createElement("strong");
    title.textContent = session.topology === "custom" ? "Modelo personalizado" : session.topology;
    const detail = document.createElement("span");
    detail.textContent = `${session.owner_id || "—"} · ${statusText(session.status)} · ${session.session_id}`;
    detail.title = detail.textContent;
    const access = document.createElement("span");
    access.className = "session-access";
    access.textContent = accessLabels[session.access_mode] || "Acceso disponible";

    let button;
    if (session.access_mode === "requestable") {
      button = actionButton("Solicitar acceso", (control) => requestAccess(session.session_id, control));
    } else if (session.access_mode === "requested") {
      button = actionButton("Solicitud enviada", () => {});
      button.disabled = true;
    } else {
      button = actionButton(invited ? "Abrir simulación" : "Abrir", () => joinSession(session.session_id));
    }
    card.append(title, detail, access, button);
    return card;
  }

  async function loadSessions() {
    if (!state.currentUser) return;
    const version = ++state.sessionListVersion;
    try {
      const sessions = await api("/simulations");
      if (version !== state.sessionListVersion) return;
      const invitations = sessions.filter((session) => session.invited);
      const others = sessions.filter((session) => !session.invited);
      elements.invitationsMessage.textContent = invitations.length ? "" : "No tienes invitaciones activas.";
      elements.invitationsList.replaceChildren(...invitations.map((session) => sessionCard(session, true)));
      elements.sessionsMessage.textContent = others.length
        ? `${others.length} simulación(es) disponible(s).`
        : "No hay otras simulaciones disponibles.";
      elements.sessionsList.replaceChildren(...others.map((session) => sessionCard(session, false)));
    } catch (error) {
      if (version === state.sessionListVersion) {
        elements.sessionsMessage.textContent = "No se pudo cargar la lista de simulaciones.";
        elements.invitationsMessage.textContent = "No se pudieron actualizar las invitaciones.";
        logEvent("Lista de simulaciones", error.message);
      }
    }
  }

  function showAccessRequest(sessionId) {
    state.requestSessionId = sessionId;
    elements.requestAccessButton.hidden = !sessionId;
    elements.requestAccessButton.disabled = false;
  }

  async function requestAccess(sessionId, button) {
    const user = state.currentUser;
    button.disabled = true;
    try {
      await api(`/simulations/${encode(sessionId)}/access-requests`, { method: "POST" });
      if (user !== state.currentUser) return;
      if (state.requestSessionId === sessionId) showAccessRequest(null);
      toast("Solicitud enviada.");
      await loadSessions();
    } catch (error) {
      if (user === state.currentUser) toast(`No fue posible solicitar acceso: ${error.message}`);
    } finally {
      button.disabled = false;
    }
  }

  function clearSession() {
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
    const socket = state.socket;
    state.socket = null;
    socket?.close();
    state.sessionId = null;
    state.sessionDetail = null;
    state.interactiveRunId = null;
    interactive.reset();
    state.sharingVersion += 1;
    state.result = null;
    state.voltageRows = [];
    state.qstsRows = [];
    elements.sessionId.textContent = "—";
    elements.sessionState.textContent = "Sin sesión";
    elements.sessionTopology.hidden = true;
    elements.sessionTopology.textContent = "";
    elements.copySession.disabled = true;
    elements.solveButton.disabled = true;
    elements.sharingPanel.hidden = true;
    elements.sharingMessage.textContent = "";
    elements.inviteUserSelect.replaceChildren();
    elements.inviteUserButton.disabled = true;
    elements.viewersList.replaceChildren();
    elements.accessRequestsList.replaceChildren();
    elements.resultState.textContent = "Sin resultados";
    elements.summaryEmpty.hidden = false;
    elements.summaryJson.hidden = true;
    elements.summaryJson.textContent = "";
    [elements.kpiConverged, elements.kpiBuses, elements.kpiNodes, elements.kpiEngine, elements.kpiTotal]
      .forEach((element) => { element.textContent = "—"; });
    renderVoltageRows();
    renderQstsRows();
    rows(elements.powersBody, [], ["concept", "value"], "Sin resultados.");
    updateProgress({});
    setProgress(0, "Esperando simulación");
    ["session", "ws", "model", "solve", "result"].forEach((line) => setLine(line, null));
    setDot(elements.wsDot, "offline", "WebSocket desconectado");
  }

  function canControlSession(session) {
    return session?.access_mode === "owner" || session?.access_mode === "admin";
  }

  function updateSolveControl() {
    const session = state.sessionDetail;
    const wantsInteractive = elements.simulationType.value === "qsts_interactive";
    const run = interactive.state();
    const live = run && ["initializing", "ready", "paused", "running"].includes(run.phase);
    elements.solveButton.textContent = wantsInteractive ? "Inicializar QSTS interactivo" : "Ejecutar simulación";
    elements.solveButton.disabled = !canControlSession(session) || session?.status === "CLOSED"
      || state.batchSolving === session || interactive.busy()
      || (wantsInteractive ? Boolean(live) : interactive.blocksLegacy());
  }

  function showTab(name) {
    document.querySelectorAll(".tab,.tab-panel").forEach((item) => item.classList.remove("is-active", "is-visible"));
    $(`[data-tab="${name}"]`)?.classList.add("is-active");
    $(`[data-panel="${name}"]`)?.classList.add("is-visible");
  }

  function renderInteractiveResults(run, series) {
    updateSolveControl();
    if (!run || !series) return;
    if (state.interactiveRunId !== run.run_id) {
      state.interactiveRunId = run.run_id;
      elements.simulationType.value = "qsts_interactive";
      updateProfileControls();
      state.voltageRows = [];
      renderVoltageRows();
      showTab("qsts");
    }
    state.qstsRows = series.slice(-1000);
    renderQstsRows();
    const step = run.latest_result;
    const status = $("#interactivePhase").textContent;
    elements.sessionState.textContent = `QSTS · ${status}`;
    updateProgress({
      ...(step || {}), total_steps: run.total_steps, simulated_hour: run.simulated_minutes / 60,
    });
    setProgress(run.completed_steps / run.total_steps * 100, `QSTS · ${status}`);
    elements.progressStep.textContent = `Paso ${run.completed_steps} / ${run.total_steps}`;
    elements.resultState.textContent = run.results_stale ? "Resultado del paso anterior" : (step ? "QSTS interactivo" : "Sin resultados");
    elements.kpiConverged.textContent = step ? (step.converged ? "Sí" : "No") : "—";
    elements.kpiBuses.textContent = state.sessionDetail?.model_summary?.num_buses ?? "—";
    elements.kpiNodes.textContent = state.sessionDetail?.model_summary?.num_nodes ?? "—";
    elements.kpiEngine.textContent = step ? `${step.solve_ms.toFixed(2)} ms` : "—";
    elements.kpiTotal.textContent = series.length ? `${series.reduce((sum, item) => sum + item.solve_ms, 0).toFixed(2)} ms` : "—";
    elements.summaryEmpty.hidden = Boolean(step);
    elements.summaryJson.hidden = !step;
    elements.summaryJson.textContent = step ? JSON.stringify(run, null, 2) : "";
    rows(elements.powersBody, step ? [
      {concept: "Potencia activa (kW)", value: step.total_kw},
      {concept: "Potencia reactiva (kvar)", value: step.total_kvar},
      {concept: "Pérdidas activas (kW)", value: step.loss_kw},
      {concept: "Pérdidas reactivas (kvar)", value: step.loss_kvar},
    ] : [], ["concept", "value"], "Sin resultados.");
    setLine("result", step ? "done" : null, step?.solve_ms ?? null);
  }

  async function joinSession(id) {
    const sessionId = id.trim();
    if (!sessionId) {
      toast("Introduzca un session_id válido.");
      return;
    }
    const version = ++state.joinVersion;
    showAccessRequest(null);

    let session;
    try {
      session = await api(`/simulations/${encode(sessionId)}`);
    } catch (error) {
      if (version !== state.joinVersion) return;
      if (error.status === 403) showAccessRequest(sessionId);
      toast(`No fue posible unirse: ${error.message}`);
      logEvent("Unión rechazada", error.message);
      return;
    }
    if (version !== state.joinVersion) return;

    clearSession();
    state.sessionDetail = session;
    state.sessionId = session.session_id;
    elements.sessionId.textContent = session.session_id;
    elements.sessionState.textContent = `Sesión ${statusText(session.status)}`;
    elements.sessionTopology.textContent = session.topology;
    elements.sessionTopology.hidden = false;
    elements.copySession.disabled = false;
    const canControl = canControlSession(session);
    updateSolveControl();
    setLine("session", "done");
    connectWebSocket(session.session_id);
    void interactive.sync();
    if (session.last_result) renderResult(session.last_result);
    if (session.current_step != null || session.status === "RUNNING") updateProgress(session);
    logEvent("Sesión", `unido a ${session.session_id}`);

    if (canControl) {
      elements.sharingPanel.hidden = false;
      void loadSharing(session.session_id);
    }
  }

  function renderSharingRows(container, usernames, empty, actions, display = (username) => username) {
    if (!usernames.length) {
      container.textContent = empty;
      return;
    }
    container.replaceChildren(...usernames.map((username) => {
      const row = document.createElement("div");
      row.className = "sharing-user";
      const label = document.createElement("span");
      label.textContent = display(username);
      const buttons = document.createElement("div");
      buttons.className = "sharing-user-actions";
      buttons.append(...actions(username));
      row.append(label, buttons);
      return row;
    }));
  }

  function renderParticipants(sessionId, participants) {
    const byName = new Map(participants.map((item) => [item.username, item]));
    renderSharingRows(elements.viewersList, [...byName.keys()], "Sin participantes autorizados.", (username) => {
      const path = `participants/${encode(username)}`;
      const role = document.createElement("select");
      role.className = "select";
      role.setAttribute("aria-label", `Rol de ${username}`);
      role.append(new Option("Espectador", "viewer"), new Option("Operador", "operator"));
      role.value = byName.get(username).role;
      return [
        role,
        actionButton("Guardar rol", (button) => shareAction(
          sessionId, path, "PUT", button, `Se actualizó el rol de ${username}.`, {role: role.value},
        )),
        actionButton("Quitar acceso", (button) => shareAction(
          sessionId, path, "DELETE", button, `Se quitó el acceso de ${username}.`,
        )),
      ];
    }, (username) => byName.get(username).invited ? `${username} · Invitación enviada` : username);
  }

  function renderAccessRequests(sessionId, requests) {
    renderSharingRows(elements.accessRequestsList, requests, "Sin solicitudes pendientes.", (username) => {
      const path = `access-requests/${encode(username)}`;
      return [
        actionButton("Aprobar", (button) => shareAction(
          sessionId, `${path}/approve`, "POST", button, `Se aprobó la solicitud de ${username}.`,
        )),
        actionButton("Rechazar", (button) => shareAction(
          sessionId, path, "DELETE", button, `Se rechazó la solicitud de ${username}.`,
        )),
      ];
    });
  }

  function updateInviteButton() {
    elements.inviteUserButton.disabled = state.invitationPending || !elements.inviteUserSelect.value;
  }

  async function loadSharing(sessionId) {
    const version = ++state.sharingVersion;
    elements.sharingMessage.textContent = "Cargando permisos…";
    const base = `/simulations/${encode(sessionId)}`;
    const [users, participants, requests] = await Promise.allSettled([
      api("/auth/users"),
      api(`${base}/participants`),
      api(`${base}/access-requests`),
    ]);
    if (version !== state.sharingVersion || state.sessionId !== sessionId) return;
    if (participants.status === "fulfilled") renderParticipants(sessionId, participants.value);
    if (requests.status === "fulfilled") renderAccessRequests(sessionId, requests.value);
    if (users.status === "fulfilled" && participants.status === "fulfilled") {
      const previous = elements.inviteUserSelect.value;
      const choices = users.value.filter((user) =>
        user.username !== state.sessionDetail.owner_id && !participants.value.some((item) => item.username === user.username));
      elements.inviteUserSelect.replaceChildren(
        new Option(choices.length ? "Seleccione un usuario" : "No hay usuarios para invitar", ""),
        ...choices.map((user) => new Option(user.username, user.username)),
      );
      elements.inviteUserSelect.value = choices.some((user) => user.username === previous) ? previous : "";
    }
    updateInviteButton();
    const failure = [users, participants, requests].find((response) => response.status === "rejected");
    elements.sharingMessage.textContent = failure ? `No se pudieron actualizar todos los permisos: ${failure.reason.message}` : "";
  }

  async function shareAction(sessionId, path, method, button, message, body) {
    const session = state.sessionDetail;
    button.disabled = true;
    try {
      const options = { method };
      if (body) options.body = JSON.stringify(body);
      await api(`/simulations/${encode(sessionId)}/${path}`, options);
      if (session !== state.sessionDetail) return;
      toast(message);
      await loadSharing(sessionId);
    } catch (error) {
      if (session === state.sessionDetail) toast(`No se pudo actualizar el acceso: ${error.message}`);
    } finally {
      if (button === elements.inviteUserButton) updateInviteButton();
      else button.disabled = false;
    }
  }

  function connectWebSocket(sessionId) {
    let socket;
    try {
      socket = new WebSocket(`${WS_BASE}/ws/simulations/${encode(sessionId)}`);
    } catch (error) {
      setDot(elements.wsDot, "offline", "Error WebSocket");
      toast("No se pudo abrir el WebSocket de la simulación.");
      logEvent("WebSocket", error.message);
      return;
    }
    state.socket = socket;
    setDot(elements.wsDot, "waiting", "Conectando WebSocket");
    socket.onopen = () => {
      if (state.socket !== socket) return;
      setDot(elements.wsDot, "online", "WebSocket conectado");
      setLine("ws", "done");
      logEvent("WebSocket", "conectado");
    };
    socket.onclose = (event) => {
      if (state.socket !== socket) return;
      state.socket = null;
      setDot(elements.wsDot, "offline", "WebSocket desconectado");
      setLine("ws", null);
      if (event.code === 1008) {
        clearSession();
        toast("Tu acceso a la simulación fue revocado.");
        void loadSessions();
      } else {
        logEvent("WebSocket", "conexión cerrada");
        if (event.code !== 1000) state.reconnectTimer = setTimeout(() => reconnect(sessionId), 1500);
      }
    };
    socket.onerror = () => {
      if (state.socket !== socket) return;
      setDot(elements.wsDot, "offline", "Error WebSocket");
      toast("El WebSocket perdió la conexión.");
    };
    socket.onmessage = (event) => {
      if (state.socket !== socket) return;
      try {
        const message = JSON.parse(event.data);
        if (message.session_id === sessionId) handleEvent(message);
      } catch {
        logEvent("WebSocket", "evento inválido");
      }
    };
  }
  async function reconnect(sessionId) {
    const session = state.sessionDetail;
    if (state.socket || session?.session_id !== sessionId) return;
    try {
      const latest = await api(`/simulations/${encode(sessionId)}`);
      if (state.sessionDetail !== session) return;
      session.access_mode = latest.access_mode;
      connectWebSocket(sessionId);
    } catch (error) {
      if (state.sessionDetail !== session) return;
      if ([403, 404].includes(error.status)) { clearSession(); void loadSessions(); }
      else state.reconnectTimer = setTimeout(() => reconnect(sessionId), 3000);
    }
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
    if (message.status === "CLOSED") {
      clearSession();
      toast("La simulación se cerró.");
      void loadSessions();
      return;
    }
    if (message.type === "participant_role") {
      state.sessionDetail.access_mode = message.access_mode;
      interactive.renderControls();
      updateSolveControl();
      void loadSessions();
      return;
    }
    if (message.type === "participants_changed") {
      if (canControlSession(state.sessionDetail) && !state.invitationPending) void loadSharing(state.sessionId);
      return;
    }
    if (["interactive_state", "interactive_step", "switch_operation"].includes(message.type)) {
      interactive.adopt(message.state, message.switches, message.operation);
      return;
    }
    logEvent(message.type || "evento", message.type === "error" ? (message.error || "Error de simulación") : "");
    if (message.simulation) elements.sessionState.textContent = `Sesión ${statusText(message.simulation.status)}`;
    if (message.type === "snapshot") {
      state.sessionDetail.access_mode = message.simulation.access_mode;
      if (message.interactive) {
        interactive.adopt(message.interactive, message.switches, undefined, {reload: true});
        return;
      }
      if (message.last_result) renderResult(message.last_result);
      if (message.current_step != null || message.simulation?.status === "RUNNING") updateProgress(message);
    }
    if (message.type === "simulation_started") {
      if (interactive.state()) { interactive.reset(); state.interactiveRunId = null; updateSolveControl(); }
      setLine("solve", "running");
      setProgress(message.progress_pct || 0, "Iniciando simulación");
    }
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
    if (state.creatingSimulation) return;
    const user = state.currentUser;
    const loadMultiplier = Number(elements.loadMultiplier.value || 1);
    state.creatingSimulation = true;
    updateModelButtons();
    try {
      const topology = await validateModel();
      if (!topology || user !== state.currentUser) return;
      const session = await api("/simulations", {
        method: "POST", body: JSON.stringify({ topology, load_multiplier: loadMultiplier }),
      });
      if (user !== state.currentUser) return;
      await joinSession(session.session_id);
      await loadSessions();
    } catch (error) {
      if (user === state.currentUser) {
        toast(`No fue posible crear la sesión: ${error.message}`);
        logEvent("Creación fallida", error.message);
      }
    } finally {
      state.creatingSimulation = false;
      updateModelButtons();
    }
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
    const session = state.sessionDetail;
    if (!canControlSession(session)) return;
    if (!validateConfiguration()) return;
    if (elements.simulationType.value === "qsts_interactive") {
      const interval = $("#initialQstsInterval");
      if (!interval.reportValidity()) return;
      await interactive.start({
        ...solvePayload().qsts, execution_mode: $("#initialQstsMode").value,
        interval_seconds: Number(interval.value),
      });
      return;
    }
    if (interactive.blocksLegacy() || state.batchSolving === session) return;
    state.batchSolving = session;
    elements.solveButton.disabled = true; setDot(elements.wsDot, "running", "Simulación ejecutándose"); setLine("solve", "running");
    try {
      await api(`/simulations/${encode(session.session_id)}/solve`, {
        method: "POST", body: JSON.stringify(solvePayload()),
      });
      if (session === state.sessionDetail) await loadResults();
      await loadSessions();
    } catch (error) {
      if (session === state.sessionDetail) {
        toast("La simulación no pudo completarse.");
        logEvent("Resolución fallida", error.message);
        setLine("solve", "error");
      }
    } finally {
      if (state.batchSolving === session) state.batchSolving = null;
      if (session === state.sessionDetail) updateSolveControl();
    }
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
      || (payload?.config || payload?.result?.config ? "qsts" : "snapshot");
    return simulationType === "qsts"
      ? normalizeQSTSResult(payload)
      : normalizeSnapshotResult(payload);
  }
  async function loadResults() {
    const session = state.sessionDetail;
    if (!session) return;
    try {
      const result = await api(`/simulations/${encode(session.session_id)}/results`);
      if (session === state.sessionDetail) renderResult(result);
    } catch (error) {
      if (session === state.sessionDetail) logEvent("Resultados", error.message);
    }
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
    elements.restoreButton.onclick = () => { elements.editor.value = state.originalDss; 
      updateLineNumbers(); 
    };
    
    elements.simulationType.onchange = updateProfileControls; 
    elements.profileSource.onchange = updateProfileControls;
    elements.durationHours.oninput = updateProfileControls; 
    elements.stepMinutes.oninput = updateProfileControls; 
    elements.valuesInput.oninput = updateProfileControls;
    elements.createButton.onclick = createSimulation; 
    elements.solveButton.onclick = solveSimulation; 
    
    elements.copySession.onclick = () => navigator.clipboard.writeText(state.sessionId).then(() => toast("session_id copiado."));
    elements.joinButton.onclick = () => joinSession(elements.sessionInput.value); elements.sessionInput.onkeydown = (event) => { if (event.key === "Enter") joinSession(elements.sessionInput.value); };
    elements.refreshSessions.onclick = loadSessions; elements.voltageSearch.oninput = renderVoltageRows; elements.qstsSearch.oninput = renderQstsRows; elements.refreshMetrics.onclick = loadMetrics;
    document.querySelectorAll("[data-qsts-sort]").forEach((header) => header.onclick = () => { const key = header.dataset.qstsSort; state.qstsSort = { key, direction: state.qstsSort.key === key ? -state.qstsSort.direction : 1 }; renderQstsRows(); });
    document.querySelectorAll(".tab").forEach((tab) => tab.onclick = () => showTab(tab.dataset.tab));
    elements.uploadButton.onclick = () => elements.fileInput.click();
    elements.fileInput.onchange = async (event) => {
      const file = event.target.files[0];
      if (!file) return;
      const user = state.currentUser;
      try {
        await uploadCustomModel(file);
        if (user === state.currentUser) logEvent("Modelo personalizado", "cargado en la API");
      } catch (error) {
        if (user === state.currentUser) {
          toast(`No fue posible cargar el modelo: ${error.message}`);
          logEvent("Modelo personalizado", error.message);
        }
      } finally {
        event.target.value = "";
      }
    };
    elements.inviteUserSelect.onchange = updateInviteButton;
    elements.inviteUserButton.onclick = async () => {
      const username = elements.inviteUserSelect.value;
      const sessionId = state.sessionId;
      if (!sessionId || !username || state.invitationPending) return;
      state.invitationPending = true;
      try {
        await shareAction(
          sessionId, `participants/${encode(username)}`, "PUT", elements.inviteUserButton,
          `Invitación enviada a ${username}.`, {role: elements.inviteRoleSelect.value},
        );
      } finally {
        state.invitationPending = false;
        updateInviteButton();
      }
    };
    elements.refreshSharing.onclick = () => {
      if (state.sessionId && canControlSession(state.sessionDetail)) void loadSharing(state.sessionId);
    };
    elements.requestAccessButton.onclick = () => {
      if (state.requestSessionId) void requestAccess(state.requestSessionId, elements.requestAccessButton);
    };
    elements.sessionInput.oninput = () => showAccessRequest(null);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) void loadSessions();
    });

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

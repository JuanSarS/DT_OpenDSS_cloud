(() => {
  "use strict";

  const activePhases = new Set(["ready", "running", "paused"]);
  const phaseLabels = {
    initializing: "Preparando contexto",
    ready: "Listo", running: "En automático", paused: "En pausa", stopped: "Detenido",
    completed: "Completado", interrupted: "Interrumpido", failed: "Error",
  };
  const switchLabels = { open: "Abierto", closed: "Cerrado", partial: "Parcial" };
  const switchColors = { open: "#a62c37", closed: "#14704d", partial: "#93640c" };
  const $ = (id) => document.getElementById(id);
  const fmt = (value, digits = 2) => value == null ? "—" : Number(value).toFixed(digits);
  const commandId = () => {
    if (crypto.randomUUID) return crypto.randomUUID();
    const values = crypto.getRandomValues(new Uint8Array(16));
    values[6] = (values[6] & 15) | 64;
    values[8] = (values[8] & 63) | 128;
    const hex = Array.from(values, (value) => value.toString(16).padStart(2, "0")).join("");
    return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join("-");
  };

  function button(label, onClick, disabled = false) {
    const control = document.createElement("button");
    control.type = "button";
    control.className = "button button-secondary";
    control.textContent = label;
    control.disabled = disabled;
    control.onclick = onClick;
    return control;
  }

  function diagramPositions(branches) {
    const adjacency = new Map();
    for (const {bus_from: from, bus_to: to} of branches) {
      if (!adjacency.has(from)) adjacency.set(from, new Set());
      if (!adjacency.has(to)) adjacency.set(to, new Set());
      adjacency.get(from).add(to);
      adjacency.get(to).add(from);
    }
    const visited = new Set();
    const levels = [];
    for (const root of adjacency.keys()) {
      if (visited.has(root)) continue;
      const queue = [[root, 0]];
      visited.add(root);
      for (let index = 0; index < queue.length; index += 1) {
        const [node, level] = queue[index];
        (levels[level] ??= []).push(node);
        for (const next of adjacency.get(node)) {
          if (!visited.has(next)) {
            visited.add(next);
            queue.push([next, level + 1]);
          }
        }
      }
    }
    const positions = new Map();
    levels.forEach((group, level) => group.forEach((name, index) => {
      positions.set(name, [(level + 0.5) / levels.length, (index + 1) / (group.length + 1)]);
    }));
    return positions;
  }

  function drawTrends(canvas, steps) {
    const ctx = canvas.getContext("2d");
    const {width, height} = canvas;
    ctx.clearRect(0, 0, width, height);
    if (!steps.length) return;
    ctx.font = "14px sans-serif";
    const plots = [
      {title: "Potencia activa (kW)", left: 70, series: [["total_kw", "#2563a3"]]},
      {title: "Tensión (p.u.) · mín. / máx.", left: width / 2 + 70,
        series: [["min_voltage_pu", "#a62c37"], ["max_voltage_pu", "#14704d"]]},
    ];
    for (const {title, left, series} of plots) {
      const minStep = steps[0].step;
      const maxStep = steps[steps.length - 1].step;
      const measured = steps.flatMap((step) => series.map(([key]) => step[key])).filter(Number.isFinite);
      if (!measured.length) continue;
      const minimum = Math.min(...measured);
      const maximum = Math.max(...measured);
      const span = maximum - minimum || 1;
      const right = left + width / 2 - 95;
      const top = 42;
      const bottom = height - 40;
      const x = (step) => left + ((step - minStep) / (maxStep - minStep || 1)) * (right - left);
      const y = (value) => bottom - (value - minimum) / span * (bottom - top);
      ctx.fillStyle = "#17324d";
      ctx.fillText(title, left, 22);
      ctx.fillText(fmt(maximum), left - 65, top + 4);
      ctx.fillText(fmt(minimum), left - 65, bottom + 4);
      ctx.fillText("Paso " + minStep, left, height - 12);
      ctx.fillText(String(maxStep), right - 16, height - 12);
      ctx.strokeStyle = "#c5d3df";
      ctx.beginPath();
      ctx.moveTo(left, top); ctx.lineTo(left, bottom); ctx.lineTo(right, bottom); ctx.stroke();
      for (const [key, color] of series) {
        let previous = false;
        ctx.strokeStyle = color;
        ctx.fillStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (const step of steps) {
          if (!Number.isFinite(step[key])) { previous = false; continue; }
          const px = x(step.step), py = y(step[key]);
          if (previous) ctx.lineTo(px, py); else ctx.moveTo(px, py);
          previous = true;
        }
        ctx.stroke();
        const last = steps[steps.length - 1];
        if (Number.isFinite(last[key])) {
          ctx.beginPath();
          ctx.arc(x(last.step), y(last[key]), 3, 0, 2 * Math.PI);
          ctx.fill();
        }
      }
      ctx.lineWidth = 1;
    }
  }

  window.createInteractiveControls = ({api, getSession, toast, onUpdate, showTab}) => {
    let current = null;
    let switches = [];
    let branches = [];
    let positions = new Map();
    let selected = null;
    let pending = null;
    let intervalDraft = null;
    const steps = new Map();
    const operations = new Map();
    const controls = Object.fromEntries(
      ["Run", "Pause", "Resume", "Step", "Stop", "Restart", "Mode", "Interval", "ApplyInterval"]
        .map((name) => [name.toLowerCase(), $("interactive" + name)]),
    );
    const phaseActive = () => Boolean(current && activePhases.has(current.phase));
    const canOwn = () => ["owner", "admin"].includes(getSession()?.access_mode);
    const canOperate = () => canOwn() || getSession()?.access_mode === "operator";
    const basePath = (session) => "/simulations/" + encodeURIComponent(session.session_id);

    function drawNetwork() {
      const canvas = $("networkCanvas");
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const visible = branches.length > 0;
      $("networkFigure").hidden = !visible;
      $("networkEmpty").hidden = visible;
      $("networkResetZoom").hidden = !selected;
      if (!visible) return;
      const status = new Map(switches.map((item) => [item.element, item.status]));
      const inspected = branches.find((branch) => branch.element === selected);
      const endpoints = inspected && [positions.get(inspected.bus_from), positions.get(inspected.bus_to)];
      const focus = endpoints && endpoints.every(Boolean)
        ? endpoints[0].map((value, index) => (value + endpoints[1][index]) / 2)
        : [0.5, 0.5];
      const zoom = endpoints ? Math.min(6, 0.7 / Math.max(
        0.05, Math.abs(endpoints[0][0] - endpoints[1][0]), Math.abs(endpoints[0][1] - endpoints[1][1]),
      )) : 1;
      const point = ([x, y]) => [
        canvas.width * (0.5 + 0.87 * zoom * (x - focus[0])),
        canvas.height * (0.5 + 0.9 * zoom * (y - focus[1])),
      ];
      $("networkLegend").textContent = inspected
        ? inspected.element + " · " + inspected.bus_from + " ↔ " + inspected.bus_to + " · " + switchLabels[status.get(selected)]
        : "Líneas y transformadores · Verde cerrado · Rojo abierto · Ámbar parcial";
      for (const branch of branches) {
        const start = point(positions.get(branch.bus_from));
        const end = point(positions.get(branch.bus_to));
        const state = status.get(branch.element);
        ctx.strokeStyle = switchColors[state] || "#90a7b9";
        ctx.lineWidth = branch.element === selected ? 5 : state ? 2.8 : 1;
        ctx.setLineDash(state === "open" ? [7, 5] : []);
        ctx.beginPath();
        ctx.moveTo(...start);
        ctx.lineTo(...end);
        ctx.stroke();
      }
      ctx.setLineDash([]);
      ctx.fillStyle = "#17324d";
      ctx.font = "13px sans-serif";
      for (const [bus, position] of positions) {
        const [x, y] = point(position);
        ctx.beginPath();
        ctx.arc(x, y, positions.size < 60 ? 3 : 1.5, 0, Math.PI * 2);
        ctx.fill();
        if (positions.size < 60 || (inspected && [inspected.bus_from, inspected.bus_to].includes(bus))) {
          ctx.fillText(bus, x + 4, y - 5);
        }
      }
    }

    function renderOperations() {
      const container = $("switchHistory");
      const entries = [...operations.values()].sort((a, b) => b.timestamp.localeCompare(a.timestamp)).slice(0, 200);
      if (!entries.length) {
        const row = document.createElement("tr");
        const cell = row.insertCell();
        cell.colSpan = 6;
        cell.textContent = "Sin operaciones.";
        container.replaceChildren(row);
        return;
      }
      container.replaceChildren(...entries.map((entry) => {
        const row = document.createElement("tr");
        const fields = [
          new Date(entry.timestamp).toLocaleString(), entry.actor, entry.element,
          entry.action === "open" ? "Abrir" : "Cerrar",
          entry.step + " · " + fmt(entry.simulated_minutes) + " min",
          switchLabels[entry.effective_state.status],
        ];
        for (const value of fields) row.insertCell().textContent = value;
        return row;
      }));
    }

    function renderControls() {
      $("interactivePanel").hidden = !current;
      $("interactiveChart").hidden = !current;
      if (!current) return;
      const owner = canOwn(), operate = canOperate(), active = phaseActive(), busy = Boolean(pending);
      $("interactivePhase").textContent = phaseLabels[current.phase];
      $("interactiveClock").textContent = "Paso " + current.completed_steps + " / " + current.total_steps
        + " · " + fmt(current.simulated_minutes) + " min simulados · " + current.interval_seconds + " s reales entre pasos";
      const note = current.message || (current.results_stale ? "La red cambió. Los resultados se actualizarán en el siguiente paso." : "");
      $("interactiveNotice").hidden = !note;
      $("interactiveNotice").textContent = note;
      controls.run.disabled = busy || !operate || !active || current.phase === "running"
        || (!owner && current.execution_mode !== "automatic");
      controls.pause.disabled = busy || !operate || !active || current.phase === "paused";
      controls.resume.disabled = busy || !operate || current.phase !== "paused";
      controls.step.disabled = busy || !operate || !active;
      controls.stop.disabled = busy || !owner || !active;
      controls.restart.disabled = busy || !owner || current.phase === "initializing";
      controls.mode.disabled = busy || !owner || !active;
      controls.mode.value = current.execution_mode;
      controls.interval.disabled = busy || !owner || !active;
      controls.applyinterval.disabled = controls.interval.disabled;
      if (intervalDraft === null) controls.interval.value = current.interval_seconds;
      const list = $("switchList");
      if (!switches.length) list.textContent = "El circuito no tiene interruptores controlables.";
      else list.replaceChildren(...switches.map((item) => {
        const row = document.createElement("div");
        row.className = "switch-row";
        const name = document.createElement("strong");
        name.textContent = item.element;
        const status = document.createElement("span");
        status.className = "switch-status " + item.status;
        status.textContent = switchLabels[item.status];
        const restricted = busy || !active || !operate;
        const open = button("Abrir", () => operateSwitch(item, "open"), restricted || item.status === "open");
        const close = button("Cerrar", () => operateSwitch(item, "close"), restricted || item.status === "closed");
        open.setAttribute("aria-label", "Abrir " + item.element);
        close.setAttribute("aria-label", "Cerrar " + item.element);
        const locate = button("Ver", () => { selected = item.element; drawNetwork(); showTab("diagram"); });
        locate.setAttribute("aria-label", "Ver " + item.element + " en el diagrama");
        row.append(name, status, open, close, locate);
        return row;
      }));
    }

    function renderResults() {
      const series = [...steps.values()].sort((a, b) => a.step - b.step);
      drawTrends($("qstsTrend"), series);
      onUpdate(current, series);
    }

    async function loadRunData(session, runId) {
      const base = basePath(session);
      const query = "?run_id=" + encodeURIComponent(runId);
      const [network, results, history] = await Promise.allSettled([
        api(base + "/qsts/interactive/network" + query),
        api(base + "/qsts/interactive/results" + query),
        api(base + "/controls/history"),
      ]);
      if (getSession() !== session || current?.run_id !== runId) return;
      if (network.status === "fulfilled") {
        branches = network.value;
        positions = diagramPositions(branches);
        drawNetwork();
      }
      if (results.status === "fulfilled") {
        for (const step of results.value) steps.set(step.step, step);
        renderResults();
      }
      if (history.status === "fulfilled") {
        for (const entry of history.value) operations.set(entry.command_id, entry);
        renderOperations();
      }
    }

    function adopt(next, newSwitches, operation, {reload = false} = {}) {
      const session = getSession();
      if (!session || !next) return;
      if (current && next.revision < current.revision) return;
      const newRun = current?.run_id !== next.run_id;
      const initialized = current?.phase === "initializing" && next.phase !== "initializing";
      if (newRun) {
        steps.clear();
        switches = [];
        branches = [];
        positions = new Map();
        selected = null;
        intervalDraft = null;
      }
      current = next;
      if (next.latest_result) steps.set(next.latest_result.step, next.latest_result);
      if (Array.isArray(newSwitches)) switches = newSwitches;
      if (operation) operations.set(operation.command_id, operation);
      renderControls();
      renderResults();
      if (newRun || newSwitches) drawNetwork();
      if (operation) renderOperations();
      if (next.phase !== "initializing" && (newRun || initialized || reload)) void loadRunData(session, next.run_id);
    }

    function reset() {
      current = null;
      pending = null;
      switches = [];
      branches = [];
      positions = new Map();
      selected = null;
      intervalDraft = null;
      steps.clear();
      operations.clear();
      renderControls();
      renderOperations();
      drawNetwork();
    }

    async function sync() {
      const session = getSession();
      if (!session) return;
      try {
        const path = basePath(session);
        const next = await api(path + "/qsts/interactive/state");
        if (getSession() !== session || !next) return;
        adopt(next, undefined, undefined, {reload: true});
        if (!["interrupted", "failed"].includes(next.phase)) {
          const observed = await api(path + "/controls/switches");
          if (getSession() === session && current?.revision === next.revision) adopt(next, observed);
        }
      } catch (error) {
        if (getSession() === session && error.status !== 503) toast(error.message);
      }
    }

    async function send(path, method, body) {
      const session = getSession();
      if (pending || !session) return;
      const request = {};
      pending = request;
      renderControls();
      onUpdate(current);
      try {
        const result = await api(basePath(session) + path, {method, body: JSON.stringify(body)});
        if (getSession() !== session) return;
        if (result.effective_state) {
          if (current?.run_id === result.run_id && !operations.has(result.command_id)) {
            operations.set(result.command_id, result);
            renderOperations();
            void sync();
          }
        } else {
          adopt(result.state || result);
          // Step results may be returned by REST before their matching WS event.
          if (path.endsWith("/step") && !$("qstsTrend").closest(".is-visible")) showTab("qsts");
        }
      } catch (error) {
        if (getSession() === session) {
          toast(error.message);
          if (error.status === 409 || error.status === 503) void sync();
        }
      } finally {
        if (pending === request) {
          pending = null;
          renderControls();
          onUpdate(current);
        }
      }
    }

    const qsts = "/qsts/interactive/";
    function transition(action, method = "POST", options = {}) {
      if (current) return send(qsts + action, method, {run_id: current.run_id, ...options});
    }
    function operateSwitch(item, action) {
      return send("/controls/switches/" + encodeURIComponent(item.element), "POST", {
        run_id: current.run_id, expected_step: current.completed_steps, command_id: commandId(), action,
      });
    }
    for (const name of ["run", "pause", "resume", "stop", "restart"]) controls[name].onclick = () => transition(name);
    controls.step.onclick = () => transition("step", "POST", {
      expected_step: current.completed_steps, command_id: commandId(),
    });
    controls.mode.onchange = () => transition("mode", "PUT", {execution_mode: controls.mode.value});
    controls.interval.oninput = controls.interval.onchange = () => { intervalDraft = controls.interval.value; };
    controls.applyinterval.onclick = async () => {
      if (controls.interval.reportValidity()) {
        const requested = controls.interval.value;
        await transition("interval", "PUT", {interval_seconds: Number(requested)});
        if (intervalDraft === requested) intervalDraft = null;
        renderControls();
      }
    };
    $("showNetworkBtn").onclick = () => showTab("diagram");
    $("networkResetZoom").onclick = () => { selected = null; drawNetwork(); };
    return {
      adopt, reset, sync, renderControls,
      state: () => current, busy: () => Boolean(pending),
      blocksLegacy: () => Boolean(current && !["stopped", "completed"].includes(current.phase)),
      start: (config) => send(qsts + "start", "POST", config),
    };
  };
})();

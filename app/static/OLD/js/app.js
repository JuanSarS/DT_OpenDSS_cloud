let sessionId = null;
let socket = null;
const $ = (id) => document.getElementById(id);

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
  return data;
}

async function loadModels() {
  const models = await api("/models");
  $("model").replaceChildren(...models.filter((m) => m.available).map((m) => new Option(`${m.name} (${m.id})`, m.id)));
}

async function loadSessions() {
  const sessions = await api("/simulations");
  $("sessions").replaceChildren(...sessions.map((s) => {
    const item = document.createElement("li");
    item.textContent = `${s.session_id} · ${s.topology} · ${s.status}`;
    const button = document.createElement("button");
    button.textContent = "Unirse";
    button.onclick = () => join(s.session_id);
    item.append(button);
    return item;
  }));
}

async function join(id) {
  const detail = await api(`/simulations/${encodeURIComponent(id)}`);
  sessionId = detail.session_id;
  $("current").hidden = false;
  $("session-title").textContent = sessionId;
  $("model-name").textContent = detail.topology;
  $("buses").textContent = detail.model_summary.num_buses;
  $("nodes").textContent = detail.model_summary.num_nodes;
  $("simulation-status").textContent = detail.status;
  if (detail.last_result) $("result").textContent = JSON.stringify(detail.last_result, null, 2);
  connectSocket();
}

function connectSocket() {
  if (socket) socket.close();
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${window.location.host}/ws/simulations/${encodeURIComponent(sessionId)}`);
  socket.onopen = () => $("connection").textContent = "conectado";
  socket.onclose = () => $("connection").textContent = "desconectado";
  socket.onerror = () => $("connection").textContent = "error";
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    $("events").textContent += `${message.type} ${message.timestamp}\n`;
    if (message.simulation) $("simulation-status").textContent = message.simulation.status;
    if (message.result) $("result").textContent = JSON.stringify(message.result, null, 2);
    if (message.last_result) $("result").textContent = JSON.stringify(message.last_result, null, 2);
  };
}

$("create").onclick = async () => { try { const data = await api("/simulations", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({topology: $("model").value}) }); await join(data.session_id); await loadSessions(); } catch (e) { alert(e.message); } };
$("join").onclick = async () => { try { await join($("join-id").value.trim()); } catch (e) { alert(e.message); } };
$("refresh").onclick = () => loadSessions().catch((e) => alert(e.message));
$("solve").onclick = () => api(`/simulations/${sessionId}/solve`, {method: "POST"}).catch((e) => alert(e.message));
$("close").onclick = async () => { try { await api(`/simulations/${sessionId}`, {method: "DELETE"}); if (socket) socket.close(); $("current").hidden = true; await loadSessions(); } catch (e) { alert(e.message); } };
$("upload-btn").onclick = async () => { const file = $("upload").files[0]; if (!file) return; const form = new FormData(); form.append("file", file); try { $("custom-status").textContent = JSON.stringify(await api("/models/upload", {method: "POST", body: form}), null, 2); } catch (e) { $("custom-status").textContent = e.message; } };
loadModels().then(loadSessions).catch((e) => alert(e.message));

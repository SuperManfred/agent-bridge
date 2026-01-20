const roomsEl = document.getElementById("rooms");
const eventsEl = document.getElementById("events");
const roomTitleEl = document.getElementById("room-title");
const roomIdEl = document.getElementById("room-id");
const newRoomInput = document.getElementById("new-room-name");
const createRoomBtn = document.getElementById("create-room");
const toSelect = document.getElementById("to");
const contentInput = document.getElementById("content");
const sendBtn = document.getElementById("send");
const streamStatusEl = document.getElementById("stream-status");
const errorEl = document.getElementById("send-error");
const participantsEl = document.getElementById("participants");
const badgePausedEl = document.getElementById("badge-paused");
const badgeDiscussionEl = document.getElementById("badge-discussion");
const togglePauseBtn = document.getElementById("toggle-pause");
const toggleDiscussionBtn = document.getElementById("toggle-discussion");

let currentRoomId = null;
let lastEventTs = null;
let minEventId = null;
let sse = null;
let eventsCache = [];
let fallbackTimer = null;
let presenceTimer = null;
let stateTimer = null;
let latestPresence = null;
let latestState = null;

const STATUS_LABELS = {
  idle: "Idle",
  connecting: "Connecting",
  streaming: "Streaming",
  polling: "Polling"
};

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function setStreamStatus(mode) {
  if (!streamStatusEl) return;
  const label = STATUS_LABELS[mode] || STATUS_LABELS.idle;
  streamStatusEl.textContent = label;
  streamStatusEl.className = `pill ${mode || "idle"}`;
}

async function fetchJson(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let payload = null;
    try {
      payload = await res.json();
    } catch {
      payload = null;
    }
    const error = new Error(`HTTP ${res.status}`);
    error.status = res.status;
    error.payload = payload;
    throw error;
  }
  return res.json();
}

function renderRooms(rooms) {
  roomsEl.innerHTML = "";
  rooms.forEach((room) => {
    const el = document.createElement("div");
    el.className = "room" + (room.id === currentRoomId ? " active" : "");
    el.innerHTML = `<strong>${escapeHtml(room.name || "Untitled")}</strong>
      <small>${escapeHtml(room.id)}</small>`;
    el.addEventListener("click", () => selectRoom(room));
    roomsEl.appendChild(el);
  });
}

function renderEvents(events) {
  let visibleEvents = events;
  if (minEventId) {
    const idx = visibleEvents.findIndex((evt) => evt.id === minEventId);
    if (idx >= 0) {
      visibleEvents = visibleEvents.slice(idx);
    }
  }
  eventsEl.innerHTML = "";
  visibleEvents.forEach((evt) => {
    const el = document.createElement("div");
    el.className = "event";
    const meta = `[${evt.ts}] ${evt.from || "unknown"} → ${evt.to || "all"} • ${evt.type}`;
    const content = typeof evt.content === "string" ? evt.content : JSON.stringify(evt.content);
    el.innerHTML = `<div class="meta">${escapeHtml(meta)}</div>
      <div>${escapeHtml(content || "")}</div>`;
    el.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      if (!currentRoomId || !evt.id) return;
      const url = `${window.location.origin}/ui/rooms/${currentRoomId}/messages/${evt.id}`;
      navigator.clipboard.writeText(url).catch(() => {});
    });
    eventsEl.appendChild(el);
  });
  eventsEl.scrollTop = eventsEl.scrollHeight;
}

async function loadRooms() {
  const data = await fetchJson("/threads");
  renderRooms(data.threads || []);
}

async function selectRoom(room) {
  currentRoomId = room.id;
  roomTitleEl.textContent = room.name || "Untitled";
  if (roomIdEl) roomIdEl.textContent = room.id || "";
  lastEventTs = null;
  minEventId = null;
  eventsCache = [];
  setStreamStatus("connecting");
  await loadEvents(true);
  await ensureUserPresence();
  startRoomPolling();
  renderRooms((await fetchJson("/threads")).threads || []);
  const url = `${window.location.origin}/ui/rooms/${currentRoomId}`;
  window.history.replaceState({}, "", url);
  startStream();
}

async function loadEvents(reset = false) {
  if (!currentRoomId) return;
  const sinceParam = reset || !lastEventTs ? "" : `?since=${encodeURIComponent(lastEventTs)}`;
  const data = await fetchJson(`/threads/${currentRoomId}/events${sinceParam}`);
  const events = data.events || [];
  if (events.length > 0) {
    lastEventTs = events[events.length - 1].ts;
  }
  if (reset) {
    eventsCache = events.slice();
  } else {
    eventsCache = eventsCache.concat(events);
  }
  renderEvents(eventsCache);
}

function currentEventsFromDom() {
  // Minimal: rebuild from DOM text. For Phase 0, just reset on poll.
  return [];
}

function getProfileFromPresence(p) {
  const details = (p && p.details && typeof p.details === "object") ? p.details : {};
  const profile = (details && typeof details.profile === "object" && details.profile) ? details.profile : details;
  const out = {...profile};
  if (p && p.id === "user") {
    out.client = out.client || "user";
    out.model = out.model || "human";
  }
  return out;
}

function clientModelLabel(profile) {
  const client = profile.client;
  const model = profile.model;
  if (client && model) return `${client}/${model}`;
  return client || model || "";
}

function displayTitle(profile, participantId) {
  const nickname = profile.nickname;
  if (nickname) return nickname;
  const cm = clientModelLabel(profile);
  return cm || participantId || "?";
}

function renderThreadState() {
  const state = (latestState && latestState.state) || null;
  const paused = !!(state && state.paused);
  const discussion = (state && state.discussion) || {};
  const discussionEnabled = !!(discussion.on && discussion.allow_agent_mentions);

  if (badgePausedEl) badgePausedEl.classList.toggle("hidden", !paused);
  if (badgeDiscussionEl) badgeDiscussionEl.classList.toggle("hidden", !discussionEnabled);

  if (togglePauseBtn) {
    togglePauseBtn.textContent = paused ? "Resume" : "Pause";
    togglePauseBtn.disabled = !currentRoomId;
  }
  if (toggleDiscussionBtn) {
    toggleDiscussionBtn.textContent = discussionEnabled ? "Discussion Off" : "Discussion On";
    toggleDiscussionBtn.disabled = !currentRoomId;
  }
}

function renderParticipants() {
  if (!participantsEl) return;
  const participants = (latestPresence && latestPresence.participants) || [];
  const mutedList = (latestState && latestState.state && Array.isArray(latestState.state.muted)) ? latestState.state.muted : [];
  const muted = new Set(mutedList);

  participantsEl.innerHTML = "";
  if (!participants.length) {
    const empty = document.createElement("div");
    empty.className = "p-meta";
    empty.textContent = "No participants yet.";
    participantsEl.appendChild(empty);
    updateToOptions([]);
    return;
  }

  participants.forEach((p) => {
    const profile = getProfileFromPresence(p);
    const participantId = p.id || "?";
    const state = p.stale ? "offline" : (p.state || "unknown");
    const isMuted = muted.has(participantId);

    const row = document.createElement("div");
    row.className = "participant";

    const left = document.createElement("div");

    const nameLine = document.createElement("div");
    nameLine.className = "p-name";

    const title = document.createElement("div");
    title.className = "p-title";
    title.textContent = displayTitle(profile, participantId);
    nameLine.appendChild(title);

    const idEl = document.createElement("div");
    idEl.className = "p-id";
    idEl.textContent = `@${participantId}`;
    nameLine.appendChild(idEl);

    left.appendChild(nameLine);

    const meta = document.createElement("div");
    meta.className = "p-meta";
    const cm = clientModelLabel(profile);
    if (cm) {
      const cmChip = document.createElement("span");
      cmChip.className = "chip";
      cmChip.textContent = cm;
      meta.appendChild(cmChip);
    }
    const roles = Array.isArray(profile.roles) ? profile.roles : [];
    roles.forEach((role) => {
      const r = String(role || "").trim();
      if (!r) return;
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = r;
      meta.appendChild(chip);
    });
    if (isMuted) {
      const mutedChip = document.createElement("span");
      mutedChip.className = "chip muted-tag";
      mutedChip.textContent = "muted";
      meta.appendChild(mutedChip);
    }
    left.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "p-actions";

    const stateBadge = document.createElement("span");
    stateBadge.className = `state ${state}`;
    stateBadge.textContent = state;
    actions.appendChild(stateBadge);

    const muteBtn = document.createElement("button");
    muteBtn.type = "button";
    muteBtn.dataset.participant = participantId;
    muteBtn.dataset.action = isMuted ? "unmute" : "mute";
    muteBtn.textContent = isMuted ? "Unmute" : "Mute";
    muteBtn.className = isMuted ? "" : "danger";
    muteBtn.disabled = !currentRoomId || participantId === "user";
    actions.appendChild(muteBtn);

    row.appendChild(left);
    row.appendChild(actions);

    participantsEl.appendChild(row);
  });

  updateToOptions(participants);
}

function updateToOptions(participants) {
  if (!toSelect) return;
  const previous = toSelect.value || "all";
  toSelect.innerHTML = "";

  const optAll = document.createElement("option");
  optAll.value = "all";
  optAll.textContent = "all (room)";
  toSelect.appendChild(optAll);

  participants.forEach((p) => {
    const participantId = p.id;
    if (!participantId) return;
    const profile = getProfileFromPresence(p);
    const label = displayTitle(profile, participantId);
    const opt = document.createElement("option");
    opt.value = participantId;
    opt.textContent = `direct: ${label} (@${participantId})`;
    toSelect.appendChild(opt);
  });

  // Restore selection if possible; otherwise default to all.
  const hasPrev = Array.from(toSelect.options).some((o) => o.value === previous);
  toSelect.value = hasPrev ? previous : "all";
}

async function loadPresence() {
  if (!currentRoomId) return;
  try {
    latestPresence = await fetchJson(`/threads/${currentRoomId}/presence`);
    renderParticipants();
  } catch {
    // Presence is best-effort.
  }
}

async function loadThreadState() {
  if (!currentRoomId) return;
  try {
    latestState = await fetchJson(`/threads/${currentRoomId}/state`);
    renderThreadState();
    renderParticipants();
  } catch {
    // State is best-effort.
  }
}

function startRoomPolling() {
  if (presenceTimer) clearInterval(presenceTimer);
  if (stateTimer) clearInterval(stateTimer);
  presenceTimer = null;
  stateTimer = null;
  latestPresence = null;
  latestState = null;
  renderThreadState();
  renderParticipants();
  if (!currentRoomId) return;
  loadThreadState();
  loadPresence();
  stateTimer = setInterval(loadThreadState, 2000);
  presenceTimer = setInterval(loadPresence, 2000);
}

function stopStream() {
  if (sse) {
    sse.close();
    sse = null;
  }
  if (fallbackTimer) {
    clearInterval(fallbackTimer);
    fallbackTimer = null;
  }
  if (!currentRoomId) {
    setStreamStatus("idle");
  }
}

function startFallbackPolling() {
  if (fallbackTimer) return;
  setStreamStatus("polling");
  fallbackTimer = setInterval(() => loadEvents(false), 3000);
}

function startStream() {
  stopStream();
  if (!currentRoomId) return;
  setStreamStatus("connecting");
  const since = lastEventTs ? `?since=${encodeURIComponent(lastEventTs)}` : "";
  const url = `/threads/${currentRoomId}/events/stream${since}`;
  sse = new EventSource(url);
  sse.onopen = () => {
    setStreamStatus("streaming");
    if (fallbackTimer) {
      clearInterval(fallbackTimer);
      fallbackTimer = null;
    }
  };
  sse.onmessage = (event) => {
    if (!event.data) return;
    try {
      const evt = JSON.parse(event.data);
      eventsCache.push(evt);
      lastEventTs = evt.ts || lastEventTs;
      renderEvents(eventsCache);
    } catch (err) {
      console.error("SSE parse error", err);
    }
  };
  sse.onerror = () => {
    startFallbackPolling();
  };
}

async function createRoom() {
  const name = newRoomInput.value.trim() || "Untitled";
  const room = await fetchJson("/threads", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name, from: "user"})
  });
  newRoomInput.value = "";
  await loadRooms();
  await selectRoom(room);
}

async function sendMessage() {
  if (!currentRoomId) return;
  const content = contentInput.value.trim();
  if (!content) return;
  const from = "user";
  const to = (toSelect && toSelect.value) || "all";
  try {
    await fetchJson(`/threads/${currentRoomId}/events`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({type: "message", from, to, content})
    });
    showError("");
  } catch (err) {
    if (err && err.status === 409 && err.payload && err.payload.error) {
      const {code, message} = err.payload.error;
      showError(`${code}: ${message}`);
    } else {
      showError("Send failed.");
    }
    return;
  }
  contentInput.value = "";
  if (!sse || fallbackTimer) {
    await loadEvents(false);
  }
}

createRoomBtn.addEventListener("click", createRoom);
sendBtn.addEventListener("click", sendMessage);
contentInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
    sendMessage();
  }
});

function showError(message) {
  if (!errorEl) return;
  if (!message) {
    errorEl.textContent = "";
    errorEl.classList.remove("visible");
    return;
  }
  errorEl.textContent = message;
  errorEl.classList.add("visible");
}

async function sendControlEvent(content) {
  if (!currentRoomId) return;
  const from = "user";
  try {
    await fetchJson(`/threads/${currentRoomId}/events`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({type: "control", from, to: "all", content})
    });
    showError("");
  } catch {
    showError("Control event failed.");
  }
}

togglePauseBtn?.addEventListener("click", () => {
  const paused = !!(latestState && latestState.state && latestState.state.paused);
  sendControlEvent({pause: {on: !paused}}).then(loadThreadState);
});
toggleDiscussionBtn?.addEventListener("click", () => {
  const discussion = (latestState && latestState.state && latestState.state.discussion) || {};
  const enabled = !!(discussion.on && discussion.allow_agent_mentions);
  sendControlEvent({discussion: {on: !enabled, allow_agent_mentions: !enabled}}).then(loadThreadState);
});

participantsEl?.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-participant][data-action]");
  if (!btn) return;
  const participant = btn.dataset.participant;
  const action = btn.dataset.action;
  if (!participant) return;
  if (action === "mute") {
    sendControlEvent({mute: {targets: [participant], mode: "hard"}}).then(loadThreadState);
  } else if (action === "unmute") {
    sendControlEvent({unmute: {targets: [participant]}}).then(loadThreadState);
  }
});

// User typing indicator
let typingTimeout = null;
let isTyping = false;

async function postPresence(state, details = null) {
  if (!currentRoomId) return;
  try {
    const payload = {from: "user", state};
    if (details && typeof details === "object") {
      payload.details = details;
    }
    await fetchJson(`/threads/${currentRoomId}/presence`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
  } catch (e) {
    // Presence is best-effort; ignore failures
  }
}

async function ensureUserPresence() {
  if (!currentRoomId) return;
  await postPresence("listening", {client: "user", model: "human"});
}

function handleTypingStart() {
  if (!isTyping) {
    isTyping = true;
    postPresence("typing", {client: "user", model: "human"});
  }
  // Reset idle timeout
  if (typingTimeout) clearTimeout(typingTimeout);
  typingTimeout = setTimeout(() => {
    isTyping = false;
    postPresence("listening");
  }, 3000); // Mark listening after 3s of no typing
}

function handleTypingStop() {
  if (typingTimeout) clearTimeout(typingTimeout);
  if (isTyping) {
    isTyping = false;
    postPresence("listening");
  }
}

contentInput.addEventListener("input", handleTypingStart);
contentInput.addEventListener("focus", () => {
  if (!isTyping) {
    postPresence("listening");
  }
});
contentInput.addEventListener("blur", handleTypingStop);

// Defaults
updateToOptions([]);
renderThreadState();
renderParticipants();

loadRooms();
const pathMatch = window.location.pathname.match(/\/ui\/rooms\/([^/]+)(?:\/messages\/([^/]+))?/);
if (pathMatch) {
  currentRoomId = pathMatch[1];
  minEventId = pathMatch[2] || null;
  loadRooms().then(() => {
    selectRoom({id: currentRoomId, name: "Room"});
  });
}

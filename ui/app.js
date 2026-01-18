const roomsEl = document.getElementById("rooms");
const eventsEl = document.getElementById("events");
const roomTitleEl = document.getElementById("room-title");
const newRoomInput = document.getElementById("new-room-name");
const createRoomBtn = document.getElementById("create-room");
const fromInput = document.getElementById("from");
const toInput = document.getElementById("to");
const contentInput = document.getElementById("content");
const sendBtn = document.getElementById("send");
const streamStatusEl = document.getElementById("stream-status");
const presenceEl = document.getElementById("presence");

let currentRoomId = null;
let lastEventTs = null;
let minEventId = null;
let sse = null;
let eventsCache = [];
let fallbackTimer = null;
let presenceTimer = null;

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
  streamStatusEl.className = `status ${mode || "idle"}`;
}

async function fetchJson(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
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
  lastEventTs = null;
  minEventId = null;
  eventsCache = [];
  setStreamStatus("connecting");
  await loadEvents(true);
  startPresencePolling();
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

function renderPresence(snapshot) {
  if (!presenceEl) return;
  const participants = (snapshot && snapshot.participants) || [];
  if (!participants.length) {
    presenceEl.innerHTML = "";
    presenceEl.classList.remove("has-thinking");
    return;
  }
  const thinkingAgents = participants.filter(p => !p.stale && p.state === "thinking");
  const hasThinking = thinkingAgents.length > 0;

  const parts = participants.map((p) => {
    const state = p.stale ? "offline" : (p.state || "unknown");
    const isThinking = !p.stale && state === "thinking";
    if (isThinking) {
      return `<strong>${escapeHtml(p.id || "?")}</strong> is thinking<span class="thinking-indicator"><span></span><span></span><span></span></span>`;
    }
    return `${escapeHtml(p.id || "?")}: <code>${escapeHtml(state)}</code>`;
  });

  presenceEl.innerHTML = parts.join(" • ");
  presenceEl.classList.toggle("has-thinking", hasThinking);
}

async function loadPresence() {
  if (!currentRoomId) return;
  try {
    const snapshot = await fetchJson(`/threads/${currentRoomId}/presence`);
    renderPresence(snapshot);
  } catch {
    // Presence is optional; fail silently.
  }
}

function startPresencePolling() {
  if (presenceTimer) {
    clearInterval(presenceTimer);
    presenceTimer = null;
  }
  if (!currentRoomId) return;
  loadPresence();
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
  if (presenceTimer) {
    clearInterval(presenceTimer);
    presenceTimer = null;
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
    body: JSON.stringify({name, from: fromInput.value.trim() || "user"})
  });
  newRoomInput.value = "";
  await loadRooms();
  await selectRoom(room);
}

async function sendMessage() {
  if (!currentRoomId) return;
  const content = contentInput.value.trim();
  if (!content) return;
  const from = fromInput.value.trim() || "user";
  const to = (toInput && toInput.value.trim()) || "all";
  await fetchJson(`/threads/${currentRoomId}/events`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({type: "message", from, to, content})
  });
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

// User typing indicator
let typingTimeout = null;
let isTyping = false;

async function setTypingPresence(state) {
  if (!currentRoomId) return;
  const from = fromInput.value.trim() || "user";
  try {
    await fetchJson(`/threads/${currentRoomId}/presence`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({from, state})
    });
  } catch (e) {
    // Presence is best-effort; ignore failures
  }
}

function handleTypingStart() {
  if (!isTyping) {
    isTyping = true;
    setTypingPresence("typing");
  }
  // Reset idle timeout
  if (typingTimeout) clearTimeout(typingTimeout);
  typingTimeout = setTimeout(() => {
    isTyping = false;
    setTypingPresence("idle");
  }, 3000); // Mark idle after 3s of no typing
}

function handleTypingStop() {
  if (typingTimeout) clearTimeout(typingTimeout);
  if (isTyping) {
    isTyping = false;
    setTypingPresence("idle");
  }
}

contentInput.addEventListener("input", handleTypingStart);
contentInput.addEventListener("focus", handleTypingStart);
contentInput.addEventListener("blur", handleTypingStop);

loadRooms();
const pathMatch = window.location.pathname.match(/\/ui\/rooms\/([^/]+)(?:\/messages\/([^/]+))?/);
if (pathMatch) {
  currentRoomId = pathMatch[1];
  minEventId = pathMatch[2] || null;
  loadRooms().then(() => {
    selectRoom({id: currentRoomId, name: "Room"});
  });
}

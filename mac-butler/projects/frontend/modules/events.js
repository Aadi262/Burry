export function formatClock(value) {
  if (!value) return "now";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function telemetryEntries(data) {
  const entries = [];
  for (const event of Array.isArray(data.events) ? data.events : []) {
    if (event.kind === "heard") {
      entries.push({ role: "user", at: event.at, text: String(event.message || "").replace(/^Heard:\s*/, "") });
    } else if (event.kind === "spoken") {
      entries.push({ role: "burry", at: event.at, text: String(event.message || "").replace(/^Said:\s*/, "") });
    } else {
      entries.push({ role: "system", at: event.at, text: event.message || event.kind || "event" });
    }
  }
  if (data.last_heard_text && !entries.some((entry) => entry.role === "user" && entry.text === data.last_heard_text)) {
    entries.push({ role: "user", at: data.last_heard_at || data.updated_at, text: data.last_heard_text });
  }
  if (data.last_spoken_text && !entries.some((entry) => entry.role === "burry" && entry.text === data.last_spoken_text)) {
    entries.push({ role: "burry", at: data.last_spoken_at || data.updated_at, text: data.last_spoken_text });
  }
  return entries;
}

function eventKindClass(kind) {
  const k = String(kind || "").toLowerCase();
  if (k === "state") return "amber";
  if (k === "intent") return "cobalt";
  if (k === "heard") return "faint";
  if (k === "ambient") return "faint";
  if (k === "tool_start") return "amber";
  if (k === "tool_end") return "success";
  if (k === "tool_call") return "cobalt";
  if (k === "tool_result") return "success";
  if (k === "tool") return "cobalt";
  if (k === "memory") return "violet";
  if (k === "agent") return "success";
  if (k === "plan") return "violet";
  if (k === "error") return "danger";
  return "faint";
}

function eventKey(event) {
  return [event.at || "", event.kind || "", event.message || ""].join("|");
}

function esc(str) {
  return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function metaMarkup(meta) {
  if (!meta || typeof meta !== "object" || !Object.keys(meta).length) return "";
  return `<pre style="max-height:120px;overflow-y:auto;font-size:9px;line-height:1.4;" class="event-meta">${esc(JSON.stringify(meta, null, 2))}</pre>`;
}

function eventMarkup(event, expandedKey) {
  const key = eventKey(event);
  const open = key === expandedKey;
  return `
    <button class="event-row${open ? " is-open" : ""}" type="button" data-event-key="${esc(key)}">
      <span class="event-time">${formatClock(event.at)}</span>
      <span class="event-kind tone-${eventKindClass(event.kind)}">${esc(event.kind) || "event"}</span>
      <span class="event-message">${esc(event.message) || "No details recorded."}</span>
      ${open ? metaMarkup(event.meta) : ""}
    </button>
  `;
}

export function createEventsPanel({ container }) {
  let expandedKey = "";
  let lastSignature = "";
  let latestData = {};

  container.addEventListener("click", (event) => {
    const row = event.target.closest("[data-event-key]");
    if (!row) return;
    const key = row.getAttribute("data-event-key") || "";
    expandedKey = expandedKey === key ? "" : key;
    render(latestData);
  });

  function render(data) {
    latestData = data || {};
    const items = Array.isArray(data.events) ? data.events : [];
    const MAX_EVENTS = 24;
    const displayItems = items.length > MAX_EVENTS ? items.slice(-MAX_EVENTS) : items;
    const truncated = items.length - displayItems.length;
    const signature = items.map(eventKey).join("||");
    const shouldStickBottom =
      !container.childElementCount
      || container.scrollHeight - container.scrollTop - container.clientHeight < 40;

    if (!displayItems.length) {
      container.innerHTML = "<div class=\"events-empty\">Runtime events will appear here as Burry listens, routes, remembers, and executes.</div>";
      lastSignature = "";
      return;
    }

    const truncatedRow = truncated > 0
      ? `<div class="events-truncated">↑ ${truncated} older events not shown</div>`
      : "";

    container.innerHTML = truncatedRow + displayItems.map((event) => eventMarkup(event, expandedKey)).join("");
    if (shouldStickBottom) {
      container.scrollTop = container.scrollHeight;
    }
    lastSignature = signature;
  }

  return {
    render,
  };
}

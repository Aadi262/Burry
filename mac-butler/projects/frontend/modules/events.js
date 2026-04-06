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
  const normalized = String(kind || "event").toLowerCase();
  if (["heard", "ambient"].includes(normalized)) return "faint";
  if (normalized === "intent") return "accent";
  if (normalized === "tool") return "cobalt";
  if (normalized === "state") return "amber";
  if (normalized === "memory") return "violet";
  if (normalized === "agent") return "success";
  return "default";
}

function eventKey(event) {
  return [event.at || "", event.kind || "", event.message || ""].join("|");
}

function metaMarkup(meta) {
  if (!meta || typeof meta !== "object" || !Object.keys(meta).length) return "";
  return `<pre class="event-meta">${JSON.stringify(meta, null, 2)}</pre>`;
}

function eventMarkup(event, expandedKey) {
  const key = eventKey(event);
  const open = key === expandedKey;
  return `
    <button class="event-row${open ? " is-open" : ""}" type="button" data-event-key="${key}">
      <span class="event-time">${formatClock(event.at)}</span>
      <span class="event-kind tone-${eventKindClass(event.kind)}">${event.kind || "event"}</span>
      <span class="event-message">${event.message || "No details recorded."}</span>
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
    const items = (Array.isArray(data.events) ? data.events : []).slice(-18);
    const signature = items.map(eventKey).join("||");
    const shouldStickBottom =
      !container.childElementCount
      || container.scrollHeight - container.scrollTop - container.clientHeight < 40
      || signature !== lastSignature;

    if (!items.length) {
      container.innerHTML = "<div class=\"events-empty\">Runtime events will appear here as Burry listens, routes, remembers, and executes.</div>";
      lastSignature = "";
      return;
    }

    container.innerHTML = items.map((event) => eventMarkup(event, expandedKey)).join("");
    if (shouldStickBottom) {
      container.scrollTop = container.scrollHeight;
    }
    lastSignature = signature;
  }

  return {
    render,
  };
}

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

export function renderTicker(refs, data) {
  const events = Array.isArray(data.events) ? data.events : [];
  if (events.length) {
    refs.eventTrack.textContent = events.map((event) => `${event.kind || "event"} · ${event.message || ""}`).join("   •   ");
    return;
  }
  if (data.last_agent_result && data.last_agent_result.result) {
    refs.eventTrack.textContent = `${formatClock(data.last_agent_result.at || data.updated_at)} · Agent ${data.last_agent_result.agent || "background"} · ${data.last_agent_result.result}`;
    return;
  }
  const brain = (data.systems || []).find((item) => item.name === "Brain");
  const voice = (data.systems || []).find((item) => item.name === "Voice");
  refs.eventTrack.textContent = `${formatClock(new Date().toISOString())} · System nominal · Brain: ${brain?.detail || "localhost:11434"} · Voice: ${(voice?.status || "edge").toUpperCase()}`;
}

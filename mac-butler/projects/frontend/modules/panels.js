import { basenamePath } from "./mac-activity.js";

const FOCUS_STORAGE_KEY = "burry.focusKind";
const VALID_FOCUS_KINDS = new Set(["mood", "session", "state"]);

export const TOOL_MAP = {
  open_app: { label: "Opening App", icon: "🪟" },
  quit_app: { label: "Closing App", icon: "✖️" },
  open_url: { label: "Opening Link", icon: "🔗" },
  open_url_in_browser: { label: "Browser Open", icon: "🌐" },
  open_editor: { label: "Editor", icon: "🧠" },
  open_terminal: { label: "Terminal", icon: "⌘" },
  run_command: { label: "Command", icon: "⌘" },
  create_file_in_editor: { label: "Creating File", icon: "📄" },
  create_folder: { label: "Creating Folder", icon: "📁" },
  browser_new_tab: { label: "New Tab", icon: "🗂" },
  browser_search: { label: "Browser Search", icon: "🔎" },
  browser_close_tab: { label: "Close Tab", icon: "🧷" },
  browser_close_window: { label: "Close Window", icon: "🪟" },
  browse_web: { label: "Browsing Web", icon: "🌐" },
  web_search_summarize: { label: "Searching", icon: "🔍" },
  browse_and_act: { label: "Browser Agent", icon: "🤖" },
  recall_memory: { label: "Memory Read", icon: "💾" },
  deep_research: { label: "Deep Research", icon: "📚" },
  plan_and_execute: { label: "Planning", icon: "📋" },
  open_project: { label: "Opening Project", icon: "📂" },
  run_shell: { label: "Shell", icon: "⚙️" },
  git_commit: { label: "Git Commit", icon: "📌" },
  send_email: { label: "Email", icon: "📧" },
  send_imessage: { label: "iMessage", icon: "💬" },
  take_screenshot_and_describe: { label: "Seeing Screen", icon: "👁" },
  search_knowledge_base: { label: "Knowledge Base", icon: "🗂" },
  spotify_control: { label: "Spotify", icon: "🎵" },
  ssh_vps: { label: "VPS Shell", icon: "🖥" },
  focus_app: { label: "Focus App", icon: "🎯" },
  minimize_app: { label: "Minimize", icon: "➖" },
  volume_up: { label: "Volume Up", icon: "🔊" },
  volume_down: { label: "Volume Down", icon: "🔉" },
  volume_mute: { label: "Mute", icon: "🔇" },
  lock_screen: { label: "Lock Screen", icon: "🔒" },
  clipboard_read: { label: "Clipboard Read", icon: "📋" },
  clipboard_write: { label: "Clipboard Write", icon: "✏️" },
  dark_mode_toggle: { label: "Dark Mode", icon: "🌙" },
  set_reminder: { label: "Reminder", icon: "⏰" },
  index_file: { label: "Indexing File", icon: "📑" },
  obsidian_note: { label: "Obsidian Note", icon: "📝" },
};

function collapseWhitespace(value) {
  return String(value || "").split(/\s+/).filter(Boolean).join(" ").trim();
}

function normalizeFocusKind(value) {
  const candidate = String(value || "").trim().toLowerCase();
  return VALID_FOCUS_KINDS.has(candidate) ? candidate : "state";
}

function toolPresentation(name) {
  const normalized = String(name || "").trim().toLowerCase();
  return TOOL_MAP[normalized] || { label: normalized || "Executing", icon: "⚡" };
}

function healthClass(project) {
  const health = String(project.health_status || project.status || "unknown").toLowerCase();
  if (["healthy", "live", "ready"].includes(health)) return "healthy";
  if (["active", "configured"].includes(health)) return "active";
  if (["paused", "degraded", "unknown"].includes(health)) return health;
  return "offline";
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return "--";
  return `${value}%`;
}

function formatUptime(value) {
  const totalSeconds = Number(value || 0);
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) return "offline";
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function vpsChip(data) {
  if (!data || String(data.status || "").toLowerCase() === "offline") {
    return {
      detail: "CPU -- · Memory -- · Disk -- · Uptime offline",
      name: "VPS",
      status: "offline",
      tone: "offline",
    };
  }
  const metrics = [Number(data.cpu || 0), Number(data.memory || 0), Number(data.disk || 0)];
  let tone = "healthy";
  let status = "healthy";
  if (metrics.some((value) => value > 95)) {
    tone = "danger";
    status = "critical";
  } else if (metrics.some((value) => value > 80)) {
    tone = "warning";
    status = "warning";
  }
  return {
    detail: `CPU ${formatPercent(data.cpu)} · Memory ${formatPercent(data.memory)} · Disk ${formatPercent(data.disk)} · Uptime ${formatUptime(data.uptime)}`,
    name: "VPS",
    status,
    tone,
  };
}

export function normalizeMode(data) {
  if (data && data.telemetry_fresh === false) return "idle";
  if (Array.isArray(data.active_tools) && data.active_tools.length) return "executing";
  const state = String(data.state || "").toLowerCase();
  if (["idle", "listening", "thinking", "executing", "speaking"].includes(state)) return state;
  return data.session_active ? "listening" : "idle";
}

export function pillNote(data, mode) {
  if (data && data.telemetry_fresh === false) {
    return "Waiting for live runtime telemetry from Butler.";
  }
  if (mode === "listening") return "Mic is hot. Burry is listening for the next move.";
  if (mode === "thinking") return "Context, tools, and memory are routing through the operator stack.";
  if (mode === "executing") return "Tool calls are running now. Watch the stream and memory panels for live progress.";
  if (mode === "speaking") return "Burry is replying now. Transcript and task truth stay live.";
  return "Standing by for the next wake-up.";
}

function orbStatusLine(data) {
  const mode = normalizeMode(data).toUpperCase();
  const focus = data.focus_project || "waiting";
  const frontmost = data.frontmost_app || "Unknown";
  return `BURRY ● ${mode} · Focus: ${focus} · ${frontmost}`;
}

export function createPanels({ refs, state, orb, events, openProject }) {
  function persistFocus(nextFocus) {
    const resolved = normalizeFocusKind(nextFocus);
    try {
      window.localStorage.setItem(FOCUS_STORAGE_KEY, resolved);
    } catch (_error) {}
    return resolved;
  }

  function restoreFocus() {
    let stored = "";
    try {
      stored = window.localStorage.getItem(FOCUS_STORAGE_KEY) || "";
    } catch (_error) {}
    const restored = normalizeFocusKind(stored || state.focusKind);
    state.focusKind = persistFocus(restored);
    return state.focusKind;
  }

  function setButlerState(mode, note) {
    const cleanedMode = ["idle", "listening", "thinking", "speaking", "executing"].includes(mode) ? mode : "idle";
    refs.body.dataset.state = cleanedMode;
    refs.statePillLabel.textContent = cleanedMode.toUpperCase();
    refs.statePillNote.textContent = note || pillNote(state.operator, cleanedMode);
    orb.setState(cleanedMode);
  }

  function setFocus(nextFocus) {
    state.focusKind = persistFocus(nextFocus);
    refs.body.dataset.focus = state.focusKind;
    [refs.modeMood, refs.modeSession, refs.modeState].forEach((button) => {
      button.classList.toggle("is-active", button.dataset.focus === state.focusKind);
    });
    refs.orbSummary.textContent = orbStatusLine(state.operator);
  }

  function renderRuntime(data) {
    const chips = [...(Array.isArray(data.systems) ? data.systems : []), ...(Array.isArray(data.mcp) ? data.mcp : [])];
    chips.push(vpsChip(state.vps));
    refs.systemChips.innerHTML = chips.map((item) => `
      <div class="runtime-chip tone-${item.tone || "degraded"}">
        <div>
          <strong>${item.name || "System"}</strong>
          <span>${item.detail || "No detail"}</span>
        </div>
        <em>${item.status || "unknown"}</em>
      </div>
    `).join("");
    refs.workspaceProject.textContent = data.focus_project || "Unknown";
    refs.workspaceApp.textContent = data.frontmost_app || "Unknown";
    refs.workspaceName.textContent = basenamePath(data.workspace);
  }

  function renderToolPills(data) {
    const tools = Array.isArray(data.active_tools) ? data.active_tools : [];
    refs.toolPillStrip.innerHTML = tools.map((tool) => {
      const info = toolPresentation(tool);
      return `
        <div class="tool-pill">
          <span>${info.icon}</span>
          <span class="tool-pill-dot"></span>
          <span>${info.label}</span>
        </div>
      `;
    }).join("");
  }

  function renderMemoryRecall(data) {
    const memory = data.memory_recall || {};
    const matches = Array.isArray(memory.matches) ? memory.matches : [];
    if (!matches.length) {
      refs.memoryRecallList.innerHTML = "<div class=\"recall-item\"><div class=\"recall-empty\">No memory recall yet. Ask Burry about a prior decision or recent work.</div></div>";
      return;
    }
    refs.memoryRecallList.innerHTML = `
      <article class="recall-item">
        <span class="recall-item-query">${memory.query || "Recent Recall"}</span>
        ${matches.map((match) => `
          <div class="recall-bullet">
            ${match.speech || match.context || "Recalled memory"}${match.timestamp ? ` — ${match.timestamp}` : ""}
          </div>
        `).join("")}
      </article>
    `;
  }

  function renderAmbient(data) {
    const items = (Array.isArray(data.ambient_context) ? data.ambient_context : [])
      .map((item) => String(item || "").trim())
      .filter(Boolean)
      .slice(0, 3);
    refs.ambientList.classList.toggle("is-empty", items.length === 0);
    refs.ambientList.innerHTML = items.length
      ? items.map((item) => `<div class="ambient-item">${item}</div>`).join("")
      : "<div class=\"ambient-empty\">Ambient context will appear here after the daemon writes its next summary.</div>";
  }

  function renderNotifications(data) {
    const payload = data.notifications && typeof data.notifications === "object" ? data.notifications : {};
    const items = (Array.isArray(payload.items) ? payload.items : [])
      .map((item) => ({
        app: collapseWhitespace(item.app || item.bundle || "Notification"),
        status: collapseWhitespace(item.status || "activity"),
        text: collapseWhitespace(item.message || item.summary || item.detail || ""),
        at: collapseWhitespace(item.at || ""),
      }))
      .filter((item) => item.app)
      .slice(0, 4);
    refs.notificationsList.innerHTML = items.length
      ? items.map((item) => `
          <article class="notification-item">
            <div class="notification-topline">
              <strong>${item.app}</strong>
              <span>${item.status}</span>
            </div>
            <div class="notification-body">${item.text || "Notification activity available."}</div>
            <div class="notification-time">${item.at || payload.detail || "recent"}</div>
          </article>
        `).join("")
      : `<div class="notification-empty">${collapseWhitespace(payload.detail || "Recent notification activity will appear here when available.")}</div>`;
  }

  function renderTasks(data, projectItems = state.projects) {
    const items = [];
    for (const task of Array.isArray(data.tasks) ? data.tasks : []) {
      const taskStatus = typeof task === "object" ? String(task.status || "").toLowerCase() : "";
      if (taskStatus === "done" || taskStatus === "completed") continue;
      const taskText = typeof task === "object" ? (task.title || task.text || "") : task;
      if (taskText) items.push({ label: "Live", text: taskText });
    }
    for (const project of projectItems) {
      for (const task of (project.next_tasks || []).slice(0, 2)) {
        items.push({ label: project.name, text: task });
      }
      if (items.length >= 4) break;
    }
    refs.pendingPanel.classList.toggle("has-work", items.length > 0);
    refs.taskList.innerHTML = items.length
      ? items.slice(0, 4).map((item) => `
          <div class="task-item ${item.label === "Live" ? "live" : "project"}">
            <span class="task-tag">${item.label}</span>
            <strong>${item.text}</strong>
          </div>
        `).join("")
      : "<div class=\"task-item\"><span class=\"task-tag\">Status</span><strong>No active tasks.</strong></div>";
  }

  function renderProjects(projectItems) {
    state.projects = projectItems;
    const ordered = [...projectItems].sort((a, b) => (Number(b.completion || 0) - Number(a.completion || 0)));
    refs.projectList.innerHTML = ordered.map((project) => {
      const isFocused = String(project.name || "").trim() === String(state.operator?.focus_project || "").trim();
      const nextAction = (project.next_tasks && project.next_tasks[0]) || (project.blockers && project.blockers[0]) || "No next action logged yet.";
      const blurb = project.blurb || project.description || "";
      const pct = Number(project.completion || 0);
      return `
        <article class="project-card${isFocused ? " is-focused" : ""}">
          <div class="project-topline">
            <div class="project-topline-copy">
              <div class="project-name">${project.name || "Project"}</div>
              ${blurb ? `<div class="project-blurb">${blurb}</div>` : ""}
            </div>
            <div class="project-status">
              <span class="health-dot ${healthClass(project)}"></span>
              <span>${isFocused ? "live focus" : (project.status || "paused")}</span>
            </div>
          </div>
          <div class="progress-wrap">
            <div class="progress-rail">
              <div class="progress-fill" style="width:${pct}%"></div>
            </div>
            <span class="project-pct">${pct}%</span>
          </div>
          <div class="project-next">${nextAction}</div>
          <button class="project-open" type="button" data-project="${project.name || ""}">OPEN PROJECT</button>
        </article>
      `;
    }).join("");

    refs.projectList.querySelectorAll(".project-open").forEach((button) => {
      button.addEventListener("click", async () => {
        const name = button.getAttribute("data-project");
        if (!name) return;
        try {
          await openProject(name);
        } catch (error) {
          console.error(error);
        }
      });
    });
  }

  function renderTranscript(data) {
    const latestHeard = collapseWhitespace(data.last_heard_text);
    if (latestHeard) {
      state.optimisticEntries = state.optimisticEntries.filter((entry) => entry.text !== latestHeard);
    }
    const optimisticHeard = [...state.optimisticEntries]
      .reverse()
      .find((entry) => entry.role === "user" && entry.text);
    refs.transcriptHeard.textContent = latestHeard || optimisticHeard?.text || "Listening for the next command.";
    refs.transcriptHeard.style.opacity = (!latestHeard && optimisticHeard?.dropped) ? "0.45" : "";
    refs.transcriptSpoken.textContent = collapseWhitespace(data.last_spoken_text) || "Standing by.";
  }

  function renderOperator(data) {
    state.operator = data || {};
    const mode = normalizeMode(state.operator);
    refs.modeMood.textContent = state.operator.mood_label || "Focused";
    refs.modeSession.textContent = state.operator.session_label || "Standby";
    refs.modeState.textContent = state.operator.state_label || mode;
    setButlerState(mode, pillNote(state.operator, mode));
    refs.orbSummary.textContent = orbStatusLine(state.operator);
    renderToolPills(state.operator);
    renderRuntime(state.operator);
    renderAmbient(state.operator);
    renderNotifications(state.operator);
    renderMemoryRecall(state.operator);
    renderTasks(state.operator, state.projects);
    renderTranscript(state.operator);
    renderProjects(state.projects);
    events.render(state.operator);
  }

  return {
    normalizeMode,
    pillNote,
    renderOperator,
    renderProjects,
    renderTasks,
    renderTranscript,
    restoreFocus,
    setVpsStatus(payload) {
      state.vps = payload || null;
      renderRuntime(state.operator || {});
    },
    setButlerState,
    setFocus,
  };
}

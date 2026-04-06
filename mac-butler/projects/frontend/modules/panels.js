import { basenamePath } from "./mac-activity.js";
import { formatClock, telemetryEntries } from "./events.js";

function toolPresentation(name) {
  const normalized = String(name || "").trim().toLowerCase();
  if (normalized === "browse_web") return { label: "Browsing", icon: "🌐" };
  if (normalized === "recall_memory") return { label: "Reading", icon: "💾" };
  if (normalized === "take_screenshot_and_describe") return { label: "Seeing", icon: "👁" };
  return { label: "Executing", icon: "⚡" };
}

function healthClass(project) {
  const health = String(project.health_status || project.status || "unknown").toLowerCase();
  if (["healthy", "live", "ready"].includes(health)) return "healthy";
  if (["active", "configured"].includes(health)) return "active";
  if (["paused", "degraded", "unknown"].includes(health)) return health;
  return "offline";
}

export function normalizeMode(data) {
  if (Array.isArray(data.active_tools) && data.active_tools.length) return "executing";
  const state = String(data.state || "").toLowerCase();
  if (["idle", "listening", "thinking", "executing", "speaking"].includes(state)) return state;
  return data.session_active ? "listening" : "idle";
}

export function pillNote(data, mode) {
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
  function setButlerState(mode, note) {
    const cleanedMode = ["idle", "listening", "thinking", "speaking", "executing"].includes(mode) ? mode : "idle";
    refs.body.dataset.state = cleanedMode;
    refs.statePillLabel.textContent = cleanedMode.toUpperCase();
    refs.statePillNote.textContent = note || pillNote(state.operator, cleanedMode);
    orb.setState(cleanedMode);
  }

  function setFocus(nextFocus) {
    state.focusKind = nextFocus;
    refs.body.dataset.focus = nextFocus;
    [refs.modeMood, refs.modeSession, refs.modeState].forEach((button) => {
      button.classList.toggle("is-active", button.dataset.focus === nextFocus);
    });
    refs.orbSummary.textContent = orbStatusLine(state.operator);
  }

  function renderRuntime(data) {
    const chips = [...(Array.isArray(data.systems) ? data.systems : []), ...(Array.isArray(data.mcp) ? data.mcp : [])];
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

  function renderTasks(data, projectItems = state.projects) {
    const items = [];
    for (const task of Array.isArray(data.tasks) ? data.tasks : []) {
      items.push({ label: "Live", text: task });
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
      : "<div class=\"task-item\"><span class=\"task-tag\">Status</span><strong>No pending tasks loaded yet.</strong></div>";
  }

  function renderProjects(projectItems) {
    state.projects = projectItems;
    const ordered = [...projectItems].sort((a, b) => (Number(b.completion || 0) - Number(a.completion || 0)));
    refs.projectList.innerHTML = ordered.map((project) => {
      const nextAction = (project.next_tasks && project.next_tasks[0]) || (project.blockers && project.blockers[0]) || "No next action logged yet.";
      return `
        <article class="project-card">
          <div class="project-topline">
            <div class="project-name">${project.name || "Project"}</div>
            <div class="project-status">
              <span class="health-dot ${healthClass(project)}"></span>
              <span>${project.status || "paused"}</span>
            </div>
          </div>
          <div class="progress-rail">
            <div class="progress-fill" style="width:${Number(project.completion || 0)}%"></div>
          </div>
          <div class="project-next">${Number(project.completion || 0)}% complete · ${nextAction}</div>
          <button class="project-open" type="button" data-project="${project.name || ""}">Open Project</button>
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
    const liveEntries = telemetryEntries(data);
    const seenUserLines = new Set(liveEntries.filter((entry) => entry.role === "user").map((entry) => entry.text));
    state.optimisticEntries = state.optimisticEntries.filter((entry) => !(entry.role === "user" && seenUserLines.has(entry.text)));
    const entries = [...liveEntries, ...state.optimisticEntries].slice(-20);
    if (!entries.length) {
      refs.transcriptLog.innerHTML = "<div class=\"transcript-entry system compact\"><div class=\"entry-text\"><span class=\"system-pill\">SYSTEM</span>System ready. Type a command or press MIC.</div></div>";
      return;
    }
    const nearBottom = refs.transcriptLog.scrollHeight - refs.transcriptLog.scrollTop - refs.transcriptLog.clientHeight < 56;
    refs.transcriptLog.innerHTML = entries.map((entry) => entry.role === "system"
      ? `
        <div class="transcript-entry system compact">
          <div class="entry-text"><span class="system-pill">SYSTEM</span>${entry.text}</div>
        </div>
      `
      : `
        <div class="transcript-entry ${entry.role}">
          <div class="entry-meta">
            ${formatClock(entry.at)}
            <div class="entry-role">${entry.role === "burry" ? "BURRY" : entry.role.toUpperCase()}</div>
          </div>
          <div class="entry-text">${entry.text}</div>
        </div>
      `).join("");
    if (nearBottom) refs.transcriptLog.scrollTop = refs.transcriptLog.scrollHeight;
  }

  function renderToolStream(data) {
    const stream = Array.isArray(data.tool_stream) ? data.tool_stream : [];
    const rows = [...stream];
    const agent = data.last_agent_result || {};
    if (agent.agent && agent.result && !rows.some((row) => row.tool === `agent:${agent.agent}` || row.detail === agent.result)) {
      rows.push({
        tool: `agent:${agent.agent}`,
        status: agent.status || "done",
        detail: agent.result,
        at: agent.at,
      });
    }
    const recentRows = rows.slice(-4).reverse();
    if (!recentRows.length) {
      refs.toolStream.innerHTML = `
        <div class="tool-stream-label">Live Tool Stream</div>
        <div class="tool-stream-item">
          <span class="tool-stream-status"></span>
          <div><strong>Idle</strong> Tool activity will appear here when Burry starts reading, browsing, or executing.</div>
          <span class="tool-stream-time">Now</span>
        </div>
      `;
      return;
    }
    refs.toolStream.innerHTML = `
      <div class="tool-stream-label">Live Tool Stream</div>
      ${recentRows.map((row) => {
        const status = String(row.status || "").toLowerCase();
        const rowClass = status === "running" ? "is-running" : status === "error" ? "is-error" : "is-done";
        const info = toolPresentation(String(row.tool || ""));
        return `
          <div class="tool-stream-item ${rowClass}">
            <span class="tool-stream-status"></span>
            <div><strong>${info.label}</strong> ${row.detail || status || "done"}</div>
            <span class="tool-stream-time">${formatClock(row.at)}</span>
          </div>
        `;
      }).join("")}
    `;
  }

  function renderOperator(data) {
    state.operator = data || {};
    const mode = normalizeMode(state.operator);
    refs.modeMood.textContent = state.operator.mood_label || "Focused";
    refs.modeSession.textContent = state.operator.session_label || "Standby";
    refs.modeState.textContent = state.operator.state_label || mode;
    refs.transcriptStatus.textContent = state.operator.session_active ? "Live" : "Standby";
    setButlerState(mode, pillNote(state.operator, mode));
    refs.orbSummary.textContent = orbStatusLine(state.operator);
    renderToolPills(state.operator);
    renderRuntime(state.operator);
    renderAmbient(state.operator);
    renderMemoryRecall(state.operator);
    renderTasks(state.operator, state.projects);
    renderTranscript(state.operator);
    renderToolStream(state.operator);
    events.render(state.operator);
  }

  return {
    normalizeMode,
    pillNote,
    renderOperator,
    renderProjects,
    renderTasks,
    renderTranscript,
    setButlerState,
    setFocus,
  };
}

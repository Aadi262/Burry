import { TOOL_MAP } from "./panels.js";

const PRIMARY_OPERATOR_WS_URL = "ws://127.0.0.1:3334/ws";

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

export function createOperatorStream({
  bootstrap,
  onConnectionChange,
  onOperator,
  onProjects,
  refs = {},
  setButlerState = () => {},
}) {
  let operatorSocket = null;
  let operatorStreamRetryTimer = null;
  let operatorConnected = false;
  let wasConnected = false;
  let liveToolExecResetTimer = null;
  let traceItems = [];

  function traceFeedEl() {
    return refs?.agentTraceFeed || document.getElementById("agent-trace-feed");
  }

  function toolExecEl() {
    return refs?.toolExecRow || document.getElementById("tool-exec-row");
  }

  function planFeedEl() {
    return refs?.planStepsFeed || document.getElementById("plan-steps-feed");
  }

  function presentTool(tool) {
    const normalized = String(tool || "").trim();
    return TOOL_MAP[normalized] || { label: normalized || "Executing", icon: "⚡" };
  }

  function renderTraceFeed() {
    const el = traceFeedEl();
    if (!el) return;
    if (!traceItems.length) {
      el.innerHTML = '<span class="trace-idle">Waiting for the next live operator event.</span>';
      return;
    }
    el.innerHTML = traceItems.map((item) => `
      <div class="trace-step trace-${escapeHtml(item.tone || "info")}${item.live ? " is-live" : ""}">
        ${escapeHtml(item.text)}
      </div>
    `).join("");
    el.scrollTop = el.scrollHeight;
  }

  function replaceTraceSteps(items) {
    const nextItems = [];
    for (const item of items) {
      const text = normalizeText(item?.text || item);
      if (!text) continue;
      const normalized = {
        text,
        tone: normalizeText(item?.tone || "info").toLowerCase() || "info",
        live: Boolean(item?.live),
      };
      const previous = nextItems[nextItems.length - 1];
      if (previous && previous.text === normalized.text && previous.tone === normalized.tone) {
        previous.live = previous.live || normalized.live;
        continue;
      }
      nextItems.push(normalized);
    }
    traceItems = nextItems.slice(-16);
    renderTraceFeed();
  }

  function appendTraceStep(text, tone = "info", options = {}) {
    replaceTraceSteps([
      ...traceItems,
      {
        text,
        tone,
        live: Boolean(options.live),
      },
    ]);
  }

  function clearToolExecResetTimer() {
    if (!liveToolExecResetTimer) return;
    window.clearTimeout(liveToolExecResetTimer);
    liveToolExecResetTimer = null;
  }

  function onAgentThinking() {
    setButlerState("thinking", "Reasoning through your request...");
    appendTraceStep("Reasoning through the current request.", "thinking", { live: true });
  }

  function onAgentReply(payload) {
    const speech = normalizeText(payload?.speech || "");
    if (speech && refs?.transcriptSpoken) {
      refs.transcriptSpoken.textContent = speech;
    }
    if (speech) {
      appendTraceStep(`Reply ready: ${speech}`, "agent");
    }
    setButlerState("idle", "");
  }

  function onAgentChunk(payload) {
    const text = String(payload?.text || "");
    if (text && refs?.transcriptSpoken) {
      const current = refs.transcriptSpoken.textContent || "";
      refs.transcriptSpoken.textContent = current === "Standing by." ? text : `${current}${text}`;
    }
  }

  function onToolStart(payload) {
    const tool = String(payload?.tool || "tool").trim() || "tool";
    const input = normalizeText(payload?.input || "");
    const info = presentTool(tool);
    setButlerState("executing", `Running ${tool}...`);
    updateLiveToolExec(tool, input, "running");
    appendTraceStep(`Running ${info.label}${input ? ` - ${input}` : ""}`, "running", { live: true });
  }

  function onToolEnd(payload) {
    const tool = String(payload?.tool || "tool").trim() || "tool";
    const result = normalizeText(payload?.result || "");
    const status = String(payload?.status || "ok").trim().toLowerCase() || "ok";
    const info = presentTool(tool);
    updateLiveToolExec(tool, result, status);
    appendTraceStep(`Tool ${status}: ${info.label}${result ? ` - ${result}` : ""}`, status === "error" ? "error" : "ok");
    clearToolExecResetTimer();
    liveToolExecResetTimer = window.setTimeout(() => updateLiveToolExec("", "", "idle"), 3000);
  }

  function onPlanUpdate(payload) {
    const steps = Array.isArray(payload?.steps) ? payload.steps : [];
    const title = normalizeText(payload?.title || "Active Plan") || "Active Plan";
    renderPlanSteps(title, steps);
    appendTraceStep(`Plan updated: ${title}`, "plan");
  }

  function updateLiveToolExec(tool, result, status) {
    const el = toolExecEl();
    if (!el) return;
    if (status === "idle" || !tool) {
      el.classList.remove("is-live");
      el.innerHTML = '<span class="tool-exec-idle">No active tool call.</span>';
      return;
    }
    const info = presentTool(tool);
    const safeStatus = escapeHtml(String(status || "ok").toLowerCase());
    el.classList.toggle("is-live", safeStatus === "running");
    el.innerHTML = `
      <span class="tool-exec-icon">${info.icon}</span>
      <span class="tool-exec-label">${escapeHtml(info.label)}</span>
      <span class="tool-exec-status ${safeStatus}">${safeStatus}</span>
      <span class="tool-exec-result">${escapeHtml(String(result || "").slice(0, 120))}</span>
    `;
  }

  function buildTraceFromOperator(payload) {
    if (payload?.telemetry_fresh === false) {
      return [{ text: "Waiting for live operator telemetry.", tone: "stale" }];
    }
    const items = [];
    const state = normalizeText(payload?.state || "").toLowerCase();
    const heard = normalizeText(payload?.last_heard_text || "");
    if (heard && ["thinking", "executing", "speaking"].includes(state)) {
      items.push({ text: `Command: ${heard}`, tone: "input", live: state !== "speaking" });
    }

    const stream = Array.isArray(payload?.tool_stream) ? payload.tool_stream.slice(-6) : [];
    for (const entry of stream) {
      const tool = normalizeText(entry?.tool || "");
      if (!tool) continue;
      const info = presentTool(tool);
      const status = normalizeText(entry?.status || "ok").toLowerCase() || "ok";
      const detail = normalizeText(entry?.detail || "");
      const prefix = status === "running" ? "Running" : status === "error" ? "Error" : "Finished";
      items.push({
        text: `${prefix} ${info.label}${detail ? ` - ${detail}` : ""}`,
        tone: status === "running" ? "running" : status === "error" ? "error" : "ok",
        live: status === "running",
      });
    }

    const agent = payload?.last_agent_result && typeof payload.last_agent_result === "object"
      ? payload.last_agent_result
      : {};
    const agentStatus = normalizeText(agent.status || "").toLowerCase();
    const agentResult = normalizeText(agent.result || "");
    if (agentResult) {
      items.push({
        text: `Agent ${normalizeText(agent.agent || "operator")}: ${agentResult}`,
        tone: agentStatus === "error" ? "error" : agentStatus === "start" ? "running" : "agent",
        live: agentStatus === "start",
      });
    }

    const spoken = normalizeText(payload?.last_spoken_text || "");
    if (spoken && state === "speaking") {
      items.push({ text: `Replying: ${spoken}`, tone: "agent", live: true });
    }

    return items.length ? items : [{ text: "Waiting for the next live action.", tone: "stale" }];
  }

  function syncTraceFromOperator(payload) {
    replaceTraceSteps(buildTraceFromOperator(payload || {}));
  }

  function syncToolExecFromOperator(payload) {
    if (payload?.telemetry_fresh === false) {
      updateLiveToolExec("", "", "idle");
      return;
    }

    const stream = Array.isArray(payload?.tool_stream) ? payload.tool_stream.slice(-6) : [];
    const activeTools = Array.isArray(payload?.active_tools) ? payload.active_tools : [];
    if (activeTools.length) {
      const currentTool = String(activeTools[activeTools.length - 1] || "").trim();
      const runningEntry = [...stream].reverse().find((entry) => (
        normalizeText(entry?.tool || "") === currentTool
        && normalizeText(entry?.status || "").toLowerCase() === "running"
      ));
      updateLiveToolExec(currentTool, normalizeText(runningEntry?.detail || ""), "running");
      return;
    }

    const lastEntry = [...stream].reverse().find((entry) => normalizeText(entry?.tool || ""));
    if (!lastEntry) {
      updateLiveToolExec("", "", "idle");
      return;
    }

    const lastTool = normalizeText(lastEntry.tool || "");
    const lastStatus = normalizeText(lastEntry.status || "ok").toLowerCase() || "ok";
    updateLiveToolExec(lastTool, normalizeText(lastEntry.detail || ""), lastStatus);
    if (lastStatus !== "running") {
      clearToolExecResetTimer();
      liveToolExecResetTimer = window.setTimeout(() => updateLiveToolExec("", "", "idle"), 3000);
    }
  }

  function applyOperatorPayload(payload) {
    syncTraceFromOperator(payload);
    syncToolExecFromOperator(payload);
    onOperator(payload);
  }

  function renderPlanSteps(title, steps) {
    const el = planFeedEl();
    if (!el) return;
    const normalizedSteps = steps.map((step) => (
      typeof step === "object" && step !== null
        ? { text: normalizeText(step.text || step.content || ""), done: Boolean(step.done) }
        : { text: normalizeText(step), done: false }
    )).filter((step) => step.text);
    if (!normalizedSteps.length) {
      el.innerHTML = '<span class="plan-empty">No active plan.</span>';
      return;
    }
    const activeIndex = normalizedSteps.findIndex((step) => !step.done);
    el.innerHTML = `<div class="plan-title">${escapeHtml(title)}</div>${
      normalizedSteps.map((step, index) => `
        <div class="plan-step ${step.done ? "done" : index === activeIndex ? "active" : ""}">
          <span class="plan-step-num">${index + 1}</span>
          <span class="plan-step-text">${escapeHtml(step.text)}</span>
          ${step.done ? '<span class="plan-check">✓</span>' : ""}
        </div>
      `).join("")
    }`;
  }

  function operatorWsUrls() {
    const candidates = [];
    const seen = new Set();

    function add(url) {
      const value = String(url || "").trim();
      if (!value || seen.has(value)) return;
      seen.add(value);
      candidates.push(value);
    }

    add(PRIMARY_OPERATOR_WS_URL);
    add(bootstrap.wsUrl);
    add(`ws://${window.location.hostname || "127.0.0.1"}:3334/ws`);
    return candidates;
  }

  function handleTransportMessage(raw) {
    try {
      const parsed = JSON.parse(raw);
      if (parsed?.type === "agent_thinking") {
        onAgentThinking();
        return;
      }
      if (parsed?.type === "agent_reply") {
        onAgentReply(parsed.payload);
        return;
      }
      if (parsed?.type === "agent_chunk") {
        onAgentChunk(parsed.payload);
        return;
      }
      if (parsed?.type === "tool_start") {
        onToolStart(parsed.payload);
        return;
      }
      if (parsed?.type === "tool_end") {
        onToolEnd(parsed.payload);
        return;
      }
      if (parsed?.type === "plan_update") {
        onPlanUpdate(parsed.payload);
        return;
      }
      if (parsed && parsed.type === "operator" && parsed.payload) {
        applyOperatorPayload(parsed.payload);
        return;
      }
      if (parsed && parsed.type === "projects") {
        onProjects(Array.isArray(parsed.payload) ? parsed.payload : []);
        return;
      }
      applyOperatorPayload(parsed && parsed.payload ? parsed.payload : parsed);
    } catch (error) {
      console.error(error);
    }
  }

  async function refreshOperator() {
    try {
      const response = await fetch("/api/operator");
      if (!response.ok) return;
      applyOperatorPayload(await response.json());
    } catch (error) {
      console.error(error);
    }
  }

  async function refreshProjects() {
    try {
      const response = await fetch("/api/projects");
      if (!response.ok) return;
      onProjects(await response.json());
    } catch (error) {
      console.error(error);
    }
  }

  function updateConnectionStatus(connected) {
    operatorConnected = connected;
    if (connected || wasConnected) {
      onConnectionChange(connected);
    }
  }

  function scheduleOperatorReconnect() {
    if (operatorStreamRetryTimer) return;
    operatorStreamRetryTimer = window.setTimeout(() => {
      operatorStreamRetryTimer = null;
      connectOperatorStream();
    }, 3000);
  }

  function connectOperatorStream(attemptIndex = 0) {
    if (!window.WebSocket) return false;
    const urls = operatorWsUrls();
    if (!urls.length) return false;

    if (attemptIndex === 0 && operatorSocket) {
      operatorSocket.onclose = null;
      operatorSocket.onerror = null;
      operatorSocket.close();
      operatorSocket = null;
    }

    const socket = new WebSocket(urls[Math.min(attemptIndex, urls.length - 1)]);
    let opened = false;
    operatorSocket = socket;

    socket.onmessage = (event) => {
      handleTransportMessage(event.data);
    };

    socket.onopen = () => {
      opened = true;
      wasConnected = true;
      updateConnectionStatus(true);
    };

    socket.onclose = () => {
      if (operatorSocket === socket) {
        operatorSocket = null;
      }
      if (!opened && attemptIndex < urls.length - 1) {
        connectOperatorStream(attemptIndex + 1);
        return;
      }
      updateConnectionStatus(false);
      scheduleOperatorReconnect();
    };

    socket.onerror = () => {
      updateConnectionStatus(false);
      try {
        socket.close();
      } catch (_error) {}
    };

    return true;
  }

  function hasActiveStream() {
    return operatorConnected;
  }

  function cleanup() {
    clearToolExecResetTimer();
    if (operatorSocket) {
      operatorSocket.onclose = null;
      operatorSocket.onerror = null;
      operatorSocket.close();
      operatorSocket = null;
    }
    if (operatorStreamRetryTimer) {
      window.clearTimeout(operatorStreamRetryTimer);
      operatorStreamRetryTimer = null;
    }
    updateConnectionStatus(false);
  }

  if (bootstrap?.operator) {
    syncTraceFromOperator(bootstrap.operator);
    syncToolExecFromOperator(bootstrap.operator);
  }

  return {
    cleanup,
    connectOperatorStream,
    handleOperatorTransportMessage: handleTransportMessage,
    hasActiveStream,
    refreshOperator,
    refreshProjects,
  };
}

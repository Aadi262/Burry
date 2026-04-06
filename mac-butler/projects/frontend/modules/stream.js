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

  function appendTraceStep(text) {
    const cleaned = normalizeText(text);
    const el = traceFeedEl();
    if (!el || !cleaned) return;
    traceItems = [...traceItems, cleaned].slice(-16);
    el.innerHTML = traceItems.map((item) => `<div class="trace-step">${escapeHtml(item)}</div>`).join("");
    el.scrollTop = el.scrollHeight;
  }

  function clearToolExecResetTimer() {
    if (!liveToolExecResetTimer) return;
    window.clearTimeout(liveToolExecResetTimer);
    liveToolExecResetTimer = null;
  }

  function onAgentThinking() {
    setButlerState("thinking", "Reasoning through your request...");
    appendTraceStep("Reasoning through the current request.");
  }

  function onAgentReply(payload) {
    const speech = normalizeText(payload?.speech || "");
    if (speech && refs?.transcriptSpoken) {
      refs.transcriptSpoken.textContent = speech;
    }
    if (speech) {
      appendTraceStep(`Reply ready: ${speech}`);
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
    const info = TOOL_MAP[tool] || { label: tool, icon: "⚡" };
    setButlerState("executing", `Running ${tool}...`);
    updateLiveToolExec(tool, input, "running");
    appendTraceStep(`Tool started: ${info.label}`);
  }

  function onToolEnd(payload) {
    const tool = String(payload?.tool || "tool").trim() || "tool";
    const result = normalizeText(payload?.result || "");
    const status = String(payload?.status || "ok").trim().toLowerCase() || "ok";
    const info = TOOL_MAP[tool] || { label: tool, icon: "⚡" };
    updateLiveToolExec(tool, result, status);
    appendTraceStep(`Tool ${status}: ${info.label}${result ? ` - ${result}` : ""}`);
    clearToolExecResetTimer();
    liveToolExecResetTimer = window.setTimeout(() => updateLiveToolExec("", "", "idle"), 3000);
  }

  function onPlanUpdate(payload) {
    const steps = Array.isArray(payload?.steps) ? payload.steps : [];
    const title = normalizeText(payload?.title || "Active Plan") || "Active Plan";
    renderPlanSteps(title, steps);
    appendTraceStep(`Plan updated: ${title}`);
  }

  function updateLiveToolExec(tool, result, status) {
    const el = toolExecEl();
    if (!el) return;
    if (status === "idle" || !tool) {
      el.innerHTML = '<span class="tool-exec-idle">No active tool call.</span>';
      return;
    }
    const info = TOOL_MAP[tool] || { label: tool, icon: "⚡" };
    const safeStatus = escapeHtml(String(status || "ok").toLowerCase());
    el.innerHTML = `
      <span class="tool-exec-icon">${info.icon}</span>
      <span class="tool-exec-label">${escapeHtml(info.label)}</span>
      <span class="tool-exec-status ${safeStatus}">${safeStatus}</span>
      <span class="tool-exec-result">${escapeHtml(String(result || "").slice(0, 120))}</span>
    `;
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
        onOperator(parsed.payload);
        return;
      }
      if (parsed && parsed.type === "projects") {
        onProjects(Array.isArray(parsed.payload) ? parsed.payload : []);
        return;
      }
      onOperator(parsed && parsed.payload ? parsed.payload : parsed);
    } catch (error) {
      console.error(error);
    }
  }

  async function refreshOperator() {
    try {
      const response = await fetch("/api/operator");
      if (!response.ok) return;
      onOperator(await response.json());
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

  return {
    cleanup,
    connectOperatorStream,
    handleOperatorTransportMessage: handleTransportMessage,
    hasActiveStream,
    refreshOperator,
    refreshProjects,
  };
}

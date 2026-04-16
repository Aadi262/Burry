function isEditableTarget(target) {
  if (!target) return false;
  const tagName = String(target.tagName || "").toLowerCase();
  return tagName === "input" || tagName === "textarea" || Boolean(target.isContentEditable);
}

function collapseWhitespace(value) {
  return String(value || "").split(/\s+/).filter(Boolean).join(" ").trim();
}

async function postCommand(body) {
  const response = await fetch("/api/v1/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (response.status === 503) {
    const payload = await response.json().catch(() => ({}));
    return { status: payload.status || "busy" };
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `Command failed with ${response.status}`);
  }
  return await response.json().catch(() => ({}));
}

function commandStatusNote(status) {
  if (status === "queued") return "Queued behind the current task.";
  if (status === "acknowledged") return "Acknowledged. Result will stream when it lands.";
  return "Executing now.";
}

export function createCommandController({
  refs,
  state,
  setButlerState,
  renderTranscript,
  refreshOperator,
  hasActiveStream,
  normalizeCurrentMode,
  currentPillNote,
}) {
  let keydownHandler = null;
  let micHoldTimer = null;
  let micRequestActive = false;

  function kickOperatorRefreshWindow() {
    if (!hasActiveStream()) {
      const start = performance.now();
      const fastPoll = () => {
        refreshOperator();
        if (performance.now() - start < 5000) {
          window.setTimeout(fastPoll, 450);
        }
      };
      fastPoll();
      return;
    }
    window.setTimeout(refreshOperator, 250);
  }

  async function sendCommand(text) {
    const clean = collapseWhitespace(text);
    if (!clean) return;

    const entry = {
      role: "user",
      at: new Date().toISOString(),
      text: clean,
    };
    state.optimisticEntries.push(entry);
    renderTranscript(state.operator);
    setButlerState("thinking", "Routing the typed command now.");

    try {
      const result = await postCommand({ text: clean, source: "hud" });
      const status = String(result?.data?.status_label || result?.status_label || result?.status || "").trim().toLowerCase();
      if (result && result.status === "busy") {
        entry.text = clean + " (not received — Burry was busy)";
        entry.dropped = true;
        renderTranscript(state.operator);
        refs.transcriptHeard.style.opacity = "0.45";
      } else if (status === "queued") {
        setButlerState("thinking", commandStatusNote(status));
      } else if (status === "acknowledged") {
        setButlerState("listening", commandStatusNote(status));
        kickOperatorRefreshWindow();
      } else if (status === "executing") {
        setButlerState("executing", commandStatusNote(status));
        kickOperatorRefreshWindow();
      } else {
        kickOperatorRefreshWindow();
      }
    } catch (error) {
      console.error(error);
      setButlerState(normalizeCurrentMode(), currentPillNote());
    }
  }

  async function requestBackendMic() {
    if (micRequestActive) return;
    micRequestActive = true;
    refs.micButton.classList.add("is-recording");
    setButlerState("listening", "Backend Whisper is listening for one command.");
    try {
      await postCommand({ action: "listen_once", source: "hud" });
      kickOperatorRefreshWindow();
    } catch (error) {
      console.error(error);
      setButlerState(normalizeCurrentMode(), currentPillNote());
    } finally {
      micRequestActive = false;
      window.setTimeout(() => refs.micButton.classList.remove("is-recording"), 900);
    }
  }

  function armMicHold() {
    if (micHoldTimer || micRequestActive) return;
    micHoldTimer = window.setTimeout(() => {
      micHoldTimer = null;
      requestBackendMic();
    }, 180);
  }

  function clearMicHold() {
    if (micHoldTimer) {
      window.clearTimeout(micHoldTimer);
      micHoldTimer = null;
    }
    if (!micRequestActive) {
      refs.micButton.classList.remove("is-recording");
    }
  }

  function setupKeyboardShortcuts() {
    keydownHandler = (event) => {
      if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !isEditableTarget(event.target)) {
        event.preventDefault();
        refs.commandInput.focus();
        refs.commandInput.select();
        return;
      }
      if (event.key === "Escape" && document.activeElement === refs.commandInput) {
        // Human-in-loop interrupt: if Burry is busy and there's text, interrupt it (Phase 7)
        const newCmd = refs.commandInput.value.trim();
        if (newCmd && document.body.dataset.state !== "idle") {
          fetch("/api/v1/interrupt", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: newCmd }),
          }).catch(() => {});
          refs.commandInput.value = "";
        }
        refs.commandInput.blur();
        return;
      }
      if (event.key === "Enter" && event.ctrlKey && document.activeElement === refs.commandInput) {
        event.preventDefault();
        refs.commandForm.requestSubmit();
      }
    };
    document.addEventListener("keydown", keydownHandler);
  }

  function setupEventHandlers({ setFocus, modeButtons }) {
    modeButtons.forEach((button) => {
      button.addEventListener("click", () => setFocus(button.dataset.focus || "state"));
    });

    refs.commandForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = refs.commandInput.value;
      refs.commandInput.value = "";
      await sendCommand(text);
    });

    refs.micButton.addEventListener("pointerdown", (event) => {
      if (event.pointerType === "mouse" && event.button !== 0) return;
      armMicHold();
    });
    refs.micButton.addEventListener("pointerup", clearMicHold);
    refs.micButton.addEventListener("pointercancel", clearMicHold);
    refs.micButton.addEventListener("pointerleave", clearMicHold);
    refs.micButton.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        requestBackendMic();
      }
    });

    setupKeyboardShortcuts();
  }

  function cleanup() {
    clearMicHold();
    refs.micButton.classList.remove("is-recording");
    if (keydownHandler) {
      document.removeEventListener("keydown", keydownHandler);
      keydownHandler = null;
    }
  }

  return {
    cleanup,
    sendCommand,
    setupEventHandlers,
  };
}

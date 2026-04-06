function isEditableTarget(target) {
  if (!target) return false;
  const tagName = String(target.tagName || "").toLowerCase();
  return tagName === "input" || tagName === "textarea" || Boolean(target.isContentEditable);
}

function collapseWhitespace(value) {
  return String(value || "").split(/\s+/).filter(Boolean).join(" ").trim();
}

async function postCommand(body) {
  const response = await fetch("/api/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `Command failed with ${response.status}`);
  }
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

    state.optimisticEntries.push({
      role: "user",
      at: new Date().toISOString(),
      text: clean,
    });
    renderTranscript(state.operator);
    setButlerState("thinking", "Routing the typed command now.");

    try {
      await postCommand({ text: clean, source: "hud" });
      kickOperatorRefreshWindow();
    } catch (error) {
      console.error(error);
      setButlerState(normalizeCurrentMode(), currentPillNote());
    }
  }

  async function requestBackendMic() {
    refs.micButton.classList.add("is-recording");
    setButlerState("listening", "Backend Whisper is listening for one command.");
    try {
      await postCommand({ action: "listen_once", source: "hud" });
      kickOperatorRefreshWindow();
    } catch (error) {
      console.error(error);
      setButlerState(normalizeCurrentMode(), currentPillNote());
    } finally {
      window.setTimeout(() => refs.micButton.classList.remove("is-recording"), 1200);
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

    refs.micButton.addEventListener("click", async () => {
      await requestBackendMic();
    });

    setupKeyboardShortcuts();
  }

  function cleanup() {
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

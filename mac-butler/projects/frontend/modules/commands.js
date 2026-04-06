export function createCommandController({
  refs,
  state,
  orb,
  setButlerState,
  renderTranscript,
  refreshOperator,
  hasActiveStream,
  normalizeCurrentMode,
  currentPillNote,
}) {
  let recognition = null;
  let recognitionActive = false;
  let micStream = null;
  let audioContext = null;
  let micAnalyser = null;
  let micSource = null;

  async function startMicMonitor() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
    if (micStream) return;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
      micSource = audioContext.createMediaStreamSource(micStream);
      micAnalyser = audioContext.createAnalyser();
      micAnalyser.fftSize = 128;
      micAnalyser.smoothingTimeConstant = 0.65;
      micSource.connect(micAnalyser);
      const data = new Uint8Array(micAnalyser.frequencyBinCount);
      const tick = () => {
        if (!micAnalyser || !recognitionActive) return;
        micAnalyser.getByteFrequencyData(data);
        const average = data.reduce((sum, value) => sum + value, 0) / Math.max(1, data.length);
        orb.setMicLevel(average / 255);
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    } catch (error) {
      console.error(error);
    }
  }

  function stopMicMonitor() {
    orb.setMicLevel(0);
    if (micSource) {
      try { micSource.disconnect(); } catch (_error) {}
    }
    micSource = null;
    micAnalyser = null;
    if (micStream) {
      micStream.getTracks().forEach((track) => track.stop());
    }
    micStream = null;
  }

  async function sendCommand(text) {
    const clean = " ".join(String(text || "").split()).trim();
    if (!clean) return;

    state.optimisticEntries.push({
      role: "user",
      at: new Date().toISOString(),
      text: clean,
    });
    renderTranscript(state.operator);
    setButlerState("thinking", "Routing the typed command now.");

    try {
      await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: clean }),
      });
      if (!hasActiveStream()) {
        const start = performance.now();
        const fastPoll = () => {
          refreshOperator();
          if (performance.now() - start < 5000) {
            window.setTimeout(fastPoll, 450);
          }
        };
        fastPoll();
      } else {
        window.setTimeout(refreshOperator, 250);
      }
    } catch (error) {
      console.error(error);
    }
  }

  function setupSpeechRecognition() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) return null;
    const engine = new Recognition();
    engine.lang = "en-IN";
    engine.interimResults = true;
    engine.continuous = false;

    engine.onstart = async () => {
      recognitionActive = true;
      refs.micButton.classList.add("is-recording");
      setButlerState("listening", "Browser mic is active. Speak naturally.");
      await startMicMonitor();
    };

    engine.onresult = (event) => {
      let transcript = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        transcript += event.results[index][0].transcript || "";
      }
      refs.commandInput.value = transcript.trim();
      const lastResult = event.results[event.results.length - 1];
      if (lastResult && lastResult.isFinal) {
        sendCommand(transcript);
      }
    };

    engine.onend = () => {
      recognitionActive = false;
      refs.micButton.classList.remove("is-recording");
      stopMicMonitor();
      setButlerState(normalizeCurrentMode(), currentPillNote());
    };

    engine.onerror = () => {
      recognitionActive = false;
      refs.micButton.classList.remove("is-recording");
      stopMicMonitor();
      setButlerState(normalizeCurrentMode(), currentPillNote());
    };

    return engine;
  }

  function setupEventHandlers({ setFocus, modeButtons }) {
    recognition = setupSpeechRecognition();

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
      if (!recognition) {
        const active = refs.micButton.classList.toggle("is-recording");
        if (active) {
          await startMicMonitor();
          setButlerState("listening", "Browser mic monitor is active.");
        } else {
          stopMicMonitor();
          setButlerState(normalizeCurrentMode(), currentPillNote());
        }
        return;
      }
      if (recognitionActive) {
        recognition.stop();
        return;
      }
      try {
        recognition.start();
      } catch (error) {
        console.error(error);
      }
    });
  }

  function cleanup() {
    if (recognition && recognitionActive) {
      try {
        recognition.stop();
      } catch (_error) {}
    }
    stopMicMonitor();
  }

  return {
    cleanup,
    sendCommand,
    setupEventHandlers,
  };
}

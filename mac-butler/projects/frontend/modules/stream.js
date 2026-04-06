const PRIMARY_OPERATOR_WS_URL = "ws://127.0.0.1:3334/ws";

export function createOperatorStream({ bootstrap, onConnectionChange, onOperator, onProjects }) {
  let operatorSocket = null;
  let operatorStreamRetryTimer = null;
  let operatorConnected = false;

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
    onConnectionChange(connected);
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

export function createOperatorStream({ bootstrap, onConnectionChange, onOperator, onProjects }) {
  let operatorSocket = null;
  let operatorStreamRetryTimer = null;
  let operatorConnected = false;

  function handleOperatorTransportMessage(raw) {
    try {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.type === "operator" && parsed.payload) {
        onOperator(parsed.payload);
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

  function operatorWsUrl() {
    if (bootstrap.wsUrl) return bootstrap.wsUrl;
    return `ws://${window.location.hostname || "127.0.0.1"}:3334/ws`;
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

  function connectOperatorStream() {
    if (!window.WebSocket) return false;
    if (operatorSocket) {
      operatorSocket.close();
    }

    const socket = new WebSocket(operatorWsUrl());
    operatorSocket = socket;

    socket.onmessage = (event) => {
      handleOperatorTransportMessage(event.data);
    };

    socket.onopen = () => {
      updateConnectionStatus(true);
    };

    socket.onclose = () => {
      if (operatorSocket === socket) {
        operatorSocket = null;
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
    handleOperatorTransportMessage,
    hasActiveStream,
    refreshOperator,
    refreshProjects,
  };
}

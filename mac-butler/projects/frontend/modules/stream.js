export function createOperatorStream({ bootstrap, onOperator, onProjects }) {
  let operatorStream = null;
  let operatorStreamRetryTimer = null;

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

  function scheduleOperatorReconnect(preferSse = false) {
    if (operatorStreamRetryTimer) return;
    operatorStreamRetryTimer = window.setTimeout(() => {
      operatorStreamRetryTimer = null;
      connectOperatorStream(preferSse);
      refreshOperator();
    }, 1500);
  }

  function connectOperatorSse() {
    if (!window.EventSource) return false;
    if (operatorStream) {
      operatorStream.close();
    }

    const stream = new EventSource("/api/stream");
    operatorStream = stream;

    stream.onmessage = (event) => {
      handleOperatorTransportMessage(event.data);
    };

    stream.onerror = () => {
      try {
        stream.close();
      } catch (_error) {}
      if (operatorStream === stream) {
        operatorStream = null;
      }
      scheduleOperatorReconnect(false);
    };

    return true;
  }

  function connectOperatorWebSocket() {
    if (!window.WebSocket) return false;
    if (operatorStream) {
      operatorStream.close();
    }

    const socket = new WebSocket(operatorWsUrl());
    operatorStream = socket;

    socket.onmessage = (event) => {
      handleOperatorTransportMessage(event.data);
    };

    socket.onclose = () => {
      if (operatorStream === socket) {
        operatorStream = null;
      }
      scheduleOperatorReconnect(true);
    };

    socket.onerror = () => {
      try {
        socket.close();
      } catch (_error) {}
    };

    return true;
  }

  function connectOperatorStream(preferSse = false) {
    if (!preferSse && connectOperatorWebSocket()) return true;
    return connectOperatorSse();
  }

  function hasActiveStream() {
    return Boolean(operatorStream);
  }

  function cleanup() {
    if (operatorStream) {
      operatorStream.close();
      operatorStream = null;
    }
    if (operatorStreamRetryTimer) {
      window.clearTimeout(operatorStreamRetryTimer);
      operatorStreamRetryTimer = null;
    }
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

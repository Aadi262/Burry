import { createCommandController } from "./modules/commands.js";
import { createEventsPanel } from "./modules/events.js";
import { createProjectGraph } from "./modules/graph.js";
import { createMacActivityPanel } from "./modules/mac-activity.js";
import { createOrbSystem } from "./modules/orb.js";
import { createPanels } from "./modules/panels.js";
import { createOperatorStream } from "./modules/stream.js";

const bootstrapNode = document.getElementById("burry-bootstrap");
const bootstrap = bootstrapNode ? JSON.parse(bootstrapNode.textContent || "{}") : {};

const state = {
  operator: bootstrap.operator || {},
  optimisticEntries: [],
  projects: bootstrap.projects || [],
  focusKind: "state",
  vps: null,
};

const refs = {
  body: document.body,
  offlineBanner: document.getElementById("offline-banner"),
  networkCanvas: document.getElementById("network-canvas"),
  orbCanvas: document.getElementById("orb-canvas"),
  graphCanvas: document.getElementById("project-graph-canvas"),
  graphTooltip: document.getElementById("graph-tooltip"),
  graphDetail: document.getElementById("graph-detail"),
  statePillLabel: document.getElementById("state-pill-label"),
  statePillNote: document.getElementById("state-pill-note"),
  toolPillStrip: document.getElementById("tool-pill-strip"),
  modeMood: document.getElementById("mode-mood"),
  modeSession: document.getElementById("mode-session"),
  modeState: document.getElementById("mode-state"),
  macActivityList: document.getElementById("mac-activity-list"),
  systemChips: document.getElementById("system-chips"),
  workspaceProject: document.getElementById("workspace-project"),
  workspaceApp: document.getElementById("workspace-app"),
  workspaceName: document.getElementById("workspace-name"),
  ambientList: document.getElementById("ambient-list"),
  memoryRecallList: document.getElementById("memory-recall-list"),
  pendingPanel: document.getElementById("pending-panel"),
  taskList: document.getElementById("task-list"),
  orbSummary: document.getElementById("orb-summary"),
  transcriptHeard: document.getElementById("transcript-heard"),
  transcriptSpoken: document.getElementById("transcript-spoken"),
  commandForm: document.getElementById("command-form"),
  commandInput: document.getElementById("command-input"),
  micButton: document.getElementById("mic-button"),
  eventsFeed: document.getElementById("events-feed"),
  projectList: document.getElementById("project-list"),
};

const { orb } = createOrbSystem({
  networkCanvas: refs.networkCanvas,
  orbCanvas: refs.orbCanvas,
});

const graph = createProjectGraph({
  canvas: refs.graphCanvas,
  tooltip: refs.graphTooltip,
  detail: refs.graphDetail,
});
const events = createEventsPanel({ container: refs.eventsFeed });
const macActivity = createMacActivityPanel({ container: refs.macActivityList });

const panels = createPanels({
  refs,
  state,
  orb,
  events,
  openProject: async (name) => fetch(`/api/open_project?name=${encodeURIComponent(name)}`, { method: "POST" }),
});

const stream = createOperatorStream({
  bootstrap,
  onConnectionChange: (connected) => {
    refs.offlineBanner.hidden = connected;
  },
  onOperator: (payload) => panels.renderOperator(payload),
  onProjects: (items) => {
    state.projects = items;
    panels.renderProjects(items);
    panels.renderTasks(state.operator, items);
    graph.setProjects(items);
  },
});

const commands = createCommandController({
  refs,
  state,
  orb,
  setButlerState: panels.setButlerState,
  renderTranscript: panels.renderTranscript,
  refreshOperator: stream.refreshOperator,
  hasActiveStream: stream.hasActiveStream,
  normalizeCurrentMode: () => panels.normalizeMode(state.operator),
  currentPillNote: () => panels.pillNote(state.operator, panels.normalizeMode(state.operator)),
});

async function refreshVps() {
  try {
    const response = await fetch("/api/vps");
    if (!response.ok) return;
    panels.setVpsStatus(await response.json());
  } catch (error) {
    console.error(error);
  }
}

window.setButlerState = panels.setButlerState;

panels.renderProjects(state.projects);
panels.renderOperator(state.operator);
graph.setProjects(state.projects);
graph.refresh();
refreshVps();
commands.setupEventHandlers({
  setFocus: panels.setFocus,
  modeButtons: [refs.modeMood, refs.modeSession, refs.modeState],
});
panels.setFocus("state");
macActivity.refresh();

stream.connectOperatorStream();
window.setInterval(stream.refreshProjects, 8000);
window.setInterval(macActivity.refresh, 10000);
window.setInterval(graph.refresh, 60000);
window.setInterval(refreshVps, 30000);
window.addEventListener("beforeunload", () => {
  stream.cleanup();
  commands.cleanup();
  graph.destroy();
});

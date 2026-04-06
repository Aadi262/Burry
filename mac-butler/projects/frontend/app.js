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
};

const refs = {
  body: document.body,
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
  transcriptStatus: document.getElementById("transcript-status"),
  transcriptLog: document.getElementById("transcript-log"),
  toolStream: document.getElementById("tool-stream"),
  commandForm: document.getElementById("command-form"),
  commandInput: document.getElementById("command-input"),
  micButton: document.getElementById("mic-button"),
  eventsFeed: document.getElementById("events-feed"),
  projectList: document.getElementById("project-list"),
  eventTrack: document.getElementById("event-track"),
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
const events = createEventsPanel({ container: refs.eventsFeed, refs });
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

window.setButlerState = panels.setButlerState;

panels.renderProjects(state.projects);
panels.renderOperator(state.operator);
graph.setProjects(state.projects);
graph.refresh();
commands.setupEventHandlers({
  setFocus: panels.setFocus,
  modeButtons: [refs.modeMood, refs.modeSession, refs.modeState],
});
panels.setFocus("state");
macActivity.refresh();

if (!stream.connectOperatorStream()) {
  window.setInterval(stream.refreshOperator, 2000);
}
window.setInterval(stream.refreshProjects, 8000);
window.setInterval(macActivity.refresh, 10000);
window.setInterval(graph.refresh, 60000);
window.addEventListener("beforeunload", () => {
  stream.cleanup();
  commands.cleanup();
  graph.destroy();
});

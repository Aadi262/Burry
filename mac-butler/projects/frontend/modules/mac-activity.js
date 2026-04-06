export const APP_CATEGORIES = {
  "Google Chrome": "browser",
  Safari: "browser",
  Firefox: "browser",
  Cursor: "editor",
  "Visual Studio Code": "editor",
  Terminal: "shell",
  iTerm2: "shell",
  Spotify: "music",
  Claude: "ai",
  ChatGPT: "ai",
  Slack: "comms",
  Discord: "comms",
  Telegram: "comms",
  Figma: "design",
  Sketch: "design",
  TablePlus: "data",
  Obsidian: "notes",
};

const APP_CATEGORY_BADGES = {
  ai: {
    background: "rgba(0, 255, 136, 0.12)",
    border: "rgba(0, 255, 136, 0.3)",
    color: "#5dffb0",
  },
  browser: {
    background: "rgba(79, 143, 255, 0.14)",
    border: "rgba(79, 143, 255, 0.34)",
    color: "#8db2ff",
  },
  comms: {
    background: "rgba(255, 34, 68, 0.12)",
    border: "rgba(255, 34, 68, 0.3)",
    color: "#ff7c91",
  },
  data: {
    background: "rgba(255, 170, 0, 0.12)",
    border: "rgba(255, 170, 0, 0.3)",
    color: "#ffd37a",
  },
  design: {
    background: "rgba(255, 98, 176, 0.14)",
    border: "rgba(255, 98, 176, 0.3)",
    color: "#ff9bca",
  },
  editor: {
    background: "rgba(0, 212, 255, 0.12)",
    border: "rgba(0, 212, 255, 0.3)",
    color: "#72e7ff",
  },
  music: {
    background: "rgba(123, 94, 167, 0.16)",
    border: "rgba(123, 94, 167, 0.34)",
    color: "#baa2e3",
  },
  notes: {
    background: "rgba(176, 227, 102, 0.12)",
    border: "rgba(176, 227, 102, 0.28)",
    color: "#d0f493",
  },
  shell: {
    background: "rgba(255, 170, 0, 0.12)",
    border: "rgba(255, 170, 0, 0.3)",
    color: "#ffc65a",
  },
  tool: {
    background: "rgba(232, 244, 255, 0.08)",
    border: "rgba(232, 244, 255, 0.18)",
    color: "rgba(232, 244, 255, 0.72)",
  },
};

export function basenamePath(value) {
  const text = String(value || "").trim();
  if (!text) return "Unknown";
  const parts = text.split("/").filter(Boolean);
  return parts[parts.length - 1] || text;
}

export function appCategory(name) {
  return APP_CATEGORIES[String(name || "").trim()] || "tool";
}

export function appCategoryBadgeStyle(name) {
  return APP_CATEGORY_BADGES[appCategory(name)] || APP_CATEGORY_BADGES.tool;
}

function browserDomain(url) {
  const value = String(url || "").trim();
  if (!value) return "";
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch (_error) {
    return value;
  }
}

function uniqueApps(apps) {
  const seen = new Set();
  const items = [];
  for (const app of Array.isArray(apps) ? apps : []) {
    const label = String(app || "").trim();
    if (!label || seen.has(label)) continue;
    seen.add(label);
    items.push(label);
  }
  return items;
}

function appContext(appName, payload) {
  const category = appCategory(appName);
  if (category === "editor") {
    return basenamePath(payload.cursor_workspace);
  }
  if (category === "browser") {
    return browserDomain(payload.browser_url) || "Browser active";
  }
  if (category === "music") {
    return payload.spotify_track || "Ready";
  }
  if (category === "shell") {
    const count = Array.isArray(payload.open_windows) ? payload.open_windows.length : 0;
    return `${count || 1} window${count === 1 ? "" : "s"}`;
  }
  if (appName === payload.frontmost_app && Array.isArray(payload.open_windows) && payload.open_windows[0]) {
    return payload.open_windows[0];
  }
  return category;
}

function appStatus(appName, payload) {
  if (appName === payload.frontmost_app) return "frontmost";
  const category = appCategory(appName);
  if ((category === "editor" && payload.cursor_workspace) || (category === "browser" && payload.browser_url) || (category === "music" && payload.spotify_track)) {
    return "active";
  }
  return "background";
}

export function renderMacActivity(container, payload) {
  const apps = uniqueApps(payload.open_apps);
  if (!apps.length) {
    container.innerHTML = "<div class=\"mac-activity-empty\">No app activity captured yet.</div>";
    return;
  }
  container.innerHTML = apps.map((appName) => {
    const status = appStatus(appName, payload);
    const category = appCategory(appName);
    const badge = appCategoryBadgeStyle(appName);
    const context = appContext(appName, payload);
    return `
      <article class="mac-app-row ${status === "frontmost" ? "is-frontmost" : ""}">
        <span class="mac-app-status is-${status}"></span>
        <div class="mac-app-copy">
          <div class="mac-app-topline">
            <strong>${appName}</strong>
            <span
              class="mac-app-badge"
              style="background:${badge.background};border-color:${badge.border};color:${badge.color};"
            >${category}</span>
          </div>
          <div class="mac-app-context">${context}</div>
        </div>
      </article>
    `;
  }).join("");
}

export function createMacActivityPanel({ container }) {
  async function refresh() {
    try {
      const response = await fetch("/api/mac-activity");
      if (!response.ok) return;
      renderMacActivity(container, await response.json());
    } catch (error) {
      console.error(error);
    }
  }

  return { refresh };
}

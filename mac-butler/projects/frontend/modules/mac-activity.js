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

export function basenamePath(value) {
  const text = String(value || "").trim();
  if (!text) return "Unknown";
  const parts = text.split("/").filter(Boolean);
  return parts[parts.length - 1] || text;
}

export function appCategory(name) {
  return APP_CATEGORIES[String(name || "").trim()] || "tool";
}

export function appCategoryTone(name) {
  const category = appCategory(name);
  if (category === "editor") return "accent";
  if (category === "browser") return "cobalt";
  if (category === "music") return "violet";
  if (category === "shell") return "amber";
  if (category === "ai") return "success";
  return "faint";
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
    const tone = appCategoryTone(appName);
    const context = appContext(appName, payload);
    return `
      <article class="mac-app-row ${status === "frontmost" ? "is-frontmost" : ""}">
        <span class="mac-app-status is-${status}"></span>
        <div class="mac-app-copy">
          <div class="mac-app-topline">
            <strong>${appName}</strong>
            <span class="mac-app-badge tone-${tone}">${category}</span>
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

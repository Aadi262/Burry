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

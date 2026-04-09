"""Canonical tool registry layered over Butler's existing executor."""

from __future__ import annotations

from typing import Any

from .contracts import ToolSpec

try:
    from intents.router import _gmail_compose_url, _youtube_search_url
except Exception:
    _gmail_compose_url = None
    _youtube_search_url = None

_RAW_EXECUTOR_ACTIONS = (
    "open_terminal",
    "open_editor",
    "open_app",
    "open_folder",
    "create_and_open",
    "run_command",
    "play_music",
    "search_and_play",
    "write_file",
    "obsidian_note",
    "ssh_open",
    "ssh_command",
    "open_url",
    "focus_app",
    "minimize_app",
    "hide_app",
    "chrome_open_tab",
    "chrome_close_tab",
    "chrome_focus_tab",
    "send_email",
    "send_whatsapp",
    "notify",
    "remind_in",
    "run_agent",
    "open_project",
    "open_dashboard",
    "github_sync",
    "speak_only",
    "quit_app",
    "open_in_editor",
    "open_last_workspace",
    "open_terminal_command",
    "create_file_in_editor",
    "spotify_search_play",
    "spotify_pause",
    "spotify_next",
    "spotify_prev",
    "spotify_volume",
    "spotify_now_playing",
    "create_folder",
    "open_url_in_browser",
    "browser_new_tab",
    "browser_search",
    "browser_close_tab",
    "browser_close_window",
    "pause_video",
    "volume_set",
    "system_volume",
    "screenshot",
    "whatsapp_open",
    "whatsapp_send",
)


def _identity_action(action_type: str):
    def _build(args: dict[str, Any]) -> dict[str, Any]:
        return {"type": action_type, **dict(args)}

    return _build


def _compose_email_action(args: dict[str, Any]) -> dict[str, Any]:
    if _gmail_compose_url is None:
        raise RuntimeError("compose email action unavailable")
    return {
        "type": "open_url_in_browser",
        "url": _gmail_compose_url(
            args.get("recipient", ""),
            args.get("subject", ""),
            args.get("body", ""),
        ),
    }


def _youtube_play_action(args: dict[str, Any]) -> dict[str, Any]:
    if _youtube_search_url is None:
        raise RuntimeError("youtube search action unavailable")
    return {
        "type": "open_url_in_browser",
        "url": _youtube_search_url(str(args.get("query", "")).strip()),
    }


def _run_agent_action(agent: str):
    def _build(args: dict[str, Any]) -> dict[str, Any]:
        payload = {key: value for key, value in dict(args).items() if value not in (None, "")}
        payload["type"] = "run_agent"
        payload["agent"] = agent
        return payload

    return _build


def _generic_description(name: str) -> str:
    return name.replace("_", " ")


TOOL_SPECS: dict[str, ToolSpec] = {
    "minimize_app": ToolSpec(
        name="minimize_app",
        action_type="minimize_app",
        kind="control",
        description="Minimize the frontmost app window.",
        required_args=("app",),
        quick_response="Minimizing the current window.",
        action_builder=_identity_action("minimize_app"),
    ),
    "create_folder": ToolSpec(
        name="create_folder",
        action_type="create_folder",
        kind="control",
        description="Create a folder at a resolved filesystem path.",
        required_args=("path",),
        quick_response="Creating that folder.",
        action_builder=_identity_action("create_folder"),
        aliases=("make_folder", "new_folder"),
    ),
    "compose_email": ToolSpec(
        name="compose_email",
        action_type="open_url_in_browser",
        kind="draft",
        description="Open Gmail compose with recipient, subject, and body prefilled.",
        quick_response="Opening Gmail compose.",
        action_builder=_compose_email_action,
    ),
    "play_youtube": ToolSpec(
        name="play_youtube",
        action_type="open_url_in_browser",
        kind="control",
        description="Open YouTube results for a requested song or video.",
        required_args=("query",),
        quick_response="Opening that on YouTube.",
        action_builder=_youtube_play_action,
        aliases=("youtube_play", "youtube_search"),
    ),
    "lookup_weather": ToolSpec(
        name="lookup_weather",
        action_type="run_agent",
        kind="lookup",
        description="Look up current weather or forecast for a location.",
        required_args=("query",),
        latency_budget_s=8.0,
        sync_execution=True,
        action_builder=_run_agent_action("search"),
        aliases=("weather", "weather_lookup"),
    ),
    "lookup_web": ToolSpec(
        name="lookup_web",
        action_type="run_agent",
        kind="lookup",
        description="Look up current facts or web information and answer directly.",
        required_args=("query",),
        latency_budget_s=8.0,
        sync_execution=True,
        action_builder=_run_agent_action("search"),
        aliases=("search_web", "live_lookup"),
    ),
    "lookup_news": ToolSpec(
        name="lookup_news",
        action_type="run_agent",
        kind="lookup",
        description="Fetch current news for a topic and summarize the latest developments.",
        latency_budget_s=8.0,
        sync_execution=True,
        action_builder=_run_agent_action("news"),
        aliases=("news", "latest_news"),
    ),
    "check_vps": ToolSpec(
        name="check_vps",
        action_type="run_agent",
        kind="lookup",
        description="Check VPS health, CPU, memory, disk, and container status.",
        latency_budget_s=10.0,
        sync_execution=True,
        action_builder=_run_agent_action("vps"),
        quick_response="Checking the VPS.",
        aliases=("vps_status", "check_server"),
    ),
}

for action_name in _RAW_EXECUTOR_ACTIONS:
    TOOL_SPECS.setdefault(
        action_name,
        ToolSpec(
            name=action_name,
            action_type=action_name,
            kind="control",
            description=_generic_description(action_name),
            action_builder=_identity_action(action_name),
        ),
    )


def get_tool_spec(name: str) -> ToolSpec | None:
    cleaned = str(name or "").strip()
    if not cleaned:
        return None
    direct = TOOL_SPECS.get(cleaned)
    if direct is not None:
        return direct
    lowered = cleaned.lower()
    for spec in TOOL_SPECS.values():
        if lowered == spec.name.lower() or lowered in {alias.lower() for alias in spec.aliases}:
            return spec
    return None


def build_action(tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any] | None:
    spec = get_tool_spec(tool_name)
    if spec is None:
        return None
    payload = dict(spec.default_args)
    payload.update(dict(args or {}))
    if spec.action_builder is not None:
        return spec.action_builder(payload)
    return {"type": spec.action_type, **payload}


def tool_catalog_for_prompt() -> str:
    lines = []
    for name in ("minimize_app", "create_folder", "compose_email", "play_youtube", "lookup_weather", "lookup_web", "lookup_news", "check_vps"):
        spec = TOOL_SPECS[name]
        required = f" args={', '.join(spec.required_args)}" if spec.required_args else ""
        lines.append(f"- {spec.name}: {spec.description}.{required}")
    return "\n".join(lines)

#!/usr/bin/env python3
"""
vscode_context.py — Reads VS Code/Cursor storage to find recently opened files/folders.

Checks multiple editor storage paths:
    - VS Code: ~/Library/Application Support/Code/User/globalStorage/storage.json
    - Cursor:  ~/Library/Application Support/Cursor/User/globalStorage/storage.json

Returns structured data for the context engine.
"""

import json
import urllib.parse
from pathlib import Path


# Possible storage paths for different editors (macOS)
STORAGE_SOURCES = [
    {
        "editor": "vscode",
        "app_name": "Visual Studio Code",
        "path": Path.home()
        / "Library"
        / "Application Support"
        / "Code"
        / "User"
        / "globalStorage"
        / "storage.json",
    },
    {
        "editor": "cursor",
        "app_name": "Cursor",
        "path": Path.home()
        / "Library"
        / "Application Support"
        / "Cursor"
        / "User"
        / "globalStorage"
        / "storage.json",
    },
    {
        "editor": "cursor",
        "app_name": "Cursor",
        "path": Path.home() / "Library" / "Application Support" / "Cursor" / "storage.json",
    },
]


def get_vscode_context() -> dict:
    """
    Read VS Code/Cursor storage and extract recently opened folders/files.

    Returns:
        {
            "workspaces": ["auth-service", "email-infra", ...],
            "workspace_paths": ["/Users/.../repo", ...],
            "recent_files": ["handler.py", "config.ts", ...],
            "editor": "vscode" | "cursor" | None,
            "app_name": "Visual Studio Code" | "Cursor" | None,
            "has_data": True/False
        }
    """
    result = {
        "workspaces": [],
        "workspace_paths": [],
        "recent_files": [],
        "editor": None,
        "app_name": None,
        "has_data": False,
    }

    sources = [source for source in STORAGE_SOURCES if source["path"].exists()]
    sources.sort(key=lambda source: source["path"].stat().st_mtime, reverse=True)

    # Try newest editor storage first
    for source in sources:
        storage_path = source["path"]
        if not storage_path.exists():
            continue

        try:
            with open(storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        result["editor"] = source["editor"]
        result["app_name"] = source["app_name"]

        workspace_paths = _collect_workspace_paths(data)
        for workspace_path in workspace_paths[:10]:
            name = Path(workspace_path).name or workspace_path
            if workspace_path not in result["workspace_paths"]:
                result["workspace_paths"].append(workspace_path)
            if name and name not in result["workspaces"]:
                result["workspaces"].append(name)

        # Legacy opened-path storage used by some versions
        opened = data.get("openedPathsList", {})
        files = opened.get("files2", []) or opened.get("files", [])

        for file_path in files[:10]:
            if isinstance(file_path, str):
                name = _extract_name(file_path)
                if name and name not in result["recent_files"]:
                    result["recent_files"].append(name)

        if result["workspace_paths"] or result["recent_files"]:
            result["has_data"] = True
            break  # Found data, stop checking other paths

    return result


def _collect_workspace_paths(data: dict) -> list[str]:
    paths = []
    seen = set()

    backup = data.get("backupWorkspaces", {})
    for item in backup.get("folders", []):
        folder_uri = item.get("folderUri", "")
        path = _extract_path(folder_uri)
        if path and path not in seen:
            seen.add(path)
            paths.append(path)

    profile_workspaces = data.get("profileAssociations", {}).get("workspaces", {})
    for uri in profile_workspaces.keys():
        path = _extract_path(uri)
        if path and path not in seen:
            seen.add(path)
            paths.append(path)

    opened = data.get("openedPathsList", {})
    for key in ("workspaces3", "workspaces2", "workspaces"):
        for item in opened.get(key, []):
            path = _extract_path(item)
            if path and path not in seen:
                seen.add(path)
                paths.append(path)

    return paths


def _extract_path(ws_entry) -> str:
    """Extract a filesystem path from a workspace entry."""
    if isinstance(ws_entry, str):
        uri = ws_entry
    elif isinstance(ws_entry, dict):
        uri = ws_entry.get("folderUri") or ws_entry.get("configPath") or ""
    else:
        return ""

    if not uri:
        return ""

    if uri.startswith("file://"):
        uri = uri.replace("file://", "", 1)
    uri = urllib.parse.unquote(uri)
    return uri.rstrip("/")


def _extract_name(ws_entry) -> str:
    """Extract a clean folder name from a workspace entry."""
    path = _extract_path(ws_entry)
    return path.split("/")[-1] if path else ""


def format_vscode_context(data: dict) -> str:
    """Format VS Code data as a human-readable string."""
    if not data["has_data"]:
        return "(No recent editor data found.)"

    lines = []
    editor = data.get("app_name") or data["editor"] or "editor"
    if data["workspaces"]:
        lines.append(f"  Open in {editor}: {', '.join(data['workspaces'][:5])}")
    if data["recent_files"]:
        lines.append(f"  Recent files: {', '.join(data['recent_files'][:5])}")
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== VS Code / Cursor Context Test ===\n")
    data = get_vscode_context()
    print(f"Raw data: {data}\n")
    print(f"Formatted:\n{format_vscode_context(data)}")

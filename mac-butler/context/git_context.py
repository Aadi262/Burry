#!/usr/bin/env python3
"""
git_context.py — Scans ~/Developer for git repos and returns structured commit data.

For each subdirectory in ~/Developer that contains a .git folder, runs:
    git log --oneline -5 --since="3 days ago"

Returns a structured dict for the context engine to format intelligently.
"""

import os
import subprocess
from pathlib import Path

from butler_config import DEVELOPER_PATH


# Root directory to scan for git repos
DEVELOPER_DIR = Path(os.path.expanduser(DEVELOPER_PATH))


def get_git_context() -> dict:
    """
    Scan all subdirectories of ~/Developer for git repos.
    For each repo, grab the last 5 commits from the past 3 days.

    Returns:
        {
            "repos": [
                {"name": "repo-name", "commits": ["fixed login bug", "added rate limiter"]},
                ...
            ],
            "has_activity": True/False
        }
    """
    result = {"repos": [], "has_activity": False}

    if not DEVELOPER_DIR.exists():
        return result

    # Walk only immediate subdirectories (not deeply nested)
    for entry in sorted(DEVELOPER_DIR.iterdir()):
        if not entry.is_dir():
            continue
        git_dir = entry / ".git"
        if not git_dir.exists():
            continue

        repo_name = entry.name
        try:
            # Run git log in the repo directory
            output = subprocess.run(
                ["git", "log", "--oneline", "-5", "--since=3 days ago"],
                cwd=str(entry),
                capture_output=True,
                text=True,
                timeout=10,
            )
            log_lines = output.stdout.strip()
            if log_lines:
                # Extract just the commit messages (skip the hash)
                commits = [
                    line.split(" ", 1)[1]
                    for line in log_lines.splitlines()
                    if " " in line
                ]
                if commits:
                    result["repos"].append({
                        "name": repo_name,
                        "commits": commits,
                    })
                    result["has_activity"] = True
        except subprocess.TimeoutExpired:
            pass  # Skip slow repos silently
        except Exception:
            pass  # Don't crash if one repo fails

    return result


def format_git_context(data: dict) -> str:
    """Format git data as a human-readable string (for backward compat)."""
    if not data["has_activity"]:
        return "(No recent git activity in ~/Developer.)"

    lines = []
    for repo in data["repos"]:
        commits_str = ", ".join(repo["commits"][:3])  # Top 3 commits
        lines.append(f"  {repo['name']}: {commits_str}")
    return "Recent work:\n" + "\n".join(lines)


if __name__ == "__main__":
    # Standalone test: run this file directly to see git context output
    print("=== Git Context Test ===\n")
    data = get_git_context()
    print(f"Raw data: {data}\n")
    print(f"Formatted:\n{format_git_context(data)}")

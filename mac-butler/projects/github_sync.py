#!/usr/bin/env python3
"""GitHub sync for Butler project metadata."""

from __future__ import annotations

import base64
import json
from typing import Any

import requests

try:
    from .project_store import load_projects, update_project
except ImportError:
    from project_store import load_projects, update_project

API_ROOT = "https://api.github.com"
TIMEOUT = 15


def _warn(message: str) -> None:
    print(f"[github_sync] {message}")


def _get_json(url: str) -> Any | None:
    try:
        response = requests.get(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "butler-project-sync",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        _warn(f"request failed for {url}: {exc}")
        return None

    if response.status_code == 404:
        _warn(f"repo not found for {url}")
        return None
    if response.status_code == 403 and "rate limit" in response.text.lower():
        _warn("rate limited by GitHub API")
        return None
    if response.status_code >= 400:
        _warn(f"GitHub returned {response.status_code} for {url}")
        return None

    try:
        return response.json()
    except ValueError:
        _warn(f"invalid JSON from {url}")
        return None


def sync_project(project: dict) -> dict:
    repo = project.get("repo")
    if not repo:
        return project

    commits = _get_json(f"{API_ROOT}/repos/{repo}/commits?per_page=1")
    issues = _get_json(f"{API_ROOT}/repos/{repo}/issues?state=open&per_page=100")
    readme = _get_json(f"{API_ROOT}/repos/{repo}/readme")

    fields: dict[str, Any] = {}

    if isinstance(commits, list) and commits:
        commit = commits[0]
        commit_date = (
            commit.get("commit", {})
            .get("author", {})
            .get("date")
        )
        if commit_date:
            fields["last_commit"] = commit_date

    if isinstance(issues, list):
        fields["open_issues"] = sum(
            1 for item in issues if "pull_request" not in item
        )

    if isinstance(readme, dict) and readme.get("content"):
        try:
            decoded = base64.b64decode(readme["content"]).decode("utf-8", errors="ignore")
            fields["readme_excerpt"] = " ".join(decoded.split())[:200]
        except Exception:
            _warn(f"could not decode README for {repo}")

    if fields:
        updated = update_project(project.get("name", ""), **fields)
        return updated or project
    return project


def sync_all() -> list[dict]:
    updated_projects: list[dict] = []
    for project in load_projects():
        updated = sync_project(project)
        updated_projects.append(updated)
        print(
            f"{updated.get('name', 'unknown')}: "
            f"{updated.get('last_commit') or 'unknown'} | "
            f"issues {updated.get('open_issues', 0)}"
        )
    return updated_projects


def get_github_context() -> str:
    items = []
    for project in load_projects():
        repo = project.get("repo")
        if not repo:
            continue
        commit = str(project.get("last_commit") or "unknown")[:10]
        issues = int(project.get("open_issues", 0))
        items.append(f"{project.get('name')}: {commit}/{issues}i")
    if not items:
        return ""
    text = "[GITHUB]\n" + " | ".join(items)
    return text[:350]


if __name__ == "__main__":
    sync_all()

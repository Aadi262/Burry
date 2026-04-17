#!/usr/bin/env python3
"""GitHub sync for Butler project metadata."""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import quote

import requests
from butler_secrets.loader import get_secret

try:
    from .project_store import load_projects, update_project
except ImportError:
    from project_store import load_projects, update_project

API_ROOT = "https://api.github.com"
TIMEOUT = 15
GITHUB_TOKEN_ENV = "GITHUB_PERSONAL_ACCESS_TOKEN"


def _warn(message: str) -> None:
    print(f"[github_sync] {message}")


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "butler-project-sync",
    }
    token = get_secret(GITHUB_TOKEN_ENV, default="")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_json(url: str) -> Any | None:
    try:
        response = requests.get(
            url,
            headers=_github_headers(),
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


def fetch_repo_status(repo: str, *, item_limit: int = 5) -> dict[str, Any] | None:
    cleaned_repo = str(repo or "").strip().strip("/")
    if not cleaned_repo or "/" not in cleaned_repo:
        return None

    repo_data = _get_json(f"{API_ROOT}/repos/{cleaned_repo}")
    if not isinstance(repo_data, dict):
        return None

    safe_limit = max(1, min(int(item_limit or 5), 10))
    issue_query = quote(f"repo:{cleaned_repo} type:issue state:open")
    pr_query = quote(f"repo:{cleaned_repo} type:pr state:open")
    issue_search = _get_json(f"{API_ROOT}/search/issues?q={issue_query}&per_page={safe_limit}")
    pr_search = _get_json(f"{API_ROOT}/search/issues?q={pr_query}&per_page={safe_limit}")
    commits = _get_json(f"{API_ROOT}/repos/{cleaned_repo}/commits?per_page=1")
    workflow_runs = _get_json(f"{API_ROOT}/repos/{cleaned_repo}/actions/runs?per_page=1")

    latest_commit = commits[0] if isinstance(commits, list) and commits else {}
    latest_issue_items = issue_search.get("items", []) if isinstance(issue_search, dict) else []
    latest_pr_items = pr_search.get("items", []) if isinstance(pr_search, dict) else []
    latest_run = (
        (workflow_runs.get("workflow_runs") or [])[0]
        if isinstance(workflow_runs, dict) and workflow_runs.get("workflow_runs")
        else {}
    )

    return {
        "repo": cleaned_repo,
        "full_name": str(repo_data.get("full_name", "")).strip() or cleaned_repo,
        "html_url": str(repo_data.get("html_url", "")).strip(),
        "default_branch": str(repo_data.get("default_branch", "")).strip(),
        "private": bool(repo_data.get("private")),
        "description": str(repo_data.get("description", "") or "").strip(),
        "stars": int(repo_data.get("stargazers_count", 0) or 0),
        "forks": int(repo_data.get("forks_count", 0) or 0),
        "language": str(repo_data.get("language", "") or "").strip(),
        "open_issues": int(issue_search.get("total_count", 0) or 0) if isinstance(issue_search, dict) else None,
        "open_pull_requests": int(pr_search.get("total_count", 0) or 0) if isinstance(pr_search, dict) else None,
        "pushed_at": str(repo_data.get("pushed_at", "") or "").strip(),
        "updated_at": str(repo_data.get("updated_at", "") or "").strip(),
        "latest_commit": {
            "sha": str(latest_commit.get("sha", "") or "").strip(),
            "message": str((latest_commit.get("commit") or {}).get("message", "") or "").strip(),
            "date": str((((latest_commit.get("commit") or {}).get("author") or {}).get("date", "")) or "").strip(),
            "url": str(latest_commit.get("html_url", "") or "").strip(),
        },
        "workflow": {
            "status": str(latest_run.get("status", "") or "").strip(),
            "conclusion": str(latest_run.get("conclusion", "") or "").strip(),
            "name": str(latest_run.get("name", "") or "").strip(),
            "updated_at": str(latest_run.get("updated_at", "") or "").strip(),
            "url": str(latest_run.get("html_url", "") or "").strip(),
        },
        "issues": [
            {
                "title": str(item.get("title", "") or "").strip(),
                "number": item.get("number"),
                "url": str(item.get("html_url", "") or "").strip(),
            }
            for item in latest_issue_items[:safe_limit]
            if isinstance(item, dict)
        ],
        "pull_requests": [
            {
                "title": str(item.get("title", "") or "").strip(),
                "number": item.get("number"),
                "url": str(item.get("html_url", "") or "").strip(),
            }
            for item in latest_pr_items[:safe_limit]
            if isinstance(item, dict)
        ],
        "token_configured": bool(get_secret(GITHUB_TOKEN_ENV, default="")),
    }


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

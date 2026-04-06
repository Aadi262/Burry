#!/usr/bin/env python3
"""Persistent project registry for Butler."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PROJECTS_PATH = Path(__file__).resolve().parent / "projects.json"
PROJECT_BLURB_MODEL = "gemma4:e4b"


def _load_raw() -> list[dict]:
    if not PROJECTS_PATH.exists():
        return []
    try:
        return json.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(projects: list[dict]) -> None:
    PROJECTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROJECTS_PATH.write_text(json.dumps(projects, indent=2), encoding="utf-8")


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def _candidate_names(project: dict) -> list[str]:
    names = [project.get("name", "")]
    names.extend(project.get("aliases", []) or [])
    return [name for name in names if name]


def _match_project(projects: list[dict], name: str) -> tuple[int, dict] | tuple[None, None]:
    if not name:
        return (None, None)

    query = str(name).strip()
    normalized_query = _normalize(query)

    for index, project in enumerate(projects):
        for candidate in _candidate_names(project):
            if candidate.lower() == query.lower():
                return (index, project)

    for index, project in enumerate(projects):
        for candidate in _candidate_names(project):
            normalized_candidate = _normalize(candidate)
            if normalized_query and (
                normalized_query in normalized_candidate
                or normalized_candidate in normalized_query
            ):
                return (index, project)

    return (None, None)


def _project_root(project: dict) -> Path:
    return Path(os.path.expanduser(str(project.get("path", "") or ""))).resolve()


def _status_file_rank(path: Path) -> int:
    name = path.name.lower()
    if any(token in name for token in ("priority", "progress", "feature_status", "roadmap", "status")):
        return 0
    if name == "plan.md":
        return 1
    if "memory" in name:
        return 2
    if name == "readme.md":
        return 3
    return 4


def _resolve_status_files(project: dict) -> list[Path]:
    root = _project_root(project)
    resolved = []
    for rel_path in project.get("status_files", []) or []:
        resolved.append((root / rel_path).resolve())
    return sorted(resolved, key=lambda path: (_status_file_rank(path), str(path).lower()))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _parse_markdown_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    tables: list[tuple[list[str], list[list[str]]]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if "|" not in line:
            index += 1
            continue
        if index + 1 >= len(lines):
            break
        separator = lines[index + 1].strip()
        if "|" not in separator or not re.fullmatch(r"[\|\s:\-]+", separator):
            index += 1
            continue

        header = [cell.strip() for cell in line.strip("|").split("|")]
        rows: list[list[str]] = []
        cursor = index + 2
        while cursor < len(lines):
            row_line = lines[cursor].strip()
            if "|" not in row_line:
                break
            row = [cell.strip() for cell in row_line.strip("|").split("|")]
            if len(row) == len(header):
                rows.append(row)
            cursor += 1

        if rows:
            tables.append((header, rows))
        index = cursor
    return tables


def _clean_text(value: str, limit: int = 120) -> str:
    text = str(value).strip()
    text = text.replace("`", "")
    text = text.replace("**", "")
    text = text.replace("__", "")
    text = text.replace("—", "-")
    text = text.replace("–", "-")
    text = text.replace("→", " to ")
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"^[-*+]\s+\[[ xX]\]\s*", "", text)
    text = re.sub(r"^[-*+]\s*", "", text)
    text = re.sub(r"^\d+\.\s*", "", text)
    text = " ".join(text.split())
    text = text.strip(" -:;,.")
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text


def _normalize_blurb_text(text: str, max_words: int = 42) -> str:
    cleaned = " ".join(str(text or "").strip().strip('"').split())
    if not cleaned:
        return ""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    if not sentences:
        return ""
    if len(sentences) == 1 and sentences[0][-1] not in ".!?":
        sentences[0] = sentences[0].rstrip(",;:-") + "."
    candidate = " ".join(sentences[:2])
    words = candidate.split()
    if len(words) > max_words:
        candidate = " ".join(words[:max_words]).rstrip(",;:-")
        if candidate and candidate[-1] not in ".!?":
            candidate += "."
    return candidate


def _project_blurb_fallback(project: dict) -> str:
    name = _clean_text(project.get("name", ""), limit=80) or "This project"
    description = _clean_text(
        project.get("description", "") or project.get("deploy_target", "") or "is still in progress",
        limit=120,
    )
    next_task = _clean_text((project.get("next_tasks") or ["review the current status"])[0], limit=120)
    blocker = _clean_text((project.get("blockers") or [""])[0], limit=120)
    first = f"{name} is {description}."
    second = f"Next up is {next_task}."
    if blocker:
        second = f"Next up is {next_task}, while {blocker} still needs attention."
    return _normalize_blurb_text(f"{first} {second}")


def _project_blurb_prompt(project: dict) -> str:
    name = _clean_text(project.get("name", ""), limit=80) or "Unknown project"
    description = _clean_text(project.get("description", ""), limit=180) or "No description provided."
    blockers = [_clean_text(item, limit=140) for item in list(project.get("blockers") or []) if _clean_text(item, limit=140)]
    next_tasks = [_clean_text(item, limit=140) for item in list(project.get("next_tasks") or []) if _clean_text(item, limit=140)]
    blocker_lines = "\n".join(f"- {item}" for item in blockers[:3]) or "- No active blockers recorded."
    task_lines = "\n".join(f"- {item}" for item in next_tasks[:3]) or "- No next tasks recorded."
    return f"""You are summarizing a software project for Burry's HUD.
Write exactly 2 short sentences, total under 42 words.
Sentence 1 should explain what the project is.
Sentence 2 should explain what needs to happen next.
Do not use bullets or a greeting.

Project: {name}
Description: {description}
Blockers:
{blocker_lines}
Next tasks:
{task_lines}
"""


def _generate_project_blurb(project: dict) -> str:
    try:
        from brain.ollama_client import _call

        raw = _call(
            _project_blurb_prompt(project),
            PROJECT_BLURB_MODEL,
            temperature=0.2,
            max_tokens=120,
        )
    except Exception:
        raw = ""
    return _normalize_blurb_text(raw) or _project_blurb_fallback(project)


def _merge_unique(items: list[str], limit: int = 4) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = _clean_text(item)
        if len(cleaned) < 4:
            continue
        key = _normalize(cleaned)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(cleaned)
        if len(merged) >= limit:
            break
    return merged


def _heading_parts(line: str) -> tuple[int, str] | None:
    match = re.match(r"^(#{2,6})\s+(.*)$", line.strip())
    if not match:
        return None
    return (len(match.group(1)), _clean_text(match.group(2), limit=200))


def _extract_section(text: str, titles: list[str]) -> str:
    target_titles = {_normalize(title) for title in titles}
    lines = text.splitlines()
    start = None
    start_level = None

    for index, line in enumerate(lines):
        heading = _heading_parts(line)
        if not heading:
            continue
        level, title = heading
        if _normalize(title) in target_titles:
            start = index + 1
            start_level = level
            break

    if start is None or start_level is None:
        return ""

    collected: list[str] = []
    for line in lines[start:]:
        heading = _heading_parts(line)
        if heading and heading[0] <= start_level:
            break
        collected.append(line)
    return "\n".join(collected).strip()


def _looks_like_file_path(text: str) -> bool:
    lowered = text.lower()
    if "/" in text or "\\" in text:
        return True
    return bool(re.search(r"\.(ts|tsx|js|jsx|py|md|json|ya?ml|toml|env)\b", lowered))


def _extract_list_items(section_text: str, max_items: int = 4) -> list[str]:
    items: list[str] = []
    lines = section_text.splitlines()
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if not stripped or stripped.startswith("```"):
            continue
        if indent <= 1 and re.match(r"^\d+\.\s+", stripped):
            has_trailing_colon = stripped.rstrip().endswith(":")
            cleaned = _clean_text(stripped)
            if has_trailing_colon:
                nested: list[str] = []
                for nested_line in lines[index + 1:]:
                    nested_indent = len(nested_line) - len(nested_line.lstrip(" "))
                    nested_stripped = nested_line.strip()
                    if nested_indent <= indent:
                        break
                    if re.match(r"^[-*+]\s+", nested_stripped):
                        nested.append(_clean_text(nested_stripped, limit=60))
                if nested:
                    cleaned = f"{cleaned.rstrip(':')} {'; '.join(nested[:3])}"
            items.append(cleaned)
            continue
        if indent <= 1 and re.match(r"^[-*+]\s+\[[ xX]\]\s+", stripped):
            cleaned = _clean_text(stripped)
            if not _looks_like_file_path(cleaned):
                items.append(cleaned)
            continue
        if indent <= 1 and re.match(r"^[-*+]\s+", stripped):
            cleaned = _clean_text(stripped)
            if _looks_like_file_path(cleaned):
                continue
            if cleaned.lower().startswith(("tasks", "files to create", "visit", "then add to", "status")):
                continue
            if len(cleaned.split()) >= 3:
                items.append(cleaned)
        if len(items) >= max_items:
            break
    return _merge_unique(items, limit=max_items)


def _first_meaningful_line(section_text: str) -> str | None:
    for raw_line in section_text.splitlines():
        cleaned = _clean_text(raw_line)
        if not cleaned:
            continue
        if cleaned.lower().startswith(("tasks", "files to create", "status")):
            continue
        if _looks_like_file_path(cleaned):
            continue
        return cleaned
    return None


def _extract_following_headings(text: str, section_title: str, limit: int = 3) -> list[str]:
    lines = text.splitlines()
    target = _normalize(section_title)
    start = None
    start_level = None
    for index, line in enumerate(lines):
        heading = _heading_parts(line)
        if heading and _normalize(heading[1]) == target:
            start = index + 1
            start_level = heading[0]
            break
    if start is None or start_level is None:
        return []

    items: list[str] = []
    for line in lines[start:]:
        heading = _heading_parts(line)
        if heading and heading[0] <= start_level:
            break
        if heading and heading[0] == start_level + 1:
            cleaned = _clean_text(heading[1])
            if cleaned:
                items.append(cleaned)
        if len(items) >= limit:
            break
    return _merge_unique(items, limit=limit)


def _extract_pending_phase_tasks(text: str, limit: int = 4) -> list[str]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        heading = _heading_parts(line)
        if not heading:
            continue
        title = heading[1].lower()
        if "pending" not in title and "blocked" not in title:
            continue
        level = heading[0]
        section_lines: list[str] = []
        for line_after in lines[index + 1:]:
            next_heading = _heading_parts(line_after)
            if next_heading and next_heading[0] <= level:
                break
            section_lines.append(line_after)
        items = _extract_list_items("\n".join(section_lines), max_items=limit)
        if items:
            return items
    return []


def _score_status_cell(cell: str) -> int | None:
    cleaned = " ".join(str(cell).upper().split())
    if not cleaned:
        return None
    if "NOT STARTED" in cleaned:
        return 0
    if "DONE" in cleaned and "PARTIAL" in cleaned:
        return 70
    if "DONE" in cleaned and "BASIC" in cleaned:
        return 85
    if "IN PROGRESS" in cleaned:
        return 65
    if "FREE KEY" in cleaned or "FREE_KEY" in cleaned:
        return 85
    if "PAID API" in cleaned or "PAID_API" in cleaned:
        return 78
    if "SEEDED" in cleaned:
        return 80
    if "SCHEMA" in cleaned:
        return 35
    if "PARTIAL" in cleaned:
        return 60
    if "MISSING" in cleaned:
        return 0
    if "MOCK" in cleaned:
        return 15
    if "PLANNED" in cleaned:
        return 0
    if "LIVE" in cleaned:
        return 100
    if "COMPLETE" in cleaned or "COMPLETED" in cleaned or "DONE" in cleaned:
        return 100
    return None


def _confidence_adjustment(path: Path) -> float:
    name = path.name.lower()
    if any(token in name for token in ("feature_status", "progress", "roadmap", "priority", "status")):
        return 0.08
    if name == "plan.md":
        return -0.08
    if name == "readme.md":
        return -0.12
    return 0.0


def _table_progress_candidate(path: Path, text: str) -> dict[str, Any] | None:
    status_scores: list[int] = []
    percent_values: list[int] = []
    for header, rows in _parse_markdown_tables(text):
        header_lower = [cell.lower() for cell in header]
        header_blob = " | ".join(header_lower)

        if "status" in header_blob:
            if "icon" in header_blob and "meaning" in header_blob:
                continue
            status_index = next(
                (i for i, value in enumerate(header_lower) if "status" in value),
                None,
            )
            if status_index is not None:
                for row in rows:
                    if status_index >= len(row):
                        continue
                    score = _score_status_cell(row[status_index])
                    if score is not None:
                        status_scores.append(score)

        percent_columns = [
            i
            for i, value in enumerate(header_lower)
            if "%" in value or "done" in value or "progress" in value
        ]
        if percent_columns:
            values = []
            for row in rows:
                for column in percent_columns:
                    if column >= len(row):
                        continue
                    match = re.search(r"\b(\d{1,3})%", row[column])
                    if match:
                        percent_values.append(int(match.group(1)))
                        break

    adjustment = _confidence_adjustment(path)
    if len(percent_values) >= 2:
        return {
            "score": round(sum(percent_values) / len(percent_values)),
            "confidence": round(min(1.0, 0.95 + adjustment), 2),
            "basis": f"{path.name} progress tables",
            "mtime": path.stat().st_mtime,
        }
    if len(status_scores) >= 2:
        return {
            "score": round(sum(status_scores) / len(status_scores)),
            "confidence": round(max(0.1, min(1.0, 0.84 + adjustment)), 2),
            "basis": f"{path.name} status tables",
            "mtime": path.stat().st_mtime,
        }
    return None


def _status_name_and_notes_indexes(header_lower: list[str], row: list[str], status_index: int) -> tuple[int | None, int | None]:
    name_index = None
    for index, value in enumerate(header_lower):
        if index != status_index and "name" in value:
            name_index = index
            break
    if name_index is None:
        for index, value in enumerate(header_lower):
            if index == status_index:
                continue
            if any(token in value for token in ("feature", "component", "item", "risk", "stage", "phase")):
                name_index = index
                break
    for index, value in enumerate(header_lower):
        if name_index is not None:
            break
        if index != status_index:
            name_index = index
            break

    notes_index = next(
        (index for index, value in enumerate(header_lower) if any(token in value for token in ("notes", "meaning", "mitigation"))),
        None,
    )
    if name_index is not None and name_index >= len(row):
        name_index = None
    if notes_index is not None and notes_index >= len(row):
        notes_index = None
    return name_index, notes_index


def _status_severity(status: str) -> int | None:
    cleaned = " ".join(str(status).upper().split())
    if "BLOCKED" in cleaned:
        return 0
    if "NOT STARTED" in cleaned or "MISSING" in cleaned:
        return 1
    if "PAID API" in cleaned or "PAID_API" in cleaned:
        return 2
    if "FREE KEY" in cleaned or "FREE_KEY" in cleaned:
        return 3
    if "PARTIAL" in cleaned:
        return 4
    if "MOCK" in cleaned or "PLANNED" in cleaned:
        return 5
    return None


def _status_row_to_blocker(name: str, status: str, notes: str = "") -> str | None:
    cleaned_status = " ".join(str(status).upper().split())
    cleaned_name = _clean_text(name, limit=90)
    cleaned_notes = _clean_text(notes, limit=110)
    if not cleaned_name:
        return None

    if "BLOCKED" in cleaned_status:
        return f"{cleaned_name} is blocked"
    if "NOT STARTED" in cleaned_status:
        return f"{cleaned_name} is not started"
    if "MISSING" in cleaned_status:
        return f"{cleaned_name} is missing"
    if "PAID API" in cleaned_status or "PAID_API" in cleaned_status:
        return f"{cleaned_name} needs OAuth or paid API setup"
    if "FREE KEY" in cleaned_status or "FREE_KEY" in cleaned_status:
        return f"{cleaned_name} needs local Ollama or a free API key"
    if "PARTIAL" in cleaned_status:
        if cleaned_notes and ("pending" in cleaned_notes.lower() or "still" in cleaned_notes.lower()):
            return cleaned_notes
        return f"{cleaned_name} is still partial"
    if "MOCK" in cleaned_status:
        return f"{cleaned_name} is still mock"
    if "PLANNED" in cleaned_status:
        return f"{cleaned_name} is only planned"
    return None


def _extract_status_row_blockers(text: str, limit: int = 3) -> list[str]:
    candidates: list[tuple[int, str]] = []
    for header, rows in _parse_markdown_tables(text):
        header_lower = [cell.lower() for cell in header]
        header_blob = " | ".join(header_lower)
        if "status" not in header_blob or ("icon" in header_blob and "meaning" in header_blob):
            continue
        status_index = next((i for i, value in enumerate(header_lower) if "status" in value), None)
        if status_index is None:
            continue
        for row in rows:
            name_index, notes_index = _status_name_and_notes_indexes(header_lower, row, status_index)
            if name_index is None:
                continue
            status = row[status_index]
            severity = _status_severity(status)
            if severity is None:
                continue
            notes = row[notes_index] if notes_index is not None else ""
            blocker = _status_row_to_blocker(row[name_index], status, notes)
            if blocker:
                candidates.append((severity, blocker))
    candidates.sort(key=lambda item: item[0])
    return _merge_unique([item[1] for item in candidates], limit=limit)


def _extract_risk_table_blockers(section_text: str, limit: int = 3) -> list[str]:
    blockers: list[str] = []
    for header, rows in _parse_markdown_tables(section_text):
        header_lower = [cell.lower() for cell in header]
        if "risk" not in " | ".join(header_lower) or "severity" not in " | ".join(header_lower):
            continue
        risk_index = next((i for i, value in enumerate(header_lower) if "risk" in value), None)
        severity_index = next((i for i, value in enumerate(header_lower) if "severity" in value), None)
        if risk_index is None or severity_index is None:
            continue
        for row in rows:
            if risk_index >= len(row) or severity_index >= len(row):
                continue
            severity = row[severity_index].strip().lower()
            if severity not in {"high", "medium"}:
                continue
            blockers.append(row[risk_index])
    return _merge_unique(blockers, limit=limit)


def _extract_sentence_blockers(text: str, limit: int = 3) -> list[str]:
    blockers: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("-"):
            continue
        cleaned = _clean_text(stripped)
        lowered = cleaned.lower()
        if any(
            phrase in lowered
            for phrase in (
                "still ",
                "not built",
                "not started",
                "remaining work",
                "unreliable",
                "blocked",
                "requires",
            )
        ):
            blockers.append(cleaned)
    return _merge_unique(blockers, limit=limit)


def _explicit_progress_candidate(path: Path, text: str) -> dict[str, Any] | None:
    total_match = re.search(
        r"\btotal:\s*.*?\((\d{1,3})%\)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if total_match:
        return {
            "score": int(total_match.group(1)),
            "confidence": round(min(1.0, 1.0 + _confidence_adjustment(path)), 2),
            "basis": f"{path.name} explicit total",
            "mtime": path.stat().st_mtime,
        }

    ratio_match = re.search(
        r"\b(\d{1,3})\s+of\s+(\d{1,3})\s+"
        r"(?:phases|steps|layers|milestones|items|features|components)"
        r"\s+(?:complete|completed|done)\b",
        text,
        re.IGNORECASE,
    )
    if ratio_match:
        done = int(ratio_match.group(1))
        total = max(1, int(ratio_match.group(2)))
        return {
            "score": round((done / total) * 100),
            "confidence": round(min(1.0, 0.98 + _confidence_adjustment(path)), 2),
            "basis": f"{path.name} completion ratio",
            "mtime": path.stat().st_mtime,
        }

    line_match = re.search(
        r"\b(\d{1,3})%\s+(?:done|complete|completed)\b",
        text,
        re.IGNORECASE,
    )
    if line_match:
        return {
            "score": int(line_match.group(1)),
            "confidence": round(max(0.1, min(1.0, 0.92 + _confidence_adjustment(path))), 2),
            "basis": f"{path.name} progress line",
            "mtime": path.stat().st_mtime,
        }
    return None


def _phase_progress_candidate(path: Path, text: str) -> dict[str, Any] | None:
    current_match = re.search(r"\bPhase\s+(\d+)\s+in\s+progress\b", text, re.IGNORECASE)
    if not current_match:
        return None

    current = int(current_match.group(1))
    phase_numbers = [int(value) for value in re.findall(r"\bPhase\s+(\d+)\b", text, re.IGNORECASE)]
    total = max(phase_numbers) if phase_numbers else current
    if total <= 0:
        return None

    return {
        "score": round(((current - 0.5) / total) * 100),
        "confidence": round(max(0.1, min(1.0, 0.66 + _confidence_adjustment(path))), 2),
        "basis": f"{path.name} phase {current} in progress",
        "mtime": path.stat().st_mtime,
    }


def _completed_bullets_score(text: str) -> int:
    match = re.search(
        r"##\s+What Is Done\s*(.*?)(?:\n##\s+|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return 0
    bullets = [
        line for line in match.group(1).splitlines()
        if line.strip().startswith("- ")
    ]
    return min(30, len(bullets) * 2)


def _local_git_last_commit(root: Path) -> str | None:
    if not root.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%cI"],
            capture_output=True,
            text=True,
            timeout=4,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _has_local_git(root: Path) -> bool:
    return _local_git_last_commit(root) is not None


def _local_git_branch(root: Path) -> str | None:
    if not root.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=4,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def _local_git_dirty(root: Path) -> bool | None:
    if not root.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=4,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def _project_memory_state(project_name: str) -> dict[str, Any]:
    try:
        from memory.store import _load as _load_memory

        return dict(_load_memory().get("project_state", {}).get(project_name, {}) or {})
    except Exception:
        return {}


def _local_live_status(url: str) -> dict[str, Any]:
    if not url:
        return {"live": False, "status": "unknown", "checked": False, "reachable": None, "status_code": None}
    try:
        from urllib.request import Request as _Request, urlopen as _urlopen
        request = _Request(url, headers={"User-Agent": "Burry/1.0"})
        with _urlopen(request, timeout=1.5) as response:
            ok = response.status == 200
            return {"live": ok, "status": "ok", "checked": True, "reachable": ok, "status_code": response.status}
    except Exception:
        return {"live": False, "status": "unknown", "checked": True, "reachable": False, "status_code": None}


def _derive_health(project: dict, root: Path) -> dict[str, Any]:
    memory_state = _project_memory_state(project.get("name", ""))
    local_git = _has_local_git(root)
    git_branch = _local_git_branch(root) if local_git else None
    git_dirty = _local_git_dirty(root) if local_git else None
    live_state = _local_live_status(project.get("live_url", ""))

    checks: list[bool] = [root.exists()]
    if local_git:
        checks.append(True)
    if live_state.get("checked"):
        checks.append(bool(live_state.get("reachable")))
    if memory_state.get("last_test_status"):
        checks.append(memory_state.get("last_test_status") == "ok")

    health_total = len(checks)
    health_ok = sum(1 for item in checks if item)
    last_error = (
        memory_state.get("last_error")
        or project.get("last_error")
        or ""
    )

    if not root.exists():
        health_status = "offline"
    elif last_error or (memory_state.get("last_test_status") == "error"):
        health_status = "degraded"
    elif live_state.get("checked") and not live_state.get("reachable"):
        health_status = "degraded"
    elif health_total and health_ok == health_total:
        health_status = "healthy"
    else:
        health_status = "degraded"

    return {
        "health_status": health_status,
        "health_signals_total": health_total,
        "health_signals_ok": health_ok,
        "git_branch": git_branch,
        "git_dirty": git_dirty,
        "live_checked": bool(live_state.get("checked")),
        "live_status_code": live_state.get("status_code"),
        "live_reachable": live_state.get("reachable"),
        "live": bool(live_state.get("reachable")) if live_state.get("checked") else bool(project.get("live")),
        "memory_last_action": memory_state.get("last_action", ""),
        "memory_last_status": memory_state.get("last_status", ""),
        "last_test_status": memory_state.get("last_test_status", ""),
        "last_test_command": memory_state.get("last_test_command", ""),
        "last_verified_at": memory_state.get("last_verified_at", ""),
        "memory_last_error": memory_state.get("last_error", ""),
        "last_error": last_error or None,
    }


def _structural_candidate(project: dict, root: Path, status_files: list[Path], texts: list[str]) -> dict[str, Any]:
    existing_files = sum(1 for path in status_files if path.exists())
    blockers = len(project.get("blockers", []) or [])
    score = 0
    if root.exists():
        score += 20
    if status_files:
        score += round((existing_files / len(status_files)) * 25)
    if _has_local_git(root):
        score += 15
    score += max(_completed_bullets_score(text) for text in texts) if texts else 0
    score -= min(12, blockers * 4)
    score = max(8, min(80, score))
    return {
        "score": score,
        "confidence": 0.35,
        "basis": "local file heuristic",
        "mtime": max((path.stat().st_mtime for path in status_files if path.exists()), default=0),
    }


def _derive_completion(project: dict) -> dict[str, Any]:
    root = _project_root(project)
    status_files = _resolve_status_files(project)
    texts = [_read_text(path) for path in status_files if path.exists()]
    candidates: list[dict[str, Any]] = []

    for path in status_files:
        if not path.exists():
            continue
        text = _read_text(path)
        for candidate in (
            _explicit_progress_candidate(path, text),
            _table_progress_candidate(path, text),
            _phase_progress_candidate(path, text),
        ):
            if candidate:
                candidates.append(candidate)

    candidates.append(_structural_candidate(project, root, status_files, texts))

    candidates.sort(
        key=lambda item: (
            float(item.get("confidence", 0)),
            float(item.get("mtime", 0)),
        ),
        reverse=True,
    )
    best = candidates[0]

    return {
        "completion": int(best["score"]),
        "completion_source": "status_files" if best["confidence"] >= 0.66 else "heuristic",
        "completion_basis": best["basis"],
        "completion_confidence": round(float(best["confidence"]), 2),
        "status_files_total": len(status_files),
        "status_files_found": sum(1 for path in status_files if path.exists()),
    }


def _extract_next_tasks_from_text(path: Path, text: str) -> list[str]:
    tasks: list[str] = []

    for section_title in (
        "What Should Happen Next",
        "What to do RIGHT NOW (in order of impact)",
        "Next Immediate Action",
        "Next Actions",
        "Next Up",
    ):
        section = _extract_section(text, [section_title])
        if not section:
            continue
        heading_task = _first_meaningful_line(section)
        if heading_task and heading_task.lower().startswith("phase "):
            tasks.append(heading_task)
        tasks.extend(_extract_list_items(section, max_items=4))
        if tasks:
            break

    if not tasks:
        current_task = _extract_section(text, ["Current Task"])
        if current_task:
            first = _first_meaningful_line(current_task)
            if first:
                tasks.append(first)

    if not tasks:
        tasks.extend(_extract_following_headings(text, "Next 3 Phases", limit=3))

    if not tasks:
        after_phase = _extract_section(text, ["After This Phase"])
        if after_phase:
            tasks.extend(_extract_list_items(after_phase, max_items=3))

    if not tasks:
        tasks.extend(_extract_pending_phase_tasks(text, limit=4))

    return _merge_unique(tasks, limit=4)


def _extract_blockers_from_text(path: Path, text: str) -> list[str]:
    blockers: list[str] = []

    blockers.extend(_extract_status_row_blockers(text, limit=4))

    risks = _extract_section(text, ["Known Risks"])
    if risks:
        blockers.extend(_extract_risk_table_blockers(risks, limit=3))
        blockers.extend(_extract_list_items(risks, max_items=2))

    for section_title in ("Known Gaps", "Open Questions"):
        section = _extract_section(text, [section_title])
        if section:
            blockers.extend(_extract_list_items(section, max_items=4))

    blockers.extend(_extract_sentence_blockers(text, limit=2))

    for raw_line in text.splitlines():
        cleaned = _clean_text(raw_line)
        lowered = cleaned.lower()
        if lowered.startswith("status:") and any(word in lowered for word in ("blocked", "pending")):
            blockers.append(cleaned)

    return _merge_unique(blockers, limit=4)


def _derive_runtime_lists(project: dict) -> dict[str, Any]:
    derived_tasks: list[str] = []
    derived_blockers: list[str] = []
    task_basis = ""
    blocker_basis = ""

    for path in _resolve_status_files(project):
        if not path.exists():
            continue
        text = _read_text(path)
        if not task_basis:
            tasks = _extract_next_tasks_from_text(path, text)
            if tasks:
                derived_tasks = tasks
                task_basis = path.name
        if not blocker_basis:
            blockers = _extract_blockers_from_text(path, text)
            if blockers:
                derived_blockers = blockers
                blocker_basis = path.name
        if task_basis and blocker_basis:
            break

    manual_tasks = list(project.get("next_tasks", []) or [])
    manual_blockers = list(project.get("blockers", []) or [])

    return {
        "manual_next_tasks": manual_tasks,
        "manual_blockers": manual_blockers,
        "derived_next_tasks": derived_tasks,
        "derived_blockers": derived_blockers,
        "next_tasks": _merge_unique(derived_tasks + manual_tasks, limit=6),
        "blockers": _merge_unique(derived_blockers + manual_blockers, limit=6),
        "next_tasks_basis": task_basis or "registry",
        "blockers_basis": blocker_basis or "registry",
    }


def _enrich_project(project: dict) -> dict:
    enriched = dict(project)
    root = _project_root(project)
    derived = _derive_completion(project)
    enriched.update(derived)
    enriched.update(_derive_runtime_lists(project))
    enriched["path_exists"] = root.exists()

    local_last_commit = _local_git_last_commit(root)
    enriched["local_git"] = local_last_commit is not None
    enriched["local_last_commit"] = local_last_commit
    enriched["blurb"] = str(enriched.get("blurb", "") or "").strip()
    if local_last_commit and not enriched.get("last_commit"):
        enriched["last_commit"] = local_last_commit
    enriched.update(_derive_health(project, root))

    return enriched


def load_projects() -> list[dict]:
    return [_enrich_project(project) for project in _load_raw()]


def _get_raw_project(name: str) -> dict | None:
    projects = _load_raw()
    _index, project = _match_project(projects, name)
    return dict(project) if project else None


def get_project(name: str, hydrate_blurb: bool = False) -> dict | None:
    if hydrate_blurb:
        hydrated = ensure_project_blurb(name)
        if hydrated is not None:
            return hydrated
    projects = load_projects()
    _index, project = _match_project(projects, name)
    return dict(project) if project else None


def update_project(name: str, **fields) -> dict | None:
    projects = _load_raw()
    index, project = _match_project(projects, name)
    if project is None or index is None:
        return None
    updated = dict(project)
    updated.update(fields)
    updated["updated_at"] = datetime.now().isoformat(timespec="seconds")
    projects[index] = updated
    _save(projects)
    return get_project(updated.get("name", name))


def ensure_project_blurb(name: str) -> dict | None:
    project = _get_raw_project(name)
    if not project:
        return None
    if str(project.get("blurb", "") or "").strip():
        return get_project(name)
    enriched = _enrich_project(project)
    blurb = _generate_project_blurb(enriched)
    if not blurb:
        return get_project(name)
    return update_project(name, blurb=blurb)


def get_projects_for_prompt() -> str:
    projects = load_projects()
    if not projects:
        return ""

    pieces = ["[PROJECTS]"]
    for project in sorted(
        projects,
        key=lambda item: (
            {"active": 0, "paused": 1, "done": 2}.get(item.get("status", "paused"), 9),
            -int(item.get("completion", 0)),
        ),
    ):
        blockers = project.get("blockers", []) or []
        blocker = blockers[0] if blockers else "ok"
        blocker = " ".join(str(blocker).split())[:32]
        snippet = (
            f"{project.get('name', 'unknown')}:{project.get('status', 'unknown')}"
            f" {int(project.get('completion', 0))}%"
            f" blk:{blocker}"
        )
        candidate = " | ".join(pieces[1:] + [snippet]) if len(pieces) > 1 else snippet
        if len(f"{pieces[0]}\n{candidate}") > 300:
            break
        pieces.append(snippet)

    if len(pieces) == 1:
        return ""
    return f"{pieces[0]}\n" + " | ".join(pieces[1:])


def add_blocker(name: str, blocker_text: str) -> dict | None:
    project = _get_raw_project(name)
    if not project:
        return None
    blockers = list(project.get("blockers", []) or [])
    cleaned = " ".join(str(blocker_text).split()).strip()
    if cleaned and cleaned not in blockers:
        blockers.append(cleaned)
    return update_project(name, blockers=blockers)


def add_task(name: str, task_text: str) -> dict | None:
    project = _get_raw_project(name)
    if not project:
        return None
    next_tasks = list(project.get("next_tasks", []) or [])
    cleaned = " ".join(str(task_text).split()).strip()
    if cleaned and cleaned not in next_tasks:
        next_tasks.append(cleaned)
    return update_project(name, next_tasks=next_tasks)


def set_last_opened(name: str) -> dict | None:
    return update_project(name, last_opened=datetime.now().isoformat(timespec="seconds"))


def mark_error(name: str, error_text: str) -> dict | None:
    cleaned = " ".join(str(error_text).split()).strip()
    project = update_project(
        name,
        last_error=cleaned,
        last_error_at=datetime.now().isoformat(timespec="seconds"),
    )
    if cleaned:
        add_blocker(name, cleaned)
    return project


if __name__ == "__main__":
    print(get_projects_for_prompt())

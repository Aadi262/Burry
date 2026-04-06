"""Skills auto-loader — drop a .py file in this directory to add a new Burry skill.
Each skill file must export:
  TRIGGER_PATTERNS: list[str]  — regex patterns that activate this skill
  DESCRIPTION: str             — one sentence what this skill does
  execute(text: str, entities: dict) -> dict  — returns {"speech": str, "actions": list}
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

_REGISTRY: list[dict] = []
_LOADED = False


def load_skills() -> None:
    """Scan skills/ directory and register all skills automatically."""
    global _LOADED
    skills_dir = Path(__file__).parent
    for skill_file in sorted(skills_dir.glob("*.py")):
        if skill_file.stem.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"skills.{skill_file.stem}")
            patterns = getattr(module, "TRIGGER_PATTERNS", [])
            description = getattr(module, "DESCRIPTION", skill_file.stem)
            execute_fn = getattr(module, "execute", None)
            if patterns and execute_fn:
                _REGISTRY.append({
                    "name": skill_file.stem,
                    "patterns": [re.compile(p, re.IGNORECASE) for p in patterns],
                    "description": description,
                    "execute": execute_fn,
                })
                print(f"[Skills] Loaded: {skill_file.stem} ({len(patterns)} patterns)")
        except Exception as exc:
            print(f"[Skills] Failed to load {skill_file.stem}: {exc}")
    _LOADED = True


def match_skill(text: str) -> tuple:
    """Return (skill, entities) if text matches any skill pattern."""
    if not _LOADED:
        load_skills()
    for skill in _REGISTRY:
        for pattern in skill["patterns"]:
            match = pattern.search(text)
            if match:
                return skill, match.groupdict()
    return None, {}


def list_skills() -> list[str]:
    return [f"{s['name']}: {s['description']}" for s in _REGISTRY]

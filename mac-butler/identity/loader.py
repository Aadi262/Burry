#!/usr/bin/env python3
"""
identity/loader.py
Loads Aditya's profile and formats it for the LLM system prompt.
Butler reads this every single time he wakes up.
"""

import sys
from pathlib import Path

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

PROFILE_PATH = Path(__file__).parent / "profile.yaml"


def _load_profile() -> dict:
    if not PROFILE_PATH.exists() or not YAML_AVAILABLE:
        return {}
    with PROFILE_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def get_identity_context() -> str:
    if not PROFILE_PATH.exists():
        return ""

    if not YAML_AVAILABLE:
        raw = PROFILE_PATH.read_text(encoding="utf-8")
        return f"[IDENTITY]\n{raw[:600]}"

    profile = _load_profile()
    name = profile.get("name", "Aditya")
    role = profile.get("role", "")
    company = profile.get("company", "")
    style = profile.get("working_style", "")
    traits = profile.get("personality", [])
    built = profile.get("what_he_has_built", [])
    projects = profile.get("current_projects", [])
    thinking = profile.get("how_he_thinks", [])
    builder_notes = profile.get("builder_notes", [])
    interests = profile.get("interests", [])
    tools = profile.get("tools_i_use_daily", [])
    talk = profile.get("how_butler_should_talk", [])
    behave = profile.get("how_butler_should_behave", [])
    tone_rules = profile.get("tone_rules", [])
    response_rules = profile.get("response_rules", [])
    system_identity = profile.get("system_identity", [])
    example_style = profile.get("example_style", "").strip()

    project_lines = []
    for project in projects:
        status = project.get("status", "")
        path = project.get("path", "")
        what = project.get("what", "")
        project_lines.append(
            f"- {project['name']}: {what} | {status} | path: {path}"
        )
        concepts = project.get("key_concepts", [])
        if concepts:
            project_lines.append(f"  includes: {', '.join(concepts[:5])}")
        commands = project.get("commands", {})
        if commands:
            formatted = " | ".join(f"{name}: {value}" for name, value in commands.items())
            project_lines.append(f"  commands: {formatted}")

    return f"""[WHO YOU ARE TALKING TO]
Name: {name}
Role: {role} at {company}
Location: {profile.get('location', '')} ({profile.get('timezone', '')} timezone)

Aditya is not a beginner. He is a systems thinker and builder.

He:
{chr(10).join(f'- {line}' for line in traits)}

[WHAT HE HAS BUILT]
{chr(10).join(f'- {line}' for line in built)}

He actively builds and iterates fast.
He does not overthink. He executes.

[WHAT HE IS CURRENTLY BUILDING]
{chr(10).join(project_lines)}

[HOW HE THINKS]
{chr(10).join(f'- {line}' for line in thinking)}

[BUILDER NOTES]
{chr(10).join(f'- {line}' for line in builder_notes)}

[TOOLS HE USES]
{chr(10).join(f'- {line}' for line in tools)}

[HIS INTERESTS]
{chr(10).join(f'- {line}' for line in interests[:6])}

[HOW YOU (BUTLER) SHOULD BEHAVE]
{chr(10).join(f'- {line}' for line in behave)}

[HOW YOU SHOULD TALK]
{chr(10).join(f'- {line}' for line in talk)}

[TONE RULES]
{chr(10).join(f'- {line}' for line in tone_rules)}

[HOW YOU SHOULD RESPOND]
{chr(10).join(f'{i + 1}. {line}' for i, line in enumerate(response_rules))}

[CORE BUTLER IDENTITY]
{chr(10).join(f'- {line}' for line in system_identity)}

Example style:
{example_style}

You are not a generic assistant.
You are part of Aditya's system.
"""


def get_project_by_name(name: str) -> dict:
    """Returns project config dict by name, or empty dict."""
    profile = _load_profile()
    for project in profile.get("current_projects", []):
        if project["name"].lower() == name.lower():
            return project
    return {}


def get_all_projects() -> list:
    profile = _load_profile()
    return profile.get("current_projects", [])


if __name__ == "__main__":
    print(get_identity_context())

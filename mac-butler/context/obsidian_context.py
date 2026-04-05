#!/usr/bin/env python3
"""
context/obsidian_context.py
Reads the configured Obsidian vault for recent planning context.
"""

from datetime import datetime, timedelta
from pathlib import Path

from butler_config import OBSIDIAN_VAULT_NAME, OBSIDIAN_VAULT_PATH


def _get_vault_path() -> Path | None:
    if OBSIDIAN_VAULT_PATH:
        return Path(OBSIDIAN_VAULT_PATH).expanduser()
    if OBSIDIAN_VAULT_NAME and OBSIDIAN_VAULT_NAME != "YourVaultName":
        return (
            Path.home()
            / "Library"
            / "Mobile Documents"
            / "iCloud~md~obsidian"
            / "Documents"
            / OBSIDIAN_VAULT_NAME
        )
    return None


def get_obsidian_context() -> str:
    vault = _get_vault_path()
    if vault is None or not vault.exists():
        return ""

    results = []
    cutoff = datetime.now() - timedelta(days=3)

    today = datetime.now().strftime("%Y-%m-%d")
    daily = vault / "Daily" / f"{today}.md"
    if daily.exists():
        try:
            content = daily.read_text(encoding="utf-8", errors="ignore")[:800]
            results.append(f"Today's note:\n{content}")
        except OSError:
            pass

    recent = []
    for md_file in vault.rglob("*.md"):
        try:
            mtime = datetime.fromtimestamp(md_file.stat().st_mtime)
            if mtime > cutoff and "Daily" not in str(md_file):
                recent.append((mtime, md_file))
        except OSError:
            continue

    recent.sort(reverse=True)
    for mtime, md_file in recent[:3]:
        try:
            content = md_file.read_text(encoding="utf-8", errors="ignore")[:300]
            stamp = mtime.strftime("%a %H:%M")
            results.append(f"Note '{md_file.stem}' (edited {stamp}):\n{content}")
        except OSError:
            continue

    return "\n\n".join(results) if results else ""


if __name__ == "__main__":
    print(get_obsidian_context() or "No Obsidian vault found at configured path")

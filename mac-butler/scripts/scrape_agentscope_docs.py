#!/usr/bin/env python3
"""Mirror AgentScope docs into local reference folders.

Uses the official llms.txt index as the source of truth, then fetches every
document it references into:

- mac-butler/references/agentscope_docs
- /Users/adityatiwari/Burry/Butler Vault/References/AgentScope Docs
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

LLMS_URL = "https://docs.agentscope.io/llms.txt"
SITEMAP_URL = "https://docs.agentscope.io/sitemap.xml"
REQUEST_HEADERS = {
    "User-Agent": "Burry-AgentScope-Mirror/1.0",
    "Accept": "text/plain, text/markdown, application/json, application/xml;q=0.9, */*;q=0.8",
}

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_TARGET = REPO_ROOT / "references" / "agentscope_docs"
VAULT_TARGET = Path("/Users/adityatiwari/Burry/Butler Vault/References/AgentScope Docs")


def fetch_text(url: str) -> str:
    result = subprocess.run(
        ["curl", "-sS", url],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def parse_llms_index(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    pattern = re.compile(r"^- \[(?P<title>.+?)\]\((?P<url>https://docs\.agentscope\.io/[^)]+)\): (?P<desc>.+)$")
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        entries.append(
            {
                "title": match.group("title").strip(),
                "url": match.group("url").strip(),
                "description": match.group("desc").strip(),
            }
        )
    return entries


def parse_sitemap(text: str) -> list[str]:
    root = ET.fromstring(text)
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls: list[str] = []
    for loc in root.findall("sm:url/sm:loc", namespace):
        value = (loc.text or "").strip()
        if value.startswith("https://docs.agentscope.io"):
            urls.append(value)
    return urls


def relative_path_for_url(url: str) -> Path:
    path = re.sub(r"^https://docs\.agentscope\.io/?", "", url).strip("/")
    if not path:
        return Path("index.md")
    if path.endswith(".json"):
        return Path(path)
    if not path.endswith(".md"):
        path = f"{path}.md"
    return Path(path)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    ensure_parent(path)
    path.write_text(content, encoding="utf-8")


def render_index(entries: Iterable[dict[str, str]], fetched_at: str) -> str:
    lines = [
        "# AgentScope Docs Mirror",
        "",
        f"Fetched: {fetched_at}",
        "",
        "This folder mirrors the official AgentScope docs listed in `llms.txt`.",
        "",
        "## Pages",
        "",
    ]
    for entry in entries:
        rel = relative_path_for_url(entry["url"]).as_posix()
        lines.append(f"- [{entry['title']}]({rel}) - {entry['description']}")
    lines.append("")
    return "\n".join(lines)


def mirror_all(targets: list[Path]) -> int:
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    llms_text = fetch_text(LLMS_URL)
    sitemap_text = fetch_text(SITEMAP_URL)
    entries = parse_llms_index(llms_text)
    sitemap_urls = parse_sitemap(sitemap_text)

    entry_urls = {entry["url"] for entry in entries}
    for url in sitemap_urls:
        md_url = f"{url}.md" if not url.endswith(".md") else url
        if md_url not in entry_urls:
            entries.append(
                {
                    "title": relative_path_for_url(md_url).stem.replace("-", " "),
                    "url": md_url,
                    "description": "Discovered from sitemap.xml",
                }
            )
            entry_urls.add(md_url)

    manifest = {
        "fetched_at": fetched_at,
        "count": len(entries),
        "entries": [
            {
                **entry,
                "relative_path": relative_path_for_url(entry["url"]).as_posix(),
            }
            for entry in entries
        ],
    }
    index_text = render_index(entries, fetched_at)

    for target in targets:
        target.mkdir(parents=True, exist_ok=True)
        write_text(target / "llms.txt", llms_text)
        write_text(target / "sitemap.xml", sitemap_text)
        write_text(target / "INDEX.md", index_text)
        write_text(target / "manifest.json", json.dumps(manifest, indent=2))

    for entry in entries:
        content = fetch_text(entry["url"])
        rel_path = relative_path_for_url(entry["url"])
        for target in targets:
            write_text(target / rel_path, content)

    return len(entries)


def main() -> int:
    targets = [REPO_TARGET, VAULT_TARGET]
    count = mirror_all(targets)
    print(f"Mirrored {count} AgentScope docs into:")
    for target in targets:
        print(f"- {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

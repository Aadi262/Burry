#!/usr/bin/env python3
"""
secrets/loader.py
Loads local-only Butler secrets that should never be committed.
"""

import json
from pathlib import Path

SECRETS_PATH = Path(__file__).parent / "local_secrets.json"


def _load_secrets() -> dict:
    if not SECRETS_PATH.exists():
        return {}
    try:
        return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_local_secrets() -> dict:
    """Return the raw local secrets payload."""
    return _load_secrets()


def get_vps_secret(host: str, label: str = "") -> dict:
    secrets = _load_secrets().get("vps", {})
    direct_match = (
        secrets.get(label)
        or secrets.get(host)
        or secrets.get(host.split("@")[-1])
    )
    if direct_match:
        return direct_match

    normalized_host = host.split("@")[-1]
    for secret in secrets.values():
        secret_host = str(secret.get("host", "")).split("@")[-1]
        if secret_host and secret_host == normalized_host:
            return secret
    return {}


def has_vps_secret(host: str, label: str = "") -> bool:
    return bool(get_vps_secret(host, label))


def get_mcp_secret(server_name: str) -> dict:
    """Return per-server MCP settings from local secrets."""
    return _load_secrets().get("mcp", {}).get(server_name, {})

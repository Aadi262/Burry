#!/usr/bin/env python3
"""
butler_secrets/loader.py
Loads local-only Butler secrets without colliding with the stdlib secrets module.
"""

import json
import os
from pathlib import Path

SECRETS_PATHS = [
    Path(__file__).resolve().parent / "local_secrets.json",
    Path(__file__).resolve().parent.parent / "vault" / "local_secrets.json",
    Path(__file__).resolve().parent.parent / "secrets" / "local_secrets.json",
]


def _merge_dicts(base: dict, overlay: dict) -> dict:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_secrets() -> dict:
    merged: dict = {}
    for path in SECRETS_PATHS:
        if not path.exists():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(loaded, dict):
            merged = _merge_dicts(loaded, merged)
    return merged


def get_local_secrets() -> dict:
    return _load_secrets()


def get_secret(name: str, default: str = "") -> str:
    key = str(name or "").strip()
    if not key:
        return default
    env_value = os.environ.get(key, "").strip()
    if env_value:
        return env_value
    value = _load_secrets().get(key, default)
    if value is None:
        return default
    return str(value).strip()


def get_vps_secret(host: str, label: str = "") -> dict:
    secrets = _load_secrets().get("vps", {})
    direct_match = secrets.get(label) or secrets.get(host) or secrets.get(host.split("@")[-1])
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
    return _load_secrets().get("mcp", {}).get(server_name, {})


def get_ollama_secret() -> dict:
    return _load_secrets().get("ollama", {})

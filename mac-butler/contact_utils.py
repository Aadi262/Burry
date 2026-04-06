#!/usr/bin/env python3
"""Shared contact normalization helpers for Butler."""

from __future__ import annotations

import difflib
import re

COMMON_EMAIL_TLDS = ("com", "org", "net", "io", "ai", "co", "in", "edu", "me", "app", "dev")


def _correct_common_tld(token: str) -> str:
    lowered = str(token or "").strip().lower()
    if lowered in COMMON_EMAIL_TLDS:
        return lowered
    matches = difflib.get_close_matches(lowered, COMMON_EMAIL_TLDS, n=1, cutoff=0.75)
    return matches[0] if matches else lowered


def normalize_email(raw: str) -> str:
    cleaned = " ".join(str(raw or "").split()).strip().lower()
    if not cleaned:
        return ""

    replacements = (
        (r"\bat\s+the\s+red\b", "@"),
        (r"\bat\s+the\s+rate\b", "@"),
        (r"\bat\s+the\b", "@"),
        (r"\bat\s+rate\b", "@"),
        (r"\bat\b", "@"),
        (r"\bdot\b", "."),
        (r"\bperiod\b", "."),
        (r"\bunderscore\b", "_"),
        (r"\bhyphen\b", "-"),
        (r"\bdash\b", "-"),
    )
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, f" {replacement} ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s*@\s*", "@", cleaned)
    cleaned = re.sub(r"\s*\.\s*", ".", cleaned)
    cleaned = re.sub(r"\s*_\s*", "_", cleaned)
    cleaned = re.sub(r"\s*-\s*", "-", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if "@" not in cleaned:
        return cleaned

    local, _, domain = cleaned.partition("@")
    local = re.sub(r"\s+", "", local)
    domain = re.sub(r"\s+", "", domain).strip(".")
    if "." in domain:
        parts = [part for part in domain.split(".") if part]
        if parts:
            parts[-1] = _correct_common_tld(parts[-1])
            domain = ".".join(parts)
    else:
        match = re.match(r"^([a-z0-9._-]+?)([a-z]{2,4})$", domain)
        if match:
            domain = f"{match.group(1)}.{_correct_common_tld(match.group(2))}"

    return f"{local}@{domain}".strip("@")

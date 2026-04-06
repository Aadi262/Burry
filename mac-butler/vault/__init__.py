"""Compatibility layer for Butler local secrets and stdlib-style secrets helpers.

This package name shadows Python's standard-library ``secrets`` module when the
repo root is on ``sys.path``. Some third-party packages import ``secrets`` for
helpers like ``token_hex``. Provide the small stdlib-compatible surface here so
those imports keep working without renaming the repo package during runtime.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import os
import random

from .loader import get_local_secrets, get_mcp_secret, get_vps_secret, has_vps_secret

_SYSTEM_RANDOM = random.SystemRandom()


def randbelow(exclusive_upper_bound: int) -> int:
    if exclusive_upper_bound <= 0:
        raise ValueError("Upper bound must be positive")
    return _SYSTEM_RANDOM.randrange(exclusive_upper_bound)


def randbits(k: int) -> int:
    if k < 0:
        raise ValueError("Number of bits must be non-negative")
    return _SYSTEM_RANDOM.getrandbits(k)


def choice(sequence):
    if not sequence:
        raise IndexError("Cannot choose from an empty sequence")
    return _SYSTEM_RANDOM.choice(sequence)


def token_bytes(nbytes: int | None = None) -> bytes:
    return os.urandom(32 if nbytes is None else nbytes)


def token_hex(nbytes: int | None = None) -> str:
    return binascii.hexlify(token_bytes(nbytes)).decode("ascii")


def token_urlsafe(nbytes: int | None = None) -> str:
    return base64.urlsafe_b64encode(token_bytes(nbytes)).rstrip(b"=").decode("ascii")


def compare_digest(a, b) -> bool:
    return hmac.compare_digest(a, b)


__all__ = [
    "choice",
    "compare_digest",
    "get_local_secrets",
    "get_mcp_secret",
    "get_vps_secret",
    "has_vps_secret",
    "randbelow",
    "randbits",
    "token_bytes",
    "token_hex",
    "token_urlsafe",
]

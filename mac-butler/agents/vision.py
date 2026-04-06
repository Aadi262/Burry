#!/usr/bin/env python3
"""Screenshot vision helper for Burry."""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from brain.ollama_client import chat_with_ollama, pick_butler_model

SCREENSHOT_PATH = Path("/tmp/burry_screen.png")


def describe_screen(question: str = "What is on the screen right now?", model: str | None = None) -> str:
    subprocess.run(
        ["screencapture", "-x", "-t", "png", str(SCREENSHOT_PATH)],
        capture_output=True,
        timeout=10,
    )
    if not SCREENSHOT_PATH.exists():
        return "I couldn't capture the screen."

    image_b64 = base64.b64encode(SCREENSHOT_PATH.read_bytes()).decode("utf-8")
    response = chat_with_ollama(
        [
            {
                "role": "user",
                "content": question,
                "images": [image_b64],
            }
        ],
        model=pick_butler_model("vision", override=model),
        max_tokens=180,
        temperature=0.2,
    )
    message = response.get("message", {}) if isinstance(response, dict) else {}
    content = " ".join(str(message.get("content", "")).split()).strip()
    return content or "I couldn't read the screen clearly."

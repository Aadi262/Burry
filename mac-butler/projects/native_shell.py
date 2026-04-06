#!/usr/bin/env python3
"""Native floating Burry HUD window powered by pywebview."""

from __future__ import annotations

import argparse
import atexit
import os
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import webview

PID_PATH = Path("/tmp/burry_hud.pid")
LOADING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Burry</title>
  <style>
    html, body {
      margin: 0;
      width: 100%;
      height: 100%;
      background: radial-gradient(circle at top left, rgba(22, 80, 140, 0.26), transparent 28%), linear-gradient(180deg, #05080d 0%, #09121d 100%);
      color: #f5f7fb;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif;
      overflow: hidden;
    }
    .shell {
      width: 100%;
      height: 100%;
      display: grid;
      place-items: center;
    }
    .card {
      width: min(520px, calc(100vw - 48px));
      padding: 28px 32px;
      border-radius: 28px;
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.1);
      box-shadow: 0 24px 60px rgba(0,0,0,0.28);
      backdrop-filter: blur(16px);
    }
    .eyebrow {
      color: #5fd0ff;
      text-transform: uppercase;
      letter-spacing: 0.24em;
      font-size: 12px;
    }
    h1 {
      margin: 10px 0 8px;
      font-size: 42px;
      line-height: 0.95;
    }
    p {
      margin: 0;
      color: rgba(233, 240, 255, 0.72);
      font-size: 15px;
      line-height: 1.5;
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="card">
      <div class="eyebrow">Burry OS</div>
      <h1>Launching</h1>
      <p>Waiting for the live operator frontend to become ready.</p>
    </div>
  </div>
</body>
</html>
"""


def _write_pid() -> None:
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")


def _cleanup_pid() -> None:
    try:
        if PID_PATH.exists() and PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _url_ok(url: str) -> bool:
    try:
        with urlopen(url, timeout=1.2) as response:
            return int(getattr(response, "status", 200)) < 500
    except URLError:
        return False
    except Exception:
        return False


def _wait_for_url(url: str, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _url_ok(url):
            return True
        time.sleep(0.2)
    return False


class BurryWindowApi:
    def __init__(self) -> None:
        self.window = None

    def attach(self, window) -> None:
        self.window = window

    def toggle_pin(self) -> dict:
        if self.window is None:
            return {"ok": False, "pinned": False}
        self.window.on_top = not bool(self.window.on_top)
        return {"ok": True, "pinned": bool(self.window.on_top)}

    def minimize(self) -> dict:
        if self.window is None:
            return {"ok": False}
        self.window.minimize()
        return {"ok": True}

    def close(self) -> dict:
        if self.window is None:
            return {"ok": False}
        self.window.destroy()
        return {"ok": True}


def _bootstrap_window(window, url: str) -> None:
    if _wait_for_url(url, timeout=8.0):
        window.load_url(url)
    else:
        window.load_html(
            LOADING_HTML.replace(
                "Waiting for the live operator frontend to become ready.",
                "The frontend server did not become ready in time. Close this window and try again.",
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Native Burry HUD window")
    parser.add_argument("--url", default="http://127.0.0.1:3333", help="HUD URL")
    parser.add_argument("--title", default="Burry", help="Window title")
    args = parser.parse_args()

    _write_pid()
    atexit.register(_cleanup_pid)

    api = BurryWindowApi()
    window = webview.create_window(
        args.title,
        html=LOADING_HTML,
        width=1500,
        height=960,
        x=36,
        y=34,
        resizable=True,
        min_size=(980, 680),
        frameless=False,
        easy_drag=False,
        focus=True,
        on_top=True,
        shadow=True,
        background_color="#05080D",
        vibrancy=False,
        js_api=api,
    )
    api.attach(window)
    webview.start(_bootstrap_window, (window, args.url), debug=False)


if __name__ == "__main__":
    main()

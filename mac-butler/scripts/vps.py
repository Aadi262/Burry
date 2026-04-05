#!/usr/bin/env python3
"""
scripts/vps.py
Reusable helper for managing the configured VPS with saved local secrets.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from butler_config import VPS_HOSTS
from butler_secrets.loader import get_vps_secret


def _default_host() -> str:
    if VPS_HOSTS:
        return str(VPS_HOSTS[0].get("host", "")).strip()
    return ""


def _resolve_target(host: str) -> tuple[str, dict]:
    configured_host = host.strip() or _default_host()
    if not configured_host:
        raise SystemExit("No VPS host configured")

    secret = get_vps_secret(configured_host)
    if "@" in configured_host:
        return configured_host, secret

    username = str(secret.get("username", "")).strip()
    return (f"{username}@{configured_host}" if username else configured_host), secret


def _build_ssh_command(host: str, remote_command: str | None = None) -> list[str]:
    target, secret = _resolve_target(host)
    command = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=10",
    ]
    if remote_command is None:
        command.append("-tt")
    command.append(target)
    if remote_command is not None:
        command.append(remote_command)

    password = str(secret.get("password", "")).strip()
    if password and shutil.which("sshpass"):
        return ["sshpass", "-p", password, *command]
    return command


def _run_status(host: str) -> int:
    commands = [
        "hostnamectl",
        "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'",
        "free -h",
        "df -h /",
        "systemctl status ollama-server --no-pager || true",
    ]
    for remote_command in commands:
        print(f"$ {remote_command}")
        result = subprocess.run(_build_ssh_command(host, remote_command))
        if result.returncode != 0:
            return result.returncode
        print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Saved VPS helper")
    subparsers = parser.add_subparsers(dest="action", required=True)

    shell_parser = subparsers.add_parser("shell", help="Open an interactive SSH session")
    shell_parser.add_argument("--host", default="", help="Override the configured VPS host")

    exec_parser = subparsers.add_parser("exec", help="Run a remote command")
    exec_parser.add_argument("--host", default="", help="Override the configured VPS host")
    exec_parser.add_argument("remote_command", help="Command string to run remotely")

    status_parser = subparsers.add_parser("status", help="Run the standard VPS status checks")
    status_parser.add_argument("--host", default="", help="Override the configured VPS host")

    args = parser.parse_args()

    if args.action == "shell":
        return subprocess.run(_build_ssh_command(args.host)).returncode
    if args.action == "exec":
        return subprocess.run(_build_ssh_command(args.host, args.remote_command)).returncode
    if args.action == "status":
        return _run_status(args.host)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

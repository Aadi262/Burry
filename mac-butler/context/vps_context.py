#!/usr/bin/env python3
"""
context/vps_context.py
Checks configured VPS hosts to see whether they respond to a ping.
"""

import subprocess

from butler_config import VPS_HOSTS
from butler_secrets.loader import has_vps_secret


def get_vps_context() -> str:
    if not VPS_HOSTS:
        return ""

    results = []
    for vps in VPS_HOSTS:
        secret_status = " | local secret saved" if has_vps_secret(vps["host"], vps.get("label", "")) else ""
        try:
            host = vps["host"].split("@")[-1]
            ping = subprocess.run(
                ["ping", "-c", "1", host],
                capture_output=True,
                timeout=5,
            )
            status = "online" if ping.returncode == 0 else "unreachable"
            results.append(f"VPS '{vps['label']}': {status}{secret_status}")
        except subprocess.TimeoutExpired:
            results.append(f"VPS '{vps['label']}': unreachable{secret_status}")
        except Exception:
            results.append(f"VPS '{vps.get('label', 'unknown')}': check failed{secret_status}")

    return "\n".join(results) if results else ""


if __name__ == "__main__":
    print(get_vps_context() or "No VPS hosts configured")

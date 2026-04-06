"""iMessage skill — send iMessages via Messages.app."""
import subprocess

DESCRIPTION = "Send iMessages via Messages.app"
TRIGGER_PATTERNS = [
    r"(?:i?message|text) (?P<contact>.+?) (?:that |saying |to say )?(?P<message>.+)",
    r"send (?P<contact>.+?) (?:an? )?(?:i?message|text)(?: saying)? (?P<message>.+)",
]


def execute(text: str, entities: dict) -> dict:
    contact = (entities.get("contact") or "").strip()
    message = (entities.get("message") or "").strip()
    script = f'tell application "Messages" to send "{message}" to buddy "{contact}"'
    subprocess.run(["osascript", "-e", script], timeout=10)
    return {
        "speech": f"iMessage sent to {contact}.",
        "actions": [{"type": "imessage", "contact": contact}],
    }

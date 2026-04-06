"""Email skill — send emails via Gmail with subject and body."""
import subprocess
import urllib.parse

DESCRIPTION = "Send emails via Gmail with subject and body"
TRIGGER_PATTERNS = [
    r"email (?P<recipient>\S+@\S+) (?:with subject|subject) (?P<subject>.+?)(?:\s+(?:body|message|saying|boyd)\s+(?P<body>.+))?$",
    r"send (?:an? )?email to (?P<recipient>\S+@\S+)",
    r"compose (?:an? )?(?:email|mail) to (?P<recipient>\S+)",
]


def execute(text: str, entities: dict) -> dict:
    recipient = (entities.get("recipient") or "").strip().rstrip("with,. ")
    subject = (entities.get("subject") or "").strip()
    body = (entities.get("body") or "").strip()
    params = {"view": "cm", "fs": "1", "tf": "1", "to": recipient}
    if subject:
        params["su"] = subject
    if body:
        params["body"] = body
    url = "https://mail.google.com/mail/u/0/?" + urllib.parse.urlencode(params)
    subprocess.run(["open", url])
    return {
        "speech": f"Opening Gmail to {recipient}.",
        "actions": [{"type": "open_url", "url": url}],
    }

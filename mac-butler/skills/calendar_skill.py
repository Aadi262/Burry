"""Calendar skill — read macOS Calendar events."""
import subprocess

DESCRIPTION = "Read macOS Calendar events"
TRIGGER_PATTERNS = [
    r"what(?:'s| is) (?:on )?my (?:calendar|schedule|agenda)(?: today| tomorrow)?",
    r"do I have (?:any )?(?:meetings?|events?) (?:today|tomorrow)?",
]


def execute(text: str, entities: dict) -> dict:
    script = '''
    tell application "Calendar"
        set today to current date
        set todayEnd to today + 1 * days
        set eventList to ""
        repeat with cal in calendars
            try
                set evts to (every event of cal whose start date is greater than today and start date is less than todayEnd)
                repeat with evt in evts
                    set eventList to eventList & summary of evt & " at " & ((start date of evt) as string) & "\n"
                end repeat
            end try
        end repeat
        return eventList
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    events = result.stdout.strip()
    if events:
        return {"speech": f"Today you have: {events[:200]}", "actions": []}
    return {"speech": "You have no events today.", "actions": []}

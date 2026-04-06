---
name: calendar
description: Read and create macOS Calendar events
trigger_patterns:
  - "what.*on my (calendar|schedule|agenda)"
  - "do I have.*meetings? today"
  - "create.*meeting.*at .+"
  - "add.*event.*called .+"
---
Reads and creates events in macOS Calendar.app via AppleScript.

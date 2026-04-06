---
name: imessage
description: Send iMessages via Messages.app
trigger_patterns:
  - "(i?message|text) .+ (saying|that) .+"
  - "send .+ a (text|message)"
  - "tell .+ (via|over) imessage .+"
---
Sends iMessages using Messages.app via AppleScript.
Approved contacts configured in channels/imessage_channel.py.

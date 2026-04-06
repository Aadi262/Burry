---
name: email
description: Send emails via Gmail with subject and body pre-filled
trigger_patterns:
  - "email .+@.+ with subject .+"
  - "send email to .+"
  - "compose .+ to .+@"
  - "write .+ an email"
---
Opens Gmail compose URL with recipient, subject and body pre-filled.
Handles STT mishears: boyd→body, massage→message.

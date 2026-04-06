---
name: email_compose
description: Compose Gmail drafts with recipient, subject, and body details for the send_email tool.
---

# Email Compose

Use this skill when the user wants to draft or send an email.

1. Extract the recipient, subject, and body.
2. If the user omitted the body, write a short default body that matches the request.
3. Use the `send_email` tool instead of describing what should happen.
4. Keep the spoken response short after the draft is opened.

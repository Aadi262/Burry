# Dashboard API Contracts

Current HTTP surface implemented in `projects/dashboard.py`.

## GET

- `/health`
  - returns `{ ok, url, port, ws_url }`
- `/api/stream`
  - SSE stream of `operator_snapshot()` payloads
- `/api/projects`
  - returns project list
- `/api/mac-activity`
  - returns current mac activity snapshot
- `/api/graph`
  - returns project graph payload
- `/api/tasks`
  - returns task payload from `tasks/tasks.json`
- `/api/vps`
  - returns cached VPS status payload
- `/api/metrics`
  - returns runtime metrics payload
- `/api/logs?limit=N`
  - returns `{ items, count }` for recent runtime log events
- `/api/traces?limit=N`
  - returns `{ items, count }` for recent trace spans
- `/api/status`
  - returns dashboard payload
- `/api/operator`
  - returns operator snapshot used by HUD

## POST

- `/api/command`
  - request:
    - `{ "action": "listen_once" }`
    - or `{ "text": "<command>" }`
  - response:
    - `{ status, status_label, accepted, text, queued_at }`
- `/api/open_project?name=<project>`
  - opens a project and returns result payload
- `/api/interrupt`
  - interrupts current Butler task with a new command payload

## Current Gaps

- Contracts are implemented in code but were not previously documented in one place.
- Endpoint payload schemas are still informal Python dicts, not shared typed models.
- The next cleanup step should move these payloads behind typed response models the same way the capability planner now uses typed task contracts.

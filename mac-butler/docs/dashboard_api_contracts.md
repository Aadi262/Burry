# Dashboard API Contracts

Current HTTP surface implemented in `projects/dashboard.py`.

## GET

- `/api/v1/health`
- `/api/v1/projects`
- `/api/v1/mac-activity`
- `/api/v1/graph`
- `/api/v1/tasks`
- `/api/v1/vps`
- `/api/v1/metrics`
- `/api/v1/logs?limit=N`
- `/api/v1/traces?limit=N`
- `/api/v1/status`
- `/api/v1/operator`
- `/api/v1/capabilities`

All GET responses use:

```json
{
  "contract_version": "1.0",
  "kind": "operator",
  "data": {}
}
```

- `/api/v1/stream`
  - SSE stream of versioned HUD envelopes:
    `{ event_version, type, ts, data }`

## POST

- `/api/v1/command`
  - request:
    - `{ "action": "listen_once" }`
    - or `{ "text": "<command>" }`
  - response:
    - `CommandResult`
- `/api/v1/open_project?name=<project>`
  - returns the typed envelope `{ contract_version, kind, data }`
- `/api/v1/interrupt`
  - interrupts current Butler task with a new command payload

## Errors

Unknown or removed API paths return:

```json
{
  "contract_version": "1.0",
  "kind": "error",
  "error": "Not found",
  "status": 404,
  "code": "not_found"
}
```

## Removed

- legacy `/api/...` aliases are no longer supported

# Burry Contract Release Notes

## v1.0 - 2026-04-12

### Added

- typed contract DTOs in `capabilities/contracts.py` for:
  `ApiResponse`
  `ApiError`
  `CommandRequest`
  `CommandResult`
  `ToolInvocation`
  `ToolResult`
  `PendingState`
  `ClassifierResult`
  `CapabilityDescriptor`
  `HudEventEnvelope`
- stable public capability descriptors exposed from code with IDs from `.CODEX/Capability_Map.md`
- primary dashboard and A2A HTTP paths under `/api/v1/...`
- HUD WebSocket envelope fields:
  `event_version`
  `type`
  `ts`
  `data`

### Changed

- dashboard and A2A write flows now target `/api/v1/run`, `/api/v1/listen_once`, and `/api/v1/interrupt`
- dashboard GET routes now return `{ contract_version, kind, data }`
- the HUD frontend now reads dashboard state from `/api/v1/...` routes
- WebSocket consumers should read event bodies from `data`

### Deprecated

- legacy WebSocket `payload` remains mirrored temporarily for compatibility only

### Migration Notes

- old dashboard `/api/...` routes have been removed
- new consumers should treat `/api/v1/...` as the supported namespace
- new WebSocket consumers should read `event_version`, `type`, `ts`, and `data`
- existing HUD code can continue reading `payload` during the migration, but that field should not be the long-term dependency

### Test Evidence

- `venv/bin/pytest tests/test_dashboard.py tests/test_a2a_server.py tests/test_capabilities_planner.py tests/test_architecture_phase2.py tests/test_runtime_telemetry.py tests/test_session_context.py`
- `venv/bin/pytest tests/test_executor.py tests/test_butler_pipeline.py tests/test_intent_router.py tests/test_instant_lane.py`
- `python3 -m py_compile capabilities/contracts.py capabilities/registry.py capabilities/__init__.py brain/session_context.py intents/router.py executor/engine.py projects/dashboard.py channels/a2a_server.py tests/test_dashboard.py tests/test_a2a_server.py tests/test_capabilities_planner.py tests/test_architecture_phase2.py tests/test_session_context.py`

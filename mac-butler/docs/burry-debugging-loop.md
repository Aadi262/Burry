# Burry Debugging Loop

Use this when fixing live operator, frontend, or shell issues.

## Order
1. Prove the failing layer directly.
2. Get a minimal healthy path working.
3. Add tests around the real failing layer.
4. Only then add wrappers or polish.

## Frontend / HUD Rule
- Never start with pywebview, frameless shells, pinning, or glass effects.
- First prove:
  - `generate_dashboard()` returns quickly
  - the HTTP route returns HTML
  - assets load
  - the page renders in a normal browser
- Only after that:
  - native shell
  - pinned / draggable behavior
  - frameless styling
  - vibrancy

## Truthfulness Rule
- Unit tests for helpers do not equal end-to-end success.
- Say exactly what is proven:
  - "route works"
  - "browser render works"
  - "native shell still unproven"

## Performance Rule
- Keep first paint cheap.
- For the dashboard, prefer raw or cached project snapshots on boot.
- Deep project enrichment and health derivation must not block UI startup.

## Failure Isolation
For render bugs, check in this order:
1. `generate_dashboard()`
2. `/` route response
3. `/style.css` and `/app.js`
4. browser render
5. native shell launch

Do not jump to voice, MCP, or model layers unless the failure clearly points there.

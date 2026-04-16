# Pre-commit Checklist
Use this before every commit or handoff.
All paths below are relative to `mac-butler/`.

## 1. Re-read the live docs

- `.CODEX/Codex.md`
- `docs/phases/PHASE.md`
- `docs/phases/PHASE_PROGRESS.md`

If the change touches runtime truth, also re-read the relevant `.CODEX` owner docs you are depending on.

## 2. Review the diff

- confirm you extended existing owners instead of creating duplicates
- confirm the touched files match the intended slice
- confirm no runtime artifacts or memory/task state files are included

Never commit generated or runtime state under `memory/`, `tasks/`, or other local state directories.

## 3. Compile and syntax-check the touched files

- Python: run `venv/bin/python -m py_compile ...` on the changed Python files
- Frontend: run `node --check ...` on the changed frontend modules
- Hooks/backbone: confirm no LLM call was introduced into hook paths

## 4. Run focused regressions

- run the smallest pytest slice that fully covers the touched owners
- if the public contract changed, include dashboard, A2A, or contract tests
- if routing or execution changed, include the relevant router, executor, and pipeline tests

Do not claim a slice is done on compile-only evidence if behavior changed.

## 5. Run host checks when the machine-operating surface changed

- use `venv/bin/python scripts/system_check.py --json --phase1-host --phase1-host-only` when the touched actions are in the safe host smoke set
- run explicit manual checks when the action is operator-gated or not covered by `system_check.py`
- record skips truthfully when credentials, permissions, or targets are missing

## 6. Close the docs

- update `.CODEX/Codex.md` if runtime or process truth changed
- update `.CODEX/SPRINT_LOG.md` with what moved, what was validated, and what remains
- append `.CODEX/Learning_loop.md` when a mistake, hard lesson, or test insight was revealed
- update `.CODEX/Capability_Map.md` when capability status or setup requirements changed
- update `docs/phases/PHASE_PROGRESS.md` for the current session
- update `README.md` when user-facing behavior or setup changed

## 7. Only then commit

- keep commits scoped to one logical unit
- do not mix unrelated dirty-worktree changes into the commit
- include validation evidence in the handoff or commit message context

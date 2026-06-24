# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:tax-offset-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:tax-offset-local-implementation-closure-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `tax_offset` is the eighth non-Go modular IO/read model pilot.
- Repository port extraction is implemented: `TaxOffsetReadModelRepositoryPort` exposes only `load_tax_offset_read_models`, `get_tax_offset_view`, and `save_tax_offset_read_models`.
- Freshness/barrier audit is implemented: SQL month/summary reads use `ReadModelQueryGateway`, missing SQL repository in production SQL runtime fails closed as refreshing/unavailable, scope policy is month-or-all, `all` fans out to concrete month shards, plan save rejects non-fresh/source-version-mismatched read models, and `TaxOffsetPage` waits on current-month `tax_offset` operation barrier after plan save/certified import.
- OA attachment invoice fallback is fixed: centralized object identity treats `invoice_type=进项发票` / `销项发票` as formal invoice evidence when `evidence_type` is missing; explicit receipt/unknown evidence remains excluded.
- Local closure audit found a remaining implementation gap: `Application.rebuild_tax_offset_read_model_scope(...)` still owns worker rebuild, read model persistence and fresh Redis cache publish behavior.
- Therefore `tax_offset` is still `implementation-gap-open` and cannot move to `production-evidence-deferred`.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:tax-offset-worker-rebuild-executor-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile:
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
5. Read target planning evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-refresh-freshness-operation-barrier-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/tax-offset/README.md`
   - `docs/modules/tax-offset/implementation-notes.md`
   - `docs/modules/tax-offset/state-machine.md`
   - `docs/modules/tax-offset/tests.md`
6. Use CodeGraph for structural lookup before implementation edits.

## Boundary Scope

Target:

- Move app-owned tax offset worker rebuild behavior out of `Application.rebuild_tax_offset_read_model_scope(...)` into an explicit executor/service boundary.
- Preserve existing behavior exactly:
  - scope normalization through `TaxOffsetRuntimeService.request_scope_key(...)`;
  - payload creation through existing tax offset route/service boundary;
  - source versions from `TaxOffsetRuntimeService.expected_source_versions()`;
  - `TaxOffsetReadModelService.upsert_read_model(...)` semantics;
  - `snapshot_scope_keys(...)` persistence via existing persistence callback;
  - fresh Redis month/summary cache envelope shape and TTL;
  - returned `scope_key`, `month`, and `entry_count`.
- Keep `Application` as dependency assembly/thin delegate only.
- Add unit/static guard tests proving the old app-owned implementation body does not return.
- Update analysis, state machine files, module docs/tests and next prompt.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not claim `tax_offset` globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.
- Do not change tax business semantics, amount rules, certification rules, plan save API shape, permissions, audit meaning, worker event names, queue schema, Redis key/envelope contract or frontend behavior.
- Do not remove `_derived_lifecycle_tax_offset_executor(...)` in the same slice unless the impact analysis proves it is necessary and tests stay narrow; that can be a later boundary if still needed.

Expected verification:

- New/updated executor tests.
- Static architecture guard for removed app-owned worker rebuild implementation.
- Relevant targeted tax offset runtime/API/read model tests from `tests/test_tax_offset_sql_runtime.py`, `tests/test_tax_offset_api.py`, `tests/test_read_model_architecture_guards.py`, and app wiring if needed.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified tax offset worker rebuild executor extraction slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.

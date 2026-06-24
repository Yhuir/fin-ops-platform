# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:tax-offset-refresh-freshness-operation-barrier-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:tax-offset-refresh-freshness-operation-barrier-audit`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `tax_offset` is the eighth non-Go modular IO/read model pilot.
- `TaxOffsetReadModelRepositoryPort` now exposes only `load_tax_offset_read_models`, `get_tax_offset_view`, and `save_tax_offset_read_models`.
- PostgreSQL state-store tax read/write wiring and tax projection save paths use the narrow port.
- Freshness/barrier audit is complete locally:
  - SQL month/summary reads use `ReadModelQueryGateway` with schema/source-version proof.
  - Missing SQL repository in production SQL runtime returns refreshing/unavailable and enqueues refresh instead of live rebuild.
  - `tax_offset` scope policy is month-or-all.
  - `TaxOffsetReadModelRefreshService` expands `all` into concrete month shards and completes parent `all` without writing an `all` payload.
  - Plan save rejects non-fresh/source-version-mismatched read models.
  - `TaxOffsetPage` waits on current-month `tax_offset` operation barrier after plan save and certified import completion.
- The recorded OA attachment invoice API regression is fixed: centralized object identity now treats `invoice_type=进项发票` / `销项发票` as formal invoice evidence when `evidence_type` is missing; explicit receipt/unknown evidence stays excluded.
- `tax_offset` is not globally closed because local implementation closure accounting and production evidence defer accounting still need completion.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:tax-offset-local-implementation-closure-audit`

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

- Audit whether all local `tax_offset` implementation support is now accounted for:
  - repository port;
  - query fresh gate;
  - force refresh/scope policy;
  - all fan-out/month shard proof;
  - operation barrier;
  - worker/manifest/App Status registration;
  - source-version proof;
  - OA attachment invoice fallback;
  - retained legacy/app-owned helper classifications;
  - tests/docs.
- Classify any remaining local gap as a new narrow queue item before closure/defer.
- If no local implementation gap remains, mark this slice `production-evidence-deferred` / `not-module-closed`, not `closed`, because real PostgreSQL/worker/App Status/high-row/browser evidence is unavailable.
- Produce/update an analysis file documenting previous state, audit evidence, remaining gaps or defer decision, legacy/pollution classification, state-machine impact, seven-category test applicability and verification.
- Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not claim `tax_offset` globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.
- Do not change tax business semantics, amount rules, certification rules, plan save API shape, permissions, audit meaning or frontend behavior unless the audit finds a concrete bug and the fix is split narrowly with tests.

Expected verification:

- Targeted tax offset/object identity/read model/API/runtime tests selected from `tests/test_object_identity_policy.py`, `tests/test_tax_offset_service.py`, `tests/test_tax_offset_api.py`, `tests/test_tax_offset_sql_runtime.py`, `tests/test_read_model_refresh_gateway.py`, `tests/test_runtime_worker_read_model_refresh_scopes.py`, `tests/test_read_model_manifest.py` and frontend operation barrier tests if frontend behavior is touched.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` if app wiring changes.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified tax offset local implementation closure/defer accounting slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.

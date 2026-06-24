# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:invoice-lifecycle-derived-lifecycle-executor-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:invoice-lifecycle-derived-lifecycle-executor-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `invoice_lifecycle` is the seventh non-Go read model implementation pilot.
- Repository port extraction is implemented: `InvoiceLifecycleReadModelRepositoryPort` wraps lifecycle read model methods, the facade uses it for lookups, and the SQL projection builder uses it for save/mark paths.
- Freshness/barrier audit is closed as a regression guard: facade reads do not expose a queryable `all`, refresh service expands `all` into month shards, source-version currentness is checked before and after rebuild, scope policy accepts month/all only, App Status/worker/manifest contracts are registered, and exact-month operation barrier behavior is covered.
- Derived lifecycle executor extraction is implemented: `InvoiceLifecycleDerivedLifecycleExecutor` owns scope selection, reason default, metadata filtering and response shape; `Application` only assembles the gateway-backed enqueue callback.
- `Application._derived_lifecycle_invoice_lifecycle_executor(...)` is removed and guarded from returning.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:invoice-lifecycle-local-implementation-closure-audit`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-derived-lifecycle-executor-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-refresh-freshness-operation-barrier-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-repository-port-extraction.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/domain-events-lifecycle/README.md`
   - `docs/modules/domain-events-lifecycle/implementation-notes.md`
   - `docs/modules/domain-events-lifecycle/tests.md`
6. Use CodeGraph for structural lookup before any implementation edits.

## Boundary Scope

Target:

- Audit whether `invoice_lifecycle` local implementation support is now fully accounted for after:
  - repository port extraction
  - freshness/force-refresh/operation-barrier audit
  - explicit derived lifecycle executor extraction
- Inspect remaining invoice lifecycle app/server/service/worker/repository/query/facade/projection paths for:
  - old live rebuild fallback contamination
  - direct dirty/outbox SQL writes outside gateway/transactional contract
  - app-owned implementation helpers that should be service-owned
  - missing read model freshness proof or operation barrier target gaps
  - speculative or broad repository/state-store exposure
- If a concrete local implementation gap is found, split to the smallest safe implementation boundary and execute that boundary instead of marking closure/defer.
- If no local implementation gap remains, mark local support as accounted and record real PostgreSQL/worker/App Status/high-row/browser evidence as `production-evidence-deferred`, not globally closed.
- Update modular IO analysis/state docs and read-models/domain-events module docs/tests as applicable.

Forbidden:

- Do not change invoice lifecycle business rules, payload shape, source-version semantics, worker event semantics, queue schema, API behavior, frontend behavior, Go/Fiber/Go Worker or production state unless the audit finds a concrete required local implementation gap.
- Do not claim `invoice_lifecycle` globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.
- Do not select Go hot-path admission while implementation-pending or implementation-gap-open read model work remains.

Expected verification:

- `bash scripts/verify.sh docs`
- `git diff --check`
- If runtime code changes, run targeted backend tests for the touched service/API/worker/read model paths plus `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`.
- If the boundary is audit-only, record why targeted runtime tests are not required.

## Stop Condition

Complete one verified invoice lifecycle local closure/defer accounting slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.

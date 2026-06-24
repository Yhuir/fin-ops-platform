# Read Model Next Pilot Selection After Invoice Lifecycle

**Date:** 2026-06-24
**Boundary:** `read-models:next-pilot-selection-after-invoice-lifecycle`
**Previous state:** `read-models:invoice-lifecycle-local-implementation-closure-audit` was `production-evidence-deferred`.
**Result state:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Scope

Select the next non-Go modular IO/read model pilot after `invoice_lifecycle`, before any Go/Fiber/Go Worker admission.

This slice is analysis/accounting only. It does not change runtime code, SQL, API shape, read model schema, worker behavior, frontend behavior, production state, Go/Fiber or Go Worker.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/prompts/04-master-goal-controller.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/06-PILOT-SELECTION.md`
- `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-derived-lifecycle-executor-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-local-implementation-closure-audit.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/tax-offset/README.md`
- `docs/modules/tax-offset/implementation-notes.md`
- `docs/modules/tax-offset/tests.md`
- `docs/modules/cost-statistics/README.md`
- `docs/modules/cost-statistics/implementation-notes.md`
- `docs/modules/cost-statistics/tests.md`
- `docs/modules/turnover-ledger/README.md`
- `docs/modules/turnover-ledger/implementation-notes.md`
- `docs/modules/turnover-ledger/tests.md`
- `docs/modules/no-oa-bank-batches/README.md`
- `docs/modules/no-oa-bank-batches/implementation-notes.md`
- `docs/modules/no-oa-bank-batches/tests.md`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/tax_offset_query_service.py`
- `backend/src/fin_ops_platform/services/tax_offset_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/cost_statistics_query_service.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`

Preflight completed:

- `pwd` confirmed `/Users/yu/Desktop/fin-ops-platform`.
- `git status --short --branch` confirmed `dev...origin/dev` with a clean worktree.
- `git fetch --prune origin` completed.
- `git pull --ff-only origin dev` was already up to date.
- `git merge --no-edit --ff origin/main` was already up to date.

CodeGraph was used to inspect the candidate read model structures, including `TaxOffsetQueryService`, `TaxOffsetReadModelRefreshService`, `CostStatisticsQueryService`, `TurnoverLedgerQueryService`, `NoOaBankBatchApplicationService`, `BankAccountBalanceReadModelRefreshService` and search-related projection/service entry points.

## Candidate Comparison

| Candidate | Stale-read / cross-page risk | IO boundary readiness | First safe slice | Risk / deferral reason | Decision |
| --- | --- | --- | --- | --- | --- |
| `tax_offset` | High. Depends on invoice lifecycle, certified import, plan save, Workbench relation fan-out and import fan-out. Bugs show as tax page stale/fresh mismatch after another page writes. | Strong. Manifest declares `partitioned_scoped_incremental`, month-or-all policy, `TaxOffsetQueryService`, `TaxOffsetReadModelRefreshService`, primary `tax-offset` worker and repository contract with only three methods. | `read-models:tax-offset-repository-port-extraction` | Requires later freshness/barrier and legacy/live path audit, but first slice is narrow and testable without local `PGSQL_URL`. | Selected. |
| `cost_statistics` | Very high and performance-sensitive. Cross-page fan-out from Workbench, no-OA, turnover, imports and settings. | Strong, but more complex because `cost_statistics` uses queryable parent aggregate and special `active/all` scope semantics. | Repository port or parent aggregate audit. | Already a Go hot-path candidate for summary rollup; parent aggregate and production performance evidence make it heavier than the next small pilot. | Defer until after tax offset or a cost-specific prep slice. |
| `turnover_ledger` | Very high. Workbench relation, bank detail, cost/search and manual closure semantics are all involved. | Good but broad. Query service still has legacy payload builder fallback and write/freshness semantics are heavier. | Repository port extraction or legacy fallback audit. | Write path and relation semantics make it too large immediately after invoice lifecycle; choose only after a smaller tax slice or split into a separate narrow audit. | Defer. |
| `no_oa_bank_batch` | High. Bankdetail subdomain, Workbench relation command service, operation barrier and cost fan-out. | Moderate. Read model is self-managed freshness and application-service owned; repository contract is narrow but domain repair/compat paths are complex. | Repository port extraction or self-managed freshness audit. | Strong candidate, but no-OA already carries Bankdetail/workbench relation repair complexity and is less directly unlocked by invoice lifecycle. | Defer. |
| `bank_account_balance` | Medium. Important account-level projection tied to bank imports, but narrower user-visible cross-page risk than tax/cost/turnover. | Moderate. Manifest/test owner exists; refresh service is isolated. | Repository port or refresh/freshness audit. | Lower immediate benefit after invoice lifecycle; better after remaining tax/cost/turnover page read models are stabilized. | Defer. |
| `search` | High shared index risk. Search can reflect many stale modules. | Complex. Partitioned scoped index has multiple auxiliary workers and broad fan-out. | Search index owner audit. | Too broad as the next pilot; should follow more page-specific read model closures so search inputs are stable. | Defer. |

## Decision

Select `tax_offset` as the next non-Go modular IO/read model pilot.

The next implementation boundary is:

```text
read-models:tax-offset-repository-port-extraction
```

Rationale:

- `invoice_lifecycle` was just locally accounted for; `tax_offset` is one of the most direct consumers of lifecycle/certification state.
- `tax_offset` has a high user-visible stale-read risk: plan save, certified import, invoice import and Workbench relation fan-out can all change what the tax page should show.
- The first implementation slice is appropriately small because the manifest repository port contract has only:
  - `load_tax_offset_read_models`
  - `get_tax_offset_view`
  - `save_tax_offset_read_models`
- Current `TaxOffsetQueryService` already uses `ReadModelQueryGateway`, expected schema/source versions and production fail-closed behavior when SQL runtime is required.
- Current `TaxOffsetReadModelRefreshService` already treats `all` as a fan-out command and handles concrete month rebuilds.
- Existing tests and docs provide enough local/fake-only coverage to implement a repository port without local `PGSQL_URL` or staging DB.

## Rejected Next Step: Go Hot Path

No Go/Fiber/Go Worker candidate is eligible next.

Go admission remains blocked because remaining modular IO/read model implementation boundaries still exist. `cost_statistics:summary-rollup`, `tax_offset:read-model-builder`, `turnover-ledger:read-model-builder`, `no-oa-bank-batch:read-model-builder` and other Go candidates require stable IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback gates before admission.

## Next Implementation Slice Contract

`read-models:tax-offset-repository-port-extraction` must:

- Add a narrow `TaxOffsetReadModelRepositoryPort` or equivalent existing-pattern port.
- Expose only the manifest-listed tax offset repository methods.
- Wire `TaxOffsetQueryService` and tax offset projection save/read paths through the port where they currently consume broad `PostgresReadModelRepository` behavior.
- Preserve SQL table ownership inside `PostgresReadModelRepository`.
- Preserve API shape, tax calculation rules, plan save semantics, certified import semantics, source-version semantics, worker event semantics and frontend behavior.
- Add a guard proving unrelated read model repository methods are not exposed through the tax offset port.
- Reuse existing tax offset SQL runtime/read model tests before adding broader tests.

## State-Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/tax-offset/state-machine.md`

No workflow, module, business, read model or worker state definition changed. This slice advances one queue item:

- `read-models:next-pilot-selection-after-invoice-lifecycle`: `pending` -> `analysis-closed`
- Module closure remains `implementation-gap-open`
- New next boundary becomes `read-models:tax-offset-repository-port-extraction`
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`

## Seven Test Categories

1. Business core unit tests: not applicable to this selection-only slice. No tax calculation, certification, plan save or state rule changed.
2. Service-layer tests: not changed in this slice. The next implementation slice must update service/repository tests for the tax offset repository port.
3. API contract tests: not applicable. No HTTP behavior or response shape changed.
4. Read model/cache/background job tests: applicable as selection criteria; no runtime behavior changed. The next implementation slice must cover the tax offset repository port and existing fresh gate/fan-out behavior.
5. Frontend component and interaction tests: not applicable. No frontend behavior changed.
6. End-to-end business-flow integration tests: not applicable to this analysis-only selection. Existing tax offset Browser and API evidence informed selection.
7. Existing feature regression tests: applicable to the next implementation slice; this slice records the regression surface but adds no runtime tests.

## Verification

Required verification for this documentation/accounting-only slice:

```bash
bash scripts/verify.sh docs
git diff --check
```

Runtime tests are not required unless runtime code changes.

## Remaining Risk

- No local `PGSQL_URL` or staging database is available; real PostgreSQL/worker/App Status/high-row/browser evidence remains unavailable.
- This slice selects `tax_offset`; it does not prove `tax_offset` implementation closure.
- `cost_statistics`, `turnover_ledger`, `no_oa_bank_batch`, `search` and `bank_account_balance` remain implementation-gap-open candidates for later slices.
- Go/Fiber/Go Worker admission remains blocked.

## Next Boundary

`read-models:tax-offset-repository-port-extraction`

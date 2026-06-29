# 2026-06-29 Read Model / Canonical Facts Consistency Audit

## Scope

- Question 1: a relation confirmed in Workbench must not disappear from downstream pages that depend on the same relation fact.
- Question 2: pages must not present stale, missing, schema-mismatched, or source-version-mismatched read models as fresh/correct data.
- Pages checked: Workbench, Cost Statistics, Bank Details, OA Pending Payments, No-OA Bank Batches, Batch Accounting, Turnover Ledger, ETC Tickets, Tax Offset, Pending Invoices, Input Invoice Usage, Output Invoice Collections.

## Findings

- Canonical relation fact owner is `workbench-relations`: `app.workbench_pair_relations` and `app.workbench_pair_relation_history` are written through `WorkbenchRelationCommandService` / relation UoW and read through `WorkbenchRelationReadFacade` / relation repository port.
- `workbench_relation` read model is the shared downstream relation distribution. It is manifest-registered with scope type `workbench_relation`, worker `workbench-relation`, query owner `WorkbenchRelationReadFacade`, repository owner `WorkbenchRelationReadModelRepositoryPort`, and test owner `tests/test_workbench_relation_read_facade.py`.
- Read model freshness is guarded by `ReadModelQueryGateway`, self-managed facades, source version checks, schema checks, dirty/outbox state, and operation barrier targets. Non-fresh states enqueue refresh and surface `refreshing`/`stale`/`missing` instead of pretending to be fresh.
- Batch Accounting and ETC Tickets do not have independent App Status read model entries. They are command/source pages: relation writes still go through the canonical relation boundary, and completed writes/jobs expose operation barrier targets before downstream page reloads.

## Verification

- GSD audit query: `audit-uat` returned zero open findings.
- Backend targeted suite: 574 tests passed.
  - Covered manifest/registry/scope/freshness/barrier contracts.
  - Covered workbench relation command/read/projection contracts.
  - Covered screenshot page modules' read model/service API contracts.
- Frontend targeted Vitest suite: 341 tests passed across 13 files.
  - Covered operation barrier mapping/waiting and page non-fresh handling.
- Playwright fan-out/nonfresh suite: 17 tests passed.
  - Covered Workbench relation fan-out to Bank Details and Pending Invoices.
  - Covered Cost Statistics relation fan-out.
  - Covered Batch Accounting, No-OA, OA Pending non-fresh diagnostics and freshness waits.

## Conclusion

Current repo evidence supports the requested guarantee at code/test level:

- Workbench relation facts have a single owner and a shared relation read model path for downstream pages.
- Downstream pages do not silently treat stale/missing/source-version-mismatched read models as fresh data.
- Known remaining risk is operational, not code-path evidence: a live production incident can still occur if required workers are stopped, the durable queue is blocked, or PostgreSQL runtime state has current uncovered outbox failures. In that case pages should show refreshing/blocked/stale instead of inconsistent fresh data.

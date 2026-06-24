# Read Model Next Pilot Selection After Cost Statistics

**Date:** 2026-06-24
**Boundary:** `read-models:next-pilot-selection-after-cost-statistics`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`cost_statistics` local implementation support is accounted for after repository port extraction, freshness/barrier audit, derived lifecycle executor extraction and full-state snapshot quarantine. The module is not globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.

Go/Fiber/Go Worker admission remains blocked while non-Go modular IO/read model candidates still have implementation gaps.

## Selected Boundary

Select the next non-Go modular IO/read model pilot and define the first narrow implementation slice.

## Candidate Comparison

| Candidate | Stale-read / cross-page risk | Current evidence | First narrow slice | Decision |
| --- | --- | --- | --- | --- |
| `turnover_ledger` | Very high. It is a user-facing write-adjacent page whose tag-selection, extra save, manual closure confirm and withdraw paths affect Workbench relation, Workbench, bank detail, cost statistics and search visibility. | Module docs require SQL read model freshness, Workbench relation context projection, operation barrier and no stale grouped payload writes. Manifest already lists a narrow three-method repository port contract, but code still reads/saves through a broad repository shape. Tests already cover fresh/stale/missing read model behavior and worker projection saves. | Extract `TurnoverLedgerReadModelRepositoryPort` for `list_turnover_ledger_view`, `save_turnover_ledger_rows` and `clear_turnover_ledger_rows`; wire query/projection paths through it; add a port guard. | Selected. |
| `no_oa_bank_batch` | High. It is a Bankdetail subdomain with submitted/draft lifecycle, Workbench relation writes and public snapshot cleanup risk. | It already has a dedicated application service and refresh service, but its read model persistence still goes through state-store/public snapshot behavior rather than a clear read-model repository-port first slice. Recent implementation notes show active lifecycle cleanup and row-tag snapshot work, so it should be audited before port extraction. | Later no-OA read model repository/state-store boundary audit before implementation. | Defer. |
| `search` | Medium/high. It is a shared index used by several downstream workflows, but it has no independent frontend route today and runs through primary plus compatibility worker lanes. | Manifest has a two-method contract and tests cover SQL index reads, saves and all-scope expansion. Because it is cross-cutting and has `search-pending`, `search-secondary` and `search-tertiary` lanes, the first slice needs worker-lane audit before implementation. | Later search repository port / worker lane audit. | Defer. |
| `bank_account_balance` | Medium. It is user-visible on Bank Details and must remain independent from bank detail rows, but its scope is narrower than the remaining page-level candidates. | It already has manifest, worker and tests; current read surface is coupled through bank detail application/service wiring. It is important, but lower cross-page stale-read risk than turnover and no-OA. | Later account-balance repository port split from bank detail read port. | Defer. |

## Selection Rationale

`turnover_ledger` is the best next non-Go pilot because:

- it has the highest remaining user-visible consistency risk after cost statistics: a stale grouped ledger can mislead manual closure/withdraw decisions and can make Workbench relation/cost/search appear inconsistent across pages;
- the first slice is narrow and already specified by the manifest: `list_turnover_ledger_view`, `save_turnover_ledger_rows`, and `clear_turnover_ledger_rows`;
- `TurnoverLedgerQueryService` already uses `ReadModelQueryGateway`, so port extraction can preserve HTTP shape, freshness behavior and legacy/local compatibility;
- `TurnoverLedgerSqlProjectionBuilder` already treats missing save capability as an explicit error, which makes a narrow repository port low-risk to introduce;
- existing tests cover stale SQL read model, missing required SQL read model, fresh SQL read model, worker handler and projection save behavior, making the boundary verifiable without broad code changes;
- unlike `search`, this is a direct page module with module docs, E2E contracts and clear permission/query owner;
- unlike `bank_account_balance`, it is a primary page-level read model rather than a supporting Bank Details sub-read model;
- unlike `no_oa_bank_batch`, the first implementation boundary does not require untangling public snapshot lifecycle semantics first.

## First Implementation Boundary

`read-models:turnover-ledger-repository-port-extraction`

Expected scope:

- Add `TurnoverLedgerReadModelRepositoryPort`.
- Expose only manifest-listed methods:
  - `list_turnover_ledger_view`;
  - `save_turnover_ledger_rows`;
  - `clear_turnover_ledger_rows`.
- Return/use the port from PostgreSQL state-store or route/service read wiring where applicable.
- Inject/use the port in `TurnoverLedgerQueryService` and `TurnoverLedgerSqlProjectionBuilder` read/save paths.
- Keep SQL table knowledge in `PostgresReadModelRepository`; do not move SQL in this slice.
- Do not change turnover business rules, grouped payload shape, manual closure semantics, Workbench relation command behavior, worker event names, queue schema, Redis/cache behavior, permissions, audit meaning, frontend behavior or Go/Fiber/Go Worker status.
- Add/update tests proving the turnover ledger port excludes unrelated read model methods and existing SQL runtime/freshness behavior remains unchanged.

## State Machine Impact

- `read-models:next-pilot-selection-after-cost-statistics` transitions to `analysis-closed`.
- Insert `read-models:turnover-ledger-repository-port-extraction` as the next pending boundary before Go candidates.
- `turnover_ledger` becomes the tenth non-Go modular IO/read model implementation pilot.
- `no_oa_bank_batch`, `search` and `bank_account_balance` remain implementation-gap-open candidates.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- Global state-machine definitions do not change; this uses existing `analysis-closed` semantics.
- `docs/modules/turnover-ledger/state-machine.md` definitions do not change; no turnover business/UI/read model/worker transition changed in this analysis slice.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable for selection | No turnover relation, amount, tag or closure rule changes in this analysis slice. |
| 2. Service-layer tests | Applicable to next slice | Repository-port extraction must add/update service/repository boundary tests. |
| 3. API contract tests | Not applicable for selection | No HTTP behavior changes in this analysis slice. Next implementation should keep existing turnover API shape green. |
| 4. Read model/cache/background job tests | Applicable to next slice | Existing query service and worker refresh tests must remain green; port guard should be added. |
| 5. Frontend component and interaction tests | Not applicable for selection | No frontend behavior changes in this analysis slice. |
| 6. End-to-end business-flow integration tests | Not applicable for selection | No runtime flow changes. Turnover E2E evidence informs priority only. |
| 7. Existing feature regression tests | Applicable to next slice | Turnover has broad Workbench/cost/search downstream regressions; next implementation must choose targeted backend regression checks. |

## Verification

This slice is analysis/accounting only. Required verification:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Next Boundary

`read-models:turnover-ledger-repository-port-extraction`

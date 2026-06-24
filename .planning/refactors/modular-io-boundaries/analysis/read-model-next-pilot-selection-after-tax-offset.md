# Read Model Next Pilot Selection After Tax Offset

**Date:** 2026-06-24
**Boundary:** `read-models:next-pilot-selection-after-tax-offset`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`tax_offset` local implementation support is accounted for and moved to `production-evidence-deferred`, without claiming global module closure. Go/Fiber/Go Worker admission remains blocked while non-Go modular IO/read model candidates still have implementation gaps.

## Selected Boundary

Select the next non-Go modular IO/read model pilot and define the first narrow implementation slice.

## Candidate Comparison

| Candidate | Stale-read / cross-page risk | Current evidence | First narrow slice | Decision |
| --- | --- | --- | --- | --- |
| `cost_statistics` | Very high. It consumes Workbench relation, bank detail tags, import facts, ETC/no-OA/turnover/settings fan-out and feeds a high-visibility summary/export page. | Has special `active/all` scope grammar, queryable parent aggregate, old `cost-tax` compatibility worker lane, and many production/SLO incidents. Manifest already defines a narrow repository port contract, but code still uses broad `PostgresReadModelRepository` directly. | Extract `CostStatisticsReadModelRepositoryPort` and wire SQL read/projection save paths through it. | Selected. |
| `turnover_ledger` | High. It is write-adjacent and depends on Workbench relation distribution, but recent Workbench relation slices already removed many relation pollution paths. | Query service uses `ReadModelQueryGateway`; write facade and UoW boundaries have substantial coverage. Remaining work is important but broader than a repository-port first slice. | Later repository/query owner and legacy fallback audit. | Defer after cost statistics selection. |
| `no_oa_bank_batch` | High. It is a bank-detail subdomain with relation write/read consistency risk. | It has active lifecycle/status compatibility complexity and relation command constraints. First slice likely needs a dedicated audit before implementation. | Later repository port / SQL read model fail-closed audit. | Defer. |
| `search` | Medium/high. Shared search projection affects multiple pages, but no independent frontend route and multiple search worker lanes make the first slice less directly page-visible. | Search is already registered with primary/secondary/tertiary workers and shares historical `search-pending` compatibility. | Later search repository port / worker lane audit. | Defer. |
| `bank_account_balance` | Medium. It is important for bank details but narrower and already adjacent to a partially accounted bank-detail pilot. | Current worker requires only `all` scope; partitioning strategy needs a separate design if account/month scopes are introduced. | Later account-level partitioning design. | Defer. |

## Selection Rationale

`cost_statistics` is the best next non-Go pilot because:

- it is the highest-risk remaining page for cross-page stale read bugs after invoice/tax/Workbench relation work;
- it has a concrete, narrow first implementation slice: the manifest already lists `load_cost_statistics_read_models`, `get_cost_statistics_view`, and `save_cost_statistics_read_models` as the repository port contract;
- `CostStatisticsSqlProjectionBuilder` still imports and stores `PostgresReadModelRepository` directly, unlike recently migrated pilots that now go through narrow ports;
- `CostStatisticsQueryService` already uses `ReadModelQueryGateway`, so repository-port extraction can be done without changing HTTP shape or freshness semantics;
- `cost_statistics` has a special queryable parent aggregate (`active:all` / `all:all`) that should be isolated before any Go summary-rollup admission;
- the old `cost-tax` combined worker remains a compatibility lane while `cost-statistics` is the primary worker, so owner boundaries need to be explicit before Go Worker consideration.

## First Implementation Boundary

`read-models:cost-statistics-repository-port-extraction`

Expected scope:

- Add `CostStatisticsReadModelRepositoryPort`.
- Expose only manifest-listed methods:
  - `load_cost_statistics_read_models`;
  - `get_cost_statistics_view`;
  - `save_cost_statistics_read_models`.
- Return the port from PostgreSQL state-store cost statistics read wiring where applicable.
- Inject/use the port in `CostStatisticsQueryService` and `CostStatisticsSqlProjectionBuilder` read/save paths.
- Do not move SQL table knowledge out of `PostgresReadModelRepository` in this slice.
- Do not change cost attribution, project scope, export, parent aggregate, worker event, queue, Redis key/envelope, permission or API shape.
- Add/update tests proving the cost statistics port excludes unrelated read model methods and existing SQL runtime/freshness behavior remains unchanged.

## State Machine Impact

- `read-models:next-pilot-selection-after-tax-offset` transitions to `analysis-closed`.
- Insert `read-models:cost-statistics-repository-port-extraction` as the next pending boundary before Go candidates.
- `cost_statistics` becomes the ninth non-Go modular IO/read model implementation pilot.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- State-machine definitions do not change; this uses existing `analysis-closed` semantics.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable for selection | No cost attribution, project scope or amount rule changes in this analysis slice. |
| 2. Service-layer tests | Applicable to next slice | Repository port extraction should add service/repository boundary tests. |
| 3. API contract tests | Not applicable for selection | No HTTP behavior changes in this analysis slice. Next implementation should keep existing API contract tests green. |
| 4. Read model/cache/background job tests | Applicable to next slice | Existing SQL runtime/freshness/parent aggregate tests must remain green; port guard should be added. |
| 5. Frontend component and interaction tests | Not applicable for selection | No frontend behavior changes in this analysis slice. |
| 6. End-to-end business-flow integration tests | Not applicable for selection | No runtime flow changes. Existing cost statistics E2E evidence informs priority. |
| 7. Existing feature regression tests | Applicable to next slice | Cost statistics has broad downstream import/relation/settings regressions; next implementation must pick targeted regression checks. |

## Verification

This slice is analysis/accounting only. Required verification:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Next Boundary

`read-models:cost-statistics-repository-port-extraction`

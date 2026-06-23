# Read Model Pending Invoice Refresh Freshness Operation Barrier Audit

**Date:** 2026-06-24
**Boundary:** `read-models:pending-invoice-refresh-freshness-operation-barrier-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit `pending_invoice` freshness, force-refresh, special scope and operation barrier behavior after repository port extraction. This slice does not change runtime behavior; it classifies the next narrow implementation gaps that must stay ahead of Go/Fiber/Go Worker admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-repository-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-and-oa-pending-payment-contract.md`
- `docs/modules/read-models/README.md`
- `docs/modules/pending-invoices/README.md`
- `docs/modules/pending-invoices/tests.md`
- `docs/modules/pending-invoices/implementation-notes.md`
- `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
- `backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_read_model_refresh_gateway.py`
- `tests/test_read_model_manifest.py`
- `tests/test_read_model_slo_smoke.py`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_pending_invoice_api.py`
- `tests/test_workbench_write_characterization.py`
- `tests/test_workbench_relation_repository.py`

## What Is Already Protected

- `PendingInvoiceReadModelService.rows(...)` fail-closes when the SQL read payload is missing, schema-stale or source-version stale; stale rows are returned as `read_model_status=refreshing` with stale reasons rather than `fresh`.
- Expected source versions include settings, parser/sync versions, bank detail source versions and workbench relation source versions when the repository exposes the source-version methods.
- `ReadModelRefreshGateway` is the enqueue boundary; pending invoice API miss/source/schema refreshes go through the scope policy registry before durable queue enqueue.
- `pending_invoice` manifest records:
  - `all_scope_semantics=forbidden_bare_all`
  - `force_refresh_contract=gateway_force_refresh_with_page_first_screen_scope`
  - `operation_barrier_contract=app_status_registry_target`
  - the pending invoice repository port method set.
- Runtime worker registration has a dedicated `pending-invoice` worker and legacy `search-pending` auxiliary consumer.
- `SearchPendingReadModelRefreshService` expands base pending invoice scopes such as `expense:all` or `income:cash_income` into month shards before projection rebuild, and rebuilds only month shards directly.
- SLO smoke explicitly adds `expense:all` as a page-first-screen scope for pending invoice unless an explicit override is provided.
- Workbench relation writers already avoid global bare `all` for pending invoice downstream refresh metadata and enqueue month-scoped pending invoice scopes when relation changes have bank-month evidence.

## Implementation Gaps Found

### P0 Gap: Scope Policy Does Not Validate Filter Allowlist

`read_model_scope_policy._validate_pending_invoice_scope_key(...)` validates:

- direction is `expense` or `income`
- shape is `direction:filter` or `direction:filter:YYYY-MM`
- optional month shape is valid

It does not validate that `filter` is in the supported filter set for that direction. As a result, a scope such as `expense:not_a_real_filter` can pass `ReadModelRefreshGateway` and reach the runtime worker before `SearchPendingSqlProjectionBuilder` rejects it.

Required next boundary:

- `read-models:pending-invoice-scope-policy-filter-allowlist`

Expected implementation:

- import or duplicate only the authoritative pending invoice filter constants needed by scope policy without creating a circular dependency;
- reject invalid `expense` filters and invalid `income` filters in gateway scope validation;
- add `tests/test_read_model_refresh_gateway.py` coverage proving valid aggregate/month scopes still pass and invalid filter groups never enqueue.

### P1 Gap: Mutation Response Freshness Target Contract Is Not Uniform

Pending invoice write-adjacent operations enqueue refreshes through lifecycle/finalizer paths, and rules update returns `read_model_status=refreshing`. Attach-existing and income-status mutation responses expose `affected_months`, but the reviewed route/application response surfaces do not provide a uniform `freshness_targets` contract equivalent to the newer write-operation barrier pattern.

This is not safe to change inside the audit slice because it may affect frontend/API expectations. It should be a separate contract audit/implementation boundary after the scope policy allowlist.

Candidate boundary after P0:

- `read-models:pending-invoice-mutation-freshness-target-contract`

Expected work:

- audit all pending invoice mutation responses and frontend callers;
- decide whether to add `freshness_targets` or document the current page-local barrier/refetch contract;
- if adding targets, test API shape, frontend behavior and operation barrier target scopes.

## Non-Gaps / Decisions

- `expense:all` and `income:<filter>` base scopes are valid refresh commands for pending invoice; they are not the forbidden global `all`.
- Month shard projection remains `direction:filter:YYYY-MM`.
- `list_pending_invoice_scope_shards(...)` stays outside `PendingInvoiceReadModelRepositoryPort` because it enumerates source fact months, not read-model repository rows.
- Go/Fiber/Go Worker admission remains blocked. The scope policy and mutation freshness target gaps are non-Go modular IO boundaries.

## Legacy Classification

| Surface | Classification | Reason |
| --- | --- | --- |
| Global `pending_invoice:all` | invalid legacy scope | Scope policy rejects it; runtime ops may still need to inspect old dead letters, but new producers must not enqueue it. |
| `direction:unknown_filter` | implementation gap | Currently accepted by gateway and rejected later by projection; must fail at scope boundary. |
| Base `expense:all` / `income:cash_income` | valid fan-out command | Worker expands to month shards and completes the base dirty scope. |
| Mutation responses without uniform `freshness_targets` | contract gap candidate | Existing operations enqueue refreshes, but operation barrier response contract is not uniform. |

## State Machine Impact

No global state machine definition changed.

Queue transition:

- `read-models:pending-invoice-refresh-freshness-operation-barrier-audit`: `pending` -> `analysis-closed`
- `read-models:pending-invoice-scope-policy-filter-allowlist`: inserted as next `pending`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Category Decision

1. Business core unit tests: not applicable; this audit does not change business status/filter semantics.
2. Service-layer tests: applicable as analysis; existing service and gateway tests were reviewed.
3. API contract tests: reviewed; no API shape changed in this slice.
4. Read model/cache/background job tests: applicable; reviewed scope policy, worker expansion, SLO smoke and SQL runtime tests.
5. Frontend component and interaction tests: not applicable for this audit slice.
6. End-to-end business-flow integration tests: not applicable for this audit slice.
7. Existing feature regression tests: applicable; no tests changed, but next implementation must update read model refresh gateway regression tests.

## Verification

Audit-only verification:

```bash
git status --short --branch
git pull --ff-only origin dev
rg -n "pending_invoice|PendingInvoice|operation_barrier|operation_projection|freshness_targets|read_model_scope_keys|force_refresh|enqueue_refreshes_for_scope|scope_key\\(" backend/src/fin_ops_platform/services backend/src/fin_ops_platform/app tests
```

Final slice verification should run:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only the audit/accounting slice is closed. `pending_invoice` remains `implementation-gap-open`; the next executable boundary is scope policy filter allowlist enforcement.

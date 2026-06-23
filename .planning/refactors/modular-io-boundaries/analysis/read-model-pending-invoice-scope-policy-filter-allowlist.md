# Read Model Pending Invoice Scope Policy Filter Allowlist

**Date:** 2026-06-24
**Boundary:** `read-models:pending-invoice-scope-policy-filter-allowlist`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Tighten the `pending_invoice` refresh scope boundary so unsupported direction/filter combinations fail at `ReadModelRefreshGateway` validation and never reach runtime worker or SQL projection code.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-refresh-freshness-operation-barrier-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-repository-port-extraction.md`
- `docs/modules/read-models/README.md`
- `docs/modules/pending-invoices/README.md`
- `docs/modules/pending-invoices/tests.md`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
- `tests/test_read_model_refresh_gateway.py`
- `tests/test_search_pending_sql_runtime.py`

CodeGraph impact check:

- `_validate_pending_invoice_scope_key` affects only the pending invoice scope policy validator path.

## Implementation

Added direction-specific pending invoice filter allowlists in `read_model_scope_policy.py`:

- expense: `all`, `requires_invoice`, `bank_statement_as_invoice`, `no_invoice_required`
- income: `all`, `requires_invoice`, `no_invoice_required`, `cash_income`

The gateway now rejects unsupported filters such as:

- `expense:cash_income`
- `expense:unknown_filter:YYYY-MM`
- `income:bank_statement_as_invoice`
- `income:unknown_filter:YYYY-MM`

Valid aggregate and month scopes continue to pass and dedupe through `ReadModelRefreshGateway`.

## Scope Decision

The allowlist is intentionally enforced at the scope policy boundary, not in the worker or SQL projection. Projection-level validation remains as a secondary guard, but invalid scope producers should fail before durable queue enqueue.

The constants are local to `read_model_scope_policy.py` to avoid importing `pending_invoice_service.py` from the shared scope policy module and creating a circular import through `read_model_refresh_gateway.py`.

## Legacy Classification

| Surface | Classification | Reason |
| --- | --- | --- |
| `expense:cash_income` | removed from valid pending invoice refresh input | Cash income is income-only. |
| `income:bank_statement_as_invoice` | removed from valid pending invoice refresh input | Bank statement as invoice is expense-only. |
| Unknown filter groups | removed from valid pending invoice refresh input | They are not page/read model contracts and must not enter durable queue. |
| Projection filter validation | retained defense-in-depth | Worker/projection still reject invalid filters if legacy rows already exist. |

## State Machine Impact

No state definition changed.

Queue transition:

- `read-models:pending-invoice-scope-policy-filter-allowlist`: `pending` -> `implementation-closed`
- Next queue item: `read-models:pending-invoice-mutation-freshness-target-contract`
- `pending_invoice` remains `implementation-gap-open`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no pending invoice business status/filter meaning changed.
2. Service-layer tests: applicable; `ReadModelRefreshGateway` tests cover the shared scope policy service boundary.
3. API contract tests: not applicable; no HTTP API shape or status code changed.
4. Read model/cache/background job tests: applicable; gateway tests now prove invalid pending invoice refresh scopes never enqueue.
5. Frontend component and interaction tests: not applicable; no frontend behavior changed.
6. End-to-end business-flow integration tests: not applicable for this narrow scope policy change.
7. Existing feature regression tests: applicable; existing valid pending invoice scope tests were expanded to prove valid scopes still enqueue.

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/read_model_scope_policy.py tests/test_read_model_refresh_gateway.py
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_refresh_gateway.ReadModelRefreshGatewayTests.test_pending_invoice_policy_accepts_aggregate_base_and_month_scopes tests.test_read_model_refresh_gateway.ReadModelRefreshGatewayTests.test_pending_invoice_policy_rejects_bare_month_and_invalid_direction tests.test_read_model_refresh_gateway.ReadModelRefreshGatewayTests.test_pending_invoice_policy_rejects_global_all_scope tests.test_read_model_refresh_gateway.ReadModelRefreshGatewayTests.test_pending_invoice_policy_rejects_unsupported_filter_groups -v
```

Final slice verification must additionally run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_refresh_handler_expands_pending_filter_scope_into_month_shards tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_refresh_handler_rebuilds_pending_filter_month_shard -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only the scope policy filter allowlist slice is closed. `pending_invoice` remains open because mutation freshness target contract work is still pending.

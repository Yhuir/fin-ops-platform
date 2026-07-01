# P004 Implementation Report - Performance And Read Model I/O

Date: 2026-07-01

## Goal

Reduce `bank-flow-rule-batches` page/API latency by eliminating unnecessary all-scope refreshes and tightening read model I/O while keeping public API behavior stable.

## Path Analysis

| Path | Before | After |
| --- | --- | --- |
| `GET /api/bank-flow-rule-batches` | Read model list with stale checks; fallback refresh if repository missing. | Same API behavior. Stale checks now use relation-mode source versions. |
| `GET /api/bank-flow-rule-batches/<batch_id>` | Always synchronous `scope_key=all` refresh before lookup. | Uses current bank-flow batch storage first; only missing batch falls back to `all`. |
| `POST /api/bank-flow-rule-batches/<batch_id>/withdraw` | Always synchronous `scope_key=all` refresh before withdraw. | Uses current bank-flow batch storage first; only missing batch falls back to `all`. |
| `POST /api/bank-flow-rule-batches/reset-submitted` | Preflight `all` refresh, then post-withdraw `all` refresh. | No preflight `all`; post-withdraw refresh is limited to affected month scopes, with `all` only when month cannot be determined. |
| Worker refresh | Bank-flow skipped unchanged optimization. | Bank-flow uses `bank_flow_rule_batch_source_versions_summary(...)` and skips rebuild/publish when unchanged. |
| `PUT /api/bank-flow-rule-batches/tag-rules` | Enqueue `all` refresh. | Still `all`, explicitly documented because rule changes can affect all active relations. |

## Implemented

- Added missing-batch-only refresh guard in `BankFlowRuleBatchApplicationService`.
- Changed reset submitted refresh from all-scope to affected-month scoped refresh.
- Made `unchanged_read_model_scope_result(...)` relation-mode aware.
- Enabled unchanged-source-version skip for bank-flow worker refresh.
- Updated module docs with performance/read-model I/O contracts.

## Tests Added Or Updated

- `tests/test_bank_flow_rule_batch_application_service.py`
  - detail skips all refresh when batch is present.
  - detail falls back to all refresh when batch is missing.
  - withdraw skips all refresh when batch is present.
  - withdraw falls back to all refresh when batch is missing.
  - reset refreshes affected months without preflight all refresh.
  - unchanged read model scope uses bank-flow source-version summary and avoids row scan.

## Verification

```bash
PYTHONPATH=backend/src:. python3 -m pytest tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_routes.py tests/test_bank_flow_rule_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_postgres_repositories_boundaries.py -q
```

Result: `76 passed, 5 warnings`.

## Seven Test Categories

- Business core unit tests: not directly applicable; no business rules changed.
- Service-layer tests: covered for detail/withdraw/reset refresh orchestration.
- API contract tests: covered through bank-flow routes and no-OA integration regressions.
- Read model/cache/background job tests: covered for source-version summary skip and producer/read-model regressions.
- Frontend component tests: not applicable in P004 because UI behavior did not change.
- End-to-end business-flow integration tests: covered at backend API integration level for reset/rebaseline; browser E2E not rerun.
- Existing feature regression tests: no-OA read model refresh and repository boundaries were rerun.

## Remaining Risks

- `tag-rules` save still enqueues `all`; this is correct until there is a reliable affected-scope index for active relation/tag changes.
- Frontend page state remains monolithic in `BankFlowRuleBatchPage.tsx`.
- Full browser E2E and production timing measurements were not run in P004.

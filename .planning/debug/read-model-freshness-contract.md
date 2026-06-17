---
status: verified
trigger: "User reports repeated stale read model failures and asks whether every page can be guaranteed to use fresh read models."
created: 2026-06-17
updated: 2026-06-17
---

# Read Model Freshness Contract

## Symptoms

- User repeatedly reproduced stale read model behavior after page-level fixes.
- `turnover_ledger` closure could still fail with "银行流水状态已变化，请刷新后重试。" after selecting balanced income/expense rows.
- User asks for an architecture-level guarantee that pages cannot read stale read models as fresh.

## Current Focus

- hypothesis: Shared and legacy read model query gates can return `fresh` when no expected freshness contract is supplied, or when actual schema metadata is missing.
- test: Add unit tests and static guard proving query gates fail closed without expected schema/source versions and treat missing schema metadata as refreshing.
- expecting: Missing/empty expected versions raise at query boundary; missing actual schema/version proof returns refreshing and enqueues a refresh.
- next_action: Implement fail-closed freshness contract in shared gateway and self-managed read model services.
- reasoning_checkpoint: CodeGraph and source inspection show `ReadModelQueryGateway.load()` accepted `expected_source_versions=None`, and `resolve_read_model_freshness()` only flagged schema mismatch when both expected and actual schema values existed.
- tdd_checkpoint: Add failing tests before implementation.

## Evidence

- 2026-06-17: `ReadModelQueryGateway.load()` normalizes missing `expected_source_versions` to `{}`. Empty expected versions make `source_version_mismatch_reasons()` return no mismatch.
- 2026-06-17: `_cached_payload_passes_fresh_gate()` returned true when an expected schema was set but cached schema metadata was missing.
- 2026-06-17: `resolve_read_model_freshness()` only returned `schema_mismatch` when both expected and actual schema versions were non-empty.
- 2026-06-17: `PendingInvoiceReadModelService` and `OaPendingPaymentReadModelService` had fallback source version providers returning `{}`, so misconfiguration could disable source freshness checks.
- 2026-06-17: Static AST inventory found legacy route/service/repository paths that directly marked `read_model_status=fresh` or directly called `source_version_mismatch_reasons(...)` outside `ReadModelQueryGateway`; these paths need architecture classification rather than page-by-page fixes.

## Eliminated

- hypothesis: The remaining issue is only a turnover ledger row-version bug.
  reason: The code allows any read model caller that omits expected versions to treat old source metadata as fresh; the failure mode is architectural.

## Resolution

- root_cause: Read model query boundaries accepted missing expected freshness contracts and missing actual schema metadata. Empty expected source versions disabled source mismatch detection, and missing actual schema was treated as compatible when an expected schema existed. Some self-managed read model services also defaulted to empty source version providers.
- fix: `ReadModelQueryGateway` now requires `expected_source_versions` or `expected_schema_version`; missing actual schema metadata returns schema mismatch/refreshing; Redis cache hits require schema proof when expected. Self-managed read model services now require non-empty source version contracts, and Cost Statistics repository returns `schema_version` in SQL views.
- hardening: `tests/test_read_model_architecture_guards.py` now maintains an explicit direct-fresh allowlist with counts and reasons, and rejects any direct `source_version_mismatch_reasons(...)` call whose expected side is not guarded by `require_expected_source_versions(...)` or an approved fail-fast service method. Legacy helpers in `server.py`, `NoOaBankBatchApplicationService`, and `TaxOffsetPlanService` were tightened to use the shared fail-fast expected contract.
- verification: `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness tests.test_read_model_query_gateway tests.test_read_model_architecture_guards tests.test_cost_statistics_sql_runtime tests.test_tax_offset_sql_runtime -v`; `PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime -v`; `PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_api -v`; `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_source_versions tests.test_turnover_ledger_service -v`; `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`; `PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_read_model_refresh tests.test_runtime_worker_read_model_refresh_scopes -v`; `bash scripts/verify.sh docs`; `git diff --check`.
- files_changed: backend/src/fin_ops_platform/services/read_model_freshness.py; backend/src/fin_ops_platform/services/read_model_query_gateway.py; backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py; backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py; backend/src/fin_ops_platform/services/input_invoice_usage_read_model_detail_service.py; backend/src/fin_ops_platform/services/postgres_repositories/read_models.py; tests/test_read_model_freshness.py; tests/test_read_model_query_gateway.py; tests/test_read_model_architecture_guards.py; tests/test_cost_statistics_sql_runtime.py; docs/modules/read-models/*; docs/operations/runtime-worker-governance.md; docs/app-architecture/runtime-and-ownership.md.

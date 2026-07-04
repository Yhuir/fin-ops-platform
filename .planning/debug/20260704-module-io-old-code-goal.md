# 2026-07-04 Module I/O and Legacy Path Goal State

## Objective

Use the GSD controller workflow, with Grill Me scrutiny and Ponytail simplicity, to fix the current workbench withdraw preview defect first, then audit module I/O boundaries, read models, imports, drawer UI consistency, and isolated legacy paths across the requested pages.

## Hard Constraints

- Do not patch symptoms in the UI when the real defect is an I/O or relation boundary problem.
- Keep one authoritative relation write path for workbench confirm and withdraw operations.
- Keep read-side pages on fresh read models or explicit stale/refreshing states.
- Remove proven unused or isolated legacy module code instead of keeping fallback paths that can pollute current flows.
- Update persistent module boundary docs under `docs/modules/**` and `docs/architecture/module-boundaries/**` whenever a boundary, I/O contract, read model contract, file ownership, or legacy-deletion condition changes.
- Use minimal changes that preserve current architecture direction; avoid broad rewrites before a failing contract is isolated.

## Current Stage

Stage 1 is the active implementation stage:

- Defect: workbench withdraw preview shows "operation after" as the same OA + bank + invoice row as "operation before".
- Expected behavior: after withdraw, rows not restored into a valid previous relation must be shown as separate rows, matching the actual after relation state.
- Acceptance: backend preview payload and UI preview both represent the same canonical after relation state; no old `case_id` or historical relation snapshot may synthesize a row that is not really restored.

## Directly Affected Modules

- `reconciliation-workbench`
- `workbench-relations`
- `read-models` if relation projections or freshness contracts change
- `runtime-workers` only if read model dirty scopes or worker refresh contracts change

## Upstream/Downstream Modules For Later Audit

- `cost-statistics`
- `bank-transactions`
- `oa-payments`
- `invoice-management` and invoice import/use/collection pages
- batch rules/accounting and external receivables/payables modules listed in `docs/architecture/module-boundaries/inventory.md`

## Grill Me Checks For Stage 1

- What is the single source of truth for withdraw preview: persisted active relation plus provably restorable relation history, not row display metadata.
- What crosses the I/O boundary: canonical relation row ids, preview id, expected versions, operation type, affected scopes, and explicit before/after relation groups.
- What must not cross the boundary: UI-selected display ids as durable ids, stale `case_id` row metadata as proof of relation membership, or legacy fallback relation writers.
- What proves the fix: a regression test where the current active relation contains OA + bank + invoice, but the after state contains no valid restored relation, and the preview returns separate after rows.

## Ponytail Checks For Stage 1

- Prefer fixing the shared preview payload builder or relation preview service over adding UI special cases.
- Reuse existing canonical row alias helpers and relation grouping helpers.
- Add one focused regression test before broadening scope.
- Do not introduce a new relation abstraction unless the current shared helper cannot express the contract.

## Legacy Path Candidate Inventory

Initial candidates to audit after Stage 1:

- legacy workbench direct relation service call sites bypassing `WorkbenchRelationCommandService`
- duplicated workbench preview/grouping code in backend route handlers or UI mappers
- page-local read model reconstruction that bypasses shared read model freshness/status contracts
- import code paths that write facts without emitting the documented dirty scopes
- stale UI drawer/detail implementations that duplicate row normalization instead of consuming the page read model contract

## Next Bounded Action

Trace the withdraw preview backend path, identify where the "after" groups are assembled, add or update the failing regression test, make the smallest shared-boundary fix, then run targeted backend and browser validation.

## Stage 1 Result

Status: implemented and locally verified.

Root cause:

- Withdraw preview/submit restored relation snapshots were filtered before row id alias canonicalization.
- Historical relation facts could contain an OA source id such as `oa-exp-69fab21659b12d7d42a50a45` while the current Workbench row id was `oa-exp-2156`.
- The raw row-set comparison treated the historical snapshot as different, then the preview payload canonicalized it later and rendered the same OA + bank + invoice group as the "after" state.

Boundary fix:

- `row_id_aliases` is now explicit command I/O from `WorkbenchWriteFacade` into `WorkbenchRelationCommandService` and `WorkbenchPairRelationService`.
- Pair service restore filtering compares alias-aware canonical row sets before deciding that a historical snapshot is restorable.
- Facade also validates canonicalized after/restored relations at the HTTP boundary so polluted adapters or test doubles cannot synthesize an after group equal to the active relation.

Verification:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_service.WorkbenchPairRelationServiceTests.test_withdraw_ignores_restorable_snapshot_with_same_canonical_alias_row_set -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_withdraw_preview_filters_same_canonical_alias_after_relation tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_withdraw_link_canonicalizes_legacy_oa_source_ids_and_drops_same_row_restore tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_withdraw_preview_after_groups_unrestored_bank_invoice_rows_individually -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_service -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_command_service -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_command_repository_adapter tests.test_workbench_relation_repository -v`
- `npm run e2e -- e2e/workbench-withdraw-flow.spec.ts --project=chromium`

Persistent docs updated:

- `docs/modules/workbench-relations/boundary-io.md`
- `docs/modules/reconciliation-workbench/boundary-io.md`
- `docs/modules/reconciliation-workbench/tests.md`

## Stage 2 Legacy Module Audit

Status: in progress.

Audit method:

- Grill Me: every old/legacy/fallback candidate must answer who calls it, whether it can write facts, whether it can publish read model freshness, and what test/doc guard prevents it from re-entering the normal path.
- Ponytail: delete only proven-dead pollution points; classify production-reachable compatibility or repair tools instead of broad rewrites.

Current classifications:

- `LegacyWorkbenchActionRoutes`: retain as compat-only old `/workbench/actions/*` route owner. It is still wired from `Application._handle_legacy_workbench_action(...)`, and static guards require quarantine. It must not call modern relation command/read model refresh paths.
- `WorkbenchLegacyApiSqlReadProvider`: retain as production SQL read-runtime fail-closed provider for legacy `/api/workbench` payload compatibility. It may enqueue refresh/read status, but must not fall back to raw builder before the SQL runtime guard.
- `WorkbenchActionService` / `WorkbenchApiRoutes`: retain as old thin action wrapper while legacy API tests still exercise it. It is not the modern relation write boundary; deletion requires separate API route deprecation/migration.
- no-OA legacy relation migration/repair services: retain. Guards require command-service backed relation writes and forbid direct pair-service fallback.
- ETC historical repair/migration/backfill tools: retain as tool/ops surfaces with dry-run/owner conditions; not page read/write normal path.
- `file_object_migration.py`: retain current object storage helper only; legacy GridFS reader/service are already guarded as removed.

Deleted pollution point:

- Removed unused `Application._bank_details_relation_tag_workbench_read_model(...)`. It had no callers and could rebuild a raw Workbench payload for BankDetails relation tags, bypassing the current `BankDetailsRelationTagProjectionService -> WorkbenchRelationReadFacade.get_by_row_ids(...)` boundary.

Guard/docs updated:

- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_bank_details_relation_tags_only_read_relation_distribution_facade` now fails if the removed helper returns or if BankDetails relation tags read raw Workbench payload.
- `docs/modules/bank-details/boundary-io.md`
- `docs/modules/bank-details/tests.md`

## Stage 3 Cost Statistics Bank Tag View

Status: implemented locally; broader module audit still in progress.

Grill Me conclusion:

- Question: should `按流水标签类型` read bank details directly, or be a cost statistics read model view?
- Answer: it must be a cost statistics read model view. The page I/O boundary is fresh `cost_statistics` explorer payload, not another page's read model.
- Question: what field crosses the boundary?
- Answer: `time_rows.bank_tag_code`, `bank_tag_label`, `bank_tag_primary_label`, `bank_tag_sub_label`, and `bank_tag_label_path`.
- Question: how do parent scopes avoid losing tag fields?
- Answer: month shard projection writes the fields into `cost_statistics_rows.payload`; parent scope aggregation reads them back from materialized rows.

Ponytail conclusion:

- No new endpoint or service for bank-tag statistics.
- Reuse existing explorer `time_rows`, existing `CostExplorerList`, and existing table component.
- Add one small pure normalization helper so SQL projection and non-SQL fallback emit the same shape.

Implementation:

- Added `cost_statistics_bank_tags.bank_tag_context_from_row(...)` as the single normalization helper for Workbench bank row effective/category payload.
- Bumped `COST_STATISTICS_READ_MODEL_SCHEMA_VERSION` to force fresh projection for the new payload contract.
- SQL projection, parent aggregation, fallback service, API mapper, mock API, and frontend page now preserve the same `bank_tag_*` fields.
- Cost statistics page now has a `bankTag` view labeled `按流水标签类型`, placed to the right of `按费用类型`, with three lanes: `主标签 / 子标签 / 流水`; the first two lanes use a 1fr + 1fr layout and the transaction lane uses 2fr.

Verification so far:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_cost_statistics_sql_projection_rebuilds_active_all_from_materialized_shard_rows tests.test_cost_statistics_service.CostStatisticsServiceTests.test_project_statistics_returns_time_amount_and_expense_fields tests.test_cost_statistics_service.CostStatisticsServiceTests.test_transaction_detail_includes_bank_and_oa_cost_fields -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_service tests.test_cost_statistics_sql_runtime tests.test_cost_statistics_api tests.test_cost_statistics_read_model_service tests.test_cost_statistics_runtime_service -v`
- `cd web && npm run build`
- `cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx`

Additional Grill Me finding:

- `tests.test_cost_statistics_api.CostStatisticsApiTests.test_cost_statistics_uses_oa_detail_fields_after_manual_confirm_link` was using mixed boundaries: legacy `WorkbenchApiRoutes`, an `Application`-scoped old `WorkbenchActionService` bound to a different query service, imported bank rows that the legacy query service cannot own, and then modern `/api/cost-statistics` read model reads.
- Fixed the test to make every I/O explicit: legacy route fixture owns only its own old Workbench rows, a test-local group helper converts old `paired.oa/bank` shape to modern `paired.groups`, cost statistics builds the explorer read model, and the API reads that read model. No production `/api/workbench/actions/confirm-link` fallback was added.

Persistent docs updated:

- `docs/modules/cost-statistics/README.md`
- `docs/modules/cost-statistics/boundary-io.md`
- `docs/modules/cost-statistics/tests.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`

## Stage 4 Cross-Module I/O And Old Code Audit

Status: completed for this pass.

Modules scanned:

- `cost-statistics`, `bank-details`, `oa-pending-payments`, `bank-flow-rule-batches`, `batch-accounting`, `turnover-ledger`, `etc-tickets`, `tax-offset`, `input-invoice-usage`, `output-invoice-collections`, `pending-invoices`, `imports-bank-transactions`, `imports-invoices`, `read-models`, `canonical-facts`, `workbench-relations`, `reconciliation-workbench`.

Grill Me questions applied to each module:

- What is the read fact source: SQL read model, active Workbench generation, canonical fact table, or legacy/local compatibility source?
- What is the write boundary: command service/UoW/facade, import job, relation command, or settings service?
- Can any page or route return stale/live fallback as if fresh?
- Can any legacy route/service write relation facts, canonical facts, read model tables, dirty scopes, or outbox directly?
- Is the old code production route, compatibility shim, migration/repair tool, or test-only fixture?

Ponytail conclusion so far:

- Do not delete migration/repair/tools simply because they contain `legacy`; deletion requires proof that no production runbook, guard, or tests still rely on the tool.
- Do delete or quarantine old code that can enter normal page/API/worker paths and bypass freshness or command boundaries.
- Current fresh finding beyond Stage 2 deletion was a test-side pollution in `test_cost_statistics_uses_oa_detail_fields_after_manual_confirm_link`: the test mixed legacy Workbench route rows, import-service rows, and modern cost-statistics read model reads. It has been converted to explicit fixture I/O.

Current classification:

- `bank-flow-rule-batches`: closed modular boundary; no production no-OA imports or `selected_tag_codes` write path reintroduced.
- `cost-statistics`: partial; current new bank-tag feature is correctly on `cost_statistics` read model. Remaining compat is local/non-SQL fallback and workbook helpers, not a new page I/O.
- `bank-details`: partial; relation tag raw Workbench helper was removed in Stage 2. Remaining local/on-demand category provider is documented as legacy/local and guarded.
- `oa-pending-payments`, `input-invoice-usage`, `output-invoice-collections`, `tax-offset`, `pending-invoices`: high-confidence read model boundaries with route owners and nonfresh tests; remaining compatibility methods must stay behind SQL-read-model provider/fresh gate and must not fake fresh.
- `batch-accounting`, `turnover-ledger`, `etc-tickets`, `workbench-relations`, `reconciliation-workbench`: legacy/repair surfaces exist but are guarded or documented; no additional deletion candidate is proven safe yet.
- `imports-bank-transactions` / `imports-invoices`: import confirmation must enqueue/fan-out downstream read models; no direct page read-model writes found in the scanned boundary docs.

Static guard coverage observed:

- `tests/test_platform_runtime_boundary_guards.py` guards old ETC API removal, canonical fact legacy source removal baselines, legacy Workbench action quarantine, cost-statistics route owner not calling old secondary service paths, OA pending live-read fallback, batch-accounting direct pair write fallback, turnover direct pair write fallback, Workbench confirm/cancel direct pair write fallback, ETC repair direct relation write fallback, and row-detail legacy fallback quarantine.

## Stage 5 OA Pending Payment Detail Drawer UI

Status: implemented and verified.

Grill Me conclusion:

- Question: should OA pending detail drawer introduce a new detail API or read another module's detail read model?
- Answer: no. The existing `fetchOaPendingPaymentDetail(...)` / `oa_pending_payment` detail payload is the I/O boundary. This is a presentation-only layout change.
- Question: how to avoid over-abstracting?
- Answer: reuse `InputInvoiceUsageDetailDrawer` and add one optional `layout="table"` prop. Default remains grid for existing pages.

Implementation:

- `InputInvoiceUsageDetailDrawer` now supports `layout="table"` and renders all visible sections in one two-column detail table.
- `OaPendingPaymentsPage` passes `layout="table"` for OA/bank/invoice/relation detail drawer.
- Added CSS for stable table layout and long-text wrapping.
- Updated `docs/modules/oa-pending-payments/tests.md` with the drawer layout regression.

Verification:

- `cd web && npm test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx src/test/OaPendingPaymentsPage.test.tsx`
- `cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/WorkbenchApiRuntimePath.test.ts src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx src/test/OaPendingPaymentsPage.test.tsx`
- `cd web && npm run e2e -- e2e/oa-pending-payments-flow.spec.ts e2e/cost-statistics-flow.spec.ts e2e/workbench-withdraw-flow.spec.ts --project=chromium`

## Stage 6 Workbench Withdraw UI Read Boundary

Status: implemented and verified.

Root cause:

- The backend withdraw fix made the preview payload correct, but the frontend still allowed `executeWorkbenchActionWithFreshness(...)` to apply a submit response `operationProjection` before the preview dialog closed.
- During the busy preview state, the underlying Workbench could therefore display the post-withdraw open group while the modal still represented an in-progress operation.
- That was a page read I/O pollution: the dialog had a preview snapshot, the mutation had a write response, and the visible Workbench page should only switch from the fresh Workbench read model.

Boundary fix:

- `loadWorkbenchData(...)` now has an explicit `deferStateApply` option, splitting read-model fetch from page-state application.
- `waitForWorkbenchFreshAfterOperation(...)` returns the fresh payload when requested instead of always writing it immediately.
- Withdraw and `split_candidate` preview submits now wait for fresh Workbench read model, then close the preview and apply the fresh payload in one state batch.
- Confirm preview keeps the existing projection fast path because that path is still covered and was not the failing withdrawal contract.

Regression:

- `web/src/test/WorkbenchSelection.test.tsx` asserts that while the withdraw preview is busy, the paired row is still visible underneath and the restored open group is not visible yet.
- `web/e2e/workbench-withdraw-flow.spec.ts` verifies the full browser flow: preview lock, freshness barrier, fresh refetch, then visible open group.

Verification:

- `cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx`
- `cd web && npm run e2e -- e2e/workbench-withdraw-flow.spec.ts --project=chromium`
- `cd web && npm run e2e -- e2e/oa-pending-payments-flow.spec.ts e2e/cost-statistics-flow.spec.ts e2e/workbench-withdraw-flow.spec.ts --project=chromium`
- `cd web && npm run build`
- `bash scripts/verify.sh docs`

Final status:

- All planned implementation phases for this prompt completed locally.
- Remaining legacy paths are classified rather than deleted where they are production-compatible, guarded repair/migration paths, or still exercised compatibility routes.
- One proven dead old helper was removed: `Application._bank_details_relation_tag_workbench_read_model(...)`.

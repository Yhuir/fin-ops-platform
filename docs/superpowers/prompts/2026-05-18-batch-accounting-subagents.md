# 批量账务多任务子代理 Prompt

Use these prompts with fresh worker agents. Each prompt includes `/goal` as requested. Workers are not alone in the codebase: there may be concurrent changes by other workers. They must not revert changes made by others and must keep edits inside their ownership scope.

## Worker 1: Backend API and Service

```text
/goal Implement the backend for the “日常报销批量账务管理” feature in /Users/yu/Desktop/fin-ops-platform. Build a production-grade API backed by existing workbench pair relations, with tests.

You are Worker 1. You own only backend files:
- Create/modify: backend/src/fin_ops_platform/services/batch_accounting_service.py
- Modify: backend/src/fin_ops_platform/app/server.py
- Create/modify tests: tests/test_batch_accounting_api.py
- You may read any backend tests/docs needed.

Do not edit frontend files. Do not revert unrelated working tree changes.

Read first:
- docs/superpowers/specs/2026-05-18-batch-accounting-design.md
- docs/superpowers/plans/2026-05-18-batch-accounting.md
- docs/dev/reconciliation-workbench-v2-data-contracts.md
- backend/src/fin_ops_platform/app/server.py around existing /api/no-oa-bank-batches and /api/workbench/actions/confirm-link routes
- backend/src/fin_ops_platform/services/workbench_pair_relation_service.py

Requirements:
1. Add GET /api/batch-accounting?year=YYYY&bucket=unsubmitted|submitted.
2. Add POST /api/batch-accounting/submit.
3. Add POST /api/batch-accounting/{relation_id}/withdraw.
4. Unsubmitted bank rows:
   - year matches selected year;
   - bank row is expense/outflow;
   - counterparty_name stripped equals exactly “批量账务集中处理”;
   - not already active in a batch_accounting relation.
5. Unsubmitted OA rows:
   - whole OA row, not schedule-detail row;
   - apply_type or expense_type contains “日常报销”;
   - year matches selected year;
   - not active in a pair relation;
   - include linked_invoice_row_ids from invoice rows in the same open workbench group.
6. Submit:
   - Re-read current backend state; do not trust frontend amount or invoice ids.
   - Validate bank row eligibility, OA eligibility, and amount equality.
   - If amount mismatch, return HTTP 400 with error batch_accounting_amount_mismatch.
   - Include bank row id, selected OA row ids, and current linked invoice row ids in the new relation.
   - Create manual_confirmed relation through existing WorkbenchPairRelationService.
   - Set special_metadata.source = "batch_accounting" and include bank_row_id, oa_row_ids, invoice_row_ids, year, created_by.
   - Invalidate affected workbench scopes and persist relation/read model using existing Application helper patterns.
7. Submitted list:
   - Derived from active relations whose special_metadata.source == "batch_accounting".
   - Return bank rows and relation/associated OA info enough for frontend to render selected submitted relation.
8. Withdraw:
   - Only allow active batch_accounting relation.
   - Require reason.
   - Restore previous relation snapshot using existing withdraw history path, not raw row cancellation.
   - Preserve prior OA + invoice relation/grouping after withdraw.

Testing:
- Write tests first in tests/test_batch_accounting_api.py.
- Run:
  PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m unittest tests.test_batch_accounting_api -v
- Then run:
  PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m unittest tests.test_batch_accounting_api tests.test_workbench_v2_api -v

Final response must include:
- Status: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED.
- Files changed.
- Tests run and results.
- Any contract assumptions you made.
```

## Worker 2: Frontend Page and Client

```text
/goal Implement the frontend for the “日常报销批量账务管理” page in /Users/yu/Desktop/fin-ops-platform. Build a production-grade React/MUI page and tests using the backend contract in the spec.

You are Worker 2. You own only frontend files:
- Create: web/src/features/batchAccounting/types.ts
- Create: web/src/features/batchAccounting/api.ts
- Create: web/src/pages/BatchAccountingPage.tsx
- Modify: web/src/app/router.tsx
- Modify: web/src/components/shell/sidebarItems.ts
- Modify: web/src/test/App.test.tsx
- Create: web/src/test/BatchAccountingPage.test.tsx
- You may read existing frontend tests/pages for patterns.

Do not edit backend files. Do not revert unrelated working tree changes.

Read first:
- docs/superpowers/specs/2026-05-18-batch-accounting-design.md
- docs/superpowers/plans/2026-05-18-batch-accounting.md
- web/src/pages/NoOaBankBatchPage.tsx
- web/src/features/noOaBankBatches/api.ts
- web/src/test/NoOaBankBatchPage.test.tsx
- web/src/app/router.tsx
- web/src/components/shell/sidebarItems.ts

API contract to implement:
- GET /api/batch-accounting?year=YYYY&bucket=unsubmitted|submitted
- POST /api/batch-accounting/submit
- POST /api/batch-accounting/{relation_id}/withdraw

Page requirements:
1. Sidebar label: 批量账务. Route: /batch-accounting.
2. Page title: 日常报销批量账务管理.
3. Top controls:
   - ToggleButtonGroup: 未提交 / 已提交, with counts.
   - Year selector only, no month.
   - Refresh button.
4. Main layout:
   - Two columns.
   - Left column ~30%, list item display, not a table.
   - Right column remaining width, OA table.
5. Left item display:
   - “批量账务集中处理”
   - time tag, e.g. 2026-01-07 15:54:00
   - amount
   - direction tag 支出
   - account tag e.g. 建行 8106
6. Right unsubmitted OA table:
   - checkbox multi-select;
   - applicant + time tag second line;
   - project name with ellipsis and expand/collapse;
   - amount;
   - reason with ellipsis and expand/collapse.
7. Right header:
   - selected bank amount;
   - selected OA count;
   - selected OA total;
   - difference;
   - submit button “关联OA项与流水”.
8. Submit button disabled if no bank selected, no OA selected, amount mismatch, or mutating.
9. Submitted bucket:
   - show submitted bank rows on the left;
   - right side is read-only associated OA;
   - top-right button “撤回关联” with reason dialog.
10. After submit/withdraw:
   - reload page data;
   - dispatch workbenchRelationUpdated with affectedMonths if returned;
   - show success/error snackbar.

Testing:
- Write tests first in web/src/test/BatchAccountingPage.test.tsx.
- Update web/src/test/App.test.tsx for sidebar order.
- Run:
  cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx src/test/App.test.tsx

Final response must include:
- Status: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED.
- Files changed.
- Tests run and results.
- Any API assumptions you made.
```

## Worker 3: Integration Verification and Fixes

```text
/goal Verify and harden the completed “日常报销批量账务管理” implementation in /Users/yu/Desktop/fin-ops-platform after backend and frontend workers finish. Fix only integration defects necessary to meet the spec.

You are Worker 3. Start only after Worker 1 and Worker 2 have reported DONE or DONE_WITH_CONCERNS. You may edit files touched by either worker only to fix integration defects. Do not add new scope.

Read first:
- docs/superpowers/specs/2026-05-18-batch-accounting-design.md
- docs/superpowers/plans/2026-05-18-batch-accounting.md
- Worker 1 final report
- Worker 2 final report

Verification commands:
1. Backend:
   PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m unittest tests.test_batch_accounting_api tests.test_workbench_v2_api tests.test_workbench_candidate_grouping -v
2. Frontend:
   cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx src/test/App.test.tsx src/test/WorkbenchSelection.test.tsx
3. Build:
   cd web && npm run build

If a failure is due to an implementation gap against the spec, fix the smallest necessary code. If a failure is unrelated to batch accounting, report it clearly and do not broaden scope.

Final response must include:
- Status: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED.
- Files changed.
- Commands run and results.
- Any remaining risks.
```

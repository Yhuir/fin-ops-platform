# No-OA Bank Batch Tree Collapse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the A+ no-OA bank batch processing solution: three-pane batch UI, concise batch nodes, bank/direction tags in detail rows, bank-split batch contract, and existing workbench collapsed-summary bug fix.

**Architecture:** Keep `NoOaBankBatchService` as the batch fact boundary and `WorkbenchCandidateGroupingService` as the only collapse implementation. The page consumes stable no-OA batch DTOs; SQL projection must propagate no-OA relation metadata so the existing collapse contract can activate.

**Tech Stack:** Python backend services and unittest, React + MUI frontend, Vitest Testing Library, existing workbench read model/projection services.

---

### Task 1: Lock Backend Batch And Collapse Contracts

**Files:**
- Modify: `tests/test_no_oa_bank_batch_service.py`
- Modify: `tests/test_workbench_candidate_grouping.py`
- Modify: `tests/test_workbench_sql_runtime.py`
- Modify: `docs/product-specs/no-oa-bank-batches.md`
- Modify: `docs/product-specs/workbench.md`

- [ ] Add/confirm tests that single-side no-OA batches split by `batch_type + scope_month + account_key`.
- [ ] Add a grouping test proving one-row no-OA groups do not collapse.
- [ ] Add a SQL projection test proving `no_oa_bank_batch` relation metadata reaches bank rows and enables collapse for 2+ rows.
- [ ] Add a workbench API test proving one-row no-OA bank rows still expose `withdraw_no_oa_batch`.
- [ ] Run the new tests and confirm they fail before implementation where expected.

### Task 2: Fix Backend DTO And SQL Projection

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_sql_projection.py`

- [ ] Ensure no-OA detail rows expose `bank_name`, `account_last4`, and `account_key`.
- [ ] Change collapse predicate to require at least 2 bank rows while keeping source-batch identity checks.
- [ ] In SQL projection, copy no-OA relation `special_metadata` and `display_tags` onto each paired bank row.
- [ ] Ensure single-row no-OA bank rows keep `withdraw_no_oa_batch` actions for the existing workbench withdraw flow.
- [ ] Run targeted backend tests.

### Task 3: Implement Three-Pane Frontend

**Files:**
- Modify: `web/src/features/noOaBankBatches/types.ts`
- Modify: `web/src/features/noOaBankBatches/api.ts`
- Modify: `web/src/pages/NoOaBankBatchPage.tsx`
- Modify: `web/src/test/NoOaBankBatchApi.test.ts`
- Modify: `web/src/test/NoOaBankBatchPage.test.tsx`

- [ ] Map bank account fields in no-OA detail rows.
- [ ] Convert the page grid to left category, middle batch list, right transaction detail.
- [ ] Keep left rail unchanged.
- [ ] Make middle batch cards show only time, bank+last4, row count, category, and submit/withdraw actions.
- [ ] Remove the right detail “收/支” column; render direction tag before amount and bank+last4 tag below amount.
- [ ] Run targeted frontend tests.

### Task 4: Full Verification

**Files:**
- No additional files expected.

- [ ] Run no-OA backend tests: `PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_service tests.test_no_oa_bank_batch_api tests.test_no_oa_bank_batch_workbench_integration tests.test_workbench_candidate_grouping tests.test_workbench_sql_runtime -v`
- [ ] Run no-OA frontend tests: `npm test -- NoOaBankBatchApi.test.ts NoOaBankBatchPage.test.tsx WorkbenchApi.test.ts --run`
- [ ] Run `npm run build`.
- [ ] If a local backend is available, smoke the page visually; otherwise document that browser smoke is limited to frontend shell.

# No-OA Bank Batch Workbench Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the production-grade no-OA bank batch workflow: dual-pane batch processing, no-OA pair relation submission, and collapsed no-OA summaries in the workbench paired area.

**Architecture:** Reuse the existing `NoOaBankBatchService` as the batch authority and `WorkbenchPairRelationService` as the paired relation authority. Extend API DTOs, workbench grouping/search contracts, and React mappers/rendering so no-OA submitted groups render as backend-owned collapsed summaries while preserving original rows for detail/search/audit.

**Tech Stack:** Python services and pytest under `backend/src/fin_ops_platform`; React + TypeScript + MUI + Vitest/RTL under `web/src`; existing in-memory/local/Mongo state store patterns.

---

## Source Documents

- Design spec: `/Users/yu/Desktop/sy/Obsidian财务文件/财务app/免OA流水批量处理/01-免OA流水批量处理-生产级整合方案.md`
- Subagent execution prompt: `/Users/yu/Desktop/sy/Obsidian财务文件/财务app/免OA流水批量处理/02-免OA流水批量处理-Codex多任务子代理执行Prompt.md`

The Obsidian execution prompt is authoritative for detailed requirements and file ownership. This plan exists to coordinate implementation in the repo.

## Current Dirty Files To Preserve

These unrelated files were dirty before this work began. Do not revert or rewrite them unless a task explicitly requires a narrow compatible edit:

- `backend/src/fin_ops_platform/services/etc_reconciliation_matcher.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
- `tests/test_etc_reconciliation_service.py`
- `web/src/pages/EtcTicketManagementPage.tsx`
- `web/src/test/EtcTicketManagementPage.test.tsx`

## Task 1: Backend Batch DTO And API Contract

**Files:**
- Modify: `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_no_oa_bank_batch_service.py`
- Test: `tests/test_no_oa_bank_batch_api.py`

- [x] **Step 1: Add failing tests for bucket/count/capability DTO fields**

Cover `status_bucket`, `tag_counts`, `direction_counts`, `can_submit`, `can_withdraw`, and `blocked_reason` for `draft`, `conflict`, `stale`, `submitted`, and `withdrawn`.
Also cover detail rows carrying `category_code`, `category_label`, and `category_source`; mutation responses carrying `affected_months`; and bulk submit partial failure regression.

- [x] **Step 2: Run targeted tests and confirm failure**

Run: `PYTHONPATH=backend/src:. pytest tests/test_no_oa_bank_batch_service.py tests/test_no_oa_bank_batch_api.py -q`

- [x] **Step 3: Implement DTO enrichment and bucket filtering**

Add the fields without changing the existing batch authority or pair relation write path. `stale` with an active no-OA relation must be withdrawable.

- [x] **Step 4: Run targeted tests and fix failures**

Run: `PYTHONPATH=backend/src:. pytest tests/test_no_oa_bank_batch_service.py tests/test_no_oa_bank_batch_api.py -q`

## Task 2: No-OA Page Dual-Pane UI

**Files:**
- Modify: `web/src/pages/NoOaBankBatchPage.tsx`
- Modify: `web/src/features/noOaBankBatches/api.ts`
- Modify: `web/src/features/noOaBankBatches/types.ts`
- Test: `web/src/test/NoOaBankBatchPage.test.tsx`
- Test: `web/src/test/NoOaBankBatchApi.test.ts`

- [x] **Step 1: Add failing API mapper and page tests**

Cover `未提交/已提交` toggle, left batch list, right detail pane, tag counts, draft-only bulk submit, partial failure retaining failed selections, stale withdraw visibility when `can_withdraw=true`, refresh on `bankTransactionCategoryUpdated`, and submit/withdraw dispatching `workbenchRelationUpdated` with affected months where available.

- [x] **Step 2: Run targeted tests and confirm failure**

Run: `npm --prefix web test -- --run NoOaBankBatchPage NoOaBankBatchApi`

- [x] **Step 3: Implement the dual-pane page and mapper updates**

Use MUI native components and the existing no-OA API functions. Do not decide paired state in the UI.

- [x] **Step 4: Run targeted tests and fix failures**

Run: `npm --prefix web test -- --run NoOaBankBatchPage NoOaBankBatchApi`

## Task 3: Workbench Backend Collapsed Summary Contract And Search

**Files:**
- Modify: `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`
- Modify: `backend/src/fin_ops_platform/services/search_service.py`
- Modify as needed: `backend/src/fin_ops_platform/app/server.py` only for no-OA relation metadata application/group payload support, not no-OA API handlers owned by Task 1.
- Test: `tests/test_workbench_candidate_grouping.py`
- Test: `tests/test_search_service.py`
- Test: `tests/test_no_oa_bank_batch_workbench_integration.py`

- [x] **Step 1: Add failing grouping and search tests**

Cover `display_mode=collapsed_summary`, `summary_row`, `collapsed_rows.bank`, mixed no-OA + non-no-OA groups not collapsing, and global search indexing original collapsed bank rows.

- [x] **Step 2: Run targeted tests and confirm failure**

Run: `PYTHONPATH=backend/src:. pytest tests/test_workbench_candidate_grouping.py tests/test_search_service.py tests/test_no_oa_bank_batch_workbench_integration.py -q`

- [x] **Step 3: Implement backend collapsed summary contract**

Keep original rows in `collapsed_rows.bank`; default `bank_rows` should contain only the summary row for pure no-OA groups. Preserve non-no-OA behavior.

- [x] **Step 4: Implement SearchService indexing for collapsed rows**

This is a delivery gate, not a follow-up. Search must not lose original bank row hits after collapse.

- [x] **Step 5: Run targeted tests and fix failures**

Run: `PYTHONPATH=backend/src:. pytest tests/test_workbench_candidate_grouping.py tests/test_search_service.py tests/test_no_oa_bank_batch_workbench_integration.py -q`

## Task 4: Workbench Frontend Collapsed Rendering And Refresh Events

**Files:**
- Modify: `web/src/features/workbench/types.ts`
- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/components/workbench/CandidateGroupGrid.tsx`
- Modify if needed: `web/src/components/workbench/CandidateGroupCell.tsx`
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Test: `web/src/test/WorkbenchApi.test.ts`
- Test: `web/src/test/CandidateGroupGrid.test.tsx`

- [x] **Step 1: Add failing mapper/render/event tests**

Cover collapsed group parsing, default summary-only render, expand-to-details render, collapsed row search matching, no-OA withdraw action using no-OA API semantics, and `bankTransactionCategoryUpdated` refresh.
Also cover `workbenchRelationUpdated` refresh after no-OA summary withdraw when affected months are available.

- [x] **Step 2: Run targeted tests and confirm failure**

Run: `npm --prefix web test -- --run WorkbenchApi CandidateGroupGrid`

- [x] **Step 3: Implement mapper/types and collapsed rendering**

Support `relationMode`, `displayMode`, `defaultCollapsed`, `summaryRow`, and `collapsedRows`. Do not alter normal groups.

- [x] **Step 4: Implement refresh and withdraw behavior**

Workbench must listen to `bankTransactionCategoryUpdated`. No-OA summary withdraw must use `source_batch_id` and `batch_version` or fetch batch detail first.

- [x] **Step 5: Run targeted tests and fix failures**

Run: `npm --prefix web test -- --run WorkbenchApi CandidateGroupGrid`

## Task 5: Integration Verification

**Files:**
- Modify only minimal glue or tests if integration fails.

- [x] **Step 1: Run backend no-OA/workbench regression**

Run:

```bash
PYTHONPATH=backend/src:. pytest \
  tests/test_no_oa_bank_batch_service.py \
  tests/test_no_oa_bank_batch_api.py \
  tests/test_no_oa_bank_batch_workbench_integration.py \
  tests/test_workbench_candidate_grouping.py \
  tests/test_search_service.py \
  tests/test_workbench_v2_api.py \
  -q
```

- [x] **Step 2: Run frontend no-OA/workbench regression**

Run:

```bash
npm --prefix web test -- --run \
  NoOaBankBatchPage \
  NoOaBankBatchApi \
  WorkbenchApi \
  CandidateGroupGrid
```

- [x] **Step 3: Run diff hygiene**

Run: `git diff --check`

- [x] **Step 4: Report outcome**

List changed files, test results, unresolved risks, and any unrelated dirty files left untouched.

# Workbench Relation Preview and Bank Details Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 2026-05-02 Obsidian requirements for workbench three-pane relation previews/withdrawal/amount checks/search/tags and the new bank details page.

**Architecture:** Extend the existing pair relation write model with history snapshots and amount checks, expose preview/withdraw APIs, and keep frontend relation actions preview-first. Add a separate bank details backend service and route that reads already-imported bank transactions, with a dedicated React page and navigation entry.

**Tech Stack:** Python backend under `backend/src/fin_ops_platform`, unittest tests under `tests`, React + TypeScript frontend under `web/src`, Vitest tests under `web/src/test`.

---

## Source Documents

- `/Users/yu/Desktop/sy/财务文件/财务文档/财务app - 20260502 需求总览.md`
- `/Users/yu/Desktop/sy/财务文件/财务文档/财务app - 关联台三栏操作增强 - 产品需求 20260502.md`
- `/Users/yu/Desktop/sy/财务文件/财务文档/财务app - 关联台三栏操作增强 - 技术设计 20260502.md`
- `/Users/yu/Desktop/sy/财务文件/财务文档/财务app - 银行明细页面 - 产品需求 20260502.md`
- `/Users/yu/Desktop/sy/财务文件/财务文档/财务app - 银行明细页面 - 技术设计 20260502.md`
- `/Users/yu/Desktop/sy/财务文件/财务文档/财务app - 20260502 多任务实施 prompts.md`

## Task 1: Backend Pair Relation History and Amount Check

**Files:**
- Modify: `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- Create: `backend/src/fin_ops_platform/services/workbench_amount_check_service.py`
- Modify: `backend/src/fin_ops_platform/services/state_store.py`
- Test: `tests/test_workbench_v2_api.py`
- Test: `tests/test_state_store.py`

- [ ] Add relation history snapshot support.
- [ ] Add amount summary/check service using Decimal, precise to cents.
- [ ] Persist relation notes and amount check metadata.
- [ ] Add tests for history persistence, mismatch note requirement, and restore snapshots.

## Task 2: Backend Preview and Withdraw APIs

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- Test: `tests/test_workbench_v2_api.py`

- [ ] Add `POST /api/workbench/actions/confirm-link/preview`.
- [ ] Add `POST /api/workbench/actions/withdraw-link/preview`.
- [ ] Add `POST /api/workbench/actions/withdraw-link`.
- [ ] Keep old cancel behavior compatible where needed, but new UI uses withdraw language.
- [ ] Validate cross-pane selection for normal confirm.
- [ ] Recompute amount checks on submit; reject missing note when required.

## Task 3: Backend Tags

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_workbench_v2_api.py`

- [ ] Derive display tags from group composition, row direction/source, relation mode, amount check, and OA attachment parse state.
- [ ] Include visible tags: `待找流水`, `待找发票`, `待找流水与发票`, `待找OA`, `金额不一致`, `OA附件`, `人工导入`, `进`, `销`, `收`, `支`, `冲`, `内部往来`, `工资`, `非税`.
- [ ] Add regression tests for tag derivation after confirm and withdraw.

## Task 4: Frontend Relation Preview, Withdraw UI, and Unified Search

**Files:**
- Modify: `web/src/features/workbench/types.ts`
- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Modify: `web/src/app/styles.css`
- Modify: `web/src/test/WorkbenchSelection.test.tsx`
- Modify: `web/src/test/apiMock.ts`

- [ ] Add preview/withdraw API client types and mocks.
- [ ] Add preview dialog with before/after three-pane layout and amount totals.
- [ ] Change confirm relation flow to preview first.
- [ ] Rename paired-zone cancel action to `撤回关联`.
- [ ] Add open-zone withdraw action when groups have withdraw history.
- [ ] Require note in dialog for amount mismatch.
- [ ] Convert pane search to unified zone search while preserving group layout and highlighting matches.
- [ ] Add tests for preview, note requirement, withdraw label, open-zone withdraw availability, and unified search.

## Task 5: Bank Details Backend

**Files:**
- Create: `backend/src/fin_ops_platform/services/bank_details_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_bank_details_service.py`
- Test: `tests/test_workbench_v2_api.py`

- [ ] Add account list API `GET /api/bank-details/accounts`.
- [ ] Add transaction list API `GET /api/bank-details/transactions`.
- [ ] Group accounts by bank name and account last four digits.
- [ ] Compute latest balances from all imported transactions, independent of date filters.
- [ ] Exclude missing balances from total balance.
- [ ] Return transaction fields and `收`/`支` labels.

## Task 6: Bank Details Frontend

**Files:**
- Modify: `web/src/App.tsx` or routing owner file.
- Modify: `web/src/app/AppChrome.tsx` or navigation owner file.
- Create: `web/src/features/bankDetails/types.ts`
- Create: `web/src/features/bankDetails/api.ts`
- Create: `web/src/pages/BankDetailsPage.tsx`
- Modify: `web/src/app/styles.css`
- Test: `web/src/test/BankDetailsPage.test.tsx`
- Modify: `web/src/test/apiMock.ts`

- [ ] Add `/bank-details` route and `银行明细` navigation entry to the right of `成本统计`.
- [ ] Build account tree, balance header, time filter, and transaction table.
- [ ] Support presets: this month, previous month, last 7 days, last 30 days, current year.
- [ ] Support month picker and custom date range.
- [ ] Ensure date filtering affects rows but not balances.
- [ ] Add tests for route, account selection, filters, balances, and amount direction tags.

## Task 7: Integration Verification

**Files:**
- Modify as needed based on failures.

- [ ] Run backend targeted tests.
- [ ] Run frontend targeted tests.
- [ ] Run frontend build.
- [ ] Run `git diff --check`.
- [ ] Verify tests use mock/constructed data and do not depend on local import files.


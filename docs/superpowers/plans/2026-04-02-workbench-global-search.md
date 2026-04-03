# Workbench Global Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strong global search experience to the reconciliation workbench, with grouped `OA / 银行流水 / 发票` results, month/project/status filters, and one-click jump-back into the workbench at the correct month and row.

**Architecture:** Build a backend `SearchService` that reads the existing OA read path plus app Mongo detail collections and returns a unified entity search payload. Then add a workbench search box and modal in the React app, with grouped result lists, filter state, and jump-to-record behavior that reloads the correct month, opens the correct zone or modal, and highlights the target row.

**Tech Stack:** Python backend services, Mongo detail collections, existing OA adapter, React 18, TypeScript, Vite, Testing Library.

---

## File Map

### Backend

- Create: `backend/src/fin_ops_platform/services/search_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
- Modify: `backend/src/fin_ops_platform/services/state_store.py` only if read helpers or indexes are needed
- Create: `tests/test_search_service.py`
- Create: `tests/test_search_api.py`

### Frontend

- Create: `web/src/features/search/types.ts`
- Create: `web/src/features/search/api.ts`
- Create: `web/src/components/workbench/WorkbenchSearchBox.tsx`
- Create: `web/src/components/workbench/WorkbenchSearchModal.tsx`
- Create: `web/src/components/workbench/WorkbenchSearchResultSection.tsx`
- Create: `web/src/components/workbench/WorkbenchSearchResultItem.tsx`
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Modify: `web/src/app/styles.css`
- Modify: `web/src/test/apiMock.ts`
- Create: `web/src/test/WorkbenchSearchModal.test.tsx`
- Modify: `web/src/test/WorkbenchSelection.test.tsx` if jump-to highlight needs integration coverage

### Docs

- Modify: `docs/README.md`
- Modify: `prompts/README.md`
- Optionally create after implementation: `docs/dev/workbench-global-search.md`

---

## Task 1: Lock backend search contract

- [ ] Define the shared search result schema for `oa_results`, `bank_results`, and `invoice_results`
- [ ] Lock the first-version query parameters:
  - `q`
  - `scope`
  - `month`
  - `project_name`
  - `status`
  - `limit`
- [ ] Define `zone_hint` values:
  - `paired`
  - `open`
  - `ignored`
  - `processed_exception`
- [ ] Define `jump_target` payload shape so the frontend does not infer navigation rules itself

## Task 2: Build the backend unified search service

- [ ] Write a failing unit test for OA keyword search
- [ ] Run it to confirm it fails for missing service behavior
- [ ] Write a failing unit test for bank keyword search across amount / company / serial / account-last4
- [ ] Run it to confirm it fails
- [ ] Write a failing unit test for invoice keyword search across invoice number / company / tax number
- [ ] Run it to confirm it fails
- [ ] Implement `SearchService` with weak normalization:
  - trim whitespace
  - lowercase
  - weaken common company suffixes
  - support exact-or-contains matching for invoice and transaction numbers
- [ ] Implement grouped result building with:
  - result title
  - primary and secondary meta
  - matched field
  - month
  - status label
  - zone hint
  - jump target
- [ ] Run targeted backend tests and confirm they pass

## Task 3: Expose the search API

- [ ] Write a failing API test for `GET /api/search`
- [ ] Run it to confirm route absence or wrong payload
- [ ] Add `GET /api/search` to `server.py`
- [ ] Validate and sanitize query params
- [ ] Return the grouped payload:
  - `summary`
  - `oa_results`
  - `bank_results`
  - `invoice_results`
- [ ] Run targeted API tests and confirm they pass

## Task 4: Add the workbench search entry point

- [ ] Write a failing frontend test that expects the old `关联台月份 2026-03` copy block to be replaced by a search box entry
- [ ] Run it to confirm failure
- [ ] Add `WorkbenchSearchBox`
- [ ] Place it in the workbench toolbar near the month picker
- [ ] Remove the old pure month copy block
- [ ] Confirm the workbench month picker still remains in-page and usable
- [ ] Run targeted frontend tests and confirm they pass

## Task 5: Build the grouped search modal

- [ ] Write a failing frontend test for opening the search modal
- [ ] Run it to confirm failure
- [ ] Add `WorkbenchSearchModal`
- [ ] Add filter controls:
  - scope
  - month
  - project
  - status
- [ ] Add grouped result sections:
  - OA
  - 银行流水
  - 发票
- [ ] Render result counts and empty states per section
- [ ] Render one `跳转至` action per result item
- [ ] Run targeted frontend tests and confirm they pass

## Task 6: Implement jump-back behavior

- [ ] Write a failing frontend integration test for clicking `跳转至`
- [ ] Run it to confirm failure
- [ ] Implement jump workflow:
  - close modal
  - switch month
  - reload workbench data
  - open the correct zone or modal
  - scroll to target row
  - apply a temporary highlight
- [ ] Cover all zone hints:
  - paired
  - open
  - ignored
  - processed_exception
- [ ] Run targeted tests and confirm they pass

## Task 7: Polish, harden, and verify

- [ ] Add matched-field labels and keyword highlighting
- [ ] Add loading / empty / error states inside the search modal
- [ ] Ensure no search result depends on three-column candidate layout
- [ ] Run full frontend tests
- [ ] Run frontend build
- [ ] Run full backend tests
- [ ] Perform manual verification:
  - search by project name
  - search by applicant name
  - search by company name
  - search by invoice number
  - search by transaction number
  - search by amount
  - jump to paired/open/ignored/processed exception targets


# Bank Internal Transfer Auto Category Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bank details auto classification first identifies internal transfers, then applies existing text categories without overriding internal transfer rows.

**Architecture:** Extract a shared internal-transfer detector that accepts normalized bank row dictionaries and returns category-compatible suggestions. `BankTransactionAutoCategoryService` owns priority ordering, so both in-memory bank details and SQL read-model projection stay consistent. No OA batches continue consuming `internal_transfer` as an input category and remain responsible for batch conflicts and submission.

**Tech Stack:** Python backend services and unittest, React/MUI frontend tests, XLSX export service.

---

### Task 1: Shared Detector And Auto Category Priority

**Files:**
- Create: `backend/src/fin_ops_platform/services/bank_internal_transfer_detector.py`
- Modify: `backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py`
- Test: `tests/test_bank_transaction_auto_category_service.py`

- [ ] Write failing tests for internal transfer detection, priority over text tags, same-account rejection, time-window rejection, single-sided rejection, and multi-solution rejection.
- [ ] Run `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_auto_category_service -v` and confirm the new tests fail because no internal transfer suggestion is produced.
- [ ] Implement the detector with 48-hour window, company identity check, equal amount, opposite direction, distinct account, and no silent multi-solution tagging.
- [ ] Wire `BankTransactionAutoCategoryService` to run internal transfer first and skip text rules for matched row ids.
- [ ] Rerun the test command and confirm it passes.

### Task 2: Bank Details, SQL Projection, Export, And Frontend Contract

**Files:**
- Modify tests around `BankDetailsService`, SQL read model, export, and bank details page/API as needed.
- Modify docs in `docs/product-specs/bank-details.md`.

- [ ] Update failing tests proving bank details rows, category counts, read model projection, export automatic category, and frontend chips include internal transfer.
- [ ] Run the relevant backend/frontend test subsets and confirm red state before production changes where existing tests still encode the old no-internal-transfer behavior.
- [ ] Update production code only where required by the detector integration; avoid duplicating detector logic in UI/export.
- [ ] Update product spec to document the new internal-transfer-first priority and 48-hour deterministic matching policy.
- [ ] Run the final verification matrix from the user prompt.

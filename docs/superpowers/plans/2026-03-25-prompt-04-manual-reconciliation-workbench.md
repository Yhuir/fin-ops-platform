# Prompt 04 Manual Reconciliation Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current reconciliation workbench prototype into a working manual-finance surface backed by real Prompt 02 import data and Prompt 03 matching results.

**Architecture:** Keep the current Python HTTP foundation and single-file workbench prototype. Add a reconciliation/workbench service that can read the latest imported invoices and bank transactions, consume matching results, materialize confirmed and exception cases as `ReconciliationCase + ReconciliationLine`, record audit entries, and expose workbench-oriented endpoints for the UI. The existing prototype HTML will fetch real data from the new endpoints while preserving the current three-column, two-zone interaction model.

**Tech Stack:** Python, dataclasses, unittest, in-memory service state, single-file HTML/CSS/JS

---

### Task 1: Extend reconciliation domain models for manual actions

**Files:**
- Modify: `backend/src/fin_ops_platform/domain/enums.py`
- Modify: `backend/src/fin_ops_platform/domain/models.py`
- Test: `tests/test_domain_models.py`

- [ ] Step 1: Add failing tests for structured exception and offline reconciliation records
- [ ] Step 2: Extend `ReconciliationCase` with exception / source-result / remark metadata needed for traceability
- [ ] Step 3: Add `ExceptionHandlingRecord` and `OfflineReconciliationRecord`
- [ ] Step 4: Run domain tests

### Task 2: Implement the manual reconciliation and workbench read service

**Files:**
- Create: `backend/src/fin_ops_platform/services/reconciliation.py`
- Test: `tests/test_reconciliation_service.py`

- [ ] Step 1: Write failing tests for confirming a manual reconciliation case from matched objects
- [ ] Step 2: Write failing tests for structured exception handling with `SO-*` / `PI-*` codes
- [ ] Step 3: Write failing tests for offline reconciliation record creation and audit logging
- [ ] Step 4: Write failing tests for workbench read models built from imports, matching, and reconciliation history
- [ ] Step 5: Implement case creation, line creation, object amount updates, and audit recording
- [ ] Step 6: Implement workbench payload assembly for paired/open zones and history
- [ ] Step 7: Run service tests

### Task 3: Expose workbench and manual action endpoints

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_workbench_api.py`
- Test: `tests/test_app.py`

- [ ] Step 1: Write failing API tests for workbench query and manual action endpoints
- [ ] Step 2: Wire `AuditTrailService` and the reconciliation service into the application
- [ ] Step 3: Expose `GET /workbench`
- [ ] Step 4: Expose `POST /workbench/actions/confirm`
- [ ] Step 5: Expose `POST /workbench/actions/exception`
- [ ] Step 6: Expose `POST /workbench/actions/offline`
- [ ] Step 7: Expose `GET /reconciliation/cases` and `GET /reconciliation/cases/{case_id}`
- [ ] Step 8: Run API tests

### Task 4: Wire the current UI prototype to real APIs

**Files:**
- Modify: `web/prototypes/reconciliation-workbench-v2.html`

- [ ] Step 1: Replace hard-coded bank / invoice workbench rows with `GET /workbench` data
- [ ] Step 2: Preserve the current three-column, two-zone layout and row-selection behavior
- [ ] Step 3: Add a right-side context action panel that uses the selected rows for confirm / exception / offline actions
- [ ] Step 4: Keep row `详情` behavior separate from selection
- [ ] Step 5: Submit manual actions to the new API endpoints and refresh the workbench state

### Task 5: Verification and docs

**Files:**
- Modify: `README.md`
- Modify: `docs/dev/reconciliation-workbench-v2-backend.md`
- Modify: `docs/dev/reconciliation-workbench-v2-frontend.md`
- Modify: `docs/dev/reconciliation-workbench-v2-testing.md`

- [ ] Step 1: Document the new workbench endpoints and UI data flow
- [ ] Step 2: Document how matching results become manual reconciliation cases
- [ ] Step 3: Run the full test suite
- [ ] Step 4: Smoke-test the prototype against the local API

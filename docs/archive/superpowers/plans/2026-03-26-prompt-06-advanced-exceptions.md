# Prompt 06 Advanced Exceptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add difference reconciliation, negative-invoice reconciliation, and offset-note based internal offset handling without breaking the existing standard reconciliation and ledger flows.

**Architecture:** Extend the current in-memory reconciliation domain with structured difference reasons plus an `OffsetNote` business object. Keep the existing workbench flow intact, and add two new workbench actions that create `ReconciliationCase` records for difference settlement and cross-side internal offset. Reuse the same workbench prototype by extending the right-side context panel instead of creating a new page.

**Tech Stack:** Python, dataclasses, unittest, static HTML prototype

---

### Task 1: Extend domain models for advanced exceptions

**Files:**
- Modify: `backend/src/fin_ops_platform/domain/enums.py`
- Modify: `backend/src/fin_ops_platform/domain/models.py`
- Test: `tests/test_domain_models.py`

- [ ] Step 1: Write the failing test for `DifferenceReason`
- [ ] Step 2: Write the failing test for `OffsetNote`
- [ ] Step 3: Add `DifferenceReason`
- [ ] Step 4: Add `difference_note` to `ReconciliationCase`
- [ ] Step 5: Add `OffsetNote`
- [ ] Step 6: Run domain tests

### Task 2: Add reconciliation service support for H/I/J scenarios

**Files:**
- Modify: `backend/src/fin_ops_platform/services/reconciliation.py`
- Test: `tests/test_reconciliation_service.py`

- [ ] Step 1: Write the failing test for difference reconciliation with structured reason
- [ ] Step 2: Write the failing test for red output invoice with reverse bank transaction
- [ ] Step 3: Write the failing test for offset reconciliation producing `OffsetNote`
- [ ] Step 4: Implement sign-aware invoice allocation for negative invoices
- [ ] Step 5: Implement `confirm_difference_reconciliation(...)`
- [ ] Step 6: Implement `record_offset_reconciliation(...)`
- [ ] Step 7: Run reconciliation service tests

### Task 3: Expose advanced exception APIs

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_workbench_api.py`
- Test: `tests/test_app.py`

- [ ] Step 1: Write the failing API test for `POST /workbench/actions/difference`
- [ ] Step 2: Write the failing API test for `POST /workbench/actions/offset`
- [ ] Step 3: Expose difference action route
- [ ] Step 4: Expose offset action route
- [ ] Step 5: Update readiness summary
- [ ] Step 6: Run API tests

### Task 4: Extend the workbench prototype for advanced exceptions

**Files:**
- Modify: `web/prototypes/reconciliation-workbench-v2.html`

- [ ] Step 1: Add `差额核销` and `内部抵扣` tabs in the context panel
- [ ] Step 2: Add form fields for structured difference reason and notes
- [ ] Step 3: Add form fields for offset reason and notes
- [ ] Step 4: Wire new form submissions to the new endpoints
- [ ] Step 5: Extend detail drawer to show `OffsetNote`
- [ ] Step 6: Run prototype script syntax validation

### Task 5: Document Prompt 06

**Files:**
- Modify: `README.md`
- Modify: `docs/dev/README.md`
- Create: `docs/dev/advanced-exception-rules.md`

- [ ] Step 1: Document H/I/J handling rules
- [ ] Step 2: Document structured difference reasons and offset note rules
- [ ] Step 3: Run full test suite

# Prompt 05 Ledger And Reminders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn unresolved reconciliation outcomes into durable follow-up ledgers and repeatable reminders so finance no longer tracks open items in offline Excel.

**Architecture:** Extend the existing in-memory finance domain with richer ledger types plus reminder records. Add a ledger/reminder service that listens to Prompt 04 reconciliation actions, derives unresolved business meaning from manual cases and exception codes, creates or updates `FollowUpLedger` rows idempotently, and schedules reminder rows without duplicate spam. Expose lightweight HTTP endpoints for querying ledgers, querying due items, updating ledger follow-up status, and running the reminder cycle.

**Tech Stack:** Python, dataclasses, unittest, in-memory service state

---

### Task 1: Extend domain types for ledgers and reminders

**Files:**
- Modify: `backend/src/fin_ops_platform/domain/enums.py`
- Modify: `backend/src/fin_ops_platform/domain/models.py`
- Test: `tests/test_domain_models.py`

- [ ] Step 1: Add failing tests for richer ledger types and reminder model
- [ ] Step 2: Extend `LedgerType` to cover催款、催票、退款、预收、预付、待开销项票、待付款、外部往来、非税收入
- [ ] Step 3: Extend `FollowUpLedger` with source-case and reminder-tracking metadata
- [ ] Step 4: Add `Reminder`
- [ ] Step 5: Run domain tests

### Task 2: Implement automatic ledger and reminder service

**Files:**
- Create: `backend/src/fin_ops_platform/services/ledgers.py`
- Test: `tests/test_ledger_service.py`

- [ ] Step 1: Write failing tests for partial receivable -> payment collection ledger
- [ ] Step 2: Write failing tests for missing invoice / overpayment -> invoice collection or refund / advance receipt ledger
- [ ] Step 3: Write failing tests for exception-code-driven ledger generation
- [ ] Step 4: Write failing tests for reminder scheduling, due query, and duplicate suppression
- [ ] Step 5: Implement idempotent ledger sync from reconciliation cases
- [ ] Step 6: Implement reminder scheduling and runnable reminder cycle skeleton
- [ ] Step 7: Run service tests

### Task 3: Wire ledger generation into Prompt 04 reconciliation actions

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/services/reconciliation.py`
- Test: `tests/test_workbench_api.py`

- [ ] Step 1: Ensure confirm / exception / offline actions trigger ledger sync automatically
- [ ] Step 2: Ensure ledger creation does not duplicate on repeated sync
- [ ] Step 3: Ensure reminder generation can be triggered repeatedly without duplicate spam
- [ ] Step 4: Run affected API tests

### Task 4: Expose ledger and reminder APIs

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_ledger_api.py`
- Test: `tests/test_app.py`

- [ ] Step 1: Write failing API tests for ledger listing and detail
- [ ] Step 2: Write failing API tests for due / overdue views and reminder run endpoint
- [ ] Step 3: Expose `GET /ledgers`
- [ ] Step 4: Expose `GET /ledgers/{ledger_id}`
- [ ] Step 5: Expose `POST /ledgers/{ledger_id}/status`
- [ ] Step 6: Expose `GET /reminders`
- [ ] Step 7: Expose `POST /reminders/run`
- [ ] Step 8: Run API tests

### Task 5: Docs and verification

**Files:**
- Modify: `README.md`
- Create: `docs/dev/ledger-and-reminder-rules.md`

- [ ] Step 1: Document ledger generation rules by reconciliation outcome
- [ ] Step 2: Document reminder triggering and duplicate suppression behavior
- [ ] Step 3: Run full test suite
- [ ] Step 4: Commit the Prompt 05 delivery

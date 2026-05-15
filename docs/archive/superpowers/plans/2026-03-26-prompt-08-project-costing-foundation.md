# Prompt 08 Project Costing Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal project-costing foundation with project assignment, audited overrides, and project-level summary queries on top of the existing reconciliation system.

**Architecture:** Reuse the existing `ProjectMaster` model from Prompt 07 and add a dedicated `ProjectCostingService` that resolves effective project ownership across invoices, bank transactions, reconciliation cases, and ledgers. Keep the current in-memory backend and prototype flow, exposing project assignment and project summary through separate HTTP endpoints and a parallel read-only-plus-action project page.

**Tech Stack:** Python, dataclasses, unittest, static HTML prototype

---

### Task 1: Extend domain models for project assignment

**Files:**
- Modify: `backend/src/fin_ops_platform/domain/models.py`
- Test: `tests/test_domain_models.py`

- [ ] Step 1: Write the failing test for `ProjectAssignmentRecord`
- [ ] Step 2: Write the failing test for `ProjectSummary`
- [ ] Step 3: Add `ProjectAssignmentRecord`
- [ ] Step 4: Add `ProjectSummary`
- [ ] Step 5: Run domain model tests

### Task 2: Add the project costing service

**Files:**
- Modify: `backend/src/fin_ops_platform/services/integrations.py`
- Create: `backend/src/fin_ops_platform/services/project_costing.py`
- Test: `tests/test_project_costing_service.py`

- [ ] Step 1: Write the failing test for effective project resolution priority
- [ ] Step 2: Write the failing test for project summary aggregation
- [ ] Step 3: Expose project/document lookup helpers from integration service
- [ ] Step 4: Implement project creation and placeholder project registration
- [ ] Step 5: Implement manual project assignment with audit logging
- [ ] Step 6: Implement project summary and detail queries
- [ ] Step 7: Run project costing service tests

### Task 3: Expose project costing HTTP APIs

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `tests/test_app.py`
- Create: `tests/test_project_costing_api.py`

- [ ] Step 1: Write the failing API test for project list, create, assign, and detail routes
- [ ] Step 2: Add `GET /projects`
- [ ] Step 3: Add `GET /projects/{project_id}`
- [ ] Step 4: Add `POST /projects`
- [ ] Step 5: Add `POST /projects/assign`
- [ ] Step 6: Update readiness summary
- [ ] Step 7: Run project costing API tests

### Task 4: Add the minimal project page in the current prototype

**Files:**
- Modify: `web/prototypes/reconciliation-workbench-v2.html`

- [ ] Step 1: Add `项目归集` entry button and page state
- [ ] Step 2: Add project summary cards and project list table
- [ ] Step 3: Add current-project detail panel
- [ ] Step 4: Add assignable-object table with row-level project assignment
- [ ] Step 5: Wire create/assign actions to the new endpoints
- [ ] Step 6: Run prototype script syntax validation

### Task 5: Document Prompt 08

**Files:**
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/dev/README.md`
- Create: `docs/dev/project-costing-foundation.md`

- [ ] Step 1: Document project assignment priority and query metrics
- [ ] Step 2: Document future extension path toward real costing
- [ ] Step 3: Run the full test suite

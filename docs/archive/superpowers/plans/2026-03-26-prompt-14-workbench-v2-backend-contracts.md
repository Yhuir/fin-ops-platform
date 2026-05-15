# Prompt 14 Workbench V2 Backend Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a stable `/api/*` contract layer for the React workbench and tax page without breaking the existing reconciliation services and tests.

**Architecture:** Keep legacy `/workbench` routes intact, then layer a new contract-oriented workbench query/action service and tax service on top. Route parsing stays in app-layer helpers; domain behavior remains isolated from the old reconciliation flow.

**Tech Stack:** Python, unittest, lightweight in-process HTTP application

---

### Task 1: Add failing API tests for Workbench V2 and tax contracts

**Files:**
- Create: `tests/test_workbench_v2_api.py`
- Create: `tests/test_tax_offset_api.py`
- Modify: `tests/test_app.py`

- [ ] Step 1: Add tests for `/api/workbench` month coverage and row detail.
- [ ] Step 2: Add tests for unified workbench action responses.
- [ ] Step 3: Add tests for `/api/tax-offset` and `/api/tax-offset/calculate`.
- [ ] Step 4: Run targeted tests and verify they fail because `/api/*` routes do not exist yet.

### Task 2: Add new backend contract services

**Files:**
- Create: `backend/src/fin_ops_platform/services/workbench_query_service.py`
- Create: `backend/src/fin_ops_platform/services/workbench_action_service.py`
- Create: `backend/src/fin_ops_platform/services/tax_offset_service.py`
- Create: `backend/src/fin_ops_platform/services/oa_adapter.py`
- Create: `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
- Create: `backend/src/fin_ops_platform/services/bank_account_resolver.py`

- [ ] Step 1: Seed two months of OA / bank / invoice data for the V2 contract layer.
- [ ] Step 2: Add row detail and summary shaping.
- [ ] Step 3: Add action mutations for confirm / exception / cancel / bank-exception.
- [ ] Step 4: Add tax month data and calculation helpers.

### Task 3: Wire `/api/*` routes into the application

**Files:**
- Create: `backend/src/fin_ops_platform/app/routes_workbench.py`
- Create: `backend/src/fin_ops_platform/app/routes_tax.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`

- [ ] Step 1: Route `/api/workbench` and row detail queries.
- [ ] Step 2: Route the four workbench V2 action endpoints.
- [ ] Step 3: Route tax list and calculate endpoints.
- [ ] Step 4: Expose new entrypoints and capability flags in `/health`.

### Task 4: Update docs and run full backend verification

**Files:**
- Modify: `README.md`
- Modify: `web/README.md`
- Modify: `docs/README.md`
- Modify: `docs/dev/README.md`
- Modify: `docs/dev/reconciliation-workbench-v2-backend.md`

- [ ] Step 1: Document Prompt 14 endpoints, boundaries, and current mock-vs-real split.
- [ ] Step 2: Run `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api tests.test_tax_offset_api tests.test_app -v`.
- [ ] Step 3: Run `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`.
- [ ] Step 4: Verify local contract endpoints are ready for Prompt 15 frontend integration.

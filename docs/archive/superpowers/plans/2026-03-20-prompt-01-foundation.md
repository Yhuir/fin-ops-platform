# Prompt 01 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable `fin-ops-platform` skeleton for reconciliation, with core domain models, a minimal HTTP API, seed data, and explicit extension points for OA integration and project costing.

**Architecture:** Use a zero-dependency Python backend so the repository can be verified locally without downloading packages. Split the code into `app`, `domain`, and `services` modules, keep a placeholder `web` workspace for future UI work, and expose a tiny health endpoint that reports current and planned capabilities.

**Tech Stack:** Python 3.13 standard library, `unittest`, `http.server`, dataclasses, Markdown docs

---

### Task 1: Write failing domain-model tests

**Files:**
- Create: `tests/test_domain_models.py`

- [ ] **Step 1: Write the failing test**

```python
def test_invoice_tracks_outstanding_amount_and_project_metadata(self):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend/src python3 -m unittest tests.test_domain_models -v`
Expected: FAIL with `ModuleNotFoundError`

### Task 2: Write failing app and audit tests

**Files:**
- Create: `tests/test_app.py`
- Create: `tests/test_audit_service.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_health_endpoint_reports_capabilities(self):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`
Expected: FAIL because application modules do not exist yet

### Task 3: Implement backend skeleton

**Files:**
- Create: `backend/src/fin_ops_platform/__init__.py`
- Create: `backend/src/fin_ops_platform/app/main.py`
- Create: `backend/src/fin_ops_platform/app/server.py`
- Create: `backend/src/fin_ops_platform/domain/enums.py`
- Create: `backend/src/fin_ops_platform/domain/models.py`
- Create: `backend/src/fin_ops_platform/services/audit.py`
- Create: `backend/src/fin_ops_platform/services/seeds.py`

- [ ] **Step 1: Write the minimal implementation**
- [ ] **Step 2: Run unit tests**

Run: `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`
Expected: PASS

### Task 4: Add repository scaffolding and startup docs

**Files:**
- Create: `.gitignore`
- Modify: `README.md`
- Create: `backend/README.md`
- Create: `web/README.md`

- [ ] **Step 1: Document module layout and startup command**
- [ ] **Step 2: Verify the API can start**

Run: `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
Expected: exit code `0` and readiness summary

### Task 5: Verify end-to-end foundation state

**Files:**
- Verify: `tests/test_domain_models.py`
- Verify: `tests/test_app.py`
- Verify: `tests/test_audit_service.py`

- [ ] **Step 1: Run fresh verification**

Run: `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`
Expected: PASS with all tests green

- [ ] **Step 2: Run service readiness check**

Run: `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
Expected: exit code `0`

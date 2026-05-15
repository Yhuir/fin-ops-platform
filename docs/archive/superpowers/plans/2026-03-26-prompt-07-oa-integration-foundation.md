# Prompt 07 OA Integration Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an isolated OA integration foundation with a mock adapter, sync runs, external-to-internal mappings, and a minimal read-only prototype view without coupling OA logic into the reconciliation core.

**Architecture:** Introduce a dedicated `Integration Hub` service that owns OA adapter calls, sync run tracking, mapping persistence, and read models for projects and OA documents. Reuse the current in-memory backend and current HTML prototype, exposing OA sync through separate HTTP endpoints and a parallel read-only page.

**Tech Stack:** Python, dataclasses, unittest, static HTML prototype

---

### Task 1: Extend integration domain models

**Files:**
- Modify: `backend/src/fin_ops_platform/domain/enums.py`
- Modify: `backend/src/fin_ops_platform/domain/models.py`
- Test: `tests/test_domain_models.py`

- [ ] Step 1: Write the failing test for integration enums and sync models
- [ ] Step 2: Add integration source, object type, and sync status enums
- [ ] Step 3: Add project, OA document, mapping, sync run, and sync issue models
- [ ] Step 4: Run domain model tests

### Task 2: Add the Integration Hub service

**Files:**
- Modify: `backend/src/fin_ops_platform/services/imports.py`
- Create: `backend/src/fin_ops_platform/services/integrations.py`
- Test: `tests/test_integration_service.py`

- [ ] Step 1: Write the failing test for syncing counterparties into existing master data
- [ ] Step 2: Write the failing test for syncing projects and OA documents
- [ ] Step 3: Expose counterparty lookup helpers from the import service
- [ ] Step 4: Implement `OAAdapter`, `MockOAAdapter`, and `IntegrationHubService`
- [ ] Step 5: Implement sync run tracking and retry linkage
- [ ] Step 6: Run integration service tests

### Task 3: Expose OA sync HTTP APIs

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `tests/test_app.py`
- Create: `tests/test_integration_api.py`

- [ ] Step 1: Write the failing API test for OA dashboard and sync endpoints
- [ ] Step 2: Add OA dashboard route
- [ ] Step 3: Add OA sync trigger route
- [ ] Step 4: Add OA sync run list and detail routes
- [ ] Step 5: Update readiness summary to advertise OA capability
- [ ] Step 6: Run OA API tests

### Task 4: Add the OA sync read-only prototype view

**Files:**
- Modify: `web/prototypes/reconciliation-workbench-v2.html`

- [ ] Step 1: Add `OA 同步` entry button and page state
- [ ] Step 2: Add OA sync summary cards and recent runs table
- [ ] Step 3: Add project / document / mapping read-only tables
- [ ] Step 4: Wire sync and retry actions to the new endpoints
- [ ] Step 5: Run prototype script syntax validation

### Task 5: Document Prompt 07

**Files:**
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/dev/README.md`
- Create: `docs/dev/oa-integration-foundation.md`

- [ ] Step 1: Document the integration boundary and supported scopes
- [ ] Step 2: Document real OA replacement points
- [ ] Step 3: Run the full test suite

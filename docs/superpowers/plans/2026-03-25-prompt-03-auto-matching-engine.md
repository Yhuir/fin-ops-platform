# Prompt 03 Auto Matching Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a queryable auto-matching engine that evaluates confirmed invoices and bank transactions, stores match results, and exposes run/query endpoints for the future workbench.

**Architecture:** Add explicit matching domain models plus an in-memory matching service layered on top of the Prompt 02 import service. The engine runs deterministic rules in order, persists matching runs and result rows in memory, and exposes them via lightweight HTTP endpoints without mutating reconciliation state.

**Tech Stack:** Python, dataclasses, unittest, in-memory service state

---

### Task 1: Add matching domain models and enums

**Files:**
- Modify: `backend/src/fin_ops_platform/domain/enums.py`
- Modify: `backend/src/fin_ops_platform/domain/models.py`
- Test: `tests/test_domain_models.py`

- [ ] Step 1: Write failing tests for matching run and result models
- [ ] Step 2: Add enums for matching result classification and confidence band
- [ ] Step 3: Add `MatchingRun` and `MatchingResult` dataclasses
- [ ] Step 4: Run domain tests

### Task 2: Implement matching service with core rules

**Files:**
- Create: `backend/src/fin_ops_platform/services/matching.py`
- Test: `tests/test_matching_service.py`

- [ ] Step 1: Write failing tests for standard one-to-one auto matching
- [ ] Step 2: Write failing tests for multi-invoice/single-transaction suggestion
- [ ] Step 3: Write failing tests for unresolved manual-review cases
- [ ] Step 4: Implement deterministic matching rules and explanation payloads
- [ ] Step 5: Persist matching runs and results in memory
- [ ] Step 6: Run service tests

### Task 3: Expose matching API endpoints

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_matching_api.py`
- Test: `tests/test_app.py`

- [ ] Step 1: Write failing API tests for run/list/detail endpoints
- [ ] Step 2: Wire matching service to the application
- [ ] Step 3: Expose `POST /matching/run`
- [ ] Step 4: Expose `GET /matching/results`
- [ ] Step 5: Expose `GET /matching/results/{result_id}`
- [ ] Step 6: Run API tests

### Task 4: Samples and docs

**Files:**
- Modify: `README.md`
- Create: `docs/dev/auto-matching-engine-samples.md`

- [ ] Step 1: Document supported rules and endpoint samples
- [ ] Step 2: Document how results flow into the manual workbench
- [ ] Step 3: Run the full test suite
- [ ] Step 4: Commit the Prompt 03 delivery

# Prompt 02 Import Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the import preview, normalization, deduplication, and confirm-ingest flow for output invoices, input invoices, and bank transactions.

**Architecture:** Keep the current Python foundation server and add an in-memory import service that parses structured JSON rows, evaluates uniqueness and fingerprints, stores preview batches plus row decisions, and confirms only safe rows into normalized invoice/bank transaction stores. Expose the flow with lightweight HTTP endpoints for preview, confirm, and batch lookup.

**Tech Stack:** Python, dataclasses, unittest, in-memory service state

---

### Task 1: Extend domain types for import tracking

**Files:**
- Modify: `backend/src/fin_ops_platform/domain/enums.py`
- Modify: `backend/src/fin_ops_platform/domain/models.py`
- Test: `tests/test_domain_models.py`

- [ ] Step 1: Add failing tests for new import tracking fields and row result model
- [ ] Step 2: Add import decision enum and extra batch counters
- [ ] Step 3: Add `source_unique_key` and `data_fingerprint` to core importable models
- [ ] Step 4: Add `ImportedBatchRowResult`
- [ ] Step 5: Run domain tests

### Task 2: Implement import normalization service

**Files:**
- Create: `backend/src/fin_ops_platform/services/imports.py`
- Test: `tests/test_import_service.py`

- [ ] Step 1: Write failing tests for invoice preview decisions
- [ ] Step 2: Write failing tests for bank transaction preview decisions
- [ ] Step 3: Implement validation, normalization, unique-key logic, and fingerprint logic
- [ ] Step 4: Implement preview batch storage and confirm ingestion
- [ ] Step 5: Run service tests

### Task 3: Expose import HTTP endpoints

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_import_api.py`
- Test: `tests/test_app.py`

- [ ] Step 1: Write failing API tests for preview, confirm, and batch lookup
- [ ] Step 2: Add JSON body parsing and POST routing
- [ ] Step 3: Wire application to import service
- [ ] Step 4: Run API tests

### Task 4: Seed integration and docs

**Files:**
- Modify: `backend/src/fin_ops_platform/services/seeds.py`
- Modify: `README.md`
- Create: `docs/dev/import-normalization-samples.md`

- [ ] Step 1: Add normalized import-related seed fields
- [ ] Step 2: Document sample request payloads and verification steps
- [ ] Step 3: Run full test suite
- [ ] Step 4: Commit the Prompt 02 delivery

# Import RabbitMQ Processors Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move import confirmation execution behind PostgreSQL-backed import jobs and RabbitMQ wakeup for all import families.

**Architecture:** API handlers validate request state and create `job.import_jobs` plus `import.process.requested` outbox events. RabbitMQ workers receive the envelope, re-read the import job from PostgreSQL, run an explicit processor by `import_type`, then mark import job and outbox status. Inline PostgreSQL mode remains the rollback path.

**Tech Stack:** Python stdlib HTTP server, PostgreSQL runtime queue/outbox, RabbitMQ runtime dispatcher/consumer, unittest.

---

### Task 1: Import Job Cutover Switch

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_import_job_queue.py`

- [ ] **Step 1: Write failing tests**
  - Verify `FIN_OPS_IMPORT_PROCESSING_BACKEND=rabbitmq` makes `/imports/confirm` return 202 with `import_job` and enqueued `import.process.requested`.
  - Verify default inline mode preserves existing 200 behavior.

- [ ] **Step 2: Run tests and verify red**

Run: `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_import_job_queue -v`

- [ ] **Step 3: Implement switch**
  - Add `_import_processing_backend()`.
  - Add `_import_job_processing_enabled()`.
  - Add `_enqueue_import_process_job()`.

- [ ] **Step 4: Verify green**

Run: `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_import_job_queue -v`

### Task 2: Shared Import Execution Bodies

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_import_api.py`, `tests/test_import_file_api.py`, `tests/test_etc_backend.py`, `tests/test_oa_manual_import_api.py`

- [ ] **Step 1: Extract bodies**
  - `_execute_general_import_confirm(batch_id)`
  - `_execute_file_import_confirm(session_id, selected_file_ids, owner_user_id, background_job_id=None)`
  - `_execute_tax_certified_import_confirm(session_id)`
  - `_execute_oa_manual_import(row_ids, actor_id)`
  - ETC processor method preserving reconciliation task transitions.

- [ ] **Step 2: Keep existing inline handlers on extracted bodies**

- [ ] **Step 3: Verify existing tests still pass**

### Task 3: Worker Processor Registry

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/app/worker.py`
- Test: `tests/test_import_job_queue.py`

- [ ] **Step 1: Add `Application.build_import_job_processors()`**
  - Map stable import types to execution body methods.

- [ ] **Step 2: Register processors in worker**
  - `--enable-import-job-processing` builds an `Application` and injects the registry into `ImportJobWorker`.

- [ ] **Step 3: Verify worker check exposes handler and route**

### Task 4: API Queue Wiring Per Import Family

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: existing API tests plus new queued-mode tests.

- [ ] **Step 1: Ordinary import**
  - Queue `general_import.confirm` with `batch_id`.

- [ ] **Step 2: File import**
  - Preserve background job response.
  - Queue `file_import.confirm` with `session_id`, `selected_file_ids`, `background_job_id`, `owner_user_id`.

- [ ] **Step 3: ETC import**
  - Preserve reconciliation validation and background job response.
  - Queue `etc_invoice_import.confirm` with task/session IDs and preview metadata.

- [ ] **Step 4: Tax certified import**
  - Queue `tax_certified_import.confirm` with `session_id`.

- [ ] **Step 5: Manual OA import**
  - Queue `oa_manual_import.create` with `row_ids` and `actor_id`.

### Task 5: Verification

Run:

```bash
PYTHONPATH=backend/src:tests python3 -m unittest \
  tests.test_import_job_queue \
  tests.test_import_api \
  tests.test_import_file_api \
  tests.test_rabbitmq_runtime \
  tests.test_rabbitmq_staging_preflight -v

PYTHONPATH=backend/src python3 -m py_compile \
  backend/src/fin_ops_platform/app/server.py \
  backend/src/fin_ops_platform/app/worker.py \
  backend/src/fin_ops_platform/services/import_job_queue.py

git diff --check
```

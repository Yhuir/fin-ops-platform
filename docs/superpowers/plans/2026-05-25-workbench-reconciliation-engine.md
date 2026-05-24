# Workbench Reconciliation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production-grade workbench reconciliation engine that replaces scattered automatic matching with paired/open decisions, DB-backed dirty execution, T-2/T/T+2 free matching, special/free domain isolation, and warning-aware OA attachment behavior.

**Architecture:** Add a focused automatic decision layer around `WorkbenchReconciliationEngine`: pure matching modules produce decisions, storage persists automatic decisions and dirty scopes, orchestration consumes them, and SQL projection/frontend only display `paired` and `open`. Manual relations remain in `app.workbench_pair_relations`; automatic decisions never mirror manual facts.

**Tech Stack:** Python services under `backend/src/fin_ops_platform`, PostgreSQL migrations/repositories, pytest/unittest backend tests, React/TypeScript workbench API mapping/tests under `web`, existing app server/workbench projection patterns.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md`
- Execution prompt: `docs/superpowers/prompts/2026-05-25-workbench-reconciliation-engine-execution.md`
- Product spec: `docs/product-specs/workbench.md`
- API contract: `docs/dev/reconciliation-workbench-v2-data-contracts.md`

## Execution Model

Use a fresh worktree before implementation. The current workspace contains unrelated dirty changes and must not be used for broad edits.

Recommended worktree:

```bash
git worktree add -b codex/workbench-reconciliation-engine ../fin-ops-platform-workbench-reconciliation HEAD
```

Run serial tasks where files overlap. Run only these tasks in parallel if using subagents:

- Task 2 can run before implementation workers and must finish first.
- Task 3 shared model contract must finish before storage/free/special workers.
- Task 4 storage, Task 5 pure free matching and Task 6 special adapter can run in parallel after Task 3 if each keeps to owned files.
- Tasks 7, 8, 9, 10 and 11 are serial integration tasks.

## File Structure

Create:

- `backend/src/fin_ops_platform/services/workbench_reconciliation_models.py`: dataclasses/constants for automatic decisions, warnings, statuses, match shape, scope ownership.
- `backend/src/fin_ops_platform/services/workbench_text_normalization.py`: text normalization and evidence token extraction.
- `backend/src/fin_ops_platform/services/workbench_free_matching_engine.py`: expenditure-only free matching rules over T-2/T/T+2.
- `backend/src/fin_ops_platform/services/workbench_special_reconciliation_adapter.py`: special rule adapter producing automatic decisions.
- `backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py`: orchestration of manual guards, special domain, free domain, claim resolving and persistence.
- `backend/src/fin_ops_platform/services/workbench_reconciliation_decision_store.py`: in-memory and repository-backed automatic decision service boundary.
- `backend/src/fin_ops_platform/services/workbench_reconciliation_dirty_queue.py`: DB-backed dirty scope queue boundary and in-memory fallback adapter.
- `backend/src/fin_ops_platform/postgres/migrations/0028_workbench_reconciliation_decisions.sql`: next available migration after inspecting current migrations.
- Focused tests:
  - `tests/test_workbench_reconciliation_models.py`
  - `tests/test_workbench_text_normalization.py`
  - `tests/test_workbench_free_matching_engine.py`
  - `tests/test_workbench_special_reconciliation_adapter.py`
  - `tests/test_workbench_reconciliation_decision_store.py`
  - `tests/test_workbench_reconciliation_dirty_queue.py`
  - `tests/test_workbench_reconciliation_engine.py`

Modify:

- `docs/product-specs/workbench.md`: update product contract to paired/open, T-2/T/T+2, warnings and DB dirty queue.
- `docs/dev/reconciliation-workbench-v2-data-contracts.md`: update API contract and remove display `needs_review`/`candidate` semantics.
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`: add repository methods for decisions and dirty scope if no better repository already exists.
- `backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py`: delegate automatic matching to `WorkbenchReconciliationEngine`.
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py` or `backend/src/fin_ops_platform/app/server.py`: consume/release automatic decisions on manual confirm/withdraw without changing manual fact ownership.
- `backend/src/fin_ops_platform/services/workbench_exception_application_service.py`: suppress/release automatic decisions on exception lifecycle.
- `backend/src/fin_ops_platform/app/worker.py`: DB dirty queue worker claim/complete/fail/retry execution.
- `backend/src/fin_ops_platform/services/workbench_sql_projection.py`: consume decisions, do not rebuild/promote candidates.
- `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`: remove business auto-close promotion from display path or fence it behind legacy-only code not used by SQL path.
- `backend/src/fin_ops_platform/app/server.py`: wire engine, dirty queue and response shape only where existing app composition requires it.
- `web/src/features/workbench/types.ts`: replace display group statuses with paired/open plus warnings.
- `web/src/features/workbench/api.ts`: map backend paired/open/warning payloads.
- `web/src/features/workbench/groupDisplayModel.ts`: remove candidate/needs_review display assumptions.
- Existing tests for orchestrator, SQL runtime, API, frontend workbench mapping.

Do not modify unrelated pending invoice, invoice usage/collection or RabbitMQ changes currently dirty in the workspace unless implementation truly requires it.

---

### Task 1: Isolate Worktree And Baseline

**Files:**
- No source files yet.

- [ ] **Step 1: Confirm current workspace dirty state**

Run:

```bash
git status --short
```

Expected: existing unrelated dirty files may be present. Do not stage or revert them.

- [ ] **Step 2: Create implementation worktree**

Run:

```bash
git worktree add -b codex/workbench-reconciliation-engine ../fin-ops-platform-workbench-reconciliation HEAD
```

Expected: new worktree created at `../fin-ops-platform-workbench-reconciliation`.

- [ ] **Step 3: Switch all implementation work to the worktree**

Run:

```bash
cd ../fin-ops-platform-workbench-reconciliation
git status --short
```

Expected: clean or only intentional plan/spec files if branch includes current commits.

- [ ] **Step 4: Read local instructions**

Run:

```bash
sed -n '1,220p' AGENTS.md
sed -n '1,180p' README.md
sed -n '1,180p' ARCHITECTURE.md
```

Expected: confirm repository-specific guidance before edits.

---

### Task 2: Contract Documentation

**Files:**
- Modify: `docs/product-specs/workbench.md`
- Modify: `docs/dev/reconciliation-workbench-v2-data-contracts.md`
- Test: document review by `rg`.

- [ ] **Step 1: Write contract update**

Update docs to state:

- workbench display states are `paired` and `open`;
- `needs_review` and `candidate` are no longer frontend display states;
- automatic free matching is expenditure-only;
- free matching window is `T-2 / T / T+2`;
- uniqueness checks cover the full five-month candidate window;
- cross-month decision ownership uses bank trade month when bank rows exist, otherwise OA month;
- OA source attachment amount mismatch yields `invoice_amount_mismatch` warning and `invoice_amount_closed=false`;
- manual relations remain in `app.workbench_pair_relations`;
- automatic decisions use `display_state` and `decision_status`;
- DB-backed dirty scope queue is the production execution mechanism.

- [ ] **Step 2: Verify old display contract is removed or marked obsolete**

Run:

```bash
rg -n "needs_review|candidate" docs/product-specs/workbench.md docs/dev/reconciliation-workbench-v2-data-contracts.md
```

Expected: remaining matches are explicitly marked as legacy/internal compatibility, not current display contract.

- [ ] **Step 3: Commit docs**

Run:

```bash
git add docs/product-specs/workbench.md docs/dev/reconciliation-workbench-v2-data-contracts.md
git commit -m "docs: update workbench reconciliation contract"
```

Expected: commit created.

---

### Task 3: Shared Model Contract

**Files:**
- Create: `backend/src/fin_ops_platform/services/workbench_reconciliation_models.py`
- Test: `tests/test_workbench_reconciliation_models.py`

- [ ] **Step 1: Write model contract tests**

Cover:

- `display_state` values are exactly `paired` and `open`;
- `decision_status` values are exactly `proposed`, `paired`, `open`, `suppressed`, `consumed`, `expired`;
- `match_domain` values are `free` and `special`;
- warning code `invoice_amount_mismatch` exists;
- bank-containing decisions use bank trade month as primary `scope_month`;
- OA+invoice decisions without bank use OA month;
- month expansion returns `T-2/T/T+2`;
- model serializes to plain dictionaries usable by repositories.

Run:

```bash
pytest tests/test_workbench_reconciliation_models.py -q
```

Expected: fail.

- [ ] **Step 2: Implement shared models**

Create canonical dataclasses/constants only. Do not implement matching logic here.

Expected public names:

```python
DISPLAY_STATE_PAIRED = "paired"
DISPLAY_STATE_OPEN = "open"
DECISION_STATUS_PAIRED = "paired"
DECISION_STATUS_OPEN = "open"
DECISION_STATUS_PROPOSED = "proposed"
DECISION_STATUS_SUPPRESSED = "suppressed"
DECISION_STATUS_CONSUMED = "consumed"
DECISION_STATUS_EXPIRED = "expired"
MATCH_DOMAIN_FREE = "free"
MATCH_DOMAIN_SPECIAL = "special"
WARNING_INVOICE_AMOUNT_MISMATCH = "invoice_amount_mismatch"
```

- [ ] **Step 3: Run model tests**

Run:

```bash
pytest tests/test_workbench_reconciliation_models.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

Run:

```bash
git add backend/src/fin_ops_platform/services/workbench_reconciliation_models.py tests/test_workbench_reconciliation_models.py
git commit -m "feat: add workbench reconciliation model contract"
```

---

### Task 4: Schema, Decision Store, Dirty Queue

**Files:**
- Create: `backend/src/fin_ops_platform/postgres/migrations/0028_workbench_reconciliation_decisions.sql`
- Create: `backend/src/fin_ops_platform/services/workbench_reconciliation_decision_store.py`
- Create: `backend/src/fin_ops_platform/services/workbench_reconciliation_dirty_queue.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Test: `tests/test_workbench_reconciliation_decision_store.py`
- Test: `tests/test_workbench_reconciliation_dirty_queue.py`
- Test: `tests/test_postgres_migrations.py`

- [ ] **Step 1: Write failing migration tests**

Add expectations covering:

- table `read_model.workbench_reconciliation_decisions`;
- unique `(tenant_id, decision_key)`;
- index for `(tenant_id, scope_month, decision_status)`;
- row id lookup support;
- dirty scope queue fields `tenant_id`, `lease_owner`, `lease_expires_at`, `available_at`, `source_versions`.
- dirty queue configuration/run lifecycle fields or supporting matching run records for `request_id`, `started_at`, completion/failure timestamps, `duration_ms`, status and error summary.

Run:

```bash
pytest tests/test_postgres_migrations.py -q
```

Expected: fail because migration is missing.

- [ ] **Step 2: Add migration**

Create the next available migration after inspecting `backend/src/fin_ops_platform/postgres/migrations/`. If `0028` already exists, use the next number.

Minimum DDL shape:

```sql
create table if not exists read_model.workbench_reconciliation_decisions (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    scope_month date not null,
    decision_key text not null,
    display_state text,
    decision_status text not null,
    match_domain text not null,
    match_shape text not null,
    rule_code text not null,
    rule_version text not null,
    row_ids text[] not null default '{}',
    row_types text[] not null default '{}',
    oa_row_ids text[] not null default '{}',
    bank_row_ids text[] not null default '{}',
    invoice_row_ids text[] not null default '{}',
    amount numeric(18, 2),
    direction text,
    cardinality text,
    payment_amount_closed boolean not null default false,
    invoice_amount_closed boolean not null default false,
    warnings jsonb not null default '[]'::jsonb,
    evidence jsonb not null default '{}'::jsonb,
    blockers jsonb not null default '[]'::jsonb,
    conflict_set jsonb not null default '[]'::jsonb,
    source_versions jsonb not null default '{}'::jsonb,
    consumed_by_relation_id uuid,
    suppressed_by_exception_case_id uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
```

Add check constraints for status/domain where compatible with existing migration style.

- [ ] **Step 3: Add repository/store tests**

Test:

- upsert is idempotent by `decision_key`;
- list by scope and status;
- consume by row ids writes `decision_status=consumed`;
- suppress by row ids writes `decision_status=suppressed`;
- expire stale source version decisions;
- dirty queue expands `T-2/T/T+2`;
- claim due scopes locks/marks running;
- retry increments attempt count and sets available_at;
- stale lease can be reclaimed.
- debounce, lease timeout, retry max attempts and retry backoff are configurable.
- matching run lifecycle is recorded with request_id, started_at, completed_at/failed_at, duration_ms, status, source_versions and error summary.

Run:

```bash
pytest tests/test_workbench_reconciliation_decision_store.py tests/test_workbench_reconciliation_dirty_queue.py -q
```

Expected: fail until implementation exists.

- [ ] **Step 4: Implement store and queue**

Implement focused APIs:

```python
class WorkbenchReconciliationDecisionStore:
    def upsert_decisions(self, decisions: list[WorkbenchDecision]) -> None: ...
    def list_decisions(self, scope_month: str, *, statuses: set[str] | None = None) -> list[dict[str, object]]: ...
    def consume_by_row_ids(self, row_ids: list[str], *, relation_id: str) -> int: ...
    def suppress_by_row_ids(self, row_ids: list[str], *, exception_case_id: str) -> int: ...
    def expire_stale(self, scope_months: list[str], *, source_versions: dict[str, object]) -> int: ...
```

```python
class WorkbenchReconciliationDirtyQueue:
    def mark_dirty_expanded(self, months: list[str], *, reason: str, source_versions: dict[str, object] | None = None) -> list[str]: ...
    def claim_due_scopes(self, *, worker_id: str, limit: int, lease_seconds: int) -> list[str]: ...
    def complete(self, scope_month: str, *, source_versions: dict[str, object]) -> None: ...
    def fail(self, scope_month: str, *, error: str, retry_delay_seconds: int) -> None: ...
```

Expose config defaults through a small options object or existing app config/env pattern:

```python
dirty_debounce_seconds = 60
lease_timeout_seconds = 600
retry_max_attempts = 5
retry_backoff_seconds = [60, 300, 900, 1800, 3600]
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/test_postgres_migrations.py tests/test_workbench_reconciliation_decision_store.py tests/test_workbench_reconciliation_dirty_queue.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/src/fin_ops_platform/postgres/migrations backend/src/fin_ops_platform/services/workbench_reconciliation_decision_store.py backend/src/fin_ops_platform/services/workbench_reconciliation_dirty_queue.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py tests/test_postgres_migrations.py tests/test_workbench_reconciliation_decision_store.py tests/test_workbench_reconciliation_dirty_queue.py
git commit -m "feat: add workbench reconciliation decision storage"
```

---

### Task 5: Pure Free Matching Engine

**Files:**
- Modify: `backend/src/fin_ops_platform/services/workbench_reconciliation_models.py` only if model contract needs non-breaking helper additions.
- Create: `backend/src/fin_ops_platform/services/workbench_text_normalization.py`
- Create: `backend/src/fin_ops_platform/services/workbench_free_matching_engine.py`
- Test: `tests/test_workbench_text_normalization.py`
- Test: `tests/test_workbench_free_matching_engine.py`

- [ ] **Step 1: Write text normalization tests**

Cover:

- company suffix removal does not make `有限公司` a valid standalone match;
- low-information tokens `报销`、`付款`、`费用` cannot match alone;
- applicant/project/reason, counterparty/summary/remark and seller name evidence report source fields.

Run:

```bash
pytest tests/test_workbench_text_normalization.py -q
```

Expected: fail.

- [ ] **Step 2: Implement text normalization**

Implement a small focused API:

```python
def normalize_match_text(value: object) -> str: ...
def evidence_tokens(fields: dict[str, object]) -> list[EvidenceToken]: ...
def matching_tokens(left: list[EvidenceToken], right: list[EvidenceToken]) -> list[dict[str, str]]: ...
```

- [ ] **Step 3: Write free matching tests**

Cover:

- exact OA+bank+invoice 1:1:1 in five-month window;
- OA+bank+multiple invoices exact unique sum;
- OA source attachment invoices with amount mismatch yields paired plus warning;
- two-way OA+bank and OA+invoice upgrade to three-way;
- competing adjacent-month invoice keeps all rows open;
- income rows ignored;
- two-way fallback only after three-way cannot uniquely form.

Run:

```bash
pytest tests/test_workbench_free_matching_engine.py -q
```

Expected: fail.

- [ ] **Step 4: Implement free engine**

Use the shared model contract from Task 3. Implement:

- decision model with `display_state`, `decision_status`, `match_domain`, `match_shape`, warnings, blockers and evidence;
- scope ownership helpers;
- five-month uniqueness resolver;
- warning generation for `invoice_amount_mismatch`;
- open blockers for conflicts.

- [ ] **Step 5: Run focused tests**

Run:

```bash
pytest tests/test_workbench_text_normalization.py tests/test_workbench_free_matching_engine.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/src/fin_ops_platform/services/workbench_reconciliation_models.py backend/src/fin_ops_platform/services/workbench_text_normalization.py backend/src/fin_ops_platform/services/workbench_free_matching_engine.py tests/test_workbench_text_normalization.py tests/test_workbench_free_matching_engine.py
git commit -m "feat: add workbench free reconciliation engine"
```

---

### Task 6: Special Rule Adapter

**Files:**
- Create: `backend/src/fin_ops_platform/services/workbench_special_reconciliation_adapter.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_special_pair_rule_service.py` only if needed.
- Test: `tests/test_workbench_special_reconciliation_adapter.py`

- [ ] **Step 1: Write special adapter tests**

Cover:

- deterministic internal transfer outputs `paired`;
- salary/no-OA batch row is special-domain and excluded from free matching;
- hint-only external turnover/cash turnover remains open or non-projected;
- offset/冲 deterministic configuration outputs `paired`;
- special claim beats free matching for the same row.

Run:

```bash
pytest tests/test_workbench_special_reconciliation_adapter.py -q
```

Expected: fail.

- [ ] **Step 2: Implement adapter**

Convert existing detector/service outputs into `WorkbenchDecision` objects without changing free matching.

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/test_workbench_special_reconciliation_adapter.py tests/test_workbench_special_pair_rule_service.py -q
```

Expected: pass.

- [ ] **Step 4: Commit**

Run:

```bash
git add backend/src/fin_ops_platform/services/workbench_special_reconciliation_adapter.py backend/src/fin_ops_platform/services/workbench_special_pair_rule_service.py tests/test_workbench_special_reconciliation_adapter.py
git commit -m "feat: adapt workbench special reconciliation rules"
```

---

### Task 7: DB Dirty Queue Production Wiring

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/app/worker.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_reconciliation_dirty_queue.py`
- Test: `tests/test_workbench_reconciliation_dirty_queue.py`
- Test: `tests/test_workbench_matching_orchestrator.py` or new focused lifecycle tests.

- [ ] **Step 1: Write production dirty queue tests**

Cover:

- OA sync/rebuild marks `T-2/T/T+2` dirty scopes in DB queue;
- bank import and invoice import mark expanded dirty scopes;
- manual confirm and withdraw mark expanded dirty scopes;
- exception create/close marks expanded dirty scopes;
- worker claims due scopes with lease and completes/fails/retries in DB queue;
- worker records request_id, started_at, completed_at/failed_at, duration_ms, status, source_versions and error summary;
- debounce, lease timeout, retry max attempts and retry backoff are configurable;
- admin/manual rebuild marks expanded dirty scopes with operator/reason;
- rule-version backfill marks affected months dirty and prevents stale results overwriting newer decisions;
- in-memory dirty service is only used when DB queue is unavailable.

Run:

```bash
pytest tests/test_workbench_reconciliation_dirty_queue.py tests/test_workbench_matching_orchestrator.py -q
```

Expected: fail until wiring is complete.

- [ ] **Step 2: Wire dirty writes**

Find current calls to `_run_workbench_auto_matching_for_scopes`, `_enqueue_workbench_auto_matching_for_scopes`, and `WorkbenchMatchingDirtyScopeService.mark_dirty`. Replace production write paths so they call DB-backed dirty queue mark/expand methods.

Do not remove in-memory fallback yet. Gate it behind repository availability.

- [ ] **Step 3: Wire worker claim/complete/fail**

Update worker/server dirty scope loop to claim due DB rows, run reconciliation, then complete/fail/retry through DB queue.

Each run must create or update a matching run audit record. Use the existing `app.matching_runs` table if it fits; otherwise add the minimal fields in the migration from Task 4.

- [ ] **Step 4: Wire admin rebuild and rule-version backfill**

Add an explicit callable/service path for rebuilding one month. It must:

- mark expanded dirty scopes;
- record operator and reason;
- preserve manual relations and special paired facts;
- enqueue or trigger DB worker processing.

Add rule-version backfill handling so changes in matching/free/special rule versions mark affected months dirty and stale results cannot overwrite newer decisions.

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/test_workbench_reconciliation_dirty_queue.py tests/test_workbench_matching_orchestrator.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/worker.py backend/src/fin_ops_platform/services/workbench_reconciliation_dirty_queue.py tests/test_workbench_reconciliation_dirty_queue.py tests/test_workbench_matching_orchestrator.py
git commit -m "feat: wire workbench dirty queue production path"
```

---

### Task 8: Engine Orchestration And Lifecycle

**Files:**
- Create: `backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_exception_application_service.py`
- Test: `tests/test_workbench_reconciliation_engine.py`
- Test: `tests/test_workbench_matching_orchestrator.py`
- Test: `tests/test_workbench_exception_application_service.py`

- [ ] **Step 1: Write engine orchestration tests**

Cover:

- manual relation row ids are excluded;
- special decisions claim before free matching;
- free matching sees T-2/T/T+2 rows;
- decisions persist only to primary scope month;
- stale source versions expire;
- conflict rows become open, not paired.

Run:

```bash
pytest tests/test_workbench_reconciliation_engine.py -q
```

Expected: fail.

- [ ] **Step 2: Implement engine**

Implement pipeline:

```text
manual guard -> special adapter -> free engine -> claim resolver -> decision store -> scope summary
```

- [ ] **Step 3: Update orchestrator**

`WorkbenchMatchingOrchestrator.run()` should delegate automatic decision generation to the new engine and stop writing display-driving `needs_review` candidates.

- [ ] **Step 4: Add lifecycle tests**

Cover:

- manual confirm consumes automatic decisions;
- withdraw releases and marks expanded dirty;
- exception suppresses decisions;
- closing exception marks expanded dirty.

- [ ] **Step 5: Wire lifecycle hooks**

Use existing manual relation and exception services/server paths. Preserve manual relation fact source.

- [ ] **Step 6: Run tests**

Run:

```bash
pytest tests/test_workbench_reconciliation_engine.py tests/test_workbench_matching_orchestrator.py tests/test_workbench_exception_application_service.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_exception_application_service.py tests/test_workbench_reconciliation_engine.py tests/test_workbench_matching_orchestrator.py tests/test_workbench_exception_application_service.py
git commit -m "feat: wire workbench reconciliation engine"
```

---

### Task 9: Projection And API Contract

**Files:**
- Modify: `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_workbench_sql_runtime.py`
- Test: `tests/test_workbench_api.py`
- Test: `tests/test_workbench_v2_api.py`

- [ ] **Step 1: Write projection/API tests**

Cover:

- active manual relations project first;
- `decision_status=paired` and `display_state=paired` forms paired group;
- `decision_status=open` and `display_state=open` forms open rows;
- proposed/suppressed/consumed/expired decisions do not project;
- warning payload reaches API;
- no display `needs_review`/`candidate`.

Run:

```bash
pytest tests/test_workbench_sql_runtime.py tests/test_workbench_api.py tests/test_workbench_v2_api.py -q
```

Expected: fail until projection changes are complete.

- [ ] **Step 2: Remove business matching from projection**

Stop rebuilding candidates inside SQL projection. Projection should read active pair relations and automatic decisions.

- [ ] **Step 3: Fence or remove grouping auto-promotion**

`WorkbenchCandidateGroupingService` must not create business `auto_closed` decisions from display-only grouping in the production SQL path.

- [ ] **Step 4: Update server response compatibility**

Keep endpoint routes stable, but response group type/status should expose only paired/open plus warning metadata.

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/test_workbench_sql_runtime.py tests/test_workbench_api.py tests/test_workbench_v2_api.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/src/fin_ops_platform/services/workbench_sql_projection.py backend/src/fin_ops_platform/services/workbench_candidate_grouping.py backend/src/fin_ops_platform/app/server.py tests/test_workbench_sql_runtime.py tests/test_workbench_api.py tests/test_workbench_v2_api.py
git commit -m "feat: project workbench reconciliation decisions"
```

---

### Task 10: Frontend Paired/Open/Warn Display

**Files:**
- Modify: `web/src/features/workbench/types.ts`
- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/features/workbench/groupDisplayModel.ts`
- Test: `web/src/test/WorkbenchApi.test.ts`
- Test: `web/src/test/WorkbenchApiRuntimePath.test.ts`
- Test: `web/src/test/groupDisplayModel.test.ts`
- Test: `web/src/test/WorkbenchZone.test.tsx`

- [ ] **Step 1: Write frontend mapping tests**

Cover:

- backend paired/open maps to frontend group types;
- warning payload maps to row/group warning list;
- `needs_review` and display `candidate` payloads are rejected or treated as legacy-only, not current display.

Run:

```bash
npm --prefix web test -- --run WorkbenchApi WorkbenchApiRuntimePath groupDisplayModel WorkbenchZone --no-file-parallelism
```

Expected: fail until mapping changes are complete.

- [ ] **Step 2: Update types and mapping**

Update TypeScript types to represent:

- group display state paired/open;
- warnings including `invoice_amount_mismatch`;
- payment/invoice amount closed flags.

- [ ] **Step 3: Update display model**

Remove display logic that treats candidate/needs_review as a current group category.

- [ ] **Step 4: Run frontend tests**

Run:

```bash
npm --prefix web test -- --run WorkbenchApi WorkbenchApiRuntimePath groupDisplayModel WorkbenchZone --no-file-parallelism
```

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add web/src/features/workbench/types.ts web/src/features/workbench/api.ts web/src/features/workbench/groupDisplayModel.ts web/src/test/WorkbenchApi.test.ts web/src/test/WorkbenchApiRuntimePath.test.ts web/src/test/groupDisplayModel.test.ts web/src/test/WorkbenchZone.test.tsx
git commit -m "feat: display workbench paired open decisions"
```

---

### Task 11: Integration Verification And Cleanup

**Files:**
- Modify only files needed to integrate previous tasks.
- Test: focused backend/frontend suites.

- [ ] **Step 1: Search old display semantics**

Run:

```bash
rg -n "needs_review|candidate" backend/src/fin_ops_platform/services/workbench* backend/src/fin_ops_platform/app web/src/features/workbench docs/dev/reconciliation-workbench-v2-data-contracts.md docs/product-specs/workbench.md
```

Expected: no current display contract remains. Any match must be internal compatibility, migration notes, or tests asserting absence.

- [ ] **Step 2: Run focused backend tests**

Run:

```bash
pytest tests/test_workbench_reconciliation_models.py tests/test_workbench_text_normalization.py tests/test_workbench_free_matching_engine.py tests/test_workbench_special_reconciliation_adapter.py tests/test_workbench_reconciliation_decision_store.py tests/test_workbench_reconciliation_dirty_queue.py tests/test_workbench_reconciliation_engine.py tests/test_workbench_matching_orchestrator.py -q
```

Expected: pass.

- [ ] **Step 3: Run focused projection/API tests**

Run:

```bash
pytest tests/test_workbench_sql_runtime.py tests/test_workbench_api.py tests/test_workbench_v2_api.py tests/test_postgres_migrations.py -q
```

Expected: pass.

- [ ] **Step 4: Run focused frontend tests**

Run:

```bash
npm --prefix web test -- --run WorkbenchApi WorkbenchApiRuntimePath groupDisplayModel WorkbenchZone --no-file-parallelism
```

Expected: pass.

- [ ] **Step 5: Run broader checks if practical**

Run:

```bash
pytest tests/test_workbench_candidate_grouping.py tests/test_workbench_candidate_match_service.py tests/test_workbench_matching_dirty_scope_service.py -q
npm --prefix web run build
```

Expected: pass, or document unrelated pre-existing failures.

- [ ] **Step 6: Final commit**

Run:

```bash
git status --short
git add <only intentional files>
git commit -m "feat: integrate workbench reconciliation engine"
```

Expected: clean implementation commits on `codex/workbench-reconciliation-engine`.

---

## Final Acceptance Criteria

- Workbench API/frontend display only `paired` and `open`.
- No user-facing display path exposes `needs_review` or `candidate`.
- Free matching is expenditure-only and uses full `T-2/T/T+2` uniqueness.
- OA source attachment invoice amount mismatch remains grouped with warning.
- Manual relations remain only in `app.workbench_pair_relations`.
- Automatic decisions persist with `display_state` and `decision_status`.
- DB-backed dirty queue supports mark/claim/complete/fail/retry/lease.
- DB-backed dirty queue supports configurable debounce/lease/retry/backoff.
- Matching executions record request_id, started_at, completed/failure timestamps, duration, status, source versions and errors.
- Admin/manual rebuild and rule-version backfill are covered by tests.
- SQL projection consumes decisions and does not generate business matches.
- Tests cover rules, storage, dirty queue, orchestration, projection, API and frontend mapping.

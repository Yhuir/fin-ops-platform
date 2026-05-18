# 日常报销批量账务管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade “批量账务” page that lets finance users manually associate “批量账务集中处理” bank outflows with one or more unmatched daily reimbursement OA rows, including existing OA-attached invoice rows, with submit/withdraw backed by workbench pair relations.

**Architecture:** Add a dedicated backend application service and API route for batch accounting, but persist the business fact through the existing workbench pair relation service. Add a dedicated frontend API mapper and page modeled after `NoOaBankBatchPage`, while keeping UI state and submit validation local to this page.

**Tech Stack:** Python backend services under `backend/src/fin_ops_platform`, unittest backend tests, React + TypeScript + MUI frontend, Vitest + Testing Library frontend tests.

---

## File Map

Backend:

- Create `backend/src/fin_ops_platform/services/batch_accounting_service.py`
  - Build list payloads for year/bucket.
  - Resolve eligible bank rows and OA rows from workbench grouped payload.
  - Submit and withdraw through `WorkbenchPairRelationService`.
- Modify `backend/src/fin_ops_platform/app/server.py`
  - Route `GET /api/batch-accounting`.
  - Route `POST /api/batch-accounting/submit`.
  - Route `POST /api/batch-accounting/{relation_id}/withdraw`.
  - Instantiate and wire service dependencies.
- Test `tests/test_batch_accounting_api.py`
  - API contract and mutation behavior.

Frontend:

- Create `web/src/features/batchAccounting/types.ts`
  - Typed page DTOs.
- Create `web/src/features/batchAccounting/api.ts`
  - Fetch/submit/withdraw APIs and snake_case to camelCase mapping.
- Create `web/src/pages/BatchAccountingPage.tsx`
  - UI and interactions.
- Modify `web/src/app/router.tsx`
  - Add route `/batch-accounting`.
- Modify `web/src/components/shell/sidebarItems.ts`
  - Add menu item “批量账务”.
- Test `web/src/test/BatchAccountingPage.test.tsx`
  - Page behavior.
- Modify `web/src/test/App.test.tsx`
  - Sidebar ordering.

Docs:

- Keep `docs/superpowers/specs/2026-05-18-batch-accounting-design.md` updated if implementation reveals a necessary contract adjustment.

## Task 1: Backend API and Service

**Files:**

- Create: `backend/src/fin_ops_platform/services/batch_accounting_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_batch_accounting_api.py`

- [ ] **Step 1: Write failing backend API tests**

Create tests covering:

1. `GET /api/batch-accounting?year=2026&bucket=unsubmitted` returns only bank rows whose `counterparty_name` is exactly `批量账务集中处理`, direction is expense, and year is 2026.
2. Unsubmitted OA rows include only unmatched whole daily reimbursement OA rows.
3. OA rows include `linked_invoice_row_ids` when an OA-attached invoice is in the same open group.
4. `POST /api/batch-accounting/submit` rejects amount mismatch with `batch_accounting_amount_mismatch`.
5. Submit success creates a `manual_confirmed` relation with `special_metadata.source == "batch_accounting"` and row ids including the bank row, selected OA rows, and linked invoice rows.
6. `GET ...bucket=submitted` returns submitted relations.
7. Withdraw restores the previous relation snapshot; specifically, if OA + invoice existed before submit, they remain related after withdraw.

Run:

```bash
PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m unittest tests.test_batch_accounting_api -v
```

Expected: FAIL because API/service does not exist.

- [ ] **Step 2: Implement service payload builder**

Implement `BatchAccountingService` with methods:

```python
class BatchAccountingService:
    def build_payload(self, *, year: str, bucket: str) -> dict[str, Any]:
        ...
    def submit(self, *, year: str, bank_row_id: str, oa_row_ids: list[str], actor: str, expected_version: int | None) -> dict[str, Any]:
        ...
    def withdraw(self, *, relation_id: str, actor: str, reason: str, expected_version: int | None) -> dict[str, Any]:
        ...
```

The service may receive callables/dependencies from `Application`:

- `workbench_payload_provider(month_or_all)`
- `pair_relation_service`
- `month_invalidator`
- `persist_scheduler`

Implementation detail:

- Use `/api/workbench?month=all` style grouped payload internally via existing `_build_api_workbench_payload("all")` or targeted year month loops if more efficient.
- Extract bank rows from open/paired groups.
- Extract OA rows from open groups.
- Treat whole OA rows by row id starting `oa-exp-` or `type == "oa"` and `apply_type`/`expense_type` containing `日常报销`.
- Find OA attached invoice ids from the same group's `invoice_rows`.
- Exact bank counterparty check must be strict string equality after stripping surrounding whitespace only.
- Expense bank amount comes from `debit_amount`.

- [ ] **Step 3: Implement submit through pair relation**

On submit:

- Rebuild current payload.
- Validate bank row and OA rows are still eligible.
- Compute `bank_amount == sum(oa_amounts)`.
- Build row_ids = `[bank_row_id, *oa_row_ids, *linked_invoice_row_ids]`.
- Use `WorkbenchPairRelationService.replace_with_confirmed_relation(...)` directly or call an Application helper that records before relations the same way `confirm-link` does.
- Set:

```python
special_metadata={
    "source": "batch_accounting",
    "bank_row_id": bank_row_id,
    "oa_row_ids": oa_row_ids,
    "invoice_row_ids": invoice_row_ids,
    "year": year,
    "created_by": actor,
}
```

- Invalidate affected workbench scopes and persist pair relation/read models using existing server helpers.

- [ ] **Step 4: Implement withdraw**

On withdraw:

- Resolve active relation by `relation_id`.
- Require `special_metadata.source == "batch_accounting"`.
- Use existing `withdraw_latest_for_row_ids` or equivalent history restore path, not raw cancel.
- Require non-empty reason.
- Invalidate/persist affected scopes.

- [ ] **Step 5: Wire routes in `server.py`**

Add routes:

- `GET /api/batch-accounting`
- `POST /api/batch-accounting/submit`
- `POST /api/batch-accounting/{relation_id}/withdraw`

Use existing OA session mutation checks for submit/withdraw.

- [ ] **Step 6: Run backend tests**

```bash
PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m unittest tests.test_batch_accounting_api tests.test_workbench_v2_api -v
```

Expected: PASS.

## Task 2: Frontend Page, Routing, and API Client

**Files:**

- Create: `web/src/features/batchAccounting/types.ts`
- Create: `web/src/features/batchAccounting/api.ts`
- Create: `web/src/pages/BatchAccountingPage.tsx`
- Modify: `web/src/app/router.tsx`
- Modify: `web/src/components/shell/sidebarItems.ts`
- Modify: `web/src/test/App.test.tsx`
- Test: `web/src/test/BatchAccountingPage.test.tsx`

- [ ] **Step 1: Write failing frontend tests**

Create `BatchAccountingPage.test.tsx` covering:

1. Renders title `日常报销批量账务管理`.
2. Renders `未提交 / 已提交` toggle and a year selector.
3. Left panel renders bank rows as list items, not a table.
4. Right panel renders OA rows with applicant/time, project name, amount, reason.
5. Multi-select updates selected count and selected OA total in real time.
6. Amount mismatch disables `关联OA项与流水`.
7. Amount match enables submit and posts selected row ids.
8. Submitted bucket renders read-only associated OA and `撤回关联`.
9. Sidebar includes `批量账务`.

Run:

```bash
cd web
npm test -- --run src/test/BatchAccountingPage.test.tsx src/test/App.test.tsx
```

Expected: FAIL because files/routes do not exist.

- [ ] **Step 2: Implement API client**

Create mappers for:

- `fetchBatchAccounting({ year, bucket })`
- `submitBatchAccounting({ year, bankRowId, oaRowIds, expectedVersion })`
- `withdrawBatchAccounting({ relationId, expectedVersion, reason })`

Map snake_case API fields to camelCase. Reject HTML/non-JSON using the same style as `noOaBankBatches/api.ts`.

- [ ] **Step 3: Implement page**

Use MUI components and follow `NoOaBankBatchPage` density:

- PageScaffold title.
- Top Paper with ToggleButtonGroup, TextField type-ish year input, refresh button.
- Main grid: `gridTemplateColumns: { xs: "1fr", lg: "30% minmax(0, 1fr)" }`.
- Left list uses `Paper`/`Box` clickable items, not `Table`.
- Right uses `Table`.
- Project/reason long text uses collapsed display and row-local expand buttons.
- Keep selected OA ids in state.
- Recompute selected total with `useMemo`.
- Disable submit if no bank, no OA, mutating, or amount mismatch.
- Dispatch `workbenchRelationUpdated` after submit/withdraw.

- [ ] **Step 4: Wire route and sidebar**

- Import page in `web/src/app/router.tsx`.
- Add `<Route path="/batch-accounting" element={<BatchAccountingPage />} />`.
- Add sidebar item near `免OA流水批量处理`, label `批量账务`.

- [ ] **Step 5: Run frontend tests**

```bash
cd web
npm test -- --run src/test/BatchAccountingPage.test.tsx src/test/App.test.tsx
```

Expected: PASS.

## Task 3: Integration Verification and Hardening

**Files:**

- Modify if needed based on failures only.
- Test commands below.

- [ ] **Step 1: Run focused backend tests**

```bash
PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m unittest \
  tests.test_batch_accounting_api \
  tests.test_workbench_v2_api \
  tests.test_workbench_candidate_grouping \
  -v
```

- [ ] **Step 2: Run focused frontend tests**

```bash
cd web
npm test -- --run src/test/BatchAccountingPage.test.tsx src/test/App.test.tsx src/test/WorkbenchSelection.test.tsx
```

- [ ] **Step 3: Run build/type checks if focused tests pass**

```bash
cd web
npm run build
```

- [ ] **Step 4: Smoke with local backend**

Restart backend if needed:

```bash
cd /Users/yu/Desktop/fin-ops-platform
FIN_OPS_DEV_ALLOW_LOCAL_SESSION=1 PYTHONPATH=backend/src /opt/miniconda3/bin/python3 -m fin_ops_platform.app.main --host 127.0.0.1 --port 8001
```

Smoke:

```bash
curl -sS "http://127.0.0.1:8001/api/batch-accounting?year=2026&bucket=unsubmitted"
```

Expected: JSON payload with `summary`, `bank_rows`, and `oa_rows`.

## Multi-Agent Execution Notes

- Backend worker owns backend service, backend routes, and backend tests.
- Frontend worker owns frontend page, frontend API mapper, router/sidebar, and frontend tests.
- Verification worker runs after backend and frontend changes land; it does not make broad product changes.
- Workers must not revert unrelated existing changes in the working tree.

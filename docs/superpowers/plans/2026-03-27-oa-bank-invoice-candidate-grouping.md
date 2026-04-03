# OA-Bank-Invoice Candidate Grouping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a workbench that only auto-closes high-confidence `OA ↔ 银行流水 ↔ 发票` chains and renders all remaining records as horizontally aligned candidate groups in `已配对` and `未配对`.

**Architecture:** Keep existing row-level detail and action flows, but insert a backend candidate-group assembly layer between the current workbench row sources and `/api/workbench`. Upgrade the React workbench from three independent pane tables to a group-oriented layout where each row renders `OA | 银行流水 | 发票` cells, preserving splitter resizing and record-level actions inside each cell.

**Tech Stack:** Python stdlib backend services, existing in-memory/local-persistence app architecture, React 18, TypeScript, Vite, Vitest, Testing Library.

---

## File Map

### Backend

- Create: `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`
  - Assemble high-confidence auto-closed groups and open candidate groups
  - Own temporary grouping keys for records without `case_id`
- Modify: `backend/src/fin_ops_platform/services/live_workbench_service.py`
  - Expose bank/invoice rows in a grouping-friendly structure
- Modify: `backend/src/fin_ops_platform/services/workbench_query_service.py`
  - Keep OA rows available in a grouping-friendly structure
- Modify: `backend/src/fin_ops_platform/app/server.py`
  - Change `/api/workbench` response shape from pane rows to grouped rows
  - Keep `/api/workbench/rows/{row_id}` and row actions working
- Modify: `tests/test_live_workbench_service.py`
- Modify: `tests/test_workbench_v2_api.py`
- Create: `tests/test_workbench_candidate_grouping.py`

### Frontend

- Modify: `web/src/features/workbench/types.ts`
  - Add candidate group types
- Modify: `web/src/features/workbench/api.ts`
  - Map grouped API payloads
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
  - Consume grouped data instead of `paired.oa / bank / invoice`
- Replace or heavily modify: `web/src/components/workbench/WorkbenchZone.tsx`
  - Render grouped rows instead of three independent pane tables
- Replace or heavily modify: `web/src/components/workbench/ResizableTriPane.tsx`
  - Keep width-resize mechanics but render grouped rows per zone
- Modify: `web/src/components/workbench/PaneTable.tsx`
  - Either remove or repurpose into record-card rendering
- Create: `web/src/components/workbench/CandidateGroupGrid.tsx`
  - Zone body rendering for grouped rows
- Create: `web/src/components/workbench/CandidateGroupCell.tsx`
  - Per-column cell that can show `0..N` records
- Create: `web/src/components/workbench/WorkbenchRecordCard.tsx`
  - Record-level UI used inside grouped cells
- Modify: `web/src/app/styles.css`
  - Add grouped-row layout, blank-cell state, multi-record stack styling
- Modify: `web/src/test/WorkbenchSelection.test.tsx`
- Create: `web/src/test/CandidateGroupGrid.test.tsx`
- Modify: `web/src/test/apiMock.ts`

### Docs

- Modify: `README.md`
- Modify: `web/README.md`
- Modify: `docs/dev/reconciliation-workbench-v2-backend.md`
- Modify: `docs/dev/reconciliation-workbench-v2-frontend.md`

---

### Task 1: Lock backend red tests for high-confidence closure and candidate grouping

**Files:**
- Create: `tests/test_workbench_candidate_grouping.py`
- Modify: `tests/test_live_workbench_service.py`
- Modify: `tests/test_workbench_v2_api.py`

- [ ] **Step 1: Write the failing grouping service tests**

Add tests that cover:

- unique `OA ↔ 银行流水` pair becomes `auto_closed`
- unique `银行流水 ↔ 发票` pair becomes `auto_closed`
- unique `OA ↔ 银行流水 ↔ 发票` chain becomes one `paired group`
- one OA with two candidate bank rows stays `candidate`
- one bank row with two candidate invoice rows stays `candidate`
- missing pane data still yields a visible group with an empty cell

- [ ] **Step 2: Run the failing backend tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_candidate_grouping tests.test_live_workbench_service tests.test_workbench_v2_api -v
```

Expected:

- FAIL because grouped payload and candidate grouping service do not exist yet

- [ ] **Step 3: Add minimal test scaffolding imports**

Create placeholder imports and fixture helpers so tests fail on behavior instead of missing modules.

- [ ] **Step 4: Re-run the same backend tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_candidate_grouping tests.test_live_workbench_service tests.test_workbench_v2_api -v
```

Expected:

- FAIL on payload shape or grouping assertions

### Task 2: Implement backend candidate grouping primitives

**Files:**
- Create: `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`
- Modify: `backend/src/fin_ops_platform/services/live_workbench_service.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_query_service.py`
- Test: `tests/test_workbench_candidate_grouping.py`

- [ ] **Step 1: Write the next failing unit tests for grouping keys**

Add focused tests for:

- grouping by existing `case_id`
- grouping by temporary key `(direction, normalized counterparty, anchor amount, date bucket)`
- amount mismatch stays grouped as `candidate`, not `auto_closed`
- conflicting alternatives prevent high-confidence closure

- [ ] **Step 2: Run the grouping-key tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_candidate_grouping.WorkbenchCandidateGroupingTests -v
```

Expected:

- FAIL on missing grouping logic

- [ ] **Step 3: Implement minimal grouping primitives**

Implement:

- record normalization helpers
- temporary candidate key builder
- high-confidence closure predicates
- candidate group assembly with `group_id`, `group_type`, `match_confidence`, `reason`

- [ ] **Step 4: Re-run the grouping-key tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_candidate_grouping.WorkbenchCandidateGroupingTests -v
```

Expected:

- PASS

### Task 3: Upgrade `/api/workbench` to grouped payloads

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/services/live_workbench_service.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_query_service.py`
- Test: `tests/test_workbench_v2_api.py`

- [ ] **Step 1: Write failing API assertions for grouped response shape**

Add assertions for:

- `paired.groups`
- `open.groups`
- each group contains `oa_rows`, `bank_rows`, `invoice_rows`
- summary counts remain correct
- OA rows are still merged into the live workbench result

- [ ] **Step 2: Run the workbench API tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v
```

Expected:

- FAIL because `/api/workbench` still returns pane-row arrays

- [ ] **Step 3: Implement grouped `/api/workbench` serialization**

Implement:

- grouped workbench response builder
- stable group ordering
- row detail endpoint remains row-based
- action endpoints keep accepting row ids

- [ ] **Step 4: Re-run the workbench API tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v
```

Expected:

- PASS

### Task 4: Add frontend red tests for grouped-zone rendering

**Files:**
- Create: `web/src/test/CandidateGroupGrid.test.tsx`
- Modify: `web/src/test/WorkbenchSelection.test.tsx`
- Modify: `web/src/test/apiMock.ts`
- Reference: `web/src/pages/ReconciliationWorkbenchPage.tsx`

- [ ] **Step 1: Write failing UI tests for grouped layout**

Cover:

- each zone renders candidate groups instead of independent pane tables
- same group displays `OA | 银行流水 | 发票` in one horizontal row
- missing pane data renders an empty cell
- multiple records in one pane stack vertically
- row-level detail button still opens modal

- [ ] **Step 2: Run the failing frontend tests**

Run:

```bash
cd web
npm run test -- --run
```

Expected:

- FAIL because grouped components and grouped mock payloads do not exist

- [ ] **Step 3: Add minimal grouped mock payload scaffolding**

Update test mocks and route helpers so tests fail on behavior rather than missing fields or components.

- [ ] **Step 4: Re-run the frontend tests**

Run:

```bash
cd web
npm run test -- --run
```

Expected:

- FAIL on grouped rendering behavior

### Task 5: Implement grouped workbench types and API mapping

**Files:**
- Modify: `web/src/features/workbench/types.ts`
- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/test/apiMock.ts`
- Test: `web/src/test/CandidateGroupGrid.test.tsx`

- [ ] **Step 1: Write failing mapping tests or strengthen current UI tests**

Add assertions that:

- grouped payloads are mapped to typed `WorkbenchCandidateGroup`
- row records inside groups retain `caseId`, `detailFields`, `actionVariant`, `availableActions`
- summary counts still map correctly

- [ ] **Step 2: Run the mapping-aware frontend tests**

Run:

```bash
cd web
npm run test -- --run
```

Expected:

- FAIL because `fetchWorkbench()` still maps pane arrays

- [ ] **Step 3: Implement grouped frontend types and API mapper**

Implement:

- `WorkbenchCandidateGroup`
- grouped `WorkbenchData`
- API mappers from `paired.groups` / `open.groups`

- [ ] **Step 4: Re-run the mapping-aware frontend tests**

Run:

```bash
cd web
npm run test -- --run
```

Expected:

- PASS for mapping-related cases

### Task 6: Implement grouped-zone UI and record-card cells

**Files:**
- Create: `web/src/components/workbench/CandidateGroupGrid.tsx`
- Create: `web/src/components/workbench/CandidateGroupCell.tsx`
- Create: `web/src/components/workbench/WorkbenchRecordCard.tsx`
- Modify: `web/src/components/workbench/WorkbenchZone.tsx`
- Modify: `web/src/components/workbench/ResizableTriPane.tsx`
- Modify: `web/src/components/workbench/PaneTable.tsx`
- Modify: `web/src/app/styles.css`
- Test: `web/src/test/CandidateGroupGrid.test.tsx`

- [ ] **Step 1: Write the next failing interaction tests**

Add assertions for:

- per-zone expand / restore still works
- column hide / restore still works
- splitter resizing still works with grouped rows
- record cards remain clickable/selectable inside a grouped row

- [ ] **Step 2: Run the interaction tests**

Run:

```bash
cd web
npm run test -- --run
```

Expected:

- FAIL on layout and interaction behavior

- [ ] **Step 3: Implement grouped grid rendering**

Implement:

- zone body as a list of grouped rows
- each row contains three pane cells
- each cell stacks `0..N` `WorkbenchRecordCard` items
- blank cells preserve horizontal alignment
- resize mechanics remain controlled by the existing pane width hook

- [ ] **Step 4: Re-run the interaction tests**

Run:

```bash
cd web
npm run test -- --run
```

Expected:

- PASS

### Task 7: Reconnect page-level selection, actions, and detail modal to grouped rows

**Files:**
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Modify: `web/src/hooks/useWorkbenchSelection.ts`
- Modify: `web/src/components/workbench/DetailDrawer.tsx`
- Modify: `web/src/test/WorkbenchSelection.test.tsx`

- [ ] **Step 1: Write failing page-level tests**

Cover:

- selecting a record in a grouped row highlights related records by `caseId`
- confirm-link still posts grouped row ids for the current case
- detail modal still loads `/api/workbench/rows/{row_id}`
- expanded focus mode still hides global chrome as expected

- [ ] **Step 2: Run the page-level tests**

Run:

```bash
cd web
npm run test -- --run
```

Expected:

- FAIL because page logic still flattens `paired.oa / bank / invoice`

- [ ] **Step 3: Implement grouped page orchestration**

Implement:

- flatten-all-rows helper from grouped zones for selection/action lookup
- grouped confirm-link row collection
- grouped detail open/close flow

- [ ] **Step 4: Re-run the page-level tests**

Run:

```bash
cd web
npm run test -- --run
```

Expected:

- PASS

### Task 8: Run full regression and update docs

**Files:**
- Modify: `README.md`
- Modify: `web/README.md`
- Modify: `docs/dev/reconciliation-workbench-v2-backend.md`
- Modify: `docs/dev/reconciliation-workbench-v2-frontend.md`

- [ ] **Step 1: Update docs to reflect grouped workbench contract**

Document:

- high-confidence auto-close boundary
- candidate-group payload shape
- grouped workbench rendering
- row-level actions within grouped cells

- [ ] **Step 2: Run backend full regression**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

Expected:

- PASS

- [ ] **Step 3: Run frontend full regression**

Run:

```bash
cd web
npm run test -- --run
npm run build
```

Expected:

- PASS

- [ ] **Step 4: Commit**

```bash
git add backend/src/fin_ops_platform/services/workbench_candidate_grouping.py \
  backend/src/fin_ops_platform/services/live_workbench_service.py \
  backend/src/fin_ops_platform/services/workbench_query_service.py \
  backend/src/fin_ops_platform/app/server.py \
  tests/test_workbench_candidate_grouping.py \
  tests/test_live_workbench_service.py \
  tests/test_workbench_v2_api.py \
  web/src/features/workbench/types.ts \
  web/src/features/workbench/api.ts \
  web/src/pages/ReconciliationWorkbenchPage.tsx \
  web/src/components/workbench/CandidateGroupGrid.tsx \
  web/src/components/workbench/CandidateGroupCell.tsx \
  web/src/components/workbench/WorkbenchRecordCard.tsx \
  web/src/components/workbench/WorkbenchZone.tsx \
  web/src/components/workbench/ResizableTriPane.tsx \
  web/src/components/workbench/PaneTable.tsx \
  web/src/app/styles.css \
  web/src/test/CandidateGroupGrid.test.tsx \
  web/src/test/WorkbenchSelection.test.tsx \
  web/src/test/apiMock.ts \
  README.md web/README.md \
  docs/dev/reconciliation-workbench-v2-backend.md \
  docs/dev/reconciliation-workbench-v2-frontend.md \
  docs/superpowers/specs/2026-03-27-oa-bank-invoice-candidate-grouping-design.md \
  docs/superpowers/plans/2026-03-27-oa-bank-invoice-candidate-grouping.md
git commit -m "feat: add grouped OA-bank-invoice workbench"
```

# Workbench Bank Counts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复关联台银行流水事实计数，让银行明细流水数与关联台主 zone 真实银行流水数加 ignored 诊断数一致。

**Architecture:** 后端在 SQL read model 层统一标准化 group 事实计数和展示计数，summary/groups/detail 均消费同一契约。前端只渲染后端事实计数字段，免 OA 折叠继续展示摘要行，但不把摘要行算作真实银行流水。

**Tech Stack:** Python repository/read model + unittest；React TypeScript + Vitest；PostgreSQL SQL read model。

---

## File Structure

- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
  - 标准化 workbench group 的 `row_counts`、`display_row_counts`、`row_count`。
  - 修正 materialized summary、summary fallback 和 groups page endpoint 级 `row_counts`。
  - 输出 summary diagnostics。
- Modify: `tests/test_workbench_sql_runtime.py`
  - 覆盖免 OA 摘要行、collapsed 原始银行流水、pagination 前 endpoint row_counts、diagnostics。
- Modify: `tests/test_no_oa_bank_batch_workbench_integration.py`
  - 覆盖免 OA 批次折叠组 `row_counts.bank = collapsed_rows.bank`。
- Modify: `web/src/features/workbench/types.ts`
  - 增加 `displayRowCounts` 和 summary diagnostics 类型。
- Modify: `web/src/features/workbench/api.ts`
  - 映射 `display_row_counts`，保留 `collapsed_row_counts` 兼容。
  - 确保 initial page 使用 `zone_counts` / groups page `row_counts`。
- Modify: `web/src/features/workbench/groupDisplayModel.ts`
  - 计数组合优先使用 `rowCounts` 事实口径；展示计数仅用于解释折叠摘要。
- Modify: `web/src/components/workbench/CandidateGroupGrid.tsx`
  - 免 OA 折叠组显示“当前显示 1 条摘要 / 实际 N 条流水”。
- Modify: `web/src/test/WorkbenchApi.test.ts`
  - 覆盖 `display_row_counts` 映射和真实 row count。
- Modify: `web/src/test/CandidateGroupGrid.test.tsx`
  - 覆盖折叠组实际流水数量文案。
- Modify: `web/src/test/WorkbenchZone.test.tsx`
  - 覆盖区域/栏标题使用事实计数。

## Task 1: 后端 Group 事实计数 Helper

**Files:**
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Test: `tests/test_workbench_sql_runtime.py`

- [ ] **Step 1: Write failing tests**

Add tests showing:

```python
def test_repository_persists_no_oa_collapsed_group_fact_and_display_counts(self) -> None:
    # bank_rows contains one source_kind=no_oa_bank_batch_summary summary row
    # collapsed_rows.bank contains 3 real bank rows
    # persisted group payload row_counts.bank == 3
    # persisted group payload display_row_counts.bank == 1
    # persisted read_model.workbench_groups row_count == 3
```

Expected RED: persisted payload currently has no standardized `row_counts` / `display_row_counts`, and `row_count` is derived from identity length including the summary row.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.PostgresWorkbenchSqlRuntimeTests.test_repository_persists_no_oa_collapsed_group_fact_and_display_counts -v
```

Expected: FAIL on missing or wrong count fields.

- [ ] **Step 3: Implement minimal helper**

In `read_models.py`, add helpers near workbench count helpers:

```python
NO_OA_BANK_BATCH_SUMMARY_SOURCE_KIND = "no_oa_bank_batch_summary"

def _is_workbench_summary_display_row(row: dict[str, Any], pane: str) -> bool:
    return pane == "bank" and text(row.get("source_kind")) == NO_OA_BANK_BATCH_SUMMARY_SOURCE_KIND

def _workbench_group_fact_row_counts(group: dict[str, Any]) -> dict[str, int]:
    # Count normal non-summary rows plus collapsed rows, de-duped by (pane, row_id).
    # Missing/null/empty source_kind remains a real bank row.
```

Also add `_workbench_group_display_row_counts(group)` and `_with_workbench_group_counts(group)` so `_iter_workbench_groups`, all-scope aggregation, and summary compaction all use the same calculation.

- [ ] **Step 4: Run test to verify it passes**

Run the same unittest command.

- [ ] **Step 5: Commit**

```bash
git add backend/src/fin_ops_platform/services/postgres_repositories/read_models.py tests/test_workbench_sql_runtime.py
git commit -m "Fix workbench group fact row counts"
```

## Task 2: 后端 Summary 与 Groups Page API 计数

**Files:**
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Test: `tests/test_workbench_sql_runtime.py`

- [ ] **Step 1: Write failing tests**

Add tests proving:

```python
def test_repository_summary_fallback_counts_collapsed_bank_rows_not_summary_rows(self) -> None:
    # fallback summary SQL must not contain jsonb_array_length(payload->'bank_rows')
    # paired/open zone bank counts come from workbench_group_rows excluding no_oa summary rows

def test_repository_repairs_materialized_workbench_summary_counts_from_structured_rows(self) -> None:
    # stale persisted read_model.workbench_summary payload must be overlaid by structured group-row fact counts
    # deployment correctness must not depend on an immediate read-model rebuild

def test_repository_groups_page_row_counts_are_fact_counts_before_pagination(self) -> None:
    # page_size=1, matching groups contain 3 real bank rows across collapsed rows
    # endpoint row_counts.bank == 3 even though returned groups list has one page item
```

Expected RED: queries still use `jsonb_array_length(payload->'bank_rows')`.

- [ ] **Step 2: Run failing tests**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v
```

Expected: new tests fail.

- [ ] **Step 3: Implement SQL row-count queries**

Replace summary/groups page JSON length aggregation with `read_model.workbench_group_rows` based counts:

- Join `read_model.workbench_groups g` to `read_model.workbench_group_rows r`.
- Count distinct `r.row_id` by `r.pane`.
- Exclude only explicit summary display rows with null-safe SQL: `not (r.pane = 'bank' and coalesce(r.source_kind, '') = 'no_oa_bank_batch_summary')`. Bank rows with `source_kind is null`, missing in payload, or empty string remain real bank facts and must be counted.
- Overlay materialized `read_model.workbench_summary` counts from the same structured group-row aggregation so stale historical summary payloads cannot keep serving old bank counts.
- Keep `total` as matching group count before pagination.
- Keep page/page_size affecting only returned `groups`.

- [ ] **Step 4: Add summary diagnostics**

Summary payload should include:

```json
{
  "diagnostics": {
    "bank_detail_count": 431,
    "ignored_bank_count": 0,
    "bank_detail_reconciliation_status": "matched"
  }
}
```

When current test doubles do not expose runtime bank tables, use deterministic zero/default diagnostics in those tests rather than querying unavailable fake tables. Runtime DB validation remains a separate verification step.

The real PostgreSQL repository path must compute diagnostics from persisted facts, not placeholders:

- `bank_detail_count` from `app.bank_transactions where status <> 'deleted'` for the matching scope, or the repository's canonical bank detail fact source if that source is later centralized.
- `ignored_bank_count` from ignored bank facts in `read_model.workbench_rows` for the matching scope.
- Tests must cover `ignored_bank_count > 0` and assert `diagnostics.bank_detail_count = summary.bank_count + diagnostics.ignored_bank_count`.

- [ ] **Step 4.5: Add group detail contract test**

Add a repository/API test where one detail group has a no-OA summary row and multiple `collapsed_rows.bank` facts. Assert:

- `GET /api/workbench/groups/detail` returns the same `row_counts` / `display_row_counts` contract as the groups page.
- `collapsed_rows.bank` contains the real bank rows.
- `row_counts.bank` does not include the summary display row.

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_workbench_integration -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/fin_ops_platform/services/postgres_repositories/read_models.py tests/test_workbench_sql_runtime.py tests/test_no_oa_bank_batch_workbench_integration.py
git commit -m "Fix workbench summary and page bank counts"
```

## Task 3: 前端 API Mapping 与折叠展示

**Files:**
- Modify: `web/src/features/workbench/types.ts`
- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/features/workbench/groupDisplayModel.ts`
- Modify: `web/src/components/workbench/CandidateGroupGrid.tsx`
- Test: `web/src/test/WorkbenchApi.test.ts`
- Test: `web/src/test/CandidateGroupGrid.test.tsx`
- Test: `web/src/test/WorkbenchZone.test.tsx`

- [ ] **Step 1: Write failing tests**

Add or update tests proving:

```typescript
expect(result.pages.paired.rowCounts.bank).toBe(237);
expect(group.rowCounts?.bank).toBe(12);
expect(group.displayRowCounts?.bank).toBe(1);
expect(screen.getByText(/当前显示 1 条摘要/)).toBeInTheDocument();
expect(screen.getByText(/实际 12 条流水/)).toBeInTheDocument();
```

Expected RED: `display_row_counts` is not mapped and collapsed explanatory text is absent.

- [ ] **Step 2: Run failing tests**

```bash
cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/CandidateGroupGrid.test.tsx src/test/WorkbenchZone.test.tsx
```

- [ ] **Step 3: Implement mapping and UI**

- Add `displayRowCounts?: WorkbenchPaneRowCounts` to `WorkbenchCandidateGroup`.
- Add optional summary diagnostics type to `WorkbenchSummary` or `WorkbenchData` only if UI or tests consume it.
- Map backend `display_row_counts`.
- Keep `rowCounts` as fact count.
- In `CandidateGroupGrid`, for collapsed summary groups, render compact helper text based on `displayRowCounts.bank ?? group.rows.bank.length` and `rowCounts.bank ?? collapsedRowCounts.bank`.

- [ ] **Step 4: Run tests**

```bash
cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/CandidateGroupGrid.test.tsx src/test/WorkbenchZone.test.tsx
```

- [ ] **Step 5: Commit**

```bash
git add web/src/features/workbench/types.ts web/src/features/workbench/api.ts web/src/features/workbench/groupDisplayModel.ts web/src/components/workbench/CandidateGroupGrid.tsx web/src/test/WorkbenchApi.test.ts web/src/test/CandidateGroupGrid.test.tsx web/src/test/WorkbenchZone.test.tsx
git commit -m "Use workbench fact counts in frontend"
```

## Task 4: Runtime Verification and Final Checks

**Files:**
- Modify only if a small verification helper is necessary; prefer one-off SQL in the terminal.

- [ ] **Step 1: Run focused test suite**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_workbench_integration -v
cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/CandidateGroupGrid.test.tsx src/test/WorkbenchZone.test.tsx
```

- [ ] **Step 2: Run build/check**

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
cd web && npm run build
```

- [ ] **Step 3: Runtime SQL consistency check**

Using `.runtime/fin_ops_platform/local-postgres.env`, verify:

```text
bank_detail_count = open_bank_count + paired_bank_count + ignored_bank_count
missing_bank_row_ids = 0
extra_bank_row_ids = 0
```

For current data, expected:

```text
431 = 194 + 237 + 0
```

Also verify the two API-level equations after read model rebuild:

```text
summary.bank_count = summary.zone_counts.open.bank + summary.zone_counts.paired.bank
diagnostics.bank_detail_count = summary.bank_count + diagnostics.ignored_bank_count
```

- [ ] **Step 4: Final commit if needed**

```bash
git status --short
git log --oneline -5
```

If all implementation commits are already present, do not squash unless requested.

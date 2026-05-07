# OA Multi Project Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 关联台整单 OA 涉及多个真实项目时，OA 栏项目列只显示 `多个项目`，但真实项目集合仍保留给详情、搜索、匹配和统计使用。

**Architecture:** 后端在现有整单 OA 聚合链路中输出真实项目集合和显示项目名，避免把 `多个项目` 写入真实业务字段。前端只在表格项目列消费 `project_name_display`，搜索和详情继续使用真实项目明细。

**Tech Stack:** Python services/tests, TypeScript React workbench mapper, Vitest, pytest.

---

### Task 1: 后端 OA 聚合契约

**Files:**
- Modify: `backend/src/fin_ops_platform/services/oa_adapter.py`
- Modify: `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_query_service.py`
- Test: `tests/test_mongo_oa_adapter.py`
- Test: `tests/test_workbench_query_service.py`
- Test: `tests/test_workbench_v2_api.py`
- Docs: `docs/dev/reconciliation-workbench-v2-data-contracts.md`

- [ ] Add `project_names: list[str]` and `project_name_display: str | None` to `OAApplicationRecord` with backward-compatible defaults.
- [ ] In `MongoOAAdapter._build_expense_claim_records()`, collect distinct non-empty real project names from expense items.
- [ ] Keep `project_name` as the real joined project summary, never as `多个项目`.
- [ ] Set `project_name_display` to the single real project name when there is one, `多个项目` when there are multiple, otherwise existing fallback.
- [ ] Output `project_names` and `project_name_display` in `WorkbenchQueryService._build_oa_row()`.
- [ ] Use display value in `_summary_fields["项目名称"]`, while `_detail_fields["项目名称汇总"]` and `project_names` retain real names.
- [ ] Keep compatibility for records without new fields.
- [ ] Add/adjust tests for multi-project, single-project, dedupe, API payload, and detail fields.

### Task 2: 前端显示映射

**Files:**
- Modify: `web/src/features/workbench/api.ts`
- Test: `web/src/test/WorkbenchApi.test.ts`

- [ ] Extend `ApiWorkbenchRow` with optional `project_name_display` and `project_names`.
- [ ] In `mapTableValues()`, set OA `projectName` from `project_name_display ?? project_name`.
- [ ] Ensure detail-derived search fields still include real project names from `detail_fields`.
- [ ] Add a Vitest case where API returns `project_name="云南溯源科技；玉烟维护项目"` and `project_name_display="多个项目"`; table displays `多个项目` while searching a real project still matches the row.

### Task 3: 回归验证

**Files:**
- All files changed by Tasks 1-2.

- [ ] Run backend focused tests:

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_mongo_oa_adapter.py tests/test_workbench_query_service.py tests/test_workbench_v2_api.py -q
```

- [ ] Run frontend focused tests:

```bash
cd web && npx vitest run src/test/WorkbenchApi.test.ts src/test/DetailDrawer.test.tsx
```

- [ ] Run whitespace check:

```bash
git diff --check
```

- [ ] Report changed files, test results, and any residual risk.

---
quick_id: 260728-g9q
status: passed
verified_at: 2026-07-28
---

# Quick Task 260728-g9q Verification

## Must Haves

- OA row 的所有显式来源身份确定性归一到唯一 canonical OA ID。
- 同一 alias 指向多个 OA 时 fail closed。
- 历史显式来源引用与当前窗口使用同一 alias 合同。
- 附件发票通过 exact source binding 进入父 OA 正式关系。
- 付款项只按显式 `row_index` 映射 canonical expense item ID。
- canonical 发票事实保留原始 `source_expense_item_id`。
- relation 扩展与撤回保持 OA/附件不可拆散。

## Test Coverage

1. Business core unit：alias 生成、canonical item ID、冲突和金额无关确定性已覆盖。
2. Service layer：formal relation repository、matching plan、command、withdraw、alignment、grouping 已覆盖。
3. API contract：不适用；本次不改变 HTTP path、参数或响应根结构。
4. Read model / worker：matching rule version、Workbench grouping 与 SQL projection 相邻回归已覆盖；未新增 worker/read model。
5. Frontend interaction：不适用；前端交互和组件合同未改变。
6. End-to-end integration：matching orchestrator -> formal relation -> Workbench query/SQL projection 的后端集成切片已覆盖。
7. Existing regression：旧纯 immutable relation、relation extension/withdraw、query 和 SQL projection 已覆盖。

## Commands

```bash
PYTHONPATH=backend/src python3 -m pytest -q \
  tests/test_workbench_formal_relation_repository.py \
  tests/test_workbench_free_matching_engine.py \
  tests/test_workbench_relation_command_service.py \
  tests/test_workbench_pair_relation_service.py \
  tests/test_workbench_relation_alignment_service.py \
  tests/test_workbench_relation_grouping.py

PYTHONPATH=backend/src python3 -m pytest -q \
  tests/test_workbench_matching_orchestrator.py \
  tests/test_workbench_oa_attachment_context_row_index.py \
  tests/test_workbench_query_service.py \
  tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_invoice_row_preserves_canonical_oa_attachment_source_metadata \
  tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_invoice_row_prefers_oa_attachment_source_link_with_context

bash scripts/verify.sh lint
bash scripts/verify.sh docs
git diff --check
```

## Remaining Production Gate

正式 release 激活后等待 matching/Workbench scope 收敛，并只读验证目标 OA、5 条付款项、附件发票同组、freshness、Audit 和请求耗时。

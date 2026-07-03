# 2026-07-03 - Confirm Link OA Row Detail KeyError

## Symptom

确认关联选中 `OA + 银行流水 + 进项发票` 后，提交失败并把 `oa-exp-*` row id 作为错误消息透给前端。

## Hypothesis

确认写入前的 row 解析边界没有完整消费 Workbench read model。`row_ids` 是 Workbench row id，但旧 row-detail 路径仍优先读取 live detail；同时 cached resolver 只索引 `paired/open.groups[*]`，遗漏平铺 `paired/open.{oa,bank,invoice}` 行。

## Evidence

- 新增回归 `test_row_detail_resolves_flat_cached_read_model_before_live_detail` 在当前实现下失败：row-detail 先调用 live detail。
- 新增回归 `test_confirm_link_resolves_selected_flat_read_model_rows_without_live_detail` 在当前实现下失败：confirm-link 金额校验解析 `oa-exp-*` 时触发 live detail。

## Fix

- `WorkbenchRowDetailApiRoutes.get_payload(...)` 改为 cache/query-facade first；legacy/live fallback 只保留在非 SQL read model runtime 兼容尾部。
- `Application._grouped_rows_by_id(...)` 统一索引平铺行和 group 成员行；group 成员保留覆盖同 id 平铺行的优先级。

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_resolves_flat_cached_read_model_before_live_detail tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_resolves_selected_flat_read_model_rows_without_live_detail -v`


---
status: resolved
trigger: "在关联台选中两组已闭环的外部往来（每组两个流水，一收一支）和一个 OA，预览页点击确认关联后弹出：关联台刷新失败：workbench_all_scope_parent_inconsistent: generation_metadata_actual_mismatch: 2026-02/workbench:2026-02:7141d3e6fa1947c99c47cde8a16b89d2: active_relation_open_membership count=4；点击 OK 后关联关系实际已建立。"
created: "2026-06-18"
updated: "2026-06-18"
---

# Debug Session: workbench-parent-inconsistent

## Symptoms

- Expected behavior: 关联台确认关联成功后，刷新关联台不报错；已闭环外部往来流水和 OA 的 active 关系保持一致并能正常展示。
- Actual behavior: 预览页确认关联后弹出 `关联台刷新失败`，但关闭弹窗后关联关系已建立。
- Error messages: `workbench_all_scope_parent_inconsistent: generation_metadata_actual_mismatch: 2026-02/workbench:2026-02:7141d3e6fa1947c99c47cde8a16b89d2: active_relation_open_membership count=4`
- Timeline: 2026-06-18 用户截图反馈。
- Reproduction: 关联台选中两组已闭环外部往来（每组两个银行流水，一收一支）和一个 OA，进入确认关联预览页后点击确认关联。

## Current Focus

- hypothesis: 已确认。确认关联写入成功后，`workbench:all` aggregate-only refresh 可能抢在 parent month shard 刷新完成前运行，用旧 active month generation 对新 canonical relation 做 consistency 校验。
- test: 已补第二轮 regression：parent `workbench` scope active 或 failed/stale 时，all aggregate handler 必须抛 `workbench_read_model_not_fresh` 并 defer；刷新状态/API/App Health 在同一 scope failed 后重新 processing 时必须显示 refreshing，不暴露旧 last_error。
- expecting: 关联写入成功后不再因旧 failed dirty scope 或 failed parent scope 显示 `workbench_all_scope_parent_inconsistent`；App Health 不再把正在重试的 `cost_statistics` deadlock 显示为当前失败。
- next_action: 发布后如果生产仍残留旧 failed dirty scope，可按 runtime worker governance requeue；本地回归已覆盖本次链路。

## Evidence

- timestamp: "2026-06-18"
  observation: "用户截图中确认关联后关联关系已经建立，说明错误发生在写入后的关联台刷新/读模型生成阶段，不是 confirm write 本身完全失败。"
- timestamp: "2026-06-18"
  observation: "错误中包含 `generation_metadata_actual_mismatch`、`workbench_all_scope_parent_inconsistent`、`active_relation_open_membership count=4`，指向 workbench read model generation metadata 的 parent scope 校验。"
- timestamp: "2026-06-18"
  observation: "`workbench.read_model.refresh` 的 all aggregate event 携带 `parent_scope_keys`，但 handler 只跳过 source version current check，没有检查这些 parent scope 的 dirty 状态。"
- timestamp: "2026-06-18"
  observation: "新增 regression 在 parent `2026-02` 仍 active 时先失败（aggregate builder 被调用），修复后返回 `workbench_read_model_not_fresh` defer。"
- timestamp: "2026-06-18"
  observation: "全量 Workbench v2 API 还暴露旧测试未按当前 mismatch note 合同提交，以及无历史撤回路径在 scope 反推失败时误报；已一并收敛。"
- timestamp: "2026-06-18"
  observation: "用户再次复现：相同操作仍显示 `workbench_all_scope_parent_inconsistent`，关联关系已建立；App Health 同时显示 `cost_statistics 2026-03 deadlock detected`。"
- timestamp: "2026-06-18"
  observation: "第一轮测试未覆盖 failed dirty scope 被重新入队后的组合状态。`_normalize_workbench_refresh_status_payload` 先看 failed，再看 pending/processing，导致历史 failed 覆盖当前刷新状态。"
- timestamp: "2026-06-18"
  observation: "第一轮 Workbench all aggregate 只检查 parent active；若 parent scope 已 failed/stale，all aggregate 仍继续聚合旧 parent active generation，可能再次写出 parent inconsistent failed generation。"
- timestamp: "2026-06-18"
  observation: "Runtime monitoring 对同一 `cost_statistics` scope 的 failed + processing 也会以 failed 作为 current status，导致 App Health 显示旧 deadlock 为当前失败。"

## Eliminated

- hypothesis: "确认关联写入事务整体回滚"
  reason: "用户关闭错误弹窗后能看到关联关系已经建立，说明至少业务关系写入已提交。"

## Resolution

- root_cause: "`parent_scope_keys` 只作为 all aggregate payload 元数据传递，未被当作完整依赖边界；因此 relation canonical state 已提交、month shard 仍旧或已 failed/stale 时，all aggregate 会把暂态 parent/member mismatch 写成 failed generation。第一轮测试只覆盖 parent pending/processing，漏掉 parent failed/stale 以及同 scope old failed + current processing 的状态展示。"
- fix: "`WorkbenchReadModelRefreshService` 在处理携带 `parent_scope_keys` 的 `workbench:all` aggregate-only event 前，查询 durable dirty scope 是否仍 active 或 not fresh；active/failed/stale 都抛 `workbench_read_model_not_fresh`，交给 runtime worker 短延迟 defer 并补投 parent refresh。`_normalize_workbench_refresh_status_payload` 对 requeued failed scope 优先显示 refreshing 并隐藏旧 last_error。`RuntimeMonitoringRepository` 合并同一 scope 的 failed + processing 为 refreshing，避免 App Health 把正在重试的 deadlock 显示为当前失败。另补 `WorkbenchWriteFacade` 撤回路径的 scope 推导顺序，避免无历史 active relation 写入成功后因 refresh scope 反推失败误报。"
- verification: "`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -q`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_runtime_worker tests.test_app_status_overview_service -q`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -q`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_repository tests.test_turnover_workbench_integration tests.test_workbench_turnover_grouping tests.test_workbench_auth_context_idempotency -q`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_cost_statistics_api -q`；`npm --prefix web test -- --run src/test/WorkbenchSelection.test.tsx src/test/OperationBarrierApi.test.ts src/test/GlobalOperationOverlayContext.test.tsx`；`bash scripts/verify.sh docs`；`git diff --check`。"
- files_changed: "`backend/src/fin_ops_platform/services/workbench_read_model_refresh.py`、`backend/src/fin_ops_platform/services/runtime_queue.py`、`backend/src/fin_ops_platform/services/runtime_monitoring.py`、`backend/src/fin_ops_platform/app/server.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_runtime_queue.py`、`tests/test_app_status_overview_service.py`、`web/src/test/apiMock.ts`、`web/src/test/WorkbenchSelection.test.tsx`、文档。"

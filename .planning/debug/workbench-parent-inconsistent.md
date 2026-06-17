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
- test: 已补 regression：parent `workbench` scope 仍 active 时，all aggregate handler 必须抛 `workbench_read_model_not_fresh` 并 defer，不调用 aggregate builder、不完成 dirty scope。
- expecting: 确认关联链路不再在刷新阶段误报 parent inconsistent；关联关系写入、read model 刷新和 UI selection/barrier 维持一致。
- next_action: 发布后如生产已有旧 failed `workbench:all` outbox/generation，按 runtime worker governance requeue 或归档已覆盖历史 failure。

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

## Eliminated

- hypothesis: "确认关联写入事务整体回滚"
  reason: "用户关闭错误弹窗后能看到关联关系已经建立，说明至少业务关系写入已提交。"

## Resolution

- root_cause: "`parent_scope_keys` 只作为 all aggregate payload 元数据传递，未被当作依赖边界；因此 relation canonical state 已提交、month shard 仍旧时，all aggregate 会把暂态 parent/member mismatch 写成 failed generation。"
- fix: "`WorkbenchReadModelRefreshService` 在处理携带 `parent_scope_keys` 的 `workbench:all` aggregate-only event 前，查询 durable dirty scope 是否仍 active；active 时抛 `workbench_read_model_not_fresh`，交给 runtime worker 短延迟 defer。另补 `WorkbenchWriteFacade` 撤回路径的 scope 推导顺序，避免无历史 active relation 写入成功后因 refresh scope 反推失败误报。"
- verification: "`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -q`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -q`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_repository tests.test_runtime_worker tests.test_turnover_workbench_integration tests.test_workbench_turnover_grouping tests.test_workbench_auth_context_idempotency -q`；`npm --prefix web test -- --run src/test/WorkbenchSelection.test.tsx src/test/OperationBarrierApi.test.ts src/test/GlobalOperationOverlayContext.test.tsx`；`bash scripts/verify.sh docs`；`git diff --check`。"
- files_changed: "`backend/src/fin_ops_platform/services/workbench_read_model_refresh.py`、`backend/src/fin_ops_platform/services/workbench_write_facade.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_v2_api.py`、`docs/modules/reconciliation-workbench/*`、`docs/modules/read-models/*`。"

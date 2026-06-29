# Canonical Facts Wave 5 - Legacy read model reconcile tool removal

日期：2026-06-29

## 目标

删除三个旧 read model 迁移对账 CLI，避免工具目录继续保留通过 `Application` 私有 legacy builder/API 计算 payload 再和 SQL read model 对比的旧 oracle 链路。

本 slice 不接管 07 read model closure，也不修改 07-owned read model runtime 文件；只删除未注册的 legacy migration/reconcile 工具，并更新长期文档中对应命令。

## 删除

- `backend/src/fin_ops_platform/tools/reconcile_workbench_read_model.py`
- `backend/src/fin_ops_platform/tools/reconcile_cost_statistics_read_model.py`
- `backend/src/fin_ops_platform/tools/reconcile_tax_offset_read_model.py`

这些工具分别调用：

- `Application._build_raw_workbench_payload(...)` / `_apply_candidate_matches_to_payload(...)`
- `Application._cost_statistics_service.get_explorer(...)`
- `Application._tax_api_routes.get_tax_offset(...)`

它们只作为旧迁移校验入口存在，不能作为长期 production/read model/canonical facts 验证方式。

## 文档更新

- `docs/architecture/persistence-and-read-models.md` 删除三个 CLI 命令，改为说明一致性验证应走 worker refresh、fresh gate、模块测试、generation consistency 或生产只读 SLO evidence。
- 同一文档同步修正 GridFS 段落：旧 verify/rollback 工具已删除，剩余 worker path 是 blocker，不算 final closure。

## Guard

- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_legacy_read_model_reconcile_tools_are_removed`

Guard 覆盖：

- 三个 deleted tool 文件不能回归。
- tools 目录不能重新引用这些 module 名。
- tools 目录不能重新调用旧 private read model oracle：`_build_raw_workbench_payload`、`_apply_candidate_matches_to_payload`、`_cost_statistics_service.get_explorer`、`_tax_api_routes.get_tax_offset`。

## 验证计划

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_read_model_reconcile_tools_are_removed
rg -n "reconcile_(workbench|cost_statistics|tax_offset)_read_model|_build_raw_workbench_payload|_apply_candidate_matches_to_payload|_cost_statistics_service\\.get_explorer|_tax_api_routes\\.get_tax_offset" backend/src/fin_ops_platform/tools -g '*.py'
bash scripts/verify.sh docs
git diff --check
```

## 剩余风险

- `docs/modules/read-models/` 和 07-owned read model runtime files 未在本 slice 修改。
- Workbench/cost/tax read model 最终 runtime closure 仍由 07 controller 负责；本 slice 只删除旧对照工具，避免旧 oracle 作为事实源验证路径长期残留。

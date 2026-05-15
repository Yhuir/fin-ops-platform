# Prompt 43：关联台 Read Model 前端性能收口与 QA

目标：在 read model 后端落地后，收口前端局部更新、静默刷新和性能回归，确保体感明显快于现有实现。

前提：

- 阅读：
  - `docs/superpowers/specs/2026-04-08-workbench-materialized-read-model-design.md`
  - `docs/superpowers/plans/2026-04-08-workbench-materialized-read-model.md`
  - 已完成 `42-workbench-read-model-actions-and-refresh.md`

要求：

- 动作成功后立即局部更新 UI
- 后台静默刷新继续保留
- 避免旧的整页 reload 阻塞 `处理中`
- 补齐前后端回归测试

建议文件：

- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/features/workbench/api.ts`
- `web/src/test/WorkbenchSelection.test.tsx`
- `tests/test_workbench_v2_api.py`

验证：

- 跑后端相关测试
- 跑前端全量 tests
- 跑前端 build

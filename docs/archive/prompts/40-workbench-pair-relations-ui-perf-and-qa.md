# Prompt 40：关联台动作局部更新、性能收口与 QA

目标：在 pair relations 新模型接入后，把关联台前端动作体验收口到“后端成功后立即局部更新 UI，后台静默刷新兜底”，并完成性能与回归验证。

前提：

- Prompt 38、39 已完成
- 阅读：
  - `docs/superpowers/specs/2026-04-08-workbench-pair-relations-design.md`
  - `docs/superpowers/plans/2026-04-08-workbench-pair-relations.md`

要求：

- 保持现有前端局部更新策略，但适配新的动作返回和 pair relation 语义
- 确认 `处理中` 不再等待整页 reload
- 验证以下动作的体感改善：
  - 确认关联
  - 取消配对
- 保持以下能力不回归：
  - 已忽略
  - 已处理异常
  - 搜索跳转
  - 内部往来款 / 工资自动匹配展示

建议文件：

- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/features/workbench/api.ts`
- `web/src/test/WorkbenchSelection.test.tsx`
- `web/src/test/WorkbenchApi.test.ts`

交付要求：

- 动作成功后立即局部更新
- 后台静默刷新仍保留
- 回归测试覆盖新的 pair relation 路径

验证：

- 跑前端测试
- 跑前端 build

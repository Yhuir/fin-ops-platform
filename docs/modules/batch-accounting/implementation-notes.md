# 批量账务 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 批量账务不拥有独立 read model；列表和 mutation 前置判断依赖 `workbench_relation` read model freshness。
- `GET /api/batch-accounting` 必须保持只读，不能为了修复历史关系在 GET 路径写入。
- `read_model_status !== "fresh"` 时前端必须显示 warning 并禁用提交/撤回；不能把空关系当作真实未提交。
- 提交/撤回成功后的前端 `workbenchRelationUpdated` 只是刷新提示，不替代后端 dirty scope、worker 和 readiness。
- 历史 case id collision 修复保留在 service 显式路径和 mutation/repair 语义中，不能重新散落到列表读取。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-11 - relation read model missing/stale 闭环

- 目标：修复批量账务页面出现 `关联台关系读模型 missing/read_model_missing` 时只能提示刷新、但列表读取和 mutation fresh gate 没有形成完整闭环的问题。
- 影响范围：`BatchAccountingService` relation facade 调用、`GET /api/batch-accounting` freshness payload、submit/withdraw 错误合同、`BatchAccountingPage` non-fresh warning 和 feedback。
- 关键决策：GET 列表保持只读，但所有 relation distribution 读取都通过现有 `WorkbenchRelationReadFacade` 的 `require_fresh` 边界入队刷新；submit/withdraw 在后端再次要求 relation read model fresh，非 fresh 返回 `batch_accounting_read_model_not_fresh`；前端只展示后端 status/reason/scope，不把 domain event 当事实源。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md` 和 `docs/dev/api-contracts.md`。
- 测试覆盖：新增/更新后端 API/service 测试覆盖 missing/stale 入队、submit/withdraw fresh gate；新增前端交互测试覆盖刷新未入队提示和 mutation non-fresh reason/scope feedback。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api tests.test_workbench_relation_read_facade -v`
  - `cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx -t "relation read model refresh is not enqueued|mutation is rejected as non-fresh"`
- 未测风险：真实 PostgreSQL/RabbitMQ/systemd worker drain 和生产历史 dirty scope 收敛仍需 staging 或发布前 smoke；单元测试验证的是 facade/gateway 调用合同和页面行为。
- 后续事项：最终合入前继续运行模块全量后端、前端和 docs verify。

## 2026-06-11 - 首轮测试闭环文档化

- 目标：用 CodeGraph 审计批量账务页面、API、service、relation read model、worker/App Status 和测试入口，补齐模块文档闭环。
- 影响范围：`BatchAccountingPage`、`batchAccounting/api.ts`、`BatchAccountingService`、`WorkbenchRelationReadFacade`、`WorkbenchRelationSqlProjectionBuilder`、`workbench-relation` worker、App Status domain/job 映射、domain event。
- 关键决策：批量账务 mutation 必须依赖 fresh relation read model；GET 保持只读；前端事件不作为事实源；历史 collision repair 通过显式 service 回归保护。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`，并在全局测试闭环依赖地图中补充 batch-accounting 细化。
- 测试覆盖：后端 `tests/test_batch_accounting_api.py` 覆盖业务/API/service 回归；relation facade/projection/registry/App Status/lifecycle tests 覆盖 read model 和 worker；前端 `BatchAccountingPage.test.tsx` 覆盖页面交互和 stale 禁用。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api tests.test_workbench_relation_read_facade tests.test_workbench_relation_sql_projection tests.test_runtime_worker_registry tests.test_app_status_overview_service tests.test_derived_data_lifecycle_service -v`
  - `cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx src/test/domainEvents.test.ts src/test/useActiveFinanceDomainEvent.test.tsx`
  - `bash scripts/verify.sh docs`
- 未测风险：真实生产 PostgreSQL 历史批量账务关系、真实 RabbitMQ/Redis/systemd `workbench-relation` worker drain、大数据浏览器性能和下游页面最终展示仍需 staging/发布前 smoke。
- 后续事项：后续改动若触及 relation freshness、DTO shape、提交/撤回规则或 Workbench relation fan-out，必须先按 `tests.md` 选择窄范围回归，再升级到跨模块验证。

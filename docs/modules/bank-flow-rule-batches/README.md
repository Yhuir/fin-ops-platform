# 流水规则批量处理 模块维护入口

- Module key: `bank-flow-rule-batches`
- 类型: 页面模块
- Route: `/bank-flow-rule-batches`
- Page key: `bank-flow-rule-batches`
- 状态: close。当前生产入口、API、全局 Bank Transaction Paired Policy 规则抽屉、提交、关联台判定、独立 application service、独立 read model key、独立 worker event、独立 persistence IO、独立 PostgreSQL 批次/read model 表、独立 tag-rule settings family、前端 feature I/O/view model/components 和 Browser E2E 已接入；本轮已收口 bank-flow HTTP 错误码、Workbench 折叠摘要 `source_kind`、display tags、关联台撤回文案和 read model display-only 判定，旧 no-OA 残留只保留在 `no-oa-bank-batches` legacy 边界内。

## 修改前必读

- `docs/architecture/module-boundaries/README.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/architecture/module-boundaries/canonical-facts.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/modules/bank-details/boundary-io.md`
- `docs/modules/workbench-relations/boundary-io.md`
- `docs/modules/reconciliation-workbench/boundary-io.md`
- `docs/modules/no-oa-bank-batches/boundary-io.md`
- `docs/dev/api-contracts.md`

## 当前代码入口

当前代码使用 bank-flow 独立 HTTP route、application boundary、read model key、refresh producer、worker event、批次/read model 表和 tag-rule settings key 承载新业务入口；新页面和生产 API 不接收或返回 `selected_tag_codes` 作为规则事实源。

- Frontend page: `web/src/pages/BankFlowRuleBatchPage.tsx`，通过 `/bank-flow-rule-batches` route 作为流水规则批量处理页。
- Frontend feature: `web/src/features/bankFlowRuleBatches/api.ts`（HTTP/DTO mapping）、`types.ts`（public DTO/domain types）、`policy.ts`（状态/权限策略）、`viewModel.ts`（格式化、规则 grid view model、operation barrier target helpers）、`components.tsx`（分页、状态标签、label rail）。API 指向 `/api/bank-flow-rule-batches`。
- Backend route: `backend/src/fin_ops_platform/app/routes_bank_flow_rule_batches.py`，只承载 `/api/bank-flow-rule-batches/*`。
- Backend service: `backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py`，新提交写 `relation_mode=bank_flow_rule_batch`；共享批次计算内核在中性 `bank_batch_application_service.py` / `bank_batch_service.py`，bank-flow 不再继承 no-OA application service；HTTP 输出边界把共享 core 仍可能抛出的 legacy `no_oa_bank_batch_*` 错误码翻译为 `bank_flow_rule_batch_*`。
- Backend read model: `backend/src/fin_ops_platform/services/bank_flow_rule_batch_read_model_repository.py`、`bank_flow_rule_batch_read_model_refresh.py`、`bank_flow_rule_batch_read_model_refresh_producer.py`。
- Rule persistence: `app_settings.bank_flow_rule_batch_tag_rules.requirements_by_tag_code`；新 API 和服务边界只读写 `rules`，拒绝 `selected_tag_codes`，重复 `tag_code` fail fast。`0083_bank_flow_rule_batch_tag_rules.sql` 只负责一次性从历史 no-OA settings key 复制缺失值。
- Browser E2E: `web/e2e/bank-flow-rule-batches-flow.spec.ts`。

## 当前目标边界

流水规则批量处理是全局 Bank Transaction Paired Policy 的管理入口：它处理所有可批量提交的银行流水，不再只处理免 OA 候选。页面右侧抽屉以紧凑 xlsx/grid 方式维护每个银行明细标签是否需要 OA、发票才能进入关联台已配对区。

核心规则：

- 左侧 `收支类型 / 流水主标签 / 流水子标签` 来自银行明细当前 active 标签事实，只读展示，不能在本模块新增、编辑或删除。
- 右侧只保留 `OA`、`发票` 两列勾选。勾选表示该标签流水进入关联台已配对区前必须具备对应 row type；空表示不需要该项即可闭环。
- 新增或未配置的银行标签默认勾选 `OA` 和 `发票`，避免新标签自动进入无需 OA/发票闭环。
- 旧 `selected_tag_codes` 不迁移为新事实源；实现时应移除或只作为只读 legacy 输入清理，所有流水重新按新规则计算。
- 页面提交的是银行流水批量关系事实。所有含银行流水的关联台 group 是否进入已配对区，由银行流水 row 上物化的 Bank Transaction Paired Policy metadata 中的 `requires_oa` / `requires_invoice` 与实际 row type 组合决定；缺失 metadata 默认等价于需要 OA 和发票。
- 从本页面提交且银行流水超过 3 条时，关联台以折叠形式展示；1 到 3 条可展开展示。

## 不属于本模块事实源

- 银行明细标签定义、自动匹配规则和分类确认归 `bank-details`。
- Workbench relation canonical fact 归 `workbench-relations`。
- 关联台 paired/open 展示归 `reconciliation-workbench` active generation；bank-flow 折叠摘要必须输出 `source_kind=bank_flow_rule_batch_summary`、`invoice_relation.code=bank_flow_rule_batch` 和 `流水规则` display tag，不得复用 `no_oa_bank_batch_summary` 或 `免OA` 标签。
- 旧 no-OA 批次历史事实仍归 `no-oa-bank-batches` 管理；本模块不再提供旧 no-OA 历史重算页面入口或 API。

## 维护触发器

发生以下变化时必须更新本目录和相关上游/下游模块文档：

- 页面名称、路由、导航、抽屉 grid、筛选、分页、提交、撤回或权限变化。
- 标签规则 DTO、默认值、乐观锁、审计、错误码或保存语义变化。
- 批量提交 relation mode、metadata、折叠展示或 paired/open 判定变化。
- 旧 no-OA 迁移/运维工具若未来重新引入，必须作为独立运维模块建模，不能挂回本页面链路。
- read model scope、worker、operation barrier、dirty scope 或 API freshness 变化。
- Playwright E2E 业务验收范围变化。

## 本目录文件

- `boundary-io.md`：模块边界、I/O、持久化、文件范围、依赖方向和旧代码删除条件。
- `state-machine.md`：标签规则、批量提交、关联台展示和 reset 状态机。
- `tests.md`：七类测试适用性、计划测试入口和验证命令。
- `e2e-spec.md`：Spec-first Playwright E2E 业务验收合同。
- `e2e-coverage.md`：E2E spec 到当前自动化覆盖的映射和缺口。
- `implementation-notes.md`：提炼后的决策、验收、风险和后续事项。

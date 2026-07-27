# 流水规则批量处理 模块维护入口

- Module key: `bank-flow-rule-batches`
- 类型: 页面模块
- Route: `/bank-flow-rule-batches`
- Page key: `bank-flow-rule-batches`
- 状态: implementation-complete / merge-validation-pending。生产页面、API、Bank Transaction Paired Policy、提交/撤回/reset 和关联台合同已接入；列表、summary、分页和详情通过页面专属 canonical query repository 在 PostgreSQL `REPEATABLE READ / READ ONLY` snapshot 中直接读取批次/事件、银行/标签规则和 active pair relations。页面不再读取 `read_model.bank_flow_rule_batch_rows`，不返回 freshness/status/version，不 enqueue 或 polling；写命令成功后只执行一次当前列表 GET。旧 no-OA 仍是独立 legacy 模块，不进入本页面运行链；共享 worker/registry 清理、合并后生产验证和 BRB-E2E-003 fixture 修复由主控完成。

## 修改前必读

- `docs/architecture/module-boundaries/README.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/architecture/module-boundaries/canonical-facts.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/modules/bank-details/boundary-io.md`
- `docs/modules/workbench-relations/boundary-io.md`
- `docs/modules/reconciliation-workbench/boundary-io.md`
- `docs/dev/api-contracts.md`

## 当前代码入口

当前代码使用 bank-flow 独立 HTTP route、application boundary、canonical query repository、canonical 批次/事件表和 tag-rule settings key 承载业务入口；新页面和生产 API 不接收或返回 `selected_tag_codes`。

- Frontend page: `web/src/pages/BankFlowRuleBatchPage.tsx`，通过 `/bank-flow-rule-batches` route 作为流水规则批量处理页。
- Frontend feature: `web/src/features/bankFlowRuleBatches/api.ts`（HTTP/DTO mapping）、`types.ts`（public DTO/domain types）、`policy.ts`（状态/权限策略）、`viewModel.ts`（格式化、规则 grid view model）、`components.tsx`（分页、状态标签、label rail）。API 指向 `/api/bank-flow-rule-batches`。
- Backend route: `backend/src/fin_ops_platform/app/routes_bank_flow_rule_batches.py`，只承载 `/api/bank-flow-rule-batches/*`。
- Backend service: `backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py`，新提交写 `relation_mode=bank_flow_rule_batch`；共享批次计算内核在中性 `bank_batch_application_service.py` / `bank_batch_service.py`，由显式 relation mode/schema/ID prefix 直接生成正式 bank-flow 领域错误和身份，bank-flow 不继承 no-OA application service，route 不保留 legacy 错误翻译或 fallback。
- Backend query: `backend/src/fin_ops_platform/services/postgres_repositories/bank_flow_rule_batch_canonical_query.py`；SQL 只读 PostgreSQL canonical facts 和 `app.workbench_pair_relations.status='active'`，不读 Workbench projection 或 no-OA fallback。
- 旧 read-model producer/worker/manifest/deploy 注册已在跨页面清理中删除；`canonical_draft.refresh` 是批次领域后台任务，不是页面 read model。
- Rule persistence: `app_settings.bank_flow_rule_batch_tag_rules.requirements_by_tag_code`；新 API 和服务边界只读写 `rules`，拒绝 `selected_tag_codes`，重复 `tag_code` fail fast。`0111_bank_flow_rule_batch_tag_rules_canonical_shape.sql` 已将一次性复制的 legacy selected seed 合并并删除。
- Browser E2E: `web/e2e/bank-flow-rule-batches-flow.spec.ts`。

## 当前目标边界

流水规则批量处理只处理无需 OA、也无需发票即可直接生成批次的银行流水。页面右侧抽屉以紧凑 xlsx/grid 方式维护每个银行明细标签的 OA/发票要求；需要任一单据的流水退出本页面未提交区，交由关联台、待找发票等单据流程处理。

核心规则：

- 标签管理抽屉左侧 `收支类型 / 流水主标签 / 流水子标签` 来自银行明细当前 active 标签事实，只读展示，不能在本模块新增、编辑或删除。
- 右侧只保留 `OA`、`发票` 两列勾选。勾选表示该标签的业务闭环/审计提示需要对应单据，不作为 paired/unpaired 判定条件。
- 新增或未配置的银行标签默认勾选 `OA` 和 `发票`，避免新标签自动进入无需 OA/发票闭环。
- 未提交主/子标签和批次的生成资格固定为 active tag 且 `requires_oa=false`、`requires_invoice=false`；任一勾选、规则缺失或标签归档都不得进入未提交区。
- 已提交/历史 bucket 保留批次提交时冻结的标签和 requirement snapshot，不受当前勾选、标签 active 状态或改名影响。
- 未提交候选还必须排除任一 canonical active relation 已占用的银行流水；页面查询和提交入口均不得用可能滞后的 Workbench relation read model 代替 canonical relation source bundle。
- 旧 `selected_tag_codes` 不迁移为新事实源；实现时应移除或只作为只读 legacy 输入清理，所有流水重新按新规则计算。
- 页面提交的是银行流水批量关系事实。由于未提交资格已经排除需单据标签，新 relation 的冻结 requirement 必须为双 false；active relation 决定 ownership。规则保存不追溯改写既有 relation metadata。
- 规则资格变化只返回信息性的受影响未提交月份；资格未变化的语义更新不重算。保存 API 不写 dirty/outbox，也不返回 `refresh_enqueued` 或 write targets；页面清空旧选择后执行一次正常 GET。
- 从本页面提交且银行流水超过 3 条时，关联台以折叠形式展示；1 到 3 条可展开展示。
- 本页 linked 提示只显示“已有未撤回关联”和 OA/发票数量，不向用户渲染内部 relation case id；case id 仍保留在 API 数据与 Audit 证据中。

## 不属于本模块事实源

- 银行明细标签定义、自动匹配规则和分类确认归 `bank-details`。
- Workbench relation canonical fact 归 `workbench-relations`。
- 关联台 paired/unpaired 展示归 `reconciliation-workbench` projection builder/active generation；
  bank-flow 折叠摘要必须输出 `source_kind=bank_flow_rule_batch_summary`、
  `invoice_relation.code=bank_flow_rule_batch` 和 `流水规则` display tag，不得复用
  `no_oa_bank_batch_summary` 或 `免OA` 标签。
- 旧 no-OA 批次历史事实仅作为 backend legacy API/read-model 兼容风险处理；本模块不再提供旧 no-OA 历史重算页面入口或 API。

## 维护触发器

发生以下变化时必须更新本目录和相关上游/下游模块文档：

- 页面名称、路由、导航、抽屉 grid、筛选、分页、提交、撤回或权限变化。
- 标签规则 DTO、默认值、乐观锁、审计、错误码或保存语义变化。
- 批量提交 relation mode、metadata、折叠展示或 paired/open 判定变化。
- 旧 no-OA 迁移/运维工具若未来重新引入，必须作为独立运维模块建模，不能挂回本页面链路。
- canonical query、read-model cleanup、operation barrier、dirty scope 或 API response shape 变化。
- Playwright E2E 业务验收范围变化。

## 本目录文件

- `boundary-io.md`：模块边界、I/O、持久化、文件范围、依赖方向和旧代码删除条件。
- `state-machine.md`：标签规则、批量提交、关联台展示和 reset 状态机。
- `tests.md`：七类测试适用性、计划测试入口和验证命令。
- `e2e-spec.md`：Spec-first Playwright E2E 业务验收合同。
- `e2e-coverage.md`：E2E spec 到当前自动化覆盖的映射和缺口。
- `implementation-notes.md`：提炼后的决策、验收、风险和后续事项。

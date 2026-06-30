# 模块文档索引


本目录按页面和关键功能域组织维护文档。每次修改或新增功能前，先从本索引定位目标模块，读取目标模块文档，再按模块链接回到产品、架构、开发或运维长期事实源。

模块文档是日常维护入口，不替代长期事实源：

- 模块边界、I/O、文件范围索引和 read model 合同以 `docs/architecture/module-boundaries/` 为准。
- PostgreSQL 业务唯一真相和 canonical fact owner matrix 以 `docs/architecture/module-boundaries/canonical-facts.md` 和 `canonical-facts/` 为准。
- 业务口径仍以 `docs/product-specs/` 为准。
- 页面、运行链、read model、worker 和跨页面影响仍以 `docs/app-architecture/` 为准。
- API、测试和本地开发仍以 `docs/dev/` 为准。
- 部署、数据安全和 worker 运维仍以 `docs/operations/` 为准。

## 使用规则

1. 修改前识别目标页面或功能域。
2. 读取 `docs/architecture/module-boundaries/README.md` 和 `docs/architecture/module-boundaries/inventory.md`。
3. 如涉及 PostgreSQL 业务事实写入、读取、迁移、修复或 owner 判定，读取 `docs/architecture/module-boundaries/canonical-facts.md` 和 `canonical-facts/README.md`。
4. 读取目标模块 `README.md`。
5. 如涉及状态、权限、API、read model、worker、部署或测试，继续读取该模块下的 `state-machine.md`、`tests.md`、`implementation-notes.md`。
6. 如涉及 read model，继续读取 `docs/architecture/module-boundaries/read-model-contracts.md`。
7. 若改动跨多个页面或资源域，读取每个受影响模块。
8. 修改后做 docs impact assessment；模块事实、边界、I/O、文件范围、状态、测试、风险或验证方式变化时，更新对应模块文档和 `docs/architecture/module-boundaries/`。
9. 不保存原始 Codex prompt；只在 `implementation-notes.md` 记录提炼后的目标、决策、验收和风险。

## 模块清单

| Module key | 名称 | 类型 | Route | 入口文档 |
| --- | --- | --- | --- | --- |
| `reconciliation-workbench` | 关联台 | 页面模块 | `/` | `reconciliation-workbench/README.md` |
| `workbench-relations` | 关联台关系事实源 | 资源模块 | `N/A` | `workbench-relations/README.md` |
| `canonical-facts` | PostgreSQL 业务唯一真相 | 资源治理模块 | `N/A` | `canonical-facts/README.md` |
| `tax-offset` | 税金抵扣 | 页面模块 | `/tax-offset` | `tax-offset/README.md` |
| `cost-statistics` | 成本统计 | 页面模块 | `/cost-statistics` | `cost-statistics/README.md` |
| `bank-details` | 银行明细 | 页面模块 | `/bank-details` | `bank-details/README.md` |
| `bank-account-balance` | 银行账户余额 | 资源/API 模块 | `/api/bank-details/accounts` | `bank-account-balance/README.md` |
| `bank-flow-rule-batches` | 流水规则批量处理 | 页面模块 | `/bank-flow-rule-batches` | `bank-flow-rule-batches/README.md` |
| `pending-invoices` | 待找发票 | 页面模块 | `/pending-invoices` | `pending-invoices/README.md` |
| `input-invoice-usage` | 进项发票使用情况 | 页面模块 | `/input-invoice-usage` | `input-invoice-usage/README.md` |
| `oa-pending-payments` | OA待付款核对 | 页面模块 | `/oa-pending-payments` | `oa-pending-payments/README.md` |
| `output-invoice-collections` | 销项发票收款情况 | 页面模块 | `/output-invoice-collections` | `output-invoice-collections/README.md` |
| `no-oa-bank-batches` | 免OA流水批量处理 | legacy API/read-model 模块 | `/api/no-oa-bank-batches/*` | `no-oa-bank-batches/README.md` |
| `search` | 搜索索引 | 资源/API 模块 | `/api/search` | `search/README.md` |
| `batch-accounting` | 批量账务 | 页面模块 | `/batch-accounting` | `batch-accounting/README.md` |
| `turnover-ledger` | 外部往来款管理 | 页面模块 | `/turnover-ledger` | `turnover-ledger/README.md` |
| `etc-tickets` | ETC票据管理 | 页面模块 | `/etc-tickets` | `etc-tickets/README.md` |
| `settings` | 设置 | 页面模块 | `/settings` | `settings/README.md` |
| `app-health-operations` | 系统状态 | 页面模块 | `/operations/app-health` | `app-health-operations/README.md` |
| `imports-bank-transactions` | 银行流水导入 | 页面模块 | `/imports/bank-transactions` | `imports-bank-transactions/README.md` |
| `imports-invoices` | 发票导入 | 页面模块 | `/imports/invoices` | `imports-invoices/README.md` |
| `imports-etc-invoices` | ETC发票导入 | 页面模块 | `/imports/etc-invoices` | `imports-etc-invoices/README.md` |
| `read-models` | Read Model | 资源模块 | `N/A` | `read-models/README.md` |
| `runtime-workers` | Runtime Worker | 资源模块 | `N/A` | `runtime-workers/README.md` |
| `domain-events-lifecycle` | Domain Events 与 Derived Lifecycle | 资源模块 | `N/A` | `domain-events-lifecycle/README.md` |
| `app-shell-navigation` | App Shell 与导航 | 资源模块 | `N/A` | `app-shell-navigation/README.md` |
| `finance-table-system` | Finance Table System | 资源模块 | `N/A` | `finance-table-system/README.md` |
| `deploy` | 部署 | 资源模块 | `N/A` | `deploy/README.md` |
| `oa-integration` | OA 集成 | 资源模块 | `N/A` | `oa-integration/README.md` |
| `data-safety-reset` | 数据安全与重置 | 资源模块 | `N/A` | `data-safety-reset/README.md` |
| `permissions-and-audit` | 权限与审计 | 资源模块 | `N/A` | `permissions-and-audit/README.md` |


## 文件约定

每个模块默认包含：

- `README.md`：模块定位、修改前必读、代码入口、事实源链接和维护触发器。
- `state-machine.md`：业务状态机、UI 状态机、read model/worker 状态和非法状态。
- `tests.md`：七类测试适用性、现有测试入口、回归范围和验证命令。
- `e2e-spec.md`：Spec-first Browser e2e 业务验收合同；页面/功能应该如何工作。
- `e2e-coverage.md`：Spec ID 到现有 Playwright/Vitest/API/integration 覆盖的映射和缺口分类。
- `boundary-io.md`：模块边界、I/O、持久化、文件范围、依赖方向、验证入口、当前缺口和旧代码删除条件。每个模块都必须维护。
- `implementation-notes.md`：提炼后的实施记录、决策、验收结果、风险和后续事项。

不适用的文件不要删除；在文件内写明“不适用原因”，这样后续 Agent 不需要重复判断。旧模块可以按风险逐步补齐 `e2e-spec.md` / `e2e-coverage.md`，但一旦开始 Spec-first E2E Audit，后续新增或修改 Browser e2e 必须先映射到 Spec ID。

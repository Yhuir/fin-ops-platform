# 模块边界清单

本清单记录当前仓库的模块入口和文件范围定位方式。详细边界、I/O、状态机、测试矩阵和实施记录以每个 `docs/modules/<module>/` 目录为准；每个登记模块都必须维护 `boundary-io.md`。

扫描日期：2026-06-26。

## 文件范围规则

模块文件范围必须覆盖以下层级，不能只写前端页面或只写后端 service：

- 后端 HTTP 边界：`backend/src/fin_ops_platform/app/routes_*.py` 和 `server.py` 中的依赖组装。
- 后端业务边界：`backend/src/fin_ops_platform/services/` 下的 service、facade、orchestrator、gateway、read model service。
- 后端持久化边界：repository port、`postgres_repositories/`、SQL projection、state store、runtime queue。
- Worker 边界：`runtime_worker_registry.py`、worker service、projection runner、tooling。
- 前端边界：`web/src/pages/`、`web/src/features/<feature>/`、`web/src/api/`。
- 测试边界：`tests/`、`web/src/test/`、`web/e2e/` 中按模块命名的测试。
- 运维和脚本边界：`scripts/`、`deploy/`、`docs/operations/` 中影响发布、队列、worker、数据安全的文件。

新增模块或移动文件时，必须同步更新模块 README 的代码入口；如果影响全局边界，还要更新本清单。

## 模块索引

| Module key | 名称 | 类型 | Route/入口 | 边界文档 | 文件范围来源 |
| --- | --- | --- | --- | --- | --- |
| `reconciliation-workbench` | 关联台 | 页面模块 | `/` | `../../modules/reconciliation-workbench/README.md` + `../../modules/reconciliation-workbench/boundary-io.md` | 模块 README 代码入口 + boundary-io + workbench read model contract |
| `workbench-relations` | 关联台关系事实源 | 资源模块 | N/A | `../../modules/workbench-relations/README.md` + `../../modules/workbench-relations/boundary-io.md` | 模块 README 代码入口 + boundary-io + relation read model contract |
| `canonical-facts` | PostgreSQL 业务唯一真相 | 资源治理模块 | N/A | `../../modules/canonical-facts/README.md` + `../../modules/canonical-facts/boundary-io.md` | `canonical-facts.md` + 拥有事实的业务模块 boundary-io |
| `tax-offset` | 税金抵扣 | 页面模块 | `/tax-offset` | `../../modules/tax-offset/README.md` + `../../modules/tax-offset/boundary-io.md` | 模块 README 代码入口 + boundary-io + tax offset read model contract |
| `cost-statistics` | 成本统计 | 页面模块 | `/cost-statistics` | `../../modules/cost-statistics/README.md` + `../../modules/cost-statistics/boundary-io.md` | 模块 README 代码入口 + boundary-io + cost statistics read model contract |
| `bank-details` | 银行明细 | 页面模块 | `/bank-details` | `../../modules/bank-details/README.md` + `../../modules/bank-details/boundary-io.md` | 模块 README 代码入口 + boundary-io + bank detail read model contract |
| `bank-account-balance` | 银行账户余额 | 资源/API 模块 | `/api/bank-details/accounts` | `../../modules/bank-account-balance/README.md` + `../../modules/bank-account-balance/boundary-io.md` | 模块 README 代码入口 + boundary-io + bank account balance read model contract |
| `bank-flow-rule-batches` | 流水规则批量处理 | 页面模块 | `/bank-flow-rule-batches` | `../../modules/bank-flow-rule-batches/README.md` + `../../modules/bank-flow-rule-batches/boundary-io.md` | 模块 README 代码入口 + boundary-io + bank flow rule batch planned read model contract |
| `pending-invoices` | 待找发票 | 页面模块 | `/pending-invoices` | `../../modules/pending-invoices/README.md` + `../../modules/pending-invoices/boundary-io.md` | 模块 README 代码入口 + boundary-io + pending invoice read model contract |
| `input-invoice-usage` | 进项发票使用情况 | 页面模块 | `/input-invoice-usage` | `../../modules/input-invoice-usage/README.md` + `../../modules/input-invoice-usage/boundary-io.md` | 模块 README 代码入口 + boundary-io + input invoice usage read model contract |
| `oa-pending-payments` | OA待付款核对 | 页面模块 | `/oa-pending-payments` | `../../modules/oa-pending-payments/README.md` + `../../modules/oa-pending-payments/boundary-io.md` | 模块 README 代码入口 + boundary-io + OA pending payment read model contract |
| `output-invoice-collections` | 销项发票收款情况 | 页面模块 | `/output-invoice-collections` | `../../modules/output-invoice-collections/README.md` + `../../modules/output-invoice-collections/boundary-io.md` | 模块 README 代码入口 + boundary-io + output invoice collection read model contract |
| `no-oa-bank-batches` | 免OA流水批量处理 | legacy 页面模块 | `/no-oa-bank-batches` | `../../modules/no-oa-bank-batches/README.md` + `../../modules/no-oa-bank-batches/boundary-io.md` | 模块 README 代码入口 + boundary-io + no-OA bank batch legacy read model contract |
| `search` | 搜索索引 | 资源/API 模块 | `/api/search` | `../../modules/search/README.md` + `../../modules/search/boundary-io.md` | 模块 README 代码入口 + boundary-io + search read model contract |
| `batch-accounting` | 批量账务 | 页面模块 | `/batch-accounting` | `../../modules/batch-accounting/README.md` + `../../modules/batch-accounting/boundary-io.md` | 模块 README 代码入口 + boundary-io |
| `turnover-ledger` | 外部往来款管理 | 页面模块 | `/turnover-ledger` | `../../modules/turnover-ledger/README.md` + `../../modules/turnover-ledger/boundary-io.md` | 模块 README 代码入口 + boundary-io + turnover ledger read model contract |
| `etc-tickets` | ETC票据管理 | 页面模块 | `/etc-tickets` | `../../modules/etc-tickets/README.md` + `../../modules/etc-tickets/boundary-io.md` | 模块 README 代码入口 + boundary-io |
| `settings` | 设置 | 页面模块 | `/settings` | `../../modules/settings/README.md` + `../../modules/settings/boundary-io.md` | 模块 README 代码入口 + boundary-io |
| `app-health-operations` | 系统状态 | 页面模块 | `/operations/app-health` | `../../modules/app-health-operations/README.md` + `../../modules/app-health-operations/boundary-io.md` | 模块 README 代码入口 + boundary-io |
| `imports-bank-transactions` | 银行流水导入 | 页面模块 | `/imports/bank-transactions` | `../../modules/imports-bank-transactions/README.md` + `../../modules/imports-bank-transactions/boundary-io.md` | 模块 README 代码入口 + boundary-io |
| `imports-invoices` | 发票导入 | 页面模块 | `/imports/invoices` | `../../modules/imports-invoices/README.md` + `../../modules/imports-invoices/boundary-io.md` | 模块 README 代码入口 + boundary-io |
| `imports-etc-invoices` | ETC发票导入 | 页面模块 | `/imports/etc-invoices` | `../../modules/imports-etc-invoices/README.md` + `../../modules/imports-etc-invoices/boundary-io.md` | 模块 README 代码入口 + boundary-io |
| `read-models` | Read Model | 资源模块 | N/A | `../../modules/read-models/README.md` + `../../modules/read-models/boundary-io.md` | 本目录 `read-model-contracts.md` + 模块 README + boundary-io |
| `runtime-workers` | Runtime Worker | 资源模块 | N/A | `../../modules/runtime-workers/README.md` + `../../modules/runtime-workers/boundary-io.md` | runtime worker registry + 模块 README + boundary-io |
| `domain-events-lifecycle` | Domain Events 与 Derived Lifecycle | 资源模块 | N/A | `../../modules/domain-events-lifecycle/README.md` + `../../modules/domain-events-lifecycle/boundary-io.md` | 模块 README 代码入口 + boundary-io |
| `app-shell-navigation` | App Shell 与导航 | 资源模块 | N/A | `../../modules/app-shell-navigation/README.md` + `../../modules/app-shell-navigation/boundary-io.md` | 模块 README 代码入口 + boundary-io |
| `finance-table-system` | Finance Table System | 资源模块 | N/A | `../../modules/finance-table-system/README.md` + `../../modules/finance-table-system/boundary-io.md` | 模块 README 代码入口 + boundary-io |
| `deploy` | 部署 | 资源模块 | N/A | `../../modules/deploy/README.md` + `../../modules/deploy/boundary-io.md` | 模块 README 代码入口 + boundary-io + `docs/operations/` |
| `oa-integration` | OA 集成 | 资源模块 | N/A | `../../modules/oa-integration/README.md` + `../../modules/oa-integration/boundary-io.md` | 模块 README 代码入口 + boundary-io |
| `data-safety-reset` | 数据安全与重置 | 资源模块 | N/A | `../../modules/data-safety-reset/README.md` + `../../modules/data-safety-reset/boundary-io.md` | 模块 README 代码入口 + boundary-io |
| `permissions-and-audit` | 权限与审计 | 资源模块 | N/A | `../../modules/permissions-and-audit/README.md` + `../../modules/permissions-and-audit/boundary-io.md` | 模块 README 代码入口 + boundary-io |

## 当前全量定位结论

- 页面模块已经统一登记在 `docs/modules/README.md`，每个模块都有维护入口。
- PostgreSQL 业务唯一真相已经登记为 `canonical-facts` 资源治理模块；它维护 owner matrix 和全局写入/读取规则，但不替代各业务 owner 模块。
- Read model 当前以 `backend/src/fin_ops_platform/services/read_model_manifest.py` 为可执行合同，覆盖 14 个 read model，详见 `read-model-contracts.md`。
- Worker 当前以 `backend/src/fin_ops_platform/services/runtime_worker_registry.py` 为可执行合同，read model worker/event 与 manifest 可以互相核对。
- 后端路由已拆出多个 `routes_*.py` route owner，`server.py` 仍承担依赖组装和部分历史入口职责；后续后端重构必须继续把业务逻辑推向 service/repository 边界。
- 前端页面已按 `web/src/pages/` 与 `web/src/features/<feature>/` 组织；修改页面时必须同步核对后端 API、read model freshness 和模块测试文档。
- `.planning/refactors/` 中的模块化记录只能作为历史分析参考；已确认的长期规则需要落到本目录和对应模块文档。

## 缺口处理规则

如果发现模块 README 的代码入口缺失后端、前端、测试或运维文件，不要只在当前改动里临时记忆。必须：

1. 补齐模块 README 和 `boundary-io.md`。
2. 如影响模块列表，更新本清单。
3. 如影响 read model，更新 `read-model-contracts.md`、manifest、registry、测试和运维文档。
4. 在最终说明中写明边界文档已更新，或明确说明 docs 不适用的理由。

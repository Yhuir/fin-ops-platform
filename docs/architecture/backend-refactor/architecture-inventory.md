# 后端架构资产清单

## Executive Summary

本文件是 `PF-P001 - Architecture Inventory / Dynamic Call Chain Discovery` 的产物，用于把当前 Python 后端按 API、文件、外部依赖、Read Model 和运行时序做宏观分拣。它不是单模块最终设计，也不包含业务代码改动。

> 2026-07-14 rebaseline：本文中 Workbench candidate/decision、candidate store、special reconciliation 和 matching dirty fallback 的文件级描述是历史盘点，已被 Phase 21 正式关系架构取代，不再是当前实现或后续设计输入。当前事实源是 `docs/product-specs/reconciliation-and-workbench.md`、`docs/modules/reconciliation-workbench/boundary-io.md` 与 `docs/modules/workbench-relations/boundary-io.md`；新代码禁止恢复旧 candidate/decision 运行时链路。

扫描范围：

- `backend/src/fin_ops_platform/app/**/*.py`
- `backend/src/fin_ops_platform/services/**/*.py`
- `backend/src/fin_ops_platform/postgres/**/*.sql`
- `backend/src/fin_ops_platform/tools/**/*.py`
- `tests/**/*.py`
- `docs/product-specs/**/*.md`
- `docs/dev/**/*.md`
- `README.md`、`ARCHITECTURE.md`、`docs/index.md`

扫描结果摘要：

- 后端核心扫描到约 407 个 Python、SQL 和文档输入文件。
- `backend/src/fin_ops_platform/app/server.py` 约 1MB，是当前最大耦合点，承担路由注册、handler、服务装配、legacy fallback 和若干读写热路径。
- `services/postgres_repositories/read_models.py` 约 363KB，是第二大耦合点，聚合了多个领域的 Read Model 查询与刷新辅助能力，后续必须拆成 platform read-model helper + 各模块 repository。
- `Turnover Ledger` 和 `Batch Accounting` 已确认必须作为独立业务模块，不应归入 Workbench 或 Bankdetail。
- `Workbench Matching Engine` 具备较清晰的算法输入输出，但当前编排层仍依赖 Workbench candidate state、pair relation、exception、read model invalidation，暂不建议直接升格为顶层模块；先作为 Workbench 内部子域做 Micro-JIT 深挖。
- 当前计划仍是 Python-first 架构重构；本清单不建议创建新语言后端或修改生产路由。
- `PF-P001-C1` 已补齐非 `services/` 核心目录覆盖：`domain/`、`app/main.py`、`app/auth.py`、PostgreSQL migration runtime、backfill jobs 和巨型测试门禁文件必须有明确 Primary Owner。

## PF-P045 Main Delta Rebaseline

PF-P045 重新校准了 `PF-P044-MG` 后进入 `main` 的新增后端事实。此次不是重做全量 inventory，而是把 `ccbf7c2d..f68d2683` 的 main delta 纳入现有 Python-first 重构事实源。

基线状态：

- `main` 已推送并与 `origin/main` 对齐到 `f68d2683 Preserve turnover ledger group breakdowns from flat read models`。
- 重构工作分支：`codex/main-delta-rebaseline-p045`。
- Delta 范围：20 个后端/部署/测试/文档相关提交，约 178 个后端相关文件，约 28k insertions / 4.5k deletions。
- 本轮只做文档和重构计划再校准；不改业务代码，不执行 Traffic Gate，不部署。

新增 / 强化的模块事实：

| 模块 | 新增事实 | 重构影响 |
| --- | --- | --- |
| Turnover Ledger | 新增 `turnover_ledger_query_service.py`、`turnover_ledger_read_model_refresh.py`、`turnover_ledger_source_versions.py`、`turnover_ledger_sql_projection.py`，并强化 `routes_turnover_ledger.py` grouped read model breakdown | Turnover Ledger 已不只是 route/service 组合，后续 Micro-JIT 必须覆盖 query service、SQL projection、source version、read model refresh 和 grouped payload contract |
| Bankdetail / No OA Batch | 新增 `routes_bank_details.py`、`routes_no_oa_bank_batches.py`、`bank_details_application_service.py`、`bank_detail_category_selection.py`、`bank_turnover_tag_semantics.py`、`no_oa_bank_batch_*` 服务和 route tests | Bankdetail 模块边界扩大到外部流水标签语义、免 OA 批次 read model/worker/selection；不能只按旧 `bank_details_service.py` 深挖 |
| Invoices / Pending Query | 新增 `routes_pending_invoices.py`、`routes_output_invoice_collections.py`、`routes_oa_pending_payments.py`、pending/output/input invoice lifecycle、read model、status、OA reverse services 和 repository | Invoices 需要拆分 Pending Invoice、Output Invoice Collections、Input Invoice Usage、OA Pending Payments 子域，但仍归入 Invoices 顶层模块 |
| Tax / Cost / ETC | 新增 `routes_cost_statistics.py`、`routes_etc.py`、`cost_statistics_*`、`etc_business_batch_application_service.py`、`tax_offset_*` query/runtime/plan services 和 migration 0050 | Tax / Cost / ETC 的 route facade 和 runtime service 已明显增多，后续 Micro-JIT 必须覆盖 route facade、query service、runtime refresh 和 repository |
| Platform / Runtime Worker | 新增 `runtime_worker_registry.py`、`workbench_matching_dirty_scope_worker.py`、多个 deploy worker env example、RabbitMQ preflight 增强和 worker registry tests | Runtime worker 现在是跨模块 shared boundary；后续任何 worker 改动必须检查 registry、deploy env、RabbitMQ/staging preflight 和 App Health |
| Workbench | Workbench durable idempotency 仍保留后续 gate，同时新增 `workbench_matching_dirty_scope_worker.py` 和 query facade 相关测试更新 | Workbench 下一步不能只看 idempotency blocker，也要纳入 matching dirty scope worker 的 runtime 边界 |

PF-P045 没有发现需要创建新模块的证据；但确认以下模块计划必须以新 delta 为输入重新生成单模块 prompt：

- Turnover Ledger Micro-JIT 必须覆盖新增 query/read-model/source-version 文件。
- Bankdetail Micro-JIT 必须覆盖 No OA Batch 和 external turnover tag semantics。
- Invoices Micro-JIT 必须覆盖 OA Pending Payments、Output Invoice Collections 和 Input Invoice Usage OA reverse。
- Tax / Cost / ETC Micro-JIT 必须覆盖 cost statistics runtime、ETC business batch 和 tax offset plans。
- Platform / Runtime Micro-JIT 必须覆盖 runtime worker registry 和 deploy env contract。

## PF-P189 Dev Branch Bootstrap / Main Delta Rebaseline

PF-P189 建立了后续重构的 `dev` 集成分支模型，并把 `PF-P188-MG` 后进入 `main` 的新增后端事实纳入当前 inventory。此次不是重做全量 inventory，也不修改业务代码。

基线状态：

- `dev` 已从当前最新 `origin/main` 创建，并推送为 `origin/dev`。
- 后续重构功能分支从最新 `dev` 创建，MG 合入 `dev` 并在 `dev` 上复验。
- `main` 继续承载产品功能、线上修复和正式主干基线；`dev` 不是生产发布分支。
- `PF-P188-MG` 后的 main delta 范围为 `52dcd403..33bebb0d`。
- 本轮只做文档和重构计划再校准；不改业务代码，不执行 Traffic Gate，不部署。

PF-P188 后新增 / 强化的模块事实：

| 模块 | 新增事实 | 重构影响 |
| --- | --- | --- |
| Workbench | 新增/强化 object identity arbitration、relation distribution read model、all-scope identity arbitration、read model rehydrate dirty scope completion、relation SQL projection 和相关 migrations/tests | Workbench 后续 Micro-JIT 必须把 identity arbitration、relation distribution、dirty scope completion 和 read model ops helper 纳入调用链与测试范围 |
| Invoices | 新增 invoice lifecycle policy/read facade/read model refresh/sql projection、OA pending payment、invoice usage collection source versions、App Status readiness 关联 | Invoices 后续必须按 Pending Invoice、Output/Input Invoice Usage、OA Pending Payments、invoice lifecycle/status 子域拆 discovery，不得一次性机械重构 |
| Tax / Cost / ETC | 新增/强化 cost statistics all-scope readiness、runtime refresh、App Health dashboard metrics indexes、readiness reporter 关联 | Tax / Cost / ETC 后续必须覆盖 readiness lifecycle、runtime refresh、SQL projection 和 App Health observability，不只看旧查询 service |
| Platform / Ops / Runtime | 新增 deploy-control contract、release step tracing、worker readiness polling、runtime queue dead-letter resolve、read model readiness reporter/backfill、deploy worker env examples | Platform/Ops 后续必须把 deploy control、runtime worker registry、readiness reporter、dead-letter ops 和 release tracing 作为治理边界 |
| Turnover Ledger | PF-P188 已标记模块完成；后续 main delta 中只有 amount column API contract rename、Workbench relation/read model 影响和少量 Turnover relation service 修正 | Turnover Ledger 不需要立即重开模块；这些变化作为未来 Workbench/Bankdetail/Platform 交叉影响输入 |
| Batch Accounting | AppHealth/dashboard 和 batch accounting reads 有性能优化提交 | Batch Accounting 仍是独立模块；后续 discovery 必须覆盖新的 dashboard/read optimization 影响 |

PF-P189 后推荐下一步：

1. 先执行 `PF-P189-MG - Dev Branch Bootstrap / Main Delta Rebaseline Merge Gate`，把新分支规则和 rebaseline 文档合入 `dev`。
2. 再从最新 `dev` 新建下一条模块分支。
3. 下一条业务模块建议优先选择 `PF-P190 - Bankdetail / No OA Batch Discovery and Planning`，因为 Turnover Ledger 完成后的 expected-version ownership 与 bank row tag/category 影响需要由 Bankdetail/No OA Batch 接住。

### PF-P190 Bankdetail / No OA Batch Discovery Update

PF-P190 已在 `codex/bankdetail-no-oa-discovery-p190` 分支对 Bankdetail / No OA Batch 做 Micro-JIT discovery。专项文档见 `bankdetail-no-oa-discovery.md`。

本次确认：

- Bankdetail 模块必须覆盖 `/api/bank-details/*` 与 `/api/no-oa-bank-batches/*`，不能只按旧 `bank_details_service.py` 分析。
- Route 边界主要在 `app/routes_bank_details.py` 和 `app/routes_no_oa_bank_batches.py`；它们可以处理 HTTP/session mapping，但业务 service 不得读取 cookie/header 或 import `app.auth`。
- 高风险 service 包括 `bank_transaction_category_service.py`、`no_oa_bank_batch_service.py`、`bank_details_application_service.py`、`no_oa_bank_batch_application_service.py`。
- Read model / worker 边界包括 `bank_detail.read_model.refresh`、`bank_account_balance.read_model.refresh`、`no_oa_bank_batch.read_model.refresh`；PostgreSQL durable queue 仍是事实源。
- No OA Batch 是 Bankdetail 模块内高风险子域，涉及 tag selection expected-version、submit/withdraw、bulk submit、legacy migration 和 Workbench read model influence。
- Turnover Ledger 已完成后的 bank row tags/category ownership 会反向依赖 Bankdetail 对分类 facts、tag versions、dirty/outbox 的明确边界。

PF-P190 后推荐下一步：

1. 生成 `PF-P191 - Bankdetail / No OA Batch Characterization Tests`。
2. PF-P191 只允许新增/补强测试，不修改 production code。
3. 测试必须锁定 read freshness、pagination/count、category expected-version conflict、No OA tag selection/submit/withdraw、no synchronous refresh、dirty/outbox baseline。
4. 如果用户更关注运行稳定性，可以选择 `PF-P190 - Platform / Ops Runtime Delta Discovery and Planning`，优先收敛 deploy-control、readiness reporter、worker registry 和 runtime queue ops。

模块遗漏 / 错归属审计：

| 发现 | 判断 | 后续动作 |
| --- | --- | --- |
| 流水台账有独立 API、service、事件和测试 | 独立模块 | 后续 Micro-JIT 必须以 Turnover Ledger 为单独模块推进 |
| 批量记账有独立 API、service、写入用例和测试 | 独立模块 | 后续 Micro-JIT 必须以 Batch Accounting 为单独模块推进 |
| Workbench 内部多个文件超过 20KB | Workbench 顶层保留，但内部必须分子域 | 优先拆 query/read-model、matching/candidates、pair-relations/actions、exceptions、special/reconciliation |
| `server.py` 承载所有模块路由和装配 | Platform/Ops primary，所有模块 secondary | 后续按模块逐步把 handler/usecase 装配边界收窄 |
| `read_models.py` 承载跨模块读模型 | Platform Read Model repository primary，多模块 secondary | 后续按模块拆出查询 repository，保留公共 freshness/generation 工具 |

推荐后续 Micro-JIT 顺序：

1. `Platform / Ops / Runtime Boundary`：先锁定 state store、runtime queue、outbox、dirty scope、auth/session、Redis/RabbitMQ/OA Mongo 边界，防止后续模块继续依赖 legacy snapshot 或散落外部服务调用。
2. `Workbench Read Model Query`：先做只读 summary/groups/group rows 的调用链和测试边界，因为它是最高频读路径，也是后续写操作一致性的验收基线。
3. `Turnover Ledger`：独立模块且曾被遗漏，应尽早固化 API、relation、read model 和 Workbench 投影影响链。
4. `Batch Accounting`：独立写模块，但强依赖 Workbench payload 和 pair relation，需要在 Workbench 读边界清晰后推进。
5. `Workbench Matching Engine`：先作为 Workbench 内部子域深挖，若输入输出和 ownership 进一步稳定，再评估是否升格。

## API Path Ownership

一个 API path 只能有一个 primary owner。`server.py` 或 route 文件是 handler 载体，不等于业务 owner。

| API path / pattern | Method | Handler 位置 | Primary owner | 测试 / 文档事实源 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `/api/session/me` | GET | `app/server.py` | Platform / Ops | `tests/test_session_api.py`、`tests/test_auth_guard.py` | auth/session 共享边界 |
| `/api/app-health` | GET | `app/server.py` | Platform / Ops | `docs/product-specs/app-health-and-background-jobs.md` | App Health 聚合 |
| `/api/app-health/stream` | GET | `app/server.py` | Platform / Ops | `docs/product-specs/app-health-and-background-jobs.md` | SSE 长连接，后续必须保留取消和 backpressure 语义 |
| `/api/operations/app-health-dashboard` | GET | `app/server.py` | Platform / Ops | `services/operations_dashboard.py` | 运维视图 |
| `/api/background-jobs/*` | GET/POST | `app/server.py` | Platform / Ops | `services/background_job_service.py` | runtime/job/outbox 观测 |
| `/api/oa-sync/status` | GET | `app/server.py` | Platform / Ops | `services/oa_projection_sync.py` | OA projection 同步状态 |
| `/api/workbench/*` | GET/POST | `app/routes_workbench.py`、`app/server.py` | Workbench | `tests/test_workbench_v2_api.py`、`docs/product-specs/workbench.md` | 顶层 Workbench 模块 |
| `/workbench*` | GET/POST | `app/server.py` | Workbench | legacy route tests | legacy UI/API wrapper，需在 Micro-JIT 中确认是否仍生产使用 |
| `/matching/*` | GET/POST | `app/server.py` | Workbench Matching Engine 候选 | `services/matching.py`、Workbench matching tests | 暂按 Workbench 内部子域归属 |
| `/api/turnover-ledger` | GET | `app/routes_turnover_ledger.py`、`app/server.py:_handle_api_turnover_ledger*` | Turnover Ledger | `tests/test_turnover_ledger_api.py` | 独立模块 |
| `/api/turnover-ledger/export-preview` | GET | `app/server.py` | Turnover Ledger | `tests/test_turnover_ledger_export_service.py` | 导出预览 |
| `/api/turnover-ledger/export` | GET | `app/server.py` | Turnover Ledger | `tests/test_turnover_ledger_export_service.py` | 导出 |
| `/api/turnover-ledger/bank-row-tags/batch` | POST | `app/server.py` | Turnover Ledger | `tests/test_turnover_ledger_api.py` | 写入银行流水标签，影响 Bankdetail facts |
| `/api/turnover-ledger/relations/*` | GET/PUT/POST | `app/server.py` | Turnover Ledger | `tests/test_turnover_relation_service.py` | relation confirm/withdraw/extra |
| `/api/batch-accounting` | GET | `app/server.py:_handle_api_batch_accounting*` | Batch Accounting | `tests/test_batch_accounting_api.py` | 独立模块 |
| `/api/batch-accounting/submit` | POST | `app/server.py` | Batch Accounting | `tests/test_batch_accounting_api.py` | 写 relation，影响 Workbench 投影 |
| `/api/batch-accounting/{relation_id}/withdraw` | POST | `app/server.py` | Batch Accounting | `tests/test_batch_accounting_api.py` | 撤销写操作 |
| `/api/bank-details/accounts` | GET | `app/server.py` | Bankdetail | `docs/product-specs/bank-details.md` | 银行账户列表 |
| `/api/bank-details/transactions` | GET | `app/server.py` | Bankdetail | `tests/test_bank_details_api.py` | 银行流水分页 |
| `/api/bank-details/transactions/export` | GET | `app/server.py` | Bankdetail | bank detail tests | 导出 |
| `/api/bank-details/transactions/{id}/category-confirmation` | POST/DELETE | `app/server.py` | Bankdetail | bank category tests | 分类确认 / 取消 |
| `/api/bank-details/transactions/categories` | GET | `app/server.py` | Bankdetail | bank detail tests | 分类选项 |
| `/api/bank-details/auto-tag-rules*` | GET/POST/PUT/DELETE | `app/server.py` | Bankdetail | auto category tests | 自动打标规则 |
| `/api/import-facts/*` | GET/POST | `app/server.py` | Bankdetail | import facts tests | 银行事实导入边界，secondary Imports |
| `/api/no-oa-bank-batches*` | GET/POST | `app/server.py` | Bankdetail | `docs/product-specs/no-oa-bank-batches.md` | 免 OA 批次 |
| `/api/pending-invoices/*` | GET/POST | `app/server.py` | Invoices | `docs/product-specs/pending-invoices.md`、`docs/dev/pending-invoices-api.md` | 待找发票 |
| `/api/input-invoice-usage/*` | GET/POST | `app/server.py` | Invoices | invoice usage tests | 进项使用 |
| `/api/oa-pending-payments/*` | GET | `app/routes_oa_pending_payments.py`、`app/server.py` | Invoices | `docs/product-specs/oa-pending-payments.md`、`docs/dev/oa-pending-payments-api.md` | OA 待付款核对 |
| `/api/output-invoice-collections/*` | GET/POST | `app/server.py` | Invoices | output invoice tests | 销项收款 |
| `/imports/*` | GET/POST | `app/server.py` | Imports | `docs/product-specs/imports.md` | 导入文件与任务 |
| `/api/search` | GET | `app/server.py:_handle_api_search` | Search / Pending Query | `tests/test_search_api.py` | 统一搜索 |
| `/api/tax-offset*` | GET/POST | `app/routes_tax.py`、`app/server.py` | Tax / Cost / ETC | `docs/product-specs/tax-offset-and-etc.md` | 税金抵扣 |
| `/api/cost-statistics*` | GET/POST | `app/server.py` | Tax / Cost / ETC | `docs/product-specs/cost-statistics.md` | 成本统计 |
| `/api/etc/*` | GET/POST | `app/server.py` | Tax / Cost / ETC | `docs/dev/etc-business-batches-api.md` | ETC 对账 |
| `/integrations/oa` | GET/POST | `app/server.py` | Platform / Ops | `docs/product-specs/oa-integration.md` | OA 集成边界 |
| `/projects`、`/ledgers`、`/reminders`、`/reconciliation/cases` | GET/POST | `app/server.py` | Legacy / Review | legacy tests / product docs | 后续需判断是否归入 Ops、Workbench 或独立 legacy 模块 |

## File Ownership

### 分拣规则

以下文件族默认归属到对应模块；有跨模块影响时只记录 secondary influence，不改变 primary owner。

| 文件族 | Primary owner | Secondary influence | 说明 |
| --- | --- | --- | --- |
| `backend/src/fin_ops_platform/app/server.py` | Platform / Ops | 所有业务模块 | 路由、装配、legacy fallback 最大耦合点 |
| `backend/src/fin_ops_platform/app/routes_workbench.py` | Workbench | Platform routing | Workbench route facade |
| `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` | Turnover Ledger | Platform routing | Turnover route facade |
| `backend/src/fin_ops_platform/app/routes_tax.py` | Tax / Cost / ETC | Platform routing | Tax/ETC route facade |
| `backend/src/fin_ops_platform/app/main.py` | Platform / App Entry | 所有 HTTP 模块 | ASGI/application 入口，不能在模块重构中遗漏 |
| `backend/src/fin_ops_platform/app/auth.py` | Platform / Auth | 所有受保护 API | 鉴权、身份上下文、中间件边界，安全高风险 |
| `backend/src/fin_ops_platform/app/worker.py` | Platform / Ops | Imports、Read Model modules | worker bootstrap |
| `backend/src/fin_ops_platform/app/rabbitmq_*.py` | Platform / Ops | All modules via outbox | RabbitMQ transport，不是业务 owner |
| `backend/src/fin_ops_platform/app/bank_account_balance_backfill.py` | Platform / Ops Backfill | Bankdetail | 账户余额回填入口，必须随 Bankdetail read model 验证 |
| `backend/src/fin_ops_platform/app/bank_detail_backfill.py` | Platform / Ops Backfill | Bankdetail | 银行流水 read model 回填入口，必须随 Bankdetail 验证 |
| `backend/src/fin_ops_platform/domain/__init__.py` | Platform / Shared Domain | All modules | shared domain package boundary |
| `backend/src/fin_ops_platform/domain/models.py` | Platform / Shared Domain | All modules | 共享 dataclass/value object/source type，依赖方向必须受控 |
| `backend/src/fin_ops_platform/domain/enums.py` | Platform / Shared Domain | All modules | 共享枚举和领域常量，禁止模块私自复制 |
| `backend/src/fin_ops_platform/postgres/migrate.py` | Platform / DB Migration Runtime | All modules via schema changes | migration 执行器，不是 SQL migration 文件 |
| `backend/src/fin_ops_platform/postgres/__main__.py` | Platform / DB Migration Runtime | All modules via schema changes | `python -m` 迁移入口 |
| `backend/src/fin_ops_platform/services/runtime_*.py` | Platform / Ops | All modules via durable queue | runtime queue、worker、Redis、bootstrap |
| `backend/src/fin_ops_platform/services/state_store*.py` | Platform / Ops | Legacy fallback risk | state store / snapshot boundary |
| `backend/src/fin_ops_platform/services/postgres_state_store.py` | Platform / Ops | Legacy fallback risk | PostgreSQL state store |
| `backend/src/fin_ops_platform/services/mongo_oa_adapter.py` | Platform / Ops | Invoices、Imports、OA projection | OA Mongo 只读 adapter |
| `backend/src/fin_ops_platform/services/postgres_repositories/core.py` | Platform / Ops | All SQL modules | DB helper / transaction helper |
| `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` | Platform Read Model | Workbench、Invoices、Tax、Cost、Search、Bankdetail、Turnover、Batch | 需拆分的大型 read model repository |
| `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py` | Workbench | Batch、Turnover influence | Workbench facts/read model repository |
| `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py` | Tax / Cost / ETC | Platform SQL | Tax/ETC repository |
| `backend/src/fin_ops_platform/services/workbench_*.py` | Workbench | Turnover、Batch、Invoices、Bankdetail influence | Workbench 顶层与内部子域 |
| `backend/src/fin_ops_platform/services/live_workbench_service.py` | Workbench | App Health/SSE | Live/refresh behavior |
| `backend/src/fin_ops_platform/services/matching.py` | Workbench Matching Engine 候选 | Legacy / Review | legacy matching service |
| `backend/src/fin_ops_platform/services/turnover_*.py` | Turnover Ledger | Bankdetail、Workbench | Turnover read/write/export |
| `backend/src/fin_ops_platform/services/batch_accounting_service.py` | Batch Accounting | Workbench | Batch submit/withdraw/list |
| `backend/src/fin_ops_platform/services/bank_*`、`no_oa_bank_*` | Bankdetail | Workbench、Turnover | 银行流水、标签、账户余额、免 OA 批次 |
| `backend/src/fin_ops_platform/services/pending_invoice_*`、`input_invoice_*`、`oa_pending_payment_*`、`output_invoice_*`、`invoice_*`、`oa_attachment_invoice_*` | Invoices | Search、Workbench | 发票、附件、使用/收款、OA 待付款核对 |
| `backend/src/fin_ops_platform/services/import*`、`object_storage.py` | Imports | Bankdetail、Invoices、Tax / Cost / ETC | 导入文件、任务、对象存储 |
| `backend/src/fin_ops_platform/services/tax_*`、`cost_*`、`etc_*`、`project_costing.py` | Tax / Cost / ETC | Imports、Search | 税金、成本、ETC |
| `backend/src/fin_ops_platform/services/search_*` | Search / Pending Query | Invoices、Bankdetail、Workbench | 搜索和 pending projection |
| `backend/src/fin_ops_platform/services/background_job_service.py`、`app_health_service.py`、`operations_dashboard.py`、`access_control_service.py`、`app_settings_service.py` | Platform / Ops | All modules | 运维、健康、权限、配置 |
| `backend/src/fin_ops_platform/tools/**/*.py` | Platform / Ops | 所在任务相关模块 | backfill、migration、diagnostics |
| `backend/src/fin_ops_platform/postgres/migrations/**/*.sql` | Platform / Ops | Table owner modules | migration 是平台资产；表 ownership 见下文 |
| `tests/test_workbench*.py` | Workbench | Batch、Turnover influence when named | Workbench 测试族 |
| `tests/test_turnover*.py` | Turnover Ledger | Workbench influence | Turnover 测试族 |
| `tests/test_batch_accounting*.py` | Batch Accounting | Workbench influence | Batch 测试族 |
| `tests/test_bank*.py`、`tests/test_no_oa*.py` | Bankdetail | Workbench influence | Bankdetail 测试族 |
| `tests/test_pending_invoice*.py`、`tests/test_input_invoice*.py`、`tests/test_output_invoice*.py`、`tests/test_invoice*.py` | Invoices | Search influence | Invoices 测试族 |
| `tests/test_import*.py` | Imports | Target facts modules | Imports 测试族 |
| `tests/test_tax*.py`、`tests/test_cost*.py`、`tests/test_etc*.py` | Tax / Cost / ETC | Search influence | Tax/Cost/ETC 测试族 |
| `tests/test_search*.py` | Search / Pending Query | Invoices、Bankdetail | Search 测试族 |
| `tests/test_runtime*.py`、`tests/test_app_health*.py`、`tests/test_auth*.py`、`tests/test_session*.py`、`tests/test_derived_data_lifecycle*.py` | Platform / Ops | All modules | runtime、auth、health、lifecycle 测试 |

### 非 Services 核心文件显式归属

`PF-P001-C1` 将非 `services/` 目录列为生产级覆盖面要求：这些文件体量不一定大，但属于入口、安全、共享模型、迁移执行和运维回填边界，后续 Micro-JIT 不得绕过。

| 文件 | 大小约 | Primary owner | Secondary influence | 生产级判断 |
| --- | ---: | --- | --- | --- |
| `domain/__init__.py` | <1KB | Platform / Shared Domain | All modules | 包边界，低风险但必须显式归属 |
| `domain/models.py` | 12KB | Platform / Shared Domain | All modules | 共享值对象和 dataclass，依赖方向高风险 |
| `domain/enums.py` | 3KB | Platform / Shared Domain | All modules | 共享枚举，不允许各模块复制分叉 |
| `app/__init__.py` | <1KB | Platform / App Entry | All app modules | 包边界 |
| `app/main.py` | 1KB | Platform / App Entry | All HTTP modules | ASGI/application 入口，启动链路事实源 |
| `app/auth.py` | 6KB | Platform / Auth | All protected APIs | 鉴权中间件、身份上下文，安全高风险 |
| `app/server.py` | 1031KB | Platform / Ops | All modules | 最大耦合点 |
| `app/worker.py` | 24KB | Platform / Ops | Imports、Read Model modules | worker bootstrap，后台链路入口 |
| `app/routes_workbench.py` | 2KB | Workbench | Platform routing | Workbench route facade |
| `app/routes_turnover_ledger.py` | 20KB | Turnover Ledger | Platform routing | Turnover route facade，超过 20KB |
| `app/routes_tax.py` | <1KB | Tax / Cost / ETC | Platform routing | Tax route facade |
| `app/rabbitmq_dispatcher.py` | 5KB | Platform / Queue Transport | All modules via outbox | RabbitMQ publisher/dispatcher 入口 |
| `app/rabbitmq_topology.py` | 1KB | Platform / Queue Transport | All modules via outbox | RabbitMQ topology helper |
| `app/bank_account_balance_backfill.py` | 4KB | Platform / Ops Backfill | Bankdetail | 账户余额回填，必须绑定 Bankdetail 验证 |
| `app/bank_detail_backfill.py` | 4KB | Platform / Ops Backfill | Bankdetail | 银行流水 read model 回填，必须绑定 Bankdetail 验证 |
| `postgres/__init__.py` | <1KB | Platform / DB Migration Runtime | All schema modules | 包边界 |
| `postgres/__main__.py` | <1KB | Platform / DB Migration Runtime | All schema modules | CLI 迁移入口 |
| `postgres/migrate.py` | 13KB | Platform / DB Migration Runtime | All schema modules | migration 执行器，高风险，必须随 schema 重构验证 |
| `postgres/migrations/*.sql` | varies | Platform / DB Schema | Table owner modules | SQL migration 是平台资产，业务表 ownership 由模块声明 |

### 高风险大文件

超过 20KB 或承载关键事务/事件链路的文件必须在后续 Micro-JIT 中显式读取，不能只用通配符归属。

| 文件 | 大小约 | Primary owner | 风险 |
| --- | ---: | --- | --- |
| `app/server.py` | 1031KB | Platform / Ops | 路由、handler、装配和 legacy fallback 混杂 |
| `services/postgres_repositories/read_models.py` | 363KB | Platform Read Model | 跨模块 Read Model 聚合过多 |
| `services/state_store.py` | 181KB | Platform / Ops | legacy snapshot / local state 风险 |
| `services/etc_service.py` | 147KB | Tax / Cost / ETC | ETC 业务和导入/对账耦合 |
| `services/mongo_oa_adapter.py` | 142KB | Platform / Ops | OA Mongo 只读边界大且复杂 |
| `services/pending_invoice_service.py` | 104KB | Invoices | 待找发票热路径和 read model fallback |
| `services/no_oa_bank_batch_service.py` | 103KB | Bankdetail | 免 OA 批次和 Workbench 影响 |
| `services/bank_transaction_category_service.py` | 92KB | Bankdetail | 分类写入影响 Turnover / Workbench |
| `services/workbench_candidate_grouping.py` | 81KB | Workbench | 候选分组、Turnover/Batch special metadata |
| `services/etc_reconciliation_service.py` | 77KB | Tax / Cost / ETC | ETC 对账核心业务逻辑，文件体量大且规则复杂 |
| `services/workbench_sql_projection.py` | 77KB | Workbench | SQL projection 与 read model freshness |
| `services/workbench_query_service.py` | 69KB | Workbench | Summary/groups/group rows 读链路 |
| `services/imports.py` | 66KB | Imports | 导入确认、事实写入、任务边界 |
| `services/output_invoice_collection_service.py` | 65KB | Invoices | 销项收款状态 |
| `services/app_settings_service.py` | 65KB | Platform / Ops | 配置和权限口径 |
| `services/workbench_free_matching_engine.py` | 62KB | Workbench Matching Engine 候选 | 匹配算法输入输出相对稳定 |
| `services/postgres_state_store.py` | 61KB | Platform / Ops | PostgreSQL state store / legacy fallback |
| `services/import_file_service.py` | 55KB | Imports | 文件对象和导入任务 |
| `services/turnover_ledger_service.py` | 54KB | Turnover Ledger | 读路径可能同步 rebuild |
| `services/workbench_matching_rules.py` | 53KB | Workbench Matching Engine 候选 | 匹配规则口径 |
| `services/input_invoice_usage_service.py` | 50KB | Invoices | 进项使用 |
| `services/postgres_repositories/ops_tax_etc.py` | 50KB | Tax / Cost / ETC | Tax/ETC SQL repository |
| `services/runtime_queue.py` | 48KB | Platform / Ops | outbox / dirty scope 核心 |
| `services/postgres_repositories/workbench.py` | 45KB | Workbench | Workbench repository |
| `services/batch_accounting_service.py` | 41KB | Batch Accounting | 独立写模块，强依赖 Workbench payload |
| `services/reconciliation.py` | 40KB | Legacy / Review | 需确认归属 Workbench 还是独立 legacy |
| `services/live_workbench_service.py` | 39KB | Workbench | Live/refresh/SSE 相关 |
| `services/oa_attachment_invoice_service.py` | 39KB | Invoices | OA 附件发票缓存 |
| `services/postgres_repositories/oa_projection.py` | 38KB | Platform / Ops | OA projection SQL |
| `services/etc_reconciliation_zip_filter.py` | 36KB | Tax / Cost / ETC | ETC 对账 ZIP/文件过滤逻辑，Imports secondary |
| `services/project_detail_export_service.py` | 35KB | Tax / Cost / ETC | 项目明细导出，成本/项目统计边界 |
| `services/turnover_relation_service.py` | 34KB | Turnover Ledger | relation confirm/withdraw |
| `services/workbench_exception_case_service.py` | 33KB | Workbench | exception case 写入和投影 |
| `services/etc_document_parsers.py` | 33KB | Tax / Cost / ETC | ETC 解析 |
| `services/bank_details_service.py` | 31KB | Bankdetail | 银行流水 API 服务 |
| `services/bank_detail_sql_projection.py` | 31KB | Bankdetail | 银行流水 SQL projection |
| `services/search_pending_sql_projection.py` | 28KB | Search / Pending Query | pending/search SQL projection |
| `services/workbench_special_pair_rule_service.py` | 28KB | Workbench | special pair rule |
| `services/runtime_monitoring.py` | 28KB | Platform / Ops | runtime health metrics |
| `services/workbench_matching_orchestrator.py` | 27KB | Workbench Matching Engine 候选 | 编排层仍写 candidate state 和 invalidation |
| `services/background_job_service.py` | 27KB | Platform / Ops | background job API |
| `services/workbench_exception_application_service.py` | 27KB | Workbench | exception application |
| `services/workbench_special_rule_detectors.py` | 26KB | Workbench | 特殊规则 detector，影响 matching/special 子域 |
| `services/search_service.py` | 25KB | Search / Pending Query | `/api/search` 主业务服务，用户可见热路径 |

### 测试门禁热点

测试文件不是生产代码 owner，但大型测试套件是 Merge Gate 的事实源。后续模块重构不能只跑小单测，必须把对应热点测试纳入验证计划。

| 测试文件 | 大小约 | Primary owner | Gate 用途 |
| --- | ---: | --- | --- |
| `tests/test_workbench_v2_api.py` | 362KB | Workbench | Workbench API 端到端/集成行为，Batch/Turnover 投影 secondary |
| `tests/test_etc_backend.py` | 203KB | Tax / Cost / ETC | ETC 后端主回归套件 |
| `tests/test_workbench_sql_runtime.py` | 197KB | Workbench | Workbench SQL runtime/read model 行为 |
| `tests/test_etc_reconciliation_service.py` | 134KB | Tax / Cost / ETC | ETC reconciliation characterization tests |
| `tests/test_mongo_oa_adapter.py` | 127KB | Platform / OA Adapter | OA Mongo adapter 回归套件 |
| `tests/test_workbench_candidate_grouping.py` | 96KB | Workbench | Workbench matching/candidate grouping |
| `tests/test_state_store.py` | 80KB | Platform / State Store | legacy state / snapshot 风险门禁 |
| `tests/test_settings_data_reset_service.py` | 62KB | Platform / Ops | settings/data reset 运维门禁 |
| `tests/test_bank_details_service.py` | 57KB | Bankdetail | 银行流水服务行为 |
| `tests/test_cost_statistics_api.py` | 50KB | Tax / Cost / ETC | 成本统计 API 回归 |

## Target Candidate Modules

| 模块 | Primary responsibility | 核心 facts / read model | 当前耦合 |
| --- | --- | --- | --- |
| Platform / Infrastructure | auth、DB、queue、cache、storage、observability、runtime、OA adapter | `job.outbox_events`、`job.read_model_dirty_scopes`、health/runtime state | `server.py`、`state_store.py`、`runtime_queue.py` 仍过宽 |
| Workbench | 工作台读写、pair relations、exceptions、reconciliation、read model | `app.workbench_pair_relations`、`read_model.workbench_*` | 与 Turnover/Batch/Invoices/Bankdetail facts 有投影协作 |
| Workbench Matching Engine 候选 | 候选分组、自由匹配、规则、金额检查 | `read_model.workbench_candidate_matches` / candidate state | 编排层仍依赖 Workbench pair relation、exception、read model invalidation |
| Turnover Ledger | 流水台账、turnover relation、extra、export | `app.turnover_relations`、`read_model.turnover_ledger_rows` | Bankdetail 分类、Workbench grouping 受影响 |
| Batch Accounting | 批量记账 list/submit/withdraw | batch relation special metadata / Workbench pair relation | 读取 Workbench payload，写入影响 Workbench |
| Bankdetail | 银行流水、标签、自动分类、账户余额、免 OA 批次 | `app.bank_transactions`、`read_model.bank_detail_*`、`read_model.no_oa_bank_batch_rows` | 分类变更影响 Workbench/Turnover |
| Invoices | 待找发票、进项使用、销项收款、OA 附件发票 | `app.invoices`、invoice usage/collection read models | 与 Search/Workbench/Imports 协作 |
| Imports | 文件导入、预览、确认、任务、对象存储 | `app.import_batches`、`app.import_files`、`job.import_jobs` | 写入目标 facts 后影响多模块 read model |
| Tax / Cost / ETC | 税金抵扣、成本统计、ETC、项目成本 | `read_model.cost_statistics_*`、`read_model.tax_offset_*`、ETC facts | 导入和 Redis cache 影响大 |
| Search / Pending Query | 统一搜索、pending projection 热路径 | `read_model.search_index_rows`、pending rows | 读模型依赖 Invoices/Bankdetail/Workbench |
| Ops / Runtime | App Health、background jobs、settings、access control、OA sync | health/job/runtime tables | 横切 platform，不能写业务规则 |

## Shared Domain / App Entry / Auth / Migration Inventory

这些文件属于跨模块稳定边界，不进入任何单一业务模块。后续模块可以依赖共享 domain 值对象，但不得让 shared domain 反向 import 业务 service。

| 边界 | 文件 | Primary owner | 约束 |
| --- | --- | --- | --- |
| Shared Domain | `domain/models.py`、`domain/enums.py`、`domain/__init__.py` | Platform / Shared Domain | 只能承载稳定值对象、枚举和跨模块通用数据结构；禁止放业务流程、SQL、Redis/RabbitMQ、HTTP 逻辑 |
| App Entry | `app/main.py`、`app/__init__.py` | Platform / App Entry | 只负责创建/暴露 application 入口；不得新增业务 usecase |
| Auth | `app/auth.py` | Platform / Auth | 必须统一 OA 用户身份、权限上下文、失败响应和审计字段；所有模块只消费 auth context，不解析 raw cookie/token |
| DB Migration Runtime | `postgres/migrate.py`、`postgres/__main__.py`、`postgres/__init__.py` | Platform / DB Migration Runtime | migration 执行器必须与 schema 文件分离验证；任何 schema 改动都要跑 migration gate |
| Ops Backfill | `app/bank_account_balance_backfill.py`、`app/bank_detail_backfill.py` | Platform / Ops Backfill | 回填脚本是生产运维入口，Bankdetail/Read Model 重构后必须更新 smoke/checklist |

## Tax / Cost / ETC Deep Inventory

本模块存在多个超过 20KB 的核心文件。后续 Tax / Cost / ETC Micro-JIT 不能只读取 `etc_service.py`、`tax_offset_service.py`、`cost_statistics_sql_projection.py` 或 `tax_offset_sql_projection.py`，必须显式覆盖 ETC 对账、ZIP/文件过滤和项目明细导出。legacy `cost_statistics_service.py` 与混合 `cost_tax_sql_projection.py` 已删除，不能恢复为第二成本归集事实源或共享 owner。

| 文件 | 子域 | 归属判断 |
| --- | --- | --- |
| `services/etc_service.py` | ETC main service | ETC 导入、查询、业务批次与对账入口，大文件，高风险 |
| `services/etc_reconciliation_service.py` | ETC reconciliation | ETC 对账核心业务逻辑，约 77KB，必须单独做调用链和 characterization tests |
| `services/etc_reconciliation_zip_filter.py` | ETC import/file filter | ZIP/文件过滤逻辑，Tax / Cost / ETC primary，Imports secondary |
| `services/etc_document_parsers.py` | ETC parsing | 文档解析，需与 Imports 文件边界隔离 |
| `services/cost_statistics_sql_projection.py` | cost statistics | 成本统计归集、特殊关系规则与 read model 构建边界；不得恢复 live service |
| `services/project_detail_export_service.py` | project cost export | 项目明细导出，归 Tax / Cost / ETC，不能遗漏在导出工具外 |
| `services/tax_offset_*` | tax offset | 税金抵扣 read model、refresh、Redis cache |
| `services/tax_offset_sql_projection.py` | tax offset SQL projection | 税金 projection 独立 owner；不得重新 import 成本模块或恢复混合层 |
| `services/postgres_repositories/ops_tax_etc.py` | SQL repository | Tax/Cost/ETC repository，后续按子域拆分 |

## Search / Pending Query Inventory

Search / Pending Query 是独立候选模块，虽然文件数少，但 `/api/search` 是用户可见热路径，不能按“小模块”低估风险。

| 文件 | 子域 | 归属判断 |
| --- | --- | --- |
| `services/search_service.py` | search API service | `/api/search` 主业务服务，约 25KB，应作为中风险文件显式读取 |
| `services/search_pending_sql_projection.py` | SQL projection | pending/search SQL projection，高风险 read model 查询 |
| `services/search_pending_read_model_refresh.py` | read model refresh | search/pending refresh worker 边界 |
| `tests/test_search_api.py`、`tests/test_search_service.py` | tests | Search Micro-JIT 的 characterization tests 入口 |

## Workbench Deep Inventory

| 文件 | 子域 | 归属判断 |
| --- | --- | --- |
| `services/workbench_query_service.py` | query/read-model | Workbench 读入口，优先 Micro-JIT |
| `services/workbench_sql_projection.py` | query/read-model | SQL projection，大文件，高风险 |
| `services/workbench_read_model_service.py` | query/read-model | active generation / freshness 读取 |
| `services/workbench_read_model_refresh.py` | query/read-model | worker refresh |
| `services/workbench_candidate_grouping.py` | matching/candidates | 候选分组，识别 Turnover/Batch special metadata |
| `services/workbench_free_matching_engine.py` | matching/candidates | 算法核心，输入 rows，输出 decisions |
| `services/workbench_matching_rules.py` | matching/candidates | 匹配规则 |
| `services/workbench_matching_orchestrator.py` | matching/candidates | 编排层，删除/upsert candidates、mark processed、invalidate read model |
| `services/workbench_candidate_match_service.py` | matching/candidates | candidate state / freshness |
| `services/workbench_amount_check_service.py` | matching/candidates | 金额检查，偏纯逻辑 |
| `services/workbench_pair_relation_service.py` | pair-relations/actions | confirm/cancel relation 核心 |
| `services/workbench_action_service.py` | pair-relations/actions | action usecase |
| `services/workbench_override_service.py` | pair-relations/actions | row override |
| `services/workbench_matching_dirty_scope_service.py` | pair-relations/actions | dirty scope / matching refresh |
| `services/workbench_exception_case_service.py` | exceptions | exception case facts |
| `services/workbench_exception_application_service.py` | exceptions | exception apply/revert |
| `services/workbench_exception_projection.py` | exceptions | exception projection |
| `services/workbench_special_pair_rule_service.py` | special/reconciliation | special pair rules |
| `services/workbench_special_rule_detectors.py` | special/reconciliation | detector rules |
| `services/workbench_reconciliation_*` | special/reconciliation | reconciliation dirty queue / decisions |
| `services/workbench_text_normalization.py` | shared-normalization | 可抽纯函数工具，但先保持 Workbench 内部 |
| `services/live_workbench_service.py` | live/read-model | live refresh / status / SSE 相关 |

Workbench 生产级拆分结论：

- 顶层仍保持一个 Workbench 模块，避免破坏同一 active generation、source version 和写后读边界。
- 内部必须按子域拆分测试与接口，禁止继续把 query、matching、relation、exception 混入同一个 service。
- 第一轮 Workbench Micro-JIT 应从 `query/read-model` 开始，不从写操作或 matching 开始。

## Workbench Matching Engine Candidate Evaluation

CodeGraph 校准结论：

- `WorkbenchFreeMatchingEngine.generate_decisions(scope_month, oa_rows, bank_rows, invoice_rows, source_versions)` 输入相对稳定，输出为 `WorkbenchDecision` 列表，偏纯算法。
- `WorkbenchAmountCheckService` 偏纯计算，适合先抽测试边界。
- `WorkbenchMatchingOrchestrator.run` 会清理月份 candidates、加载 rows、排除 active pair relations、生成 candidates、抑制 active exception cases、upsert candidate、mark scope processed，并触发 read model invalidation。
- `WorkbenchCandidateMatchService` 管理 candidate/scope_run 状态和 freshness，不只是算法函数。

升格评估：

| 问题 | 当前答案 | 证据 |
| --- | --- | --- |
| 是否有稳定输入 | 部分有 | `generate_decisions` 输入 rows + source_versions |
| 是否有稳定输出 | 部分有 | 输出 decisions/candidates，但编排层还写 candidate state |
| 是否直接拥有 facts 写入 | 暂未确认独立 facts | candidate state 与 Workbench read model 绑定 |
| 是否直接拥有 Workbench active generation 发布权 | 不应拥有 | 当前通过 Workbench read model invalidation 协作 |
| 是否与 Workbench 写操作共享不可拆 transaction | 编排层存在强耦合风险 | pair relation、exception、candidate freshness 互相影响 |
| 是否建议升格顶层模块 | 暂不升格 | 先作为 Workbench 内部 `matching/candidates` 子域 |

结论：

Workbench Matching Engine 可以作为后续独立模块候选，但当前不应直接提升为顶层模块。下一步应先在 Workbench 内部建立 ports：row provider、candidate store、relation reader、exception reader、read model invalidator，并用单元测试固定纯算法和编排边界。

## Turnover Ledger Inventory

范围：

- `/api/turnover-ledger*`
- `app/routes_turnover_ledger.py`
- `app/server.py` 中 `_handle_api_turnover_ledger*`
- `services/turnover_ledger_service.py`
- `services/turnover_relation_service.py`
- `services/turnover_ledger_extra_service.py`
- `services/turnover_ledger_export_service.py`
- `services/derived_data_lifecycle_service.py` 中 `turnover_relation_changed`

测试事实源：

- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_service.py`
- `tests/test_turnover_relation_service.py`
- `tests/test_turnover_ledger_export_service.py`
- `tests/test_workbench_turnover_grouping.py`

运行时序候选：

```text
GET /api/turnover-ledger
  -> server / routes_turnover_ledger
  -> TurnoverLedgerService.list_ledger/list_grouped_ledger
  -> bank rows / category rows / turnover relations
  -> read_model.turnover_ledger_rows 或同步 rebuild fallback
  -> response
```

```text
POST /api/turnover-ledger/relations/confirm
  -> server handler
  -> TurnoverRelationService.confirm_relation
  -> write relation/audit
  -> derived_data_lifecycle.turnover_relation_changed
  -> dirty scope / outbox / Workbench projection impact
```

风险：

- 读路径存在 `rebuild_from_bank_rows` 线索，必须确认是否仍在请求路径同步重建。
- `turnover_ledger_extras` 有 legacy fallback 线索，后续必须判断生产路径是否还会触发 full snapshot/local state。
- 银行流水标签批量更新属于 Turnover API，但写入 Bankdetail facts，必须在事务和事件契约中明确 primary owner。

结论：

Turnover Ledger 是独立模块。自 2026-07-26 起，它与 Workbench 的读取协作只通过同一个 canonical
`app.workbench_pair_relations` 事实表；页面在一个 repeatable-read 只读快照内组合结果，不再经过自己的
source version、dirty scope、read model 或 worker，也不直接调用 Workbench usecase。

### PF-P046 Turnover Ledger Discovery Update

PF-P046 已对 PF-P045 main delta 后的 Turnover Ledger 做 Micro-JIT discovery。专项文档见 `turnover-ledger-discovery.md`。

新增确认：

- Turnover Ledger 当前读路径由 `TurnoverLedgerQueryService` 在单个 canonical PostgreSQL snapshot 中直接构建；旧 SQL projection、flat compatibility、freshness enqueue 和 worker 链已删除。
- `GET /api/turnover-ledger?view=grouped` 只接受原生 grouped payload，不再把旧 flat projection 转回 grouped。
- Turnover 没有 manifest、scope policy、worker registration、RabbitMQ event 或 App Status readiness。
- `RuntimeQueueRepository.enqueue_read_model_refresh_in_transaction()` 已提供 dirty scope + outbox + monotonic source_version 的平台能力，但 Turnover relation confirm/withdraw、extra update、bank-row-tags batch 仍由 `server.py` handler finalizer 编排多个 side effect，不是显式 Turnover Unit of Work。
- `/api/turnover-ledger/bank-row-tags/batch` 是 Turnover API，但写入 Bankdetail category facts；后续必须用明确 service port 和 characterization tests 固定 ownership。
- `turnover_ledger_extras` 仍存在 `legacy_turnover_ledger_extras_fallback_persist` 风险，后续应优先锁定并移除或限制 fallback。

下一步建议：

- `PF-P047 - Turnover Ledger Characterization Tests`，先锁定 freshness、grouped breakdown、relation write side effects、extra fallback、bank tag batch 和 export payload。
- 不应直接进入 extraction/refactor。

## Batch Accounting Inventory

范围：

- `/api/batch-accounting*`
- `app/server.py` 中 `_handle_api_batch_accounting*`
- `services/batch_accounting_service.py`
- `services/postgres_repositories/read_models.py` 中 `load_batch_accounting_workbench_payload`
- `services/derived_data_lifecycle_service.py` 中 `batch_accounting_relation_changed`

测试事实源：

- `tests/test_batch_accounting_api.py`
- `tests/test_workbench_v2_api.py` 中 batch accounting 投影相关用例
- `tests/test_workbench_persist_scheduler.py`
- `tests/test_derived_data_lifecycle_service.py`

运行时序候选：

```text
GET /api/batch-accounting
  -> server handler
  -> BatchAccountingService.build_payload
  -> load_batch_accounting_workbench_payload
  -> Workbench pair relation reader
  -> response
```

```text
POST /api/batch-accounting/submit
  -> server handler
  -> BatchAccountingService.submit
  -> validate submitted bank/OA rows, expected_version, amount/note/invoice ids
  -> write relation / metadata / audit
  -> derived_data_lifecycle.batch_accounting_relation_changed
  -> dirty scope / outbox / Workbench projection impact
```

风险：

- Batch 读取 Workbench payload，但写入边界应属于 Batch relation usecase。
- submit/withdraw 的 expected_version、note/reason、amount check 必须保持在 usecase，不应落在 handler。
- `repair_legacy_case_id_collisions` 保留为 service-level repair capability；高频读路径和 app/server wrapper 不得触发 repair，旧 app-level wrapper 已删除。

结论：

Batch Accounting 是独立模块，但需要在 Workbench query/read-model 边界明确后推进。

## External Dependency Matrix

| 模块 | PostgreSQL facts | PostgreSQL read model | Redis | RabbitMQ / outbox | OA Mongo | MinIO/S3 | Auth/session | local state / legacy snapshot |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Platform / Ops | runtime/job/settings/auth related | health/runtime projections | runtime wakeup/cache | `job.outbox_events`、`job.read_model_dirty_scopes` | `mongo_oa_adapter.py` | object storage port | primary owner | primary risk owner |
| Workbench | pair relations、overrides、exceptions | `read_model.workbench_*` | versioned page/status cache | dirty scope / read model refresh | 通过 OA projection 间接 | 不直接 | required | 不得生产 fallback |
| Workbench Matching Engine 候选 | candidate state / relation readers | candidate matches / scope runs | 可选短 TTL | matching refresh events | 不直接 | 不直接 | required | 不得生产 fallback |
| Turnover Ledger | turnover relations、extras、bank tags | `read_model.turnover_ledger_rows` | 可选短 TTL | `turnover_relation_changed` | 不直接 | export 可用 | required | extra fallback 风险 |
| Batch Accounting | relation metadata / pair relation impact | 读取 Workbench payload | 不应直接依赖 | `batch_accounting_relation_changed` | 不直接 | 不直接 | required | 不得生产 fallback |
| Bankdetail | bank transactions、categories、auto rules | bank detail / no OA / balance rows | 可选短 TTL | category/bank dirty scopes | 不直接 | import files via Imports | required | 不得生产 fallback |
| Invoices | invoices、usage、collections、attachments | pending/input/output rows | 可选短 TTL | invoice dirty scopes | OA attachments read | attachment cache | required | 不得生产 fallback |
| Imports | import batches/files/jobs | import status projections | wakeup 可选 | import job outbox | OA import input | primary file storage | required | 不得生产 fallback |
| Tax / Cost / ETC | tax/cost/etc facts | cost/tax/etc rows | 热点短 TTL | read model refresh events | 可能读 OA projection | ETC/import files | required | 不得生产 fallback |
| Search / Pending Query | 不直接写 facts | `read_model.search_index_rows`、pending rows | 可选短 TTL | search/pending refresh | 间接 | 不直接 | required | 不得生产 fallback |

外部服务模块化判断：

- PostgreSQL、Redis、RabbitMQ、OA Mongo、MinIO/S3、auth/session 必须通过 platform port/adapter 或稳定 service 边界访问。
- RabbitMQ 只能作为 outbox envelope transport，不能替代 PostgreSQL facts 或 dirty scope。
- Redis key 必须包含 generation/source version/schema/query scope，不能作为事实源。
- OA Mongo 当前只读，不能让重构后的生产路径写入 OA Mongo。
- local state / legacy snapshot / pickle 只能保留在非生产 legacy、migration、test 明确路径，不能进入新模块生产路径。

## Runtime Sequence Candidates

### 高频读链路

候选路径：

- `GET /api/workbench` combined initial
- `GET /api/workbench/groups`
- `GET /api/workbench/group-rows`
- `GET /api/bank-details/transactions`
- `GET /api/turnover-ledger`
- `GET /api/batch-accounting`
- `GET /api/search`
- `GET /api/tax-offset`
- `GET /api/cost-statistics/explorer`

优化检查：

- 是否优先读取 PostgreSQL Read Model。
- Redis miss 是否回 PostgreSQL Read Model，而不是同步扫描 facts。
- stale/miss 是否 enqueue durable refresh，并返回 `refreshing`/`stale` 语义。
- 分页、筛选、排序是否在 SQL/index 层完成。

### 写请求 transaction / outbox / dirty scope 链路

候选路径：

- Workbench pair relation confirm/cancel。
- Workbench exception apply/revert。
- Turnover relation confirm/withdraw。
- Batch Accounting submit/withdraw。
- Bankdetail category confirmation。
- Imports confirm。
- Invoice status / usage / collection write。

硬约束：

```text
HTTP handler
  -> module usecase
  -> PostgreSQL transaction
      -> facts
      -> audit
      -> dirty scope / source version
      -> outbox event
  -> commit
  -> response with freshness hint
```

### Worker refresh 链路

候选路径：

- `RuntimeQueueRepository.enqueue_read_model_refresh`
- `job.outbox_events`
- `job.read_model_dirty_scopes`
- Python worker claim。
- module read model builder。
- active generation / source_versions 发布。
- dirty scope complete。

风险：

- 旧 source version 不能覆盖新 active generation。
- building generation 不能进入用户读路径。
- worker 重试必须按 `(scope_type, scope_key, source_version)` 幂等。

### SSE / App Health 链路

候选路径：

- `/api/app-health`
- `/api/app-health/stream`
- `/api/workbench/refresh-status`

风险：

- SSE 不能在请求线程里执行昂贵计算。
- App Health 聚合 outbox backlog、worker heartbeat、read model stale scope 时必须有上限和超时。

### 同步全量重算 / fallback 候选

需要 Micro-JIT 优先审计：

- `state_store.py` / `postgres_state_store.py` / `runtime_bootstrap.py` 中 full snapshot。
- `TurnoverLedgerService.list_ledger/list_grouped_ledger` 中 `rebuild_from_bank_rows`。
- pending invoice / search / cost / tax 在 read model miss/stale 时是否同步扫描。
- `server.py` 中 legacy helper 和 best-effort fallback。

## Risk Register

| 风险 | 严重度 | 证据 | 建议 |
| --- | --- | --- | --- |
| `server.py` 超大且跨模块 | 高 | 约 1MB，所有 API handler 与服务装配混杂 | 后续按模块把 handler 薄化，先抽 usecase 边界和 route ownership |
| `read_models.py` 跨模块 | 高 | 约 363KB，包含多个 read model loader | 拆成 platform helper + module repository |
| legacy full snapshot / local state | 高 | `state_store.py`、`postgres_state_store.py`、`runtime_bootstrap.py`、文档已限制生产路径 | PF-P002 优先锁定 Platform/Ops runtime boundary |
| Shared Domain 被遗漏或反向依赖业务模块 | 高 | `domain/models.py`、`domain/enums.py` 是跨模块值对象 | PF-P002 必须明确 Shared Domain 依赖方向和允许内容 |
| Auth 入口被模块绕过 | 高 | `app/auth.py` 是鉴权上下文边界 | PF-P002 必须把 auth/session 纳入 Platform / Auth |
| Migration runtime 被当作普通 SQL 文件遗漏 | 高 | `postgres/migrate.py` 是 migration 执行器 | PF-P002 必须加入 DB migration runtime gate |
| 巨型测试套件未纳入 Merge Gate | 高 | `test_workbench_v2_api.py`、`test_etc_backend.py`、`test_workbench_sql_runtime.py` 等 | 每个 Micro-JIT 必须声明对应测试热点和可运行验证入口 |
| Backfill 脚本未随模块重构验证 | 中高 | `app/bank_account_balance_backfill.py`、`app/bank_detail_backfill.py` | Bankdetail/Read Model 重构必须补回填 smoke checklist |
| Turnover 读路径同步 rebuild | 高 | `TurnoverLedgerService` 存在 `rebuild_from_bank_rows` 调用链 | Turnover Micro-JIT 中确认生产路径并移出请求线程 |
| Batch 读取 Workbench payload 后写 relation | 高 | `BatchAccountingService` 依赖 Workbench loader 和 relation service | 在 Workbench read model 边界后推进 Batch |
| Workbench Matching Engine 边界未稳定 | 中高 | 算法纯度较高，但 orchestrator 写 candidate state 和 invalidation | 暂不升格顶层模块，先内部子域拆 ports |
| Redis/RabbitMQ 直接散落调用 | 中高 | `runtime_redis.py`、`rabbitmq_runtime.py`、runtime docs | 只允许 platform adapter，业务模块依赖接口 |
| OA Mongo adapter 体量大 | 中 | `mongo_oa_adapter.py` 约 142KB | 保持只读 port，禁止新生产写入 |
| orphan / legacy API | 中 | `/projects`、`/ledgers`、`/reminders`、`/reconciliation/cases`、`/matching/*` | 下一轮 Platform/Ops inventory 或 legacy module review 归属 |
| 大文件拆分破坏行为 | 中 | 多个 service >20KB，测试覆盖分散 | 每个 Micro-JIT 先写 characterization tests，再拆分 |

## Recommended Micro-JIT Order

### PF-P002 建议：Platform / Ops / Runtime Boundary Deep Dive

理由：

- 它是所有模块的共同前置条件。
- 能先锁住 Shared Domain、App Entry、Auth、PostgreSQL migration runtime、transaction、outbox、dirty scope、Redis、RabbitMQ、OA Mongo、MinIO/S3、backfill jobs 和 legacy snapshot 边界。
- 可以先消除“后续模块继续直接依赖外部服务或 full snapshot”的风险。
- 不需要改业务口径，适合作为第一个 Micro-JIT 深挖。

建议 PF-P002 只生成并审查 prompt，不直接执行代码修改。PF-P002 应读取本文件，并聚焦：

- Platform/Ops 文件归属确认。
- Shared Domain、App Entry、Auth、Migration Runtime 和 Backfill Jobs 依赖方向确认。
- DB connection、transaction helper、repository core、outbox/dirty scope 的统一写边界确认。
- Settings / Access Control 与 auth context 的关系确认。
- OA Identity / Role / Projection 的事实来源和依赖方向确认。
- 外部依赖 port/adapter 清单。
- Redis/RabbitMQ 直接依赖点审计，并输出“允许的 platform adapter 调用”和“禁止的业务层直接调用”清单。
- 生产路径禁止 legacy snapshot/local state/pickle 的代码事实审计。
- `state_store.py`、`postgres_state_store.py`、`runtime_bootstrap.py` 和 state diff 相关文件的 production request/worker path 审计，明确 legacy snapshot/local state/pickle 是否仍可能进入生产路径；shadow/dual state store 模块已删除。
- `app/auth.py` 到 handler/usecase 的 auth context 传导链审计，明确统一身份上下文接口和测试门禁。
- Ops tools、backfill scripts、observability/audit/performance metrics 的平台边界审计。
- runtime queue / outbox / dirty scope 调用链。
- App Health / SSE / worker heartbeat 调用链。
- 产出 `platform-runtime-boundary-audit.md`，作为后续业务模块 Micro-JIT 的底座事实源。
- 后续可执行重构的测试入口和验收标准。

### PF-P003 建议：Workbench Query / Read Model

理由：

- Workbench 是高频核心读路径。
- query/read-model 是写操作和 matching 的验收基线。
- 先做只读链路风险较低，能固定 `fresh/stale/refreshing` 语义。

### PF-P004 建议：Turnover Ledger

理由：

- 已确认是独立模块且曾遗漏。
- API、service、tests 边界较明确。
- 需要尽早处理同步 rebuild / extra fallback 风险。

### PF-P005 建议：Batch Accounting

理由：

- 独立写模块，但强依赖 Workbench payload。
- 在 Workbench query/read-model 边界明确后推进更稳。

### PF-P006 建议：Workbench Matching Engine 子域

理由：

- 算法核心可能独立，但当前编排层仍与 Workbench read model 和 candidate state 耦合。
- 需要先通过内部子域 ports 和 characterization tests 固定行为，再决定是否升格。

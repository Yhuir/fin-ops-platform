# Canonical Facts 边界合同

本文记录业务唯一真相的模块化边界。这里的 canonical facts 指 PostgreSQL 中代表业务事实本体的 `app.*` 表，不包括派生 read model、Redis cache、RabbitMQ message、frontend domain event、local pickle、full snapshot、`state:*` JSON 或 Mongo app snapshot。

## 目标

- 每类业务事实只有一个业务 owner。
- 写入必须经过 owner 的 command service、application service、facade、UoW、repository port 或明确 adapter。
- 非 owner 只能通过公开 read port/query service 读取；直接 SQL 读取必须在 owner 模块 `boundary-io.md` 登记。
- 写入后必须明确输出 domain event、dirty scope、affected scopes/months、operation barrier target 或说明不适用。
- 旧生产 source-of-truth 路径必须删除。migration、audit、rollback 工具如果暂时保留，必须隔离在生产 API/worker 主链路之外；保留状态不算 closure。

不要把本文理解成一个新的运行时代码模块。`canonical-facts` 是治理边界和 ownership matrix，不是 `UnifiedFactSource` service。业务事实仍归属现有业务模块；`read-models` 继续只管理派生投影、freshness、refresh 和 operation barrier。

## 事实分层

| 层 | 示例 | 事实 owner | 规则 |
| --- | --- | --- | --- |
| 外部事实 | OA Mongo、Excel/PDF/ZIP、银行导出文件 | 外部系统或导入文件 | app 只读接入或导入，不写外部原始库。 |
| Canonical facts | `app.invoices`、`app.bank_transactions`、`app.workbench_pair_relations` | 现有业务模块 | 业务唯一真相，写入必须经过 owner 边界。 |
| Runtime/audit facts | `job.outbox_events`、`job.read_model_dirty_scopes`、`job.background_jobs`、`audit.events`、`audit.external_control_evidence*` | runtime-workers / read-models / permissions-and-audit | 描述任务、刷新、审计和外部 complete-snapshot 对照证据，不替代业务事实；外部 manifest 不允许由 App canonical rows 反向生成后自证。 |
| Read models | `read_model.*` 页面投影 | read-models + 各 query/projection owner | 派生投影，只能从 canonical facts 或上游 fresh read model 生成。 |
| Cache / transport / UI hints | Redis、RabbitMQ、frontend event | runtime/UI | 只做缓存、唤醒、传输或刷新提示。 |

## 全局规则

1. 一个 canonical fact family 只允许一个 owner 模块。
2. Shared repository 可以知道 SQL 表结构，但不是业务 owner。
3. Owner 模块负责业务状态机、权限前置、写入幂等、审计、版本冲突和下游影响。
4. 其它模块需要写入时，必须调用 owner 的 command service、application service、facade、UoW 或明确 adapter。
5. 其它模块需要读取时，优先使用 owner 暴露的 read facade、query service 或 repository port；直接 SQL 读取必须写入对应模块 `boundary-io.md` 的允许路径。
6. 生产 API/worker 主路径不得把 legacy full snapshot、local pickle、`state:*` JSON、Mongo app snapshot 或 GridFS fallback 当作业务事实源。
7. `read_model.*`、Redis cache、RabbitMQ message 和前端 domain event 不得反向成为业务事实源。
8. 同事务 writer 可以写 dirty scope/outbox，但必须承担与 07 read model closure 等价的 scope contract。本文不重新设计 read model runtime。
9. repair、migration、audit、rollback 工具可以读取或修复 facts，但必须有 dry-run、审计、回滚策略和明确 owner，且不得成为生产主链路。

## Ownership Matrix

| Canonical fact family | PostgreSQL facts | Owner module | 允许写入口 | 允许读入口 | 下游输出 | 禁止路径 |
| --- | --- | --- | --- | --- | --- | --- |
| 导入批次和文件 | `app.import_batches`、`app.import_batch_rows`、`app.import_files`、`app.file_objects` | `imports-bank-transactions`、`imports-invoices`、`imports-etc-invoices` | import preview/confirm/job、PostgreSQL object storage write path | import fact repository、导入 API | import job、affected months、read model dirty/outbox | production bootstrap 读取 full snapshot；临时 SQL 直接写正式导入事实；恢复 legacy GridFS migration worker。 |
| 统一发票池 | `app.invoices` | `imports-invoices` / canonical invoice pool | `ImportNormalizationService`、受控 OA 附件票 promotion、受控 ETC existing-link | invoice query/context ports、业务 owner API | workbench、pending invoice、invoice lifecycle、tax、cost、search refresh | ETC metadata 或 OA cache 绕过发票池 owner 创建第二发票池。 |
| 银行流水 | `app.bank_transactions` | `imports-bank-transactions` + `bank-details` | 银行导入确认、import job、受控分类上下文更新 | bank transaction repository/query ports | bank detail、bank-flow、turnover、no-OA canonical query；Workbench matching/generation | 页面从 snapshot 加载全量流水后自行改写状态。 |
| 银行分类和标签 | `app.bank_transaction_categories`、`app.bank_transaction_category_events`、`app.bank_transaction_category_confirmations` | `bank-details` | bank detail category/rule/confirmation services | bank detail read/query ports、tag read facade | bank detail、bank-flow、turnover、no-OA canonical query；Workbench matching/generation | turnover/no-OA/流水规则批量处理直接写银行分类表。 |
| Workbench 关系事实 | `app.workbench_pair_relations`、`app.workbench_pair_relation_history` | `workbench-relations` | `WorkbenchRelationCommandService`、workbench relation UoW、明确 migration/repair adapter | `WorkbenchRelationReadFacade`、relation repository port | workbench_relation、workbench、bank_flow_rule_batch、pending invoice、invoice usage、OA pending、tax、cost、search refresh | 调用方直接改关系表或自行拼 confirmed relation 状态。 |
| Workbench 操作事实 | `app.workbench_row_overrides`、`app.workbench_exception_cases`、`app.workbench_exception_case_events`、`app.matching_runs`、`app.matching_results`、`app.workbench_idempotency_records` | `reconciliation-workbench` | workbench command/facade services、matching worker | workbench query/facade ports | workbench active generation、workbench_relation、search/cost/tax as applicable | 绕过 active generation 边界把 building/failed 投影当页面事实。 |
| 流水规则批量处理 / Bank Transaction Paired Policy | 正式状态与历史：`app.bank_flow_rule_batches`、`app.bank_flow_rule_batch_events`；规则：`app_settings.bank_flow_rule_batch_tag_rules`；live candidate 输入：银行/分类事实和 `app.workbench_pair_relations` active rows | `bank-flow-rule-batches` | `BankFlowRuleBatchApplicationService`、Bank Transaction Paired Policy rule writer、relation command、`save_bank_flow_rule_batch_mutation(...)` caller-owned UoW/delta writer | `BankFlowRuleBatchCanonicalQueryRepository` + shared live builder、policy payload | 页面在同一 repeatable-read snapshot 实时推导未提交 candidate，并读取 submitted/withdrawn/history；提交事务使用同一内核复核 identity/member/amount/occupancy；relation/history 与 batch/events 在一个 caller-owned PostgreSQL transaction 原子提交；跨月内部转账由最早成员月份唯一拥有；relation 写入按 owner 合同影响关联台 | persisted draft 作为 expected set、draft event/owner/producer/worker/replay、`read_model.bank_flow_rule_batch_rows` 页面读取、Workbench relation projection、旧 `selected_tag_codes`、规则保存 refresh/enqueue、旧 no-OA fallback、追溯改写 existing relation、shared broad snapshot、嵌套独立写 transaction 或调用方直接改 batch/relation 状态。 |
| 免 OA 批次 | `app.no_oa_bank_batches`、`app.no_oa_bank_batch_events` | `no-oa-bank-batches` legacy owner | `NoOaBankBatchApplicationService`、明确 UoW、受控 legacy repair adapter | no-OA application/query ports | canonical no-OA API、Workbench relation/turnover consumers；无 Search/no-OA projection refresh | shared state-store broad snapshot 写入、调用方直接改 batch 状态、或把旧 `selected_tag_codes` 迁移为新规则事实。 |
| OA 投影和附件缓存 | `app.oa_applications`、`app.oa_application_items`、`app.oa_attachments`、`app.oa_sync_*`、`app.oa_attachment_invoice_cache*`、`app.manual_oa_imports` | `oa-integration` | OA sync worker、manual OA import service、OA attachment repair tools | OA projection adapters/read ports | workbench、pending invoice、OA pending、invoice lifecycle、search refresh | API server 直接读 OA Mongo 或把 OA cache 当正式发票池。 |
| OA 待付款准入/支付状态快照 | `app.oa_pending_payment_admissions`、`app.oa_pending_payment_status_snapshots`、`app.oa_sync_watermarks` 中 `oa_pending_payment_source:<tenant>:<scope>` | `oa-integration` / `oa-pending-payments` | OA sync 的 `commit_authoritative_snapshot` 权威 replace/delete；页面支付写回后的 `record_paid_statuses` 幂等增量 reconcile | OA PG-only projector、freshness source-version provider、Page Audit | 精确月份 `oa_pending_payment` dirty/outbox/read model refresh | 页面/worker直读Mongo/MySQL；外部读取失败仍删除snapshot；MySQL成功后只enqueue但不更新PG snapshot；其它模块直接写这些表。 |
| 税金事实 | `app.tax_certified_import_*`、`app.tax_offset_plans` | `tax-offset` | certified import confirm、tax plan service | tax query/application service | tax_offset、cost_statistics、invoice_lifecycle refresh | 其它模块直接写认证抵扣或计划表。 |
| ETC 事实 | `app.etc_invoices`、`app.etc_import_*`、`app.etc_submission_batches`、`app.etc_business_batches`、`app.etc_reconciliation_*`、`app.etc_batch_invoice_links`、`app.historical_etc_repair_*` | `etc-tickets` / `imports-etc-invoices` | ETC import、business batch service、受控 historical repair/backfill tools | ETC business batch API、ETC services、canonical invoice existing-link ports | workbench、workbench_relation、tax/cost/search as applicable | 把 `app.etc_invoices` 当 canonical invoice pool；绕过 batch/link owner 改 membership；runtime delete/reimport 调用通用 import service 清理 legacy ETC canonical invoice 污染。 |
| 外部往来款 | `app.turnover_relations`、`app.turnover_relation_events`、`app.turnover_ledger_extras` | `turnover-ledger` | turnover write facade/UoW | turnover query service/read ports | turnover_ledger、workbench_relation、workbench、cost、search refresh | legacy fallback facade 进入 production normal write path。 |
| 销项收款生命周期 | `app.output_invoice_collection_*`、`app.output_invoice_receipts`、`app.output_invoice_receipt_events` | `output-invoice-collections` | output invoice collection lifecycle services | output collection application/query services | output_invoice_collection、invoice_lifecycle、workbench_relation refresh | route overlay 伪造 fresh 或直接写生命周期表。 |
| 进项使用 OA 冲销 | `app.input_invoice_usage_oa_reverse_batches` | `input-invoice-usage` | input invoice usage OA reverse service | input invoice usage application/query services | input_invoice_usage、invoice_lifecycle、workbench_relation refresh | OA reverse 工具绕过 owner 状态机。 |
| OA 待付款进行中准入 | `app.oa_pending_payment_admissions` | OA integration | OA source snapshot writer | `PostgresOAWorkflowRepository`、OA pending query repository | Workbench workflow gate、OA 待付款、待找发票、进项使用 | 页面或 relation service 自造进行中 OA、把 admission 当 relation owner。 |
| 历史 OA 待付款关系审计 | `app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims`、`app.oa_pending_payment_bank_relation_events` | 无运行时 owner；migration `0136` 后只读审计 | 仅 migration/受控审计 | 审计查询 | 无 read model refresh | 任何运行时 create/update/cancel/promote/claim、候选排除或 source proof。completed/in-progress OA 关系统一由 `app.workbench_pair_relations` 拥有。 |
| 设置和凭证 | `app.app_settings`、`app.oa_applicant_credentials` | `settings` / `oa-integration` | settings service、credential service | settings/OA integration APIs | affected read model dirty scopes by setting family | `state:full_state` 或旧 snapshot 作为 production 业务事实 fallback。 |

## 输入 I/O

| 输入 | 来源 | Owner 责任 |
| --- | --- | --- |
| Business command | 页面 API、worker、repair 工具 | 校验业务状态、权限、版本、幂等、审计身份。 |
| Imported source data | Excel/PDF/ZIP/OA projection | 去重、normalize、确认前重检、写 canonical facts。 |
| Cross-module write request | 其它业务模块 | 只能进入 owner command/service/UoW，不接收裸表写入。 |
| Runtime repair request | 运维 runbook | dry-run、scope、审计、rollback manifest。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Canonical write result | API/service caller | 返回业务状态、version、affected objects/months/scopes。 |
| Domain event | Derived lifecycle / producer | 事件必须包含足够 scope 信息，不能靠下游猜测全量影响。 |
| Dirty scope/outbox | runtime queue/read models | 通过 owner producer、`ReadModelRefreshGateway` 或同事务等价 writer。 |
| Operation barrier targets | frontend/API response | 高影响写操作必须返回或透出目标 read model/scope；不适用时由模块说明。 |
| Audit record | audit service | 记录 actor、action、scope、before/after 或 repair manifest，不记录 secrets。 |

## 旧生产事实源移除规则

旧代码默认必须删除，不能以 `compat-only` 名义算完成。以下路径不得存在于 production API/worker 主链路：

- `ApplicationStateStore.load()` / `ApplicationStateStore.load_bootstrap_snapshot()` / `PostgresStateStore.load_bootstrap_snapshot()` full snapshot。
- local pickle snapshot。
- `app.app_settings` 中的 `state:*` JSON 业务事实 fallback。
- App Mongo snapshot。
- GridFS 文件内容 fallback。
- OA Mongo direct adapter fallback。
- 直接读写其它 owner canonical facts 的 legacy facade。

删除标准是生产链路不可达，而不是文件名不可见。只要旧代码仍能在生产 app/API/worker 链路中读、写、恢复、bootstrap、refresh 或覆盖同一类业务事实，就仍会污染新链路，不能标记 canonical facts closure。不能通过兼容开关、fallback provider、双写旁路、旧 snapshot 恢复或 read model 反推来规避 owner 边界。

如果 migration、audit、rollback 工具暂时保留，必须满足：

- 不在 production API/worker hot path 被调用。
- 有 owner、caller list、dry-run、审计、rollback/cleanup。
- 有删除条件或明确 non-production tooling 接受标准。
- 在 final report 中标为 deferred/blocker，不能算 canonical facts closure；已隔离并被接受为 non-production tooling 或 owner-runbook adapter 的路径必须有 guard 证明不会进入 production API/worker source-of-truth 链路。

## 当前状态

- 状态：closed。
- 已完成：owner matrix 和分层规则已建立；App Mongo/full snapshot/`app.app_settings state:*` 生产 fallback、旧 shadow/dual/cutover/export/staging/reconcile 工具、Turnover legacy fallback、legacy ETC batch API、`file_object.gridfs_migration` worker 等旧事实源路径已删除或由 static guard 锁定；工具侧直接 `Application` 私有访问已收口到 `tools/runtime_application.py`。
- 未完成：无 final closure blocker；后续仅保留 owner 模块常规维护，以及 retained bank/ETC 运维工具在 runbook 退休后的删除或归并。
- 运维工具边界：`tools/runtime_application.py` 只作为 retained bank/ETC operational tools 的 lightweight public app tool-port adapter；工具文件不得直接访问 `Application._*`、`_state_store` 或 `_initialize_runtime_services`；`tool_runtime_ports()` 不得暴露完整 `state_store`，工具初始化只能通过 `Application.tool_runtime_state_snapshot()` 取得最小 state。
- 已接受边界：`ApplicationStateStore` / local pickle 只作为非生产 fixture/tooling I/O 保留，不是业务事实源；生产 factory 必须使用 PostgreSQL，生产 app/service/tool 路径不得 import local `state_store.py`。

# Canonical Facts 边界合同

本文记录业务唯一真相的模块化边界。这里的 canonical facts 指 PostgreSQL 中代表业务事实本体的 `app.*` 表和少量 runtime/audit 事实，不包括派生 read model、Redis cache、RabbitMQ message 或前端 domain event。

## 目标

- 每类业务事实只有一个业务 owner。
- 写入必须经过 owner 的 command service、application service、repository port 或明确 adapter。
- 非 owner 只能通过公开 read port/query service 读取，不能绕过 owner 直接改表。
- 写入后必须明确输出 domain event、affected scope/job diagnostics、outbox/真实后台任务或说明不适用。

不要把本文理解成一个新的运行时代码模块。`canonical-facts` 是治理边界和 ownership matrix，不是 `UnifiedFactSource` service。业务事实仍归属现有业务模块；legacy `read-models` 只作为下线清单和防回流 guard。

## 事实分层

| 层 | 示例 | 事实 owner | 规则 |
| --- | --- | --- | --- |
| 外部事实 | OA Mongo、Excel、PDF、ZIP、银行导出文件 | 外部系统或导入文件 | app 只读接入或导入，不写外部原始库。 |
| Canonical facts | `app.invoices`、`app.bank_transactions`、`app.workbench_pair_relations` | 现有业务模块 | 业务唯一真相，写入必须经过 owner 边界。 |
| Runtime facts | `job.outbox_events`、`job.background_jobs`、`job.runtime_worker_heartbeats` | runtime-workers | 描述真实后台任务、worker heartbeat 和运行诊断，不替代业务事实。 |
| Legacy read models | `read_model.*` 历史页面投影 | read-models 下线清单 + 各业务 owner guard | 不再作为页面读取目标；只能作为迁移/审计/负向 guard。 |
| Cache / transport / UI hints | Redis、RabbitMQ、frontend domain event | runtime/UI | 只做缓存、唤醒、传输或刷新提示。 |

## 全局规则

1. 一个 canonical fact family 只允许一个 owner 模块。
2. owner 模块负责业务状态机、权限前置、写入幂等、审计、版本冲突和下游影响。
3. 其它模块需要写入时，必须调用 owner 的 command service、application service、UoW 或明确 adapter。
4. 其它模块需要读取时，优先使用 owner 暴露的 read facade、query service 或 repository port；直接 SQL 读取必须写入对应模块 `boundary-io.md` 的允许路径。
5. 生产 API/worker 主路径不得把 legacy full snapshot、local pickle、`state:*` JSON、Mongo app snapshot 或 GridFS fallback 当作业务事实源。
6. `read_model.*`、Redis cache、RabbitMQ message 和前端 domain event 不得反向成为业务事实源。
7. 同事务 writer 可以写 outbox、真实后台任务或 affected scope diagnostics，但不得恢复页面 read-model refresh gateway。
8. repair、migration、audit、rollback 工具可以读取或修复 facts，但必须有 dry-run、审计、回滚策略和明确 owner。

## Ownership Matrix

| Canonical fact family | PostgreSQL facts | Owner module | 允许写入口 | 允许读入口 | 下游输出 | 禁止路径 |
| --- | --- | --- | --- | --- | --- | --- |
| 导入批次和文件 | `app.import_batches`、`app.import_batch_rows`、`app.import_files`、`app.file_objects` | `imports-bank-transactions`、`imports-invoices`、`imports-etc-invoices` | import preview/confirm/job、file object migration | import fact repository、导入 API | import job、affected months/scopes、outbox/真实后台任务 | production bootstrap 读取 full snapshot；临时 SQL 直接写正式导入事实。 |
| 统一发票池 | `app.invoices` | `imports-invoices` / canonical invoice pool | `ImportNormalizationService`、受控 OA 附件票 promotion、受控 ETC existing-link | invoice query/context ports、业务 owner API | workbench、pending invoice、invoice lifecycle、tax、cost；`/api/search` direct read | ETC metadata 或 OA cache 绕过发票池 owner 创建第二发票池。 |
| 银行流水 | `app.bank_transactions` | `imports-bank-transactions` + `bank-details` | 银行导入确认、import job、受控分类上下文更新 | bank transaction repository/query ports | bank_detail、workbench、turnover、no-OA；`/api/search` direct read | 页面从 snapshot 加载全量流水后自行改写状态。 |
| 银行分类和标签 | `app.bank_transaction_categories`、`app.bank_transaction_category_events`、`app.bank_transaction_category_confirmations` | `bank-details` | bank detail category/rule/confirmation services | bank detail direct query/provider | bank details direct reload、turnover/no-OA/workbench affected scopes、`/api/search` direct read | turnover/no-OA 直接写银行分类表。 |
| 关联关系 | `app.workbench_pair_relations`、`app.workbench_pair_relation_history` | `workbench-relations` | `WorkbenchRelationCommandService`、workbench relation UoW、明确 migration/repair adapter | `WorkbenchRelationReadFacade`、relation repository port | workbench_relation、workbench、pending invoice、invoice usage、OA pending、tax、cost；`/api/search` direct read | 调用方直接改关系表或自行拼 confirmed relation 状态。 |
| Workbench 操作事实 | `app.workbench_row_overrides`、`app.workbench_exception_cases`、`app.matching_runs`、`app.matching_results`、`app.workbench_idempotency_records` | `reconciliation-workbench` | workbench command/facade services、matching worker | workbench direct query/facade ports | Workbench direct payload、relation/cost/tax affected scopes as applicable；`/api/search` direct read | 绕过 direct query 边界把旧 projection building/failed 状态当页面事实。 |
| 免 OA 批次 | `app.no_oa_bank_batches`、`app.no_oa_bank_batch_events` | `no-oa-bank-batches` | `NoOaBankBatchApplicationService`、明确 UoW | no-OA application/query ports | no_oa_bank_batch、workbench_relation、turnover_ledger；`/api/search` direct read | shared state-store broad snapshot 写入或调用方直接改 batch 状态。 |
| OA 投影和附件缓存 | `app.oa_applications`、`app.oa_application_items`、`app.oa_attachments`、`app.oa_sync_*`、`app.oa_attachment_invoice_cache*`、`app.manual_oa_imports` | `oa-integration` | OA sync worker、manual OA import service、OA attachment repair tools | OA projection adapters/read ports | workbench、pending invoice、OA pending、invoice lifecycle；`/api/search` direct read | API server 直接读 OA Mongo 或把 OA cache 当正式发票池。 |
| 税金事实 | `app.tax_certified_import_*`、`app.tax_offset_plans` | `tax-offset` | certified import confirm、tax plan service | tax query/application service | tax_offset/cost_statistics direct reload 或 cache warmup、invoice lifecycle facts | 其它模块直接写认证抵扣或计划表。 |
| ETC 事实 | `app.etc_invoices`、`app.etc_import_*`、`app.etc_submission_batches`、`app.etc_business_batches`、`app.etc_reconciliation_*`、`app.etc_batch_invoice_links` | `etc-tickets` / `imports-etc-invoices` | ETC import、business batch service、受控 historical repair/backfill tools | ETC business batch API、ETC services、canonical invoice existing-link ports | workbench、workbench_relation、tax/cost as applicable；`/api/search` direct read | 把 `app.etc_invoices` 当 canonical invoice pool；绕过 batch/link owner 改 membership。 |
| 外部往来款 | `app.turnover_relations`、`app.turnover_relation_events`、`app.turnover_ledger_extras` | `turnover-ledger` | turnover write facade/UoW | turnover query service/read ports | turnover_ledger、workbench_relation、workbench、cost；`/api/search` direct read | legacy fallback facade 进入 production normal write path。 |
| 销项收款生命周期 | `app.output_invoice_collection_*`、`app.output_invoice_receipts`、`app.output_invoice_receipt_events` | `output-invoice-collections` | output invoice collection lifecycle services | output collection application/query services | output collection direct reload、invoice lifecycle facts、relation affected scopes | route overlay 伪造 current 状态或直接写生命周期表。 |
| 进项使用 OA 冲销 | `app.input_invoice_usage_oa_reverse_batches` | `input-invoice-usage` | input invoice usage OA reverse service | input invoice usage application/query services | input usage direct reload、invoice lifecycle facts、relation affected scopes | OA reverse 工具绕过 owner 状态机。 |
| OA 待付款银行关系 | `app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims`、`app.oa_pending_payment_bank_relation_events` | `oa-pending-payments` | OA pending payment relation service | OA pending payment read/query ports | OA pending direct reload、bank detail/turnover/relation affected scopes | 其它模块直接 claim 银行流水关系。 |
| 设置和凭证 | `app.app_settings`、`app.oa_applicant_credentials` | `settings` / `oa-integration` | settings service、credential service | settings/OA integration APIs | affected scopes、cache warmup 或真实后台任务 by setting family | `state:full_state` 或旧 snapshot 作为 production 业务事实 fallback。 |
| Runtime 和审计 | `job.outbox_events`、`job.background_jobs`、`job.runtime_worker_heartbeats`、`audit.events`、`audit.app_health_alerts` | `runtime-workers`、`permissions-and-audit` | queue/background/audit services | App Status、ops tools | worker heartbeat、job diagnostics、SLO、repair evidence | 业务 service 裸 SQL 写 job/audit 表；删除 current-effective failure 来伪装后台任务完成。 |

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
| Outbox / background job | runtime queue/workers | 通过 owner service 或同事务 writer 产生真实后台任务。 |
| Affected scope diagnostics | frontend/API response | 高影响写操作返回业务对象、affected months/scopes 或 job/result 诊断；页面写后直接 refetch，不等待旧操作屏障。 |
| Audit record | audit service | 记录 actor、action、scope、before/after 或 repair manifest，不记录 secrets。 |

## 模块文档要求

拥有 canonical facts 的模块必须在 `docs/modules/<module>/boundary-io.md` 维护：

- 拥有哪些 PostgreSQL canonical facts。
- 允许的写入口和读入口。
- 写后产生哪些 domain events、affected scopes/job diagnostics、outbox/真实后台任务或为什么不适用。
- 禁止哪些直接 SQL、legacy snapshot、read model 反向写入或跨模块绕过路径。
- 旧代码保留条件和删除条件。

## 当前状态和缺口

- 状态：partial。
- 当前边界可信度：medium-high。表级 owner 初表来自 migrations、长期文档和当前 service/repository 命名；后续代码重构时必须逐调用点验证。
- 已完成：页面级 read model manifest/registry 保持空 guard，direct API 与 legacy 下线规则已有测试保护。
- 未完成：canonical fact owner matrix 仍需逐模块落到具体 `boundary-io.md`，shared repository 和 legacy/compat path 仍需按模块小步收口。
- 删除旧路径前必须证明 production API/worker 不再读取 full snapshot、local pickle、`state:*` JSON 或 legacy direct write path。

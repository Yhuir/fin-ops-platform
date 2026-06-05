# 模块化重构计划

## 拆分原则

- 按业务领域拆模块，不按技术层横切成一个大 controllers、一个大 models、一个大 utils。
- 一个 API path 只能归属一个模块。
- 一个模块可以读取共享 facts，但必须声明自己写哪些 facts、产生哪些 event、刷新哪些 read model scope。
- 如果两个动作必须在同一个 PostgreSQL transaction 中提交，它们属于同一个 usecase。
- 如果一个动作只需要通知另一个领域变化，使用 outbox/dirty scope/read model，不直接 import 对方 usecase。
- 模块重构必须有测试；当前模块测试全绿后才能进入下一个模块。
- `PF-P001` 必须扫描全量 API path、service 文件、repository、tests 和文件体量；不得只依赖 `workbench_*` 这类通配符来判断模块边界。
- 单文件超过 20KB 或承载关键事务/事件链路时，必须在模块计划中显式列出，不允许只写“相关文件若干”。

## 模块锁定规则

本文档中的模块清单在 `PF-P001` 完成前是目标候选边界，不是最终代码目录结构。

规则：

- `PF-P001` 必须生成 `architecture-inventory.md`，并把所有文件归属到模块或 platform。
- 有 API path、service、tests 和独立事务/事件链路的领域，优先作为独立模块候选。
- 只有内部算法和查询组合、没有独立 API 或事实 ownership 的领域，优先作为所属模块的子域。
- Workbench Matching Engine 必须在 `PF-P001` 中显式评估：如果输入输出、测试和依赖边界稳定，可以升格为独立模块；否则先作为 Workbench 内部子域。
- Search / Pending Query 是否独立，也必须由 `PF-P001` 根据 API ownership、read model ownership 和测试归属确认。
- 最终模块边界只能由 `architecture-inventory.md` 反向修订本文档，不能在没有文件级扫描前拍定。

`PF-P001` 执行后的当前事实源：

- `architecture-inventory.md` 已成为模块归属和后续 Micro-JIT prompt 的输入事实源。
- Turnover Ledger 和 Batch Accounting 确认为独立模块。
- Workbench Matching Engine 暂不升格为顶层模块，先作为 Workbench 内部 `matching/candidates` 子域推进；后续只有在输入输出、facts ownership、read model ownership 和事务边界进一步稳定后，才重新评估是否独立。
- `/projects`、`/ledgers`、`/reminders`、`/reconciliation/cases`、`/matching/*` 当前标记为 Legacy / Review，后续必须在 Platform/Ops 或对应业务模块 Micro-JIT 中确认归属。

`PF-P045` 执行后的增量事实源：

- `main` 在 `PF-P044-MG` 后新增了大量已提交功能；当前重构计划不重做，但后续每个模块 prompt 必须读取 `architecture-inventory.md` 的 `PF-P045 Main Delta Rebaseline`。
- Turnover Ledger 已新增 query service、SQL projection、source versions、read model refresh 和 grouped breakdown contract；后续 Turnover Micro-JIT 不得只围绕旧 `turnover_ledger_service.py`。
- Bankdetail 已扩展到 route facade、application service、category selection、external turnover tag semantics 和 No OA Batch read model；后续 Bankdetail Micro-JIT 必须包含 No OA Batch 子域。
- Invoices 已扩展到 Pending Invoice lifecycle、Output Invoice Collections lifecycle、Input Invoice Usage OA reverse、OA Pending Payments read model；后续 Invoices Micro-JIT 必须先分子域做 discovery，不得一次性改所有 invoice service。
- Tax / Cost / ETC 已新增 cost statistics runtime、ETC business batch application service、tax offset plan/query/runtime；后续 Micro-JIT 必须覆盖 runtime refresh 和 SQL projection。
- Platform / Runtime 已新增 runtime worker registry、deploy worker env examples 和 RabbitMQ/staging preflight 强化；后续 worker 相关改动必须同步 registry、deploy env、tests 和 App Health 观测。
- 当前没有证据需要推翻 Python-first 计划或创建新语言后端。

`PF-P189` 执行后的 Dev 集成分支与 main delta 事实源：

- 后续重构不再直接合入 `main`；`dev` 是 Python-first 后端重构的长期集成分支。
- `dev` 已从当前最新 `origin/main` 创建，并推送为 `origin/dev`。
- 后续重构功能分支必须从最新 `dev` 创建，MG 合入 `dev` 并在 `dev` 上复验；`main` 只在用户明确要求发布或整合重构成果时才接收 `dev`。
- `PF-P188-MG` 后进入 `main` 的新增后端事实主要集中在 Workbench object identity/read model、Invoice lifecycle/runtime status、Cost statistics readiness、Pending invoice lifecycle、Runtime/Ops deploy control、Workbench relation distribution 和少量 Turnover Ledger/Workbench relation 修正。
- `main` 后续继续承载产品功能和线上修复；每次继续重构前必须确认 `dev` 是否落后 `main`。如果落后，先执行 `main -> dev` 同步或 Main Delta Rebaseline，再生成下一条模块 prompt。

PF-P189 后的模块计划调整：

- Workbench 下一轮 Micro-JIT 必须纳入 object identity arbitration、relation distribution read model、all-scope identity arbitration、rehydrate dirty scope completion 和 deploy/ops helper 对 read model 的影响。
- Invoices 下一轮 Micro-JIT 必须纳入 invoice lifecycle read facade/read model/sql projection、OA pending payments、output/input invoice collection source versions 和 App Status readiness。
- Tax / Cost / ETC 下一轮 Micro-JIT 必须纳入 cost statistics all-scope readiness、runtime refresh、dashboard readiness 和 migration `0057_app_health_dashboard_metrics_indexes.sql`。
- Platform / Ops 下一轮 Micro-JIT 必须纳入 deploy-control contract、release step tracing、read model readiness reporter/backfill、runtime queue dead-letter resolve 和 worker registry/env examples。
- Turnover Ledger 当前模块已达到 PF-P188 的完成目标；PF-P189 后只有局部 API contract/Workbench relation 相关修正需要作为未来跨模块影响输入，不要求重新打开 Turnover Ledger 模块。

后续 prompt 的低耦合硬规则：

- 优先复用已有封装、service、repository、platform helper 和测试工具，不重复造轮子。
- `server.py` / `routes_*` 只做路由、HTTP 映射、依赖组装和调用。
- 不允许机械拆文件；不能把 `server.py` 函数原样搬到 service 就算完成。
- service 不依赖整个 `Application` 对象，只接收明确依赖。
- service 不直接读 HTTP cookie/header，不 import `app.auth`。
- worker runner 不知道 HTTP response，不构造页面 payload。
- repository 可以知道 SQL 表结构；业务 service 不散落 SQL。
- 业务写操作继续遵守 facts、audit、dirty scope、outbox 同事务底线。

## Platform / Infrastructure

`platform` 不是业务模块，是所有模块共享的边界集合。

职责：

- `auth`：OA token、cookie、userinfo、权限上下文。
- `db`：PostgreSQL connection、transaction、repository helper。
- `queue`：PostgreSQL durable queue、outbox、RabbitMQ transport。
- `cache`：Redis cache、wakeup、lock、版本化 key。
- `storage`：MinIO/S3 文件对象。
- `observability`：trace id、structured log、metrics、App Health。
- `runtime`：worker bootstrap、runtime dependency health。

验收：

- 业务模块不得直接依赖 Redis/RabbitMQ/driver/OA raw client。
- 所有 platform port 有 fake 或 mock。
- 真实 adapter 有集成测试或明确跳过条件。

## Workbench

范围：

- `/api/workbench/*`
- 工作台 summary、groups、group rows、details。
- pair relation confirm/cancel。
- exception preview/apply/revert。
- reconciliation decision。
- SSE refresh status。

当前相关代码：

- `app/routes_workbench.py`
- `services/workbench_query_service.py`
- `services/workbench_read_model_service.py`
- `services/workbench_read_model_refresh.py`
- `services/workbench_pair_relation_service.py`
- `services/workbench_action_service.py`
- `services/workbench_exception_*`
- `services/workbench_sql_projection.py`
- `services/workbench_reconciliation_*`

必须显式盘点的大文件：

- `services/workbench_candidate_grouping.py`
- `services/workbench_sql_projection.py`
- `services/workbench_query_service.py`
- `services/workbench_free_matching_engine.py`
- `services/workbench_matching_rules.py`
- `services/live_workbench_service.py`
- `services/workbench_exception_case_service.py`
- `services/workbench_special_pair_rule_service.py`
- `services/workbench_matching_orchestrator.py`
- `services/workbench_exception_application_service.py`
- `services/workbench_pair_relation_service.py`
- `services/workbench_special_rule_detectors.py`
- `services/workbench_exception_projection.py`
- `services/workbench_candidate_match_service.py`

生产级拆分策略：

- Workbench 先保持一个顶层业务模块，因为 summary、groups、group rows、pair relation、exception、reconciliation 共享 read model generation、dirty scope、source version 和写后读语义。
- Workbench 内部必须继续拆成子域，不允许形成单个“超级模块”：
  - `query/read-model`：`workbench_query_service.py`、`workbench_sql_projection.py`、`workbench_read_model_service.py`、`workbench_read_model_refresh.py`。
  - `matching/candidates`：`workbench_candidate_grouping.py`、`workbench_free_matching_engine.py`、`workbench_matching_rules.py`、`workbench_matching_orchestrator.py`、`workbench_candidate_match_service.py`、`workbench_amount_check_service.py`。
  - `pair-relations/actions`：`workbench_pair_relation_service.py`、`workbench_action_service.py`、`workbench_override_service.py`、`workbench_matching_dirty_scope_service.py`。
  - `exceptions`：`workbench_exception_*`。
  - `special/reconciliation`：`workbench_special_*`、`workbench_reconciliation_*`。
  - `shared-normalization`：`workbench_text_normalization.py`。
- 是否把 Workbench 子域提升为独立顶层模块，必须等 `PF-P001` 产出真实调用链和事务边界后再决定。没有代码事实前，不拆成多个顶层模块，避免打断同一 read model 的一致性边界。

重构顺序：

1. 只读 summary/groups：先固化 response contract 和 read model freshness。
2. group rows/detail：固化分页、筛选、搜索和 row identity。
3. pair relation write：固化 transaction、audit、dirty scope、outbox。
4. exception/reconciliation writes：固化写后读、幂等和回滚。
5. 性能评估：只在 Python、SQL、read model、Redis/RabbitMQ 和 worker 边界内优化。

## Workbench Matching Engine（候选独立模块）

范围候选：

- 工作台候选分组。
- 自由匹配引擎。
- 匹配规则。
- 匹配编排。
- 候选匹配服务。
- 金额一致性检查。

当前相关代码：

- `services/workbench_candidate_grouping.py`
- `services/workbench_free_matching_engine.py`
- `services/workbench_matching_rules.py`
- `services/workbench_matching_orchestrator.py`
- `services/workbench_candidate_match_service.py`
- `services/workbench_amount_check_service.py`

锁定条件：

- 如果它的输入可以稳定定义为 normalized rows、facts 或 read model snapshot，输出可以稳定定义为 candidate groups、match suggestions 或 validation result，并且不直接拥有 Workbench active generation 发布权，则可以作为独立模块推进。
- 如果它仍与 Workbench read model generation、pair relation 写操作或 exception/reconciliation 写操作共享不可拆事务，则先作为 Workbench 内部子域推进。
- `PF-P001` 必须输出函数级调用链和测试覆盖事实后，才能决定它是否升格为独立顶层模块。

## Turnover Ledger

范围：

- `/api/turnover-ledger`
- `/api/turnover-ledger/export-preview`
- `/api/turnover-ledger/export`
- `/api/turnover-ledger/bank-row-tags/batch`
- `/api/turnover-ledger/relations/*`

职责：

- 流水台账列表、分组视图、relation detail。
- turnover relation confirm/withdraw。
- 台账补充信息 extra 的读取和更新。
- 银行流水标签批量更新。
- 台账导出预览和导出。
- 台账 read model 的 source version、stale reason 和刷新失效边界。

当前相关代码：

- `app/routes_turnover_ledger.py`
- `app/server.py` 中 `_handle_api_turnover_ledger*`、`_turnover_ledger_source_versions`、`_turnover_ledger_stale_reasons`、`_persist_turnover_ledger_extras_best_effort`
- `services/turnover_ledger_service.py`
- `services/turnover_relation_service.py`
- `services/turnover_ledger_extra_service.py`
- `services/turnover_ledger_export_service.py`
- `services/bank_transaction_category_service.py` 中 `turnover_ledger` 类目写入影响
- `services/derived_data_lifecycle_service.py` 中 `turnover_relation_changed`

测试事实源：

- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_service.py`
- `tests/test_turnover_relation_service.py`
- `tests/test_turnover_ledger_export_service.py`
- `tests/test_workbench_turnover_grouping.py`

重点：

- Turnover Ledger 是独立业务模块，不归入 Workbench 或 Bankdetail。
- 它与 Workbench 的关系通过 turnover relation facts、source version 和 read model 投影协作。
- confirm/withdraw 必须保持事务、audit、dirty scope、derived lifecycle event 的一致性。
- 当前仍存在 `legacy_turnover_ledger_extras_fallback_persist` 这类 legacy fallback 线索，`PF-P001` 必须明确是否仍在生产路径触发，并制定移除顺序。

`PF-P046` 后的模块切片建议：

1. Characterization tests：锁定 SQL read model freshness、grouped breakdown、legacy fallback、relation write side effects、extra persist、bank-row-tags batch、export payload 和 Workbench/Bankdetail influence。
2. Query / route boundary：在测试保护下薄化 `server.py` 和 `routes_turnover_ledger.py`，保留 HTTP mapping 和 grouped compatibility，不移动业务规则到新大泥球。
3. Write orchestration boundary：设计 Turnover write service/UoW，只接收明确依赖，不接收 `Application` 或完整 state store；目标是把 relation facts、audit、dirty scope/outbox/source_version 放入明确事务边界。
4. Repository boundary：将 `postgres_repositories/workbench.py` 中 Turnover relation/extras 持久化从 Workbench 命名耦合中解出，或至少先加 Turnover repository port。
5. Runtime worker boundary：保持 `TurnoverLedgerReadModelRefreshService` 不知道 HTTP response；worker 只处理 event -> projection -> dirty scope completion。

当前不做：

- 不直接移除 legacy fallback。
- 不直接改事务模型。
- 不直接重写 export 或 grouped payload。
- 不把 `/api/turnover-ledger/bank-row-tags/batch` 机械归入 Bankdetail；它是 Turnover API + Bankdetail facts influence，需要测试后设计 port。

## Batch Accounting

范围：

- `/api/batch-accounting`
- `/api/batch-accounting/submit`
- `/api/batch-accounting/{relation_id}/withdraw`

职责：

- 批量记账待提交/已提交列表。
- 批量记账 submit/withdraw。
- 批量记账 relation、note、special metadata 和 case id collision 修复。
- 触发 `batch_accounting_relation_changed`，影响 Workbench 投影和银行流水标签/关联状态。

当前相关代码：

- `app/server.py` 中 `_handle_api_batch_accounting*`、`_batch_accounting_service`、`_repair_batch_accounting_relation_case_ids`
- `services/batch_accounting_service.py`
- `services/postgres_repositories/read_models.py` 中 `load_batch_accounting_workbench_payload`
- `services/workbench_candidate_grouping.py` 中 batch accounting relation 识别
- `services/derived_data_lifecycle_service.py` 中 `batch_accounting_relation_changed`

测试事实源：

- `tests/test_batch_accounting_api.py`
- `tests/test_workbench_v2_api.py` 中 batch accounting 投影相关用例
- `tests/test_workbench_persist_scheduler.py`
- `tests/test_derived_data_lifecycle_service.py`

重点：

- Batch Accounting 是独立业务模块，不归入 Workbench。
- 它可以读取 Workbench/SQL read model payload 作为展示输入，但写入边界属于 batch accounting relation usecase。
- submit/withdraw 必须固化 version conflict、note/reason 校验、audit、dirty scope、outbox/derived lifecycle event。
- `PF-P001` 必须补齐 exact API path、handler、service、read model loader、derived event、Workbench 投影影响链。

## Bankdetail

范围：

- `/api/bank-details/*`
- `/api/no-oa-bank-batches/*`
- 银行流水分页、标签、自动分类、候选投影、账户余额、免 OA 批次。

当前相关代码：

- `services/bank_details_service.py`
- `services/bank_detail_sql_projection.py`
- `services/bank_detail_read_model_refresh.py`
- `services/bank_transaction_*`
- `services/no_oa_bank_batch_service.py`
- `services/bank_account_balance_*`

重点：

- 金额、余额、方向和流水 identity 不能用 float。
- 标签和自动分类写操作只标记相关 read model dirty，不同步重算全量列表。
- 与 Workbench 的关系通过 facts/read model/event 协作。

## Invoices

范围：

- `/api/pending-invoices/*`
- `/api/input-invoice-usage/*`
- `/api/oa-pending-payments/*`
- `/api/output-invoice-collections/*`
- 发票候选、进项使用、销项收款、发票附件缓存。

当前相关代码：

- `services/pending_invoice_service.py`
- `services/input_invoice_usage_service.py`
- `services/oa_pending_payment_*`
- `services/output_invoice_collection_service.py`
- `services/invoice_usage_collection_*`
- `services/oa_attachment_invoice_service.py`
- `services/invoice_identity_service.py`

重点：

- 待找发票 read model miss/stale 只 enqueue refresh，不同步扫描全量事实。
- 发票状态变更必须写 audit、command/outbox 和 dirty scope。
- 与银行流水和 Workbench 通过 relation facts 和 read model 协作。

## Imports

范围：

- `/imports/*`
- 导入文件、预览、确认、撤回、import job、文件对象。

当前相关代码：

- `services/imports.py`
- `services/import_file_service.py`
- `services/import_job_queue.py`
- `services/import_preview_audit.py`
- `services/object_storage.py`
- `app/worker.py`

重点：

- Excel/PDF/OCR/OA 附件解析继续由 Python worker 承担。
- API 只接收请求、写 job、返回任务状态。
- 确认动作必须幂等，写 facts、audit、dirty scope、outbox。

## Tax / Cost / ETC

范围：

- `/api/tax-offset/*`
- `/api/cost-statistics/*`
- `/api/etc/*`
- 税金抵扣、成本统计、ETC 对账、项目成本。

当前相关代码：

- `app/routes_tax.py`
- `services/tax_offset_*`
- `services/cost_statistics_*`
- `services/cost_tax_sql_projection.py`
- `services/etc_*`
- `services/project_costing.py`

重点：

- 优先 SQL read model 和 Redis 短 TTL cache。
- Redis miss 后读 PostgreSQL read model，不同步全量计算。
- 多月/跨项目聚合必须只读取一致的 active read model。

## Search / Pending Query

范围：

- `/api/search*`
- 待找发票查询热路径。
- 跨 OA、银行、发票、项目的统一搜索。

当前相关代码：

- `services/search_service.py`
- `services/search_pending_sql_projection.py`
- `services/search_pending_read_model_refresh.py`

重点：

- 搜索是 read-only 热路径。
- 必须以 SQL read model 和索引为准。
- 重点验证分页稳定性、权限过滤、搜索命中和跳转 payload。

## Ops / Runtime

范围：

- `/health`
- `/api/app-health`
- `/api/app-health/stream`
- background jobs、worker heartbeat、runtime diagnostics。

当前相关代码：

- `services/app_health_service.py`
- `services/app_health_alert_service.py`
- `services/background_job_service.py`
- `services/runtime_*`
- `services/operations_dashboard.py`

重点：

- 运维接口不承载业务规则。
- App Health 必须显示 outbox backlog、RabbitMQ/DLQ、worker lag、read model stale/failed、Redis 状态。
- SSE 需要代理关闭 buffering，并支持断线回退轮询。

## 模块推进模板

每个模块按以下顺序推进：

1. Discovery：列出 API path、service、repository、read model、external dependency。
2. Static Call Chain：使用 CodeGraph 和代码阅读整理函数级调用链。
3. Runtime Sequence：整理请求、事务、outbox、worker、cache、read model 的动态时序。
4. Contract Tests：锁定 Python 当前 API response、错误码、权限和副作用。
5. Boundary Refactor：抽出 usecase/service、port/adapter、repository。
6. Unit Tests：mock 外部服务，覆盖 happy path 和异常边界。
7. Integration Tests：连接 PostgreSQL 或测试容器，覆盖 transaction/read model/outbox。
8. Performance Gate：必要时跑 SQL explain、P95/P99、worker lag 和 cache 命中率。
9. Merge Gate：当前分支验证通过后 merge 到 `dev`，再在 `dev` 重跑验证。
10. Traffic Gate：Python-only 模块重构默认不需要；只有改网关、auth/session、SSE、worker 消费方式或部署拓扑时才单独执行。

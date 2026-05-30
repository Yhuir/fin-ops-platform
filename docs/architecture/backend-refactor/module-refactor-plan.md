# 模块化重构计划

## 拆分原则

- 按业务领域拆模块，不按技术层横切成一个大 controllers、一个大 models、一个大 utils。
- 一个 API path 只能归属一个模块。
- 一个模块可以读取共享 facts，但必须声明自己写哪些 facts、产生哪些 event、刷新哪些 read model scope。
- 如果两个动作必须在同一个 PostgreSQL transaction 中提交，它们属于同一个 usecase。
- 如果一个动作只需要通知另一个领域变化，使用 outbox/dirty scope/read model，不直接 import 对方 usecase。
- 模块重构必须有测试；当前模块测试全绿后才能进入下一个模块。

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

重构顺序：

1. 只读 summary/groups：先固化 response contract 和 read model freshness。
2. group rows/detail：固化分页、筛选、搜索和 row identity。
3. pair relation write：固化 transaction、audit、dirty scope、outbox。
4. exception/reconciliation writes：固化写后读、幂等和回滚。
5. 性能评估：只有 SQL/read model/Python 优化后仍无法达标，才进入 Go Fiber Hot Path Gate。

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
- `/api/output-invoice-collections/*`
- 发票候选、进项使用、销项收款、发票附件缓存。

当前相关代码：

- `services/pending_invoice_service.py`
- `services/input_invoice_usage_service.py`
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
9. Merge Gate：当前分支验证通过后 merge 到 `main`，再在 `main` 重跑验证。
10. Traffic Gate：只有引入 Go accelerator 或网关切流时才单独执行。

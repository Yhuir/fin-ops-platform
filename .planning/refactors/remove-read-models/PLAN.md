# Remove Read Models Implementation Plan

日期：2026-06-26

## 原则

- 删除优先于替换。不建新的 read-layer 框架。
- 逐模块迁移，每次只让一个页面或一个共享依赖从 read model 切到 direct API。
- 每个切换都必须同时处理 API shape、前端状态、测试、文档和旧代码删除条件。
- 性能问题先用 SQL 索引、分页、过滤下推、`EXPLAIN` 和 targeted aggregation 解决；没有证据不引入缓存。

## Phase 0 - 冻结 read model 扩张

目标：

- 文档声明 read model 架构进入下线状态。
- 禁止新增 read model、refresh worker、read model readiness 或 operation barrier target。
- 保留旧文档作为迁移清单。

验收：

- `docs/architecture/direct-api-read-architecture.md` 成为目标架构入口。
- `docs/architecture/module-boundaries/read-model-contracts.md` 和 `docs/modules/read-models/*` 明确只作为 legacy inventory。
- `AGENTS.md` 指向 direct API 目标，未来实现不得继续扩展 read model。

## Phase 1 - App Health 和写后闭环改造

目标：

- App Health 从页面 read model readiness 解耦，只展示 session、DB、后台任务、外部依赖、worker heartbeat、告警和真实队列状态。
- 写 API 不再返回 `operation_barrier_targets` / `freshness_targets`。
- 前端删除 `waitForOperationFreshness(...)` 的强依赖，写成功后直接 refetch 目标页面 GET。

主要文件：

- `backend/src/fin_ops_platform/services/app_status_*`
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
- `backend/src/fin_ops_platform/services/read_model_write_targets.py`
- `web/src/features/operationBarrier/api.ts`
- 各页面 mutation handler

验收：

- 写操作成功后 direct GET 能读到已提交事实。
- App Health 不因不存在 read model readiness 变红。
- 删除或隔离 operation barrier tests，并用 direct refetch tests 替代。

## Phase 2 - 共享关系和生命周期 direct query

目标：

- `workbench_relation` 改成 direct relation query service，直接读取 `app.workbench_pair_relations`、自动决策事实和对象表。
- `invoice_lifecycle` 改成 direct lifecycle query service，避免下游页面依赖 lifecycle read model。
- 若 `read_model.workbench_reconciliation_decisions` 当前承载业务事实，迁移到 `app.*` 或明确 canonical 表；不能继续把 `read_model.*` 当事实源。

优先级原因：

- 这是批量账务、待找发票、OA 待付款、进项使用、销项收款、银行明细、成本和税金的共同上游。

验收：

- 下游页面可通过 direct service 获取同一关系上下文。
- 旧 `workbench_relation.read_model.refresh` 和 `invoice_lifecycle.read_model.refresh` 不再被新写路径投递。

## Phase 3 - 页面 GET direct API 迁移

建议顺序：

1. `bank_account_balance` 和 `bank_details`：直接按账户、日期、标签、关键字分页读取银行流水和余额。
2. `no_oa_bank_batches`：直接读取 batch facts、关联关系和银行标签候选。
3. `batch_accounting`：直接读取关系事实和银行/OA候选。
4. `pending_invoices` 和 `search`：直接 SQL 查询发票、流水、OA projection 和关系上下文；搜索先保持简单 SQL/trigram，不做新搜索投影。
5. `input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`：基于 direct relation/lifecycle query 组装。
6. `tax_offset` 和 `cost_statistics`：补索引和聚合 SQL 后迁移，避免把全量 builder 放入请求线程。
7. `turnover_ledger`：直接读取闭环事实、银行流水、关系事实和项目归因。
8. `workbench`：最后迁移，先保证分页、summary、detail、search 和 candidate 查询都有直接 SQL 方案。

每个模块验收：

- GET API 不读 `read_model.*`。
- GET API 不返回 `read_model_status`、`refresh_enqueued`、`read_model_scope_keys`。
- 页面没有 stale/refreshing read model UI。
- 写后直接 refetch 能看到提交后的事实。
- 相关旧 read model refresh producer 不再被该模块写路径调用。

## Phase 4 - Worker、queue、deploy 清理

目标：

- 从 `runtime_worker_registry.py` 删除页面 read model worker registrations。
- 删除 RabbitMQ read model dispatch event。
- 删除 read model worker env/systemd 模板。
- `DerivedDataLifecycleService` 只保留真实 cache cleanup / background job / external sync 语义，或按模块删除。
- `RuntimeQueueRepository` 删除 read model dirty scope 专用 API。

验收：

- deploy worker manifest 只包含真实后台任务 worker。
- 没有代码投递 `*.read_model.refresh`。
- 生产发布脚本不等待 read model worker readiness。

## Phase 5 - 数据库和工具下线

目标：

- 删除 read model 表和相关 readiness/dirty scope 状态。
- 删除 read model repair、rehydrate、reconcile、SLO smoke 工具。
- 删除 read model architecture guards，替换成 direct API guard。

删除条件：

- 生产日志和 static scan 证明没有 API、worker、tool、script、frontend 或 test 读取 `read_model.*`。
- 至少一次完整 authenticated HTTP gate 通过。
- 高风险页面有 query plan / p95 证据。
- 有 rollback plan：恢复旧 release 不依赖已 drop 的 read_model 表；否则先保留表一段观察期。

## 测试矩阵

1. Business core unit tests：迁移不应改变金额、分类、状态机、权限。若 direct query 重新实现规则，必须补业务核心测试。
2. Service-layer tests：每个 direct query service 必须覆盖 pagination、filter、empty、duplicate、permission scope、repository failure。
3. API contract tests：每个迁移 GET 断言新 response shape 不含 read model freshness 字段，错误码和分页字段稳定。
4. Read model/cache/background job tests：迁移阶段用于证明旧 read model 不再被调用；完成后删除 read model 专用测试，保留真实 background job tests。
5. Frontend interaction tests：覆盖 loading、empty、error、filter/sort/pagination、写后 refetch、权限隐藏/禁用。
6. E2E business-flow tests：至少覆盖导入 -> 页面 direct GET、关系确认/撤回 -> 下游页面 direct GET、设置变化 -> 受影响页面 direct GET。
7. Existing feature regression tests：每个模块保留旧页面 rows、summary、导出、权限和关键业务链路不退化。

## 不做

- 不在本轮文档阶段改代码。
- 不立即 drop 数据库表。
- 不创建新的通用 direct read gateway。
- 不把查询组装塞回 React 前端。

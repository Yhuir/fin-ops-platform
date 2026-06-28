# Remove Read Models Analysis

日期：2026-06-26

## 决策

目标架构改为：所有页面通过 direct API 读取和组装数据，不使用 app 页面级 read model。API 不再依赖 `read_model_status`、freshness gate、dirty scope、operation barrier 或 read model refresh worker 来证明页面可读。

直接含义：

- 页面 GET 请求直接从 PostgreSQL canonical facts、必要的 OA SQL projection、导入事实表和业务 repository 查询。
- 写操作提交 canonical facts 后，页面可以直接重新 GET，或由写 API 返回足够的 updated projection/affected ids。无需等待 read model worker 收敛。
- App Health 不再把 read model readiness 作为页面 green/yellow/red 的事实源。它只报告 session、数据库、真实后台任务、外部依赖、worker heartbeat、告警和队列状态。
- Redis 可以作为可删除的短 TTL response cache，但不能承担 freshness proof。迁移初期优先不用缓存，等 direct API 有真实性能数据后再加。

## 当前影响面

代码和文档显示，read model 不是局部组件，而是横跨后端、前端、测试、部署和运维的运行时架构。

### 后端共享架构

- `backend/src/fin_ops_platform/services/read_model_manifest.py` 登记 14 个 read model：`workbench`、`workbench_relation`、`bank_detail`、`bank_account_balance`、`pending_invoice`、`search`、`invoice_lifecycle`、`input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`cost_statistics`、`tax_offset`、`no_oa_bank_batch`、`turnover_ledger`。
- `app_status_read_model_registry.py` 和 `app_status_domain_registry.py` 把页面状态绑定到 read model readiness 和 read model worker。
- `runtime_worker_registry.py` 登记大量 `*.read_model.refresh` worker/event。
- `DerivedDataLifecycleService` 把业务事件 fan-out 到 `*_read_model` 域。
- `ReadModelQueryGateway`、`ReadModelRefreshGateway`、`ReadModelScopePolicyRegistry`、`OperationFreshnessBarrierService`、`read_model_write_targets.py` 共同组成 freshness/enqueue/barrier 协议。
- `PostgresReadModelRepository` 和多个 `*_read_model_repository.py`、`*_sql_projection.py`、`*_read_model_refresh.py` 是各页面投影实现。

### 前端

页面和 feature API client 消费或展示：

- `readModelStatus` / `read_model_status`
- `read_model_stale_reasons`
- `read_model_scope_keys`
- `refresh_enqueued`
- `operationBarrierTargets`
- `waitForOperationFreshness(...)`

直接受影响页面包括关联台、银行明细、待找发票、进项发票使用、OA 待付款、销项收款、税金抵扣、成本统计、免 OA 批次、批量账务、往来款和 ETC 相关写后同步。

### 数据库与运维

- `read_model.*` schema 保存页面投影、generation、rows、readiness。
- `job.read_model_dirty_scopes` 和 `job.outbox_events` 当前承担读模型刷新状态。
- RabbitMQ dispatcher、systemd worker env、deploy helper、runtime worker manifest、SLO smoke、repair scripts 都包含 read model refresh 事件。
- 监控文档和 App Health 使用 read model readiness 解释页面 busy/blocked。

### 测试

大量测试直接保护 read model 架构，例如：

- `tests/test_read_model_*.py`
- `tests/test_runtime_worker_read_model_refresh_scopes.py`
- `tests/test_operation_freshness_barrier.py`
- 各页面 API/SQL runtime tests 中的 `read_model_status` 断言
- 前端页面测试和 Playwright 对 stale/refreshing/operation barrier 的断言

这些测试不能一次性删除。每迁移一个模块，必须替换成 direct API 合同、SQL 查询、写后重新读取和旧字段消失的回归测试。

## Direct API 目标态

### 读路径

```text
React page
  -> feature API client
  -> route 参数/权限/错误映射
  -> application query service
  -> narrow repository / SQL query
  -> PostgreSQL canonical facts / OA SQL projection / import facts
  -> DTO payload
```

约束：

- route 不拼 SQL，不做业务组装。
- service 可以组装跨表 DTO，但不能依赖 `read_model.*` 或 `job.read_model_dirty_scopes`。
- repository 负责 SQL、分页、排序、过滤、聚合和索引友好的查询。
- API 响应只表达业务数据、分页、summary、权限和错误；不再返回 read model freshness 字段。
- 空结果就是当前事实下的空结果，不需要 `missing` / `refreshing` 防伪空态。

### 写路径

```text
POST/PUT/DELETE
  -> route
  -> command service / UoW
  -> canonical facts + audit
  -> response: status, affected ids/months, version, optional updated DTO
  -> frontend refetch direct GET
```

约束：

- 写成功代表 canonical write 已提交。没有 read model 收敛等待。
- 如果写后页面需要阻塞用户继续操作，阻塞条件来自写事务、业务版本、权限、DB 可用性或真实后台任务，不来自 read model freshness。
- `operationBarrierTargets`、`freshness_targets`、`read_model_scope_keys` 在迁移后删除。

### 后台任务

保留：

- 导入处理
- OA 同步
- 文件对象迁移
- 大文件/OCR/外部系统同步
- 受控数据修复和审计工具

删除或迁移：

- 页面 read model refresh worker
- read model scope policy/gateway
- read model readiness reporter
- read model SLO smoke
- read model repair/runbook
- Redis fresh-gate cache envelope

## 实施难点

1. `workbench_relation` 是多个页面的共享关系上下文。必须先提供 direct relation query service，否则批量账务、待找发票、OA 待付款、发票使用、银行明细标签等页面会失去共同事实口径。
2. `workbench` active generation 当前承担首屏性能和一致性。迁移时需要用可分页、可解释的 SQL query 替代 generation payload，而不是把旧 builder 放回请求线程做全量扫描。
3. 成本统计、税金抵扣和搜索是重查询路径。下线 read model 前必须先补 SQL 索引、分页、聚合和 `EXPLAIN` 验证。
4. App Health 当前把 read model readiness 当页面状态事实。迁移后需要重定义 App Health：它只展示后台任务和依赖状态，不再展示页面数据是否 fresh。
5. 前端大量 non-fresh UI 和 operation overlay 要删除或改成普通 loading/error/refetch 逻辑。
6. 部署 env 和 systemd worker 数量会显著减少。需要有迁移发布顺序，避免生产仍投递旧 event 却没有 consumer。

## 还需要改的地方

除 `.planning/` 和 `/docs` 外，完整实现还必须改：

- `AGENTS.md`：未来 agent 入口规则必须从 read model governance 改成 direct API governance。
- 后端 services/routes/repositories：逐模块移除 read model query/refresh/projection/freshness/barrier 依赖。
- 前端 pages/features：删除 read model status、operation barrier、stale false-empty 防护，改为 direct GET loading/error/empty。
- 测试：删除 read model 架构守卫，新增 direct API contract、repository SQL、写后 refetch 和性能回归测试。
- PostgreSQL migrations：迁移或删除 `read_model.*` 表、`job.read_model_dirty_scopes`、readiness 历史状态和相关索引。
- deploy/systemd/env：删除 read model worker env、RabbitMQ read model event、worker manifest 和 deploy readiness checks。
- scripts/tools：删除或替换 `read_model_slo_smoke`、scope contract repair、rehydrate/reconcile read model 工具。
- monitoring/runbooks：删除 read model freshness SLO 和 repair 流程，改为 direct API latency、DB query plan、background job health。
- CI/nightly：删除 read model smoke gate，新增 direct API authenticated HTTP gate 和 query performance gate。

## Ponytail 约束

不新增 `DirectReadGateway`、`QueryFreshnessGateway`、`PageDataAssemblerFramework` 之类替代抽象。先逐页面把 GET API 改到现有 service/repository 和 SQL 查询；只有多个模块真的重复同一段查询或 DTO 映射时，才抽小函数或窄 service。

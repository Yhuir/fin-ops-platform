# Read Model 模块边界与 I/O

日期：2026-07-27

## 模块化状态

- 状态：运行时 read model 已收敛为关联台 active-generation `workbench`，以及三个共享投影 `workbench_relation`、`search`、`no_oa_bank_batch`。
- 当前边界可信度：high。
- `RUNTIME_WORKER_REGISTRY`、`READ_MODEL_MANIFEST`、App Status registry 和 scope policy registry 必须保持同一集合。
- 除关联台外的页面 read model runtime 已退休。migration `0127` 是纯 no-op 标记，不改写旧 queue/readiness，也不删除回滚表；新版本仅从 registry、dispatcher、App Status 和 worker claim 合同中退出已退休 runtime。
- Workbench matching 仍是独立 canonical matching owner，不属于 read model registry。
- BankFlow 规则批次的异步 owner 是 canonical draft worker，事件为
  `bank_flow_rule_batch.canonical_draft.refresh`；它不是 read model refresh。

## 职责边界

### 负责

- `workbench` 与三个共享 read model 的 manifest、scope、refresh enqueue、worker、freshness/status 与维护 backfill。
- `job.outbox_events`、`job.read_model_dirty_scopes` 的 durable queue/status 合同。
- 防止共享投影缺失、stale 或 refreshing 时被伪装为 fresh。

### 不负责

- 不拥有业务页面 canonical facts。
- 不为直接 canonical 页面提供 projection、worker、scope、readiness 或 refresh API。
- 不把 Redis 或 RabbitMQ 作为 freshness 事实源。
- 不把 Workbench matching、BankFlow canonical draft 或普通 background job 登记为 read model。

## 当前 Manifest

| Read model | Scope | Worker | Query owner | Repository owner |
| --- | --- | --- | --- | --- |
| `workbench` | month shard；`all` 仅冷启动/显式恢复 fan-out | `workbench`、`workbench-secondary` | `WorkbenchQueryFacade` | `PostgresReadModelRepository` active-generation methods |
| `workbench_relation` | `workbench_relation` month / `all` fan-out command | `workbench-relation` | `WorkbenchRelationReadFacade` | `WorkbenchRelationReadModelRepositoryPort` |
| `search` | `search` month / `all` fan-out command | `search` 及并行 search 实例 | Search read API | `SearchReadModelRepositoryPort` |
| `no_oa_bank_batch` | `no_oa_bank_batch` month / `all` fan-out command | `no-oa-bank-batch` | `NoOaBankBatchApplicationService` | `NoOaBankBatchReadModelRepositoryPort` |

三个共享模型的 `all` 只是 maintenance fan-out 命令。关联台页面的 `all` 查询由 active month
generations 组合，不发布 materialized `all` parent；各 producer 必须枚举真实 month shards。
普通业务写不得用 `all` 代替精确影响范围。

## 直接 Canonical 页面

以下页面在请求内读取 canonical PostgreSQL facts，不依赖 read model registry、worker、queue 或 readiness：

- OA 待付款。
- BankFlow 规则批次；异步 canonical draft 只负责 canonical draft facts。
- ETC 管理。
- Turnover ledger。
- 进项发票使用。
- 销项发票收款。
- 成本统计和税金抵扣。

页面 GET 必须保持只读。写命令只提交 owner facts/version/audit，并返回业务 identity 与精确
affected months；不得为隐藏页面 enqueue refresh、返回 operation barrier target，或恢复旧 AppHealth
页面 refresh routes。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Refresh request | Workbench 页面 query owner、三个共享 read owner 或显式 maintenance | 非事务入口经 `ReadModelRefreshGateway` normalize、validate、dedupe；事务内 writer 使用等价 scope contract |
| Scope key | `ReadModelScopePolicyRegistry` | 四种 scope 均只接受 `YYYY-MM` 或 `all`；空值和其它形状 fail fast |
| Canonical source proof | 各 projection producer | 必须包含 own schema version 与实际依赖版本；dirty `source_version` 只作发布 CAS 令牌 |
| Query request | facade/API | payload I/O 前检查 durable dirty/outbox 与 canonical source proof；cache 不能替代 proof |
| Maintenance command | `scripts/backfill-runtime-read-models.py` | `--enqueue-missing` 只向四个 active scope type 写入 `all` fan-out command；显式 BankFlow replay 是独立 canonical domain event，非 read-model refresh，非 dry-run 必须提供操作人 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Dirty scope/outbox | PostgreSQL durable queue | `job.outbox_events` 与 `job.read_model_dirty_scopes` 是唯一状态事实源 |
| Fresh payload | 页面 API/Redis | Redis 只能保存 fresh gate 后 payload；旧版本必须能被当前 proof 拒绝 |
| Readiness/status | App Status / Operations | 只包含当前 manifest 四项；retired event/readiness 只可作为历史清理对象，不能进入当前状态 |
| RabbitMQ envelope | optional transport | 只发布 registry 登记且 `rabbitmq_eligible` 的事件；consumer 仍回 PostgreSQL claim/ack |
| Canonical draft event | BankFlow worker | 不进入 read model manifest、scope policy、readiness 或 RabbitMQ dispatcher |

## 特殊边界

- `workbench_relation` 只分发 eligible shared relation；`turnover_manual_closure` 由 Workbench/Turnover
  直接消费 canonical relation，不进入共享 distribution。
- `workbench` 页面读取 active generation，查询前先做 canonical source proof 与 durable queue freshness gate；
  `all` 组合视图只能使用 fresh active month generations。
- Search 从 canonical Workbench query owner 构建索引；source version 未变化时允许 no-op，变化时使用
  row-level upsert + stale-row delete。
- `no_oa_bank_batch` 保留 legacy 免 OA 消费页投影，查询缺失时 fail closed，不回退本地 snapshot fresh。
- Workbench confirm/withdraw/cancel 等普通 UoW 不产生共享 read-model targets；消费页再次访问时按自身合同收敛。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Manifest / registry | `read_model_manifest.py`、`runtime_worker_registry.py`、`app_status_read_model_registry.py` |
| Scope / gateway | `read_model_scope_policy.py`、`read_model_refresh_gateway.py`、`read_model_scope_contract.py` |
| Freshness / query | `read_model_freshness.py`、`read_model_query_gateway.py` |
| Repository | `postgres_repositories/read_models.py` 及三个共享 narrow repository ports |
| Worker | `runtime_worker.py`、`runtime_worker_handlers.py`、四个 active read-model handlers |
| Maintenance | `scripts/backfill-runtime-read-models.py`、`tools/read_model_slo_smoke.py` |
| Migration | `postgres/migrations/0127_direct_canonical_page_runtime_retirement.sql` |

## 依赖方向

- 允许：read facade/API -> narrow repository port / refresh gateway -> runtime queue repository。
- 禁止：业务 service 直接 SQL 写 dirty scope/outbox。
- 禁止：直接 canonical 页面 import 或调用 retired read-model producer/service。
- 禁止：worker 依赖 `Application`、HTTP auth/cookie/header 或 response 对象。

## 测试与验证

- Manifest/registry/scope：`tests/test_read_model_manifest.py`、`tests/test_runtime_worker_registry.py`、
  `tests/test_read_model_scope_contract.py`。
- Gateway/freshness：`tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_query_gateway.py`。
- Runtime/RabbitMQ：`tests/test_runtime_worker.py`、`tests/test_rabbitmq_runtime.py`。
- 维护入口：`tests/test_runtime_read_model_backfill.py`。
- 页面 direct/canonical 与零 fan-out：
  `tests/test_page_read_model_fact_display_matrix.py`、`tests/test_write_operation_impact_matrix.py`、
  `tests/test_platform_runtime_boundary_guards.py`。

## 维护风险和删除条件

- 新增 read model 必须同时更新 manifest、scope policy、worker registry、App Status registry、env、tests 和本文档。
- 新增事件若不是 read model，必须显式保持在 manifest/scope/readiness 之外。
- 0127 保留旧物理表用于回滚；只有另行审批并验证无读写调用方后，才可设计 drop-table migration。
- 历史实现与生产证据保留在 implementation history/state log，不得重新作为当前 runtime 合同。

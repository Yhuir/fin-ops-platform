# Read Model 模块边界与 I/O

日期：2026-06-29

## 模块化状态

- 状态：PSCIP-L4 closed
- 当前边界可信度：high
- 目标边界：所有当前 App Status read model 通过 manifest、scope policy、refresh gateway、runtime worker、freshness/status gate 和 operation barrier 形成可验证闭环。
- 当前闭环：14 个当前 App Status read model 已完成 Read Model 模块化 PSCIP-L4，`workbench`、`bank_account_balance`、`pending_invoice`、`cost_statistics` 以显式例外语义闭环。
- 当前非阻塞风险：Search 曾有一次生产 grouped-run 高延迟样本，targeted rerun 通过；Workbench groups admin smoke 有一次 probe shape `400`，不是 stale-as-fresh 证据。
- 旧代码删除条件：legacy/local compat path 仍可保留为明确隔离路径；删除前必须证明对应页面 API、worker、测试和生产脚本不再调用该路径。

## 闭环证据

- 最终报告：`.planning/refactors/modular-io-boundaries/analysis/read-model-main-final-closure-report-2026-06-28.md`
- 生产证据：`.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-evidence-2026-06-28.md`
- 远端闭环提交：`c771b894 docs: close read model production evidence`
- 生产 runtime 证据：`/health/ready` ready，scope contract `ok=true`，`violation_count=0`，current uncovered outbox failure count `0`，dirty/outbox/readiness 收敛。
- 生产 SLO：`read_model_slo_smoke --apply --critical-only --target-ms 5000` grouped run 14/15 pass；唯一 Search grouped miss targeted rerun `499.357ms` pass。

## 职责边界

### 负责

- Read model manifest 合同、scope 规范、refresh enqueue、freshness/status 查询和 operation barrier。
- 约束所有 read model 的 Partitioned + Scoped + Incremental Projection 目标态。
- 防止页面读取旧 read model 却伪装 fresh。

### 不负责

- 不拥有具体业务页面的源事实。
- 不直接替代页面 service/repository 的业务逻辑。
- 不用 Redis/RabbitMQ 作为 read model 状态事实源。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Refresh request | 页面 service、writer、worker、API force refresh | 非事务入口必须经 `ReadModelRefreshGateway` normalize/validate/dedupe |
| Scope key | manifest/scope policy | 必须符合注册 scope policy |
| Query freshness request | API/read facade | 必须返回 fresh/stale/refreshing 或等价状态 |
| Write response target envelope | 页面写 API/service | 会影响 read model 的成功写入必须返回或透出 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets` 和 `operation_barrier_targets`；缺少/未知前端 read model status 必须保持非 fresh |
| Projection source versions | Worker/projection/upstream read model | 必须包含 own projection schema version 和依赖 source_versions；行为变更必须 bump version |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Dirty scope/outbox event | PostgreSQL durable queue | `job.outbox_events` 与 `job.read_model_dirty_scopes` 是事实源 |
| Fresh payload | 页面 API/Redis | Redis 只能缓存 fresh gate 后 payload |
| Readiness/status | app status/operation barrier | 页面不能伪装 fresh |
| Source-version proof | Scope rows / API fresh gate | `source_versions_unchanged` 只能在 own schema version 与依赖版本都匹配时跳过重建 |

## 持久化与投影

- Manifest：`backend/src/fin_ops_platform/services/read_model_manifest.py`
- Scope policy：`backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- Refresh gateway：`backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- Query gateway：`backend/src/fin_ops_platform/services/read_model_query_gateway.py`
- Repository：`backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Worker registry：`backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Gateway/manifest | `read_model_query_gateway.py`、`read_model_refresh_gateway.py`、`read_model_manifest.py` |
| Scope/freshness | `read_model_scope_policy.py`、`read_model_scope_contract.py`、`read_model_freshness.py`、`operation_freshness_barrier.py` |
| Write target envelope | `read_model_write_targets.py` 与页面/service 本地 target mapper，当前已覆盖 batch/no-OA/OA pending/pending invoice/turnover、bank-detail、input-invoice-usage OA reverse、output-invoice-collections、tax-offset plan/certified import、workbench relation action、general/file import、ETC import job completion、OA manual import/create/refresh/remove |
| Repository | `postgres_repositories/read_models.py`、`postgres_repositories/read_model_scope_contracts.py` |
| Worker | `runtime_worker_registry.py`、`runtime_worker.py`、`runtime_worker_handlers.py` |
| Frontend | `web/src/features/operationBarrier/api.ts` |
| Scripts | `scripts/check-read-model-scope-contracts.py` |
| Production evidence | `docs/operations/read-model-production-evidence-runbook.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-main-final-closure-report-2026-06-28.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-evidence-2026-06-28.md` |
| Tests | `tests/test_read_model_*.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` |

## 依赖方向

- 允许依赖：runtime queue repository、scope policy registry、app status registry。
- 必须通过：refresh gateway 或同事务等价 scope contract。
- 禁止绕过：业务 service 直接 SQL 写 dirty scope/outbox；页面绕过 freshness gate；RabbitMQ 作为状态事实源。

## 测试与验证

- Architecture guards：`tests/test_read_model_architecture_guards.py`、`tests/test_platform_runtime_boundary_guards.py`。
- Manifest/scope：`tests/test_read_model_manifest.py`、`tests/test_read_model_scope_contract.py`。
- Gateway/freshness：`tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_query_gateway.py`、`tests/test_read_model_freshness.py`。
- Write target envelope：`tests/test_read_model_write_targets.py`，以及 batch/no-OA/OA pending/pending invoice/turnover、bank-detail、input-invoice-usage OA reverse、output-invoice-collections、tax-offset、workbench relation action、general/file import、ETC import job completion、OA manual import/create/refresh/remove 的 API/service/page tests。

## 维护风险和删除条件

- 新增 read model 必须同时更新 manifest、scope policy、registry、tests、docs。
- 删除旧 read path 前必须证明所有页面 API 和 worker 均通过新 freshness/status 边界。
- Projection 行为、索引、跨 scope 分发或上游依赖合同变化时必须 bump projection schema version；禁止只改 SQL/service 逻辑却复用旧 `source_versions`。
- `workbench_relation` 的 `rows` 索引是 scope 内唯一，不是 row 全局唯一；跨月 relation 必须在每个受影响 scope 写入所有成员 row 索引，禁止恢复旧的 `(tenant_id, row_id)` 覆盖模型。
- legacy compat path 删除不是当前 PSCIP-L4 blocker；它必须继续保持生产 fail-closed、不能绕过 fresh gate，也不能新增未登记 dirty/outbox/readiness 写入。
- Search 高行数 refresh latency 仍需在后续生产 evidence sweep 中观察；单次高延迟不是当前 stale-as-fresh 或 readiness blocker。

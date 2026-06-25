# Read Model 模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：所有页面 read model 通过 manifest、scope policy、refresh gateway、runtime worker、freshness/status gate 形成可验证闭环。
- 当前缺口：部分页面仍存在历史 service/read facade 和特殊例外，后续变更必须逐页面核验旧路径是否还被调用。
- 旧代码删除条件：manifest、registry、API、frontend、tests、生产 drain 验证全部证明旧路径不再参与 fresh 读取。

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

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Dirty scope/outbox event | PostgreSQL durable queue | `job.outbox_events` 与 `job.read_model_dirty_scopes` 是事实源 |
| Fresh payload | 页面 API/Redis | Redis 只能缓存 fresh gate 后 payload |
| Readiness/status | app status/operation barrier | 页面不能伪装 fresh |

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
| Write target envelope | `read_model_write_targets.py` 与页面/service 本地 target mapper，当前已覆盖 batch/no-OA/OA pending/pending invoice/turnover、bank-detail、input-invoice-usage OA reverse、output-invoice-collections、tax-offset plan/certified import、workbench relation action、general/file import、OA manual import/create/refresh/remove |
| Repository | `postgres_repositories/read_models.py`、`postgres_repositories/read_model_scope_contracts.py` |
| Worker | `runtime_worker_registry.py`、`runtime_worker.py`、`runtime_worker_handlers.py` |
| Frontend | `web/src/features/operationBarrier/api.ts` |
| Scripts | `scripts/check-read-model-scope-contracts.py` |
| Tests | `tests/test_read_model_*.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` |

## 依赖方向

- 允许依赖：runtime queue repository、scope policy registry、app status registry。
- 必须通过：refresh gateway 或同事务等价 scope contract。
- 禁止绕过：业务 service 直接 SQL 写 dirty scope/outbox；页面绕过 freshness gate；RabbitMQ 作为状态事实源。

## 测试与验证

- Architecture guards：`tests/test_read_model_architecture_guards.py`、`tests/test_platform_runtime_boundary_guards.py`。
- Manifest/scope：`tests/test_read_model_manifest.py`、`tests/test_read_model_scope_contract.py`。
- Gateway/freshness：`tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_query_gateway.py`、`tests/test_read_model_freshness.py`。
- Write target envelope：`tests/test_read_model_write_targets.py`，以及 batch/no-OA/OA pending/pending invoice/turnover、bank-detail、input-invoice-usage OA reverse、output-invoice-collections、tax-offset、workbench relation action、general/file import、OA manual import/create/refresh/remove 的 API/service/page tests。

## 当前缺口和删除条件

- 新增 read model 必须同时更新 manifest、scope policy、registry、tests、docs。
- 删除旧 read path 前必须证明所有页面 API 和 worker 均通过新 freshness/status 边界。
- 剩余未闭合重点是 queued import job completion propagation、生产证据和 legacy compat path 删除/隔离；未完成前不能宣称全页面 PSCIP-L4。

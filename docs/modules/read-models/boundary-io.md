# Read Model 模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：legacy-guard-only
- 当前边界可信度：high
- 目标边界：页面读取走 direct API；本模块只保留旧 read model 的删除清单和负向 guard。
- 当前缺口：继续清理历史文档/fixture 中把 read model 当当前架构的表述；生产 app/services/tools 可执行 refresh/freshness/dirty/readiness surface 已由扫描保护。
- 旧代码删除条件：manifest/registry 为空，API/frontend/tests/生产验证继续证明旧路径不再参与页面读取。

## 职责边界

### 负责

- Legacy read model 空 manifest guard、scope 历史清单、迁移清单和删除条件。
- 记录所有旧 read model 的删除条件和 direct API 替代路径。
- 防止尚未迁移的页面读取旧 read model 却伪装 fresh。

### 不负责

- 不拥有具体业务页面的源事实。
- 不拥有 PostgreSQL canonical facts；事实 owner matrix 由 `docs/architecture/module-boundaries/canonical-facts.md` 和各业务 owner 模块维护。
- 不直接替代页面 service/repository 的业务逻辑。
- 不用 Redis/RabbitMQ 作为 read model 状态事实源。
- 不新增新的页面 read model、readiness、freshness gate 或 refresh worker。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Refresh request | 已删除 | 当前 registry 为空；不得新增 page `.read_model.refresh` |
| Scope key | 历史 scope policy | 仅作为删除/负向 guard；不得作为新页面读取合同 |
| Query freshness request | 已删除页面 fresh gate | 页面 API 不得返回 read-model freshness 作为读取证明 |
| Write response scope envelope | 页面写 API/service | 已迁移写 API 仅返回 `affected_scope_keys` 作为写后影响 scope 诊断；不再返回 legacy target fields；前端不得再等待 operation barrier |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Dirty scope/outbox event | PostgreSQL durable queue | 当前无 active page read-model producer；旧行只作迁移/诊断 |
| Fresh payload | 无 active owner | 页面 direct API payload 不经过 read-model fresh gate |
| Readiness/status | app status | App Status 不投影 page read-model readiness |

## 持久化与投影

- Manifest：`backend/src/fin_ops_platform/services/read_model_manifest.py`，当前只包含空 `READ_MODEL_MANIFEST`
- Scope policy：`backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- Refresh gateway：已删除；`tests/test_read_model_architecture_guards.py` 和 `tests/test_platform_runtime_boundary_guards.py` 防止模块或 import 回流
- Query gateway：已删除；剩余旧查询由模块自管 freshness service 维护
- Repository：`backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Worker registry：`backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Manifest/guards | 空 `read_model_manifest.py`、gateway deletion architecture guards |
| Scope/freshness | `read_model_scope_policy.py`、`read_model_freshness.py` |
| Write affected scopes | `scope_keys.py` 与页面/service 本地 affected-scope mapper，当前已覆盖 batch/no-OA/OA pending/pending invoice/turnover、bank-detail、input-invoice-usage OA reverse、output-invoice-collections、tax-offset plan/certified import、workbench relation action、general/file import、ETC import job completion、OA manual import/create/refresh/remove |
| Repository | `postgres_repositories/read_models.py` |
| Worker | `runtime_worker_registry.py`、`runtime_worker.py`、`runtime_worker_handlers.py` |
| Frontend | 已无 operation barrier API client；页面写后走 direct GET/refetch |
| Scripts | 无 current scope-contract repair script |
| Production evidence | `docs/operations/read-model-production-evidence-runbook.md` |
| Tests | `tests/test_read_model_*.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` |

## 依赖方向

- 允许依赖：runtime queue repository、scope policy registry、app status registry 的负向/空清单。
- 必须通过：direct API/canonical facts；legacy refresh 调用不得写未登记 durable dirty/outbox。
- 禁止绕过：业务 service 直接 SQL 写 dirty scope/outbox；页面依赖 freshness gate 或 operation barrier 作为可读证明；RabbitMQ 作为状态事实源。

## 测试与验证

- Architecture guards：`tests/test_read_model_architecture_guards.py`、`tests/test_platform_runtime_boundary_guards.py`。
- Manifest/scope：`tests/test_read_model_manifest.py` 证明 manifest/App Status registry 为空；`tests/test_runtime_worker_read_model_refresh_scopes.py` 证明旧 refresh scope 不回流。
- Gateway/freshness：`tests/test_read_model_architecture_guards.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_freshness.py`；`ReadModelRefreshGateway` 正向测试已删除。
- Write affected scopes：`tests/test_scope_keys.py`，以及 batch/no-OA/OA pending/pending invoice/turnover、bank-detail、input-invoice-usage OA reverse、output-invoice-collections、tax-offset、workbench relation action、general/file import、ETC import job completion、OA manual import/create/refresh/remove 的 API/service/page tests。

## 当前缺口和删除条件

- 不得新增页面 read model；确需短期触碰旧 read model 时必须同时记录 direct API 替代路径和删除条件。
- 删除旧 read path 前必须证明所有页面 API 已迁移到 direct API，且 worker/deploy/scripts/tests 不再引用对应 read model。
- 剩余未闭合重点是历史文档/fixture 清理和 legacy compat path 负向验证；未完成前不能宣称全仓库 read model 架构痕迹已下线。

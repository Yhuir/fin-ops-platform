# Search 模块边界与 I/O

日期：2026-07-27

## 模块化状态

- 状态：retained shared read model
- Scope：`search`
- Event：`search.read_model.refresh`
- Workers：`search`、`search-secondary`、`search-tertiary`
- Query owner：Search read API
- Repository owner：`SearchReadModelRepositoryPort`

## 职责

### 负责

- `/api/search` 查询和权限合同。
- 月份分区 search index 的 freshness proof、refresh enqueue、projection 与持久化。
- `all` maintenance command 的月份枚举。

### 不负责

- 不拥有搜索结果对应的 canonical 业务事实。
- 不提供待找发票或其它页面 projection。
- 不读取 Workbench page generation/payload。
- 不接受普通业务 writer 的跨页面 fan-out。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Search query | API | 规范化 query 与月份 scope；读取 payload 前验证 current-effective dirty/outbox 与 source proof |
| Refresh scope | `ReadModelRefreshGateway` | 只接受 `YYYY-MM` 或 `all`；normalize、validate、dedupe 后写 durable queue |
| Projection source | canonical query owner | 只读取构建索引需要的 canonical row/context；不读取页面 DTO |
| Maintenance `all` | 显式运维入口 | 枚举月份 shard；不得发布可查询 `all` payload |

## 输出 I/O

| 输出 | Consumer | 合同 |
| --- | --- | --- |
| Search results | `/api/search` | 只来自 fresh index；non-fresh 明确返回状态，不 live fallback |
| Index rows | PostgreSQL | 按 `row_id` no-op-aware bulk upsert，删除同 scope stale rows |
| Scope summary | freshness/worker | row count、source versions 与 readiness，不加载完整结果 |
| Dirty/outbox | runtime worker | 只允许 `search.read_model.refresh` |

## 性能与一致性

- source versions 与 scope summary一致时，worker 返回 `source_versions_unchanged`，不扫描/写索引。
- source 变化时只重建当前月份；空结果允许清空当前 scope。
- Redis 只缓存 freshness gate 后的结果；RabbitMQ 只作 transport/wakeup。
- repository unavailable、非法 scope 或 proof 缺失必须 fail closed。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Route | `/api/search` in `app/server.py` |
| Query | `search_service.py`、`search_query_freshness_service.py` |
| Refresh | `search_read_model_refresh_producer.py`、`search_read_model_refresh.py` |
| Projection | `search_sql_projection.py` |
| Repository | `search_read_model_repository.py`、`postgres_repositories/read_models.py` |
| Runtime | `read_model_manifest.py`、`read_model_scope_policy.py`、`runtime_worker_registry.py` |
| Tests | `tests/test_search_api.py`、`tests/test_search_service.py`、`tests/test_search_sql_runtime.py`、manifest/worker/gateway tests |

## 依赖方向

`Search API -> freshness service/repository -> ReadModelRefreshGateway -> durable queue -> Search worker -> Search repository`

- service 不读取 HTTP cookie/header，不依赖 `Application`。
- business service 不直接写 index、dirty scope 或 outbox。
- 禁止恢复 `search-pending`、pending-invoice compatibility projector、Workbench generation input 或 synchronous live scan fallback。

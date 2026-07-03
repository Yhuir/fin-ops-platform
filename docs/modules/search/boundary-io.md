# Search 模块边界与 I/O

日期：2026-07-03

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：搜索索引由 `search` read model 投影，页面/API 查询只读 fresh-gated index。
- 当前缺口：search 与 pending invoice 共用 worker/投影链路，scope 变更必须同步两个模块。
- 旧代码删除条件：旧搜索即时查询路径不再被 `/api/search` 或前端引用。

## 职责边界

### 负责

- `/api/search` 搜索 API。
- `search` read model index 投影。
- 为 pending invoice/search 页面提供索引 freshness。

### 不负责

- 不拥有搜索结果对应业务对象的源事实。
- 不直接修改 pending invoice 业务状态。
- 不接受无界 all 查询绕过 fan-out。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 搜索请求 | 前端/API | 查询 read model index |
| Refresh scope | `search` manifest | month or `all`；`all` 是 fan-out command |
| 业务对象变化 | lifecycle/producer | 产生 search scope refresh |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 搜索结果 | 调用页面 | 必须来自 fresh index 或暴露 nonfresh |
| Search index rows | repository | partitioned scoped index；保存时按 `row_id` 做 no-op aware bulk upsert，只删除同 scope 不再存在的 stale rows；空结果 scope 才允许整月删除 |
| Dirty scope | runtime queue | `search.read_model.refresh` |

## 持久化与投影

- Read model：`search`
- Projection：`partitioned_scoped_index`
- Worker：`search`，辅助 `search-pending`、`search-secondary`、`search-tertiary`
- Query owner：Search read API
- Repository owner：`SearchReadModelRepositoryPort`
- Persistence contract：`save_search_index_rows(...)` 不允许恢复整月 delete + 全量 rewrite 的旧逻辑；更新必须通过 `row_id` upsert 和 `is distinct from` 跳过 no-op 行，避免 grouped SLO 写放大。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Backend route | `/api/search` in `backend/src/fin_ops_platform/app/server.py` |
| Backend service | `search_service.py`、`search_query_freshness_service.py`、`search_read_model_refresh_producer.py`、`search_pending_read_model_refresh.py` |
| Repository / SQL | `search_read_model_repository.py`、`search_pending_sql_projection.py`、`postgres_repositories/read_models.py` |
| Manifest/worker | `read_model_manifest.py`、`runtime_worker_registry.py` |
| Tests | `tests/test_search*.py`、`tests/test_search_pending_sql_runtime.py` |

## 依赖方向

- 允许依赖：read model repository, pending invoice projection, runtime queue。
- 必须通过：search read model freshness service/API。
- 禁止绕过：页面直查源业务表作为搜索结果；business service 直接写 index 表。

## 测试与验证

- `tests/test_search_api.py`
- `tests/test_search_service.py`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_read_model_manifest.py`
- `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_search_index_rows_are_saved_with_bulk_values`
- `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_search_index_bulk_save_deletes_scope_when_result_is_empty`

## 当前缺口和删除条件

- 如拆出 route owner，必须同步本文件和 module README。
- 删除旧查询前必须验证 pending invoice/search fan-out。

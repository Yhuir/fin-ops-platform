# Search 模块边界与 I/O

日期：2026-06-27

## 模块化状态

- 状态：active-direct
- 当前边界可信度：high
- 目标边界：`/api/search` 直接通过 `SearchService.search(...)` 读取并组装业务 payload；Search read-model refresh/freshness/worker 架构不再参与页面读取。
- 当前缺口：无 Search SQL index 读写路径；历史 `search_pending_sql_projection.py` 已删除。
- 旧代码删除条件：Search SQL storage 当前运行面已删除；不得恢复 Search SQL storage。

## 职责边界

### 负责

- `/api/search` 搜索 API。
- `/api/search` direct search payload 组装。
- Search SQL index/projection 不回流的边界。

### 不负责

- 不拥有搜索结果对应业务对象的源事实。
- 不直接修改 pending invoice 业务状态。
- 不接受无界 all 查询绕过 fan-out。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 搜索请求 | 前端/API | 直接调用 `SearchService.search(...)`，不要求 read model freshness |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 搜索结果 | 调用页面 | direct business payload；不返回 `read_model_status`、scope key 或 refresh enqueue 字段 |

## 持久化与投影

- Read model：已从 manifest/App Status/runtime worker/current SQL storage 删除
- Projection：无 Search projection
- Worker：无 Search read-model worker
- Query owner：`SearchService.search(...)`
- Repository owner：无 Search SQL repository owner

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Backend route | `/api/search` in `backend/src/fin_ops_platform/app/server.py` |
| Backend service | `search_service.py` |
| Repository / SQL | 无 Search SQL index repository；无 Search/Pending legacy SQL projection |
| Manifest/worker | 无 Search read-model registration；`read_model_manifest.py`、`runtime_worker_registry.py` 必须保持不登记 Search |
| Tests | `tests/test_search*.py`、`tests/test_platform_runtime_boundary_guards.py` |

## 依赖方向

- `/api/search` 允许依赖：`SearchService` 及其既有 direct query 来源。
- pending invoice direct query 不能作为 Search 读取依赖。
- 禁止绕过：route 内重新实现搜索 SQL/拼装逻辑；business service 直接写 Search index 表；fresh migration 重新创建 `read_model.search_index_rows`。

## 测试与验证

- `tests/test_search_api.py`
- `tests/test_search_service.py`
- `tests/test_read_model_manifest.py`

## 当前缺口和删除条件

- 如拆出 route owner，必须同步本文件和 module README。
- 如后续触碰搜索 API 或 pending invoice direct query，必须验证 `/api/search` direct contract 和 Search SQL storage negative guard。

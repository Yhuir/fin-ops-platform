# Prompt 61: 成本统计后端物化缓存与异步预热

## 背景

成本统计页面打开时会请求 `/api/cost-statistics/explorer?month=YYYY-MM|all&project_scope=active|all`。当前后端由 `CostStatisticsService` 实时从关联台 grouped payload 构建成本 entries；`month=all` 会解析所有银行流水月份并逐月构建，冷缓存时会串行触发多个 workbench read model 构建，导致页面长期显示“正在加载成本统计数据...”。前端缓存只能改善同一浏览会话内的重复打开，不能解决首次加载和服务端全量计算问题。

本 prompt 的目标是把成本统计做成后端独立 read model/materialized cache，并把失效、预热和观测接入生产链路。

## 必须完成

1. 为成本统计建立独立 read model/materialized cache。
   - 缓存粒度为 `month + project_scope`。
   - `month` 支持 `YYYY-MM` 和 `all`。
   - `project_scope` 支持 `active` 和 `all`。
   - read model payload 保存完整 explorer 响应，包含 `summary`、`time_rows`、`project_rows`、`expense_type_rows`。
   - 使用 schema version 过滤旧缓存，避免旧结构污染。

2. 增加持久化。
   - local pickle 模式保存到 `cost_statistics_read_models`。
   - Mongo 模式使用独立 detailed collection，不要把大 payload 塞进单个 app_state 文档。
   - 支持按 `changed_scope_keys` 增量保存和删除。

3. API 使用缓存。
   - `/api/cost-statistics/explorer` 先查成本统计 read model。
   - cache hit 时直接返回缓存 payload，不调用实时构建。
   - cache miss 时按月份构建、写缓存、持久化，再返回。
   - `month=all` cache miss 不应在用户请求线程同步全量计算；应返回结构完整的空 explorer payload，并创建后台预热任务。

4. 精确失效。
   - 关联台确认、撤回、取消配对、异常、忽略/恢复、OA 源变化等操作，复用现有 workbench read model scope 失效入口，联动删除成本统计对应月份缓存。
   - 银行流水导入、发票导入成功后，按导入行日期失效相关月份；如果无法精确月份，则至少失效 `all` 和相关 scope。
   - 项目状态变化会影响所有月份的 `project_scope=active` 口径，应清理 active 相关缓存；简单可靠方案是成本统计全量清理并后台预热。
   - 任意月份变化都必须同时失效 `active:all` 和 `all:all`。

5. 异步预热。
   - 复用现有 `BackgroundJobService`，不新增独立 worker 进程。
   - job type 使用 `cost_statistics_cache_warmup`。
   - job 必须幂等，避免同一批月份重复创建任务。
   - 预热按 affected months 构建 `active` 和 `all` 两种项目范围。
   - 任意月份变化后，后台也要预热 `month=all` 的两种项目范围。
   - 预热失败不得破坏已有缓存；只在单个 explorer payload 构建成功后写入 read model。

6. 日志和指标。
   - 每次 explorer 请求输出结构化 JSON。
   - 字段至少包含：
     - `kind="cost_statistics_explorer_metric"`
     - `metric="cost_statistics.explorer.duration_ms"`
     - `month`
     - `project_scope`
     - `cache_hit`
     - `duration_ms`
     - `entry_count`
     - `timestamp`
   - 缓存持久化异常输出 `kind="cost_statistics_persistence_warning"`。
   - 不得输出 OA、银行流水、发票明细等敏感数据。

## 不需要立即做

1. 不需要新增独立后端 worker 进程。
   - 当前项目已有 `BackgroundJobService` 和 background job API，足够支撑后台预热。
   - 后续只有当同进程线程池影响 API 延迟、需要水平扩展或需要任务隔离时，再把同一 warmup handler 移到独立 worker 进程。

2. 不需要改前端页面行为。
   - 前端已有短 TTL explorer cache，可以保留。
   - 本 prompt 只处理后端生产级加载问题。

3. 不需要改成本统计业务口径。
   - OA 成本字段、银行支出金额、项目状态过滤、自动 OA 发票冲抵过滤等现有规则必须保持不变。

## 推荐拆分

### 子任务 A: read model 服务与持久化

写入范围：

- `backend/src/fin_ops_platform/services/cost_statistics_read_model_service.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `tests/test_cost_statistics_read_model_service.py`
- `tests/test_state_store.py`

验收：

- read model deep copy、schema version、entry_count、month/project_scope key、invalidate_months 行为正确。
- local pickle 和 Mongo detailed collection 都能保存/加载。
- Mongo 支持 `changed_scope_keys` 增量写入和删除。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_read_model_service tests.test_state_store
```

### 子任务 B: Application 接入、失效、预热、指标

写入范围：

- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_cost_statistics_api.py`
- 必要时少量更新 `tests/test_workbench_v2_api.py`

验收：

- explorer cache hit 不调用 `CostStatisticsService.get_explorer`。
- explorer cache miss 构建并写入 read model。
- `month=all` cache miss 返回结构完整空 payload，并创建后台预热任务。
- workbench read model scope 失效会联动删除成本统计 month/all 缓存。
- 指标日志包含 `cost_statistics.explorer.duration_ms`、cache hit/miss、entry count。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api tests.test_workbench_v2_api
```

### 子任务 C: 集成验证

验收：

- 后端成本统计相关测试通过。
- 前端成本统计缓存相关测试仍通过。
- 现有关联台核心测试不因新增失效调用回归。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_read_model_service tests.test_cost_statistics_service tests.test_cost_statistics_api tests.test_workbench_v2_api
cd web && npx vitest run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx
git diff --check
```

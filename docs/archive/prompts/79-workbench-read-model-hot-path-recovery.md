# 79. Workbench read model 热路径恢复生产级执行方案与 Prompt

## 线上事实

- 生产 release：`main-ccbf7c2d-20260531135252`。
- 用户侧错误文案来自后端顶层 500 wrapper：`接口处理失败，请联系管理员查看后端日志。`
- 线上 `journalctl -u fin-ops.service` 已确认失败请求：
  - `GET /api/workbench/groups?month=all&zone=open&page=1&page_size=200&detail_level=summary`
  - `GET /api/workbench/groups?month=all&zone=paired&page=1&page_size=200&detail_level=summary`
  - `GET /api/workbench/refresh-status?month=all`
- 精确异常：

```text
psycopg.errors.QueryCanceled: canceling statement due to statement timeout
```

- Traceback 入口：
  - `Application._handle_api_workbench_groups(...)`
  - `WorkbenchQueryFacade.groups(...)`
  - `WorkbenchQueryFacade._groups_refresh_status_payload(...)`
  - `PostgresReadModelRepository.get_workbench_refresh_status(...)`
  - `PostgresReadModelRepository._workbench_generation_consistency_failures(...)`

- 线上 read model 数据状态：
  - `workbench_generations`: `active=35`, `failed=36`, `superseded=1653`
  - `job.read_model_dirty_scopes`: 无 `pending` / `processing` / `failed`
  - 近 24 小时 `job.outbox_events`: 无 failed backlog
  - `read_model.workbench_rows`: 总量约 117 万，active 约 2179
  - `read_model.workbench_groups`: 总量约 71 万，active 约 1243
  - `read_model.workbench_group_rows`: 总量约 139 万，active 约 2358

## 根因判断

这不是前端静态包问题，不是 worker 全挂，也不是数据没生成。真实根因是 Workbench query/read-model 重构后，freshness/consistency gate 被放进了页面热路径：

1. `/api/workbench/groups` 每次调用 `WorkbenchQueryFacade.groups(...)`。
2. `groups(...)` 每次先调用 `_groups_refresh_status_payload(...)`。
3. `_groups_refresh_status_payload(...)` 调用 `get_workbench_refresh_status(...)`。
4. `get_workbench_refresh_status(...)` 同步执行 `_workbench_generation_consistency_failures(...)`。
5. `_workbench_generation_consistency_failures(...)` 当前 SQL 先对历史 generation 全表聚合，再在外层筛 active generation。
6. 历史 generation 膨胀后，页面加载和 refresh-status 请求都可能超过 PostgreSQL statement timeout，最终变成顶层泛化 500。

这和部分后端架构重构有关，但不是重构方向错误。正确方向仍然是 PostgreSQL read model + active generation + facade + repository + Redis cache + worker。问题在于热路径职责边界和 SQL 过滤顺序。

## 生产级解决方案

### 1. 拆 fast freshness gate 和 deep consistency audit

保留 `WorkbenchQueryFacade` 作为 query/read-model 入口，不把逻辑搬回 `server.py`。

- `groups(...)` 只能调用轻量 freshness gate。
- 轻量 gate 只判断 active generation、dirty scopes、building/failed generation、groups schema status 等便宜状态。
- `groups(...)` 不得同步跑 historical consistency audit。
- `refresh-status` 默认也不得扫历史 generation；它可以返回 active-only consistency。
- 深度历史审计如果仍有价值，必须是显式方法、运维工具或后台任务，不进入首屏 API 热路径。

推荐接口边界：

```python
PostgresReadModelRepository.get_workbench_groups_freshness_status(scope_key=...)
PostgresReadModelRepository.get_workbench_refresh_status(scope_key=...)
PostgresReadModelRepository.get_workbench_generation_consistency_audit(scope_key=..., include_historical=False)
```

如果为了最小 diff 不新增第三个公开方法，也必须保证 `get_workbench_refresh_status(...)` 的 consistency 部分只看 active generation。

### 2. 修正 active-only consistency SQL

`_workbench_generation_consistency_failures(...)` 必须先圈定 active target generations，再 join 各 read model 表聚合。禁止先聚合历史全表。

目标 SQL 形态：

```sql
with target_generations as (
  select generation_id, scope_key, row_count, group_count, summary_count, build_metadata
  from read_model.workbench_generations gen
  where gen.tenant_id = 'default'
    and gen.status = 'active'
    -- scope_key / include_all 条件在这里生效
),
row_counts as (
  select r.generation_id, r.scope_key, count(distinct r.row_id)::bigint as actual_row_count
  from read_model.workbench_rows r
  join target_generations tg
    on tg.generation_id = r.generation_id
   and tg.scope_key = r.scope_key
  group by r.generation_id, r.scope_key
),
...
select ...
from target_generations gen
left join row_counts ...
```

已有 migration 包含 generation/scope 索引，先复用现有索引。只有在 `EXPLAIN` 证明仍缺索引时才新增 migration，且必须评估生产 `CONCURRENTLY` / lock 风险。

### 3. 复用已有 generation stats 和 retention 能力

仓库里已有：

- `read_model.workbench_generation_stats`
- `PostgresReadModelRepository._workbench_generation_stats_for_groups_page(...)`
- `PostgresReadModelRepository.preview_workbench_generation_retention(...)`
- `PostgresReadModelRepository.prune_workbench_generations(...)`

执行时必须复用这些方法，不重新造轮子。

需要补齐的是：

- fast freshness / refresh-status 不因为 stats 或 consistency 而扫历史表。
- retention 操作要有 CLI 或现有工具入口，支持 dry-run、execute、limit、keep_recent、keep_days。
- retention 永远保护 active generation。
- 删除顺序必须继续覆盖 stats、group_rows、groups、rows、summary、snapshots、generations。

### 4. 显式处理已知 transient read-model timeout

不能让已知 PostgreSQL statement timeout 冒泡成泛化 500。

在 `WorkbenchQueryFacade` 增加明确依赖，例如：

```python
transient_read_model_error: Callable[[Exception], bool]
```

由 `Application._workbench_query_facade()` 注入 app-shell 里的识别函数。只识别明确 transient DB/read-model 错误：

- `psycopg.errors.QueryCanceled`
- error class / message 明确包含 `statement timeout`
- error class / message 明确包含 `canceling statement due to statement timeout`

返回结构化响应，例如：

```json
{
  "error": "read_model_temporarily_unavailable",
  "read_model_status": "refreshing",
  "retryable": true,
  "scope_key": "all",
  "message": "Workbench SQL read model query timed out; retry after refresh."
}
```

建议状态码：`503 Service Unavailable`。不要吞掉未知异常。

### 5. 保持 Redis cache 语义

`groups` Redis cache 仍然保留，但缓存读写前置条件必须只依赖 fast freshness gate。

- cache key 必须继续包含 active generation/version、zone、page、page_size、search、search_mode、search_by_pane、sort、detail_level、column_filters、time_filters、schema version。
- stale / refreshing / unavailable 时不得写入可复用 Redis payload。
- Redis miss 后仍只走 SQL read model，不回退 legacy snapshot 或同步 rebuild。

### 6. 生产验证和回滚

上线前：

- 不把生产 SSH 密码写入文件、脚本、commit 或日志。
- 只读记录 baseline：日志 request_id、表行数、active generation、dirty scopes、outbox backlog、worker heartbeat。
- 跑本地单元测试和必要集成测试。

上线后：

- 访问 `/fin-ops-api/health`。
- 用认证态访问 Workbench 页面，确认 summary、open groups、paired groups、refresh-status 不再出现 500。
- `journalctl -u fin-ops.service` 检查不再出现同类 `QueryCanceled` traceback。
- 观察 `workbench.api.duration_ms`，`groups` 和 `refresh-status` 不应再稳定打满 statement timeout。

回滚：

- 代码发布失败：使用现有部署回滚机制回到上一 release。
- retention execute 只在代码热路径修复并稳定后执行；执行前必须 dry-run 和备份。

## 最终执行 Prompt：主控总任务

```text
/goal 生产级修复 Workbench read-model 热路径 statement timeout：保持现有重构架构，拆 fast freshness gate / deep consistency audit，修 active-only consistency SQL，显式处理 transient read-model timeout，复用现有 generation stats 与 retention 能力，并完成测试、验证、生产只读复核和回滚说明。

你在 /Users/yu/Desktop/fin-ops-platform 工作。先读 AGENTS.md、README.md、ARCHITECTURE.md、docs/dev/backend.md、docs/architecture/persistence-and-read-models.md、docs/architecture/backend-refactor/target-architecture.md、docs/architecture/backend-refactor/workbench-read-model-query-plan.md。使用 CodeGraph 先理解 WorkbenchQueryFacade、PostgresReadModelRepository、Application workbench handlers、read_model generation/retention 相关调用关系。

背景事实：
- 线上 release main-ccbf7c2d-20260531135252。
- 失败 endpoint 是 /api/workbench/groups 和 /api/workbench/refresh-status。
- 精确异常是 psycopg.errors.QueryCanceled: canceling statement due to statement timeout。
- traceback：Application._handle_api_workbench_groups -> WorkbenchQueryFacade.groups -> _groups_refresh_status_payload -> PostgresReadModelRepository.get_workbench_refresh_status -> _workbench_generation_consistency_failures。
- read_model 历史 generation 膨胀：active 数据只有几千行，但历史 rows/groups/group_rows 是百万级。

硬性架构约束：
- 不回退 legacy snapshot / Mongo / pickle / _build_raw_workbench_payload。
- 不把业务查询逻辑塞回 server.py；server.py 只做 app-shell、参数解析、response mapping。
- 保持 WorkbenchQueryFacade 作为 query/read-model orchestration 边界。
- 保持 PostgresReadModelRepository 作为 SQL 边界。
- Redis 只能是 generation-aware TTL cache，不能成为事实源。
- RabbitMQ/Outbox/dirty scope/worker 语义不得改变。
- 不新增依赖，除非有明确必要并先说明。
- 不把生产 SSH 密码或任何 secret 写入仓库、脚本、日志或提交信息。

串行执行：
1. 新建工作分支 codex/workbench-read-model-hot-path-recovery。
2. 做只读 baseline：本地 git 状态、相关测试入口、必要时生产日志/DB 状态只读复核；不得改生产。
3. 先写 characterization tests，复现当前缺陷：
   - groups cache/freshness gate 不得调用 heavy get_workbench_refresh_status。
   - refresh-status/consistency 只看 active generation，不聚合历史 generation。
   - QueryCanceled/statement timeout 返回结构化 503，不再冒泡成泛化 500。
   - retention 不删除 active generation，并可 dry-run。
4. 实现最小代码变更：
   - 在 PostgresReadModelRepository 增加/复用 fast freshness 方法，供 groups hot path 使用。
   - 改写 _workbench_generation_consistency_failures 为 active-first SQL。
   - WorkbenchQueryFacade.groups 使用 fast freshness gate；不再在 groups 热路径同步跑 deep consistency。
   - WorkbenchQueryFacade.refresh_status 保留 API contract，但不得扫历史 generation。
   - 增加 transient_read_model_error 识别与结构化 503 响应，只处理明确 statement timeout/QueryCanceled。
   - 复用现有 prune_workbench_generations；如没有 CLI，则补一个薄 CLI 工具调用 repository 方法，支持 dry-run/execute/keep/limit。
5. 运行验证：
   - python -m unittest tests.test_workbench_query_facade -v
   - python -m unittest tests.test_workbench_sql_runtime -v
   - python -m unittest tests.test_postgres_migrations -v
   - rg guards：
     - rg -n "_build_raw_workbench_payload\\(" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_query_facade.py
     - rg -n "mock\\.patch\\(.+WorkbenchQueryFacade|patch\\(.+workbench_query_facade|monkeypatch.+WorkbenchQueryFacade|WorkbenchQueryFacade.*Mock|Mock.*WorkbenchQueryFacade" tests/test_workbench_sql_runtime.py
6. 本地验证通过后，给出生产发布步骤、只读验收命令、retention dry-run/execute 顺序和 rollback。

并行策略：
- 可以并行做“测试锁定审查”“SQL/索引审查”“retention 工具审查”“生产验收清单审查”，但实际修改同一文件时必须串行合并，避免冲突。
- 每个并行任务只能读代码和提出补丁建议；最终由主控任务统一落地和跑完整验证。

完成标准：
- /api/workbench/groups 不再依赖 historical consistency audit。
- /api/workbench/refresh-status 不再因为历史 generation 膨胀触发 statement timeout。
- active-only consistency 保持原有 mismatch 检测语义。
- QueryCanceled/statement timeout 有结构化响应和 metric，不再出现泛化 internal_server_error。
- retention 能安全 dry-run，并保护 active generation。
- 相关测试全部通过；未通过的测试必须解释原因和剩余风险。
```

## 并行 Prompt A：只读生产与基线复核

```text
/goal 只读复核 Workbench read-model 线上失败基线，输出 request_id、traceback、DB 表规模、active generation、dirty scope、outbox、worker 状态，不修改生产服务或数据库。

范围：
- 只读 SSH / journalctl / systemctl / SQL SELECT。
- 不重启服务，不改配置，不执行 DDL/DML。
- 不保存、不打印、不提交任何 secret。

要确认：
1. 最近 2 小时 fin-ops.service 的 unhandled request error，按 endpoint/error 聚合。
2. 是否只有 psycopg.errors.QueryCanceled / statement timeout。
3. request_id 列表和对应 path。
4. workbench worker / workbench-matching worker 状态。
5. read_model.workbench_rows / groups / group_rows / summary / generation_stats 的总量和 active 数量。
6. read_model.workbench_generations 按 status 聚合。
7. job.read_model_dirty_scopes 是否存在 pending/processing/failed。
8. job.outbox_events 近 24 小时 workbench.read_model.refresh 是否有 backlog。

输出：
- 事实表。
- 是否发现第二故障。
- 是否影响后续修复方案。
```

## 并行 Prompt B：测试锁定

```text
/goal 为 Workbench read-model hot path timeout 写最小但足够的 characterization tests，先失败再实现，禁止 mock 掉 WorkbenchQueryFacade。

目标文件优先：
- tests/test_workbench_query_facade.py
- tests/test_workbench_sql_runtime.py
- tests/test_workbench_v2_api.py 或现有 Application handler 测试附近

必须覆盖：
1. WorkbenchQueryFacade.groups 优先使用 repository 的 fast freshness 方法；当 fast 方法存在时，不得调用 get_workbench_refresh_status。
2. groups 在 fast status 为 refreshing/stale 时绕过 Redis payload，且不写 Redis。
3. groups 的 SQL page 查询如果抛明确 QueryCanceled/statement timeout，返回 503 read_model_temporarily_unavailable。
4. refresh_status 如果遇到明确 QueryCanceled/statement timeout，返回 503 read_model_temporarily_unavailable。
5. _workbench_generation_consistency_failures 的 SQL 必须先限定 active target generations，再 join rows/groups/group_rows/summary；测试用 fake connection 断言 SQL 包含 target_generations 或等价 active-first 结构，且不再出现历史全表先 group 的形态。
6. prune_workbench_generations 继续保护 active generation；如果补 CLI，则 CLI dry-run 不执行 delete。

禁止：
- 不用 mock.patch 绕过 WorkbenchQueryFacade。
- 不写依赖真实生产数据的测试。
- 不为了测试通过改变公开 API contract。

输出：
- 新增/修改的测试名。
- 哪些测试在实现前会失败。
```

## 并行 Prompt C：SQL 与 repository 审查

```text
/goal 审查并修复 PostgresReadModelRepository 的 Workbench refresh-status/consistency SQL，使其只扫描 active generation，并复用现有 generation stats / retention 方法。

目标文件：
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
- backend/src/fin_ops_platform/postgres/migrations/* 仅在确认必须新增索引时修改

实现要求：
1. _workbench_generation_consistency_failures 先构造 target_generations，再 join workbench_rows/workbench_groups/workbench_group_rows/workbench_summary 聚合。
2. scope_key 和 include_all 条件必须作用在 target_generations 上。
3. 保持 tombstone、row_count/group_count/summary_count mismatch 语义。
4. get_workbench_refresh_status 不得触发历史 generation 全表聚合。
5. 如新增 get_workbench_groups_freshness_status，必须复用 dirty scope、generation metadata、groups schema status 的现有封装，不复制大段 SQL。
6. 优先复用 _workbench_generation_metadata、_workbench_groups_schema_status、_workbench_generation_stats_for_groups_page、preview_workbench_generation_retention、prune_workbench_generations。
7. 不改变 worker 写 read model 的事实语义。

验证：
- tests.test_workbench_sql_runtime 通过。
- 必要时用 EXPLAIN 确认 active-only 查询走 generation/scope 索引。
```

## 并行 Prompt D：facade / API 错误语义

```text
/goal 修复 WorkbenchQueryFacade 和 Application workbench handler 的 transient read-model timeout 语义：已知 statement timeout 返回结构化 503，未知异常继续冒泡。

目标文件：
- backend/src/fin_ops_platform/services/workbench_query_facade.py
- backend/src/fin_ops_platform/app/server.py
- tests/test_workbench_query_facade.py
- tests/test_workbench_sql_runtime.py 或 handler 测试附近

实现要求：
1. WorkbenchQueryFacade.__init__ 增加 transient_read_model_error callable，默认由 Application 注入。
2. Application 增加小而明确的 helper，例如 _is_transient_workbench_read_model_error(error)。
3. 只识别 QueryCanceled / statement timeout / canceling statement due to statement timeout。
4. groups 和 refresh_status 对该类错误返回 HTTPStatus.SERVICE_UNAVAILABLE。
5. payload 包含 error=read_model_temporarily_unavailable、read_model_status=refreshing、retryable=true、scope_key、message。
6. emit_status_metric 记录 endpoint、scope_key、read_model_status=refreshing、reason=query_timeout。
7. 未知异常不被吞掉，仍由顶层 handler 记录 traceback。

禁止：
- 不在 server.py 写业务 SQL。
- 不把所有 Exception 都转 503。
- 不改变已有 read_model_unavailable/migration_missing 语义。
```

## 并行 Prompt E：retention 工具与运维流程

```text
/goal 为 Workbench read-model generation retention 补齐生产可执行入口和运维验证，复用 PostgresReadModelRepository.prune_workbench_generations，不重新实现删除逻辑。

目标文件：
- backend/src/fin_ops_platform/tools/* 如需新增 CLI
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py 仅在已有方法缺少必要保护时修改
- tests/test_workbench_sql_runtime.py 或新增工具测试
- docs/dev/backend.md 或 docs/operations/* 如需补 runbook

实现要求：
1. CLI 只负责解析参数、建立 PostgresConnection、调用 repository.prune_workbench_generations。
2. 参数至少包括 --keep-recent-generations-per-scope、--keep-days、--limit、--dry-run、--execute。
3. 默认 dry-run；execute 必须显式传入。
4. 输出 JSON，包含 candidate_count、deleted_count、dry_run、generations 截断列表。
5. repository 删除逻辑必须继续保护 status='active'。
6. 不在 API 请求路径调用 retention。

生产顺序：
1. 热路径代码修复发布并稳定后，先运行 dry-run。
2. 备份数据库或确认云快照。
3. 离峰小 limit execute，多批执行。
4. 每批后检查 active generation、summary、groups 页面和 journal。
```

## 串行合并与验收 Prompt

```text
/goal 合并 Workbench hot path 修复的所有子任务，跑完整验证，输出生产发布、验收、retention 和 rollback 清单。

合并顺序：
1. 测试锁定。
2. repository active-only SQL 和 fast freshness。
3. facade groups hot path 调整。
4. transient timeout 结构化响应。
5. retention CLI/runbook。
6. 文档/运维说明。

必须运行：
- python -m unittest tests.test_workbench_query_facade -v
- python -m unittest tests.test_workbench_sql_runtime -v
- python -m unittest tests.test_postgres_migrations -v
- python -m fin_ops_platform.app.main --check

可选但推荐：
- scripts/check-local-runtime.sh --dependencies-only
- 针对 /api/workbench/summary、/api/workbench/groups、/api/workbench/refresh-status 的本地 smoke

生产验收：
- 部署新 release 后检查 /fin-ops-api/health。
- 带认证态打开 Workbench 页面。
- journalctl 确认没有新的 workbench groups / refresh-status QueryCanceled traceback。
- 对比 workbench.api.duration_ms，不应再出现 refresh-status/groups 稳定打满 statement timeout。

最终输出：
- 改动文件。
- 架构边界说明。
- 测试结果。
- 未执行项和原因。
- 生产发布命令或人工步骤。
- 回滚步骤。
- retention dry-run/execute 建议。
```

## Prompt 自审结果

已按以下标准审阅：

- 覆盖已确认线上 request_id 和 traceback：是。
- 明确根因不是前端/worker/down/缺数据：是。
- 遵循现有重构架构：是，继续使用 `Application -> WorkbenchQueryFacade -> PostgresReadModelRepository -> read_model/worker/Redis`。
- 不重复造轮子：是，要求复用 generation stats、retention repository 方法、现有 Redis key 构造和 status metric。
- 阻止常见错误修法：是，明确禁止 legacy snapshot、同步 `_build_raw_workbench_payload`、server.py 内写 SQL、吞掉所有异常、把 Redis 当事实源。
- 解决热路径 timeout：是，`groups` 不再调用 historical consistency audit，consistency SQL active-first。
- 解决 refresh-status timeout：是，默认 active-only consistency，不扫历史 generation。
- 解决泛化 500：是，QueryCanceled/statement timeout 结构化 503，未知异常继续 traceback。
- 解决历史 generation 膨胀：是，补齐/复用 retention dry-run/execute，但安排在热路径修复稳定后执行。
- 生产风险控制：是，包含只读 baseline、测试、发布验收、journal 验证、备份、离峰分批、回滚。

当前 prompt 可以交给 Codex 作为最终执行入口。执行时如果测试发现还有第二故障，应先停下来记录事实并扩展计划，不得用宽泛 fallback 掩盖未知错误。

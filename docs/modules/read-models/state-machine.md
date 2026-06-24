# Read Model 状态机

> 修改 `Read Model` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。页面自己的 UI 状态在页面模块维护；本文件维护共享 freshness、dirty scope、worker readiness 和非法状态。

## 业务状态

- 当前状态：read model 是写模型之外的派生投影；写入事实不直接改页面投影，而是通过 dirty scope/outbox 触发 worker 重建。
- 状态事实源：
  - PostgreSQL durable queue：`job.outbox_events`、`job.read_model_dirty_scopes`
  - Readiness 证明层：`read_model.app_status_readiness`
  - Workbench 例外：active generation/readiness metadata
- 允许流转：
  - business write -> lifecycle/dirty scope -> outbox event -> worker processing -> projection publish -> readiness fresh
  - API miss/stale -> `ReadModelQueryGateway` 返回 refreshing payload -> `ReadModelRefreshGateway` enqueue refresh
  - expected schema/source contract 与 actual projection metadata 不匹配或缺失 -> refreshing/stale reason -> enqueue refresh
  - fresh gate 通过但业务 payload contract 不满足当前 API shape -> 忽略 Redis cache 或返回 refreshing/stale reason -> enqueue refresh
  - worker failure -> readiness failed/unavailable -> App Status busy/blocked
- 禁止流转：
  - query service 没有 expected schema/source contract，却把 projection 判为 fresh
  - 页面或 service 绕过 freshness gate 读取旧 projection 并标记 fresh
  - 新增 direct `read_model_status=fresh` 或 direct `source_version_mismatch_reasons(...)` 调用，却没有进入架构 guard 分类和 expected contract 证明
  - Redis/RabbitMQ 被当作 read model 状态事实源
  - 业务 service 直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`
  - fan-out-only refresh 结果写假 fresh readiness

## UI 状态

本模块没有独立页面，但定义页面消费 read model 状态的共享语义：

- loading：页面首次请求或后台 refresh 状态未返回时展示局部 loading；不得写入业务事实。
- empty：只有 `read_model_status=fresh` 且 rows/summary 为空时，才能展示真实空态。
- error：API/worker/readiness failed 或 unavailable 时展示可恢复错误/blocked，不得吞失败。
- stale/refreshing：stale、missing、source/schema mismatch 或 dirty scope pending 时，页面必须展示刷新语义；不能把空 rows 当真实无数据。
- permission disabled/hidden：权限由业务 API/session 模块维护；read model 状态不能替代权限判断。

## Read Model / Worker 状态

- `fresh`：query service 已声明 expected schema/source contract，projection/readiness 的实际 schema/source version 与之匹配，并且 payload 满足业务 query service 声明的 API shape contract；通过后才可以对外展示 payload，也可以写 fresh-gated Redis cache。
- `missing`：没有可用 projection/readiness；API 应返回 refreshing 语义并入队 refresh。
- `refreshing`：dirty scope pending/processing、worker 等待 shard、source/schema stale 后已入队；页面显示刷新中或后台刷新提示。
- `stale`：内部 freshness 判定不匹配；公开 API 通常映射为 refreshing 语义并带 stale reasons。
- `failed`：worker 或 rebuild 失败，readiness 记录 last error；App Status 可升级 busy/blocked。
- `unavailable`：依赖、runtime snapshot 或 critical worker 不可用；App Status blocked，不得解释为 ready。

## Refresh / Force Refresh 状态

| 状态 | 来源 | 允许行为 | 禁止行为 |
| --- | --- | --- | --- |
| `validated` | `ReadModelScopePolicyRegistry` 已接受 scope | gateway 可生成 durable queue request 或返回 existing active refresh | 绕过 policy 直接写 dirty/outbox。 |
| `deduped` | gateway 发现同 scope active refresh | API 可返回 `refreshing` 且 `refresh_enqueued=false` | 把去重解释为 fresh 或再次强制写入重复 outbox。 |
| `queued` | `job.outbox_events` / `job.read_model_dirty_scopes` 已写入 | worker 可 claim；App Status / operation barrier 显示 refreshing | RabbitMQ publish success 被当作状态事实源。 |
| `force_refresh_requested` | runbook/API/smoke 通过受控入口请求 | 受权限、scope validation、dedupe、audit 保护；返回 job/readiness proof | 页面任意触发 refresh all；不记录 actor/scope/reason。 |
| `force_refresh_rejected` | 非法 scope、权限不足、缺少 contract 或 current-effective blocker 不可覆盖 | fail fast 并暴露诊断 | 自动降级到 broad all 或 live scan。 |
| `barrier_fresh` | operation barrier 目标 scope current-effective fresh | 前端可释放操作 overlay 并重读/应用 projection | 跳过页面自身 fresh gate。 |
| `barrier_refreshing` | 目标 scope pending/processing/deferred | 前端继续等待或提示后台同步中 | 显示操作失败，除非写 API 本身失败。 |
| `barrier_blocked` | failed/unavailable/current uncovered failure | API 返回具体 read model/scope/reason | 伪装 fresh 或吞掉 blocker。 |

## Projection 策略状态

| 策略 | 适用 read model | 状态约束 |
| --- | --- | --- |
| active generation | `workbench` | building/failed generation 不对页面发布；`all` 聚合来自 active month shards。 |
| partitioned scoped incremental | `bank_detail`、`search` 等 month shard read model | fan-out `all` 只投递子 scope；页面 fresh proof 来自真实 shard 或 parent aggregate proof。 |
| all-only scoped projection | `bank_account_balance` | 只接受 `bank_account_balance:all`；month/account/active scope 必须在 gateway 前失败。 |
| page-first-screen explicit scope | `pending_invoice` | 拒绝裸 `all`；首屏和筛选 scope 必须显式包含 direction/filter/month contract。 |
| parent aggregate + shards | `cost_statistics` | legacy 裸 scope 只能由 scope gateway 归一化；parent aggregate 需要独立 readiness/source proof。 |

依赖未 fresh 不是 fresh，也不是普通失败：当 downstream refresh handler 读取 source read model 时遇到 `*_read_model_not_fresh`，runtime worker 会短延迟 defer 该 outbox event，等待 source projection/readiness 真实收敛后再处理；readiness reporter 必须记录为 `refreshing` 并保留 last_error 诊断，不能写 `failed` blocker，也不得因为 defer 把页面标为已同步。Workbench `all` aggregate-only refresh 携带 `parent_scope_keys` 时同样适用：parent month shard 仍 pending/processing/failed 时返回 `workbench_read_model_not_fresh`，等待 parent active generation 收敛后再聚合。

同一 scope 的 current-effective 状态必须合并后展示：如果历史 `failed` 已被新的 `pending`/`processing` 覆盖，当前状态是 `refreshing`，旧 `last_error` 只能作为历史诊断，不能继续作为当前失败阻断页面或操作。App Health 聚合 Workbench active generation 诊断时也必须遵守这一点：`read_model_status=refreshing/rebuilding` 时，即使 `consistency_status=failed`，也只能展示 busy/rebuilding 和诊断字段，不能把 `workbench_read_model` 写成 unavailable dependency 或全局 blocked。

`refresh_enqueued` 只表示本次 query gateway 调用实际写入了新的 refresh request；如果 `ReadModelRefreshGateway` 因同 scope 已有 active refresh 而合并/去重，API 仍可返回 `read_model_status=refreshing`，但 `refresh_enqueued=false`。页面和 SLO probe 不能把“已有刷新在跑”误解为“本次请求又触发了一轮刷新”。

## refresh 触发来源

- API miss
- missing expected freshness contract（代码配置错误，fail fast）
- missing schema/source metadata proof
- schema version mismatch
- source version missing/mismatch
- 业务 payload shape invalid，例如旧 projection 或旧 Redis payload 不满足当前 API mapper 的必需字段
- 业务写入后的 `DerivedDataLifecycleService` dirty cascade
- 高影响写操作可把 `metadata.action_name` 随 dirty/outbox 一起传递，用于 write operation SLO 审计区分具体动作；metadata 不替代权限、审计或业务状态事实源
- `startup_stale_scan` 之后的 workbench matching dirty worker 间接更新；startup scan 本身默认不运行，且不得直接刷新用户可见 read model
- worker shard fan-out / parent scope convergence
- 手工 runtime scope contract 清理后的 replacement scope

## 失败恢复

- API miss/stale 可以重新 enqueue refresh。
- Worker failed/unavailable 由 App Health 暴露具体 scope、last error 和 worker 状态。
- 旧生产 scope contract 由 `scripts/check-read-model-scope-contracts.py` dry-run 检查；dry-run 必须输出 repair manifest，列出 legacy/invalid cost statistics 行、已被 later done/fresh readiness 覆盖的历史 outbox failure，以及 current-effective 未覆盖 failure。
- `--apply` 只能受控清理非规范旧状态并补投可归一化 replacement scope；apply 必须记录 audit event，并带可回滚 manifest。current-effective 未覆盖 failure 不自动删除、不伪造 fresh，只能调查原因后 requeue、修复 worker 或修复投影。
- 生产真实库修复前必须保留 dry-run 报告，不能直接热改 runtime 表。

## 非法状态

- `read_model_status=fresh` 但缺少对应 readiness/source version 证明。
- `read_model_status=fresh` 但 query service 没有声明 expected schema/source contract。
- `read_model_status=fresh` 由未分类 direct path 写出，或 direct source version mismatch 比较没有先调用 `require_expected_source_versions(...)`。
- `read_model_status=fresh` 但已声明 expected schema，actual projection 或 Redis fresh gate 缺少 schema proof。
- `read_model_status=fresh` 但业务 query service 已声明 payload contract，Redis 或 SQL payload 不满足该 contract。
- `read_model_status=fresh` 但 dirty scope 仍 pending/processing 且覆盖同一 scope。
- API 返回空 rows 且不带 refreshing/stale/missing 语义，却实际没有 fresh projection。
- Redis cache 命中绕过 fresh gate。
- RabbitMQ transport 成为状态事实源。
- 未覆盖的 failed/dead_lettered/publish_failed outbox event 被删除或忽略，但没有 later done/fresh readiness 证明。
- 新增 read model/worker 后未同步 registry、manifest/systemd env、tests、docs。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-22 | App Health 和 query gateway 对 active repair/coalescing 采用 current-effective 语义：Workbench 修复中不再把旧 consistency failure 提升为 blocked；已被 active refresh 合并的 API miss 不再报告 `refresh_enqueued=true` | 修复 App Status 同时显示“刷新中/阻断”的矛盾状态，减少页面和 SLO 误判“每次加载都新触发刷新”的噪音；不改变 durable queue/readiness 事实源 | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_health_api tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_app_status_overview_service -v` |
| 2026-06-18 | `ReadModelQueryGateway` 支持业务 payload validator；旧 Redis/SQL payload 即使通过 freshness gate，也不能绕过当前 API payload contract | 避免 App Health 显示 fresh/已同步，但业务页面因旧 payload 缺少必需字段而报泛化加载失败；invalid Redis cache 改走 SQL view，invalid SQL view 返回 refreshing 并入队 refresh，不写 fresh cache | `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_query_gateway tests.test_read_model_architecture_guards -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime -v` |
| 2026-06-18 | Workbench `all` aggregate-only refresh 在 parent month scope 仍 active 或 not fresh 时走 dependency-not-fresh defer；同 scope 旧 failed 被重新 pending/processing 覆盖时展示 refreshing | 避免 relation 写入后的暂态“旧 month generation + 新 canonical relation”被误写为 failed all generation；避免旧 `workbench_all_scope_parent_inconsistent` / deadlock last_error 在重试中继续污染 Workbench refresh status 和 App Health | `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime tests.test_runtime_queue tests.test_runtime_worker tests.test_app_status_overview_service -v` |
| 2026-06-17 | read model 查询 freshness contract fail-closed，并纳管 legacy direct fresh/direct mismatch 路径 | `ReadModelQueryGateway` 必须传 expected schema/source；actual schema/source metadata 缺失时不能 fresh；自管 read model service 禁止空 source version provider；所有直接写 fresh 或直接比较 source version 的 legacy 入口必须通过静态架构 guard 分类 | `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness tests.test_read_model_query_gateway tests.test_read_model_architecture_guards -v` |
| 2026-06-14 | 依赖未 fresh 的 readiness 记录从 failed 收敛为 refreshing | 下游 read model 等待 Bankdetail/Workbench relation 等依赖时不污染 App Status blocker；仍保留 last_error 诊断和真实 retry/defer | `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_readiness_reporter tests.test_runtime_worker tests.test_runtime_queue tests.test_read_model_refresh_gateway -v` |
| 2026-06-13 | 依赖未 fresh 的 outbox event 短延迟 defer | downstream read model 不再因普通 60s retry 放大失败长尾；freshness 事实源不变 | `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_queue.RuntimeQueueRepositoryTests.test_defer_event_delays_dependency_retry_without_failure_or_dead_letter -v` |
| 2026-06-13 | 写操作 refresh metadata/action_name 透传 | `workbench_relation_withdraw`、`no_oa_bank_batch_withdraw` 可按具体动作审计跨页面 enqueue-to-fresh；不改变 freshness 事实源 | `PYTHONPATH=backend/src python3 -m pytest tests/test_read_model_refresh_gateway.py tests/test_workbench_uow_contract.py tests/test_no_oa_bank_batch_application_service.py tests/test_workbench_dirty_queue_wiring.py tests/test_write_operation_slo_audit.py tests/test_write_operation_scenario_discovery.py -q` |
| 2026-06-12 | 补齐 repair manifest 与 current-effective failure 保留规则 | dry-run/apply 可审计区分历史已覆盖失败和当前未覆盖 blocker；禁止假同步 | `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract tests.test_platform_runtime_boundary_guards tests.test_runtime_queue_ops -v` |
| 2026-06-11 | 补齐共享 read model 状态机 | 明确 fresh/missing/refreshing/stale/failed/unavailable、非法状态和恢复路径 | `bash scripts/verify.sh docs` |
| 2026-06-24 | T8 module IO contract reconciliation | 补齐 refresh/force refresh、operation barrier、projection strategy 的共享状态合同；不改变运行时状态定义 | `bash scripts/verify.sh docs` |

# 成本统计状态机

> 修改 `成本统计` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。成本统计使用 scope-level readiness：父 scope 和月份 shard 的状态不能混为一个全局布尔值。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 项目范围 | `active` | app settings project status / cost statistics API query | 默认视图；排除明确已完成项目，未知项目保持 active。 |
| 项目范围 | `all` | app settings project status / cost statistics API query | 用户选择 all project scope 后展示所有项目。 |
| 成本行 | `included` | `CostStatisticsSqlProjectionBuilder` / SQL projection payload | 支出流水或可计入成本关系满足项目/费用字段要求后进入统计。 |
| 成本行 | `excluded` | cost attribution policy / relation context | OA 发票抵扣、现金代收代付确认组等不应计入成本的关系被排除。 |
| 月份 shard | `active:YYYY-MM` / `all:YYYY-MM` | `read_model.cost_statistics_rows`、`read_model.cost_statistics_bank_flow_rows`、readiness metadata | 由 `cost-statistics` 专用 worker 从对应 Workbench 月份 active generation 与单次 bank-detail snapshot 构建。OA 配对成本行与全银行收支行分表存储，parent JSON 不保存两类大数组；禁止再从 `workbench_groups.payload` 或旧成本 JSON array 读取成员行；旧 `cost-tax` 不再消费成本统计刷新。 |
| 全期间父 scope | `active:all` / `all:all` | `read_model.cost_statistics_read_models`、readiness | 从已物化月份 shard rows 聚合生成；不读取 Workbench `all` 全量 payload。 |

关键规则：

- 成本统计页面不重新定义项目归因、发票生命周期、银行标签或 relation identity。
- 只有 confirmed/linked 成本关系可以进入金额统计；未正式化的 Workbench automatic decision 或历史 candidate 兼容值不能被 live service 或 SQL projection 计入成本行。
- 合法 read model scope 只允许 `active:YYYY-MM`、`all:YYYY-MM`、`active:all`、`all:all`。
- 裸月份或裸 `all` 只能通过 `ReadModelRefreshGateway` 归一化后入队；未知 project scope 必须拒绝。
- 月份 shard 只有在当前 event `source_version` 成功条件发布且用同一版本完成 dirty scope 后，才重新入队同 project scope 的父 scope，推动全期间视图收敛。任一 CAS 失败都保持 `refreshing`，不允许 fan-out。
- 父 scope 每次被读取都必须证明全部 active Workbench 月份、Cost child 嵌入的 Workbench/Bank Detail versions、child dependency dirty state 与 parent `source_shards` 一致；只看 parent 自身 dirty/readiness 不足以返回 `fresh`。
- 父 scope 等待缺失、stale 或 failed 月份 shard 时只能记录 `refreshing`，并只 enqueue 证明漂移的 exact month scopes，不能伪造 `fresh` 或先投一个宽泛 parent 掩盖 child drift。

禁止流转：

- 禁止 API 请求线程同步重建 read model 来掩盖缺失或 stale。
- 禁止把月份 shard failed/unavailable 直接解释为整个成本统计主体验 blocked。
- 禁止把父 scope failed/unavailable 降级为普通 busy。
- 禁止手工把 historical failed readiness 改成 fresh；只能由真实成功 rebuild 覆盖。
- 禁止父 scope 读取 Workbench `all` 大 payload 作为全期间统计事实。

## UI 状态

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | 页面首次请求 explorer，或 scope/view/domain/lifecycle refresh 触发当前 scope 重读 | 显示内联“正在加载成本统计”状态轨；成本业务区域 `inert`，上一 scope payload 立即退出可操作内容，不渲染假数据。 |
| export reference loading | 项目/费用类型导出缺少 fresh 全期间筛选选项 | 用户动作后才并行读取两个 `scope=all&page_size=1` bounded facets；请求期间禁止重复触发，fresh 后打开导出中心，non-fresh/失败则保持关闭并显示错误。 |
| refreshing | explorer GET 判定 Workbench dependency 或当前精确 Cost scope 为 loading/pending/processing/refreshing | 显示“成本数据正在同步”并锁定业务区域；150ms 有界重试 normal GET，不能把空 accepted payload 或上一 scope 内容当作当前最终结果。 |
| stale | API 返回 stale/schema/source mismatch，或 App Status 显示当前精确 cost scope stale | 显示“正在更新至最新数据”并锁定；其他月份或其他 read model non-fresh 不得误锁当前页面。 |
| unavailable | API/App Status 当前精确 cost scope 为 missing/failed/unavailable | 显示“成本数据暂未就绪”，保持锁定并提供状态轨内的“重新检查”。 |
| fresh | 当前 request identity 的 explorer payload 明确 fresh，且 App Status 当前精确 cost scope 没有 non-fresh 反证 | 一次性移除成本业务区域 `inert` 与拦截层；如焦点曾被锁定迁移，安全地恢复原控件或页面标题。 |
| empty | fresh payload 且 summary row count 为 0 | 只有 fresh 后才代表当前 view/range/project scope 真实无成本数据。 |
| error | explorer/export/detail 请求失败 | 显示错误态；不暴露底层 SQL 或 worker internals。 |
| export loading | export preview/download 进行中 | 弹窗内反馈进度和错误，保留当前页面上下文。 |
| permission disabled/hidden | 当前模块主要为只读/导出 | 若未来增加写操作，必须按 session 权限和 App Status mutation gate 禁用。 |

前端事件：

- `workbenchRelationUpdated`、`bankTransactionCategoryUpdated`、`turnoverRelationUpdated`、`invoiceFactUpdated`、`etcBusinessBatchUpdated` 等事件只能触发页面 refetch 或刷新提示。
- domain/manual/tag-rule refresh 必须丢弃本次 mount 内的导出参考数据并重新经过后端 fresh gate；页面不拥有 TTL freshness 事实源。
- 前端事件不是事实源；后端 dirty scope/outbox/worker/readiness 才证明成本统计已收敛。
- 进入锁定立即关闭并清除 transaction detail、export center 和范围 popover；标签规则 drawer 壳与草稿保留，但 body/footer inert。可取消的 detail/export-reference 请求必须 abort，晚到响应不得恢复旧 portal。
- 窗口 blur→focus、document hidden→visible、`pageshow.persisted=true` 都先清除当前可操作 payload，再重新通过 API/read boundary；同一次返回事件去重。离开页面后 React tree 卸载，inactive 页面不 replay 事件。

## Read Model / Worker 状态

| 状态 | 判定 | 后续动作 |
| --- | --- | --- |
| `fresh` | dependency-bound gate 证明 cost metadata/current dirty 一致；concrete month 还必须证明 settings、Workbench active generation/current dirty、Bank Detail schema/status/current dirty/source versions 均有效。parent `all` 先用 set-based canonical→active Workbench month proofs 收敛精确上游月份，再由单条 Cost gate 证明全部 concrete child 的嵌入 lineage、dependency dirty state 与 parent `source_shards` 一致；不读取虚构 upstream `all` scope | 页面可展示；只有 gate 之后才可执行 ETag short-circuit、读取/写入 query-owned Redis 或 page SQL。projection 不写 Redis。 |
| `missing` | 没有对应 scope readiness 或 read model payload | 入队对应 scope refresh；页面/API 返回 refreshing 或 busy。 |
| `refreshing` | dirty scope pending/processing，或父 scope 正等待 shard | worker 继续处理；父 scope 不能 complete 为 fresh。 |
| `stale` / `source_mismatch` / `schema_mismatch` | source/schema/version 落后 | 入队重建；不得同步 rebuild 伪装 fresh。 |
| `failed` | worker refresh 失败或 readiness 记录失败 | 父 scope failed 阻断成本统计主体验；月份 shard failed 只标记局部 busy/attention。 |
| `unavailable` | repository/queue/worker dependency 不可用 | App Status blocked 或 busy，视父 scope/月 shard 和 dependency 关键性判定。 |

Refresh 触发来源：

- 银行流水、发票、ETC 导入确认。
- Workbench relation 确认/撤回、批量账务、往来款手动闭环。
- 待找发票规则、银行标签、税金认证、发票生命周期变化。
- 项目范围或项目状态设置变化。
- scope contract repair、App Health/backfill 运维任务。
- explorer page shape invalid，例如旧 Redis cache 缺少 `scope`、`view`、`summary`、`facets`、`rows`、`row_count`、`next_cursor`。
- `startup_stale_scan` 默认关闭，且不直接刷新成本统计 read model；只有后续 matching 结果真实变化并触发业务 lifecycle 时才影响成本。

父 scope 流程：

1. 收到 `active:all` 或 `all:all` refresh。
2. 检查同 project scope 的月份 shard readiness。
3. 缺失、stale 或 failed shard 通过 `ReadModelRefreshGateway` 入队。
4. 父 scope 写/返回 `refreshing`，不写 fake rows，不 complete dirty scope 为 fresh。
5. 所有 shard fresh 后，从 `read_model.cost_statistics_rows` 和 `read_model.cost_statistics_bank_flow_rows` 聚合父 scope metadata/逻辑 DTO，并计算需删除的过期月份 scope；禁止读取 child JSON arrays。
6. repository 在同一事务内通过现有 partial unique index 锁定唯一 active 父 dirty row；仅当其 `source_version` 与事件版本精确相等时，原子发布 parent snapshot 并删除过期月份 rows。拒绝发布时不写 SQL/Redis。
7. 仅用同一 `source_version` 成功完成父 dirty scope 后，父 scope 才可进入 fresh；若期间有新 dirty 版本则保持 `refreshing`，等待新事件收敛。

失败恢复：

1. 先看 `/api/app-health.app_status` 中 `cost_statistics.read_model_scopes[]`，区分父 scope 和月份 shard。
2. 对 legacy/invalid scope，先运行 `scripts/check-read-model-scope-contracts.py --json`，确认后再按 runbook `--apply`。
3. 对月份 shard failed，重跑对应 `active:YYYY-MM` 或 `all:YYYY-MM`；不要手工改父 scope。
4. 对父 scope failed/unavailable，确认所有月份 shard readiness 后重跑 `active:all` 或 `all:all`。
5. 若是 Redis/hot cache 问题，清 cache 后仍必须通过 SQL/readiness fresh gate，不得缓存 stale payload。
6. 旧 warmup job type 与 retry/recovery 入口已删除；恢复只能入队正式 `cost_statistics.read_model.refresh`，不得新建兼容 job 或直接写 payload/read model/Redis。
7. full-view loader 已删除；诊断必须读取 `get_cost_statistics_freshness_gate()` 的 published/latest version、status 与 stale reasons，再按 page/export/transaction 窄 I/O 排查。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-07-24 | 修复 `scope=all` parent false-fresh | 生产写后证明 parent 自身 `done` 不能代表 child lineage fresh。全期间访问先用一个 set-based Workbench canonical proof 找出 exact stale months，再由 Cost parent gate 比较 child Workbench/Bank Detail versions 与 `source_shards`；只 enqueue 漂移 child，child 完成后沿既有 month→parent 收敛。不新增 worker、queue、cache、表、HTTP 或写后 fan-out | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_cost_statistics_postgres_integration.py`、`tests/test_batch_accounting_postgres_integration.py`、`tests/test_read_model_manifest.py` |
| 2026-07-16 | 统一发布准备删除最后的 warmup 与旧 HTTP/full-view 链 | owner 证明与生产只读 active/attention=0 关闭删除门；root/project route、warmup job、full-view repository/query、projection Redis compat I/O 与相应 registry/mock/test 均删除。正式状态机只剩 durable refresh + narrow read I/O | `tests/test_cost_statistics_*`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_read_model_architecture_guards.py`、前端与 E2E 回归 |
| 2026-07-16 | bulk export/preview 改为有界 SQL 与 write-only XLSX | UI 状态与 HTTP 错误码不变；preview 只读 summary+8 行，download 门槛后每批 <=1000 并在结束时复核发布版本。中途变化继续表现为 409 non-fresh，不返回混合版本文件 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`tests/test_platform_runtime_boundary_guards.py` |
| 2026-07-16 | 删除成本 read model 全量 load 与无条件 save 旧表面 | 启动/全状态 snapshot 不再扫描或携带成本表；broad save 不再写成本 snapshot；port/manifest 只保留 scoped reads 与 source-version conditional publish。其他页面 read model、API、worker、schema 和 UI 不变 | `tests/test_postgres_state_store.py::PostgresStateStoreTests::test_postgres_full_state_snapshot_omits_cost_statistics_read_model`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_cost_statistics_does_not_retain_full_snapshot_load_or_unconditional_save_io`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_read_model_manifest.py` |
| 2026-07-16 | 删除进程内成本 read model owner | `CostStatisticsReadModelService`、Application startup snapshot 与 local persistence 已删除；invalidation 只投递 durable dirty scope，SQL 旧 rows 由 fresh gate 阻断而非请求期删除。queue 不可用时不报告已失效 | `tests/test_cost_statistics_runtime_service.py`、`tests/test_cost_statistics_derived_lifecycle_executor.py`、`tests/test_cost_statistics_api.py`、`tests/test_settings_data_reset_service.py`、边界 guards |
| 2026-07-16 | 请求期多 owner expected-source 链路收敛为单次依赖门禁 | explorer/page、当时保留的 full/month 和 detail 都先读取一次成本 gate；同一 SQL snapshot 内比较 cost、settings、Workbench、Bank Detail。旧 Application/runtime/query providers 与 Redis delete 已删除，任一 dependency 漂移都在 cache/rows 前锁页并入队；full/month 后续已删除 | `tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_runtime_service.py`、`tests/test_app_settings_service.py`、`tests/test_platform_runtime_boundary_guards.py` |
| 2026-07-16 | 页面 explorer 原子切换为 view-specific cursor | 原 endpoint 强制 `scope+view`，gate 后以 ETag/versioned Redis/单条 page SQL 返回 summary、facets 和每页最多 100 rows；切换 identity 清除旧可操作数据，cursor 绑定已发布版本。删除前端 full DTO/全量聚合及详情 local fallback，不新增 `/v2`、year scope、表、worker或索引 | `tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_sql_runtime.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` |
| 2026-07-16 | 两类大数组迁移为结构化行，详情改为 identity 点查，删除 projection Redis writer | `0107` 新增 bank-flow 行表和 OA/bank identity index；v9 parent snapshot 只保存 metadata，详情通过同一 freshness gate 后直接查 `project_scope + transaction_id`；cost projection 不写/删 Redis | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_repository_parses_grouped_display_amount_into_structured_cost_row`、`test_repository_gets_cost_statistics_transaction_by_indexed_identity`、`test_cost_statistics_sql_projection_rejects_legacy_redis_dependency`、`tests/test_postgres_migrations.py` |
| 2026-07-16 | 成本读取改为 PostgreSQL metadata gate 后才允许 Redis | `0105` 为 cost parent metadata 增加 nullable `published_source_version` 且不回填旧 completion history；历史 scope 必须经新版 conditional publish 建立 proof。explorer 先用单条 SQL 比较 parent metadata 与最新 durable dirty version/status，metadata 缺失或 non-fresh 都不触碰 Redis/page rows | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_api_reads_redis_hot_cache_after_postgres_gate_without_full_payload`、`test_cost_statistics_non_fresh_postgres_gate_blocks_redis_and_full_payload`、`test_repository_reads_cost_statistics_freshness_with_one_gate_query`、`test_repository_cost_statistics_gate_handles_done_failed_mismatch_and_pruned_history`、`tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_cost_statistics_freshness_gate_tracks_published_queue_version` |
| 2026-07-16 | 成本 worker 发布与完成改为 source-version 条件边界 | event 缺失/非法 `source_version` fail fast；旧事件只能在 repository 锁定的唯一 active dirty 版本精确相等时写 read model，发布后又出现新版本则条件完成失败并保持 `refreshing`。月分片只有发布与完成均成功才投递 parent；父级过期 shard 删除与 parent snapshot 在同一事务，拒绝发布不污染 SQL/Redis | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_repository_conditionally_publishes_cost_scope_and_obsolete_deletes_in_one_transaction`、`test_repository_rejects_stale_cost_publish_without_any_write`、`test_cost_statistics_refresh_handler_does_not_complete_or_fan_out_rejected_publish`、`test_cost_statistics_refresh_handler_keeps_new_dirty_when_completion_loses_race`、`test_cost_statistics_sql_projection_reports_rejected_publish` |
| 2026-07-15 | 三次 bank-detail 依赖读取收敛为一次跨月一致性快照 | v7 生产中两个成本事件 attempts 从 18/17 持续升至 48/47，证明三个 pure read 仍会观察不同 freshness 时点；v8 先提取 Workbench 正式关系流水 ID，再用一次 `REPEATABLE READ READ ONLY` snapshot 同时取得目标月全流水、跨月关系行和全部 scope signatures。目标月 rows 与跨月补充 rows 分离，旧三段成本读取链路删除，runtime worker 仍是唯一 dependency enqueue owner | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_defers_when_bank_detail_tags_are_not_fresh`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_snapshot_for_month_returns_target_month_rows_and_cross_month_relation_rows_in_one_read`、`tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests::test_get_tagged_snapshot_reads_target_month_and_cross_month_ids_in_one_repeatable_read_snapshot` |
| 2026-07-15 | 银行明细 dependency read 改为纯读，runtime worker 单点调度刷新 | v6 生产证明 active coalescing 仍存在 read-status/ack TOCTOU 窗口；source versions、transaction tags、month rows 三个读取统一 `require_fresh=False`，projection 显式 fail-closed，只有 runtime worker 能 enqueue dependency，消除读侧 I/O 污染和移动目标 | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_defers_when_bank_detail_tags_are_not_fresh`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_non_fresh_dependency_reads_do_not_enqueue_when_projection_owns_retry_boundary` |
| 2026-07-15 | 银行明细三个 fresh read gate 统一复用 ensure/wakeup reason | 成本月份 shard 的 source versions、transaction tags 和 month rows 全部使用 `downstream_bank_tag_read`；同 scope 已 pending/processing 时由统一 gateway coalesce，避免任一旧 cost-specific reason 重新 bump 移动目标 | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts`、`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_defers_when_bank_detail_tags_are_not_fresh`、`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_ensure_refresh_reason_does_not_bump_active_scope` |
| 2026-07-05 | 成本统计模块化 Close，删除旧 fallback 和 live export 链路 | API/query miss 只返回 `refreshing` 并入队 `cost_statistics.read_model.refresh`；runtime 不再持有 live explorer loader/read model upsert writer；live export helper 和 `ProjectDetailExportService` 删除；当时保留的 warmup 兼容桥已在统一发布准备收口中删除 | `tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_derived_lifecycle_executor.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_platform_runtime_boundary_guards.py` |
| 2026-07-03 | Workbench group payload 去重后的成本输入迁移 | 成本统计月份 shard 从 Workbench active generation 的结构化 `workbench_group_rows + workbench_rows` materialize 成本关系输入；`workbench_groups.payload` 不再包含 `oa_rows/bank_rows`，不能作为成员事实源 | `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts` |
| 2026-06-24 | 成本统计 full-state snapshot quarantine | 不改变成本统计业务/UI/read model/worker 状态流转；当时仅移除 broad `_persist_state(...)` 的旧全状态写入；显式进程内 persistence/startup owner 已由 05-13 删除，repository/state-store 全量 load 与无条件 save 表面已由 05-14 删除 | `tests/test_read_model_architecture_guards.py`、`tests/test_platform_runtime_boundary_guards.py` |
| 2026-06-23 | 补 read model manifest 合同守卫 | 不改变成本统计业务/UI/read model/worker 状态；锁定 `cost_statistics` 为 `partitioned_scoped_parent_rollup` 与 queryable parent aggregate，避免 `active:all` / `all:all` 被误改为 fan-out-only scope | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_cost_tax_and_turnover_manifest_preserve_summary_contracts` |
| 2026-06-18 | 成本统计 explorer 接入 read model payload contract validator | App Health 显示成本统计 fresh 时，API 仍会校验 explorer payload 必须包含当前前端 mapper 需要的 summary/time/project/expense type rows；旧 Redis cache 不直接返回，旧 SQL payload 返回 refreshing 并入队 `api_payload_shape_invalid`，避免页面泛化加载失败 | `PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_read_model_query_gateway -v`；`cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx` |
| 2026-06-18 | Browser e2e 补齐 Workbench 成本关系 fan-out | 真实 Chromium 证明 open/proposed candidate 不进入成本项目、金额或明细；确认 OA+bank+invoice 成本关系后，成本页重新读取并展示对应项目、金额、流水和详情；不改变业务/read model 状态机 | `cd web && npx playwright test e2e/cost-statistics-relation-fanout.spec.ts` |
| 2026-06-17 | Browser e2e 补齐项目下钻与导出错误反馈闭环 | 真实 Chromium 保护按时间首屏、按项目视图、`project_scope=all`、项目/费用类型/流水详情下钻、导出 preview 和 row-limit 错误反馈；不改变业务/read model 状态机 | `cd web && npx playwright test e2e/cost-statistics-flow.spec.ts` |
| 2026-06-12 | Workbench candidate 关系不再计入成本统计 | 成本归因 explorer、cost statistics SQL projection、月份 shard rows | `tests.test_cost_statistics_service`、`tests.test_cost_statistics_sql_runtime` |
| 2026-06-11 | 补齐测试闭环状态机 | 业务归因、UI、父 scope、月份 shard、App Status 和 worker 状态边界；此后已删除旧 live/read-model service tests，由 projection/runtime/architecture guards 接替 | `tests.test_project_costing_service`、`tests.test_project_costing_api`、`tests.test_cost_statistics_api`、`tests.test_cost_statistics_runtime_service`、`tests.test_cost_statistics_sql_runtime`、`tests.test_cost_statistics_derived_lifecycle_executor`、`tests.test_read_model_architecture_guards`、`tests.test_read_model_refresh_gateway`、`tests.test_runtime_worker_read_model_refresh_scopes`、`tests.test_read_model_scope_contract`、`tests.test_app_status_overview_service`、`tests.test_runtime_monitoring`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx` |
| 2026-06-10 | 成本统计 scope contract 修复 | 裸月份/裸 `all` 只能经 gateway 归一化，非法 scope 拒绝 | `tests.test_read_model_refresh_gateway`、`tests.test_runtime_worker_read_model_refresh_scopes`、`tests.test_read_model_scope_contract` |

---
phase: 05-cost-statistics-improvements
plan: 04
status: complete
completed_at: 2026-07-16
next_state: IMPLEMENTING
requirements:
  - COST-PERF-01
  - COST-FRESH-01
  - COST-LEGACY-01
---

# 05-04 执行摘要：结构化成本行、详情点查与旧投影缓存 writer 删除

## 结果

本切片已闭环 05-03 后最高风险的行存储和详情读取缺口：成本统计的 OA 配对成本行与全银行收支行现在分别由 `read_model.cost_statistics_rows` 和新增的 `read_model.cost_statistics_bank_flow_rows` 持久化。v9 parent/month metadata storage copy 会同时剥离 `time_rows` 与 `bank_flow_time_rows`；full explorer 逻辑 DTO 暂从两张结构化表重建，零行也不回退旧 parent/child JSON arrays。

transaction detail 继续先通过现有 cost-specific PostgreSQL freshness/business-source gate，fresh 后直接按 `project_scope + transaction_id` 查询两张结构化表，保持 OA cost row 优先于 bank-flow row的旧语义。该路径不调用 `get_cost_statistics_view()`、不读取 Redis、不加载 `active:all` arrays；non-fresh、not-found 和 tag-selection 可见性合同保持不变。

成本 projection 的旧 `cost_statistics:explorer:{scope}` 无版本 Redis set/delete 及 cost-local `_set_redis_json` 已删除。Redis 仍只由 query owner 在 PostgreSQL gate fresh 后通过共享 gateway 写 versioned payload；Tax Offset 的独立缓存 writer 没有修改。

复审还发现并补齐了一个直接相关的一致性遗漏：父 scope 的 `source_shards` 不再从“有业务行的月份”反推，而是读取全部 concrete month metadata。合法空月份因此仍进入 parent exact manifest，不会因零行从 freshness/Audit proof 中消失。

本轮未修改共享 `ReadModelQueryGateway`、全局连接池、Workbench/Bank Detail/Tax Offset 的 payload 或其他页面 read model。没有部署、生产访问/写入、stage、commit、branch、push 或 PR，也没有生成 05-05 prompt。唯一下一状态是 `IMPLEMENTING`。

## Grill-me / 反过度设计复核

| 问题 | 结论 |
| --- | --- |
| 是否新增通用 repository、v2 API、feature flag 或双读 | 不新增；扩展现有 cost repository port 和共享 repository 的 cost-owned 方法。 |
| 为什么需要新表 | `bank_flow_time_rows` 没有现有结构化 owner；新增一张表是消除大 JSON 和建立索引点查的最小完整边界。 |
| 是否一次性建立所有未来筛选索引 | 不建立；0107 只包含当前执行的 scope/time、parent rollup 与 transaction identity indexes。其他索引必须等 cursor SQL 和 EXPLAIN 证明。 |
| parent 是否重复物化 all rows | 不物化；parent 是 readiness/metadata owner，业务内容按 project scope 从 concrete month rows 读取。 |
| 是否保留旧 JSON fallback 以便迁移 | 不保留；schema v9 mismatch fail-closed 后重建，避免旧数据继续污染新链路。 |
| 是否已达到最终页面 SLO | 尚未；explorer/month 仍返回完整 DTO，请求期 expected-source providers、前端 all-prefetch/cache、Audit 和导出仍待后续唯一切片。 |

## 实现边界

- `0107_cost_statistics_structured_bank_flow_rows.sql`
  - 新增 cost-owned bank-flow rows 表、scope/time、parent rollup 和 identity indexes。
  - 给既有 OA cost rows 补 `project_scope + transaction_id` identity index。
  - 保持 API/worker/readonly/migrator 条件权限合同。
- `CostStatisticsReadModelRepositoryPort` / PostgreSQL repository
  - 新增 `get_cost_statistics_transaction(...)` 窄 I/O。
  - conditional publish 的现有 CAS transaction 同时写 metadata shell 与两类 month rows，并同步删除 obsolete scope 的两类 rows。
  - `get_cost_statistics_view()` 对 month 读 exact scope rows，对 parent 读同 project scope concrete rows；旧 JSON arrays 永不作为 fallback。
- `CostStatisticsSqlProjectionBuilder`
  - parent 从两张结构化 row tables 聚合；source shard manifest 从 month metadata 获取，覆盖空 shard。
  - 删除 cost projection 的 unversioned Redis writer；保留构造参数兼容现有 server assembly，待剩余旧模块删除切片移除调用面。
- `CostStatisticsQueryService`
  - detail 复用现有 freshness gate 后执行 identity point lookup。
  - 保持 tag selection、detail DTO、409/404 语义和 OA-row-first 规则。
- schema
  - `COST_STATISTICS_READ_MODEL_SCHEMA_VERSION` 升级为 `2026-07-cost-statistics-structured-rows-v9`；旧 v8 不能被新 gate 认证 fresh。

## 旧代码删除

已删除：

- parent builder 从 child `cost_statistics_read_models.payload.bank_flow_time_rows` 解析/聚合的路径；
- view loader 对 parent/month 两类数组的 JSON fallback；
- detail 的 `_require_fresh_explorer("all")` + 两次数组线性扫描；
- cost projection 的 `cost_statistics:explorer:{scope}` set/delete 和 cost-local Redis helper method。

仍保留且必须在后续有调用方证明的旧链路删除切片处理：legacy warmup job/retry、runtime local/persist dependencies、请求期 expected-source/tag-selection providers、前端 5 分钟 cache 与首屏 all-prefetch、完整 explorer/导出组装、旧 summary/project clients、`CostStatisticsService` / `CostStatisticsReadModelService` / `CostStatisticsRuntimeService` 的剩余调用面，以及 cost/tax 混合文件所有权。禁止用兼容 fallback 延长这些路径。

## 测试变化与七类覆盖

更新 `tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`tests/test_postgres_migrations.py`、`tests/postgres_test_utils.py`：

- migration 表、约束、grants、scope/parent/identity indexes；
- metadata `payload` 与 `raw_payload.normalized_payload` 均不含两类大 arrays；
- month bulk replace、parent/obsolete 两表删除、stale publish 零写；
- parent 只从结构化 rows 聚合，并通过 metadata 保留合法空 shard；
- full view 优先结构化 rows 且零行不回退旧 JSON；
- identity SQL 同时查询两张表并保持 OA cost row 优先；
- detail fresh path 不加载 full explorer，non-fresh 阻断点查，tag-excluded 保持 not-found；
- projection publish 成功/拒绝均不写旧无版本 Redis；
- 既有 explorer/detail/export API response shape 回归。

| 类别 | 结论 |
| --- | --- |
| 1. Business core unit | 当前金额/方向/归因公式未改变；OA-vs-bank-flow identity 优先级和 tag 可见性在 query/repository 测试中覆盖，不新增重复 core policy tests。 |
| 2. Service-layer | 适用；覆盖 projection、query service、repository port、两表 persistence、parent manifest 与 CAS 零写。 |
| 3. API contract | 适用；覆盖 detail fresh/non-fresh/not-found/tag selection 和既有 explorer/export DTO 回归。 |
| 4. Read model/cache/background job | 适用；覆盖 schema v9、migration、metadata quarantine、两表 publish/delete、parent/empty shard 和旧 Redis writer 删除。 |
| 5. Frontend interaction | 不适用；本轮 HTTP DTO 和 UI 行为未改变。 |
| 6. End-to-end business flow | backend projection→repository→query/API 组合路径已覆盖；真实 Browser/worker/migration E2E 留到 UI 与统一部署门禁。 |
| 7. Existing regression | 适用；成本 API/runtime、共享 gateway、Tax Offset、state store、repository boundary、worker registry 与 migration 回归已执行。 |

## 验证

- `python3 -m pytest -q tests/test_cost_statistics_sql_runtime.py tests/test_cost_statistics_api.py tests/test_postgres_migrations.py`：115 passed，29 subtests passed。
- `python3 -m pytest -q tests/test_read_model_query_gateway.py tests/test_tax_offset_sql_runtime.py tests/test_cost_statistics_read_model_service.py tests/test_cost_statistics_runtime_service.py tests/test_runtime_worker_read_model_refresh_scopes.py`：49 passed。
- `python3 -m pytest -q tests/test_runtime_worker_registry.py tests/test_state_store.py tests/test_postgres_repositories_boundaries.py`：96 passed，38 subtests passed。
- cost-specific platform guards + worker ownership：4 passed。
- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- `git diff --check`：通过。
- whole-repo literal/symbol scan：cost projection 已无 `cost_statistics:explorer:{scope}` writer；parent builder 已无 child bank-flow JSON read；detail 已无 all explorer scan。

扩展全文件 gate 的已知非本轮失败：

- `tests/test_platform_runtime_boundary_guards.py` 的 legacy Workbench row-detail owner guard 失败，来源是其他 thread 正在修改的 Workbench/server 工作区；本轮未触碰这些代码。
- `tests/test_read_model_manifest.py` 的 `oa_pending_payment` primary worker/registry 两个 subtest 失败，来源是其他 thread 正在修改的 OA pending worker/manifest 工作区；本轮未触碰这些代码。

当前环境未设置 `FIN_OPS_TEST_DATABASE_URL`，因此未执行真实 disposable PostgreSQL migration/runtime integration。按用户要求没有用生产数据库替代测试环境。

## 文档影响

已同步成本 boundary/state/tests/implementation notes、read-model contracts/boundary、runtime-worker boundary/governance 和唯一主设计文档。设计文档现在区分 05-02/05-03/05-04 已完成内容与 view cursor、overlay、Audit、旧模块删除、生产 SLO 等未完成门禁，不把结构化存储误报为最终性能闭环。

## 未完成风险

- explorer/month 仍重建并返回完整 DTO；`active:all` 首屏 payload 和前端 map/render 长尾尚未由 view-specific cursor API 消除。
- gate fresh 后仍调用现有 settings/Workbench/Bank Detail expected-source providers。必须先证明 Bank Detail/settings durable fan-out 和 Audit exact proof 完整，再删除请求期读取，不能以跳过校验换性能。
- export-preview/export 仍使用完整 explorer 和内存 workbook；流式、有界读取尚未实施。
- impeccable 轻量 inert overlay、App Status/focus/BFCache revalidation、前端 all-prefetch/cache/last-response-wins 删除尚未实施。
- cost-owned Audit repository、四组集合 SQL、当前 mismatch 根因与 `<=5s` 门槛尚未闭环。
- 剩余旧模块/route/client/warmup/runtime 调用面尚未全量删除。
- 未运行真实 PostgreSQL EXPLAIN、migration/rebuild、浏览器、worker drain、Audit 或生产性能门槛；这些只能在用户统一授权部署后执行。

## 共享工作树保护

共享工作树中其他 thread 正在修改 Workbench、OA pending payment、server、worker、前端和共享测试。本轮只编辑 05-04 允许的成本区块、新 migration、成本测试和受影响长期文档；未覆盖或回退并行 hunks。`0107` 写入前已确认 `0106` 属于其他 thread 且当前无更高 migration 冲突。没有任何 git 暂存、提交或部署。

## 唯一下一状态

`IMPLEMENTING`

理由：05-04 已关闭 parent/child 大数组事实源、详情 all-scan、空 shard manifest 和旧 projection Redis writer，但总目标仍有 view-specific cursor/首屏 payload、请求期 source I/O、前端遮罩、Audit、导出、全量旧模块删除和最终生产性能证据。按主控规则，本摘要不生成下一 prompt；下一 prompt 必须根据本次完成状态与届时共享工作树事实重新决定。

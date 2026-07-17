---
phase: 05-cost-statistics-improvements
plan: 03
status: complete
completed_at: 2026-07-16
next_state: IMPLEMENTING
requirements:
  - COST-PERF-01
  - COST-FRESH-01
  - COST-LEGACY-01
---

# 05-03 执行摘要：成本读取 PostgreSQL freshness gate before Redis

## 结果

本切片已闭环“统一事实源变化已持久入队，但旧 Redis 仍可能被直接返回”的读侧漏洞。CodeGraph 证明旧路径为 `get_explorer -> ReadModelQueryGateway.load -> _get_cached_payload`，Redis hit 发生在任何 PostgreSQL dirty/status 读取之前。

当前 explorer/month 请求必须先通过 cost-specific repository port 执行一条 metadata-only PostgreSQL gate。gate 读取 parent schema/business source metadata、独立 `published_source_version`，并通过 lateral lookup 读取该 scope 最高 durable dirty version/status。metadata 缺失、pending/processing/failed、published/latest 不等、schema/source mismatch 都返回空的 `202 refreshing` envelope，并在不访问 Redis/full rows 的前提下经既有 refresh gateway 入队。只有 gate fresh 后才复用现有 `ReadModelQueryGateway` 读取 Redis 或 full payload。

`0105` 增加 nullable `published_source_version` 与 cost-only latest-version partial index。版本只由 05-02 的 conditional publish 在原 CAS transaction 内与 snapshot/rows/obsolete deletes 一起写入。历史 `done` completion 不足以证明旧 snapshot 曾原子发布，因此 migration 不回填；旧 scope 会 fail-closed 并由新版 worker 重建一次。这样比信任历史状态更简单，也不会把旧数据误认证为 fresh。

本轮未修改共享 `ReadModelQueryGateway` 或其他页面 query/read-model 行为，未部署、未访问或写入生产、未 stage/commit/branch/push，也未生成 05-04 prompt。唯一下一状态是 `IMPLEMENTING`。

## Grill-me / 反过度设计复核

| 问题 | 结论 |
| --- | --- |
| 是否修改共享 gateway 的默认顺序 | 不修改；那会扩大所有页面回归面。成本 query owner 通过窄 repository-port gate opt in。 |
| 是否新增分布式锁、缓存层或通用 freshness 框架 | 不需要；复用 PostgreSQL dirty queue、现有 query gateway 和 refresh gateway。 |
| runtime version 是否混入业务 `source_versions` | 不允许；独立 metadata 列只承担 CAS proof 与 cache namespace token。 |
| 是否可信回填历史 done version | 不可信；旧 completion 存在 05-02 前的写入竞态，故保持 `NULL` 并 fail-closed rebuild。 |
| hot path 是否仍重复查 dirty | 不再；旧 `get_cost_statistics_view()` dirty SQL 已删除，gate 是唯一 cost read-status owner。 |
| 是否已经达到最终性能 SLO | 尚未；gate 后仍有现有 expected-source provider 查询，full JSON/rows、分页/详情/导出和前端预取仍待迁移。 |

## 实现边界

- `0105_cost_statistics_freshness_gate.sql`
  - 新增 nullable、非空时非负的 `published_source_version`；不做历史数据回填。
  - 新增仅覆盖 `scope_type='cost_statistics'` 的 latest durable version partial index。
- `CostStatisticsReadModelRepositoryPort` / PostgreSQL repository
  - 新增 `get_cost_statistics_freshness_gate(scope_key)` 窄 I/O。
  - 单条 SQL 返回 parent metadata + latest durable dirty record。
  - conditional publish 在既有 transaction 内写 published version。
  - `get_cost_statistics_view()` 删除旧 dirty/status 查询，仅组装 parent/rows payload。
- `CostStatisticsQueryService`
  - explorer/month 先 gate；non-fresh 不读取 Redis/full payload。
  - fresh cache key 加入 published version token；token 不参与业务 source-version 比较，也不进入 API payload。
  - gate fresh 后继续复用现有 payload validator、source/schema 比较和短 TTL Redis。
- 其他 read model
  - `ReadModelQueryGateway`、Tax Offset、Turnover Ledger 无代码变化；共享回归通过。

## 旧代码删除

已删除：

- `get_cost_statistics_view()` 内 cache miss 才执行的 `job.read_model_dirty_scopes` 查询；
- full-payload loader 内的 `refresh_status` / `dirty_scope` 推导；
- 测试中的“成本 Redis hit 不应发生任何 SQL”错误合同，替换为“先一个 metadata gate、零 full-payload SQL”。

仍保留且必须由后续旧链路切片证明后删除：legacy cost warmup job/retry、runtime local/full snapshot persistence、projection legacy Redis key writer、full-payload explorer/detail/export 线性扫描、旧 frontend cache/all-prefetch/route-client 路径。

## 测试变化与七类覆盖

更新 `tests/test_cost_statistics_sql_runtime.py`、`tests/test_cost_statistics_api.py`、`tests/test_postgres_migrations.py`：

- fresh gate 必须先于 Redis；Redis hit 不执行 full payload/rows；
- published version 改变会旋转 cache key；
- pending/processing/failed/version mismatch/metadata `NULL` 阻断 Redis 与 full payload；
- missing gate 入队并返回 202 empty envelope；
- done version match、done-history retention 后无 dirty record仍可 fresh；
- conditional publish 同事务写 published version，stale publish 仍零写入；
- migration 是 nullable fail-closed、无历史回填、cost-only index；
- memory API repository 实现相同 gate contract。

| 类别 | 结论 |
| --- | --- |
| 1. Business core unit | 不适用；金额、标签、归因和 scope 业务规则未变。 |
| 2. Service-layer | 适用；覆盖 query service、repository port、PostgreSQL repository 与 publish transaction。 |
| 3. API contract | 适用；覆盖 fresh 200、missing/non-fresh 202、empty payload、stale reasons 和 refresh enqueue。 |
| 4. Read model/cache/background job | 适用；覆盖 gate、Redis 顺序、published/dirty versions、history retention 与 migration。 |
| 5. Frontend interaction | 不适用；本轮未修改 UI。 |
| 6. End-to-end business flow | route→gate→Redis/full repository 组合路径已覆盖；浏览器与真实 worker→UI E2E 留给后续 UI/统一部署验收。 |
| 7. Existing regression | 适用；成本 API/runtime、共享 gateway、Tax Offset、Turnover Ledger 与 migration 全量回归通过。 |

## 验证

- `PYTHONPATH=backend/src:. python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_cost_statistics_api tests.test_postgres_migrations`：110/110 通过。
- `PYTHONPATH=backend/src:. python3 -m unittest tests.test_read_model_query_gateway tests.test_tax_offset_sql_runtime tests.test_turnover_ledger_query_service -v`：42/42 通过。
- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- `git diff --check`：通过。
- CodeGraph / whole-repo scan：cost query 是新 gate 的唯一生产调用边界；`get_cost_statistics_view()` 已无 dirty/status SQL；共享 gateway 与其他页面 query service 零 diff。

## 文档影响

已同步 cost boundary/state/tests、read-model contracts/boundary 与主设计文档。设计文档明确记录当前只完成 PostgreSQL-first gate，仍不声称最终 query-count/SLO 已达成；历史 proof 不回填、统一部署后必须先重建成本 scopes。

## 未完成风险

- fresh gate 后仍调用现有 business expected-source providers，包含 settings、Workbench 与 Bank Detail version I/O；必须在证明 durable fan-out/Audit 完整后收敛为已发布 metadata，不能直接跳过校验。
- parent/full JSON、`cost_statistics_rows` 全量加载、详情线性扫描、导出内存组装和缺少 view-specific cursor/point lookup 仍是主要性能瓶颈。
- 前端 `active:all`/导出参考数据首屏预取、5 分钟 cache、last-response-wins 与 impeccable inert overlay 尚未实施。
- cost-owned Audit repository、四组集合校验、当前 Audit failure 根因和性能尚未闭环。
- legacy/live/local/warmup/full-payload/旧 route-client 代码仍未全量删除。
- 尚未运行真实 PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)`、浏览器 Audit/E2E、生产并发竞态或门槛量测；按用户要求只能在统一部署后执行。

## 共享工作树保护

共享工作树中的其他 thread 在本轮继续修改 Workbench、OA pending payment、worker、server、migration、前端与共享测试。本轮只编辑 cost query/port、共享 repository 的 cost methods、`0105`、对应 cost tests/docs，以及 migration test 的独立方法；未覆盖或回退并行 hunks。`0104` 与后续 `0106` 均属于其他 thread，`0105` 编号当前无冲突。没有进行任何 git 暂存、提交或部署。

## 唯一下一状态

`IMPLEMENTING`

理由：05-03 已关闭 Redis 绕过 durable freshness 的正确性漏洞，但总目标仍有结构化 view API/rows、请求期 source-version I/O 收敛、前端轻量遮罩、Audit、全量旧代码删除和最终性能证据。按主控规则，本摘要不生成下一 prompt；下一 prompt 必须根据本次完成状态与届时共享工作树事实重新决定。

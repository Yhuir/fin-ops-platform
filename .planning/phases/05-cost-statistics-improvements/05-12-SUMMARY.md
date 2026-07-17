---
phase: 05-cost-statistics-improvements
plan: 12
status: passed
completed_at: 2026-07-16
next_state: IMPLEMENTING
deployment_status: DEPLOYMENT_HOLD
---

# 05-12 Summary：单次依赖鲜度门禁并删除请求期多 owner provider

## 结果

`PASS`。成本统计 page explorer、内部 full explorer、month summary 和 transaction detail 在读取 ETag、Redis 或结构化 rows 前，
现在只调用一次成本专属 PostgreSQL freshness gate。该 statement 在同一数据库 snapshot 内读取：

- cost metadata、`published_source_version` 与当前 durable dirty status/version；
- App Settings 中成本需要的 bank tags、bank account mappings 与 tag selection 小型片段；
- concrete month 的 Workbench active generation source versions/current dirty；
- concrete month 的 Bank Detail scope schema/status/source versions/current dirty。

query 只对这一 gate snapshot 做纯映射，不再通过 Application/runtime 串行调用 settings、Workbench 或 Bank Detail owner。
事实源数据变化但页面仍显示旧值的问题在该边界 fail-closed：当前 settings 或 upstream source versions 与已发布成本
source versions 不一致时，query 在 payload/cache I/O 前返回空的 `refreshing` envelope 并入队正式 refresh。

本轮没有部署、没有访问生产，也没有把本地 I/O 收敛冒充生产 SLO 达标。

## 模块与 I/O

- 新增 `cost_statistics_source_versions(...)` 纯 helper，成为 worker projection 与 query gate 的唯一业务 source-version字段构造合同；
  parent `all` 明确不包含虚构的 Workbench/Bank Detail `all` dependency。
- `AppSettingsService.cost_statistics_tag_selection_payload_from_settings(...)` 只消费 caller 已读取的 settings mapping，不访问
  repository/state store；route 的 tag-rule 管理 I/O 不变。
- PostgreSQL gate 仍只通过一次 `fetch_one`，所有 lateral 分支都是 singleton/scope point lookup；没有扫描 Workbench groups/rows、
  Bank Detail rows 或 canonical facts。
- concrete month 对 cost/Workbench/Bank Detail pending、processing、failed、published/dirty version drift、缺失 source versions、
  Bank Detail schema/status异常和 settings JSON shape异常全部 fail-closed。
- `active:all/all:all` 继续只依赖 cost parent metadata/current dirty 与 settings source vector，不查询 Workbench/Bank Detail `all`。
- cache key 继续绑定 schema、业务 source versions、cost published version、tag token 和 query fingerprint；旧 versioned namespace
  不再命中并由 TTL 自然退出。

## 旧代码删除证据

已删除且未保留 shim/fallback：

- Application `_cost_statistics_expected_source_versions(...)`；
- Application `_cost_statistics_source_versions(...)`；
- Application `_cost_statistics_workbench_source_versions(...)`；
- Application `_cost_statistics_bank_detail_source_versions(...)`；
- Application dead `_delete_cost_statistics_redis_cache(...)` delegate；
- `CostStatisticsRuntimeService.source_versions_provider`、`expected_source_versions(...)`、`delete_redis_cache(...)` 及 enqueue 时
  按当前 expected key 删除 Redis 的逻辑；
- `CostStatisticsQueryService.tag_selection_provider` 和 request-time `_cost_tag_selection_payload()` settings reload；
- 只为上述 Application/runtime provider 存在的 API/SQL runtime 测试 fixtures。

whole-repo production/tests scan 只剩 architecture guard 中用于禁止这些符号回归的字符串。静态 guard 同时禁止 legacy
`CostStatisticsService`、本轮 provider 和 Redis delete 路径回归。

## 测试与验证

- `tests/test_cost_statistics_sql_runtime.py`：
  - 四种 query 入口分别只调用一次 gate，non-fresh 不触碰 page/full/detail payload；
  - 当前 settings version 改变会锁住旧 cost snapshot；
  - gate SQL 同时包含 settings、Workbench 与 Bank Detail dependency lookups；
  - dependency pending/failed、非法 settings、空 source versions 和发布版本漂移均 fail-closed；
  - shared helper 对 concrete month/parent 的字段合同一致。
- `tests/test_app_settings_service.py`：纯 tag-selection mapper 只依赖传入 gate snapshot。
- `tests/test_cost_statistics_api.py`：fixture 改为 gate snapshot + production pure helper，不恢复 Application source shim；既有 API、
  export、tag rule、permission 与 detail contract 全部回归。
- `tests/test_cost_statistics_runtime_service.py`：锁定 refresh enqueue 不依赖 provider 或主动 Redis delete。
- `tests/test_platform_runtime_boundary_guards.py`：禁止本轮全部旧 symbol/wiring 回归。

已执行：

- 成本/App Settings/边界主回归：`316 tests`，`OK`；
- 共享 query gateway/freshness/worker scope 回归：`46 tests`，`OK`；
- `bash scripts/verify.sh lint`：通过；
- `bash scripts/verify.sh docs`：通过；
- `git diff --check`：通过；
- production import smoke：`cost_statistics_source_versions`、projection builder 与 `Application` 同进程导入通过。

## 七类责任

1. Business core unit：适用；shared source-version helper、parent/month合同、settings version drift 和 tag selection纯映射已覆盖。
2. Service-layer：适用；query/runtime/repository/App Settings/Application装配与旧 provider删除已覆盖。
3. API contract：适用；`200/202/304`、detail `409/404`、export/tag/permission shape 由完整成本 API 回归保护。
4. Read model/cache/background job：适用；dirty/dependency状态、schema/source mismatch、versioned cache namespace 与 scope合同已覆盖；
   worker实现未修改。
5. Frontend component：不适用；页面、Impeccable轻量遮罩、drawer、权限和交互均未修改。
6. End-to-end business flow：适用；本地 projection/shared source contract → gate → query/route 链路已覆盖；真实 worker/生产 DB
   因部署冻结未运行。
7. Existing regression：适用；316 个目标/边界测试与 46 个共享 gateway/freshness/scope 测试全部通过，其他页面代码零行为变更。

## 文档影响

已更新成本统计 README、boundary I/O、state machine、tests、implementation notes、唯一主设计，以及 read-model contracts。
长期事实现在明确：cost query 使用单次 dependency-bound gate；projection/query 共用纯 source-version合同；旧 Application/runtime/query
provider 与主动 Redis delete 不再是当前模块 I/O。

## 下一状态与剩余风险

`next_state=IMPLEMENTING`。本轮没有生成 05-13；下一 prompt 只能基于 05-12 的真实 PASS 重新选择一个剩余有界风险。
仍未关闭的主要项目包括：

- 真实 PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)`、连接获取与页面 p95/p99；
- 成本 Audit 剩余固定 SQL 组及生产 `<=5s`、mismatch 与连续 pass；
- 历史 warmup/background-job/local read-model dependencies 与 `CostStatisticsReadModelService` 的独立迁移；
- 流式导出和仍有真实调用的内部 full loader/API 清理。

整体 `/goal` 继续 active，状态为 `DEPLOYMENT_HOLD`。本轮未部署、未创建或切换分支，未 stage/commit/push/PR，未
stash/reset/clean。只有用户明确说“允许统一部署”后，才进入 migration/rebuild、生产 EXPLAIN/SLO 和 Audit 证据阶段。

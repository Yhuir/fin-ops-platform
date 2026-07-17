---
phase: 05-cost-statistics-improvements
plan: 19
status: passed
completed_at: 2026-07-16
next_state: IMPLEMENTING
deployment_status: DEPLOYMENT_HOLD
---

# 05-19 Summary：worker unchanged 判定移除 full-view I/O

## 结果

`PASS`。`CostStatisticsSqlProjectionBuilder` 的 `source_versions_unchanged` 快路径已从
`get_cost_statistics_view(...)` 迁到 cost-local `get_cost_statistics_scope_metadata(...)`。新的 repository I/O 只按唯一
`scope_key` 点查 `read_model.cost_statistics_read_models`，仅返回 `scope_key/entry_count/source_versions`。

因此，当输入没有变化时，worker 不再为了决定“无需重建”而读取 parent payload、两张结构化成本明细表、dirty queue、App Settings、
Workbench 或 Bank Detail。source versions 完全相等时仍返回原 `entry_count/row_count/refresh_kind/skipped/skip_reason`；missing、非法或
mismatch metadata 仍 fail closed 为正常重建。dirty scope 正在 processing 时，判等仍只比较已经发布的 parent source versions，不会因读取
页面 freshness status 而错误击穿幂等 skip。

本轮没有部署、没有访问生产、没有运行生产 worker/EXPLAIN/SLO，也没有
branch/stage/commit/push/PR/stash/reset/clean。没有修改 route/server、API response shape、前端、shared gateway、queue/worker wiring、
migration/schema/index、Tax Offset、Workbench、Bank Detail或其他页面 read model。

## Grill-me / Ponytail 复审

- 这不是额外的平台抽象：只增加一个 cost repository port method、一个三字段 point query和既有 shared repository 的委托；没有新 DTO
  class、缓存、表、索引、队列、feature flag、fallback 或通用 metadata framework。
- 没有机械复用页面 freshness gate。该 gate 包含当前 dirty、settings、Workbench、Bank Detail 的多个 dependency lookup，适合页面防旧数据，
  但 projection unchanged 只需要已发布 parent 的 source versions；复用会增加无关 I/O并让 processing 状态击穿幂等 skip。
- 没有为了“删旧代码”破坏仍有效合同。CodeGraph + whole-repo scan 证明 projection 的 full-view 引用已归零；production 剩余引用只有
  `CostStatisticsQueryService` 的两处，分别支撑旧 `GET /api/cost-statistics` 和
  `/api/cost-statistics/projects/{project_name}`。按既定门禁，它们必须等覆盖正常财务周期的生产 access log 或全部 owner 明确确认后再删除。
- 删除了 `UnchangedCostStatisticsSaveRecorder.get_cost_statistics_view(...)`、payload fixture 与 `views` tracking；测试只暴露新的 metadata
  contract，不保留 worker fallback。
- projection 输出、source-version 组成、read-model schema 和发布数据均未改变，因此不需要 schema version bump 或 migration。

## 代码与合同变更

- `CostStatisticsReadModelRepositoryPort` 新增 `get_cost_statistics_scope_metadata(...)`，manifest 显式登记。
- `PostgresSummaryReadModelRepository` 用一次 parent point lookup 返回三字段；`PostgresReadModelRepository` 只做窄委托。
- projection unchanged 判定只调用 metadata port；`AttributeError`/missing/mismatch 都不 skip，不回退 full view。
- 模块 README、boundary I/O、tests、implementation notes、read-model contracts 与唯一性能/freshness/遮罩设计已同步记录 05-19 边界和剩余删除门禁。

## 测试与验证

新增/更新：

- `test_repository_reads_cost_statistics_scope_metadata_without_payload_or_row_scans`：锁定一次 point query、精确三字段、零 payload/join/dirty/
  dependency SQL 与零 `fetch_all`。
- 两个 projection unchanged 回归：锁定相等时 skip、dirty-processing 时仍 skip；新增 mismatch metadata 不 skip。
- port、manifest 与 physical SQL owner 测试登记新方法。
- `test_cost_statistics_projection_unchanged_check_reads_scope_metadata_only`：静态禁止 projection 恢复 full-view 或 payload I/O。
- 旧成本 API/repository 回归继续保护 month/project HTTP合同和 scoped read model 行为。

已执行并通过：

- SQL runtime、manifest、platform boundary：`286 tests`，`OK`；
- 成本 API + PostgreSQL repository boundary unittest：`19 tests`，`OK`；
- metadata mismatch 增补后的成本 SQL runtime复跑：`57 tests`，`OK`；
- PostgreSQL repository boundaries pytest：`34 passed`；
- 修改 Python 文件 `py_compile`：通过；
- `bash scripts/verify.sh lint`：通过；
- `bash scripts/verify.sh docs`：通过；
- `git diff --check`：通过；
- CodeGraph 最终 index：1050 files / 38100 nodes / 93893 edges，无 pending-sync banner；
- whole-repo caller scan：projection 为零 `get_cost_statistics_view`；query owner 精确保留两处生产兼容调用。

第一次 unittest 命令未设置 `PYTHONPATH=backend/src`，三个模块在 collection 阶段因找不到 `fin_ops_platform` 而退出；修正环境后上述测试全部
通过。该记录不是产品测试失败，没有修改代码来绕过 import contract。

## 七类责任

1. Business core unit：适用；source-version exact equality、mismatch、entry/row count 与 skip envelope 已覆盖。
2. Service-layer：适用；projection、repository port/SQL owner/manifest和一次 metadata I/O 已覆盖。
3. API contract：shape/status 未改；成本 API回归通过，旧 month/project合同保持。
4. Read model/cache/background job：适用；worker unchanged、parent metadata事实源、dirty-processing 与零 cache/queue/row scan已覆盖。
5. Frontend component/interaction：不适用；页面与轻量锁未修改。
6. End-to-end business flow：本轮没有新增跨模块业务流；projection→port→repository contract与旧 API integration已覆盖。真实 worker drain和生产
   写后鲜度属于统一部署后证据，当前不可冒充完成。
7. Existing regression：适用；manifest、physical SQL owner、repository boundary、旧 HTTP caller保留和其他页面零实现 diff已保护。

## 下一状态与剩余风险

`next_state=IMPLEMENTING`，整体 `/goal` 继续 active；部署状态仍为 `DEPLOYMENT_HOLD`。本轮只生成并执行 05-19，不预生成 05-20。

仍未关闭：

- 旧 summary/project API及其 full-view loader：等待生产 access-log/owner证据后迁移真实 caller并全量删除 route/DTO/tests/port/repository/helper，
  禁止 fallback；
- 历史 `cost_statistics_cache_warmup` job/delegates：等待统一部署窗口证明 production active job 为零；
- `cost_tax_sql_projection.py` 混合 cost/tax 文件所有权：需要单独、跨 owner且有冲突审计的切片，不能混入当前小改动；
- 真实数据 `EXPLAIN (ANALYZE, BUFFERS)`、worker skip耗时、write-to-fresh p99、页面/API p95/p99、Audit `<=5s`、Browser遮罩与跨页面隔离证据；
- 统一发布前仍需等待其他 thread 收口并冻结唯一 release artifact。

只有用户明确授权“允许统一部署”后，才进入协调部署和生产证据阶段；当前局部 PASS 不能标记整体 `/goal` 完成。

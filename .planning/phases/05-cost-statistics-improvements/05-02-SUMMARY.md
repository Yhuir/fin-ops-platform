---
phase: 05-cost-statistics-improvements
plan: 02
status: complete
completed_at: 2026-07-16
next_state: IMPLEMENTING
requirements:
  - COST-FRESH-01
  - COST-AUDIT-01
  - COST-LEGACY-01
---

# 05-02 执行摘要：成本 worker source-version 条件发布

## 结果

本切片已闭环成本统计 worker 的写侧版本竞态。实现复用 PostgreSQL durable dirty scope 的 `source_version`，只增加一个 cost-specific conditional publish I/O；没有新增表、migration、依赖、锁服务、平台状态机或其他页面分支。

当前成本 event 必须带合法非负整数版本。month/parent builder 显式接收该版本；repository 复用现有 partial unique index，在一个事务内锁定该 scope 唯一 `pending` / `processing` dirty row，只有版本精确相等才写 snapshot/rows。父 scope 的 obsolete month 删除和 parent snapshot 同属该条件事务。发布成功后，handler 再以同一版本条件完成 dirty scope；月 scope 只有发布与完成都成功才 fan-out parent。

旧 event 遇到更高 dirty 版本时，发布返回 false 且零 read-model 写入；projection 不写 Redis，handler 不完成 dirty、不 fan-out，返回 `refreshing`。若新版本在 publish 后才到达，条件完成返回 false，新 dirty 保持 active，月 scope 同样不 fan-out。

本轮未部署、未访问或写入生产、未 stage/commit/branch/push，也未生成 05-03 prompt。唯一下一状态是 `IMPLEMENTING`。

## Grill-me / 反过度设计复核

| 问题 | 结论 |
| --- | --- |
| 是否需要新表或分布式锁 | 不需要；dirty scope 已提供单调版本和 PostgreSQL 行锁事实源。 |
| 是否修改共享 queue 语义 | 不需要；复用现有 versioned completion，只在 cost repository 增加条件发布。 |
| 是否保留旧 worker fallback | 不保留；handler 只调用显式 month/parent builder。 |
| parent cleanup 是否需要独立事务 | 不允许；obsolete 删除已并入同一版本条件发布事务。 |
| 是否影响其他页面/read model | 没有新增跨页面行为；Tax Offset 共享文件回归 21/21 通过。 |
| 是否已经完成全部成本目标 | 没有；读侧 freshness-before-Redis、结构化 view API、Audit、前端遮罩和全量旧代码删除仍由后续 bounded prompt 处理。 |

## 实现边界

- `CostStatisticsReadModelRefreshService`
  - 保留合法版本 `0`；缺失、布尔、负数和非整数版本 fail fast。
  - 删除 worker 对通用 `rebuild_cost_statistics_read_model_scope` 的 fallback。
  - conditional publish 拒绝时不 complete、不 fan-out。
  - completion 始终携带 event `source_version`；返回 false 时保持 `refreshing`。
  - 月 scope 只在 conditional completion 成功后 enqueue parent。
- `CostStatisticsSqlProjectionBuilder`
  - month/parent rebuild 显式接收 tenant/version。
  - parent obsolete scope 先只计算集合，不在 CAS 前持久化。
  - repository 拒绝发布时不写新 Redis，也不删除 obsolete Redis key。
- `CostStatisticsReadModelRepositoryPort` / PostgreSQL repository
  - 增加窄的 `publish_cost_statistics_read_models(...) -> bool`。
  - 在一个 transaction 内通过现有 partial unique index 锁定唯一 active cost dirty row，避免扫描和排序历史 terminal rows。
  - 版本相等才写 snapshots、month rows 和 obsolete deletes；不匹配或缺失时零写入。
  - 旧无版本 `save_cost_statistics_read_models(...)` 暂时保留给已识别的非 worker 调用方，禁止回到 worker 链路；最终删除由旧代码清理切片负责。

## 测试变化与七类覆盖

更新 `tests/test_cost_statistics_sql_runtime.py`，新增或加强：event version `0`、非法版本、匹配版本单事务发布、active dirty 缺失或版本更高时零写入、parent cleanup 原子性、拒绝发布不缓存、拒绝发布/完成竞态不 fan-out、versioned completion、正常 month/parent 收敛。

| 类别 | 结论 |
| --- | --- |
| 1. Business core unit | 不适用；本轮未改变金额、归因、标签或 scope 业务规则。 |
| 2. Service-layer | 适用；覆盖 handler、projection、port、repository 和 completion/fan-out。 |
| 3. API contract | 不适用；HTTP status、DTO 和权限未改变。 |
| 4. Read model/cache/background job | 适用；覆盖版本 CAS、零写入、Redis 阻断、parent cleanup 和新 dirty 保留。 |
| 5. Frontend interaction | 不适用；本轮未改页面。 |
| 6. End-to-end business flow | 本切片不新增跨模块行为；service→repository 组合测试覆盖写侧链路，最终 canonical write→UI/Audit E2E 仍属后续。 |
| 7. Existing regression | 适用；成本 SQL/runtime、queue、worker scope、bootstrap 和共享 Tax Offset 回归均通过。 |

## 验证

- `PYTHONPATH=backend/src:. python3 -m unittest tests.test_cost_statistics_sql_runtime -v`：38/38 通过。
- `PYTHONPATH=backend/src:. python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_runtime_queue tests.test_runtime_worker_read_model_refresh_scopes tests.test_runtime_bootstrap -v`：119/119 通过。
- `PYTHONPATH=backend/src:. python3 -m unittest tests.test_tax_offset_sql_runtime tests.test_postgres_repositories_boundaries -v`：21/21 通过。
- `bash scripts/verify.sh lint`：通过。
- `bash scripts/verify.sh docs`：通过。
- `git diff --check`：通过。
- whole-repo target scan：cost handler 无无版本 completion 或 generic builder fallback；parent obsolete persistence 不再发生在条件发布前。

## 文档影响

已同步 cost module boundary/state/tests、read-model contracts/boundary、runtime-worker boundary 与 worker governance。设计文档不需要为本切片增加新层；本实现正是其中的 durable version/CAS 边界。

## 未完成风险

- 当前读链路仍可能先查 Redis；必须在后续切片完成 PostgreSQL freshness gate before Redis，才能闭环“统一事实源已变但页面仍显示旧数据”。
- parent JSON 全量 payload、详情线性扫描、首屏 `active:all` 预取和前端 5 分钟 cache 尚未移除。
- cost-owned Audit repository、Audit 性能/正确性和页面 Audit 通过尚未实施。
- impeccable 轻量 inert 遮罩、last-response-wins 和各 UI 状态测试尚未实施。
- live/local/warmup/full-payload/旧 route-client/混合 cost-tax owner 等全部旧代码尚未完成迁移删除。
- 尚未运行全量 backend/frontend/E2E 或生产竞态/SLO；这些必须在后续本地切片与统一部署窗口完成。

## 共享工作树保护

共享工作树中其他 thread 持续修改 Workbench、OA pending payment、migration、worker wiring 和测试文件。本轮没有改动这些业务。`postgres_repositories/read_models.py` 当前同时包含其他 thread 的 Workbench initial-page hunk；本轮只拥有 cost conditional-publish 相关 hunk，未覆盖或回退并行变更。没有进行任何 git 暂存或提交。

## 唯一下一状态

`IMPLEMENTING`

理由：05-02 的写侧竞态门禁已经通过，但总目标仍有明确的读侧性能/freshness、Audit、UI 和旧代码删除切片。按主控规则，本摘要不生成下一 prompt；下一 prompt 必须由本次完成状态和届时共享工作树事实重新决定。

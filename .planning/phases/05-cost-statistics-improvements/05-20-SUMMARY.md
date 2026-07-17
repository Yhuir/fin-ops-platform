---
phase: 05-cost-statistics-improvements
plan: 20
status: passed
completed_at: 2026-07-16
next_state: READY_FOR_COORDINATED_DEPLOY
deployment_status: DEPLOYMENT_HOLD
---

# 05-20 Summary：拆除 cost/tax 混合投影旧模块

## 结果

`PASS`。旧 `cost_tax_sql_projection.py` 已删除，成本统计与税金抵扣的 SQL projection owner 已分别迁入
`cost_statistics_sql_projection.py` 和 `tax_offset_sql_projection.py`。生产 worker 与直接测试只 import 新 owner；没有保留旧 module
空壳、re-export、compat shim、动态 import 或 fallback。

本轮是所有权拆分，不是业务重写：两个 builder 的公共 constructor/method、SQL、source versions、repository/cache I/O、返回值、worker
event、read model、API 与页面合同保持不变。Tax Offset 只做机械迁移；成本 module 不 import tax owner，税金 module 不 import cost owner。
三个极小的纯格式 helper 分别保留为 module-private code，没有为了去重新增 base class、共享 utils、projection framework、package、表、索引、
队列、配置或依赖。

本轮没有部署、没有访问生产，也没有 branch/stage/commit/push/PR/stash/reset/clean。共享 `worker.py` 中其他 thread 的未提交修改保持原状；
本轮只改变 cost/tax projection import owner。

## Grill-me / Ponytail 复审

- 模块边界已闭合：成本 projection 只拥有成本事实输入与 cost read-model 输出；税金 projection 只拥有发票/认证输入与 tax read-model 输出。
- I/O 没有被“抽象化”或搬入共享层；拆分只消除了错误的共同文件所有权，不增加运行时 hop、serialization、cache 或查询。
- 生产 caller 已由 CodeGraph 与 whole-repo scan 定位为 `app/worker.py`；直接测试 caller 同轮迁移。current backend/tests 中旧 module
  只剩静态 guard 对“文件必须不存在/worker 不得 import”的负向字符串，运行时代码零引用。
- 本轮没有越权删除仍受生产证据门禁保护的两类旧链路：历史 `cost_statistics_cache_warmup` 必须先证明 active job 为零；旧
  summary/project HTTP 与 full-view loader 必须先取得正常财务周期 access log 或全部 owner 明确确认。两者都不得靠本地猜测删除。
- 这不是过度设计：两个业务 owner、两个现有 builder、一个生产 assembly import；没有第三个共享 owner或兼容层。

## 代码与文档变更

- 删除 `backend/src/fin_ops_platform/services/cost_tax_sql_projection.py`。
- 新增 `backend/src/fin_ops_platform/services/cost_statistics_sql_projection.py`，唯一拥有
  `CostStatisticsSqlProjectionBuilder`。
- 新增 `backend/src/fin_ops_platform/services/tax_offset_sql_projection.py`，唯一拥有
  `TaxOffsetSqlProjectionBuilder`。
- 更新 `backend/src/fin_ops_platform/app/worker.py` 和成本/税金直接测试的 import。
- 新增 architecture guard，锁定旧文件不存在、两个新 owner 不交叉、worker 无旧 import/fallback。
- 同步成本统计、税金抵扣、backend refactor inventory/audit/state log 与主性能/freshness/轻量遮罩设计中的 current owner 和删除状态。

## 测试与验证

新增/更新：

- `test_cost_and_tax_sql_projection_owners_are_split_without_legacy_module`：锁定旧 module 物理删除、builder 唯一 owner、跨 owner 零引用、
  worker 只 import 新路径。
- 成本 projection rules、SQL runtime、API、read-model architecture/runtime-state guards 更新到成本新 owner。
- 税金 SQL runtime 更新到税金新 owner；既有 shard/source-version/repository/cache/refresh 行为回归继续保护零业务变化。

已执行并通过：

- 首轮成本 rules/SQL/API、税金 SQL、worker bootstrap、runtime-state、read-model architecture 与 owner guards：`158 tests`，`OK`；
- 税金 service/read-model/API、worker refresh scopes 与 platform guards 扩展回归：`248 tests` 中 `247 passed`，唯一失败见下方共享工作树阻断项；
- 最终成本/税金 projection 与新 owner guard 定向复跑：`87 tests`，`OK`；
- 两个新 module 与 worker `py_compile`：通过；
- `bash scripts/verify.sh lint`：通过；
- `bash scripts/verify.sh docs`：通过；
- `git diff --check`：通过；
- current-code scan：旧 module 在 backend/web/tests/scripts/deploy 中零运行时 import；只保留负向 guard 的路径与禁止字符串。

扩展回归中唯一失败为
`PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline`：共享 dirty
`app/worker.py` 当前有 `7` 个 `pair_relation_service` 字符串，既有 removal baseline 为 `6`。该 token 与 cost/tax projection 拆分无关，
本轮 diff 没有新增、删除或迁移其业务调用；它来自并行 thread 正在修改的 Workbench/OA worker 区域。为避免污染其他 thread，本轮没有把 baseline
从 6 放宽到 7，也没有修改该链路。统一发布冻结 release artifact 前，必须由对应 owner 恢复 guard 全绿。

## 七类测试责任

1. Business core unit：适用；成本归集规则与 Tax Offset projection/source-version 既有单元回归通过，业务输出未变。
2. Service-layer：适用；两个 builder、repository/cache 调用、refresh service 与 worker assembly 已覆盖。
3. API contract：合同未改；成本与税金直接 API 回归已执行，shape/status 保持。
4. Read model/cache/background job：适用；cost/tax projection、refresh handler、runtime-state、worker bootstrap/import 与 architecture guard 已覆盖；
   queue/registry/schema 未修改。
5. Frontend component/interaction：不适用；前端、轻量遮罩与用户交互均未修改。
6. End-to-end business flow：本轮没有新增业务流；现有 projection -> repository 与 worker assembly integration 足以保护 owner 迁移。真实生产
   worker drain/页面读取留给统一部署后的证据阶段。
7. Existing regression：适用；成本、税金、runtime bootstrap、architecture/platform guards 同轮覆盖；共享工作树唯一非本任务失败已隔离并登记，
   未用宽松断言掩盖。

## 下一状态与发布门禁

本功能的本地可执行切片进入 `READY_FOR_COORDINATED_DEPLOY`；整体 `/goal` 继续 active，发布状态立即保持
`DEPLOYMENT_HOLD`。本轮只生成并执行 05-20，不预生成下一个 prompt。

等待用户明确授权“允许统一部署”且其他 thread 全部收口后，主控才可根据唯一冻结 release artifact 生成下一条部署/验证 prompt。进入部署前必须先：

1. 复跑全仓约定校验并关闭上述共享 `pair_relation_service` baseline 红项；
2. 证明生产历史 `cost_statistics_cache_warmup` active job 为零，再删除该旧 job/delegate/current tests/docs；
3. 取得旧 summary/project HTTP 的 access-log/owner 证据，再决定是迁移真实 caller还是删除 route/DTO/full-view port/repository/tests；
4. 协调部署、迁移/重建 read model、queue drain 与回滚检查；
5. 在真实数据上完成 PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)`、API/browser cold/warm/view/filter p95/p99、`active:all`、Audit
   `<=5s`、write-to-fresh p99、轻量遮罩和其他页面隔离证据。

在这些生产门禁关闭前，不得标记整体 `/goal` complete，也不得宣称生产性能/Audit 已闭环。

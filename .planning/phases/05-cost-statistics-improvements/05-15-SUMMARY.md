---
phase: 05-cost-statistics-improvements
plan: 15
status: passed
completed_at: 2026-07-16
next_state: IMPLEMENTING
deployment_status: DEPLOYMENT_HOLD
---

# 05-15 Summary：成本导出有界查询与 write-only XLSX

## 结果

`PASS`。成本统计 bulk `export-preview` / `export` 已退出完整 explorer payload：preview 只读取完整 SQL summary 与最多 8 行；
下载先以 summary 判断既有 20,000 行同步导出上限，再按每批最多 1,000 行读取结构化 cost/bank-flow rows，并直接追加到
`Workbook(write_only=True)`。服务不再构造完整 entries list、完整 rows list或普通 workbook。

导出开始前仍执行成本 freshness gate；XLSX 序列化完成后再次比较 `schema_version`、`source_versions` 与
`published_source_version`。生成期间发布版本变化时，bytes 被丢弃并通过既有 non-fresh 409 合同 fail-closed，不会交付混合版本文件。

本轮没有部署、没有访问生产、没有 Git 写操作，也没有修改成本页面 query、前端、Audit、worker、数据库 schema、route、权限或其他页面
read model。

## 生产边界与性能设计

- 唯一新增 I/O 是成本 port 的 `get_cost_statistics_export_page(...)`；输入显式包含 scope、month/date range、project、expense type、
  selected tag、row shape、offset/page size，输出只包含可选 summary、有界 rows 与 next offset。
- PostgreSQL repository 将单次 page size 硬限制在 1..1,000；preview 调用固定为 8。time/bank-tag 读取 bank-flow rows，
  month/project/expense 读取 OA cost rows，筛选与聚合均在 SQL 内完成。
- 首批 summary 保留完整集合的 source/result row count、distinct transaction count、总额、收支金额/笔数和费用类型数；preview
  返回样本行数不会污染完整汇总语义。
- transaction 单笔导出继续走 freshness gate + identity 点查，没有被机械迁入 bulk 分页边界。
- 最终文件仍按既有 route 合同返回 bytes；没有引入异步导出、HTTP streaming、server cursor、长事务、通用 export framework、
  新 dependency、table、migration、job、cache 或 feature flag。
- 该改动减少大导出峰值 Python 对象和 workbook 内存，并把单次数据库行 payload 变为硬上限；真实 PostgreSQL 执行时间、内存峰值和
  生产 SLO 仍须在统一部署后测量，不能以本地结构性证明替代生产证据。

## 旧代码删除与隔离证据

已删除且不保留 fallback、shim 或 compatibility alias：

- `_filtered_entries_from_read_model(...)`；
- 只为旧 bulk full-payload 导出服务的 `_project_aggregate_rows(...)` 与 `_directional_summary_from_entries(...)`；
- 普通 `_project_detail_workbook(...)` 及其全量 rows/entries 构造路径；
- bulk export 对 `_require_fresh_explorer(...)` / `get_cost_statistics_view(...)` 的依赖。

whole-repo production/tests symbol scan 对上述旧方法只有 architecture guard 中的禁止回归断言；不存在 production caller。manifest 与
port 测试证明新 export I/O 只暴露在 cost repository boundary，未扩散到 Workbench、Tax Offset、Bank Detail、共享 gateway 或其他页面。

## 测试与验证

新增或加强的关键证明：

- preview 只请求 8 行，不读取 full view，summary 仍代表完整筛选集合；
- bulk 每批最多 1,000，只有首批请求 summary，结束时重新读取 gate；
- 版本在行读取后变化会抛 `export_snapshot_changed`，不返回 XLSX；
- 超过 20,000 行在 workbook 创建前失败；
- PostgreSQL SQL contract 覆盖 month/date/project/expense/tag filters、结构化表选择、summary、offset/limit 与 row shape；
- API workbook、列、sheet、filename、筛选和既有错误合同保持；
- architecture guard 禁止 full explorer payload、旧 helper 和普通 workbook 回归。

已执行并通过：

- `tests.test_cost_statistics_api`、`tests.test_cost_statistics_sql_runtime`、`tests.test_read_model_manifest`、
  `tests.test_platform_runtime_boundary_guards`：`303 tests`，`OK`；
- `tests/test_postgres_repositories_boundaries.py`：`34 passed`；
- 修改后的 service/repository/port `py_compile`：通过；
- `bash scripts/verify.sh lint`：通过；
- `bash scripts/verify.sh docs`：通过；
- 旧 helper exact symbol scan：production caller 为零；
- `git diff --check`：通过。

## 七类责任

1. Business core unit：适用；筛选、聚合、完整 summary、同步行上限与版本冲突失败分支已覆盖。
2. Service-layer：适用；cost port、manifest、bounded page/batch、write-only serialization 与前后 gate 复核已覆盖。
3. API contract：适用；preview/download、filename、sheet、400 row-limit、409 non-fresh 与 permission/route 既有回归通过。
4. Read model/cache/background job：适用；fresh gate、SQL rows、版本变化、full payload/Redis 不参与 bulk export 已覆盖；worker 未修改。
5. Frontend component/interaction：不适用；本轮没有修改页面、轻量遮罩、交互或前端 API client。
6. End-to-end business flow：适用；本地 read-model fixture 到 preview/download 再到 workbook 解析已覆盖；真实 PostgreSQL/worker/browser
   因部署冻结未运行。
7. Existing regression：适用；成本 API/runtime、manifest、repository boundary、page/detail 隔离和其他页面 port 排除已覆盖。

## 文档影响

已更新成本统计 README、boundary I/O、tests、state machine、implementation notes、唯一性能/freshness/遮罩设计，及 read-model
contracts/boundary/tests/implementation notes和 API contract。产品业务口径、route shape与 app 页面拓扑未改变，因此产品 spec和 app architecture
无需修改。

## 下一状态与剩余风险

`next_state=IMPLEMENTING`，整体 `/goal` 继续 active，状态为 `DEPLOYMENT_HOLD`。本轮只生成并执行 05-15，不提前生成下一 prompt。

仍未关闭：

- 历史 `cost_statistics_cache_warmup` job type、App Health/retry delegates：只有在统一部署窗口证明 production active job 为零后才能删除；
- 成本 Audit 剩余 SQL、真实 mismatch、连续 pass 与 `p95 <= 5s`；
- 内部 month/summary 的 scoped full view 剩余调用方，以及能否在不改变其合同的前提下删除；
- 真实 PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)`、索引命中、连接池排队、导出内存/耗时、页面冷/暖/筛选 p95/p99、
  `active:all <= 500ms` 与 operation-to-fresh `p99 <= 3s`；
- 统一 release 后的 migration/rebuild、跨页面隔离、浏览器 Audit和轻量阻断遮罩验收。

只有用户明确授权“允许统一部署”后，才进入统一部署和生产证据阶段。本轮未创建或切换分支，未 stage/commit/push/PR，也未
stash/reset/clean。

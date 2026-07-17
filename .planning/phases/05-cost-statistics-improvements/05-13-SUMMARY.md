---
phase: 05-cost-statistics-improvements
plan: 13
status: passed
completed_at: 2026-07-16
next_state: IMPLEMENTING
deployment_status: DEPLOYMENT_HOLD
---

# 05-13 Summary：删除进程内成本 read model 旧模块并收敛失效 I/O

## 结果

`PASS`。`CostStatisticsReadModelService` 的 module/class/test、Application startup snapshot/field、显式 local persistence callback，
以及 runtime 的 local clear/invalidate/persist 依赖均已删除。成本统计不再拥有 SQL read model 之外的第二状态 owner。

projection 直接构造现有 repository port 接受的单 scope write model，并继续走原有 source-version 条件发布。runtime invalidation
只经 `ReadModelRefreshGateway` 写 PostgreSQL durable dirty scope；返回值只包含 gateway 实际接受的 scope。queue 不可用时返回空，
derived lifecycle 不再把目标 scope 误报为已失效。

本轮没有部署、没有访问生产、没有 Git 写操作。正式 PostgreSQL cost read-model table/repository、共享 gateway、其他页面 read model、
前端遮罩和 Audit owner 均未改变。

## 模块与 I/O

- `COST_STATISTICS_READ_MODEL_SCHEMA_VERSION` 现在只由既有 `cost_statistics_source_versions.py` 定义；query、runtime、projection
  与测试从同一 owner 导入。为避免 repository package 反向导入 Application runtime，依赖较重的 source-version 常量在纯 helper
  调用边界内延迟导入；同进程 production import smoke 已通过。
- projection 直接提交 `scope_key`、`scope_type`、`schema_version`、`month`、`project_scope`、`generated_at`、`cache_status`、
  `entry_count`、`payload`、`source_scope_keys` 和 `source_versions`，没有复制旧 service 或新增 adapter。
- 全局 invalidation 精确投递 `active:all`、`all:all`；月份 scope 经现有 normalization 扩展为 `active/all × YYYY-MM`。
- invalidation 不删除 SQL rows。新 durable dirty version 先让 freshness gate 阻断旧 rows，只有 worker 条件发布成功后页面才重新 fresh。
- derived lifecycle 保留既有外部 `deleted_counts` 字段兼容，但其计数现在表示成功进入 durable queue 的规范 scope 数，不再表示
  本地 dict 删除数。
- 历史 `cost_statistics_cache_warmup` job bridge 只识别、转换为正式 refresh 并终结旧 job；没有 local snapshot/read-model I/O。

## 旧代码删除证据

已删除且未保留 shim/fallback：

- `backend/src/fin_ops_platform/services/cost_statistics_read_model_service.py`；
- `tests/test_cost_statistics_read_model_service.py`；
- `CostStatisticsReadModelService` class/import/fixture；
- Application `_cost_statistics_read_model_service` startup load、dependency key、constructor wiring；
- Application `_persist_cost_statistics_read_models_best_effort(...)`；
- runtime `read_model_service`、`persist_read_models`、`_persist_read_models`、local clear/invalidate/snapshot 分支；
- projection 为单 scope publish 临时实例化整套旧 service 的路径；
- API/settings-reset tests 中的旧本地 owner 替身与 snapshot 断言；
- 已失效的 direct-fresh architecture allowlist 项。

production/tests whole-repo scan 的相关命中只剩静态 guard 字符串，用于禁止旧 module/class/server field/persistence helper 回归。
长期文档中的其他命中均明确标记为“已删除”或历史迁移记录，不是当前入口。

正式 PostgreSQL repository 的 `load/save/publish_cost_statistics_read_models` 本轮保留。它是当前表级持久化合同，不是被删除的
进程内 service；是否进一步缩窄旧 `load/save` 调用面，需要下一独立 prompt 的 caller proof，不能在本轮猜测删除。

## 测试与验证

新增或更新的保护包括：

- runtime queue-only invalidation：精确 scope、normalize/dedupe、queue unavailable 不伪报成功；
- derived lifecycle：只有 durable enqueue 成功才报告 `invalidated_scopes`/job，generic fallback 失败返回零；
- SQL projection：直接 repository publish 的单 scope shape与 conditional publish不变；
- 成本 API：测试 repository 自持 SQL view mapping，不重造旧 service，同时完整回归 query/detail/export/permission；
- settings reset：不再写/读 local cost snapshot，改为断言精确 durable refresh；
- Application/state-store/import：启动无旧 field，schema constant owner和 production同进程导入稳定；
- architecture/boundary guards：旧 module/test/class/import/server field/runtime dependency/local persistence回归即失败。

已执行：

- 成本 API/runtime/SQL/derived lifecycle/settings reset/state store/architecture guards：`358 tests`，`OK`；
- shared refresh gateway/runtime worker scope/scope contract/derived lifecycle：`61 tests`，`OK`；
- 单独复现并修正失效 direct-fresh allowlist 后：`1 test`，`OK`；
- production/test modules `py_compile`：通过；
- `Application`、runtime、schema constant、projection builder 同进程 import smoke：通过；
- `bash scripts/verify.sh lint`：通过；
- `bash scripts/verify.sh docs`：通过；
- `git diff --check`：通过。

## 七类责任

1. Business core unit：不适用；归因、金额、项目范围、状态转换和 tag 规则均未改变。
2. Service-layer：适用；runtime durable invalidation、derived lifecycle accounting、Application 组合根和旧 owner删除已覆盖。
3. API contract：适用；成本 API 的成功、non-fresh、detail/export、permission和响应 shape由完整回归保护。
4. Read model/cache/background job：适用；conditional publish、dirty-before-read、queue unavailable、legacy job bridge和 parent/month scope已覆盖。
5. Frontend component/interaction：不适用；页面、Impeccable轻量遮罩、drawer、权限和前端 API未修改。
6. End-to-end business flow：适用；本地 lifecycle → durable queue recorder → SQL projection publish → query gate链路已覆盖；真实 worker、
   PostgreSQL和浏览器因部署冻结未运行。
7. Existing regression：适用；358 项目标/边界回归与 61 项共享 refresh/scope/lifecycle回归全部通过，且静态 guard防止旧链路复活。

## 文档影响

已更新成本统计 README、boundary I/O、state machine、tests、implementation notes、唯一性能/freshness/遮罩设计，及 read-model
contracts/boundary和测试闭环依赖地图。当前事实明确为：成本只有正式 PostgreSQL repository owner，失效只有 durable gateway I/O；
历史记录被标注为已由 05-13 取代。

## 下一状态与剩余风险

`next_state=IMPLEMENTING`，但整体 `/goal` 继续 active，状态为 `DEPLOYMENT_HOLD`。本轮只生成并执行了 05-13，不生成 05-14。

仍未关闭：

- 历史 `cost_statistics_cache_warmup` job type、App Health/retry delegates：必须在统一部署窗口证明 production active job 为零后再删除；
- 正式 repository 旧 `load/save` 方法是否已无 production caller：需要独立 whole-repo/caller proof；
- 真实 PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)`、连接获取、worker drain、页面 load p95/p99 与 operation-to-fresh p99；
- 成本 Audit 剩余 SQL、真实 mismatch 修复、`<=5s` 和连续通过证据；
- 同步大导出/内部 full loader 的剩余性能与旧调用面。

只有用户明确授权“允许统一部署”后，才进入 migration/rebuild、生产性能和 Audit验证。本轮未创建或切换分支，未
stage/commit/push/PR，也未 stash/reset/clean。

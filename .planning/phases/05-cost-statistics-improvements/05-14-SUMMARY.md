---
phase: 05-cost-statistics-improvements
plan: 14
status: passed
completed_at: 2026-07-16
next_state: IMPLEMENTING
deployment_status: DEPLOYMENT_HOLD
---

# 05-14 Summary：删除成本 read model 全量 load 与无条件 save 旧表面

## 结果

`PASS`。成本统计已经退出应用全状态 snapshot：启动 load 不再扫描整张
`read_model.cost_statistics_read_models`，broad `save(payload)` 不再接受或回写成本 read-model key，本地
`ApplicationStateStore` 与 `StateStoreProtocol` 也不再声明成本 snapshot I/O。

成本 worker 的唯一正式写边界现在是带 `tenant_id + scope_key + source_version` 的
`publish_cost_statistics_read_models(...)` conditional publish；正式读取只保留 freshness/page/view/transaction 和
Workbench source-version 的 scoped I/O。没有新增 adapter、fallback、表、migration、job、cache 或第二条路径。

本轮没有部署、没有访问生产、没有 Git 写操作。其他页面 read model、API/DTO、worker event/registry、Audit、前端遮罩、数据库
schema 和业务规则均未改变。

## Caller proof 与模块边界

- CodeGraph/caller 检查确认：旧 full load 的 production caller 只有 `PostgresStateStore._load_snapshot_payload(...)`；旧 unconditional
  save 的 production caller只有 `PostgresStateStore.save(...)`。两者均属于本轮删除的 broad state 分支。
- 当前 projection 只调用 conditional publish；query/page/detail/export 均不依赖旧 load/save。
- `CostStatisticsReadModelRepositoryPort` 当前 I/O 为：freshness gate、page、单 scope view、transaction identity、Workbench source versions
  与 conditional publish。
- manifest 已登记上述全部当前 port 方法；没有把成本特例扩散到 Tax Offset、Workbench、Bank Detail 或共享 query/refresh gateway。
- 正式 PostgreSQL cost tables 和内部 scoped view 保留；本轮删除的是错误的全表/无版本访问表面，不是 read-model 数据本身。

## 旧代码删除证据

已删除且未保留 shim、deprecated alias 或 compatibility branch：

- cost repository port 的 full-table load 与 unconditional save wrapper；
- PostgreSQL summary repository 的 full-table loader、无条件 saver及共享 facade delegates；
- `PostgresStateStore` 的成本显式 load/save、startup snapshot key 和 broad save branch；
- `ApplicationStateStore` 的成本本地 pickle load/save 及 non-empty-state key；
- `StateStoreProtocol` 与 read-model manifest 的旧合同；
- 仅保护旧本地 persistence、full loader 或 direct save 行为的 fixtures/tests；
- Workbench test spy 中无 consumer 的旧协议占位。

仍有价值的 structured rows、bank-flow rows、parent metadata、obsolete delete 与 batch-write 断言已迁到真实 conditional publish。
static guard 明确禁止旧方法定义、facade delegate、state-store key、protocol/manifest method 与 direct-save fixture 回归。

`backend/`、`tests/`、`scripts/`、`web/` 的 exact symbol scan 对两个旧方法均为零命中；历史 planning/docs 只保留明确“当时存在、
已由 05-14 删除”的迁移证据。

## 测试与验证

已执行并通过：

- `tests.test_cost_statistics_api`、`tests.test_cost_statistics_sql_runtime`、Postgres/local state store、manifest 与 platform guards：
  `372 tests`，`OK`；
- repository boundary 与 Postgres state-store integration：`34 passed, 9 skipped`；skip 为未配置真实 integration database 的既有条件，
  不是隐藏失败；
- cost runtime/derived lifecycle、refresh gateway、worker scopes、scope contract：`48 tests`，`OK`；
- read-model architecture guards 与完整 `test_workbench_v2_api`：`48 tests`，`OK`；
- 修改后的 production/test modules `py_compile`：通过；
- whole-repo production/tests 旧方法 exact/definition scan：零命中；
- `bash scripts/verify.sh lint`：通过；
- `bash scripts/verify.sh docs`：通过；
- `git diff --check`：通过。

## 七类责任

1. Business core unit：不适用；金额、归因、项目范围、标签、权限和状态转换均未改变。
2. Service-layer：适用；repository port、Postgres/local state store、protocol、manifest 与 conditional publish 边界已覆盖。
3. API contract：适用但无新合同；完整成本 API/SQL runtime 回归保护既有 `200/202/304/409`、detail/export/permission shape。
4. Read model/cache/background job：适用；CAS publish、两类 batch rows、parent metadata、obsolete delete、stale reject、启动无全表 load
   与 broad save 排除已覆盖。历史 warmup bridge没有在本轮改动。
5. Frontend component/interaction：不适用；页面、Impeccable 轻量遮罩、drawer、前端 API 与交互合同均未修改。
6. End-to-end business flow：适用；本地 projection → conditional publish → fresh gate/query 组合链路已覆盖；真实 worker/PostgreSQL/浏览器
   因部署冻结未运行。
7. Existing regression：适用；成本 API/runtime/state store、共享 manifest/scope/gateway、read-model architecture 和 Workbench fixture 回归通过，
   其他页面 port/合同没有修改。

## 文档影响

已更新成本统计 README、boundary I/O、state machine、tests、implementation notes、唯一性能/freshness/遮罩设计，以及 read-model
README/boundary/contracts/tests/implementation notes和 canonical-facts 相关历史校准。当前事实源统一表述为：成本 broad state I/O 已删除，
正式写入只走 conditional publish，读取只走 scoped port。

## 下一状态与剩余风险

`next_state=IMPLEMENTING`，但整体 `/goal` 继续 active，状态为 `DEPLOYMENT_HOLD`。本轮只生成并执行了 05-14，不生成 05-15。

仍未关闭：

- 历史 `cost_statistics_cache_warmup` job type、App Health/retry delegates：必须在统一部署窗口证明 production active job 为零后再删除；
- 成本 Audit 剩余 SQL、真实 mismatch、连续 pass 与 `p95 <= 5s`；
- 同步大导出/内部 full view 的剩余调用面与高数据量性能；
- 真实 PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)`、连接池排队、worker drain、页面冷/暖/筛选 p95/p99、`active:all <= 500ms`
  和 operation-to-fresh `p99 <= 3s`；
- 统一 release 后的 migration/rebuild、跨页面隔离与浏览器 Audit/遮罩验收。

只有用户明确授权“允许统一部署”后，才进入统一部署和生产证据阶段。本轮未创建或切换分支，未 stage/commit/push/PR，也未
stash/reset/clean。

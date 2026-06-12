# Read Model 状态机

> 修改 `Read Model` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。页面自己的 UI 状态在页面模块维护；本文件维护共享 freshness、dirty scope、worker readiness 和非法状态。

## 业务状态

- 当前状态：read model 是写模型之外的派生投影；写入事实不直接改页面投影，而是通过 dirty scope/outbox 触发 worker 重建。
- 状态事实源：
  - PostgreSQL durable queue：`job.outbox_events`、`job.read_model_dirty_scopes`
  - Readiness 证明层：`read_model.app_status_readiness`
  - Workbench 例外：active generation/readiness metadata
- 允许流转：
  - business write -> lifecycle/dirty scope -> outbox event -> worker processing -> projection publish -> readiness fresh
  - API miss/stale -> `ReadModelQueryGateway` 返回 refreshing payload -> `ReadModelRefreshGateway` enqueue refresh
  - worker failure -> readiness failed/unavailable -> App Status busy/blocked
- 禁止流转：
  - 页面或 service 绕过 freshness gate 读取旧 projection 并标记 fresh
  - Redis/RabbitMQ 被当作 read model 状态事实源
  - 业务 service 直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`
  - fan-out-only refresh 结果写假 fresh readiness

## UI 状态

本模块没有独立页面，但定义页面消费 read model 状态的共享语义：

- loading：页面首次请求或后台 refresh 状态未返回时展示局部 loading；不得写入业务事实。
- empty：只有 `read_model_status=fresh` 且 rows/summary 为空时，才能展示真实空态。
- error：API/worker/readiness failed 或 unavailable 时展示可恢复错误/blocked，不得吞失败。
- stale/refreshing：stale、missing、source/schema mismatch 或 dirty scope pending 时，页面必须展示刷新语义；不能把空 rows 当真实无数据。
- permission disabled/hidden：权限由业务 API/session 模块维护；read model 状态不能替代权限判断。

## Read Model / Worker 状态

- `fresh`：projection/readiness 与期望 schema/source version 匹配，可以对外展示 payload，也可以写 fresh-gated Redis cache。
- `missing`：没有可用 projection/readiness；API 应返回 refreshing 语义并入队 refresh。
- `refreshing`：dirty scope pending/processing、worker 等待 shard、source/schema stale 后已入队；页面显示刷新中或后台刷新提示。
- `stale`：内部 freshness 判定不匹配；公开 API 通常映射为 refreshing 语义并带 stale reasons。
- `failed`：worker 或 rebuild 失败，readiness 记录 last error；App Status 可升级 busy/blocked。
- `unavailable`：依赖、runtime snapshot 或 critical worker 不可用；App Status blocked，不得解释为 ready。

## refresh 触发来源

- API miss
- schema version mismatch
- source version missing/mismatch
- 业务写入后的 `DerivedDataLifecycleService` dirty cascade
- `startup_stale_scan` 之后的 workbench matching dirty worker 间接更新；startup scan 本身默认不运行，且不得直接刷新用户可见 read model
- worker shard fan-out / parent scope convergence
- 手工 runtime scope contract 清理后的 replacement scope

## 失败恢复

- API miss/stale 可以重新 enqueue refresh。
- Worker failed/unavailable 由 App Health 暴露具体 scope、last error 和 worker 状态。
- 旧生产 scope contract 由 `scripts/check-read-model-scope-contracts.py` dry-run 检查；dry-run 必须输出 repair manifest，列出 legacy/invalid cost statistics 行、已被 later done/fresh readiness 覆盖的历史 outbox failure，以及 current-effective 未覆盖 failure。
- `--apply` 只能受控清理非规范旧状态并补投可归一化 replacement scope；apply 必须记录 audit event，并带可回滚 manifest。current-effective 未覆盖 failure 不自动删除、不伪造 fresh，只能调查原因后 requeue、修复 worker 或修复投影。
- 生产真实库修复前必须保留 dry-run 报告，不能直接热改 runtime 表。

## 非法状态

- `read_model_status=fresh` 但缺少对应 readiness/source version 证明。
- `read_model_status=fresh` 但 dirty scope 仍 pending/processing 且覆盖同一 scope。
- API 返回空 rows 且不带 refreshing/stale/missing 语义，却实际没有 fresh projection。
- Redis cache 命中绕过 fresh gate。
- RabbitMQ transport 成为状态事实源。
- 未覆盖的 failed/dead_lettered/publish_failed outbox event 被删除或忽略，但没有 later done/fresh readiness 证明。
- 新增 read model/worker 后未同步 registry、manifest/systemd env、tests、docs。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-12 | 补齐 repair manifest 与 current-effective failure 保留规则 | dry-run/apply 可审计区分历史已覆盖失败和当前未覆盖 blocker；禁止假同步 | `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract tests.test_platform_runtime_boundary_guards tests.test_runtime_queue_ops -v` |
| 2026-06-11 | 补齐共享 read model 状态机 | 明确 fresh/missing/refreshing/stale/failed/unavailable、非法状态和恢复路径 | `bash scripts/verify.sh docs` |

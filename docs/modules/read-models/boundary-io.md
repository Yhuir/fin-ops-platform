# Read Model 模块边界与 I/O

日期：2026-07-03

## 模块化状态

- 状态：Read Model 模块化 PSCIP-L4 closed；full external PSCIP-L4 / 高性能全域闭环 open
- 当前边界可信度：high
- 目标边界：所有当前 App Status read model 通过 manifest、scope policy、refresh gateway、runtime worker、freshness/status gate 和 operation barrier 形成可验证闭环。
- 当前闭环：14 个当前 App Status read model 已完成 Read Model 模块化 PSCIP-L4，`workbench`、`bank_account_balance`、`pending_invoice`、`cost_statistics` 以显式例外语义闭环。
- 当前阻塞风险：2026-07-03 release `pscip-l4-workbench-group-row-min-20260703` 已把 Workbench 月分片 warmed targeted 1s direct SLO 收敛到 `10/10` pass，`source_version 3124..3133` p95/max `890.808ms`；成本统计 `active:2026-02` targeted `5/5` pass，p95/max `938.124ms`。但 full critical grouped 1s smoke 仍未闭环，最新一轮 `15/16` pass，`search:2026-03` handler `3087.035ms` / enqueue `3399.122ms` fail；targeted search `4/5` pass 但仍有一次 `1425.676ms` handler 长尾。固定 write scenario/ticket 后的 full gate 仍缺当前 release 真实 confirm/withdraw/no-OA withdraw 写样本；因此性能专项仍 open，不能声明高性能全域闭环。
- 旧代码删除条件：legacy/local compat path 仍可保留为明确隔离路径；删除前必须证明对应页面 API、worker、测试和生产脚本不再调用该路径。

## 闭环证据

- 最终报告：`.planning/refactors/modular-io-boundaries/analysis/read-model-main-final-closure-report-2026-06-28.md`
- 生产证据：`.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-evidence-2026-06-28.md`
- 远端闭环提交：`c771b894 docs: close read model production evidence`
- 生产 runtime 证据：`/health/ready` ready，scope contract `ok=true`，`violation_count=0`，current uncovered outbox failure count `0`，dirty/outbox/readiness 收敛。
- 生产 SLO：2026-06-28 `read_model_slo_smoke --apply --critical-only --target-ms 5000` grouped run 14/15 pass，唯一 Search grouped miss targeted rerun `499.357ms` pass。2026-07-02 release `HEAD-ef1a13cd-20260702120002` 复核 5s target 为 16/16 pass，max enqueue-to-fresh `3915.162ms`；同环境 1s target 为 7/16 pass、9/16 fail。2026-07-02 release `pscip-l4-bulk-persistence-abcca6f78` 复核 5s target 为 13/16 pass，1s target 为 9/16 pass。2026-07-02 release `pscip-l4-alignment-d725fdb6d` `/health/ready` `532.808ms` pass，scope contract `ok=true`；5s critical 为 11/16 pass，失败项为 `no_oa_bank_batch` `12890.546ms`、`invoice_lifecycle` `12098.140ms`、`turnover_ledger` `10900.840ms`、`search` `8350.434ms`、`pending_invoice` `6591.686ms`；1s critical 为 6/16 pass。2026-07-02 release `pscip-l4-workbench-sv-200f66b9d` 修复 Workbench worker event `source_version` 输入后，critical 5s 重采样一次 fail `max=5334.577ms`、两次 pass `max=3683.860ms/1467.466ms`，Workbench 1s targeted 仍 fail `1526.300ms`。2026-07-02 release `pscip-l4-workbench-insert-5f530d1b5` 删除 Workbench generation 明细旧 upsert 分支后，production code `DETAIL_CONFLICT_COUNT=0`，scope contract default/invalid-scope 均 `ok=true`；本轮最新 grouped 5s 为 14/16 pass，`turnover_ledger:all` `5591.378ms`、`bank_flow_rule_batch:2026-02` `5445.482ms` fail，targeted retry 分别 `993.910ms`、`455.961ms` pass；Workbench targeted 1s 仍 fail `1485.007ms`，不能声明高性能全域闭环。

## 职责边界

### 负责

- Read model manifest 合同、scope 规范、refresh enqueue、freshness/status 查询和 operation barrier。
- 约束所有 read model 的 Partitioned + Scoped + Incremental Projection 目标态。
- 防止页面读取旧 read model 却伪装 fresh。

### 不负责

- 不拥有具体业务页面的源事实。
- 不直接替代页面 service/repository 的业务逻辑。
- 不用 Redis/RabbitMQ 作为 read model 状态事实源。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Refresh request | 页面 service、writer、worker、API force refresh | 非事务入口必须经 `ReadModelRefreshGateway` normalize/validate/dedupe |
| Scope key | manifest/scope policy | 必须符合注册 scope policy |
| Query freshness request | API/read facade | 必须返回 fresh/stale/refreshing 或等价状态 |
| Write response target envelope | 页面写 API/service | 会影响 read model 的成功写入必须返回或透出 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets` 和 `operation_barrier_targets`；缺少/未知前端 read model status 必须保持非 fresh |
| Transactional refresh targets | `WorkbenchWriteUnitOfWork` 等事务 writer | 事务 writer 可以在业务事务内直接写 dirty scope/outbox，但必须使用等价 scope contract。Workbench confirm/withdraw 的 target source 是 `refresh_metadata.downstream_scope_types` 与 `pending_invoice_scope_keys`，并通过 scope policy registry normalize/validate/dedupe；禁止依赖 repository 隐式 SQL 扫描来补 downstream scope |
| Projection source versions | Worker/projection/upstream read model | 必须包含 own projection schema version 和依赖 source_versions；行为变更必须 bump version |
| Parent/shard freshness | Repository/API fresh gate | 父 scope 不能在子 scope dirty/missing dependency 时返回 fresh；`pending_invoice` 父 scope 必须聚合子月份 dirty status |
| Workbench pending OA claim lookup | `app.bank_transaction_relation_claims` | Workbench 月投影排除 OA 待付款进行中认领的银行流水时，必须使用 active `oa_pending_payment_relation` + `scope_month` + `bank_transaction_id` 的窄索引合同；该 I/O 只影响投影读取计划，不改变候选/关系业务语义 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Dirty scope/outbox event | PostgreSQL durable queue | `job.outbox_events` 与 `job.read_model_dirty_scopes` 是事实源 |
| Fresh payload | 页面 API/Redis | Redis 只能缓存 fresh gate 后 payload |
| Readiness/status | app status/operation barrier | 页面不能伪装 fresh |
| Workbench relation fan-out | runtime queue / workers | confirm/withdraw UoW 显式输出 `workbench`、`workbench_relation` 和 metadata 声明的 downstream scopes。`PostgresWorkbenchRelationRepository(..., enqueue_refreshes=False)` 是该主链路的持久化-only adapter，不能写 hidden outbox |
| Workbench generation payload | PostgreSQL read_model.workbench_* | 新 generation 的规范 payload 由各结构化 owner 表输出：`workbench_rows.payload` 拥有行详情，但不保存 nested `object_identity` 仲裁对象；canonical identity owner 是 `workbench_rows` / `workbench_group_rows` 的结构化 `object_identity_*` 列和行 payload 顶层字段。`workbench_groups.payload` 只拥有组级 metadata/sort/count/`workbench_group_rows_materialized` marker，`workbench_group_rows` 只拥有成员关系、过滤、排序、搜索和 object identity 结构化列，`payload` / `raw_payload` / `source_versions` 写 `{}`；`workbench_snapshots.payload` 只保存 metadata/summary shell 与 `workbench_groups_materialized=true` marker；旧 `/api/workbench`、groups page/detail 和成本统计如需完整 group rows，从 active generation 的 `workbench_group_rows + workbench_rows` 重建。Repository 遍历 rows/groups 时不得先 eager `serialize_value(...)` 整行/整组；序列化只允许发生在 `workbench_rows.payload`、`workbench_groups.payload` 等 JSON 写入 helper 的最终 I/O 边界。`raw_payload` 不再复制同一 JSON，只作为旧数据 fallback 字段存在 |
| Workbench pending claim hot path index | PostgreSQL migration | `0087_oa_pending_payment_claim_hot_path.sql` 保留 `bank_transaction_relation_claims_active_oa_scope_bank_idx`，覆盖 active OA 认领按月份读取和按 `bank_transaction_id` 排序；禁止用 handler sleep、页面补丁或 broad query fallback 掩盖该查询慢点 |
| Source-version proof | Scope rows / API fresh gate | `source_versions_unchanged` 只能在 own schema version 与依赖版本都匹配时跳过重建 |
| Queue history retention | Runtime worker ops | 只回收 `done` 历史，不改变 pending/processing/failed/dead-lettered freshness 事实源 |

## 持久化与投影

- Manifest：`backend/src/fin_ops_platform/services/read_model_manifest.py`
- Scope policy：`backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- Refresh gateway：`backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- Query gateway：`backend/src/fin_ops_platform/services/read_model_query_gateway.py`
- Repository：`backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Worker registry：`backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Gateway/manifest | `read_model_query_gateway.py`、`read_model_refresh_gateway.py`、`read_model_manifest.py` |
| Scope/freshness | `read_model_scope_policy.py`、`read_model_scope_contract.py`、`read_model_freshness.py`、`operation_freshness_barrier.py` |
| Write target envelope | `read_model_write_targets.py` 与页面/service 本地 target mapper，当前已覆盖 batch/no-OA/OA pending/pending invoice/turnover、bank-detail、input-invoice-usage OA reverse、output-invoice-collections、tax-offset plan/certified import、workbench relation action、general/file import、ETC import job completion、OA manual import/create/refresh/remove；pending_invoice import fan-out 使用 `pending_invoice_scope_planner.py` |
| Repository | `postgres_repositories/read_models.py`、`postgres_repositories/read_model_scope_contracts.py` |
| Worker | `runtime_worker_registry.py`、`runtime_worker.py`、`runtime_worker_handlers.py`；`workbench` 月份 shard 和 `workbench-aggregate` all-scope 聚合使用同一 event type 但不同 claim scope lane |
| Frontend | `web/src/features/operationBarrier/api.ts` |
| Scripts | `scripts/check-read-model-scope-contracts.py` |
| Production evidence | `docs/operations/read-model-production-evidence-runbook.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-main-final-closure-report-2026-06-28.md`、`.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-evidence-2026-06-28.md` |
| Tests | `tests/test_read_model_*.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` |

## 依赖方向

- 允许依赖：runtime queue repository、scope policy registry、app status registry。
- 必须通过：refresh gateway 或同事务等价 scope contract。
- 禁止绕过：业务 service 直接 SQL 写 dirty scope/outbox；页面绕过 freshness gate；RabbitMQ 作为状态事实源。

## 测试与验证

- Architecture guards：`tests/test_read_model_architecture_guards.py`、`tests/test_platform_runtime_boundary_guards.py`。
- Manifest/scope：`tests/test_read_model_manifest.py`、`tests/test_read_model_scope_contract.py`。
- Gateway/freshness：`tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_query_gateway.py`、`tests/test_read_model_freshness.py`。
- Write target envelope：`tests/test_read_model_write_targets.py`，以及 batch/no-OA/OA pending/pending invoice/turnover、bank-detail、input-invoice-usage OA reverse、output-invoice-collections、tax-offset、workbench relation action、general/file import、ETC import job completion、OA manual import/create/refresh/remove 的 API/service/page tests。
- Transactional writer boundary：`tests/test_workbench_uow_contract.py`、`tests/test_workbench_relation_repository.py::test_relation_repository_can_persist_without_refresh_fanout_for_uow_boundary`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_uow_pair_relation_repository_disables_repository_fanout`。

## 维护风险和删除条件

- 新增 read model 必须同时更新 manifest、scope policy、registry、tests、docs。
- 删除旧 read path 前必须证明所有页面 API 和 worker 均通过新 freshness/status 边界。
- Projection 行为、索引、跨 scope 分发或上游依赖合同变化时必须 bump projection schema version；禁止只改 SQL/service 逻辑却复用旧 `source_versions`。
- 事务 writer 若直接写 dirty scope/outbox，必须有等价 scope contract 测试。Workbench confirm/withdraw 不能恢复 repository 内部 hidden fan-out；新增 downstream 只能走 UoW target planner 或明确 gateway/lifecycle owner。
- `pending_invoice` 的 `filter=all` freshness dependency 月份必须来自 canonical `app.bank_transactions`，父 scope refresh_status 必须上卷子月份 dirty scope，防止新导入事实源已增加但页面仍显示旧 rows 且标记 fresh。
- `workbench_relation` 的 `rows` 索引是 scope 内唯一，不是 row 全局唯一；跨月 relation 必须在每个受影响 scope 写入所有成员 row 索引，禁止恢复旧的 `(tenant_id, row_id)` 覆盖模型。
- `workbench` 保留 active generation 原子发布；月份 shard 刷新后可投递 `all` aggregate，但 aggregate 必须由 `workbench-aggregate` lane 独立消费，不能阻塞页面首屏使用的月份 shard worker。
- legacy compat path 删除不是当前 PSCIP-L4 blocker；它必须继续保持生产 fail-closed、不能绕过 fresh gate，也不能新增未登记 dirty/outbox/readiness 写入。
- Search 高行数 refresh latency 仍需在后续生产 evidence sweep 中观察；单次高延迟不是当前 stale-as-fresh 或 readiness blocker。

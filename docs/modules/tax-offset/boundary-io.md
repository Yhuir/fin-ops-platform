# 税金抵扣模块边界与 I/O

## 页面完整性统计合同

- 税金抵扣既有主响应增加 `statistics`，统计来自该页面已经拉取并发布的进项发票、销项发票和认证抵扣明细，始终覆盖未筛选完整数据，不读取统一事实源汇总。
- 统计在一个 `tax_offset_items` `FILTER` 扫描内完成各状态计数；只有全部月份 projection schema/cache fresh，且不存在 active dirty/outbox 时才返回，任一条件不满足即返回 `statistics=null`，禁止 stale fallback。
- Page Audit 从 tax 页面 read model 与结构化 item 行独立重算统计并对比主响应口径；不新增 endpoint、表、worker 或缓存。
- 既有 Redis 月度/摘要缓存键绑定完整统计的稳定 generation token；API 只在 token 已存在时按需读写缓存，token 缺失时绕过 Redis 并走 freshness gate，worker/projection 不在 dirty scope 完成前预热，也不再写入或读取旧固定键及 `token=missing` 死链。

日期：2026-07-22

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：税金抵扣页面读取 `tax_offset` read model，通过 query service/gateway 保证 scoped freshness。
- 当前缺口：税金导入、认证、计划、worker cache warmup 与页面查询耦合较多，变更时必须明确影响面。
- 页面 Audit 状态：proof-ready；`relation_proof_required=false`，因为页面和 SQL projection 均不消费 Workbench relation。
- 旧代码删除条件：旧 service/cache 路径不再被 API 或 worker 引用，并有 SQL runtime/e2e 回归。

## 职责边界

### 负责

- 税金抵扣页面查询、认证导入、抵扣计划、税金 read model。
- `tax_offset` scoped incremental projection。
- 税金 projection 由 `tax_offset_sql_projection.py` 独立拥有；兼容 `cost-tax` worker 只组装税金 builder，不共享成本投影代码或 scope。
- 抵扣计划保存和认证导入只提交 canonical facts、source version 与审计；普通写返回空 read model targets，前端不等待 operation barrier。税金页面在 route 进入/重进、月份变化、浏览器手动刷新或明确重试时按当前月份执行 freshness/status/enqueue 并轮询收敛；focus/visibility 不触发税金数据 load。

### 不负责

- 不拥有成本统计 parent rollup。
- 不直接处理关联台关系事实写入。
- 不读取 `app.workbench_pair_relations` 或 `read_model.workbench_relation_*`，Workbench relation 写入也不得触发 `tax_offset` dirty/outbox。
- 不在页面里绕过 freshness gate 读取旧缓存。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/筛选 | `TaxOffsetPage.tsx`、`features/tax/api.ts` | 进入 tax offset API/query service |
| 税金导入/认证 | tax certified import services | 写后只提交事实与 source version；响应返回精确 `affected_scope_keys`，普通写的 `read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` 为空 |
| 普通银行流水导入 | bank file/session confirm | 不属于 tax canonical 输入：不得回写 invoice、tax-certified 或 tax_offset source version，也不得投递 tax_offset refresh；只有同一导入任务真实确认了 invoice facts 时才按 invoice scope 触发 tax_offset |
| 抵扣计划保存 | `TaxOffsetPlanService.save_plan(...)` | 验证 source versions 后保存计划并返回当前月份 `affected_scope_keys`；不触发或等待页面 read model rebuild |
| Refresh scope | `tax_offset` manifest | month or `all`；`all` 是 fan-out command，shard expected-set 必须取 canonical invoice/certified 月份与现有 projection 月份的并集，并把 parent 的 tenant、priority、trace 和显式 `force_refresh=true` 透传到每个 month shard，禁止父事件完成但历史月份仍保留旧 projection |
| 页面 Audit | 管理员统一 page-audit API | 同一 `REPEATABLE READ READ ONLY` snapshot 读取 canonical、projection、dirty/outbox；只读 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 税金抵扣 rows/summary | 前端页面 | query gateway 后 fresh/status |
| 导入/认证结果 | API/worker | 返回事实提交结果与精确 affected scope；普通写不发布页面 dirty scope |
| 计划保存结果 | 前端页面 | 保存成功立即结束写反馈；当前可见页直接重新读取，页面 freshness gate 在需要时精确入队当前月份 |
| Dirty scope | runtime queue | 仅由页面访问 freshness gateway 或显式 admin maintenance 通过 `ReadModelRefreshGateway` 发布 `tax_offset.read_model.refresh` |
| ETC 页面刷新提示 | 前端 `invoiceFactUpdated` | 只在 ETC invoice facts 真正导入或成功删除时刷新当前月份；明确忽略 `etcBusinessBatchUpdated`，OA/batch-only 状态不得触发税金 I/O。事件不是 freshness 事实源 |
| Audit proof | App Health 页面 | 五组 item 双向相等、关键字段/匹配/选择/summary/version/queue 证明；relation 明确为不适用 |

## 持久化与投影

- Read model：`tax_offset`
- Projection：`partitioned_scoped_incremental`
- Worker：`tax-offset`，辅助 `cost-tax`
- Query owner：`TaxOffsetQueryService`
- Repository owner：`TaxOffsetReadModelRepositoryPort`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/TaxOffsetPage.tsx` |
| Frontend feature/components | `web/src/features/tax/*`、`web/src/components/tax/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_tax.py` |
| Backend service | `tax_offset_service.py`、`tax_offset_query_service.py`、`tax_offset_runtime_service.py`、`tax_offset_plan_service.py`、`tax_offset_read_model_service.py` |
| Import services | `tax_certified_import_service.py`、`tax_certified_import_application_service.py`、`tax_certified_import_job_service.py` |
| Repository / SQL | `tax_offset_read_model_repository.py`、`tax_offset_sql_projection.py`、`postgres_repositories/tax_offset_page_audit.py` |
| Worker/read model | `tax_offset_read_model_refresh.py`、`tax_offset_derived_lifecycle_executor.py`、`tax_offset_cache_warmup_executor.py`、`tax_offset_worker_rebuild_executor.py` |
| Tests | `tests/test_tax_offset*.py`、`web/src/test/Tax*.test.*`、`web/e2e/tax-offset-flow.spec.ts` |

## 依赖方向

- 允许依赖：tax-offset projection、read model query gateway、certified import job service。
- 必须通过：TaxOffsetQueryService for reads, application/import service for writes。
- 禁止绕过：直接 SQL 写 read model；把成本统计 parent aggregate 当成税金事实源。
- 禁止污染：relation command/UoW/repository 不得把 `tax_offset` 当作 relation downstream；页面不得从 relation 状态推断发票是否应进入税金计划。

## 测试与验证

- `tests/test_tax_offset_sql_runtime.py`
- `tests/test_audit_tax_offset_read_model_tool.py`
- `tests/test_tax_offset_api.py`
- `tests/test_tax_offset_read_model_service.py`
- `web/src/test/TaxOffsetPage.test.tsx` 覆盖保存/认证导入后不等待 barrier、当前页重新读取与页面激活刷新。
- `web/e2e/tax-offset-flow.spec.ts`

## 当前缺口和删除条件

- cache warmup/rebuild worker 变更必须同步 runtime registry 和 deploy env。
- 删除旧 cache/read path 前必须证明页面不会读 stale 数据。
- 已删除旧 relation→tax_offset fan-out、SLO 期望和动态造数 Browser mock；不得恢复“配对后税金进项才出现”的旧合同。
- 队列化认证导入的 job result 与直接确认路径保持等价：普通写不携带 `tax_offset` operation barrier targets；显式维护操作才可返回自身 targets。

## Canonical facts ownership

- Owned facts: `app.tax_certified_import_sessions`、`app.tax_certified_import_batches`、`app.tax_certified_import_records`、`app.tax_offset_plans`。
- Allowed writes: certified import confirm、tax plan service、tax offset application service。
- Allowed reads: tax query/application service、tax certified import repository/read ports。
- Downstream outputs: tax_offset、cost_statistics、invoice_lifecycle dirty scopes 或 owner producer 输出。
- Forbidden paths: 其它模块不得直接写认证抵扣或计划表；tax read model 不得反向成为抵扣事实源。
- `app.tax_offset_plans` 是计划写入事实，但当前页面 read model 不读取计划表；因此页面 Audit expected-set 不混入计划表。若未来页面 projection 消费计划，必须先更新 projection、source version、Audit 和 API 合同。
- tax_offset 各月份共享同一个全局 invoice fact source version。任何 canonical invoice 写入使该版本变化时，旧月份会因 expected/actual source version 不一致而自然 stale；普通写不得把所有历史月份展开入队。用户访问某个月份时，query freshness gate 只为该 scope 入 durable queue。只有显式全量维护命令可以展开 `all`，且仍须走 scope policy 与 gateway。
- Audit v21 不从 `amount + tax_amount` 猜测 `total_with_tax`：历史来源对 `amount` 的含税语义并不统一。证明边界以 canonical `total_with_tax` 为事实，逐项比较 payload/结构化列并重算页面 summary；空字符串与 SQL NULL 在可空展示字段上按同一空值处理。schema `2026-07-tax-offset-audit-proof-v3` 强制正式 worker 重写 `tax_offset_items` structured columns，禁止旧 structured amount 残留与新 payload 并存。
- Old code deletion: 旧认证抵扣 snapshot、旧计划 fallback 和直接 SQL 写税金事实路径必须删除；migration/audit/rollback 工具保留不算 closure。

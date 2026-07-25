# Read Model 模块边界与 I/O

日期：2026-07-25

## 模块化状态

- 状态：Read Model 模块化 PSCIP-L4 closed；full external PSCIP-L4 / 高性能全域闭环 open
- 当前边界可信度：high
- 目标边界：所有当前 App Status read model 通过 manifest、scope policy、refresh gateway、runtime worker、freshness/status gate 和 operation barrier 形成可验证闭环。
- 当前闭环：Phase 27 coverage inventory 的 15 个 read model 均已有 manifest/scope/query/worker owner；`workbench`、`bank_account_balance`、`pending_invoice`、`cost_statistics` 保留各自显式例外语义。`no_oa_bank_batch` 仍登记为 legacy API/read-model 回归项，但不再代表当前页面 `/bank-flow-rule-batches`，也不进入默认 critical production SLO。
- 当前阻塞风险：HEAD/origin/main `719c9a34` 已作为 release `main-719c9a34-20260725101310` 激活，v7、migration `0125` 与正式 Workbench rehydrate 已完成。生产可逆 fixture 已证明普通 relation 写约 `173–343ms` 且零下游 fan-out，Workbench/Cost/Turnover 能最终 fresh，但仍有超过 3 秒样本。3 秒优化已后置为 `performance_follow_up`；当前阻塞仅是用同一 current release 完成全页面/操作正确性、恢复、隔离与 queue/worker/Audit 生产矩阵。
- 旧代码删除条件：Phase 27 当前主链路不得保留并行 refresh producer、写后 fan-out、request-local Workbench builder 或 proof cache；其它明确隔离的 legacy API/local path 只有在其页面/API/worker/测试和生产脚本调用方归零后才能删除。

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
| Refresh request | 页面 service、writer、worker、API force refresh | 非事务入口必须经 `ReadModelRefreshGateway` normalize/validate/dedupe；显式 force 只允许以安全 metadata `force_refresh=true` 进入 worker，普通写请求不得默认 force。访问 gate 已计算的 Workbench expected proof 只能以 token 成对、JSON 可序列化且有大小上限的 metadata 进入 durable queue；worker必须重新计算token并校验scope后才能复用，不能把metadata变成第二事实源。`invoice-usage-collection` 只负责进项使用/销项收款并传播其 force；`oa-pending-payment` 专属 handler 独立传播 OA `all -> month` force。禁止工具已接受 force、worker 却静默按普通 refresh 跳过，也禁止 shared invoice worker 重新 claim OA 事件 |
| Active refresh coalescing | `ReadModelRefreshGateway` / `RuntimeQueueRepository` | `api_*` 与其它 ensure/wakeup reason 必须调用 exact-scope atomic ensure。单 scope 与多 scope 共用 `enqueue_read_model_refreshes_if_inactive(...)`：按稳定顺序在同一事务锁定全部 exact `tenant/type/key`，一次查询 `job.outbox_events` 的 `pending/processing`，一次 set-based dirty/outbox CTE 只写未被 active metadata 覆盖的 scopes。覆盖关系固定为 `force > full scope > partial delta`：full 覆盖 partial，partial 不覆盖 full，非 force 不覆盖 force；partial 之间只在规范化 metadata 已覆盖 incoming `row_ids`、`case_ids` 与 `relation_deltas` 时 no-op。Workbench own `freshness_token`可覆盖active/最新成功同target；Cost child的`workbench_freshness_token`只合并同target active waiter，禁止用历史done短路missing/dirty Cost。新增语义在同一锁内合并 pending event，或为 processing event 建立 pending follow-up。禁止每 scope 独立事务 N+1、两事务竞态或同 scope 丢失新 delta。orphan dirty 必须重新 enqueue；真实 mutation/repair/reapply 与显式 force 保留独立版本语义 |
| Scope key | manifest/scope policy | 必须符合注册 scope policy |
| Query freshness request | API/read facade | 必须返回 fresh/stale/refreshing 或等价状态。共享 `ReadModelQueryGateway` 必须先调用当前 repository view，或调用方显式提供的轻量 `load_freshness_view`，完成 durable dirty + canonical dependency proof；只有该次请求明确 fresh 才可读取 Redis，cache hit 不能替代当前 freshness proof。轻量 proof 只能来自同一 owner 已完成的 PostgreSQL gate；cache miss 后必须再加载完整 view 并复核，不能由前端/内存猜测。Workbench exact scope 有 `pending/processing` outbox event 时，freshness service 直接返回 `refreshing`，不在每次页面 poll 重跑全月份 canonical proof；只有 dirty 没有 active event 时标记 stale 并返回 exact re-enqueue scopes。Application 共享的 Workbench projection builder 只合并时间上重叠的同 scope canonical proof；完成即删除 flight，后续访问重新证明事实，失败可重试，因此不构成 freshness cache 或第二事实源。`cost_statistics` 与 `oa_pending_payment` 复用各自已有 gate；`tax_offset` 复用已经进入 cache key 的当前 statistics generation token（该 token 聚合 projection、dirty 与 outbox）。竞态返回 `202`，不写其它页面 cache 或失效目标 |
| Write response target envelope | 页面写 API/service | 普通 canonical write 至少返回业务 receipt/identity 和可确定的 `affected_scope_keys` / `read_model_scope_keys`，但不为未访问页面制造 `freshness_targets` / `operation_barrier_targets`。只有显式 import/reapply/batch 或当前页面必须阻塞验证的 exact target 才返回 barrier；缺少/未知前端 read model status 必须保持非 fresh |
| Transactional refresh targets | 显式 reapply/repair writer | 只有仍登记为显式重建的 maintenance/reapply/repair 事务可直接写 dirty scope/outbox，并必须使用等价 scope contract。普通 import confirm、OA 权威 snapshot、Workbench relation、bank-flow/no-OA/batch-accounting/turnover，以及 pending/input/OA pending/output invoice-family 的命令与可写 Drawer 均为零 target，不得恢复 `refresh_metadata.downstream_scope_types`、UoW target planner、service callback 或 repository 隐式 scope 扫描。 |
| Projection source versions | Worker/projection/upstream read model | 必须包含 own projection schema version 和依赖 source_versions；行为变更必须 bump version。runtime event 的 dirty `source_version` 是发布竞态令牌，不得混入业务 projection `source_versions`：`cost_statistics` 必须用它在 repository 内锁定唯一 active dirty row 并精确比较；内容变化走条件发布，内容未变走 cost-only unchanged CAS 推进同一 `published_source_version`，然后再用同一版本条件完成 |
| Invoice lifecycle upstream rows | `InvoiceLifecycleReadModelRepositoryPort` / `pending_invoice` | 只读 exact `expense:all:YYYY-MM` 与 `income:all:YYYY-MM` fresh shards；dirty/missing 在 rows I/O 前 fail closed，fresh 才按 `scope_month + direction` 读取 payload。dependency-not-fresh 恢复必须补投这两个合法月方向 scope，禁止投递 `pending_invoice:YYYY-MM` 裸月份。禁止回流 canonical pending-invoice builder、HTTP 或 live fallback |
| Query-time read model filters | 页面 query service / settings owner | 只允许在 fresh payload 之后做不会改变 projection source fact 的过滤，例如成本统计标签规则；这类 filter 必须进入 query cache key，但不得写 dirty scope/outbox 或伪装成 read model source version |
| Parent/shard freshness | Repository/API fresh gate | 父 scope不能在子scope dirty/missing或child source lineage漂移时返回fresh。`cost_statistics`先读取现有Cost gate；gate已non-fresh时直接使用其`workbench_refresh_scope_keys`、`bank_detail_refresh_scope_keys`或`child_refresh_scope_keys`，跳过canonical全量证明。只有gate可fresh时才执行Workbench set-based canonical→active month proof。Workbench stale时，同次只stage当前project/page所需的exact Workbench与Cost child；不stage parent或sibling。query把本次已计算的exact Workbench proof同时交给Workbench event和对应Cost child waiter；两个worker先验证token/scope，再复用proof并分别比较当前active generation，避免重复canonical proof SQL。Cost worker沿manifest dependency fail closed/defer，dependency fresh后发布child并由成功child收敛parent。Workbench own target token在共享advisory lock内合并active/最新成功同target；Cost依赖token只合并active waiter；dirty orphan/failed不得被历史成功短路。禁止把系统中任意active Workbench/Bank Detail event当作Cost全局阻塞条件。普通Cost parent worker只rollup，只有显式`force_refresh`可full fan-out；parent-only`done`不能伪装fresh。 |
| Workbench pending OA claim lookup | `app.bank_transaction_relation_claims` | Workbench 月投影排除 OA 待付款进行中认领的银行流水时，必须使用 active `oa_pending_payment_relation` + `scope_month` + `bank_transaction_id` 的窄索引合同；该 I/O 只影响投影读取计划，不改变正式关系业务语义 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Dirty scope/outbox event | PostgreSQL durable queue | `job.outbox_events` 与 `job.read_model_dirty_scopes` 是事实源 |
| OA sync canonical commit | OA snapshot repository / `OAProjectionSyncService` | 权威 complete snapshot repository 在一个 PostgreSQL 事务内只提交 completed/admission/payment-status/watermark canonical facts，并返回 change summaries；不写任何页面 dirty/outbox。周期 sync service 不再拥有 shared downstream producer、matching invalidator 或页面 refresh gateway。OA 与其它消费页都在访问时比较 canonical source vector并只 enqueue 自身精确 scope。 |
| Fresh payload | 页面 API/Redis | Redis 只能缓存 fresh gate 后 payload；每次读取 cache 前仍要完成当前 SQL/source-version proof。版本化 key 必须让当前 gate 能机械拒绝旧版本，不能要求 writer 广播无边界 cache invalidation |
| Readiness/status | app status/operation barrier | 页面不能伪装 fresh。App Status dashboard 保留全局 snapshot；高频 operation barrier 必须把请求中的 registry target 传入 `PostgresStateStore.operation_barrier_runtime_snapshot(...)`，只查询这些 read model 的 exact/`all` readiness、dirty、current-effective outbox 与相关 worker 状态。target-scoped outbox 查询通过 migration `0114` 的规范 scope 索引，对每个 exact/`all` scope 执行 `LATERAL ... ORDER BY created_at DESC, id DESC LIMIT 1`，再用较新的 readiness/active dirty 判定是否已覆盖；禁止在每次轮询中对同 scope 全量历史事件逐行执行相关子查询。全局 App Status 仍保留完整历史诊断。缺少该 target-scoped provider 时 fail closed，禁止回退全局 App Status 聚合或另建缓存事实源 |
| Parent readiness role | manifest / app status | `fan_out_command` 的 command-only `all` parent 不写 current readiness；旧记录只作 diagnostics。真实 month shard、`queryable_parent_aggregate`、`queryable_all_scope` 和 Workbench active generation 继续作为 current proof。当前 parent command 失败仍由 dirty/outbox 阻断，不能因旧 fresh readiness 被覆盖。 |
| Workbench relation access convergence | Workbench/其它消费页 | confirm/withdraw/cancel/split/exception/ignore/cash 仅推进 canonical relation version，不输出任何 read-model target。当前访问页的 normal GET 先比较 expected/active source proof，只对所需精确 month scope 经 `ReadModelRefreshGateway` enqueue；隐藏页面延迟到再次可见。已入队的精确 relation delta/full rebuild 仍必须按 repository/worker 合同安全发布，但不得作为普通写产生者的 fallback。 |
| Workbench generation payload | PostgreSQL read_model.workbench_* | 新 generation 的规范 payload 由各结构化 owner 表输出：`workbench_rows.payload` 拥有行详情，但不保存 nested `object_identity` 仲裁对象；canonical identity owner 是 `workbench_rows` / `workbench_group_rows` 的结构化 `object_identity_*` 列和行 payload 顶层字段。`workbench_groups.payload` 只拥有组级 metadata/sort/count/`workbench_group_rows_materialized` marker，`workbench_group_rows` 只拥有成员关系、过滤、排序、搜索和 object identity 结构化列，`payload` / `raw_payload` / `source_versions` 写 `{}`；`workbench_snapshots.payload` 只保存 metadata/summary shell 与 `workbench_groups_materialized=true` marker；旧 `/api/workbench`、groups page/detail 和成本统计如需完整 group rows，从 active generation 的 `workbench_group_rows + workbench_rows` 重建。Repository 遍历 rows/groups 时不得先 eager `serialize_value(...)` 整行/整组；序列化只允许发生在 `workbench_rows.payload`、`workbench_groups.payload` 等 JSON 写入 helper 的最终 I/O 边界。`raw_payload` 不再复制同一 JSON，只作为旧数据 fallback 字段存在 |
| Workbench relation preview selection | PostgreSQL read_model.workbench_rows | 只读 preview port 以 `(generation_id, scope_key, row_id=ANY)` 读取受限 selected rows，并在同一 active generation/set 内补充必要 OA attachment context；前后复核 status/version，固定查询数，禁止 snapshot/full payload copy、逐 row detail N+1、cache、queue 或 schema/index fallback。最大 selected rows 为 20、context rows 为 100，超限 fail closed |
| Workbench generation-set publish | PostgreSQL advisory transaction lock | 月分片 payload 计算与 generation staging/COPY仍可在 worker 间并行；重型数据写完后，所有月份复用一个 `workbench_generation_set` transaction lock，只串行完成 generation 激活、当前 active-month digest 计算和 `scope_key=all` stats 发布。禁止按月份分别锁定后并发发布不同 digest，否则最终 active set 可能没有对应 stats；若生产证明短发布段本身超过 3 秒，再单独优化 stats SQL，不能拆回非原子 writer。 |
| Turnover ledger page payload | `TurnoverLedgerReadModelRepositoryPort` / `read_model.turnover_ledger_rows` | 查询 missing 必须经 query gateway fail-closed/enqueue，不得回退 live builder。v6 完整 DTO 只存/读 `payload`，`raw_payload` 写空；summary/family/total 在 SQL 内聚合，data query 只读取当前页。`all` query 必须聚合全部 turnover child dirty scope，不能只检查 command-only `all` key。旧 direct clear port 已删除，重建只走正式 gateway/worker。 |
| Workbench pending claim hot path index | PostgreSQL migration | `0087_oa_pending_payment_claim_hot_path.sql` 保留 `bank_transaction_relation_claims_active_oa_scope_bank_idx`，覆盖 active OA 认领按月份读取和按 `bank_transaction_id` 排序；禁止用 handler sleep、页面补丁或 broad query fallback 掩盖该查询慢点 |
| Relation source fast path for downstream workers | `WorkbenchRelationReadModelRepositoryPort` / canonical repository | 实际消费 `workbench_relation` distribution 的下游 worker 只能通过 workbench-relations repository port 读取 eligible active relation source rows/source summary；`turnover_manual_closure` 由 Workbench/Turnover 直接消费 canonical relation，不进入共享 rows/groups/source version。Bank Details 与 Pending Invoice 的 source proof 使用同一排除条件，避免专用 closure 污染非 consumer。旧 scope 若仍含被排除 mode，只在其 exact scope 被访问时 fail closed 并由正式 worker 重建。OA 等直接消费 canonical relation 的投影仍按各自读 gate 收敛；Workbench UoW 不再为它们直接投递月份。任一路径都禁止把 relation source 伪装成页面 fresh payload。 |
| Source-version proof | Scope rows / API fresh gate | `source_versions_unchanged` 只能在 own schema version 与依赖版本都匹配时跳过重建。主 `workbench` generation proof 必须覆盖所有状态的 relation/exception/override、active pending claim、requested month 与 relation 跨月成员的 OA/银行流水/发票 canonical `updated_at`、ETC submission/business/invoice/link，以及 Workbench 实际消费的银行规则版本和账户映射 fingerprint；无关 settings 字段不得进入 proof。`all` query proof 聚合 active month generation 的同一完整 vector，不能只依赖静态 OA sync schema version。同一次请求已完成的 proof 可向 payload/Cost dependency gate 复用；跨请求只允许 active in-flight 合并，不缓存已完成结论。一个请求校验多个月 scope 时，允许用一次 canonical bulk SQL 返回逐 scope版本映射以消除查询 N+1，但每个 scope 的 source/member边界、mismatch reason和精确enqueue语义必须与单月proof完全等价；禁止用年度汇总版本替代逐月证明。当前 v7 schema 已通过正式 queue/active-generation publish 和 `workbench-rehydrate` 完成生产迁移；migration `0125` 仅优化 bank/invoice canonical identity lookup |
| Invoice lifecycle dependency reads | `InvoiceLifecycleReadFacade` / `InvoiceLifecycleReadModelRepositoryPort` / upstream read models | own schema version 为 `2`。manifest 登记的只读依赖固定为 `pending_invoice`、`input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`workbench_relation`，并由 graph-completeness/acyclic test 锁定；这只是既有 query owner + gateway I/O，不是第二编排器。月份访问先检查 dependency readiness，一次投递所有 non-fresh exact scopes，再投 lifecycle；worker 仍在发布前 fail closed，并只可从 manifest 图内补投遗漏依赖。pending-invoice exact 月方向 scope 缺失时，只有 fresh Bank Detail 月 scope 且同方向结构化行数为零，repository 才输出携带 Bank Detail source proof 的空集。OA 必须走 lifecycle 专用 exact-month source I/O，同时读取 scope fresh gate、source versions 与 rows。禁止恢复 canonical live rebuild、图外递归 fan-out 或 stale-as-empty fallback。 |
| Cost statistics conditional publish/read gate | `CostStatisticsReadModelRepositoryPort` / runtime worker / query owner | 月份与 parent snapshot 只有在 event `source_version` 等于当前唯一 `pending` / `processing` dirty 版本时才可写；snapshot/rows、父级过期月份删除与独立 parent metadata `published_source_version` 同事务。若完整业务 `source_versions` 未变，cost-only `acknowledge_unchanged_cost_statistics_scope(...)` 必须在单事务内同时锁定当前 dirty 版本并精确匹配 parent `source_versions`，只推进 `published_source_version/updated_at`；不得重写 payload/rows，也不得返回通用 `skipped` 使 readiness 忽略本事件。读请求用单条 cost-only SQL 比较 published version 与最高 durable dirty version/status，metadata `NULL` 或 non-fresh 时禁止 Redis/full rows；旧 completion history 不回填 proof，必须经新版 rebuild/确认。full payload loader 不再拥有 dirty 查询。runtime version 不进入业务 `source_versions`。拒绝发布或确认不写 Redis、不完成 dirty、不 fan-out；条件完成失败也保持 `refreshing`，保护新 dirty 版本。该 CAS 只属于成本统计，不改变其它 read model 的 repository、queue 或 readiness 语义 |
| Cost statistics broad state exclusion | `PostgresStateStore` / `ApplicationStateStore` / manifest | 成本 read model 不属于应用全状态 snapshot：启动 load 不扫描整张成本 metadata 表，broad save 不识别成本 key，protocol/manifest 不暴露全量 load 或无 source-version save。正式 PostgreSQL 表继续由成本 repository 拥有，读取只走 scoped gate/page/export-page/view/transaction，写入只走 conditional publish；bulk export-page 只能返回 SQL summary 与最多 1,000 行，不得用 local pickle、full payload、facade delegate 或兼容 shim 恢复旧入口 |
| Cost statistics structured row storage | `CostStatisticsReadModelRepositoryPort` / PostgreSQL migrations `0107`、`0123` | OA allocation只归属 `cost_statistics_rows`；`time|bank_tag` 直接消费 freshness-gated `bank_detail_rows`。`0123` 删除由 `0107` 历史创建的 `cost_statistics_bank_flow_rows` 复制表。parent metadata不保存业务 arrays，full DTO/parent rollup不得回退 JSON。transaction detail按 `view` 选择 Bank Detail或Cost identity point query。Cost projection无 Redis writer，query gateway只在对应 profile fresh gate后缓存 versioned payload。禁止 dual-read、第二 writer或跨页面 HTTP I/O。 |
| Cost statistics invalidation | `CostStatisticsRuntimeService` / `ReadModelRefreshGateway` | 只把规范 scope 写入 PostgreSQL durable queue，并只返回 gateway 已接受的 scope。queue 不可用时返回空；不得恢复进程内 read model service、startup snapshot、local clear 或显式 persistence callback。旧 SQL rows 由 fresh gate 阻断，不能在请求线程删除 |
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
| Scope/freshness | `read_model_scope_policy.py`、`read_model_scope_contract.py`、`read_model_freshness.py`、`operation_freshness_barrier.py`、`runtime_monitoring.py` 的 target-scoped barrier snapshot |
| Write target envelope | `read_model_write_targets.py` 只保留信息性 scope envelope 与仍有明确 production owner 的显式 maintenance/reapply/repair 路径。import、pending/input/OA pending/output invoice-family 普通 command 可以返回 affected scope hints，但 freshness/barrier targets 必须为空；已删除的 `pending_invoice_scope_planner.py` 不得恢复。 |
| Repository | `postgres_repositories/read_models.py`、`postgres_repositories/read_model_scope_contracts.py` |
| Worker | `runtime_worker_registry.py`、`runtime_worker.py`、`runtime_worker_handlers.py`；`workbench` primary 处理月份 shard 与 `all` fan-out command，`workbench-secondary` 只并行处理月份 shard，`all` 不发布 generation；`cost-statistics` primary/secondary 竞争同一 exact scope queue |
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
- Readiness reporter 与 App Status current-effective 聚合必须通过 `read_model_manifest.is_command_only_read_model_scope(...)` 使用同一 scope-role 合同；禁止页面、worker 或运维脚本另写 OA/bank 等 read model 特例。
- Operation barrier 只保留给显式 import/reapply/batch/repair 或当前页必须阻塞验证的 exact target，只能读取调用方明确提交的 scopes 并复用 App Status 折叠语义。普通 relation/bank-flow/no-OA/batch-accounting/turnover 页面不得轮询 barrier 或全局 `app_status_runtime_snapshot()`。
- 显式 maintenance/reapply/repair 事务 writer 若直接写 dirty scope/outbox，必须有等价 scope contract 测试。普通 import/OA sync/Workbench confirm/withdraw 不能恢复 repository hidden fan-out、UoW target planner 或 downstream discovery。
- `pending_invoice` 的 `filter=all` freshness dependency 月份必须来自 canonical `app.bank_transactions`，父 scope refresh_status 必须上卷子月份 dirty scope，防止新导入事实源已增加但页面仍显示旧 rows 且标记 fresh。
- `workbench_relation` 的 `rows` 索引是 scope 内唯一，不是 row 全局唯一；跨月 relation 必须在每个受影响 scope 写入所有成员 row 索引，禁止恢复旧的 `(tenant_id, row_id)` 覆盖模型。
- `workbench_relation` 操作级局部投影必须通过 `WorkbenchRelationReadModelRepositoryPort.save_workbench_relation_distribution_rows(...)` 进入 repository；service/projection 不得直接写 SQL。relation-only delta 的版本输入必须先通过 `workbench_relation_delta_source_versions(...)` 在一个 bounded canonical/read-model snapshot 中读取既有 scope proof并只推进受影响 relation version；scope 缺失或 schema 不匹配必须显式 full rebuild。repository 必须按受影响 row overlap 删除旧 groups、删除/写回受影响 rows、同步 scope source_versions 并重算 row/group count。
- `workbench` 保留 active generation 原子发布；ordinary write 后不主动发布任何 shard。访问查询检测受影响月份 stale 后才投递该 shard。`month=all` 查询组合 active 月度 generation；显式 `all` refresh 只是由同一 worker 投递月份 shard 的 command，不写全局 generation，也不成为普通 relation 写入的 operation barrier。
- legacy compat path 删除不是当前 PSCIP-L4 blocker；它必须继续保持生产 fail-closed、不能绕过 fresh gate，也不能新增未登记 dirty/outbox/readiness 写入。
- Search 高行数 refresh latency 仍需在后续生产 evidence sweep 中观察；单次高延迟不是当前 stale-as-fresh 或 readiness blocker。

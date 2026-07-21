# 外部往来款管理模块边界与 I/O

日期：2026-07-20

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：外部往来款页面读取 `turnover_ledger` read model；写操作通过 write facade/UoW/adapters 进入 scoped dirty projection。
- 当前闭环：read path 由 `TurnoverLedgerApiRoutes` route owner 进入 `TurnoverLedgerQueryService` / read model，并在 repository 内用固定查询数完成 SQL 过滤、汇总和有界分页；repository miss 只允许经 `ReadModelQueryGateway` fail-closed/enqueue，不存在 live page builder fallback。write path 由 request-boundary facade 进入 `TurnoverLedgerWriteFacade` / UoW / explicit adapters；现代 closure confirm 先由 Turnover domain 做无副作用业务校验，再由 `WorkbenchRelationCommandService.prepare_confirm_relation(...)` 在同一事务完成 freshness、member lock 和 scoped relation snapshot，最终只写 canonical Workbench relation。通用 suggested relation confirm/withdraw 仍写 Turnover-owned relation/audit。全部 scoped dirty/outbox 目标经 scope policy 后交给 runtime queue 的 transaction-bound batch enqueue，一条 SQL 原子落库，不重写全量关系快照。refresh producer 只负责通过 `ReadModelRefreshGateway` enqueue。
- 旧代码删除状态：`TurnoverLedgerReadFacade` app 转发壳、`TurnoverLedgerRelationMutationInvalidationLegacyAdapter`、`TurnoverLedgerRelationRepositoryAdapter`、确认/撤回的全量 `rebuild_from_bank_rows`/`save_turnover_relations` 链、现代 closure 的重复 Turnover relation/event 持久化、无收益的 `turnover-ledger-secondary`、turnover projection 对 `WorkbenchRelationReadFacade(require_fresh=True)` 的串行依赖、`Application._after_turnover_relation_mutation(...)`、`Application._refresh_local_app_settings_snapshot(...)`、refresh producer direct clear、query service `legacy_payload_builder/settings_provider` 分叉、repository `clear_turnover_ledger_rows` port、UoW 按 request/scope 逐条 enqueue、幂等事务外预查、同一 selected bank rows 的版本校验/closure preview 重复读取、cash-closure 撤回的 current relation 二次加载，以及 `assert_turnover_manual_closure_write_precondition` 独立预检和 `_active_relations_for_row_ids_from_command` 二次快照热路径已删除；列表不再从 `raw_payload` 回退业务行 payload，projection 不再复制规范化 payload；边界 guard 防止恢复。

## 职责边界

### 负责

- 外部往来款列表、确认关联、撤回、导出、余额/账期查询。
- `turnover_ledger` read model。
- 与银行流水、关联台关系事实源之间的 write/read adapter。

### 不负责

- 不拥有银行流水源事实。
- 不直接维护 workbench relation 表。
- 不绕过 write UoW 直接更新 turnover source versions。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/筛选 | `TurnoverLedgerPage.tsx`、`features/turnoverLedger/api.ts` | 进入 `TurnoverLedgerApiRoutes` route owner，再由 `TurnoverLedgerQueryService` 读取 read model |
| 页面只读 Audit | `PageBusinessAuditIcon` / AppHealth operations API | admin-only 调用 `page-audit?page=turnover-ledger`；canonical expected-set 从 active bank facts + fresh bank-detail effective turnover fields + 当前 tag selection 独立形成，并按 `family + counterparty` 聚合完整 bank member set，与页面 group 双向相等；余额按去重 leaf 分方向重算（有本金时结算最多冲减到零，纯结算组保留负余额），待还/已还/待收/已收分别按 leaf action/amount 重算，ledger extras 另行核对；ledger/flow payload 必须保留 `workbench_relations` 的 case/status/mode/source/typed members，并按每个 row 的 bank anchor 与 linked shared groups 做双向 edge equality；全部检查位于同一只读一致性快照，只消费结构化 audit status 与 issue samples，不进入本模块写 facade |
| 确认/撤回写操作 | write facade/UoW | 已知 affected months 的写路径触发 turnover/workbench/workbench_relation/cost/search affected month scopes；银行流水分类批量更新还必须在同一事务输出 `bank_detail` 与 `bank_flow_rule_batch` 精确月份 dirty/outbox。月份从 canonical bank facts 一次批量读取。UoW 必须先汇总全部目标，经 scope policy normalize 后调用 runtime queue 的 transaction-bound batch enqueue，在同一条 SQL 内原子写 dirty scopes/outbox，禁止按 read model/scope 逐条往返；Turnover 注入的 `PostgresWorkbenchRelationRepository` 必须关闭 repository fan-out，禁止 relation repository 再做 scope 查询和第二次 outbox enqueue。幂等首次占位、冲突与 replay 统一由事务内原子 reserve 判定，不允许恢复事务外预查。现代 closure confirm 调用 `preview_zero_difference_closure` 只验证所选银行事实，不写 Turnover relation/audit；request-scoped bank-row selection port 将同一次 canonical rows 读取同时用于 expected-version 校验和 preview。Turnover command service 使用 canonical 模式，不查询派生 relation read model；prepared relation command 只执行一次所选 bank member lock、一次 scoped canonical relation snapshot，并只写 Workbench active case。cash-closure 撤回同样在一个 transaction-bound preparation 内完成一次 case lock 和一次 scoped canonical relation snapshot，先按当前 relation 复核 row types 只能为 `oa/bank` 且至少两条 bank，再把同一 preparation 交给 withdraw；禁止重新加载 current relation。准备上下文必须绑定同一 service/transaction、case/月份和允许成员集合，任何不匹配都 fail closed。跨月准备必须保留全部精确月份作为 `scope_keys_hint`，并把 `turnover_closure_affected_months` 写入 relation metadata。旧关系无 metadata 时只用 canonical relation 中的 bank members 经既有月份 resolver 补足。无法得到精确月份必须 fail closed，禁止返回永远不会产生 current readiness 的 `turnover_ledger:all` command scope 作为 operation barrier target |
| 标签选择写操作 | write facade/UoW + Settings domain port | PostgreSQL 路径通过 supplied transaction 保存 canonical settings/audit/outbox；本地路径只调用 `AppSettingsService` 的 tag-selection state/commit/restore 端口，queue 失败仅回滚该 family，不得直接访问 `_snapshot` 或 `state_store.save_app_settings(...)` |
| Workbench relation requirement | `TurnoverLedgerWorkbenchPairPort` | 创建 `turnover_manual_closure` 时必须写入 `requires_oa`、`requires_invoice`、`paired_requirement_source`、`paired_requirement_version`；这些字段是关联台分区的唯一输入，不能由关联台查询当前设置兜底 |
| Refresh scope | `turnover_ledger` manifest | month or `all`；`all` 是 fan-out command，不是普通写操作默认 scope。relation context 通过一个 bounded SQL bundle 从 canonical `app.workbench_pair_relations` 的同一快照读取 active source rows 和 source summary，不串行等待 `workbench_relation` read model，也不允许行/版本跨快照。事件同时携带 `relation_deltas`、`row_ids` 且 scope 为精确月份时，turnover worker 必须按 `scope_month + bank_row_ids overlap` 只读/更新受影响 grouped rows；共享 `workbench_relation` worker 同样只能按 affected rows推进 pair-relation proof并局部替换 overlap groups/rows。两者都禁止读取全月 payload/对象/relation集合或 delete/rewrite 整月。scope 缺失、schema/mixed proof不安全时显式执行 full rebuild；导入、标签、设置、extra 和 `all` 仍按自身 source 变化执行完整 scope 投影。worker 连续处理同一 canonical source version 的多个 month scope 时，只允许复用一份进程内基础 rows 计算结果；cache key 必须等于完整 own source_versions，版本变化立即失效，cache 不带 TTL、不跨进程、不作为事实源或 stale fallback。`all` 查询由月度/行级 rows 拼接时允许 mixed row source_versions；repository 必须聚合所有 turnover 子月份 current-effective dirty 状态，任一 failed 为 stale，否则任一 pending/processing 为 refreshing，全部 clean 才为 fresh。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 外部往来款 rows/summary | 前端页面 | query gateway 后 fresh/status；完整重建和 relation delta 在发布事务内从未筛选 read-model rows/`flow_rows` 计算标题 `statistics`（去重流水、收支、台账组、结清、OA/发票关联），原子写入 `read_model.turnover_ledger_scopes`；请求 SQL 只读取 scope summary 标量，不再展开 `flow_rows`，且统计不受页面筛选、排序或分页影响；0 行 generation 仍由 scope row 证明存在并 fresh 返回全零统计；read model 或 scope summary 非 fresh 时统计为 `null` 并触发 scoped refresh，禁止用银行 canonical/统一事实源替代 |
| 页面 Audit 状态 | 标题附件 | unknown/non-fresh 不得显示 Fresh；样本截断必须显式呈现 |
| 写操作结果 | API/frontend operation barrier | 可审计、幂等或有版本保护；返回 `affected_months`、`affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets`。前端轮询由共享 target-scoped runtime snapshot 只读取这些 scopes，不触发全局 App Status 聚合 |
| Workbench active relation | `workbench-relations` | 只通过 `WorkbenchRelationCommandService` 写入/撤回；`turnover_manual_closure` relation metadata 明确声明 OA/发票 requirement。metadata 缺失的旧关系必须 fail closed，等待规则保存同步链路升级 |
| Dirty scope | runtime queue | `turnover_ledger.read_model.refresh` |
| 导出 | 用户下载 | 复用查询权限和筛选 |

## 持久化与投影

- Read model：`turnover_ledger_rows` 业务行 + `turnover_ledger_scopes` generation/row-count/statistics summary
- Projection：`partitioned_scoped_incremental`
- 生产投影必须信任 `BankTransactionTagReadFacade` 输出的 fresh bank-detail tag 事实；只有无 provider 的 legacy/local 路径才允许回退 `BankTransactionCategoryService` snapshot。禁止在 provider-backed worker hot path 逐笔读取旧 category service。
- 关系 enrichment 必须通过 `WorkbenchRelationReadModelRepositoryPort.workbench_relation_source_bundle_from_source(...)` 读取 `app.workbench_pair_relations`；rows 与 source summary 必须来自同一个 SQL 快照。这是只读 shared-fact I/O，不读取或等待 `read_model.workbench_relation_*`。canonical source 不可用时不得伪造 linked relation context。
- grouped 当前台账不得消费 `withdrawn` relation；撤回历史只留在 relation snapshot/audit log。系统自动关系恢复后，同一 bank leaf 在 grouped financial totals 和 flow rows 中只能计算一次。
- `turnover_relation_snapshot_version` 只散列通用 suggested-relation 链会改变当前台账的 canonical `confirmed` Turnover relations，并按 `relation_id` 稳定排序；`withdrawn` relation 与 audit history 不属于当前 projection 输入。现代 closure confirm/withdraw 只改变 Workbench canonical context，不得改变该版本；通用 relation 确认改变版本、撤回后回到操作前值。
- Month projection 首次读取的现有 read-model page 必须在 unchanged 检查和 relation-only refresh 之间复用，禁止对 page 1 重复 SQL；同一 worker 内的基础 grouped rows memoization 只能保留最近一个完整 source-version 快照，调用方得到副本，任何 source-version 变化都必须重新读取 canonical facts 并重算。
- Relation-only month refresh 的正式 I/O 是 `load_turnover_ledger_relation_delta(...)` / `save_turnover_ledger_relation_delta(...)`。查询依赖 `turnover_ledger_rows_bank_row_ids_gin`，保存不得 delete scope；它必须与 affected month 及 `all` scope summary 在同一事务更新。完整 `save_turnover_ledger_rows(...)` 只属于 own-source 变化、repair、首次构建或明确安全 fallback，并同样原子发布对应 scope summaries。full/month/delta/unchanged acknowledgement 共享唯一 turnover advisory transaction lock，并在写前比较内部 global generation 与目标 scope 的 event `published_source_version`；先获得锁再做 CAS，锁集合恒为一个，禁止增加 month/all 多锁顺序。CAS 失败必须中止整个事务并由 worker 重试，旧 generation 不得覆盖新 projection。
- `all` 聚合发现行级 `source_versions` mixed 时必须 fail closed，禁止把实际版本改写成 expected 后伪装 fresh。API 应入队 `turnover_ledger:all`；full-all builder 必须绕过 existing-row reuse，从 canonical facts 重建所有 rows 并写入同一 source vector，从而收敛 mixed 状态。
- 列表 page payload 只能从规范化 `payload` 读取；family/status/scope/direction、总 summary、family summaries 和 total 在 PostgreSQL 中计算，第二条 data query 只读取当前 `page_size<=200` 的 payload。筛选为空但 projection 已存在时返回 fresh 空结果，不得误触发 rebuild。
- `raw_payload` 不属于 turnover 业务行读取合同，完整业务 payload 只由 `payload` 拥有；不得恢复业务 payload fallback，也不得把 scope metadata/统计寄存在任一业务行。`turnover_ledger_scopes` 是 generation 存在性、source versions、row count、标题 statistics 与内部 CAS metadata 的唯一持久边界；scope row 缺失或 row count 不一致时 statistics 判为 stale，并复用现有 scope rows 补发。`generation` / `published_source_version` 只允许 repository port 与 builder 消费，禁止进入公开 API DTO。
- Worker：`turnover-ledger`
- Query owner：`TurnoverLedgerQueryService`
- Repository owner：`TurnoverLedgerReadModelRepositoryPort`，仅暴露 `list_turnover_ledger_view`、`save_turnover_ledger_rows`、`turnover_ledger_generation`、`acknowledge_unchanged_turnover_ledger_scope`、`load_turnover_ledger_relation_delta`、`save_turnover_ledger_relation_delta`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/TurnoverLedgerPage.tsx` |
| Frontend feature/components | `web/src/features/turnoverLedger/*`、`web/src/components/turnoverLedger/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` |
| Backend service | `turnover_ledger_service.py`、`turnover_relation_service.py`、`turnover_ledger_query_service.py`、`turnover_ledger_write_facade.py`、`turnover_ledger_write_uow.py`、`turnover_ledger_write_adapters.py` |
| Repository / SQL | `turnover_ledger_read_model_repository.py`、`turnover_ledger_sql_projection.py` |
| Worker/read model | `turnover_ledger_read_model_refresh.py`、`turnover_ledger_read_model_refresh_producer.py`、`turnover_ledger_source_versions.py` |
| Tests | `tests/test_turnover_*.py`、`web/src/test/TurnoverLedger*.test.*`、`web/e2e/turnover-ledger-flow.spec.ts` |

## 依赖方向

- 允许依赖：bank row version provider, workbench relation adapters, read model query gateway。
- 必须通过：TurnoverLedgerQueryService for reads, write facade/UoW for writes。
- 禁止绕过：直接操作数据库确认/撤回；API 返回 stale payload as fresh。

## 测试与验证

- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `tests/test_turnover_ledger_read_model_refresh.py`
- `web/src/test/TurnoverLedgerApi.test.ts`
- `web/src/test/TurnoverLedgerPage.test.tsx`
- `web/e2e/turnover-ledger-flow.spec.ts`

## 当前缺口和删除条件

- 本地模块化边界已 close；后续若新增写入口，必须先明确 affected scopes，不能恢复 default direct clear、route forwarding shell 或 legacy invalidation adapter。
- 方式 B 可控样本验证优先通过业务操作恢复；若生产样本没有业务恢复路径，可按用户批准的 bounded DB restore protocol 使用精确 predicate 恢复到操作前快照，不得通过 DB 伪造 read model freshness。

## Canonical facts ownership

- Owned facts: `app.turnover_relations`、`app.turnover_relation_events`、`app.turnover_ledger_extras`。
- Shared facts: relation facts 由 `workbench-relations` owner 管理；银行分类与 effective turnover leaf facts 由 `bank-details` owner 管理，Audit 只读消费，不反向写入。
- Allowed writes: turnover write facade、write UoW、turnover relation service。
- Allowed reads: turnover query service/read ports、turnover ledger read model boundary，以及通过 `WorkbenchRelationReadModelRepositoryPort` 的 bounded canonical active relation source rows/source summary。
- Downstream outputs: turnover_ledger、workbench_relation、workbench、bank_detail、bank_flow_rule_batch、cost、search dirty scopes 或 owner producer 输出。
- Forbidden paths: query/service 不得回退 live page builder 或 raw payload；write facade 不得进入 direct relation fallback；不能直接写 workbench relation 或 bank category facts；不能从银行明细或 Application helper 直接清 `turnover_ledger` read model；local adapter 不得读写 Settings 私有 snapshot 或整份 settings store。
- Old code deletion: app read forwarding facade、query live fallback/settings switch、relation mutation legacy invalidation adapter、dead relation repository adapter、确认/撤回全量 relation snapshot rebuild/save、turnover projection 的 workbench-relation read-model wait、producer/repository direct clear I/O、direct relation fallback、snapshot bank-row source fallback、raw payload 双写和 Settings snapshot save/refresh fallback 已删除；migration/audit/rollback 工具保留不算 closure。

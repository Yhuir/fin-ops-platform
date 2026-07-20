# 外部往来款管理模块边界与 I/O

日期：2026-07-20

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：外部往来款页面读取 `turnover_ledger` read model；写操作通过 write facade/UoW/adapters 进入 scoped dirty projection。
- 当前闭环：read path 由 `TurnoverLedgerApiRoutes` route owner 进入 `TurnoverLedgerQueryService` / read model，并在 repository 内用固定查询数完成 SQL 过滤、汇总和有界分页；repository miss 只允许经 `ReadModelQueryGateway` fail-closed/enqueue，不存在 live page builder fallback。write path 由 request-boundary facade 进入 `TurnoverLedgerWriteFacade` / UoW / explicit adapters；确认/撤回只加载目标银行行并在同一事务写一条 turnover relation、一条 audit event，并把全部 scoped dirty/outbox 目标经 scope policy 后交给 runtime queue 的 transaction-bound batch enqueue，一条 SQL 原子落库，不重写全量关系快照。refresh producer 只负责通过 `ReadModelRefreshGateway` enqueue。
- 旧代码删除状态：`TurnoverLedgerReadFacade` app 转发壳、`TurnoverLedgerRelationMutationInvalidationLegacyAdapter`、`TurnoverLedgerRelationRepositoryAdapter`、确认/撤回的全量 `rebuild_from_bank_rows`/`save_turnover_relations` 链、turnover projection 对 `WorkbenchRelationReadFacade(require_fresh=True)` 的串行依赖、`Application._after_turnover_relation_mutation(...)`、`Application._refresh_local_app_settings_snapshot(...)`、refresh producer direct clear、query service `legacy_payload_builder/settings_provider` 分叉、repository `clear_turnover_ledger_rows` port 和 UoW 按 request/scope 逐条 enqueue 的旧热路径已删除；列表不再读取或回退 `raw_payload`，projection 不再复制规范化 payload；边界 guard 防止恢复。

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
| 确认/撤回写操作 | write facade/UoW | 已知 affected months 的写路径触发 turnover/workbench/workbench_relation/cost/search affected month scopes；UoW 必须先汇总全部目标，经 scope policy normalize 后调用 runtime queue 的 transaction-bound batch enqueue，在同一条 SQL 内原子写 dirty scopes/outbox，禁止按 read model/scope 逐条往返。银行行 stale precondition 和 domain refresh 只读取命令中的 row IDs；relation persistence 只 upsert 命令结果并 append 匹配 audit event，禁止全表/全快照重建。跨月确认的 relation freshness precondition 必须同时保留全部精确月份作为 `scope_keys_hint`，不能只把多月压缩成 `month_scope=all` 后丢失 scope I/O；未知月份例外才允许 `all` fan-out |
| 标签选择写操作 | write facade/UoW + Settings domain port | PostgreSQL 路径通过 supplied transaction 保存 canonical settings/audit/outbox；本地路径只调用 `AppSettingsService` 的 tag-selection state/commit/restore 端口，queue 失败仅回滚该 family，不得直接访问 `_snapshot` 或 `state_store.save_app_settings(...)` |
| Workbench relation requirement | `TurnoverLedgerWorkbenchPairPort` | 创建 `turnover_manual_closure` 时必须写入 `requires_oa`、`requires_invoice`、`paired_requirement_source`、`paired_requirement_version`；这些字段是关联台分区的唯一输入，不能由关联台查询当前设置兜底 |
| Refresh scope | `turnover_ledger` manifest | month or `all`；`all` 是 fan-out command，不是普通写操作默认 scope。relation context 通过一个 bounded SQL bundle 从 canonical `app.workbench_pair_relations` 的同一快照读取 active source rows 和 source summary，不串行等待 `workbench_relation` read model，也不允许行/版本跨快照。`all`/month scope 在 own source_versions 未变化、仅 canonical relation source summary 变化时，可以从现有 rows 重套 relation context 后保存，避免重建整本台账。`all` 查询由月度/行级 rows 拼接时允许 mixed row source_versions；repository 必须聚合所有 turnover 子月份 current-effective dirty 状态，任一 failed 为 stale，否则任一 pending/processing 为 refreshing，全部 clean 才为 fresh。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 外部往来款 rows/summary | 前端页面 | query gateway 后 fresh/status |
| 页面 Audit 状态 | 标题附件 | unknown/non-fresh 不得显示 Fresh；样本截断必须显式呈现 |
| 写操作结果 | API/frontend operation barrier | 可审计、幂等或有版本保护；返回 `affected_months`、`affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` |
| Workbench active relation | `workbench-relations` | 只通过 `WorkbenchRelationCommandService` 写入/撤回；`turnover_manual_closure` relation metadata 明确声明 OA/发票 requirement。metadata 缺失的旧关系必须 fail closed，等待规则保存同步链路升级 |
| Dirty scope | runtime queue | `turnover_ledger.read_model.refresh` |
| 导出 | 用户下载 | 复用查询权限和筛选 |

## 持久化与投影

- Read model：`turnover_ledger`
- Projection：`partitioned_scoped_incremental`
- 生产投影必须信任 `BankTransactionTagReadFacade` 输出的 fresh bank-detail tag 事实；只有无 provider 的 legacy/local 路径才允许回退 `BankTransactionCategoryService` snapshot。禁止在 provider-backed worker hot path 逐笔读取旧 category service。
- 关系 enrichment 必须通过 `WorkbenchRelationReadModelRepositoryPort.workbench_relation_source_bundle_from_source(...)` 读取 `app.workbench_pair_relations`；rows 与 source summary 必须来自同一个 SQL 快照。这是只读 shared-fact I/O，不读取或等待 `read_model.workbench_relation_*`。canonical source 不可用时不得伪造 linked relation context。
- grouped 当前台账不得消费 `withdrawn` relation；撤回历史只留在 relation snapshot/audit log。系统自动关系恢复后，同一 bank leaf 在 grouped financial totals 和 flow rows 中只能计算一次。
- `turnover_relation_snapshot_version` 只散列会改变当前台账的 canonical `confirmed` relations，并按 `relation_id` 稳定排序；`withdrawn` relation 与 audit history 不属于当前 projection 输入。确认必须改变该版本，撤回完成后版本必须回到操作前值，避免 audit-only 历史让 fresh worker 结果被 API 永久误判为 stale。
- `all` 聚合查询不得要求所有行级 source_versions 完全一致；按月增量 worker 刷新会让不相关月份保留旧 provenance。Query owner 只能在 repository 标记 mixed row versions 且 durable dirty scope 为 fresh 时把 all-view 判为 fresh，不能绕过 dirty scope。
- 列表 page payload 只能从规范化 `payload` 读取；family/status/scope/direction、总 summary、family summaries 和 total 在 PostgreSQL 中计算，第二条 data query 只读取当前 `page_size<=200` 的 payload。筛选为空但 projection 已存在时返回 fresh 空结果，不得误触发 rebuild。
- `raw_payload` 不属于 turnover 新 projection 的业务读取合同，v6 新写入固定为空对象；完整业务 payload 只由 `payload` 拥有。
- Worker：`turnover-ledger`
- Query owner：`TurnoverLedgerQueryService`
- Repository owner：`TurnoverLedgerReadModelRepositoryPort`，仅暴露 `list_turnover_ledger_view`、`save_turnover_ledger_rows`。

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
- Downstream outputs: turnover_ledger、workbench_relation、workbench、cost、search dirty scopes 或 owner producer 输出。
- Forbidden paths: query/service 不得回退 live page builder 或 raw payload；write facade 不得进入 direct relation fallback；不能直接写 workbench relation 或 bank category facts；不能从银行明细或 Application helper 直接清 `turnover_ledger` read model；local adapter 不得读写 Settings 私有 snapshot 或整份 settings store。
- Old code deletion: app read forwarding facade、query live fallback/settings switch、relation mutation legacy invalidation adapter、dead relation repository adapter、确认/撤回全量 relation snapshot rebuild/save、turnover projection 的 workbench-relation read-model wait、producer/repository direct clear I/O、direct relation fallback、snapshot bank-row source fallback、raw payload 双写和 Settings snapshot save/refresh fallback 已删除；migration/audit/rollback 工具保留不算 closure。

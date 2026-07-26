# 外部往来款管理模块边界与 I/O

日期：2026-07-26

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：外部往来款页面读取 `turnover_ledger` read model；写操作通过 write facade/UoW/adapters 只更新所属 canonical facts/version/audit，页面访问时再收敛精确 scope。
- 当前闭环：read path 由 `TurnoverLedgerApiRoutes` route owner 进入 `TurnoverLedgerQueryService` / read model；query service 先读取 `all` scope 的轻量 freshness/source proof，只有明确 fresh 后才执行固定查询数的 SQL 过滤、汇总和有界分页。repository miss/version drift 只允许经 `ReadModelQueryGateway` fail-closed/enqueue，不存在 live page builder fallback。仅 canonical `turnover_manual_closure` proof 变化时，访问入口从 canonical relation history 推导精确月份、bank row 与 relation delta；其它业务 source drift 才 fail closed 为显式 full-`all` refresh。write path 由 request-boundary facade 进入 `TurnoverLedgerWriteFacade` / UoW / explicit adapters；现代 closure confirm 经 Turnover domain 校验后只写 canonical Workbench relation，通用 suggested relation confirm/withdraw 仍写 Turnover-owned relation/audit。普通 closure/relation/tag/extra/settings 写入不产生任何页面 dirty/outbox；当前可见页面仅通过正常 GET 重校验当前 scope。
- 旧代码删除状态：`TurnoverLedgerReadFacade` app 转发壳、`TurnoverLedgerRelationMutationInvalidationLegacyAdapter`、`TurnoverLedgerRelationRepositoryAdapter`、确认/撤回的全量 `rebuild_from_bank_rows`/`save_turnover_relations` 链、现代 closure 的重复 Turnover relation/event 持久化、无收益的 `turnover-ledger-secondary`、turnover projection 对 `WorkbenchRelationReadFacade(require_fresh=True)` 的串行依赖、`Application._after_turnover_relation_mutation(...)`、`Application._refresh_local_app_settings_snapshot(...)`、refresh producer direct clear、query service `legacy_payload_builder/settings_provider` 分叉、repository `clear_turnover_ledger_rows` port、UoW 按 request/scope 逐条 enqueue、幂等事务外预查、同一 selected bank rows 的版本校验/closure preview 重复读取、确认闭环前的前端整页 reload、用整个 Bank Detail 页面 freshness 阻塞精确所选行写入、cash-closure 撤回的 current relation 二次加载、`assert_turnover_manual_closure_write_precondition` 独立预检、`_active_relations_for_row_ids_from_command` 二次快照热路径，以及 no-OA 规则保存后扫描并回写 turnover relation requirement 的旧同步链已删除；列表不再从 `raw_payload` 回退业务行 payload，projection 不再复制规范化 payload；边界 guard 防止恢复。

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
| 页面只读 Audit | `PageBusinessAuditIcon` / AppHealth operations API | admin-only 调用 `page-audit?page=turnover-ledger`；canonical expected-set 从 active bank facts + fresh bank-detail effective turnover fields + 当前 tag selection 独立形成，并按 `family + counterparty` 聚合完整 bank member set，与页面 group 双向相等；余额按去重 leaf 分方向重算（有本金时结算最多冲减到零，纯结算组保留负余额），待还/已还/待收/已收分别按 leaf action/amount 重算，ledger extras 另行核对；ledger/flow payload 必须保留 `workbench_relations` 的 case/status/mode/source/typed members。共享 edge equality 只检查共享 distribution eligible modes；`turnover_manual_closure` 由 Turnover 自身 canonical source/version、row relation summary 和 Workbench 主 generation proof 覆盖，不要求出现在共享 rows/groups。全部检查位于同一只读一致性快照，只消费结构化 audit status 与 issue samples，不进入本模块写 facade |
| 确认/撤回写操作 | write facade/UoW | 只保存所属 canonical relation/category/event/audit 与可比较版本，不输出 turnover/workbench/workbench_relation/cost/search 或其它页面 dirty/outbox，不返回 operation barrier target。银行流水分类批量更新仍共用 `BankTransactionCategoryMutationWriter`，在同一事务批量写 canonical category/event/audit，禁止恢复分类全量 snapshot 保存、逐行事务或二次 enqueue。现代 closure confirm 只读取所选 bank rows；在同一写事务内以 canonical `bank_transactions.updated_at`、活动分类/确认版本及当前自动规则版本校验 `selection_version`，再执行一次成员锁和一次 scoped relation snapshot。整个 Bank Detail 页面因其它 scope stale 不得阻塞本次选择；任一所选事实不一致返回 `409 turnover_relation_conflict`，精确校验边界不可用返回 `503 turnover_bank_row_selection_unavailable`。所有 bank member 必须属于 selected ids，且 requirement metadata 从同次 settings 读取冻结。cash-closure withdraw 复用同一 transaction-bound preparation，禁止二次加载关系。跨月操作保留精确月份作为信息性 scope hint，无法得到精确月份时 fail closed，禁止恢复 `all` 写后 fan-out。 |
| 标签选择写操作 | write facade/UoW + Settings domain port | PostgreSQL 路径通过 supplied transaction 保存 canonical settings/audit/version，不写页面 refresh outbox；本地路径只调用 `AppSettingsService` 的 tag-selection state/commit/restore 端口，不得直接访问 `_snapshot` 或 `state_store.save_app_settings(...)` |
| Workbench relation requirement | `TurnoverLedgerWorkbenchPairPort` | 创建 `turnover_manual_closure` 时必须从所选银行行的有效分类标签与一次 canonical rule payload，通过 `build_bank_relation_requirement_metadata(...)` 冻结 tag code、`requires_oa`、`requires_invoice`、`paired_requirement_source`、`paired_requirement_version`；这些字段是关联台分区的唯一输入，不能由关联台查询当前设置兜底，也不能由规则保存追溯回写 |
| Refresh scope | `turnover_ledger` manifest | month or `all`；`all` 是显式完整重建 command，不是普通写操作默认 scope。relation context 通过一个 bounded SQL bundle 从 canonical `app.workbench_pair_relations` 的同一快照读取 active source rows 和 source summary，不串行等待 `workbench_relation` read model，也不允许行/版本跨快照。`turnover_manual_closure` 属于 Turnover 自身 canonical proof，不进入共享 relation distribution/source version。访问入口只有在唯一 mismatch 是 `turnover_manual_closure_source_version_mismatch`、已发布与当前 closure proof 都完整、且 canonical change rows 能安全给出 case/status/row_ids/affected_months 时，才把每个月份作为 exact scope 并携带 `relation_deltas`、`row_ids`；任一条件缺失都显式回退 full-`all`，禁止猜测局部范围。精确月份事件由 turnover worker 按 `scope_month + bank_row_ids overlap` 只读/更新受影响 grouped rows，禁止读取全月 payload/对象/relation 集合或 delete/rewrite 整月。导入、标签、设置、extra 和其它 own-source drift 仍按自身 source 变化执行完整 scope 投影。worker 连续处理同一 canonical source version 的多个 month scope 时，只允许复用一份进程内基础 rows 计算结果；cache key 必须等于完整 own source_versions，版本变化立即失效，cache 不带 TTL、不跨进程、不作为事实源或 stale fallback。`all` 查询由月度/行级 rows 拼接时允许 mixed row source_versions；公开 freshness/source proof 以原子发布的 `turnover_ledger_scopes:all` 和全部 current-effective child dirty 已收敛为准。任一 child failed 为 stale，任一 pending/processing 为 refreshing，全部 clean 且 all scope proof 匹配才为 fresh。 |

普通 relation/tag/settings/extra 写入只推进 canonical version，不创建上述 refresh event。只有当前页面 GET 检测 source mismatch，或显式 import/reapply/repair 合同，才可通过正式 gateway 创建精确 scope job。

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 外部往来款 rows/summary | 前端页面 | query gateway 后 fresh/status；完整重建和 relation delta 在发布事务内从未筛选 read-model rows/`flow_rows` 计算标题 `statistics`（去重流水、收支、台账组、结清、OA/发票关联），原子写入 `read_model.turnover_ledger_scopes`；请求 SQL 只读取 scope summary 标量，不再展开 `flow_rows`，且统计不受页面筛选、排序或分页影响；0 行 generation 仍由 scope row 证明存在并 fresh 返回全零统计；轻量 proof 非 fresh 时必须在 page SQL 前返回空 `rows`、`statistics=null` 与 refreshing/stale status，并触发 scoped refresh，禁止返回旧 rows、读取重 page SQL 或用银行 canonical/统一事实源替代 |
| 页面 Audit 状态 | 标题附件 | unknown/non-fresh 不得显示 Fresh；样本截断必须显式呈现 |
| 写操作结果 | API/frontend | 可审计、幂等或有版本保护；grouped flow row 暴露 opaque `selection_version` 供精确 OCC，前端不得解析。确认点击后立即进入 `确认中…`/disabled 状态，直接提交当前已加载选择，不执行确认前整页 GET；写成功后只重跑当前可见页面的正常 GET，不轮询全局 App Status。返回业务 receipt 与信息性 affected scopes，`freshness_targets` / `operation_barrier_targets` 为空 |
| Workbench active relation | `workbench-relations` | 只通过 `WorkbenchRelationCommandService` 写入/撤回；`turnover_manual_closure` relation metadata 明确声明 OA/发票 requirement。active 仅表示 ownership，未满足冻结 requirement 的同一个 case 发布到未配对区；metadata 缺失的旧关系必须 fail closed，只能通过受控 repair 补齐，规则保存不得扫描或升级既有 relation |
| Dirty scope | runtime queue | `turnover_ledger.read_model.refresh` |
| 导出 | 用户下载 | 复用查询权限和筛选 |

## 持久化与投影

- Read model：`turnover_ledger_rows` 业务行 + `turnover_ledger_scopes` generation/row-count/statistics summary
- Projection：`partitioned_scoped_incremental`
- 生产投影必须信任 `BankTransactionTagReadFacade` 输出的 fresh bank-detail tag 事实；只有无 provider 的 legacy/local 路径才允许回退 `BankTransactionCategoryService` snapshot。禁止在 provider-backed worker hot path 逐笔读取旧 category service。
- 关系 enrichment 必须通过 `WorkbenchRelationReadModelRepositoryPort.workbench_relation_source_bundle_from_source(...)` 读取 `app.workbench_pair_relations`；rows 与 source summary 必须来自同一个 SQL 快照。这是只读 shared-fact I/O，不读取或等待 `read_model.workbench_relation_*`。canonical source 不可用时不得伪造 linked relation context。
- 页面与 worker 的基础 source vector 必须额外包含 canonical `app.workbench_pair_relations` 中 active `turnover_manual_closure` 的 count/max-updated proof；confirm/withdraw 即使不改变 Turnover 自有 relation snapshot，也必须使下一次页面访问判 stale。该查询归 workbench-relations repository 所有，Turnover service 不直接写 SQL。
- grouped 当前台账不得消费 `withdrawn` relation；撤回历史只留在 relation snapshot/audit log。系统自动关系恢复后，同一 bank leaf 在 grouped financial totals 和 flow rows 中只能计算一次。
- `turnover_relation_snapshot_version` 只散列通用 suggested-relation 链会改变当前台账的 canonical `confirmed` Turnover relations，并按 `relation_id` 稳定排序；`withdrawn` relation 与 audit history 不属于当前 projection 输入。现代 closure confirm/withdraw 只改变 Workbench canonical context，不得改变该版本；通用 relation 确认改变版本、撤回后回到操作前值。
- Month projection 首次读取的现有 read-model page 必须在 unchanged 检查和 relation-only refresh 之间复用，禁止对 page 1 重复 SQL；同一 worker 内的基础 grouped rows memoization 只能保留最近一个完整 source-version 快照，调用方得到副本，任何 source-version 变化都必须重新读取 canonical facts 并重算。
- Relation-only month refresh 的正式 I/O 是 `load_turnover_ledger_relation_delta(...)` / `save_turnover_ledger_relation_delta(...)`。查询依赖 `turnover_ledger_rows_bank_row_ids_gin`，保存不得 delete scope；它必须与 affected month 及 `all` scope summary 在同一事务更新。完整 `save_turnover_ledger_rows(...)` 只属于 own-source 变化、repair、首次构建或明确安全 fallback，并同样原子发布对应 scope summaries。full/month/delta/unchanged acknowledgement 共享唯一 turnover advisory transaction lock，并在写前比较内部 global generation 与目标 scope 的 event `published_source_version`；先获得锁再做 CAS，锁集合恒为一个，禁止增加 month/all 多锁顺序。CAS 失败必须中止整个事务并由 worker 重试，旧 generation 不得覆盖新 projection。
- `all` 聚合允许精确月份 relation delta 完成后存在不同月份的行级 `source_versions`；页面不得把行级版本改写成 expected，也不得仅因跨月 mixed 强制 full-`all`。公开 `all` source proof 来自与 rows/statistics 同事务发布的 `turnover_ledger_scopes:all`，并且所有 current-effective child dirty 必须收敛。单个月份内部 mixed、all scope proof 缺失或 relation change 无法安全定位时仍 fail closed，并显式执行对应完整 month 或 full-`all` 重建。
- 列表 page payload 只能从规范化 `payload` 读取；family/status/scope/direction、总 summary、family summaries 和 total 在 PostgreSQL 中计算，第二条 data query 只读取当前 `page_size<=200` 的 payload。筛选为空但 projection 已存在时返回 fresh 空结果，不得误触发 rebuild。
- `raw_payload` 不属于 turnover 业务行读取合同，完整业务 payload 只由 `payload` 拥有；不得恢复业务 payload fallback，也不得把 scope metadata/统计寄存在任一业务行。`turnover_ledger_scopes` 是 generation 存在性、source versions、row count、标题 statistics 与内部 CAS metadata 的唯一持久边界；scope row 缺失或 row count 不一致时 statistics 判为 stale，并复用现有 scope rows 补发。`generation` / `published_source_version` 只允许 repository port 与 builder 消费，禁止进入公开 API DTO。
- Worker：`turnover-ledger`
- Query owner：`TurnoverLedgerQueryService`
- Repository owner：`TurnoverLedgerReadModelRepositoryPort`，暴露轻量 `get_turnover_ledger_freshness_view`、canonical `list_turnover_manual_closure_changes`，以及 `list_turnover_ledger_view`、`save_turnover_ledger_rows`、`turnover_ledger_generation`、`acknowledge_unchanged_turnover_ledger_scope`、`load_turnover_ledger_relation_delta`、`save_turnover_ledger_relation_delta`。query service 不直接写 closure SQL。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/TurnoverLedgerPage.tsx` |
| Frontend feature/components | `web/src/features/turnoverLedger/*`、`web/src/components/turnoverLedger/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` |
| Backend service | `turnover_ledger_service.py`、`turnover_relation_service.py`、`turnover_ledger_query_service.py`、`turnover_ledger_write_facade.py`、`turnover_ledger_write_uow.py`、`turnover_ledger_write_adapters.py` |
| Repository / SQL | `turnover_ledger_read_model_repository.py`、`turnover_ledger_sql_projection.py`；银行流水分类写入复用 `postgres_repositories/bank_transaction_category.py` |
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
- Downstream outputs: 普通 turnover 写入无页面 read-model dirty scope/outbox；受影响消费者在访问时各自验证 canonical source version 并精确收敛。
- Forbidden paths: query/service 不得回退 live page builder 或 raw payload；write facade 不得进入 direct relation fallback；不能直接写 workbench relation 或 bank category facts；不能从银行明细或 Application helper 直接清 `turnover_ledger` read model；local adapter 不得读写 Settings 私有 snapshot 或整份 settings store。
- Old code deletion: app read forwarding facade、query live fallback/settings switch、relation mutation legacy invalidation adapter、dead relation repository adapter、确认/撤回全量 relation snapshot rebuild/save、turnover projection 的 workbench-relation read-model wait、producer/repository direct clear I/O、direct relation fallback、snapshot bank-row source fallback、raw payload 双写和 Settings snapshot save/refresh fallback 已删除；migration/audit/rollback 工具保留不算 closure。

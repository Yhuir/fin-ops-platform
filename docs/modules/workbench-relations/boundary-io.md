# 关联台关系事实源模块边界与 I/O

日期：2026-07-04

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：关系写入、撤回、展示、历史回放和下游 read model 扇出统一通过 workbench relation command/read boundary。
- 当前缺口：仍有多个页面和历史修复工具调用关系相关 service，后续删除旧链路必须逐调用点核验。
- 旧代码删除条件：所有确认/撤回/修复调用点都通过 command service 或明确 adapter，且下游 fan-out 测试覆盖。

## 职责边界

### 负责

- 关联关系事实源，包括配对、撤回、关系展示、关系历史和分布投影。
- 产生 workbench_relation read model 和下游页面刷新依据。
- 为 pending invoice、no-OA、turnover、batch accounting、ETC 等模块提供关系读取边界。

### 不负责

- 不拥有下游页面 read model 的最终投影。
- 不直接替代各页面的业务 service。
- 不在调用方模块散落关系状态机判断。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 关系写命令 | workbench、workbench matching、batch accounting、pending invoice、no-OA、turnover、ETC 修复工具 | 必须包含关系对象、方向、操作上下文和审计身份。跨进程或生产修复场景必须让 command repository 的 load/save 接入 durable repository，不能只读进程内 `WorkbenchPairRelationService` snapshot。自动 paired decision 只有通过 command service 写成 active relation 后，才算业务已配对。 |
| 已知 row/case 的关系命令读取 | `WorkbenchRelationCommandService.confirm_relation(...)`、按 row 撤回/预览、按 case 更新/撤回 | 必须通过 `load_workbench_pair_relations_for_row_ids(row_ids, case_ids=...)` 读取 scoped snapshot，只加载可能与目标 row 冲突的 active relation 和目标 case/history。禁止在这些热路径调用 `load_workbench_pair_relations()` 全量快照；全量 loader 只允许全量列表、离线审计、迁移或明确需要遍历所有 relation 的场景使用。 |
| 撤回 row id alias | `WorkbenchWriteFacade` -> `WorkbenchRelationCommandService.preview_withdraw_relation(...)` / `withdraw_relation(...)` -> `WorkbenchPairRelationService.preview_withdraw_for_row_ids(...)` / `withdraw_latest_for_row_ids(...)` | 撤回 preview 和 submit 必须显式携带 `row_id_aliases`，把历史 relation fact 中残留的 OA source id 映射到 canonical Workbench row id。恢复历史 relation 时，`restorable_on_withdraw=true` 仍必须经过 alias-aware canonical row-set 比较；canonical 后与当前 active relation 同 row-set 的历史快照不能恢复，必须展示/提交为撤回到无关系状态。OA 自带附件发票 binding 不走 history restore 标记：完整 relation 撤回后必须保留或重建 OA+自带附件发票 active relation，纯 OA+自带附件发票 relation 的撤回 preview 必须不可提交，submit 必须被拒绝。 |
| OA 附件发票不可变 binding | `WorkbenchOaAttachmentContextRowIndex`、`WorkbenchCanonicalOaAttachmentRawPayloadRepairer`、`WorkbenchOaAttachmentRepairContextExecutor`、`WorkbenchPairRelationService`、`WorkbenchRelationCommandService`、`WorkbenchCandidateGroupingService`、`oa_attachment_invoice_linking` | `oa-att-inv-<oa-row-id>*` 或通过 OA source alias 可证明来自父 OA 的发票必须和该 OA 处于同一个 active relation。该 relation 是 source binding，不是用户配对结果；不能只作为 display-only candidate，也不能被普通撤回拆成 OA standalone + 发票 standalone。 |
| 撤回提交 preview lock | `WorkbenchRelationCommandService.withdraw_relation(...)` | submit 路径必须在同一个 canonical pair-service snapshot 上完成 active relation 读取、preview lock 和状态转换；只允许一次 relation read model fresh precondition。preview lock、恢复历史 relation 和 submit 状态转换必须使用同一份 alias-aware after relation 合同。禁止 submit 内部先按 case 加载 snapshot，又调用 public preview API 重新加载 snapshot/重复 fresh check。 |
| no-OA relation metadata | `NoOaBankBatchApplicationService` | legacy `special_metadata` 可包含 `paired_requires_oa`、`paired_requires_invoice`、`paired_requirement_tag_code`、`paired_requirement_version`；关系事实源负责原样保存和投影，不拥有标签规则解释 |
| Bank Transaction Paired Policy metadata | `BankFlowRuleBatchApplicationService` submit / tag-rule sync / turnover sync / legacy no-OA submit | 所有含银行流水的 relation facts 应把 paired policy 物化到银行流水 row 可投影的 `special_metadata.requires_oa` / `requires_invoice` 或 legacy `paired_requires_oa` / `paired_requires_invoice`。`relation_mode=bank_flow_rule_batch` 的 metadata 还至少包含 `source_batch_id`、`flow_rule_tag_code`、`flow_rule_version`、`source_row_count`、`collapsed_bank_rows`；`row_types=["bank"]` 且已有 `month_scope` 的内部往来提交，relation fan-out scope resolver 必须直接使用 relation month，禁止再探测 invoice/OA/workbench source 表或银行月份 scope。标签规则保存后也必须通过 command service 更新这些 requirement 字段。关系事实源只保存和分发，不解释银行标签规则。 |
| 外部往来闭环 relation metadata | `TurnoverLedgerWorkbenchPairPort` / 流水规则 tag-rule sync | `relation_mode=turnover_manual_closure`；`special_metadata` 至少包含 `source=turnover_ledger`、`turnover_relation_id`、`requires_oa`、`requires_invoice`、`paired_requirement_source`、`paired_requirement_version`。历史 `turnover:* manual_confirmed` 关系只能通过 `WorkbenchRelationCommandService.update_relation_metadata_for_case_id(..., relation_mode=turnover_manual_closure)` 受控升级并记录 before/after history |
| 关系读请求 | 下游 read facade/service | 只暴露 read facade 或 repository port |
| 批量账务 submitted count | `BatchAccountingService` | 未提交首屏通过 `WorkbenchRelationReadFacade.count_batch_accounting_relations_by_year(year)` 读取年份级 batch-accounting relation count 和 freshness/status；禁止为了 summary count 读取 12 个月 relation DTO |
| 批量账务 submitted relation DTO | `BatchAccountingService` | 已提交 bucket 通过 `WorkbenchRelationReadFacade.list_batch_accounting_relations_by_year(year)` 一次读取年份内 active batch-accounting relation groups 和 freshness/status；禁止调用方按 12 个月循环 list 或直接 SQL 读 relation read model 表 |
| 批量账务 relation metadata | `BatchAccountingService.submit` | `relation_mode=batch_accounting`、`special_metadata.source=batch_accounting`、`bank_row_id`、`oa_row_ids`、`invoice_row_ids`、`bank_year`、`oa_years`、`affected_scope_keys`。关系事实源负责原样保存并投影；`affected_scope_keys` 是 command repository dirty/outbox fan-out 的 scope I/O，跨月关系也应是具体月份集合，不应自动变成 `all`。批量账务撤回必须通过 command service 的取消语义把当前 batch relation 持久化为 cancelled，并记录 `withdraw_link` history；不得走调用方旧 snapshot restore 或 in-memory-only fallback。 |
| Refresh scope | `workbench_relation` manifest | month scope；`all` 只允许明确 fan-out command。批量账务 submit/withdraw route 不再直接触发 duplicate lifecycle；repository 必须根据具体月份 scope 投递 dirty/outbox，不能把 all 当默认后置刷新 |
| Projection source objects | `app.bank_transactions`、`app.oa_applications`、`app.invoices`、`app.workbench_pair_relations` | `workbench_relation` 月分片投影先读取本月源对象，再读取 active relation；关系成员若已存在于本月对象集，禁止第二次全月扫描。只有跨月 relation 的缺失成员可按显式 `row_id` 补读，并且必须根据 relation `row_types` 限定到 bank/OA/invoice 所需源表。OA 源对象完成态由 OA projection 边界统一定义，必须接受 canonical `completed` 和历史完成态别名，不能让 relation distribution 因 workflow status 表示差异丢失 `linked_oa` summary。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 关系事实 | repository | 原子持久化关系状态和审计 |
| 关系 read model | `workbench_relation` projection | scoped incremental distribution；`rows` 是 scope 内 row 索引，唯一键为 `(tenant_id, scope_key, row_id)`；只向下游分发 active relation 的 linked/unlinked 业务口径，不分发 automatic decision candidate。 |
| 下游 dirty scope | runtime queue | command repository 按受影响页面 fan-out |
| no-OA / 流水规则批量 read model dirty scope | `no_oa_bank_batch` runtime queue | `relation_mode=no_oa_bank_batch` 与 `relation_mode=bank_flow_rule_batch` 共用迁移期底座，但 dirty/outbox payload 必须携带 `relation_mode`，outbox dedupe key 必须按 relation mode 分桶；不能让同一月份 no-OA 与 bank-flow 刷新互相覆盖 metadata。 |

## 持久化与投影

- Read model：`workbench_relation`
- Projection：`scoped_incremental_distribution`
- Worker：`workbench-relation`
- Repository owner：`WorkbenchRelationReadModelRepositoryPort`
- Query owner：`WorkbenchRelationReadFacade`
- 跨月关系合同：一个 active relation 可同时包含 OA、银行流水、进项/销项发票等不同月份对象。每个被重建的 `workbench_relation` month scope 必须保存该 scope 内 relation group 涉及的所有成员 row 索引，而不仅是当前月份原生对象；下游页面按自身 row id 读取时必须能发现跨月 group。
- 源对象读取性能合同：月分片对象读取和跨月缺失成员补读是两个不同输入 I/O。普通同月确认/撤回后的 changed rebuild 不得恢复旧逻辑的第二次全月 `bank_transactions` / `oa_applications` / `invoices` 扫描；跨月补读也不得为了一个缺失发票 row 再探测银行和 OA 源表。该规则只改变 projection 读取计划，不改变 relation 状态机、read model payload schema 或下游 fan-out。
- 批量账务性能合同：未提交列表只做候选 row-id relation lookup 和年份级 submitted count；已提交列表才读取完整 relation DTO，并且必须使用年份级 `list_batch_accounting_relations_by_year` I/O。`count_batch_accounting_relations_by_year` 和 `list_batch_accounting_relations_by_year` 都是 read facade/repository port 合同的一部分，不能被调用方直接 SQL 替代。
- 批量账务写入合同：批量账务 submit/withdraw 不能在 command service 保存 relation 后再次调用旧 pair relation persist/snapshot restore、duplicate derived lifecycle 或旧 workbench read model persist。关系事实持久化和 read model dirty/outbox fan-out 只通过 command repository；调用方只消费 changed scopes 返回给前端。生产 PostgreSQL runtime 的 command service 必须接入 `PostgresWorkbenchRelationRepository`，否则 command 只能改变进程内 snapshot，会导致 API 成功但 `app.workbench_pair_relations`、`workbench_relation` 和关联台 active generation 不收敛。
- 命令读取性能合同：`PostgresWorkbenchRelationRepository.load_workbench_pair_relations_for_row_ids(row_ids, case_ids=...)` 是确认/撤回/按 case 更新等热命令的 durable 读入口，SQL 只能按 `row_ids` overlap 和显式 `case_id` 限定 relation，再按选中 case 读取 history。`WorkbenchPairRelationService.snapshot_case_ids(...)` 也只能输出相关 case 的 relation 和 history，不能把全量 history 带回 mutation persistence。旧 `load_workbench_pair_relations()` 全量读取不得重新接入这些热命令，否则会随着历史 relation 数量线性放大提交耗时。
- Workbench withdraw UoW 合同：`WorkbenchWriteFacade._withdraw_link_with_uow(...)` 不得在事务外读取 `WorkbenchPairRelationService.snapshot()`，也不得在异常时走旧 snapshot restore。rollback、idempotency、relation command write 和 read model dirty/outbox enqueue 必须由 `WorkbenchWriteUnitOfWork` 的单一事务边界承担；facade 只组装 command、调用 UoW 和映射 response。
- Workbench withdraw alias 合同：`row_id_aliases` 是撤回 command I/O，不是 UI 展示修正。pair service 的 `_restorable_relation_snapshots(...)` 必须在 alias-aware row-set 上过滤同一 active relation；facade 在 canonicalize restored/after relations 后还必须执行同一过滤，防止测试替身、兼容 adapter 或历史路径返回污染后的 after relation。
- OA 附件发票 binding 合同：row index 和 raw payload repair 必须用 OA canonical row id 和 source aliases（如 Mongo 文档 ID、OA 单号）识别附件发票父 OA；raw payload repair 必须在发现可证明的父 OA+自带附件发票且缺 active relation 时，通过 command service 创建 `CASE-OA-ATT-<oa_row_id>` source binding；pair service 必须在 withdraw preview/submit 的状态转换中维护父 OA+自带附件发票 active relation；command service 必须把纯 OA+自带附件发票撤回变成不可提交 preview 和业务错误，防止 API 绕过前端禁用按钮；grouping 必须把 immutable OA+附件发票两栏 active relation 留在 open/source binding group，不能把 source binding 当作进入 paired 区的业务完成条件。该规则不允许通过 `existing_case`、row payload `case_id` 或未标记 history 恢复任意旧关系。
- 旧逻辑已废弃：`read_model.workbench_relation_rows` 不允许再使用 `(tenant_id, row_id)` 全局唯一覆盖模型；迁移 `0077_workbench_relation_rows_scope_unique.sql` 建立目标约束，`0078_workbench_relation_rows_scope_unique_repair.sql` 为已应用早期 0077 的环境做幂等 forward repair，`0079_workbench_relation_rows_scope_unique_hardening.sql` 在已接受 0077/0078 checksum drift 的环境中重新断言目标唯一性并清理同 scope 重复投影行，避免最后一次重建的月份覆盖其它月份的关系索引。跨月成员索引属于 projection schema 合同，当前版本为 `2026-06-cross-month-relation-member-index-v1`；发布该版本后必须受控重建 `workbench_relation` 月份 shard，再重建依赖它的 `input_invoice_usage` 等下游 read model。OA 完成态别名变更由 `OA_PROJECTION_SYNC_VERSION=2026-07-03-completed-workflow-status-aliases-v1` 驱动重建，禁止在 pending invoice 等下游页面用 fallback 反推 OA。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Backend services | `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`、`workbench_relation_command_service.py`、`workbench_oa_attachment_repair_context_executor.py`、`workbench_candidate_grouping.py`、`workbench_relation_read_facade.py`、`workbench_relation_sql_projection.py`、`workbench_relation_read_model_refresh.py` |
| Adapters | `backend/src/fin_ops_platform/services/workbench_relation_command_repository_adapter.py`、`workbench_relation_repository.py` |
| Repository / SQL | `backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py`、`postgres_repositories/workbench.py` |
| Downstream callers | `pending_invoice_service.py`、`bank_flow_rule_batch_*`、`no_oa_bank_batch_*`、`turnover_ledger_*`、`batch_accounting_service.py`、`input_invoice_usage_oa_reverse_service.py`、ETC migration/repair services |
| Tools | `backend/src/fin_ops_platform/tools/link_existing_etc_batches.py`、`migrate_historical_etc_business_batches.py` |
| Tests | `tests/test_workbench_relation_*.py`、`tests/test_workbench_pair_relation_*.py`、downstream fan-out e2e specs |

## 依赖方向

- 允许依赖：repository port、audit、runtime queue、downstream scope mapping。
- 必须通过：command service for writes、read facade for reads。
- 禁止绕过：调用方直接改关系表、直接构造下游 read model payload、跳过撤回状态机。

## 测试与验证

- Core/service：`tests/test_workbench_relation_command_service.py`、`tests/test_workbench_relation_read_facade.py`。
- Withdraw alias regression：`tests/test_workbench_pair_relation_service.py::WorkbenchPairRelationServiceTests::test_withdraw_ignores_restorable_snapshot_with_same_canonical_alias_row_set`、`tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_preview_filters_same_canonical_alias_after_relation`。
- OA attachment immutable withdraw regression：`tests/test_workbench_pair_relation_service.py::WorkbenchPairRelationServiceTests::test_withdraw_preserves_oa_attachment_binding_without_history`、`tests/test_workbench_pair_relation_service.py::WorkbenchPairRelationServiceTests::test_withdraw_rejects_plain_oa_attachment_binding_relation`、`tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_preview_withdraw_relation_blocks_plain_oa_attachment_binding`、`tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_withdraw_relation_rejects_plain_oa_attachment_binding_submit`。
- Projection：`tests/test_workbench_relation_sql_projection.py`。
- Cross-month regression：`tests/test_workbench_relation_sql_projection.py::test_rebuild_indexes_cross_month_relation_members_in_current_scope`。同月撤回热路径还必须覆盖源表各只扫一次；跨月成员补读必须覆盖只按缺失成员类型补读。
- E2E fan-out：`web/e2e/workbench-relation-fanout.spec.ts`、`workbench-relations-*.spec.ts`。

## 当前缺口和删除条件

- 每个历史修复工具保留时必须写明迁移/兼容理由。
- 删除旧关系路径前必须证明确认关联和撤回都可通过业务逻辑恢复到原状态。

## Canonical facts ownership

- Owned facts: `app.workbench_pair_relations`、`app.workbench_pair_relation_history`。
- Allowed writes: `WorkbenchRelationCommandService`、relation UoW、明确 migration/repair adapter。`update_relation_metadata_for_case_id` 可更新 metadata/display tags/amount_check，并可在 command service 白名单校验后升级 relation mode；调用方不得绕过 command service 直接改 relation mode。
- Allowed reads: `WorkbenchRelationReadFacade`、relation repository/read ports。
- Downstream outputs: workbench_relation、workbench、bank_flow_rule_batch、pending invoice、input/output invoice usage、OA pending、tax、cost、search dirty scopes 或 owner producer 输出。
- `no_oa_bank_batch` 下游输出在过渡期同时覆盖 no-OA 与 bank-flow 批量处理：关系事实源只根据 relation payload 的 `relation_mode` 分发，不解释业务规则；worker handler 必须从 payload/metadata 读取目标 relation mode。
- Forbidden paths: 调用方不得直接改关系表、不得自行拼 confirmed relation 状态、不得通过 legacy fallback 绕过 command service。
- Old code deletion: direct pair relation write fallback、旧关系修复半写入和调用方内联关系状态机必须删除；离线 migration/audit/rollback 工具保留不算 closure。

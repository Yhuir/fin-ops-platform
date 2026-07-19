# Bank Transaction Paired Policy / 流水规则批量处理模块边界与 I/O

日期：2026-07-20

## 模块化状态

- 状态：close
- 当前边界可信度：closed for API/UI/application service/relation rules/paged read I/O/bulk detail and reset/read model runtime/physical batch storage/tag-rule settings family/frontend feature split/workbench summary I/O
- 本 slice 范围：生产入口、API、全局 Bank Transaction Paired Policy 规则抽屉、批量提交、关联台分区判定、旧 bank-flow/no-OA 历史重算页面链路清理、文档和自动化测试。
- 当前边界：本模块是 Bank Transaction Paired Policy 的规则管理入口，`requires_oa` / `requires_invoice` 只用于候选校验、新批次审计提示和 source version，不决定关联台 paired/unpaired 分区。HTTP route、application service、read model key、refresh producer、worker event、operation barrier target、repository port、mutation persistence port、refresh persistence port、PostgreSQL 批次存储、read model row 表和 tag-rule settings family 已独立为 `bank_flow_rule_batch`。旧 no-OA 模块只保留自身 legacy API 与历史批次功能，不再承接 bank-flow 新链路。
- 当前缺口：无已知生产链路模块边界缺口。页面级 state/effect 编排仍保留在 `BankFlowRuleBatchPage.tsx`，纯 I/O、DTO、策略、view model、operation barrier helper 和通用组件位于 `web/src/features/bankFlowRuleBatches/`。新功能生产路径不接收 `selected_tag_codes`；旧 no-OA `selected_tag_codes` 写路径只属于 legacy no-OA 域。
- 旧代码删除条件：closed。bank-flow 新链路不得 import/继承 no-OA route、application service、derived lifecycle executor、read model refresh、persistence port、no-OA worker 或 no-OA physical batch/read-model 表；不得输出 `no_oa_bank_batch_summary`、`no_oa_bank_batch_*` HTTP error code、`no_oa_bank_batch` relation display code、`no-oa-*` Browser transaction/batch id 或 `免OA` display tag/成本项目名作为 bank-flow I/O。route legacy error translation map、同步 reset rebuild、逐成员银行流水读取、逐 relation reset cancel 和前端同步等待全部下游 freshness 的旧路径已删除；architecture guard 禁止回归。no-OA 主入口、`selected_tag_codes` 写路径和 no-OA 常驻 worker只属于 no-OA legacy 业务，不得重新接入 bank-flow。

## 职责边界

### 负责

- 流水规则批量处理页面和右侧紧凑 xlsx/grid 抽屉。
- 读取银行明细 active 标签事实，并为每个标签维护全局 Bank Transaction Paired Policy：`requires_oa` / `requires_invoice`。
- 基于用户当前选择的银行流水创建批量 relation，并把提交时规则值写入历史审计 metadata。
- 规则保存只触发独立 `bank_flow_rule_batch` read model 刷新；批次 relation 写入由 relation owner 输出其自身及跨页下游刷新。

### 不负责

- 不新增、编辑或删除银行明细标签。
- 不拥有银行流水、银行分类、OA、发票或 Workbench relation canonical facts。
- 不在前端本地伪造 paired/open 状态。
- 不绕过 `WorkbenchRelationCommandService` 写入、取消或恢复 relation。
- 不把旧 `selected_tag_codes` 自动迁移成新规则事实。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 银行标签事实 | `bank-details` active tag read facade / 自动标签规则 payload | 只读。每个标签至少包含 code、direction、primary label、sub label、status 和 rule version。标签增减必须反映到本模块抽屉左侧。 |
| 标签闭环规则 | `GET/PUT /api/bank-flow-rule-batches/tag-rules` | 本模块拥有 `app_settings.bank_flow_rule_batch_tag_rules` 中的规则版本和 `requirements_by_tag_code`。未知、停用、重复 tag code fail fast。新增/未配置标签默认 `requires_oa=true, requires_invoice=true`。 |
| 页面查询 | `BankFlowRuleBatchPage.tsx` | 查询候选/已提交/已撤回批次，默认 page size 50；服务端通过专属 paged read port 执行 `LIMIT/OFFSET`、过滤范围 total 与 summary 范围聚合，查询数不随批次数增长，并携带 read model freshness/status。 |
| 页面只读 Audit | `PageBusinessAuditIcon` / AppHealth operations API | admin-only 调用 `page-audit?page=bank-flow-rule-batches`；non-deleted batch 及其精确银行成员集是 canonical expected-set，批次总金额/笔数必须从 canonical 银行流水按批次规则重算：普通批次求成员金额合计，内部转账一收一支只计单边金额，不能把两边绝对值重复相加；canonical batch、fresh page payload 和 `bank_flow_rule_batch` active relation 必须按 batch/case id 与完整 bank member set 相等，submitted 缺 relation、非 submitted 残留 relation、relation orphan 均阻断；同时要求共享 relation 双向 edge equality 与只读一致性快照；不得借 audit 绕过规则/提交/撤回 service 边界。 |
| 批量提交 | `POST /api/bank-flow-rule-batches/submit-selection` | `transaction_ids` 必填、非空、去重。提交前重查银行流水身份、月份、账户、标签、active relation 占用和当前规则版本。 |
| 已提交重置 | `POST /api/bank-flow-rule-batches/reset-submitted` | 批量撤回当前所有 submitted 批次，领域状态逐批校验，但 relation 通过一次 `cancel_relations_by_case_ids(...)` 取消，并以一次 `save_bank_flow_rule_batch_mutation(...)` 原子保存 changed relations 与显式 changed batch IDs；请求内不得同步逐月 rebuild。旧批次保留 withdrawn/audit history，释放的银行 rows 由现有 scoped worker 后台重新投影。 |
| 权限/session | API session / permissions | 读取、保存规则、提交批次、撤回批次、reset 分别校验权限；缺权限 fail fast。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 标签规则 payload | 前端抽屉 | 返回 `active_tags`、`rules`、`requirements_by_tag_code`、`version`、`bank_auto_tag_rules_version`、`permissions`。不返回 `selected_tag_codes` / `inactive_selected_tag_codes`，不返回可编辑左侧标签字段。 |
| 标签规则保存副作用 | `bank_flow_rule_batch` read model | 语义变化时单次写 settings、单次写 audit，并通过 owner producer 只 enqueue `bank_flow_rule_batch/all`；相同规则为 no-op。禁止读取或改写 existing Workbench/turnover relation，既有 relation metadata 保持提交时的历史快照。 |
| 批次列表 payload | 页面 | 返回 summary、当前页 rows、status bucket、read model status、stale reasons、scope keys 和分页信息。summary 由 SQL 对完整 summary filter 范围聚合，不能由当前页推算；非 fresh 不能展示为真实空态。 |
| 页面 Audit 状态 | 标题附件 | 只有结构化 status 与页面 read model 都 fresh/pass 才显示成功；issue counts 是样本。 |
| Relation command | `workbench-relations` | 使用 `relation_mode=bank_flow_rule_batch`，行级 relation display code 必须保持 `bank_flow_rule_batch`，不能退回 `fully_linked` 或 `no_oa_bank_batch`。metadata 至少包含 `source_batch_id`、`flow_rule_tag_code`、`flow_rule_version`、`requires_oa`、`requires_invoice`、`source_row_count`、`collapsed_bank_rows`；display tags 使用 `流水规则` + 业务标签，不能继承旧 `免OA` 标签。 |
| 关联台展示 | `reconciliation-workbench` | paired/unpaired 只由 active formal relation 决定：active relation 的完整成员进入 paired，无 active relation 的事实进入 unpaired singleton。requirement metadata 不参与分区。银行流水数 `>3` 时默认折叠，折叠摘要必须使用 `source_kind=bank_flow_rule_batch_summary`、summary id prefix `bank_flow_rule_summary:`、`invoice_relation.code=bank_flow_rule_batch`、`流水规则` display tag 和“流水规则批次”撤回文案。 |
| Browser fixture / E2E | `web/e2e/bank-flow-rule-batches-flow.spec.ts` / `web/e2e/fixtures/apiMocks.ts` | 本模块浏览器链路的测试 I/O 必须使用 `bank-flow-rule-e2e-*` transaction id、`bank-flow-rule-batch-e2e-*` batch id、`bank-flow-rule-relation-e2e-*` relation case id、`bank_flow_rule_batch_*` stale reason/error code 和 `流水规则手续费成本项目`；禁止用旧 `no-oa-*` id 或“免OA”成本项目名表示 bank-flow 行为。 |
| HTTP 错误 | 前端 API client | HTTP 输出边界只返回 `bank_flow_rule_batch_*` 错误码。共享 bank-batch core 由显式 `relation_mode=bank_flow_rule_batch` 直接产生正式错误码；`routes_bank_flow_rule_batches.py` 不得保留 legacy translation map、message fallback 或 no-OA compatibility branch。 |
| Operation barrier | 前端 | 写成功后返回 `affected_months`、`affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets`。批量提交、撤回和 reset 的完整 target envelope 必须同时包含页面自身 `bank_flow_rule_batch` 受影响 month scope，以及关联台实际读取的 `workbench_relation`、`workbench` 的 `all` + 受影响 month scope；不能由 route 覆盖 service 返回的目标，也不能只返回 `bank_flow_rule_batch` 后让关联台读取旧 `month=all` 空 generation。流水规则批量处理页面的单批内部往来提交和选中流水提交都以 command 成功为用户阻塞边界，前端立即清空当前选择、禁止自动选中下一笔触发 detail GET；`bank_flow_rule_batch` freshness wait 和 reload 只作为后台 reconcile I/O。完整跨页 visibility targets 必须继续通过 `workbenchRelationUpdated` 事件传给下游页面和全局刷新链路，禁止把 `workbench/all` 聚合刷新重新接入当前页提交阻塞链路。 |
| Dirty scope/outbox | runtime/read models | 通过 owner producer 或同事务等价 writer 污染 `bank_flow_rule_batch`、`workbench_relation`、`workbench`、`bank_detail` 以及受影响下游。 |
| Audit record | permissions/audit | 保存规则、提交、撤回、reset 都记录 actor、reason、before/after、affected rows/months 和 request id。 |

## 持久化与投影

目标 canonical facts：

- `app.bank_flow_rule_batches`
- `app.bank_flow_rule_batch_events`
- `read_model.bank_flow_rule_batch_rows`

当前规则持久化选择：

- 使用 `app_settings.bank_flow_rule_batch_tag_rules.requirements_by_tag_code`，通过 `/api/bank-flow-rule-batches/tag-rules` 暴露为 `rules`。
- 迁移 `0083_bank_flow_rule_batch_tag_rules.sql` 只在缺失新 key 时从 `app_settings.no_oa_bank_batch_tag_selection` 一次性复制历史值；迁移 `0111_bank_flow_rule_batch_tag_rules_canonical_shape.sql` 把复制来的 legacy selected 值合并到 requirements 后删除 selected 字段。运行时不再回退读取 no-OA settings family。
- 新 API 和服务边界拒绝 `selected_tag_codes` / `selectedTagCodes`；`rules` 中重复 `tag_code` fail fast。bank-flow public payload 不返回旧 selected 字段。legacy no-OA API 仍可读取旧字段用于历史兼容。
- 未配置 active tag 默认 `requires_oa=true`、`requires_invoice=true`。
- 规则设置不是关联台分区事实源。existing active relation 是不可追溯改写的历史事实；规则变化只影响未来候选/新批次，并只触发 `bank_flow_rule_batch` 刷新。

目标拆分仍可新增独立表 `app.bank_flow_rule_tag_requirements`，前提是保留版本、审计和乐观锁，并提供旧 settings family 的一次性迁移。

当前 read model：

- Read model：`bank_flow_rule_batch`
- Projection：`scoped_incremental`
- `all` 语义：`fan_out_command`
- Scope：month scope。
- Worker：`bank-flow-rule-batch`
- Event：`bank_flow_rule_batch.read_model.refresh`
- Query owner：`BankFlowRuleBatchApplicationService`
- Repository owner：`BankFlowRuleBatchReadModelRepositoryPort`
- Operation barrier：`bank_flow_rule_batch` 自身目标直接读取 `bank_flow_rule_batch` readiness/outbox/worker facts，不再映射到 `no_oa_bank_batch`；同一次 mutation 返回的 `workbench_relation` / `workbench` visibility targets 必须覆盖关联台 `month=all` 首屏和受影响月份，确保批量提交后关联台不会在 relation 已写入但 active generation 未刷新时显示真实空态。
- 新 relation 写入 `relation_mode=bank_flow_rule_batch`，批次 payload/read model row 也必须携带 `relation_mode=bank_flow_rule_batch`。列表 API 查询 submitted/unsubmitted/withdrawn 时必须通过 `list_bank_flow_rule_batch_rows` repository port 过滤，旧 no-OA payload 缺失该字段时只按 `no_oa_bank_batch` 处理。
- PostgreSQL 运行时批次存储和 read model 查询使用 `app.bank_flow_rule_batches`、`app.bank_flow_rule_batch_events`、`read_model.bank_flow_rule_batch_rows`；迁移 `0082_bank_flow_rule_batch_storage.sql` 从历史 no-OA 物理表按 `relation_mode=bank_flow_rule_batch` 回填，但运行时不再把 no-OA 表作为 bank-flow source of truth。no-OA legacy 仍使用 `app.no_oa_bank_batches`、`app.no_oa_bank_batch_events`、`read_model.no_oa_bank_batch_rows`。
- 持久化 I/O 使用 `save_bank_flow_rule_batch_mutation(...)` / `PostgresWorkbenchRepository.save_bank_flow_rule_batch_items(...)` / `save_bank_flow_rule_batches_scope(...)` 命名入口；提交/撤回/reset 等在线 mutation 只允许用 batch delta writer 同步 upsert 变更 batch rows 和对应事件，`changed_batch_ids` 是显式输入，不能仅从仍存在的 relation 反推，否则历史 relation 缺失会漏写 withdrawn 状态。禁止按月份 scope replace 重写未变更 batch。`save_bank_flow_rule_batches_scope(...)` 只属于 worker/rebuild/scope refresh，不得重新接入提交热路径。没有变更 batch id 的全局规则变更或显式 rebuild 才允许 fallback `all`/scope batch snapshot。禁止同步读取或写入 Workbench read model snapshot，禁止通过 no-OA persistence port、no-OA 物理表、Workbench read model broad snapshot 或逐行 projection fallback 写入新模块。
- Read model refresh 从 active relation 或已提交批次 relation fact 回灌 submitted 批次时必须按调用方目标 relation mode 判定；`bank_flow_rule_batch` 刷新不能复用 no-OA event/scope/producer，也不能把 bank-flow 批次显示到 legacy no-OA 列表。
- 月份 scope 的 API freshness gate 与 worker refresh 必须使用同一份 scope source-version 合同：先通过 bank-detail scope summary 与 Workbench relation source-version port 计算 `read_model_scope_source_versions(month)`，再用于 stale 判断、unchanged skip 和 snapshot 发布。禁止用 provider 的 mutable `last_source_versions` 作为月份 scope 的期望版本，否则同一刷新完成后 API 可能因 `bank_detail_source_versions_mismatch` 持续返回 stale。
- 规则配置变化直接通过 `BankFlowRuleBatchReadModelRefreshProducer` enqueue 单一 `bank_flow_rule_batch/all`，不得调用 `bank_flow_rule_batch_changed` broad lifecycle。在线 submit/withdraw/reset 仍由 relation command repository 在同一写入边界内产生 downstream dirty/outbox fan-out。
- 服务内由 submitted batch 反推 relation fact 时，必须继承该 batch 的 `relation_mode`、`source=bank_flow_rule_batch` 和 bank-flow display tags，并且只为当前 refresh `relation_mode` 生成 fact；禁止再把所有 submitted batch 硬编码为 `no_oa_bank_batch`。旧 no-OA legacy migration/repair 只允许处理 no-OA/明确 legacy relation，不得处理 `bank_flow_rule_batch`。
- 关联台按 active formal relation 判定 paired/unpaired，不读取 policy metadata 重新分类。

## 性能与刷新 I/O

- 列表 API 优先读取 `BankFlowRuleBatchReadModelRepositoryPort.list_bank_flow_rule_batch_rows(...)`；read model missing/stale 时返回非 fresh 状态并 enqueue `bank_flow_rule_batch` refresh，不能伪装空态。
- Worker 持久化写入必须保持 scoped incremental I/O；同一 scope 的多个 batch rows 应在 repository 边界批量 upsert，避免逐 batch round-trip 放大 worker handler 时间。
- `detail_payload(batch_id)`、`submit_batch(batch_id)` 和 `withdraw_batch(batch_id)` 先读取当前 bank-flow batch runtime；runtime 缺失时，detail 只能先按 `batch_id` 从 `bank_flow_rule_batch` read model 单行补齐当前 runtime，再尝试持久化批次快照；持久化快照只有包含目标 batch 时才允许替换 runtime。只有这些目标 batch hydrate 都失败时才 fallback `scope_key=all` 重建 runtime snapshot。已知 batch id 的提交和详情热路径不得为了单批操作前置全量候选 refresh。
- `submit-selection` 热路径必须先按选中 `transaction_ids` 读取银行流水和分类，再按选中行月份读取 relation/source-version 边界；普通费用、手续费等非内部往来选择不得前置 `scope_key=all` 全量候选 refresh。若选中行包含 `internal_transfer`，必须 fail fast 并要求使用单批内部往来提交入口，禁止回退全量批次构建或旧 no-OA selection 校验路径。
- `submit_batch(batch_id)` mutation 保存不得同步 `WorkbenchReadModelService.snapshot()` 或 `save_workbench_read_models(...)`；Workbench visibility 通过 dirty scope/outbox/worker 收敛。单批提交必须调用 batch delta writer，只 upsert 当前 batch 和当前 batch 事件；不得重写全部 bank-flow batch rows，也不得用 month scope replace 重写同月未变更批次。
- `submit_batch(batch_id)` 热路径不得为了 relation command、rollback 或响应组装读取完整 Workbench relation snapshot；`WorkbenchRelationCommandService.confirm_relation(...)` 必须通过 `load_workbench_pair_relations_for_row_ids(row_ids, case_ids=[case_id])` 读取 row/case scoped snapshot。bank-flow service 只能保存当前 bank-flow batch runtime snapshot，并通过 `snapshot_case_ids([case_id])` 读取变更 case 的 relation payload 和相关 history。`after_mutation(...)` 只允许把 month scope 规范化为 `["all", YYYY-MM...]` 后交给 bank-flow mutation persistence；submit/withdraw/reset 不得调用 `bank_flow_rule_batch_changed` 派生生命周期、不得调用 Workbench read model scope 枚举或把 `workbench/all` 聚合刷新重新放回当前页阻塞等待。
- `workbench-relations` owner 在保存 relation facts 后仍负责输出下游 dirty scope/outbox，但该事务内 fan-out 必须先计算 refresh intents，再一次性批量写 `job.read_model_dirty_scopes` 和 `job.outbox_events`。禁止恢复旧的 per-scope `fetch_one + execute` 入队函数；新增下游 scope 必须扩展批量 intent 合同和测试，而不是在 bank-flow service 内补同步刷新。
- `reset-submitted` 不做前置 `all` refresh；撤回后只同步刷新受影响月份 scope，没有月份时才 fallback `all`。
- 页面提交的前端阻塞等待到 command 成功为止：单批内部往来提交随后立即本地移除已提交批次，选中流水提交随后清空选择和当前展开批次；提交成功后的下一笔不得被自动选中或自动触发 detail GET，下一笔明细 I/O 只能来自用户显式选择或后续正常列表加载。`bank_flow_rule_batch` freshness wait / reload 在后台 reconcile。撤回、reset 至少只能等待 `bank_flow_rule_batch` 自身 target。`workbench_relation` / `workbench` targets 保留在 mutation result 和事件广播中，由关联台或后台 runtime 收敛；不能让 `workbench/all` 聚合刷新拖慢当前页提交完成反馈。
- Worker refresh 使用 `bank_flow_rule_batch_source_versions_summary(...)` 判断 scope source versions 是否 unchanged；该 summary 必须在数据库内聚合 row count、distinct source versions 和示例 source_versions，不能把 scope 下全部 read-model rows 的 JSON 拉回 Python。能证明 unchanged 时完成 dirty scope 并跳过批次重建和 snapshot 发布。
- 列表 presentation 在单次请求内只允许读取一次银行标签字典，并把同一份 definition index 用于当前页标签和完整 summary categories；禁止按 batch/category 重复 deep-copy 整份字典。列表 freshness 只读取本模块 repository 返回的 durable dirty/readiness/source-consistency proof，不得在每次 GET 时跨读 bank-detail/workbench-relation dependency facts；canonical writers 的事务内 dirty/outbox 是防旧数据边界。fresh 月份 scope 若同时存在多个 `source_versions` 必须返回 `schema_mismatch` 并入队修复，不能伪装 fresh。worker/refresh precheck 对 canonical category snapshot hash 的读取使用 `BankTransactionCategoryService.snapshot_version()`；该值与完整 snapshot SHA-256 合同完全一致，只在分类或标签字典真实变更时失效，不能引入 TTL、跨进程业务缓存或绕过 durable readiness。
- Worker 无法 skip、必须 rebuild 时，发布到 `read_model.bank_flow_rule_batch_rows.source_versions` 的版本仍必须复用该 scope precheck source_versions；后续读取分类或 relation 明细只能影响行内容，不能把 `last_source_versions` 形态写成另一个版本。
- PostgreSQL hot path index 位于 `0089_read_model_performance_hot_paths.sql`；新增 source-version 判断字段时必须同步维护该查询和索引，不得用 no-OA summary 或全量 Workbench snapshot 兜底。
- `tag-rules` 保存仍触发 `all` refresh，因为规则变更可能影响所有 active bank-flow relation requirement metadata；后续若要优化必须先有按 relation/tag 反查受影响 scope 的可靠索引。

Workbench relation facts 仍归 `workbench-relations`：

- 新模块只能通过 `WorkbenchRelationCommandService` 写入/撤销 `relation_mode=bank_flow_rule_batch`。
- 不能直接 SQL 写 `app.workbench_pair_relations` 或 read model。

## 文件范围

| 层 | 计划文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/BankFlowRuleBatchPage.tsx` via `/bank-flow-rule-batches`；只负责页面级状态编排、请求生命周期和模块组合 |
| Frontend feature | `web/src/features/bankFlowRuleBatches/api.ts`、`types.ts`、`policy.ts`、`viewModel.ts`、`components.tsx` via `/api/bank-flow-rule-batches` |
| Frontend tests | `web/src/test/BankFlowRuleBatch*.test.*`、`web/e2e/bank-flow-rule-batches-flow.spec.ts` |
| Backend route | `backend/src/fin_ops_platform/app/routes_bank_flow_rule_batches.py` |
| Backend service | `bank_flow_rule_batch_application_service.py`；共享批次计算内核在中性 `bank_batch_application_service.py` / `bank_batch_service.py` |
| Repository/read model | `bank_flow_rule_batch_read_model_repository.py`、`bank_flow_rule_batch_read_model_refresh.py`、`bank_flow_rule_batch_read_model_refresh_producer.py`、`bank_flow_rule_batch_derived_lifecycle_executor.py`、`postgres_repositories/workbench.py`、`postgres_repositories/read_models.py`、`postgres_state_store.py`；refresh/mutation 保存走 `save_bank_flow_rule_batch*` 命名 IO |
| PostgreSQL migration | `0082_bank_flow_rule_batch_storage.sql`、`0083_bank_flow_rule_batch_tag_rules.sql` |
| Runtime registry | `read_model_manifest.py`、`runtime_worker_registry.py`、`app_status_domain_registry.py`、`app_status_read_model_registry.py` |
| Integration | `workbench_candidate_grouping.py`、Workbench display policy/decorator、relation command metadata mapping |
| Tests | `tests/test_bank_flow_rule_batch*.py`、`tests/test_workbench_candidate_grouping.py`、affected no-OA regression tests |

## 依赖方向

- 允许依赖：bank detail tag read facade、bank transaction identity/query port、Workbench relation command/read boundary、runtime queue/read model gateway、audit/permission service。
- 必须通过：`BankFlowRuleBatchApplicationService` 作为页面/API 编排入口；`WorkbenchRelationCommandService` 作为 relation 写入口。
- `BankFlowRuleBatchApplicationService` mutation 入口只接受 `relation_mode=bank_flow_rule_batch`；非 bank-flow relation mode 必须 fail fast，不能委托共享 core 或 no-OA 旧 application path。
- 禁止绕过：直接写银行分类表、直接写 relation 表、直接操作 read model 表、直接复用旧 no-OA `selected_tag_codes` 作为规则事实、将 bank-flow Workbench 摘要或错误输出继续命名为 no-OA。

## 测试与验证

实现 slice 必须新增或更新：

- Business unit tests：规则默认值、semantic no-op、标签增减、提交校验、formal relation paired/unpaired gate。
- Service tests：规则保存单一 enqueue、existing relation 非改写、批次提交、relation command payload、dirty scope、旧历史重算页面链路不可达。
- API contract tests：规则 GET/PUT、列表、submit-selection、reset、权限和版本冲突。
- Read model/worker tests：`bank_flow_rule_batch` freshness、scope、source version。
- Frontend interaction tests：xlsx/grid 抽屉、checkbox、只读左侧标签、保存错误、分页/选择/提交。
- Playwright E2E：详见 `e2e-spec.md`。
- Existing regression：no-OA、Workbench formal relation grouping、bank details tag rules、pending invoices、turnover、search affected paths。

## 当前缺口和删除条件

- 代码已实现 bank-flow route/service/worker/event/barrier/producer/repository/persistence IO、PostgreSQL 物理批次/read model 表和 tag-rule settings family 独立。
- 本轮关闭旧残留：`workbench_candidate_grouping.py` 的 bank-flow 折叠摘要输出改为 `bank_flow_rule_batch_summary`；`postgres_repositories/read_models.py` 将 `bank_flow_rule_batch_summary` 纳入 summary display-only source kind；`web/src/features/workbench/api.ts` 和 `ReconciliationWorkbenchPage.tsx` 使用 bank-flow source kind/relation metadata 和“流水规则批次”文案；`routes_bank_flow_rule_batches.py` 把共享 core legacy no-OA 错误码翻译成 bank-flow HTTP 错误码。
- 旧 no-OA 模块仍承载自身历史事实和 legacy no-OA read model，当前不能删除其 route/service/tests；但 bank-flow HTTP、application service、read model event、worker、operation barrier、producer、mutation persistence 和 refresh persistence 不得再进入 no-OA route/service/event/scope/worker/persistence port。
- 历史 submitted no-OA 全量撤回不再属于本页面/API 合同；若未来需要数据迁移，必须作为独立运维工具重新建模，不得重新挂回 `/api/bank-flow-rule-batches` 或页面 UI。
- 旧 `selected_tag_codes` 写路径、no-OA 页面主入口、no-OA internal transfer 特例和 no-OA read model 常驻 worker 只能服务 no-OA legacy 域，要么删除，要么有明确 retained tooling 边界和退休条件；它们不得作为 bank-flow fallback 或输出 I/O。

## Canonical facts ownership

- Owned facts: `app.bank_flow_rule_batches`、`app.bank_flow_rule_batch_events`、`read_model.bank_flow_rule_batch_rows`、`app_settings.bank_flow_rule_batch_tag_rules`。
- Shared facts: 银行标签和分类由 `bank-details` owner 管理；relation facts 由 `workbench-relations` owner 管理；WorkBench active generation 由 `reconciliation-workbench` 管理。
- Allowed writes: `BankFlowRuleBatchApplicationService`、明确 UoW。
- Allowed reads: bank flow rule batch query/read ports、规则 read service、read model boundary。
- Downstream outputs: `bank_flow_rule_batch`、`workbench_relation`、`workbench`、`bank_detail`、`turnover_ledger`、`search` dirty scopes 或 owner producer 输出。
- Forbidden paths: shared state-store broad snapshot、旧 no-OA selected code 兼容写入、调用方直接改 batch/relation 状态。

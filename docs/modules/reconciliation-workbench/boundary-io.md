# 关联台模块边界与 I/O

日期：2026-07-06

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：页面查询走 `workbench` read model active generation；首屏 summary 只读物化 `read_model.workbench_summary`，groups summary 页只输出 UI 必需字段；写操作通过 workbench action/relation service 进入关系事实源和 dirty scope。
- 当前闭环：前端 `fetchWorkbench` / `fetchWorkbenchWithProgress` full-payload 客户端已删除，运行时页面只能走 `fetchWorkbenchInitialPage` + summary/groups API；旧 `/workbench`、`/workbench/prototype` 和 `/workbench/actions/*` HTTP 入口已删除；legacy `WorkbenchApiRoutes` 已降为只读兼容壳，仅保留 `get_workbench` / `get_row_detail`，不再拥有 action I/O。后端 `GET /api/workbench` full payload 是受限 read-only API contract：生产 SQL runtime 必须通过 `WorkbenchLegacyApiSqlReadProvider` 读取 active generation，repository/provider 缺失时 fail closed；非生产/local 才允许 `_build_api_workbench_payload(...)` 兼容构造。confirm-link context expansion 仍在 `Application` adapter 内，但输出合同已收紧为 canonical Workbench row id，禁止把上游 source id 注入 action row_ids；withdraw-link action boundary 会用已选 canonical OA row 的 source aliases 生成显式 `row_id_aliases`，并传入 relation command/pair service 的 preview 与 submit 恢复判断。历史 relation fact 中残留的 OA source id 必须在 preview、submit response、restored relations、scope fallback 和刷新目标前统一收敛为 canonical Workbench row id；canonical 后与当前 active relation 同 row-set 的历史快照不得恢复，也不得在撤回预览“操作后”合成同一行。OA 自带附件发票绑定不是历史快照恢复，而是 relation command/repair/grouping 必须维护的 source binding 不变量：row index 和 raw payload repair 必须用 OA canonical row id 和 source aliases 识别附件发票父 OA；raw payload repair 发现可证明父 OA+附件发票且缺 active relation时必须创建 `CASE-OA-ATT-<oa_row_id>`；已有 relation 缺父 OA 或缺附件时必须补齐同一 case；完整关系撤回后 OA+自带附件发票仍保持同一 active relation，纯 OA+自带附件发票撤回必须返回不可提交。row detail legacy fallback 已在生产 SQL read model runtime 完全关闭，只保留非 SQL/legacy 模式兼容入口。`workbench-matching` worker 已走 PostgreSQL dirty scope 和 `WorkbenchMatchingRelationReadPort`，运行时本地 pair service 只作为 canonical relation command/read 支撑，不再作为页面或 read model fallback。
- 旧代码删除条件：已满足当前页面/runtime close；后续若要物理删除后端 `GET /api/workbench` full-payload contract，必须先迁移仍直接覆盖该 contract 的后端集成测试和外部调用方。

## 职责边界

### 负责

- 关联台页面展示、候选分组、异常处理、配对/撤回等用户交互入口。
- 读取 `workbench` active generation read model，展示 fresh/stale/refreshing 状态。
- 通过公开 action/relation 边界触发业务写操作和下游 dirty scope。
- 配对确认、取消关联、撤回关联、旧异常分类/标记、现金特殊、票款购买、个人垫付还款、忽略/取消忽略等写操作返回统一 write target envelope；关系写目标是 `workbench_relation`，不是普通 `workbench` active generation。

### 不负责

- 不直接维护银行、发票、OA、税金或外部往来款的源事实。
- 不直接写 read model 表或 durable queue。
- 不绕过 workbench relation 事实源直接修补下游页面数据。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面过滤、月份、分页、候选分组操作 | `web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/components/workbench/*` | 前端状态只进入 workbench API，不直接拼持久化查询 |
| 查询请求 | `backend/src/fin_ops_platform/app/routes_workbench.py`、历史 `server.py` 入口 | 必须返回 read model freshness/status |
| 首屏读取 | `fetchWorkbenchInitialPage(...)` -> `/api/workbench/summary` + `/api/workbench/groups` | summary 缺失时返回 refreshing/stale 并入队，不允许在请求线程从 `workbench_group_rows` 或 `app.invoices` 重算；groups `detail_level=summary` 不输出 search/debug/raw payload |
| Row detail / confirm row 解析 | `GET /api/workbench/rows/{row_id}`、`WorkbenchRowDetailApiRoutes`、`WorkbenchQueryFacade.row_detail(...)`、`Application._resolve_rows_from_cached_read_models(...)` | row id 输入必须先通过 workbench read model / row-detail 边界解析为标准 OA/流水/发票行。`month=all` 的 row detail 与 confirm-link preview/submit 行解析必须遵循 composed active month shards 语义：先按 `all` 查询 active row detail，miss 时由 `WorkbenchQueryFacade` 通过 read model repository 的 `row_id -> active month scope` 只读端口定位真实月度 shard 后重试；不得要求普通写路径提前生成 materialized all generation，也不得在前端、route 或 action service 里推断月份。SQL row detail 主事实源仍是同一 active generation 的 `read_model.workbench_rows.payload`；仅为兼容历史 active generation，`workbench_rows` miss 时可读取同一 active generation 的非空 `read_model.workbench_group_rows.payload/raw_payload` member 行，member payload 为空仍必须按缺失处理，不能合成 `{id,type}` 占位。cached resolver 必须同时索引 `paired/open.{oa,bank,invoice}` 平铺行和 `paired/open.groups[*].{oa_rows,bank_rows,invoice_rows}` 成员行，group 成员可覆盖同 id 平铺行。confirm-link preview/submit 的上下文扩展只允许补充 canonical Workbench row id；OA 附件发票的 `derived_from_oa_id`、`source_expense_item_id`、row id 前缀中的原始来源 id 只能作为 source metadata，不得进入 action row_ids。已选 OA 必须先从 read model 行 payload 提取 canonical row id、`detail_fields.Mongo文档ID`、`OA单号/流程请求ID` 等 source aliases，再用于判断附件发票是否已被已选 OA 覆盖。生产 SQL read model runtime 下禁止 live-first 或 legacy query service fallback；缓存/query facade 失败时 fail closed，不能合成 `{id,type}` 占位或把 `KeyError(row_id)` 原样透出。非 SQL legacy/read-only 兼容入口在无 month hint 时可先查 live row detail，命中后不得再读 cached read model 或 legacy route fallback。 |
| 写操作 | workbench action/relation services | 写后污染受影响 workbench/workbench_relation/downstream scopes；confirm/cancel/withdraw 的 action I/O 只接受和输出 canonical Workbench row id。撤回操作必须把已选 OA source alias 作为 `row_id_aliases` 显式传入 relation command 边界，历史 relation fact 中的 OA source alias 不能传入 relation groups、amount check、response 或 operation barrier targets；canonical 后与当前 active relation 同 row-set 的 after/restored relation 必须过滤为无关系 after state。OA 自带附件发票 binding 是唯一例外：它由 OA source row id/source aliases 证明，不由 history restore 标记证明，raw payload repair 必须通过 relation command 边界创建或补齐 active source binding，撤回完整关系后必须继续输出 OA+附件发票 after relation；纯 OA+附件发票撤回必须输出 `can_submit=false`。 |
| Bank Transaction Paired Policy metadata | `workbench_relation` / bank-flow-rule-batch submit、tag-rule sync、turnover/manual closure sync、legacy no-OA submit | 只有 policy-managed 银行 relation code（`no_oa_bank_batch`、`bank_flow_rule_batch`、`turnover_manual_closure`，以及工资、内部转账、个人垫付还款等银行自动闭合 code）可用银行流水 row 上的物化 policy metadata 决定是否进入 paired 区。`requires_oa=true` 必须存在 OA row；`requires_invoice=true` 必须存在发票 row；两者都为 false 时银行-only 或部分栏位 relation 可 paired；metadata 缺失或字段缺失默认等价于 `requires_oa=true, requires_invoice=true`，但 legacy no-OA 缺字段按 no-OA 历史合同等价于两者都 false。Workbench 不读取当前标签设置作为 fallback。普通 `manual_confirmed` 银行关系和 `batch_accounting` 关系不得被该 policy 的默认发票要求污染；它们分别按普通三栏完整性或批量账务 relation I/O 判定。bank-flow submit/withdraw/reset 不是 `WorkbenchWriteFacade` 入口，但其 API 返回的 operation barrier 必须包含 `workbench_relation` 与 `workbench` 的 `all` + 受影响 month scope，因为关联台首屏读取 `month=all` active generation。 |
| 外部往来闭环 relation metadata | `workbench_relation` / turnover manual closure and tag-rule sync | `relation_mode=turnover_manual_closure` 仍是外部往来闭环事实类型，但 paired/open 分区不再由 relation mode 直接决定；必须满足上面的 Bank Transaction Paired Policy。旧 `turnover:* manual_confirmed` 必须由规则 owner 通过 relation command 升级，Workbench 不回读当前标签设置。 |
| no-OA relation metadata | `workbench_relation` / no-OA submit | legacy `special_metadata.paired_requires_oa`、`paired_requires_invoice` 决定 no-OA relation 是否具备进入 paired 区的 row type |
| 写后 target envelope | `WorkbenchWriteFacade` | 返回 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets`；`read_model_key=workbench_relation` |
| 外部 OA 手工导入影响 | settings/OA manual import API | 不属于 `WorkbenchWriteFacade`，但必须返回并等待 `workbench`/`workbench_relation` 等受影响 read model targets |
| Refresh scope | `workbench` manifest | month or `all`；普通写路径只刷新受影响 month shard，`month=all` 查询组合 active 月度 generation；显式 rebuild/repair/backfill 才使用 materialized all aggregate |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 关联台页面 payload | 前端 workbench components | 来自 active generation read model |
| Summary payload | 前端首屏和 App 状态 | month scope 来自对应 active generation 的 `read_model.workbench_summary`；`month=all` 从 active 月度 summary 组合，缺少月度 summary 时标记 stale，不回退旧 materialized all summary 或请求线程热修复 |
| Groups summary page | 前端三栏列表 | 保留 rows、counts、display tags、核心 decision 字段；剔除 `searchable_text`、`source_versions`、`group_metadata`、`object_identity*`、decision evidence/debug 等非首屏 UI 字段 |
| Generation payload | read_model.workbench_* 新 generation | `workbench_rows.payload` 拥有行详情，但不保存 nested `object_identity` 仲裁对象；canonical identity 由 `workbench_rows` / `workbench_group_rows` 的结构化 `object_identity_*` 列和行 payload 顶层字段承载。`workbench_groups.payload` 只拥有组级 metadata/sort/count/`workbench_group_rows_materialized` marker，不再复制 `oa_rows/bank_rows/invoice_rows/collapsed_rows`；`workbench_group_rows` 只拥有成员关系、过滤、排序、搜索和 object identity 结构化列，`payload` / `raw_payload` / `source_versions` 写 `{}`；`workbench_snapshots.payload` 只保存 metadata/summary shell 和 `workbench_groups_materialized=true` marker。旧 `/api/workbench`、groups page/detail 和下游成本统计需要完整组 payload 时，必须从同一 active generation 的 `workbench_group_rows + workbench_rows` 重建；repository 遍历 rows/groups 时不得 eager serialize 整行/整组，序列化只允许在 JSON 写入 helper 的最终 I/O 边界发生；`raw_payload` 只保留旧数据 fallback 语义，新写入不得再复制 `normalized_payload`、整页 grouped payload、成员行数组、nested identity 或 group-row member payload/source_versions 放大持久化 I/O |
| paired/open 分区 | 前端 workbench components | policy-managed 银行 relation 先按 Bank Transaction Paired Policy 判定 required row type；缺少 required OA 或发票 row 必须留在 open 区，满足后才进入 paired。普通两栏 `manual_confirmed` 银行 relation 不消费该 policy，缺发票时按普通三栏完整性留在 open candidate。带 immutable binding metadata 的 OA+自带附件发票两栏 active relation不含银行流水时只是不可拆 source binding，也必须留在 open 区。 |
| batch-accounting paired 分区 | 前端 workbench components | active `relation_mode=batch_accounting` 且 `special_metadata.source=batch_accounting` 是批量账务模块的 confirmed relation I/O；行级 relation code 为 `batch_accounting` 时也必须作为 paired row 参与分组，不得落入 open `existing_case_candidate`，也不得被 Bank Transaction Paired Policy 的默认发票要求降级。 |
| 折叠批次展示 | `CandidateGroupGrid` | `collapsed_summary` 默认只展示摘要 row 和“展开 N 条/张明细”按钮；不得再渲染“当前显示 1 条摘要 / 实际 N 条流水”等绝对定位计数文案，避免与流水标签和日期重叠。 |
| 配对/撤回结果 | 调用方和页面刷新 | 返回业务结果并触发 dirty scope；confirm/cancel/withdraw 输入输出的 `row_ids`、`affected_row_ids`、operation barrier targets 均使用 canonical Workbench row id，撤回读取 active relation facts，不从 source metadata 反推任意行集合。撤回预览的 `before.groups` 和 `after.groups` 必须来自 relation command/pair service 的 alias-aware before/after relation 合同；没有被合法恢复的行按独立 selection row 展示，不能因为 row payload 残留 `case_id` 或历史 source alias 合成同一行。OA 自带附件发票必须作为父 OA 的绑定成员保留在 active relation 和 after relation 中，不能作为 standalone 发票行输出，也不能只作为 `oa_attachment_source_relation` display candidate 输出。确认关联可在 operation projection 有效时用于页面快速更新；撤回和 `split_candidate` 预览提交期间，页面输出只能来自 fresh Workbench read model，必须延迟应用 fresh payload 到关闭预览同一批状态更新，禁止把 submit response 的 operation projection 直接渲染到底层 Workbench。 |
| Operation barrier targets | 前端页面 | 写成功后等待 `workbench_relation` targets 以及可见性依赖的 `workbench` targets，再刷新 workbench/相关页面；跨模块写入若会影响关联台 `month=all`，必须把 `all` scope 纳入 targets，不能只等待业务页面自身 read model。 |
| Dirty scope/outbox | runtime queue | 通过 gateway 或等价事务合同进入 durable queue |
| 下游影响 | workbench relation、tax offset、pending invoice、bank-flow-rule-batches、no-OA、turnover 等 | 由关系事实源和 lifecycle/worker 扇出 |

## 持久化与投影

- Read model：`workbench`
- Projection：`active_generation_scoped_publish`
- Partition：month scope active generation；`month=all` 查询组合 active month shards，不再要求 ordinary write 后生成 materialized all generation。composed all 的 groups/rows/row detail 必须只读取 active 月度 generation；groups/open 必须在分页前复用 all-scope visible owner 仲裁，优先保留 paired、source-linked、跨 pane automatic decision 等证据更强的 owner；可合并 group id（如 `case:`）按业务 case 合并，非可合并临时 group id 必须带 source scope 前缀，避免跨月覆盖。
- materialized `all` aggregate 只作为显式 rebuild/repair/backfill 兼容路径保留，不参与普通写后可见性、summary/groups freshness gate 或 operation barrier。旧 materialized all 缺失、为空或 builder 版本落后，不能污染 query-composed all 读路径。
- Worker：`workbench`
- 特殊例外：保留 active generation 原子发布模型，不机械改成普通 read model gateway。
- Summary 物化合同：`read_model.workbench_summary` 是 summary 读路径唯一事实源；repository 不再用 groups/group_rows/app.invoices 在 API 请求内补算 summary。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/ReconciliationWorkbenchPage.tsx` |
| Frontend components | `web/src/components/workbench/*` |
| Frontend API/tests | `web/src/features/workbench/*`、`web/src/test/Workbench*.test.*`、`web/e2e/workbench-*.spec.ts` |
| Backend route | `backend/src/fin_ops_platform/app/routes_workbench.py`、`backend/src/fin_ops_platform/app/routes_workbench_actions.py` |
| Backend service | `backend/src/fin_ops_platform/services/workbench_*`、`backend/src/fin_ops_platform/services/live_workbench_service.py`、`backend/src/fin_ops_platform/services/matching.py` |
| Repository / SQL | `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`、`backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py`、`backend/src/fin_ops_platform/services/workbench_sql_projection.py` |
| Worker/read model | `backend/src/fin_ops_platform/services/workbench_read_model_service.py`、`backend/src/fin_ops_platform/services/runtime_worker_registry.py` |
| Tests | `tests/test_workbench_*.py`、`tests/test_live_workbench_service.py`、`tests/test_workbench_sql_runtime.py` |

## 依赖方向

- 允许依赖：workbench relation read facade、read model repository、runtime queue、audit/idempotency service。
- 必须通过：route owner、service/facade、repository port、manifest scope contract。
- 禁止绕过：直接 SQL 写 read model、直接操作 dirty scope 表、在前端假设 stale 数据为 fresh。

## 测试与验证

- Read model/cache/worker：`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_dirty_queue_wiring.py`。
- Service/API：`tests/test_workbench_api.py`、`tests/test_workbench_v2_api.py`、`tests/test_workbench_query_facade.py`。
- Withdraw preview alias regression：`tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_preview_filters_same_canonical_alias_after_relation`、`tests/test_workbench_pair_relation_service.py::WorkbenchPairRelationServiceTests::test_withdraw_ignores_restorable_snapshot_with_same_canonical_alias_row_set`。
- OA attachment immutable withdraw regression：`tests/test_workbench_pair_relation_service.py::WorkbenchPairRelationServiceTests::test_withdraw_preserves_oa_attachment_binding_without_history`、`tests/test_workbench_pair_relation_service.py::WorkbenchPairRelationServiceTests::test_withdraw_rejects_plain_oa_attachment_binding_relation`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_withdraw_link_without_history_preserves_oa_attachment_invoice_binding`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_withdraw_link_blocks_plain_oa_attachment_invoice_binding`、`web/src/test/WorkbenchSelection.test.tsx::paired zone withdraw preview blocks immutable OA attachment invoice binding`。
- Frontend/e2e：`web/src/test/Workbench*.test.*`、`web/e2e/workbench-*.spec.ts`。
- `WorkbenchV2ApiTests.test_api_workbench_actions_return_unified_result_structure` 覆盖 confirm/cancel/update-bank-exception/mark-exception/cash-special/cash-ticket 的 target envelope；其他异常与 ignore/unignore 路径由相邻 WorkbenchV2ApiTests 覆盖。
- OA manual import/create/refresh/remove 由 `tests/test_oa_manual_import_api.py`、`web/src/test/WorkbenchApi.test.ts`、`web/src/test/SettingsOaManualSearchImportTable.test.tsx` 覆盖写后 target envelope 和 operation barrier 等待。

## 当前缺口和删除条件

- 对 legacy workbench API 的任何修改都必须同时写清是否仍有调用方。
- `fetchWorkbenchInitialPage` 是当前首屏和导入后 fallback 刷新入口；前端 full-payload `fetchWorkbench` / `fetchWorkbenchWithProgress` 已删除，`/api/workbench` full payload 仅允许作为后端兼容迁移面存在，不能重新进入页面 runtime 主链路。
- `GET /api/workbench` 在生产 SQL read model runtime 下必须通过 `WorkbenchLegacyApiSqlReadProvider` 读取 SQL active generation；repository/provider 缺失时返回 `read_model_unavailable`，不得回退 `_build_api_workbench_payload(...)` raw builder。
- `GET /api/workbench/rows/{row_id}` 在生产 SQL read model runtime 下不得回退到 `WorkbenchApiRoutes.get_row_detail(...)` 或旧 query service 内存记录；命中 live/cache/query facade 失败时必须 fail closed。
- `workbench-matching` 只能通过 `job.workbench_matching_dirty_scopes` claim/complete/fail 和 `WorkbenchMatchingRelationReadPort` 读取 canonical active relations；不得直接依赖页面 full payload、legacy dirty scope snapshot 或 read model distribution 作为 matching 事实源。
- 删除后端 `GET /api/workbench` full-payload contract 前必须证明 route、backend tests、生产脚本和外部调用方都不再依赖。
- Workbench exception action 已归入现代 `/api/workbench/actions/*`/`/api/workbench/exception/*` 写边界；不得回退到旧 `/workbench/actions/*` 或丢弃 `_apply_exception_payload` 计算出的 affected scopes。

## Canonical facts ownership

- Owned facts: `app.workbench_row_overrides`、`app.workbench_exception_cases`、`app.workbench_exception_case_events`、`app.matching_runs`、`app.matching_results`、`app.workbench_idempotency_records`。
- Shared facts: relation facts 由 `workbench-relations` owner 管理；Workbench 只能通过 relation command/read boundary 写读关系。
- Allowed writes: workbench route owner、workbench command/facade services、matching worker、idempotency service。
- Allowed reads: workbench query/facade ports、active generation/read model boundary。
- Downstream outputs: workbench active generation、workbench_relation、search/cost/tax dirty scopes 或 owner producer 输出。
- Forbidden paths: legacy workbench handler 不得直接写 relation facts、read model 或 dirty/outbox；building/failed projection 不得被当作页面事实。
- Old code deletion: frontend legacy full-payload client 已删除；legacy `WorkbenchActionService` 已删除，legacy `WorkbenchApiRoutes` 只保留 read-only `get_workbench` / `get_row_detail` 兼容壳，不得承载 `confirm_link`、`mark_exception`、`cancel_link` 或 `update_bank_exception` 写状态机；旧 `/workbench`、`/workbench/prototype` 和 `/workbench/actions/confirm|difference|exception|offline|offset` HTTP compat route owner 已删除，ledger/reminder 行为保留在 reconciliation/ledger service 和 `/ledgers`/`/reminders` API；后端 `GET /api/workbench` full payload 是受限 read-only compat API，不进入前端页面 runtime，不拥有写 I/O，不作为旧代码污染面。

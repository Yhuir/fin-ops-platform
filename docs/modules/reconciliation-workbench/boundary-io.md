# 关联台模块边界与 I/O

日期：2026-07-04

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：页面查询走 `workbench` read model active generation；首屏 summary 只读物化 `read_model.workbench_summary`，groups summary 页只输出 UI 必需字段；写操作通过 workbench action/relation service 进入关系事实源和 dirty scope。
- 当前缺口：`server.py` 与历史 workbench service 仍保留部分入口，`GET /api/workbench` full payload 仍是兼容迁移面；confirm-link context expansion 仍在 `Application` adapter 内，但输出合同已收紧为 canonical Workbench row id，禁止把上游 source id 注入 action row_ids；withdraw-link action boundary 会用已选 canonical OA row 的 source aliases 识别历史 active relation 中残留的 OA source id，并在 preview、submit response、restored relations、scope fallback 和刷新目标前统一收敛为 canonical Workbench row id；row detail legacy fallback 已在生产 SQL read model runtime 完全关闭，只保留非 SQL/legacy 模式兼容入口。`workbench-matching` worker 已走 PostgreSQL dirty scope 和 `WorkbenchMatchingRelationReadPort`，运行时本地 pair service 只作为 canonical relation command/read 支撑，不再作为页面或 read model fallback。
- 旧代码删除条件：没有 API、前端、worker、测试继续读取 legacy live/pickle 路径，并且 active generation freshness 与回归测试覆盖写后刷新。

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
| Row detail / confirm row 解析 | `GET /api/workbench/rows/{row_id}`、`WorkbenchRowDetailApiRoutes`、`Application._resolve_rows_from_cached_read_models(...)` | row id 输入必须先通过 workbench read model / row-detail 边界解析为标准 OA/流水/发票行。cached resolver 必须同时索引 `paired/open.{oa,bank,invoice}` 平铺行和 `paired/open.groups[*].{oa_rows,bank_rows,invoice_rows}` 成员行，group 成员可覆盖同 id 平铺行。confirm-link preview/submit 的上下文扩展只允许补充 canonical Workbench row id；OA 附件发票的 `derived_from_oa_id`、`source_expense_item_id`、row id 前缀中的原始来源 id 只能作为 source metadata，不得进入 action row_ids。已选 OA 必须先从 read model 行 payload 提取 canonical row id、`detail_fields.Mongo文档ID`、`OA单号/流程请求ID` 等 source aliases，再用于判断附件发票是否已被已选 OA 覆盖。生产 SQL read model runtime 下禁止 live-first 或 legacy query service fallback；缓存/query facade 失败时 fail closed，不能合成 `{id,type}` 占位或把 `KeyError(row_id)` 原样透出。 |
| 写操作 | workbench action/relation services | 写后污染受影响 workbench/workbench_relation/downstream scopes；confirm/cancel/withdraw 的 action I/O 只接受和输出 canonical Workbench row id，历史 relation fact 中的 OA source alias 必须在 action facade 边界被转换，不能传入 relation groups、amount check、response 或 operation barrier targets |
| 流水规则批量处理 relation metadata | `workbench_relation` / bank-flow-rule-batch submit and tag-rule sync | `special_metadata.requires_oa`、`requires_invoice` 决定 `relation_mode=bank_flow_rule_batch` 是否具备进入 paired 区的 row type；行级 relation display code 必须保留 `bank_flow_rule_batch`，不能被旧 `fully_linked` 人工关联语义覆盖；`source_row_count>3` 时默认折叠。Workbench 不读取当前标签设置作为 fallback；规则 owner 必须在保存设置后同步 active relation metadata。bank-flow submit/withdraw/reset 不是 `WorkbenchWriteFacade` 入口，但其 API 返回的 operation barrier 必须包含 `workbench_relation` 与 `workbench` 的 `all` + 受影响 month scope，因为关联台首屏读取 `month=all` active generation。 |
| 外部往来闭环 relation metadata | `workbench_relation` / turnover manual closure and tag-rule sync | `relation_mode=turnover_manual_closure` 且 metadata 显式声明 `requires_oa` / `requires_invoice` 时，按 required row type 判定 open/paired；metadata 缺失的旧关系 fail closed。旧 `turnover:* manual_confirmed` 必须由规则 owner 通过 relation command 升级，Workbench 不回读当前标签设置。 |
| no-OA relation metadata | `workbench_relation` / no-OA submit | legacy `special_metadata.paired_requires_oa`、`paired_requires_invoice` 决定 no-OA relation 是否具备进入 paired 区的 row type |
| 写后 target envelope | `WorkbenchWriteFacade` | 返回 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets`；`read_model_key=workbench_relation` |
| 外部 OA 手工导入影响 | settings/OA manual import API | 不属于 `WorkbenchWriteFacade`，但必须返回并等待 `workbench`/`workbench_relation` 等受影响 read model targets |
| Refresh scope | `workbench` manifest | month or `all`；`all` 是 active month shard aggregate |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 关联台页面 payload | 前端 workbench components | 来自 active generation read model |
| Summary payload | 前端首屏和 App 状态 | 来自 `read_model.workbench_summary` 物化结果；缺少 `summary` 视为 read model 未完成，不做热路径 repair |
| Groups summary page | 前端三栏列表 | 保留 rows、counts、display tags、核心 decision 字段；剔除 `searchable_text`、`source_versions`、`group_metadata`、`object_identity*`、decision evidence/debug 等非首屏 UI 字段 |
| Generation payload | read_model.workbench_* 新 generation | `workbench_rows.payload` 拥有行详情，但不保存 nested `object_identity` 仲裁对象；canonical identity 由 `workbench_rows` / `workbench_group_rows` 的结构化 `object_identity_*` 列和行 payload 顶层字段承载。`workbench_groups.payload` 只拥有组级 metadata/sort/count/`workbench_group_rows_materialized` marker，不再复制 `oa_rows/bank_rows/invoice_rows/collapsed_rows`；`workbench_group_rows` 只拥有成员关系、过滤、排序、搜索和 object identity 结构化列，`payload` / `raw_payload` / `source_versions` 写 `{}`；`workbench_snapshots.payload` 只保存 metadata/summary shell 和 `workbench_groups_materialized=true` marker。旧 `/api/workbench`、groups page/detail 和下游成本统计需要完整组 payload 时，必须从同一 active generation 的 `workbench_group_rows + workbench_rows` 重建；repository 遍历 rows/groups 时不得 eager serialize 整行/整组，序列化只允许在 JSON 写入 helper 的最终 I/O 边界发生；`raw_payload` 只保留旧数据 fallback 语义，新写入不得再复制 `normalized_payload`、整页 grouped payload、成员行数组、nested identity 或 group-row member payload/source_versions 放大持久化 I/O |
| paired/open 分区 | 前端 workbench components | 已确认 `bank_flow_rule_batch`、`turnover_manual_closure` 或 legacy no-OA relation 若缺少 metadata 声明要求的 OA 或发票 row，必须留在 open 区；不要求 OA/发票的 `bank_flow_rule_batch` 银行组应直接进入 paired 区。补齐 required row type 后才进入 paired 区。 |
| batch-accounting paired 分区 | 前端 workbench components | active `relation_mode=batch_accounting` 且 `special_metadata.source=batch_accounting` 是批量账务模块的 confirmed relation I/O；行级 relation code 为 `batch_accounting` 时也必须作为 paired row 参与分组，不得落入 open `existing_case_candidate` |
| 折叠批次展示 | `CandidateGroupGrid` | `collapsed_summary` 默认只展示摘要 row 和“展开 N 条/张明细”按钮；不得再渲染“当前显示 1 条摘要 / 实际 N 条流水”等绝对定位计数文案，避免与流水标签和日期重叠。 |
| 配对/撤回结果 | 调用方和页面刷新 | 返回业务结果并触发 dirty scope；confirm/cancel/withdraw 输入输出的 `row_ids`、`affected_row_ids`、operation barrier targets 均使用 canonical Workbench row id，撤回读取 active relation facts，不从 source metadata 反推行集合。 |
| Operation barrier targets | 前端页面 | 写成功后等待 `workbench_relation` targets 以及可见性依赖的 `workbench` targets，再刷新 workbench/相关页面；跨模块写入若会影响关联台 `month=all`，必须把 `all` scope 纳入 targets，不能只等待业务页面自身 read model。 |
| Dirty scope/outbox | runtime queue | 通过 gateway 或等价事务合同进入 durable queue |
| 下游影响 | workbench relation、tax offset、pending invoice、bank-flow-rule-batches、no-OA、turnover 等 | 由关系事实源和 lifecycle/worker 扇出 |

## 持久化与投影

- Read model：`workbench`
- Projection：`active_generation_scoped_publish`
- Partition：month scope active generation；`all` 聚合 active month shards。`all` 聚合必须把可见 paired group 的 row ownership
  作为 strict claim；同一个 `case:<case_id>` 在部分月份为 paired、部分月份仍残留 open candidate 时，paired 可见 owner
  必须赢，open 重复行不得发布。只有“没有可见 paired group、仅 canonical active relation 额外 claim”的 same-case open group
  才允许保留为 partial/open 展示。
- `all` 聚合输入 shard 的事实源必须包含 canonical 业务源月份和已发布的 active 月度 generation；query freshness/status 必须校验 active 父 generation 与 `all` active generation 的 source_version/row/group 基本一致性。父 generation 有内容而 `all` 缺失或为空时，`summary`/`groups` 必须返回 stale 并入队刷新，不能把空结果标记为 fresh。
- Worker：`workbench`
- 特殊例外：保留 active generation 原子发布模型，不机械改成普通 read model gateway。
- Summary 物化合同：`read_model.workbench_summary` 是 summary 读路径唯一事实源；repository 不再用 groups/group_rows/app.invoices 在 API 请求内补算 summary。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/ReconciliationWorkbenchPage.tsx` |
| Frontend components | `web/src/components/workbench/*` |
| Frontend API/tests | `web/src/features/workbench/*`、`web/src/test/Workbench*.test.*`、`web/e2e/workbench-*.spec.ts` |
| Backend route | `backend/src/fin_ops_platform/app/routes_workbench.py`、`backend/src/fin_ops_platform/app/routes_workbench_actions.py`、`backend/src/fin_ops_platform/app/routes_legacy_workbench_actions.py` |
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
- Frontend/e2e：`web/src/test/Workbench*.test.*`、`web/e2e/workbench-*.spec.ts`。
- `WorkbenchV2ApiTests.test_api_workbench_actions_return_unified_result_structure` 覆盖 confirm/cancel/update-bank-exception/mark-exception/cash-special/cash-ticket 的 target envelope；其他异常与 ignore/unignore 路径由相邻 WorkbenchV2ApiTests 覆盖。
- OA manual import/create/refresh/remove 由 `tests/test_oa_manual_import_api.py`、`web/src/test/WorkbenchApi.test.ts`、`web/src/test/SettingsOaManualSearchImportTable.test.tsx` 覆盖写后 target envelope 和 operation barrier 等待。

## 当前缺口和删除条件

- 对 legacy workbench API 的任何修改都必须同时写清是否仍有调用方。
- `fetchWorkbenchInitialPage` 是当前首屏和导入后 fallback 刷新入口；`fetchWorkbenchWithProgress` / `/api/workbench` full payload 只允许作为兼容迁移面存在，不能重新进入页面 runtime 主链路。
- `GET /api/workbench` 在生产 SQL read model runtime 下必须通过 `WorkbenchLegacyApiSqlReadProvider` 读取 SQL active generation；repository/provider 缺失时返回 `read_model_unavailable`，不得回退 `_build_api_workbench_payload(...)` raw builder。
- `GET /api/workbench/rows/{row_id}` 在生产 SQL read model runtime 下不得回退到 `WorkbenchApiRoutes.get_row_detail(...)` 或旧 query service 内存记录；命中 live/cache/query facade 失败时必须 fail closed。
- `workbench-matching` 只能通过 `job.workbench_matching_dirty_scopes` claim/complete/fail 和 `WorkbenchMatchingRelationReadPort` 读取 canonical active relations；不得直接依赖页面 full payload、legacy dirty scope snapshot 或 read model distribution 作为 matching 事实源。
- 删除旧路径前必须证明 route、frontend、worker、tests、生产脚本都不再依赖。
- legacy exception action 不得再丢弃 `_apply_exception_payload` 计算出的 affected scopes；删除旧异常入口前必须保留 target envelope 回归。

## Canonical facts ownership

- Owned facts: `app.workbench_row_overrides`、`app.workbench_exception_cases`、`app.workbench_exception_case_events`、`app.matching_runs`、`app.matching_results`、`app.workbench_idempotency_records`。
- Shared facts: relation facts 由 `workbench-relations` owner 管理；Workbench 只能通过 relation command/read boundary 写读关系。
- Allowed writes: workbench route owner、workbench command/facade services、matching worker、idempotency service。
- Allowed reads: workbench query/facade ports、active generation/read model boundary。
- Downstream outputs: workbench active generation、workbench_relation、search/cost/tax dirty scopes 或 owner producer 输出。
- Forbidden paths: legacy workbench handler 不得直接写 relation facts、read model 或 dirty/outbox；building/failed projection 不得被当作页面事实。
- Old code deletion: legacy workbench API、legacy exception action 和同步 builder production fallback 必须删除或迁移到 route/service owner；保留 compat wrapper 不算 closure。

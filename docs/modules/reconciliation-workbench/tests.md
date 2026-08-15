# 关联台测试与验证

日期：2026-08-13

## 2026-08-13 Direct canonical API 与 page runtime 退役

- Repository/SQL：首屏在一个 `REPEATABLE READ READ ONLY` snapshot 中构造一次 scope-first typed group spine，同时得到 summary、inventory、paired/unpaired exact totals 与两区各 10 个 keys；只批量 hydration 可见页。普通 groups 使用 query-bound opaque keyset cursor，facet 一条有界 SQL，detail 只按 case 或 typed identity 窄查。搜索只覆盖展示字段并转义 literal wildcard；非法 scope/filter/sort/status/source/page size/cursor 返回 400。
- Typed identity：页面、preview 与 submit 都以有序 `(row_type,row_id)` 表达成员；同一文本 ID 跨 OA/银行/发票不得冲突或错绑。active relation member array 形状、typed 重复、missing canonical member、completed/pending OA 双源冲突都 fail closed。
- API/frontend：响应删除 page generation/freshness/version/job；`/api/workbench/refresh-status` 404。mount 使用 combined initial + 独立 OA sync status；区域 search/filter 只重读受影响 zone；异常抽屉 cursor 增量读取，展开才取详情。写成功恰好一次 normal canonical GET，refetch 失败不重试 mutation。
- Runtime：manifest/App Status/scope 只保留 `workbench_relation`；required worker 精确为 5 个。`workbench.read_model.refresh`、page worker/env、Redis page cache、generation rehydrate/prune/convergence current tooling 全部退役，matching 与 shared relation 保留。
- Performance：迁移前生产基线已分别记录 combined/groups/facet；发布后以相同参数复测。阻断合同为 HTTP error=0、专项 P95≤1000ms、P99≤2000ms；P50≤600ms/P95≤800ms/P99≤1200ms 是优化目标，不伪称百万级已证明。
- 下方 2026-08-12 及更早章节是当时验证记录。其中 generation/freshness/cache/worker 断言已由本节替代，不是当前合同。

## 2026-08-12 关系撤回事务安全闭环（专项已验证）

- Business core / service：显式 row ids 在 preview 与 submit 都必须与目标 case 当前完整 active typed member set 精确相等；子集、超集、显式空集合或 case/rows 不一致返回 `workbench_relation_exact_selection_required`，零写。case-only 仅保留给可信内部 owner 调用。
- Transaction / repository：同一 relation UoW 内先锁 current case 与持久化 members，再按稳定顺序锁 predecessor case/members；随后重载 current/restored scope，重验目标 topology、canonical member 存在与类型、restored case 未复用和唯一 active owner。缺 canonical 返回 `workbench_relation_canonical_member_missing`，case/owner 冲突返回 `workbench_relation_restore_conflict`，整笔 rollback。
- Version / stale preview：新关系 version=`1`；status 或 typed member set 变化单调 `+1`，cancel `+1`，restore predecessor 使用 `max(数据库当前 predecessor version, history snapshot version)+1`。withdraw preview fingerprint 覆盖 `operation_type`、current/after relation 的 case/version/status/排序 typed members，以及 confirm history 的 operation id/type/created at；任一拓扑或历史漂移都拒绝旧 preview。
- API / idempotency / audit：exact selection 映射 HTTP 400；canonical/restore drift 映射 HTTP 409。相同 idempotency key 重放不产生第二次 relation save；withdraw history `created_by` 取认证 actor。兼容 `POST /api/workbench/exception/apply` 忽略 payload `actor` / `confirmed_by`，只使用认证 session actor；自动异常/行级异常后端能力继续保留。
- Regression：`internal_transfer` 人工确认继续统一走标准 relation UoW，独立 no-OA API 保留；没有新增旧分流、fallback、read model、worker、queue 或 schema。
- 当前证据：本轮 direct/UoW/repository 专项共 `106 passed`，后端 lint 与 diff-check 已通过。该数字只证明本轮专项，不声明全后端、Browser、生产部署或真实 PostgreSQL 并发门禁已经在本轮重跑。

## 2026-08-12 人工 confirm-link 内部转账旧分流删除（已验证）

- Business core / service：分别覆盖全 `internal_transfer` 银行成员、`internal_transfer` 与其它银行分类混合、普通银行分类三种人工选择；三者都必须以 `manual_confirmed` 进入同一 `WorkbenchRelationCommandService` + relation UoW，并保留 canonical revalidation、active overlap、幂等、history 与 rollback，不得调用 no-OA batch callback。
- API contract：继续复用既有 preview/confirm request 与 response shape；mixed 选择不得再返回 `no_oa_bank_batch_selection_internal_transfer_conflict`，全 `internal_transfer` 选择不得返回 no-OA batch response。既有 `amount_check.requires_note=true` 时的 `note` 门禁、权限、版本与错误 envelope 不变。
- Boundary / regression：静态边界 guard 保护 `submit_internal_transfer_rows_from_workbench`、`_bank_only_internal_transfer_confirm_status` 和 `_confirm_internal_transfer_rows_via_no_oa_batch` 不再进入 facade 组装或人工确认调用图；独立 no-OA batch API/service、其关系 mode 和既有批次测试必须继续通过。
- E2E 非适用：该删除不改变前端选择、HTTP shape、页面分区或用户操作序列，不新增仅用于观察内部 dispatch 的 Browser case；内部路由由 474 项关系专项矩阵与 4259 项全后端回归中的 service/API、真实 UoW 幂等及边界 guard 证明。

## 2026-08-12 人工关系准入、未配对撤回与旧异常入口删除

- Business core：人工 confirm 对 normalize 后 requested selection 断言至少 2 个不同 canonical IDs，逐个精确解析为 `oa|bank|invoice`；覆盖 OA-only、bank-only、invoice-only 与跨栏组合，1 个成员、重复 ID、missing/unknown row、active overlap/version drift、非法 summary 零写。金额不一致或方向不确定只触发既有 `amount_check.requires_note` + `note`，材料不完整不阻止 active relation 创建，分组仍可保持同-case `unpaired`。
- Service layer：confirm/withdraw 继续走 `WorkbenchRelationCommandService` + UoW，保护 canonical revalidation、idempotency、history/audit、partial-failure rollback 与 immutable OA attachment/ETC 既有约束。未配对 active case 撤回必须要求 exact full active member set，并从最近 confirm history 的 `before_relations` 恢复上一稳定拓扑；在同一事务锁内重验 canonical member、restored case 与唯一 owner，历史不可证明或 owner 冲突时 fail closed，不做部分恢复。
- API contract：继续复用 `confirm-link/preview -> confirm-link` 与 `withdraw-link/preview -> withdraw-link`；response shape、error envelope、权限和 `amount_check.requires_note`/`note` 字段不变。preview/submit 覆盖同栏人工关系、`requires_note=true` 时缺 note 拒绝/带 note 成功、材料不完整成功后仍 unpaired、两区 active case 可撤回、singleton 撤回拒绝、exact selection 400 和 topology/canonical/version drift 409。
- Read model/cache/worker（历史当时合同）：当时覆盖 relation mutation 后 exact scope 与 generation；2026-08-13 起由 direct normal GET 和 page runtime 零引用合同替代，unpaired relation topology 恢复仍保持。
- Frontend interaction：`WorkbenchSelection.test.tsx` / `WorkbenchZone.test.tsx` 保护关系确认/撤回；`WorkbenchExceptionDrawer.test.tsx` 保护 `未配对异常 n | 已配对异常 m`、逐项审阅、accept/keep/撤回、具体 chip 和只读权限。
- End-to-end：`workbench-withdraw-flow.spec.ts` 承担 paired/unpaired active relation 撤回与上一稳定拓扑恢复；relation/network flows 承担同栏/跨栏 confirm、`requires_note` 路径、fresh 收敛与幂等；permissions/stale/exception flows 保护权限、non-fresh gate 和删除人工入口后系统异常链仍可用。覆盖映射以 `e2e-coverage.md` 的实际落地状态为准。
- Regression：自动 matching exact-sum/证据/唯一性/资源保护与撤回 fingerprint 不放宽；paired/unpaired 完整性、520/13 张发票、OA attachment、ETC、no-OA、batch accounting、turnover 和下游 linked/unlinked 保持原合同。
- 非适用：无 DB schema/migration/backfill、API response shape、read-model scope、worker topology 或新依赖变化，因此不新增迁移兼容、worker registry/manifest 或部署拓扑测试；用现有边界 guard 证明未扩散即可。

## 2026-08-11 自动匹配旧快照并发回归

- Repository：`tests/test_workbench_relation_repository.py::test_canonical_relation_member_lock_reports_deleted_member_and_locks_existing_rows` 保护 OA/流水/发票一次按类型读取、`FOR KEY SHARE` 行锁和缺失 typed identity 输出。
- Service：`tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_formal_plan_fails_before_relation_lock_when_canonical_member_was_deleted` 保护缺失成员在 relation advisory lock 与 snapshot write 之前 fail closed。
- Adapter：`tests/test_workbench_relation_command_repository_adapter.py::WorkbenchRelationCommandRepositoryAdapterTests::test_canonical_member_lock_delegates_to_durable_repository` 保护 command service 继续通过既有 durable repository 边界读取，不在 service 散落 SQL。
- PostgreSQL integration：`tests/test_oa_pending_payment_postgres_integration.py::OaPendingPaymentPostgresIntegrationTests::test_stale_matching_plan_cannot_recreate_relation_after_oa_disappears` 复现事务外旧 plan、OA 权威删除和后续 formal confirm，断言错误码稳定且零 active relation 写入。
- Regression：不改变 API response、generation、queue、worker、Redis 或前端交互；既有 confirm/withdraw、matching orchestrator、runtime boundary 和 OA snapshot 回归必须继续通过。

## 2026-08-11 固定紧凑三栏与区域时间筛选

- Frontend component：`WorkbenchZone.test.tsx` 保护银行“全部 + 年月”位于区域标题栏、栏显示菜单只包含 OA/银行流水/进销项发票且最后一栏不可隐藏；`WorkbenchSelection.test.tsx` 保护 paired/unpaired 时间筛选独立、筛选仍映射既有银行时间 I/O、两区始终同时可见且无布局/放大入口。
- `WorkbenchZone.test.tsx` 同时保护 OA、银行流水、进销项发票三栏长文本完整直显、不创建行单元格 hover 浮层，且直接点击文本仍只触发一次行选择；列筛选候选仍由 HeroUI 菜单惰性读取并允许长标签换行。

## 2026-08-14 OA 申请时间与银行完整分类路径

- PostgreSQL integration：`test_workbench_query_postgres_integration.py` 使用真实 migration 后临时库，保护 in-progress OA 从 source snapshot 的嵌套 `detail_fields.申请日期` 输出 `apply_time/application_date`，并能按真实申请日期搜索；不得回退 scope 月首日。
- Frontend API/component：`WorkbenchApi.test.ts` 保护 PostgreSQL `timestamptz::text` 的 `+08` 后缀被格式化为稳定本地展示文本且完整 `category_label_path` 保真；`WorkbenchColumns.test.tsx` 保护每个 OA 父记录有时间或“时间缺失”chip、银行分类显示完整 `主标签 / 子标签` 路径，并保留待分类/待确认状态优先级。
- Regression/performance：实现复用 direct canonical 批量查询和既有 DTO，无新增 HTTP、SQL statement、逐行 I/O、React state/effect、Popover、read model、cache 或 worker；日常报销子付款项仍不重复父 OA 时间。
- Layout / regression：`RelationGroupGrid.test.tsx`、`WorkbenchColumnLayout.test.tsx` 与 `App.test.tsx` 保护单一紧凑列合同、无经典 action column/focus body class；详情、预览、异常抽屉继续复用同一固定布局。没有后端、API response、read model、worker、权限或持久化合同变化。

## 2026-08-06 进行中 OA workflow gate v21

- Business core：`tests/test_workbench_relation_grouping.py` 覆盖材料完整但进行中的关系仍为 unpaired、`oa_in_progress` 阻断、多 OA 任一进行中阻断和完成后同 case paired。
- Service/read model：`tests/test_workbench_relation_sql_projection.py`、`tests/test_workbench_sql_runtime.py` 保护 admission canonical rows/source proof、删除 pending claim exclusion、v21 淘汰 v20 generation/cache。
- Frontend：`OaWorkflowStatusChip.test.tsx` 与 `WorkbenchColumns.test.tsx` 保护 HeroUI 申请类型及“已完成/进行中/状态未知”chip；API mapper传播 `blockingReasons`。
- Regression（历史记录）：当时验证过 1 秒 refresh-status 与 active-generation 原子发布；这两条页面合同已在 2026-08-13 direct canonical 迁移中退役。其它 relation mode 不变，且没有新增 read model、worker、queue、缓存或第三个 zone。

## 2026-08-05 历史 WEX 运行时退役与搜索合同 v20

- Business core：`tests/test_workbench_relation_grouping.py` 证明任何当前异常默认阻断已配对、`accept_paired` 只覆盖异常 blocker、`keep_unpaired` 与撤回保持未配对，历史 WEX 不再改变分组。
- Service/read model/API：`tests/test_workbench_sql_runtime.py` 保护 v20 淘汰 v19 generation/cache、projection 丢弃 `exception_case`/`handled_exception`、source freshness 排除历史 exception table、搜索投影包含 OA `completed_at`；`tests/test_search_query.py` 和 `tests/test_workbench_routes.py` 保护金额及人民币符号数值等价与普通文本转义。
- Frontend：`WorkbenchSelection.test.tsx` 与 `WorkbenchExceptionDrawer.test.tsx` 保护单 bucket 有界读取、逐项审阅、进入已配对、留在未配对、撤回与主区 canonical refetch。
- E2E / regression：`workbench-exception-flow.spec.ts` 保护异常默认未配对、人工放行进入已配对、撤回同步返回未配对；权限套件验证 read-export 零 mutation。没有增加表、worker、queue、cache owner、依赖或并行 fallback。

## 2026-08-05 OA/发票比较单元与附件缺失异常

- Business core：`tests/test_workbench_amount_check_service.py` 保护日常报销逐 `source_expense_item_id` 比较全部显式绑定发票，覆盖 `290=145+145`、`405=350+55`、一项多发票差异只生成一个 anomaly item、附件数大于零且零绑定发票生成 `OA发票附件缺失`；支付申请继续按关系组总额比较，缺金额不误报。
- Service/API：`tests/test_workbench_relation_grouping.py` 保护 `workbench_anomaly.items[]` 和具体 pair chip；`tests/test_workbench_anomaly_review_service.py` 保护 exact item review、stale fingerprint、其他 blocker 与新 API；PostgreSQL integration 保护异常桶在分页前过滤及 SQL/Python fingerprint 一致。
- Frontend：`groupDisplayModel.test.ts` 保护显式 ownership 与金额判断解耦、组合发票同行和附件占位；`WorkbenchApi.test.ts` 保护统一 anomaly DTO；抽屉/页面测试保护具体 chip、两个新 bucket、逐项审阅、流转与只读行为。

## 2026-08-15 退款净额、历史附件归一与人工金额分类

- Business core：`tests/test_workbench_amount_check_service.py` 保护付款关系按同 relation 的 `1050 支出 - 35 退款收入 = 1015` 与 OA/五张发票 `1015` 比较，三种金额异常均为空；`tests/test_oa_attachment_invoice_linking.py` 保护历史 OA 子项 ID 通过唯一 parent + row index 归一，使 `350` 子付款项与 `150+100+100` 三张发票同带，歧义来源保持 fail closed。
- Service/API：`tests/test_workbench_page_query_repository.py` 保护 SQL 异常候选分区同步使用净额而非 gross；`tests/test_workbench_anomaly_review_service.py` 保护金额异常必须提交 allowlist 人工分类、`无异常` 互斥、fingerprint/idempotency/persistence；`WorkbenchApi.test.ts` 保护 `review_classification_codes[]` 双向 DTO。
- Frontend：`WorkbenchExceptionDrawer.test.tsx` 保护金额下拉多选、提交前禁用、`无异常` 互斥、已配对撤回沿用原人工分类及只读权限。没有新增 table、migration、read model、worker、queue、cache、逐行 I/O 或依赖。

## 2026-08-15 OA附件发票多对多与子付款项定位

- Business/service：`test_mongo_oa_adapter.py` 保护同一物理附件跨两个子付款项只解析一次、再分别绑定来源；`test_oa_attachment_invoice_promotion_service.py` 与 `test_import_service.py` 保护同 OA 多来源边不丢失；`test_workbench_amount_check_service.py` 和 `test_workbench_relation_grouping.py` 保护 `18+18=36` 不重复计票、一个 item 多票集合求和，以及缺失/解析失败/待归属分类。
- API/frontend：Workbench DTO 只发布复数 `source_expense_item_ids[]` / anomaly source arrays；`WorkbenchApi.test.ts`、`groupDisplayModel.test.ts`、`RelationGroupGrid.test.tsx` 保护一票多项只渲染一次、多票一项同带、待归属发票不进入父摘要。`WorkbenchExceptionDrawer.test.tsx` 保护缺失 chip 使用 `target=_blank` 与 `noopener noreferrer` 打开稳定 OA 列表路由。
- Performance/regression：复用单次 Workbench direct canonical SQL 与前端纯内存图遍历；无新增 HTTP、read model、worker、数据库表、逐行 I/O 或页面 effect。PostgreSQL exception filter 使用 relation 内递归连通分量，避免顶部异常计数继续按旧单值来源误报。
- Regression：没有新增表、migration、read model、worker、queue、cache owner、HTTP 详情链路或依赖；旧逐关系总额、逐发票复制字段和金额决定显式 ownership 的判断已删除。

## 2026-08-05 紧凑异常抽屉与撤回忽略（历史合同，已由 2026-08-15 统一异常审阅替代）

- Business core / repository：`tests/test_workbench_relation_grouping.py` 与 `tests/test_workbench_sql_runtime.py` 保护进行中、已忽略 OA/发票异常组的互斥计数；历史 ignored row/WEX 不进入运行时列表或计数。
- API / frontend：`WorkbenchApi.test.ts` 保护 additive `ignored_exception_count` 与三栏总金额映射；`WorkbenchExceptionDrawer.test.tsx` 保护 HeroUI 单选状态、默认折叠摘要、单组展开、无重复三栏表头、ignore/撤回忽略和只读权限；`WorkbenchSelection.test.tsx` 保护撤回忽略直接调用 canonical action、刷新主表和抽屉且不再打开旧确认 modal。
- E2E / regression：`workbench-exception-flow.spec.ts` 与权限 Browser suites 覆盖“进行中的异常/已忽略的异常”、折叠展开、写权限和撤回忽略；旧 `CancelProcessedExceptionModal` 已删除，不保留兼容入口。

## 2026-08-04 OA/发票金额不一致异常闭环（历史合同，已由 2026-08-15 统一异常审阅替代）

- Business core：`tests/test_workbench_amount_check_service.py` 覆盖按分精确相等、1 分差异、缺少任一侧和任一成员金额时不误报；`test_workbench_relation_grouping.py` 保护 active/ignored anomaly 在 group payload 中传播。
- Service/repository/API：`tests/test_workbench_amount_mismatch_exception_service.py` 覆盖 server actor、all-scope 实际 month、stale fingerprint/version、幂等 ignore/restore、审计、month-scoped decision read，并证明 legacy exception loader 排除独立 scenario；`test_workbench_query_facade.py` 保护 `exception_bucket` 透传，`test_auth_guard.py` 保护 read-export 拒绝两个写接口。
- Read model/cache：现有 Workbench generation payload 增加 additive anomaly 字段；过滤在 PostgreSQL active generation group payload 上完成，按 bucket 先过滤再分页。没有新增 manifest、scope、worker、queue、Redis owner 或第二 read model。
- Frontend：`WorkbenchApi.test.ts` 覆盖 DTO、bucket query 和 action contract；`WorkbenchExceptionDrawer.test.tsx` 覆盖 active ignore、发票来源下 chip、processed restore；`WorkbenchSelection.test.tsx` 保护统一抽屉替代旧双 modal 且旧恢复行为不丢失。
- E2E/regression：`workbench-exception-flow.spec.ts` 覆盖精确 1 分金额差异从主表 chip、统一抽屉忽略、已处理、恢复到主表的完整链路；权限 Browser suites 继续证明 read-export 零 mutation。旧 `IgnoredItemsModal`、`ProcessedExceptionsModal` 与对应独立测试已删除。

## 2026-07-31 row detail 稳定代际纯读与错误分层

- Service/API：`tests/test_workbench_query_facade.py` 证明 stable generation 详情即使 repository 状态为 `refreshing` 仍返回 200，不调用第二次 canonical stale proof、零 refresh enqueue；同时覆盖 404 真缺失、409 version conflict、503 visible-member invariant 与 timeout unavailable。
- Repository/read model：`tests/test_workbench_sql_runtime.py` 证明 version check 与 detail read 继续位于同一 repeatable-read snapshot；仅在 detail miss 的冷分支检查 active group membership，区分真 404 与可见成员缺详情 503，且绝不读取 `workbench_group_rows.payload/member_payload` fallback。
- Frontend：`WorkbenchSelection.test.tsx` 证明只有 409 重载一次 active generation；404 不重载、不重试并显示安全中文错误；关闭抽屉 abort 在途详情。`WorkbenchApi.test.ts` 覆盖新增 503 错误映射；`RelationGroupGrid.test.tsx` 证明 ETC/流水规则 summary 没有 row detail 入口。
- Regression：OA、流水、发票继续共用同一 drawer/API/facade/repository 链路；没有新增表、索引、cache、worker、queue 或第二详情实现。生产验证要求为三类详情 p95 `<1s`、同一 exact generation 请求全成功、读取前后 generation/dirty scope/outbox 无增量，并完成 release gate T+0/T+60/T+300。

## 2026-07-28 逐栏折叠、普通行直显与搜索真实预览

- Business core：`no_oa_bank_batch` 与普通关系保留全部真实行；`bank_flow_rule_batch` 只有银行成员数 `>3` 才生成银行栏 summary/collapsed rows，1 到 3 行直接显示；ETC 仍只折叠发票栏。
- Repository/read model：summary page 不再把普通银行/发票行截成 3 行；折叠栏只传 summary + count，搜索只决定组命中、不携带或自动展开 collapsed rows。ETC business batch 即使只有部分成员已建立严格 link，折叠汇总仍保留完整 `invoice_ids` 成员并按发票身份去重。schema v12 淘汰旧 generation/page cache，并统一 ETC relation proof，不新增表、worker、cache 或 API。
- API/Frontend：group detail 按 `collapsed_row_counts.<pane>` 逐栏验证；ETC 的 OA/银行栏验证正常 rows，发票栏验证 collapsed rows。闭合态搜索直接渲染真实命中行并高亮，不显示“隐藏内容命中”、不自动展开或预取详情。
- Regression：普通多行与 legacy no-OA 不出现通用“还有 N 条，展开”；bank-flow 与 ETC 保留 click-only detail、失败可重试和同 generation fail-closed。

## 2026-07-28 日常报销付款明细复合行

- Backend/API：`tests/test_workbench_query_service.py` 保护父 OA 行只发布精简稳定付款明细字段，附件发票继续携带显式 `source_expense_item_id`；不新增 relation member 或独立配对对象。
- Frontend：`web/src/test/WorkbenchApi.test.ts` 保护 item/source ID DTO；`WorkbenchColumns.test.tsx` 保护申请类型移入申请人栏并清理项目栏 process/evidence chip；`RelationGroupGrid.test.tsx` 保护“多个项目 · N + 父 OA 金额”、逐项项目/金额、单条精确金额才同行、部分精确覆盖与残余发票独立展示，以及点击子项仍只选择父 OA。
- Frontend display：`groupDisplayModel.test.ts` 以 `174.94 = 78.34 + 12.00 + 28.80 + 55.80` 的生产形状保护显式发票逐付款项同行、父 OA 级银行流水不参与子项分段，以及缺失项只保留 `OA发票附件缺失`；`RelationGroupGrid.test.tsx` 保护该父级流水复用既有整栏 CSS grid 跨越全部展开行。
- Read model：Workbench schema 升级为 v8，使旧 generation/page cache 失效并经现有 exact/all freshness gateway 重建；没有新增表、worker、cache 或第二 read model。

## 2026-07-26 relation preview 真实 DTO、并发反馈与安全错误回归

- `web/src/test/WorkbenchApi.test.ts` 使用真实 confirm-before / withdraw-after `selection + zone/status=unpaired` fixture，证明 preview-only adapter 保留 `rawGroupType=selection`、正式页面仍映射为 unpaired，非法 selection fail closed，普通 groups mapper 继续拒绝 selection。
- `web/src/test/WorkbenchSelection.test.tsx` 与 `web/src/test/WorkbenchZone.test.tsx` 用受控未 resolve Promise 证明 confirm/withdraw 在下一 render 已显示可访问 busy 状态，pending 期间重复点击只产生一次 POST，selection/version 漂移响应不会打开 drawer，失败后入口恢复且后端英文/parser sentinel 不进入 UI；既有 formal submit drawer 回归保持通过。
- Workbench API 安全错误矩阵覆盖 stale/version conflict、row unavailable、401/403、409、invalid preview、5xx 与 non-JSON response；只允许批准的中文文案，同时保留 `status/code/requestId` 支持字段。
- `web/e2e/workbench-relation-fanout.spec.ts` 与 `web/e2e/workbench-withdraw-flow.spec.ts` 的 Chromium fixture 使用真实 selection DTO，覆盖 confirm/withdraw pending、成功 drawer/关闭和失败恢复；本次不运行无关 Browser suite。

## 2026-07-25 关联台写后恢复读放大回归

- 历史 `tests/test_workbench_query_facade.py` 曾验证公开 refresh-status 与 generation cache；该文件及对应 runtime 已在 2026-08-13 退役，当前由 direct query repository、HTTP 503 与零 fallback 合同取代。
- `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests::test_groups_cache_miss_waits_for_same_generation_fill_before_querying` 证明同一 fresh generation + query 的缓存回填并发只由锁 owner 查询 PostgreSQL，follower 等待后读取精确代际缓存；缓存未生成时仍有界退回原 repository 路径。
- 历史 withdraw 用例曾等待 refresh-status；当前写成功后只执行一次 `no-store` canonical GET，并继续验证 OA、银行、发票分别恢复为完整 unpaired singleton。
- `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_filters_workbench_groups_page_from_structured_group_rows` 锁定 active-member CTE 为 `NOT MATERIALIZED`，防止 all-scope 条件查询恢复“先复制全部 active members、再应用搜索/筛选”的优化屏障；同文件搜索、pane/列/时间、total/row counts 和数据库内有界分页回归继续保护原业务语义，并断言不再构造 matching id 数组。
- 现有 Workbench Selection 全文件继续覆盖 confirm operation projection、withdraw blocking UI、generation version conflict、failed/stale 状态、权限、筛选和详情交互；没有增加 retry fallback、第二轮询器或放宽 fresh 判断。

## 2026-07-25 访问时 exact Workbench proof 与 consumer 隔离

- `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_workbench_all_freshness_returns_only_exact_canonical_mismatch_scopes` 证明 `month=all` 使用 canonical/active-generation bulk proof，只返回真实变化月份。
- `tests/test_workbench_sql_runtime.py` 的 relation-preview selection 合同证明 selected row 查询使用 generation/scope/`row_id=ANY`，OA attachment context 仍绑定同一 generation-set；跨月 shard 中规范化内容完全相同的 canonical selected/context row 只返回一次，同 row id 的金额、状态或来源内容漂移继续 fail closed，missing、non-fresh 和 version drift 合同不变。
- `tests/test_workbench_write_characterization.py` 与 `tests/test_workbench_auth_context_idempotency.py` 证明 confirm/withdraw preview 每请求只调用一次 bounded selection，旧 full-payload/alias/withdraw row resolver 一旦调用即失败；formal confirm/withdraw 把 preview callable 设为一旦调用即失败后仍通过 canonical command/UoW。
- disposable PostgreSQL fixture（month/all、2/6/20 rows、active/obsolete generations、OA/银行/发票及 attachment context）旧/新各 10 次证据：旧 full-payload preview p50 为 `12.699–222.378ms`、p95 为 `12.902–248.509ms`；新 bounded preview p50 为 `0.728–2.930ms`、p95 为 `0.755–3.516ms`，每次固定 6 条测试计数 SQL、完整 payload copy/scan 为零。EXPLAIN 证明 month bulk 命中 `workbench_rows_generation_scope_row_uidx`（3 rows、10 shared hits、0 reads），all generation-set join 同样命中该索引（3 rows、19 hits、0 reads），无需 migration/index。
- `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests::test_searched_initial_all_page_enqueues_only_exact_workbench_mismatch_scopes` 证明带搜索的 combined initial 也必须先通过 freshness gate，只入队 exact Workbench scopes，不得因查询不可缓存而退化成 `api_initial_page_stale -> workbench:all`。
- `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests::test_month_initial_does_not_enqueue_unrelated_all_statistics_scopes` 证明单月页面只读取 all-period 统计 generation 状态用于 cache/fail-closed，不得因此入队其它月份。
- 关联台不消费 `workbench_relation` distribution，已删除 combined initial 的 relation dependency callback、阻塞、状态字段和双投递；其它实际消费者的 relation gate 不变。
- `tests/test_app_postgres_mode.py`证明access enqueue只在既有active projection存在时附canonical `freshness_token`，并复用调用方已计算的expected versions、不重复canonical proof；missing projection仍按普通enqueue自愈。`tests/test_runtime_queue.py`与真实PostgreSQL integration证明同target并发/完成窗口去重、A→B→A latest-target语义、不同target follow-up及failed dirty恢复。
- `tests/test_platform_runtime_boundary_guards.py`、Workbench write/idempotency/stale与Batch Accounting回归机械禁止`_schedule_workbench_read_model_persist`、后台rebuild线程、旧async env和测试monkeypatch重新进入生产/测试链路。

## 2026-07-24 Workbench generation 批量发布回归

- `tests/test_workbench_sql_runtime.py` 证明 rows、groups、group_rows 三张热点 generation 表使用同一事务内 PostgreSQL `COPY`，旧多值 `INSERT` 不再承担这三段写入，activation 仍在全部数据成功后执行。
- `tests/test_postgres_connection.py` 覆盖 `copy_rows(...)` 的 cursor 生命周期、typed row 传递与计时边界；`tests/test_postgres_state_store_integration.py` 在 disposable PostgreSQL 证明 JSONB、数组、日期、numeric 行真实落库后才激活 generation，并证明任一 COPY 中途失败会回滚全部 payload、保留一条既有 `failed` 诊断且绝不留下 active 状态。
- 没有新增第二 writer、staging 表、缓存或 worker；不支持 `COPY` 的测试连接保留既有批量写 fallback，生产 psycopg 只走原生 COPY。

## 2026-07-22 Turnover 人工闭环冻结要求分区回归

- Business core：`turnover_manual_closure` active relation 只拥有同组关系，不无条件代表完成；OA/发票四种冻结 requirement 组合按 OR 聚合，未知、空或缺失 snapshot fail closed。要求 OA 的 bank-only case 保持完整 unpaired，补齐要求后才以同 case paired；`batch_accounting` 与 ETC 显式完成合同保持隔离。
- Service/API：Turnover 人工确认复用同一次 selected-row 快照，并且只读取一次 canonical rule payload，冻结 tag code、OA/发票布尔值、来源和版本；合并后的任一 bank member 不在 selected ids、bank row 缺失/重复或规则无效时 UoW 不打开。deterministic 写入的既有冻结合同不变。
- Read model/Audit：SQL projection、写后 operation projection 和 preview 复用 relation 自身冻结要求；Page Audit 独立发现缺快照与错误 zone；本次不改变共享 projection schema、scope、worker 或 cache。
- Frontend：API mapper 保留显式 false、缺字段保持缺失语义；不完整 relation 的空 pane显示“待补 OA/发票”。生产组件与页面请求 I/O 未改变。
- 旧链回归：no-OA 规则保存不再扫描并追溯回写既有 Turnover relation；普通 manual、deterministic、batch accounting、ETC、合并与撤回测试共同防止其它页面分区被放宽。

## 2026-07-20 折叠流水详情惰性加载回归

- Repository：production-shape materialized group 只有银行成员时，group detail 仍必须返回 `oa_rows=[]`、完整 `bank_rows`、`invoice_rows=[]`，且折叠计数与明细成员一致。
- API client：HTTP 200 若缺少任一 pane 数组、group identity 不一致，或逐栏声明成员数与实际详情不一致，必须 fail-closed，不能把不完整 payload 安装为可展开数据；有 `collapsed_row_counts.<pane>` 的栏校验 collapsed rows，其它栏校验正常 rows。
- 前端交互：页面加载和 group 更新不得自动预取折叠明细；用户点击后只发一次详情请求，成功后展开，失败后保持折叠并显示可重试状态。
- 列筛选定位继续由 `WorkbenchColumnLayout.test.tsx`、`WorkbenchPaneFilter.test.ts` 和 App Shell Chromium smoke 保护；打开时读取真实侧栏宽度，不得恢复 `--sidebar-width` 继承状态或因侧栏开关重新渲染业务页面。
- E2E：首屏只显示 3 条流水摘要时不请求详情；用户点击“展开 4 条明细”后恰好请求一次 group detail，并渲染 4 条完整流水。

## 2026-07-20 Turnover 撤回 preparation 隔离回归

- `tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_prepared_withdraw_reuses_lock_relation_snapshot_and_freshness` 保护同一 service/transaction 的 preparation 复用一次 lock/scoped snapshot/freshness。
- `test_prepared_withdraw_rejects_a_different_case` 保护 preparation 不得跨 case 使用；普通 Workbench withdraw 不传 preparation，既有测试继续覆盖原调用合同。

## 七类测试

| 类别 | 适用 | 主要覆盖 |
| --- | --- | --- |
| 1. Business core | 是 | 人工至少 2 个不同 canonical members（同栏/跨栏）、`requires_note` 门禁、上一稳定拓扑撤回恢复；确定性证据、365/30 日边界、N:M:K exact-sum、歧义/金额-only/红冲 fail-closed、撤回阻断指纹、paired/unpaired 精确分区 |
| 2. Service layer | 是 | repository 输入、relation/matching 单 UoW、幂等、rollback、history/`before_relations` restore、普通 relation 写零 dirty/outbox、旧状态清理 |
| 3. API contract | 是 | paired/unpaired shape、分页/search/detail、filter-options、confirm/withdraw shape 不变、差额 note、版本冲突、权限、unknown state fail-fast |
| 4. Read model/cache/worker | 是 | page runtime 零 manifest/worker/cache/queue/generation；normal GET 只走一个 read-only canonical snapshot；共享 `workbench_relation` 与 matching 继续按各自 exact-scope 合同收敛 |
| 5. Frontend interaction | 是 | 两区渲染、singleton/active relation 未配对、任意至少 2 个成员选择/preview、两区关系级撤回、旧人工异常入口缺席且系统异常抽屉保留、loading/empty/error/stale、权限与分页 |
| 6. End-to-end | 是 | canonical import/OA -> matching；人工同栏/跨栏 confirm -> paired/unpaired；两区 active relation withdraw -> previous stable topology/singletons；跨页独立收敛与非消费者隔离 |
| 7. Regression | 是 | 520 样例、13 张发票、ETC/OA 附件、no-OA、batch accounting、turnover、cost/search/invoice lifecycle |

本轮 direct canonical 迁移覆盖 Category 1–7：direct repository/facade/API tests 保护 typed identity、bounded
snapshot query、HTTP shape 与 fail-closed；runtime registry/gateway/boundary tests 保护 page scope 零链路；既有组件和
Browser tests 保护两区交互与写后一次 normal GET。历史 generation retention 测试记录保留在下方日期章节，不再是
current runtime gate。

## 核心固定测试

- `tests/test_workbench_free_matching_engine.py`
- `tests/test_workbench_formal_relation_repository.py`
- `tests/test_workbench_matching_orchestrator.py`
- `tests/test_workbench_relation_grouping.py`
- `tests/test_workbench_relation_alignment_service.py`
- `tests/test_workbench_direct_query_facade.py`
- `tests/test_workbench_page_query_repository.py`
- `tests/test_workbench_query_postgres_integration.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_workbench_query_service.py`
- `tests/test_postgres_migrations.py`
- `web/src/test/RelationGroupGrid.test.tsx`
- `web/src/test/WorkbenchApi.test.ts`
- `web/src/test/WorkbenchSelection.test.tsx`
- `web/src/test/WorkbenchWriteGate.test.ts`
- `web/src/test/WorkbenchZone.test.tsx`

## 必须保护的不变量

- 520 元历史 case 前缀不影响 active relation 进入 paired。
- 13 张合计 1709.49 元发票保持 13 个 unpaired singleton。
- `paired ∩ unpaired = ∅`，`paired ∪ unpaired = canonical identities`。
- 人工 confirm 只以 normalize 后至少 2 个不同 canonical rows 为最低成员门槛；同类型集合合法。每个 exact requested ID 必须解析为支持类型，1 个成员、duplicate/missing/unknown row 与 active owner/version 冲突均零写。只有 `amount_check.requires_note=true` 时才必须填写既有 `note`；金额相等和完整性不得重新成为人工创建门槛。
- paired/unpaired active relation 都可按关系级撤回；最近 confirm history 的 `before_relations` 是上一稳定拓扑恢复源，未配对 singleton、row `case_id` 和 display metadata 不能触发或决定恢复。
- 装饰字段、输入顺序和旧 candidate/decision metadata 不改变 membership/group id。
- OA 附件来源 alias 与 canonical OA row id 不同的情况下，正式关系 alignment 仍指向 canonical OA；复合行只按显式 source item + 唯一 row index 映射 canonical expense item id，且不修改 canonical 发票来源字段。
- 同金额竞争、exact single 与 exact sum 竞争、duplicate reference、currency/direction mismatch、fuzzy/date-only evidence 均不写关系。
- 显式引用跨全部历史；通用组合证据 365 天接受、366 天拒绝。日常报销申请人和银行对方户名的专用员工强证据 30 天接受、31 天拒绝，且不放宽通用公司对方户名最小长度。
- 缺银行的 OA+附件发票 active relation 只有在一对多附件总额与唯一员工流水精确相等时才原 case 补全；多个同额候选、跨 case 重叠、完整三栏和人工撤回 exact member set 均零写。
- 超过六个成员和 2:2:2 均能在有界唯一闭合时形成一条正式关系。
- UoW 失败时 relation、history、idempotency 和 outbox 不得半写入。
- source payload 即使把无 active relation 的 row 放在旧 paired section，最终也必须降级为 unpaired singleton。
- E2E mock 不得用共享历史 `case_id` 构造未配对组；每区单一搜索词必须扫描该区三类结构化行，任一行命中后保留完整组上下文，隐藏 pane 与折叠明细也必须可命中。
- 未配对 canonical row 若携带旧 `candidate:` / `decision:` / `temp:` ownership，direct descriptor 必须清理与该候选 ownership 绑定的 mode 装饰且仍保持 singleton；control owner 优先级只允许 active formal relation > 有效非异常 override。正式关系成员不能携带旧 override/WEX decoration；历史 `exception_case`、`handled_exception` 与 row-ignore 不得进入 direct page DTO，`pending_input_invoice` 等合法非异常 override fields 仍与 canonical override 精确一致。
- ETC collapsed-summary 必须同时物化 summary row 和全部 invoice detail rows；paired/unpaired 只改变 zone/status，不得丢失、重复或隐藏明细。
- Workbench page GET 不得访问 Redis page payload、generation/projection 表或 refresh queue；同一请求的 SQL 条数必须有界且与成员数无关。
- combined initial 两区首屏必须各为 50 groups、`has_more` 保留 exact total，candidate SQL 每区读取最多 51 个 keys；前端不显示手动“加载更多”，只在查询稳定且滚动接近底部时请求下一 cursor。同区请求去重，搜索/筛选变化会清 cursor，旧响应不得并入新结果；不得退回 OFFSET、200-group 首屏或全量 payload。
- 默认 all-scope `/groups` 的 total/row_counts 由同一 direct group spine 精确计算；keyset 只优化深分页，不能把 exact count 伪装成近似值。候选和 hydration 的 SQL 数必须与成员数无关、无 N+1。
- all-scope 区域搜索、来源、pane/列/时间筛选只扫描 scope-first canonical facts/active formal relations，条件按既有 AND/OR 语义相交；分页只 hydration `page_size` 可见 groups。搜索覆盖展示字段、排除内部 identity/raw payload、转义 ILIKE 通配符并限制 200 字符。
- 前端必须断言每区只有一个 HeroUI `SearchField` 且位于区域 header 同行；输入时只请求受影响 zone，等待期间保留当前稳定结果并显示 pending，失败可重试。所有可见命中片段都高亮；只命中折叠明细时仍返回对应关联组，但闭合态只显示摘要，不显示折叠成员且不发详情请求。搜索和非搜索状态下，ETC 发票与流水规则批次都只能由用户显式点击展开；收起后必须恢复摘要，搜索切换期间完成的旧详情请求不得重新展开新结果。
- 搜索框在首个 combined initial 完成前已可输入时，initial 安装后必须补发该 zone 的权威 direct query；不能只对首屏 10 组做本地高亮并漏掉其它组或折叠明细。
- 关联台 Audit 绿色结果只绑定本次 immutable canonical snapshot 的 expected-set、typed membership、active relations、异常与关键字段；下一次 dashboard refresh 清除旧结果。matching scope 是独立 domain 诊断，不是页面 GET freshness。
- matching source-version 回归必须证明 Workbench page direct SQL 不进入 matching provider；bank-flow/no-OA 的独立 read-model provider 只保留自身真实依赖。失败 scope 运维重试必须覆盖 dry-run 零写、fingerprint drift 零写、非 failed 拒绝和 exact month 单次 durable requeue。
- 普通标量列的同列多选必须按 OR，`全选`不能把结果清空；不同列/不同 pane 继续按 AND，银行金额表头的方向+付款账号复合筛选继续要求同一行同时满足。前端本地过滤、HTTP mock、repository SQL 和 summary preview 必须使用同一合同。
- group detail 必须稳定输出三个 pane 数组；详情保持 click-only lazy load，按 case/typed detail key 在一个 repeatable-read snapshot 中窄查，禁止 mount/update 自动预取、全区 scan 或静默吞错。row miss 返回明确 404，不做 generation reload/retry loop。
- 每个 visible summary member 必须能在同一请求 page-only hydration 中解析为 typed canonical row；缺成员或 identity drift 整个请求 fail closed，不回退历史 `workbench_rows` 或 member payload。

## 验证命令

```bash
python3 -m pytest -q \
  tests/test_workbench_free_matching_engine.py \
  tests/test_workbench_formal_relation_repository.py \
  tests/test_workbench_matching_orchestrator.py \
  tests/test_workbench_relation_grouping.py

python3 -m pytest -q \
  tests/test_workbench_page_cursor.py \
  tests/test_workbench_page_query_repository.py \
  tests/test_workbench_page_selection_repository.py \
  tests/test_workbench_direct_query_facade.py \
  tests/test_workbench_query_postgres_integration.py \
  tests/test_workbench_v2_api.py \
  tests/test_workbench_routes.py \
  tests/test_postgres_migrations.py

# 需设置一次性本地 FIN_OPS_TEST_DATABASE_URL
python3 -m pytest -q \
  tests/test_workbench_query_postgres_integration.py

cd web && npm test -- --run \
  src/test/RelationGroupGrid.test.tsx \
  src/test/WorkbenchApi.test.ts \
  src/test/WorkbenchSelection.test.tsx \
  src/test/WorkbenchWriteGate.test.ts \
  src/test/WorkbenchZone.test.tsx

bash scripts/verify.sh lint
bash scripts/verify.sh docs
```

本次行为变更的最小定向验证还包括：

```bash
python3 -m pytest -q \
  tests/test_workbench_v2_api.py \
  tests/test_workbench_pair_relation_service.py \
  tests/test_workbench_relation_command_service.py \
  tests/test_workbench_uow_contract.py \
  tests/test_workbench_idempotency_contract.py \
  tests/test_workbench_relation_grouping.py \
  tests/test_platform_runtime_boundary_guards.py

cd web && npm test -- --run \
  src/test/WorkbenchSelection.test.tsx \
  src/test/WorkbenchZone.test.tsx \
  src/test/WorkbenchApi.test.ts \
  src/test/WorkbenchWriteGate.test.ts \
  src/test/WorkbenchExceptionDrawer.test.tsx
```

发布后只读验证：

```bash
scripts/with-production-admin-token.sh python3 -m fin_ops_platform.tools.http_slo_probe \
  --profile workbench-direct --warmup 2 --requests 100
```

生产命令的实际参数和 release 环境以 `docs/operations/runtime-worker-governance.md` 与 deploy control 为准；不得输出 token。

## 数据安全验收

- 本次不创建或恢复 canonical 数据备份，不删除或重建主数据库，也不修改已应用历史 migration。
- direct GET 必须是 `REPEATABLE READ READ ONLY`，不得修改 OA、银行流水、发票、正式关系或 history。
- 发布切换不 drop 历史 page-generation 表；它们只作为上一 immutable release 的离线回滚材料，当前 release 零读写。
- Audit 必须证明满足冻结 requirement 的 active relation typed members 与 paired display 双向相等；未满足 requirement 的 active relation 必须保持同 case、显式 incomplete 并进入 unpaired；无 active owner 的其余 canonical facts 全部 singleton unpaired。
- 520 case、发票号和 OA row id 必须在 direct canonical response 中同组；13 张样例必须完整可见。

## 2026-07-28 OA 子项对齐与完整性回归

- `tests/test_mongo_oa_adapter.py`、`tests/test_workbench_query_service.py` 保护来源费用内容/费用说明分别保真并进入 Workbench DTO，既有 `expense_content` 口径不变。
- `tests/test_workbench_relation_grouping.py` 保护普通 OA+发票 active relation 缺银行时保持同 case、进入 `unpaired` 并报告 `missing_row_types=["bank"]`；只有 batch-accounting 豁免，ETC marker 不再绕过冻结要求。
- `tests/test_workbench_auth_context_idempotency.py` 保护 confirm 在同一 UoW 内重读 selected canonical rows、拒绝漂移/多 batch，并把合法 ETC summary 的 external batch identity 持久化。
- `tests/test_workbench_page_audit.py` 保护合法 synthetic ETC summary 只有在 canonical batch + exact deterministic row id 双重证明时通过；任意 `etc-summary-*` 不得绕过 canonical integrity。
- `tests/test_workbench_query_facade.py`、`tests/test_workbench_sql_runtime.py` 与 `web/src/test/WorkbenchSelection.test.tsx` 保护 refreshing 时继续显示上一版 active generation、禁止 Redis payload 写入，并阻止迟到 non-fresh 响应覆盖操作投影。
- `web/src/test/WorkbenchApi.test.ts`、`web/src/test/RelationGroupGrid.test.tsx` 和 `groupDisplayModel.test.ts` 保护显式 `source_expense_item_id` 的单张/多张发票逐项同行；显式 ownership 不再被金额差异拆开，只有缺少显式来源的唯一单条兜底仍要求精确同额。输入乱序不影响付款项顺序，费用内容/说明在申请事由列显示，点击子项仍选择父 OA。

## 2026-08-03 三栏完整高度与严格一一对应回归

- Business/display core：`groupDisplayModel.test.ts` 证明显式费用子项 ownership 可承载一对多同行且不要求金额相等；缺少显式来源时，方向已知的唯一单条精确金额才可逐项同行。完整 source group 中存在隐藏组成项、重复金额或无显式归属的金额组合时 fail closed 并进入残余带。
- Frontend interaction：`RelationGroupGrid.test.tsx` 固定 `4 OA / 2 流水 / 1 发票` 的精确行逐项同行，其余 OA 保持独立；一对多来源只让其中唯一精确项同行，其它记录不伪装为同排。
- Browser E2E：`workbench-relation-fanout.spec.ts` 用 Chromium `boundingBox()` 证明部分费用项中的 200 元 OA 子项与 200 元发票实际同高同行，未匹配子项不出现该发票，同时点击子项仍选择父 OA。
- Expense-item regression：多项目报销的 OA 摘要、费用内容、选择父 OA 和项目顺序不变；发票比较使用价税合计，部分精确附件可同行，其余附件独立残余显示且不丢失。
- Performance：测试和 whole-repo scan 保护旧 `assignRowsByAmountFallback` / `findUniqueAmountSubset` 组合枚举不存在；实现只使用已有 DTO 的 Map/Set 线性判断，没有新请求、state/effect、DOM 测量、依赖、read model 或 worker。
- Workbench month/all schema 升至 v9，旧 v8 generation 与 page cache 必须返回 builder mismatch 并经既有 freshness gateway 重建。

## 2026-08-03 流水分类与内容高度回归

- Business/service：`test_bank_details_canonical_query.py` 保护 Workbench 目标银行 IDs 通过同一 bounded canonical classifier 得到 effective category 与 `category_resolution_status`，包含人工确认优先级和 SQL 参数边界。
- Read model/freshness：`test_workbench_sql_runtime.py` 保护单次批量 enrich、缺分类输出 `unmatched`、OA 不受影响；月份/all source proof 包含分类事实和确认/撤销版本，跨月 active relation 银行成员也进入对应月份 proof。month/all schema 升至 v16，旧 v15 generation 必须 stale。
- Frontend/API/layout：`WorkbenchApi.test.ts` 保护 resolution status 映射；`WorkbenchColumns.test.tsx` 保护金额三层、待分类/待确认与旧 relation status chip 删除；`RelationGroupGrid.test.tsx` 保护 cell 使用内容驱动 `min-height`、多记录项不可收缩裁切。
- Regression/performance：相关后端 404 条和前端 116 条回归通过；分类 enrich 是每 scope 一次 set-based query，不新增逐行 I/O、页面轮询、DOM 测量、worker、cache 或跨页写后 fan-out。

## 2026-08-13 direct API 流水分类 Chip 回归

- Repository/API：`test_workbench_query_postgres_integration.py` 保护 initial、groups 与 row detail 仅对当前可见 bank IDs 一次批量复用 Bank Details canonical classifier，输出 effective category 与 `category_resolution_status`；SQL 数量与 page size 无关，且不恢复页面 read model、cache、queue 或 worker。
- Frontend：`WorkbenchColumns.test.tsx` 保护金额单元格第三行使用 HeroUI 原生 `Chip`；已分类显示分类名称，`unmatched`/`needs_confirmation` 分别显示“待分类”/“待确认”，不恢复手写伪 Chip 或大卡片式 UI。
- Regression：Bank Details 仍拥有分类规则与页面组件；Workbench 只消费轻量 canonical projection，页面事实矩阵登记分类、确认和 settings facts。

## 2026-08-03 all-scope 成员筛选 SQL 回归

- `tests/test_workbench_sql_runtime.py` 保护 `month=all` 的搜索成员 join 只从 `g` 读取 group 投影字段，禁止重新生成会与成员 join 的 `zone` 冲突的裸列选择。
- `tests/test_workbench_query_postgres_integration.py` 在 disposable PostgreSQL 中实际执行搜索、来源类型、银行对方名列筛选和银行月份筛选四条成员 join 链路；每条都必须返回同一 active group，零结果搜索仍返回空页而不是 SQL 错误。
- API response shape、分页、freshness、active generation、worker、缓存与权限合同不变；本次不新增前端交互测试。

## 2026-07-22 Workbench v6 与历史修复回归

- `tests/test_workbench_sql_runtime.py` 证明当前 month/all v7 同步，groups/initial cache key 随 schema 派生失效，旧 v6 source version 返回 `builder_mismatch`，不能作为 fresh generation 消费。
- requirement repair 测试证明 legacy Turnover active relation 的完整 preimage/intended after fingerprint、partial execute、exact metadata rollback、partial rollback retry 和 drift zero-write；普通 relation、ETC、batch 与 inactive relation 不受影响。
- 既有 grouping/projection/query 回归继续证明：要求 OA 的 bank-only case 保持同 case unpaired，补齐 OA 后进入 paired，active generation 只经现有原子 publish 边界切换。
- `tests/test_audit_workbench_relation_display_tool.py` 同步保护审计口径：`turnover_manual_closure` 不再享有旧的 requirement 豁免；缺 OA 的 bank-only closure 在 unpaired 不报警，若出现在 paired 必须报告 `relation_requirement_partition_mismatch`。
- `tests/test_workbench_dirty_queue_wiring.py` 证明 v6 展示 schema 不再污染 matching stale scan，同时 bank-flow read-model source versions 仍包含展示 schema；`tests/test_workbench_matching_scope_retry_ops.py` 保护生产失败 scope 的精确、fingerprint-guarded durable retry。

## 2026-07-22 Workbench 写入门禁与 OA 同步恢复回归

- `web/src/test/WorkbenchWriteGate.test.ts` 保护权限、系统写安全、OA dirty/refreshing、read model non-fresh 和缺 active generation version 的单一优先级门禁。
- `web/src/test/WorkbenchSelection.test.tsx` 保护已选 OA + 银行流水在 OA 同步期间禁用确认/异常操作并展示真实原因；关联台专属 `/api/oa-sync/status` 返回 synced 后，即使全局 App Health 仍是旧 dirty 快照，也必须在既有 3 秒轮询周期内自动恢复按钮且保留同 generation 选择。
- `web/src/test/WorkbenchZone.test.tsx` 保护选择区禁用原因的可见与可访问输出；`web/e2e/workbench-stale-error-flow.spec.ts` 保护 Chromium 下 OA dirty/refreshing 的按钮、提示和零 mutation 请求。
- 性能不新增 I/O：门禁复用既有 OA status 轮询和已加载的 Workbench page status/version，不新增 API、轮询器、worker、read model 或跨页面状态。

## 2026-07-25 Workbench active-refresh polling 回归

- `tests/test_workbench_sql_runtime.py` 证明 exact scope 有 `pending/processing` outbox event 时直接返回 `refreshing`，不重复执行全月份 canonical proof或 schema scan；dirty 没有 active event 时标记 stale并返回 exact re-enqueue scope。

## 2026-07-25 - v7 complete canonical proof 与 active-flight 合并

- `tests/test_workbench_sql_runtime.py` 覆盖 Application 复用同一个 projection builder、重叠同 scope proof 只执行一次数据库读取、完成后独立访问重新查询、失败 flight 清理可重试、month/all v7 拒绝 v6，以及 composed all proof 保留全部业务字段。
- `tests/test_workbench_etc_relation_enrichment_postgres.py` 在 disposable PostgreSQL 证明 ETC 四表、bank/invoice soft delete、跨月 member 更新、relation withdraw 和 consumed bank settings 都会改变正确 scope proof；无关 settings 不污染 proof，migration `0125` 两个 identity 索引已应用。
- 当前候选没有改 HTTP shape、权限或前端交互；本条不新增重复前端测试。页面双开、写后零 fan-out、access-to-fresh `<3s`、Audit/queue/worker 与 fixture 恢复由最终生产矩阵负责。
- `tests/test_workbench_relation_sql_projection.py` 证明 `turnover_manual_closure` 保留在 Workbench 主 generation 的 canonical 输入，但不进入共享 `workbench_relation` distribution。

## 2026-07-25 - 并发恢复窄 OA I/O 与真实首屏验证

- `tests/test_workbench_query_service.py` 证明 exact/all scope 只返回 OA rows、all scope 继续使用既有 bulk adapter，且不构造 grouped Workbench payload。
- `tests/test_workbench_sql_runtime.py` 证明 generation builder 每个 scope 只调用一次 `list_oa_rows(...)`，附件父 OA 按既有 row-id/SQL fallback 补载，最终 projection shape 不变。
- `tests/test_write_operation_e2e_smoke.py` 与 `tests/test_write_operation_impact_matrix.py` 证明 relation consumer 使用 combined initial 的真实业务 zone：普通完整关系 confirm 在 `paired`，冻结要求未满足的 active Turnover closure 与 withdraw/recovery 均在 `unpaired`；并拒绝把 `/groups` 注册为关联台页面首屏。
- 本地 10,000 OA-row characterization 的旧路径中位数为 `145.809ms`，窄 I/O 为 `84.885ms`，重复组装/序列化 CPU 减少约 `41.8%`；该合成数据只证明共享 worker CPU 路径改善，不替代部署后真实 worker、首屏和总恢复耗时。
- 本次未改前端组件、交互或 HTTP response shape，不重复运行无关 183-browser suite；生产用同一类 test-owned 可逆 relation fixture 验证真实 combined initial、zero fan-out、queue/worker drain 与 System Audit。

## 2026-07-25 - exact/all 并发恢复禁止暂态 all fan-out

- `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests::test_initial_all_page_does_not_fan_out_while_exact_refresh_is_active` 复现生产并发形状：exact scope 已 processing，all freshness 暂时返回 `stale + active_refresh_in_progress` 且没有新的 exact target。
- 回归断言 all 请求返回 non-fresh 轻量状态但不 enqueue `workbench:all`；已有 exact 任务完成后，下一次页面轮询重新执行 canonical proof 并只 enqueue 剩余 mismatch 月份。
- 既有 `test_initial_all_page_enqueues_only_exact_workbench_mismatch_scopes` 继续保护稳定态 exact targets；冷启动/missing 且没有 active refresh 时仍保留正式 `all` 恢复入口。
- `test_default_initial_page_version_drift_fails_closed_without_caching_old_payload` 继续断言 generation-set 切换时不返回、不缓存旧 payload；同时锁定该正常发布竞态不再 enqueue `workbench:all`，下一次请求直接读取新的 active generation-set。

## 2026-07-26 - Candidate 可逆 runner 的 bounded preview 采样

- `tests/test_write_operation_e2e_smoke.py` 保护既有可逆 runner 的 `--relation-preview-samples`：默认 1、上限 20；生产候选使用 10。confirm/withdraw 的每个 sample 都经过 canonical preview DTO 校验，但每个 checkpoint 仍只允许一次正式 mutation。
- withdraw 的正式提交只消费最后一次成功 preview 返回的 `preview_id` 与 `submit_expected_versions`；任一 sample 的 HTTP/DTO 错误都会在 mutation 前 fail closed。preview p50/p95/max 与 request IDs 独立报告，p95 超过 3 秒只登记 `performance_status=miss`，不伪装成 correctness failure。
- `bank_oa_invoice` 的 affected consumers 固定为关联台、银行明细、待找发票、进项使用、OA 待付款、成本统计；销项收款与税务抵扣只作 isolation。测试按当前 scenario entry 断言 role，不使用其它 relation shape 的 affected 联集。
- 同条件旧/新 10 次 characterization 继续采用 Task 30-02 的同一 PostgreSQL fixture、scope/version/row IDs、连接与 warm-up：新路径固定每次 6 条 counted SQL、完整 generation scan 为 0、formal snapshot dependency 为 0，最大新样本 5.089ms。
- 相同 URL、无独立 `AbortSignal`、仍在进行的 combined initial 必须只产生一个 HTTP 请求；所有调用方都获得同一映射结果。请求完成或失败后必须移除 in-flight entry，后续读取重新访问服务器；搜索/筛选可取消请求不得被该合并吞掉。
- 正式 confirm/withdraw 的 canonical row resolver 必须读取生产已配置的 `PostgresWorkbenchPageSelectionRepository` typed canonical port；不得静默回退到全量 live builder。preview 与 submit 都携带同序 `row_ids` + `row_types`，正式 command/UoW 在事务内按 exact typed set 重新校验，不能消费页面 DTO。
- relation preview 必须保留首尾 fresh/version drift 门禁，但同一次 selection 只允许一次 generation proof；末次 freshness 的 active version 是结束 version 证据，不得再次执行等价 proof。`active_relations_for_row_ids` 必须走 active-only repository loader，不能为 active lookup 读取 relation history；withdraw restore preview 仍保留 history loader。
- `tests/test_workbench_relation_command_repository_adapter.py::WorkbenchRelationCommandRepositoryAdapterTests::test_scoped_load_filters_in_memory_snapshot_when_repository_has_no_scope_boundary` 使用禁止 `snapshot()` 的 service，证明撤回 scoped read 直接调用既有 `snapshot_for_row_ids(...)`，只复制目标 relation/history，不重建全量进程内状态。
- 本地 release gate：700 项定向 backend/deploy unittest、123 项 scoped Vitest、3 项 Chromium E2E、repository lint、docs gate 与 production build 全部通过。没有运行 pytest、完整 CI 或 183 项 Browser suite。

## 2026-07-29 - Phase 34 最终验证

- 最新后端根因修复的定向矩阵为 550 passed，覆盖 command adapter/service、pair relation service、write characterization、SQL runtime、鉴权/幂等、runtime boundary 与 relation repository。
- 前端 combined-initial in-flight 合并由 `web/src/test/WorkbenchApi.test.ts` 保护；本轮后端-only scoped snapshot 修复未新增重复 UI 测试。
- production release `main-632dd2aa-20260729153028` 的 Page Audit 为 `pass / fresh / drained`，issues 为空；20 次 gzip 样本的 combined initial、groups 首屏、confirm preview、withdraw preview、refresh status p95 分别为 `312.664/712.718/718.591/557.145/138.925ms`。

## 2026-07-30 - 详情 generation 一致性回归

- `tests/test_workbench_sql_runtime.py` 保护 active version 与 row detail 在一个只读 repeatable-read 快照内读取；详情缺失不得回退空的 group-member payload。
- 同文件保护健康 active generation 在相同 `source_versions` 下不重复发布；active consistency 失败时允许重建；任何可见非 summary row 缺少 `workbench_rows` 物化详情都必须在激活前失败，并进入 active consistency 报告。
- `web/src/test/WorkbenchSelection.test.tsx` 保护 OA、流水、发票共享的详情入口：遇到 generation version conflict 或 row miss 时，只等待一次 combined initial 刷新并重试一次详情请求；成功后安装新 generation 详情，失败则保留明确错误，不循环请求。
- 未运行无关完整 CI 或浏览器套件。未执行真实生产 confirm/withdraw mutation：现有 scenario 不是 test-owned 且缺完整恢复检查点，不能为了测速修改真实财务关系。

## 2026-08-03 - 两栏确认与 all-scope fan-out 回归

- `web/src/test/WorkbenchApi.test.ts` 保护后端 snake-case `unpaired_groups` 能映射为正式两栏 relation projection；`web/src/test/WorkbenchSelection.test.tsx` 让提交后的 generation 保持 refreshing，证明页面仍直接应用权威投影、关闭确认抽屉且不轮询 all-scope refresh status。
- `tests/test_workbench_sql_runtime.py` 直接实例化生产 `PostgresReadModelRepository`，保护 exact scope 去重、一次批量 active source-version 查询，以及 bulk 合同缺失时 fail closed、禁止旧 single-scope `all` proof。
- `tests/test_workbench_query_facade.py` 保护普通 all-scope stale 且已有 active generation 时返回零恢复 scope；只有明确缺少 active generation 的冷启动状态才允许保留 `all` fan-out。

## 2026-08-06 - visible self-convergence 与 writer 零通知

- Backend/API（历史记录）：旧 refresh-status/gateway/enqueue 合同已经退役；当前 `tests/test_workbench_direct_query_facade.py`、`tests/test_workbench_routes.py` 与 runtime boundary guards 保护 direct GET 零 enqueue、零 cache、零 fallback。
- Service/PostgreSQL：`tests/test_workbench_source_proof_contract.py` 覆盖所有 mutable Workbench dependency 的 writer→proof 变化、无关 scope 不变、bank-flow writer 零 dirty/outbox，以及既有 worker 原子发布新 generation 后 status 回到 fresh。
- Frontend：`web/src/test/WorkbenchSelection.test.tsx` 保护 visible entry/focus immediate、每次 settle+1000ms、hidden pause、single-flight，以及 changed fresh generation 只经既有 300ms debounce reload 一次。
- Browser：`web/e2e/bank-flow-rule-batches-flow.spec.ts` 保护 bank-flow 写响应零 Workbench target，并由持续可见关联台的 status→generation→业务 identity 链收敛；性能样本使用同一 Node monotonic clock，不能用 mock、混合时钟或最快样本替代 p99。

## 2026-08-07 - OA 行操作入口收口

- Backend：`tests/test_workbench_query_service.py` 与 `tests/test_workbench_exception_projection.py` 保护 paired/unpaired OA row 都只生成 `available_actions=['detail']`；银行流水和发票动作合同保持原测试覆盖。
- API mapping：`web/src/test/WorkbenchApi.test.ts` 向 paired/unpaired OA 注入旧 generation 的 `confirm_link`、`mark_exception`、`cancel_link`，验证映射后统一为 detail-only，避免发布必须等待 read model 全量重建。
- Component：`web/src/test/WorkbenchColumns.test.tsx` 保护 OA 栏无“操作”表头、无逐行“确认关联/异常处理”；同一用例继续保护银行流水和发票现有操作列。
- 性能/隔离：归一化是每行常数级数组替换，OA 栏减少一个固定列和逐行按钮 DOM；不新增 HTTP、数据库查询、read model、worker、queue、cache、轮询或跨页面 I/O。

## 2026-08-04 - OA 附件发票正式关系扩展回归

- `tests/test_oa_attachment_invoice_promotion_service.py` 保护一个费用项可绑定多张正式发票，promotion 写入时复用现有五个月 matching window，并证明 canonical invoice 与 durable dirty scope 在同一 PostgreSQL transaction 内提交。
- `tests/test_workbench_free_matching_engine.py` 保护已有 OA + 流水 active relation 能按明确 `attachment_source` 一次扩展全部 5 张发票；附件合计与 OA 相差 0.13 元时保留金额不一致，不丢附件、不改 case id。
- 同一 promotion service 的人工刷新回归进一步保护：canonical 发票已全部存在且 source link 不变时零 invoice write，但显式补发精确五个月 matching reconciliation；自动 OA sync 仍保持幂等零 dirty。
## 2026-08-10 视觉回归

- `web/src/test/ReconciliationWorkbenchPage.test.tsx` 继续保护关联台交互；共享对话框/抽屉与 token 由前端组件测试和 `DesignTokens.test.ts` 保护。
- `web/src/test/RelationGroupGrid.test.tsx` 保护同一三栏 DOM 在窄屏按 OA、银行流水、进销项发票纵向重排，1440px 级宽度下工具栏换行；不新增 API、read model 请求或第二份页面状态。

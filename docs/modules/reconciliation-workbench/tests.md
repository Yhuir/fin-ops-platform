# 关联台测试与验证

日期：2026-08-27

## 2026-08-27 paired / unpaired canonical 发票守恒统计

- Business/repository：`tests/test_workbench_page_query_repository.py` 保护两区 SQL 同时返回展示 `invoice` 和业务 `canonical_invoice`，无筛选统计直接按唯一 canonical ID 分区；paired owner 优先，未拥有者进入 unpaired，禁止 summary 与真实成员重复计数。
- PostgreSQL integration：`tests/test_workbench_query_postgres_integration.py::WorkbenchQueryPostgresIntegrationTests::test_direct_initial_and_groups_use_canonical_facts_without_read_model` 构造一个 summary 内含两张隐藏 canonical ETC 发票，断言展示发票数为 4、canonical 发票数为 5，并保护 paired + unpaired canonical 数等于统一发票池总数。
- API/frontend：`web/src/test/WorkbenchApi.test.ts` 保护 `canonical_invoice -> canonicalInvoice` DTO 映射及两区求和；`RelationGroupGrid.test.tsx` 保护发票栏标题消费 canonical 数，ETC 展开/收起仍只改变展示行；`WorkbenchZone.test.tsx` 保护分页 I/O 新字段不改变 `rows` 语义。
- 非适用：未修改数据库 schema、mutation、权限、read model、worker、queue、cache 或其它页面 API，因此不新增 migration、写事务/幂等、后台任务或跨页面数据修复测试。

## 2026-08-27 异常审阅人身份快照与 Popover 时间格式

- Service/repository/API：`tests/test_workbench_anomaly_review_service.py` 保护异常审阅只接收后端认证的 actor id/account/name，账户缺失 fail closed；持久化同时保留内部 actor id 与用户可见账户/姓名快照，幂等重复请求返回原审核人的快照和原审阅时间，不被后来点击者覆盖。compact/full 两条 direct hydration 都只发布 `reviewed_by_account/reviewed_by_name/reviewed_at`，旧 `reviewed_by` 用户可见字段已删除。
- PostgreSQL migration：`0156_backfill_workbench_anomaly_reviewer_identity.sql` 仅为缺少账户快照的历史异常审阅记录补齐唯一 `audit.events` 账户和最新非空姓名；映射缺失或同一内部 actor 出现多个账户时整笔迁移失败，既有 decision/version/updated_by/updated_at 与历史 audit 不重写，并追加一次可审计的 migration event。集成测试保护成功、幂等和歧义零部分写入。
- Frontend interaction：`WorkbenchAnomalyIndicator.test.tsx` 保护 Popover 显示 `YNSYLP007（杨丽萍）`、正常业务时区时间 `2026-08-25 17:03:47` 和可选备注，不再显示内部 `8` 或原始 `+08:00`。
- 性能与回归：写入只增加固定大小 JSON 快照；两条既有页面 SQL 在原 projection 内读取 JSON 字段，不增加 SQL、HTTP、read model、worker、cache、依赖或 N+1。七类金额异常、三类资料异常、分区、筛选、分页、确认/撤回与其它页面合同保持不变。

## 2026-08-26 ETC 折叠汇总、选择去重与误异常迁移

- Business core：`tests/test_workbench_amount_check_service.py` 保护 `batch_accounting + etc_invoice_summary` 不产生 OA 附件缺失/未解析/待归属资料异常，同时证明普通关系仍保留同样的真实异常；`web/src/test/WorkbenchSelectionModel.test.ts` 保护选择 ETC 关系后再勾选任意展开发票，正式成员数量和发票金额仍只计算一次。
- Formal matching 幂等：`tests/test_workbench_relation_command_service.py` 保护 deterministic 正式关系的新建与既有 case 扩展在完全相同计划重跑时都返回 `noop`，不刷新 relation、不追加 history；`tests/test_reversible_relation_closure_postgres.py` 在 disposable PostgreSQL 上证明仅 normalized `updated_at` 变化不会更新持久化时间，而真实 note 变化仍会落库。
- Repository/API：`tests/test_workbench_page_query_repository.py` 与 `tests/test_workbench_query_postgres_integration.py` 保护 compact payload 只有 canonical summary + 完整真实成员总数，detail 才返回全部真实发票；`web/src/test/WorkbenchApi.test.ts` 保护严格映射且验证 `formal_member_ids/formal_member_types` 等长、类型合法、身份唯一，非法合同 fail closed。
- Frontend interaction：`web/src/test/RelationGroupGrid.test.tsx` 保护折叠汇总、展开全量、收起恢复、详情加载失败及 canonical reload 后自动回到汇总；`web/src/test/WorkbenchSelection.test.tsx` 保护展示成员不进入统计或通用撤回 payload，银行规则批次仍走专用撤回链路。
- PostgreSQL migration：`tests/test_etc_summary_anomaly_review_migration_postgres_integration.py` 保护 0154 的历史 fingerprint/evidence 前镜像迁移；`tests/test_postgres_migrations.py` 锁定 0155 退役标记不得写业务或审阅数据，并由全 migration disposable PostgreSQL 验证可应用。
- 性能/回归：compact 查询 statement budget 不增加；正式选择为已加载组内线性 `Map/Set` 去重，不发新增请求。direct canonical SQL 的 all-scope active invoice owner 复用既有 relation-member CTE，发票来源只读取受 schema 约束的 canonical `source_links` 并一次生成来源标志，普通 groups 页只对可能从 base-paired 移区的关系计算 anomaly；异常页、initial、跨月 owner 和最终页面 hydration 继续保留完整事实集。普通 OA/流水/发票关系、真实待归属异常、银行批次专用撤回、详情查看和其它页面 API shape 保持不变。
- Read model/cache/worker：不适用。关联台继续 direct canonical PostgreSQL 读取，本次没有 projection、refresh、queue、worker 或缓存状态。

## 2026-08-26 OA + 外部往来完整闭环金额

- Business core / service：`tests/test_workbench_auth_context_idempotency.py` 覆盖 `200000 OA + 2×100000 收入 + 2×100000 支出` 的 preview/submit，断言同方向本金 `200000`、净额 `0`、差额 `0`、无需备注，并持久化 `turnover_manual_closure` evidence/history；单边外部往来选择继续走普通人工金额规则，结构化 action 缺失时 fail closed。
- Canonical query / performance：`tests/test_bank_details_canonical_query.py` 证明 Workbench 在既有一次批量分类查询中取得 turnover role/action/family，不增加逐行 I/O。

## 2026-08-25 三栏统一搜索展示字段对齐

- Repository/SQL：`tests/test_workbench_page_query_repository.py` 保护 unified search 显式覆盖 completed/in-progress OA 的申请人、展示项目、类型、费用类型、对方户名、事由、申请时间与付款项字段，流水的对方户名、时间、摘要、备注、方向和展示账户，以及发票的号码、销购方/税号、日期、金额、税率/税额、进销方向和 canonical 来源标签；内部 workflow no、project id、整段 raw/source payload 与隐藏 counterparty 字段不得重新进入搜索面。
- PostgreSQL integration：`tests/test_workbench_query_postgres_integration.py::WorkbenchQueryPostgresIntegrationTests::test_unified_search_covers_visible_oa_bank_and_invoice_columns` 在全 migration disposable PostgreSQL 上复现 completed OA `counterparty_name=张丽芬`，并逐项验证 OA 父项/子付款项、流水、发票字段命中后返回完整组；同文件 pending OA 用例同时保护进行中流程标签及其对方户名、事由和子付款项字段。
- Frontend：`groupDisplayModel.ts` 不再对浏览器当前已加载页执行第二套 search membership；输入 search 后由 zone direct API 唯一决定组命中，旧页在请求期间保持稳定，响应到达后保留服务端返回的完整 relation context。金额 canonicalize、高亮、列/时间筛选和排序仍走各自现役边界。
- 性能/边界：search 继续复用既有 `needed_keys` materialized 候选和一次 source-hit CTE；没有新增 SQL round-trip、API、索引、表、read model、worker、cache、依赖或数据库写入。

## 2026-08-25 OA 附件发票 current-item 展示分组

- Business core：`tests/test_workbench_relation_grouping.py` 保护 OA 附件发票只按 current canonical expense item 的精确 ownership 分组；历史 `row_index`、旧 alias 和金额相等均不能充当归属，`id / row_id / expense_item_id` 冲突时 fail closed。一个附件 occurrence 合法归属同一 OA 多个明细时保留全部精确分组，跨 OA 或无 current owner 时保持未归属。
- Repository / pagination：`tests/test_workbench_page_query_repository.py` 保护 current item owner 在搜索、筛选、分区、计数、游标和 `LIMIT` 之前由单条 set-based SQL 得出；目标详情先由目标 OA current items 发现 exact source-owned 发票月份，再沿有限月份集合水合，不增加逐行查询、full-scope spine 或 cache fallback。
- PostgreSQL E2E：`tests/test_workbench_query_postgres_integration.py::WorkbenchQueryPostgresIntegrationTests::test_oa_attachment_source_owner_groups_are_readable_and_formal_safe` 保护未配对 OA、流水和 OA 附件发票按 source owner 同行；`scope=all` source-owned detail 与 relation detail 完整携带跨月 display-only 发票。已有正式关系时，附件发票仍不进入正式成员、版本、完成度、异常、撤回或写操作。
- Query DTO / regression：`tests/test_workbench_query_service.py` 保护 expense item ID 只读取定义字段 `id / row_id / expense_item_id`，仅接受唯一一致非空值；source-owned 分组不改变既有 API DTO、正式 relation membership、confirm/withdraw 或其它页面链路。

## 2026-08-24 OA附件历史归属与来源标签回归

- Repository/SQL：`tests/test_workbench_page_query_repository.py` 保护 candidate 与 summary hydration 都读取 payload、owned item/attachment 和 active OA source alias，且页面热查询不扫描 attachment cache bridge；`tests/test_oa_projection_sql_runtime.py` 与 `tests/test_workbench_query_service.py` 保护 full/detail 的既有 row-id 查询在单条 statement 内携带同一 alias 集合；`tests/test_oa_attachment_invoice_linking.py` 以两个历史 parent 子付款项证明按 `row_index` 精确映射当前 canonical items。
- Frontend：`web/src/test/groupDisplayModel.test.ts` 与 `WorkbenchColumns.test.tsx` 保护 OA附件优先、人工导入其次、明细归属独立，以及旧“导入记录”Chip 不再出现；来源标签搜索由 direct repository 的 SQL/PostgreSQL integration 用例保护，Browser fanout/exception specs 保护主表和异常抽屉一致。
- Regression：不改变 API DTO、canonical `source_links[]`、relation membership、数据库 schema、read model、worker 或其它页面导入历史标签。

## 2026-08-23 补充凭证全局只读画廊

- Service/repository：`test_workbench_oa_supporting_document_service.py` 覆盖 active-only metadata page、稳定 `(created_at,id)` cursor、1～9 page size、列表不含二进制，以及 JPG/PNG/PDF 缩略图不改原文件；repository 测试锁定 keyset predicate、部分索引排序和 `limit=page_size+1`。
- API contract：`test_workbench_invoice_supplement_api.py` 覆盖 gallery shape、非法 page size、JPEG thumbnail、ETag/private immutable cache，并回归 scoped upload/list/content/delete。
- Frontend：`SupportingDocumentGalleryDrawer.test.tsx` 覆盖打开前零请求、九卡首屏、加载更多、同抽屉 PDF 预览和空状态；`ImportCenterPage.test.tsx` 覆盖 invoice-only 入口与 read-only 可见；`WorkbenchApi.test.ts` 覆盖 cursor/DTO mapper。
- Read model/worker：不适用。gallery GET 只读 owner repository/file store，不 enqueue、不访问 matching/read-model/worker/cache；migration 只新增 active 时间游标部分索引。
- Regression：现有 `WorkbenchInvoiceEntryDrawer.test.tsx` 继续保护补充凭证上传/删除和正式发票录入，`groupDisplayModel.test.ts` 继续保护当前 OA 明细内局部展示，没有删除现役 scoped 链路。

## 2026-08-22 relation invoice 显式 OA 明细归属

- Business core：`test_workbench_amount_check_service.py` 保护 relation 有 OA expense items 时，每张无有效 item edge 的 invoice 只产生一个 row-scoped `oa_invoice_attachment_unassigned`；不会按费用项重复，relation 没有 OA expense items 时不误报。`test_oa_attachment_invoice_linking.py` 继续保护显式 ownership 优先且旧附件来源保留。
- Service/API：`test_workbench_invoice_expense_item_assignment_service.py` 覆盖显式一对多 targets、零金额推断、stale item fingerprint、重复 target、缺 idempotency key、不同或 malformed 既有显式边冲突零写，以及 exact targets 幂等 no-op；`test_workbench_invoice_expense_item_assignment_api.py` 覆盖 actor/tenant/request、稳定 409/503 映射与 operation semantics。
- PostgreSQL/UoW：`test_workbench_query_postgres_integration.py::test_assign_invoice_expense_item_closes_document_only_anomaly_atomically` 保护 pending relation 从 unpaired 出发，写入保留旧来源、追加显式 edge、幂等 replay 只产生一次业务审计，并在下一次 canonical GET 消除该 document-only anomaly 后进入 paired；同文件继续锁定 SQL/Python fingerprint 与 no-expense-item 排除语义。
- Frontend：`WorkbenchInvoiceAssignmentDrawer.test.tsx`、`WorkbenchAnomalyIndicator.test.tsx`、`RelationGroupGrid.test.tsx` 和 `WorkbenchSelection.test.tsx` 保护 Popover 内唯一“选择 OA 明细”、抽屉默认零选择/显式多选、权限与错误态、一个 POST + 恰好一次 canonical GET、零本地挪行，并在回读后让 27.05 发票与所选 27.05 OA 明细同行、移除对应待归属感叹号；待归属链路全程不显示“录入发票”。
- Browser E2E / regression：`workbench-exception-flow.spec.ts` 保护异常抽屉先关闭再打开唯一归属抽屉；`workbench-relation-fanout.spec.ts` 保护真实浏览器中的 request DTO、单次回读、分区变化和 OA/发票同行。既有 confirm/withdraw、录票、七类金额异常、read-export 权限及跨页面回归继续执行。
- Read model/cache/worker：本 action 只复用现有 canonical UoW、source-links CAS 与 direct GET，没有 schema、read model、worker、queue、cache 或后台刷新；现有 runtime boundary guards 继续禁止 Workbench page runtime 回流。

## 2026-08-21 异常抽屉双视图与七分类唯一关系队列

- Business core / PostgreSQL：`test_workbench_query_postgres_integration.py` 构造七种金额分类各一个关系、一个同时含金额与资料异常的关系、一个含多个资料 item 的纯资料关系；保护 `amount_total=sum(by_code)`、`total=amount_total+document_only`、混合关系只进金额分类、纯资料关系只计一次，以及 SQL/Python fingerprint 与 paired/unpaired 分区一致。
- Repository / cursor：`test_workbench_page_query_repository.py` 与 `test_workbench_page_cursor.py` 保护同一 page SQL 返回完整七类零值、默认首个非零分类、显式零数量分类空页及 query-bound cursor。默认首屏未显式传 code 时，resolved code 被完整性校验地封存在 cursor；第二页继续省略 code 并强制复用原分类，即使最新首个非零分类已经变化。把自动 code 回填成新的显式 query 必须被拒绝。
- API contract：`test_workbench_routes.py`、`test_workbench_v2_api.py` 覆盖 `exception_view=amount|document_only` 与七类 `exception_code` 白名单、非法组合拒绝、route/server/facade 透传，以及 additive `selected_exception_code/exception_counts` 结构。
- Frontend component / interaction：`WorkbenchApi.test.ts`、`WorkbenchExceptionDrawer.test.tsx`、`WorkbenchSelection.test.tsx` 覆盖 URL/DTO 映射、两类视图、七分类数量、空分类、切换时 latest-wins、默认分类 cursor 续读不回填 code、bucket 总数不被当前分类 `page.total` 覆盖，以及抽屉内仅开放具备权限的既有“录入发票”动作。
- Browser E2E：`workbench-exception-flow.spec.ts` 保护首开金额分类、游标加载更多仍省略自动 code、切换仅资料视图、录票前关闭异常抽屉，以及既有 accept/keep/withdraw、Popover 和响应式链路。
- Regression：旧 WEX/row-ignore、人工分类字段和已退役 ignore/restore routes 继续不能进入新 counts、bucket 或 marker；personal advance settlement 等仍有现行消费者的 exception repository 能力保持不变，不做误删。
- 性能：`http_slo_probe.py` 默认加入未配对金额、未配对仅资料和已配对金额三个认证只读 probe；每个 probe 继续服从 p95 `<=1000ms`、p99 `<=2000ms`、错误为零。新筛选不增加 schema、read model、cache、worker、队列或逐组 SQL。

## 2026-08-21 自动异常分类、感叹号定位与审阅闭环

- Business core：`test_workbench_amount_check_service.py` 覆盖七种互斥三栏分类、分精度、净额/外部往来本金、方向未知/冲突不猜测、局部差异不生成第八类，以及附件缺失/未解析/待归属；精确单行与歧义 group scope 均有断言。
- Service/repository/API：`test_workbench_anomaly_review_service.py` 保护服务端重取 canonical bundle 并自行持久化 evidence fingerprints/detected codes，忽略客户端旧人工字段；fingerprint、其他 blocker、跨月 scope、幂等和审计不变。`WorkbenchApi.test.ts` 保护 review request 不再发送人工分类或逐项 fingerprints。
- Frontend interaction：`WorkbenchAnomalyIndicator.test.tsx`、`WorkbenchExceptionDrawer.test.tsx`、`RelationGroupGrid.test.tsx` 保护主表/抽屉复用同一三栏定位，默认只显示感叹号；hover/键盘 focus 临时打开，显示时首次点击关闭且当前停留期间不自动重开，再次点击持续打开，离开后恢复下一次 hover；无先行 hover 的鼠标/触屏式点击也能独立开关。Popover 只展示 HeroUI Chip；折叠态不新增栏，展开态无重复 Chip、复选框或人工下拉，只读权限无 mutation。
- E2E/regression：`workbench-exception-flow.spec.ts` 保护自动分类的接受、目标 bucket 单次重读、撤回及 1440/1024px 边界；权限套件保护 read-export/App Health blocked 下证据可见且零写入。`WorkbenchSelection.test.tsx` 保护写成功但重读失败不重复提交。
- 性能与边界：分类为现有 group 内固定规模纯计算，前端定位为单次 Map/Set 遍历；未新增 API round-trip、逐行 I/O、表、migration、read model、worker、cache 或依赖。PostgreSQL candidate 仍在分页前用三栏总额、成员和附件状态计算 review fingerprint，但不再为全量关系递归构建费用项—发票连通分量；该图只在已分页的当前组内存中用于感叹号定位。PostgreSQL integration 同时保护 SQL/Python fingerprint 一致、旧递归 CTE 缺席和 summary/detail 分区一致。
- 旧链删除：删除 `workbench_exception_classifier.py` 及其测试、客户端人工分类/逐项审阅状态、请求字段和旧 CSS；dead-code guard 将旧 classifier 列为禁止恢复模块。

## 2026-08-20 大批量确认/撤回与旧上下文扫描删除

- Query/service：30/100/500 条 typed selection 必须完整到达 canonical repository；空输入、类型错位、重复 typed identity 与 unsupported type 仍 fail closed。500 是测试样本，不是业务上限。
- Repository：500 条 selected rows 从正式 group descriptor 一次水合，OA `source_links` 附件扫描为零；同组 context 只来自正式 relation descriptor，不从页面 payload 或旧 helper 猜测。
- Business core：100 成员 formal relation 覆盖 confirm、preview、exact-set withdraw、confirm/withdraw idempotent replay 和撤回后 active state 清空。
- Frontend/E2E：500 成员 selection model/API payload 不截断；Chromium 场景加载并选择 30 条后只发一次 confirm preview，`row_ids`/`row_types` 均为 30。
- Dead-code guard：`WorkbenchWriteFacade` 构造参数和 `Application` 不再暴露 confirm context expansion；孤立 read port/index/module/test 已删除，whole-repo runtime symbol scan 必须为零。

## 2026-08-20 submitted ETC summary 正式成员闭环

- Business/service：`tests/test_workbench_matching_orchestrator.py` 保护新建关系与已有 OA/流水关系都加入精确 `etc-summary-*` invoice member；历史关系替换保留金额检查和差额说明，summary 已属于其它 active relation 时零写 fail closed；延迟 OA 申请月份会在 fact load 前并入同次 scope。
- Repository/API contract：`tests/test_workbench_formal_relation_repository.py` 保护 exact ETC marker 候选不按 OA 申请日期误过滤，并输出 ETC 月份与 OA 申请月份；`tests/test_workbench_relation_repository.py` 保护只有 submitted/closed 且拥有真实 ETC 发票成员的 summary 才能通过 canonical lock。
- Real PostgreSQL：`tests/test_workbench_pending_oa_relation_lock_postgres_integration.py` 证明 OA、流水和 submitted ETC summary 可在一个事务形成正式关系；`tests/test_workbench_query_postgres_integration.py` 继续保护 direct initial/groups/detail 与 68 张批次展示。
- Unpaired detail：`tests/test_workbench_query_postgres_integration.py::test_unpaired_submitted_etc_summary_detail_hydrates_all_invoices` 构造无 OA/流水、无 active relation 的 49 张 submitted ETC 批次，保护列表 `detail_key` 可由同一权威 summary identity 精确定位；详情必须返回 49 张唯一 `etc_invoice`，不得返回 404 或混入 summary 占位行。
- Audit/regression：`tests/test_workbench_page_audit.py` 区分缺 OA、缺 relation 和 metadata-only/member-missing 三类 warning；不新增前端交互、HTTP shape、表、worker、read model 或 cache。
- Repair regression：`tests/test_workbench_etc_summary_relation_repair_ops.py` 覆盖 metadata-only 历史关系补 member、fingerprint 漂移拒绝、幂等和 rollback；`tests/test_workbench_page_audit.py` 锁定 v29 的 historical relation-case OA 证明条件。

## 2026-08-19 ETC 68 张部分桥接回归

- PostgreSQL integration：`tests/test_workbench_query_postgres_integration.py::WorkbenchQueryPostgresIntegrationTests::test_page_etc_hydration_is_one_statement_and_matches_legacy_dto` 构造同批 canonical link、重复 business row、未桥接 business row 与 legacy submission，断言现代层逐票去重后保留完整 2 张/33 元，link 覆盖同票、legacy 不混入，page/detail DTO 一致。
- Business anomaly：同一 fixture 让 OA、银行流水与 ETC summary 都为 33 元，证明异常 SQL 使用相同现代来源集合，不再因部分桥接产生 OA/流水—发票金额误报。
- Audit：`tests/test_workbench_page_audit.py` 保护 submitted business 与现代合并集的数量/金额 parity warning；audit 为独立只读查询，不进入页面热路径。
- Regression/performance：旧批次级 source 选择和 Python skip 已删除；关联台仍使用一个 set-based hydration statement，无 API/schema/read model/worker/cache 变化。

## 2026-08-19 外部往来闭环、已接受异常与历史来源修复

- Business core：`tests/test_workbench_amount_check_service.py` 保护 `turnover_manual_closure` 的 240000 收入 + 240000 支出闭环以付款本金侧和 OA 240000 比较且不误报，同时真实本金差异继续生成异常；普通付款关系仍使用支出减退款收入的净额。
- Service/repository：`tests/test_workbench_relation_grouping.py` 继续保护 relation mode 传入统一金额判断；该轮曾要求 `accept_paired` Chip 增加 `已接受：` 前缀，此展示合同已由 2026-08-21 顶部口径取代，现改为原异常 Chip 与审阅信息分离。`test_invoice_expense_item_link_repair_service.py` 与 `test_postgres_repositories_core.py` 保护历史发票来源修复的精确 identity/总额、冲突拒绝、幂等、rollback manifest 和旧 `source_links` CAS。
- Tool/audit：`test_import_audit_repair_ops.py` 保护 dry-run 零写；生产执行必须使用 dry-run 指纹、serializable transaction、advisory lock、operator/reason 和 `ops.operation_events` 审计，禁止直接 SQL 或页面 fallback。
- Frontend：`WorkbenchApi.test.ts` 保护审阅元数据映射，`RelationGroupGrid.test.tsx` 与 `groupDisplayModel.test.ts` 保护“未解析 + 录入发票”跨整栏 HeroUI 状态操作区且无占位横杠；其它页面 API、read model、worker、cache 和依赖均不变。

## 2026-08-18 异常审阅决定与 direct candidate fingerprint 一致性

- Repository/SQL：生产形态 PostgreSQL fixture 保护 OA 费用项对发票金额异常的 fingerprint 与 Python `WorkbenchAmountCheckService` 完全一致；`accept_paired` 后 initial、groups summary/full 与 group detail 必须同时进入 paired，不能触发 candidate/hydration zone disagreement。
- Hydration/performance：compact 与 full/detail 都按 relation group 选最新决定并执行相同 relation freshness；full/detail 只读取当前可见 relation 的决定，删除 `WorkbenchCanonicalRowsBuilder` 对 month/all 全范围异常决定的隐式 fallback，不增加 SQL statement budget、read model、cache、worker、schema 或跨页面 I/O。
- Regression：旧 fingerprint 在 relation 输入更新时间变化后继续失效；zone 一致性 fail-fast 保留，不以吞错、强制改区或兼容分支掩盖 SQL/Python 漂移。

## 2026-08-16 异常抽屉紧凑布局回归（审阅控件合同已于 2026-08-21 替代）

- Frontend interaction：该轮曾保护折叠/展开布局；其中逐项复选、人工金额判断和直接平铺 Chip 已在 2026-08-21 删除，现行合同见本文件顶部。
- Browser E2E：`workbench-exception-flow.spec.ts` 保护 1440px 与 1024px 视口内抽屉和审阅区不越界，详情仍按点击惰性加载，accept/withdraw 后 bucket 重置为折叠态且链路仍只执行既有 API。
- 非适用：本轮不改变业务金额判断、API DTO、repository、数据库、read model、worker、cache、权限或其它页面 I/O，因此不新增后端、迁移或跨页面数据测试；既有异常 Browser 主链和全量前端回归承担隔离验证。

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
- Frontend interaction：`WorkbenchSelection.test.tsx` / `WorkbenchZone.test.tsx` 保护关系确认/撤回；`WorkbenchExceptionDrawer.test.tsx` 保护 `未配对异常 n | 已配对异常 m`、服务端证据 accept/keep/撤回、感叹号 Popover 和只读权限。旧逐项审阅合同已由本文件顶部 2026-08-21 口径取代。
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
- Frontend：`WorkbenchSelection.test.tsx` 与 `WorkbenchExceptionDrawer.test.tsx` 保护单 bucket 有界读取、服务端分类决定、接受异常、留在未配对、撤回与主区 canonical refetch。
- E2E / regression：`workbench-exception-flow.spec.ts` 保护异常默认未配对、接受风险进入已配对、撤回同步返回未配对；权限套件验证 read-export 零 mutation。没有增加表、worker、queue、cache owner、依赖或并行 fallback。

## 2026-08-05 OA/发票比较单元与附件缺失异常

- Business core：`tests/test_workbench_amount_check_service.py` 保护日常报销逐 `source_expense_item_id` 比较全部显式绑定发票，覆盖 `290=145+145`、`405=350+55`、一项多发票差异只生成一个 anomaly item、无附件/附件未解析/待归属三类状态，以及“唯一单票落发票、一项多票落 OA 子项、组级流水—发票差异落流水而不误贴 55 元发票”；支付申请继续按关系组总额比较，缺金额不误报。
- Service/API：`tests/test_workbench_relation_grouping.py` 保护 `workbench_anomaly.items[]` 和具体 pair chip；`tests/test_workbench_anomaly_review_service.py` 保护 exact item review、stale fingerprint、其他 blocker 与新 API；PostgreSQL integration 保护异常桶在分页前过滤及 SQL/Python fingerprint 一致。
- Frontend：`groupDisplayModel.test.ts` 保护显式 ownership 与金额判断解耦、组合发票同行和附件占位；`WorkbenchApi.test.ts` 保护统一 anomaly DTO；抽屉/页面测试保护感叹号 Popover、两个异常 bucket、服务端证据流转与只读行为。旧逐项审阅合同已由本文件顶部 2026-08-21 口径取代。

## 2026-08-15 退款净额、历史附件归一与人工金额分类（人工分类已于 2026-08-21 删除）

- Business core：`tests/test_workbench_amount_check_service.py` 保护付款关系按同 relation 的 `1050 支出 - 35 退款收入 = 1015` 与 OA/五张发票 `1015` 比较，三种金额异常均为空；`tests/test_oa_attachment_invoice_linking.py` 保护历史 OA 子项 ID 通过唯一 parent + row index 归一，使 `350` 子付款项与 `150+100+100` 三张发票同带，歧义来源保持 fail closed。
- Service/API：净额与历史附件归一合同继续有效；旧 allowlist 人工分类与 `review_classification_codes[]` DTO 已删除，现由服务端持久化 detected codes/evidence fingerprints。
- Frontend：旧金额下拉、逐项复选和 `无异常` 人工覆盖已删除；现行自动分类交互见本文件顶部。仍未新增 table、migration、read model、worker、queue、cache、逐行 I/O 或依赖。

## 2026-08-15 OA附件发票多对多与子付款项定位

- Business/service：`test_mongo_oa_adapter.py` 保护同一物理附件跨两个子付款项只解析一次、再分别绑定来源；`test_oa_attachment_invoice_promotion_service.py` 与 `test_import_service.py` 保护同 OA 多来源边不丢失；`test_workbench_amount_check_service.py` 和 `test_workbench_relation_grouping.py` 保护 `18+18=36` 不重复计票、一个 item 多票集合求和，以及缺失/解析失败/待归属分类。
- API/frontend：Workbench DTO 只发布复数 canonical `source_expense_item_ids[]` / anomaly source arrays，前端不把历史 `source_links[].source_expense_item_id` 混入展示 identity；`WorkbenchApi.test.ts`、`groupDisplayModel.test.ts`、`RelationGroupGrid.test.tsx` 保护 145 元高铁票与唯一子付款项同带且不生成缺失占位、一票多项只渲染一次、多票一项同带、待归属 OA 附件不按金额兜底且不进入父摘要。`WorkbenchExceptionDrawer.test.tsx` 保护缺失 chip 使用 `target=_blank` 与 `noopener noreferrer` 打开稳定 OA 列表路由。
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

## 2026-08-20 ETC 批次折叠、搜索、计数与关系缺口审计

- Business/repository：`tests/test_workbench_page_query_repository.py` 保护发票统计直接复用 canonical invoice facts，只输出总数、进项、销项、人工导入和 OA 解析新增入池，并确保旧 `invoice_inventory` / ETC 展示诊断统计不回流；同文件继续保护搜索命中 external/business/submission batch ID、成员发票号和精确金额，并让 compact summary 只携带 canonical ETC `summary_row` 与完整真实成员总数；`tests/test_workbench_query_postgres_integration.py` 在真实 PostgreSQL 上保护分页快速水合从部分 link + business 完整成员中稳定物化汇总行、声明完整折叠数量，且 statement budget 不增加。
- Audit：`tests/test_workbench_page_audit.py` 保护缺 OA 与缺 active relation 的 submitted ETC batch 分别输出稳定 warning code，既有无效 relation member 仍为 error。
- Frontend：`web/src/test/RelationGroupGrid.test.tsx` 保护折叠态只显示 `summaryRow`、不显示任何真实发票；展开态只显示全部 N 张 `collapsedRows`，收起恢复同一汇总行。缺少 `summaryRow` 时显示明确空态，禁止以 `rows[0]`、第一张真实发票或 `slice(0, 1)` 兜底。
- 性能：首屏不携带全部 ETC 发票，成员发票号仅在用户搜索时通过有界 `exists` 查询；不新增 API、SQL round-trip、表、worker、read model、cache 或第二套展开状态。

## 2026-07-28 逐栏折叠、普通行直显与搜索真实预览

- Business core：`no_oa_bank_batch` 与普通关系保留全部真实行；`bank_flow_rule_batch` 只有银行成员数 `>3` 才生成银行栏 summary/collapsed rows，1 到 3 行直接显示；ETC 仍只折叠发票栏。
- Repository/read model：summary page 不再把普通银行/发票行截成 3 行；折叠栏传 canonical summary + count，ETC 发票栏同样只传汇总行，不把第一张真实发票混入首屏。搜索只决定组命中、不自动展开全部 collapsed rows。ETC business batch 即使只有部分成员已建立严格 link，折叠汇总仍保留完整 `invoice_ids` 成员并按发票身份去重。schema v12 淘汰旧 generation/page cache，并统一 ETC relation proof，不新增表、worker、cache 或 API。
- API/Frontend：group detail 按 `collapsed_row_counts.<pane>` 逐栏验证；ETC 的 OA/银行栏验证正常 rows，发票栏验证 collapsed rows。闭合态搜索只保留命中组并渲染 summary，不显示折叠成员或“隐藏内容命中”，也不自动展开或预取详情。
- Regression：普通多行与 legacy no-OA 不出现通用“还有 N 条，展开”；bank-flow 与 ETC 保留 click-only detail、失败可重试和同 generation fail-closed。

## 2026-07-28 日常报销付款明细复合行

- Backend/API：`tests/test_workbench_query_service.py` 保护父 OA 行只发布精简稳定付款明细字段，附件发票继续携带显式 `source_expense_item_id`；不新增 relation member 或独立配对对象。
- Frontend：`web/src/test/WorkbenchApi.test.ts` 保护 item/source ID DTO；`WorkbenchColumns.test.tsx` 保护申请类型移入申请人栏并清理项目栏 process/evidence chip；`RelationGroupGrid.test.tsx` 保护“多个项目 · N + 父 OA 金额”、逐项项目/金额、单条精确金额才同行、部分精确覆盖与残余发票独立展示，以及点击子项仍只选择父 OA。
- Frontend display：`groupDisplayModel.test.ts` 以 `174.94 = 78.34 + 12.00 + 28.80 + 55.80` 的生产形状保护显式发票逐付款项同行、父 OA 级银行流水不参与子项分段，以及未解析项只保留 `OA发票附件未解析 + 录入发票`；`RelationGroupGrid.test.tsx` 保护该父级流水复用既有整栏 CSS grid 跨越全部展开行。

## 2026-08-18 OA 附件处置、多发票录入与防误导显示目标

- Business core / service：`tests/test_manual_invoice_entry_service.py` 保护一个 session 多张发票、同批重复整批拒绝及 PNG 识别入口；`tests/test_workbench_invoice_supplement_service.py` 保护全部 file ids、canonical source link、现有 case 扩展以及 relation 失败时 import runtime 回滚；`tests/test_workbench_oa_supporting_document_service.py` 保护 JPG/JPEG/PNG/PDF 签名、内容哈希重试幂等、精确 OA 子付款项归属、预览与删除且不写发票池。
- API contract：`tests/test_import_file_api.py` 保护 `invoices[] / values[] / file_ids[]`；`tests/test_workbench_invoice_supplement_api.py` 保护手工整批关联和补充凭证上传/列表/内容/删除 DTO；`tests/test_operation_history_semantics.py` 保护三种写操作的审计语义。
- Frontend：`ManualInvoiceEntryDrawer.test.tsx` 保护“预览/保存信息”只保存本地编辑态、最后一次整批入池及拖拽 PNG 识别；`WorkbenchInvoiceEntryDrawer.test.tsx` 保护 HeroUI 单抽屉两种内部页面、JPG/PNG/PDF 拖拽上传、精确 target 透传与明确错误；`WorkbenchApi.test.ts`、`groupDisplayModel.test.ts`、`RelationGroupGrid.test.tsx` 保护显示目标、补充凭证局部更新和录入入口。
- Regression / performance：普通发票文件导入继续走原 durable confirm job；关联台 direct page GET 在已读取的 OA 子项 JSON 上附加索引查询得到的补充凭证，summary hydration 保持原窄字段投影，抽屉列表 API 只按 OA 子付款项索引读取，不引入 worker、read model、Redis 或全表投影。补充凭证写入后直接局部更新目标子付款项，只有 canonical 手工发票提交才执行关联台 post-commit 重读。生产使用既有 HTTP SLO probe 与 runtime closure gate 验证。
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
- `tests/test_workbench_invoice_expense_item_assignment_service.py`
- `tests/test_workbench_invoice_expense_item_assignment_api.py`
- `tests/test_postgres_migrations.py`
- `web/src/test/RelationGroupGrid.test.tsx`
- `web/src/test/WorkbenchApi.test.ts`
- `web/src/test/WorkbenchInvoiceAssignmentDrawer.test.tsx`
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
- relation 有 OA expense items 时，每张无有效 item edge 的 relation invoice 恰好生成一个行级待归属异常并保持 unpaired；relation 没有 OA expense items 时不得误报。显式归属只接受同一 active case 的真实 OA item，默认零选择且禁止金额推断；不同或 malformed 旧显式边不得覆盖。成功只追加来源边，前端以一次 canonical 回读决定同行、异常与分区。
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

## 2026-08-15 显式父 OA 银行流水复合同行

- Business/display core：`groupDisplayModel.test.ts` 保护普通父 OA 下多条 canonical `sourceOaId` 流水在合计按分等于 OA 时共享复合行轨；金额不等时继续进入 OA 局部残余带。既有无来源金额组合测试继续证明 `64996.69 + 23053.31 = 88050.00` 本身不足以建立同行。
- Frontend interaction：`RelationGroupGrid.test.tsx` 保护 OA 只渲染一次、两条显式来源流水在同一银行 pane 内各渲染一次、对应 residual 不存在，旁侧单条精确 OA/流水仍保持原行为。
- Browser/production：复用既有多行 segment/Flex 渲染和生产 `CASE-AUTO-0016` 只读几何验证；不新增 API、状态、请求、DOM 测量、read model、worker、cache、数据库对象或依赖。
- Performance：布局继续只消费已加载 DTO 并使用现有 source segment 与一次金额求和，复杂度保持 `O(OA + bank + invoice)`；不恢复 subset-sum、日期、顺序或名称推断。

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

## 2026-08-19 - combined initial 统计热路径回归

- `tests/test_workbench_page_query_repository.py::test_initial_page_uses_one_shared_candidate_spine_and_one_combined_hydration` 保护组级 summary 不再 join `canonical_group_members`、不再执行 `count(distinct groups.internal_key)`；成员只先按 `(row_type, row_id)` 物化一次，默认 paired/unpaired 精确行数和组总数复用该统计事实，防止性能修复改变计数合同。
- `tests/test_workbench_query_postgres_integration.py` 必须在 disposable PostgreSQL 上全量通过，证明拆分后的 CTE 可真实解析执行，initial/groups/detail 与 ETC 部分桥接 68 张恢复链路保持一致。

## 2026-08-20 - 附件异常审阅分区回归

- `tests/test_workbench_query_postgres_integration.py::WorkbenchQueryPostgresIntegrationTests::test_anomaly_state_is_sql_compact_fingerprint_parity_and_keyset_bounded` 在真实 PostgreSQL 中同时构造“无 OA 附件”和三栏金额差异，验证 SQL/Python 指纹一致；服务端证据审阅后 combined initial 与 paired/unpaired groups 必须稳定分区且不返回 500。

## 2026-08-20 - 手工发票补足 OA 子付款项来源回归

- `tests/test_workbench_amount_check_service.py::WorkbenchAmountCheckServiceTests::test_manual_invoice_binding_satisfies_zero_attachment_evidence` 保护 OA 原附件数为零但已有精确子付款项发票归属时不再生成“无OA附件”；OA—流水和 OA—发票的真实金额差异仍保留。
- `tests/test_workbench_page_query_repository.py::test_compact_hydration_exposes_the_same_external_oa_identity_aliases` 锁住 compact summary SQL 同时承载 `oa_attachment_invoice` 与 `oa_expense_item_invoice`，禁止恢复只保留原附件来源的旧过滤。
- `tests/test_workbench_query_postgres_integration.py::WorkbenchQueryPostgresIntegrationTests::test_manual_expense_item_invoices_satisfy_missing_attachment_evidence` 在 disposable PostgreSQL 中构造生产同形 OA、流水和多张手工发票关系，验证 summary hydration 输出精确来源、OA 原附件数保持零且仅保留真实金额异常。

## 2026-08-21 - 补充凭证分页装配回归

- `tests/test_workbench_page_query_repository.py::test_canonical_spine_defers_supporting_documents_to_page_hydration` 保护全量 anomaly candidate 不得重新扫描补充凭证表，同时保留完成态和进行中 OA 的原始费用项数组。
- `tests/test_workbench_query_postgres_integration.py` 全量在 disposable PostgreSQL 运行，保护 initial/groups/detail、附件异常指纹以及已审阅 paired/unpaired 分区仍能真实解析并执行。

## 2026-08-21 - Filter-options 候选与窄 DTO 回归

- unit SQL-shape 与 disposable PostgreSQL 回归共同保护窄成员投影、typed anomaly rehydrate、paired→unpaired 候选、未知类型/流程、空申请人，以及附件 absent/unparsed/unassigned、显式费用项归属和已接受指纹语义。

## 2026-08-21 - 三栏详情触发器视觉与链路回归

- `web/src/test/WorkbenchColumns.test.tsx` 保护 OA、银行流水和发票只使用共享的透明 `workbench-detail-trigger`，不再继承旧 `.row-action-btn` 方框样式、原生 `title` 或重复文本详情入口；`WorkbenchSelection.test.tsx` 继续保护按钮位于首行、点击不触发行选择且复用既有详情抽屉。
- `web/e2e/workbench-large-scroll-flow.spec.ts` 在 Chromium 中检查三类按钮均为 28px、透明背景、零边框、零阴影，hover 显示 HeroUI Tooltip、键盘焦点显示 2px 可见轮廓且交互前后几何不变；逐一打开三类详情时每类恰好一次现有 GET、零 Workbench 写请求、零选择副作用，抽屉壳在页面内单调时钟下 `<100ms` 出现。
- 该改动不改变 API response shape、权限、数据库、direct repository、read model、worker 或跨页面 I/O；业务核心、service、API、cache/worker 测试不适用，既有三栏、汇总行和详情错误态回归继续执行。

## 2026-08-21 - 发票强身份复用、关系确认与后台回读闭环

- Business core / service：`test_manual_invoice_entry_service.py` 保护普通手工预览继续拒绝 duplicate，Workbench 专用预览只允许强身份唯一既有票并拒绝 suspected duplicate；`test_workbench_invoice_supplement_service.py` 保护既有 27.05 canonical invoice 不重复创建、历史 attachment 来源保留、显式 expense-item 来源追加且关系在同一事务扩展。
- API contract：`test_workbench_invoice_supplement_api.py` 与 `WorkbenchApi.test.ts` 保护专用 preview endpoint、完整 session/file target 透传和原全局导入 endpoint 不变；`WorkbenchInvoiceEntryDrawer.test.tsx` 保护抽屉默认进入发票录入，补充凭证降为次级且不预加载其列表。
- Read/SQL parity：`test_oa_attachment_invoice_linking.py`、`test_workbench_amount_check_service.py` 和 `test_workbench_query_postgres_integration.py` 保护显式 `oa_expense_item_invoice` 优先于历史 attachment 归属，SQL/Python hydration 对齐，目标付款项不再显示附件异常和录入按钮。
- Relation/UoW：`test_workbench_pair_relation_service.py`、`test_workbench_relation_command_service.py`、`test_workbench_uow_contract.py`、repository adapter tests 与 `test_workbench_write_characterization.py` 保护已有 immutable OA+invoice 加入流水时保留 formal/binding metadata，差额 note 提交成功，数据库 commit 后才发布 runtime delta，回滚不留半写。
- Frontend interaction：`WorkbenchSelection.test.tsx` 保护 OA 状态变化发生在多选、preview request/drawer 或发票编辑期间时不清空用户交互；响应落地前再次检查竞态，全部交互结束后只补一次 canonical GET，post-commit 写成功仍只做一次强制回读。
- Existing regression / performance：发票全局导入、补充凭证文件链、普通相等确认、withdraw、异常七分类、筛选分页与权限合同不变；所有新增处理均为固定项或当前页/当前关系有界操作，没有轮询加速、额外列表 N+1、read model、worker、Redis 或数据库 schema 变化。

## 2026-08-24 - 进行中 OA 自动正式关系闭环

- Business core / repository：`tests/test_workbench_formal_relation_repository.py` 保护 in-progress payment OA 与强证据流水进入同一 fact batch，并生成唯一 `strong_evidence_exact_closure`；可选日期占位值回退权威日期，权威日期无效时按 row id fail closed。
- Service / transaction：`tests/test_oa_pending_payment_source_snapshot_repository.py` 保护 admission/completed OA 匹配相关变化与 matching dirty scope 同事务提交，队列写失败整体回滚，payment-status-only 更新零 matching I/O。
- App Health regression：`tests/test_app_health_alert_service.py`、`tests/test_app_status_overview_service.py` 保护 failed scope 显式告警、stale matching 不再显示 Workbench ready，同时不设置全局写门禁。
- API/UI/Read model 不适用：本次不改变 HTTP response shape、页面组件或页面 read model；既有 Workbench direct API、OA pending API 和页面回归继续保护其它页面链路。

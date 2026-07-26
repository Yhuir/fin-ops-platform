# 待找发票测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 2026-07-27 - 页面 canonical PostgreSQL 直读迁移

- 变更类型：删除 `/pending-invoices` 页面 read-model gate/refresh/polling/fallback，改为页面专属 canonical query service/repository。
- 业务核心（适用）：`tests/test_pending_invoice_canonical_query.py` 覆盖 direction/filter/date/filter DSL/sort/page 非法输入、空集、状态 DTO 校验、候选去重和金额合同；既有 `tests/test_pending_invoice_service.py` 保护规则优先级、支出/收入/现金收入、无需开票、冲突、幂等与 CAS。
- Service/repository（适用）：覆盖一个 `REPEATABLE READ / READ ONLY` snapshot、rows 固定两次 SELECT、候选固定有界查询、canonical tables、active relation、`turnover_manual_closure` 排除、服务端分页和 export row limit。
- API contract（适用）：`tests/test_pending_invoice_api.py` 覆盖权限拒绝、非法参数、空集、rows/summary/statistics/filter-options、详情/候选/导出、规则/关联/收入状态写入与写后 GET；断言不再出现 `read_model_status/source_versions`，旧 read-model miss 不 gate/enqueue。
- Read model/worker cleanup（适用）：静态 SQL contract 禁止四类 read model；前端测试断言不展示状态且不轮询。共享 Search/invoice-lifecycle/relation worker 尚有其它调用方，删除交主控 HANDOFF，因此本分支不修改其测试。
- Frontend interaction（适用）：`PendingInvoicesPage.test.tsx` 覆盖 loading/empty/error、筛选、排序、分页、抽屉、候选、批量写、写后 refetch、导出禁用和无 polling。
- E2E（适用）：`web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts` 改为直读契约回归，覆盖无 read-model diagnostics、无 polling 和真实空集；既有 `web/e2e/pending-invoices-*.spec.ts` 继续保护写后重读等关键浏览器流程。
- 范围外回归（适用）：运行 pending invoice service/API 及 Search SQL runtime 相关测试，确认 Search API 和共享 lifecycle/relation 链路未被删除或改写。
- 性能 guard：SQL template 必须包含 `LIMIT/OFFSET` 且不得出现 forbidden read-model schema；真实 50,003 canonical bank rows 记录 rows 50/200 的五次端点耗时，不用 cache 或新索引掩盖。

> 下列 2026-07-27 之前的日期段落和历史 bug 回归库记录当时的 read-model 架构事实，不是当前页面运行时合同；当前合同以本节、`README.md` 和 `boundary-io.md` 为准。

## 2026-07-22 - Phase 27 访问时收敛

- 变更类型：删除 import/runtime 写后 pending-invoice scope fan-out。
- 新增/更新测试：write-operation impact/SLO、pending-invoice API/read-model、import processing 与 architecture guards。
- 覆盖点：规则、关联、income status 与 import confirm 只提交 facts/version/hints，targets 为空；当前页面 GET 只 enqueue 当前精确 direction/month scope。`pending_invoice_scope_planner.py` 已删除并由静态 guard 防回归。
- 验证命令：见 Phase 27 verification。

## 2026-07-23 - filter-options source-version 热路径收敛

- 变更类型：只读 freshness/source-version SQL 性能修复，不改变 API shape、scope、worker 或业务口径。
- 新增/更新测试：`test_filter_options_fresh_gate_skips_unused_page_statistics`、`test_pending_invoice_repository_loads_workbench_relation_source_versions_for_matching_months`。
- 覆盖点：filter-options freshness gate 显式 `include_statistics=false`；全部命中月份的 `workbench_pair_relations` count/max(updated_at) 在一次批量 SQL 中返回，禁止恢复逐月 `fetch_one` N+1；每月 source-version payload shape 保持不变。
- 验证命令：见 Phase 27 最终 verification 与生产 SLO 证据。

## 2026-07-25 - rows 请求内 settings I/O 去重

- 变更类型：只读请求热路径性能修复，不改变 API shape、read-model scope、worker 或业务口径。
- 新增/更新测试：`test_pending_invoice_source_provider_reuses_request_settings_payload`、`test_pending_invoice_rows_loads_settings_once_for_all_request_consumers`、`test_normalize_row_payloads_uses_request_scoped_settings_without_reloading`。
- 覆盖点：同一 rows 请求的 statistics、当前 scope source proof、bank tags 和银行账号名称归一复用同一个 settings payload；禁止恢复多次 `get_settings_payload()`，避免一个请求重复执行设置 repository 查询。

## 2026-07-05 - pending invoice boundary close

- 变更类型：旧同步读链路删除与 route/read-model 边界收口。
- 新增/更新测试：更新 `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_search_pending_sql_runtime.py` 中待找发票 rows/read-model 入口断言；`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_pending_invoice_read_export_routes_use_route_owner` 继续防止 route callback 回归。
- 覆盖点：`/api/pending-invoices/rows` 只走 route owner + `PendingInvoiceReadModelService`；read model miss/unconfigured repository 不同步扫描；filter-options/export 非 fresh 返回 refreshing；QueryService 不再暴露同步 `list_rows`、旧同步 filter/export 或旧 `_handle_api_pending_invoice_rows` 兼容入口。
- 验证命令：见本轮最终说明。

## 2026-07-06 - source fast path relation member summaries

- 变更类型：`pending_invoice` source fast path 展示字段修复。
- 新增/更新测试：更新 `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_source_fast_path_does_not_wait_for_relation_read_model`。
- 覆盖点：当 `pending_invoice` projection 直接读取 active relation source rows 而不等待 `workbench_relation` read model 时，仍必须从 workbench-relations repository 边界补齐银行金额、OA 申请人/项目、发票号码/供应商/金额；避免只凭 relation `row_ids` 算出 `paid_invoiced`，但待找发票列表 OA/发票列显示为空。
- 漏测原因：原有 source fast path 测试只断言 relation count、case id、source version 和状态，完整展示字段只在已物化 `workbench_relation` distribution 的假数据里覆盖，未覆盖生产中 source fast path 的 id-only relation row。
- 验证命令：见本轮最终说明。

## 当前影响面清单

待找发票是发票/OA、银行标签规则、Workbench 关系、选择已有发票和收入状态覆盖的交汇页。Search 与共享 worker 是回归面，但不再是页面读依赖：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 发票获取状态 | canonical bank/invoice/OA/income override facts + `pending_invoice_status_payload` | `invoice_acquisition_status` shape 保持兼容；页面不能私有定义状态或 primary action。 |
| 方向 | `expense` / `income` query scope | 支出读取进项发票与支出流水；收入读取销项发票与收入流水；`all` direction 组合双方 summary。 |
| 规则组与状态桶 | `pending_invoice_tag_groups.version`、`pending_output_invoice_tag_groups.version`、`invoice_acquisition_status.code` | 支出/收入规则版本独立；`requires_invoice` 作为规则解释是 active tag complement，不是可编辑持久事实；作为列表 filter 是最终状态桶，不能依赖 `filter_group`。 |
| 银行标签 | canonical bank category/confirmation facts + settings | 规则筛选必须使用 effective category；标签归档/重命名后正常 GET 读取新 facts/settings。 |
| 历史 manual command | `PendingInvoiceApplicationService.preview_manual_invoice` / `confirm_manual_invoice`、command repository | 只保留旧数据恢复/迁移兼容测试；待找发票 HTTP API 和页面 UI 不再暴露 manual invoice 新写入口。 |
| 选择已有发票 | attach existing candidates/preview/confirm、`WorkbenchRelationCommandService` | 只允许 expense 选择 input invoice；支持多条流水和多张发票批量 preview/confirm；候选表“流水关联”chip 由后端 relation facts 驱动；可附加已被其他付款或 OA 关联的发票并通过 command service 合并到兼容 active relation；Workbench withdraw 应恢复 confirm 前上一 active 状态；必须写 audit/finalizer。 |
| 多关系成员展示 | active `app.workbench_pair_relations` + canonical bank/invoice/OA facts | `bank_transactions`、`input_invoices`、`oa` 分区必须按 relation 成员聚合；多流水时银行栏展示真实对方户名列表且不显示交易时间，不用 `+N` 替代户名；多发票/多 OA 仍用 `+N` 表示该类型全部成员；不能同时展示 primary，也不能把多流水成员重复输出为 standalone 行。 |
| 收入状态标记 | income status override | `income_no_invoice_required` / `cash_income` 支持批量选择；必须全量预检后一次写 command/audit/finalizer，只刷新 pending/search，不误刷税金/成本/银行余额。 |
| 页面读 API | `PendingInvoiceCanonicalQueryService`、`PostgresPendingInvoiceCanonicalRepository` | rows/filter-options/details/candidates/export 直接读 canonical PostgreSQL；无 freshness gate、202、enqueue 或 fallback。 |
| 页面 SQL | `pending_invoice_canonical_query.py` | 同一 RR/RO snapshot 组装 four-zone payload、summary、statistics、facets，并做服务端 filter/sort/page。 |
| 共享 worker | pending/search/invoice-lifecycle/relation workers | 不在页面请求热路径；本分支只做回归，最终清理由主控在所有调用方迁移后统一执行。 |
| 前端交互 | `PendingInvoicesPage`、`web/src/features/pendingInvoices/api.ts` | 方向/filter、表头筛选、rules/detail/attach/export drawers、收入批量状态及 loading/empty/error；没有 read-model 状态或 polling。 |
| 跨模块写后行为 | pending rules、attach existing、income status、workbench relation | 保留既有 audit/idempotency/CAS/lifecycle 副作用；成功后页面重新 GET canonical facts，无关页面行为不得改变。 |

## 场景覆盖清单

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 支出待找发票状态 | P0 | `tests/test_pending_invoice_service.py`、`tests/test_invoice_lifecycle_page_integration.py`、`web/e2e/pending-invoices-fanout.spec.ts` | covered | 多发票同流水、规则命中、发票付款事实、最终 `invoice_acquisition_status`；Browser e2e 覆盖关联台 confirm 后从 `已支付待开票` 更新为 `已支付已开票`。 |
| 收入待找发票状态 | P0 | `tests/test_pending_invoice_service.py`、`tests/test_search_pending_sql_runtime.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/e2e/pending-invoices-income-status-flow.spec.ts` | covered | `income_pending_invoice`、`cash_income`、`income_no_invoice_required`、收入规则筛选和 income status override；Browser 覆盖收入方向多选、批量状态写入、rows refetch、成功后无操作失败/同步失败/read model 失败残留、后端拒绝时零半写，以及保存暂时失败时错误可见、选择保持、rows 不半写并可重试成功。 |
| 规则版本与规则保存 | P0 | `tests/test_pending_invoice_api.py`、`tests/test_pending_invoice_service.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesRulesSaveTimeout.test.tsx`、`web/src/test/GlobalOperationOverlayContext.test.tsx`、`web/e2e/pending-invoices-rules-save-flow.spec.ts` | covered | 支出/收入版本独立、stale version conflict、requires complement、互斥分组、保存后 lifecycle；前端保存后全局遮罩等待 `pending_invoice` barrier fresh 并重读当前 rows 后释放，若仅 barrier timeout 则保留保存成功并展示刷新中，不弹保存失败；Browser 覆盖规则 drawer 保存、PUT contract、`pending_invoice:expense:requires_invoice` barrier target、rows refresh、刷新中反馈、成功后无保存失败/同步失败/read model 失败残留，以及保存暂时 503 时抽屉内错误可见、草稿保持、全局操作弹窗不阻塞、不触发 barrier/rows 刷新并可重试成功。 |
| manual invoice 新写入口移除 | P0 | `tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts` | covered | manual preview/confirm HTTP route 返回 not_found；页面没有行内三点、补票 dialog 或 manual API client。 |
| 历史 manual command 恢复 | P1 | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py` | covered | 保留旧命令幂等/失败可恢复/audit/finalizer 覆盖，不作为新 HTTP/UI 入口。 |
| 选择已有发票 attach existing | P0 | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts`、`web/e2e/pending-invoices-attach-existing-flow.spec.ts` | covered | 单条和批量 candidates/preview/confirm、expense/input 限制、候选“流水关联”chip、preview 冲突原因、已关联其他付款或 OA 仍可选、command service relation 合并、Workbench withdraw 恢复上一状态、行刷新；Browser 覆盖多选流水/发票、搜索、preview 汇总、confirm 后 rows refetch、成功后无操作失败/同步失败/read model 失败残留、confirm 暂时 503 时错误可见且不半写、drawer/preview/选择保持并可重试、重试成功后才刷新 rows，conflict 禁用确认和零半写。 |
| 多 OA / 多流水 / 多发票聚合展示 | P0 | `tests/test_pending_invoice_service.py`、`tests/test_search_pending_sql_runtime.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx` | covered | Transaction-scoped row/detail helper 和 SQL projection 都覆盖同一 `workbench_relation` 下 2 OA、3 流水、2 发票只输出 1 行，`bank_transactions.relation_count=3`、发票/OA count 正确、linked paid total 正确；前端 mapper/table 覆盖 `bankTransactions`，多流水展示真实对方户名且不显示交易时间，发票/OA 多项仍显示 `+N`，抽屉按 `kind=bank|invoice|oa` 只展示对应分区。 |
| relation command boundary | P0 | `tests/test_pending_invoice_service.py`、`tests/test_platform_runtime_boundary_guards.py` | covered | 当前 attach 写入和历史 manual command 恢复必须委托 `WorkbenchRelationCommandService`；服务代码不得 fallback 到 pair service 读取 active relation。 |
| API contract | P0 | `tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesApi.test.ts` | covered | rows、detail、candidates、rules、manual endpoint removal、attach、income status batch、export、权限和错误 shape。 |
| canonical snapshot 与旧链路隔离 | P0 | `tests/test_pending_invoice_canonical_query.py`、`tests/test_pending_invoice_api.py`、`web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts` | covered | rows/summary/statistics/facets 同一 RR/RO snapshot；页面不读四类 read model，不返回旧状态字段、不 enqueue、不 polling。 |
| active relation 合同 | P0 | `tests/test_pending_invoice_canonical_query.py`、`tests/test_pending_invoice_service.py` | covered | 只读取 active `app.workbench_pair_relations`，排除 `turnover_manual_closure`，跨月 relation 仍可见，候选关联状态来自 canonical relation facts。 |
| filter-options SQL 聚合 | P0 | `tests/test_pending_invoice_canonical_query.py`、`tests/test_pending_invoice_api.py` | covered | PostgreSQL 在页面 set-based 查询中有界聚合筛选项，避免为筛选项加载全量 rows。 |
| export 全量收集上限 | P2 | `tests/test_pending_invoice_canonical_query.py`、`tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/e2e/pending-invoices-export-download.spec.ts` | covered | canonical query service 在匹配行数超过 20,000 时结构化返回 `pending_invoice_export_row_limit_exceeded`，只执行一次有界查询，不继续分页生成 XLSX。 |
| 首屏分页性能护栏 | P2 | `tests/test_pending_invoice_service.py`、`web/src/test/PendingInvoicesPage.test.tsx` | covered | 页面首屏 rows 请求固定 `page=1&page_size=50`，控件限制 25/50/100；service 对异常大 `page_size` 夹到 200 并保留真实 `total`。 |
| canonical SQL 内容 | P0 | `tests/test_pending_invoice_canonical_query.py` | covered | four-zone payload、active relation distribution、bank tag、OA identity、candidate id 隔离、filter/sort/page 和固定查询次数。 |
| 共享 worker 回归 | P1 | `tests/test_search_pending_sql_runtime.py`、`tests/test_invoice_lifecycle_page_integration.py` | covered | 页面迁移未删除或改写 Search、invoice-lifecycle、pending projection 与共享 relation worker；最终清理由主控处理。 |
| 写入 lifecycle 回归 | P0 | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py` | covered | rules/attach/income status 保持原子写、audit/idempotency/CAS/finalizer；成功后页面重新 GET canonical facts。 |
| App Status / registry | P1 | `tests/test_app_status_overview_service.py`、`tests/test_app_status_readiness_backfill.py` | unchanged | 共享 pending read model/worker 仍因其它调用方保留；页面不读取或显示其状态。 |
| 前端交互 | P1 | `web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesRulesSaveTimeout.test.tsx`、`web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts`、既有 `web/e2e/pending-invoices-*.spec.ts` | covered | four-zone table、filters、rules/detail/attach/export drawers、收入批量状态、loading/empty/error、写后 refetch、导出错误；页面无 refreshing/stale 状态、无 freshness barrier 和 polling。 |
| 前端 API mapper | P1 | `web/src/test/PendingInvoicesApi.test.ts` | covered | 不猜缺失状态、filter/sort query、rules/detail/candidates、候选 `bankRelationStatus`、preview conflict object 文案、批量 candidates/attach、export/income batch mapper、下载失败结构化消息透出。 |
| 真实生产验证 | P2 | 主控部署/生产 smoke | documented-risk | 本分支已做本地真实 PostgreSQL 50,003 行 smoke/EXPLAIN；生产权限、审计、真实并发写后可见性和端点 SLO 由主控合并部署后验证。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_pending_invoice_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | 覆盖支出/收入状态、规则组、attach existing、candidate 流水关联状态、多 relation 成员聚合和去重、income override、manual 新入口移除、候选排序和状态优先级。 |
| 2. Service-layer tests | 适用 | `tests/test_pending_invoice_canonical_query.py`、`tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py` | 覆盖 canonical repository/service snapshot、固定查询次数、分页/导出上限，以及 application service、command repository、relation command service、audit/finalizer、idempotency/CAS。 |
| 3. API contract tests | 适用 | `tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesApi.test.ts` | 覆盖 rows、`bank_transactions` mapper、filter-options、detail、rules、manual endpoint removal、candidate 流水关联字段、attach、income status batch、export 和权限/错误。 |
| 4. Read model/cache/background job tests | 适用（cleanup/regression） | `tests/test_pending_invoice_canonical_query.py`、`tests/test_search_pending_sql_runtime.py`、`web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts` | 页面测试锁定四类 read model、status/source versions、enqueue/polling 已退出热路径；共享 Search/lifecycle/worker 测试继续通过，因仍有范围外调用方不在本分支删除。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesRulesSaveTimeout.test.tsx`、`web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts`、既有 `web/e2e/pending-invoices-*.spec.ts` | 覆盖 loading/empty/error、筛选/排序/分页、rules/detail/attach/export drawers、批量写、写后 refetch、错误恢复、无 read-model status/freshness barrier/polling。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_pending_invoice_api.py`、`tests/test_pending_invoice_service.py`、`web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts`、既有 `web/e2e/pending-invoices-*.spec.ts` | 覆盖 Workbench/attach/rules/income write → canonical facts → 页面重新 GET，以及 canonical 空集；生产真实并发写后可见性留给主控部署验证。 |
| 7. Existing feature regression tests | 适用 | 上述全部 pending invoice tests，加 `tests/test_invoice_lifecycle_page_integration.py`、`tests/test_search_pending_sql_runtime.py` 和既有 pending invoice E2E | 保护 Search API、共享 lifecycle/relation worker、旧写入权限/审计/idempotency/CAS，以及 filter/sort/page/export shape；成本统计、外部往来款、ETC、导入、设置代码未改。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 长期 | 前端在后端缺少状态字段时自行推断 pending invoice 状态或 primary action。 | `web/src/test/PendingInvoicesApi.test.ts` | covered |
| 长期 | `bank_statement_as_invoice` 筛选继续展示已经关联发票的流水。 | `tests/test_search_pending_sql_runtime.py::test_pending_invoice_sql_projection_excludes_already_invoiced_rows_from_statement_filter` | covered |
| 长期 | `requires_invoice` 被当成用户可编辑持久分组。 | `tests/test_pending_invoice_api.py::test_pending_invoice_rules_put_ignores_legacy_requires_invoice_input`、`tests/test_pending_invoice_service.py::test_requires_invoice_filter_uses_active_tag_complement` | covered |
| 长期 | 收入规则和支出规则共用版本或互相污染。 | `tests/test_pending_invoice_api.py::test_income_pending_invoice_rules_are_saved_separately_from_expense_rules`、`tests/test_pending_invoice_service.py::test_income_filters_use_pending_output_invoice_rule_groups` | covered |
| 长期 | 候选 relation case id 被当作真实 OA id 请求详情。 | `tests/test_pending_invoice_service.py::test_rows_keep_candidate_case_id_separate_from_real_oa_id`、`web/src/test/PendingInvoicesPage.test.tsx` | covered |
| 长期 | API/read model miss 时同步扫描旧 snapshot 并伪装 fresh。 | `tests/test_pending_invoice_api.py::test_read_model_miss_returns_refreshing_without_sync_scan`、`tests/test_search_pending_sql_runtime.py` | covered |
| 2026-07-07 | 多流水聚合行在银行栏用 `+N` 替代真实对方户名，且户名下继续显示交易时间。 | `web/src/test/PendingInvoicesPage.test.tsx::renders project four-zone table contract and summarizes multiple relations`、`web/src/test/PendingInvoicesPage.test.tsx::opens relation, rules, and export drawers with loading callbacks` | covered |
| 2026-06-23 | 同一 Workbench relation 下多笔流水、多张发票或多张 OA 被同时显示为 primary 和聚合明细，或多笔流水成员又作为 standalone 行重复出现。 | `tests/test_pending_invoice_service.py::PendingInvoiceQueryServiceTests::test_transaction_rows_collapse_multi_bank_relation_into_one_grouped_row`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_sql_projection_collapses_multi_bank_relation_members`、`web/src/test/PendingInvoicesPage.test.tsx::renders project four-zone table contract and summarizes multiple relations`、`web/src/test/PendingInvoicesPage.test.tsx::opens relation, rules, and export drawers with loading callbacks` | covered；service test 已迁到 test-local row builder，生产 `PendingInvoiceQueryService.list_rows` 已删除。 |
| 2026-06-13 | filter-options 为生成筛选项读取全量 rows，导致认证态页面 HTTP SLO 长尾。 | `tests/test_pending_invoice_api.py::PendingInvoiceApiTests::test_filter_options_uses_sql_aggregation_after_fresh_gate`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_repository_builds_filter_options_in_sql` | covered |
| 2026-06-14 | direct read model SLO 只刷新月度 shard，未覆盖页面默认 `direction=expense` 使用的 `pending_invoice:expense:all` aggregate scope，导致登录态 HTTP SLO 首屏返回 `refreshing`。 | `tests/test_read_model_slo_smoke.py::ReadModelSloSmokeTests::test_pending_invoice_smoke_includes_page_first_screen_aggregate_scope`、`tests/test_http_slo_probe.py` | covered |
| 2026-06-16 | 页面或调用方请求过大 `page_size`，导致待找发票首屏 rows 长尾或误把全量列表当首屏渲染。 | `tests/test_pending_invoice_service.py::PendingInvoiceQueryServiceTests::test_page_size_limit_protects_first_screen_slo`、`web/src/test/PendingInvoicesPage.test.tsx` | covered |
| 2026-06-16 | 待找发票 export-preview/export 对大匹配集继续分页收集并同步生成 XLSX，拖慢 API 线程和内存；或前端下载路径/导出抽屉吞掉后端超限消息。 | `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_read_model_service_all_rows_rejects_export_row_limit_before_scanning_more_pages`、`tests/test_pending_invoice_api.py::PendingInvoiceApiTests::test_export_endpoints_reject_row_limit_before_xlsx_generation`、`web/src/test/PendingInvoicesApi.test.ts::surfaces backend row-limit messages from failed export downloads`、`web/src/test/PendingInvoicesPage.test.tsx::shows backend export row-limit messages inside the export drawer`、`web/e2e/pending-invoices-export-download.spec.ts::surfaces backend row-limit errors without creating a download` | covered |
| 2026-07-02 | 首屏 rows API 排序为 `trade_date desc nulls last, row_id`，但热路径索引若只声明 `trade_date desc` 会默认 `NULLS FIRST`，生产大数据下可能退化为额外排序并导致 authenticated HTTP SLO 超过 1s。 | `tests/test_postgres_migrations.py::PostgresMigrationDiscoveryTests::test_pending_invoice_first_screen_sort_index_matches_query_order` | covered |
| 2026-07-02 | rows 新写入继续把同一 JSON 同时写入 `payload` 和 `raw_payload.normalized_payload`，查询又无条件 select `raw_payload`，导致首屏按返回行数重复读取/解码无用 JSONB。 | `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_repository_reads_rows_page_and_summary`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_repository_writes_canonical_payload_without_raw_payload_duplication` | covered |
| 2026-07-02 | rows normalization 对每行重复读取 settings 构建银行账号映射，导致首屏耗时随返回行数线性增加。 | `tests/test_pending_invoice_service.py::PendingInvoiceQueryServiceTests::test_normalize_row_payloads_loads_bank_mapping_once_per_page` | covered |
| 2026-06-17 | 规则抽屉保存成功但页面在 read model 仍 refreshing 时提前恢复可操作，用户仍需手动刷新才能看到新规则结果。 | `web/src/test/PendingInvoicesPage.test.tsx::refetches rows after saving rules and displays refreshed rule filter buckets`、`web/src/test/GlobalOperationOverlayContext.test.tsx` | covered |
| 2026-06-18 | 支出/收入待找发票规则保存 API 已成功，但 `pending_invoice` read model barrier 在 10 秒内仍 refreshing，被全局遮罩误报为“操作失败”。 | `web/src/test/PendingInvoicesRulesSaveTimeout.test.tsx::keeps expense and income rule saves successful when read model freshness wait times out`、`web/src/test/OperationBarrierApi.test.ts::throws timeout error when targets keep refreshing` | covered |
| 2026-06-18 | 待找发票四区表使用 React Aria Collection table 时，正文单元格拖拽无法选中文字。 | `web/e2e/pending-invoices-fanout.spec.ts::allows selecting text in the pending invoice table body` | covered |
| 2026-06-19 | 待找发票列筛选或排序可能丢失默认 `paid_pending_invoice` 状态过滤，或只更新 query 不更新可见行。 | `web/e2e/pending-invoices-filter-sort-flow.spec.ts::keeps status filters while applying column filters and amount sorting` | covered |
| 2026-06-21 | 关联台已确认 OA/流水/发票后，待找发票 read model 已经是 `paid_invoiced`，但页面首屏只默认筛 `paid_pending_invoice`，导致 350 这类已闭环流水默认不可见。 | `web/src/test/PendingInvoicesPage.test.tsx::renders project four-zone table contract and summarizes multiple relations`、`web/e2e/pending-invoices-filter-sort-flow.spec.ts::keeps status filters while applying column filters and amount sorting` | covered |
| 2026-06-21 | `workbench_relation` typed OA identity 若不是旧 `oa-` 前缀，待找发票旧身份校验会丢弃 OA summary，使已确认关系看起来缺 OA。 | `tests/test_pending_invoice_relation_identity.py::PendingInvoiceRelationIdentityTests::test_accepts_typed_oa_identity_without_legacy_prefix_requirement`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_sql_projection_consumes_workbench_relation_distribution` | covered |
| 2026-07-03 | 关联台选择“银行流水+OA 附件进项发票”确认时，旧上下文扩展只把发票并入 OA+银行方向，没有反向把 OA 并入银行+发票方向；Workbench 旧分组看起来三栏完整，但 canonical relation 和待找发票 `workbench_relation` distribution 只剩银行+发票，导致 145 类已闭环行 OA 栏为空。已写坏的 active relation 也必须通过 OA 附件上下文 repair executor 走 command service 修正。 | `tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_confirm_link_includes_existing_oa_attachment_context_when_bank_and_invoice_selected`、`tests/test_workbench_oa_attachment_repair_context_executor.py::WorkbenchOaAttachmentRepairContextExecutorTests::test_repair_adds_missing_parent_oa_when_relation_has_bank_and_attachment_invoice`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_read_model_repairs_active_relation_missing_parent_oa_for_attachment_invoice`、`tests/test_workbench_relation_sql_projection.py::WorkbenchRelationSqlProjectionTests::test_rebuild_indexes_cross_month_relation_members_in_current_scope`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_sql_projection_consumes_workbench_relation_distribution` | covered |
| 2026-06-20 | 待找发票 rows 首屏请求失败时，页面同时显示正常空态且导出仍可点，容易把临时加载失败误判为真实无数据或触发伪成功导出。 | `web/e2e/pending-invoices-filter-sort-flow.spec.ts::recovers rows after a transient load failure when refreshed` | covered |
| 2026-06-20 | 选择已有发票 confirm 第一次暂时失败时，页面可能关闭抽屉、刷新 rows 或显示假成功，造成用户误以为 relation 已建立，或者错误弹窗出现但关系状态不清晰。 | `web/e2e/pending-invoices-attach-existing-flow.spec.ts::keeps attach-existing confirmation recoverable after a transient relation failure` | covered |
| 2026-06-20 | 收入批量状态保存第一次暂时失败时，页面可能清空选择、刷新 rows 或显示假成功，导致部分收入流水状态是否写入不清晰。 | `web/e2e/pending-invoices-income-status-flow.spec.ts::keeps income status batches recoverable after a transient save failure` | covered |
| 2026-06-20 | 规则保存暂时失败时，全局操作错误弹窗可能被抽屉 top-layer 拦截导致“确定”点不到，或者页面触发 barrier/rows 刷新造成假保存。 | `web/e2e/pending-invoices-rules-save-flow.spec.ts::keeps rule drafts recoverable after a transient save failure`、`web/src/test/GlobalOperationOverlayContext.test.tsx::can clear failures immediately when the caller owns local error feedback` | covered |
| 2026-06-19 | 关联台已确认 OA/发票 relation 后，待找发票导出仍可能只按旧筛选/当前分页导出，或漏掉 OA 申请人、进项发票号、relation case 和 linked 状态。 | `web/e2e/pending-invoices-export-download.spec.ts::downloads current filtered pending invoices with confirmed OA and invoice relation fields` | covered |
| 2026-06-19 | 规则保存 Browser 流缺失，导致真实页面中规则 drawer 保存、PUT body、`pending_invoice` freshness barrier、rows refetch 或保存反馈任一环节坏掉时只能由组件测试发现。 | `web/e2e/pending-invoices-rules-save-flow.spec.ts::saves expense rules through the pending invoice freshness barrier and refreshes rows` | covered |
| 2026-06-19 | 选择已有发票 Browser 流可能只在组件测试中覆盖，真实浏览器里多选流水、候选抽屉、preview、confirm、冲突禁用、rows refetch 或成功后错误残留任一环节坏掉都无法发现。 | `web/e2e/pending-invoices-attach-existing-flow.spec.ts::previews and confirms selected expense rows with existing input invoices then refreshes rows`、`web/e2e/pending-invoices-attach-existing-flow.spec.ts::shows preview conflicts and blocks confirm without a half-written relation`、`web/e2e/fixtures/successAssertions.ts` | covered |
| 2026-06-18 | 发票获取状态只能单选且展示“需要开票”中间桶，首屏默认全部，用户需要二次筛到常用的“已支付待开票”。 | `web/src/test/PendingInvoicesPage.test.tsx::supports multi-select invoice acquisition status filters for expense rows`、`web/src/test/PendingInvoicesPage.test.tsx::renders project four-zone table contract and summarizes multiple relations` | covered |
| 2026-06-18 | 关联台已经有 OA/发票 relation，但待找发票 API expected-source gate 未校验 `workbench_relation_source_versions`，旧的无 OA 行被当作 fresh 返回。 | `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_api_workbench_relation_source_version_stale_enqueues_refresh`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_api_workbench_relation_source_version_mismatch_enqueues_refresh`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_repository_aggregates_bank_detail_source_versions_across_month_shards`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_repository_loads_workbench_relation_source_versions_for_matching_months` | covered |
| 2026-06-25 | pending invoice projection writer 和 API expected-source 合同不一致，且 `expense:all` aggregate source-version proof 被零行历史 month shard 污染，导致生产刷新完成后仍返回 refreshing。 | `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_writer_and_api_source_version_contracts_match`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_repository_ignores_zero_row_historical_shards_for_aggregate_source_versions` | covered |
| 长期 | 人工补票 confirm 中途失败后重复创建发票或关系。 | `tests/test_pending_invoice_service.py::test_retry_recovers_invoice_created_before_relation_created`、`tests/test_pending_invoice_service.py::test_retry_recovers_relation_created_before_finalization` | covered |
| 2026-06-12 | relation write safety 不通过时人工补票先创建发票，形成孤儿发票或半写状态。 | `tests/test_pending_invoice_service.py` command service / rollback coverage | covered |
| 2026-06-12 | 待找发票 relation 写入绕过统一 command service，形成页面私有事实源。 | `tests/test_pending_invoice_service.py::test_confirm_manual_invoice_delegates_relation_write_to_command_service`、`tests/test_pending_invoice_service.py::test_confirm_attach_existing_invoice_delegates_relation_write_to_command_service`、`tests/test_pending_invoice_service.py::test_confirm_attach_existing_invoices_batch_delegates_relation_write_to_command_service`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_read_models_use_workbench_relation_distribution` | covered |
| 长期 | attach existing 不允许已关联其他付款的发票，阻断合法多付款场景。 | `tests/test_pending_invoice_service.py::test_attach_existing_allows_invoice_already_linked_to_another_bank_payment` | covered |
| 2026-06-17 | 候选表用 `remaining_amount` / “待支付”暗示是否已关联流水，且 preview `can_confirm=false` 时只禁用确认按钮不展示原因。 | `tests/test_pending_invoice_service.py::test_invoice_candidate_with_other_bank_payment_remains_available`、`web/src/test/PendingInvoicesApi.test.ts::maps attach-existing preview conflict objects into readable messages`、`web/src/test/PendingInvoicesPage.test.tsx::shows preview conflicts and keeps confirm disabled when attach-existing cannot be confirmed` | covered |
| 2026-06-17 | 已有 OA+发票 active relation 的进项发票无法在待找发票 attach existing 中并入同一个 active case，或关联台撤回后没有恢复上一状态。 | `tests/test_pending_invoice_service.py::test_invoice_candidates_keep_oa_invoice_relation_available_for_attachment`、`tests/test_pending_invoice_service.py::test_attach_existing_batch_merges_existing_oa_relation_and_withdraw_restores_previous_state` | covered |
| 2026-06-11 | 多条流水选择已有进项发票只能单选流水/单选发票，且前端不展示已选流水金额、已选发票金额和差额。 | `tests/test_pending_invoice_service.py::test_preview_and_confirm_attach_existing_invoices_batch_are_idempotent`、`tests/test_pending_invoice_api.py::PendingInvoiceApiTests::test_batch_attach_existing_invoice_endpoints`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx` | covered |
| 2026-06-11 | 支出状态下拉缺少 `已支付待开票` 和 `已支付已开票` 直接筛选入口。 | `web/src/test/PendingInvoicesPage.test.tsx` | covered |
| 2026-06-15 | 行内三点和补票入口继续暴露，导致旧 manual 新写路径污染待找发票链路。 | `tests/test_pending_invoice_api.py::PendingInvoiceApiTests::test_manual_invoice_endpoints_are_not_reachable`、`web/src/test/PendingInvoicesPage.test.tsx` | covered |
| 2026-06-15 | 收入侧只能逐行标记，前端循环调用单条接口可能造成半成功。 | `tests/test_pending_invoice_service.py::PendingInvoiceApplicationServiceTests::test_confirm_income_status_overrides_batch_is_idempotent_and_fans_out_once`、`tests/test_pending_invoice_service.py::PendingInvoiceApplicationServiceTests::test_confirm_income_status_overrides_batch_rejects_ineligible_rows_before_writing`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/e2e/pending-invoices-income-status-flow.spec.ts::batch marks selected income rows as cash income with one mutation and a rows refresh`、`web/e2e/pending-invoices-income-status-flow.spec.ts::surfaces rejected income status batches without clearing selection or changing rows` | covered |
| 2026-06-15 | `filter=requires_invoice` 被错误耦合到 `filter_group='requires_invoice'`，生产中 `filter_group=all` 但状态为 `paid_pending_invoice` / `paid_invoiced` 的行被筛空。 | `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_repository_requires_invoice_filter_uses_status_bucket`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_sql_projection_uses_active_complement_for_requires_invoice_filter`、`tests/test_pending_invoice_service.py::PendingInvoiceQueryServiceTests::test_expense_status_priority_uses_rules_and_invoice_payment_facts` | covered |

## 关键 smoke flows

1. `发票导入确认 -> invoice_lifecycle refresh -> pending_invoice/read search dirty scope -> pending-invoice/search workers -> /pending-invoices rows fresh`
2. `待找发票规则保存 -> pending_invoice_rules_changed lifecycle -> pending/invoice_lifecycle/workbench/tax/cost/search refresh -> 不刷新 no_oa/bank balance/turnover -> 保存成功后无保存失败/同步失败/read model 失败残留`
3. `选择已有发票 candidates(流水关联 chip) -> preview(conflicts/warnings/关联后待付) -> confirm -> relation/audit/finalizer -> affected months -> relation/detail/drawer 刷新`
4. `多选支出流水 -> 批量候选进项发票 -> 多选发票 -> preview 汇总本次选择差额 -> confirm 合并兼容 bank/invoice/oa relation 写一条 active relation -> 关联台 withdraw 恢复上一状态 -> 页面 refetch`
5. `多选收入流水 -> 批量标记 no invoice required/cash income -> pending_invoice_income_status_override_confirmed -> pending/search refresh -> 税金/成本不误刷`
6. `manual invoice legacy command retry -> command log 恢复旧中断状态；HTTP/UI 新入口保持不可达`
7. `关联台 confirm -> workbench relation distribution -> pending invoice read model rows fresh -> 待找发票从已支付待开票更新为已支付已开票，并显示发票和 OA`
8. `未正式化 decision / 历史 candidate 兼容值 -> 待找发票仍保持已支付待开票，不把非 active relation 计入 linked-only 开票状态`
9. `relation-backed pending invoice read model refreshing/stale -> 页面显示刷新/读模型诊断；refreshing 保留选择发票入口，stale 空 rows 不伪装真实空`
10. `rows 首屏暂时加载失败 -> 页面显示错误和错误态空行文案、禁用导出 -> 用户点击刷新 -> rows fresh 恢复且错误消失`
11. `选择已有发票 confirm 暂时失败 -> drawer/preview/选择保持、错误可见、rows 不重读且状态不半写 -> 用户重试 -> confirm 成功后 rows refresh 到已开票且无错误残留`
12. `收入批量状态保存暂时失败 -> 错误可见、选中保持、rows 不重读且状态不半写 -> 用户重试 -> 保存成功后 rows refresh 到现金收入且无错误残留`
13. `规则保存暂时失败 -> 抽屉内错误可见、草稿保持、无不可点击全局错误层、barrier/rows 不触发 -> 用户重试 -> 保存成功后 barrier/rows refresh 且无错误残留`

## 本模块验证命令

最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_pending_invoice_api tests.test_invoice_lifecycle_page_integration -v
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_pending_invoice_relation_identity tests.test_pending_invoice_oa_identity_backfill -v
PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service.PendingInvoiceQueryServiceTests.test_page_size_limit_protects_first_screen_slo -v
cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/PendingInvoicesPage.test.tsx
cd web && npx playwright test e2e/pending-invoices-attach-existing-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/pending-invoices-income-status-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/pending-invoices-export-download.spec.ts --project=chromium
cd web && npx playwright test e2e/pending-invoices-rules-save-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/pending-invoices-filter-sort-flow.spec.ts --project=chromium
cd web && npm run e2e:smoke
bash scripts/verify.sh docs
```

扩展回归按改动选择：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api tests.test_tax_offset_api tests.test_cost_statistics_api tests.test_bank_auto_tag_rules_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api tests.test_oa_pending_payment_api tests.test_output_invoice_collection_api -v
cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx src/test/TaxOffsetPage.test.tsx src/test/CostStatisticsPage.test.tsx
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_worker_manifest --json
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend Vitest、build 和 deterministic Playwright smoke，覆盖完整待找发票、SQL projection、invoice lifecycle、App Status 和前端测试集，并覆盖真实 Chromium 中 Workbench confirm 后待找发票行状态更新、未正式化 decision / 历史 candidate 兼容值不驱动 `已支付已开票` 状态、规则保存 barrier/rows refresh 后无错误残留，以及 relation-backed read model 非 fresh 诊断。单轮模块验证只跑最小闭环。

## 未测风险

- 本地测试不连接真实生产 Postgres 大数据量，不验证真实搜索/待找发票 SQL projection 的 EXPLAIN、锁等待或长尾分页性能。
- 本地测试不跑真实 RabbitMQ/Redis/systemd `pending-invoice`、`search` 与 invoice-lifecycle worker drain；dirty/outbox 到 projection 的最终收敛需要 staging 或夜间 CI/生产前 smoke。
- 本地已覆盖待找发票超过 20,000 行导出 fail-closed；当前 Browser e2e 覆盖 Workbench confirm fan-out、默认状态过滤、列筛选/排序、rows 首屏暂时加载失败后手动刷新恢复、规则保存 pending read model barrier/rows refresh、规则保存暂时失败草稿重试恢复、选择已有发票成功/冲突/confirm 暂时失败重试流、收入批量状态成功/拒绝/暂时失败重试流、candidate/linked 负面语义、relation-backed read model 非 fresh 诊断、真实 download event 和 row-limit 下载失败反馈，但不覆盖 attach existing / income status / rules save 后真实 worker drain、withdraw、真实 XLSX workbook 打开、大文件下载耗时和 withdraw 等其它 mutation 真实网络中断恢复。

## 2026-07-03 - relation distribution legacy OA completed aliases

- 根因：待找发票的 OA 列只消费 `workbench_relation` distribution 的 `linked_oa`，而 `workbench_relation` 生成 OA summary 时旧完成态 predicate 只接受 `completed`/空值。历史 OA projection 行若保留 `已完成`、`approved` 或 `2` 等完成态别名，canonical relation 仍可包含 OA row id，但 distribution 的 `linked_oa` 为空，导致 145 类已配对行在待找发票 OA 列为空。
- 修复：完成态识别收敛到 OA projection 边界并 bump `OA_PROJECTION_SYNC_VERSION`，让 relation/pending read model 重新生成；待找发票不新增附件/OA raw payload fallback。
- 新增测试：`tests/test_workbench_relation_sql_projection.py::WorkbenchRelationSqlProjectionTests::test_rebuild_keeps_oa_summary_for_legacy_completed_workflow_status`、`tests/test_oa_projection_sync_service.py::OaProjectionSyncServiceTests::test_oa_sync_treats_legacy_completed_workflow_aliases_as_completed`。

## 2026-07-25 - shared relation source eligibility

- `tests/test_search_pending_sql_runtime.py` 与 `tests/test_postgres_repositories_boundaries.py` 证明 pending/search worker 的 relation rows/source summary 排除 Turnover 专属 `turnover_manual_closure`。
- `tests/test_audit_page_business_read_model_tool.py` 证明该专用关系不使 Pending Invoice consumer/Audit stale；HTTP shape、规则保存、attach/status 写合同和前端交互不变。

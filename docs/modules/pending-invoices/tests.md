# 待找发票测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

待找发票是发票生命周期、银行标签规则、Workbench 关系、选择已有发票、收入状态覆盖和搜索 read model 的交汇页。任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 发票获取状态 | `InvoiceLifecyclePolicy`、`invoice_lifecycle` read boundary、pending invoice read model | `invoice_acquisition_status` shape 保持兼容；页面不能私有定义状态或 primary action。 |
| 方向 | `expense` / `income` query scope | 支出读取进项发票与支出流水；收入读取销项发票与收入流水；`all` direction 组合双方 summary。 |
| 规则组与状态桶 | `pending_invoice_tag_groups.version`、`pending_output_invoice_tag_groups.version`、`invoice_acquisition_status.code` | 支出/收入规则版本独立；`requires_invoice` 作为规则解释是 active tag complement，不是可编辑持久事实；作为列表 filter 是最终状态桶，不能依赖 `filter_group`。 |
| 银行标签 | bank detail effective category facade/read model | 规则筛选必须使用 effective category；标签归档/重命名刷新规则 drawer 和 pending read model。 |
| 历史 manual command | `PendingInvoiceApplicationService.preview_manual_invoice` / `confirm_manual_invoice`、command repository | 只保留旧数据恢复/迁移兼容测试；待找发票 HTTP API 和页面 UI 不再暴露 manual invoice 新写入口。 |
| 选择已有发票 | attach existing candidates/preview/confirm、`WorkbenchRelationCommandService` | 只允许 expense 选择 input invoice；支持多条流水和多张发票批量 preview/confirm；候选表“流水关联”chip 由后端 relation facts 驱动；可附加已被其他付款或 OA 关联的发票并通过 command service 合并到兼容 active relation；Workbench withdraw 应恢复 confirm 前上一 active 状态；必须写 audit/finalizer。 |
| 收入状态标记 | income status override | `income_no_invoice_required` / `cash_income` 支持批量选择；必须全量预检后一次写 command/audit/finalizer，只刷新 pending/search，不误刷税金/成本/银行余额。 |
| API/read model | `PendingInvoiceReadModelService`、`SearchPendingSqlProjectionBuilder` | rows/filter-options/export 必须先经过 read model fresh gate；非 fresh 不能把空 rows 当真实结果。 |
| SQL projection | `read_model.pending_invoice_rows`、`read_model.pending_invoice_scopes` | four-zone payload、filter JSON、sort、source versions、bank tag freshness、relation distribution 和 OA identity。 |
| worker | `pending-invoice` / `search` workers，旧 `search-pending` 兼容 worker | `pending_invoice.read_model.refresh` 支持方向/规则 filter/month shard 和 legacy scope fan-out；`search.read_model.refresh` 由专用 search consumer drain。 |
| 前端交互 | `PendingInvoicesPage`、`web/src/features/pendingInvoices/api.ts` | 方向/filter、表头筛选、rules drawer、detail drawers、选中工具栏 attach existing、收入批量状态、read model refreshing。 |
| 跨模块 fan-out | invoice import、pending rules、attach existing、income status、workbench relation、bank tag update | 必须先触发 invoice lifecycle，再刷新 pending invoice、search、税金/成本等下游；无关页面不能被误刷。 |

## 场景覆盖清单

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 支出待找发票状态 | P0 | `tests/test_pending_invoice_service.py`、`tests/test_invoice_lifecycle_page_integration.py`、`web/e2e/pending-invoices-fanout.spec.ts` | covered | 多发票同流水、规则命中、发票付款事实、最终 `invoice_acquisition_status`；Browser e2e 覆盖关联台 confirm 后从 `已支付待开票` 更新为 `已支付已开票`。 |
| 收入待找发票状态 | P0 | `tests/test_pending_invoice_service.py`、`tests/test_search_pending_sql_runtime.py`、`web/src/test/PendingInvoicesPage.test.tsx` | covered | `income_pending_invoice`、`cash_income`、`income_no_invoice_required`、收入规则筛选和 income status override。 |
| 规则版本与规则保存 | P0 | `tests/test_pending_invoice_api.py`、`tests/test_pending_invoice_service.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesRulesSaveTimeout.test.tsx` | covered | 支出/收入版本独立、stale version conflict、requires complement、互斥分组、保存后 lifecycle；前端保存后全局遮罩等待 `pending_invoice` barrier fresh 并重读当前 rows 后释放，若仅 barrier timeout 则保留保存成功并展示刷新中，不弹保存失败。 |
| manual invoice 新写入口移除 | P0 | `tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts` | covered | manual preview/confirm HTTP route 返回 not_found；页面没有行内三点、补票 dialog 或 manual API client。 |
| 历史 manual command 恢复 | P1 | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py` | covered | 保留旧命令幂等/失败可恢复/audit/finalizer 覆盖，不作为新 HTTP/UI 入口。 |
| 选择已有发票 attach existing | P0 | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts` | covered | 单条和批量 candidates/preview/confirm、expense/input 限制、候选“流水关联”chip、preview 冲突原因、已关联其他付款或 OA 仍可选、command service relation 合并、Workbench withdraw 恢复上一状态、行刷新。 |
| relation command boundary | P0 | `tests/test_pending_invoice_service.py`、`tests/test_platform_runtime_boundary_guards.py` | covered | 当前 attach 写入和历史 manual command 恢复必须委托 `WorkbenchRelationCommandService`；服务代码不得 fallback 到 pair service 读取 active relation。 |
| API contract | P0 | `tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesApi.test.ts` | covered | rows、detail、candidates、rules、manual endpoint removal、attach、income status batch、export、权限和错误 shape。 |
| SQL read model freshness | P0 | `tests/test_search_pending_sql_runtime.py` | covered | miss/stale/source mismatch 返回 refreshing 并入队，不同步扫描；filter-options/export 非 fresh 返回 accepted。 |
| filter-options SQL 聚合 | P0 | `tests/test_pending_invoice_api.py`、`tests/test_search_pending_sql_runtime.py`、`tests/test_http_slo_probe.py` | covered | fresh gate 通过后由 PostgreSQL 聚合筛选项，避免页面首屏为选项拉取全量 rows；HTTP SLO 探针使用前端默认 `direction=expense`。 |
| export 全量收集上限 | P2 | `tests/test_search_pending_sql_runtime.py`、`tests/test_pending_invoice_api.py` | covered | `PendingInvoiceReadModelService.all_rows()` 和 export-preview/export API 在匹配行数超过 20,000 时结构化返回 `pending_invoice_export_row_limit_exceeded`，且只读取第一页，不继续分页生成 XLSX。 |
| 首屏分页性能护栏 | P2 | `tests/test_pending_invoice_service.py`、`web/src/test/PendingInvoicesPage.test.tsx` | covered | 页面首屏 rows 请求固定 `page=1&page_size=50`，控件限制 25/50/100；service 对异常大 `page_size` 夹到 200 并保留真实 `total`。 |
| SQL projection 内容 | P0 | `tests/test_search_pending_sql_runtime.py` | covered | four-zone payload、relation distribution、bank tag freshness、OA identity、candidate id 隔离、filter/sort。 |
| worker scope fan-out | P0 | `tests/test_search_pending_sql_runtime.py`、`tests/test_runtime_worker_registry.py` | covered | search/pending refresh handler、legacy pending scope、filter scope、month shard。 |
| lifecycle fan-out | P0 | `tests/test_derived_data_lifecycle_service.py`、`tests/test_pending_invoice_api.py` | covered | rules/attach/income status 事件刷新正确 read model；历史 manual command 恢复保持兼容，不误刷无关域。 |
| App Status / registry | P1 | `tests/test_app_status_overview_service.py`、`tests/test_app_status_readiness_backfill.py` | covered | pending route/read model/worker 在 domain registry 中可观测。 |
| 前端交互 | P1 | `web/src/test/PendingInvoicesPage.test.tsx`、`web/e2e/pending-invoices-fanout.spec.ts` | covered | four-zone table、filters、状态多选筛选、首屏默认 `已支付待开票`、rules drawer、conflict、detail drawers、选中工具栏 attach existing、候选流水关联 chip、preview 冲突原因和禁用确认、收入批量标记、refreshing 时选择栏可用、导出下载错误消息可见；Browser e2e 覆盖真实导航、Workbench confirm 弹窗和返回待找发票后的行状态。 |
| 前端 API mapper | P1 | `web/src/test/PendingInvoicesApi.test.ts` | covered | 不猜缺失状态、filter/sort query、rules/detail/candidates、候选 `bankRelationStatus`、preview conflict object 文案、批量 candidates/attach、export/income batch mapper、下载失败结构化消息透出。 |
| 真实生产数据与 worker drain | P2 | 运维 runbook / staging smoke | documented-risk | 需要真实 Postgres、RabbitMQ/Redis、`pending-invoice` / `search` / `invoice-lifecycle` workers 和大数据量样本。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_pending_invoice_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | 覆盖支出/收入状态、规则组、attach existing、candidate 流水关联状态、income override、manual 新入口移除、候选排序和状态优先级。 |
| 2. Service-layer tests | 适用 | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`tests/test_pending_invoice_relation_identity.py`、`tests/test_pending_invoice_oa_identity_backfill.py` | 覆盖 application service、command repository、relation command service 委托、兼容 OA+invoice active relation 合并、Workbench withdraw 恢复上一状态、audit/finalizer、identity/backfill、状态写入边界和 `page_size` 上限。 |
| 3. API contract tests | 适用 | `tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesApi.test.ts` | 覆盖 rows、filter-options、detail、rules、manual endpoint removal、candidate 流水关联字段、attach、income status batch、export 和权限/错误。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_search_pending_sql_runtime.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py` | 覆盖 SQL read model fresh/stale/missing/source mismatch、worker refresh、lifecycle fan-out 和 App Status。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts`、`web/e2e/pending-invoices-fanout.spec.ts` | 覆盖页面状态、筛选、规则、drawer、选中工具栏 attach/income 操作、manual UI 移除、refreshing 状态、首屏有界请求、API mapper、下载失败消息和真实浏览器跨页确认后行状态更新。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_pending_invoice_api.py`、`tests/test_search_pending_sql_runtime.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/e2e/pending-invoices-fanout.spec.ts` | 覆盖 attach/rules/income status -> lifecycle/dirty scope -> read model -> 页面刷新；Browser e2e 覆盖 Workbench confirm -> pending invoice rows fresh 后页面刷新；真实 worker drain 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | 上述全部 pending invoice tests，加 invoice lifecycle、workbench、tax offset、cost statistics、bank details tests 的按改动选择扩展集，以及 `web/e2e/pending-invoices-fanout.spec.ts` | 待找发票规则和关系会影响多个下游页面；任何改动都要问旧页面会不会被误刷或误判 fresh。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 长期 | 前端在后端缺少状态字段时自行推断 pending invoice 状态或 primary action。 | `web/src/test/PendingInvoicesApi.test.ts` | covered |
| 长期 | `bank_statement_as_invoice` 筛选继续展示已经关联发票的流水。 | `tests/test_search_pending_sql_runtime.py::test_pending_invoice_sql_projection_excludes_already_invoiced_rows_from_statement_filter` | covered |
| 长期 | `requires_invoice` 被当成用户可编辑持久分组。 | `tests/test_pending_invoice_api.py::test_pending_invoice_rules_put_ignores_legacy_requires_invoice_input`、`tests/test_pending_invoice_service.py::test_requires_invoice_filter_uses_active_tag_complement` | covered |
| 长期 | 收入规则和支出规则共用版本或互相污染。 | `tests/test_pending_invoice_api.py::test_income_pending_invoice_rules_are_saved_separately_from_expense_rules`、`tests/test_pending_invoice_service.py::test_income_filters_use_pending_output_invoice_rule_groups` | covered |
| 长期 | 候选 relation case id 被当作真实 OA id 请求详情。 | `tests/test_pending_invoice_service.py::test_rows_keep_candidate_case_id_separate_from_real_oa_id`、`web/src/test/PendingInvoicesPage.test.tsx` | covered |
| 长期 | API/read model miss 时同步扫描旧 snapshot 并伪装 fresh。 | `tests/test_pending_invoice_api.py::test_read_model_miss_returns_refreshing_without_sync_scan`、`tests/test_search_pending_sql_runtime.py` | covered |
| 2026-06-13 | filter-options 为生成筛选项读取全量 rows，导致认证态页面 HTTP SLO 长尾。 | `tests/test_pending_invoice_api.py::PendingInvoiceApiTests::test_filter_options_uses_sql_aggregation_after_fresh_gate`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_repository_builds_filter_options_in_sql` | covered |
| 2026-06-14 | direct read model SLO 只刷新月度 shard，未覆盖页面默认 `direction=expense` 使用的 `pending_invoice:expense:all` aggregate scope，导致登录态 HTTP SLO 首屏返回 `refreshing`。 | `tests/test_read_model_slo_smoke.py::ReadModelSloSmokeTests::test_pending_invoice_smoke_includes_page_first_screen_aggregate_scope`、`tests/test_http_slo_probe.py` | covered |
| 2026-06-16 | 页面或调用方请求过大 `page_size`，导致待找发票首屏 rows 长尾或误把全量列表当首屏渲染。 | `tests/test_pending_invoice_service.py::PendingInvoiceQueryServiceTests::test_page_size_limit_protects_first_screen_slo`、`web/src/test/PendingInvoicesPage.test.tsx` | covered |
| 2026-06-16 | 待找发票 export-preview/export 对大匹配集继续分页收集并同步生成 XLSX，拖慢 API 线程和内存；或前端下载路径/导出抽屉吞掉后端超限消息。 | `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_read_model_service_all_rows_rejects_export_row_limit_before_scanning_more_pages`、`tests/test_pending_invoice_api.py::PendingInvoiceApiTests::test_export_endpoints_reject_row_limit_before_xlsx_generation`、`web/src/test/PendingInvoicesApi.test.ts::surfaces backend row-limit messages from failed export downloads`、`web/src/test/PendingInvoicesPage.test.tsx::shows backend export row-limit messages inside the export drawer` | covered |
| 2026-06-17 | 规则抽屉保存成功但页面在 read model 仍 refreshing 时提前恢复可操作，用户仍需手动刷新才能看到新规则结果。 | `web/src/test/PendingInvoicesPage.test.tsx::refetches rows after saving rules and displays refreshed rule filter buckets`、`web/src/test/GlobalOperationOverlayContext.test.tsx` | covered |
| 2026-06-18 | 支出/收入待找发票规则保存 API 已成功，但 `pending_invoice` read model barrier 在 10 秒内仍 refreshing，被全局遮罩误报为“操作失败”。 | `web/src/test/PendingInvoicesRulesSaveTimeout.test.tsx::keeps expense and income rule saves successful when read model freshness wait times out`、`web/src/test/OperationBarrierApi.test.ts::throws timeout error when targets keep refreshing` | covered |
| 2026-06-18 | 待找发票四区表使用 React Aria Collection table 时，正文单元格拖拽无法选中文字。 | `web/e2e/pending-invoices-fanout.spec.ts::allows selecting text in the pending invoice table body` | covered |
| 2026-06-18 | 发票获取状态只能单选且展示“需要开票”中间桶，首屏默认全部，用户需要二次筛到常用的“已支付待开票”。 | `web/src/test/PendingInvoicesPage.test.tsx::supports multi-select invoice acquisition status filters for expense rows`、`web/src/test/PendingInvoicesPage.test.tsx::renders project four-zone table contract and summarizes multiple relations` | covered |
| 长期 | 人工补票 confirm 中途失败后重复创建发票或关系。 | `tests/test_pending_invoice_service.py::test_retry_recovers_invoice_created_before_relation_created`、`tests/test_pending_invoice_service.py::test_retry_recovers_relation_created_before_finalization` | covered |
| 2026-06-12 | relation write safety 不通过时人工补票先创建发票，形成孤儿发票或半写状态。 | `tests/test_pending_invoice_service.py` command service / rollback coverage | covered |
| 2026-06-12 | 待找发票 relation 写入绕过统一 command service，形成页面私有事实源。 | `tests/test_pending_invoice_service.py::test_confirm_manual_invoice_delegates_relation_write_to_command_service`、`tests/test_pending_invoice_service.py::test_confirm_attach_existing_invoice_delegates_relation_write_to_command_service`、`tests/test_pending_invoice_service.py::test_confirm_attach_existing_invoices_batch_delegates_relation_write_to_command_service`、`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_read_models_use_workbench_relation_distribution` | covered |
| 长期 | attach existing 不允许已关联其他付款的发票，阻断合法多付款场景。 | `tests/test_pending_invoice_service.py::test_attach_existing_allows_invoice_already_linked_to_another_bank_payment` | covered |
| 2026-06-17 | 候选表用 `remaining_amount` / “待支付”暗示是否已关联流水，且 preview `can_confirm=false` 时只禁用确认按钮不展示原因。 | `tests/test_pending_invoice_service.py::test_invoice_candidate_with_other_bank_payment_remains_available`、`web/src/test/PendingInvoicesApi.test.ts::maps attach-existing preview conflict objects into readable messages`、`web/src/test/PendingInvoicesPage.test.tsx::shows preview conflicts and keeps confirm disabled when attach-existing cannot be confirmed` | covered |
| 2026-06-17 | 已有 OA+发票 active relation 的进项发票无法在待找发票 attach existing 中并入同一个 active case，或关联台撤回后没有恢复上一状态。 | `tests/test_pending_invoice_service.py::test_invoice_candidates_keep_oa_invoice_relation_available_for_attachment`、`tests/test_pending_invoice_service.py::test_attach_existing_batch_merges_existing_oa_relation_and_withdraw_restores_previous_state` | covered |
| 2026-06-11 | 多条流水选择已有进项发票只能单选流水/单选发票，且前端不展示已选流水金额、已选发票金额和差额。 | `tests/test_pending_invoice_service.py::test_preview_and_confirm_attach_existing_invoices_batch_are_idempotent`、`tests/test_pending_invoice_api.py::PendingInvoiceApiTests::test_batch_attach_existing_invoice_endpoints`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx` | covered |
| 2026-06-11 | 支出状态下拉缺少 `已支付待开票` 和 `已支付已开票` 直接筛选入口。 | `web/src/test/PendingInvoicesPage.test.tsx` | covered |
| 2026-06-15 | 行内三点和补票入口继续暴露，导致旧 manual 新写路径污染待找发票链路。 | `tests/test_pending_invoice_api.py::PendingInvoiceApiTests::test_manual_invoice_endpoints_are_not_reachable`、`web/src/test/PendingInvoicesPage.test.tsx` | covered |
| 2026-06-15 | 收入侧只能逐行标记，前端循环调用单条接口可能造成半成功。 | `tests/test_pending_invoice_service.py::PendingInvoiceApplicationServiceTests::test_confirm_income_status_overrides_batch_is_idempotent_and_fans_out_once`、`tests/test_pending_invoice_service.py::PendingInvoiceApplicationServiceTests::test_confirm_income_status_overrides_batch_rejects_ineligible_rows_before_writing`、`web/src/test/PendingInvoicesPage.test.tsx` | covered |
| 2026-06-15 | `filter=requires_invoice` 被错误耦合到 `filter_group='requires_invoice'`，生产中 `filter_group=all` 但状态为 `paid_pending_invoice` / `paid_invoiced` 的行被筛空。 | `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_repository_requires_invoice_filter_uses_status_bucket`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_sql_projection_uses_active_complement_for_requires_invoice_filter`、`tests/test_pending_invoice_service.py::PendingInvoiceQueryServiceTests::test_expense_status_priority_uses_rules_and_invoice_payment_facts` | covered |

## 关键 smoke flows

1. `发票导入确认 -> invoice_lifecycle refresh -> pending_invoice/read search dirty scope -> pending-invoice/search workers -> /pending-invoices rows fresh`
2. `待找发票规则保存 -> pending_invoice_rules_changed lifecycle -> pending/invoice_lifecycle/workbench/tax/cost/search refresh -> 不刷新 no_oa/bank balance/turnover`
3. `选择已有发票 candidates(流水关联 chip) -> preview(conflicts/warnings/关联后待付) -> confirm -> relation/audit/finalizer -> affected months -> relation/detail/drawer 刷新`
4. `多选支出流水 -> 批量候选进项发票 -> 多选发票 -> preview 汇总本次选择差额 -> confirm 合并兼容 bank/invoice/oa relation 写一条 active relation -> 关联台 withdraw 恢复上一状态 -> 页面 refetch`
5. `多选收入流水 -> 批量标记 no invoice required/cash income -> pending_invoice_income_status_override_confirmed -> pending/search refresh -> 税金/成本不误刷`
6. `manual invoice legacy command retry -> command log 恢复旧中断状态；HTTP/UI 新入口保持不可达`
7. `关联台 confirm -> workbench relation distribution -> pending invoice read model rows fresh -> 待找发票从已支付待开票更新为已支付已开票，并显示发票和 OA`
8. `candidate relation -> 待找发票显示候选发票/OA 证据，但仍保持已支付待开票，不把 candidate 计入 linked-only 开票状态`
9. `relation-backed pending invoice read model refreshing/stale -> 页面显示刷新/读模型诊断；refreshing 保留选择发票入口，stale 空 rows 不伪装真实空`

## 本模块验证命令

最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_pending_invoice_api tests.test_invoice_lifecycle_page_integration -v
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_pending_invoice_relation_identity tests.test_pending_invoice_oa_identity_backfill -v
PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service.PendingInvoiceQueryServiceTests.test_page_size_limit_protects_first_screen_slo -v
cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/PendingInvoicesPage.test.tsx
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

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend Vitest、build 和 deterministic Playwright smoke，覆盖完整待找发票、SQL projection、invoice lifecycle、App Status 和前端测试集，并覆盖真实 Chromium 中 Workbench confirm 后待找发票行状态更新、candidate relation 只展示候选证据不驱动 `已支付已开票` 状态，以及 relation-backed read model 非 fresh 诊断。单轮模块验证只跑最小闭环。

## 未测风险

- 本地测试不连接真实生产 Postgres 大数据量，不验证真实搜索/待找发票 SQL projection 的 EXPLAIN、锁等待或长尾分页性能。
- 本地测试不跑真实 RabbitMQ/Redis/systemd `pending-invoice`、`search` 与 invoice-lifecycle worker drain；dirty/outbox 到 projection 的最终收敛需要 staging 或夜间 CI/生产前 smoke。
- 本地已覆盖待找发票超过 20,000 行导出 fail-closed；当前 Browser e2e 覆盖 Workbench confirm fan-out、candidate/linked 负面语义和 relation-backed read model 非 fresh 诊断，但不覆盖 withdraw、真实浏览器下载、文件打开、大文件下载耗时和真实网络中断恢复。

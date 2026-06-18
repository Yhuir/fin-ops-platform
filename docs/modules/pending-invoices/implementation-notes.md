# 待找发票 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 待找发票行状态由 `InvoiceLifecyclePolicy` / `invoice_lifecycle` read boundary 与 pending invoice read model 表达，页面不得在字段缺失时自行推断状态或 primary action。
- 支出规则版本是 `pending_invoice_tag_groups.version`，收入规则版本是 `pending_output_invoice_tag_groups.version`；二者独立，且都不同于 `bank_transaction_tags.version`。
- `requires_invoice` 是 active tag complement，由后端实时派生；保存规则时即使请求包含该字段也必须忽略。
- `requires_invoice` 作为列表 filter 是最终状态桶；支出状态桶包含 `paid_pending_invoice`、`paid_invoiced`、`paid_pending_future_invoice`、`invoice_not_fully_paid`，收入状态桶包含 `income_pending_invoice`、`income_invoiced`。`filter_group` / `matched_rule` 只解释规则命中，不能作为 rows/filter-options/export 的父筛选可见性条件。
- rows、filter-options、export-preview 和 export 必须先经过 `PendingInvoiceReadModelService` 的 freshness gate；非 fresh 时不能把空 rows 当真实结果。
- filter-options 在 fresh gate 通过后应优先走 SQL 聚合读取选项，不再为生成筛选项拉取全量 rows；这属于页面首屏性能路径，不能回退到伪 fresh。
- export-preview 和 export 通过 `PendingInvoiceReadModelService.all_rows()` 收集当前筛选结果时，超过 20,000 行必须 fail-closed，不能继续分页并同步生成大 XLSX。
- OA/流水/发票 relation 不是待找发票私有事实；当前页面只通过 attach existing 写入选择已有发票关系，且必须委托 `WorkbenchRelationCommandService`；读取既有关系必须通过 `WorkbenchRelationReadFacade` / `workbench_relation` distribution。
- 选择已有进项发票候选表的“流水关联”chip 必须使用后端返回的 `bank_relation_status` / `linked_bank_transaction_count`，不能用 `remaining_amount=0` 或候选金额推断；最终补付金额以 preview `payment_impact.remaining_amount_after` 为准。
- attach existing 可并入兼容的 bank+invoice 或 OA+invoice active relation；confirm 后如果从关联台 withdraw 新 active case，必须恢复 confirm 前上一 active relation 状态。
- manual invoice 不再是当前待找发票 HTTP/UI 新写入口；历史 `preview_manual_invoice` / `confirm_manual_invoice` 只保留旧 command 恢复和迁移兼容。
- 收入状态覆盖必须走批量 service/API 边界，先整批校验再一次写 command/audit/finalizer，不能由前端循环单条接口形成半成功。
- 2026-06-15 测试闭环审计确认：现有 P0/P1 覆盖支出/收入状态、规则保存、manual 新写入口移除、历史 manual command 兼容、attach existing、income status batch、API 契约、SQL read model、worker fan-out、lifecycle fan-out、App Status 和前端交互。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-17 - 选择已有发票候选关系 chip 与 active case restore

- 目标：修复“选择已有进项发票”预览后确认按钮不可解释地禁用的问题，并把候选表“待支付”列替换为后端事实驱动的“流水关联”chip；同时确保已有 OA+发票关系能与本次选择的流水/发票合并进同一 active case，关联台撤回恢复上一状态。
- 影响范围：`PendingInvoiceQueryService` candidates、`PendingInvoiceApplicationService` attach existing 合并规则、`PendingInvoiceInvoicePickerDrawer`、前端 pending invoice API/types、API/module 文档和服务/API/前端测试。
- 关键决策：候选表继续保留后端 `remaining_amount` 兼容字段，但 UI 不用它表达流水关联；新增 `bank_relation_status` 和 `linked_bank_transaction_count`。preview 中 `selection_summary.difference_amount` 只表示本次选择差额，最终补付看 `payment_impact.remaining_amount_after`。兼容 active relation 的 row types 限定为 `bank` / `invoice` / `oa`，未知 row type 仍按冲突处理。
- 文档影响：更新 `docs/dev/api-contracts.md`、本模块 `README.md`、`state-machine.md`、`tests.md` 和本实施记录。
- 测试覆盖：新增/更新 `tests/test_pending_invoice_service.py` 覆盖 candidate chip 状态、OA+invoice 可并入和 withdraw restore；更新 `tests/test_pending_invoice_api.py` 覆盖 batch candidate 字段；更新 `web/src/test/PendingInvoicesApi.test.ts` 覆盖 mapper 和 conflict object 文案；更新 `web/src/test/PendingInvoicesPage.test.tsx` 覆盖 chip、差额标签、preview 冲突原因和禁用确认。
- 验证命令：`PYTHONPATH=backend/src python -m unittest tests.test_pending_invoice_service.PendingInvoiceQueryServiceTests tests.test_pending_invoice_service.PendingInvoiceApplicationServiceTests tests.test_pending_invoice_api.PendingInvoiceApiTests.test_batch_attach_existing_invoice_endpoints -v`；`cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/PendingInvoicesPage.test.tsx`。
- 未测风险：本地未跑真实浏览器截图和真实 Workbench 页面 withdraw 操作；withdraw restore 由 service-level canonical relation command 覆盖。真实 Postgres/RabbitMQ/Redis worker drain 仍需 staging 或夜间 CI。
- 后续事项：可在 staging 用真实“OA+发票+多流水+多发票”样本做一次关联台展示和撤回人工 smoke。

## 2026-06-16 - P2/P3 导出全量收集上限

- 目标：收敛待找发票大数据导出风险，避免 export-preview/export 在命中大匹配集时继续按 200 行分页收集并同步生成 XLSX，拖慢 API 线程和内存。
- 影响范围：`PendingInvoiceReadModelService.all_rows()`、`PendingInvoiceQueryService` 旧 export helper、待找发票 API 回归测试、SQL/runtime 测试矩阵和 P2/P3 闭环台账。
- 关键决策：与银行明细、进项发票使用情况导出保持同一类 fail-closed 语义；超过 20,000 行返回 `pending_invoice_export_row_limit_exceeded`，错误 details 包含 `total` 和 `limit`，并要求用户缩小筛选范围。
- 文档影响：更新 `tests.md`、本实施记录和 `.planning/P2P3-CLOSURE-PLAN.md`；产品/API 长期口径未单独扩展，因为这是性能保护边界，不新增用户流程。
- 测试覆盖：新增 `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_read_model_service_all_rows_rejects_export_row_limit_before_scanning_more_pages`，验证超限只读第一页；新增 `tests/test_pending_invoice_api.py::PendingInvoiceApiTests::test_export_endpoints_reject_row_limit_before_xlsx_generation`，验证 preview/download API 结构化错误。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_pending_invoice_read_model_service_all_rows_rejects_export_row_limit_before_scanning_more_pages tests.test_pending_invoice_api.PendingInvoiceApiTests.test_export_endpoints_reject_row_limit_before_xlsx_generation -v`。
- 未测风险：真实浏览器下载、文件打开、生产数据 EXPLAIN、网络中断恢复和下载耗时仍需 staging/manual smoke；本地只证明超大匹配集不会继续同步生成 XLSX。
- 后续事项：继续推进 P2/P3 final gated smoke，收集真实登录态 HTTP/SSE/read model/write evidence。

## 2026-06-16 - P2/P3 首屏分页性能护栏证据

- 目标：补齐待找发票在 P2/P3 一秒级同步推进中的本地首屏有界请求证据，避免 rows API 被页面或调用方当作全量拉取路径。
- 影响范围：`PendingInvoiceQueryService` service 测试、`PendingInvoicesPage` 前端回归测试、模块测试矩阵和 P2/P3 闭环台账；未改变业务代码、HTTP contract 或页面默认行为。
- 关键决策：页面默认首屏保持 `page=1&page_size=50`，用户控件限制为 25/50/100；service 对异常大的 `page_size` 继续按既有 contract 夹到 200，而不是改成 `invalid_paging`，避免改变老调用方语义。
- 文档影响：更新 `tests.md` 和本实施记录；长期 API/产品文档不变，因为本轮只补测试证据。
- 测试覆盖：新增 `tests/test_pending_invoice_service.py::PendingInvoiceQueryServiceTests::test_page_size_limit_protects_first_screen_slo`；更新 `web/src/test/PendingInvoicesPage.test.tsx` 断言首屏 rows 请求和页大小选项。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service.PendingInvoiceQueryServiceTests.test_page_size_limit_protects_first_screen_slo -v`；`npm --prefix web test -- --run src/test/PendingInvoicesPage.test.tsx`。
- 未测风险：本地合成数据不验证真实 PostgreSQL EXPLAIN、索引选择、锁等待、浏览器长表滚动或大文件导出下载；这些仍属于 staging/生产 smoke。
- 后续事项：P2/P3 闭环继续处理成本统计首屏/导出性能证据和真实登录态 HTTP SLO。

## 2026-06-15 - 修复 requires_invoice 状态桶筛空

- 目标：修复待找发票“需要开票 / 已支付待开票 / 已支付已开票”筛选在生产数据中返回空结果的问题，禁止旧 `filter_group='requires_invoice'` 假设继续污染 rows、filter-options、export 和 projection scope。
- 影响范围：`pending_invoice_status` 状态筛选 helper、`PendingInvoiceQueryService` fallback、`PostgresReadModelRepository` pending invoice rows/filter-options SQL、`SearchPendingSqlProjectionBuilder` pending invoice scope projection、模块/API/产品文档和测试矩阵。
- 关键决策：列表父筛选以最终 `invoice_acquisition_status.code` 为事实源；`filter_group` / `matched_rule` 只保留规则解释和规则列表头筛选。收入 `cash_income` 保持独立状态桶，不再混入 `requires_invoice`。
- 文档影响：更新 `docs/product-specs/invoice-lifecycle.md`、`docs/dev/api-contracts.md`、`state-machine.md`、`tests.md` 和本实施记录。
- 测试覆盖：新增/更新 repository SQL、SQL projection、service fallback 测试，覆盖 `filter_group=all` 但状态为待/已开票的生产形态、income cash override 不污染 requires bucket、projection scope row_count 口径。
- 验证命令：见最终交付说明。
- 未测风险：本地 fake repository 不执行真实 PostgreSQL EXPLAIN；真实生产 rows/filter-options/export 性能和 worker drain 仍需 staging 或发布后 smoke。
- 后续事项：发布后对生产 `expense:requires_invoice` 和状态快捷筛选执行一次 read model refresh/smoke，确认旧 `filter_group=all` 行能被返回。

## 2026-06-15 - 移除补票入口并闭环收入批量状态

- 目标：移除待找发票行内三点按钮和“补票”新入口；支出侧只保留选中工具栏“选择发票”；收入侧增加多选后批量“标记无需开票/标记现金收入”。
- 影响范围：pending invoice routes/application service/status action、SQL projection、`PendingInvoicesPage`、`PendingInvoicesTable`、relation drawer、pending invoice API/types、模块/API/产品/页面架构文档和相关测试。
- 关键决策：manual invoice HTTP preview/confirm 返回 `not_found`；历史 manual command/service/table 保留为旧数据恢复兼容。收入批量状态复用 income status command/audit/finalizer/projection 模式，先拒绝重复 ID、非收入流水、已关联发票和非法状态，再一次写入并合并 affected months。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md`、本实施记录、`docs/dev/api-contracts.md`、`docs/product-specs/invoice-lifecycle.md` 和 `docs/app-architecture/pages.md`。
- 测试覆盖：新增/更新 backend service/API、SQL projection 兼容、frontend page/API mapper 测试，覆盖 manual 新入口不可达、历史 command 恢复、支出选中工具栏、收入批量状态和旧 UI/API 移除。
- 验证命令：见最终交付说明。
- 未测风险：真实生产 worker drain 和大数据量样本仍按运维 smoke 验证。
- 后续事项：发布后用真实支出多流水/多发票样本和收入多选样本核对页面筛选、刷新状态与审计记录。

## 2026-06-13 - filter-options fresh-gated SQL 聚合

- 目标：把待找发票筛选项从全量 rows Python 聚合改为 fresh gate 后的 PostgreSQL 聚合，降低认证态页面 HTTP SLO 长尾。
- 影响范围：`PendingInvoiceReadModelService.filter_options(...)`、pending invoice route、`PostgresReadModelRepository.list_pending_invoice_filter_options(...)`、HTTP SLO probe 默认待找发票探针。
- 关键决策：filter-options 仍必须先通过 rows freshness/source-version gate；SQL 只读取 `read_model.pending_invoice_rows` 中符合方向、业务筛选、日期、关键字和表头筛选的候选值，并按 field/count/value 取前 50 个选项。
- 文档影响：更新本实施记录和测试矩阵。
- 测试覆盖：`tests/test_pending_invoice_api.py::PendingInvoiceApiTests::test_filter_options_uses_sql_aggregation_after_fresh_gate`、`tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_repository_builds_filter_options_in_sql`、`tests/test_http_slo_probe.py`。
- 验证命令：见最终交付说明。
- 未测风险：本地 repository fake 不执行真实 PostgreSQL EXPLAIN；生产 authenticated HTTP SLO 需要发布后用真实登录态验证。
- 后续事项：如果真实数据下仍有长尾，继续用 `pg_stat_statements` / EXPLAIN 优化 `read_model.pending_invoice_rows` 筛选列索引。

## 2026-06-11 - 多流水选择已有进项发票闭环

- 目标：待找发票页面支持选择多条支出流水，在“选择已有进项发票”右侧抽屉中选择多张进项发票，并展示已选流水金额、已选发票金额和差额；同时保留原页面四区表 UI 和单条行菜单入口。
- 影响范围：`PendingInvoiceQueryService`、`PendingInvoiceApplicationService`、`routes_pending_invoices.py`、`server.py` pending invoice routes、`PendingInvoicesPage`、`PendingInvoicesTable`、`PendingInvoiceInvoicePickerDrawer`、前端 pending invoices API/types、模块/API 文档和相关测试。
- 关键决策：批量选择复用 Workbench active pair relation 作为关系事实源；单条入口也走同一批量抽屉。状态下拉中的 `已支付待开票` / `已支付已开票` 不新增后端规则组，而是前端映射为 `filter=requires_invoice` 加 `status_code` 表头筛选。
- 文档影响：更新 `docs/dev/api-contracts.md`、本模块 `README.md`、`state-machine.md`、`tests.md` 和本实施记录。
- 测试覆盖：新增/更新 `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx`，覆盖批量 candidates、preview、confirm、幂等、页面多选和状态快捷筛选。
- 验证命令：`pytest tests/test_pending_invoice_service.py tests/test_pending_invoice_api.py -q`；`cd web && npm test -- PendingInvoicesApi.test.ts PendingInvoicesPage.test.tsx --run`；`cd web && npm run build`。
- 未测风险：本地未连接真实生产 Postgres/Redis/RabbitMQ，不验证真实 worker drain 或大数据量页面滚动性能；需要 staging 用真实月份做批量选择 smoke。
- 后续事项：发布前可用包含多 OA、多付款流水、多发票的真实 relation 样本核对待找发票、OA 待付款和关联台详情展示一致性。

## 2026-06-11 - 待找发票测试闭环矩阵与状态机补齐

- 目标：执行 testing closure master goal 的 `pending-invoices` 模块轮次，确认新功能改动不会绕过规则版本、人工补票、选择已有发票、收入状态、read model freshness、invoice lifecycle 或页面交互回归保护。
- 影响范围：`docs/modules/pending-invoices/README.md`、`docs/modules/pending-invoices/tests.md`、`docs/modules/pending-invoices/state-machine.md`、`docs/modules/pending-invoices/implementation-notes.md`；未改变业务代码或测试代码。
- 关键决策：现有 P0/P1 自动化测试已覆盖支出/收入待找发票状态、规则 active complement、支出/收入规则版本隔离、manual preview/confirm、attach existing preview/confirm、income status override、API shape、SQL read model fresh/stale/missing/source mismatch、worker scope fan-out、lifecycle fan-out、App Status 和前端 rules/detail/manual/attach/filter/refreshing 交互；本轮不新增重复测试。
- 文档影响：补齐模块必读事实源、代码入口、七类测试矩阵、影响面清单、关键 smoke flows、历史 bug 回归库、状态机和 remaining risk。
- 测试覆盖：沿用 `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_search_pending_sql_runtime.py`、`tests/test_pending_invoice_relation_identity.py`、`tests/test_pending_invoice_oa_identity_backfill.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_pending_invoice_api tests.test_invoice_lifecycle_page_integration -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_pending_invoice_relation_identity tests.test_pending_invoice_oa_identity_backfill -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_runtime_worker_registry -v`；`cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/PendingInvoicesPage.test.tsx`。
- 未测风险：未连接真实生产 Postgres 大数据量，不验证真实 SQL projection EXPLAIN、锁等待或长尾分页性能；未跑真实 RabbitMQ/Redis/systemd search-pending 与 invoice-lifecycle worker drain；未做真实浏览器大文件导出和网络中断恢复 smoke。
- 后续事项：下一轮处理 `oa-pending-payments`，重点审计 OA/bank/invoice detail、read model freshness、filter-options 和 invoice lifecycle fan-out。

## 2026-06-18 - pending invoice relation source freshness gate

- 目标：修复关联台 relation 已更新但待找发票 `/api/pending-invoices/rows` 仍把旧的无 OA pending row 当作 fresh 返回的问题。
- 影响范围：`PendingInvoiceReadModelService` expected-source provider、`PostgresReadModelRepository` pending invoice source-version 聚合、`tests/test_search_pending_sql_runtime.py`。
- 关键决策：`SearchPendingSqlProjectionBuilder` 已在写入 `read_model.pending_invoice_scopes.source_versions` 时保存 `workbench_relation_source_versions`；API expected-source gate 必须从当前 pending rows 命中的月份读取 `read_model.workbench_relation_scopes.source_versions` 并纳入比较。base scope 聚合时同时保留 `bank_detail_source_versions` 和 `workbench_relation_source_versions` 的按月版本，避免 aggregate scope 丢失 relation freshness。
- 文档影响：更新本模块测试矩阵和历史 bug 回归库。
- 测试覆盖：新增 `tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_pending_invoice_api_workbench_relation_source_version_stale_enqueues_refresh`、`test_pending_invoice_api_workbench_relation_source_version_mismatch_enqueues_refresh`、`test_pending_invoice_repository_aggregates_bank_detail_source_versions_across_month_shards` relation 断言、`test_pending_invoice_repository_loads_workbench_relation_source_versions_for_matching_months`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_search_pending_sql_runtime.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_api.py -q`。
- 未测风险：未连接真实生产 Postgres 验证 23053.31 原始数据行，但 freshness 契约已覆盖同类 stale 机制；真实 worker drain 仍按运维 smoke 验证。

## 2026-06-12 - relation 写入口迁入 workbench relation command service

- 目标：让待找发票 manual invoice confirm、attach existing 单条和批量不再直接写 `WorkbenchPairRelationService`，统一委托 workbench relation 模块，避免待找发票页面形成独立关系事实源。
- 影响范围：`PendingInvoiceApplicationService`、`WorkbenchRelationCommandService`、`Application` dependency wiring、`tests/test_pending_invoice_service.py`、本模块 README/tests 和 `docs/modules/workbench-relations/*`。
- 关键决策：manual/attach 写 relation 走 `WorkbenchRelationCommandService.confirm_relation(...)`；写前读取既有 active relation 只走 `WorkbenchRelationReadFacade.get_by_row_ids(...)` 的 distribution payload；缺少 command service 时 fail fast。manual invoice confirm 在创建发票前先调用 relation write precondition，relation read model stale 时不创建发票并把 pending command 标记为 `failed_recoverable`。
- 文档影响：更新本模块 `README.md`、`tests.md`、本实施记录，以及 `workbench-relations` 模块 README/tests/implementation-notes。
- 测试覆盖：新增/更新 `tests/test_pending_invoice_service.py`，覆盖 manual/attach 单条/批量委托 command service、stale fail-fast、不产生孤儿发票、命令可恢复状态；保留 pending invoice API 旧 shape 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_service.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_api.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_read_models_use_workbench_relation_distribution -q`；`python3 -m compileall -q backend/src/fin_ops_platform/services/pending_invoice_service.py backend/src/fin_ops_platform/services/workbench_relation_command_service.py`。
- 未测风险：HTTP 层尚未单独断言 relation read model stale 的 error shape；真实 Postgres 并发 row occupation 仍未用锁或唯一占用约束保护；跨页面真实 worker drain 仍需 staging smoke。
- 后续事项：迁移 no-OA submit/withdraw/internal transfer confirm-link，继续消除剩余 relation 写事实源。

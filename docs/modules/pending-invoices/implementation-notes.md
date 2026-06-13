# 待找发票 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 待找发票行状态由 `InvoiceLifecyclePolicy` / `invoice_lifecycle` read boundary 与 pending invoice read model 表达，页面不得在字段缺失时自行推断状态或 primary action。
- 支出规则版本是 `pending_invoice_tag_groups.version`，收入规则版本是 `pending_output_invoice_tag_groups.version`；二者独立，且都不同于 `bank_transaction_tags.version`。
- `requires_invoice` 是 active tag complement，由后端实时派生；保存规则时即使请求包含该字段也必须忽略。
- rows、filter-options、export-preview 和 export 必须先经过 `PendingInvoiceReadModelService` 的 freshness gate；非 fresh 时不能把空 rows 当真实结果。
- filter-options 在 fresh gate 通过后应优先走 SQL 聚合读取选项，不再为生成筛选项拉取全量 rows；这属于页面首屏性能路径，不能回退到伪 fresh。
- OA/流水/发票 relation 不是待找发票私有事实；manual invoice 和 attach existing 写入必须委托 `WorkbenchRelationCommandService`，读取既有关系必须通过 `WorkbenchRelationReadFacade` / `workbench_relation` distribution。
- 2026-06-11 测试闭环审计确认：现有 P0/P1 覆盖支出/收入状态、规则保存、人工补票、attach existing、income status、API 契约、SQL read model、worker fan-out、lifecycle fan-out、App Status 和前端交互；本轮不新增重复代码测试，主要补齐模块测试矩阵和状态机文档。

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

## 2026-06-12 - relation 写入口迁入 workbench relation command service

- 目标：让待找发票 manual invoice confirm、attach existing 单条和批量不再直接写 `WorkbenchPairRelationService`，统一委托 workbench relation 模块，避免待找发票页面形成独立关系事实源。
- 影响范围：`PendingInvoiceApplicationService`、`WorkbenchRelationCommandService`、`Application` dependency wiring、`tests/test_pending_invoice_service.py`、本模块 README/tests 和 `docs/modules/workbench-relations/*`。
- 关键决策：manual/attach 写 relation 走 `WorkbenchRelationCommandService.confirm_relation(...)`；写前读取既有 active relation 只走 `WorkbenchRelationReadFacade.get_by_row_ids(...)` 的 distribution payload；缺少 command service 时 fail fast。manual invoice confirm 在创建发票前先调用 relation write precondition，relation read model stale 时不创建发票并把 pending command 标记为 `failed_recoverable`。
- 文档影响：更新本模块 `README.md`、`tests.md`、本实施记录，以及 `workbench-relations` 模块 README/tests/implementation-notes。
- 测试覆盖：新增/更新 `tests/test_pending_invoice_service.py`，覆盖 manual/attach 单条/批量委托 command service、stale fail-fast、不产生孤儿发票、命令可恢复状态；保留 pending invoice API 旧 shape 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_service.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_api.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_read_models_use_workbench_relation_distribution -q`；`python3 -m compileall -q backend/src/fin_ops_platform/services/pending_invoice_service.py backend/src/fin_ops_platform/services/workbench_relation_command_service.py`。
- 未测风险：HTTP 层尚未单独断言 relation read model stale 的 error shape；真实 Postgres 并发 row occupation 仍未用锁或唯一占用约束保护；跨页面真实 worker drain 仍需 staging smoke。
- 后续事项：迁移 no-OA submit/withdraw/internal transfer confirm-link，继续消除剩余 relation 写事实源。

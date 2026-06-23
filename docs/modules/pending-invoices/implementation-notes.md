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

## 2026-06-23 - 多 OA / 多流水 / 多发票 `+N` 聚合展示

- 目标：让待找发票列表严格按统一 `workbench_relation` distribution 显示 OA、银行流水和发票配对关系；当同一 relation 下某类成员大于 1 时，该栏只显示代表全部成员的 `+N`，点击后只展开对应类型明细。
- 影响范围：`PendingInvoiceQueryService`、`SearchPendingSqlProjectionBuilder`、`PendingInvoiceApiRoutes.relation_detail`、pending invoice API mapper/types、`PendingInvoicesTable`、`PendingInvoiceRelationDrawer`、本模块文档和 API/product 合同。
- 关键决策：不新建页面私有事实源；rows 新增向后兼容的 `bank_transactions` 分区，`input_invoices` / `oa` 沿用 relation count 和 summaries。多笔流水属于同一 relation 时只输出一条聚合行，成员不再重复作为 standalone 行；`kind=bank|invoice|oa` 只过滤关系详情的展示列表，不改变金额汇总和 relation case 事实。
- 文档影响：更新 `docs/product-specs/invoice-lifecycle.md`、`docs/dev/api-contracts.md`、`README.md`、`state-machine.md`、`tests.md` 和本实施记录。
- 测试覆盖：新增 query service fallback 和 SQL projection 多流水 relation 聚合测试；扩展 relation detail kind 过滤测试；扩展前端 API mapper 和页面测试，覆盖 `bankTransactions`、多项只显示 `+N`、不展示 primary 重复项，以及 `+N` 分栏抽屉只显示发票/流水/OA 对应列表。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_search_pending_sql_runtime tests.test_pending_invoice_api -v`；`cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/PendingInvoicesPage.test.tsx`。
- 未测风险：本地未跑真实 Browser E2E、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain，也未用真实跨月 relation 样本验证“一个 relation 横跨多个 month shard”时的展示 owner 选择；当前实现按单次 rows 构建去重，跨月 aggregate scope 如存在同一 relation 的多个 owner month 仍需 staging 数据验证。
- 后续事项：如生产确认存在跨月多流水 relation，应补充 owner month 规则和 SQL projection/repository 回归；导出是否完全镜像 grouped row 的明细拼接仍需在下一轮导出专项验证。

## 2026-06-20 - rules save mutation 暂时失败草稿重试恢复

- 目标：补齐待找发票规则保存的 mutation 级 `NETWORK-RECOVERY` Browser 负面链路，防止保存暂时失败时误触发 freshness barrier/rows refresh、丢失草稿，或留下被抽屉 top-layer 拦截的不可点击全局错误弹窗。
- 影响范围：`web/src/contexts/GlobalOperationOverlayContext.tsx`、`web/src/pages/PendingInvoicesPage.tsx`、`web/src/test/GlobalOperationOverlayContext.test.tsx`、`web/e2e/fixtures/apiMocks.ts`、`web/e2e/pending-invoices-rules-save-flow.spec.ts`、本模块测试/覆盖文档和全局 Spec-first inventory。
- 关键决策：规则抽屉已经有本地错误提示和草稿状态，保存失败应回到抽屉内联错误并允许用户直接重试；因此 `runOperation` 新增 `blockOnError=false` 选项，待找发票规则保存只使用全局 overlay 表达 loading/progress，不在失败后留下全局阻塞错误层。默认 `runOperation` 失败仍保持阻塞直到用户确认，避免影响其它页面。
- 文档影响：更新 `e2e-spec.md`、`e2e-coverage.md`、`tests.md`、`docs/dev/testing.md`、`docs/dev/spec-first-e2e-inventory.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：deterministic mock 新增 `pendingInvoiceRulesSaveFailuresBeforeSuccess`，Browser 覆盖第一次 `PUT /api/pending-invoices/rules` 返回 503、抽屉内错误可见、`设备款` 草稿勾选保持、全局操作弹窗不存在、`operation-barrier/status` 和 rows 不触发；第二次保存 200 后才等待 `pending_invoice:expense:requires_invoice` barrier、rows refetch、刷新中反馈和无成功后错误残留。Vitest 覆盖 `GlobalOperationOverlayProvider` 的默认阻塞错误行为不变，以及 `blockOnError=false` 时失败后 overlay 立即清除。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-rules-save-flow.spec.ts --project=chromium`；`cd web && npm test -- --run src/test/GlobalOperationOverlayContext.test.tsx`。
- 未测风险：本地 mock 不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `pending-invoice`、`search`、`invoice-lifecycle` worker drain，也不覆盖 withdraw 等其它 mutation 的真实网络中断恢复。
- 后续事项：继续把 withdraw 或未来新增待找发票写入口的失败恢复迁入 Browser/staging smoke；真实 worker 最新性仍走 `infra-smoke` / staging gate。

## 2026-06-20 - income status mutation 暂时失败重试恢复

- 目标：补齐待找发票收入批量状态的 mutation 级 `NETWORK-RECOVERY` Browser 负面链路，防止保存暂时失败时页面清空选择、刷新 rows、显示假成功或形成半写状态。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/pending-invoices-income-status-flow.spec.ts`、本模块测试/覆盖文档和全局 Spec-first inventory。
- 关键决策：不改产品逻辑；现有页面在 `savePendingInvoiceIncomeStatuses` 失败时保留选中流水、展示后端错误，并在 `finally` 恢复按钮，本轮只加固 deterministic mock 和 Browser 断言，把“失败可见、选中保持、无半写、可重试、成功后才刷新”固定为页面合同。
- 文档影响：更新 `e2e-spec.md`、`e2e-coverage.md`、`tests.md`、`docs/dev/testing.md`、`docs/dev/spec-first-e2e-inventory.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：deterministic mock 新增 `pendingInvoiceIncomeStatusFailuresBeforeSuccess`，Browser 覆盖第一次 `PUT /api/pending-invoices/income-statuses` 返回 503、错误提示可见、选中 2 条流水保持、rows 请求数不变、原 rows 保持 `未开票`；第二次保存 200 后 rows refetch、两条流水更新为 `现金收入`、选择清空且无成功后错误残留。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-income-status-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `pending-invoice`、`search`、`invoice-lifecycle` worker drain，也不覆盖 withdraw 等其它 mutation 的真实网络中断恢复。
- 后续事项：rules save 暂时失败草稿重试恢复已由后续 Browser 覆盖；继续把 withdraw 等其它待找发票 mutation 失败恢复迁入 Browser/staging smoke；真实 worker 最新性仍走 `infra-smoke` / staging gate。

## 2026-06-20 - attach existing confirm mutation 暂时失败重试恢复

- 目标：补齐待找发票“选择已有发票”关系确认的 mutation 级 `NETWORK-RECOVERY` Browser 负面链路，防止 confirm 暂时失败时页面关闭抽屉、刷新 rows、显示假成功或形成半写状态。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/pending-invoices-attach-existing-flow.spec.ts`、本模块测试/覆盖文档和全局 Spec-first inventory。
- 关键决策：不改产品逻辑；现有抽屉已经在 `confirmAttach` 失败时保留 drawer/preview/选择并展示后端错误，本轮只加固 deterministic mock 和 Browser 断言，把“失败可见、无半写、可重试、成功后才刷新”固定为页面合同。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、`docs/dev/testing.md`、`docs/dev/spec-first-e2e-inventory.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：deterministic mock 新增 `pendingInvoiceAttachExistingConfirmFailuresBeforeSuccess`，Browser 覆盖第一次 `POST /api/pending-invoices/attach-existing-invoices` 返回 503、错误提示可见、drawer 仍打开、确认按钮可重试、rows 请求数不变、原 rows 保持 `已支付待开票` 且不出现发票号；第二次 confirm 200 后 drawer 关闭、rows refetch、两条流水更新为 `已支付已开票` 且无成功后错误残留。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-attach-existing-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `pending-invoice`、`search`、`invoice-lifecycle` worker drain，也不覆盖 withdraw 等其它 mutation 的真实网络中断恢复。
- 后续事项：income status 和 rules save 暂时失败重试恢复已由后续 Browser 覆盖；继续把 withdraw 等其它待找发票 mutation 失败恢复迁入 Browser/staging smoke；真实 worker 最新性仍走 `infra-smoke` / staging gate。

## 2026-06-20 - rows 加载失败刷新恢复 Browser E2E

- 目标：补齐待找发票页面级 `NETWORK-RECOVERY` 负面链路，防止 rows 首屏请求临时失败时被误看成真实空数据或继续允许导出。
- 影响范围：`web/src/components/pendingInvoices/PendingInvoicesTable.tsx`、`web/src/pages/PendingInvoicesPage.tsx`、`web/e2e/fixtures/apiMocks.ts`、`web/e2e/pending-invoices-filter-sort-flow.spec.ts`、本模块测试/覆盖文档和全局 Spec-first inventory。
- 关键决策：保留现有刷新按钮交互，不新增产品流程；表格支持错误态空行文案，`PendingInvoicesPage` 在 `error` 存在时禁用导出并显示“待找发票加载失败，请点击刷新重试。”，避免正常空态和失败态混淆。
- 测试覆盖：deterministic mock 新增 `pendingInvoiceRowsFailuresBeforeSuccess`，Browser 覆盖首屏 `/api/pending-invoices/rows` 暂时 503、错误提示、非正常空态、导出禁用、点击刷新后 rows 200 恢复、错误消失和导出重新可用。
- 未测风险：本地 mock 只覆盖 rows 首屏失败恢复；attach existing confirm、income status 保存和 rules save 暂时失败重试恢复已由后续 Browser 覆盖，其它 mutation 的真实网络中断和真实 worker drain 仍需后续 Browser/staging smoke。

## 2026-06-19 - Relation 导出成功路径 UI 错误残留 guard

- 目标：补齐待找发票 relation 字段导出 Browser 成功链路的“假成功”检测，防止 export-preview/download 成功后页面仍残留导出失败、同步失败或 read model 失败提示。
- 影响范围：`web/e2e/pending-invoices-export-download.spec.ts`、`tests/test_playwright_e2e_strict_diagnostics.py`、本模块测试文档、workbench relation 覆盖矩阵和全局 testing 文档。
- 关键决策：只加固成功下载路径；row-limit 仍是 negative path，继续断言错误文案可见且不产生 download event。
- 文档影响：更新 `tests.md`、`docs/dev/testing.md`、`docs/dev/testing-closure-state.md` 和 `docs/modules/workbench-relations/e2e-coverage.md`。
- 测试覆盖：Workbench confirm 后 export-preview/export 带当前筛选和排序、不带分页、真实 download event 内容包含 OA/发票/relation 字段，随后调用 `expectNoUnexpectedSuccessUiErrors`；静态诊断防止后续移除。
- 验证命令：`cd web && npx playwright test e2e/bank-details-category-flow.spec.ts e2e/bank-details-export-download.spec.ts e2e/bank-details-filtered-export-permissions.spec.ts e2e/pending-invoices-export-download.spec.ts --project=chromium` 通过 11 tests；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v` 通过 8 tests；`python3 -m py_compile tests/test_playwright_e2e_strict_diagnostics.py`、`bash scripts/verify.sh docs` 和目标文件 `git diff --check` 均通过。
- 未测风险：真实 XLSX workbook 打开、真实代理下载 headers、真实大匹配集查询和真实 worker drain 仍需 staging/runtime smoke。

## 2026-06-19 - 规则保存成功路径 UI 错误残留 guard

- 目标：补齐待找发票规则保存 Browser 成功链路的“假成功”检测，防止规则 PUT、operation barrier 和 rows refresh 成功后页面仍残留保存失败、同步失败或 read model 失败提示。
- 影响范围：`web/e2e/pending-invoices-rules-save-flow.spec.ts`、共享 `successAssertions` helper、Playwright 严格诊断静态测试和本模块测试文档。
- 关键决策：只加固 deterministic Browser E2E，不改产品逻辑；barrier timeout 仍由组件测试覆盖“保存成功但刷新中”的合法降级，本 Browser flow 覆盖正常 barrier/rows refresh 成功路径。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、`docs/dev/testing.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：规则保存后等待 `pending_invoice:expense:requires_invoice` operation barrier、rows refresh 和成功反馈，然后调用 `expectNoUnexpectedSuccessUiErrors`。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts e2e/tax-offset-flow.spec.ts e2e/pending-invoices-rules-save-flow.spec.ts --project=chromium`；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`；`bash scripts/verify.sh docs`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd pending/search/invoice-lifecycle worker drain、真实 XLSX workbook 打开、生产大数据和真实网络恢复仍需 staging/runtime smoke。
- 后续事项：新增待找发票写入口、网络恢复 UI 或真实下载解析 gate 时，追加 Browser E2E 并接入同一成功残留 guard。

## 2026-06-19 - 待找发票 Spec-first covered 校准

- 目标：完成 `/pending-invoices` 本地 Spec-first E2E Audit 校准，确认 `PENDING-E2E-001..009` 已由 Browser、组件、API 和后端 contract 覆盖。
- 影响范围：待找发票 Spec-first 覆盖矩阵、全局 Spec-first inventory、testing closure state 和本实施记录；不改产品逻辑。
- 关键决策：当前 Browser 已覆盖页面 ready、默认支出 rows、Workbench confirm fan-out、candidate 负面语义、relation-backed refreshing/stale 诊断、当前筛选/排序导出和 row-limit、选择已有发票、收入批量状态、规则保存 freshness barrier；真实 PostgreSQL/RabbitMQ/Redis/systemd pending/search/invoice-lifecycle worker drain、真实 XLSX workbook 打开、生产大数据和真实网络恢复继续作为 staging/runtime 风险。
- 文档影响：全局 inventory 和 testing closure state 将 `pending-invoices` 从 `partial` 校准为 `covered`。
- 测试覆盖：未新增测试；基于现有 `web/e2e/pending-invoices-*.spec.ts`、`workbench-relations-candidate-semantics`、`workbench-relations-nonfresh-diagnostics`、PendingInvoices Vitest、pending invoice API/service/SQL runtime/lifecycle tests 校准。
- 验证命令：本轮运行 pending-invoices 相关 Playwright specs、`bash scripts/verify.sh docs` 和 `git diff --check`。
- 未测风险：真实 Postgres 大数据/EXPLAIN/锁等待/长分页、真实 RabbitMQ/Redis/systemd worker drain、真实 XLSX workbook 解析/打开、真实网络中断恢复。
- 后续事项：新增独立 search Browser route、真实下载解析 gate、网络恢复 UI 或新增待找发票写入口时，按功能追加 Browser E2E；真实 worker 最新性走 staging/runtime smoke。

## 2026-06-19 - 列筛选与排序 Browser E2E

- 目标：补齐待找发票 `PENDING-E2E-001` 的列筛选/排序 Browser 保护，证明默认状态过滤、表头列筛选和金额排序会同时保留正确 API query 并改变页面可见行。
- 影响范围：`web/e2e/pending-invoices-filter-sort-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 覆盖矩阵和测试矩阵。
- 关键决策：不改产品逻辑；deterministic Browser mock 增加 `pendingInvoiceFilterSortRows`，让 `/api/pending-invoices/rows` 按 `filters`、`sort_field`、`sort_direction` 返回不同顺序/子集，并让 `/api/pending-invoices/filter-options` 提供对方户名、流水标签、银行账户和收支选项。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录及全局 Spec-first inventory/closure state。
- 测试覆盖：新增 `web/e2e/pending-invoices-filter-sort-flow.spec.ts`，覆盖金额升/降序、默认 `status_code=paid_pending_invoice` 保留、对方户名列筛选、rows query contract、分页回到 `1-1 / 1` 和前端运行时报错捕获。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-filter-sort-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 不覆盖真实 PostgreSQL filter/sort EXPLAIN、复杂组合索引、长分页和真实 worker drain；这些仍需 staging 或运维 smoke。
- 后续事项：继续补真实 infra worker drain smoke，或转入 OA pending 进行中写回/关联支出流水 Browser 流。

## 2026-06-19 - 规则保存 Browser E2E

- 目标：补齐待找发票 `PENDING-E2E-009` 的真实浏览器规则保存保护，证明规则 drawer 保存、API contract、operation barrier、rows refresh 和保存反馈在页面中完整连通。
- 影响范围：`web/e2e/pending-invoices-rules-save-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 覆盖矩阵和测试矩阵。
- 关键决策：不改产品逻辑；加固 deterministic Browser mock，使 `/api/pending-invoices/rules` 可按测试场景返回 `can_save=true`、支持 `PUT` 后版本递增和 `read_model_status=refreshing`。Browser 断言 `PUT /api/pending-invoices/rules` body、`POST /api/operation-barrier/status` 的 `pending_invoice:expense:requires_invoice` target、rows 重读和“规则已保存，相关数据正在刷新。”反馈。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录及全局 Spec-first inventory/closure state。
- 测试覆盖：新增 `web/e2e/pending-invoices-rules-save-flow.spec.ts`，覆盖支出规则保存 Browser smoke、前端运行时报错捕获、read model freshness barrier 请求和 rows refetch。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-rules-save-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 证明浏览器流程和 contract，不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `pending-invoice` worker drain；真实 infra freshness 仍需 staging 或运维 smoke。
- 后续事项：继续补更多列筛选/排序 Browser 组合和真实 infra worker drain smoke。

## 2026-06-19 - 导出 row-limit Browser E2E

- 目标：补齐待找发票 `PENDING-E2E-006` 的真实浏览器错误反馈保护，证明后端导出 row-limit 错误不会被导出抽屉吞掉，也不会生成假下载。
- 影响范围：`web/e2e/pending-invoices-export-download.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、本模块 Spec-first E2E 覆盖矩阵和测试矩阵。
- 关键决策：不改产品逻辑；deterministic Browser mock 增加 `pendingInvoiceExportRowLimitError`，让 `/api/pending-invoices/export` 返回现有 contract 的 `pending_invoice_export_row_limit_exceeded`。Browser 测试保留预览成功，点击下载后断言后端错误文案可见且没有 download event。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录及全局 Spec-first inventory/closure state。
- 测试覆盖：扩展 `web/e2e/pending-invoices-export-download.spec.ts`，覆盖 row-limit 下载失败、错误提示和零下载文件。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-export-download.spec.ts --project=chromium`。
- 未测风险：本地 mock download body 和错误 response 不解析真实 XLSX workbook；真实大匹配集查询、真实对象存储/代理下载和大文件耗时仍需 staging 或运维 smoke。
- 后续事项：补更多列筛选/排序 Browser 组合、规则保存 Browser smoke 和真实 infra worker drain smoke。

## 2026-06-19 - 收入批量状态 Browser E2E

- 目标：补齐待找发票 `PENDING-E2E-008` 的真实浏览器保护，证明收入方向多选、批量标记、后端拒绝和 rows 刷新链路不是只在组件/API 测试中成立。
- 影响范围：`web/e2e/pending-invoices-income-status-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 覆盖矩阵和测试矩阵。
- 关键决策：不改产品逻辑；deterministic Browser mock 增加 income direction rows 和 `PUT /api/pending-invoices/income-statuses` 状态机。成功分支返回空 `rows` 以强制页面通过 refresh token 重读 rows；失败分支返回结构化 409，断言页面显示错误、保留选择且没有半写。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录及全局 Spec-first inventory/closure state。
- 测试覆盖：新增 `web/e2e/pending-invoices-income-status-flow.spec.ts`，覆盖批量现金收入成功、单次 mutation、无单行 fallback API、rows refetch、后端拒绝错误可见、选中保留和状态不变。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-income-status-flow.spec.ts --project=chromium`。
- 未测风险：本地 deterministic Browser mock 不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `pending-invoice`、`search`、`invoice-lifecycle` worker drain；真实 infra freshness 仍需 staging 或运维 smoke。
- 后续事项：补导出失败/row-limit Browser 场景和真实 infra worker drain smoke。

## 2026-06-19 - 选择已有发票 Browser E2E

- 目标：补齐待找发票 `PENDING-E2E-007` 的真实浏览器保护，证明多选 eligible 支出流水、选择已有进项发票、preview、confirm、conflict 和 rows 刷新链路不是只在组件测试里成立。
- 影响范围：`web/e2e/pending-invoices-attach-existing-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 覆盖矩阵和测试矩阵。
- 关键决策：Browser mock 按现有 API contract 表达 candidates/preview/confirm；confirm response 不返回 `row`，让页面通过 `refreshToken` 重新读取 rows 后显示 `已支付已开票`，从浏览器层证明刷新链路。conflict 分支返回 `can_confirm=false`，断言确认按钮禁用且没有 confirm mutation 或半写。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录及全局 Spec-first inventory/closure state。
- 测试覆盖：新增 `web/e2e/pending-invoices-attach-existing-flow.spec.ts`，覆盖多选流水/发票、候选“流水关联”chip、搜索请求、preview/confirm body、rows refetch、conflict 原因展示、零半写和浏览器错误捕获。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-attach-existing-flow.spec.ts --project=chromium`。
- 未测风险：本地 deterministic Browser mock 不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `pending-invoice`、`search`、`invoice-lifecycle` worker drain；真实 infra freshness 仍需 staging 或运维 smoke。
- 后续事项：补收入批量标记 Browser 流和导出失败/row-limit Browser 场景。

## 2026-06-19 - Spec-first 导出 relation 字段 Browser E2E

- 目标：补齐待找发票在 Workbench confirm 后导出当前筛选内容时必须包含 OA、进项发票和 relation 字段的真实浏览器保护。
- 影响范围：`web/e2e/pending-invoices-export-download.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 文档和测试矩阵。
- 关键决策：导出测试从业务流程出发，先执行 Workbench confirm，再返回待找发票搜索目标对方户名，断言 export-preview/export 请求带方向、状态桶、关键字和排序，且不带 `page/page_size`；下载内容必须包含 OA 申请人、进项发票号、relation case 和 linked 状态。
- 文档影响：新增 `e2e-spec.md`、`e2e-coverage.md`，更新 `README.md`、`tests.md`、本实施记录及全局 Spec-first inventory/closure state。
- 测试覆盖：新增 `web/e2e/pending-invoices-export-download.spec.ts`；扩展 deterministic Browser API mock 的 pending invoice export-preview/export。
- 验证命令：`cd web && npx playwright test e2e/pending-invoices-export-download.spec.ts --project=chromium`。
- 未测风险：本地 mock download body 是文本化 xlsx payload，尚未解析真实 XLSX workbook；真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain 仍需 staging 或运维 smoke。
- 后续事项：补选择已有发票完整 Browser 流、收入批量标记 Browser 流和导出失败/row-limit Browser 场景。

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

## 2026-06-24 - modular IO next pilot selection

- 目标：作为 `bank_detail` 和 `workbench_relation` 之后的下一条 read model 模块化 IO pilot。
- 决策：先执行 `read-models:pending-invoice-repository-port-extraction`，不直接改业务规则或页面。
- 理由：待找发票 read model 同时依赖银行明细和关联台关系 source versions；已有 freshness gate 曾修复 relation 更新后 pending invoice 伪 fresh 的 bug，适合继续用窄 port 强化 IO 边界。
- 第一条实现边界：新增/使用窄 `PendingInvoiceReadModelRepositoryPort`，只暴露 pending invoice rows、filter options、source summary、bank detail/workbench relation source versions、save/mark 等 read-model repository 方法，并用测试证明不会暴露其它 read model 方法。
- 非目标：不改 attach/manual/income status command 行为，不改 API response shape，不改 UI，不实现 Go/Fiber/Go Worker，不依赖 staging DB 或本地 `PGSQL_URL`。

## 2026-06-12 - relation 写入口迁入 workbench relation command service

- 目标：让待找发票 manual invoice confirm、attach existing 单条和批量不再直接写 `WorkbenchPairRelationService`，统一委托 workbench relation 模块，避免待找发票页面形成独立关系事实源。
- 影响范围：`PendingInvoiceApplicationService`、`WorkbenchRelationCommandService`、`Application` dependency wiring、`tests/test_pending_invoice_service.py`、本模块 README/tests 和 `docs/modules/workbench-relations/*`。
- 关键决策：manual/attach 写 relation 走 `WorkbenchRelationCommandService.confirm_relation(...)`；写前读取既有 active relation 只走 `WorkbenchRelationReadFacade.get_by_row_ids(...)` 的 distribution payload；缺少 command service 时 fail fast。manual invoice confirm 在创建发票前先调用 relation write precondition，relation read model stale 时不创建发票并把 pending command 标记为 `failed_recoverable`。
- 文档影响：更新本模块 `README.md`、`tests.md`、本实施记录，以及 `workbench-relations` 模块 README/tests/implementation-notes。
- 测试覆盖：新增/更新 `tests/test_pending_invoice_service.py`，覆盖 manual/attach 单条/批量委托 command service、stale fail-fast、不产生孤儿发票、命令可恢复状态；保留 pending invoice API 旧 shape 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_service.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_api.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_read_models_use_workbench_relation_distribution -q`；`python3 -m compileall -q backend/src/fin_ops_platform/services/pending_invoice_service.py backend/src/fin_ops_platform/services/workbench_relation_command_service.py`。
- 未测风险：HTTP 层尚未单独断言 relation read model stale 的 error shape；真实 Postgres 并发 row occupation 仍未用锁或唯一占用约束保护；跨页面真实 worker drain 仍需 staging smoke。
- 后续事项：迁移 no-OA submit/withdraw/internal transfer confirm-link，继续消除剩余 relation 写事实源。

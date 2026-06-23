# 进项发票使用情况 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 默认 all scope 查询不得因为月份间嵌套 `workbench_relation_source_versions` 不同而清空基础 `source_versions`；API freshness 只要求服务端期望的基础 source version 字段匹配。
- `以发票反提 OA` 第一版前端只暴露 `创建 OA 草稿`，后端保留 batch 作为内部状态对象；创建草稿使用目标 OA 申请人的已配置凭据/token，OA 提交由用户在 OA 系统手动完成。
- 设置页新增 `OA 申请人凭据管理`，第一版只展示目标 OA 申请人、OA 登录账号和 `已配置`/`未配置` 状态；密码保存/更新成功后不回显，且不能进入普通 app settings payload。
- Phase 1 已落地后端凭据管理：`app.oa_applicant_credentials.encrypted_password` 使用 PostgreSQL `pgcrypto` 加密落库；生产保存/读取密钥来自 `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY`。
- Phase 2 已落地后端一步创建草稿：`POST /api/input-invoice-usage/oa-reverse/oa-draft` 校验 preview hash 后，使用目标 OA 申请人凭据登录 OA 并创建 `isDraft=true` 暂存草稿；当前操作人的 request token 不参与目标申请人草稿创建。
- `已提交 OA` 由用户手动确认后进入本地 `submitted_confirmed` 历史；`未提交 OA` 只清理 FinOps 本地草稿字段并回到可重新创建状态，不调用 OA 删除暂存草稿。
- 目标 OA 申请人登录需要 `FIN_OPS_OA_BASE_URL`、`FIN_OPS_OA_LOGIN_RSA_PUBLIC_KEY`、可选 `FIN_OPS_OA_LOGIN_PATH` 和 OpenSSL runtime；密码登录前必须用 OA 公钥 RSA 加密。
- OA reverse evidence detected 后的 OA/发票 relation 写入必须通过 `WorkbenchRelationCommandService.confirm_relation(...)`，relation mode 为 `input_invoice_oa_reverse`；relation read model 不 fresh 或 command service 缺失时 fail fast，不先推进本地 batch。
- 关联台未配对区 open/proposed 候选必须通过 `WorkbenchRelationReadFacade` 进入进项发票使用情况页面展示；页面不能直接读取关联台候选表。candidate 只展示关系证据，不参与支付状态或 confirmed relation 判断。
- `+N` 详情展开优先读取 `read_model.input_invoice_usage_rows` 单行 payload；SQL read model stale/missing 时返回 refreshing 并入队刷新，不在详情接口中触发全量 live rebuild。
- 月份 shard 构建时，当前 workbench relation scope 的 unlinked/empty row 不能阻止按发票 row id 定向补查跨月 linked group；补查用于展示 OA/银行流水/发票摘要，但 read model 的 `workbench_relation_source_versions` 仍按当前 shard scope 保存。
- 支付状态规则保存、OA reverse 草稿创建和 OA submitted/manual status 写成功后，页面必须先等待当前 scope 的 `input_invoice_usage` operation barrier fresh，再重新读取 rows；barrier blocked/timeout 只提示后台同步未完成，不能提前读旧投影。
- `以发票反提 OA` 的草稿提交确认弹窗可以由用户取消；取消、父页面重渲染和 preview reload 都不能清空当前草稿 batch，状态为 `oa_draft_created` 的 batch 必须出现在 `暂存` 页签。暂存列表不展示 OA 草稿链接，只展示两项处理动作。
- OA reverse preview 中已有 active/linked OA 关系的发票仍然不是可创建候选，但需要作为 rejected display row 返回给前端，展示 `已关联oa` chip、禁用勾选；关联台未配对区 open/proposed OA candidate 也不是可创建候选，展示 `候选oa` chip、禁用勾选。drawer 支持 `全部/已经关联oa/候选oa/未关联oa` 表头筛选。
- 2026-06-11 测试闭环审计确认：本模块 P0/P1 已有测试覆盖 read model all scope、OA 反提、凭据加密、目标申请人 token provider、未提交回滚、已提交历史、设置页 UI 和进项页面 drawer；本轮不新增重复测试，主要补齐测试矩阵并同步长期 API 契约。

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

## 2026-06-23 - 跨月配对 relation 显示修复

- 目标：修复 75,799 元进项发票在 Workbench 已与 OA/银行流水配对，但进项发票使用情况 OA、流水、发票配对列为空的问题。
- 影响范围：`DistributedInvoiceRelationContext` 的 relation 预加载策略；`InvoiceUsageCollectionSqlProjectionBuilder` 保存 relation source versions 的 scope 选择；进项使用服务和 SQL projection 测试；模块状态机和测试矩阵。
- 关键决策：保持“不是全量拉取全部 relation”的边界；先读当前月份 relation scope，再对当前请求发票 row id 中 empty/unlinked 的部分做一次定向 fallback。fallback 只用于补齐该发票相关 linked group，不能替代 read model freshness gate。
- 文档影响：更新 `state-machine.md`、`tests.md` 和本实施记录。
- 测试覆盖：新增 service 回归测试覆盖当月 unlinked row 不遮蔽跨月 linked group；新增 SQL projection 回归测试覆盖跨月 fallback 后当前 shard source versions 不被 fallback scope 覆盖。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_service.InputInvoiceUsageQueryServiceTests.test_month_scope_unlinked_row_does_not_hide_cross_month_linked_relation -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_projection_keeps_current_scope_relation_versions_after_cross_month_fallback -v`。
- 未测风险：尚未在真实生产数据上重建 `input_invoice_usage:2026-05` 后截图复核 75,799 行；本地验证使用 synthetic relation distribution。
- 后续事项：发布后刷新对应 scope，并只读检查 `/api/input-invoice-usage/rows?keyword=良固阀门集团` 中 75,799 行是否带 OA/流水 summaries。

## 2026-06-22 - 写后等待 input_invoice_usage operation barrier

- 目标：修复支付规则保存、OA reverse 草稿创建和 manual status 写成功后前端立即 `loadRows("refresh")`，可能读到旧 `input_invoice_usage` projection 的缺口。
- 影响范围：`InputInvoiceUsagePage`、`PaymentStatusRulesDrawer`、`OaReverseWorkspaceDrawer`、operation barrier label、`InputInvoiceUsagePage.test.tsx` 和本模块测试矩阵；后端业务 contract 不变。
- 关键决策：父页面集中用当前 `month || all` 构造 `input_invoice_usage` barrier target；drawer 的 `onSaved` / `onBatchChanged` 改为可 await。barrier fresh 后才刷新 rows；barrier blocked/timeout 是 post-commit 同步未完成，不读取旧投影。
- 文档影响：更新本实施记录、`tests.md` 和 Spec-first E2E 覆盖说明。
- 测试覆盖：新增 Vitest 回归，证明 OA reverse draft 创建后 barrier resolve 前 rows 请求数不增加，request body 为 `input_invoice_usage:all`；既有支付规则/OA reverse drawer 测试继续保护保存和弹窗交互。
- 验证命令：`cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx src/test/OperationBarrierApi.test.ts`。
- 未测风险：本地 Vitest 只证明页面等待 barrier，不证明真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain。

## 2026-06-21 - 支付状态规则抽屉第一阶段 UI 闭环

- 目标：按 `payment-status-rules-ui-spec.md` 落地 `发票与支付状态规则设置` 右侧抽屉第一阶段 UI，避免显示内部版本号并明确规则抽屉不负责补全 OA/流水关系。
- 影响范围：`PaymentStatusRulesDrawer`、input invoice usage API/types 规则字段映射、抽屉样式、`InputInvoiceUsageFiltersAndDrawers.test.tsx` 和本模块测试矩阵。
- 关键决策：UI 不显示版本号；前端仍保留 `version` 并在保存时提交 `expectedVersion`。规则条件只读展示为 chips；可编辑字段包含启用状态、优先级、状态名称和原因文案。待处理方向展示为标签并明确“当前仅作为待处理方向标签，不影响自动分流”。
- 文档影响：更新本实施记录和 `tests.md`；长期产品/API 事实未变化。
- 测试覆盖：扩展 `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`，覆盖无版本号展示、条件 chips、待处理方向边界、`保存并刷新`、内部 expectedVersion 提交和冲突反馈；更新 `web/e2e/input-invoice-usage-flow.spec.ts` 支付规则保存流程，验证真实浏览器下保存后刷新 rows 且不展示版本号；`InputInvoiceUsagePage.test.tsx` 作为页面集成回归。
- 验证命令：`cd web && npm test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`；`cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`；`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts --project=chromium --grep "payment status rules"`；`cd web && npm run build`。
- 未测风险：未新增规则影响 preview API，未开放条件编辑，未把 OA 反提目标申请人迁移到设置事实源；真实 worker drain 和真实 OA 仍按既有风险处理。
- 后续事项：若继续推进完整自动化闭环，可新增 preview API 或拆分待处理方向/OA 反提目标申请人设置，并补 API/service/read model/Browser 覆盖。

## 2026-06-21 - 支付状态规则抽屉 UI Spec

- 目标：为 `发票与支付状态规则设置` 右侧抽屉补小范围 UI 合同，明确抽屉只维护支付状态解释规则，不负责补全 OA/流水关系。
- 影响范围：`docs/modules/input-invoice-usage/payment-status-rules-ui-spec.md` 与模块 README 文档索引；不改产品代码、API contract 或测试代码。
- 关键决策：UI 不显示版本号；前端仍可在内存中保留版本并提交 `expectedVersion` 做后端冲突保护。第一阶段规则条件只读展示，只开放启用、优先级、状态名称和原因文案等低风险字段。
- 文档影响：新增本模块 UI spec，并在 `README.md` 本目录文件中登记。
- 测试覆盖：本轮仅新增设计文档，未新增自动化测试；后续实现时按 spec 补 frontend/API/service/read model 回归。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：尚未实现 UI、preview API 或条件编辑能力；真实影响范围需在实现阶段通过 read model 和 Browser 回归验证。
- 后续事项：确认是否新增规则影响 preview API、是否拆出待处理方向设置、是否将 OA 反提目标申请人迁移到设置事实源。

## 2026-06-20 - rows 加载失败刷新恢复 Browser E2E

- 目标：补齐进项发票使用页的本地 `NETWORK-RECOVERY` 负面链路，防止 rows 首屏暂时失败时显示普通空态、允许导出或隐藏真实加载错误。
- 影响范围：`InputInvoiceUsagePage` 错误/刷新/导出禁用状态、`InputInvoiceUsageTable` 错误态空行文案、Playwright deterministic mock、`web/e2e/input-invoice-usage-flow.spec.ts`、`InputInvoiceUsagePage.test.tsx` 和测试闭环文档。
- 关键决策：不改后端业务语义；Browser mock 表达 `/api/input-invoice-usage/rows` 暂时 503，页面必须显示错误提示和错误态空行，禁用筛选导出，并通过显式刷新恢复 fresh rows/pagination/export。
- 文档影响：更新本文件、`e2e-coverage.md`、`tests.md`、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/input-invoice-usage-flow.spec.ts::recovers rows after a transient load failure when refreshed`；扩展 `web/src/test/InputInvoiceUsagePage.test.tsx` 验证显式刷新入口会重新请求 rows。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts --project=chromium`；本轮最终说明列出额外 Vitest/类型/docs 验证。
- 未测风险：本地 deterministic Browser 不能证明真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain；真实网络中断、真实 XLSX 下载性能、真实 OA 和生产数据量仍需 staging/runtime smoke。
- 后续事项：继续补其他页面 mutation 网络中断恢复、真实 worker drain gate，或把全量 e2e smoke 跑到稳定绿色。

## 2026-06-19 - 成功写流 UI 错误残留 guard

- 目标：补齐进项发票使用 Browser 成功链路的“假成功”检测，防止支付规则保存、OA 草稿创建或用户确认已提交后页面仍残留操作失败、保存失败、同步失败或 read model 失败提示。
- 影响范围：`web/e2e/input-invoice-usage-flow.spec.ts`、共享 `successAssertions` helper、Playwright 严格诊断静态测试和本模块测试文档。
- 关键决策：只加固 deterministic Browser E2E，不改产品逻辑；`未提交`、`未关联oa` 等合法业务状态不是失败残留，不纳入 helper 模式。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、`docs/dev/testing.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：支付规则保存成功、OA 草稿创建确认弹窗、manual submitted 历史成功节点都会调用 `expectNoUnexpectedSuccessUiErrors`。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts e2e/tax-offset-flow.spec.ts e2e/pending-invoices-rules-save-flow.spec.ts --project=chromium`；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`；`bash scripts/verify.sh docs`。
- 未测风险：真实 OA、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、search 外层 UI 和真实网络中断恢复仍需 staging/runtime smoke。
- 后续事项：新增 OA 状态刷新按钮或全局 search UI 时，按新入口补 Browser E2E 并接入同一成功残留 guard。

## 2026-06-19 - Tax certified import fan-out applicability audit

- 目标：收敛 `IN-USAGE-E2E-009` 中“认证状态变化 Browser fan-out”缺口，避免在进项使用页硬造没有用户入口的 Browser 场景。
- 影响范围：`tests/test_derived_data_lifecycle_service.py`、本模块 `e2e-coverage.md` / `tests.md`；产品逻辑和前端交互不变。
- 关键决策：税务认证导入的用户可见 Browser 流程归 `tax-offset` 模块，已有 `web/e2e/tax-offset-flow.spec.ts` 覆盖 XLSX 选择、preview、confirm、税金页刷新和已认证结果展示。跨 read model fan-out 的事实范围是 `tax_certified_import_confirmed -> invoice_lifecycle_read_model -> tax_offset_read_model/tax_offset_month_cache/search_cache`，不应错误扩展到 cost 或 OA pending。
- 文档影响：`IN-USAGE-E2E-009` 继续保持 partial，但 Browser 缺口收敛为真实基础设施 worker drain；认证导入不再登记为进项使用页 Browser 缺口。
- 测试覆盖：新增 `tests/test_derived_data_lifecycle_service.py::DerivedDataLifecycleServiceTests::test_tax_certified_import_confirmed_refreshes_lifecycle_tax_and_search_only`，固定认证导入 lifecycle/tax/search fan-out 范围。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_derived_data_lifecycle_service.py::DerivedDataLifecycleServiceTests::test_tax_certified_import_confirmed_refreshes_lifecycle_tax_and_search_only -q`；`cd web && npx playwright test e2e/tax-offset-flow.spec.ts --project=chromium`；`bash scripts/verify.sh docs`。
- 未测风险：deterministic Browser 不证明真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain；真实税务认证导入文件解析和 all-scope worker shard drain 仍需 infra/staging smoke。
- 后续事项：转入真实基础设施 worker drain smoke，或在新增全局 search UI 后补认证导入 search Browser fan-out。

## 2026-06-19 - Payment rules enqueue invoice lifecycle refresh

- 目标：推进 `IN-USAGE-E2E-009` 的 read model/worker freshness 闭环，修复支付规则版本变化后只刷新 `input_invoice_usage`、未刷新 `invoice_lifecycle` 的风险。
- 影响范围：`backend/src/fin_ops_platform/app/server.py`、`tests/test_input_invoice_usage_payment_rules.py`、本模块 `e2e-coverage.md` / `tests.md`；前端交互和产品逻辑不变。
- 关键决策：`InvoiceLifecyclePolicy.source_versions()` 和 `InvoiceLifecycleSqlProjectionBuilder._source_versions()` 都包含 `input_invoice_usage_payment_rules_version`；因此保存支付规则后必须同时入队 `input_invoice_usage:all` 和 `invoice_lifecycle:all`，否则 lifecycle projection 可能继续以旧规则版本标记 fresh。
- 文档影响：`IN-USAGE-E2E-009` 继续保持 partial；支付规则保存的 Browser 覆盖仍是当前页 rows refresh，跨 read model freshness 改由 API/runtime 测试覆盖。
- 测试覆盖：更新 `tests/test_input_invoice_usage_payment_rules.py::InputInvoiceUsagePaymentRulesTests::test_put_rules_handler_saves_and_enqueues_refresh`，断言保存规则后同时入队 `input_invoice_usage` 与 `invoice_lifecycle`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_input_invoice_usage_payment_rules.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_invoice_lifecycle_read_model_refresh.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_derived_data_lifecycle_service.py::DerivedDataLifecycleServiceTests::test_invoice_lifecycle_domain_precedes_downstream_invoice_pages -q`；`bash scripts/verify.sh docs`。
- 未测风险：本地测试证明 durable queue enqueue contract，不证明真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain；真实 `invoice_lifecycle` all-scope shard drain 仍需 infra/staging smoke。
- 后续事项：继续补认证状态变化 Browser fan-out，或配置真实 infra env 后跑 worker drain smoke。

## 2026-06-19 - OA reverse evidence detected Browser applicability audit

- 目标：推进 `IN-USAGE-E2E-009`，审计 OA reverse `evidence_detected` 是否应补 Browser E2E，并加固 read model invalidation 自动化证据。
- 影响范围：`tests/test_input_invoice_usage_oa_reverse_service.py`、本模块 `e2e-coverage.md` / `tests.md`；不改产品逻辑、API contract 或前端 UI。
- 关键决策：`oa-status/refresh` 虽有后端 route 和前端 API client，但当前 `以发票反提 OA` UI 流程不暴露用户可点击的刷新 OA 状态入口，`canRefreshStatus` 在现有 Browser 流程中也不是可操作动作。因此本轮不硬造 Browser E2E；`evidence_detected` 由 service/API 测试覆盖 relation command 写入、409 no half-write、evidence payload 和成功 detected 后 read model invalidation。
- 文档影响：`IN-USAGE-E2E-009` 继续保持 partial；缺口从 “OA reverse evidence detected Browser fan-out” 修正为 “当前无 Browser 入口，service/API 覆盖，未来暴露刷新按钮后再补 Browser”。真实 worker drain 仍保留为 infra/staging 风险。
- 测试覆盖：补强 `tests/test_input_invoice_usage_oa_reverse_service.py`，断言 relation writer 传递 evidence payload，并断言 `refresh_oa_status` evidence detected 成功路径按发票月份 invalidates `input_invoice_usage_oa_reverse_evidence_detected`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_input_invoice_usage_oa_reverse_service.py -q`；`bash scripts/verify.sh docs`；`bash scripts/verify.sh infra-smoke`。
- 未测风险：`infra-smoke` 本地 runtime/read-model smoke 通过，但当前环境未配置 `FIN_OPS_TEST_DATABASE_URL` / `RABBITMQ_TEST_URL`，真实 PostgreSQL/RabbitMQ preflight 被跳过；本地 service 测试仍不证明真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain。未来若新增 OA 状态刷新按钮，需要补 Browser E2E 捕获点击、错误弹窗、relation 写入和 rows refresh。
- 后续事项：继续补 `IN-USAGE-E2E-009` 的支付规则到更多下游、认证状态变化 Browser fan-out，或补真实 infra worker drain smoke。

## 2026-06-19 - Browser e2e OA reverse batch mutations refresh current rows

- 目标：继续推进 `IN-USAGE-E2E-009`，补齐 OA reverse 草稿创建和用户确认 submitted 后的当前页 read model refresh 浏览器闭环。
- 影响范围：`OaReverseWorkspaceDrawer` batch mutation 成功回调、`InputInvoiceUsagePage` 当前查询 refresh、`web/e2e/input-invoice-usage-flow.spec.ts` 和本模块覆盖文档；后端业务逻辑不变。
- 关键决策：后端 `InputInvoiceUsageOaReverseService.create_draft_from_selection(...)` / `manual_oa_status(...)` 已在成功后 `_invalidate_read_models(...)`，本轮只修前端未通知父页面重新拉 rows 的缺口。`submitted_confirmed` 仍只是本地历史状态；真正 OA/发票 relation fan-out 只在 `evidence_detected` 通过 `WorkbenchRelationCommandService.confirm_relation(...)` 后发生。
- 文档影响：`IN-USAGE-E2E-004` 继续 covered，并补充 draft/manual submitted 后当前 rows refresh；`IN-USAGE-E2E-009` 继续 partial，仍保留 OA reverse evidence detected 到更多下游和真实 worker drain 风险。
- 测试覆盖：扩展 `web/e2e/input-invoice-usage-flow.spec.ts::creates an OA reverse draft from a selected invoice subset and records submitted history`，覆盖草稿创建后 rows refresh、manual submitted 后 rows refresh、submitted history、内部 batch id 不展示和无浏览器错误。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts --project=chromium --grep "OA reverse draft"`。
- 未测风险：本地 Browser mock 不能证明真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain；OA reverse `evidence_detected` 关系写入到更多下游页面仍需后续轮次或 staging/nightly。
- 后续事项：继续补 `IN-USAGE-E2E-009` 的 `evidence_detected -> workbench_relation -> downstream read models` 或真实 infra worker drain smoke。

## 2026-06-19 - Browser e2e payment rules save refreshes current rows

- 目标：推进 `IN-USAGE-E2E-009` 的非 relation 触发源，证明 full-access 用户保存进项发票支付状态规则后，当前页面会按后端刷新语义重新读取 rows，而不是继续显示旧支付状态。
- 影响范围：`PaymentStatusRulesDrawer` 保存成功回调、`InputInvoiceUsagePage` 当前查询 refresh、Playwright deterministic mock、`web/e2e/input-invoice-usage-flow.spec.ts` 和本模块覆盖文档；后端业务逻辑不变。
- 关键决策：后端 `tests/test_input_invoice_usage_payment_rules.py` 已覆盖保存规则后入队 `input_invoice_usage:all`，本轮不重复改后端；前端补最小回调 `onSaved`，保存成功后触发当前页 `loadRows("refresh")`。Browser mock 表达版本递增、幂等键、保存后 fresh rows 的 contract，不把 mock worker 当成真实 infra drain。
- 文档影响：`IN-USAGE-E2E-009` 继续保持 partial，但新增“支付规则保存 -> 当前页 rows refresh -> 新支付状态可见”的 Browser 覆盖；真实 worker drain 和支付规则到更多下游页面仍登记为未测风险。
- 测试覆盖：新增 `web/e2e/input-invoice-usage-flow.spec.ts::refreshes current rows after full-access payment status rules are saved`，覆盖真实 Chromium 编辑规则、保存按钮状态、PUT `expectedVersion/idempotencyKey`、保存成功反馈、版本递增、当前 rows 重新读取、无浏览器错误。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts --project=chromium --grep "payment status rules"`。
- 未测风险：本地 Browser mock 不能证明真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain；支付规则变化到更多下游页面、OA reverse、认证状态变化的 Browser fan-out 仍需后续轮次或 staging/nightly。
- 后续事项：继续补 `IN-USAGE-E2E-009` 的更多非 relation 触发源 fan-out，或补真实 infra worker drain smoke。

## 2026-06-19 - Search fan-out Browser applicability audit

- 目标：审计 `IN-USAGE-E2E-009` 中 search downstream 是否应该补 Browser E2E，避免为不存在的前端入口硬造 Playwright。
- 影响范围：本模块 `e2e-coverage.md` / `tests.md`；不改产品逻辑、API contract 或测试代码。
- 关键决策：`/api/search` 当前没有独立前端 route；`web/src` 中只有 AppHealth/Vitest mock 和各业务页自己的本页搜索框引用，业务页面不会在 Browser 中调用 `/api/search`。因此 search downstream 在当前 UI 形态下属于 API/runtime coverage，不属于 Browser E2E 缺口。
- 文档影响：`IN-USAGE-E2E-009` 继续保持 partial，但缺口从 “search Browser fan-out” 修正为 “search 由 API/runtime 覆盖，未来如新增外层搜索入口再补 Browser”；继续保留支付规则、OA reverse、认证状态变化到更多下游和真实 infra worker drain 风险。
- 测试覆盖：复用现有 `tests/test_workbench_relation_repository.py` 和 `tests/test_search_pending_sql_runtime.py`，覆盖 relation 写入 high priority 入队 `search`、search worker projection 保留 linked group jump target、`/api/search` SQL read model hit 返回 `fresh` group context 且不回扫 in-memory 状态。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_search_api_reads_sql_index tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_search_api_miss_enqueues_refresh_without_sync_scan tests/test_search_pending_sql_runtime.py::SearchPendingSqlRuntimeTests::test_refresh_handler_skips_stale_search_source_version -q`；`bash scripts/verify.sh docs`。
- 未测风险：没有真实 Browser `/api/search` 入口可点；如果后续增加全局搜索 UI，需要新增 Spec-first Browser E2E。真实 worker drain 仍需 staging/nightly。
- 后续事项：继续补 `IN-USAGE-E2E-009` 的支付规则、OA reverse、认证状态变化到更多下游，或补真实 infra worker drain smoke。

## 2026-06-19 - Browser e2e relation downstream fan-out partial

- 目标：推进 `IN-USAGE-E2E-009`，用真实 Chromium 证明进项发票使用情况中的 Workbench candidate relation 经确认后，不只本页变 linked，下游 OA 待付款、税金抵扣和成本统计也通过各自 read model 看到 confirmed 后的新事实。
- 影响范围：`web/e2e/input-invoice-relation-fanout.spec.ts`、本模块 `e2e-coverage.md` / `tests.md`；产品逻辑和 API contract 不变。
- 关键决策：复用现有 deterministic mock 的 `relationConfirmed` 状态和 `oaPendingPaymentRelationFanout` / `taxOffsetRelationFanout` / `costStatisticsRelationFanout` 选项，不新增业务语义；Browser 测试从进项使用页的 candidate 证据出发，经 Workbench confirm 后分别进入下游页面，并断言页面重新请求 rows/payload、候选消失、confirmed 文案和金额/税额/项目事实出现。
- 文档影响：`IN-USAGE-E2E-009` 从 missing 更新为 partial；明确已覆盖 relation-confirm 到 OA pending/tax/cost 的 Browser fan-out，后续 search applicability audit 又确认 `/api/search` 当前无独立 Browser route 且由 API/runtime 覆盖；仍缺支付规则、OA reverse、认证状态变化到更多下游的 Browser fan-out，以及真实 infra worker drain。
- 测试覆盖：Playwright 扩展 `input invoice usage relation browser fan-out` 场景，覆盖 candidate OA evidence non-selectable、Workbench confirm、input invoice usage linked evidence、OA pending `已支付`、tax offset 进项票认证计划、cost statistics 项目/费用类型/流水表和无浏览器错误。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-relation-fanout.spec.ts --project=chromium`。
- 未测风险：本地 Browser mock 只证明 UI/fan-out contract；真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、支付规则/OA reverse/认证状态变化后的全链路仍需后续轮次或 staging/nightly。
- 后续事项：继续补 `IN-USAGE-E2E-009` 的非 relation 触发源，或补真实 infra worker drain smoke。

## 2026-06-19 - Browser e2e read-export 权限零 durable write

- 目标：完成 `IN-USAGE-E2E-007` 的本页权限 Browser 覆盖，证明 `read_export_only` 用户能读列表和导出，但不能保存支付规则、创建 OA 草稿、创建 batch 或提交 OA manual status。
- 影响范围：Playwright deterministic API mock、`web/e2e/input-invoice-usage-flow.spec.ts`、本模块 `e2e-coverage.md` / `tests.md` 和全局 Spec-first E2E 状态文档；产品逻辑不变。
- 关键决策：`/api/input-invoice-usage/oa-reverse/preview` 当前是 read-like POST，后端用 read session 放行并通过 `canCreateDraft=false` 禁止只读用户创建草稿；Browser 权限测试单独允许该 preview POST，但对 payment rules save、OA draft、batch 和 manual status 等 durable write endpoint 断言零调用。
- 文档影响：`IN-USAGE-E2E-007` 从 partial 更新为 covered；本模块仍保持 spec-first-partial，因为 `IN-USAGE-E2E-009` 下游 fan-out 和真实 infra worker drain 仍未完整闭环。
- 测试覆盖：Playwright 新增 `read_export_only` 场景，覆盖列表可读、导出预览可用、支付规则 drawer 只读且无保存/编辑控件、OA reverse preview 返回不可创建草稿、创建草稿按钮禁用、durable write endpoint 零调用和无浏览器错误。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts --project=chromium --grep "read-export users"`；完整模块回归和 smoke 见本轮最终说明。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实 OA、真实 XLSX workbook 完整解析/性能和 `IN-USAGE-E2E-009` downstream fan-out 仍需后续 smoke。
- 后续事项：继续补 `IN-USAGE-E2E-009` downstream fan-out，或在有真实 infra env 时补 rows/detail/export 从 non-fresh 恢复 fresh 的 worker drain smoke。

## 2026-06-19 - Browser e2e fresh rows filter/sort/page-size

- 目标：完成 `IN-USAGE-E2E-001` 的真实浏览器覆盖，证明进项发票使用情况 fresh rows 首屏、筛选、排序和 page-size 控件与 rows API contract 和可见行同步。
- 影响范围：Playwright deterministic API mock、`web/e2e/input-invoice-usage-flow.spec.ts`、本模块 `e2e-coverage.md` / `tests.md` 和全局 Spec-first E2E 状态文档；产品逻辑不变。
- 关键决策：新增专用 `inputInvoiceUsageFilterSortRows` deterministic dataset，让 filter-options 包含当前页外供应商，测试证明筛选选项不是从当前页 rows 伪造；Browser 断言 rows URL 的 `page/page_size/filters/sort_field/sort_direction` 和 DOM 可见行一致。
- 文档影响：`IN-USAGE-E2E-001` 从 partial 更新为 covered；权限全矩阵、下游 fan-out、真实 worker drain 和真实大数据性能继续登记为风险/后续队列。
- 测试覆盖：Playwright 新增 fresh rows/filter/sort/page-size 场景，覆盖首屏有界分页、页外全局筛选项、销方筛选、开票日期升序排序、page-size 切换、零 mutation 和无浏览器错误。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts --project=chromium`。
- 未测风险：真实 PostgreSQL 大数据 EXPLAIN/锁等待、真实浏览器长表滚动、真实 worker drain 和每按钮权限矩阵仍需后续 smoke。
- 后续事项：`IN-USAGE-E2E-007` 已补；继续补 `IN-USAGE-E2E-009` downstream fan-out 或真实 infra worker drain。

## 2026-06-19 - Browser e2e 当前筛选导出/download

- 目标：完成 `IN-USAGE-E2E-008` 的真实浏览器覆盖，证明进项发票使用情况导出使用当前筛选，不受当前分页限制，并且 row-limit/read model 非 fresh 状态不会触发下载。
- 影响范围：Playwright deterministic API mock、`web/e2e/input-invoice-usage-flow.spec.ts`、本模块 `e2e-coverage.md` / `tests.md` 和全局 Spec-first E2E 状态文档；产品逻辑不变。
- 关键决策：导出测试按业务 Spec 验收，不按当前组件实现细节验收；Browser 断言 export-preview/export URL contract、download event、文件内容字段、row-limit 结构化错误和导出 read model refreshing 禁用下载。
- 文档影响：`IN-USAGE-E2E-008` 从 missing 更新为 covered；真实 XLSX 完整解析/性能、权限全矩阵、真实 worker drain 和下游 fan-out 继续登记为风险/后续队列。
- 测试覆盖：Playwright 新增当前筛选导出真实下载、row-limit 零下载、export read model 非 fresh 禁用下载三个场景，覆盖真实 Chromium 下载事件、API contract、零 mutation 和无浏览器错误。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts --project=chromium`。
- 未测风险：下载体使用 deterministic mock 内容，不解析真实 XLSX workbook；真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain 后恢复 fresh、真实大数据导出性能和每按钮权限矩阵仍需后续 smoke。
- 后续事项：`IN-USAGE-E2E-001` / `IN-USAGE-E2E-007` 已补；继续补 `IN-USAGE-E2E-009` downstream fan-out 或真实 infra worker drain。

## 2026-06-19 - Browser e2e fresh +N relation detail 展开

- 目标：完成 `IN-USAGE-E2E-006` 的真实浏览器正向覆盖，证明多 OA 关系在进项发票使用情况行内显示合计后，用户点击 `+N` 能从单行 read model relation detail endpoint 展开完整摘要。
- 影响范围：`web/e2e/input-invoice-usage-flow.spec.ts`、本模块 `e2e-coverage.md` / `tests.md` 和全局 Spec-first E2E 状态文档。
- 关键决策：沿用现有 deterministic API mock 的 fresh relation detail contract，不改产品逻辑；Browser 断言 detail endpoint 返回 200、drawer 展示两条 OA 摘要，不显示 loading/不可用态，不触发任何 mutation API。
- 文档影响：`IN-USAGE-E2E-006` 从 partial 更新为 covered；后续已补 `IN-USAGE-E2E-008` download，权限组合、下游 fan-out 和真实 worker drain 仍作为后续风险/队列。
- 测试覆盖：Playwright 新增 fresh `+N` relation detail 正向展开场景，覆盖真实 Chromium 点击、drawer 渲染、API contract、零 mutation 和无浏览器错误。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts --project=chromium`。
- 未测风险：当前仅覆盖 OA 多关系正向展开；银行/发票多关系正向展开由 API/Vitest 覆盖，后续如发现浏览器差异可补代表性 bank/invoice 场景。真实 worker drain 后恢复 fresh、真实 OA/PostgreSQL/RabbitMQ/Redis/systemd 和真实下载性能/完整 XLSX 解析仍需后续 smoke。
- 后续事项：`IN-USAGE-E2E-001` / `IN-USAGE-E2E-007` / `IN-USAGE-E2E-008` 已补；继续补 `IN-USAGE-E2E-009` downstream fan-out 或真实 infra worker drain。

## 2026-06-19 - Browser e2e relation detail refreshing 诊断

- 目标：完成 `IN-USAGE-E2E-005` 的 relation detail Browser negative 场景，防止 `+N` 明细在 read model stale/refreshing 时长期停留在 loading 或显示假空态。
- 影响范围：`InputInvoiceUsage` relation detail API mapper、Playwright deterministic API mocks、`web/e2e/input-invoice-usage-flow.spec.ts`、`InputInvoiceUsageFiltersAndDrawers.test.tsx` 和本模块测试/覆盖文档。
- 关键决策：`/api/input-invoice-usage/rows/{row_id}/relation-details` 返回非 fresh read model contract 时，前端把 detail 映射为 `detailAvailable=false`，drawer 显示“详情暂不可用”和业务诊断，不泄露 stale reason，也不展示旧明细。
- 文档影响：`IN-USAGE-E2E-005` 从 partial 更新为 covered；真实 worker drain 后恢复 fresh 仍登记为 infra/staging risk。
- 测试覆盖：Vitest 覆盖 relation detail mapper 对 `read_model_status=refreshing` 的不可用详情映射；Playwright 覆盖真实浏览器点击 `+N` 后收到 202 relation detail contract、显示诊断、不长期 loading、不展示 stale 明细、零 mutation 和无浏览器错误。
- 验证命令：`cd web && npm test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`；`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts --project=chromium`。
- 未测风险：真实 worker drain 后恢复 fresh、真实 OA/PostgreSQL/RabbitMQ/Redis/systemd 和真实下载性能仍需后续 smoke。
- 后续事项：`IN-USAGE-E2E-001` / `IN-USAGE-E2E-007` / `IN-USAGE-E2E-008` 已补；继续补 `IN-USAGE-E2E-009` downstream fan-out 或真实 infra worker drain。

## 2026-06-19 - Browser e2e rows read model refreshing 防 false-empty

- 目标：推进 `IN-USAGE-E2E-005`，修复进项发票使用页在 rows read model 非 fresh 时显示普通空态的问题，并补真实 Chromium 负面保护。
- 影响范围：`InputInvoiceUsagePage` refreshing UI、`InputInvoiceUsagePage.test.tsx`、Playwright deterministic API mocks、`web/e2e/input-invoice-usage-flow.spec.ts` 和本模块测试/覆盖文档。
- 关键决策：当 rows/filter-options 返回 `read_model_status=refreshing` 时，页面显示“进项发票使用情况数据正在刷新”，不渲染普通 empty state 或空表；mock 用 `inputInvoiceUsageReadModelStatus` 表达 stale/missing/refreshing，但对页面保持真实 API contract：`202`、空 rows、`refresh_enqueued=true`。
- 文档影响：当时 `IN-USAGE-E2E-005` 仍保持 partial；后续已补 relation detail Browser negative 并更新为 covered。
- 测试覆盖：Vitest 覆盖 refreshing 诊断、非普通空态和路由卸载后不重试；Playwright 覆盖 stale rows contract 下刷新诊断、不显示旧发票行、普通空态或空表、零 mutation 和无浏览器错误。
- 验证命令：`cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx`；`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts --project=chromium`。
- 未测风险：真实 worker drain 后恢复 fresh、真实 Redis/RabbitMQ/systemd backlog、真实大数据浏览器和下载性能仍需后续 smoke。
- 后续事项：后续已补 `IN-USAGE-E2E-001` 筛选/排序/page-size、`IN-USAGE-E2E-005` relation detail Browser negative、`IN-USAGE-E2E-006` 正向 `+N` 明细展开、`IN-USAGE-E2E-007` 权限零 durable write 和 `IN-USAGE-E2E-008` download；继续补 downstream fan-out 或真实 infra worker drain。

## 2026-06-18 - OA reverse 新增暂存 bucket

- 目标：修复创建 OA 草稿后用户关闭确认弹窗时，本地批次缺少可恢复入口的问题。
- 影响范围：`InputInvoiceUsageOaReverseService`、OA reverse API、`OaReverseWorkspaceDrawer`、前端 API mapper、模块/API 文档和测试矩阵。
- 关键决策：不新增数据库状态；复用已有 `oa_draft_created` 作为事实状态，前端展示为 `暂存`。暂存列表只展示批次摘要和两个处理选项，不展示 OA 草稿链接。关闭确认弹窗只关闭 UI 并切到暂存，不调用 manual status，也不清理 batch。
- 文档影响：更新本实施记录、`README.md`、`state-machine.md`、`tests.md`、`oa-reverse-design.md` 和 `docs/dev/api-contracts.md`。
- 测试覆盖：新增 service/API/frontend 暂存恢复测试，并同步既有确认按钮文案断言。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：真实 OA 外部草稿仍需 staging 联调；本功能不改变外部 OA 系统草稿生命周期。

## 2026-06-18 - Browser e2e 覆盖 relation fan-out 与 OA 三态保护

- 目标：为 `进项发票使用情况` 建立 Spec-first E2E 基线，并补真实 Chromium smoke，证明 Workbench relation candidate/linked 语义在进项页和 OA reverse drawer 中不回归。
- 影响范围：Playwright deterministic mock、`web/e2e/input-invoice-relation-fanout.spec.ts`、`npm run e2e:smoke`、本模块 `e2e-spec.md` / `e2e-coverage.md` / `tests.md` / `state-machine.md` 和 `workbench-relations` 覆盖矩阵。
- 关键决策：不新增页面私有匹配规则；mock 表达真实 API contract。candidate OA/流水关系只作为证据显示，支付状态保持 `待处理`；Workbench confirm 后重新进入页面读取 linked rows，显示 `已支付`。OA reverse preview 中 candidate/linked 发票均不可勾选，且不触发草稿 API。
- 文档影响：新增本模块 Spec-first E2E 文档，更新全局 inventory、nightly、testing 和 closure state。
- 测试覆盖：新增 `web/e2e/input-invoice-relation-fanout.spec.ts`，覆盖七类中的前端交互、端到端业务流和既有功能回归。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：真实 OA、真实 worker drain、真实下载、tax/cost/search 更下游 fan-out 仍需后续轮次或 staging。

## 2026-06-17 - 主列表显示 OA 附件来源 relation 证据

- 目标：修复 `进项发票使用情况` 主列表中正式发票已由 OA 附件来源提升/合并，但 OA 列仍为空的问题；例如 `安徽德易智莱科技有限公司 / 913401003366798893` 在关联事实中有 OA，却因 row id 不一致未展示。
- 影响范围：`InputInvoiceUsageQueryService` rows 构建、relation preload、发票 relation summary、模块 README/状态机/测试矩阵。
- 关键决策：不新增页面私有匹配，不直接从前端或 pending invoice UI 推断 OA；列表仍通过 `WorkbenchRelationReadFacade` 读取统一 relation distribution，只是在查询 key 中加入 `source_links[].source_workbench_row_id`，覆盖正式发票 id 与 OA 附件 row id 不同的生产形态。candidate 证据只展示，不参与支付状态。
- 文档影响：更新本实施记录、`README.md`、`state-machine.md` 和 `tests.md`；API shape 未变化，不更新 `docs/dev/api-contracts.md`。
- 测试覆盖：新增 `InputInvoiceUsageQueryServiceTests.test_oa_attachment_source_relation_displays_for_promoted_formal_invoice`，覆盖 OA 附件来源 row id 的 OA candidate 展示和支付状态不变。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：真实生产行仍需部署后通过 read model refresh/只读 smoke 确认；本地测试覆盖 service 和 SQL read model 构建路径，不连接真实 OA/Postgres worker drain。

## 2026-06-17 - OA reverse 候选 OA 三态 chip 修复

- 目标：修复截图中发票在关联台未配对区已经有 OA candidate，但在 `以发票反提 OA` drawer 中显示 `未关联oa` 的问题。
- 影响范围：`InputInvoiceUsageOaReverseService.preview` 的 rejected invoice contract、`OaReverseWorkspaceDrawer` 的 chip/filter/disabled 状态、前端 API mapper/types、样式、API contract 测试和模块文档。
- 关键决策：截图 1 的“有 OA”是关联台未配对区 candidate，不是 active/linked OA 关系；旧实现只有 `linked/unlinked` 二态，导致 candidate 默认落到 `unlinked`。修复后 OA reverse 使用 `linked/candidate/unlinked` 三态：`linked` 显示 `已关联oa`，`candidate` 显示 `候选oa`，两者都不可勾选且不进入创建 OA 草稿 payload。
- 文档影响：更新本实施记录、`README.md`、`state-machine.md`、`tests.md`、`oa-reverse-design.md` 和 `docs/dev/api-contracts.md`。
- 测试覆盖：新增 service/API candidate OA preview 回归；更新前端 drawer 测试覆盖 `候选oa` chip、禁用勾选和 `全部/已经关联oa/候选oa/未关联oa` 筛选。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：真实生产截图行仍需部署后用实际 read model 数据只读 smoke；本地测试已覆盖 relation facade candidate payload 到 preview/API/UI mapper 的路径。

## 2026-06-17 - OA reverse 确认弹窗持久化与 OA 关联状态筛选

- 目标：修复 `以发票反提 OA` 创建草稿后提交确认弹窗自动消失的问题，并让已有 OA 关联的发票在反提清单中可见、不可选、可筛选。
- 影响范围：`OaReverseWorkspaceDrawer`、OA reverse preview rejected invoice contract、前端 API mapper/types、样式、service preview display rows、模块/API 文档和测试矩阵。
- 关键决策：弹窗消失的真实原因是父页面异步刷新导致重渲染，drawer 每次收到新的内联 `selectedInvoiceIds={[]}` 数组都会重建 preview request，preview reload 成功后执行 `setBatch(null)`，从而卸载确认弹窗。修复时稳定 selected invoice ids，并在确认弹窗打开后禁止 preview reload 清空当前 batch。
- 文档影响：更新本实施记录、`state-machine.md`、`tests.md`、`oa-reverse-design.md` 和 `docs/dev/api-contracts.md`。
- 测试覆盖：新增/更新 `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` 覆盖确认弹窗跨重渲染/preview reload 保持、linked OA disabled row 和筛选菜单；更新 `tests/test_input_invoice_usage_oa_reverse_service.py` 覆盖 active OA rejected row 保留展示字段。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：真实 OA 草稿页面人工提交仍需 staging/发布前 smoke；本修复覆盖 FinOps 内部 drawer 状态、preview contract 和 API mapper。

## 2026-06-17 - Browser e2e 覆盖 OA reverse 子集草稿闭环

- 目标：给进项发票使用情况补真实 Chromium 流，覆盖 rows 首屏、`以发票反提 OA` drawer、候选子集重新 preview、创建 OA 草稿、确认 `已提交 OA` 和 submitted history 展示。
- 影响范围：deterministic Playwright API mock、`web/e2e/input-invoice-usage-flow.spec.ts`、`npm run e2e:smoke` 和测试闭环文档；业务实现不变。
- 关键决策：mock 保持后端真实 contract 的 preview/draft/manual-status/history shape；e2e 明确断言子集 preview request 只携带当前勾选发票，并断言已提交历史不展示内部 batch id。
- 文档影响：更新本实施记录、`tests.md`、`state-machine.md`、`docs/dev/testing.md`、`docs/dev/nightly-ci.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：新增 `web/e2e/input-invoice-usage-flow.spec.ts`，并加入 `web/package.json` 的 `e2e:smoke`。
- 验证命令：`cd web && npx playwright test e2e/input-invoice-usage-flow.spec.ts`；完整最终命令见本轮最终说明。
- 未测风险：真实 OA 登录、公钥 RSA、草稿页面打开、人工提交、真实 Postgres/RabbitMQ/Redis worker drain 仍需 staging/发布前 smoke。

## 2026-06-17 - OA reverse 子集候选 preview hash 修复

- 目标：修复 `以发票反提 OA` drawer 中只勾选部分候选后点击 `创建 OA 草稿` 报 `OA reverse preview is stale. Refresh preview before creating an OA draft.` 的问题。
- 影响范围：`OaReverseWorkspaceDrawer` 创建草稿交互、OA reverse 前端回归测试和模块测试矩阵；后端 preview hash fail-fast 契约保持不变。
- 关键决策：不放松后端 stale 校验；前端创建草稿前按当前勾选发票和目标申请人重新请求 preview，使用刷新后的 `previewId`/`previewHash` 与有效候选发票创建草稿。
- 文档影响：更新本实施记录和 `tests.md` 历史 bug 回归库；状态机/API contract 未变化。
- 测试覆盖：更新 `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`，先验证旧行为会继续使用全量候选 hash，再改为断言子集创建前刷新 preview 并提交刷新后的 hash。
- 验证命令：`npm --prefix web test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`；`npm --prefix web test -- --run src/test/InputInvoiceUsagePage.test.tsx`；完整最终命令见本轮最终说明。
- 未测风险：真实 OA 草稿创建仍依赖 staging/生产 OA 登录和草稿接口 smoke；本修复只覆盖 FinOps 前端 preview/hash 提交流程。

## 2026-06-16 - 首屏 page-size 性能护栏证据

- 目标：补齐 P2/P3 大数据列表本地 synthetic SLO 与前端首屏请求证据，防止进项发票使用情况首屏请求把超大 page size 透传为全量读取。
- 影响范围：`InputInvoiceUsageQueryService.list_rows` 的分页 contract、`InputInvoiceUsagePage` 首屏 rows 请求回归和模块测试矩阵；业务行为不变。
- 关键决策：保留现有严格上限语义，`page_size=200` 为最大允许页大小，`page_size>200` 返回 `invalid_paging`，不做静默 clamp；前端默认继续使用更保守的 `page_size=20`，页大小选项限制为 20/50/100。
- 文档影响：更新 `tests.md` 与 P2/P3 closure ledger。
- 测试覆盖：新增 `InputInvoiceUsageQueryServiceTests.test_page_size_limit_protects_first_screen_slo`，用 250 行 synthetic 数据验证 200 行上限、total 保留和超限错误；更新 `web/src/test/InputInvoiceUsagePage.test.tsx` 锁定首屏 `page=1&page_size=20` 和 20/50/100 页大小选项。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_service.InputInvoiceUsageQueryServiceTests.test_page_size_limit_protects_first_screen_slo -v`；`npm --prefix web test -- --run src/test/InputInvoiceUsagePage.test.tsx src/test/OutputInvoiceCollectionsPage.test.tsx src/test/OaPendingPaymentsPage.test.tsx`。
- 未测风险：真实 PostgreSQL EXPLAIN、锁等待、浏览器滚动和导出下载性能仍需 staging/production smoke。
- 后续事项：如 API 层改变 page size 映射，必须同步保留 `invalid_paging` 或等价 fail-closed contract。

## 2026-06-12 - 统一 relation candidate 展示与 `+N` 详情闭环

- 目标：让进项发票使用情况页面和关联台使用同一 relation 读事实源，展示 linked 与未配对 candidate 关系，并修复点击 `+N` 详情后长期 loading。
- 影响范围：`workbench_relation` SQL projection、distribution mapper、`InputInvoiceUsageQueryService`、input usage relation detail API、SQL read model repository、模块/API/架构文档。
- 关键决策：open/proposed unmatched decision 通过 `WorkbenchRelationReadFacade` 分发为 `relationStatus=candidate`；candidate 不写入 confirmed relation，不参与支付状态；`relationStatus=linked` 才能证明已支付/已确认。详情接口新增 read-model detail service，优先按 row id 读取单行 payload。
- 文档影响：更新本实施记录、`README.md`、`state-machine.md`、`tests.md`、`docs/dev/api-contracts.md` 和 `docs/architecture/persistence-and-read-models.md`。
- 测试覆盖：新增/更新 projection、facade mapper、input usage service、API 和 repository runtime tests；前端沿用 `InputInvoiceUsagePage` 的多关系 `+N` 覆盖。
- 验证命令：本轮最终说明列出实际执行命令。
- 未测风险：真实生产数据量下的 worker drain 与浏览器手工 smoke 仍需 staging/发布前验证。

## 2026-06-12 - OA reverse relation command boundary Phase 7C

- 目标：把 OA reverse 检测到 OA evidence 后建立 OA/发票关系的写入口迁入统一 workbench relation command boundary，避免直接写 pair relation 事实源。
- 影响范围：`WorkbenchInputInvoiceUsageOaReverseRelationWriter`、Application OA reverse service wiring、OA reverse status refresh API error mapping、workbench relation/input invoice usage 测试矩阵。
- 关键决策：writer 写 `input_invoice_oa_reverse`，并把 `case_id`、row identity、actor、month scope、metadata、evidence、idempotency key 和 history operation 交给 `WorkbenchRelationCommandService.confirm_relation(...)`；缺 command service 或 read model non-fresh 时返回结构化错误，不保存本地 detected batch。
- 文档影响：更新本实施记录、`tests.md`，并同步 `docs/modules/workbench-relations/`。
- 测试覆盖：新增 service 测试覆盖 writer command delegation 和缺 command fail-fast；新增 API 测试覆盖 command stale/conflict 409 且无半写入；新增 runtime boundary guard 防止重新注入 pair service 或 direct pair mutation。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_input_invoice_usage_oa_reverse_service.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_input_invoice_usage_api.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py -q`。
- 未测风险：真实 OA evidence 来源仍使用本地 fake projection 测试；完整跨页面 read model smoke 和真实 worker drain 仍需后续闭环。
- 后续事项：继续收口 no-OA/turnover/batch accounting legacy repair/fallback，以及 relation command service 的生产级并发占用约束。

## 2026-06-11 - 测试闭环矩阵与 API 契约同步

- 目标：执行测试闭环 master goal 的 input-invoice-usage 模块轮次，审计进项发票使用页面/API/read model、OA 反提、目标申请人凭据、设置页 UI 和相关测试覆盖。
- 影响范围：本模块 `tests.md`、`state-machine.md`、`implementation-notes.md`；同步 `docs/dev/api-contracts.md` 中反提 OA 当前一键创建、目标申请人 token、`submitted_confirmed` 历史和 `not_submitted` 本地回滚语义。
- 关键决策：现有 P0/P1 测试已经覆盖 all scope freshness、rows/filter/detail/export、OA reverse preview/one-step draft/manual status/submitted history、credential service/API/PG encryption、target token provider、Settings UI 和 InputInvoiceUsage drawer；本轮不新增重复代码测试。
- 文档影响：将 `tests.md` 迁入闭环标准结构，补齐影响面清单、场景覆盖清单、七类测试适用性、历史 bug 回归库、关键 smoke flows、验证命令和未测风险。
- 测试覆盖：沿用现有 input invoice usage、invoice usage collection、OA reverse、credential、settings 前后端测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_input_invoice_usage_api tests.test_read_model_freshness -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_service tests.test_oa_applicant_credentials_api tests.test_postgres_oa_applicant_credentials_repository tests.test_postgres_migrations -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_target_oa_applicant_token_provider tests.test_input_invoice_usage_oa_reverse_service tests.test_postgres_input_invoice_usage_oa_reverse_repository -v`；`cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx src/test/SettingsPage.test.tsx src/test/WorkbenchSelection.test.tsx`。
- 未测风险：真实 OA 登录、公钥 RSA 加密、OA 草稿 URL 打开和人工提交仍需 staging/发布前联调；真实 Postgres/RabbitMQ/Redis 多 worker drain 仍由夜间或 staging smoke 覆盖。
- 后续事项：下一模块继续处理 `cost-statistics`。

## 2026-06-10 - 反提 OA 全链路回归与文档收口 Phase 5

- 目标：补齐跨模块 API 集成、未提交回滚重建测试、敏感信息检查和文档收口，确认 `以发票反提 OA` 从凭据维护到已提交历史的闭环。
- 影响范围：增强 `tests/test_input_invoice_usage_api.py`，新增管理员保存凭据后 full-access 用户创建 OA 草稿的 API 集成测试，以及 `未提交 OA` 后用新 idempotency key 重新创建草稿的 API 测试；更新测试矩阵和实现计划。
- 关键决策：API 层允许 `未提交 OA` 返回内部 `not_submitted` 状态，但业务可重建契约以 `canCreateDraft=true`、`oaDraftId=null`、`oaDraftUrl=null` 和再次创建成功为准；前端仍不展示该内部状态。
- 文档影响：更新本实施记录、测试矩阵和实现计划；状态机主规则保持不变，继续把 `未提交 OA` 视为不展示长期历史的本地回滚路径。
- 测试覆盖：新增 API 集成测试覆盖凭据 API -> target applicant login provider -> OA draft client -> 用户确认 -> 已提交历史；新增 API 回滚测试覆盖未提交后重新创建。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v`；完整目标回归命令见本次最终说明。
- 未测风险：真实 OA 登录接口、真实 RSA 公钥和真实 OA 草稿页面仍需生产发布前联调。
- 后续事项：发布前配置 `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY`、`FIN_OPS_OA_BASE_URL`、`FIN_OPS_OA_LOGIN_RSA_PUBLIC_KEY`，并在目标申请人测试账号上做一次草稿创建联调。

## 2026-06-10 - 进项发票使用页反提 OA UI 闭环 Phase 4

- 目标：把 `以发票反提 OA` 前端主路径收敛为单一 `创建 OA 草稿` 操作，并提供 `待处理 | 已提交` 视图、OA 草稿提交确认弹窗和未提交本地回滚。
- 影响范围：更新 `OaReverseWorkspaceDrawer`、进项发票使用页 API 接线、input invoice usage API/types、页面测试 mock 和前端样式；不改变后端 batch 的内部状态对象语义。
- 关键决策：前端不再暴露 `创建本地批次`、`刷新 OA 状态`、撤销草稿绑定或人工检测 fallback；创建草稿成功后只显示 OA 草稿链接与 `已提交 OA`/`未提交 OA` 确认；`未提交 OA` 清空当前前端 batch 并回到可重新创建状态；已提交历史只展示申请人、时间、金额、张数和发票摘要，不展示内部 id 或英文状态。
- 文档影响：更新本实施记录、实现计划、状态机和测试矩阵。
- 测试覆盖：`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` 覆盖 API mapper、一键创建草稿、确认弹窗、未提交回滚、已提交历史和隐藏旧控件；`web/src/test/InputInvoiceUsagePage.test.tsx` 覆盖页面入口接线到一键草稿 API 和已提交 tab。
- 验证命令：`cd web && npm test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`；`cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx`；`cd web && npm run build`。
- 未测风险：本地前端测试使用 mock API；真实浏览器连接生产后端和 OA 草稿页面打开行为仍需联调验证。
- 后续事项：Phase 5 运行完整后端/前端回归、做 secret 泄漏检查并收口文档。

## 2026-06-10 - 设置页 OA 申请人凭据管理 UI Phase 3

- 目标：让管理员 `YNSYLP005` 可在设置页维护目标 OA 申请人的 OA 登录账号密码，支撑后续 `创建 OA 草稿` 使用目标申请人身份登录。
- 影响范围：新增 `SettingsOaApplicantCredentialsSection`；扩展设置页导航、页面状态、workbench API client/types 和前端 mock；不改变普通 settings payload。
- 关键决策：`OA申请人凭据` section 仅 admin 可见；全操作非 admin 不展示入口；保存/清空凭据走 `/api/workbench/settings/oa-applicant-credentials` 独立接口；密码只存在于表单输入中，保存成功后清空，不回显到列表，不进入 `saveWorkbenchSettings(...)`。
- 文档影响：更新本实施记录、实现计划、设置模块状态机和测试矩阵。
- 测试覆盖：`web/src/test/SettingsPage.test.tsx` 覆盖管理员维护凭据、非 admin 隐藏、保存密码走独立 endpoint、普通 settings save 不含密码；`web/src/test/WorkbenchSelection.test.tsx` 覆盖既有关联台设置入口回归。
- 验证命令：`cd web && npm test -- --run src/test/SettingsPage.test.tsx`；`cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx`。
- 未测风险：尚未在真实浏览器连接生产后端验证凭据保存；完整 `待处理 | 已提交` drawer UI 和创建草稿确认流仍待 Phase 4。
- 后续事项：Phase 4 实现进项发票使用页面 `创建 OA 草稿`、确认弹窗和已提交历史。

## 2026-06-10 - 目标 OA 申请人创建草稿后端闭环 Phase 2

- 目标：把 `创建 OA 草稿` 后端路径从“当前操作人 token”切到“目标 OA 申请人凭据/token”，并提供前端后续一键创建和历史展示所需 API。
- 影响范围：新增 `TargetOaApplicantTokenProvider`、`OaLoginClient` 和 OpenSSL RSA 密码加密；扩展 `InputInvoiceUsageOaReverseService` 一步创建草稿、手动确认语义和已提交历史；扩展 PG batch repository 的 status 查询；新增 `/api/input-invoice-usage/oa-reverse/oa-draft` 和 `/submitted-history` API；旧 batch 草稿接口也改为按 batch 目标申请人取 token。
- 关键决策：preview hash 过期、候选失效或凭据缺失时不创建内部 batch；创建 OA draft 仍写内部 batch 作为状态对象但不暴露为用户入口；目标申请人登录失败、RSA 配置缺失或 OA 外部失败返回结构化错误且不包含密码/token；`submitted` 手动确认落为 `submitted_confirmed`，`not_submitted` 清理本地 `oaDraftId`/`oaDraftUrl`/OA row 字段后允许重新创建。
- 文档影响：更新本实施记录、状态机、测试矩阵、实现计划和 OA 部署环境变量说明。
- 测试覆盖：新增 token provider/OA login client 单测、一步创建 service/API 测试、PG repository status 查询测试；更新手动确认、未提交回滚和已提交历史 shape 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_target_oa_applicant_token_provider -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_oa_reverse_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_input_invoice_usage_oa_reverse_repository -v`。
- 未测风险：本地测试使用 fake login client 和 fake OA draft client，未真实连通 OA 登录接口；生产发布前必须配置 `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY`、`FIN_OPS_OA_LOGIN_RSA_PUBLIC_KEY`，确认 runtime 可执行 `openssl`，并做一次目标申请人登录和 OA 暂存草稿联调。
- 后续事项：Phase 3 实现设置页凭据管理 UI；Phase 4 实现进项发票页面 `待处理 | 已提交` 和 `创建 OA 草稿` 用户闭环。

## 2026-06-10 - OA 申请人凭据管理后端闭环 Phase 1

- 目标：先完成设置页后端凭据管理能力，为后续 `创建 OA 草稿` 使用目标 OA 申请人登录态提供事实源。
- 影响范围：新增 `OaApplicantCredentialService`、内存/PG repository、`app.oa_applicant_credentials` 迁移、`/api/workbench/settings/oa-applicant-credentials` API；未改动当前 OA draft 创建路径。
- 关键决策：凭据管理 admin-only；`YNSYLP005` 默认 admin 可维护；全操作非 admin 不能维护；密码只写不读，API 只返回 `已配置`/`未配置`；普通 `/api/workbench/settings` 不包含密码或凭据 payload。
- 文档影响：更新本实施记录、测试矩阵、状态机，以及设置模块状态机/测试矩阵。
- 测试覆盖：新增 service、API、Postgres repository 和迁移契约测试，覆盖权限、非敏感响应、PG 加密 SQL、迁移 schema。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_oa_applicant_credentials_repository -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v`。
- 未测风险：Phase 1 尚未接入 OA 登录/token provider，也未改前端设置页；生产环境必须配置 `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY` 后才能在 PostgreSQL 模式保存/读取凭据。
- 后续事项：Phase 2 将使用该凭据事实源实现目标 OA 申请人 token provider，并替换当前从操作人请求 header 取 token 的创建草稿路径。

## 2026-06-10 - 以发票反提 OA 实现计划

- 目标：为 `以发票反提 OA` 闭环生成可由 Codex 分阶段执行的生产级实现计划。
- 影响范围：计划覆盖后端凭据管理、目标申请人 token provider、一键创建 OA 草稿、设置页凭据 UI、`待处理 | 已提交` 前端闭环、集成测试和文档收口。
- 关键决策：先落后端凭据管理，再落目标申请人 token provider 和一键草稿创建，随后实现设置页与进项发票页面 UI，最后做全链路回归；每个阶段都要求先测试、再实现、再维护文档。
- 文档影响：新增 `oa-reverse-implementation-plan.md`，并在 `README.md` 登记。
- 测试覆盖：计划阶段未改业务代码；计划要求实施阶段覆盖七类测试中的业务核心、service、API、前端交互、集成和既有回归。
- 验证命令：文档计划阶段未运行自动化测试；已通过读取计划文件和 `git diff` 检查内容。
- 未测风险：计划中的加密实现需要实施阶段根据 `backend/requirements.txt` 和运行环境确认是否可复用现有库；如需新增依赖必须先停下确认。
- 后续事项：按 `oa-reverse-implementation-plan.md` 的 Phase 1 prompt 开始实现。

## 2026-06-10 - 以发票反提 OA 闭环设计

- 目标：明确进项发票使用情况页面中 `以发票反提 OA` 的生产级闭环设计。
- 影响范围：设置页目标 OA 申请人凭据管理；输入发票使用页面 OA 反提 drawer；后端 OA reverse service、凭据 service/repository、target applicant token provider、OA draft client 集成；已提交历史展示。
- 关键决策：前端不暴露 `创建本地批次`；batch 仅作为内部状态对象；创建 OA 草稿使用目标 OA 申请人凭据/token；FinOps 只创建 `isDraft=true` 暂存草稿，不自动提交 OA；用户选择 `未提交 OA` 时只回滚本地状态，不删除 OA 暂存草稿。
- 文档影响：新增 `oa-reverse-design.md`，更新 `README.md`、`state-machine.md` 和 `tests.md`。
- 测试覆盖：当前为设计阶段；实施时必须按 `tests.md` 的七类测试矩阵补齐权限、凭据、服务、API、前端交互、集成和回归测试。
- 验证命令：文档设计阶段未运行自动化测试；实施后按具体代码变更运行后端 unittest、前端组件测试和构建。
- 未测风险：OA 外部系统登录、token 缓存和 form draft API 需要在实现阶段用 mock/contract 测试保护，并在生产发布前做联调验证。
- 后续事项：生成分阶段实现 prompt；每个大阶段完成后维护本模块文档和状态机文档。

## 2026-06-10 - all scope source_versions 聚合修复

- 目标：修复“进项发票使用情况”默认不传 `month` 时页面没有加载数据的问题。
- 真实原因：生产 read model 行数据和月 scope 均存在且 fresh，但 repository 在 all scope 聚合时要求所有月份的完整 `source_versions` 字典完全相等；不同月份的 `workbench_relation_source_versions` 嵌套时间戳不同，导致 all scope 返回 `{}`，API 随后以 `api_source_versions_stale` 返回 `202/refreshing` 和空 rows。
- 影响范围：`PostgresReadModelRepository._invoice_relation_scope_row` 的 all scope source_versions 聚合；输入发票使用页面 rows API；同 helper 也服务于 output invoice collection all scope。
- 关键决策：all scope 仍要求各月 cache status 为 fresh；版本聚合改为保留各月份共同一致的顶层 source version 字段，差异字段从 all scope source_versions 中剔除。
- 文档影响：更新 `state-machine.md` 的 read model 状态规则与 `tests.md` 的测试矩阵。
- 测试覆盖：新增 repository 回归测试和 API 正向契约测试；保留 source version 缺失返回 refreshing 的反向测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness -v`；`cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx`；`cd web && npm run build`。
- 未测风险：本地验证已完成；生产仍需部署后只读验证默认 rows API 是否返回 `fresh` 与非空分页总数。
- 后续事项：发布必须走 `./scripts/deploy-oa.sh` 或现有运维流程，不直接在服务器热改代码。

# OA待付款核对 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 2026-06-23 - 右侧抽屉候选流水按已选 OA 月份收敛

- 目标：修复 OA 待付款核对进行中视图中，勾选 OA 后打开“关联支出流水”右侧抽屉长期停留在“加载中”的问题。
- 影响范围：`OaPendingPaymentCommandService.bank_transaction_candidates`、`fetchOaPendingPaymentBankCandidates`、`OaBankLinkDrawer`、API/command/page 回归测试和本模块维护文档；`link-bank-transactions` 提交、pending relation、bank claim 和自动写回语义不变。
- 真实原因：抽屉虽然从一个已选 OA 打开，但前端没有把已选 OA row id 传给候选接口；后端因此每次都按 `month=all` 读取全部历史支出流水，并为这些历史流水计算 Workbench active relation 与 OA pending bank claim 状态。生产历史流水多时，金额搜索如 `2152` 仍要先完成全量候选与关系状态扫描，页面就表现为右侧抽屉一直“加载中”。这不是流水不存在，也不是前端筛选按钮问题。
- 关键决策：抽屉有已选 OA 上下文时，前端必须传 repeated `oa_row_ids`；后端基于这些 OA 的 `month` 得出候选月份，只读取对应月份的支出流水并去重，再执行 relation status 和关键字筛选。没有 OA 上下文的旧调用继续保留 `all` 语义；有 OA id 但无法解析月份时返回空候选，不回退到全量历史扫描。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md`、`e2e-spec.md` 和 `e2e-coverage.md`；产品口径仍是“人工抽屉作为自动匹配失败后的兜底”，只是候选读取边界从全量历史收敛到已选 OA 所在月份。
- 测试覆盖：新增 `tests/test_oa_pending_payment_command_service.py::OaPendingPaymentCommandServiceTests::test_bank_transaction_candidates_uses_selected_oa_month_scope` 和 `::test_bank_transaction_candidates_with_selected_oa_does_not_fallback_all_when_month_missing`；更新 `tests/test_oa_pending_payment_api.py::OaPendingPaymentApiTests::test_bank_transaction_candidates_route_delegates_to_command_service` 锁定 repeated `oa_row_ids` 透传；更新 `web/src/test/OaPendingPaymentsPage.test.tsx::switches to in-progress OA view and links bank payment with automatic writeback` 锁定抽屉候选请求携带已选 OA row id。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：本地自动化没有连接真实生产 OA/Mongo/PostgreSQL/银行流水库和真实浏览器会话；发布后仍需用截图中的 `2152.80` 进行中 OA 样本确认候选接口返回对应月份流水，并观察生产请求耗时。

## 2026-06-23 - 多 OA 多流水 relation 聚合成员补全

- 目标：修复 OA 待付款核对中同一 Workbench active relation 已包含多条 OA 与多条支出流水时，OA 侧可能只显示主 OA 金额、缺少 `+N`，并把支出合计大于主 OA 金额误判为 `pending_review` 的场景。
- 影响范围：`OaPendingPaymentQueryService` relation group 构建、`DistributedInvoiceRelationContext` OA row lookup 使用、服务层回归测试和本模块测试矩阵；前端 API contract 不变，继续消费 `oa.relationCount/detailMode/summaries` 与 `bankTransaction.relationCount/detailMode/summaries`。
- 关键决策：relation 分组时不能只使用当前视图首轮 `list_all_application_records()` 中已经枚举到的主 OA；必须基于 relation 的 OA row ids 通过 OA projection lookup 补齐同一 relation 内可权威读取的 OA records，再计算 OA 合计、付款状态和 `+N`。进入聚合行的 OA 成员继续作为同一 relation owner，不再生成 standalone OA pending row。
- 文档影响：更新 `tests.md`；产品/API 长期口径不变，这是对既有“多 OA/多流水 relation 聚合成一行”合同的补漏。
- 测试覆盖：新增 `tests/test_oa_pending_payment_service.py::OaPendingPaymentQueryServiceTests::test_relation_group_loads_all_oa_members_from_projection_lookup_and_suppresses_standalone_rows`，复现 list-all 只返回主 OA 但 relation lookup 能读出 3 条 OA 的场景，断言 rows 只返回 1 条聚合行、OA 合计 `587000.00`、OA `relationCount=3`、流水 `relationCount=4` 且付款状态为 `paid`。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：本地 synthetic projection 不替代真实生产 OA Mongo/Postgres projection、真实 worker drain 和截图样本 read model 重建；发布后需要用该 relation 样本确认 rows payload 的 `oa.summaries` 完整并且页面显示 OA `+2`。

## 2026-06-22 - completed OA 已匹配流水自动写回补漏

- 目标：修复 OA 待付款核对页 completed OA 已显示支出流水配对但 `oaPaymentWriteback` 仍为“未写回”的场景，并处理截图中自动写回请求被 `/fin-ops/api/*` SPA HTML fallback 吞掉后无法命中后端 API 的问题。
- 影响范围：`OaPendingPaymentCommandService` active relation ID 解析、共享 `apiClient` HTML fallback、`OaPendingPaymentsPage` 自动写回失败后的重试行为、command/api/page 前端测试和本模块状态机/测试矩阵；业务口径不变，仍是 completed/in-progress 已有有效支出流水 active relation 且金额相等时自动写回 `t_payment_simple.pay_status=1`。
- 关键决策：自动写回处理 existing active relation 时，不能只依赖 `row_ids/row_types` 同时存在；部分 relation/distribution payload 可能有 `oa_row_ids`、`bank_transaction_ids` 或 camelCase 字段但 `row_types` 为空。命令服务现在先读显式 OA/银行 ID 字段，再按 `row_ids` 和 row id 前缀推断类型，避免静默跳过 completed 写回。前端 API fallback 同时兼容根 `/api/*` 和 `/fin-ops/api/*` 返回 HTML 的路径错配；自动写回请求失败后不把 scope 永久标记完成，用户刷新后可重试。
- 文档影响：更新 `state-machine.md` 和 `tests.md`；部署长期口径仍要求 Nginx `/api/`、`/fin-ops/api/`、`/fin-ops-api/` 都返回 JSON API，不应依赖前端 fallback 作为唯一修复。
- 测试覆盖：新增 `tests/test_oa_pending_payment_command_service.py::OaPendingPaymentCommandServiceTests::test_auto_reconcile_writes_completed_oa_from_explicit_relation_ids_when_row_types_are_missing`；新增 `web/src/test/apiClient.test.ts::falls back to canonical fin-ops API prefix when a fin-ops relative API request returns HTML`；新增 `web/src/test/OaPendingPaymentsPage.test.tsx::retries auto reconcile after a failed attempt when the user refreshes rows`；既有 API/page 回归继续覆盖 auto-reconcile 路由、写后 barrier 和页面自动写回。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：本地没有真实 OA MySQL、生产 Nginx、真实 OA/Mongo/PostgreSQL/RabbitMQ worker drain；发布后仍需用截图中 completed OA 样本确认 `/fin-ops-api/api/oa-pending-payments/auto-reconcile-bank-transactions` 返回 JSON，`t_payment_simple.flow_id` 对应记录变为 `pay_status=1`，read model fresh 后页面显示“已写回”。

## 2026-06-22 - 自动匹配等待 read model fresh 与 API fallback

- 目标：修复 OA 待付款核对页在 rows/read model 仍显示“同步中”时仍立即触发后台自动匹配/写回，并且当根 `/api/*` 请求被前端 HTML fallback 吞掉时把 `接口返回了 HTML 页面` 错误直接暴露给用户的问题。
- 影响范围：`OaPendingPaymentsPage` 自动匹配 effect、共享 `apiClient` HTML fallback 处理、前端回归测试和本模块状态机/测试矩阵；后端 API endpoint、匹配规则、read model freshness gate 和 OA MySQL 写回语义不变。
- 关键决策：自动匹配/写回是写命令，必须在 rows/filter-options 加载完成且 `oa_pending_payment` read model 为 fresh 后才触发；refreshing/stale/unavailable 或 rows 加载失败时只展示同步/错误状态，不叠加写命令。前端 API 仅在 `/fin-ops/` 页面下确认根 `/api/*` 返回 HTML shell 时重试 canonical `/fin-ops-api/*`，JSON 错误和非 HTML 响应仍按原契约处理。
- 文档影响：更新 `state-machine.md` 和 `tests.md`；部署/Nginx 长期口径不变，真实代理仍应保证 `/api/`、`/fin-ops/api/`、`/fin-ops-api/` 返回 JSON API 而不是 HTML。
- 测试覆盖：新增/更新 `web/src/test/OaPendingPaymentsPage.test.tsx::does not auto reconcile while OA pending payment read model is still refreshing` 和 `web/src/test/apiClient.test.ts::falls back to canonical fin-ops API prefix when root API returns the SPA shell under fin-ops`。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：生产 App Status 中 `Workbench read model generation consistency failed` 仍表示运行时/worker/readiness 层有独立问题，需要用生产只读 App Health、dirty scopes、outbox 和 worker journal 继续定位；本地修复只防止页面在 non-fresh 状态下额外发写命令，并提高 API prefix 临时错配恢复能力。

## 2026-06-22 - 自动匹配跳过诊断

- 目标：排查“金额、对方名和日期看似满足规则但未自动配对”的进行中 OA 场景，补齐自动匹配失败的可观测性。
- 影响范围：`OaPendingPaymentCommandService.auto_reconcile_bank_transactions` 响应、前端 `AutoReconcileOaPendingPaymentBankTransactionsResponse` 类型、command service 回归测试和本模块测试矩阵；自动匹配业务规则不变。
- 关键决策：规则层已能对“云南心诚环保科技有限公司 / 7000 / 2026-04-16 -> 2026-04-23”生成 `oa_bank_exact_amount` 候选；当候选在确认 relation、解析 `flow_id` 或 OA MySQL 写回阶段失败时，后端不再静默吞掉，而是在 `skippedAutoMatches` 返回 OA/流水 row、规则码、错误码、消息和 details，便于现场判断是 row 占用、`flow_id` 缺失、写回不可用还是 relation 冲突。
- 文档影响：更新本实施记录和 `tests.md`；产品口径、状态机和 read model freshness 语义不变。
- 测试覆盖：新增 `tests/test_oa_pending_payment_command_service.py::OaPendingPaymentCommandServiceTests::test_auto_reconcile_reports_skipped_exact_match_when_flow_id_is_missing`。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：本地没有真实生产 OA/Mongo/MySQL/PostgreSQL 数据，无法直接确认截图中那条记录的生产 `flow_id`、active relation 占用和写回错误；发布后需要用该月份调用 auto-reconcile 接口查看 `skippedAutoMatches`。

## 2026-06-22 - 自动匹配 relation 持久化闭环

- 目标：修复生产 `威斯达昆明信息技术有限责任公司 / 163000 / 2026-02` 自动匹配返回成功后，页面 read model 仍显示未关联支出流水，且重复执行 auto-reconcile 仍继续返回相同 3 条自动匹配的问题。
- 影响范围：`Application._oa_pending_payment_command_service` 的 Workbench relation command service 组装、OA 待付款自动匹配 relation 持久化、重复执行幂等性和 read model 刷新；匹配规则、前端 API contract、OA MySQL 写回逻辑不变。
- 关键决策：真实原因不是规则不匹配，也不是 OA 支付状态未写回。生产验证显示目标 `flow_id=69a262c6db8c0a3633bd74a2` 已经 `pay_status=1`，但 `active_relations_for_row_ids` 查不到 `oa-pay-69a262c6db8c0a3633bd74a2` / `txn_imported_1185` 的 active relation，read model 因没有持久化 relation 继续判定“未关联支出流水”。OA 待付款命令服务原来注入默认 `_workbench_relation_command_service()`，该默认 repository 只更新当前进程内存 snapshot；不像 Workbench 主路由那样在路由层另行调用 `_persist_workbench_pair_relations`。现在 OA 待付款命令服务注入 `repository=self._state_store`，让自动确认 relation 同步落持久层，worker/read model 和后续进程都能读到。
- 文档影响：更新本实施记录和 `tests.md`；产品口径、匹配规则、状态机和接口字段不变。
- 测试覆盖：新增 `tests/test_oa_pending_payment_api.py::OaPendingPaymentApiTests::test_auto_reconcile_persists_relation_and_reload_is_noop`，断言第一次 auto-reconcile 后 state store 持久化 OA-bank relation；用同一 data dir 重建应用后再次 auto-reconcile 必须 `autoMatchedCount=0`、`writebackCount=0`、不重复写回。
- 生产验证：发布 release `main-6652abe4-20260622124730` 后，目标自动匹配 relation `OA-PAY-63d72411227871d3` 已持久化，row_ids 为 `oa-pay-69a262c6db8c0a3633bd74a2` 与 `txn_imported_1185`；重建应用实例后 active relation 可读，重复 auto-reconcile 返回 `autoMatchedCount=0`、`writebackCount=0`；`oa_pending_payment:2026-02` read model fresh，目标行 `paymentStatus=paid`，`bankTransaction.primaryBankTransactionId=txn_imported_1185`，金额 `163000.00`。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：未跑浏览器端截图验证；后端生产 read model payload 已确认页面表格使用的 `bankTransaction` 字段完整。

## 2026-06-22 - 进行中 OA 自动匹配投影源闭环

- 目标：修复生产 `威斯达昆明信息技术有限责任公司 / 163000 / 2026-02` 页面 fresh 展示进行中 OA，但页面级 auto-reconcile 没有自动关联同名同额支出流水的问题。
- 影响范围：`Application._oa_pending_payment_projection` 的服务组装缓存边界、`OaPendingPaymentCommandService.auto_reconcile_bank_transactions` 的 in-progress OA 输入、应用层 API 回归测试和本模块测试矩阵；匹配规则、API endpoint、read model freshness 语义不变。
- 关键决策：真实原因不是 OA-bank 规则不匹配。生产诊断显示 read model 中目标 OA `oa-pay-69a262c6db8c0a3633bd74a2` fresh 存在，支出流水 `txn_imported_1185` eligible；但命令服务的 payment-admitted projection 被生产启动时显式传入的 `PostgresOAProjectionAdapter` 缓存污染，实时扫描 `in_progress_records=0`。显式 `source_adapter` 创建的 OA 待付款投影现在只作为调用点局部对象，不写入默认 lazy projection 缓存；自动匹配命令默认 lazy path 会重新使用 Mongo-backed source adapter，确保与页面 in-progress OA 可见性一致。
- 文档影响：更新本实施记录和 `tests.md`；产品口径、状态机、匹配规则和 read model freshness 语义不变。
- 测试覆盖：新增 `tests/test_oa_pending_payment_api.py::OaPendingPaymentApiTests::test_auto_reconcile_uses_payment_admitted_source_after_completed_projection_cache`，复现生产初始化顺序：先用 completed/Postgres 投影创建显式 projection，再执行 auto-reconcile，断言仍能读取 payment-admitted in-progress OA 并生成 `oa_bank_exact_amount` 写回。
- 验证命令：本轮最终说明列出完整命令。
- 生产验证：发布 release `main-6652abe4-20260622124730` 后，目标 2026-02 样本能生成并确认 `oa_bank_exact_amount`；详见上方 relation 持久化闭环验证。
- 未测风险：未跑浏览器端截图验证。

## 2026-06-22 - 撤销 completed 指纹排除，进行中只按 flow_id 准入

- 目标：修正“completed 正本排除 in-progress 影子行”的错误口径。业务允许同项目、同供应商、同金额、同事由发起多张不同 OA；这些字段不是付款申请唯一身份。
- 关键决策：`in_progress` 主行身份只由 `t_payment_simple.flow_id` 准入、OA Mongo `_id` 匹配和当前 workflow status 决定。不得再用 completed projection 的业务字段指纹反向排除进行中 OA；不同 `flow_id` 必须作为不同付款申请保留。
- 测试覆盖：更新 `tests/test_oa_pending_payment_service.py::OaPendingPaymentQueryServiceTests::test_in_progress_view_keeps_payment_admitted_record_when_completed_projection_has_same_business_record`，锁定 completed 中存在同业务字段正本时，payment-admitted 的进行中 OA 仍展示。
- 风险控制：展示层保留不同 flow id；自动匹配层若同一支出流水同时命中多张同额 OA，不能强行确认，应按既有冲突/歧义路径留给人工关联或更强证据判定。

## 2026-06-22 - 已完成 OA 的进行中影子行去重（已撤销）

- 目标：修复生产 `云南心诚环保科技有限公司 / 7000 / 2026-04` 在“进行中 OA”中显示未配对，但真实 completed 行已关联支出流水的重复展示问题。
- 影响范围：`OaPendingPaymentQueryService` 的 in-progress 视图过滤、`invoice-usage-collection` 重建 `oa_pending_payment` read model 的结果、服务层回归测试和本模块测试矩阵；Workbench relation、自动匹配规则和前端 API contract 不变。
- 关键决策（历史，已撤销）：当时认为生产中旧 in-progress 行使用 Mongo 旧 row id（如 `oa-pay-69e5c2a3...`）、真实 completed 行使用请求号 row id（如 `oa-pay-2094`），两者业务字段相同但 row id 不同，因此用月份、类型、申请人、项目、对方、金额、申请日期、开户行、收款账号和事由组成业务指纹排除 in-progress payment-admitted 记录。该假设后来被确认不成立，因为业务允许相同业务字段的不同 OA。
- 文档影响：更新本实施记录和 `tests.md`；产品口径不变，仍是 completed/in-progress 两视图，只是避免同一业务单跨投影重复展示。
- 测试覆盖（历史，已替换）：原 `test_in_progress_view_hides_payment_admitted_shadow_when_completed_projection_has_same_business_record` 已由保留不同 flow id 的回归测试替代。
- 生产验证：发布 release `main-6652abe4-20260622115629` 后重建 `oa_pending_payment:2026-04`，rows API 返回 `in_progress.total=0`、`summary.viewCounts.in_progress=0`；completed 视图保留 `oa-pay-2094`，付款状态 `paid`，支出流水 `txn_imported_1521`。
- 未测风险（历史，已关闭）：真实业务已确认允许同日同申请人同项目同对方同金额同账号同事由的两张不同付款申请，因此不能使用业务指纹作为跨 flow id 排除依据。

## 2026-06-22 - 刷新态分页与自动写回幂等闭环

- 目标：修复 OA 待付款核对页 rows read model 刷新中时分页显示 `NaN-NaN / undefined`，并避免已有 active 支出流水 relation 且 OA 已写回时，页面级自动写回每次进入页面都重复入队刷新，导致用户长期看到“数据正在刷新”。
- 影响范围：`OaPendingPaymentsPage`、`OaPendingPaymentsTable`、`OaPendingPaymentReadModelService.refreshing_rows_payload`、`OaPendingPaymentCommandService` 自动写回分支、组件/API/command 回归测试和本模块测试矩阵；业务匹配规则、read model freshness gate 和 API endpoint 不变。
- 关键决策：刷新态 payload 也必须返回稳定 `summary.rowCount=0` 与 `summary.viewCounts` shape；前端分页只信任有限数值并把缺失/非数值 total 归零，不用 `0 || undefined` 这类 truthy fallback。已有 relation 的自动写回先读取同一 `flow_id` 当前支付状态，已经 `pay_status=1` 时视为 no-op，不增加 `writebackCount`、不返回写回记录、不触发 read model refresh。
- 文档影响：更新本实施记录和 `tests.md` 历史 bug 回归库；长期产品/API 口径不变。
- 测试覆盖：后端 command 测试覆盖“active relation 且 OA 已写回”no-op，不重复 mark-paid 或入队；API 测试覆盖 rows/filter-options refreshing payload summary shape；前端 Vitest 覆盖 refreshing rows 空 summary 时不显示真实空态，也不渲染 `NaN` 或 `undefined` 分页。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_command_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_payment_status_service -v`；`cd web && npx vitest run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npm run build`。
- 未测风险：本地自动化没有连接真实 OA MySQL/PostgreSQL/RabbitMQ/Redis/systemd worker drain；真实环境仍需在发布后确认 App Health 的 `oa_pending_payment` read model 从 refreshing 回到 fresh，且 rows 分页不再出现 `NaN/undefined`。

## 2026-06-22 - 写后 operation barrier

- 目标：修复写操作成功后前端立即刷新 rows，可能读到旧 `oa_pending_payment` read model 的缺口。该记录创建时覆盖进行中 OA `confirm-paid`、`link-bank-transactions` 和支出流水无需开票规则保存；2026-06-22 自动匹配/写回上线后，前端主写回入口由 auto-reconcile 替代 `confirm-paid`。
- 影响范围：`OaPendingPaymentsPage`、`PendingInvoiceRulesDrawer` async callback contract、`operationBarrier` 前端 label、`OaPendingPaymentsPage.test.tsx` 和本模块测试矩阵；后端 API contract 不变，confirm/link 继续复用响应中的 `readModelRefresh.scopeKeys`。
- 关键决策：前端写 API 成功后先用当前页面可见 scope 构造 `oa_pending_payment` operation barrier target，barrier fresh 后才 `loadRows("refresh")`；barrier blocked/timeout 属于 post-commit 同步未完成，只显示“后台同步尚未完成”，不把已成功写入渲染成操作失败，也不提前读取旧投影。
- 测试覆盖：新增/维护 Vitest 回归，锁定写回、link-bank 和规则保存，在 barrier resolve 前不得增加 rows 请求，且 barrier request body 使用 `oa_pending_payment:all`。
- 验证命令：`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`。

## 2026-06-22 - OA 自动匹配支出流水并自动写回

- 目标：取消 OA 待付款页面的人工写回入口，让进行中 OA 自动匹配未配对支出流水；completed 和 in-progress 只要已有有效支出流水 active relation 且金额相等，都自动写回 `t_payment_simple.pay_status=1`。
- 影响范围：`OaPendingPaymentCommandService`、`/api/oa-pending-payments/auto-reconcile-bank-transactions`、`link-bank-transactions` 响应、`OaPendingPaymentsPage` 自动 reconcile effect、`OaPendingPaymentsTable`、前端 API/types、Browser mock、模块/API/E2E 文档和相关测试。
- 关键决策：自动匹配只复用关联台 OA-bank 精确金额/精确合计规则；不做模糊匹配。候选 relation 不写回；写回必须基于 completed Workbench active relation、in-progress active pending relation 或自动命令刚确认的 pending relation，并通过 outflow、金额相等和 `flow_id` 校验。支出流水抽屉保留为自动匹配失败后的人工兜底，但提交成功后同样自动写回。
- 文档影响：更新 README、state-machine、tests、e2e-spec、e2e-coverage、implementation-notes 和 `docs/dev/api-contracts.md`。
- 测试覆盖：后端 command/API 覆盖自动匹配未配对支出流水、已有 relation 写回、link-bank 自动写回和金额不匹配不写回；前端 Vitest 覆盖 auto-reconcile、无人工按钮、operation barrier、link-bank 写回消息；Playwright 覆盖自动写回成功/失败和抽屉关联后自动写回。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：本地 mock/单测不替代真实 OA MySQL、真实 OA Mongo 字段变体、真实 Workbench 大数据和生产 worker drain；需要 staging 用真实进行中 OA 与支出流水样本做 smoke。

## 2026-06-22 - 进行中 OA relation 独立事实源与 promotion 闭环

- 目标：修复进行中 OA 自动/人工关联支出流水后进入关联台的问题，并解决 OA 从进行中变为已完成后的关系归属闭环。
- 影响范围：`OaPendingPaymentCommandService`、`OaPendingPaymentQueryService`、`OaPendingPaymentRelationPromotionService`、`PostgresOaPendingPaymentRelationRepository`、`SnapshotOaPendingPaymentRelationRepository`、`OAProjectionSyncService`、`WorkbenchRelationSqlProjectionBuilder`、Postgres migration 0073、worker 组装链路、模块文档和测试矩阵。
- 关键决策：进行中 OA 的 OA-流水关系写入 `app.oa_pending_payment_bank_relations`，支出流水占用写入 `app.bank_transaction_relation_claims`，不写 `app.workbench_pair_relations`。关联台 read model 读取 active pending bank claim 后排除对应流水，避免它作为未配对/候选进入关联台。OA sync 发现 active pending relation 的所有 OA row 已 completed 后，复用 Workbench relation command promotion 成普通 `manual_confirmed`/`normal_match` active relation，并把 pending relation 标记为 `promoted`、释放 claim。
- 迁移决策：migration `0073_oa_pending_payment_bank_relations.sql` 将历史 `special_metadata.origin=oa_pending_payment_in_progress` 的 Workbench active relation 迁移到 OA 待付款独立 pending relation 和 bank claim，同时撤回旧 Workbench active relation，避免关联台继续显示进行中 OA。
- 性能决策：候选排除走月度 active claim 集合和索引，Workbench active generation 与 workbench relation projection 每个 scope 各一次查询 active pending bank claim，避免逐行查库；pending relation 查询使用 GIN overlap 索引。
- 测试覆盖：新增/更新 command/API/query service 测试、Workbench relation SQL projection 测试、promotion service 测试、OA sync promoter fan-out 测试、migration schema/allowlist 测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_command_service tests.test_oa_pending_payment_api tests.test_oa_pending_payment_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_sql_projection tests.test_oa_pending_payment_relation_promotion_service tests.test_oa_projection_sync_service tests.test_postgres_migrations -v`。
- 未测风险：未在真实生产 Postgres 上执行 migration 0073、真实 OA sync promotion、真实 worker drain 和真实页面 smoke；发布后需确认历史 `origin=oa_pending_payment_in_progress` Workbench active relation 已撤回，pending relation promotion 后关联台出现普通 completed relation。

## 2026-06-22 - OA 待付款表格 OA 区域五列压缩

- 目标：让 OA 大列内直接显示“申请人 / 项目 / 申请事由 / 对方户名 / 金额”，同时压缩申请人内部列和发票大列宽度，降低用户横向滚动成本。
- 影响范围：`OaPendingPaymentsTable`、`OaPendingPaymentOaSummary` 前端类型、`styles.css` OA pending table 规则、`OaPendingPaymentsPage.test.tsx` 和本模块测试矩阵；后端 rows 已输出 `oa.reason` 与 `oa.counterpartyName`，API contract 不变。
- 关键决策：不新增前端伪筛选字段；申请事由和对方户名只作为 OA payload 展示，若后端为空则显示 `-`。发票列继续纵向展示但从 20% 收窄到 13%，支付状态列收窄到 8%，OA 大列扩到 40% 以容纳五个内部字段。
- 文档影响：更新本实施记录、`state-machine.md` 历史变更和 `tests.md` 布局回归口径。
- 测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，覆盖 OA 内部五列 DOM、申请事由/对方户名内容、压缩字号、发票列/支付状态列宽和 OA grid CSS contract；Browser e2e 继续覆盖真实 Chromium 无横向滚动。
- 验证命令：本轮最终说明列出完整命令。

## 当前决策

- OA 待付款列表以 OA application 为主行；银行流水、进项发票和 relation 只是付款证据或详情证据。
- completed 视图以 Workbench active relation 作为 OA/支出流水/进项发票关联关系事实源；in-progress 视图以 OA 待付款独立 pending relation 作为 OA/支出流水关系事实源。多 OA、流水或发票在同一 relation 中必须聚合成一条核对行，并通过 `relationCount`/`summaries` 展开详情。
- `paymentStatus` 由 `InvoiceLifecyclePolicy` / `OaPendingPaymentQueryService` 判定，前端不得按金额字段自行推断。
- `paymentStatus` 不输出 `overpaid` 或 `merged_paid`；支出流水合计大于 OA 合计进入 `pending_review`，多 OA 合并付款先按 relation group 合计后再判定。
- `/oa-pending-payments` 通过 `view_mode=completed|in_progress` 承载同一页面的两类 OA：completed 是原待付款核对，in_progress 只展示 OA 系统仍进行中的支付申请/日常报销。
- OA 待付款核对的 OA 范围以 OA MySQL `t_payment_simple.flow_id` 为准。页面/read model 先用该字段匹配 OA Mongo `form_data._id`，再按 OA 当前 workflow status 分配到 completed/in-progress；未进入 `t_payment_simple` 的重复/异常 OA 不进入正常表格。
- `t_payment_simple.id` 不是 OA ID，只能作为支付状态记录诊断字段；支付状态展示、tab 统计和写回闭环都必须围绕同一 `flow_id`。
- 页面切换按钮数量来自 rows `summary.viewCounts.completed/in_progress`，统计口径与当前搜索/筛选条件一致，并且使用同一批 `t_payment_simple.flow_id` 准入后的 OA。
- completed 与 in_progress 视图展示同一套 OA、支付状态、支出流水和进项发票证据四分组表格；没有发票证据时发票列显示 `-`。
- OA/支付状态/支出流水/发票是表格主体的固定四段：OA 单元格内按“申请人 / 项目 / 申请事由 / 对方户名 / 金额”五栏展示，支出流水单元格内按“对方户名 / 金额 / 摘要”三栏展示；支付状态列保持窄列，只展示付款状态和“未写回/已写回”；发票列纵向展示发票号、发票方、日期 chip 和金额，不显示“价税合计”chip。表格优先避免横向滚动，必要时通过紧凑字号、紧凑 chip、换行和行高增长承载信息。
- 进行中 OA 的候选流水不能写回；页面级自动匹配只接受关联台 OA-bank 精确金额/精确合计规则确认的无冲突匹配。已有 completed Workbench active relation、in-progress active pending relation 或自动确认 pending relation 通过 workflow/outflow/金额/flow_id 校验后，自动写回 OA MySQL `t_payment_simple.pay_status=1`。
- 进行中 OA 自动匹配、`link-bank-transactions` 和规则保存成功后，页面必须先等待 `oa_pending_payment` operation barrier fresh，再重新读取 rows；barrier blocked/timeout 只能提示后台同步尚未完成，不能提前读旧投影或把已提交写入显示成操作失败。
- OA MySQL `t_payment_simple.flow_id` 使用 OA Mongo `form_data._id`。该结论来自 2026-06-17 服务器实机脱敏验证：现有 `t_payment_simple.flow_id` 为 24 位 ObjectId 形态，能匹配 Mongo `_id`，未匹配 Flowable `PROC_INST_ID_`；流程实例 ID 和流程请求 ID 只作为详情/诊断信息，不作为最终写回 ID。
- 生产 rows、filter-options 和 detail 必须走 `OaPendingPaymentReadModelService` 的 freshness/source-version gate；非 fresh 返回 refreshing/unavailable 并入队 `oa_pending_payment.read_model.refresh`，不能 live scan。
- `invoice-usage-collection` worker 同时负责 `input_invoice_usage`、`output_invoice_collection` 和 `oa_pending_payment` read model；OA all scope 只 fan-out month shards，不同步重建全量历史。
- `invoice-usage-collection` refresh handler 必须在 rebuild/fan-out 前校验 event source_version 是否仍为当前 dirty scope；旧事件只能返回 `skipped/stale_source_version`，不能覆盖较新的 read model。
- OA pending `all` scope 的 source version 判定优先从 `read_model.oa_pending_payment_rows` 的实际行聚合；只有完全没有实际行时才退回 scope 表，避免历史空月份 scope 把默认视图误判为 stale。
- 2026-06-17 生产已通过 release `main-e8de2711-20260617182353` 更新/重启服务器 `invoice-usage-collection` worker；后续不得只用本地手工 rebuild 代替标准 release/worker helper。
- 生产 OA MySQL 支付状态写回必须显式配置 `FIN_OPS_OA_PAYMENT_STATUS_*`。2026-06-17 已创建最小权限 MySQL 账号 `finops_oa_payment_status` 并写入 root-only 生产 env；该账号仅有 `smart_oa.t_payment_simple` 的 `SELECT`、`INSERT(flow_id, pay_status)`、`UPDATE(pay_status)` 权限。
- pending invoice rules 对 OA 待付款的刷新当前由执行层 workbench invalidation 间接入队 invoice usage collection，已有 `tests/test_pending_invoice_api.py` 回归保护；dry-run plan 的 domain 名称不直观，暂记为 documented-risk。

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

## 2026-06-20 - rows 加载失败刷新恢复 Browser E2E

- 目标：补齐 OA 待付款核对页的本地 `NETWORK-RECOVERY` 负面链路，防止 rows 首屏暂时失败时显示普通空态或用户无法从页面恢复。
- 影响范围：`OaPendingPaymentsPage` 显式刷新入口和错误/刷新状态、`OaPendingPaymentsTable` 错误态空行文案、Playwright deterministic mock、`web/e2e/oa-pending-payments-flow.spec.ts`、`OaPendingPaymentsPage.test.tsx` 和测试闭环文档。
- 关键决策：不改后端业务语义或真实 API contract；mock 表达 `/api/oa-pending-payments/rows` 暂时 503，页面必须显示错误提示和错误态空行，不显示普通空态，并允许用户点击显式刷新恢复 fresh rows/pagination。
- 文档影响：更新本文件、`e2e-coverage.md`、`tests.md`、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/oa-pending-payments-flow.spec.ts::recovers rows after a transient load failure when refreshed`；扩展 `web/src/test/OaPendingPaymentsPage.test.tsx` 验证刷新入口会重新请求 rows。
- 验证命令：`cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts --project=chromium`；本轮最终说明列出额外 Vitest/类型/docs 验证。
- 未测风险：本地 deterministic Browser 不证明真实 OA Mongo/MySQL、PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实网络中断、生产大数据和真实用户 confirm-paid/link-bank 写流恢复。
- 后续事项：继续补其它页面或 mutation 级网络恢复；真实 rows/detail non-fresh 恢复和 confirm-paid/link-bank worker drain 仍走 staging/runtime gate。

## 2026-06-19 - OA pending rows/detail non-fresh Browser E2E

- 目标：补齐 `OA-PENDING-E2E-008`，让真实 Chromium 覆盖 rows/detail read model 非 fresh 时的页面诊断，避免把 refreshing 空 rows 当成真实空态。
- 影响范围：`OaPendingPaymentsPage`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-nonfresh-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块状态机/coverage/tests 和全局 Spec-first E2E 文档。
- 关键决策：这是 Spec-first 产品行为修复。rows/filter-options 返回 `read_model_status=refreshing` 或 202 且 rows 为空时，页面显示中性“OA 待付款核对数据正在刷新”，不展示真实空态，也不向业务用户暴露 stale reason；detail 202 继续通过 drawer 展示“详情暂不可用”。
- 文档影响：更新 `state-machine.md`、`e2e-coverage.md`、`tests.md`、本实施记录，并同步全局 Spec-first inventory/closure state/testing 文档。
- 测试覆盖：新增 `web/e2e/oa-pending-payments-nonfresh-flow.spec.ts` 两条 Browser 测试；更新组件测试覆盖 rows refreshing 诊断和 detail unavailable。
- 验证命令：`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npx playwright test e2e/oa-pending-payments-nonfresh-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 不替代真实 OA Mongo/MySQL、真实 PostgreSQL/RabbitMQ/Redis/systemd `invoice-usage-collection` worker drain；真实 worker 停止/恢复、source-version stale 到 fresh 的恢复链路仍需要 staging/生产 smoke。
- 后续事项：补真实基础设施 confirm-paid/link-bank/rows-detail worker drain smoke，以及真实生产大数据、网络恢复和视觉遮挡 smoke。

## 2026-06-19 - 进行中 OA bank-link Browser E2E

- 目标：补齐 `OA-PENDING-E2E-007`，让真实 Chromium 覆盖进行中 OA 勾选后打开“关联支出流水”抽屉、筛选/禁选/提交和刷新闭环。
- 影响范围：`web/e2e/oa-pending-payments-bank-link-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 文档和测试矩阵。
- 关键决策：只加固 Browser E2E 和 deterministic mock，不改产品逻辑；link-bank 成功流只模拟 Workbench relation/read model 更新，断言页面仍 `未写回` 且 `confirm-paid` 零调用，避免把抽屉关联误当成 OA MySQL 支付状态写回。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录，并同步全局 Spec-first inventory/closure state/testing 文档。
- 测试覆盖：新增 `web/e2e/oa-pending-payments-bank-link-flow.spec.ts` 两条 Browser 测试，覆盖抽屉默认全部、已配对/已关联禁选、relation_status 筛选、提交 body、rows/read model refresh、失败错误可见、零半写和不调用 confirm-paid。
- 验证命令：`cd web && npx playwright test e2e/oa-pending-payments-bank-link-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 不替代真实 OA Mongo/MySQL、真实 PostgreSQL/RabbitMQ/Redis/systemd `invoice-usage-collection` worker drain；真实 Workbench active relation 和 OA pending read model fan-out 仍需要 staging/生产样本 smoke。
- 后续事项：补 `OA-PENDING-E2E-008` rows/detail non-fresh Browser 诊断，以及真实基础设施 confirm-paid/link-bank worker drain smoke。

## 2026-06-19 - 进行中 OA confirm-paid Browser E2E

- 目标：补齐 `OA-PENDING-E2E-006`，让真实 Chromium 覆盖进行中 OA 用户点击“确认已支付并写回”的成功刷新、重复提交防护和失败零半写。
- 影响范围：`web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 文档和测试矩阵。
- 关键决策：只加固 Browser E2E 和 deterministic mock，不改产品逻辑；mock 成功流模拟 confirm-paid 返回 `readModelRefresh` 后 rows/read model 重新请求并显示 `已写回`，失败流模拟后端 409 并断言页面保留 `未写回`、不触发 rows refresh。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录，并同步全局 Spec-first inventory/closure state/testing 文档。
- 测试覆盖：新增 `web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts` 两条 Browser 测试，覆盖成功写回、防重复提交、POST body、read model refresh、失败错误可见和零半写。
- 验证命令：`cd web && npx playwright test e2e/oa-pending-payments-confirm-paid-flow.spec.ts --project=chromium`。
- 未测风险：本地 mock 不替代真实 OA Mongo/MySQL、真实 PostgreSQL/RabbitMQ/Redis/systemd `invoice-usage-collection` worker drain；真实 confirm-paid 写回仍需要 staging/生产样本 smoke。
- 后续事项：补 `OA-PENDING-E2E-007` 进行中 OA 关联支出流水 Browser 流、`OA-PENDING-E2E-008` rows/detail non-fresh Browser 诊断，以及真实基础设施 confirm-paid worker drain smoke。

## 2026-06-19 - Spec-first OA pending linked fan-out Browser E2E

- 目标：补齐 Workbench confirm 后 OA 待付款页面必须通过 read model 重新读取并从候选/少付状态更新为 linked/已支付状态的 Browser 保护。
- 影响范围：`web/e2e/workbench-relations-oa-pending-fanout.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块 Spec-first E2E 文档和测试矩阵。
- 关键决策：新增 opt-in deterministic mock `oaPendingPaymentRelationFanout`，不影响既有 OA 页面 smoke；Browser flow 先进入 OA 待付款确认候选状态，再通过 Workbench confirm，回到 OA 待付款断言 rows 重新请求、状态变为 `已支付`、候选标记消失并显示 `关联台已确认`。
- 文档影响：新增 `e2e-spec.md`、`e2e-coverage.md`，更新 README、tests 和本实施记录，并同步全局 Spec-first inventory/closure state。
- 测试覆盖：新增 `web/e2e/workbench-relations-oa-pending-fanout.spec.ts`。
- 验证命令：`cd web && npx playwright test e2e/workbench-relations-oa-pending-fanout.spec.ts --project=chromium`。
- 未测风险：本地 mock 不替代真实 OA Mongo/MySQL、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain；进行中 OA 确认写回和关联支出流水仍缺完整 Browser 流。
- 后续事项：补进行中 OA confirm-paid Browser 流、link-bank-transactions Browser 流和 rows/detail non-fresh 浏览器诊断。

## 2026-06-18 - OA 待付款准入源改为 t_payment_simple.flow_id

- 目标：把 OA 待付款核对的 OA 范围从“扫 OA 系统所有进行中/已完成 OA”调整为“以 `t_payment_simple.flow_id` 为支付状态管理准入表”，避免网络波动导致的重复 OA 污染付款核对页面。
- 影响范围：`OaPendingPaymentQueryService` live query、OA payment status repository、Postgres OA pending read model rows summary、前端视图切换按钮、模块/产品/API/页面架构文档和相关测试。
- 关键决策：`flow_id` 必须匹配 OA Mongo `form_data._id`；查到 OA 后按当前 workflow status 进入 completed/in-progress。`t_payment_simple.id` 不是 OA ID；写回时更新同一 `flow_id` 的 `pay_status=1`。查不到 OA 的 `flow_id` 不进入正常表格，后续可作为异常计数/诊断扩展。
- 文档影响：更新本模块 README、state-machine、tests、implementation-notes，并同步 `docs/product-specs/invoice-lifecycle.md`、`docs/dev/api-contracts.md`、`docs/app-architecture/pages.md`。
- 测试覆盖：新增/更新 `tests/test_oa_payment_status_service.py`、`tests/test_oa_pending_payment_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py` 和 `web/src/test/OaPendingPaymentsPage.test.tsx`，覆盖 latest flow_id 列表、准入过滤、`summary.viewCounts` 和 tab 数量展示。
- 未测风险：本地自动化没有连接真实 OA Mongo/生产 MySQL 同步链路；生产中 `t_payment_simple.flow_id` 找不到 OA Mongo `_id` 的记录需要后续异常列表或运维报表承接。

## 2026-06-18 - 拆分 completed OA projection 与 OA 待付款准入 projection

- 目标：落实长期设计，避免 `app.oa_applications` 同时承担“普通已完成 OA 投影”和“OA 待付款支付准入 OA 投影”两个语义。
- 影响范围：`PaymentAdmittedOAProjectionAdapter`、Postgres OA projection repository、`OAProjectionSyncService`、`InvoiceUsageCollectionSqlProjectionBuilder`、`InvoiceLifecycleSqlProjectionBuilder`、API server/worker 装配、workbench SQL projection、workbench relation projection/repository、模块/产品/API 文档和相关测试。
- 关键决策：普通 `app.oa_applications` 只写入/读取 completed 或历史未知 workflow status，`oa.sync` 扫到 in-progress 时仍入队 `oa_pending_payment` refresh，但不再把 in-progress 写入普通 projection，并会清理旧 in-progress 残留。OA 待付款 read model 使用专用 `PaymentAdmittedOAProjectionAdapter`，先读取 `t_payment_simple.flow_id`，再生成 `oa-pay-/oa-exp-` row_id 候选向 OA Mongo 精确读取当前 OA。
- 文档影响：更新本模块 README、state-machine、tests、implementation-notes，并同步 `docs/product-specs/invoice-lifecycle.md`、`docs/dev/api-contracts.md` 和 `docs/app-architecture/pages.md`。
- 测试覆盖：新增/更新 `tests/test_oa_payment_status_service.py`、`tests/test_oa_projection_sync_service.py`、`tests/test_oa_projection_sql_runtime.py`、`tests/test_invoice_usage_collection_sql_runtime.py` 和 `tests/test_invoice_lifecycle_page_integration.py`，并跑 workbench relation、worker registry、migration、runtime boundary 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_payment_status_service tests.test_oa_projection_sync_service tests.test_oa_projection_sql_runtime tests.test_oa_pending_payment_service tests.test_oa_pending_payment_api tests.test_invoice_usage_collection_sql_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_registry tests.test_postgres_migrations tests.test_platform_runtime_boundary_guards tests.test_workbench_relation_repository tests.test_workbench_relation_sql_projection tests.test_invoice_lifecycle_page_integration -v`。
- 未测风险：本地未连接真实 OA Mongo/生产 MySQL 做 read model rebuild smoke；部署后仍需触发 `oa.sync:all` 和 `oa_pending_payment:all`，确认普通 projection 中 in-progress 被清理，OA 待付款进行中数量来自 `t_payment_simple.flow_id` 准入后的专用投影。

## 2026-06-18 - completed/in-progress 统一四分组表格 UI

- 目标：按最新 UI 要求，让“已完成 OA / 进行中 OA”使用同一个表格 UI：第一行大分组固定为 OA、支付状态、流水、发票；第二行保留各分组筛选/排序入口；发票列纵向展示发票号、发票方、日期 chip 和金额。
- 影响范围：`OaPendingPaymentsTable`、`OaPendingPaymentsPage` 调用、表格 CSS、`OaPendingPaymentsPage.test.tsx`、本模块 README/state-machine/tests/implementation-notes；后端 API、read model、付款判定和写回流程不变。
- 关键决策：`view_mode` 只控制数据范围，不控制表格列结构。进行中 OA 缺少发票证据时发票列显示 `-`；发票方改为普通文本，不使用 chip；移除“价税合计”chip。
- 文档影响：更新本实施记录、README、state-machine 和 `tests.md`；长期 API/架构文档不适用。
- 测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，覆盖统一发票列、发票筛选、进行中视图发票空值 `-`、发票方非 chip、移除价税合计 chip。

## 2026-06-18 - OA pending 四分组表格取消横向滚动

- 目标：保证用户不需要左右滑动即可看见 OA、支付状态、流水和发票四组信息。
- 影响范围：表格 CSS、`OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-flow.spec.ts` 和本模块文档；后端数据契约不变。
- 关键决策：取消固定 `1420px` 表格宽度，改为 100% 自适应；列宽按百分比分配，内部 grid 使用 `minmax(0, ...)` 允许文本换行，局部缩小表格字号、chip、详情按钮和确认按钮。
- 文档影响：更新本实施记录和 `tests.md`；长期 API/架构文档不适用。
- 测试覆盖：Vitest 覆盖紧凑 CSS contract，Playwright 在真实 Chromium 数据行渲染后断言 `scrollWidth <= clientWidth + 1`。

## 2026-06-18 - OA pending 主体三段表格内部布局调整

- 目标：按最新 UI 要求调整 OA 待付款核对的 completed/in-progress 表格主体，让 OA 区域内部固定展示申请人、项目、金额三栏；流水区域内部固定展示对方户名、金额、摘要三栏；支付状态列收窄并只展示“待支付/已支付”“确认已支付”和“未写回/已写回”。
- 影响范围：`OaPendingPaymentsTable`、表格 CSS、`OaPendingPaymentsPage.test.tsx` 和本模块测试/实施文档；后端 API、read model、付款判定和写回流程不变。
- 关键决策：保持 HTML 主表格仍以 OA、支付状态、流水为主体；completed 视图按既有状态机继续保留发票情况列，in-progress 视图继续隐藏发票列。写回状态不展示失败标签，外部依赖不可用仍只展示同步状态异常。
- 文档影响：更新本实施记录和 `tests.md`；长期 API/架构文档不适用。
- 测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，覆盖 OA/流水内部三栏结构、流程状态 chip 文案、支付状态列宽、写回状态文案和缺流水 `-` 展示。

## 2026-06-18 - 修复进行中 OA 投影后页面不刷新的链路

- 目标：修复生产“OA 待付款核对 / 进行中 OA”为空。排查确认 Mongo 中 2026 年后存在进行中支付申请/日常报销，Postgres OA projection 与 `read_model.oa_pending_payment_rows` 中没有 `in_progress` 行；直接原因是生产未用当前 projection 逻辑重跑，且 `oa.sync` 完成后没有把 `oa_pending_payment` read model 标脏。
- 影响范围：`OAProjectionSyncService`、生产 `oa.sync` / `oa_pending_payment.read_model.refresh` worker drain、本模块测试文档。
- 关键决策：OA projection sync 仍是统一事实源；页面不 live scan Mongo。`oa.sync` 完成后必须同时 fan-out `workbench`、`search`、`pending_invoice` 和 `oa_pending_payment`，让进行中 OA 通过 worker/read model 进入页面。
- 测试覆盖：新增 `tests/test_oa_projection_sync_service.py`，锁定 `in_progress` OA 同步后会入队 `oa_pending_payment` 月份和 `all` refresh。
- 生产修复动作：部署后触发一次 `oa.sync:all`，确认 `app.oa_applications.workflow_status='in_progress'` 和 `read_model.oa_pending_payment_rows.oa_workflow_status='in_progress'` 均有数据。

## 2026-06-18 - OA pending completed 视图恢复发票证据列

- 目标：修复 Playwright smoke 暴露的回归：`oa-pending-payments` rows payload 已返回 `invoice.digitalInvoiceNo`，但表格只渲染 OA/支付状态/流水三列，导致真实浏览器首屏看不到发票号，也无法打开发票详情。
- 影响范围：`OaPendingPaymentsTable`、`OaPendingPaymentsPage`、表格 CSS、`OaPendingPaymentsPage.test.tsx`、本模块测试/实施文档；后端 API contract 不变。
- 关键决策：按当时状态机保留 view-mode 区分。`completed` 视图显示发票情况列，支持单发票详情和多发票 relation 明细；`in_progress` 视图当时继续隐藏发票列。该展示口径已被 2026-06-18 “completed/in-progress 统一四分组表格 UI”替代。
- 文档影响：更新本实施记录和 `tests.md`；状态机既有“completed 视图保留 invoice detail 能力、in_progress 不展示发票列”的口径不变。
- 测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，覆盖 completed 发票列/发票筛选/开票日期排序/单发票详情/多发票 relation 明细，并保留当时的 in-progress 隐藏发票列断言；`web/e2e/oa-pending-payments-flow.spec.ts` 重新通过。该断言已在后续统一四分组 UI 中改为发票列空值 `-` 断言。
- 验证命令：`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts`；`cd web && npm run e2e:smoke`。
- 未测风险：未做真实大数据横向滚动截图；新增列宽由 deterministic browser smoke 和 Vitest 覆盖基本可读性，真实生产宽表仍需 staging/人工抽样。

## 2026-06-17 - OA 支付状态 MySQL 写回生产配置闭环

- 目标：解除 Phase 08 最后一项生产 blocker，使“进行中 OA 确认已支付”具备可用的 OA MySQL 写回路径。
- 影响范围：生产 MySQL `smart_oa.t_payment_simple` 最小权限账号、`/etc/fin-ops/fin-ops.secrets.env`、fin-ops API/worker/dispatcher 重启、`oa_pending_payment` read model refresh。
- 关键决策：不重置 MySQL root；通过一次 MySQL init-file 重启创建 `finops_oa_payment_status` 的 `127.0.0.1` 和 `localhost` host entry；临时 init-file/drop-in 创建后立即删除；验证写权限使用事务 rollback，不落业务 probe 行。
- 文档影响：更新本实施记录；`deploy/oa/README.md` 保留后续运维 runbook。
- 测试覆盖：生产侧验证 `MySQLOAPaymentStatusRepository.from_environment()` 可实例化并读取 sentinel flow_id；MySQL 最小权限账号对 `t_payment_simple` 的读、插入、更新通过 rollback smoke；`MySQLOAPaymentStatusRepository.mark_paid()` 真实 SQL 路径通过 rollback-on-commit smoke；重启后 `oa_pending_payment:all` durable refresh 由生产 worker 消费。
- 验证命令：root SSH 生产脚本创建账号并执行 PyMySQL rollback smoke；`sudo -n /usr/local/sbin/finops-deploy-control restart`；生产 env repository smoke；`/fin-ops-api/health/ready`；投递 `oa_pending_payment:all` refresh 并查询 `job.outbox_events`、`job.read_model_dirty_scopes`、`read_model.oa_pending_payment_*`。
- 运行时证据：`finops_oa_payment_status@127.0.0.1` 与 `finops_oa_payment_status@localhost` 均可读取 `smart_oa.t_payment_simple`，事务内 insert/update 后 rollback 剩余 probe 行数为 `0`；`SHOW GRANTS FOR CURRENT_USER()` 显示 `USAGE` 以及 `SELECT, INSERT(flow_id, pay_status), UPDATE(pay_status)` on `smart_oa.t_payment_simple`。生产 env 七个 `FIN_OPS_OA_PAYMENT_STATUS_*` key 均存在，repository configured/read_ok；`mark_paid()` rollback-on-commit smoke 返回 `pay_status=1` 且 probe 剩余行数为 `0`。
- Worker 证据：重启后 source_version `123` 的 `oa_pending_payment.read_model.refresh` event `a8a7eee2-04ff-4033-8f07-7276f0c1ccd2` 已 `done`，dirty scope `done`，月份 shard 更新在 `2026-06-17 18:44:56` 至 `18:44:58`，`invoice-usage-collection` heartbeat current。
- 数据结论：生产 repository 同源读取 `view_mode=in_progress` 为 fresh、total `0`；`view_mode=completed` 为 fresh、total `210`。当前仍没有可执行真实 confirm-paid 的进行中 OA 行，因此没有改动真实业务支付状态；写回能力通过生产权限和 rollback smoke 验证。
- 未测风险：真实用户点击 confirm-paid 需要未来出现一条真实进行中 OA + 支出流水候选/关系时再做业务级 smoke；当前生产事实数据没有 in-progress 行可用于不造数验证。
- 后续事项：当出现真实进行中 OA 样本时，执行一次确认已支付，核对 `t_payment_simple.flow_id=<OA Mongo form_data._id>` 最新记录 `pay_status=1`，并核对页面 `oaPaymentWriteback.label=已写回`。

## 2026-06-22 - 全部月份自动匹配接口 500 修复

- 目标：修复 OA 待付款核对页月份为空（全部月份）时，页面级 `auto-reconcile-bank-transactions` 报“接口处理失败，请联系管理员查看后端日志”的生产故障。
- 真实原因：生产日志显示后端调用 Workbench 候选匹配服务时传入 `scope_month=all`，而候选匹配服务只接受 `YYYY-MM`；异常为 `ValueError: scope_month must be YYYY-MM for workbench candidate matches.`。页面 rows 已经 fresh 并能展示数据，失败发生在 rows 加载后的自动匹配写命令。
- 影响范围：`OaPendingPaymentCommandService._auto_confirm_in_progress_bank_matches`、自动匹配候选生成、OA-bank relation confirm、OA MySQL 写回和 read model refresh enqueue。
- 关键决策：`month=all` 不再把 `all` 传给候选匹配服务；改为按进行中 OA 自身月份分组，并只用同月未配对支出流水生成候选，避免跨月匹配和 matcher contract 违规。
- 文档影响：更新本实施记录和测试矩阵历史 bug 回归库；业务口径不变。
- 测试覆盖：新增 `tests/test_oa_pending_payment_command_service.py::OaPendingPaymentCommandServiceTests::test_auto_reconcile_all_months_groups_matches_by_month`，覆盖全部月份下跨月 OA/流水按月分组、分别确认 relation、写回对应 flow id 并入队对应月份 read model refresh。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_command_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_api tests.test_oa_pending_payment_service -v`；`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/oa_pending_payment_command_service.py backend/src/fin_ops_platform/services/oa_pending_payment_service.py`。
- 未测风险：本地单测使用 fake repository，不替代真实浏览器携带登录态触发生产 HTTP；生产发布后仍需通过线上日志和页面刷新确认不再出现同一异常。

## 2026-06-17 - Phase 08 生产发布与 worker smoke

- 目标：按 GSD 主控闭环完成 Phase 08 发布后验证，确认进行中 OA 视图的生产 read model/worker/页面数据路径不是只在本地可用。
- 影响范围：生产 release、PostgreSQL durable queue、`invoice-usage-collection` worker、`oa_pending_payment` read model、公开前端入口和 OA MySQL 写回配置核验。
- 关键决策：生产 smoke 使用 `ReadModelRefreshGateway` 入队 `oa_pending_payment:all`，等待已部署 worker 消费；不通过手工 rebuild 伪造 fresh。支付状态 MySQL 只做只读连通性核验，不在没有样本 flow_id 时写入。
- 文档影响：更新本实施记录，明确生产 release 已闭合以及 OA MySQL 写回 env/凭据仍未闭合。
- 测试覆盖：沿用 Phase 08 后端 service/API/read model、migration/boundary、前端 Vitest 和 docs/build 验证；生产侧补 durable queue smoke 和 repository 同源读取。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_oa_pending_payment_api tests.test_oa_pending_payment_service tests.test_oa_payment_status_service tests.test_oa_pending_payment_command_service tests.test_oa_projection_sql_runtime tests.test_mongo_oa_adapter -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations tests.test_platform_runtime_boundary_guards -v`；`cd web && npm test -- OaPendingPaymentsPage.test.tsx --run`；`bash scripts/verify.sh docs`；`cd web && npm run build`；`./scripts/deploy-oa.sh --dry-run`；`./scripts/deploy-oa.sh`；生产入队 `oa_pending_payment:all` refresh 并查询 `job.outbox_events`、`job.read_model_dirty_scopes`、`read_model.oa_pending_payment_*`。
- 运行时证据：生产 release metadata 为 `main-e8de2711-20260617182353` / commit `e8de27118e15403ff0b256a6c40ab82b13a69932`；`/fin-ops-api/health/ready.status=ready`，runtime release consistent；deploy-control 显示 API、dispatcher 和 `fin-ops-worker@invoice-usage-collection.service` active。post-deploy event `cade4a8b-d7e3-40f8-a704-9b591803dbf0` source_version `122` 已 `done`，all scope fan-out 到 `2026-06` 至 `2025-12` month shards，最近生产 rows 更新在 `2026-06-17 18:27:19` 至 `18:27:21`。
- 数据结论：生产 repository 同源读取 `view_mode=in_progress` 为 fresh、total `0`；`view_mode=completed` 为 fresh、total `211`。当前进行中视图空表是 OA 投影事实数据，不是页面未加载。
- 未测风险：当时未能完成生产 OA MySQL 写回配置验证；文件层已确认目标表在 MySQL datadir 的 `smart_oa/t_payment_simple.ibd`，但缺少可用 MySQL 管理凭据。该 blocker 已由后续“OA 支付状态 MySQL 写回生产配置闭环”记录解除。
- 后续事项：已由后续记录补齐最小权限账号、生产 env、只读 repository smoke 和 rollback 写权限 smoke；真实业务级 confirm-paid smoke 仍需等待生产出现进行中 OA 样本。

## 2026-06-17 - OA pending read model runtime freshness 闭环

- 目标：修复 Phase 08 runtime smoke 中发现的默认 `all` 视图持续 `refreshing`、手工 v3 rebuild 后又被旧刷新路径写回 v1/空 workflow status 的问题。
- 影响范围：`InvoiceUsageCollectionReadModelRefreshService`、`PostgresReadModelRepository.list_oa_pending_payment_rows`、`Application.rebuild_oa_pending_payment_read_model_scope` 兼容路径、SQL runtime 测试、生产发布/worker 运维。
- 关键决策：刷新事件处理前复用 durable queue 的 `read_model_refresh_is_current` guard；stale event 不 rebuild、不 complete dirty scope；OA pending `all` freshness 优先从实际 rows 的 `source_versions` 聚合，历史空 scope 不参与有行视图的新鲜度证明。
- 文档影响：更新本模块 implementation-notes、tests、state-machine；生产发布仍按 `scripts/deploy-oa.sh`，不能手工绕过 release/worker helper。
- 测试覆盖：新增/更新 `tests/test_invoice_usage_collection_sql_runtime.py::test_oa_refresh_handler_skips_stale_source_version_before_rebuild`、`test_oa_repository_all_scope_aggregates_monthly_scope_source_versions`，以及 `tests/test_oa_pending_payment_api.py::test_legacy_application_rebuild_includes_completed_and_in_progress_rows`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_oa_pending_payment_api tests.test_oa_pending_payment_service tests.test_oa_payment_status_service tests.test_oa_pending_payment_command_service tests.test_oa_projection_sql_runtime tests.test_mongo_oa_adapter -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations tests.test_platform_runtime_boundary_guards -v`；`cd web && npm test -- OaPendingPaymentsPage.test.tsx --run`；`cd web && npm run build`；本地 Playwright 打开 `/oa-pending-payments` 并切换“进行中 OA”。
- 运行时证据：当前源码 rebuild 后 7 个活跃月份 scope 均写入 `oa-pending-payment:v3` / `2026-06-17-workflow-status-v1`；HTTP smoke 显示 `view_mode=in_progress` fresh 且 total=0、`view_mode=completed` fresh 且 total=210。当前 OA projection 没有 `in_progress` 行，因此页面空表是事实数据，不是未加载。
- 未测风险：生产服务器 heartbeat 显示 `invoice-usage-collection` worker 仍在运行旧部署；未完成 release activate 前，服务器 worker 可能继续用旧逻辑覆盖 read model。由于当前工作树包含未提交 Phase 08 改动，`scripts/deploy-oa.sh` 标准发布会拒绝 dirty worktree，必须先提交/发布/重启 worker 后再做生产 smoke。
- 后续事项：完成干净 release 发布后，重跑 `oa_pending_payment:all` refresh，确认 worker heartbeat 更新时间、scope source versions、HTTP rows/filter-options 和页面空态/数据态一致。

## 2026-06-17 - 进行中 OA 支付确认与 OA 写回

- 目标：在 OA 待付款核对页新增 `已完成 OA / 进行中 OA` 切换，把进行中支付申请/日常报销拉入三列视图，并支持候选流水确认后写回 OA 支付状态。
- 影响范围：OA Mongo adapter/projection、OA pending payment query/read model/service/API、OA MySQL payment status adapter、Workbench relation confirm command、`OaPendingPaymentsPage`/table/API types/styles、模块/产品/API 文档和相关测试。
- 关键决策：继续复用 Workbench relation 作为关联事实源；candidate relation 只展示证据和确认按钮，不直接判定 `paid` 或写回；confirm-paid 后端负责金额相等、outflow、workflow_status、flow_id 和 relation command 校验，页面只提交用户确认。
- 文档影响：更新本模块 README、state-machine、tests、implementation-notes，并同步 `docs/product-specs/invoice-lifecycle.md`、`docs/dev/api-contracts.md` 和 `docs/app-architecture/pages.md`。
- 测试覆盖：新增/更新 `tests/test_oa_payment_status_service.py`、`tests/test_mongo_oa_adapter.py`、`tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_api.py` 和 `web/src/test/OaPendingPaymentsPage.test.tsx`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_payment_status_service tests.test_mongo_oa_adapter.MongoOAAdapterTests.test_list_application_records_maps_payment_requests_and_reimbursement_details tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_external_oa_mysql_client_is_confined_to_role_sync_adapter tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_raw_postgres_sql_in_services_is_classified_by_platform_boundary -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_oa_pending_payment_command_service tests.test_oa_pending_payment_api -v`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npm run build`。
- 未测风险：未连接真实 OA MySQL/Mongo，不覆盖真实网络超时、账号权限、生产锁等待、真实 OA 字段变体和 worker drain；需要 staging 用真实进行中 OA、候选流水和 `t_payment_simple` 样本 smoke。
- 后续事项：部署前配置 `FIN_OPS_OA_PAYMENT_STATUS_*` 环境变量并在 staging 验证 `flow_id` 解析命中率、confirm-paid 审计链和 2 秒目标 refresh。

## 2026-06-17 - OA待付款Browser e2e闭环

- 目标：补齐 OA 待付款核对页面真实浏览器层的首屏、筛选/排序和详情抽屉保护，降低只靠 Vitest 时漏掉实际导航、drawer、请求参数编码或规则抽屉复用 endpoint 回归的风险。
- 影响范围：Playwright deterministic API mocks、`web/e2e/oa-pending-payments-flow.spec.ts`、smoke 脚本和 OA 待付款测试文档；后端业务代码和 API 契约不变。
- 关键决策：本轮选择只读高价值链路，覆盖 rows/filter-options、搜索、支付状态筛选、交易时间排序、OA/流水/发票详情和支出流水无需开票规则抽屉；真实 OA/Mongo、真实 Postgres 和 worker drain 仍留给 staging/生产 smoke。
- 文档影响：更新本模块 `tests.md`、`state-machine.md`，并同步 `docs/dev/testing.md`、`docs/dev/nightly-ci.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：新增 `web/e2e/oa-pending-payments-flow.spec.ts`，并加入 `npm run e2e:smoke`。
- 验证命令：`cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx src/test/TableAlignmentStyles.test.ts`；`cd web && npm run e2e:smoke`；`bash scripts/verify.sh docs`。
- 未测风险：真实 OA/Mongo 字段变体、真实生产 PostgreSQL 大数据 EXPLAIN/锁等待/长分页、真实 RabbitMQ/Redis/systemd worker drain、虚拟滚动压力、像素级视觉和网络中断恢复仍需 staging/生产 smoke。
- 后续事项：继续按 fan-out 风险补 `no-oa-bank-batches` 等页面的 Browser e2e。

## 2026-06-16 - 首屏 page-size 性能护栏证据

- 目标：补齐 P2/P3 大数据列表本地 synthetic SLO 与前端首屏请求证据，防止 OA 待付款核对首屏请求把超大 page size 透传为全量读取。
- 影响范围：`OaPendingPaymentQueryService.list_rows` 的分页 contract、`OaPendingPaymentsPage` 首屏 rows 请求回归和模块测试矩阵；业务行为不变。
- 关键决策：保留现有严格上限语义，`page_size=200` 为最大允许页大小，`page_size>200` 返回 `invalid_paging`，不做静默 clamp；前端默认继续使用更保守的 `page_size=20`，页大小选项限制为 20/50/100。
- 文档影响：更新 `tests.md` 与 P2/P3 closure ledger。
- 测试覆盖：新增 `OaPendingPaymentQueryServiceTests.test_page_size_limit_protects_first_screen_slo`，用 250 行 synthetic 数据验证 200 行上限、total 保留和超限错误；更新 `web/src/test/OaPendingPaymentsPage.test.tsx` 锁定首屏 `page=1&page_size=20` 和 20/50/100 页大小选项。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service.OaPendingPaymentQueryServiceTests.test_page_size_limit_protects_first_screen_slo -v`；`npm --prefix web test -- --run src/test/InputInvoiceUsagePage.test.tsx src/test/OutputInvoiceCollectionsPage.test.tsx src/test/OaPendingPaymentsPage.test.tsx`。
- 未测风险：真实 PostgreSQL EXPLAIN、锁等待、浏览器滚动和网络中断恢复仍需 staging/production smoke。
- 后续事项：如 API 层改变 page size 映射，必须同步保留 `invalid_paging` 或等价 fail-closed contract。

## 2026-06-11 - OA待付款关联台分组关系闭环

- 目标：修复多条 OA/支出流水/进项发票在关联台已清晰配对时，OA 待付款页拆成多行并误显示“支付多了”或“多条OA合并支付”的问题。
- 影响范围：`InvoiceLifecyclePolicy`、`OaPendingPaymentQueryService`、OA pending payment read model detail builder、SQL projection 复用路径、`/api/oa-pending-payments/rows/{row_id}/relation-details`、`OaPendingPaymentsTable`、前端 OA pending payments 类型、模块/API 文档和相关测试。
- 关键决策：关联关系完全来自 Workbench active relation；同一 relation 下的 OA、有效 outflow 支出流水和进项发票分别汇总为一条核对行，列表只显示合计金额和 `+N`，点击 `+N` 分别以 `kind=oa|bank|invoice` 查看明细。
- 文档影响：更新模块状态机、测试矩阵、实施记录、产品口径和 API 合同。
- 测试覆盖：新增/更新 lifecycle policy、query service、API/read model detail、SQL projection runtime 和前端交互回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_invoice_lifecycle_policy tests.test_oa_pending_payment_api tests.test_invoice_usage_collection_sql_runtime -v`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npm run build`。
- 未测风险：未连接真实 OA/Mongo、生产 Postgres 大数据、真实 RabbitMQ/Redis/systemd worker drain 和真实浏览器截图 smoke。
- 后续事项：如需发布前进一步验证，使用截图中的真实月份在 staging 触发 relation 确认/撤回、`oa_pending_payment` scope refresh 和页面浏览器 smoke。

## 2026-06-11 - OA待付款测试闭环矩阵与状态机补齐

- 目标：执行 testing closure master goal 的 `oa-pending-payments` 模块轮次，确认 OA 单据、支出流水、进项发票、Workbench relation、SQL read model、worker 和前端交互的回归保护。
- 影响范围：`docs/modules/oa-pending-payments/README.md`、`docs/modules/oa-pending-payments/tests.md`、`docs/modules/oa-pending-payments/state-machine.md`、`docs/modules/oa-pending-payments/implementation-notes.md`；未改变业务代码。
- 关键决策：现有 P0/P1 自动化测试已覆盖付款状态、缺失证据、API shape、权限、read model freshness、detail stale/missing、SQL projection/repository、worker fan-out、App Status registry 和前端交互；本轮不新增重复测试。
- 文档影响：补齐模块必读事实源、代码入口、七类测试矩阵、影响面清单、关键 smoke flows、历史 bug 回归库、状态机和 remaining risk。
- 测试覆盖：沿用 `tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/TableAlignmentStyles.test.ts`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_oa_pending_payment_api tests.test_invoice_lifecycle_page_integration -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_runtime_worker_registry -v`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx src/test/TableAlignmentStyles.test.ts`。
- 未测风险：未连接真实 OA/Mongo，不验证真实 OA sync 字段变体和权限菜单；未在真实生产 Postgres 跑大数据 EXPLAIN/锁等待/长分页；未跑真实 RabbitMQ/Redis/systemd `invoice-usage-collection` 与 `invoice-lifecycle` worker drain；未做真实浏览器大数据表格和网络中断 smoke。
- 后续事项：下一轮处理 `turnover-ledger`，重点审计手动闭环、extra、relation stale precondition、read model freshness 和前端筛选/抽屉交互。

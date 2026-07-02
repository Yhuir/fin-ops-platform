# 批量账务 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 需要保护的行为 | 当前测试入口 |
| --- | --- | --- |
| 页面交互 | 加载、空态、错误、筛选、bucket 切换、银行/OA 选择、差额说明、提交、撤回、feedback、侧栏入口 | `web/src/test/BatchAccountingPage.test.tsx`、`web/e2e/batch-accounting-flow.spec.ts` |
| Operation overlay / 写后 scope | 提交/撤回 command 失败必须显示失败；command 成功后短等 `workbench_relation` barrier 并 reload，barrier blocked/timeout 或 reload 中断只能提示后台同步，不能把已成功的 command 改写成操作失败；写后 lifecycle 必须只使用 service 输出的具体 `affected_scope_keys` 且 `include_all=False`；成功后不能残留操作失败/同步失败/read model 失败等可见错误提示 | `web/src/test/BatchAccountingPage.test.tsx`、`web/src/test/OperationBarrierApi.test.ts`、`web/src/test/GlobalOperationOverlayContext.test.tsx`、`web/e2e/batch-accounting-flow.spec.ts`、`tests/test_batch_accounting_api.py` |
| API contract | `GET /api/batch-accounting`、`POST /api/batch-accounting/submit`、`POST /api/batch-accounting/{relation_id}/withdraw` 的状态码、错误码、DTO shape、freshness 字段 | `tests/test_batch_accounting_api.py` |
| 业务核心 | 日常报销 OA 过滤、批量账务银行流水过滤、金额差异说明、version conflict、active relation 排除、跨年选择、撤回原因 | `tests/test_batch_accounting_api.py` |
| Service / repository | `BatchAccountingService` 调用 Workbench payload、relation command service、relation facade、legacy collision repair；未提交读路径使用候选级 relation lookup 和年份级 submitted count；submit/withdraw 不再调用旧 pair persist，affected scopes 由 row 日期/metadata 计算 | `tests/test_batch_accounting_api.py`、`tests/test_workbench_relation_read_facade.py`、`tests/test_workbench_v2_api.py` |
| Relation read model | `workbench_relation` fresh/missing/stale、row id 去重、linked/unlinked projection、refresh enqueue、source version | `tests/test_workbench_relation_read_facade.py`、`tests/test_workbench_relation_sql_projection.py`、`tests/test_batch_accounting_api.py` |
| Worker / App Status | `workbench-relation` worker registry、`workbench_relation.read_model.refresh` job、App Status domain/job 映射 | `tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` |
| Cross-page fan-out | 批量账务关系变化影响关联台、银行明细、成本统计、搜索、发票 lifecycle 相关页面；前端事件只做刷新提示 | `tests/test_derived_data_lifecycle_service.py`、`web/src/test/domainEvents.test.ts`、`web/src/test/useActiveFinanceDomainEvent.test.tsx`、`web/e2e/batch-accounting-flow.spec.ts` |
| 关联台投影 | active `relation_mode=batch_accounting` 关系必须进入关联台 paired 区，不能被 open `existing_case_candidate` 旧候选链路接管；覆盖多 OA、多 OA 附件发票和金额不一致说明形态 | `tests/test_workbench_sql_runtime.py` |

## 关键场景覆盖

| 场景 | 当前状态 | 保护入口 |
| --- | --- | --- |
| 首屏 `GET /api/batch-accounting` 暂时失败时显示错误态、不显示普通空态，点击刷新后恢复银行/OA rows 且清除失败文案 | covered | `BatchAccountingPage.test.tsx::recovers after a transient batch accounting load failure when refreshed`、`web/e2e/batch-accounting-flow.spec.ts::recovers list after a transient load failure when refreshed` |
| unsubmitted 列表优先走 SQL read model loader；银行按流水年份筛选，OA 按“日常报销且没有关联银行流水”筛选，旧 `oa_year` 参数不能过滤候选 | covered | `test_unsubmitted_list_uses_sql_read_model_loader_when_available`、`test_unsubmitted_list_ignores_legacy_oa_year_filter`、`test_unsubmitted_list_filters_oa_rows_by_linked_bank_transactions_only` |
| submit 优先走 SQL read model narrow loader，通过 submit context 边界只读取本次选中银行/OA/附件发票 rows；写前 active relation 检查只按本次选中的银行/OA/发票 row ids 走 canonical command service，不再请求 relation read model fresh，不扫描整页候选 payload 或整页候选 relation distribution | covered | `test_submit_uses_sql_read_model_loader_when_available`、`test_submit_checks_active_relations_only_for_selected_rows_without_relation_read_model_gate`、`test_batch_accounting_route_handlers_do_not_bypass_service_boundaries` |
| submit/withdraw 写后 side effect 不再调用旧 pair persist/snapshot restore；lifecycle 只按具体月份 scope 执行，跨月关系不默认落到 all；旧关系撤回缺 metadata 时可用窄上下文推导月份 | covered | `test_submit_does_not_call_legacy_pair_relation_persist_and_scopes_lifecycle_to_months`、`test_submit_records_concrete_affected_scope_keys_for_cross_month_relation`、`test_withdraw_legacy_relation_derives_scope_keys_from_narrow_context` |
| unsubmitted 列表显式分页首屏保护；首屏 relation I/O 只查候选行且 `submitted_count` 使用轻量 count，不扫描 12 个月 submitted 明细 | covered | `test_unsubmitted_list_explicit_pagination_protects_first_screen_slo`、`test_unsubmitted_relation_lookup_is_scoped_to_batch_candidates`、`test_unsubmitted_list_uses_relation_count_instead_of_month_relation_scan`、`test_batch_accounting_count_uses_repository_count_without_loading_rows`、`BatchAccountingPage.test.tsx::uses backend pagination for bank and OA first screens` |
| GET 列表只读，不触发 legacy repair | covered | `test_unsubmitted_list_does_not_run_legacy_relation_repair` |
| 未提交列表排除已经被其他关系占用的银行行 | covered | `test_unsubmitted_list_excludes_bank_rows_already_linked_elsewhere` |
| relation read model missing/stale 透传到 API 和页面，列表通过 freshness 边界入队刷新，页面不能把非 fresh 空关系当真实空；写操作阻断由 canonical write safety 决定 | covered | `test_unsubmitted_list_exposes_relation_read_model_missing_status`、`test_submitted_list_exposes_relation_read_model_stale_status`、`test_unsubmitted_list_requires_fresh_relation_read_model_to_enqueue_missing_refresh`、`test_submitted_list_requires_fresh_relation_read_model_to_enqueue_stale_refresh`、canonical command service / version conflict / rollback tests |
| 金额不一致必须填写 trim 后非空差额说明，金额一致忽略说明 | covered | `test_submit_amount_mismatch_requires_difference_note`、`test_submit_amount_mismatch_rejects_whitespace_note`、`test_submit_matched_amount_ignores_supplied_difference_note` |
| 提交通过 relation command service 写入 batch relation、当前 invoice rows、历史备注和 `affected_scope_keys`；缺 command service 时 fail fast，不 direct pair fallback；OA 仅有发票关系时可补关联流水 | covered | `test_submit_creates_batch_accounting_relation_with_current_invoice_rows`、`test_submit_allows_invoice_only_oa_relation_without_linked_bank_flow`、`test_submit_amount_mismatch_with_note_persists_relation_and_history`、`test_submit_delegates_relation_write_to_command_service`、`test_submit_requires_relation_command_service_without_direct_pair_fallback`、`test_submit_records_concrete_affected_scope_keys_for_cross_month_relation` |
| 批量账务 active relation 在关联台投影为 paired group | covered | `tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_sql_projection_keeps_active_batch_accounting_oa_bank_relation_paired`、`test_sql_projection_keeps_active_batch_accounting_multi_oa_invoice_relation_paired` |
| 旧 case_id collision repair 通过 relation command service 恢复合法 batch relation，缺 command service 时 fail fast，不覆盖当前非 batch relation | covered | `test_repair_legacy_case_id_collision_*`、`test_batch_accounting_repair_has_no_direct_pair_write_fallback` |
| submitted 列表来自 active batch relation，并按年份级 relation distribution 归桶；不能按 12 个月循环读取，也不能用整页候选 payload 补齐 OA/发票明细 | covered | `test_submitted_list_is_derived_from_active_batch_accounting_relations`、`test_submitted_list_relation_bucket_uses_workbench_relation_distribution` |
| 撤回恢复旧 OA invoice snapshot、保留历史说明、要求撤回原因且只能撤回 batch relation；缺 command service 时 fail fast，不 direct pair fallback | covered | `test_withdraw_restores_previous_oa_invoice_snapshot`、`test_withdraw_mismatch_batch_preserves_submit_and_withdraw_notes`、`test_withdraw_requires_reason_and_batch_accounting_relation`、`test_withdraw_delegates_relation_write_to_command_service`、`test_withdraw_requires_relation_command_service_without_direct_pair_fallback`、`test_batch_accounting_withdraw_has_no_direct_pair_write_fallback` |
| 前端提交/撤回后广播 `workbenchRelationUpdated`，选中行和差额说明在刷新/bucket/选择变化时正确清理 | covered | `BatchAccountingPage.test.tsx` |
| 前端提交/撤回后显示全屏 operation overlay；command 成功后 barrier blocked/timeout 或 reload 中断不再显示操作失败，而是返回成功并提示后台同步 | covered | `BatchAccountingPage.test.tsx::keeps a successful submit successful when the relation barrier is still blocked`、operation overlay/API tests |
| 窄桌面窗口下左侧批量账务流水 rail 保持可读，标题、说明、年份输入和分页控件不互相挤压或溢出 | covered | `BatchAccountingPage.test.tsx` CSS 契约、`web/e2e/batch-accounting-flow.spec.ts` |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_batch_accounting_api.py` | 覆盖金额差异说明、合法银行/OA 行、OA 仅按关联银行流水排除、version conflict、撤回原因、legacy collision repair。后续如改匹配/金额/状态规则，必须继续补。 |
| 2. Service-layer tests | 适用 | `tests/test_batch_accounting_api.py`、`tests/test_workbench_relation_read_facade.py`、`tests/test_workbench_v2_api.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 `BatchAccountingService` 与 relation command service、relation facade、旧 pair persist 删除、历史关系 command 恢复、unsubmitted 候选级 relation lookup、年份级 submitted count、年份级 submitted relation DTO、submit 窄 payload loader、affected scope metadata，以及 submit/withdraw 的 canonical write safety。 |
| 3. API contract tests | 适用 | `tests/test_batch_accounting_api.py` | 覆盖 GET/submit/withdraw 的成功 shape、显式分页 `pagination` / `invalid_paging`、错误码、freshness 字段、summary/relations/mutation result；read model non-fresh 由 GET/facade 透出诊断，mutation 默认不因普通 distribution 追赶中被拒。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_workbench_relation_read_facade.py`、`tests/test_workbench_relation_sql_projection.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` | 覆盖 `workbench_relation` facade、projection、non-fresh enqueue、worker registry 和 App Status 绑定；批量账务列表读取必须通过 facade `require_fresh` 触发入队。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/BatchAccountingPage.test.tsx`、`web/src/test/GlobalOperationOverlayContext.test.tsx`、`web/src/test/OperationBarrierApi.test.ts`、`web/e2e/batch-accounting-flow.spec.ts` | 覆盖 loading/empty/error、首屏 GET 暂时失败后的错误态/刷新恢复、防 false-empty、freshness 诊断、刷新未入队提示、筛选、搜索、选择、提交、撤回、operation overlay、CSS/组件契约、窄桌面左侧 rail 可读性和侧栏入口；Browser e2e 覆盖真实 Chromium 中首屏 503 后手动刷新恢复、窄桌面左侧 header 不挤压、`read_model_status=stale` 诊断下保留当前可用 rows、不显示普通空态且零 mutation、未提交 bucket 选择银行/OA、金额归零、提交反馈、已提交 bucket 展示、撤回弹窗、撤回后回到未提交状态，并在恢复/成功反馈后检查没有操作失败/同步失败/read model 失败等可见错误残留。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_batch_accounting_api.py`、`tests/test_workbench_v2_api.py`、`tests/test_workbench_sql_runtime.py`、`web/src/test/domainEvents.test.ts`、`web/e2e/batch-accounting-flow.spec.ts` | 覆盖 submit -> Workbench relation -> submitted list / Workbench projection、active `relation_mode=batch_accounting` -> workbench paired group、withdraw -> snapshot restore、前端刷新事件；Browser e2e 额外证明 submit/withdraw 后都等待 `workbench_relation` operation barrier，再重新读取并恢复对应 bucket，且严格捕获 console/page/request/dialog 隐藏错误和成功后的可见错误残留。生产 smoke 需要覆盖 1273.06 撤回->重提->关联台 paired 可见和耗时。真实 worker drain 仍是 external-risk。 |
| 7. Existing feature regression tests | 适用 | `tests/test_batch_accounting_api.py`、`tests/test_workbench_v2_api.py`、`web/src/test/BatchAccountingPage.test.tsx`、`web/e2e/batch-accounting-flow.spec.ts` | 覆盖旧 case_id collision、非 batch relation 不被覆盖、GET 不执行 legacy repair、旧页面不把 non-fresh relation 当真实空；Browser e2e 防止提交/撤回后的 summary、bucket、OA 表格状态和“成功但报错提示仍显示”的回归。 |

## 历史 Bug 回归库

| 来源 | 回归点 | 当前状态 |
| --- | --- | --- |
| Legacy case id collision | 历史批量账务关系被同 case_id 覆盖后，可通过 relation command service 从历史合法 relation 恢复；已撤回或当前非 batch relation 不恢复 | covered |
| Relation read model non-fresh | missing/stale 不能被解释成“无关联，可提交”；列表读取必须入队刷新，submit/withdraw 默认由 canonical write safety、owner 状态、权限/session、DB 可写性决定 | covered |
| Submit command boundary | submit 缺少 relation command service 时不能 direct 写 pair service，必须返回结构化错误 | covered |
| Withdraw command boundary | withdraw 缺少 relation command service 时不能 direct 写 pair service，必须返回结构化错误 | covered |
| Route boundary contamination | GET route 只能通过 `BatchAccountingApiRoutes.list_payload(...)` / `BatchAccountingService.build_payload(...)` 读，不得 repair/write/schedule；submit/withdraw `server.py` wrapper 必须经 mutation session 并委托 `BatchAccountingApiRoutes`，route owner 必须委托 `BatchAccountingService` 且不得直接调用 relation write internals；app-level `_repair_batch_accounting_relation_case_ids` 不得回归 | covered |
| Mismatch note | 金额不一致必须填写非空说明；切换银行、bucket、OA 选择时清空旧说明 | covered |
| Legacy pair persist deletion | batch-accounting route 不得在 command service 保存后再次调用旧 pair relation persist 或 snapshot restore；command 后 lifecycle 必须按具体月份 scope 执行 | covered |
| Withdraw history | 撤回差额批量账务时保留提交和撤回备注；不把 OA 附件 case_id / `existing_case` 显示归属恢复成 active relation | covered |
| Operation-to-fresh closure | submit/withdraw 后不靠前端事件假装完成；优先短等 `workbench_relation` barrier fresh 并重新加载页面，但 post-command barrier/reload 失败不能覆盖 command 成功 | covered |
| Load failure false-empty | 首屏列表 GET 暂时失败不能显示“当前年份暂无批量账务流水”，用户点击刷新后必须恢复业务行并清除失败文案 | covered |
| First-screen page-size guard | 显式请求分页时 `page_size=200` 是上限，`bank_rows` / `oa_rows` 有界返回，summary total 保留，`page_size>200` 返回结构化 `invalid_paging`；前端未提交 bucket 首屏发送 `bank_page_size=200` / `oa_page_size=200` 并独立翻页 | covered |
| Daily reimbursement OA bank-link filter | 日常报销 OA 的右侧候选只因已关联银行流水而排除；仅发票关系或无流水候选关系不能排除，也不能在提交时被 active invoice-only relation 拒绝 | covered |

## 关键 Smoke Flows

1. 首屏 `GET /api/batch-accounting` 暂时 503 -> 页面显示错误态且不显示普通空态 -> 用户点击刷新 -> 银行/OA rows 恢复、失败文案消失、没有隐藏浏览器错误。
2. 批量账务列表 fresh -> 选择银行流水 -> 选择 OA 行 -> 金额一致提交 -> `workbenchRelationUpdated` -> submitted bucket 展示关系；`web/e2e/batch-accounting-flow.spec.ts` 在真实 Chromium 中覆盖该 happy path，并断言 `workbench_relation` operation barrier 被调用且成功后没有可见错误残留。
3. 金额不一致 -> 空说明被拒 -> 填写说明提交 -> 关联台/银行明细/成本统计下游通过 relation read model 看到关系标签。
4. submitted bucket -> 填写撤回原因 -> 撤回 -> relation read model refresh -> 原银行/OA 行回到可处理状态；`web/e2e/batch-accounting-flow.spec.ts` 覆盖真实 Chromium 撤回弹窗、原因输入、确认撤回、barrier、回到未提交 bucket 和成功后无可见错误残留。
5. `workbench_relation` missing/stale -> API 透出 freshness 并经 facade/gateway 入队刷新 -> 页面显示 warning/reason/scope，不把当前可用 rows 当作真实空态，也不因普通 read model non-fresh 全局禁用具备 canonical write safety 的操作 -> worker 刷新后恢复；`web/e2e/batch-accounting-flow.spec.ts` 已覆盖 stale 诊断下可见 rows 和零 mutation。
6. 显式 `page/page_size` -> `bank_rows` / `oa_rows` 有界返回、summary 仍保留完整命中数量，超限页大小 fail closed。
7. submit/withdraw -> 全屏 overlay -> 写 API 成功 -> 短等 `workbench_relation` operation barrier 并重新加载当前 bucket；若 barrier/reload 未及时完成，页面显示“后台同步”成功提示，用户刷新后读取后端事实。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_batch_accounting_api \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_route_handlers_do_not_bypass_service_boundaries \
  tests.test_workbench_relation_read_facade \
  tests.test_workbench_relation_sql_projection \
  tests.test_runtime_worker_registry \
  tests.test_app_status_overview_service \
  tests.test_derived_data_lifecycle_service \
  -v

cd web && npm test -- --run \
  src/test/BatchAccountingPage.test.tsx \
  src/test/GlobalOperationOverlayContext.test.tsx \
  src/test/OperationBarrierApi.test.ts \
  src/test/domainEvents.test.ts \
  src/test/useActiveFinanceDomainEvent.test.tsx

cd web && npx playwright test e2e/batch-accounting-flow.spec.ts

bash scripts/verify.sh docs
```

P2/P3 首屏分页目标验证：

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_batch_accounting_api.BatchAccountingApiTests.test_unsubmitted_list_explicit_pagination_protects_first_screen_slo \
  -v

npm --prefix web test -- --run src/test/BatchAccountingPage.test.tsx
```

## Nightly CI 覆盖

Nightly CI 通过 `scripts/verify.sh all` 执行后端、前端、Playwright browser smoke 和文档校验。当前 Playwright smoke 已包含 `web/e2e/batch-accounting-flow.spec.ts`，覆盖提交批量账务关系、等待 `workbench_relation` freshness barrier、重新加载并在已提交 bucket 展示关联 OA，以及撤回后等待 barrier 并回到未提交 bucket；该 spec 还覆盖首屏 GET 暂时 503 后手动刷新恢复、窄桌面银行 rail 可读性、stale relation read model 诊断下保留当前 rows/防普通空态/零 mutation，捕获浏览器隐藏错误，并在恢复/成功写操作后检查页面没有可见错误残留。批量账务的窄范围回归命令应在本地模块变更时优先运行；跨模块改动再升级为 `scripts/verify.sh backend` / `scripts/verify.sh frontend` / `scripts/verify.sh e2e`。

## 未测风险

- 真实 PostgreSQL 历史数据中批量账务 legacy relation / 半迁移 / 重复 case id 的全量回放仍需 staging 或生产前 dry-run。
- 真实 RabbitMQ/Redis/systemd `workbench-relation` worker drain、App Status readiness 收敛和长时间队列重试仍需环境 smoke。
- 大年份范围、超长 OA 描述、长备注和高行数表格的真实浏览器性能/视觉回归未由当前单元测试完全证明；当前前端分页接入由 Vitest 证明请求参数和可见行边界，Playwright smoke 只覆盖小样本提交链路，仍需要真实登录态浏览器 smoke 采集实际渲染耗时。
- 关联台、银行明细、成本统计、搜索等下游页面对同一 relation read model 的最终显示仍由对应模块回归继续保护。

# 批量账务 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 需要保护的行为 | 当前测试入口 |
| --- | --- | --- |
| 页面交互 | 加载、空态、错误、筛选、bucket 切换、银行/OA 选择、差额说明、提交、撤回、feedback、侧栏入口 | `web/src/test/BatchAccountingPage.test.tsx`、`web/e2e/batch-accounting-flow.spec.ts` |
| 当前页写后收敛 | 提交/撤回 command 失败必须显示失败；成功响应 targets 为空并立即重跑当前页 normal GET，零 operation barrier、零 downstream dirty/outbox；route/repository 不得调用旧 lifecycle、旧 pair/read-model persist 或 hidden enqueue；reload 中断不能把已成功 command 改写成失败，成功后不能残留错误提示 | `web/src/test/BatchAccountingPage.test.tsx`、`web/e2e/batch-accounting-flow.spec.ts`、`tests/test_batch_accounting_api.py`、`tests/test_platform_runtime_boundary_guards.py` |
| API contract | `GET /api/batch-accounting`、`POST /api/batch-accounting/submit`、`POST /api/batch-accounting/{relation_id}/withdraw` 的状态码、错误码、DTO shape、freshness 字段 | `tests/test_batch_accounting_api.py` |
| 业务核心 | 日常报销 OA 过滤、批量账务银行流水过滤、金额差异说明、version conflict、active relation 排除、跨年选择、撤回原因 | `tests/test_batch_accounting_api.py` |
| Service / repository | `BatchAccountingService` 调用 Workbench payload、relation command service、relation facade；未提交 relation rows、候选/年度 proof、groups 和年份 `submitted_count` 固定为一个 batch-only bundle I/O，不存在独立 count reader；年度 count 使用 migration 0113 的 batch-only partial expression index；列表银行/OA/附件固定为一个 active-generation repository I/O，只返回规范化 `payload`、不读取未消费的 `raw_payload`，银行只按结构化 counterparty 读取，OA 类型使用 migration 0112 覆盖的稳定组合表达式，OA 附件只按候选 IDs 读取；submit/withdraw 边界不变 | `tests/test_batch_accounting_api.py`、`tests/test_workbench_relation_read_facade.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_batch_accounting_postgres_integration.py`、`tests/test_workbench_v2_api.py` |
| Relation read model | `workbench_relation` fresh/missing/stale、row id 去重、linked/unlinked projection、refresh enqueue、source version；repository 12-scope read-model proof 固定 1 条 SQL，canonical expected proof 固定 1 条 bulk SQL并逐 scope 等价比较，禁止恢复 12 次单月查询；count/list 总语句数固定为 2，候选 lookup 固定为 2–3 | `tests/test_workbench_relation_read_facade.py`、`tests/test_workbench_relation_sql_projection.py`、`tests/test_batch_accounting_api.py` |
| 真实 PostgreSQL | 当前全部 migrations 上执行 bulk scope proof、年度 count/list、row lookup、processing fail-closed、列表单 I/O 与 submit OA-ID-scoped attachment SQL；bulk canonical expected proof 必须与 12 个单月 proof 完全相等；5,000 行非命中 OA 和 5,000 条非 batch relation 样本上的 `EXPLAIN` 必须分别命中 0112 OA 类型索引与 0113 年度 relation count 索引 | `tests/test_batch_accounting_postgres_integration.py`（需要 visibly disposable `FIN_OPS_TEST_DATABASE_URL`） |
| Worker / App Status | `workbench-relation` worker registry、`workbench_relation.read_model.refresh` job、App Status domain/job 映射 | `tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` |
| Cross-page access convergence | 批量账务关系变化不主动刷新关联台、银行明细、成本统计、搜索或发票 lifecycle；轻量事件只提示已可见 consumer GET，隐藏页面在再次可见时 GET | `tests/test_platform_runtime_boundary_guards.py`、`web/src/test/domainEvents.test.ts`、`web/src/test/useActiveFinanceDomainEvent.test.tsx`、`web/e2e/batch-accounting-flow.spec.ts` |
| 关联台投影 | active `relation_mode=batch_accounting` 关系必须进入关联台 paired 区，不能被 open `existing_case_candidate` 旧候选链路接管；覆盖多 OA、多 OA 附件发票和金额不一致说明形态 | `tests/test_workbench_sql_runtime.py` |

## 关键场景覆盖

| 场景 | 当前状态 | 保护入口 |
| --- | --- | --- |
| 首屏 `GET /api/batch-accounting` 暂时失败时显示错误态、不显示普通空态，点击刷新后恢复银行/OA rows 且清除失败文案 | covered | `BatchAccountingPage.test.tsx::recovers after a transient batch accounting load failure when refreshed`、`web/e2e/batch-accounting-flow.spec.ts::recovers list after a transient load failure when refreshed` |
| unsubmitted 列表只走专属 SQL read model loader；银行按流水年份筛选，OA 按“日常报销且没有关联银行流水”筛选，旧 `oa_year` 参数不能过滤候选；loader 缺失时 503，不回退 full-page builder | covered | `test_unsubmitted_list_uses_sql_read_model_loader_when_available`、`test_unsubmitted_list_fails_closed_without_sql_workbench_loader`、`test_unsubmitted_list_ignores_legacy_oa_year_filter`、`test_unsubmitted_list_filters_oa_rows_by_linked_bank_transactions_only` |
| submit 只走 SQL narrow loader，通过 submit context 边界只读取本次选中银行/OA/附件发票 rows；写前 active relation 检查只按本次 row ids 走 canonical command service，不再请求 relation read model fresh，不扫描整页候选 payload 或整页候选 relation distribution；loader 缺失时 503 | covered | `test_submit_uses_sql_read_model_loader_when_available`、`test_submit_fails_closed_without_sql_narrow_loader`、`test_submit_checks_active_relations_only_for_selected_rows_without_relation_read_model_gate`、`test_batch_accounting_route_handlers_do_not_bypass_service_boundaries` |
| submit/withdraw 只保存 canonical relation/history/idempotency/audit；不调用旧 pair persist/snapshot restore/lifecycle/read-model persist，durable repository 零 dirty/outbox；跨月只返回信息性 scopes，不 fallback all；旧关系撤回缺 metadata 时用 SQL 窄上下文推导月份 | covered | `test_submit_does_not_call_legacy_post_command_side_effects`、`test_submit_records_concrete_affected_scope_keys_for_cross_month_relation`、`test_withdraw_legacy_relation_derives_scope_keys_from_narrow_context`、`test_withdraw_legacy_relation_uses_sql_narrow_loader_for_scope_backfill`、`test_batch_accounting_route_handlers_do_not_bypass_service_boundaries`、零 targets/queue assertions |
| unsubmitted 列表显式分页首屏保护；首屏银行/OA/附件只有一个 active-generation repository I/O、附件只读当前 OA candidate，候选 relation 与 `submitted_count` 共用一个 bundle；银行/OA/年度 relation count 查询命中专用索引，候选/已提交 relation lookup 不再进入通用逐 scope reader | covered | `test_unsubmitted_list_explicit_pagination_protects_first_screen_slo`、`test_unsubmitted_relation_lookup_is_scoped_to_batch_candidates`、`test_unsubmitted_list_uses_relation_count_instead_of_month_relation_scan`、`test_batch_accounting_repository_uses_fixed_statement_counts`、`test_batch_accounting_loader_reads_only_active_workbench_generations`、`test_unsubmitted_candidate_and_attachment_reads_use_hot_paths`、`test_batch_accounting_route_handlers_do_not_bypass_service_boundaries` |
| GET 列表只读，不触发 legacy repair | covered | `test_unsubmitted_list_does_not_run_legacy_relation_repair` |
| 未提交列表排除已经被其他关系占用的银行行 | covered | `test_unsubmitted_list_excludes_bank_rows_already_linked_elsewhere` |
| relation read model missing/stale 透传到 API 和页面，列表通过 freshness 边界入队刷新，页面不能把非 fresh 空关系当真实空；写操作阻断由 canonical write safety 决定 | covered | `test_unsubmitted_list_exposes_relation_read_model_missing_status`、`test_submitted_list_exposes_relation_read_model_stale_status`、`test_unsubmitted_list_requires_fresh_relation_read_model_to_enqueue_missing_refresh`、`test_submitted_list_requires_fresh_relation_read_model_to_enqueue_stale_refresh`、canonical command service / version conflict / rollback tests |
| 金额不一致必须填写 trim 后非空差额说明，金额一致忽略说明 | covered | `test_submit_amount_mismatch_requires_difference_note`、`test_submit_amount_mismatch_rejects_whitespace_note`、`test_submit_matched_amount_ignores_supplied_difference_note` |
| 提交通过 relation command service 写入 batch relation、当前 invoice rows、历史备注和 `affected_scope_keys`；缺 command service 时 fail fast，不 direct pair fallback；OA 仅有发票关系时可补关联流水 | covered | `test_submit_creates_batch_accounting_relation_with_current_invoice_rows`、`test_submit_allows_invoice_only_oa_relation_without_linked_bank_flow`、`test_submit_amount_mismatch_with_note_persists_relation_and_history`、`test_submit_delegates_relation_write_to_command_service`、`test_submit_requires_relation_command_service_without_direct_pair_fallback`、`test_submit_records_concrete_affected_scope_keys_for_cross_month_relation` |
| 批量账务 active relation 在关联台投影为 paired group | covered | `tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_sql_projection_keeps_active_batch_accounting_oa_bank_relation_paired`、`test_sql_projection_keeps_active_batch_accounting_multi_oa_invoice_relation_paired` |
| 旧 case_id collision repair 入口已删除，不允许重新进入 batch-accounting service/API/worker 主链路 | covered | `test_batch_accounting_legacy_repair_entrypoint_is_removed`、`test_batch_accounting_route_handlers_do_not_bypass_service_boundaries` |
| submitted 列表来自 active batch relation，并按年份级 relation distribution 归桶；不能按 12 个月循环读取、跨用未提交 loader 或用整页候选 payload 补齐 OA/发票明细；缺少专属银行 loader/年份级 relation reader时 fail closed | covered | `test_submitted_list_is_derived_from_active_batch_accounting_relations`、`test_submitted_list_relation_bucket_uses_workbench_relation_distribution`、`test_submitted_list_does_not_fallback_to_unsubmitted_loader`、`test_submitted_list_fails_closed_without_year_relation_reader` |
| 撤回取消当前 batch relation、保留历史说明、要求撤回原因且只能撤回 batch relation；缺 command service 时 fail fast，不 direct pair fallback；PostgreSQL runtime 必须使用 durable relation repository，避免 in-memory-only 成功 | covered | `test_withdraw_mismatch_batch_preserves_submit_and_withdraw_notes`、`test_withdraw_requires_reason_and_batch_accounting_relation`、`test_withdraw_delegates_relation_write_to_command_service`、`test_withdraw_requires_relation_command_service_without_direct_pair_fallback`、`test_postgres_batch_withdraw_uses_durable_relation_repository`、`test_batch_accounting_withdraw_has_no_direct_pair_write_fallback` |
| 前端提交/撤回后广播 `workbenchRelationUpdated`，选中行和差额说明在刷新/bucket/选择变化时正确清理 | covered | `BatchAccountingPage.test.tsx` |
| 前端提交/撤回只阻塞 HTTP command；成功后零 barrier并以 normal GET 恢复 bucket，reload 中断不把成功改写成失败 | covered | `BatchAccountingPage.test.tsx` normal GET / zero-barrier assertions、`web/e2e/batch-accounting-flow.spec.ts` |
| 窄桌面窗口下左侧批量账务流水 rail 保持可读，标题、说明、年份输入和分页控件不互相挤压或溢出 | covered | `BatchAccountingPage.test.tsx` CSS 契约、`web/e2e/batch-accounting-flow.spec.ts` |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_batch_accounting_api.py` | 覆盖金额差异说明、合法银行/OA 行、OA 仅按关联银行流水排除、version conflict、撤回原因。后续如改匹配/金额/状态规则，必须继续补。 |
| 2. Service-layer tests | 适用 | `tests/test_batch_accounting_api.py`、`tests/test_workbench_relation_read_facade.py`、`tests/test_workbench_v2_api.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 `BatchAccountingService` 与 relation command service、relation facade、旧 pair/lifecycle/workbench persist、legacy repair 和 full-page fallback 删除、三类专属 Workbench loader 与缺失 fail-closed、unsubmitted 候选级 relation lookup、年份级 submitted count/DTO、affected scope metadata、PostgreSQL durable relation repository wiring，以及 submit/withdraw canonical write safety。 |
| 3. API contract tests | 适用 | `tests/test_batch_accounting_api.py` | 覆盖 GET/submit/withdraw 的成功 shape、显式分页 `pagination` / `invalid_paging`、错误码、freshness 字段、summary/relations/mutation result；read model non-fresh 由 GET/facade 透出诊断，mutation 默认不因普通 distribution 追赶中被拒。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_workbench_relation_read_facade.py`、`tests/test_batch_accounting_postgres_integration.py`、`tests/test_workbench_relation_sql_projection.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`、`tests/test_batch_accounting_api.py` | 覆盖 bulk freshness proof 的固定查询数与真实 PostgreSQL 语法/状态、projection、non-fresh enqueue、worker registry 和 App Status 绑定；submit/withdraw route 不得重复触发旧 read model persist 或旧 lifecycle。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/BatchAccountingPage.test.tsx`、`web/e2e/batch-accounting-flow.spec.ts` | 覆盖 loading/empty/error、首屏失败恢复、防 false-empty、freshness 诊断、筛选、选择、提交、撤回、零 operation barrier、当前页 normal GET、窄桌面可读性和成功后零可见错误。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_batch_accounting_api.py`、`tests/test_workbench_v2_api.py`、`tests/test_workbench_sql_runtime.py`、`web/src/test/domainEvents.test.ts`、`web/e2e/batch-accounting-flow.spec.ts` | 覆盖 submit -> canonical Workbench relation -> 当前页 GET -> submitted、withdraw -> cancel relation -> 当前页 GET -> unsubmitted；Browser 额外证明零 barrier与零隐藏错误。生产 smoke 需证明写后零 fan-out，并逐页访问验证 paired/consumer 可见性和耗时。 |
| 7. Existing feature regression tests | 适用 | `tests/test_batch_accounting_api.py`、`tests/test_workbench_v2_api.py`、`web/src/test/BatchAccountingPage.test.tsx`、`web/e2e/batch-accounting-flow.spec.ts` | 覆盖非 batch relation 不被覆盖、legacy repair 入口不得回归、旧页面不把 non-fresh relation 当真实空；Browser e2e 防止提交/撤回后的 summary、bucket、OA 表格状态和“成功但报错提示仍显示”的回归。 |

## 历史 Bug 回归库

| 来源 | 回归点 | 当前状态 |
| --- | --- | --- |
| Legacy case id collision | 旧 batch-accounting service-level repair 入口已删除，生产 API/worker 主链路不再提供该兼容写入口；如仍需处理历史数据，必须走 owner 批准的独立迁移/repair runbook，而不是重新接回页面模块 | covered |
| Relation read model non-fresh | missing/stale 不能被解释成“无关联，可提交”；列表读取必须入队刷新，submit/withdraw 默认由 canonical write safety、owner 状态、权限/session、DB 可写性决定 | covered |
| Annual bulk proof source versions | 年度 12-scope bundle 必须逐 scope 返回 source version proof；canonical expected versions 必须由一次 bulk SQL 读取且与 12 次单月证明完全相等，facade 只在 bulk 缺单 scope 时回退该 scope；版本一致时必须 fresh 且零 enqueue，不能因只返回首月汇总版本而永久 stale | covered |
| Submit command boundary | submit 缺少 relation command service 时不能 direct 写 pair service，必须返回结构化错误 | covered |
| Withdraw command boundary | withdraw 缺少 relation command service 时不能 direct 写 pair service，PostgreSQL runtime 必须接入 durable repository；撤回语义是 cancel current batch relation，不是旧 snapshot restore | covered |
| Route boundary contamination | GET route 只能通过 `BatchAccountingApiRoutes.list_payload(...)` / `BatchAccountingService.build_payload(...)` 读，不得 repair/write/schedule；submit/withdraw `server.py` wrapper 必须经 mutation session 并委托 `BatchAccountingApiRoutes`，route owner 必须委托 `BatchAccountingService` 且不得直接调用 relation write internals、旧 lifecycle、旧 pair persist 或旧 workbench persist；app-level `_repair_batch_accounting_relation_case_ids` 和 service-level `repair_legacy_case_id_collisions` 不得回归 | covered |
| Mismatch note | 金额不一致必须填写非空说明；切换银行、bucket、OA 选择时清空旧说明 | covered |
| Legacy post-command side-effect deletion | batch-accounting route/repository 不得在 command service 保存后调用旧 pair persist、snapshot restore、lifecycle、read-model persist 或任何 fan-out；普通写必须零 queue I/O | covered |
| Withdraw history | 撤回差额批量账务时保留提交和撤回备注；不把 OA 附件 case_id / `existing_case` 显示归属恢复成 active relation | covered |
| Access-to-fresh closure | submit/withdraw 后不靠前端事件假装完成；零 barrier，仅当前页 normal GET 证明 fresh，reload 失败不能覆盖 command 成功 | covered |
| Load failure false-empty | 首屏列表 GET 暂时失败不能显示“当前年份暂无批量账务流水”，用户点击刷新后必须恢复业务行并清除失败文案 | covered |
| First-screen page-size guard | 显式请求分页时 `page_size=200` 是上限，`bank_rows` / `oa_rows` 有界返回，summary total 保留，`page_size>200` 返回结构化 `invalid_paging`；前端未提交 bucket 首屏发送 `bank_page_size=200` / `oa_page_size=200` 并独立翻页 | covered |
| Daily reimbursement OA bank-link filter | 日常报销 OA 的右侧候选只因已关联银行流水而排除；仅发票关系或无流水候选关系不能排除，也不能在提交时被 active invoice-only relation 拒绝 | covered |
| Submitted relation reader boundary | 已提交 bucket 缺少年份级 relation reader 时必须 fail closed 为 unavailable，不能回退 12 个月 `list_by_month` | covered |
| Workbench full-payload fallback | 三类专属 SQL loader 缺失/无效时必须返回 `503 batch_accounting_workbench_read_model_unavailable`；不得调用 generic grouped/full-page builder，也不得跨用其它操作的 loader | covered |
| Read timing boundary | 批量账务 GET 必须只在 `Server-Timing` 头暴露候选/relation/组装/序列化阶段，业务 JSON 不得出现 timing 内部字段；service observer 必须覆盖 relation read 阶段 | covered |
| Read-copy budget | 列表 payload mapper 与 service group 注解不得递归复制嵌套 JSON；relation bundle 不得重新携带未消费的 row payload/raw payload 或 group raw payload | covered |

## 关键 Smoke Flows

1. 首屏 `GET /api/batch-accounting` 暂时 503 -> 页面显示错误态且不显示普通空态 -> 用户点击刷新 -> 银行/OA rows 恢复、失败文案消失、没有隐藏浏览器错误。
2. 批量账务列表 fresh -> 选择银行流水 -> 选择 OA 行 -> 金额一致提交 -> `workbenchRelationUpdated` 轻量提示 -> 当前页 normal GET -> submitted bucket 展示关系；Browser 明确断言零 operation barrier和零可见错误。
3. 金额不一致 -> 空说明被拒 -> 填写说明提交 -> 关联台/银行明细/成本统计下游通过 relation read model 看到关系标签。
4. submitted bucket -> 填写撤回原因 -> 撤回 -> relation read model refresh -> 原银行/OA 行回到可处理状态；`web/e2e/batch-accounting-flow.spec.ts` 覆盖真实 Chromium 撤回弹窗、原因输入、确认撤回、barrier、回到未提交 bucket 和成功后无可见错误残留。
5. `workbench_relation` missing/stale -> API 透出 freshness 并经 facade/gateway 入队刷新 -> 页面显示 warning/reason/scope，不把当前可用 rows 当作真实空态，也不因普通 read model non-fresh 全局禁用具备 canonical write safety 的操作 -> worker 刷新后恢复；`web/e2e/batch-accounting-flow.spec.ts` 已覆盖 stale 诊断下可见 rows 和零 mutation。
6. 显式 `page/page_size` -> `bank_rows` / `oa_rows` 有界返回、summary 仍保留完整命中数量，超限页大小 fail closed。
7. submit/withdraw -> 只阻塞写 API -> 成功后 normal GET 当前 bucket；GET 非 fresh 使用页面内 refreshing/retry，禁止调用 operation barrier或改写 command 成功。

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

Nightly CI 通过 `scripts/verify.sh all` 执行后端、前端、Playwright browser smoke 和文档校验。`web/e2e/batch-accounting-flow.spec.ts` 覆盖 submit/withdraw 零 barrier、当前页 normal GET、bucket 恢复、首屏失败重试、stale 诊断、窄桌面布局和零隐藏/可见错误；后端 guards 保护 repository 零 fan-out。跨模块改动再升级为完整 backend/frontend/e2e 验证。

## 未测风险

- 真实 PostgreSQL 历史数据中如仍存在批量账务 legacy relation / 半迁移 / 重复 case id，当前页面模块不再提供内置 repair 入口；必须走 owner 批准的独立迁移/repair runbook。
- 真实 RabbitMQ/Redis/systemd `workbench-relation` worker drain、App Status readiness 收敛和长时间队列重试仍需环境 smoke。
- 大年份范围、超长 OA 描述、长备注和高行数表格的真实浏览器性能/视觉回归未由当前单元测试完全证明；当前前端分页接入由 Vitest 证明请求参数和可见行边界，Playwright smoke 只覆盖小样本提交链路，仍需要真实登录态浏览器 smoke 采集实际渲染耗时。
- 关联台、银行明细、成本统计、搜索等下游页面对同一 relation read model 的最终显示仍由对应模块回归继续保护。

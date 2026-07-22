# 银行流水导入 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 需要保护的行为 | 当前测试入口 |
| --- | --- | --- |
| 前端页面/共享工作流 | 独立路由、银行账户映射加载、每文件银行选择、预览、确认、preview stale 错误、session restore、read-only 导入门禁、视觉/CSS 契约 | `web/src/test/ImportCenterPage.test.tsx`、`web/e2e/imports-bank-transactions-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` |
| 前端 API mapper | multipart `file_overrides`、Authorization/credentials、session/confirm/retry/fetch、duplicate groups、skipped rows、preview stale message | `web/src/test/ImportsApi.test.ts` |
| 文件预览 API | 损坏 Excel、模板识别、银行流水模板、per-file override、银行选择冲突、只确认 selected files | `tests/test_import_file_api.py` |
| 文件预览 service | 文件级错误、session/file/batch id 去重、银行映射冲突与别名、preview stale、真实银行流水模板 | `tests/test_import_file_service.py` |
| 银行流水 parser/normalizer | 原始文本列、真实 Excel text contract、银行流水 identity、不改 identity 的文本字段 | `tests/test_import_api.py`、`tests/test_import_service.py`、`tests/test_import_preview_audit.py` |
| 确认/持久化 | confirm 持久化、重复跳过、selected bank mapping 字段保留、导入跨重启持久化、batch revert/download | `tests/test_import_service.py`、`tests/test_import_formalization_api.py` |
| Import worker / queue | idempotency key、small RabbitMQ envelope、unknown processor failure、registered processor success、worker check、RabbitMQ confirm queue | `tests/test_import_job_queue.py`、`tests/test_runtime_worker_registry.py` |
| Import worker 跨进程恢复 | worker 启动后新增 file session 仍须在 job 执行时从 PostgreSQL 重载，禁止使用启动时陈旧 session/canonical snapshot | `tests/test_import_job_queue.py::ImportJobRepositoryTests::test_runtime_import_processor_reloads_durable_state_after_worker_bootstrap` |
| Import API 跨进程恢复 | API 重启后 session GET/confirm/retry 从显式 PostgreSQL import/file-session loaders 恢复当前 session，且不调用 legacy/full-state load | `tests/test_runtime_bootstrap.py::RuntimeBootstrapTests::test_postgres_file_import_boundary_reloads_current_session_without_full_state_load` |
| 下游 fan-out | bank import confirmed -> bank detail/balance、Workbench/relation/matching、invoice lifecycle、cost/search | `tests/test_derived_data_lifecycle_service.py`、`tests/test_workbench_v2_api.py`、`tests/test_bank_account_balance_read_model.py`、`tests/test_bank_details_sql_runtime.py` |
| App Status/App Health | imports bank domain route、import worker/job、file import explicit affected domain、generic import job fallback 不误指发票页、global status plane | `tests/test_app_status_overview_service.py`、`web/src/test/AppStatusIndicator.test.tsx` |
| 边界/旧代码 guard | 银行流水前端只走 `/imports/files/*`；`server.py` 不重新持有 import confirm processor wrapper | `tests/test_platform_runtime_boundary_guards.py` |
| Page Audit 时间点一致性 | 无时区中国本地交易时间与等价 UTC `timestamptz` 必须视为同一时刻；真实时间漂移必须阻断 | `tests/test_audit_bank_transaction_import_page.py::BankTransactionImportPageAuditPostgresTests::test_naive_china_trade_time_is_compared_as_the_same_instant_and_real_drift_blocks` |
| Page Audit 可恢复失败诊断 | retryable failed import job 返回正式重试所需的 session/file 坐标和有限错误信息，不要求直接数据库修复 | `tests/test_audit_bank_transaction_import_page.py::BankTransactionImportPageAuditTests::test_retryable_failed_job_exposes_admin_safe_retry_coordinates` |

## 关键场景覆盖

| 场景 | 当前状态 | 保护入口 |
| --- | --- | --- |
| 银行导入独立路由使用共享 `ImportWorkflowPage`，每个文件发送银行映射 override | covered | `bank transaction import uses the standalone route and sends bank mapping overrides`、`ImportsApi.test.ts` |
| 页面展示 preview audit counts 和确认文案 | covered | `bank transaction import displays preview audit counts and confirm copy` |
| 前端把 `preview_stale` 映射为“重新预览”提示 | covered | `file import confirm maps preview_stale to the refresh preview message` |
| 损坏文件作为文件级错误，不中断整批预览 | covered | `test_preview_files_keeps_corrupt_excel_as_file_level_error_without_aborting_batch`、`test_preview_marks_corrupt_excel_as_file_level_error_instead_of_raising` |
| 银行流水模板识别与真实银行 Excel 文本字段保留 | covered | `test_preview_files_recognizes_bank_statement_templates`、`test_bank_file_parsers_preserve_real_excel_text_field_contracts` |
| 光大/建行真实导出表头别名识别 | covered | `test_preview_accepts_ceb_xlsx_statement_with_income_expense_amount_headers`、`test_parse_ccb_statement_accepts_customer_account_and_voucher_number_headers` |
| 240 行合成银行流水同文件重复组只产生一个可确认代表，其余进入 duplicate audit | covered | `test_preview_bounds_large_bank_duplicate_group_to_one_confirmable_row` |
| 选择银行映射持久化，检测账号冲突，银行别名/简称/法定名称不误报 | covered | `test_preview_persists_selected_bank_mapping_and_marks_conflict_against_detected_account`、`test_preview_does_not_mark_bank_*_as_conflict_when_last4_matches` |
| preview stale 时拒绝 confirm | covered | `test_confirm_session_rejects_stale_preview_when_existing_records_change`、`test_import_file_confirm_returns_preview_stale_when_existing_records_change` |
| confirm 只导入 selected files | covered | `test_confirm_files_imports_only_selected_files_from_session` |
| stale API 预览银行文件不得覆盖另一进程已确认的发票/session/batch | covered | `test_preview_session_persistence_payload_excludes_unrelated_sessions_and_canonical_facts`、`test_stale_api_preview_cannot_downgrade_another_process_confirmed_import`、`test_save_import_delta_rolls_back_batch_when_file_write_fails` |
| file/session confirm 只处理 selected files 并返回银行导入 domain targets | covered | `test_confirm_files_imports_only_selected_files_from_session`、`test_confirm_bank_transaction_file_job_reports_bank_import_domain`、`test_file_import_confirm_job_returns_import_write_targets` |
| 旧 JSON HTTP route、`general_import.confirm` processor 和 server confirm wrapper 保持删除 | covered | `test_bank_transaction_import_frontend_uses_file_session_api_only`、`test_server_no_longer_exposes_legacy_json_import_write_routes`、`test_server_no_longer_owns_import_confirm_processors` |
| 银行导入确认后的 Workbench/bank detail/cost operation targets | covered | `test_file_import_confirm_job_returns_import_write_targets` |
| bank import lifecycle fan-out 到银行明细/账户余额、Workbench、relation、matching、invoice lifecycle、cost/search | covered | `test_bank_import_confirmed_maps_workbench_candidate_cost_and_search_domains` |
| Browser e2e 上传/预览/慢预览防重复提交/重复/损坏文件混合/冲突取消零提交/冲突确认/preview stale/confirm 失败/下游银行明细 | covered | `web/e2e/imports-bank-transactions-flow.spec.ts` |
| read_export_only 不能上传/预览/确认导入 | covered | `web/e2e/permissions-role-matrix.spec.ts` |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_import_service.py`、`tests/test_import_api.py`、`tests/test_import_preview_audit.py` | 覆盖银行流水 direction、金额、identity、重复/疑似重复、缺失秒级时间、账号维度唯一键、原始文本字段。 |
| 2. Service-layer tests | 适用 | `tests/test_import_file_service.py`、`tests/test_import_job_queue.py`、`tests/test_import_formalization_api.py` | 覆盖 session/file/batch 生命周期、preview stale、confirm 持久化、job idempotency、worker processor。 |
| 3. API contract tests | 适用 | `tests/test_import_file_api.py`、`tests/test_import_api.py`、`web/src/test/ImportsApi.test.ts`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 `/imports/files/preview`、`confirm`、`retry`、`sessions`、legacy preview/confirm、错误 shape 和 mapper；boundary guard 锁定银行流水前端不调用旧 JSON API。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_import_job_queue.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_bank_account_balance_read_model.py`、`tests/test_bank_details_sql_runtime.py`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_bank_detail_for_transaction_month_scopes`、`tests/test_app_status_overview_service.py`、`tests/test_write_operation_slo_audit.py` | 覆盖 import worker、dirty fan-out、银行余额/明细 projection、App Status，并用 `bank_import_confirmed` write-operation profile 防止真实银行确认少刷新通用下游 read model、银行账户余额 `bank_account_balance.read_model.refresh` 或银行明细真实 `bank_detail.read_model.refresh` 时仍被判定闭环；进项/销项发票方向页未命中时允许 `skipped`，账户余额 API fresh gate 仍需 staging/browser smoke 观察。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/ImportCenterPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/e2e/imports-bank-transactions-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 覆盖独立路由、上传/预览/确认、错误、session restore、job feedback、App Status popover；Browser e2e 覆盖真实文件 input、账户 select、慢预览期间禁用预览/清空/确认动作、audit/重复明细、损坏文件 file-level error、未导入项明细、冲突 dialog、取消冲突零提交、preview stale、confirm 失败、确认后 dialog close、银行明细账户余额 fresh gate、成本统计下游 fresh read model、成功后无导入失败/后台导入失败/read model 失败可见残留和 read-only 禁用上传/预览/确认。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_import_formalization_api.py`、`tests/test_workbench_v2_api.py`、`web/src/test/ImportCenterPage.test.tsx`、`web/e2e/imports-bank-transactions-flow.spec.ts` | 覆盖 preview -> confirm -> persisted import -> declared operation barrier / stale preview；Browser e2e 覆盖慢预览单次提交、confirm 后只等待显式 targets 且零 Workbench 页面请求、银行明细账户余额 fresh gate 和导入行、成本统计自身 fresh read model，以及损坏文件、冲突取消、preview stale / confirm 失败时零 barrier/零 Workbench 请求且不误报成功。组件测试另覆盖 targets 为空时直接完成。真实 worker drain 仍是 documented-risk。 |
| 7. Existing feature regression tests | 适用 | `tests/test_import_file_service.py`、`tests/test_workbench_v2_api.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_platform_runtime_boundary_guards.py`、`web/src/test/ImportCenterPage.test.tsx`、`web/e2e/imports-bank-transactions-flow.spec.ts` | 覆盖旧 JSON import 兼容、文件导入、发票/ETC 共享工作流、损坏文件 file-level error、下游页面 refresh、preview stale、confirm 失败、旧 wrapper 删除防回归，以及冲突确认弹窗取消不提交、成功提交后不会继续挡住导航。 |

## 历史 Bug 回归库

| 来源 | 回归点 | 当前状态 |
| --- | --- | --- |
| Preview stale | 预览后底层记录变化，确认必须拒绝并提示重新预览 | covered |
| 银行账号映射冲突 | 用户选择银行与文件识别账号不一致时必须展示冲突，别名/简称/法定名称不能误报 | covered |
| 损坏文件 | 单个损坏 Excel 不能中断整批预览；Browser 必须显示 file-level error，且 confirm 只提交正常文件 ID。 | covered |
| 慢预览/大文件耗时 | 预览请求未完成时按钮必须显示“预览中...”，预览/清空/确认全部禁用，不能重复提交 preview 或中断成半状态。 | covered |
| 原始文本列 | 银行流水导入必须保留摘要、备注、用途等原始文本列，不影响 identity | covered |
| 光大/建行官方导出表头别名 | 光大 `借方金额（支出）` / `贷方金额（收入）`、光大负数支出/收入列回退行、建行 `客户账号` / `凭证号码` 必须识别为既有银行流水模板，不得做模糊猜列。 | fixed 2026-06-22 |
| RabbitMQ confirm | 异步 confirm 只能传小 envelope，processor 由 worker 拉取事实 | covered |
| App Status job mapping | 银行流水文件确认必须写入 `imports_bank_transactions` affected domain；generic `file_import` / `import.process.requested` fallback 不能误指发票页 | fixed 2026-06-16 |
| 2026-07-05 边界 close | 银行流水页面不得回退旧 `/imports/preview`、`/imports/confirm` JSON API；`server.py` 不得重新拥有 import confirm processor wrapper | fixed by `tests/test_platform_runtime_boundary_guards.py` |
| 2026-07-22 stale preview lost update | 银行 preview/retry 只能写当前 session/preview batch，不能把其它已确认导入覆盖回 pending；PostgreSQL batch 与 file/session 同事务 | fixed by `tests/test_import_file_service.py`、`tests/test_import_formalization_api.py`、`tests/test_postgres_repositories_core.py` |
| 大重复组 | 合成 240 行同文件银行流水重复组必须只产生一个 confirmable representative，避免大文件 preview 把重复项全部当作可确认 | fixed 2026-06-16 |
| 2026-06-17 Browser e2e | 银行账户冲突弹窗里确认导入成功后未关闭，modal backdrop 阻塞用户导航到银行明细或其他页面。 | fixed by `web/e2e/imports-bank-transactions-flow.spec.ts` |
| 2026-06-19 Browser e2e | 银行账户冲突弹窗取消必须只关闭弹窗，不能提交 confirm、不能调用 operation barrier 或 Workbench 页面 API、不能显示导入成功；用户随后仍可重新确认导入。 | fixed by `web/e2e/imports-bank-transactions-flow.spec.ts` |
| 2026-06-19 Browser e2e | 损坏银行流水文件与正常文件混合上传时，页面必须保留正常文件 preview，不整批失败，确认时不得提交损坏文件 ID。 | fixed by `web/e2e/imports-bank-transactions-flow.spec.ts` |
| 2026-06-19 Browser e2e | 银行流水预览耗时较长时，用户不能重复点击预览、清空文件或提前确认，避免多个 `/imports/files/preview` 请求或半状态。 | fixed by `web/e2e/imports-bank-transactions-flow.spec.ts` |
| 2026-06-19 Browser e2e | 银行流水导入确认后不能只证明银行明细刷新，还要证明成本统计以 fresh read model 显示导入流水成本证据。 | fixed by `web/e2e/imports-bank-transactions-flow.spec.ts` |
| preview stale Browser 回归 | 预览后底层事实变化时，前端不得创建 import job、不得调用 operation barrier 或 Workbench 页面 API、不得显示成功。 | fixed by `web/e2e/imports-bank-transactions-flow.spec.ts` |
| confirm 失败 Browser 回归 | 导入任务创建失败时，页面必须显示错误并保留 preview，不能误报“已确认导入”。 | fixed by `web/e2e/imports-bank-transactions-flow.spec.ts` |

## 关键 Smoke Flows

1. 上传银行流水 XLS/XLSX -> 为每个文件选择银行账户 -> 预览成功 -> 展示 audit counts、重复组和跳过明细；240 行合成重复组本地回归只允许一个 confirmable representative。Browser smoke 覆盖两份 XLSX 文件、小样本重复审计、慢预览防重复提交、重复项明细、银行账户冲突弹窗、取消冲突零提交和重新确认。
2. 预览后底层数据变化 -> 确认返回 `preview_stale` -> 前端提示重新预览，不创建导入 job，不调用 operation barrier 或 Workbench 页面 API。
3. 确认可导入银行流水文件 -> 创建 background `file_import` job，`affected_domains=["imports_bank_transactions"]`、`route="/imports/bank-transactions"` -> import worker event -> worker confirm -> Workbench matching 入队 -> 银行明细和关联台后续 fresh。
4. 损坏文件 + 正常文件混合上传 -> 损坏文件显示 file-level error 和未导入项明细 -> 正常文件仍可确认，confirm body 只包含正常文件 ID。
5. 导入完成后进入银行明细和成本统计，确认 `bank_account_balance`、`bank_detail` 和 `cost_statistics` 不显示 stale 为 fresh。Browser smoke 当前覆盖导入后进入银行明细等待账户余额 fresh gate 并看到导入行，并在成本统计等待 fresh read model 后看到导入流水成本证据；confirm、银行明细和成本统计成功节点都会检查无导入失败/后台导入失败/read model 失败可见残留。关联台最终显示仍由后端 integration/staging smoke 保护。
6. Staging write-flow audit：真实银行流水确认后运行 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed bash scripts/verify.sh infra-smoke`，必须看到 Workbench、Workbench relation、invoice lifecycle、search、待找发票、OA 待付款、银行账户余额、银行明细和成本统计 refresh scopes 通过 SLO；进项使用/销项收款未命中时应为 `skipped`；随后用 `/api/bank-details/accounts` 或页面 smoke 核对账户余额 API freshness gate 为 fresh。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_import_api \
  tests.test_import_service \
  tests.test_import_file_service \
  tests.test_import_file_api \
  tests.test_import_preview_audit \
  tests.test_import_job_queue \
  tests.test_import_formalization_api \
  tests.test_derived_data_lifecycle_service \
  tests.test_runtime_worker_registry \
  tests.test_app_status_overview_service \
  tests.test_bank_account_balance_read_model \
  tests.test_bank_details_sql_runtime \
  tests.test_write_operation_slo_audit \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_no_longer_owns_import_confirm_processors \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_no_longer_exposes_legacy_json_import_write_routes \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_transaction_import_frontend_uses_file_session_api_only \
  tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_import_file_confirm_returns_preview_stale_when_existing_records_change \
  -v

cd web && npm test -- --run \
  src/test/ImportsApi.test.ts \
  src/test/ImportCenterPage.test.tsx \
  src/test/AppStatusIndicator.test.tsx

cd web && npx playwright test e2e/imports-bank-transactions-flow.spec.ts
cd web && npx playwright test e2e/imports-bank-transactions-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/permissions-role-matrix.spec.ts

bash scripts/verify.sh docs
```

真实 staging/发布前 worker/read model 验证：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit \
  --json \
  --operation bank_import_confirmed \
  --lookback-hours 24

FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed bash scripts/verify.sh infra-smoke
```

该命令审计银行导入后通用下游 `*.read_model.refresh` 事件、`bank_account_balance.read_model.refresh` 事件和 `bank_detail.read_model.refresh`；它不替代账户余额 API fresh gate 页面 smoke，也不替代真实大文件 preview/confirm smoke。

## Nightly CI 覆盖

Nightly CI 通过 `scripts/verify.sh all` 执行后端、前端、Playwright browser smoke 和文档校验。Browser smoke 当前包含 `web/e2e/imports-bank-transactions-flow.spec.ts` 和 `web/e2e/permissions-role-matrix.spec.ts`，保护银行流水导入页真实文件上传、预览、慢预览防重复提交、重复项明细、损坏文件混合上传 file-level error、账户冲突取消零提交、账户冲突确认、preview stale、confirm 失败、confirm 后只等待显式 operation barrier targets 且零 Workbench 页面请求、银行明细账户余额 fresh gate、银行明细下游行、成本统计下游 fresh read model、成功后无错误残留，以及 read-only 用户不能上传/预览/确认导入。银行流水导入变更优先运行本模块窄范围命令；如果改动触及共享 `ImportWorkflowPage`，还要同时评估 `imports-invoices` 和 `imports-etc-invoices` 模块测试。

## 未测风险

- 真实银行多模板大文件、加密/损坏/超大 Excel、边界编码和历史生产文件样本仍需 staging smoke；本地慢预览只证明 UI 防重复提交，不证明真实大文件解析性能。本地已用用户提供的光大、建行、交行、民生、工行文件做 `FileImportService.preview_files` 只读 smoke，均返回 `preview_ready` 且文件级 `error_count=0`；整批仍有 1 条 audit/dedup skipped row，不属于模板或行格式错误。
- 本地已覆盖 240 行合成 ICBC 重复组；它不替代真实银行多模板、加密文件、异常编码、超大 Excel 内存/耗时和历史生产样本 smoke。
- 真实 PostgreSQL + RabbitMQ + Redis + systemd import worker drain、job retry、worker crash/restart、幂等重复确认仍需环境验证；`write_operation_slo_audit --operation bank_import_confirmed` 已有本地契约测试，并要求真实银行确认样本产生 recent `bank_account_balance` outbox rows，但仍需要 staging 中真实 recent outbox rows 和账户余额 API fresh gate 证据。
- 下游页面最终展示依赖银行明细、关联台、成本统计等模块自己的 fresh/read model 回归；本模块 Browser e2e 已覆盖银行明细小样本导入行和成本统计 fresh read model 导入证据，不覆盖真实 worker drain、关联台/search 最终显示或大文件性能。

## 2026-07-15 import row owner 回归

- `tests/test_import_file_service.py`：batch-scoped row id 不再依赖进程级 counter。
- `tests/test_postgres_repositories_core.py`：同一 row id 若已属于其它 batch，repository fail closed，不重挂 owner。
- `tests/test_import_audit_repair_ops.py`：registered file evidence + canonical owner 恢复、重复执行幂等、legacy row id/owner 冲突拒绝。

## 2026-07-22 Phase 27 写后零 fan-out 回归

- `tests/test_import_processing_service.py`、`tests/test_import_file_api.py`：confirm 仍原子提交精确 import delta、幂等/失败回滚和必要领域任务，但结果中的页面 `freshness_targets` / `operation_barrier_targets` 为空，且不发布 read-model refresh。
- `web/src/test/ImportCenterPage.test.tsx` 与共享 `ImportWorkflowPage` 回归：普通完成反馈不等待跨页面 barrier；后续访问银行明细等页面时由页面 freshness gate 收敛。
- 旧的 `write_operation_slo_audit` “确认后必须产生下游 refresh 事件”断言不再是本模块正确性合同；Phase 27-07 改为验证写延迟、零 fan-out 和逐页面访问收敛延迟。

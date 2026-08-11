# 银行流水导入 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 需要保护的行为 | 当前测试入口 |
| --- | --- | --- |
| 前端页面/共享工作流 | 独立路由、银行账户映射加载、每文件银行选择、预览、字段映射 retry、确认、preview stale 错误、session restore、read-only 导入门禁、视觉/CSS 契约 | `web/src/test/ImportCenterPage.test.tsx`、`web/e2e/imports-bank-transactions-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` |
| 前端 API mapper | multipart `file_overrides`、Authorization/credentials、session/confirm/retry/fetch、嵌套 `field_mapping`、duplicate groups、skipped rows、preview stale message | `web/src/test/ImportsApi.test.ts` |
| 文件预览 API | 损坏 Excel、模板识别、银行流水模板、per-file override、银行选择冲突、只确认 selected files | `tests/test_import_file_api.py` |
| 文件预览 service | 文件级错误、session/file/batch id 去重、银行映射冲突与别名、preview stale、真实银行流水模板 | `tests/test_import_file_service.py` |
| 银行 identity v3/v4 / 批量去重 | 复用官方参考号时不同业务指纹可创建；基础键冲突且余额/币种不同的事实生成稳定 statement-position v4 键，同位置重放即使自由文本 fingerprint 漂移也按 position key 判重；历史行尚无 v4 时只接受账户/秒级时间/方向/金额/余额/币种六项全等的唯一 position 命中，多义转疑似；历史 v2 唯一参考号迁移判重、缺失/多义参考号疑似、preview/confirm 常数次批量 preload、同批重复阻断、页面 Audit 对相同业务指纹及相交官方参考号的 v3→v2 引用迁移放行 | `tests/test_bank_transaction_identity_service.py`、`tests/test_object_dedup_decision_service.py`、`tests/test_import_service.py`、`tests/test_postgres_repositories_core.py`、`tests/test_audit_bank_transaction_import_page.py` |
| 生产 cohort 恢复 | 精确 source session/file、目标/保护/重复删除/重放新增/受控重复/错误 reference 释放数门禁、保护集合不相交、唯一 fingerprint/reference duplicate、指纹漂移时唯一 statement-position 二级证据、4 位账户尾号与完整账户的单向兼容及不同完整账户拒绝、dry-run 匹配证据、修复重复 keeper、现存 created owner、既有 canonical duplicate reference 三类权威行证据、reference 六字段不一致释放普通 decision、缺失目标拒绝、拒绝指向待删除事实的引用、关系/核销 fail-closed、文件 hash、审计计数 CAS、可重复受控重放；每次重放登记独立归档对象；历史缺失 object link 和 audit count 只允许在唯一 URI/hash/lifecycle 证明、精确计数、fingerprint 与 CAS 门禁下修复；清理、首轮重放、幂等重放、审计与 refresh outbox 共享一个写事务，任一重放计数门禁失败时回滚全部写入 | `tests/test_bank_import_dedup_repair_service.py`、`tests/test_bank_import_audit_contract_repair.py`、`tests/test_import_file_service.py`、`tests/test_audit_bank_transaction_import_page.py`、`tests/test_import_audit_repair_ops.py` |
| 银行流水 parser/normalizer | 原始文本列、真实 Excel text contract、银行流水 identity、不改 identity 的文本字段 | `tests/test_import_api.py`、`tests/test_import_service.py`、`tests/test_import_preview_audit.py` |
| 确认/持久化 | confirm 持久化、重复跳过、selected bank mapping 字段保留、导入跨重启持久化、batch revert/download | `tests/test_import_service.py`、`tests/test_import_formalization_api.py` |
| Import worker / queue | idempotency key、small RabbitMQ envelope、unknown processor failure、registered processor success、worker check、RabbitMQ confirm queue | `tests/test_import_job_queue.py`、`tests/test_runtime_worker_registry.py` |
| Import worker 跨进程恢复 | worker 启动后新增 file session 仍须在 job 执行时从 PostgreSQL 重载，禁止使用启动时陈旧 session/canonical snapshot | `tests/test_import_job_queue.py::ImportJobRepositoryTests::test_runtime_import_processor_reloads_durable_state_after_worker_bootstrap` |
| Import API 跨进程恢复 | API 重启后 session GET/confirm/retry 从显式 PostgreSQL import/file-session loaders 恢复当前 session，且不调用 legacy/full-state load | `tests/test_runtime_bootstrap.py::RuntimeBootstrapTests::test_postgres_file_import_boundary_reloads_current_session_without_full_state_load` |
| 下游访问收敛 | bank import confirmed 推进 canonical fact/version；银行明细/余额、成本等 direct 页面在下一次 canonical GET 读取新事实，关联台按正式 `workbench` freshness 合同收敛 | `tests/test_import_job_queue.py`、`tests/test_write_operation_slo_audit.py`、`tests/test_write_operation_impact_matrix.py`、`tests/test_bank_details_canonical_query.py` |
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
| 单一 `bank_statement` canonical 解析器识别现有银行 Excel 并保留原始文本字段 | covered | `test_preview_files_recognizes_bank_statement_templates`、`test_bank_file_parsers_preserve_real_excel_text_field_contracts` |
| 建行 `/元` + 半角括号表头、元数据账号/账户名识别 | covered | `test_ccb_current_export_header_uses_metadata_account_and_unit_aliases` |
| 未知核心字段 fail closed、人工映射 retry、相同表头签名复用 | covered | `test_manual_mapping_is_reused_for_same_header_signature`、`bank transaction import maps an unknown amount header and retries the same file`、`ImportsApi.test.ts` |
| 240 行合成银行流水同文件重复组只产生一个可确认代表，其余进入 duplicate audit | covered | `test_preview_bounds_large_bank_duplicate_group_to_one_confirmable_row` |
| 选择银行映射持久化，检测账号冲突，银行别名/简称/法定名称不误报 | covered | `test_preview_persists_selected_bank_mapping_and_marks_conflict_against_detected_account`、`test_preview_does_not_mark_bank_*_as_conflict_when_last4_matches` |
| preview stale 时拒绝 confirm | covered | `test_confirm_session_rejects_stale_preview_when_existing_records_change`、`test_import_file_confirm_returns_preview_stale_when_existing_records_change` |
| preview 汇总计数相同但逐行 canonical owner 调换时拒绝 confirm | covered | `test_confirm_session_rejects_stale_preview_when_linked_object_changes_without_count_change` |
| confirm 只导入 selected files | covered | `test_confirm_files_imports_only_selected_files_from_session` |
| stale API 预览银行文件不得覆盖另一进程已确认的发票/session/batch | covered | `test_preview_session_persistence_payload_excludes_unrelated_sessions_and_canonical_facts`、`test_stale_api_preview_cannot_downgrade_another_process_confirmed_import`、`test_save_import_delta_rolls_back_batch_when_file_write_fails` |
| file/session confirm 只处理 selected files 并返回银行导入 domain targets | covered | `test_confirm_files_imports_only_selected_files_from_session`、`test_confirm_bank_transaction_file_job_reports_bank_import_domain`、`test_file_import_confirm_job_returns_import_write_targets` |
| 旧 JSON HTTP route、`general_import.confirm` processor 和 server confirm wrapper 保持删除 | covered | `test_bank_transaction_import_frontend_uses_file_session_api_only`、`test_server_no_longer_exposes_legacy_json_import_write_routes`、`test_server_no_longer_owns_import_confirm_processors` |
| 银行导入确认返回空页面 freshness/barrier targets，当前页结束写命令 | covered | `test_file_import_confirm_job_returns_import_write_targets` |
| bank import 写后零 direct-page refresh 事件；直接读取页面通过下一次 canonical GET 收敛，关联台按自身 freshness gate 收敛 | covered | `tests/test_write_operation_slo_audit.py`、`tests/test_write_operation_impact_matrix.py`、各页面 canonical query/API tests |
| Browser e2e 上传/预览/慢预览防重复提交/重复/损坏文件混合/冲突取消零提交/冲突确认/preview stale/confirm 失败/下游银行明细 | covered | `web/e2e/imports-bank-transactions-flow.spec.ts` |
| read_export_only 不能上传/预览/确认导入 | covered | `web/e2e/permissions-role-matrix.spec.ts` |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_import_service.py`、`tests/test_import_api.py`、`tests/test_import_file_service.py`、`tests/test_import_preview_audit.py` | 覆盖 canonical 表头归一、元数据提取、direction、金额、identity、重复/疑似重复、缺失秒级时间、账号维度唯一键、原始文本字段。 |
| 2. Service-layer tests | 适用 | `tests/test_import_file_service.py`、`tests/test_import_job_queue.py`、`tests/test_import_formalization_api.py` | 覆盖 session/file/batch 生命周期、人工映射保存与复用、preview stale、confirm 持久化、job idempotency、worker processor。 |
| 3. API contract tests | 适用 | `tests/test_import_file_api.py`、`tests/test_import_api.py`、`web/src/test/ImportsApi.test.ts`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 `/imports/files/preview`、`confirm`、`retry`、`sessions`、legacy preview/confirm、错误 shape 和 mapper；boundary guard 锁定银行流水前端不调用旧 JSON API。 |
| 4. Read model/cache/background job tests | cleanup 适用 | `tests/test_import_job_queue.py`、`tests/test_app_status_overview_service.py`、`tests/test_write_operation_slo_audit.py`、`tests/test_write_operation_impact_matrix.py` | 覆盖 import worker、退休银行明细/余额/Search/no-OA refresh 事件不再出现，以及关联台按正式 `workbench` 合同精确收敛；两个保留 read model 由各自模块测试负责。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/ImportCenterPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/e2e/imports-bank-transactions-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 覆盖独立路由、上传/预览/字段映射 retry/确认、错误、session restore、job feedback、App Status popover；Browser e2e 覆盖导入后银行明细和成本统计 normal GET 结果，不等待页面 freshness 或 operation barrier。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_import_formalization_api.py`、`tests/test_workbench_v2_api.py`、`web/src/test/ImportCenterPage.test.tsx`、`web/e2e/imports-bank-transactions-flow.spec.ts` | 覆盖 preview -> confirm -> persisted import、stale preview 和错误回滚；confirm 返回空页面 targets，随后银行明细与成本统计 direct API 显示导入事实。 |
| 7. Existing feature regression tests | 适用 | `tests/test_import_file_service.py`、`tests/test_workbench_v2_api.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_platform_runtime_boundary_guards.py`、`web/src/test/ImportCenterPage.test.tsx`、`web/e2e/imports-bank-transactions-flow.spec.ts` | 覆盖旧 JSON import 兼容、文件导入、发票/ETC 共享工作流、损坏文件 file-level error、下游页面 refresh、preview stale、confirm 失败、旧 wrapper 删除防回归，以及冲突确认弹窗取消不提交、成功提交后不会继续挡住导航。 |

## 历史 Bug 回归库

| 来源 | 回归点 | 当前状态 |
| --- | --- | --- |
| Preview stale | 预览后底层记录变化，确认必须拒绝并提示重新预览 | covered |
| 银行账号映射冲突 | 用户选择银行与文件识别账号不一致时必须展示冲突，别名/简称/法定名称不能误报 | covered |
| 损坏文件 | 单个损坏 Excel 不能中断整批预览；Browser 必须显示 file-level error，且 confirm 只提交正常文件 ID。 | covered |
| 慢预览/大文件耗时 | 预览请求未完成时按钮必须显示“预览中...”，预览/清空/确认全部禁用，不能重复提交 preview 或中断成半状态。 | covered |
| 原始文本列 | 银行流水导入必须保留摘要、备注、用途等原始文本列，不影响 identity | covered |
| 银行官方表头变化 | 明确别名（含单位、半角/全角符号）归一为 canonical 字段；未知核心列要求人工映射，禁止模糊猜列。相同表头签名复用已确认映射。 | fixed 2026-08-08 |
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
| 2026-08-11 生产重复删除授权漂移 | dry-run/execute 必须显式绑定精确重复删除数；候选数变化时在关系撤回、标签清理和流水删除前失败，并在 dry-run 输出官方参考号或余额/币种的逐对证据。 | fixed by `tests/test_bank_import_dedup_repair_service.py`、`tests/test_import_audit_repair_ops.py` |
| 2026-08-12 普通确认放行弱指纹疑似流水 | `suspected_duplicate` 在 confirm 后必须保持未写入，batch 为 `completed_with_errors`；受控恢复必须同时匹配固定修复原因、来源 row、同一 keeper 和精确计数，二次重放零新增。 | fixed by `tests/test_import_service.py`、`tests/test_import_file_service.py`、`tests/test_runtime_worker.py`、`tests/test_bank_import_dedup_repair_service.py`、`tests/test_import_audit_repair_ops.py` |
| 2026-08-12 受控重放文件无 object link、审计误判与历史计数漂移 | 重放必须生成并登记独立归档对象；source identity 漂移只有在登记受控 reason 和 statement-position 六字段完全一致时可引用旧 canonical；历史 link/count 修复必须唯一 hash/URI/lifecycle、精确 action count、fingerprint、serializable lock 和 CAS。 | fixed by `tests/test_import_file_service.py`、`tests/test_audit_bank_transaction_import_page.py`、`tests/test_bank_import_audit_contract_repair.py`、`tests/test_import_audit_repair_ops.py` |

## 关键 Smoke Flows

1. 上传银行流水 XLS/XLSX -> 为每个文件选择银行账户 -> 自动归一成功，或对缺失 canonical 字段完成一次人工映射 retry -> 展示 audit counts、重复组和跳过明细；240 行合成重复组本地回归只允许一个 confirmable representative。
2. 预览后底层数据变化 -> 确认返回 `preview_stale` -> 前端提示重新预览，不创建导入 job，不调用 operation barrier 或 Workbench 页面 API。
3. 确认可导入银行流水文件 -> 创建 background `file_import` job，`affected_domains=["imports_bank_transactions"]`、`route="/imports/bank-transactions"` -> import worker event -> worker confirm -> 必要的 Workbench matching 领域任务；银行明细下一次 canonical GET 读取新事实，关联台经 `workbench` freshness gate/worker 读取新 active generation。
4. 损坏文件 + 正常文件混合上传 -> 损坏文件显示 file-level error 和未导入项明细 -> 正常文件仍可确认，confirm body 只包含正常文件 ID。
5. 导入完成后进入银行明细和成本统计，确认 normal canonical GET 直接返回新账户余额、导入行和成本证据，响应不含页面 freshness/status/job 字段。
6. Staging write-flow audit：真实银行流水确认后运行 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed bash scripts/verify.sh infra-smoke`，必须证明退休页面 refresh/dirty delta 为零；随后对银行明细、账户余额、关联台和成本统计执行只读结果与延迟验证。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_import_api \
  tests.test_import_service \
  tests.test_import_file_service \
  tests.test_import_file_api \
  tests.test_import_preview_audit \
  tests.test_import_job_queue \
  tests.test_import_audit_repair_ops \
  tests.test_import_formalization_api \
  tests.test_derived_data_lifecycle_service \
  tests.test_runtime_worker_registry \
  tests.test_app_status_overview_service \
  tests.test_bank_details_canonical_query \
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

该命令证明银行导入后退休页面 `*.read_model.refresh`、dirty scope 和 barrier target 为零；它不替代账户余额/银行明细 canonical API 页面 smoke，也不替代真实大文件 preview/confirm smoke。

## Nightly CI 覆盖

Nightly CI 通过 `scripts/verify.sh all` 执行后端、前端、Playwright browser smoke 和文档校验。Browser smoke 当前包含 `web/e2e/imports-bank-transactions-flow.spec.ts` 和 `web/e2e/permissions-role-matrix.spec.ts`，保护银行流水导入主链、零页面 barrier、银行明细/成本统计 direct read 和 read-only 权限。

## 未测风险

- 加密/损坏/超大 Excel、边界编码和完全无法定位表头的文件仍需 staging smoke；未知字段会要求人工映射而不会自动猜测。两份用户提供的建行 `.xls` 已纳入发布前/生产 preview smoke，分别应得到 6/24 行且文件级 `error_count=0`。
- 本地已覆盖 240 行合成 ICBC 重复组；它不替代真实银行多模板、加密文件、异常编码、超大 Excel 内存/耗时和历史生产样本 smoke。
- 真实 PostgreSQL + RabbitMQ + Redis + systemd import worker drain、job retry、worker crash/restart、幂等重复确认仍需环境验证；`write_operation_slo_audit --operation bank_import_confirmed` 已有本地契约测试，并要求真实银行确认样本产生 recent `bank_account_balance` outbox rows，但仍需要 staging 中真实 recent outbox rows 和账户余额 API fresh gate 证据。
- 下游页面最终展示依赖银行明细、成本统计等模块自己的 canonical query，以及关联台 active-generation 回归；本模块 Browser e2e 已覆盖银行明细小样本导入行和成本统计证据，不覆盖真实生产大数据延迟或关联台完整分组。

## 2026-07-15 import row owner 回归

- `tests/test_import_file_service.py`：batch-scoped row id 不再依赖进程级 counter。
- `tests/test_postgres_repositories_core.py`：同一 row id 若已属于其它 batch，repository fail closed，不重挂 owner。
- `tests/test_import_audit_repair_ops.py`：registered file evidence + canonical owner 恢复、重复执行幂等、legacy row id/owner 冲突拒绝。

## 2026-07-22 Phase 27 写后零 fan-out 回归

- `tests/test_import_processing_service.py`、`tests/test_import_file_api.py`：confirm 仍原子提交精确 import delta、幂等/失败回滚和必要领域任务，但结果中的页面 `freshness_targets` / `operation_barrier_targets` 为空，且不发布 read-model refresh。
- `web/src/test/ImportCenterPage.test.tsx` 与共享 `ImportWorkflowPage` 回归：普通完成反馈不等待跨页面 barrier；后续访问银行明细等页面时执行 normal canonical GET。
- 旧的 `write_operation_slo_audit` “确认后必须产生下游 refresh 事件”断言不再是本模块正确性合同；Phase 27-07 改为验证写延迟、零 fan-out 和逐页面访问收敛延迟。
## 2026-08-10 视觉回归

- `web/src/test/ImportCenterPage.test.tsx` 保护共享导入汇总、文件/问题/冲突行及银行流水导入交互；后端导入合同测试保持不变。

## 2026-08-11 预览生命周期回归

- `tests/test_import_lifecycle_service.py` 覆盖统一状态、可恢复会话聚合、owner 校验和原子 discard。
- `tests/test_import_file_service.py`、`tests/test_import_file_api.py`、`web/src/test/ImportCenterPage.test.tsx` 共同保护 preview -> recover/discard 以及 preview -> durable confirm 两条互斥路径。

## 2026-08-11 候选版本死信恢复回归

- `tests/test_import_audit_repair_ops.py` 证明恢复只接受完整 job/event/background job/session/file 白名单、已知唯一键错误（或该精确恢复的 `preview_stale` 中止态）、untouched 且可正式确认的 bank preview（含仅有弱指纹疑似重复的 `preview_ready_with_errors`）和零 canonical 写入，并在正式确认前用归档原文件重新预览。
- 候选 processor 处理完成后必须先证明 import/background job、batch/file 和 canonical transaction 计数闭环，才 resolve 原 dead letter；不完整结果保留死信。
- 只读 recovery discovery 必须从一个明确 failed import job 推导唯一 event/background job/session/file target；多个 dead letter、缺失坐标或不完整 preview 必须 fail closed。

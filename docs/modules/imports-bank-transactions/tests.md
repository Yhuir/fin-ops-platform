# 银行流水导入 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 需要保护的行为 | 当前测试入口 |
| --- | --- | --- |
| 前端页面/共享工作流 | 独立路由、银行账户映射加载、每文件银行选择、预览、确认、preview stale 错误、session restore、视觉/CSS 契约 | `web/src/test/ImportCenterPage.test.tsx` |
| 前端 API mapper | multipart `file_overrides`、Authorization/credentials、session/confirm/retry/fetch、duplicate groups、skipped rows、preview stale message | `web/src/test/ImportsApi.test.ts` |
| 文件预览 API | 损坏 Excel、模板识别、银行流水模板、per-file override、银行选择冲突、只确认 selected files | `tests/test_import_file_api.py` |
| 文件预览 service | 文件级错误、session/file/batch id 去重、银行映射冲突与别名、preview stale、真实银行流水模板 | `tests/test_import_file_service.py` |
| 银行流水 parser/normalizer | 原始文本列、真实 Excel text contract、银行流水 identity、不改 identity 的文本字段 | `tests/test_import_api.py`、`tests/test_import_service.py`、`tests/test_import_preview_audit.py` |
| 确认/持久化 | confirm 持久化、重复跳过、selected bank mapping 字段保留、导入跨重启持久化、batch revert/download | `tests/test_import_service.py`、`tests/test_import_formalization_api.py` |
| Import worker / queue | idempotency key、small RabbitMQ envelope、unknown processor failure、registered processor success、worker check、RabbitMQ confirm queue | `tests/test_import_job_queue.py`、`tests/test_runtime_worker_registry.py` |
| 下游 fan-out | bank import confirmed -> bank detail/balance、Workbench/relation/matching、invoice lifecycle、cost/search | `tests/test_derived_data_lifecycle_service.py`、`tests/test_workbench_v2_api.py`、`tests/test_bank_account_balance_read_model.py`、`tests/test_bank_details_sql_runtime.py` |
| App Status/App Health | imports bank domain route、import worker/job、file import explicit affected domain、global status plane | `tests/test_app_status_overview_service.py`、`web/src/test/AppStatusIndicator.test.tsx` |

## 关键场景覆盖

| 场景 | 当前状态 | 保护入口 |
| --- | --- | --- |
| 银行导入独立路由使用共享 `ImportWorkflowPage`，每个文件发送银行映射 override | covered | `bank transaction import uses the standalone route and sends bank mapping overrides`、`ImportsApi.test.ts` |
| 页面展示 preview audit counts 和确认文案 | covered | `bank transaction import displays preview audit counts and confirm copy` |
| 前端把 `preview_stale` 映射为“重新预览”提示 | covered | `file import confirm maps preview_stale to the refresh preview message` |
| 损坏文件作为文件级错误，不中断整批预览 | covered | `test_preview_files_keeps_corrupt_excel_as_file_level_error_without_aborting_batch`、`test_preview_marks_corrupt_excel_as_file_level_error_instead_of_raising` |
| 银行流水模板识别与真实银行 Excel 文本字段保留 | covered | `test_preview_files_recognizes_bank_statement_templates`、`test_bank_file_parsers_preserve_real_excel_text_field_contracts` |
| 选择银行映射持久化，检测账号冲突，银行别名/简称/法定名称不误报 | covered | `test_preview_persists_selected_bank_mapping_and_marks_conflict_against_detected_account`、`test_preview_does_not_mark_bank_*_as_conflict_when_last4_matches` |
| preview stale 时拒绝 confirm | covered | `test_confirm_session_rejects_stale_preview_when_existing_records_change`、`test_import_file_confirm_returns_preview_stale_when_existing_records_change` |
| confirm 只导入 selected files | covered | `test_confirm_files_imports_only_selected_files_from_session` |
| RabbitMQ/import worker 模式下 confirm 入队并可被 import processor 执行 | covered | `test_general_import_confirm_queues_import_job_in_rabbitmq_mode`、`test_application_import_processor_registry_runs_general_import_confirm` |
| 银行导入确认后 Workbench read model invalidated | covered | `test_bank_import_confirm_invalidates_workbench_read_model` |
| bank import lifecycle fan-out 到银行明细/账户余额、Workbench、relation、matching、invoice lifecycle、cost/search | covered | `test_bank_import_confirmed_maps_workbench_candidate_cost_and_search_domains` |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_import_service.py`、`tests/test_import_api.py`、`tests/test_import_preview_audit.py` | 覆盖银行流水 direction、金额、identity、重复/疑似重复、缺失秒级时间、账号维度唯一键、原始文本字段。 |
| 2. Service-layer tests | 适用 | `tests/test_import_file_service.py`、`tests/test_import_job_queue.py`、`tests/test_import_formalization_api.py` | 覆盖 session/file/batch 生命周期、preview stale、confirm 持久化、job idempotency、worker processor。 |
| 3. API contract tests | 适用 | `tests/test_import_file_api.py`、`tests/test_import_api.py`、`web/src/test/ImportsApi.test.ts` | 覆盖 `/imports/files/preview`、`confirm`、`retry`、`sessions`、legacy preview/confirm、错误 shape 和 mapper。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_import_job_queue.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_bank_account_balance_read_model.py`、`tests/test_bank_details_sql_runtime.py`、`tests/test_app_status_overview_service.py` | 覆盖 import worker、dirty fan-out、银行余额/明细 projection、App Status。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/ImportCenterPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx` | 覆盖独立路由、上传/预览/确认、错误、session restore、job feedback、App Status popover。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_import_formalization_api.py`、`tests/test_workbench_v2_api.py`、`web/src/test/ImportCenterPage.test.tsx` | 覆盖 preview -> confirm -> persisted import -> Workbench refresh / stale preview；真实 worker drain 仍是 documented-risk。 |
| 7. Existing feature regression tests | 适用 | `tests/test_import_file_service.py`、`tests/test_workbench_v2_api.py`、`tests/test_derived_data_lifecycle_service.py`、`web/src/test/ImportCenterPage.test.tsx` | 覆盖旧 JSON import、文件导入、发票/ETC 共享工作流、下游页面 refresh 和 preview stale。 |

## 历史 Bug 回归库

| 来源 | 回归点 | 当前状态 |
| --- | --- | --- |
| Preview stale | 预览后底层记录变化，确认必须拒绝并提示重新预览 | covered |
| 银行账号映射冲突 | 用户选择银行与文件识别账号不一致时必须展示冲突，别名/简称/法定名称不能误报 | covered |
| 损坏文件 | 单个损坏 Excel 不能中断整批预览 | covered |
| 原始文本列 | 银行流水导入必须保留摘要、备注、用途等原始文本列，不影响 identity | covered |
| RabbitMQ confirm | 异步 confirm 只能传小 envelope，processor 由 worker 拉取事实 | covered |
| App Status job mapping | `imports_bank_transactions` domain 声明 `import.process.requested`，但 job registry 的该 job 当前只映射 `imports_invoices` | P1 documented-risk |

## 关键 Smoke Flows

1. 上传银行流水 XLS/XLSX -> 为每个文件选择银行账户 -> 预览成功 -> 展示 audit counts、重复组和跳过明细。
2. 预览后底层数据变化 -> 确认返回 `preview_stale` -> 前端提示重新预览，不创建导入 job。
3. 确认可导入文件 -> 创建 background `file_import` job / import worker event -> worker confirm -> Workbench matching 入队 -> 银行明细和关联台后续 fresh。
4. 损坏文件 + 正常文件混合上传 -> 损坏文件显示 file-level error -> 正常文件仍可确认。
5. 导入完成后进入银行明细和关联台，确认 `bank_detail`、`bank_account_balance`、`workbench` / `workbench_relation` 不显示 stale 为 fresh。

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
  tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_import_file_confirm_returns_preview_stale_when_existing_records_change \
  tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_bank_import_confirm_invalidates_workbench_read_model \
  -v

cd web && npm test -- --run \
  src/test/ImportsApi.test.ts \
  src/test/ImportCenterPage.test.tsx \
  src/test/AppStatusIndicator.test.tsx

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

Nightly CI 通过 `scripts/verify.sh` 执行后端、前端和文档校验。银行流水导入变更优先运行本模块窄范围命令；如果改动触及共享 `ImportWorkflowPage`，还要同时评估 `imports-invoices` 和 `imports-etc-invoices` 模块测试。

## 未测风险

- 真实银行多模板大文件、加密/损坏/超大 Excel、边界编码和历史生产文件样本仍需 staging smoke。
- 真实 PostgreSQL + RabbitMQ + Redis + systemd import worker drain、job retry、worker crash/restart、幂等重复确认仍需环境验证。
- `import.process.requested` 在 App Status background job registry 当前只映射 `imports_invoices`，但 `imports_bank_transactions` domain 也声明该 job type；本轮记录为 P1 documented-risk，后续改 App Status 时应补 job affected domain 回归。
- 下游页面最终展示依赖银行明细、关联台、成本统计等模块自己的 fresh/read model 回归；本模块只证明 fan-out 入口和关键 contract。

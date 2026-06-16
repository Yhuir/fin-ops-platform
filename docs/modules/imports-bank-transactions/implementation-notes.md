# 银行流水导入 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 银行流水导入页面复用 `ImportWorkflowPage`，业务差异通过 `mode="bank_transaction"` 和 per-file bank mapping overrides 表达。
- 新页面路径使用 `/imports/files/preview`、`/imports/files/confirm`、`/imports/files/sessions/{session_id}`；legacy `/imports/preview`、`/imports/confirm` 仍作为旧 API/程序化导入回归入口。
- preview 是可失效的临时判断；confirm 前必须通过后端 `assert_session_preview_current` 防 stale。
- confirm 是异步导入动作；返回 `job` / `import_job` 只能说明已开始处理，不能说明银行明细、关联台、成本统计等下游已 fresh。
- 银行导入的跨页一致性以后端 lifecycle、dirty scope、read model worker 和 App Status 为准，前端只展示 job feedback 和刷新提示。

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

## 2026-06-16 - 银行流水导入合成大重复组守护

- 目标：为 P2/P3 大文件导入风险补本地可重复证据，避免银行流水同文件大重复组在 preview audit 中被全部当作可确认行。
- 影响范围：`FileImportService.preview_files`、ICBC Excel parser、import preview duplicate audit、银行流水导入测试矩阵。
- 关键决策：不改导入行为；使用 240 行合成 ICBC Excel fixture 锁定当前 contract：同一稳定 identity 只产生一个 confirmable representative，其余 239 行进入同文件重复组和 skipped count。
- 文档影响：更新 `tests.md` 的关键场景、历史 bug 回归和未测风险；P2/P3 台账记录为 local synthetic evidence。
- 测试覆盖：新增 `test_preview_bounds_large_bank_duplicate_group_to_one_confirmable_row`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service.ImportFileServiceTests.test_preview_bounds_large_bank_duplicate_group_to_one_confirmable_row -v`；本轮也与发票/ETC 合成导入测试一起运行通过。
- 未测风险：真实银行多模板大文件、加密/损坏 Excel、异常编码、历史生产样本、真实 worker drain 和浏览器上传耗时仍需 staging/manual smoke。
- 后续事项：拿到用户批准的真实银行样本后，在 staging 跑文件 preview/confirm/job/read-model smoke，不在本地 fixture 中保存真实业务文件。

## 2026-06-16 - 银行流水导入 App Status job 域修复

- 目标：修复银行流水文件确认后 `file_import` background job 在 App Status 中误归到发票导入页的风险。
- 影响范围：`/imports/files/confirm` 创建 background job 的 `source.affected_domains` / `source.route`，以及 `file_import` / `import.process.requested` generic registry fallback。
- 关键决策：精确场景由 confirm route 根据 selected files 的 `BatchType` 写入具体 domain 和 route；generic fallback 覆盖全部导入域并跳转 App Health，避免无 source 旧 job 误指某一个导入页。
- 文档影响：更新 `tests.md` 的历史 bug 回归库、关键 smoke flow 和 App Status 影响面；`state-machine.md` 记录 queued 状态的 domain contract。
- 测试覆盖：新增 `test_confirm_bank_transaction_file_job_reports_bank_import_domain`、`test_generic_import_job_defaults_cover_all_import_domains_without_wrong_invoice_route`、`test_background_job_registry_file_import_default_does_not_point_bank_import_to_invoice_page`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_api.ImportFileApiTests.test_confirm_bank_transaction_file_job_reports_bank_import_domain tests.test_app_status_overview_service.AppStatusRuntimeRepositoryTests.test_generic_import_job_defaults_cover_all_import_domains_without_wrong_invoice_route tests.test_app_status_overview_service.AppStatusRuntimeRepositoryTests.test_background_job_registry_file_import_default_does_not_point_bank_import_to_invoice_page -v`；模块后端 181 tests；前端导入/App Status 27 tests。
- 未测风险：真实 import worker/RabbitMQ/Redis/systemd drain 与生产历史 job source 仍需 staging/生产 smoke。
- 后续事项：共享导入新增 batch type 时必须同步 file import domain mapping、App Status registry 和前端 route。

## 2026-06-11 - 首轮测试闭环文档化

- 目标：用 CodeGraph 审计银行流水导入页面、共享导入组件、API mapper、后端 import endpoints、service/job queue、parser/normalizer/persistence、dirty scope/lifecycle、App Status 和测试入口。
- 影响范围：`ImportBankTransactionsPage`、`ImportWorkflowPage`、`imports/api.ts`、`FileImportService`、`ImportNormalizationService`、`ImportProcessingService`、`ImportJobRepository`、`ImportJobWorker`、`DerivedDataLifecycleService`、App Status domain/job registry、银行明细/账户余额/Workbench 下游 read models。
- 关键决策：确认导入必须防 stale 和幂等；单文件错误不能中断整批 preview；导入 job 只代表后台处理状态；下游 fresh 必须由对应 read model/worker 证明。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`，并在全局测试闭环依赖地图中补充 imports-bank-transactions 细化。
- 测试覆盖：后端 import service/API/job queue/lifecycle/read model/App Status tests 覆盖核心链路；前端 `ImportCenterPage.test.tsx` 与 `ImportsApi.test.ts` 覆盖页面和 API mapper。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_import_api tests.test_import_service tests.test_import_file_service tests.test_import_file_api tests.test_import_preview_audit tests.test_import_job_queue tests.test_import_formalization_api tests.test_derived_data_lifecycle_service tests.test_runtime_worker_registry tests.test_app_status_overview_service tests.test_bank_account_balance_read_model tests.test_bank_details_sql_runtime tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_import_file_confirm_returns_preview_stale_when_existing_records_change tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_bank_import_confirm_invalidates_workbench_read_model -v`
  - `cd web && npm test -- --run src/test/ImportsApi.test.ts src/test/ImportCenterPage.test.tsx src/test/AppStatusIndicator.test.tsx`
  - `bash scripts/verify.sh docs`
- 未测风险：真实银行大文件/历史模板、真实 Postgres/RabbitMQ/Redis/systemd import worker drain、worker crash/retry、下游最终页面展示仍需 staging/发布前 smoke；`import.process.requested` App Status job affected domain 与银行导入 domain 声明存在 P1 文档化风险。
- 后续事项：若修改共享 `ImportWorkflowPage` 或 `/imports/files/*` contract，必须同时评估 `imports-invoices` 与 `imports-etc-invoices`。

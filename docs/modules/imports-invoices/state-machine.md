# 发票导入状态与恢复

## 当前执行合同（2026-09-21）

导入执行的唯一事实源是 `job.import_jobs`。上传完成只说明原件和草稿登记完成；prepare 完成只说明逐项预览可读；正式 facts、来源、批次行和 job 成功必须在一个数据库事务中提交。

| 阶段/状态 | 含义 | 用户操作 |
| --- | --- | --- |
| `prepare / pending` | 原件和 session 已登记，等待解析 | 查看进度；可以离开页面 |
| `prepare / processing` | worker 读取已归档原件并解析 | 等待同一任务，禁止猜测导入成功 |
| `awaiting_confirmation` | 预览已持久化，正式事实未写入 | 查看逐项新增/重复/错误，选择本次范围 |
| `needs_review` | 字段、身份、财务或预览版本发生需复核的问题 | 修改映射/选择并重新预览 |
| `commit / pending` | 已确认的精确选择范围待执行 | 重复确认返回同一意图 |
| `commit / processing` | 短业务事务正式提交 | 查询同一任务；取消与提交由事务判定 |
| `succeeded` | 正式数据与结果已一并提交 | 显示实际新增/更新/重复数量 |
| `failed` | 无成功结果；错误和重试范围可读 | 可恢复故障重试原意图；业务冲突重新复核 |
| `canceled` | 确认的取消已生效 | 不将取消误报为导入成功 |

文件/session 的 `uploaded / preview_ready / preview_ready_with_errors / confirmed` 仅描述原件和预览业务状态，不再另设 background job 执行事实。未选择文件保留 `preview_ready`，不能被其它文件成功标成 confirmed 或 skipped。一个选择范围内有错误/疑似行时，整个范围不写事实；正常重复不是错误。

确认时复核只加载当前 session 的批次和相关身份候选。同一强身份刚被别的导入合法创建，可以转为重复并返回实际计数；身份指向漂移、财务冲突或扩大写集仍需复核。worker 在业务写入前锁定任务的领取者和 claim version；旧进程不可提交。失败后从持久化草稿恢复，不从旧进程全量状态补写。

## 不允许的旧路径

- 不按已确认文件 SHA 拒绝整文件；每次主动重传都按业务项比较当前池。
- 不创建导入专用 `import.process.requested` 事件，不使用双租约或第二份 background job 结果。
- 不把 valid 行先提交、error 行跳过后显示整批成功。
- 不在预览、清理草稿、较小的全量文件或文件删除时删除 canonical 事实。
- 不将下游页面刷新任务当作事实提交成功的前提。页面按其 owner 的 canonical 查询读取；必要匹配任务保留既有边界。

## 验证

`tests/test_import_closed_loop.py` 覆盖注册不解析、跨进程草稿恢复、原子选择范围、未选择文件、真实 PostgreSQL 提交/回滚/领取版本隔离。解析与计数见 `test_import_file_service.py`、`test_import_service.py`、`test_import_preview_audit.py`；API/页面/worker 回归由各 owner 维护。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-08-20 | suspected duplicate 候选引用只保留到 preview | confirm 后 terminal suspected row 清空非权威 invoice 引用；created、status_updated、duplicate_skipped 保持正式引用 | `tests/test_import_service.py` |
| 2026-08-14 | 新增单张发票人工录入并删除待找发票旧写链 | 可选附件识别只预填；服务端预览、重复校验、红蓝字金额和普通 confirm job 形成单一闭环；不自动绑定银行流水 | `tests/test_manual_invoice_entry_service.py`、`tests/test_import_file_api.py`、`web/src/test/ManualInvoiceEntryDrawer.test.tsx`、`web/src/test/ImportCenterPage.test.tsx` |
| 2026-09-01 | 导入页面每次进入 fresh，并保留显式放弃 | 删除浏览器/活跃 session 自动恢复；放弃当前 preview 仍走 durable owner/discard 合同，确认链继续复用既有 durable job/outbox | `tests/test_import_lifecycle_service.py`、`test_preview_session_can_be_discarded_before_confirm`、`ImportCenterPage.test.tsx` |
| 2026-08-11 | 放弃状态 formal payload 原子闭环 | batch/file/session 的 canonical 列与 normalized payload 同时进入 `reverted`；历史精确 mismatch 通过指纹绑定工具修复，不扫描 canonical 发票 | `tests/test_import_lifecycle_service.py`、`tests/test_audit_invoice_import_page.py`、`tests/test_import_audit_repair_ops.py` |
| 2026-07-22 | preview 持久化收窄为 session-scoped exact delta | stale API 后续预览不能覆盖另一进程已确认的 file/session/batch；batch 与 file/session 同事务提交 | `test_stale_api_preview_cannot_downgrade_another_process_confirmed_import`、`test_save_import_delta_rolls_back_batch_when_file_write_fails` |
| 2026-06-16 | 补齐发票确认 job 的 App Status domain/route contract | `file_import` 发票确认不再落到泛化导入页面，跨页状态反馈可回到 `/imports/invoices`；共享 `import.process.requested` 仍作为多导入域兜底 | `tests/test_import_file_api.py::ImportFileApiTests::test_confirm_files_imports_only_selected_files_from_session`、`tests/test_app_status_overview_service.py`、`web/src/test/AppStatusIndicator.test.tsx` |
| 2026-06-11 | 首轮补齐发票导入状态机 | 明确 file/session/job/lifecycle/read model 状态边界 | `tests/test_import_*`、`web/src/test/ImportCenterPage.test.tsx`、`bash scripts/verify.sh docs` |

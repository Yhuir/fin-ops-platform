# 银行流水导入状态与恢复

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

- 2026-08-14：新增 `completed -> withdrawn` 管理员纠错流转；只允许纯新增且可证明 owner 的银行批次。撤回在同一事务内处理 relation/current state、canonical 流水、lifecycle 与审计，重复请求幂等。

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-08-28 | 银行流水手工多笔录入 | 新增有界表单预览入口，复用 file/session confirm durable job；批量 identity preload，重复不进入可确认列表，不新增 canonical 写链 | `tests/test_manual_bank_transaction_entry_service.py`、`tests/test_import_file_api.py`、`web/src/test/ManualBankTransactionBatchEditor.test.tsx`、`web/src/test/ImportsApi.test.ts` |
| 2026-08-22 | 零新增预览语义闭环 | 全部银行流水已存在时不再显示“待确认”或创建零变更 job；混合文件只提交实际可处理文件，判重/API/数据库合同不变 | `ImportCenterPage.test.tsx`、`imports-bank-transactions-flow.spec.ts` |
| 2026-08-20 | 弱指纹终态引用与历史审计合同闭环 | confirm 仅在 preview 保留候选证据，terminal suspected row 清空 canonical 引用；历史正式银行行通过 exact-count/fingerprint/CAS 工具定点 unlink，不触碰 canonical 流水 | `tests/test_import_service.py`、`tests/test_bank_import_audit_contract_repair.py`、`tests/test_import_audit_repair_ops.py` |
| 2026-08-11 | 服务端恢复、owner 隔离和显式放弃闭环 | 预览不再依赖单一浏览器 key；AppHealth 可区分待确认、队列、处理、完成、失败和放弃 | `tests/test_import_lifecycle_service.py`、`tests/test_import_file_api.py`、`web/src/test/ImportCenterPage.test.tsx` |
| 2026-08-12 | 关闭普通 confirm 的弱指纹放行，并收紧生产受控重放 | 疑似流水不再被确认写入；受控重放只接受固定修复原因和同一 keeper 证据 | `tests/test_import_service.py`、`tests/test_import_file_service.py`、`tests/test_bank_import_dedup_repair_service.py`、`tests/test_import_audit_repair_ops.py` |
| 2026-08-12 | 补齐现存 canonical owner 的受控重放证据 | 恢复 cohort 中仍合法存在的 created owner 按文件、行号、指纹和 canonical ID 冻结；弱身份重放只可跳过到该 owner，真正缺失行仍走正常创建 | `tests/test_import_file_service.py`、`tests/test_bank_import_dedup_repair_service.py`、`tests/test_import_audit_repair_ops.py` |
| 2026-08-12 | 补齐既有 canonical duplicate reference 的受控重放证据 | 历史已判重行按文件、行号、指纹和修复后仍保留的 canonical ID 冻结；禁止引用本次待删除事实，避免重放产生悬空关系 | `tests/test_import_file_service.py`、`tests/test_bank_import_dedup_repair_service.py`、`tests/test_import_audit_repair_ops.py` |
| 2026-08-11 | 候选版本定点恢复旧 background snapshot 污染产生的银行导入死信 | 只对白名单 job/event/session/files 做 dry-run fingerprint 验真；先完成 canonical 导入再 resolve 精确死信 | `tests/test_import_audit_repair_ops.py` |
| 2026-08-08 | 银行表头统一为 canonical 字段解析与人工映射闭环 | 删除按银行 exact-header 分支；兼容元数据账号、单位/括号差异，未知核心字段 fail closed 并可按表头签名复用人工映射 | `test_ccb_current_export_header_uses_metadata_account_and_unit_aliases`、`test_manual_mapping_is_reused_for_same_header_signature`、`bank transaction import maps an unknown amount header and retries the same file` |
| 2026-07-22 | preview 持久化改为 session-scoped exact delta | 银行预览不再携带历史 session/batch，避免跨导入域 stale snapshot 丢失更新 | `test_preview_session_persistence_payload_excludes_unrelated_sessions_and_canonical_facts`、`test_stale_api_preview_cannot_downgrade_another_process_confirmed_import` |
| 2026-06-11 | 首轮测试闭环状态机补齐 | 明确文件/session/job/worker/read model 状态和禁止流转 | `tests/test_import_*`、`tests/test_import_job_queue.py`、`web/src/test/ImportCenterPage.test.tsx` |
| 2026-06-16 | 修复银行流水导入 job 的 App Status 域 | 银行流水文件确认后的 background job 不再误归到发票导入页；generic import fallback 覆盖全部导入域 | `tests.test_import_file_api`、`tests.test_app_status_overview_service` |
| 2026-07-05 | 模块边界 close 与旧 wrapper 删除 | 银行流水页面 file/session 状态机锁定；`server.py` 不再保留 import confirm processor wrapper | `tests.test_platform_runtime_boundary_guards` |

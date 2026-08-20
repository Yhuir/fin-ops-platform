# 银行流水导入 实施记录

## 2026-08-20 - terminal suspected canonical 引用闭环

- 根因：去重 preview 会为弱/多义命中保留 candidate ID；普通 confirm 已不创建 canonical 流水，但旧终态序列化仍把 transient candidate 写进 `app.import_batch_rows.linked_object_*` 与 normalized payload，违反 Page Audit 的 terminal decision 合同并持续制造阻断。
- 修复：共享导入确认边界在终态只对 `suspected_duplicate` 清空候选引用；created、status_updated、duplicate_skipped 保持正式引用，银行与发票不建立第二条确认链。
- 既有数据：候选 release 的银行 Audit repair planner 冻结 exact terminal bank rows，要求显式 unlink count、fingerprint、serializable advisory lock 和逐行 CAS；只清 typed/normalized link，不改 decision、reason、batch 计数或 canonical 流水。非银行、非终态、字段缺失或任何漂移整批零写。
- 不新增表、migration、API、worker、read model、fallback 或数据库备份。

## 2026-08-14 - OA-first 成本隔离更正

- 银行流水导入只新增银行事实；可以进入成本统计“按时间/按标签”，但没有完成 OA 与付款流水正式关系时，不得进入“按项目/按银行/按 OA 费用类型”。
- `web/e2e/imports-bank-transactions-flow.spec.ts` 已改为同时证明导入流水可见与 OA 项目成本不受污染。下文早期记录中“导入后直接形成项目成本证据”的表述已被本节取代。


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 2026-08-12 - legacy statement-position 重放与恢复事务原子性

- 生产事实：7 个授权附件解析出 1,100 条严格唯一流水；首次受控重放后库内为 1,101 条、1,100 个严格位置，唯一多重项是平安 0093、2026-04-16 10:51:46、支出 0.90、余额 979.57。
- 根因一：保留的历史 canonical 行没有 `bank-v4` key；重放行因官方参考号冲突生成 v4，旧决策只查 v4 key，没有用六项完整账单位置反向匹配 legacy 行，因此错建一条副本。修复后唯一六项命中判为 duplicate，多义命中判为 suspected，任一字段缺失不自动合并。
- 根因二：旧恢复 CLI 在一个事务内提交清理，再通过根连接运行自主重放；因此外层计数门禁发现“预期新增 7、实际 8”时，不能回滚已提交的重放写入。修复后清理、两轮重放、审计与 refresh outbox 都使用同一 serializable advisory-lock 事务，门禁失败不会留下半写状态。
- 生产执行补充验证发现正式回放内部 repository 仍会请求 `connection.transaction()`；repair 工具现在用窄 connection-shaped 适配器复用已经打开的事务，并保留 `PostgresTransaction` 的 psycopg JSON 参数适配契约，避免恢复旧的分段提交或向 read-model outbox 传入未适配 `dict`，同时保持普通导入 runtime 不变。
- 性能：完整 statement-position 候选通过一次 `jsonb_to_recordset` 批量查询预取，后续逐行判定只读文件级内存 cache，不增加 N+1 SQL。
- 数据修复：只允许通过原 source session/file 的 `import-audit-repair --repair-bank-source` dry-run + fingerprint + CAS 门禁删除该一条错建副本，重放必须零新增；禁止手工 SQL 扩大清理范围。

## 2026-08-12 - statement-position 重放判重与错误引用释放

- 根因：官方参考号复用后首次导入可生成 `bank-v4` statement-position identity，但同一位置再次导入时，旧决策只检查基础 `bank-v3` 冲突，没有直接查询已经存在的 `bank-v4`，在自由文本 fingerprint 漂移时会再次判为新建。生产受控回放另有 38 条旧 canonical reference 指向六项账单证据不一致的流水，旧逻辑会无条件覆盖当前 importer decision。
- 修复：基础 identity 冲突后直接查询确定性的 statement-position canonical key；相同账单位置返回 duplicate，不同位置才创建。受控 canonical reference 在回放时重读目标并严格比较账户、时间、方向、金额、余额、币种，不一致时释放回普通 importer，目标缺失 fail closed。
- 门禁：恢复计划新增精确 released-reference count，并纳入 dry-run fingerprint、首轮重放和幂等重放；授权数不得超过 source files 实际拥有的 reference evidence。普通 confirm 的 stale gate 同时逐行比较 decision/type/id，汇总计数相同但 owner 调换仍拒绝。
- 性能与边界：正常文件仍使用单批 identity preload 和内存 cache；只在已检测到基础 canonical 冲突时追加一次 position-key 查询，不引入扫描、第二 parser、第二导入链或页面 I/O。
- 测试：`test_reused_canonical_reference_reimport_matches_existing_position_identity`、逐行 owner drift stale 回归、canonical reference 释放/缺失目标回归、CLI 精确释放计数和恢复计划上界门禁。

## 2026-08-12 - 真实附件解析、statement-position 唯一键与生产去重收口

- 真实原因：部分银行 OOXML 把 worksheet dimension 错写为 `A1`，read-only 读取会把有数据的工作表截成一个单元格；同时部分官方参考号在历史导出中复用，旧 canonical 冲突即使被 service 判定为新事实，仍会撞上 PostgreSQL `source_unique_key` 唯一索引。
- 修复：共享 XLSX reader 在逐表读取前重算维度；正常流水默认继续使用 `bank-v3`，只有基础键已存在且余额/币种证明是另一账单位置时生成确定性 `bank-v4`。preview、confirm、内存 identity cache 和最终持久化使用同一个决策 identity，禁止“service 判新建、repository 用旧键写入”的分裂合同。
- 生产恢复：历史错误 cohort 的 data fingerprint/reference 因旧 parser 漂移时，只允许秒级时间、方向、金额、余额、币种全等且一对一的 statement-position 二级匹配。账户表示不一致时，仅接受一方明确为 4 位尾号并与另一方完整账号尾号一致；两个不同完整账户即使尾号相同也不得匹配。多义、缺字段或计数漂移继续 fail closed。关系撤回、标签事件删除和重复流水删除仍受同一 dry-run fingerprint/CAS 约束。
- 测试：新增畸形 dimension 的银行/发票共享 reader 回归、累计控制字段别名、v4 键别名稳定性、基础键冲突的创建与重放判重、恢复匹配唯一/多义门禁；批量 identity 查询和旧 v2/v3 行为保持回归。

## 2026-08-11 - 银行重复清理数量授权门禁与匹配证据

- 银行 identity v3 受控恢复把 `expected_duplicate_delete_count` 提升为 dry-run/execute 的必填输入；计划解析出的删除数只要与授权数不同，就在任何关系撤回、标签清理或流水删除前失败。
- dry-run 报告输出每个候选的 delete/keeper 身份、创建/更新时间、匹配依据和官方参考号交集；execute 报告不重复输出全量 pair evidence，避免生产审计输出膨胀。
- 匹配依据只允许现有两类：官方参考号唯一相交，或官方参考号缺失时余额/币种严格唯一；该诊断只解释既有算法，不新增兼容分支或放宽去重规则。

## 2026-08-11 - 官方参考号复用、批量去重与受控生产恢复

- 真实原因：旧 `bank-v2` 把“账户 + 官方参考号”当成唯一强 identity；部分银行在同一文件内复用参考号时，不同交易被错误跳过。后续恢复导入又让已有历史流水以新 batch owner 重建，形成恢复 cohort 中的历史副本。
- 修复：新记录使用 `bank-v3`（账户 + 官方参考号 + 业务指纹摘要）；历史 v2 只在业务指纹一致且官方参考号唯一相交时判重。preview/confirm 统一一次批量 preload，并在同批创建后更新内存 cache，删除逐行 identity 查询链。
- Audit 与生产恢复使用同一迁移证据：v3 导入行引用历史 v2 canonical 时，只有业务指纹一致且双方官方参考号存在交集才视为一致；file→batch 关系兼容正式 nested payload 与既有顶层 `batch_id/preview_batch_id`，流水 batch owner 兼容 canonical UUID 与 `legacy_source_batch_id`，不依赖生产已移除的 `import_files.import_batch_id`。
- 生产恢复：显式绑定 source session/file、expected counts 和 dry-run fingerprint。工具只清理唯一匹配且零关系/零核销的错误副本；双方官方参考号存在但不相交，或新流水有官方参考号且双方非空账后余额明确不同时，保留为不同流水。只有官方参考号缺失时，才允许在本次授权 cohort 内以相同业务指纹、唯一保护候选、相同非空账后余额和币种作为严格二级恢复证据，避免把会随导出模板变化的自由文本当身份。同步修正原导入审计后通过正式 processor 重放归档文件；不扫描其它任务、不迁移关系、不修改保护流水。
- 性能：identity 读取从每行一次数据库查询收敛为每批一次 bulk query；计划构建按 data fingerprint 分桶，避免恢复集合与保护集合做笛卡尔比较。
- 测试：业务核心、service、repository、受控 replay 和旧 CLI 回归由 `test_bank_transaction_identity_service.py`、`test_object_dedup_decision_service.py`、`test_import_service.py`、`test_import_file_service.py`、`test_postgres_repositories_core.py`、`test_bank_import_dedup_repair_service.py`、`test_import_audit_repair_ops.py` 覆盖。

## 当前决策

- 银行流水导入页面复用 `ImportWorkflowPage`，业务差异通过 `mode="bank_transaction"` 和 per-file bank mapping overrides 表达。
- 页面路径唯一使用 `/imports/files/preview`、`/imports/files/confirm`、`/imports/files/sessions/{session_id}`；旧 JSON `/imports/preview`、`/imports/confirm` 及 `general_import.confirm` worker 链已于 2026-07-11 删除。
- preview 是可失效的临时判断；confirm 前必须通过后端 `assert_session_preview_current` 防 stale。
- confirm 是异步导入动作；返回 `job` / `import_job` 只能说明已开始处理，不能说明银行明细、关联台、成本统计等下游已 fresh。
- 银行导入的跨页一致性以后端 lifecycle、dirty scope、read model worker 和 App Status 为准，前端只展示 job feedback 和刷新提示。

## 2026-08-08 - canonical 表头归一与人工映射闭环

- 目标：处理银行官方 Excel 表头版本差异，同时避免维护按银行、按版本膨胀的模板集合。
- 关键决策：保留单一 `bank_statement` parser；前 60 行有界定位表头，NFKC/空白/单位/括号归一后只匹配明确 alias。核心字段不完整则 fail closed，由页面提交字段映射；相同表头签名从既有 import file audit payload 复用最近一次人工映射。
- 删除项：六套银行 exact-header template definition、detector 分支和 parser 分支；不保留兼容 fallback，不新增模板表、worker 或 read model。
- 测试覆盖：现有六家银行 fixture、建行 `/元` 半角括号与元数据账号、未知字段人工 retry/持久化复用、API 嵌套 mapping 和 HeroUI 交互。
- 未测风险：加密/损坏/超大文件与完全无表头线索的文件仍需人工处理；系统不会为追求“全自动”猜测金额或方向。

## 2026-08-01 - import batch rows 批量 upsert

- 活动 `save_import_delta` 链路中的 `import_batch_rows` 从逐行 execute 改为复用现有 `execute_many_values` bounded chunk；`ON CONFLICT` owner guard、事务回滚、审计 payload 和 canonical delta 不变。
- repository 测试证明两行只发生一次批量调用，并继续覆盖跨 batch re-parent 拒绝和 batch/file 任一失败整体回滚。

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

## 2026-07-22 - preview session-scoped delta

- 目标：防止银行流水 preview/retry 的 stale API 内存覆盖其它进程已确认的发票或银行导入状态。
- 关键决策：共享 preview writer 只接收当前 `session_id`，只持久化当前 session/files/preview batches；确认链和 downstream lifecycle 不变。
- 测试覆盖：精确 payload、发票确认后 stale API 继续预览银行文件的跨进程回归、PostgreSQL 原子回滚和旧路径 guard。

## 2026-07-11 - direct-canonical Audit 与旧 JSON 写入链删除

- 目标：证明全部已登记 bank file/session/batch/row/canonical transaction 与当前 import job/outbox 闭包，并删除并行 HTTP 写入合同。
- 关键决策：页面无 own read model、不消费配对关系；下游 bank detail、account balance、Workbench、cost、search 仅是 impact targets。App 文件 hash 不替代银行外部 control evidence。
- 删除项：`/imports/preview`、`/imports/confirm` route/handler/entrypoint，`general_import.confirm` producer/processor/check registry，以及只服务旧 confirm 的 preview scope dependencies和旧 HTTP 回归。
- 保留项：`ImportNormalizationService.preview_import/confirm_import` 领域端口和 `FileImportService.snapshot/from_snapshot` worker 恢复端口。
- 验证：全迁移 disposable PostgreSQL clean pass；金额漂移、hash 缺失、canonical transaction 删除、active/terminal job/outbox 均 fail closed；旧 URL 只允许存在于 404/边界 guard。

## 2026-07-05 - 银行流水导入边界 close 与旧 wrapper 删除

- 目标：完成银行流水导入模块边界与 I/O 收口，确认页面主链路只走 files/session API，移除会让 `server.py` 继续拥有 import confirm 处理职责的旧 wrapper。
- 影响范围：`server.py` import endpoints、`ImportProcessingService` 委托边界、银行流水导入前端 API guard、本模块 boundary/tests/state-machine 文档。
- 当时决策：`/imports/preview`、`/imports/confirm` 暂时作为共享程序化导入和旧回归入口保留；该临时决定已由 2026-07-11 记录取代。`FileImportService.snapshot/from_snapshot` 仍是当前 file/session 与 import worker 跨进程恢复 I/O，不是旧 full snapshot 事实源 fallback。
- 删除项：移除 `server.py` 中无调用的 `_process_general_import_confirm_job`、`_process_tax_certified_import_confirm_job`、`_process_file_import_confirm_job`、`_process_etc_invoice_import_confirm_job`，以及单调用委托 `_execute_general_import_confirm`、`_execute_file_import_confirm_job`、`_file_import_job_label`。
- 文档影响：更新 `boundary-io.md` 为 `close`，并同步 README、state-machine、tests 和全局测试依赖地图。
- 测试覆盖：新增/扩展 `tests/test_platform_runtime_boundary_guards.py`，防止银行流水前端回退旧 JSON import API，防止 `server.py` 重新持有 import confirm processor wrapper。
- 验证命令：`python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/import_processing_service.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_no_longer_owns_import_confirm_processors tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_transaction_import_frontend_uses_file_session_api_only -v`；后续本轮还需跑模块窄范围后端/前端和 docs/lint。
- 当时未测风险中的共享 legacy JSON import API 已在 2026-07-11 删除；真实银行大文件、真实 import worker drain、RabbitMQ/Redis/systemd、生产账户余额 fresh gate 仍按测试矩阵走 staging/infra-smoke。

## 2026-07-03 - 导入文件事实列表摘要化

- 目标：修复生产 HTTP SLO 中 `/api/import-facts/files?page=1&page_size=50` 返回约 15MB 导致导入页探针超时的问题。
- 影响范围：`/api/import-facts/files`、`PostgresCoreRepository.list_import_files_page()`、默认 HTTP SLO probe；不改变 `/imports/files/*` 上传、预览、确认和 session detail 合同。
- 关键决策：导入文件事实列表是摘要 read API，只投影文件名、模板、状态、计数、批次 ID 和审计计数；完整 `raw_payload`、`row_results`、`normalized_rows` 只能保留在导入预览/session 边界，禁止旧 full payload 污染列表链路。
- 2026-07-05 后续修正：列表 repository 返回 summary dict，不再构造完整 `FileImportPreviewItem`；SQL 继续保留计数/batch/audit 摘要，但删除银行选择、识别结果和冲突消息等预览上下文 JSONB 提取。
- 文档影响：更新本模块 boundary、共享 persistence/read-model 边界、发票导入和 ETC 导入 boundary。
- 测试覆盖：`tests/test_postgres_repositories_core.py::test_list_import_files_page_uses_summary_projection_without_raw_payload_blob`、`tests/test_import_file_api.py::ImportFileApiTests::test_import_fact_files_list_omits_preview_detail_payloads`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_import_file_api.py tests/test_postgres_repositories_core.py tests/test_http_slo_probe.py -q`。
- 未测风险：尚需发布后复跑生产 HTTP SLO，确认公网响应体和耗时已降到 1s 目标内。
- 后续事项：如果未来需要文件明细查看，应新增明确详情/下载 API，不得把预览明细重新放回列表。

## 2026-06-22 - 光大和建行真实流水表头别名识别

- 目标：修复用户上传 5 份银行流水时光大和建行文件显示“无法识别”的问题。
- 影响范围：`FileImportService` 的银行流水模板识别、光大/建行 parser 字段映射、银行流水导入 service/API 回归。
- 关键决策：模板需要比当前实现更能容忍同一家银行的官方导出表头别名，但不能做宽泛模糊猜列；本次只增加明确白名单别名：光大 `借方金额（支出）` / `贷方金额（收入）`，建行 `客户账号` / `凭证号码`。光大失败转账回退行使用负数借方金额表达收入回退，本次只在单列负数时做符号归一，双列都有值时仍不猜测。
- 文档影响：更新本模块 `tests.md`、本实施记录和 GSD quick task 记录；前端 API、状态机、read model/worker contract 不变。
- 测试覆盖：新增 `test_preview_accepts_ceb_xlsx_statement_with_income_expense_amount_headers` 和 `test_parse_ccb_statement_accepts_customer_account_and_voucher_number_headers`；覆盖 service 层模板识别、parser 字段映射、负数金额方向归一和关键字段保留。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service.ImportFileServiceTests.test_preview_accepts_ceb_xlsx_statement_with_income_expense_amount_headers tests.test_import_file_service.ImportFileServiceTests.test_parse_ccb_statement_accepts_customer_account_and_voucher_number_headers -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_import_api tests.test_import_service tests.test_import_preview_audit -v`；本地只读 smoke 用用户提供 5 个文件跑 `FileImportService.preview_files`，均返回 `preview_ready` 且文件级 `error_count=0`。
- 未测风险：未跑 Browser 上传/确认、后台 import worker drain 和下游 read model freshness；整批只读 preview 仍有 1 条 audit/dedup skipped row，不属于模板或行格式错误。
- 后续事项：如果后续遇到同一行借贷双列都有金额、双列为负数或其它银行符号规则，应先明确业务含义并补 business core 测试，不应靠模糊猜测导入。

## 2026-06-19 - 银行导入成功路径 UI 错误残留 guard

- 目标：补齐银行流水导入 Browser 成功链路的“假成功”检测，防止 confirm 或下游 fresh 成功后页面仍残留导入失败、后台导入失败、read model 失败等提示。
- 影响范围：`web/e2e/imports-bank-transactions-flow.spec.ts`、`web/e2e/fixtures/successAssertions.ts`、Playwright 严格诊断静态测试和本模块测试文档。
- 关键决策：只加固 deterministic Browser E2E 和静态 guard，不改产品逻辑；损坏文件 file-level error 仍是可接受的 preview 结果，不纳入成功残留错误模式。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、`docs/dev/testing.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：银行导入 confirm 成功、银行明细账户余额 fresh gate 和成本统计 fresh read model 成功节点都会调用 `expectNoUnexpectedSuccessUiErrors`。
- 验证命令：`cd web && npx playwright test e2e/imports-bank-transactions-flow.spec.ts e2e/imports-invoices-flow.spec.ts e2e/imports-etc-invoices-flow.spec.ts --project=chromium`；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`；`bash scripts/verify.sh docs`。
- 未测风险：真实银行大文件、真实 import worker drain、job retry/crash、真实 Workbench matching、search 最终展示和生产账户余额 API freshness 仍需 staging 或生产只读 smoke。
- 后续事项：新增导入进度 UI、search Browser route 或银行模板时，把成功后错误残留 guard 加入对应 Browser flow。

## 2026-06-19 - 银行流水导入 Spec-first covered 校准

- 目标：完成 `/imports/bank-transactions` 本地 Spec-first E2E Audit 校准，确认 `IMPORT-BANK-E2E-001..008` 均已由 Browser/组件/API/后端 contract 覆盖，`IMPORT-BANK-E2E-009` 明确归为真实基础设施 external-risk。
- 影响范围：银行流水导入 Spec-first 覆盖矩阵、全局 Spec-first inventory、testing closure state 和本实施记录；不改产品逻辑。
- 关键决策：当前页面本地 Browser 已覆盖上传/预览/慢预览锁定、重复明细、损坏文件混合、账户冲突取消/确认、preview stale、confirm 失败、权限 gate、银行明细账户余额 fresh gate 和成本统计 fresh read model 下游证据。真实 PostgreSQL/RabbitMQ/Redis/systemd import worker drain、真实 Workbench matching、真实大文件和真实 search 展示不能作为 deterministic 本地 CI 通过项，继续保留在 `IMPORT-BANK-E2E-009`。
- 文档影响：全局 inventory 和 testing closure state 可将 `imports-bank-transactions` 从 `partial` 校准为 `covered`，同时继续列出 staging/production smoke 风险。
- 测试覆盖：未新增测试；基于现有 `web/e2e/imports-bank-transactions-flow.spec.ts`、`permissions-role-matrix`、导入 API/service/read model/lifecycle 和 write-operation SLO audit contract 证据校准。
- 验证命令：待本轮运行三类导入 Playwright specs、`bash scripts/verify.sh docs` 和 `git diff --check`。
- 未测风险：真实银行大文件/历史模板、真实 import worker drain、job retry/crash、真实 Workbench matching、search 最终展示和生产账户余额 API freshness 仍需 staging 或生产只读 smoke。
- 后续事项：新增真实 search Browser route、导入进度 UI 或新银行模板时，按功能追加 Browser E2E；真实 worker 最新性走 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed bash scripts/verify.sh infra-smoke`。

## 2026-06-19 - 银行导入真实 write-operation audit 进入 infra-smoke

- 目标：把银行导入的真实 worker/read model 最新性验证接入统一 `infra-smoke`，避免 staging/服务器验证仍依赖手工拼 `write_operation_slo_audit` 命令。
- 影响范围：`scripts/verify.sh` 的 `infra-smoke` opt-in 分支、Nightly/测试闭环文档、runtime/read-models/银行导入测试矩阵。
- 关键决策：默认本地和 CI 不运行真实写链路 audit；只有同时有 `FIN_OPS_TEST_DATABASE_URL` 且显式设置 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed` 等 profile 时，才对最近真实业务写入的 durable outbox events 运行只读 SLO audit。该 gate 不发起写操作，不替代真实导入确认样本。
- 文档影响：更新全局 `docs/dev/testing.md`、`docs/dev/nightly-ci.md`、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing-closure-state.md`，以及 `runtime-workers`、`read-models` 和本模块测试矩阵。
- 测试覆盖：`tests/test_nightly_ci.py` 锁定 `infra-smoke` 必须包含 write-operation audit opt-in env 和 CLI 调用。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v`；`bash scripts/verify.sh infra-smoke`；`bash scripts/verify.sh docs`。
- 未测风险：当前本地没有 staging PostgreSQL URL 和真实银行导入样本，因此只验证工具合同和入口 wiring；真实证明仍需在 staging/服务器上先执行银行导入确认，再运行 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=bank_import_confirmed bash scripts/verify.sh infra-smoke`。

## 2026-06-19 - 银行流水导入到账户余额和成本统计 fresh read model Browser fan-out

- 目标：补齐 `IMPORT-BANK-E2E-007` 的下游页面 Browser 证据，避免银行导入只证明 Workbench/银行明细刷新，而没有证明账户余额或成本统计 read model 已 fresh。
- 影响范围：deterministic Playwright mock、`web/e2e/imports-bank-transactions-flow.spec.ts`、银行流水导入 Spec-first 覆盖矩阵。
- 关键决策：不改产品逻辑；mock 增加 `bankImportDownstreamFanout`，只有银行导入 confirm 成功后才让成本统计暴露导入流水成本证据；Browser 用例等待 `/api/cost-statistics/explorer` 响应并断言 `read_model_status=fresh`。
- 文档影响：更新 `e2e-spec.md`、`e2e-coverage.md`、`tests.md`、全局 Spec-first inventory 和测试闭环状态。
- 测试覆盖：新增/扩展银行导入 Browser flow，覆盖 confirm -> bank details account balance fresh gate -> 导入行，以及 confirm -> cost statistics fresh read model -> 按项目下钻 -> 导入流水成本证据。
- 验证命令：`cd web && npx playwright test e2e/imports-bank-transactions-flow.spec.ts --project=chromium`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd import worker drain、真实 Workbench matching、账户余额 API fresh gate、真实大文件和 search 最终展示仍需 staging 或生产只读 smoke。

## 2026-06-19 - 银行流水导入真实 write-flow SLO audit profile

- 目标：补齐银行流水导入 Spec-first E2E 闭环中的真实 read model/worker 证据入口，避免只用 deterministic Browser mock 或直接 enqueue smoke 声称真实写链路已闭环。
- 影响范围：`write_operation_slo_audit`、银行流水导入测试矩阵、`IMPORT-BANK-E2E-009` 真实基础设施 gate。
- 关键决策：profile 名使用业务规格 `bank_import_confirmed`；通用下游仍匹配真实 `*.read_model.refresh` 事件中的 `import_state_changed` scopes，银行账户余额必须出现 `bank_account_balance.read_model.refresh`，银行明细必须出现真实 `bank_detail.read_model.refresh` + `import_facts_changed` reason。`import.fact.changed` 只保留为 legacy bridge，不再作为银行明细闭环验收事件。银行导入不命中进项/销项发票方向页时，`input_invoice_usage` / `output_invoice_collection` 允许在审计中显示 `skipped`，避免无关方向页固定双刷；后台 worker 的税金抵扣 scope helper 也必须忽略银行流水文件，`tax_offset` 只由进项/销项发票导入触发。银行导入持久化路径以本次导入产生的 `bank_detail_scope_keys` 为信号，同步投递 `bank_account_balance:all`，避免账户余额页面只能靠 API miss 被动补刷。
- 覆盖 scope：Workbench、Workbench relation、invoice lifecycle、search、待找发票、OA 待付款、银行账户余额、银行明细和成本统计；进项使用/销项收款为方向命中项。
- 测试覆盖：新增 `tests/test_write_operation_slo_audit.py` 回归，验证完整 scope 才通过，缺少成本统计、银行账户余额等下游 scope 时必须失败。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_write_operation_slo_audit -v`；`bash scripts/verify.sh docs`；`bash scripts/verify.sh infra-smoke`。
- 未测风险：本地契约测试不产生真实银行确认 outbox rows；仍需 staging/发布前运行 `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit --json --operation bank_import_confirmed --lookback-hours 24`，并通过银行明细账户接口或页面 smoke 核对账户余额 API freshness gate 和真实 import worker / read model worker 状态。

## 2026-06-19 - 银行流水导入 Browser 负面路径

- 目标：补齐银行流水导入 Spec-first Browser E2E 基线，覆盖重复明细、`preview_stale` 和 confirm 失败，避免导入页在失败时误报成功或刷新下游页面。
- 影响范围：`web/e2e/imports-bank-transactions-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`docs/modules/imports-bank-transactions/e2e-spec.md`、`e2e-coverage.md`、`tests.md`、本实施记录和全局 Spec-first inventory/closure state。
- 关键决策：只加固 deterministic Browser E2E 和 mock，不改后端导入业务逻辑；mock 新增无账户冲突模式用于精确模拟 stale/失败，成功流仍保留账户冲突弹窗。
- 文档影响：新增 `e2e-spec.md` 和 `e2e-coverage.md`，更新 README、tests 和本实施记录，并同步全局 Spec-first 文档。
- 测试覆盖：`web/e2e/imports-bank-transactions-flow.spec.ts` 覆盖成功预览/冲突/下游银行明细、重复项明细、显式 operation barrier 等待、零 Workbench 页面请求，以及 `preview_stale`/confirm 失败时零 barrier 且不显示成功；`ImportCenterPage.test.tsx` 另覆盖空 targets 直接完成。
- 验证命令：`cd web && npx playwright test e2e/imports-bank-transactions-flow.spec.ts --project=chromium`。
- 未测风险：真实银行大文件、真实 PostgreSQL/RabbitMQ/Redis/systemd import worker drain、job retry/crash、真实 Workbench matching 和下游 read model fresh 仍需 staging/生产只读 smoke。
- 后续事项：补真实 worker drain smoke；继续给 `imports-invoices` 和 `imports-etc-invoices` 建立同等 Spec-first E2E coverage。

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
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_import_api tests.test_import_service tests.test_import_file_service tests.test_import_file_api tests.test_import_preview_audit tests.test_import_job_queue tests.test_import_formalization_api tests.test_derived_data_lifecycle_service tests.test_runtime_worker_registry tests.test_app_status_overview_service tests.test_bank_account_balance_read_model tests.test_bank_details_sql_runtime tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_import_file_confirm_returns_preview_stale_when_existing_records_change -v`
  - `cd web && npm test -- --run src/test/ImportsApi.test.ts src/test/ImportCenterPage.test.tsx src/test/AppStatusIndicator.test.tsx`
  - `bash scripts/verify.sh docs`
- 未测风险：真实银行大文件/历史模板、真实 Postgres/RabbitMQ/Redis/systemd import worker drain、worker crash/retry、下游最终页面展示仍需 staging/发布前 smoke；`import.process.requested` App Status job affected domain 与银行导入 domain 声明存在 P1 文档化风险。
- 后续事项：若修改共享 `ImportWorkflowPage` 或 `/imports/files/*` contract，必须同时评估 `imports-invoices` 与 `imports-etc-invoices`。
## 2026-07-15 Audit import fact 修复

- 根因：旧 `batch_row_00001` 由 process-global counter 生成，多进程/多文件会重用；PostgreSQL upsert 又允许同 ID 跨 batch 更新 owner，后续发票预览因此覆盖了 153 条银行导入 row evidence，但 79 条 canonical bank transaction 未丢失。
- 决策：runtime 改为 `batch_row:<batch_id>:<row_no>` 并在 repository 拒绝跨 batch re-parent；历史恢复走固定 dry-run/fingerprint 工具，不在 API/service 增加 fallback。
## 2026-08-10 - 共享导入工作区去嵌套卡片

- 共享 `ImportWorkflowPage` 将审计卡、文件卡、问题卡和冲突卡收敛为连续汇总带与分隔行；上传、预览、确认、重复检测和后台任务状态机不变。
- 删除对应旧卡片样式，不新增导入阶段、表、API、worker、fallback 或第二条写链。
## 2026-08-11 - 预览所有者与并发 ID 闭环

- 根因：共享 preview 持久化遗漏 `app.import_files` owner，恢复/放弃无法证明当前认证用户；顺序型 session/file/batch/candidate ID 还存在多 API worker 竞态。
- 修复：首写和最终 delta 持久化认证 username；`0144` 从已关联 batch 回填现存缺失 owner；discard 只忽略已删除旧文件，权限、terminal/job guard 不放宽。
- 旧链删除：共享导入新 ID 改为带类型前缀的 UUID，删除运行时“计数器递增 + 先查存在性”分配循环；不新增表、队列、read model、缓存或兼容写链。
- 验证：共享 service/repository/API 合同、迁移、完整后端回归及生产可逆 preview→recover→discard；银行正式事实不在该 smoke 中写入。

## 2026-08-11 - 旧 background snapshot 污染后的定点恢复

- 根因修复仍是 background job canonical `job_id` 单行持久化；不增加第二条导入写链。
- 当前生产旧版本已留下的一条 dead letter 不能由旧 worker安全重试，因此复用候选 release 的正式 import processor，并用显式五类 ID + dry-run fingerprint 限定唯一目标。
- 只有 untouched preview 与零 canonical 写入可进入恢复；业务完成后再 resolve 原事件。其它历史 pending/failed 记录不扫描、不推断、不自动重放。
- 发布门禁在首条证据恢复后揭示另一个明确失败 import job；增加只读 discovery 从该 job 的正式 payload/event 解析完整 target，避免人工猜测 background job id，执行白名单与 fingerprint 不放宽。

## 2026-08-11 - 银行重复修复关系阻断证据结构化

- 目标：生产银行去重 dry-run 因下游引用阻断时，能够逐条核对“错误导入副本 → 受保护原流水”的业务字段和具体引用类型，不再只返回内部流水 UUID。
- 关键决策：删除资格、零关系门禁和写路径保持不变；`BankImportDedupRelationEvidenceError` 只携带最多本次严格候选集的只读对照证据，CLI 以 `eligible=false`、`written=false` 和 `relationful_delete_candidates` 输出结构化 JSON 后返回非零状态。
- I/O：每条证据包含副本与 keeper 的账户、时间、方向、金额、余额、对方户名、批次、官方参考号及业务指纹，以及已有的核销金额和各下游引用计数；不新增 SQL、表、API、worker、read model、缓存或写权限。
- 测试覆盖：service 测试锁定副本/keeper 对照和关系计数；CLI 测试锁定阻断输出不可写且不会调用 apply。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_bank_import_dedup_repair_service.py tests/test_import_audit_repair_ops.py -q`；`bash scripts/verify.sh lint`；`bash scripts/verify.sh docs`。

## 2026-08-11 - 已授权 8+1 duplicate-owned 关系清理闭环

- 目标：在不删除 keeper 流水、不迁移标签、不直接改 Workbench relation 的前提下，处理严格去重候选中 8 条仅有单标签/单事件的错误副本和 1 条仅有银行流水+进项发票正式关系的错误副本，再清理全部已证明重复项。
- 边界：默认 repair 仍要求零关系；只有显式 related-cleanup 参数同时锁定 category 数、Workbench 数和唯一 relationful duplicate transaction id 才启用本合同。任何 OA、核销、确认、批次、claim、override、exception、额外标签/event 或多关系仍 fail closed。
- 写链：dry-run 把 category/event 完整 CAS 字段、relation case/version/preview、发票成员及无历史恢复结论纳入 source fingerprint；execute 在同一 serializable 事务内先走 `WorkbenchRelationCommandService.prepare_withdraw_relation/withdraw_relation`，再删除精确 category/event，修正 import 审计并删除 duplicate。transaction 删除触发 correction/audit，工具另写聚合 operation audit；relation history 保留。
- Read model：提交后只对受影响月份经 `ReadModelRefreshGateway` 强制入队 `workbench` 与 `workbench_relation`，不恢复跨页面 fan-out；其它页面继续直读 canonical facts。
- 测试：business core 覆盖严格 8+1 形状、错位 event、错误 transaction、发票成员和撤回后恢复旧关系拒绝；service/repository 覆盖正式 withdraw、append-only history、category/event 删除顺序和全部 CAS 字段；CLI 覆盖参数门禁、单事务编排、audit、精确 refresh scope、重放与二次幂等。
- 生产 dry-run 进一步发现 35 个待删副本除唯一 `created` owner 外，还各有一条同批次已正确判重的 `duplicate_skipped` 审计引用。修复计划不把这些引用误算成第二个 owner，也不重复调整 batch 计数；它们只以完整 CAS 条件把 `linked_object_id` 重定向到 keeper，并保留原 decision/reason，防止删除后留下悬挂导入审计。
- 后续生产 dry-run 证明 `import_files.raw_payload.normalized_payload.row_results` 保存的是预览阶段证据：对应正式 batch 已完成时，文件内行仍全部是 `suspected_duplicate`，文件级计数仍为初始化 `0/0`。因此删除把最终 row/batch 决策回写到文件 payload 的旧修复链；文件 payload 只以 SHA-256 纳入 source fingerprint 并保持不可变，最终审计只修正 `app.import_batch_rows` 与 `app.import_batches`。这避免用最终状态覆盖预览事实，也消除了旧 file counter 推断分支。

## 2026-08-11 去重恢复工具对象存储装配修复

- 生产 dry-run 暴露出维护工具直接构造 `PostgresStateStore` 时未注入对象存储 repository，导致已配置在正式 runtime 的归档导入文件无法读取。
- 修复复用现有 `ObjectStorageSettings` 与 `S3ObjectStorageRepository`，通过与应用相同的 runtime 环境装配对象存储；不新增维护专用凭据、fallback 或第二条文件读取链路。
- 银行去重恢复仍必须从正式归档文件读取并校验 SHA-256，配置缺失或文件漂移继续 fail closed。

## 2026-08-12 - 普通去重确认与受控恢复闭环

- 真实根因：旧 `ImportNormalizationService.confirm_import` 会把银行弱指纹 `suspected_duplicate` 直接改成 `created`，因此确认操作能够绕过预览去重并制造 canonical 重复项。
- 回放事实源：`import_files.raw_payload` 只保存旧预览，不能证明修复后的 decision/owner。生产受控回放由 dry-run 从 `app.import_batch_rows` 冻结 file、row_no、record type、data fingerprint 与 keeper，再由 processor 对当前预览逐行严格核对。
- 删除旧链：移除该强制新建分支；普通 confirm 只持久化 `created/status_updated/duplicate_skipped`，疑似项保持未写入并以 `completed_with_errors` 明确暴露。
- 恢复边界：生产恢复工具新增精确受控跳过计数。只有已由本次 repair reason 重定向到 keeper 的来源 row，且重新预览仍命中同一 keeper，才能转换为 `duplicate_skipped`；其余疑似项全部失败。
- Read model：修复工具把数据库可能返回的月初日期规范为 `YYYY-MM` 后再进入正式 gateway，避免业务事务已提交后刷新 scope 校验失败。
- 不新增表、API、worker、read model、fallback 或第二条导入写链；继续复用正式 file/session preview-confirm processor。

## 2026-08-12 - 受控恢复 stale gate 精确复核

- 生产候选执行证明受控预览持久化成功后，普通 stale gate 会把已由冻结证据确认的 767 条弱指纹 keeper 重新归类为 `suspected_duplicate`，使审计投影变化并整体回滚；生产 canonical 事实未发生半写入。
- 修复不跳过 stale gate，也不增加恢复专用确认链。只有受控 row 的登记 reason、银行流水类型和 canonical transaction ID 与当前普通去重重算结果完全一致时，才保留权威 `duplicate_skipped`；不同 ID、缺失 ID 或重算为 `created` 仍报 `preview_stale`。
- 测试同时锁定同 canonical 可确认、canonical 漂移必拒绝和普通 preview 竞争写入仍拒绝，避免受控恢复例外污染普通银行/发票导入。
- `preview_stale` 异常只记录发生变化的审计计数字段；HTTP 仍返回固定用户文案，不暴露业务行或 canonical ID。该诊断用于候选恢复失败时区分 importable、existing duplicate 与 suspected duplicate 漂移，不改变门禁结果。
- 生产诊断显示 853 条受控回放中有 27 条被通用去重重算为 `created`（`existing_duplicate_count 853→826`、`importable_count 0→27`）。这些是历史 parser/identity 漂移，不得通过放宽 decision 枚举处理；stale gate 只在冻结 canonical ID 仍能读取、且账户/秒级时间/方向/金额/余额/币种六项严格相等时接受，任何缺失或变化继续失败。
- 受控回放的六字段失败只记录差异字段名，不记录账号、时间、金额、余额、币种值或 canonical ID；该日志只服务于候选生产恢复诊断，不改变普通导入或 stale gate 的通过条件。

## 2026-08-12 - 重放归档与银行导入 Audit 合同闭环

- 发布门禁暴露出三项同源问题：受控重放创建新 file 行时沿用了来源 `stored_file_path` 却没有登记新 `file_object_id`；page Audit 把已证明的 statement-position 引用误当成 source key 漂移；历史正式 row 决策修正后，file/session audit 计数没有同步重算。
- 正式重放继续复用共享 file/session preview-confirm service，但每个 replay file 先通过现有 `_store_upload_file` 写入并登记独立对象，再进入 parser；没有新增重放专用存储或 fallback。
- Audit 只对登记的三类受控 reason 开放 statement-position 等价，且复用 `BankTransactionIdentityService`；普通合同要求账户、交易时间、方向、金额、余额、币种完整相等，历史双方币种同时缺失的受控审计规则见下节。其余字段比较、created owner、batch owner 和 queue 门禁不放宽。
- 一次性修复拆成纯 plan 与 PostgreSQL CAS repository：dry-run 必须给出精确 link/update 数和 fingerprint；execute 使用 serializable transaction、advisory lock、correction actor/reason 与 operation audit。对象 URI 多义、hash/size/lifecycle 不完整、计数或 payload 漂移均在写前/写中失败。
- 旧污染链已移除：不再创建“有 file row、无 object link”的 replay 记录；不通过修改 canonical source key 或覆盖原上传证据来让旧 Audit 通过。

## 2026-08-12 - 历史空币种受控重放 Audit 对齐

- 候选发布门禁证明光大等历史 canonical 流水与新重放 row 的账户、秒级时间、方向、金额、余额一致。历史 canonical 币种字段为空；正常文件解析器对未提供逐行币种的文件按既有合同补 `CNY`，因此新重放 row 为 `CNY`。普通 statement-position 合同正确拒绝这一对值，页面 Audit 却没有使用生产 repair 已冻结的历史缺失证据语义。
- `BankTransactionIdentityService.statement_position_for_mapping` 默认仍要求币种；只有调用方显式声明 `allow_missing_currency=True` 时才允许构造历史缺失位置。银行导入 Page Audit 仅在三类已登记受控重放 reason 下使用该模式，并额外只接受 `row=CNY / canonical=空` 这一种解析器默认值兼容。
- 账户、时间、方向、金额、余额任一缺失/不同，row 缺失但 canonical 有值、非 CNY 的单边缺失或显式币种不同，仍然失败；普通导入、普通去重 identity、source key/fingerprint 和 stale gate 均不放宽。
- 不新增 API、表、worker、read model、fallback 或第二条导入链；边界 I/O 只补充受控历史审计语义。

## 2026-08-12 - 去重恢复 owner 转移审计闭环

- 候选发布门禁最终定位到历史正式 row：去重恢复工具把被删除副本的唯一 `created` owner 转为 `duplicate_skipped`，并写入专用 reclassification reason；Page Audit 之前只登记三类 runtime replay reason，因此即使该 row 与 keeper 的 statement position 相同，仍会被误报为 `unregistered_decision_reason`。
- reclassification reason 现与三类 runtime replay reason 在共享导入审计合同中分开登记。Page Audit 对两类 provenance 都执行相同的账户、秒级时间、方向、金额、余额、币种证明；任一字段漂移继续阻断。普通 preview、confirm 与 stale gate 仍只接受三类 runtime replay reason，repair reason 不获得运行时导入例外。
- 没有新增 API、表、worker、read model、fallback 或第二条导入链；改动只修正历史正式 row 的只读审计解释。

## 2026-08-17 - 导入工作区紧凑统计与按需明细

- 银行流水导入页保留上传文件、逐文件账户选择、条件字段映射和异步确认；右栏只展示“本次识别 / 本次将处理 / 本次不处理”三个互斥统计，并以次要标签补充 `APP 内已存在` 数量。
- 删除旧七项审计汇总带、预览成功解释、常驻文件宽表与常驻重复/未导入明细表；逐文件解析状态收敛为紧凑结果行。
- 重复项和未处理项复用现有 review API，仅在用户打开 HeroUI 右侧抽屉后加载；预览完成到抽屉打开前不发起 detail request，不新增 API、worker、read model、缓存或第二条写链。
- 统计口径固定为 `本次识别 = 本次将处理 + 本次不处理`；`APP 内已存在` 可能与其它不处理原因交叠，不参与该等式。
- Browser 回归覆盖预览、按需加载、文件损坏、账户冲突、慢预览锁定、stale/confirm failure、异步确认及下游页面隔离。

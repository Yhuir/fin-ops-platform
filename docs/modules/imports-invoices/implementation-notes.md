# 发票导入 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 发票导入不是独立实现；页面入口复用 `ImportWorkflowPage mode="invoice"`，因此任何共享导入工作流改动都必须同时检查银行流水导入和 ETC 发票导入。
- 发票导入确认后的事实源是 canonical invoice facts + derived lifecycle + read model freshness，不是 confirm API 或 background job 的返回值。
- 本模块首轮闭环状态为 `documented-risk`：自动化测试已覆盖核心 contract 和历史 bug，但真实大文件、真实 Postgres/RabbitMQ/Redis/systemd worker drain、下游页面真实浏览器 smoke 仍需发布前验证。

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

## 2026-06-19 - 发票导入后台链路闭环

- 目标：修复发票文件上传/预览/确认后，用户看到导入成功但关联台仍长期刷新中的闭环缺口。
- 影响范围：发票导入确认后的 background job、`import.fact.changed` durable event、下游 workbench/workbench_relation/tax/cost/invoice lifecycle/search read model refresh，以及 App Status 导入进度展示。
- 关键决策：发票导入成功的用户口径必须同时满足三段链路：文件导入 job 完成、`import.fact.changed` 被 import worker claim/ack、下游 read model dirty scope 被各自 worker 刷新并通过 freshness/readiness 暴露。RabbitMQ 模式下 `import.fact.changed` 不得只注册在 PostgreSQL claim override；它必须进入 import worker 的统一 claim event types 和 RabbitMQ dispatch route。
- 文档影响：同步 runtime worker、关联台和系统状态模块实施记录；发票导入 API contract 与业务字段不变。
- 测试覆盖：`tests/test_import_job_queue.py` 覆盖 RabbitMQ import worker check 暴露 `import.fact.changed` route；`tests/test_runtime_worker_registry.py` 覆盖 import worker 所有 transport claim event types；`web/src/test/AppStatusIndicator.test.tsx` 覆盖发票导入进度在全局状态框显示为“正在导入发票 210/500”。
- 验证命令：见本轮最终交付说明。
- 未测风险：本地测试不执行真实 RabbitMQ broker/systemd 长跑，也不证明生产历史 pending 自动 drain；发布后需只读观察 backlog 并重新导入小批量发票 smoke。
- 后续事项：重新导入验证前，只能清理本次导入批次对应发票/source links/import rows，不能删除历史发票事实；清理前必须用 import session/batch/job 精确圈定范围。

## 2026-06-18 - 服务器发票预览 500 修复

- 目标：修复服务器 `/imports/files/preview` 在发票 Excel 预览完成后返回 `接口处理失败` 的问题。
- 影响范围：发票导入预览后的 PostgreSQL import facts 持久化、`job.outbox_events` 的 import-fact changed 入队、下游 read model dirty/outbox fan-out。
- 关键决策：不改 Excel 解析和模板识别；真实异常来自 `PostgresCoreRepository._mark_import_fact_read_models_dirty()` 中 `job.outbox_events` 的 `ON CONFLICT` predicate 仍使用旧合同 `status in ('pending', 'processing')`，而当前 `0016` 后的 `outbox_events_dedupe_uidx` 只覆盖 `status = 'pending'`。修复为与 schema 一致的 predicate。
- 文档影响：更新本实施记录和 `tests.md`；API contract 和业务状态不变。
- 测试覆盖：新增 `tests/test_postgres_repositories_core.py::test_save_imports_marks_read_models_dirty_and_outbox_event` 断言 import fact outbox 使用 `status = 'pending'`，并用用户提供的 5 个真实 Excel 在本地一次性 PostgreSQL schema 中跑 `/imports/files/preview` smoke。
- 验证命令：本地 PostgreSQL 临时库 `fin_ops_preview_test_260618` 完整迁移后，通过同一 HTTP handler 上传 5 个真实 Excel，返回 `status=200`、session `preview_ready`、391 行、错误 0，并写入 `app.import_batches=5`、`app.import_batch_rows=391`、`app.import_files=5`、`app.file_objects=5`、`job.outbox_events(import.fact.changed)=14`。
- 未测风险：尚未在服务器用真实 OA 登录态重新点击页面确认；当前 SSH 用户不能读取 `fin-ops.service` journal traceback，生产验证需要发布本修复后再看 `/health/ready.api_performance["POST /imports/files/preview"].last_status_code` 和页面上传结果。
- 后续事项：发布后如果仍报错，优先查看服务器 journal 中新的 traceback；不要再按模板识别方向排查。

## 2026-06-18 - 发票信息汇总表模板识别

- 目标：支持用户从发票平台导出的 `信息汇总表` Excel，该格式使用 `数电号码`、`购方企业名称`、`购方税号`、`销方企业名称`、`销方税号`、`商品名称` 等表头，旧导入器会因缺少 `购买方名称` / `销方识别号` 判定为无法识别模板。
- 影响范围：`FileImportService` 发票模板识别、发票行解析、file/session preview、发票导入测试矩阵。
- 关键决策：不新增前端 API 或独立 batch type；在 `invoice_export` 模板内做发票表头别名归一，保持 normalized row、重复审计、confirm 和下游 lifecycle 语义不变。`信息汇总表` 末尾 `份数：...金额：...` 汇总页脚不是发票明细，解析阶段跳过。
- 文档影响：更新本实施记录和 `tests.md` 的场景覆盖、历史 bug 回归和 smoke flow；长期 API contract 不变。
- 测试覆盖：新增 `test_preview_accepts_invoice_summary_header_aliases` 和 `test_preview_detects_invoice_summary_without_template_override`，覆盖表头别名、前端 override 场景、自动识别场景和汇总页脚跳过。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service tests.test_import_file_api tests.test_import_api tests.test_import_service tests.test_import_preview_audit -v`；本地还用用户提供的 5 个真实 Excel 跑 `FileImportService.preview_files` smoke，结果均为 `preview_ready` 且 `errors=0`。
- 未测风险：尚未通过真实浏览器上传和真实 background worker drain 确认完整 confirm -> lifecycle -> 下游 read model 链路；真实业务文件不纳入仓库 fixture。
- 后续事项：如发票平台继续新增表头口径，优先扩展 alias mapping 并补合成 fixture，不保存真实业务 Excel。

## 2026-06-16 - 发票导入合成大重复组守护

- 目标：为 P2/P3 发票大文件和超大重复组风险补本地可重复证据，防止同文件重复发票在 preview audit 中被全部当作可确认。
- 影响范围：`FileImportService.preview_files`、invoice Excel parser、invoice identity、import preview duplicate audit、发票导入测试矩阵。
- 关键决策：不改导入行为；使用 240 行合成发票 Excel fixture 锁定当前 contract：同一稳定 identity 只产生一个 confirmable representative，其余 239 行进入 duplicate group 和 skipped count。
- 文档影响：更新 `tests.md` 的场景覆盖、历史 bug 回归和未测风险；P2/P3 台账记录为 local synthetic evidence。
- 测试覆盖：新增 `test_preview_bounds_large_invoice_duplicate_group_to_one_confirmable_row`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service.ImportFileServiceTests.test_preview_bounds_large_invoice_duplicate_group_to_one_confirmable_row -v`；本轮也与银行/ETC 合成导入测试一起运行通过。
- 未测风险：真实客户发票大文件、历史模板变体、异常编码、真实浏览器上传耗时、真实 worker drain 和下游页面 fresh 仍需 staging/manual smoke。
- 后续事项：拿到用户批准的真实发票样本后，在 staging 跑文件 preview/confirm/job/read-model smoke，不在仓库保存真实业务文件。

## 2026-06-16 - 发票导入 App Status job domain 闭环

- 目标：关闭发票文件确认后 App Status/job feedback 可能落到泛化导入域的缺口，让用户能从全局状态返回 `/imports/invoices`。
- 影响范围：`/imports/files/confirm` 的 `file_import` background job source、`app_status_job_registry` 的共享 import fallback、发票导入模块测试矩阵和状态机。
- 关键决策：具体文件确认 job 使用 `source.affected_domains` / `source.route` 精确报告发票导入页；共享 `import.process.requested` 仍保留多导入域兜底，避免在没有文件类型上下文时伪装成单一页面。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md`，并在 Phase16 GSD 产物记录本次闭环。
- 测试覆盖：新增/更新 API contract 与 App Status registry 回归，覆盖发票确认 job domain/route 和泛化 import fallback。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_api.ImportFileApiTests.test_confirm_files_imports_only_selected_files_from_session`；扩展后端 187 tests；前端导入页/App Status 27 tests；`bash scripts/verify.sh docs`。
- 未测风险：真实大文件、真实 Postgres/RabbitMQ/Redis/systemd worker drain、worker crash/retry、下游真实浏览器大数据和导出 smoke。
- 后续事项：进入 `imports-etc-invoices` phase，确认 ETC 导入 job domain/route 与本页一致闭环。

## 2026-06-11 - 发票导入测试闭环首轮

- 目标：补齐 `/imports/invoices` 的影响面、七类测试矩阵、状态机、历史 bug 回归库和验证命令。
- 影响范围：共享 import workflow、file/session import API、发票 normalizer、import worker、`invoice_import_confirmed` derived lifecycle、关联台、待找发票、税金抵扣、进项/销项/OA 待付款、成本统计、搜索和 App Status。
- 关键决策：不新增低价值测试；先把现有发票导入和下游回归测试登记到模块矩阵，并把真实基础设施/大样本风险标记为 `documented-risk`。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`docs/dev/testing-closure-dependency-map.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：覆盖七类测试；重点保护发票 identity、重复审计、preview stale、file confirm、worker/job、derived lifecycle、下游 read model/API 和前端交互状态。
- 验证命令：见 `tests.md` 和 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实发票大文件/历史模板、真实 Postgres/RabbitMQ/Redis/systemd worker drain、worker crash/retry、下游真实浏览器大数据和导出 smoke。
- 后续事项：后续模块处理 `imports-etc-invoices`；另行专项校准共享 `import.process.requested` App Status affected domain。

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

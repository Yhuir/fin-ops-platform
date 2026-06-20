# ETC发票导入 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- ETC 发票导入不是通用发票导入的一种 batch type；它走 `/api/etc/import/preview`、`/api/etc/import/confirm`、reconciliation task 和 `etc_invoice_import.confirm` processor。
- ETC zip preview 的事实源是 confirmed reconciliation task 的版本和 `confirmed_item_set_hash`。task 或 canonical invoice 变化后必须重新预览，不能复用旧 session。
- ETC import confirm 后的事实源是 ETC business batch + ETC invoice facts + canonical invoice sync + `etc_import_confirmed` lifecycle，不是 confirm API 或 background job 的返回值。
- 本模块首轮闭环状态为 `documented-risk`：自动化测试已覆盖核心 contract 和历史 bug，但真实大 zip、对象存储、真实 OA 草稿和真实 worker drain 仍需发布前验证。

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

## 2026-06-19 - ETC 导入成功路径 UI 错误残留 guard

- 目标：补齐 ETC 导入 Browser 成功链路的“假成功”检测，防止 confirm job 或下游 fresh 成功后页面仍残留导入失败、后台导入失败、read model 失败等提示。
- 影响范围：`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/fixtures/successAssertions.ts`、Playwright 严格诊断静态测试和本模块测试文档。
- 关键决策：只加固 deterministic Browser E2E 和静态 guard，不改产品逻辑；preview 中的 XML 解析失败是文件级 preview 证据，不纳入成功残留错误模式。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、`docs/dev/testing.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：ETC import confirm job 成功、ETC 票据、税金抵扣和成本统计 fresh 成功节点都会调用 `expectNoUnexpectedSuccessUiErrors`。
- 验证命令：`cd web && npx playwright test e2e/imports-bank-transactions-flow.spec.ts e2e/imports-invoices-flow.spec.ts e2e/imports-etc-invoices-flow.spec.ts --project=chromium`；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`；`bash scripts/verify.sh docs`。
- 未测风险：真实大 zip、票根网/PDF/XML/TXT 混合包、对象存储、真实 OA 草稿、真实 import/derived lifecycle worker drain、Workbench/search/historical repair 最终 fresh 仍需 staging 或生产只读 smoke。
- 后续事项：新增 search Browser route、历史修复页面入口或新 ETC 模板时，把成功后错误残留 guard 加入对应 Browser flow。

## 2026-06-19 - ETC 导入 Spec-first covered 校准

- 目标：完成 `/imports/etc-invoices` 本地 Spec-first E2E Audit 校准，把剩余 `IMPORT-ETC-E2E-004` 和 `IMPORT-ETC-E2E-010` 从 partial 收敛为 covered，并把真实对象存储/worker/OA 草稿风险保留在 `IMPORT-ETC-E2E-011` external-risk。
- 影响范围：ETC 导入 Spec-first 覆盖矩阵、全局 Spec-first inventory、testing closure state 和本实施记录；不改产品逻辑。
- 关键决策：当前 Browser 已覆盖 ready task、zip preview、included/duplicate/attachment_completed/failed 文案、preview stale、stale reconciliation task preview、confirm 失败、background job feedback、权限 gate，并覆盖 ETC 票据、税金抵扣和成本统计 downstream fresh read model 展示。missing requirements 由组件/后端覆盖；Workbench/search/historical repair scope 由后端 contract 和 staging gate 保护，search 当前无独立前端 route。
- 文档影响：`IMPORT-ETC-E2E-004` 和 `IMPORT-ETC-E2E-010` 标记为 `covered`；全局 inventory 和 testing closure state 可将 `imports-etc-invoices` 从 `partial` 校准为 `covered`。
- 测试覆盖：未新增测试；基于现有 `web/e2e/imports-etc-invoices-flow.spec.ts`、`permissions-role-matrix`、ETC API/service/lifecycle/read model 和 write-operation SLO audit contract 证据校准。
- 验证命令：待本轮运行三类导入 Playwright specs、`bash scripts/verify.sh docs` 和 `git diff --check`。
- 未测风险：真实大 zip、票根网/PDF/XML/TXT 混合包、对象存储、真实 OA 草稿、真实 import/derived lifecycle worker drain、Workbench/search/historical repair 最终 fresh 仍需 staging 或生产只读 smoke。
- 后续事项：新增独立 search Browser route、历史修复页面入口或新 ETC 真实模板时，按功能追加 Browser E2E；真实 worker 最新性走 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=etc_import_confirmed bash scripts/verify.sh infra-smoke`。

## 2026-06-19 - ETC 导入下游 fresh read model Browser fan-out

- 目标：补齐 `IMPORT-ETC-E2E-010` 的 Browser 证据，避免 ETC 导入只证明 confirm job queued，而没有证明下游页面能读取 fresh read model。
- 影响范围：deterministic Playwright mock、`web/e2e/imports-etc-invoices-flow.spec.ts`、ETC 导入模块 Spec-first 覆盖矩阵。
- 关键决策：不改产品逻辑；mock 增加 `etcImportDownstreamFanout`，只有 ETC confirm 成功后才让 ETC 票据批次、税金抵扣和成本统计暴露导入证据；Browser 用例等待下游 GET 响应并断言 `read_model_status=fresh`。
- 文档影响：更新 `e2e-coverage.md` 和 `tests.md`，把真实 worker drain、Workbench/search/historical repair 仍保留为 staging/documented risk。
- 测试覆盖：新增 ETC 导入 Browser flow，覆盖 confirm -> ETC ticket business batch -> tax offset fresh row -> cost statistics fresh project/transaction evidence。
- 验证命令：`cd web && npx playwright test e2e/imports-etc-invoices-flow.spec.ts --project=chromium`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd import worker、derived lifecycle worker、真实对象存储/OA 草稿、Workbench/search/historical repair 最终 fresh 仍需 staging 或生产只读 smoke。

## 2026-06-19 - ETC 导入真实 write-flow SLO audit profile

- 目标：补齐 ETC 导入 Spec-first E2E 闭环中的真实 read model/worker 证据入口，避免只用 deterministic Browser mock 或直接 enqueue smoke 声称真实写链路已闭环。
- 影响范围：`write_operation_slo_audit`、ETC 导入测试矩阵、`IMPORT-ETC-E2E-011` 真实基础设施 gate。
- 关键决策：profile 名使用业务规格 `etc_import_confirmed`，但匹配真实 durable queue reason `etc_invoice_import_confirm`；search 是 cache clear，不属于该工具审计的 `*.read_model.refresh` 事件。
- 覆盖 scope：Workbench、Workbench relation、invoice lifecycle、tax offset 和 cost statistics。
- 测试覆盖：新增 `tests/test_write_operation_slo_audit.py` 回归，验证完整 scope 才通过，缺少税金抵扣等下游 scope 时必须失败。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_write_operation_slo_audit -v`；`bash scripts/verify.sh docs`；`bash scripts/verify.sh infra-smoke`。
- 未测风险：本地契约测试不产生真实 ETC confirm outbox rows；仍需 staging/发布前运行 `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit --json --operation etc_import_confirmed --lookback-hours 24`，并配合真实对象存储/OA 草稿/import worker/read model worker 和下游页面最终 fresh 检查。

## 2026-06-19 - ETC 导入 Spec-first Browser 负面路径

- 目标：把 `/imports/etc-invoices` 从单一 happy path Browser smoke 提升为 Spec-first E2E 基线，覆盖 `preview_stale`、`stale_reconciliation_task_preview` 和 confirm failure，防止页面在旧 preview、task 变更或 confirm 失败时仍展示后台导入成功。
- 影响范围：deterministic Playwright mock、`web/e2e/imports-etc-invoices-flow.spec.ts`、ETC 导入模块 Spec-first E2E 文档和全局测试闭环状态。
- 关键决策：不改产品逻辑；复用 ETC API mapper 的固定 stale 文案，只在 mock 中增加 ETC 导入专用失败开关。mock confirm job queued 不等同于真实 worker drain，真实 PostgreSQL/RabbitMQ/Redis/systemd worker、对象存储、OA 草稿和下游 read model freshness 仍作为 `external-risk` 记录。
- 文档影响：新增 `e2e-spec.md`、`e2e-coverage.md`，更新 `README.md`、`tests.md`、全局 Spec-first inventory、测试说明和闭环状态。
- 测试覆盖：Browser E2E 覆盖 ready task、zip preview、audit、异常/重复/附件补齐明细、confirm job feedback、`preview_stale` 无 job success、`stale_reconciliation_task_preview` 清空旧 preview 并禁用 confirm、confirm 500 无 job success，且全部断言不走通用 `/imports/files/*`。
- 验证命令：见本轮最终交付说明。
- 未测风险：真实票根网 zip、大 zip、对象存储、真实 OA 草稿、真实 import worker drain、derived lifecycle worker、Workbench/tax/cost/search read model 最终 fresh 仍需 staging 或生产只读 smoke。
- 后续事项：继续补真实基础设施 worker drain smoke，或补 ETC 导入后的下游多页面 Browser fan-out。

## 2026-06-16 - ETC 导入合成混合 zip 预览守护

- 目标：为 P2/P3 ETC 大 zip、重复票号和坏 XML 风险补本地可重复证据，避免混合包 preview 因单个坏文件中断或把重复/失败计数混入有效导入。
- 影响范围：`EtcService.preview_import_zips`、ETC zip parser/audit、ETC 发票导入测试矩阵。
- 关键决策：不改 ETC 导入行为；使用 120 张合成 ETC 发票、PDF 附件、同包重复 XML 和 malformed XML 锁定 preview contract：有效发票、duplicatesSkipped 和 failed item 分离计数，preview 不持久化发票记录。
- 文档影响：更新 `tests.md` 的场景覆盖、历史 bug 回归和未测风险；P2/P3 台账记录为 local synthetic evidence。
- 测试覆盖：新增 `test_preview_large_mixed_zip_keeps_valid_invoices_duplicates_and_failures_separate`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcServiceTests.test_preview_large_mixed_zip_keeps_valid_invoices_duplicates_and_failures_separate -v`；本轮也与银行/发票合成导入测试一起运行通过。
- 未测风险：真实票根网 zip、PDF/XML/TXT 混合包、对象存储、Nginx 上传限制、真实 OA/worker drain 和浏览器上传耗时仍需 staging/manual smoke。
- 后续事项：拿到用户批准的真实 ETC 样本后，在 staging 跑 preview/confirm/object-storage/Nginx/job/read-model smoke，不在仓库保存真实业务文件。

## 2026-06-16 - ETC 导入 App Status job metadata 闭环

- 目标：关闭 ETC 导入 confirm 后 background job 缺少 task/domain/route 元数据的风险，让全局状态能稳定指向 `/imports/etc-invoices` 并标记 `etc_tickets` 受影响。
- 影响范围：`/api/etc/import/confirm` 的 `etc_invoice_import` background job source、ETC 导入 API contract regression、模块状态机和测试矩阵。
- 关键决策：ETC 导入仍使用专用 `/api/etc/import/*` 和 `etc_invoice_import.confirm` processor；job type 已有 registry 默认值，但具体 job source 也持久化 `task_id`、`affected_domains` 和 `route`，便于 App Status、审计和后续排障。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md`，并在 Phase17 GSD 产物记录本次闭环。
- 测试覆盖：更新 ETC confirm API regression，覆盖 job type、domain、route、source task、异步导入和下游发票可见。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_etc_confirm_returns_background_job_and_imports_asynchronously -v`；扩展后端 302 tests；前端 ETC/导入/App Status 111 tests；`bash scripts/verify.sh docs`。
- 未测风险：真实大 zip/票根网/PDF/XML 混合包、真实对象存储、真实 OA 草稿、真实 Postgres/RabbitMQ/Redis/systemd import worker drain、Nginx 代理和大数据浏览器 smoke。
- 后续事项：17 个页面 phase 完成后做最终跨 phase 状态和 diff sanity check。

## 2026-06-11 - ETC 发票导入测试闭环首轮

- 目标：补齐 `/imports/etc-invoices` 的影响面、七类测试矩阵、状态机、历史 bug 回归库和验证命令。
- 影响范围：共享 `ImportWorkflowPage`、ETC API mapper、`/api/etc/import*`、reconciliation task、zip parser/filter、ETC service、import worker、business batch、canonical invoice sync、`etc_import_confirmed` lifecycle、关联台、税金抵扣、成本统计、搜索和 App Status。
- 关键决策：不新增低价值测试；先把现有 ETC backend/reconciliation/API/frontend/business-batch 测试登记到模块矩阵，并把真实基础设施/真实 OA 风险标记为 `documented-risk`。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`docs/dev/testing-closure-dependency-map.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：覆盖七类测试；重点保护 ready task gate、zip preview filter、stale task preview、async confirm job、canonical invoice sync、business batch summary 和下游 read model refresh。
- 验证命令：见 `tests.md` 和 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实大 zip/票根网/PDF/XML 混合包、真实对象存储、真实 OA 草稿、真实 Postgres/RabbitMQ/Redis/systemd import worker drain、Nginx 代理和大数据浏览器 smoke。
- 后续事项：后续模块处理 `output-invoice-collections`；另行专项校准共享 `import.process.requested` App Status affected domain。

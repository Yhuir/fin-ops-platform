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

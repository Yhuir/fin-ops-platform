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

## 2026-06-11 - ETC 发票导入测试闭环首轮

- 目标：补齐 `/imports/etc-invoices` 的影响面、七类测试矩阵、状态机、历史 bug 回归库和验证命令。
- 影响范围：共享 `ImportWorkflowPage`、ETC API mapper、`/api/etc/import*`、reconciliation task、zip parser/filter、ETC service、import worker、business batch、canonical invoice sync、`etc_import_confirmed` lifecycle、关联台、税金抵扣、成本统计、搜索和 App Status。
- 关键决策：不新增低价值测试；先把现有 ETC backend/reconciliation/API/frontend/business-batch 测试登记到模块矩阵，并把真实基础设施/真实 OA 风险标记为 `documented-risk`。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`docs/dev/testing-closure-dependency-map.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：覆盖七类测试；重点保护 ready task gate、zip preview filter、stale task preview、async confirm job、canonical invoice sync、business batch summary 和下游 read model refresh。
- 验证命令：见 `tests.md` 和 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实大 zip/票根网/PDF/XML 混合包、真实对象存储、真实 OA 草稿、真实 Postgres/RabbitMQ/Redis/systemd import worker drain、Nginx 代理和大数据浏览器 smoke。
- 后续事项：后续模块处理 `output-invoice-collections`；另行专项校准共享 `import.process.requested` App Status affected domain。

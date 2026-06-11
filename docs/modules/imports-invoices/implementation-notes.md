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

## 2026-06-11 - 发票导入测试闭环首轮

- 目标：补齐 `/imports/invoices` 的影响面、七类测试矩阵、状态机、历史 bug 回归库和验证命令。
- 影响范围：共享 import workflow、file/session import API、发票 normalizer、import worker、`invoice_import_confirmed` derived lifecycle、关联台、待找发票、税金抵扣、进项/销项/OA 待付款、成本统计、搜索和 App Status。
- 关键决策：不新增低价值测试；先把现有发票导入和下游回归测试登记到模块矩阵，并把真实基础设施/大样本风险标记为 `documented-risk`。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`docs/dev/testing-closure-dependency-map.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：覆盖七类测试；重点保护发票 identity、重复审计、preview stale、file confirm、worker/job、derived lifecycle、下游 read model/API 和前端交互状态。
- 验证命令：见 `tests.md` 和 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实发票大文件/历史模板、真实 Postgres/RabbitMQ/Redis/systemd worker drain、worker crash/retry、下游真实浏览器大数据和导出 smoke。
- 后续事项：后续模块处理 `imports-etc-invoices`；另行专项校准共享 `import.process.requested` App Status affected domain。

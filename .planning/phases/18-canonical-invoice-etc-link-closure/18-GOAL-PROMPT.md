---
phase: 18-canonical-invoice-etc-link-closure
status: master_prompt
created: 2026-06-23
---

# 18-GOAL-PROMPT：主控 /goal prompt

把下面整段喂给 Codex 主控 `/goal` 使用。

```text
/goal
目标：完全闭环“发票池与 ETC 批次关系重复发票”修复和中长期架构演进。

必须遵守仓库根目录 AGENTS.md、.planning/README.md、.planning/ROADMAP.md，以及本阶段文件：
- .planning/phases/18-canonical-invoice-etc-link-closure/18-CONTEXT.md
- .planning/phases/18-canonical-invoice-etc-link-closure/18-PLAN.md

背景：
- app.invoices 必须成为统一发票池，一张真实发票只能有一行 active canonical row。
- ETC 批次归属必须进入 app.etc_batch_invoice_links。
- app.etc_invoices 在迁移期只作为 ETC 源数据/导入审计/文件元数据，不得继续与 app.invoices 竞争成为关联台发票事实源。
- 如果发票已经属于 submitted/manual-submitted ETC business batch，它不应作为独立待关联发票出现在关联台。
- 用户提供的 Excel 全量镜像为 /Users/yu/Desktop/sy/财务运营平台/发票/进项全量发票查询导出结果1-6.22(1).xlsx，执行前必须用它重新核对发票池。

工作流要求：
1. 用 GSD 方式执行，不跳过计划、审计、测试、实现、验证、文档、运行手册和最终总结。
2. 本目标包含三个阶段，必须全部闭环：
   - Phase A：生产稳定化。重跑只读审计，写失败测试，最小修复导入/关联台重复发票，提供 dry-run-first 生产修复工具，明确是否需要清理数据库。
   - Phase B：事实源边界重构。新增 app.etc_batch_invoice_links，迁移写入/读取路径，保证 app.invoices canonical identity 唯一。
   - Phase C：历史 backfill、旧路径清理、reset/runbook/docs 闭环。
3. 一次只生成并执行一个 bounded execution prompt。每个 prompt 必须包含：
   - 本轮目标。
   - 必读上下文。
   - 允许改动范围。
   - 停止条件。
   - 验证命令。
4. 每个 prompt 执行完成后，先根据实际完成状态判断下一步，不要机械推进；如果审计数字、测试失败或 schema 事实改变，先调整下一 prompt。
5. 生产数据写入规则：
   - 默认只允许 read-only 审计和 dry-run。
   - 任何真实数据库 --apply、删除、隐藏、回填、修正之前必须停止并请求用户明确确认 exact row set、reason、rollback 和验证方式。
6. 完成标准：
   - 关联台不再显示同一真实发票的 duplicate open invoice row。
   - app.invoices canonical invoice identity 不产生重复 active row。
   - app.etc_batch_invoice_links 成为 ETC batch membership 的事实源。
   - app.etc_invoices 的长期职责已在代码和文档中收敛为 ETC 源数据/审计，或有明确迁移窗口。
   - Excel 全量镜像核对完成：发票池总数、Excel 有效身份数、缺失、extra、mismatch 都有报告和处理结论。
   - Tests 覆盖 AGENTS.md 中七类适用测试，并且相关验证命令已运行。
   - docs/modules 与 .planning 阶段文件已更新。

首个 bounded execution prompt：
“读取 Phase 18 上下文、相关模块文档、当前 schema/service/test 入口，执行只读审计和 Excel 镜像核对，不做任何代码或数据库写入。停止条件：产出当前事实清单，包括 app.invoices 总数、Excel 有效发票身份数、Excel 缺失、DB extra、字段 mismatch、ETC overlap row set、自动修复候选/人工判定候选/禁止自动处理候选，并据此生成下一轮 Phase A 测试与最小修复 prompt。”
```

## 主控循环模板

每轮结束后用这个模板决定下一轮：

```text
上一轮结果：
- 已完成：
- 未完成：
- 新事实/偏差：
- 风险：

下一轮 bounded execution prompt：
“……”
```


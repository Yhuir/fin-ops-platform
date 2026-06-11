# Finance Table System 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 共享 `FinanceTable` 保持 presentation primitive，不上提页面业务查询、导出、read model freshness 或权限判断。
- 页面级表格 wrapper 可继续保留 domain-specific 结构；迁移时必须先补 characterization/regression test 保护旧筛选、排序、分页、导出和详情入口。
- `useFinanceTableSession` 只保存轻量表格 UI state；当前未强制所有页面使用。未接入该 hook 的页面必须在页面模块里保护自己的 session/query state。
- 共享 primitive 的低层 contract 由 `FinanceTable.test.tsx`、CSS token/style tests 保护；页面表格行为由具体页面测试保护。

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

## 2026-06-11 - Finance Table System 首轮测试闭环

- 目标：完成共享表格系统 CodeGraph 审计、测试矩阵、状态机、实施记录和共享 primitive 回归测试补强。
- 影响范围：`FinanceTable.tsx`、`useFinanceTableSession.ts`、`PageSessionStateContext`、表格 token/style tests，以及银行明细、税金、进项使用、待找发票、销项收款、OA 待付款、成本、往来款、导入预览、App Health 等页面表格。
- 关键决策：不重构业务页面表格；先补共享 primitive 低层测试，并把页面级表格行为继续归属到对应页面模块。
- 文档影响：补齐本模块 `README.md`、`tests.md`、`state-machine.md` 和全局 dependency map。
- 测试覆盖：
  - 新增 `web/src/test/FinanceTable.test.tsx`，覆盖 `FinanceTablePagination` clamp/summary/disabled/callback，以及 `TableCellStack`、`AmountCell`、`FinanceDirectionTag`、`FinanceStatusTag`、`EmptyValue` 的稳定 class/data contract。
- 验证命令：
  - `cd web && npm test -- --run src/test/FinanceTable.test.tsx`
- 未测风险：真实大数据浏览器滚动、超宽列、浏览器下载保存行为；页面级 wrapper 未全部统一到共享 `FinanceTable`，需由页面模块持续保护。
- 后续事项：任何页面表格迁移必须按 `docs/refactor-ui/table_layout_system.md` 的 checklist 先列旧功能入口并补旧行为回归。

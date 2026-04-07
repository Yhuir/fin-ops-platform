# 开发 Prompt 使用说明

这些 prompt 按推荐顺序拆分，目标是让编码代理逐步构建系统，而不是一次性生成一个大而散的版本。

推荐使用顺序：

1. `01-foundation.md`
2. `02-import-normalization.md`
3. `03-auto-matching-engine.md`
4. `04-manual-reconciliation-workbench.md`
5. `05-ledger-and-reminders.md`
6. `06-advanced-exceptions.md`
7. `07-oa-integration-foundation.md`
8. `08-project-costing-foundation.md`
9. `09-workbench-v2-web-foundation.md`
10. `10-workbench-v2-layout-and-resize.md`
11. `11-workbench-v2-row-selection-and-drawer.md`
12. `12-workbench-v2-bank-and-invoice-actions.md`
13. `13-tax-offset-workbench.md`
14. `14-workbench-v2-backend-contracts.md`
15. `15-workbench-v2-integration-and-qa.md`
16. `16-cost-statistics-backend-foundation.md`
17. `17-cost-statistics-page-and-drilldown.md`
18. `18-cost-statistics-export-and-qa.md`
19. `19-project-detail-export-foundation.md`
20. `20-project-detail-export-ux.md`
21. `21-project-detail-export-history-and-qa.md`
22. `22-workbench-global-search-backend-foundation.md`
23. `23-workbench-global-search-modal-and-navigation.md`
24. `24-workbench-global-search-polish-and-qa.md`
25. `25-tax-offset-certified-foundation.md`
26. `26-tax-offset-plan-and-certified-drawer-ui.md`
27. `27-tax-offset-certified-integration-and-qa.md`
28. `28-oa-shell-auth-foundation.md`
29. `29-oa-menu-iframe-integration.md`
30. `30-oa-visibility-and-access-control.md`
31. `31-oa-integration-deployment-and-qa.md`

使用方式建议：

- 一次只执行一个 prompt
- 每个 prompt 完成后先做代码评审和验收，再进入下一个
- 后续 prompt 默认建立在前一个 prompt 已完成的基础上
- 如果中途技术栈已确定，执行 prompt 时优先遵循现有仓库技术栈

Workbench V2 这一组 prompt 对应的需求与文档：

- 需求源：[银企核销需求.md](/Users/yu/Desktop/fin-ops-platform/银企核销需求.md)
- 开发文档：[docs/dev/README.md](/Users/yu/Desktop/fin-ops-platform/docs/dev/README.md)
- 实现计划：[2026-03-25-reconciliation-workbench-v2.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-03-25-reconciliation-workbench-v2.md)

成本统计这一组 prompt 对应的需求与文档：

- 需求源：[银企核销需求.md](/Users/yu/Desktop/fin-ops-platform/银企核销需求.md)
- 开发文档：[cost-statistics-workbench.md](/Users/yu/Desktop/fin-ops-platform/docs/dev/cost-statistics-workbench.md)
- 设计文档：[2026-04-01-cost-statistics-workbench-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-01-cost-statistics-workbench-design.md)
- 强导出设计文档：[2026-04-01-cost-statistics-project-export-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-01-cost-statistics-project-export-design.md)
- 实施计划：[2026-04-01-cost-statistics-workbench.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-01-cost-statistics-workbench.md)

关联台强搜索这一组 prompt 对应的需求与文档：

- 需求源：[银企核销需求.md](/Users/yu/Desktop/fin-ops-platform/银企核销需求.md)
- 设计文档：[2026-04-02-workbench-global-search-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-02-workbench-global-search-design.md)
- 实施计划：[2026-04-02-workbench-global-search.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-02-workbench-global-search.md)

税金抵扣“计划 vs 已认证结果”这一组 prompt 对应的需求与文档：

- 参考文件：[发票认证模块.xlsx](/Users/yu/Desktop/fin-ops-platform/测试数据/发票认证模块.xlsx)
- 设计文档：[2026-04-03-tax-offset-certified-plan-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-03-tax-offset-certified-plan-design.md)
- 实施计划：[2026-04-03-tax-offset-certified-plan.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-03-tax-offset-certified-plan.md)
- 当前实现口径：销项票只读、进项票做认证计划、已认证结果进入右侧抽屉并自动计入试算

OA 页面壳体 / 登录复用 / 可见性控制这一组 prompt 对应的需求与文档：

- 总方案文档：[OA 集成当前 app 技术方案.md](/Users/yu/Desktop/fin-ops-platform/OA%20%E9%9B%86%E6%88%90%E5%BD%93%E5%89%8D%20app%20%E6%8A%80%E6%9C%AF%E6%96%B9%E6%A1%88.md)
- 设计文档：[2026-04-03-oa-shell-auth-visibility-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-03-oa-shell-auth-visibility-design.md)
- 实施计划：[2026-04-03-oa-shell-auth-visibility.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-03-oa-shell-auth-visibility.md)
- 外部 OA 前端源码：`/Users/yu/Desktop/sy/smart-oa-ui`
- 外部 OA 后端源码：`/Users/yu/Desktop/sy/smart_oa`

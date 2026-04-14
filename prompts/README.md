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
32. `32-tax-offset-certified-import-parser-and-storage.md`
33. `33-tax-offset-certified-import-matching-and-refresh.md`
34. `34-tax-offset-certified-import-ui-and-qa.md`
35. `35-oa-access-role-backend-foundation.md`
36. `36-oa-access-role-ui-and-action-gating.md`
37. `37-oa-access-role-sync-and-qa.md`
38. `38-workbench-pair-relations-foundation.md`
39. `39-workbench-pair-relations-actions-and-read-model.md`
40. `40-workbench-pair-relations-ui-perf-and-qa.md`
41. `41-workbench-read-model-foundation.md`
42. `42-workbench-read-model-actions-and-refresh.md`
43. `43-workbench-read-model-ui-perf-and-qa.md`
44. `44-workbench-pane-search-filter-foundation.md`
45. `45-workbench-pane-search-filter-ui.md`
46. `46-workbench-pane-sort-and-qa.md`
47. `47-workbench-column-layout-foundation.md`
48. `48-workbench-column-layout-rendering-and-drag-ui.md`
49. `49-workbench-column-layout-save-and-qa.md`
50. `50-settings-data-reset-backend-foundation.md`
51. `51-settings-data-reset-ui-and-oa-rebuild.md`
52. `52-settings-data-reset-integration-and-qa.md`

使用方式建议：

- 一次只执行一个 prompt
- 每个 prompt 完成后先做代码评审和验收，再进入下一个
- 后续 prompt 默认建立在前一个 prompt 已完成的基础上
- 如果中途技术栈已确定，执行 prompt 时优先遵循现有仓库技术栈

Workbench V2 这一组 prompt 对应的需求与文档：

- 需求源：[银企核销需求.md](/Users/yu/Desktop/fin-ops-platform/docs/product/银企核销需求.md)
- 开发文档：[docs/dev/README.md](/Users/yu/Desktop/fin-ops-platform/docs/dev/README.md)
- 实现计划：[2026-03-25-reconciliation-workbench-v2.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-03-25-reconciliation-workbench-v2.md)

成本统计这一组 prompt 对应的需求与文档：

- 需求源：[银企核销需求.md](/Users/yu/Desktop/fin-ops-platform/docs/product/银企核销需求.md)
- 开发文档：[cost-statistics-workbench.md](/Users/yu/Desktop/fin-ops-platform/docs/dev/cost-statistics-workbench.md)
- 设计文档：[2026-04-01-cost-statistics-workbench-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-01-cost-statistics-workbench-design.md)
- 强导出设计文档：[2026-04-01-cost-statistics-project-export-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-01-cost-statistics-project-export-design.md)
- 实施计划：[2026-04-01-cost-statistics-workbench.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-01-cost-statistics-workbench.md)

关联台强搜索这一组 prompt 对应的需求与文档：

- 需求源：[银企核销需求.md](/Users/yu/Desktop/fin-ops-platform/docs/product/银企核销需求.md)
- 设计文档：[2026-04-02-workbench-global-search-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-02-workbench-global-search-design.md)
- 实施计划：[2026-04-02-workbench-global-search.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-02-workbench-global-search.md)

税金抵扣“计划 vs 已认证结果”这一组 prompt 对应的需求与文档：

- 参考文件：[发票认证模块.xlsx](/Users/yu/Desktop/fin-ops-platform/fixtures/测试数据/发票认证模块.xlsx)
- 设计文档：[2026-04-03-tax-offset-certified-plan-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-03-tax-offset-certified-plan-design.md)
- 实施计划：[2026-04-03-tax-offset-certified-plan.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-03-tax-offset-certified-plan.md)
- 当前实现口径：销项票只读、进项票做认证计划、已认证结果进入右侧抽屉并自动计入试算

税金抵扣“真实已认证模板导入”这一组 prompt 对应的需求与文档：

- 参考文件：
  - [2026年1月 进项认证结果  用途确认信息.xlsx](/Users/yu/Desktop/fin-ops-platform/fixtures/测试数据/2026年1月%20进项认证结果%20%20用途确认信息.xlsx)
  - [2026年2月 进项认证结果  用途确认信息.xlsx](/Users/yu/Desktop/fin-ops-platform/fixtures/测试数据/2026年2月%20进项认证结果%20%20用途确认信息.xlsx)
- 设计文档：[2026-04-07-tax-offset-certified-import-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-07-tax-offset-certified-import-design.md)
- 实施计划：[2026-04-07-tax-offset-certified-import.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-07-tax-offset-certified-import.md)
- 当前目标：让已认证结果来自真实 Excel 导入与持久化，而不是后端写死样例

OA 页面壳体 / 登录复用 / 可见性控制这一组 prompt 对应的需求与文档：

- 总方案文档：[OA 集成当前 app 技术方案.md](/Users/yu/Desktop/fin-ops-platform/docs/architecture/OA%20%E9%9B%86%E6%88%90%E5%BD%93%E5%89%8D%20app%20%E6%8A%80%E6%9C%AF%E6%96%B9%E6%A1%88.md)
- 设计文档：[2026-04-03-oa-shell-auth-visibility-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-03-oa-shell-auth-visibility-design.md)
- 实施计划：[2026-04-03-oa-shell-auth-visibility.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-03-oa-shell-auth-visibility.md)
- 外部 OA 前端源码：`/Users/yu/Desktop/sy/smart-oa-ui`
- 外部 OA 后端源码：`/Users/yu/Desktop/sy/smart_oa`

OA “访问账户管理 / 只读导出 / 管理员独占权限”这一组 prompt 对应的需求与文档：

- 需求源：[银企核销需求.md](/Users/yu/Desktop/fin-ops-platform/docs/product/银企核销需求.md)
- 总方案文档：[OA 集成当前 app 技术方案.md](/Users/yu/Desktop/fin-ops-platform/docs/architecture/OA%20%E9%9B%86%E6%88%90%E5%BD%93%E5%89%8D%20app%20%E6%8A%80%E6%9C%AF%E6%96%B9%E6%A1%88.md)
- 设计文档：[2026-04-07-oa-access-role-management-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-07-oa-access-role-management-design.md)
- 实施计划：[2026-04-07-oa-access-role-management.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-07-oa-access-role-management.md)
- 关键业务口径：
  - 不可见且不可访问
  - 可见且可访问，但分为 `所有操作均可` / `只可看和只可导出`
  - 只有 `YNSYLP005` 可管理权限

关联台“pair relations 轻量写模型 / 确认关联取消配对加速”这一组 prompt 对应的需求与文档：

- 需求源：[银企核销需求.md](/Users/yu/Desktop/fin-ops-platform/docs/product/银企核销需求.md)
- 设计文档：[2026-04-08-workbench-pair-relations-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-08-workbench-pair-relations-design.md)
- 实施计划：[2026-04-08-workbench-pair-relations.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-08-workbench-pair-relations.md)
- 当前目标：
  - 配对关系独立建模
  - `确认关联 / 取消配对` 只改 pair relation
  - 前端成功后立即局部更新，后台静默刷新兜底

关联台“pair relations + 物化 read model”这一组 prompt 对应的需求与文档：

- 需求源：[银企核销需求.md](/Users/yu/Desktop/fin-ops-platform/docs/product/银企核销需求.md)
- 设计文档：[2026-04-08-workbench-materialized-read-model-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-08-workbench-materialized-read-model-design.md)
- 实施计划：[2026-04-08-workbench-materialized-read-model.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-08-workbench-materialized-read-model.md)
- 当前目标：
  - 写动作只改最小状态
  - 页面加载优先读缓存好的关联台快照
  - `确认关联 / 取消配对` 与整页 load 都明显提速

关联台“三栏局部搜索 / 筛选 / 排序”这一组 prompt 对应的需求与文档：

- 需求源：[银企核销需求.md](/Users/yu/Desktop/fin-ops-platform/docs/product/银企核销需求.md)
- 设计文档：[2026-04-08-workbench-pane-search-filter-sort-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-08-workbench-pane-search-filter-sort-design.md)
- 实施计划：[2026-04-08-workbench-pane-search-filter-sort.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-08-workbench-pane-search-filter-sort.md)
- 当前目标：
  - 三栏支持栏级实时搜索
  - 列级多选筛选
  - 银行流水 / 发票按组时间排序
  - 当前栏驱动、整组三栏联动显示

关联台“三栏列拖拽排序 / 持久化”这一组 prompt 对应的需求与文档：

- 需求源：[银企核销需求.md](/Users/yu/Desktop/fin-ops-platform/docs/product/银企核销需求.md)
- 设计文档：[2026-04-08-workbench-column-layout-drag-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-08-workbench-column-layout-drag-design.md)
- 实施计划：[2026-04-08-workbench-column-layout-drag.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-08-workbench-column-layout-drag.md)
- 当前目标：
  - 三栏列头支持拖拽重排
  - 每栏列顺序独立保存
  - 登录后恢复上次保存的列排列
  - 列宽变化后表头、内容和滚动轨道继续对齐

设置页“数据清理 / OA 模式 B 重刷”这一组 prompt 对应的需求与文档：

- 需求源：[银企核销需求.md](/Users/yu/Desktop/fin-ops-platform/docs/product/银企核销需求.md)
- 设计文档：[2026-04-14-settings-data-reset-tools-design.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/specs/2026-04-14-settings-data-reset-tools-design.md)
- 实施计划：[2026-04-14-settings-data-reset-tools.md](/Users/yu/Desktop/fin-ops-platform/docs/superpowers/plans/2026-04-14-settings-data-reset-tools.md)
- 当前目标：
  - 设置页新增高风险数据重置工具
  - 只清 `fin_ops_platform_app`
  - 明确禁止改动 `form_data_db.form_data`
  - 三个危险按钮执行前都必须输入当前 OA 用户密码并由后端复核，密码不得保存、写日志、写审计明文或出现在错误响应中
  - 未输入 / 输错 OA 密码时不执行清理、不失效缓存、不触发 OA 重建
  - `清 OA` 固定采用模式 B：彻底重刷 OA 相关状态
  - Prompt 52 已补集成 QA：三类删表边界、`oa_retention.cutoff_date` 重建、管理员可见性与密码泄露防护

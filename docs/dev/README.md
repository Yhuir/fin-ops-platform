# 开发文档索引

这组文档面向真正开始实现 `OA & 银行流水 & 进销项发票关联台` 的工程阶段，默认建立在以下输入之上：

- 业务需求源：[银企核销需求.md](/Users/yu/Desktop/fin-ops-platform/docs/product/银企核销需求.md)
- 当前交互原型：[reconciliation-workbench-v2.html](/Users/yu/Desktop/fin-ops-platform/web/prototypes/reconciliation-workbench-v2.html)

推荐阅读顺序：

1. `reconciliation-workbench-v2-overview.md`
2. `reconciliation-workbench-v2-frontend.md`
3. `reconciliation-workbench-v2-backend.md`
4. `reconciliation-workbench-v2-data-contracts.md`
5. `reconciliation-workbench-v2-testing.md`
6. `../superpowers/plans/2026-03-25-reconciliation-workbench-v2.md`
7. `import-normalization-samples.md`
8. `auto-matching-engine-samples.md`
9. `ledger-and-reminder-rules.md`
10. `advanced-exception-rules.md`
11. `oa-integration-foundation.md`
12. `project-costing-foundation.md`
13. `cost-statistics-workbench.md`
14. `../superpowers/specs/2026-04-01-cost-statistics-workbench-design.md`
15. `../superpowers/plans/2026-04-01-cost-statistics-workbench.md`
16. `../superpowers/specs/2026-04-01-cost-statistics-project-export-design.md`
17. `../superpowers/specs/2026-03-26-import-formalization-design.md`
18. `../superpowers/plans/2026-03-26-import-formalization.md`

文件说明：

- `reconciliation-workbench-v2-overview.md`：范围、页面边界、交互口径、分期交付顺序
- `reconciliation-workbench-v2-frontend.md`：前端页面结构、组件拆分、状态设计、拖拽与抽屉交互
- `reconciliation-workbench-v2-backend.md`：后端模块、接口、适配层、种子数据与动作接口
- `reconciliation-workbench-v2-data-contracts.md`：前后端字段契约、DTO、示例响应
- `reconciliation-workbench-v2-testing.md`：测试策略、验收点、回归清单
- `../superpowers/plans/2026-03-25-reconciliation-workbench-v2.md`：完整实现计划
- `import-normalization-samples.md`：Prompt 02 的导入请求样例与验证方式
- `auto-matching-engine-samples.md`：Prompt 03 的匹配规则、接口样例与结果流转
- `ledger-and-reminder-rules.md`：Prompt 05 的台账生成规则、提醒去重策略与页面口径
- `advanced-exception-rules.md`：Prompt 06 的差额核销、红字发票与内部抵扣规则
- `oa-integration-foundation.md`：Prompt 07 的集成边界、同步范围、映射模型与真实 OA 替换点
- `project-costing-foundation.md`：Prompt 08 的项目归属优先级、汇总指标、接口和扩展路径
- `cost-statistics-workbench.md`：成本统计页的页面定位、数据口径、下钻层级、接口建议和导出要求
- `../superpowers/specs/2026-04-01-cost-statistics-workbench-design.md`：成本统计页面的整体产品与技术设计
- `../superpowers/plans/2026-04-01-cost-statistics-workbench.md`：成本统计页面的分阶段实施计划
- `../superpowers/specs/2026-04-01-cost-statistics-project-export-design.md`：项目明细强导出的工作簿结构、高级导出交互、后端导出任务和导出历史设计
- `reconciliation-workbench-v2-backend.md` 已在 Prompt 14 后更新，补充了 `/api/workbench`、`/api/tax-offset`、OA adapter 边界与统一动作结果结构
- `../superpowers/specs/2026-03-26-import-formalization-design.md`：导入正式化 A 的文件上传、模板识别、预览会话、持久化、重试撤销和前端导入中心设计
- `../superpowers/plans/2026-03-26-import-formalization.md`：导入正式化 A 的 TDD 实施计划与后续正式化收口

配套拆分 prompt 在 [prompts/README.md](/Users/yu/Desktop/fin-ops-platform/prompts/README.md) 中追加列出。

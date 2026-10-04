# 公共财务表格

入口：`共享前端组件`。

提供列布局、滚动、选择、排序事件、分页与可访问展示；业务行、筛选和网络请求仍由页面负责。

## 边界与 I/O

输入：rows/columns/actions、受控分页/排序/选择、页面隔离的 session key。输出：用户交互回调和布局，不产生业务 API 或持久化 I/O。

## 当前业务约定

- 普通页面复用 HeroUI FinanceTable，关联台专用分组表由关联台负责。
- 共享表格不解释金额或权限，不自行排序服务端数据，不保存业务 rows。
- 表头、横向滚动和 contained 容器适配窄屏；需要复制文本的消费者显式启用 selectableText。
- 普通页面通过应用壳的 `data-finance-presentation` 开启表头与正文的列语义对齐、金额主辅层级和次级按钮样式；关联台不启用此范围，来源详情键值表保持左对齐。
- 页面用业务总数而非当前页长度显示统计；金额、抽屉、搜索和分段展示遵循统一 UI 说明。
- 现金可复用纯 UI，不复用普通页面的持久 session。

公共来源详情的发票换行选择与 OA/流水横向选择、单份正文、字段来源和流水编辑保护合同见 [UI 约定](../../ui.md#oa流水与发票来源详情)。公共组件仅管理选择与展示，不拥有请求或业务状态。

## 依赖方向

[应用壳与导航](../app-shell-navigation/README.md)、[现金账](../cash/README.md)、[关联台](../reconciliation-workbench/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/components/common/FinanceTable.tsx](../../../web/src/components/common/FinanceTable.tsx)
- [web/src/hooks/useFinanceTableSession.ts](../../../web/src/hooks/useFinanceTableSession.ts)
- [web/src/app/financePresentation.css](../../../web/src/app/financePresentation.css)
- [web/e2e/finance-table-presentation.spec.ts](../../../web/e2e/finance-table-presentation.spec.ts)
- [web/src/app/styles.css](../../../web/src/app/styles.css)
- [web/src/test/FinanceTable.test.tsx](../../../web/src/test/FinanceTable.test.tsx)
- [web/src/test/TableLayoutTokens.test.ts](../../../web/src/test/TableLayoutTokens.test.ts)
- [web/src/test/TableAlignmentStyles.test.ts](../../../web/src/test/TableAlignmentStyles.test.ts)
- [web/src/test/FinanceTableMigration.test.ts](../../../web/src/test/FinanceTableMigration.test.ts)
- [web/src/test/useFinanceTableSession.test.tsx](../../../web/src/test/useFinanceTableSession.test.tsx)
- [web/src/test/MuiContainment.test.ts](../../../web/src/test/MuiContainment.test.ts)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。

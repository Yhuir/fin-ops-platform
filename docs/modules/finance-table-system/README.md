# 公共财务表格

入口：`共享前端组件`。

提供列布局、滚动、选择、排序事件、分页与可访问展示；业务行、筛选和网络请求仍由页面负责。

## 边界与 I/O

输入：rows/columns/actions、受控分页/排序/选择、页面隔离的 session key。输出：用户交互回调和布局，不产生业务 API 或持久化 I/O。

## 当前业务约定

- `PageScaffold` 的可选 `query` 放在标题统计右侧，`secondaryActions` 在紧凑头部进入“更多”；组件只管理布局及菜单，不保存查询或请求数据。四个分类列表使用 32px 控件，年月位于右侧操作区最前；桌面合并单行，窄屏换行，保持滚动条占位。普通列表不提供常驻刷新按钮，首次读取、保存后重读与失败重试仍由页面负责。

- 普通页面复用 HeroUI FinanceTable；进项发票使用表由本页原生 table 承载跨列/跨行双层表头，继续复用公共控件和财务列样式，不改变共享表格默认行为。关联台专用分组表由关联台负责。
- `TableClassificationHeader` 为待找发票、OA 核对和销项页面提供固定三层分类展示，只接收数量、区域、选中状态及点击回调，不请求 API、不计算分类。其样式与其他页面分段按钮隔离，错误数量显示未知，正常零值保留。
- 分类区域底色只表达层级；当前精确分类用内描边和勾选表达，不连带高亮父子项。四个分类页面共用选中样式，查询范围与选中判断仍归页面；不能对应单一分类的组合条件不伪造单项勾选。
- 共享表格不解释金额或权限，不自行排序服务端数据，不保存业务 rows。
- 表头、横向滚动和 contained 容器适配窄屏；需要复制文本的消费者显式启用 selectableText。
- 固定视口列表通过 PageScaffold 的 fillViewport 显式分配剩余高度，表格框架最小可用高度 240px；小窗口允许外层滚动，自然长页面不启用此布局。根滚动容器、contained 表体与公共浮层正文保留滚动条空间，页面不手工猜测滚动条宽度。
- 加载、空结果和失败保留表格结构；查询与操作有效性由页面负责，不能用旧查询结果代替新结果。外部往来款与操作历史的列宽由各自页面定义，不随状态行内容重新分配。
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

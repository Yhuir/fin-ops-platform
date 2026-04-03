# Prompt 15 设计记录

日期：2026-03-26

## 目标

把 Workbench V2 React 前端从 mock 数据切到真实 `/api/*` 契约，并补齐验收所需的加载、空态、错态和联调说明。

## 关键设计

### 1. 保留组件，替换数据源

不重写 Prompt 10-13 的组件结构，继续沿用：

- `WorkbenchZone`
- `ResizableTriPane`
- `PaneTable`
- `DetailDrawer`
- `TaxSummaryCards`
- `TaxTable`

只把页面数据源替换成真实接口。

### 2. 引入 API adapter 层

新增：

- `web/src/features/workbench/api.ts`
- `web/src/features/tax/api.ts`

理由：

- 后端是 snake_case DTO
- 现有表格和抽屉都是 camelCase view-model
- adapter 层可以把 DTO 变化收口，不污染组件

### 3. 详情抽屉按需加载

详情按钮点击后：

1. 先选中当前行并打开抽屉
2. 再请求 `/api/workbench/rows/{row_id}`
3. 返回后替换抽屉内容

这样既满足“按行加载”，又不让抽屉交互显得卡顿。

### 4. 税金页改成后端驱动

税金页不再本地重算，而是：

- 首次进入请求 `GET /api/tax-offset`
- 勾选变化请求 `POST /api/tax-offset/calculate`

## 非目标

- 不做浏览器级 E2E
- 不新增新的工作台视觉方案
- 不把 `关联情况` 补成新的后端接口

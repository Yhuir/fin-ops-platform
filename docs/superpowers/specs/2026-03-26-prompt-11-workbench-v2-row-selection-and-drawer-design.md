# Prompt 11 Workbench V2 Row Selection And Drawer Design

## Goal

实现工作台核心交互口径：点击行只选中并联动高亮同 `caseId` 记录，详情只能通过行内 `详情` 按钮打开右侧抽屉。

## Scope

本次只覆盖以下内容：

- 为 mock 记录补 `caseId` 和详情字段
- 页面级选中状态
- 同 `caseId` 候选联动高亮
- 行内 `详情` 按钮
- 右侧详情抽屉
- 不同类型记录的详情展示

本次不做：

- 真实接口详情请求
- 编辑详情字段
- 详情抽屉内的核销动作
- 批量选中

## Design

### 1. Selection Scope

选中和联动范围以整个工作台页面为单位，不区分 `已配对` 和 `未配对` zone。

规则：

- 点击任意一行，只更新当前选中记录
- 当前选中记录使用更深的蓝色高亮
- 与它 `caseId` 相同的其他记录使用浅蓝色高亮
- 若记录没有 `caseId`，则只有当前行高亮，不产生候选联动

### 2. State Ownership

新增 `useWorkbenchSelection.ts`，由页面统一维护：

- `selectedRowId`
- `selectedCaseId`
- `detailRow`

组件只消费状态和回调，不在 pane 内各自保存选中态。这样后续接真实核销动作和详情接口时，不会出现跨 pane 状态碎片。

### 3. Table Interaction

`PaneTable` 的交互口径固定为：

- 点击 `tr`：只调用 `onSelectRow`
- 点击 `详情` 按钮：
  - `stopPropagation`
  - 调用 `onOpenDetail`
  - 不影响“点击行不弹详情”的规则

表格主列继续只保留直接字段，详情字段不进主表。

### 4. Detail Drawer

新增 `DetailDrawer.tsx`，固定停靠在页面右侧。

抽屉能力：

- 根据当前 `detailRow` 打开 / 关闭
- 支持关闭
- 支持切换不同记录
- 按记录类型展示不同详情字段：
  - OA
  - 银行流水
  - 发票

### 5. Mock Data

为工作台 mock 数据补字段：

- `caseId`
- `recordType`
- `summaryFields`
- `detailFields`

这样可以在不接后端的前提下先把交互链路做完整。

## Impact

### New Files

- `web/src/components/workbench/RowActions.tsx`
- `web/src/components/workbench/DetailDrawer.tsx`
- `web/src/hooks/useWorkbenchSelection.ts`
- `web/src/test/WorkbenchSelection.test.tsx`

### Modified Files

- `web/src/features/workbench/mockData.ts`
- `web/src/components/workbench/PaneTable.tsx`
- `web/src/components/workbench/ResizableTriPane.tsx`
- `web/src/components/workbench/WorkbenchZone.tsx`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/app/styles.css`
- `web/README.md`
- `README.md`

## Testing

至少覆盖：

- 点击行只更新选中态，不打开详情抽屉
- 点击 `详情` 按钮会打开抽屉
- 同 `caseId` 记录联动高亮
- 抽屉可关闭
- 前端测试与构建继续通过

# Prompt 10 Workbench V2 Layout And Resize Design

## Goal

把 React 版工作台升级为真正的上下两区、三栏 Excel 风格布局，并支持完整拖拽、独立收起与恢复。

## Scope

本次只覆盖以下内容：

- 工作台拆成两个 zone：
  - 已配对
  - 未配对
- 每个 zone 固定三栏：
  - OA
  - 银行流水
  - 进项 / 销项发票
- 每个 zone 各自独立拖拽和收起
- splitter 可拖到 `0` 宽
- 当前 zone 头部按钮可恢复被收起的栏
- 各栏独立滚动，表头固定

本次不做：

- 详情抽屉
- 行选中联动
- 后端接口接入
- 重型 grid/table 库

## Design

### 1. State Ownership

本次不采用共享宽度状态。

每个 zone 都有自己的一套三栏宽度：

- 上面的 `已配对` 独立维护
- 下面的 `未配对` 独立维护

因此：

- 上面拖拽不会影响下面
- 上面收起 OA，不会同步收起下面的 OA
- 恢复按钮也只作用于当前 zone

### 2. Technical Approach

继续使用：

- 原生 `table`
- `CSS Grid`
- `Pointer Events`

不引入 `AG Grid`、`Handsontable` 等重型库。原因是当前工作台不是单一数据表，而是“两个 zone + 三栏 + splitter + 后续行内动作”的组合工作台，重型表格库会放大后续定制成本。

### 3. Component Split

新增四个清晰单元：

- `useResizablePanes.ts`
  - 管理当前 zone 的宽度、拖拽、收起、恢复
- `ResizableTriPane.tsx`
  - 根据当前可见栏位，渲染 pane 和 splitter
- `WorkbenchZone.tsx`
  - 渲染 zone 头部、恢复按钮和三栏容器
- `PaneTable.tsx`
  - 渲染单栏表格和固定表头

这样 `ReconciliationWorkbenchPage` 只负责页面级排版，不再直接持有三栏内部实现。

### 4. Splitter Behavior

splitter 规则：

- 只显示在当前可见栏之间
- 三栏可见时显示两条 splitter
- 两栏可见时显示一条 splitter
- 一栏可见时不显示 splitter

拖拽规则：

- 可一路拖到 `0`
- 到 `0` 后当前栏视为收起
- 被拖到 `0` 的栏不再渲染内容区

### 5. Recovery Behavior

每个 zone 头部都有三枚按钮：

- `OA`
- `银行流水`
- `进销项发票`

按钮行为：

- 当前栏可见时，点击可收起该栏，但至少保留一栏可见
- 当前栏已收起时，点击可恢复为默认宽度
- 恢复只作用于当前 zone

因此可以切到：

- 只看一栏
- 看两栏
- 看三栏

### 6. Scroll And Header Behavior

每栏独立滚动：

- pane 自身固定高度
- 表格内容区滚动
- `thead` sticky 固定

这样上下两个 zone 不会因为单栏内容过长把整体布局顶乱。

## Impact

### New Files

- `web/src/components/workbench/PaneTable.tsx`
- `web/src/components/workbench/ResizableTriPane.tsx`
- `web/src/components/workbench/WorkbenchZone.tsx`
- `web/src/hooks/useResizablePanes.ts`
- `web/src/test/WorkbenchZone.test.tsx`

### Modified Files

- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/app/styles.css`
- `web/README.md`
- `README.md`

## Testing

至少覆盖：

- zone 内按钮可收起并恢复 pane
- 仅剩一栏时不显示 splitter
- splitter 拖拽可改变宽度
- splitter 拖到边界时可把 pane 收起
- 工程测试与构建继续通过

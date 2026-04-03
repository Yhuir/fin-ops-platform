# Prompt 12 Workbench V2 Bank And Invoice Actions Design

## Goal

把工作台三栏主表字段和行内动作补齐到需求文档口径，同时保持 Excel 风格和横向滚动能力。

## Scope

本次只覆盖以下内容：

- OA / 银行 / 发票主表字段补齐
- 按列配置渲染三栏表格
- 银行行内动作：
  - 详情
  - 关联情况
  - 取消关联
  - 异常处理
- OA / 发票未配对行行内动作：
  - 确认关联
  - 标记异常
- 主表横向滚动与动作列稳定布局

本次不做：

- 真实接口动作提交
- 后端状态落库
- 复杂操作弹窗
- 行内编辑

## Design

### 1. Main Table Strategy

继续保持 `table`，不改卡片。

表格改为“列配置驱动”：

- 每个 pane 自带一组 `columns`
- `PaneTable` 只按配置渲染字段
- 各栏主表字段严格对齐需求文档

这样 `12` 只是补字段契约，不会把 `PaneTable` 继续堆成大量 `if/else`。

### 2. Data Model

为 mock 数据新增：

- `tableFields`
- `actionVariant`

其中：

- OA 记录主表字段对应：
  - 申请人
  - 项目名称
  - 申请类型
  - 金额
  - 对方户名
  - 申请事由
  - OA 和流水关联情况
- 银行记录主表字段对应：
  - 交易时间
  - 借方发生额
  - 贷方发生额
  - 对方户名
  - 支付账户
  - 和发票关联情况
  - 支付 / 收款时间
  - 备注
  - 还借款日期
- 发票记录主表字段对应：
  - 销方识别号
  - 销方名称
  - 购方识别号
  - 购买方名称
  - 开票日期
  - 金额
  - 税率
  - 税额
  - 价税合计
  - 发票类型

### 3. Action Strategy

行内动作保持轻量：

- 银行栏：
  - `详情` 按钮单独保留
  - `关联情况 / 取消关联 / 异常处理` 进入 `更多` 下拉
- OA / 发票未配对行：
  - `详情`
  - `确认关联`
  - `标记异常`
- 已配对 OA / 发票：
  - 只保留 `详情`

动作本轮先走前端 mock 回调，不接真实后端。

### 4. Layout And Overflow

由于列数明显变多：

- 各 pane 继续纵向独立滚动
- 表格支持横向滚动
- 动作列 sticky 在右侧，避免大量字段时操作入口丢失
- 状态类字段继续保留标签化视觉

## Impact

### New Files

- `web/src/features/workbench/tableConfig.ts`
- `web/src/test/WorkbenchColumns.test.tsx`

### Modified Files

- `web/src/features/workbench/mockData.ts`
- `web/src/components/workbench/PaneTable.tsx`
- `web/src/components/workbench/RowActions.tsx`
- `web/src/components/workbench/ResizableTriPane.tsx`
- `web/src/components/workbench/WorkbenchZone.tsx`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/app/styles.css`
- `web/README.md`
- `README.md`

## Testing

至少覆盖：

- OA / 银行 / 发票主表列标题出现
- 银行行内存在 `详情` 和 `更多`
- OA / 发票未配对行存在 `确认关联` 和 `标记异常`
- 前端测试与构建继续通过

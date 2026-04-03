# Prompt 13 Tax Offset Workbench Design

## Goal

把 `销项票税金 - 进项票税金` 从静态展示页补成可交互的税金抵扣工作台，并和全局月份上下文保持一致。

## Scope

本次覆盖：

- 税金页按月份切换数据
- 销项票 / 进项票两张税金清单
- 行勾选与实时税金试算
- 本月抵扣额、应纳税额 / 留抵税额动态展示
- 页面内 `返回关联台` 入口

本次不做：

- 真实后端税金接口
- 抵扣结果落库
- 税金申报流转
- 跨月结转规则

## Design

### 1. Data Strategy

税金 mock 数据改成按月组织：

- `2026-03`
- `2026-04`

每个月包含：

- `outputInvoices`
- `inputInvoices`

并提供统一计算函数：

- 金额解析
- 金额格式化
- 税金试算结果输出

### 2. Selection Model

页面进入某个月时，默认全选该月全部销项票和进项票。

勾选状态分成两组：

- `selectedOutputIds`
- `selectedInputIds`

切换月份后重置为新月份的默认全选，避免跨月把上个月的勾选残留到当前月。

### 3. Page Composition

税金页拆成三个子组件：

- `TaxSummaryCards`
- `TaxTable`
- `TaxResultPanel`

页面结构：

1. 页头：标题、当前月份、返回关联台
2. 摘要卡片：销项税额、进项税额、本月抵扣额、应纳税额 / 留抵税额
3. 结果面板：说明当前已选票数和试算结果
4. 左右两张清单表：销项票税金清单、进项票税金清单

### 4. Calculation Rules

- `销项税额`：当前已选销项票税额合计
- `进项税额`：当前已选进项票税额合计
- `本月抵扣额`：`min(销项税额, 进项税额)`
- 如果 `销项税额 >= 进项税额`
  - 展示 `本月应纳税额 = 销项税额 - 本月抵扣额`
- 否则
  - 展示 `本月留抵税额 = 进项税额 - 本月抵扣额`

## Impact

### New Files

- `web/src/components/tax/TaxSummaryCards.tsx`
- `web/src/components/tax/TaxTable.tsx`
- `web/src/components/tax/TaxResultPanel.tsx`
- `web/src/test/TaxOffsetPage.test.tsx`

### Modified Files

- `web/src/features/tax/mockData.ts`
- `web/src/pages/TaxOffsetPage.tsx`
- `web/src/app/styles.css`
- `web/README.md`
- `README.md`

## Testing

至少覆盖：

- 取消勾选进项票后税金摘要实时重算
- 切换月份后税金清单切到新月份数据
- 从税金页返回主工作台时，全局月份保持不变
- 全量前端测试和构建继续通过

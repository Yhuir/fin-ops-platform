# 260622-oal - OA 待付款表格 OA 区域五列压缩

## 目标

- 在 OA 待付款核对表格的 OA 大列内新增“申请事由”和“对方户名”两个小列。
- 将 OA 内部“申请人”列约压缩到原来的 2/3，并将“发票”大列从 20% 收窄到 13%。
- 通过更紧凑的字号、间距和列宽配置，保持真实浏览器下无需横向滑动即可看到完整四分组表格。

## 范围

- 前端表格组件：`web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx`
- 前端类型：`web/src/features/oaPendingPayments/types.ts`
- 全局样式：`web/src/app/styles.css`
- 前端回归测试：`web/src/test/OaPendingPaymentsPage.test.tsx`
- 模块文档：`docs/modules/oa-pending-payments/*`

## 约束

- 不改后端 API。后端 rows 已返回 `oa.reason` 和 `oa.counterpartyName`。
- 不新增不存在的筛选字段；申请事由和 OA 对方户名只展示，不参与筛选。
- 不改变自动匹配、自动写回、支出流水抽屉、详情抽屉和状态机语义。

## 验收

- 表头 OA 子列显示“申请人 / 项目 / 申请事由 / 对方户名 / 金额”。
- 第一行 OA 单元格能展示申请事由和对方户名。
- CSS contract 锁定发票列 13%、支付状态列 8%、表格字号 10.5px、OA 内部五列 grid。
- `web/e2e/oa-pending-payments-flow.spec.ts` 的无横向滚动断言继续通过。

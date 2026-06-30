# 2026-06-30 OA 待付款月份选择器全部视图

## GSD UI 合同

- 范围：`/oa-pending-payments` 页面顶部月份筛选控件。
- 决策：把“全部”和原生 `type="month"` 合并成同一个分段式月份选择器。
- 数据合同：全部月份继续使用空 `month` 查询值；具体月份继续使用 `YYYY-MM`，不新增 API 字段。
- 交互：默认选中“全部”；选择月份后取消“全部”高亮并请求该月份；点击“全部”清空月份并回到 all scope。
- 样式：沿用现有 OA 待付款控件高度、边框、字体和 focus 状态；移动端单列不溢出。

## 验收

- 初始 rows/filter-options 请求不携带 `month`。
- 选择 `2026-04` 后 rows 请求携带 `month=2026-04`。
- 点击“全部”后 rows 请求不再携带 `month`。
- 不改变 read model、worker、API response shape 或模块边界。

## 验证计划

- `cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`
- `cd web && npm run build`

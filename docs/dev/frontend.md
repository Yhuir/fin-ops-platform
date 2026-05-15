# 前端开发

## 结构

```text
web/src/
  pages/       页面入口
  features/    API client、领域类型和功能模块
  components/  可复用组件
  contexts/    全局状态和健康状态
  test/        前端测试
```

## 主要页面

- `ReconciliationWorkbenchPage.tsx`：关联工作台。
- `BankDetailsPage.tsx`：银行明细。
- `CostStatisticsPage.tsx`：成本统计。
- `TaxOffsetPage.tsx`：税金抵扣。
- `SettingsPage` 相关组件：设置页。

## API 约定

- API client 应在 `web/src/features/*/api.ts`。
- 请求必须携带 OA token 和 credentials，具体封装沿用现有 feature API。
- HTML 响应通常意味着反向代理或路由错误，要给出明确错误提示。
- 写操作成功后按后端返回的 affected months/rows 进行局部刷新或全量刷新。

## UI 约束

- 财务工作台优先表格、分栏、抽屉和紧凑操作。
- 不把业务事实存在 local state 作为唯一来源。
- 只读导出权限要隐藏写入口，但不能替代后端权限校验。
- 长任务要显示后台任务进度，不让用户误以为页面卡死。

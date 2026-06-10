# OA待付款核对 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 不适用（纯前端布局时） | N/A | 业务规则、金额计算、状态流转、权限、去重、幂等未变化时不需要。 |
| 2. Service-layer tests | 不适用（纯前端布局时） | N/A | service、repository、audit、read model、cache、worker 编排未变化时不需要。 |
| 3. API contract tests | 不适用（纯前端布局时） | N/A | HTTP/API contract、DTO shape、错误字段和权限响应未变化时不需要。 |
| 4. Read model/cache/background job tests | 不适用（纯前端布局时） | N/A | read model freshness、cache、worker、dirty scope 和后台刷新未变化时不需要。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/OaPendingPaymentsPage.test.tsx` | 覆盖页面渲染、分组表格、筛选/排序、详情抽屉、规则抽屉、空状态和银行金额/方向 chip 非重叠布局。 |
| 6. End-to-end business-flow integration tests | 不适用（纯前端布局时） | N/A | 未跨导入、关系确认、后台任务、read model 刷新等业务链路。 |
| 7. Existing feature regression tests | 适用 | `web/src/test/OaPendingPaymentsPage.test.tsx`; `web/src/test/TableAlignmentStyles.test.ts` | 保护既有表格 CSS 契约、页面交互、筛选/排序参数和共享财务表格对齐样式。 |

## 现有验证命令

```bash
cd web && npx vitest run src/test/OaPendingPaymentsPage.test.tsx
cd web && npx vitest run src/test/TableAlignmentStyles.test.ts
cd web && npm run build
```

## 未测风险

- 纯前端布局修复不覆盖真实浏览器像素级截图差异；必要时在本地 dev server 打开 `/oa-pending-payments` 做人工视觉确认。

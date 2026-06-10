# OA待付款核对 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 不适用 | N/A | 本模块当前变更仅调整 OA 行 DTO 展示字段和前端空流水呈现；业务规则、金额计算、状态流转、权限、去重、幂等未变化。 |
| 2. Service-layer tests | 适用 | `tests/test_oa_pending_payment_service.py` | 覆盖 `OaPendingPaymentQueryService` 从 OA 明细字段提取 `applicationTime` 并写入行 payload 的服务层契约。 |
| 3. API contract tests | 适用 | `tests/test_oa_pending_payment_service.py`; `tests/test_oa_pending_payment_api.py` | 行 DTO 新增 `oa.applicationTime`，需要保护 API/服务返回 shape 及既有查询契约。 |
| 4. Read model/cache/background job tests | 不适用 | N/A | read model schema、freshness gateway、cache、worker、dirty scope 和后台刷新未变化时不需要。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/OaPendingPaymentsPage.test.tsx` | 覆盖页面渲染、分组表格、筛选/排序、详情抽屉、规则抽屉、空状态、OA 时间 chip、无支出流水仅显示 `-` 和银行金额/方向 chip 非重叠布局。 |
| 6. End-to-end business-flow integration tests | 不适用 | N/A | 未跨导入、关系确认、后台任务、read model 刷新等业务链路。 |
| 7. Existing feature regression tests | 适用 | `tests/test_oa_pending_payment_service.py`; `tests/test_oa_pending_payment_api.py`; `web/src/test/OaPendingPaymentsPage.test.tsx`; `web/src/test/TableAlignmentStyles.test.ts` | 保护既有行状态、查询参数、API shape、表格 CSS 契约、页面交互、筛选/排序参数和共享财务表格对齐样式。 |

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_api
cd web && npx vitest run src/test/OaPendingPaymentsPage.test.tsx
cd web && npx vitest run src/test/TableAlignmentStyles.test.ts
cd web && npm run build
```

## 未测风险

- 自动化组件测试不覆盖真实浏览器像素级截图差异；必要时在本地 dev server 打开 `/oa-pending-payments` 做人工视觉确认。
- 本次 DTO 只在既有 OA 行 payload 增加展示字段，不修改 read model schema、freshness gateway、dirty scope 或 worker registry。

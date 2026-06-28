# 税金抵扣 Spec-first E2E Coverage

本文件把 `tax-offset` 的 Spec ID 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `TAX-E2E-001` | `covered` | `web/e2e/tax-offset-flow.spec.ts`、`tests/test_tax_offset_api.py`、`web/src/test/TaxOffsetPage.test.tsx` | Browser 覆盖 direct 首屏、统计卡、销项/进项 grid 和已认证 drawer 基础展示。 |
| `TAX-E2E-002` | `covered` | `web/e2e/tax-offset-flow.spec.ts`、`tests/test_tax_offset_service.py`、`web/src/test/TaxOffsetPage.test.tsx` | Browser 覆盖取消进项计划后 calculate API 被调用并更新结果；业务公式由后端单元测试保护。 |
| `TAX-E2E-003` | `covered` | `web/e2e/tax-offset-flow.spec.ts`、`tests/test_tax_offset_api.py`、`web/src/test/TaxOffsetPage.test.tsx` | Browser 覆盖保存成功和 409 source/version conflict：冲突错误必须可见、不能显示保存成功、不能刷新成伪成功且保存按钮可恢复；保存成功节点还会检查没有保存失败或后台同步失败残留；API/Vitest 覆盖 stale source/version conflict、幂等合同，以及保存成功后直接刷新页面且不请求 operation barrier。 |
| `TAX-E2E-004` | `covered` | `web/e2e/tax-offset-flow.spec.ts`、`tests/test_tax_certified_import_service.py`、`tests/test_import_job_queue.py`、`web/src/test/TaxOffsetPage.test.tsx` | Browser 覆盖 XLSX 选择、preview、confirm、modal 关闭、页面刷新、已认证结果展示，并检查认证导入成功后没有导入失败或后台同步失败残留；Vitest 覆盖 confirm/job 完成后直接重读页面数据且不请求 operation barrier。 |
| `TAX-E2E-005` | `covered` | `web/e2e/tax-offset-flow.spec.ts`、`web/src/test/TaxOffsetPage.test.tsx`、`tests/test_tax_offset_api.py` | Browser 覆盖 direct tax offset payload 首屏展示且没有页面级 read model retry；Vitest 覆盖空 direct payload 显示真实空态。真实税务导入后台任务和 direct API 收敛归 staging/runtime smoke。 |
| `TAX-E2E-006` | `covered` | `web/e2e/workbench-relations-tax-offset-fanout.spec.ts`、`docs/modules/workbench-relations/e2e-coverage.md` | Browser 覆盖 Workbench confirm 后重新读取 `/api/tax-offset`、显示 relation 影响后的进项计划行且无同步错误。 |
| `TAX-E2E-007` | `covered` | `tests/test_tax_offset_api.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/tax-offset-flow.spec.ts` | Browser 覆盖 read-export 用户可读但无保存/导入入口且零 tax write API、forbidden/expired session 在加载 `/api/tax-offset` 前被 gate、admin 可见保存/导入入口；API/Vitest 覆盖后端写权限拒绝合同。 |
| `TAX-E2E-008` | `covered` | `web/e2e/tax-offset-flow.spec.ts`、`web/src/test/TaxOffsetPage.test.tsx` | Browser 覆盖 390px 窄屏下 81 张销项/92 张进项大表，保存/导入按钮未遮挡，搜索、时间排序、对方名称筛选、共享横向滚动和右侧金额列可见；真实生产超大数据性能仍归 staging/runtime smoke。 |

## 下一轮补测建议

1. 保持真实后台任务和 direct API 收敛为 staging/runtime smoke，不把 deterministic mock 标成真实基础设施 covered。
2. 发布前用真实税局 XLSX 大样本、真实 OA/ETC 数据和生产级大月份补 staging/只读 smoke。

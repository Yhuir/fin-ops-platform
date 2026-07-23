# 税金抵扣 Spec-first E2E Coverage

本文件把 `tax-offset` 的 Spec ID 映射到自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `TAX-E2E-001` | `covered` | `web/e2e/tax-offset-flow.spec.ts`、`tests/test_tax_offset_api.py`、`tests/test_tax_offset_read_model_service.py`、`web/src/test/TaxOffsetPage.test.tsx` | Browser 覆盖 fresh 首屏、统计卡、销项/进项 grid 和已认证 drawer 基础展示。 |
| `TAX-E2E-002` | `covered` | `web/e2e/tax-offset-flow.spec.ts`、`tests/test_tax_offset_service.py`、`web/src/test/TaxOffsetPage.test.tsx` | Browser 覆盖取消进项计划后 calculate API 被调用并更新结果；业务公式由后端单元测试保护。 |
| `TAX-E2E-003` | `covered` | `web/e2e/tax-offset-flow.spec.ts`、`tests/test_tax_offset_api.py`、`web/src/test/TaxOffsetPage.test.tsx`、`tests/test_read_model_architecture_guards.py` | Browser 覆盖保存成功和 409 source/version conflict：冲突错误必须可见、不能显示保存成功、不能刷新成伪成功且保存按钮可恢复；保存成功后立即重跑当前月份 normal GET，并检查没有保存/同步/read model 失败残留；API/Vitest/guard 覆盖幂等、普通 plan write 零页面 fan-out 和访问时 exact-month 收敛。 |
| `TAX-E2E-004` | `covered` | `web/e2e/tax-offset-flow.spec.ts`、`tests/test_tax_certified_import_service.py`、`tests/test_import_job_queue.py`、`web/src/test/TaxOffsetPage.test.tsx` | Browser 覆盖 XLSX 选择、preview、confirm、modal 关闭、当前页 normal GET、已认证结果展示，并检查成功后没有导入失败/同步失败/read model 失败残留；Vitest/后端覆盖 confirm job 只提交 facts/version、页面 target 为空，税金页访问时按 exact month 收敛。 |
| `TAX-E2E-005` | `covered` | `web/e2e/tax-offset-flow.spec.ts`、`tests/test_tax_offset_api.py`、`tests/test_tax_offset_read_model_service.py`、`web/src/test/TaxOffsetPage.test.tsx` | Browser 覆盖 `refreshing` / `stale` / `missing` / `failed` read model 不显示真实空态、不泄露 stale reason、不允许保存计划伪成功，并覆盖 `stale -> fresh` 自动重试恢复；真实 worker drain 仍归 staging/runtime smoke。 |
| `TAX-E2E-006` | `covered` | `web/e2e/workbench-relations-tax-offset-isolation.spec.ts`、`tests/test_workbench_relation_repository.py` | Browser 证明 relation confirm 前后税金 item 集合不变；repository 测试证明 relation 写入不产生 `tax_offset` dirty/outbox。 |
| `TAX-E2E-007` | `covered` | `tests/test_tax_offset_api.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/tax-offset-flow.spec.ts` | Browser 覆盖 read-export 用户可读但无保存/导入入口且零 tax write API、forbidden/expired session 在加载 `/api/tax-offset` 前被 gate、admin 可见保存/导入入口；API/Vitest 覆盖后端写权限拒绝合同。 |
| `TAX-E2E-008` | `covered` | `web/e2e/tax-offset-flow.spec.ts`、`web/src/test/TaxOffsetPage.test.tsx` | Browser 覆盖 390px 窄屏下 81 张销项/92 张进项大表，保存/导入按钮未遮挡，搜索、时间排序、对方名称筛选、共享横向滚动和右侧金额列可见；真实生产超大数据性能仍归 staging/runtime smoke。 |

## Operation latency baseline

本轮已为 `web/e2e/tax-offset-flow.spec.ts` 接入 Playwright `operation-latency-*.json` 附件。当前记录的操作覆盖：read-export/admin/forbidden/expired/large-dataset/non-fresh/conflict/happy-path 页面打开、已认证发票导入弹窗打开、窄屏大表搜索、时间排序、对方名称筛选、non-fresh 202 和自动重试、进项计划试算/保存、409 conflict、已认证导入 preview/confirm，以及 confirm 后税金页 normal GET/access-time 收敛。

## 下一轮补测建议

1. 保持真实 worker drain 为 staging/runtime smoke，不把 deterministic mock 标成真实基础设施 covered。
2. 发布前用真实税局 XLSX 大样本、真实 OA/ETC 数据和生产级大月份补 staging/只读 smoke。

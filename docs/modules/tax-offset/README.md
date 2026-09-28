# 税金抵扣

入口：`/tax-offset`。

按业务月核对销项、进项及认证记录，执行试算并保存抵扣计划。

## 边界与 I/O

输入：合法 YYYY-MM、精确选择、expected_canonical_snapshot_version 和幂等键；认证文件经导入工作流。输出：发票与认证 rows、summary/statistics、canonical_snapshot_version、试算和已保存计划。

## 当前业务约定

- 默认采用上海当前业务月，已有有效选择按页面合同恢复。
- 查询在一个只读快照批量读取非删除发票、认证记录和最新 saved 计划；旧选择与当前可用 IDs 求交。
- 金额由 Decimal 策略计算；保存重检页面事实 token，版本冲突不得覆盖新事实。
- 同一幂等键返回原计划；认证导入由共享 import worker 处理，批次/明细/审计/任务成功同事务。
- 认证任务保留其 owner 校验，不套用三类共享导入任务的权限规则。

## 依赖方向

[发票导入](../imports-invoices/README.md)、[后台任务](../runtime-workers/README.md)、[设置](../settings/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/TaxOffsetPage.tsx](../../../web/src/pages/TaxOffsetPage.tsx)
- [backend/src/fin_ops_platform/app/routes_tax.py](../../../backend/src/fin_ops_platform/app/routes_tax.py)
- [backend/src/fin_ops_platform/services/tax_offset_query_service.py](../../../backend/src/fin_ops_platform/services/tax_offset_query_service.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/tax_offset.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/tax_offset.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/tax_offset_page_audit.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/tax_offset_page_audit.py)
- [backend/src/fin_ops_platform/services/tax_offset_service.py](../../../backend/src/fin_ops_platform/services/tax_offset_service.py)
- [backend/src/fin_ops_platform/services/tax_offset_plan_service.py](../../../backend/src/fin_ops_platform/services/tax_offset_plan_service.py)
- [web/src/test/TaxOffsetPage.test.tsx](../../../web/src/test/TaxOffsetPage.test.tsx)
- [web/e2e/drawer-motion.spec.ts](../../../web/e2e/drawer-motion.spec.ts)
- [tests/test_tax_offset_canonical_repository.py](../../../tests/test_tax_offset_canonical_repository.py)
- [tests/test_tax_offset_page_audit.py](../../../tests/test_tax_offset_page_audit.py)
- [tests/test_tax_offset_service.py](../../../tests/test_tax_offset_service.py)
- [tests/test_tax_offset_api.py](../../../tests/test_tax_offset_api.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。

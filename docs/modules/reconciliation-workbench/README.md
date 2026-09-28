# 关联台

入口：`/`。

展示 OA、银行用途和发票的已配对/未配对分组，提供预览、人工关联、撤回、异常审阅、补充凭证与关系收据。

## 边界与 I/O

输入：月份、分区、搜索、过滤、排序和 opaque cursor；命令输入精确 typed 成员、预览版本、稳定幂等键、备注及受信 actor。输出：首屏 summary/statistics、两区首页、groups/total/row_counts/has_more/next_cursor、按需详情与命令回执。

## 当前业务约定

- WorkbenchQueryFacade 通过专属 PostgreSQL repository 在一个短只读快照查询。首屏两区各 10 组，后续游标续读；精确计数在 cursor 和 LIMIT 前计算，hydrate 仅处理当前页 keys。
- 正式成员归 workbench-relations；页面分组、来源展示归属和 display-only 发票不能改变成员、版本或完成状态。
- 人工关联允许同栏或跨栏成员；金额异常需要备注，成员存在、身份、占用和版本仍严格检查。
- 金额诊断保留在组级，异常审阅保存服务端 actor 快照；来源抽屉只显示有来源依据的原始字段。
- OA 补充凭证以组保存金额和文件集合，原子提交后通知匹配任务一次；不把凭证金额重复复制到每份文件或正式发票。
- 收据以 canonical 快照生成 PDF，生成与打印请求留审计；打印不改变正式关系，不能宣称浏览器已实际打印。
- 只读与命令职责分离；当前实现部分组装和 HTTP 映射仍位于 Application。

## 依赖方向

[正式关联关系](../workbench-relations/README.md)、[银行明细](../bank-details/README.md)、[发票导入](../imports-invoices/README.md)、[OA 集成](../oa-integration/README.md)、[后台任务](../runtime-workers/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/ReconciliationWorkbenchPage.tsx](../../../web/src/pages/ReconciliationWorkbenchPage.tsx)
- [web/src/components/workbench/RelationGroupGrid.tsx](../../../web/src/components/workbench/RelationGroupGrid.tsx)
- [web/src/features/workbench/api.ts](../../../web/src/features/workbench/api.ts)
- [backend/src/fin_ops_platform/app/routes_workbench.py](../../../backend/src/fin_ops_platform/app/routes_workbench.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/workbench_page_query.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/workbench_page_query.py)
- [backend/src/fin_ops_platform/services/workbench_relation_grouping.py](../../../backend/src/fin_ops_platform/services/workbench_relation_grouping.py)
- [backend/src/fin_ops_platform/services/workbench_anomaly_contract.py](../../../backend/src/fin_ops_platform/services/workbench_anomaly_contract.py)
- [backend/src/fin_ops_platform/services/workbench_free_matching_engine.py](../../../backend/src/fin_ops_platform/services/workbench_free_matching_engine.py)
- [backend/src/fin_ops_platform/services/postgres_repositories/workbench_formal_relation.py](../../../backend/src/fin_ops_platform/services/postgres_repositories/workbench_formal_relation.py)
- [backend/src/fin_ops_platform/services/workbench_relation_command_service.py](../../../backend/src/fin_ops_platform/services/workbench_relation_command_service.py)
- [web/src/test/WorkbenchApi.test.ts](../../../web/src/test/WorkbenchApi.test.ts)
- [web/src/test/WorkbenchSelection.test.tsx](../../../web/src/test/WorkbenchSelection.test.tsx)
- [web/src/test/WorkbenchSelectionModel.test.ts](../../../web/src/test/WorkbenchSelectionModel.test.ts)
- [web/src/test/WorkbenchZone.test.tsx](../../../web/src/test/WorkbenchZone.test.tsx)
- [tests/test_workbench_relation_receipt_eligibility.py](../../../tests/test_workbench_relation_receipt_eligibility.py)
- [tests/test_workbench_relation_receipt_service.py](../../../tests/test_workbench_relation_receipt_service.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。

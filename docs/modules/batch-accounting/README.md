# 批量账务历史

入口：设置页的“批量账务”Tab。旧 `/batch-accounting` 地址进入该 Tab。

本模块只查询当前有效的批量账务正式关系，不创建、撤回关系或修改标签规则。已撤回关系的审计仍由既有操作历史保存。历史页面读取当前 canonical facts，不保存提交时的字段快照。

## 边界与 I/O

- `GET /api/batch-accounting` 接受 `bank_year=all|YYYY`、`page`、`page_size`，默认全部年份、第一页、每页 50 条，最大 200 条。返回 `rows`、`summary`、`pagination`、`available_years`。
- 每行以 `relation_id` 标识，账户使用 `bank_accounts` 对象数组保持银行名称和后四位的配对；同一关系的流水金额不因 OA 或发票展开重复累计。
- `summary.relation_count` 是有效关系列表条数；`transaction_count` 是这些关系包含的原始流水去重笔数。分页使用关系条数。
- `GET /api/batch-accounting/relations/{relation_id}` 返回完整的流水、OA、发票成员、已有备注、流水金额、OA 金额、差额及 `missing_member_ids`。ETC 汇总成员复用 canonical owner 批量解析，`etc_invoice_detail_rows` 提供实际发票明细；不存在或身份冲突的批次保留明确缺失状态。
- Route 负责参数与错误映射，Application 的页面权限边界负责鉴权；service 组装 DTO，repository 持有 SQL。

## 当前业务约定

- 只读取 `status=active` 且 `relation_mode=batch_accounting` 的正式关系。详情不会读取其它关系类型或已撤回记录。
- 年份按 canonical 流水交易日期筛选。关系有任一流水成员落入选定年份就进入列表；列表和详情展示该关系的完整成员及金额。可选年份来自全部有效历史。
- 列表按关系最新流水日期倒序、关联 ID 排序。列表、统计和年份在一个只读 repeatable-read 快照内查询；详情关系和成员也使用一个请求快照。
- 流水支出金额为 canonical `-signed_amount`，退款保留负数；OA、发票保留 canonical 原符号。缺失成员或金额以明确缺失状态呈现，不替换成零、不使用关系元数据补造事实。
- 成员类型复用正式关系 owner 的类型规范化，支持已登记的银行、OA、发票别名。
- 查询不加载未提交候选、候选 OA、标签选择或完整来源 raw payload，不产生写入与后台任务。
- `batch-accounting` 查看权限独立于 `settings` 权限。设置容器不会让历史用户获取其它设置内容或修改权限。

## 依赖方向

消费[银行明细](../bank-details/README.md)、[正式关联关系](../workbench-relations/README.md)、[OA 集成](../oa-integration/README.md)及发票正式事实；由[设置](../settings/README.md)提供 UI 容器。不得读取其它页面展示结果作为业务事实。

## 代码与验证入口

- [历史前端接口](../../../web/src/features/batchAccounting/api.ts)
- [历史前端 DTO](../../../web/src/features/batchAccounting/types.ts)
- [HTTP route](../../../backend/src/fin_ops_platform/app/routes_batch_accounting.py)
- [查询 service](../../../backend/src/fin_ops_platform/services/batch_accounting_service.py)
- [PostgreSQL repository](../../../backend/src/fin_ops_platform/services/postgres_repositories/batch_accounting.py)
- [API 与 service 测试](../../../tests/test_batch_accounting_api.py)
- [真实 PostgreSQL 测试](../../../tests/test_batch_accounting_postgres_integration.py)
- [只读性能抽查工具](../../../backend/src/fin_ops_platform/tools/batch_accounting_read_smoke.py)
- [前端交互测试](../../../web/src/test/BatchAccountingPage.test.tsx)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。

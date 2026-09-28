# 成本统计

入口：`/cost-statistics`。

根据银行用途、OA 费用单元、正式来源和人工决定生成唯一成本事件集合，提供项目、费用、账户、时间和标签视角。

## 边界与 I/O

输入：view/filter/cursor、成本范围配置，以及逐 OA 单元金额、来源、oa_amount_locks、oa_cost_tag_overrides、version/fingerprint。输出：聚合、下钻、来源详情、待分配/人工记录和导出。

## 当前业务约定

- Repository 负责同快照批量取事实，Policy 是无数据库/网络 I/O 的纯计算，query service 组装 DTO，人工 service 通过 repository 事务保存。
- 银行外部往来本金按结构化 turnover_role 排除；独立利息用途有唯一来源且金额闭合时自动计成本，金额或来源歧义保留待分配。
- 明确来源引用和正式历史约束自动分配，不用展示同行或金额子集搜索猜来源；多来源须覆盖完整且无冲突。
- 无决定或 automatic 按当前事实计算，manual 优先；stale manual 进入复核，不静默转自动。自动完成不要求保存人工记录。
- OA 原额锁定按单元控制；解锁只改变分配金额，不修改 OA。来源容量、退款、非成本和范围外已确认金额一并校验。
- 人工成本标签只属于成本事件，不能改银行标签或扩大来源准入；保存保留范围外有效决定，CAS、版本和审计同事务。
- 银行用途改变由银行 owner 调用成本撤销端口，保留审计和连续版本；纯排序变化不撤销决定。
- 银行视角不加载无关人工分配；OA payload 只读取计算所需字段，分页/导出共用业务策略。

## 依赖方向

[银行明细](../bank-details/README.md)、[正式关联关系](../workbench-relations/README.md)、[OA 集成](../oa-integration/README.md)、[设置](../settings/README.md)、[外部往来款](../turnover-ledger/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/CostStatisticsPage.tsx](../../../web/src/pages/CostStatisticsPage.tsx)
- [backend/src/fin_ops_platform/app/routes_cost_statistics.py](../../../backend/src/fin_ops_platform/app/routes_cost_statistics.py)
- [tests/test_bank_split_cost_migration_service.py](../../../tests/test_bank_split_cost_migration_service.py)
- [tests/test_bank_split_relations_postgres.py](../../../tests/test_bank_split_relations_postgres.py)
- [tests/test_bank_split_consumers_postgres.py](../../../tests/test_bank_split_consumers_postgres.py)
- [tests/test_cost_statistics_policy.py](../../../tests/test_cost_statistics_policy.py)
- [tests/test_cost_statistics_canonical_repository.py](../../../tests/test_cost_statistics_canonical_repository.py)
- [tests/test_cost_statistics_api.py](../../../tests/test_cost_statistics_api.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。

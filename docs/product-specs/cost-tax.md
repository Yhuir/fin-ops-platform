# 成本统计、项目归因与税金抵扣

本文维护成本统计、项目成本归因、税金抵扣、已认证发票和发票使用/收款 read model 的当前业务口径。

## 成本统计

成本统计页面面向项目和期间展示费用、发票、流水和核销关系：

- 项目范围、金额归因和下钻口径必须来自统一 cost attribution policy。
- 页面负责筛选、排序、分页、导出 shape，不重新定义项目归因。
- 导入、关系确认、发票状态变化和项目配置变化都可能影响统计。

## 项目归因

项目归因至少需要考虑：

- OA 单据项目、发票项目、银行流水摘要/对手方、人工修正关系。
- 多项目拆分、缺失项目、冲突项目和撤回关系。
- source version、归因来源和审计记录。

## 税金抵扣

税金抵扣页面关注可抵扣发票、已认证发票和发票使用状态：

- 认证状态、税额、发票类型和使用状态必须由统一 policy 判定。
- 发票关系确认/撤回会影响税金抵扣和成本统计。
- backfill/refresh 需要按月份或发票对象范围执行，避免逐行重建。

## 相关文档

- 发票生命周期：`invoice-lifecycle.md`
- Runtime：`../app-architecture/runtime-and-ownership.md`
- Worker 运维：`../operations/runtime-worker-governance.md`

# 成本统计、项目归因与税金抵扣

本文维护成本统计、项目成本归因、税金抵扣、已认证发票和发票使用/收款 read model 的当前业务口径。

## 成本统计

成本统计页面面向项目和期间展示费用、发票、流水和核销关系：

- 项目范围、金额归因和下钻口径必须来自统一 cost attribution policy。
- 页面负责筛选、排序、分页、导出 shape，不重新定义项目归因。
- 导入、关系确认、发票状态变化和项目配置变化都可能影响统计。
- 成本统计 read model 的物化 scope 包含 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 和 `all:all`。`active:all` / `all:all` 是全期间视图的一等 read model，不只是月份分片 fan-out 的父 scope。
- 刷新 `active:all` / `all:all` 时，worker 必须先重建该全期间 scope 并写入 readiness，再入队对应月份分片。月份分片失败只影响该分片 readiness，不能反向污染已成功的全期间 scope。
- App Health 只根据 `cost_statistics` read model 的真实 readiness、dirty scope、outbox 和 cost-tax worker 状态判定成本统计页面。历史 failed readiness 必须由后续真实成功 rebuild 覆盖，不能手工伪造绿色。
- App Status 必须保留 `cost_statistics` 的 scope-level readiness：`active:all`、`all:all`、`active:YYYY-MM`、`all:YYYY-MM`。全期间父 scope failed/unavailable 代表成本统计主体验不可用；单个月份 shard failed/unavailable 只代表局部分片需要重试，域级显示 busy/attention，不阻断已经 fresh 的全期间视图。
- 页面 API 只表达当前查询 scope 的数据平面状态，例如 `fresh`、`refreshing`、`stale`、`failed` 或 `unavailable`；App Status 负责解释多个 scope、dirty scope、outbox、worker heartbeat 和 last error 的状态平面。两者必须使用同一套 scope key 语义，不能用页面请求线程同步重建来掩盖缺失 read model。

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

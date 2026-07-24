# 成本统计、项目归因与税金抵扣

本文维护成本统计、项目成本归因、税金抵扣、已认证发票和发票使用/收款 read model 的当前业务口径。

## 成本统计

成本统计页面面向项目和期间展示费用、发票、流水和核销关系：

- 项目范围、金额归因和下钻口径必须来自统一 cost attribution policy。
- 页面负责筛选、排序、分页、导出 shape，不重新定义项目归因。
- OA 配对成本以银行流水为起点：银行流水原生月份内的非零支出，只要属于一个至少包含一条已完成 OA 的 active 正式 Workbench relation，就进入 OA 配对成本；该 relation 位于 `paired` 或因冻结条件未满足而位于 `unpaired` 都不影响资格，是否存在发票也不影响资格。无 OA 的流水、candidate/singleton 和仅 bank+invoice 的关系不进入 OA 配对成本。
- 一笔流水只归属其银行原生月份，跨月 relation 副本不得重复计入。一个流水关联多个 OA 时，只有“一笔银行流水 + 每张 OA 都有正数明确金额 + OA 金额按分精确合计等于流水金额”才按 OA 金额拆分；项目和费用类型分别使用各 OA 维度。其它多 OA / 多流水组合不按比例推断，流水金额只计一次：一致维度正常归属，不一致项目显示 `多项目`，不一致费用类型显示 `多费用类型`；缺失维度使用 `未归集项目` / `未分类`。
- OA 上的 `cost_excluded`、`冲`、`oa_invoice_offset_auto_match`、借款/还款费用类型和 relation `cost_policy=exclude_all` 不再否决已经成立的 OA+流水成本资格。`include_ticket_cost_only` 只保留为明确票据成本金额覆盖规则，不改变 OA+流水资格。
- 成本统计 read model 的物化 scope 包含 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 和 `all:all`。`active:all` / `all:all` 是全期间视图的一等 read model，不只是月份分片 fan-out 的父 scope。
- 月份 scope 由 `cost-statistics` 专用 worker 从对应工作台月份 read model 构建；旧 `cost-tax` 不再消费成本统计刷新。`active:all` / `all:all` 父 scope 从已物化的成本统计月份 rows 聚合并原子发布，不再读取工作台 `all` scope 的全量 JSON payload。
- 刷新 `active:all` / `all:all` 时，worker 必须先检查所需月份 shard readiness。缺失、stale 或 failed 的 shard 先通过 durable queue 入队，父 scope 记录 `refreshing`，不得伪造 `fresh`；所有 shard 都 fresh 后才聚合发布父 scope 并写入父 scope readiness。
- 月份 shard 成功后会重新入队同 project scope 的父 scope，使全期间视图最终收敛。月份分片失败只影响该分片 readiness，不能反向污染已成功的全期间 scope。
- App Health 只根据 `cost_statistics` read model 的真实 readiness、dirty scope、outbox 和 `cost-statistics` worker 状态判定成本统计页面。历史 failed readiness 必须由后续真实成功 rebuild 覆盖，不能手工伪造绿色。
- App Status 必须保留 `cost_statistics` 的 scope-level readiness：`active:all`、`all:all`、`active:YYYY-MM`、`all:YYYY-MM`。全期间父 scope failed/unavailable 代表成本统计主体验不可用；单个月份 shard failed/unavailable 只代表局部分片需要重试，域级显示 busy/attention，不阻断已经 fresh 的全期间视图。
- 页面 API 只表达当前查询 scope 的数据平面状态，例如 `fresh`、`refreshing`、`stale`、`failed` 或 `unavailable`；App Status 负责解释多个 scope、dirty scope、outbox、worker heartbeat 和 last error 的状态平面。两者必须使用同一套 scope key 语义，不能用页面请求线程同步重建来掩盖缺失 read model。
- 页面存在两套不可混用的事实集：`按项目`、`按银行`、`按OA费用类型` 消费 OA配对支出 allocation；`按时间`、`按标签` 消费完整银行收入与支出。因此两组金额不要求相等。API只暴露当前 view的 bounded `rows`，产品口径不依赖已删除的旧 full-array DTO字段。
- 全流水统计不显示“总金额”或净额。页面顶部、主标签和子标签分别显示支出金额与收入金额，二者均为正数绝对值；支出金额是当前可见支出流水绝对金额之和，收入金额是当前可见收入流水绝对金额之和。收入用绿色、支出用橘色；明细逐行保留资金方向和该笔金额。
- 主标签和子标签分别显示收支金额及收支笔数，不显示合并金额和占比。收入与支出都进入同一成本统计标签选择规则；旧显式规则升级时保留原支出选择并一次性加入当前有效收入标签，未分类选择保持不变。
- `按时间` 和 `按标签` 导出都必须包含收入与支出明细、资金方向，以及分方向金额/笔数摘要；OA 项目类导出保持 OA 配对支出口径。

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

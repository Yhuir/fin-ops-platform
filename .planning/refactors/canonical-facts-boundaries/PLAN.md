# Canonical Facts Modularization Plan

日期：2026-06-26

## 原则

- 不新增集中式运行时大模块。
- 不把 read model 当作源业务事实。
- 不把 shared repository 误当 shared business owner。
- 每个 canonical fact family 只允许一个业务 owner。
- 非 owner 通过 owner 的 command/read port、service 或明确 adapter 访问。
- 每个 canonical write 必须声明下游 read model dirty scope、domain event、operation barrier target 或明确不适用。

## 文档阶段

1. 新增 canonical facts 总合同。
2. 新增 canonical-facts governance 模块文档。
3. 更新 inventory、docs index 和模块清单。
4. 保留本 `.planning` 分析作为执行参考。

## 后续代码重构顺序

| 顺序 | 模块 | 目标 |
| --- | --- | --- |
| 1 | workbench-relations | 确认/撤回/repair 全部通过 command/read boundary，禁止调用方直接改关系事实。 |
| 2 | imports + canonical invoice/bank facts | 导入确认和 import job 写入 fact 后明确 affected scopes、domain events 和 dirty/outbox。 |
| 3 | bank-details | 银行分类、标签、确认/撤回事实收口到 bank detail owner，并证明下游 fan-out。 |
| 4 | pending-invoices / invoice lifecycle | 规则、补票、生命周期写入与 downstream scopes 建立 owner matrix。 |
| 5 | tax-offset / cost-statistics | 税金认证、计划、成本统计上游事实和父聚合 scope 做闭环证明。 |
| 6 | no-oa-bank-batches / turnover-ledger | 写闭环、legacy fallback、operation barrier 和样本恢复证明。 |
| 7 | ETC / OA integration | ETC metadata、canonical invoice pool、OA projection 和 repair tools 的边界收口。 |

## 验收标准

- 每个 canonical fact family 有 owner、writer、reader、downstream read models 和禁止路径。
- 每个 owner 模块的 `boundary-io.md` 至少记录自身 facts、输入、输出、持久化、依赖方向和旧代码删除条件。
- 写 API/service 返回或透出 affected scopes / freshness targets / operation barrier targets，或在模块文档说明不适用。
- 旧 snapshot/live fallback 保留时标记为 migration/shadow/audit/rollback-only，并有测试或 guard 防止进入 production API 主路径。
- 相关测试覆盖 service-layer、API contract、read model/cache/background job、existing feature regression；前端和 E2E 只在用户可见流程变化时补。

## 本轮不做

- 不改 SQL schema。
- 不新增 runtime service。
- 不移动 repository 代码。
- 不清理 legacy path。
- 不做生产 smoke 或数据修复。

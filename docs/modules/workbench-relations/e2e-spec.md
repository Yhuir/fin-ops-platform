# 关联台关系事实源 Spec-first E2E Spec

本文件定义 `workbench-relations` 资源模块的浏览器级验收合同。该模块没有单独 route；它通过关联台和下游页面证明 canonical relation write model、distribution read model 和跨页面 fan-out 是否符合业务。

## 模块目标

`app.workbench_pair_relations` 是 confirmed relation fact。`workbench_relation` read model 是下游页面读取 linked/unlinked relation context 的统一边界。Browser E2E 必须证明用户写入 relation 后，下游页面通过后端事实重新读取到一致结果；也必须证明未正式化自动决策不会被当作 confirmed fact。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `WB-REL-E2E-001` | 关联台 confirm -> bank details linked tags | P0 | confirm 后，银行明细从候选标签变为 linked 标签，且列表重新请求。 |
| `WB-REL-E2E-002` | 关联台 confirm -> pending invoices linked status | P0 | confirm 后，待找发票 linked-only 状态更新为已开票，显示发票号码/OA 申请人。 |
| `WB-REL-E2E-003` | batch accounting submit/withdraw -> relation barrier -> bucket recovery | P0 | 批量账务提交后进入已提交 bucket，撤回后回未提交 bucket，期间等待 `workbench_relation` barrier。 |
| `WB-REL-E2E-004` | turnover closure confirm/withdraw -> turnover/workbench barriers -> grouped recovery | P0 | 外部往来闭环后显示收支闭环，撤回后恢复，期间等待目标 freshness barriers。 |
| `WB-REL-E2E-005` | 未正式化自动决策不驱动 linked-only 业务状态 | P0 | 下游页面不能把 open/proposed automatic decision 推断成候选或已关联 chip；支付/开票/收款/成本等业务状态只按 linked relation 计算。 |
| `WB-REL-E2E-006` | relation read model non-fresh | P0 | 页面显示 freshness 诊断，不把空 relation 当真实空，不全局禁用具备 canonical write safety 的无关 mutation。 |
| `WB-REL-E2E-007` | canonical write safety 和 idempotency | P0 | 重复提交不创建第二条 active relation；version conflict 显示明确错误。 |
| `WB-REL-E2E-008` | relation fan-out 到 invoice usage / output collection / OA pending / cost / tax / search | P1 | 关键下游页面在 relation 写后通过自己的 read model 展示一致状态；candidate 不进入 linked-only 金额。 |
| `WB-REL-E2E-009` | real download/export with relation fields | P1 | 含 relation 字段的导出文件在真实浏览器 download event 中成功生成，字段与当前筛选/权限一致。 |
| `WB-REL-E2E-010` | production/staging relation display audit | P1 | 只读 audit 证明 active relation 成员在 active Workbench generation 中同组展示，没有多 owner、缺失或 all 滞后。 |

## 不属于本地 deterministic E2E 的风险

- 真实 PostgreSQL 历史 relation 半迁移。
- 真实 worker drain 和 queue priority。
- 生产 active generation display audit。
- 大数据下游全链路 P95/P99。

这些风险必须由 staging、生产只读工具和 runbook smoke 承接。

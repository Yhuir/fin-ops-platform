# 关联台关系事实源 Spec-first E2E Spec

本文件定义 `workbench-relations` 资源模块的浏览器级验收合同。该模块没有单独 route；它通过关联台和下游页面证明 canonical relation write model、distribution read model 和跨页面访问收敛是否符合业务。

## 模块目标

`app.workbench_pair_relations` 是正式 relation fact。`workbench_relation` read model 是下游页面读取 linked/unlinked relation context 的统一边界。Browser E2E 必须证明用户写入 relation 后，下游页面通过后端事实重新读取到一致结果；无 active relation 的对象必须保持独立 unlinked。

## Spec 场景

| Spec ID | 场景 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| `WB-REL-E2E-001` | 关联台 confirm -> bank details linked tags | P0 | confirm 后，银行明细从未关联变为 linked 标签，且列表重新请求。 |
| `WB-REL-E2E-002` | 关联台 confirm -> pending invoices linked status | P0 | confirm 后，待找发票 linked-only 状态更新为已开票，显示发票号码/OA 申请人。 |
| `WB-REL-E2E-003` | batch accounting submit/withdraw -> current-page GET -> bucket recovery | P0 | 批量账务提交后零 read-model target，通过当前页 normal GET 进入已提交 bucket；撤回后以同一 gate 回未提交 bucket。 |
| `WB-REL-E2E-004` | turnover closure confirm/withdraw -> current-page GET -> grouped recovery | P0 | 外部往来闭环写入只保存 canonical relation，当前往来页 normal GET 后显示收支闭环；撤回后同样恢复，零 freshness barrier。 |
| `WB-REL-E2E-005` | 非正式历史输入不驱动 linked-only 业务状态 | P0 | 下游页面不能把非 linked 的历史输入推断成已关联 chip；支付/开票/收款/成本等业务状态只按 linked relation 计算。 |
| `WB-REL-E2E-006` | relation read model non-fresh | P0 | 页面显示 freshness 诊断，不把空 relation 当真实空，不全局禁用具备 canonical write safety 的无关 mutation。 |
| `WB-REL-E2E-007` | canonical write safety 和 idempotency | P0 | 重复提交不创建第二条 active relation；version conflict 显示明确错误。 |
| `WB-REL-E2E-008` | relation 后 invoice usage / output collection / OA pending / cost 访问一致与 tax 隔离 | P1 | relation 写时零页面 fan-out；关键下游页面逐个访问后从 canonical facts 展示一致状态，tax 不消费 relation；unlinked 对象不进入 linked-only 金额。 |
| `WB-REL-E2E-009` | real download/export with relation fields | P1 | 含 relation 字段的导出文件在真实浏览器 download event 中成功生成，字段与当前筛选/权限一致。 |
| `WB-REL-E2E-010` | production/staging relation display audit | P1 | 只读 audit 在同一 canonical snapshot 中证明 active relation 成员由 Workbench direct query 同组展示，没有多 owner、typed member 缺失或区域分类错误。 |
| `WB-REL-E2E-011` | manual same-pane/different-pane confirm -> incomplete relation | P0 | 至少 2 个不同 canonical members 可人工确认；同栏合法，只有 `amount_check.requires_note=true` 时要求既有 `note`，材料不完整时 active relation 保持同 case `unpaired`；自动 matching 的严格门禁不变。 |
| `WB-REL-E2E-012` | unpaired active relation withdraw -> stable topology restore | P0 | 未配对 active case 可撤回；显式 row ids 在 preview/submit 都必须精确等于完整 active typed member set。preview fingerprint 绑定 current/after topology 与 confirm-history identity；submit 在同一 UoW 内锁 current/predecessor case 与 members，重验 canonical member、restored case 和唯一 owner，再从最近 confirm history 的 `before_relations` 恢复上一稳定拓扑。任何漂移或冲突整笔 fail closed，无 predecessor 才变 singleton；旧 row metadata 不参与恢复。 |

## 不属于本地 deterministic E2E 的风险

- 真实 PostgreSQL 历史 relation 半迁移。
- 真实 worker drain 和 queue priority。
- 生产 direct canonical display audit 与 SQL planner/缓冲区表现。
- 大数据下游全链路 P95/P99。

这些风险必须由 staging、生产只读工具和 runbook smoke 承接。

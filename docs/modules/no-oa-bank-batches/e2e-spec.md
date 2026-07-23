# 免 OA 银行批次 Spec-first E2E

本模块目前没有独立前端 route，保留 legacy API/历史批次能力；新流水规则页面由 `bank-flow-rule-batches` 模块负责。

| Spec ID | 场景 | 验收 |
| --- | --- | --- |
| `NO-OA-E2E-001` | submit / withdraw canonical closure | 提交或撤回只保存 no-OA batch、canonical relation、history/version/audit；普通写的 freshness/barrier targets 为空，零页面 dirty/outbox。 |
| `NO-OA-E2E-002` | access-time convergence | legacy API/read facade 被访问时比较 exact month source versions；missing/stale 才经 gateway 去重入队，不回退 `all`。 |
| `NO-OA-E2E-003` | bank-flow isolation | no-OA route/service 不调用 bank-flow route/service，bank-flow 新页面也不复用 no-OA read/write model。 |
| `NO-OA-E2E-004` | failure/idempotency | version conflict、重复 submit/withdraw、持久化失败和 relation conflict 不产生半写或页面 job。 |

真实 PostgreSQL worker drain、历史批次大数据和生产 access-to-fresh 时延由 Phase 27 生产矩阵验证。

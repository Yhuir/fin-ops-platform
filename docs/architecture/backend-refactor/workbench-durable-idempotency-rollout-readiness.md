# Workbench Durable Idempotency Rollout Readiness

对应 prompt：`PF-P040 - Workbench Durable Idempotency Rollout Readiness and Integration Contract Tests`

状态：`implemented`

本文档记录 Workbench durable idempotency 在打开 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY` 前必须满足的上线就绪门禁。PF-P040 不启用 feature flag，不部署，不执行 Traffic Gate，不迁移更多 Workbench 写 API。

## 1. 结论

Feature flag must remain off，直到本文档中的 `blocked` 项被后续 prompt 机械化补齐并通过 Merge Gate。

当前可合入主干的是“默认关闭的基础能力 + rollout readiness 文档 + contract tests”，不是“可以打开 durable idempotency”。生产默认路径仍应继续使用 `InMemoryWorkbenchIdempotencyRepository`。

## 2. Rollout Readiness Matrix

| Gate | 状态 | 当前证据 | 打开前要求 |
| --- | --- | --- | --- |
| default-off safety | ready | `Application._workbench_confirm_link_unit_of_work()` 和 `_workbench_cancel_link_unit_of_work()` 只有在显式设置 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY=1/true/yes/on` 时才构造 `PostgresWorkbenchIdempotencyRepository`。新增 rollout test 锁定默认关闭行为。 | 继续保持默认关闭；任何部署配置不得默认打开。 |
| opt-in feature flag wiring | ready | 显式设置 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY=1` 时，PostgreSQL storage backend 会构造 durable repository。 | 只能在完成本表 blocker 后通过单独 Traffic / canary 操作打开。 |
| migration apply readiness | documented-risk | `0043_workbench_idempotency_records.sql` 已合入，schema 有 migration discovery tests。PF-P040 未连接真实生产或 staging PostgreSQL。 | 打开前必须确认目标数据库已应用 migration，并确认 grant 与 API 用户一致。 |
| repository transaction-bound behavior | ready | `PostgresWorkbenchIdempotencyRepository.for_transaction(transaction)` 已存在；reserve/commit contract tests 证明不打开自己的 nested transaction。 | 继续禁止 repository 在 reserve/commit 中自行打开 transaction。 |
| transaction-bound reserve/commit | ready | UoW 在 transaction 内绑定 idempotency store，facts、dirty/outbox 和 idempotency commit 共用同一个 transaction object。 | 未来迁移更多 Workbench 写 API 时必须复用 UoW，不得绕过 transaction-bound writer。 |
| committed replay | ready | `WorkbenchWriteUnitOfWork.run()` 对相同 fingerprint 的 committed record replay response，不执行 handler，也不写 dirty/outbox。 | replay payload 必须保持 sanitized 且 replay-safe。 |
| same-key different-fingerprint conflict | ready | `WorkbenchIdempotencyKeyConflict` 稳定返回 409 风格 payload；测试锁定 same-key different-fingerprint conflict。 | 前端/调用方需要把 409 视为幂等 key 复用错误，不应静默重试。 |
| payload sanitization | ready | repository 与 record tests 已覆盖 authorization、cookie、token、password、secret 类字段过滤。 | 新增 payload 字段时必须继续走 sanitizer。 |
| reserved/in-progress duplicate policy | blocked | 当前 repository `reserve()` 能写入/读取记录，但没有明确“同 key 同 fingerprint 正在处理”的 HTTP 契约。 | 需要新增 deterministic in-progress duplicate primitive，例如 409/425 payload，且必须有 tests。 |
| expired reserved takeover | blocked | 当前 schema 有 `expires_at`，但 repository 尚未实现 expired reserved takeover 或 mark-failed-then-retry 策略。 | 需要明确过期判断、锁行、接管或失败策略，并用 fake 和真实 PostgreSQL concurrency test 覆盖。 |
| failed reservation policy | blocked | `failed` 状态存在，但 failed 是否允许同 fingerprint retry、如何返回历史失败、如何避免盲重放未定。 | 需要单独 contract 和 repository tests。 |
| cleanup/retention | blocked | 有 `expires_at` 字段，但没有 cleanup job、retention policy 实现和运维门禁。 | 需要 ops cleanup 策略、监控和测试；request path 不得隐式清理大量历史记录。 |
| actor/tenant auth context | blocked | 当前 UoW command 仍可能落到默认 `tenant_id="default"`、`actor_id="system"`；durable unique key 依赖 `(tenant_id, actor_id, idempotency_key)`，默认身份会降低隔离性和审计价值。 | 打开前必须从 auth context 注入真实 actor/tenant，并补测试证明不会默认落到 `system/default`。 |
| real PostgreSQL row-lock concurrency | future-test-needed | 当前默认 CI 使用 fake/contract tests；没有真实 PostgreSQL 并发 reserve test。 | 打开前至少在可控环境跑真实 PostgreSQL concurrent reserve / committed replay test。 |
| observability/metrics/logging | future-test-needed | 当前没有 durable idempotency 专用 metrics，例如 replay count、conflict count、reserved age、expired count。 | 打开前需要最少的日志/指标清单和告警阈值。 |
| rollback | ready | 回滚主开关是关闭 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`，默认路径回到 in-memory repository。 | 关闭 flag 只能停止新请求写 durable records；已存在 records 保留用于审计，不应在回滚时删除。 |

## 3. 打开前 Checklist

- `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY` 仍默认关闭。
- 目标数据库已应用 `0043_workbench_idempotency_records.sql`。
- API 数据库用户具备 `select/insert/update` 相关权限。
- `actor/tenant auth context` 已接入真实身份，且不再默认落到 `system/default`。
- `reserved/in-progress duplicate policy` 已定义并测试。
- `expired reserved takeover` 已定义并测试。
- `failed reservation policy` 已定义并测试。
- `cleanup/retention` 有明确运维方案。
- 至少完成一次真实 PostgreSQL row-lock concurrency 验证。
- replay、conflict、failed、expired、reserved-age 至少有可观测日志或指标。
- 回滚预案明确：关闭 feature flag，保留表数据，不改业务路由。

## 4. 回滚方式

1. 关闭 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。
2. 重启或滚动发布 API 进程，使配置生效。
3. 验证 Workbench confirm/cancel 写路径继续走 `InMemoryWorkbenchIdempotencyRepository`。
4. 保留 `app.workbench_idempotency_records` 数据用于审计和事后分析。
5. 不在 request path 中删除或清空 durable records。

## 5. Migration Apply / Rollback 注意事项

- PF-P040 不修改 `0043_workbench_idempotency_records.sql`。
- 如果目标环境 migration 未应用，feature flag 不得打开。
- 如果 feature flag 打开后需要回滚，优先关闭 flag，不应回滚 schema。schema 已合入后可保持空表或历史记录。
- 如果未来 schema 需要修改，应走单独 migration prompt 和 Merge Gate。

## 6. Blocker 分组

打开 feature flag 前必须解决：

- `actor/tenant auth context`
- `reserved/in-progress duplicate policy`
- `expired reserved takeover`
- `failed reservation policy`
- `real PostgreSQL row-lock concurrency`

可以 disabled-by-default 合入但必须继续跟踪：

- `cleanup/retention`
- `observability/metrics/logging`
- migration apply runbook

## 7. 下一步建议 Prompt

建议下一条实现类 prompt 优先处理身份隔离：

`PF-P041 - Workbench Durable Idempotency Actor/Tenant Context Contract`

边界建议：只把真实 auth context 注入 Workbench UoW command / idempotency identity，并补 contract tests；不打开 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`，不迁移更多 Workbench 写 API。

如果用户更关注并发策略，也可以先生成：

`PF-P041 - Workbench Durable Idempotency Reserved/In-Progress Policy`

该方向只处理 reserved/in-progress duplicate、expired reserved takeover 和 failed reservation policy，不打开 feature flag。

# Workbench 持久幂等生产契约

状态：`production-always-on`

## 结论

PostgreSQL 运行时的 Workbench 财务写操作固定使用 `PostgresWorkbenchIdempotencyRepository`。旧的开关与内存生产路径已移除；本地非 PostgreSQL 测试仍可使用显式内存适配器。

## Rollout Readiness Matrix

| 契约 | 状态 | 生产约束 |
| --- | --- | --- |
| transaction-bound reserve/commit | ready | 幂等 reserve、业务事实、dirty scope、outbox 与 committed response 共用一个事务。 |
| committed replay | ready | 相同 key 与 fingerprint 返回首次提交结果，不重复执行写 handler。 |
| same-key different-fingerprint conflict | ready | 返回稳定冲突，不覆盖旧记录。 |
| reserved/in-progress duplicate policy | ready | 正在处理的相同请求返回 in-progress，不重复写事实。 |
| expired reserved takeover | ready | 仅相同 fingerprint 可接管过期 reservation。 |
| failed reservation policy | ready | 失败记录不自动重放；重新执行必须使用新 key。 |
| actor/tenant auth context | ready | actor 来自当前 OA session；当前系统显式使用单租户 `default`。 |
| client idempotency key | ready | Workbench、批量账务和高风险数据重置均由客户端为一次用户意图生成稳定 key。 |
| cleanup/retention | documented-risk | 历史记录保留用于审计；清理必须由独立运维策略执行，禁止在请求路径批量删除。 |
| observability | ready | 财务操作审计记录与 runtime worker attempt history 分别保存业务结果和每次执行结果。 |
| rollback | ready | 回滚应用版本，不删除幂等表或历史记录；禁止切回生产内存幂等。 |

## 数据库与运行时门禁

- 目标数据库必须完成所有 migration。
- API 与 worker 数据库角色必须具备对应表的最小读写权限。
- Workbench 写 API 缺少 idempotency key 时必须 fail closed。
- 相同 key 的重试只能 replay 或返回明确状态，不得重复追加关系、核销、审计或 outbox。
- 队列采用 at-least-once 投递；业务副作用必须由唯一约束、幂等记录或状态转换保护。

## 验证

- repository contract：reserve、replay、conflict、failed、expired takeover。
- UoW contract：事实、审计、dirty scope、outbox、幂等结果同事务提交或回滚。
- API contract：缺 key 拒绝、相同 key 稳定重试、不同 payload 冲突。
- PostgreSQL integration：并发 reserve 只能有一个执行者，其余请求读取同一 durable record。

## 剩余运维风险

当前不引入在线 cleanup worker。数据量达到需要清理的阈值后，再依据表体积、最老记录时间和审计保留期增加离线清理任务；该任务不得影响活跃 reservation。

# Read Model 状态机

> 本文件只描述共享 `workbench_relation` read model。关联台 page generation 与其它已退役页面的
> 历史 projection、active generation、页面 freshness 和 worker 状态不再是当前合同。

## 当前集合

`READ_MODEL_MANIFEST`、scope policy、App Status registry 和 runtime worker registry
必须精确登记 `workbench_relation`。

关联台与其它 direct 页面在 PostgreSQL `REPEATABLE READ READ ONLY` snapshot 中读取 canonical facts
和 active canonical relations。页面 GET 只有 loading、empty、error、result，不返回
read-model status/scope/version，不 enqueue，不轮询，也不回退历史 projection。

## 共享 Read Model 状态

| 状态 | 事实 | 允许行为 |
| --- | --- | --- |
| `missing` | 没有满足 schema/source contract 的 projection/readiness | 经 gateway enqueue 精确 scope；消费者显示 refreshing/missing |
| `refreshing` | current-effective dirty scope/outbox 为 pending/processing/deferred | worker 继续处理；保留诊断，不返回 fresh |
| `fresh` | schema/source proof、payload contract、current-effective queue 状态全部通过 | 返回共享 projection；此后才允许写 Redis cache |
| `stale` | schema/source/payload proof 不匹配 | 映射为 refreshing 并经 gateway enqueue 精确 scope |
| `failed` | current-effective worker/outbox/readiness failure 未被后续 active refresh 覆盖 | 暴露具体 scope/error；不得吞掉或伪装 fresh |
| `unavailable` | PostgreSQL、queue、repository 或关键 worker 不可用 | App Status blocked/degraded；不得同步扫描替代 |

历史 failure 已被同 scope 新的 pending/processing 覆盖时，当前状态是 `refreshing`；
旧错误只作诊断，不能继续阻断。`refresh_enqueued=false` 只表示本次请求复用了已有 active
refresh，不表示 fresh。

## Refresh 状态

| 状态 | 合同 |
| --- | --- |
| `validated` | `ReadModelScopePolicyRegistry` 已 normalize/validate scope |
| `deduped` | 同 scope 已有 active refresh；返回 refreshing，不重复写 outbox |
| `queued` | gateway 已原子写入 `job.outbox_events` 与 `job.read_model_dirty_scopes` |
| `processing` | 登记 worker 已 claim；PostgreSQL 仍是状态事实源 |
| `published` | projection、schema/source proof 与 readiness 已原子收敛 |
| `failed` | worker 记录 current-effective failure，等待明确 retry/repair |

共享 relation 模型接受 `YYYY-MM` 或 `all`；`all` 是 fan-out command，只枚举并投递
月份 shard，不发布 materialized parent projection，也不得写假 fresh readiness。关联台 `month=all`
在当前只读请求内直接查询 canonical facts，不通过该状态机。

## 允许的流转

```text
registered read-model query
  -> expected/actual proof mismatch
  -> ReadModelRefreshGateway
  -> durable dirty scope + outbox
  -> registered worker
  -> projection + readiness publish
  -> fresh query
```

显式 maintenance/reapply/repair 可以按已登记合同产生精确 `workbench_relation` refresh。关联台及其它
canonical 页面 GET、确认、撤回、规则保存和 import confirm 不得重新制造 page fan-out。

## 非法状态

- manifest、scope policy、App Status registry、worker registry 的 read-model key 集合不一致。
- 已退役页面 key/event/scope/worker/deploy env 重新出现。
- 已退役页面读取历史 projection、readiness、Redis payload 或 active generation；关联台重新接入任何
  page freshness/generation gate。
- 业务 service 绕过 gateway 直接 SQL 写 dirty scope/outbox。
- Redis 或 RabbitMQ 被当作 freshness 状态事实源。
- `fresh` 缺少 schema/source/payload proof，或同 scope 仍有 current-effective active blocker。
- fan-out-only `all` 被当成页面可查询 projection。
- 缺少 canonical repository 时回退旧 read model，而不是 fail fast。

## 恢复与回滚

- 共享 projection failure 通过受控 requeue/repair/force-refresh 恢复；保留 actor、scope、
  reason 和 audit。
- `scripts/check-read-model-scope-contracts.py` 默认只读检查旧 runtime 状态；apply 只处理
  policy 明确判定 invalid 的行，不补投已退役页面 refresh。
- migration `0127_direct_canonical_page_runtime_retirement.sql` 不删除历史表或 backlog；
  它们只供上一版本回滚，当前代码不得读写。
- 物理 drop 需要独立、可回滚 migration，并在生产确认零 reader、writer、processing
  backlog 后执行。

## 验证入口

- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_read_model_refresh_gateway.py`
- `tests/test_read_model_query_gateway.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_deploy_runtime_examples.py`
- `tests/test_page_read_model_fact_display_matrix.py`

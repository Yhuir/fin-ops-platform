# 监控与告警

日期：2026-08-15

## 当前可观察对象

- `/health`、`/health/ready`、`/metrics`。
- Admin App Health dashboard 与 canonical page/system audit。
- API endpoint duration、DB duration、connection acquire、SQL execute/fetch、query count、payload size。
- OA sync、background jobs、PostgreSQL outbox、worker heartbeat。
- RabbitMQ publish backlog、queue depth、unacked、DLQ（启用时）。
- 退役 projection event 负向审计。

## 必须告警

- `/health/ready` 非 200 或 payload 不完整/过慢。
- required worker missing/stale/mismatch；required exact-set 不是四个当前 instance。
- outbox pending age 持续增长、failed/dead-lettered 非零并增长。
- RabbitMQ publish failed、DLQ 增长或 eligible queue 没有 consumer。
- 核心 GET p95 > 1000ms 或 p99 > 2000ms、5xx、HTML fallback、连接池等待或 query count 异常。
- OA Mongo/同步连续失败、PostgreSQL canonical commit 失败、import/reset job 失败。
- 任意新 `%.read_model.refresh` event，或 runtime 访问已退役 projection schema/worker/env/timer。

## HTTP 与数据库诊断

先按 endpoint 对比：

1. 总 duration；
2. connection acquire；
3. database duration 与 SQL execute/fetch；
4. query count、rows/payload；
5. 错误 request ID。

只有数据库时间/扫描证据指向 SQL 时才用 `EXPLAIN (ANALYZE, BUFFERS)` 和索引调优。禁止用页面缓存或后台
projection 遮盖无界 SQL。生产普通巡检用 authenticated bounded GET 和 plain EXPLAIN；ANALYZE 需独立窗口。

## Queue 与 worker 指标

- outbox：pending、processing、failed、dead-lettered、oldest age、publish status。
- worker：instance/kind/registration、heartbeat lag、attempt/retry/terminal failure。
- RabbitMQ：publisher confirm latency、unpublished/publish-failed backlog、queue depth/unacked/DLQ。
- matching：domain scope pending/processing/failed 与 source-version convergence。

RabbitMQ 只补充 transport 证据，不能替代 PostgreSQL outbox/job 状态。不得删除失败行、伪造 heartbeat 或清空
DLQ 来获得绿色状态。

## Canonical audit

一次 system audit 使用一个 outer `REPEATABLE READ READ ONLY` snapshot，验证页面合同、active relation 双向成员、
App Health inventory 与业务 integrity。Audit 只读，不 enqueue、不修复。发现 drift 时保存 audit ID、release、
snapshot 和 issue samples，再由对应 owner 的正式 repair/service 处理。

## 生产性能采样

```bash
scripts/with-production-admin-token.sh \
  python3 -m fin_ops_platform.tools.http_slo_probe --json

scripts/with-production-admin-token.sh \
  python3 -m fin_ops_platform.tools.runtime_sync_closure_gate --profile stability --json
```

API probe 只接受业务成功 JSON，不接受 HTML fallback。报告保存 endpoint samples、p50/p95/p99、status/shape、
release/commit 与时间窗。Admin token 不得出现在命令输出或 artifact。

## 受控写闭环

`write_operation_e2e_smoke` 仅用于显式批准、测试自有、可逆 scenario。它通过正式 API/UoW 执行，验证
idempotency/CAS、当前页 canonical reread、受影响/非消费者页面与恢复结果。网络 outcome 不明确时禁止盲重试。

自动 release gate 不产生真实业务写；只使用 `pg_temp` 可逆 insert/read/delete/rollback 验证 DB write path。

## 日志安全

记录 request ID、route、actor、duration、status、event/job ID、attempt 和错误摘要。禁止记录 token、密码、完整
附件正文、原始财务文件或敏感 payload。高风险修复必须另有 durable audit。

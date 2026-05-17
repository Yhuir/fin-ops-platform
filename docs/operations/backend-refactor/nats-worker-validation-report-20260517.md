# NATS Worker Replay Staging Validation Report - 2026-05-17

## 判定

| 字段 | 值 |
| --- | --- |
| go/no-go | `NO_GO` |
| blocking | `true` |
| operator | `yu` |
| generated_at | `2026-05-17T09:23:00+08:00` |
| staging actual execution | `false` |
| nats_worker_replay gate | `NO_GO` |
| PostgreSQL final task fact source | `true` |
| OA source database accessed | `false` |
| production cutover | `false` |

本报告没有执行真实 staging replay：`DATABASE_URL` 和 `NATS_URL` 未提供。已完成 Rust/Python 本地实现级测试，但这不能替代 staging 的 JetStream stream/consumer、ack/redelivery、DLQ 和 manual replay 证据，因此总判定为 **NO_GO**。

## 本地实现级验证

| 命令 | 结果 | 覆盖 |
| --- | --- | --- |
| `cargo test --workspace jobs::outbox_publisher` | passed | claim/publish ack/retry/dead letter/payload guard，5 passed |
| `cargo test --workspace infra::nats` | passed | `Nats-Msg-Id`、`X-Event-Id`、`X-Idempotency-Key`、`X-Trace-Id` headers，1 passed |
| `pytest worker task tests` | passed | consume、attempt、heartbeat、success/fail/retry/dead_letter、ack/nak/term，16 passed |
| `job_dead_letter_replay.py --help` | passed | list/replay CLI 参数存在 |
| `run_worker_task_consumer.py --help` | passed | env-backed worker consumer 参数存在 |

## Staging 验证状态

| 维度 | 状态 |
| --- | --- |
| Streams `FINOPS_EVENTS/FINOPS_JOBS/FINOPS_DLQ` | `not_executed_no_nats_url` |
| Consumers / AckWait / MaxDeliver / BackOff | `not_executed_no_nats_url` |
| Outbox claim batch | `unit_test_passed_not_staging_verified` |
| Publish ack -> `published` | `unit_test_passed_not_staging_verified` |
| Worker consume/attempt/heartbeat/success/fail/retry/dead_letter | `unit_test_passed_not_staging_verified` |
| Ack delay | `not_executed_no_staging_message` |
| Redelivery/backoff | `not_executed_no_nats_url` |
| PostgreSQL DLQ rows | `unit_tested_paths_not_staging_verified` |
| Manual replay by `task_id/event_id` | `not_executed_no_database_url` |
| Replay operator/reason/result audit | `not_executed_no_database_url` |

## Replay / DLQ 结果

| 项 | 结果 |
| --- | --- |
| actual staging replay executed | `false` |
| PostgreSQL dead letter rows replayed | `not_evaluated` |
| new worker task ids | `[]` |
| new outbox event ids | `[]` |
| audit events recorded | `not_evaluated` |
| DLQ result | `not_executed_no_database_url_or_nats_url` |

## Blockers

| code | dimension | required action |
| --- | --- | --- |
| `STAGING_POSTGRES_URL_MISSING` | `postgres_staging` | 提供受控 staging `DATABASE_URL` 后重跑验证。 |
| `STAGING_NATS_URL_MISSING` | `nats_jetstream` | 提供受控 staging `NATS_URL` 后重跑 stream/consumer/ack/redelivery 验证。 |
| `MANUAL_REPLAY_NOT_EXECUTED` | `manual_replay` | 对 disposable staging dead letter 执行 list/replay，并记录 operator、reason、result。 |

## 安全边界

- 未访问 OA 源数据库。
- 未修改业务 API，未切换生产。
- 未记录 PostgreSQL 或 NATS 连接值。
- NATS/Redis 不作为最终事实源；任务事实以 PostgreSQL 为准。

## 配套 JSON

- `docs/operations/backend-refactor/nats-worker-validation-report-20260517.json`

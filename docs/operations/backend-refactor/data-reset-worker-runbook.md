# Data reset worker runbook

本文档覆盖 `settings_data_reset` worker 的生产级操作边界。两个 API endpoint 必须保持 queue-only：

- `POST /api/workbench/settings/data-reset/jobs`
- `POST /api/workbench/settings/data-reset`

请求路径只创建 `app.data_reset_requests`、`job.worker_tasks`、`job.outbox_events`、`audit.events` 和 `app.write_idempotency_records`，不得同步执行破坏性 reset。

## 前置条件

执行 worker 前必须同时具备：

- `approval_id`：来自 product/ops 审批事实源，不能由 operator 临时编造。
- `backup_evidence_id`：指向可恢复备份或 PITR 点。
- 维护窗口上下文：显式设置 `FIN_OPS_ALLOW_DATA_RESET_WORKER=1` 或使用 `run_worker_task_consumer.py --allow-data-reset-worker`。
- staging proof：至少一次真实 staging worker 执行、lineage join、恢复/PITR drill 证据。
- secret redaction：worker payload/source 不读取、不记录 `oa_password`；错误和 result summary 通过敏感字段过滤后写入。

缺任一条件时，worker 必须 fail-fast，不执行 destructive reset，并保持 cutover 报告 `NO_GO_EXTERNAL_EVIDENCE_REQUIRED`。

## 状态机

| 状态 | 含义 | Operator 动作 |
| --- | --- | --- |
| `queued` | API 已排队，worker 尚未开始。 | 可在维护窗口取消；确认 idempotency、approval、backup evidence。 |
| `running` | worker 已拿到 lease 并开始执行。 | 禁止直接删除事实；只允许监控、记录 evidence、准备恢复或补偿。 |
| `cancelled` | queued 阶段取消。 | 保留审计，不重用旧 idempotency key；如需重提，创建新 request。 |
| `failed` | worker 失败或缺 evidence fail-fast。 | 查询 lineage，按失败阶段选择重试、恢复、PITR 或补偿。 |
| `succeeded` | worker 完成并写入 result summary/proof。 | 运行 lineage 脚本、read-model validation、业务抽样和恢复演练回查。 |

## 取消窗口

只允许取消 `queued` task。取消必须更新 `job.worker_tasks.status='cancelled'` 和 `app.data_reset_requests.status='cancelled'`，并记录 audit event。

task 进入 `running` 后不得通过删除 `app.data_reset_requests`、`job.worker_tasks`、业务 facts 或 outbox 事件来“回滚”。running 后的恢复只能走：

- 已验证 backup/PITR restore。
- 以新 worker task 创建补偿导入、read-model rebuild 或业务事实修复。
- 对 partial failure 保留失败事实和 attempt lineage，禁止覆盖证据。

## 执行命令

正式 worker：

```bash
FIN_OPS_ALLOW_DATA_RESET_WORKER=1 \
PYTHONPATH=backend/src \
python3 scripts/tools/run_worker_task_consumer.py \
  --database-url "$DATABASE_URL" \
  --nats-url "$NATS_URL" \
  --worker-id "settings-data-reset-worker-$(hostname)"
```

一次性 proof/report：

```bash
python3 scripts/tools/data_reset_worker_staging_proof.py \
  --database-url "$DATABASE_URL" \
  --task-id "$TASK_ID" \
  --approval-id "$APPROVAL_ID" \
  --backup-evidence-id "$BACKUP_EVIDENCE_ID" \
  --pitr-evidence-id "$PITR_EVIDENCE_ID" \
  --staging-run-id "$STAGING_RUN_ID" \
  --staging-environment "$STAGING_ENV" \
  --confirm-real-staging \
  --confirm-product-ops-approval \
  --confirm-restorable-backup \
  --confirm-pitr-drill
```

lineage join：

```bash
python3 scripts/tools/data_reset_audit_lineage.py \
  --database-url "$DATABASE_URL" \
  --task-id "$TASK_ID"
```

## Lineage 证据

每次执行后必须能 join 到以下事实；join 缺口必须在报告中显式列出：

- `app.data_reset_requests`
- `job.worker_tasks`
- `job.outbox_events`
- `audit.events`
- `app.write_idempotency_records`
- `job.worker_attempts`

worker success/failure result summary 和 error detail 中必须能定位：

- `task_id`
- `outbox_event_id`
- `data_reset_request_id`
- `attempt_id`
- `trace_id`

## 恢复和补偿

`reset_bank_transactions` 或 `reset_invoices` 成功后发现误删：

1. 冻结新的导入确认和匹配任务。
2. 用 `backup_evidence_id` 对应备份或 PITR 点恢复到隔离库。
3. 对比被 reset scope 的 import/file/workbench facts。
4. 通过补偿导入或受控 restore 写回，保留新 audit/outbox。
5. 重建 workbench/search/cost/tax read models。

`reset_oa_and_rebuild` partial failure：

1. 保留 worker attempt 和 failure detail。
2. 禁止直接清理 OA/workbench facts。
3. 如果 OA rebuild 失败，优先重试 rebuild/read-model task；如果人工状态已清除且需要回滚，按备份恢复或补偿事件恢复。

## 监控告警

至少配置以下告警：

- `settings_data_reset` task `running` 超过维护窗口阈值。
- `job.worker_attempts.status in ('failed', 'dead_lettered')`。
- `app.data_reset_requests.status='failed'`。
- `job.outbox_events.subject='finops.jobs.settings.data_reset'` backlog 或 dead letter。
- worker heartbeat 丢失或 lease 过期。
- data reset 后 read-model rebuild backlog 或 stale scope 超阈值。

## Secret redaction

- API 可验证 `oa_password`，但 queue payload、source、worker result 和 error detail 不得保存 password。
- worker 不读取 `oa_password`，只读取 `action`、`approval_id`、`backup_evidence_id`、`scope`。
- 日志中只允许记录证据 ID、task ID、attempt ID、trace ID；禁止记录 token、password、database URL、对象存储 credential。

## Go/no-go

本 runbook 和本地脚本只能补齐代码侧 proof 能力。没有真实 staging、product/ops approval、backup evidence 和 PITR/restore drill 时，`p0-data-reset-worker-staging-proof-20260517.json` 必须保持 `NO_GO_EXTERNAL_EVIDENCE_REQUIRED`。

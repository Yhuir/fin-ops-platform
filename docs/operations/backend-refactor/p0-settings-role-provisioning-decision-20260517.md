# P0 settings role provisioning decision

生成时间：2026-05-17T11:20:25Z

状态：`IMPLEMENTED_RECOMMENDED_DECISION_PENDING_PRODUCT_OPS_APPROVAL_AND_WORKER_SLA`

## 结论

本次代码实现采用推荐方案：`POST /api/workbench/settings` 不再把 OA MySQL 角色同步作为请求路径内的同步副作用。Rust/Axum 写入成功的语义调整为：

1. PostgreSQL `app.settings_profiles` 中的 workbench settings fact 已保存并成为 active 版本。
2. 同一 PostgreSQL 事务内已记录 `settings.updated` 审计和 `settings.save` 幂等记录。
3. 同一事务内已排队 identity role provisioning request、worker task 和 outbox event，或相同 access_control payload 已有排队/历史 provisioning request。

这不代表 OA role 已经同步完成。product/ops 仍需人工批准这个合同变化。

## 背景

旧 Python 合同中，`AppSettingsService.update_settings` 会同步调用 `OARoleSyncService.sync_access_control`。如果 OA role sync 失败，`POST /api/workbench/settings` 返回 `502 oa_role_sync_failed`；如果 app settings 持久化失败，还会尝试回滚 OA role sync。

现有 P0 报告将该差异标记为 `SETTINGS_WRITE_OA_ROLE_SYNC_DECISION`，推荐迁移为 audited async task/outbox workflow。本次实现把推荐方案落到 Rust/PostgreSQL，但不伪造 product/ops 批准。

## 已实现合同

- 新增 `app.identity_provisioning_requests`，记录 settings profile/version、状态、请求人、worker task、outbox event、idempotency key、trace id、payload hash 和失败字段。
- settings 写入事务内新增 `job.worker_tasks`，`task_type=identity_role_provisioning`。
- settings 写入事务内新增 `job.outbox_events`，`event_type=identity.role_provisioning_requested`，`subject=finops.jobs.identity.role_provisioning`。
- provisioning payload 使用 `schema_version=finops.identity.role_provisioning.v1`，包含 `settings_profile_id`、`settings_version`、`access_control`、`assignments`、`source=workbench_settings`、`requested_by`、`trace_id`。
- provisioning payload 不包含 secret。
- 保留 `audit.events(settings.updated)`，并在创建 provisioning request 时补充 `audit.events(identity_role_provisioning.requested)`。
- `settings.save` 原幂等合同继续生效；同一 key 不同 payload 仍是 409。
- 对 `(settings_profile_id, settings_version)`、provisioning idempotency key、`payload_hash` 建唯一约束，避免相同 settings profile/version 或相同 access_control/assignments 重复创建 provisioning request/job/outbox。

## 未改变事项

- 没有新增同步 OA MySQL 写入。
- route 层没有新增 SQL。
- settings write 不依赖 OA 可用性。
- 本次不处理 data reset worker 文件，也不更新 Prompt07 final report。

## 仍需人工批准

- Product：批准“settings write 成功不代表 OA role 已同步完成”的合同变化。
- Ops：批准 UI/health/告警口径，明确 queued/running/failed provisioning 如何展示和升级。
- Ops：定义 worker 失败 SLA、重试/dead-letter 策略、恢复 runbook 和 staging 证据要求。

## 仍余风险

- worker 实际连接 OA 并应用角色的执行路径仍需 staging proof。
- UI/health endpoint 若不展示 provisioning 状态，用户可能误以为 settings 保存即权限生效。
- 告警必须区分 settings persistence 成功和 identity provisioning 完成。

## 验证

- `cd rust/fin-ops-api && cargo fmt --all --check`：PASS
- `cd rust/fin-ops-api && cargo check --workspace`：PASS
- `cd rust/fin-ops-api && cargo test platform_legacy --workspace`：PASS，35 passed
- `cd rust/fin-ops-api && cargo test identity_role_provisioning --workspace`：PASS，3 passed

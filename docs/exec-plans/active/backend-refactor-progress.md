# Axum + PostgreSQL 后端重构进度

## 当前决策

- PostgreSQL 不开放公网访问。
- 当前 PostgreSQL 只监听 `localhost:5432`。
- 如果未来 Axum API、Worker 和 PostgreSQL 分机部署，也只允许内网/VPC 访问，并通过防火墙白名单、最小权限账号和 TLS 加固。
- OA 源数据库不纳入备份、导出、恢复、迁移或压测范围。
- 只备份 app 关联 Mongo 数据库 `fin_ops_platform_app`。

## 已完成服务器操作

- 已在 `139.155.5.132` 创建 `/data/backups/fin_ops` 目录结构。
- 已安装 PostgreSQL 16.12。
- 已初始化并启动 `postgresql.service`。
- 已创建 `fin_ops` 数据库。
- 已创建账号：`fin_ops_migrator`、`fin_ops_api`、`fin_ops_worker`、`fin_ops_readonly`。
- 已创建 schema：`app`、`read_model`、`job`、`audit`、`staging`。
- 已启用扩展：`pgcrypto`、`pg_trgm`、`btree_gin`。
- 已将本机 TCP 认证设置为 `scram-sha-256`。
- 已验证四个业务账号可连接。
- 已验证 `fin_ops_readonly` 不能写 `app` schema。

## 已完成 app Mongo 备份

- 备份目录：`/data/backups/fin_ops/2026-05-16_012900`
- 备份文件：`app-mongo-fin_ops_platform_app.archive.gz`
- checksum：`1968e81888dd359ba7d9d8424cdef399744d81a6d5e7305db1f8222404b9422a`
- `mongorestore --dryRun` 已通过。
- 已恢复到测试库 `fin_ops_platform_app_restore_test_20260516`。
- collection count 比对：`total=50 diff=0`。
- GridFS 抽样：`integrity=OK`。

## 已完成子代理任务

- 子代理 A：仓库盘点与契约梳理，输出 `backend-refactor-inventory.md`。
- 子代理 D：PostgreSQL schema 详细设计，输出 `docs/architecture/backend-refactor/postgresql-schema-notes.md`。
- 子代理 G/H：outbox、任务队列、Worker 协议、读模型和搜索设计，输出 `outbox-and-jobs.md` 与 `read-models-and-search.md`。
- 子代理 H：生产就绪、观测、安全、切换和回滚 runbook，输出 `observability-and-alerting.md`、`production-readiness-checklist.md` 与 `cutover-and-rollback-runbook.md`。
- 子代理 E：Axum API 阶段 1 骨架，输出 `rust/fin-ops-api/` 与 `docs/dev/axum-backend.md`。
- 子代理 M1/M2/M3：按模块生成 PostgreSQL SQLx migrations，输出 `rust/fin-ops-api/migrations/0001_foundation.sql` 到 `0007_read_models_search.sql`。

## 已完成 migration 验证

- 已将 `0001` 到 `0007` 复制到服务器临时目录执行 PostgreSQL 16.12 空库验证。
- 验证数据库：临时库，执行完成后已删除。
- 验证结果：全部通过。
- 创建表数量：`38`。
- 验证扩展：`btree_gin`、`pg_trgm`、`pgcrypto`。
- 验证边界：只验证 schema 语法和依赖顺序，不导入生产数据，不访问 OA 源库。

## P0 baseline（2026-05-17）

- 工作树基线：任务开始时仅发现既有未提交修改 `docs/archive/prompts/codex prompt.md`，本任务未回滚或改动该文件。
- Rust 格式门禁：初始 `cargo fmt --all --check` 失败，仅涉及 `rust/fin-ops-api/crates/fin-ops-api/src/repositories/platform_legacy.rs` 和 `rust/fin-ops-api/crates/fin-ops-api/src/services/platform_legacy.rs` 的 rustfmt 排版差异；已执行 `cargo fmt --all` 修复。
- Rust 验证：`cargo fmt --all --check` 通过，`cargo check --workspace` 通过，`cargo test --workspace` 通过（library tests `107 passed`，bin/doc tests `0`）。
- Python 旧后端验证：`PYTHONPATH=backend/src python3 -m unittest discover -s tests -v` 通过（`Ran 1058 tests`，`OK (skipped=5)`）。
- 生产 readiness gate：`python3 scripts/tools/backend_refactor_readiness_gate.py --format markdown` 结论仍为 `NO_GO`，共 `9` 个阻塞项。
- 当前 readiness 阻塞项：`postgres_backup_pitr`、`migration_dry_run`、`file_checksum`、`api_shadow_validation`、`nats_worker_replay`、`read_model_rebuild`、`monitoring_alerts`、`load_test`、`cutover_window_rollback`。
- 机器可读报告：`docs/operations/backend-refactor/p0-baseline-report-20260517.json`。
- 结论：P0 Prompt 01 基线任务完成；整体 P0 生产切流仍为 `NO_GO`。

## P0 API 合同冻结（2026-05-17）

- 已运行 `python3 scripts/tools/api_route_inventory_check.py`，route inventory 结构检查结果为 `GO`。
- 当前 `api-route-inventory-route-level.json` 中仍为 `pending_contract` 或 `blocked_fact_source` 的 route 为 `43` 条（`pending_contract=16`，`blocked_fact_source=27`）。
- `docs/architecture/backend-refactor/remaining-api-contracts.md` 保留并冻结 P0 范围 `50` 条 route：其中 `7` 条历史 P0 route 已有 Rust route，但仍需要 shadow、事实源或 readiness 证据，不能视为可切流。
- 已在 `remaining-api-contracts.md` 新增 `P0 最终合同冻结（2026-05-17）`，每条 route 均明确：`method/path`、`final_contract`、`request_schema`、`response_schema`、`auth_policy`、`permission_failure_semantics`、`audit_event`、`idempotency_requirement`、`error_codes`、`fact_source`、`rust_target_module`、`tests_required`、`migration_dependency`、`shadow_fixture_needed`。
- 机器可读报告：`docs/operations/backend-refactor/p0-api-contract-freeze-20260517.json`。
- 冻结状态统计：`ready_for_implementation=8`、`needs_schema=40`、`needs_product_decision=2`、`blocked_by_environment=0`。
- 仍需产品/架构决策：`POST /api/workbench/settings/data-reset` 是否继续保留同步执行语义；`GET|PATCH|DELETE /api/etc/reconciliation-tasks/{task_id}/*` 需要在实现前拆分为 typed child route 合同。
- 结论：P0 Prompt 02 合同冻结完成；未实现任何 route，整体 P0 生产切流仍为 `NO_GO`。

## P0 PostgreSQL 事实源差距闭环（2026-05-17）

- 已按冻结合同回读 `remaining-api-contracts.md`、`0001` 到 `0008` migration、`data-model-and-read-models.md`、目标架构和生产就绪检查表。
- 已新增 `rust/fin-ops-api/migrations/0009_p0_api_fact_sources.sql`，覆盖 P0 50 条 API 的剩余事实源差距：background job ack、settings/project、data reset、ledger/reminder、import preview/session/revert lineage、matching run、turnover extra/event、ETC import/task/batch/invoice event、tax certified preview、export artifact 和 staging backfill plan。
- `0009` 复用既有 `app`、`job`、`staging`、`read_model`、`audit` schema；未新增平行事实源，未把最终状态放入 Redis、内存或临时 JSON。
- 新增表统一保留 `created_at`、`updated_at`、`created_by`、`updated_by`、`audit_event_id`、`idempotency_key`（写入/事件表）、`legacy_id_map_id`、`legacy_collection`、`legacy_id`、状态/版本约束、唯一约束和查询索引；新增 `staging.p0_api_fact_source_backfill_plan` 承载 Mongo/GridFS/OA 回填计划。
- 已新增 migration 结构测试 `rust/fin-ops-api/crates/fin-ops-api/src/migration_contracts.rs`，并在 `lib.rs` 只以 `#[cfg(test)]` 接入，验证 `0009` 覆盖必要表、审计、幂等、legacy traceability 和 updated_at trigger。
- 机器可读报告：`docs/operations/backend-refactor/p0-postgres-fact-source-gap-20260517.json`，包含 50 条 API 的 PostgreSQL 表、字段组、索引/约束、迁移状态和 legacy id map 口径。
- 结构验证：`cargo test -p fin-ops-api migration_contracts` 通过；`python3 -m json.tool docs/operations/backend-refactor/p0-postgres-fact-source-gap-20260517.json` 通过，报告 `route_fact_sources=50`。
- 仍需产品/实现前决策：`POST /api/workbench/settings/data-reset` 是否保持 job-only 或开放 worker-maintenance execution；`GET|PATCH|DELETE /api/etc/reconciliation-tasks/{task_id}/*` 需要拆分 typed child route 合同。
- 数据库 apply/dry-run：本机 PostgreSQL 可连接但版本为 `14.15 (Homebrew)`，低于目标架构要求的 PostgreSQL 16/17；隔离临时库顺序执行 migration 时在既有 `0002_imports_files.sql` 的 `NULLS NOT DISTINCT` unique index 语法处失败，未到达 `0009`。临时库 `p0_prompt03_20260517` 已删除；该项记录为 `NO_GO_LOCAL_POSTGRES_VERSION`，不能作为 staging migration GO 证据。
- 结论：P0 Prompt 03 schema/事实源计划完成；整体 P0 生产切流仍为 `NO_GO`，还需要真实 PostgreSQL migration dry-run、API 实现、shadow case 清零、NATS/Worker、read model rebuild、PITR/rollback/load/alert 验证。

## P0 平台类 API 实现（2026-05-17）

- 已实现并接入 Rust route：`POST /api/background-jobs/{job_id}/acknowledge`、`POST /api/workbench/settings`、`POST /api/workbench/settings/projects/sync`、`POST /api/workbench/settings/projects`、`DELETE /api/workbench/settings/projects/{project_id}`、`POST /api/workbench/settings/data-reset/jobs`、`POST /api/workbench/settings/data-reset`、`GET|POST /projects`、`GET /projects/{project_id}`、`POST /projects/assign`、`GET /ledgers`、`GET /ledgers/{ledger_id}`、`POST /ledgers/{ledger_id}/status`、`GET /reminders`、`POST /reminders/run`。
- 分层边界：`routes/platform_legacy.rs` 只做 HTTP/path/query/body/header 解析、actor/trace 注入和状态码；`services/platform_legacy.rs` 做合约校验、legacy 状态枚举和 use case command 组装；`repositories/platform_legacy.rs` 负责 PostgreSQL SQL、事务、audit、outbox 和 idempotency。
- 写路径覆盖：background job ack 写 `job.worker_task_acknowledgements`（含 `acknowledged_at/trace_id`）；settings 写 `app.settings_profiles`，读后投影从 `app.settings_profiles` + `app.project_profiles` 生成旧 Python settings payload；project create/delete 写 `app.project_profiles`，expected_version 冲突返回 409；project assignment 校验目标 project/object 后写 `app.project_assignments/app.project_profile_events` 并 supersede 旧 active assignment；data reset 写 `app.data_reset_requests`（含 `requested_by/outbox_event_id`）并排队 `job.worker_tasks/job.outbox_events`，同一 action active job 返回 `settings_data_reset_job_running`；ledger status 写 `app.ledgers/app.ledger_events`，expected_version 冲突返回 409；reminder run 写 `app.reminder_runs` 并排队 worker task/outbox。所有写路径均记录 actor、trace/request id、audit 或 outbox、idempotency。
- 已修正 Prompt 03 产出的 `0009_p0_api_fact_sources.sql`：data reset action、ledger type/status、reminder status 均改为旧 Python domain enum 值，避免把错误枚举固化到 PostgreSQL。
- 已补 Rust tests：平台 service 覆盖 ack actor/idempotency、settings normalization、data reset/reminder async job、ledger legacy status 校验、project assignment object type/UUID 校验；settings projection 测试覆盖旧 Python access control、bank mapping、layout、OA import normalization；repository 结构测试覆盖平台 P0 query 事实源。
- 已修正 `GET /ledgers` 旧 Python 等价性：Rust PostgreSQL 查询现在区分 `view=all`、`view=overdue`、`view=due` 和未知非 all 的 open fallback；`overdue/due/open` 类视图统一排除 `resolved/cancelled`，`due` 使用旧服务的 7 天窗口。
- 已更新 `docs/dev/api-fixtures/api-route-inventory.json`、`docs/dev/api-fixtures/api-route-inventory-route-level.json` 和 `docs/dev/api-fixtures/business-api-shadow-validation.json`，新增平台写入/读取 shadow endpoint，并生成 route-level inventory：`docs/operations/backend-refactor/p0-platform-route-level-inventory-20260517.json`。
- 已硬化验证工具：`api_shadow_validate.py --validate-fixture-only` 现在会尊重 `--endpoint-id/--risk` 过滤，未知 endpoint filter 会返回 `NO_GO`；`api_route_inventory_check.py` 现在能发现 Axum `get(...).post(...)` 链式 route，因此 `POST /projects` 不再被扫描遗漏。
- 已新增 runtime shadow 前置检查：`scripts/tools/platform_shadow_preflight.py`，并生成 `docs/operations/backend-refactor/p0-platform-shadow-preflight-20260517.json` 与 `.md`。该报告会固定检查 16 个平台 endpoint fixture、Python/Axum base URL、`DATABASE_URL`、本地 PostgreSQL major、Docker daemon、`cargo sqlx` 可用性、scoped fixture 内 `${...}` runtime 变量是否已提供、平台 seed fact 是否能被 PostgreSQL probe 证明、fixture 内写样本是否存在重复幂等键/data reset action 复用/destructive target reuse，以及 Rust `middleware/auth.rs` 要求的 Axum trusted header 认证条件。
- `p0-platform-shadow-preflight-20260517.json` 现在额外输出 `runtime_shadow_input_plan`：列出 13 个必须导出的环境变量、5 步启动/迁移/probe/shadow validation 顺序、5 条 PostgreSQL fact probe 命令，以及最终 `api_shadow_validate.py` runtime shadow 命令。该计划仍为 `NO_GO`，因为当前 shell 缺 base URL、`DATABASE_URL`、runtime fixture IDs、认证 token/password 和 Axum trusted_headers 确认。
- 已新增 `scripts/tools/platform_shadow_seed.py`：按唯一 `SHADOW_RUN_ID` 生成确定性的 PostgreSQL seed SQL 和 env export 文件，覆盖 runtime shadow 需要的 `BACKGROUND_JOB_ID`、`BANK_TRANSACTION_ID`、`LEDGER_ID`、`PROJECT_ID`、`PROJECT_DELETE_ID` 和 `SHADOW_RUN_ID`。preflight 的 `runtime_shadow_input_plan` 已加入 `platform_postgres_seed` 步骤：`python3 scripts/tools/platform_shadow_seed.py --run-id "$SHADOW_RUN_ID" --apply`。当前因缺 `DATABASE_URL` 仅验证生成，不执行 apply。
- 已新增 runtime shadow runner：`scripts/tools/platform_shadow_runtime.py`，并生成 `docs/operations/backend-refactor/p0-platform-runtime-shadow-20260517.json` 与 `.md`。runner 会串联 preflight、Python `/health`、Axum `/healthz`、Axum `/readyz`，只有全部 `GO` 后才执行 16 个平台 endpoint 的 Python-vs-Axum runtime shadow（含 permission-failure cases）。当前报告为 `NO_GO`，blocking reasons 为 `preflight_no_go` 与 `shadow_service_health_no_go`，实际 shadow validation 保持 `SKIPPED`。
- 已补齐平台 shadow fixture 默认认证头：保留旧 Python 使用的 `Authorization: Bearer ${FIN_OPS_SHADOW_OA_TOKEN}`，并新增 Axum trusted headers `x-fin-ops-oa-user-id`、`x-fin-ops-oa-username=YNSYLP005`、`x-fin-ops-oa-display-name`、`x-fin-ops-oa-roles`、`x-fin-ops-oa-permissions=finops:app:view`。Python 会忽略这些 trusted headers，Axum 则需要它们避免 protected route 出现 `oa_identity_lookup_failed`。
- 已硬化 data reset 密码处理：Rust `POST /api/workbench/settings/data-reset/jobs` 和 `POST /api/workbench/settings/data-reset` 现在要求 `oa_password` 非空，但不会把该字段写入 `PlatformJobCommand.source`、`payload` 或 `request_payload`，避免通过 outbox、audit 或 idempotency 记录持久化 OA 密码；缺失密码返回 `oa_password_verification_failed`。真实 OA 密码校验仍需要 staging/legacy 认证适配器，runtime GO 前不能只凭本地 presence check 视为等价。
- 已修正 background job ack 权限等价性：Rust middleware 现在把 `POST /api/background-jobs/{job_id}/acknowledge` 作为 `AppSession`，只要求 `can_access_app`，与旧 Python protected route 和冻结合同一致；settings/data reset/project create 仍保持 `Admin`，其他写业务事实 route 仍按 `Mutate`。
- 已补 `POST /reminders/run` 请求不变量校验：`days_ahead` 现在必须为空或非负，非法值在 service 层返回 `invalid_reminder_run_request`，不会进入 `job.worker_tasks/outbox_events`，与 `app.reminder_runs.days_ahead >= 0` schema invariant 一致。
- Prompt04 平台代码缺口审计补强：本轮复核 `platform_legacy` 与 `task_status` route/service/repository 后，补齐 `POST /api/background-jobs/{job_id}/retry` 的旧 Python protected-route 权限等价性和 `Idempotency-Key` header 注入；后台 job command 的 audit/outbox event type 改为冻结合同名称（如 `background_job.retry_requested`、`project_sync.requested`、`data_reset.requested`、`reminder.run_requested`），避免由 `operation + ".requested"` 生成不一致事件名。新增 targeted Rust tests 覆盖 retry 权限、header 幂等和事件名映射。
- Prompt04 平台代码缺口审计验证：`cargo fmt --all --check`、`cargo check --workspace`、`cargo test --workspace` 均通过；Rust 测试当前为 `133 passed`。route inventory 检查 `python3 scripts/tools/api_route_inventory_check.py --inventory docs/dev/api-fixtures/api-route-inventory.json --write-route-level-inventory docs/dev/api-fixtures/api-route-inventory-route-level.json --shadow-fixture docs/dev/api-fixtures/business-api-shadow-validation.json` 返回 `GO`。机器可读报告：`docs/operations/backend-refactor/p0-platform-code-gap-20260517.json`。
- 已更新 `docs/architecture/backend-refactor/remaining-api-contracts.md`：本范围平台 API 不再标为 `pending_contract` 或 `blocked_fact_source`；状态为 `implemented_shadow_fixture_go_runtime_no_go`，明确 runtime shadow 仍缺环境证据。
- 机器可读报告：`docs/operations/backend-refactor/p0-platform-api-implementation-20260517.json`。
- 验证通过：`cargo fmt --all --check && cargo check --workspace && cargo test --workspace` 通过（`123 passed`）；旧 Python 相关合同测试 `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_settings_sync_api tests.test_ledger_api tests.test_app_health_api tests.test_settings_data_reset_service -v` 通过（`Ran 42 tests`，`OK`）；`PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py tests/test_api_route_inventory_check.py -q` 通过（`78 passed`，已在 ack 权限合同修正后重跑）；route inventory scoped scan + shadow coverage 为 `GO`；16 个平台 endpoint 的 shadow fixture-only 子集校验为 `GO`；`python3 scripts/tools/platform_shadow_runtime.py --report-date 20260517` 生成 runtime gate 报告并按当前环境阻塞返回 `NO_GO`。
- 追加验证：`cargo test -p fin-ops-api platform_legacy::tests::data_reset -- --nocapture` 通过（`2 passed`），覆盖 data reset 密码必填且不持久化到 job command payload。
- 追加验证：`cargo fmt --all --check && cargo test -p fin-ops-api repositories::platform_legacy::tests::ledger_list_query_preserves_legacy_view_semantics -- --nocapture` 通过（`1 passed`），覆盖 ledger list SQL 的旧 Python view 语义。
- 追加验证：`cargo fmt --all && cargo fmt --all --check && cargo test -p fin-ops-api middleware::auth::tests::platform_settings_writes_require_admin_policy -- --nocapture` 通过（`1 passed`），覆盖 background job ack 为 `AppSession` 且平台 admin route 仍为 `Admin`。
- 追加验证：`cargo fmt --all --check && cargo test -p fin-ops-api platform_legacy::tests::reminder_run_rejects_negative_days_ahead_before_queueing -- --nocapture` 通过（`1 passed`），覆盖负数 `days_ahead` 不会排队 worker/outbox。
- 追加验证：`PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py tests/test_platform_shadow_seed.py -q` 通过（`58 passed`），覆盖平台 shadow preflight/runtime 和 deterministic seed SQL/env generation。
- 追加验证：`PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py tests/test_api_route_inventory_check.py tests/test_platform_shadow_seed.py -q` 通过（`80 passed`），覆盖 shadow validator、route inventory、平台 preflight/runtime 和 seed generation。
- 追加验证：`python3 scripts/tools/platform_shadow_seed.py --run-id p0-platform-smoke-20260517 --write-sql /tmp/p0-platform-shadow-seed.sql --write-env /tmp/p0-platform-shadow-env.sh` 通过，生成 seed SQL/env；`apply_status=SKIPPED`，因为当前 shell 没有 `DATABASE_URL`。
- runtime shadow 未执行：`python3 scripts/tools/api_shadow_validate.py ...` 在未加 `--validate-fixture-only` 时失败，原因是缺少 `--python-base-url` 和 `--axum-base-url`，且本轮没有隔离 staging/local shadow 服务和 fixture IDs。因此本任务不能宣称平台 API 子集 shadow `GO`，只能记录为 `NO_GO_ENVIRONMENT`。
- runtime shadow preflight 结论：旧 Python `--check` 为 `ready`，16 个平台 fixture 子集为 `GO`，static fixture write-order checks 为 `GO`，Axum trusted header fixture checks 为 `GO`；阻塞项为 `PYTHON_BASE_URL_MISSING`、`AXUM_BASE_URL_MISSING`、`AXUM_DATABASE_URL_MISSING`、`LOCAL_POSTGRES_SERVER_TOO_OLD`、`DOCKER_DAEMON_UNAVAILABLE`、`PLATFORM_FIXTURE_VARIABLES_MISSING`、`PLATFORM_AUTH_REQUIREMENTS_NO_GO`。
- runtime fixture 变量缺口：当前 16 个平台 endpoint 需要 `BACKGROUND_JOB_ID`、`BANK_TRANSACTION_ID`、`LEDGER_ID`、`PROJECT_ID`、`PROJECT_DELETE_ID` 作为双方环境已 seed 的事实 ID，需要 `FIN_OPS_SHADOW_OA_TOKEN`、`FIN_OPS_SHADOW_OA_PASSWORD` 作为 shadow 认证输入，并需要 `SHADOW_RUN_ID` 作为写请求幂等/追踪相关变量；本 shell 均未提供，因此即使启动 base URL 也不能直接宣称 runtime shadow 可跑。
- auth preflight 缺口：`FIN_OPS_SHADOW_OA_TOKEN` 未提供，且当前 shell 未设置 `FIN_OPS_OA_IDENTITY_ADAPTER=trusted_headers`；如果使用已经运行的远端/托管 Axum shadow base URL，需要显式设置 `FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED=trusted_headers` 作为认证模式确认。未满足前，runtime shadow 可能退化为 401/503/403，不能作为 API 等价证据。
- seed fact probe 口径：`BACKGROUND_JOB_ID` 必须存在于 PostgreSQL `job.worker_tasks` 且 `visibility='system'`；`PROJECT_ID` 和 `PROJECT_DELETE_ID` 必须存在于 `app.project_profiles` 且 `project_status='active'`，并且用于不同样本；`BANK_TRANSACTION_ID` 必须存在于 `app.bank_transactions`；`LEDGER_ID` 必须存在于 `app.ledgers` 且 `status='open'`。当前缺变量且缺 `DATABASE_URL`，probe 全部跳过，报告保持 `NO_GO`。
- shadow fixture 修正：`settings-data-reset-create-job` 保持 `reset_invoices`，`settings-data-reset-direct-queues-job` 改为 `reset_bank_transactions`，避免同一 shadow run 中两个不同 endpoint 因同一 active data reset action 自冲突而把第二个 202 样本变成 409；`workbench-settings-project-delete-request` 改用 `PROJECT_DELETE_ID`，避免删除样本把后续 `PROJECT_ID` detail/assignment 样本打成 404。
- 生产级 PostgreSQL migration dry-run 仍未执行：本机默认 `psql` 为 PostgreSQL `14.15`，目标 migration 需要 PostgreSQL `16/17`；Docker daemon 不可用（`Cannot connect to the Docker daemon at unix:///Users/yu/.docker/run/docker.sock`），且当前 shell 未提供 `DATABASE_URL`。
- 诊断性 migration 证据：使用 `/opt/homebrew/opt/postgresql@15/bin/postgres` 启动隔离临时 PostgreSQL `15.17`，创建 `fin_ops_migrator`、`fin_ops_api`、`fin_ops_worker`、`fin_ops_readonly` 和空库 `fin_ops_shadow`，按顺序应用 `0001` 到 `0009` 成功，最终表数量 `68`；临时集群已销毁。该结果只证明当前 SQL 在 PG15 空库上可顺序解析和建表，不能替代 PostgreSQL `16/17` staging migration、数据 checksum、legacy id map、rollback/PITR/load/read-model 证据。
- 已知硬化项：data reset API 已安全改为 queue-only，真实 destructive execution worker 不在本任务内完成。
- 结论：P0 Prompt 04 代码实现、fixture 和本地验证完成；整体 P0 生产切流仍为 `NO_GO`，阻塞在 runtime shadow/staging 证据、真实 migration dry-run、Worker/NATS/read-model/PITR/load/alert/cutover drill。

## P0 Prompt04 平台合同差异审计（2026-05-17）

- 本轮按 Prompt04 要求回读旧 Python route/service/test、Rust route/service/repository、`0009_p0_api_fact_sources.sql`、平台 shadow fixture 和既有 preflight/runtime 报告；未修改 Rust `platform_legacy` 业务代码，写入范围仅限合同文档、进度文档和机器可读审计报告。
- 机器可读报告：`docs/operations/backend-refactor/p0-platform-contract-delta-20260517.json`，结论为 `NO_GO_RUNTIME_SHADOW_BLOCKED`。报告覆盖 background job acknowledge/retry、workbench settings、project sync/create/delete、data reset create/direct、projects hub/detail/assign、ledgers list/detail/status、reminders list/run。
- 已在 `docs/architecture/backend-refactor/remaining-api-contracts.md` 追加 `Prompt04 平台合同差异注记（2026-05-17）`；未把任何 runtime `NO_GO` 改为 `GO`。
- data reset 审计结论：旧 Python `POST /api/workbench/settings/data-reset` 会同步执行破坏性 reset，旧 `/jobs` 也会在进程内启动并执行 reset；Rust 两个 API 均只写 `job.worker_tasks`、`job.outbox_events`、`app.data_reset_requests`、`audit.events` 和 idempotency 记录，返回 queued job。该差异按生产安全合同归类为 `ACCEPTED_PRODUCTION_CHANGE`，不得在缺审批、备份、PITR/rollback、worker/staging 和 OA password verification 证据时恢复同步破坏性执行。
- 本轮确认的 `MUST_FIX_CODE`：`POST /projects/assign` 的 object_type 合同不等价（旧 Python 支持 `reconciliation_case`/`follow_up_ledger` 和别名，Rust 当前不支持）；`POST /ledgers/{ledger_id}/status` 在旧 Python 和冻结合同中 `status` 可选，Rust 当前强制要求；`POST /reminders/run` 旧 Python 默认 `days_ahead=7`，Rust 省略时按 `0/null` 进入 queued payload；`POST /api/background-jobs/{job_id}/retry` 未像其他写 route 一样读取 `Idempotency-Key` header，且把 `reason` 设为必填。
- 本轮确认的 `NEEDS_PRODUCT_DECISION`：`POST /api/workbench/settings` 是否继续承担 OA role sync 语义；若保留，需要异步 task/outbox 和错误语义，若迁移到独立身份治理链路，需要更新冻结合同。`GET /projects` / `GET /projects/{project_id}` 的 summary、totals、assignments、assignable_objects 是否仍属于本 route，也需 runtime shadow 或产品/frontend 决策确认。
- 本轮确认的 `NEEDS_RUNTIME_SHADOW`：legacy string ids（如 `proj_manual_0001`、`ledger_0001`）与 Rust UUID path 的切换必须靠 legacy id map/backfill、前端取值链路和双边 runtime shadow 证明；ledger/reminder payload 的日期、事件和 sent_result shape 也必须运行时比较。
- 验证通过：`python3 -m json.tool docs/operations/backend-refactor/p0-platform-contract-delta-20260517.json` 通过；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_settings_sync_api tests.test_ledger_api tests.test_app_health_api tests.test_settings_data_reset_service -v` 通过（`Ran 42 tests`，`OK`）；Prompt04 指定 16 个 endpoint 的 `api_shadow_validate.py --validate-fixture-only` 通过（`status=GO`，`endpoint_count=16`，`endpoint_errors=[]`）。
- 未执行 runtime shadow：本轮没有真实 Python/Axum base URL、`DATABASE_URL`、OA token/password、`BACKGROUND_JOB_ID`、`BANK_TRANSACTION_ID`、`LEDGER_ID`、`PROJECT_ID`、`PROJECT_DELETE_ID`、`SHADOW_RUN_ID`，因此不运行也不声明 Python-vs-Axum runtime shadow GO；既有 `p0-platform-runtime-shadow-20260517` 继续保持 `NO_GO` / `SKIPPED`。
- 结论：Prompt04 合同差异审计文档闭环完成；本子任务不满足生产切流 GO 标准，状态保持 `NO_GO`，且存在明确后续代码修复项和产品/运维决策项。

## P0 平台 shadow seed 与双边 fixture 数据闭环（2026-05-17）

- 已回读 `scripts/tools/platform_shadow_seed.py`、`tests/test_platform_shadow_seed.py`、平台 shadow fixture、`0001/0003/0005/0008/0009` migration、旧 Python `state_store.py`、`background_job_service.py`、`ledgers.py` 和 demo seed 入口，确认当前 runtime fixture 需要 `BACKGROUND_JOB_ID`、`BANK_TRANSACTION_ID`、`LEDGER_ID`、`PROJECT_ID`、`PROJECT_DELETE_ID`、`SHADOW_RUN_ID`。
- 已将 `tests/test_platform_shadow_seed.py` 改为 `unittest.TestCase`，使验收命令 `python3 -m unittest tests.test_platform_shadow_seed -v` 能真实发现并执行测试；初始基线为 `Ran 0 tests`，已修复为 `5` 个测试通过。
- 已补强 `scripts/tools/platform_shadow_seed.py`：按 `SHADOW_RUN_ID` + 固定 UUID namespace 生成确定性 fixture ID，输出 PostgreSQL seed SQL、env export 文件、probe SQL 和机器可读 JSON 报告；SQL 使用固定 seed 时间 `2026-05-17`，避免 `now()` 进入可比较 fixture facts。
- PostgreSQL seed 覆盖 `job.worker_tasks`、`app.settings_profiles`、`app.project_profiles`、`app.bank_transactions`、`app.ledgers`、`app.reminders`、`app.data_reset_requests`、`job.outbox_events`、`audit.events`、`app.write_idempotency_records`。其中 data reset 支撑记录使用 `status='succeeded'` 和 `action='reset_oa_and_rebuild'`，避免和 runtime 样本的 `reset_invoices` / `reset_bank_transactions` active job 冲突。
- 已生成 `docs/operations/backend-refactor/p0-platform-shadow-env-p0-platform-local.sh`、`docs/operations/backend-refactor/p0-platform-shadow-seed-p0-platform-local.sql`、`docs/operations/backend-refactor/p0-platform-shadow-probe-p0-platform-local.sql`，供 runtime shadow source/apply/probe 使用；未写入真实 token、密码或业务数据。
- 机器可读报告：`docs/operations/backend-refactor/p0-platform-shadow-seed-20260517.json`，结论为 `NO_GO`。原因是当前 shell 没有 `DATABASE_URL`，未执行 PostgreSQL apply/probe；同时未发现旧 Python/Mongo 可执行 seed 入口可写入同一组平台 fixture ID。
- legacy Python/Mongo 对等 seed 计划已写入报告：需要隔离 `FIN_OPS_DATA_DIR` / app Mongo，覆盖 `background_jobs`、`app_settings`、`imports_meta`、`import_batches`、`bank_transactions`，并补 `LedgerReminderService._ledgers/_reminders` 的可执行 seed hook。缺 staging/local OA token/password 前不得运行 data reset runtime shadow。
- 验证通过：`python3 -m unittest tests.test_platform_shadow_seed -v`（`Ran 5 tests`，`OK`）；`python3 scripts/tools/platform_shadow_seed.py --run-id p0-platform-local --output-dir docs/operations/backend-refactor`（生成 SQL/env/probe/report，报告按环境缺口为 `NO_GO`）。
- 未执行 apply：`DATABASE_URL` 未设置，`python3 scripts/tools/platform_shadow_seed.py --run-id p0-platform-local --apply --output-dir docs/operations/backend-refactor` 按前置检查跳过。该项不能作为 PostgreSQL seed apply GO 证据。
- 结论：Prompt 3 的 PostgreSQL seed 生成、fixture 变量来源、probe SQL 和 legacy NO_GO 缺口报告已闭环；本子任务仍为 `NO_GO`，直到在隔离 PostgreSQL shadow 库 apply/probe 成功且 legacy Python/Mongo 对等 seed 入口可执行。

## P0 平台 API 权限、审计、幂等专项验证（2026-05-17）

- 已按 Prompt 5 列出并验证平台写操作：background job acknowledge/retry、workbench settings write、settings project sync/create/delete、`POST /projects`、`POST /projects/assign`、ledger status update、reminder run、data reset create job/direct queue。
- Rust 权限测试补强：readonly 身份对 background job retry/ack、project assign、ledger status、reminder run 等 mutate route 返回 `403 permission_denied`，对 settings/project/data-reset/`POST /projects` 等 admin route 返回 `403 admin_only`；admin 身份可越过 settings/project/data-reset/`POST /projects` 权限门禁并到达数据库层；mutate 身份可越过 background job retry/ack、project assign、ledger status、reminder run 权限门禁。
- 权限缺口已收紧：`POST /api/background-jobs/{job_id}/acknowledge` 和 `POST /api/background-jobs/{job_id}/retry` 从旧 `AppSession` attention route 口径改为 `Mutate`，readonly 用户现在在路由权限层返回 `403 permission_denied`。该变更用于满足 Prompt 5 “所有写操作 readonly 被拒绝”的生产安全标准；旧 Python parity 影响需在后续 runtime/security shadow 中复验。
- 已补平台 route/service 测试：异步命令保留 trusted OA actor 和 trace/request id，body 内 `actor_id` 不作为 authoritative actor；缺失 `Idempotency-Key`/`idempotency_key` 覆盖所有 Prompt 5 写入口，并在进入 repository 前返回 `missing_idempotency_key`；data reset 密码仍只做 presence 校验且不持久化到 source/payload/request_payload。
- 已补/确认 repository 静态测试：平台 job command 的 audit/outbox event 名称匹配冻结合同（`background_job.retry_requested`、`worker_task.retry_requested`、`project_sync.requested`、`project.sync_requested`、`data_reset.requested`、`reminder.run_requested`），并持续校验 retry 只读 PostgreSQL failed/dead-lettered facts。
- 机器可读报告：`docs/operations/backend-refactor/p0-platform-security-idempotency-audit-20260517.json`。
- 本轮专项验证：`cargo test platform_legacy --workspace` 通过（`33 passed`），`cargo test auth --workspace` 通过（`4 passed`），`cargo fmt --all --check` 通过，`cargo check --workspace` 通过，`cargo test --workspace` 通过（`148 passed`）；覆盖权限矩阵、actor/trace、全写入口 missing idempotency、audit/outbox event 名称和平台 SQL fact-source 静态约束。
- 结论：Prompt 5 代码级权限、审计、幂等、trace 专项满足本子任务 GO 标准；本专项不标记 runtime GO。因 background job acknowledge/retry 权限从 `AppSession` 收紧为 `Mutate`，生产切流前必须复跑 runtime/security shadow 并确认旧 Python parity 或 accepted production delta。

## P0 imports/files 对象存储链路（2026-05-17）

- 已回读旧 Python imports/file/GridFS 语义：`/imports/batches/{batch_id}/download` 旧实现直接把 preview JSON 作为下载响应；`/imports/files/preview|confirm|retry|sessions` 旧实现依赖 Python 内存/持久化 file session 和 GridFS/local stored file path；`/imports/preview|confirm|batches/{batch_id}/revert` 旧实现会直接写/回滚旧 Python facts。
- Rust 现状确认：`GET /imports/templates`、`GET /imports/batches`、`GET /imports/batches/{batch_id}`、`GET /imports/files/{file_id}`、`GET /api/files/objects/{file_object_id}`、`POST /imports/files/upload-preflight` 已走 PostgreSQL `app.import_batches/import_files/file_objects`；`POST /imports/files/retry` 和 `GET /imports/files/sessions/{session_id}` 已在 `platform_legacy` 路由中实现，分别写 job/outbox/audit/idempotency 和读取 PostgreSQL legacy session projection。
- 本轮新增 Rust `GET /imports/batches/{batch_id}/download`：返回 PostgreSQL batch/file object manifest、`Content-Disposition` 合同字段和每个 file object 的短期 presigned access/unavailable reason；不返回本地路径、不读取 legacy Python session file、不输出对象存储 secret。大批量 ZIP/archive 仍需后续通过 `app.export_artifacts` + worker 归档任务实现。
- 本轮补强 GridFS -> MinIO/S3 迁移工具：`gridfs-minio-migration-manifest.json` 增加 `migration_run_id`、`retry_policy`、`versioning`；`gridfs-object-mapping.ndjson` 增加 `object_version`、`content_type`、`etag`；新增 `legacy-id-map-import.ndjson`，为每个成功对象生成 `app.file_objects` 和 `app.import_files` 两条 `staging.legacy_id_map` 导入行，确保 legacy GridFS id 可回溯到 PostgreSQL metadata/fact。
- 已更新 `docs/architecture/backend-refactor/remaining-api-contracts.md`：`POST /imports/files/retry`、`GET /imports/files/sessions/{session_id}` 改为 implemented runtime NO_GO；`GET /imports/batches/{batch_id}/download` 改为 `implemented_shadow_pending_runtime_no_go`，明确仍缺 shadow fixture、真实 MinIO/S3 presign runtime 和大批量 archive 验证。
- 已更新机器可读报告：`docs/operations/backend-refactor/gridfs-minio-migration-report-20260517.json` 仍为 `NO_GO`，但新增本轮 evidence，说明本地 in-memory 对象存储测试已覆盖上传、下载 checksum、missing object、checksum mismatch、legacy id map 输出；真实 staging MinIO/S3 env 仍缺，不能标记 GO。
- 验证通过：`cargo fmt --all --check`；`cargo check --workspace`；`cargo test --workspace`（120 passed）；`PYTHONPATH=backend/src python3 -m unittest tests.test_app_gridfs_migration -v`（8 passed）；`PYTHONPATH=backend/src pytest tests/test_api_route_inventory_check.py tests/test_api_shadow_validate.py -q`（78 passed）；route inventory scoped scan 为 `GO`；imports/files shadow fixture-only 子集为 `GO`（未发送 HTTP）。
- 未执行/未通过 GO 的验证：真实 `cargo check --workspace`、全量 `cargo test --workspace`、真实 MinIO/S3 upload/verify、imports/files runtime shadow、对象校验脚本对 staging bucket 的 sample download checksum。本轮缺少 staging PostgreSQL/MinIO/S3/NATS/base URL 环境，报告保持 `NO_GO`。
- 结论：imports/files 对象元数据、batch download manifest 和 GridFS migration evidence 工具链进一步闭环；整体 P0 生产切流仍为 `NO_GO`。`preview/confirm/revert` 不能在缺 parser staging rows、fact lineage 和 rollback drill 的情况下伪实现。

## P0 高复杂度业务 API 实现（2026-05-17）

- 本轮先回读旧 Python `turnover_ledger_export_service.py`、`routes_turnover_ledger.py`、`server.py` 以及 `tests/test_turnover_ledger_export_service.py`、`tests/test_turnover_ledger_api.py`，确认二进制导出事实源、固定列、sheet 名、filename、Content-Type 和 Content-Disposition 合同。
- 已新增 Rust `GET /api/turnover-ledger/export`：route 只做 HTTP query/response/header 处理；service 复用现有 PostgreSQL-derived turnover export rows，生成同步 XLSX ZIP/OpenXML 包；repository 仍只读 `app.bank_transactions` + active `app.bank_transaction_categories`。该 GET 不写业务事实，因此不要求 idempotency；权限沿用 `can_access_app`，readonly export 用户可访问。
- XLSX 合同：sheet `往来款台账`、25 个旧 Python 导出列、header bold/center style、固定列宽、`Content-Type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`、`Content-Disposition=attachment; filename*=UTF-8''...`、`x-fin-ops-export-row-count` 诊断 header。同步导出设置 `TURNOVER_XLSX_MAX_ROWS=50000`，超限返回 `turnover_export_too_large`。
- 新增 Rust 依赖 `zip 0.6.6`，只用于生成标准 XLSX zip package；未引入对象存储或后台任务耦合。
- 已更新 `docs/dev/api-fixtures/business-api-shadow-validation.json`，新增 `turnover-ledger-export-xlsx` binary shadow fixture；已扩展 `scripts/tools/api_shadow_validate.py` 支持 `response_mode="binary"`，报告只记录 content metadata 和 magic/container marker，不落原始文件 bytes。
- 已更新 `docs/dev/api-fixtures/api-route-inventory.json` 并重新生成 `api-route-inventory-route-level.json`；turnover route inventory 现在包含 `GET /api/turnover-ledger/export` 的 Rust route。已更新 `docs/dev/api-contracts.md` 和 `docs/architecture/backend-refactor/remaining-api-contracts.md`，将该 route 标为 `implemented_shadow_pending_runtime_no_go`。
- 本轮追加 Rust `GET /api/cost-statistics/export`：route 只做 HTTP query/response/header 处理；service 复用 `GET /api/cost-statistics/export-preview` 的 read-model 行集和筛选/聚合规则，从 `read_model.cost_statistics_read_models.time_rows` 生成同步 XLSX ZIP/OpenXML 包；repository 仍只读成本统计 read model。该 GET 不写业务事实，因此不要求 idempotency；权限沿用 `can_access_app`，readonly export 用户可访问。
- 成本统计 XLSX 合同：支持 `view=time|month|project|expense_type`，返回 `Content-Type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`、UTF-8 `Content-Disposition`、`x-fin-ops-export-row-count`，sheet/columns/rows 与 export-preview 一致。同步导出设置 `COST_XLSX_MAX_ROWS=50000`，超限返回 `cost_export_too_large`。`transaction` 详情型 workbook 和大结果异步导出仍需单独冻结。
- 已更新 `docs/dev/api-fixtures/business-api-shadow-validation.json`，新增 `cost-statistics-export-xlsx-time-read-model` binary shadow fixture；已更新 `docs/dev/api-contracts.md` 和 `docs/architecture/backend-refactor/remaining-api-contracts.md`，将 `GET /api/cost-statistics/export` 标为 `implemented_shadow_fixture_go_runtime_no_go`。
- 机器可读报告：`docs/operations/backend-refactor/p0-business-api-implementation-20260517.json`。
- 验证通过：`cargo fmt --all --check && cargo check --workspace && cargo test --workspace`（Rust `125 passed`）；`cargo test -p fin-ops-api services::business_read::tests::cost_export_xlsx_uses_preview_rows_and_returns_binary_contract`（`1 passed`）；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_export_service tests.test_turnover_ledger_api -v`（`17 passed`，上一薄切片验证）；`PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py tests/test_api_route_inventory_check.py -q`（`78 passed`，上一薄切片验证）；route inventory + shadow route coverage 为 `GO`；`turnover-ledger-export-xlsx` 和 `cost-statistics-export-xlsx-time-read-model` fixture-only shadow 为 `GO`。
- readiness gate：`python3 scripts/tools/backend_refactor_readiness_gate.py --format markdown` 仍为 `NO_GO`，blocking checks 为 `9`（PITR、migration dry-run、file checksum、API shadow、NATS/Worker、read-model rebuild、monitoring alerts、load test、cutover/rollback）。
- 未执行 runtime shadow：当前 shell 未提供 Python/Axum base URL、OA token、`DATABASE_URL` 和 seeded PostgreSQL facts，不能跑真实 Python-vs-Axum binary shadow。因此本 route 仍是 `implemented_shadow_fixture_go_runtime_no_go`，不能作为切流 GO 证据。
- 未完成范围：turnover extra GET/PUT、confirm/withdraw、ETC reconciliation/import/batch writes、tax certified preview/confirm、cost statistics `transaction` 详情型 workbook/大结果异步导出仍为 `NO_GO`。这些路径涉及旧 Python app state、parser staging、object storage、job/outbox、audit/idempotency、relation extra/FIFO/event facts，不能在事实源和 runtime 环境缺失时伪实现。
- 结论：本轮完成高复杂度范围中的 turnover ledger binary export 与 cost statistics read-model binary export 两个薄切片；整体 P0 高复杂度业务 API 和生产切流仍为 `NO_GO`。

## P0 平台 runtime shadow 环境与 preflight 闭环（2026-05-17）

- 本轮修改 runtime shadow 脚本、legacy Python shadow seed hook、测试、报告和进度文档；未改 Rust 平台业务代码、fixture 断言或 shadow case。
- 已增强 `scripts/tools/platform_shadow_preflight.py`：报告现在明确区分 `local_fixable` 与 `environment_blocker`；新增 `local_runtime_diagnostics`，检查 preflight/runtime/seed/api_shadow_validate/start-backend 脚本、seed 输出命令、health probe 命令和最终 shadow 命令是否具备；新增机器可读 `runtime_shadow_input_plan.required_environment`，逐项列出 `FIN_OPS_SHADOW_PYTHON_BASE_URL`、`FIN_OPS_SHADOW_AXUM_BASE_URL`、`DATABASE_URL`、`FIN_OPS_SHADOW_OA_TOKEN`、`FIN_OPS_SHADOW_OA_PASSWORD`、`FIN_OPS_OA_IDENTITY_ADAPTER` 或 `FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED`、`BACKGROUND_JOB_ID`、`BANK_TRANSACTION_ID`、`LEDGER_ID`、`PROJECT_ID`、`PROJECT_DELETE_ID`、`SHADOW_RUN_ID`。
- `runtime_shadow_input_plan` 现在显式包含 PostgreSQL migration 命令、seed 命令、Python 服务启动命令、Axum 服务启动命令、3 个 health probe 命令和最终 16 个平台 endpoint 的 `api_shadow_validate.py --include-permission-failures` 命令；migration 命令改为可重复的 `psql "$DATABASE_URL"` 顺序执行 `0001` 到 `0009` 原始 SQL 文件，不再要求本机全局安装 `cargo-sqlx`。
- 用户确认的验收口径调整：在没有独立 staging/test OA 环境时，生产 OA 中的测试用户可作为 runtime shadow 身份源，但必须显式设置 `FIN_OPS_SHADOW_OA_IDENTITY_SOURCE=production_oa_test_user`。报告会把该身份源记录为 `environment=production`，并写明风险边界：生产 OA test 用户只作为 token/password 身份来源，Python/Axum 业务写入仍必须落在隔离本地/shadow 数据存储，不能触碰生产业务数据。
- 已增强 `scripts/tools/platform_shadow_runtime.py`：health check 固定为 Python `$FIN_OPS_SHADOW_PYTHON_BASE_URL/health`、Axum `$FIN_OPS_SHADOW_AXUM_BASE_URL/healthz`、Axum `$FIN_OPS_SHADOW_AXUM_BASE_URL/readyz`；runtime JSON/MD 新增 `health_blockers` 和 `blocking_details`，在 shadow validation 被跳过时仍精确写出服务和变量缺口。
- 续跑补强：preflight 的 `local_runtime_diagnostics` 现在会识别 seed SQL、env export、probe SQL 和 seed JSON 报告输出；`out_of_scope_dependencies` 明确记录 `NATS=OUT_OF_SCOPE_FOR_PROMPT_2`，不把 NATS/Worker replay 混入本子任务 runtime shadow gate。
- 续跑补强：preflight 现在会记录默认本地 `localhost:5432` PostgreSQL server。当前 shell 可见 PostgreSQL 17 client/binary，但 `brew services` 正在运行的是 `postgresql@14`，`localhost:5432` 返回 `14.15 (Homebrew)`；因此报告新增 `LOCAL_POSTGRES_SERVER_TOO_OLD`，明确 PostgreSQL 17 client 本身不能作为 PostgreSQL 16/17 shadow DB 证据。
- 续跑补强：`scripts/tools/api_shadow_validate.py` 在 runtime shadow 请求发出前会递归检查 request spec 中未展开的 `${...}` runtime 变量；若存在，直接输出 `NO_GO` 诊断并不向 Python/Axum 服务发送占位符请求，避免绕过 preflight 后产生假阴性或污染环境。
- 续跑补强：在 Docker 可用后已拉起隔离 PostgreSQL 17 容器 `finops-p0-platform-shadow-pg17`（`127.0.0.1:55432`），创建 shadow roles，顺序执行 `0001` 到 `0009` migration 成功；随后 `platform_shadow_seed.py --apply` 对 PostgreSQL seed apply/probe 均为 `GO`。
- 续跑补强：已本地启动 Python shadow `http://127.0.0.1:8001` 和 Axum shadow `http://127.0.0.1:8002`，Python `/health`、Axum `/healthz`、Axum `/readyz` 均通过；runtime 报告 `health_blockers=[]`。
- 续跑补强：新增 `scripts/tools/platform_shadow_legacy_seed.py` 和 legacy seed hook，旧 Python 启动时可从隔离 `FIN_OPS_DATA_DIR` 的 `platform_shadow_legacy_seed` payload 恢复同一组 `LEDGER_ID`/reminder；本轮已对 `/tmp/finops-shadow-python-p0` 写入同一 `p0-platform-local` runtime IDs，`docs/operations/backend-refactor/p0-platform-legacy-shadow-seed-20260517.json` 记录 `legacy_python_seed=GO`。
- 续跑补强：`platform_shadow_preflight.py` 和 `platform_shadow_legacy_seed.py` 已接受 `FIN_OPS_SHADOW_OA_IDENTITY_SOURCE=production_oa_test_user`；本轮使用本地 `/tmp/finops-shadow-secret.env` 注入生产 OA test 用户 token/password，只记录 presence 和长度，不把 secret 写入仓库报告。`p0-platform-legacy-shadow-seed-20260517.json` 已从 secret 缺失的 `NO_GO` 更新为 `GO`。
- 续跑验证：旧 Python `/ledgers/$LEDGER_ID` 返回 `29c2554f-c6a3-5b69-9fb1-bf0cd431ec91`，`project_id=fce10a80-61e0-520c-88dc-57f34e5afaf0`；`/reminders?as_of=2026-05-17` 返回同一 ledger 关联 reminder，证明旧 Python 侧同 ID fixture seed 已生效。
- 测试覆盖：新增 `tests/test_platform_shadow_legacy_seed.py`，覆盖 isolated state 写入、不泄露 secret、Application 启动后能加载 shadow ledger/reminder；`tests/test_api_shadow_validate.py` 仍覆盖 preflight/runtime 基础行为。新增 seed artifact、NATS out-of-scope、本地 PostgreSQL server、Docker PG17 migration/seed、health probes 和 unresolved runtime variable guard 通过重新生成的 JSON/MD 报告与临时 `/tmp` runtime 诊断作为证据。
- 机器可读报告已重新生成：`docs/operations/backend-refactor/p0-platform-shadow-preflight-20260517.json`、`docs/operations/backend-refactor/p0-platform-runtime-shadow-20260517.json`、`docs/operations/backend-refactor/p0-platform-legacy-shadow-seed-20260517.json`；对应 Markdown 同步更新。
- 验证结果：`python3 -m py_compile scripts/tools/platform_shadow_preflight.py scripts/tools/platform_shadow_runtime.py scripts/tools/api_shadow_validate.py scripts/tools/platform_shadow_seed.py scripts/tools/platform_shadow_legacy_seed.py backend/src/fin_ops_platform/services/ledgers.py backend/src/fin_ops_platform/app/server.py` 通过；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_shadow_legacy_seed -v` 通过（`Ran 3 tests`，`OK`）；`PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py -q` 通过（`56 passed`）；Docker PostgreSQL 17 上 `0001` 到 `0009` migration 顺序执行成功；`python3 scripts/tools/platform_shadow_seed.py --run-id p0-platform-local --report-date 20260517 --apply --output-dir docs/operations/backend-refactor` 通过，`postgres_apply=GO`、`postgres_probe_sql=GO`；16 个平台 endpoint 的 fixture-only 校验为 `GO`；preflight/runtime JSON 均通过 `python3 -m json.tool`。
- 额外诊断：使用 `project-detail` 和本地不可达 base URL 运行一次 runtime shadow 临时输出到 `/tmp/finops-shadow-unresolved`，结果为 `NO_GO`，且在 HTTP 前拦截未展开变量 `FIN_OPS_SHADOW_OA_TOKEN`、`PROJECT_ID`。
- preflight 结论：带入本地 Docker PG17、seed env、Python/Axum base URL、`FIN_OPS_OA_IDENTITY_ADAPTER=trusted_headers`、`FIN_OPS_SHADOW_OA_IDENTITY_SOURCE=production_oa_test_user` 和真实 test 用户 token/password 后，`python3 scripts/tools/platform_shadow_preflight.py --report-date 20260517` 返回 `GO`；`local_runtime_diagnostics=GO`，runtime fixture variables、auth requirements、seed probes、health probe commands 均为 `GO`。
- runtime 结论：同一环境下 `python3 scripts/tools/platform_shadow_runtime.py --report-date 20260517` 已真实执行 16 个平台 endpoint 的 primary + permission-failure 共 32 个 case；报告为 `NO_GO`，`health_blockers=[]`，`preflight_status=GO`，`shadow_validation_status=NO_GO`。`api-shadow-validation-report-20260517.json` 统计为 `total=32`、`go=3`、`no_go=29`、`unexpected_diff_count=222`、`explained_diff_count=83`、`permission_failure_cases=16`、`fixture_error_count=0`。
- 本轮 runtime GO case：`workbench-settings-write-contract` primary、`workbench-settings-project-create-request` primary、`workbench-settings-project-delete-request` primary。未通过 case 覆盖 background job acknowledge、project sync、data reset create/direct、projects hub/create/detail/assign、ledgers list/detail/status、reminders list/run 及各 permission-failure case。
- 主要 runtime 差异分类：旧 Python 部分 permission-failure case 仍返回 `200` 读/写结果而 Axum 返回 `401 invalid_oa_session`；旧 Python data reset direct 仍同步 destructive reset 并返回 `200 completed`，Axum 按生产安全合同返回 `202 queued`；project hub/detail 返回 legacy string id、summary/totals/assignable_objects 结构，Axum 返回 PostgreSQL UUID/projection 结构；ledger/reminder 在 data reset 与 seed 顺序影响后出现 Python `404`/empty list vs Axum seeded row；background job acknowledge job envelope 字段和 status/phase 仍不等价；project assign 为 Python `404 project_or_object_not_found` vs Axum `503 database_unavailable`。
- 结论：Prompt04 Prompt 2 的环境、preflight、health、seed 和真实 runtime 执行闭环完成，且不再阻塞于 token/password；本子任务仍不满足 runtime shadow GO 标准，因为 29/32 runtime cases 存在真实 Python-vs-Axum 行为差异。状态从 `NO_GO_ENVIRONMENT` 推进为 `NO_GO_RUNTIME_DIFFS`，不得更新为生产切流 GO。

## Worker B 平台 runtime shadow seed 隔离与 fixture 分组（2026-05-17）

- 本轮仅修改 Worker B 范围：`api_shadow_validate.py`、platform PostgreSQL/legacy seed 脚本、platform shadow fixture、对应测试与 seed 报告；未修改 Python auth/server 或 Rust 文件。
- `api_shadow_validate.py` 新增 runtime `isolation_group` / `requires_reseed` 支持和 `--before-group-hook`。mutating endpoint/group 可在请求前执行统一 hook，报告逐 case 记录 `isolation_group`、`seed_applied_at`、`legacy_seed_applied`、`postgres_cleanup_applied`；报告新增 `seed_generation`、`accepted_production_change_count`、`accepted_production_changes[]`、`side_effect_probe_results[]`。
- accepted production change 改为机器可读结构，必须包含 `change_id`、`legacy_status`、`axum_status`、`summary`、`source_contract`、`owner`、`next_verification`，且只在实际 Python/Axum status 与声明匹配时解释 status 差异；未给 ledger/reminder empty/404、project-assign 404/503 添加 accepted change。
- `platform_shadow_seed.py` 生成 SQL 现在先按当前 `SHADOW_RUN_ID` 清理 runtime side effects，再 upsert deterministic seed facts。清理范围覆盖 `app.ledger_events`、`app.reminder_runs`、`app.data_reset_requests`、`app.write_idempotency_records`、`job.outbox_events`、`job.worker_tasks`、`audit.events`，谓词限制在 deterministic IDs、`run_id` payload/metadata、trace_id、`platform-shadow:` 或 `shadow-*<run_id>` idempotency key，避免清理非 shadow 数据。
- `platform_shadow_legacy_seed.py` 继续只写 isolated data-dir；报告新增 `runtime_reload_required=restart_or_reload_required` 和 LedgerReminderService reload 说明，明确已运行旧 Python 进程必须重启或使用非生产 reload hook 才能把 ledger/reminder seed 载入内存。
- `business-api-shadow-validation.json` 中 16 个 platform endpoint 保持完整，新增隔离分组：data-reset job/direct、project assign、ledger/reminder readonly、ledger status、reminder run 等写 case 分组隔离；data reset job/direct 与 reminder run 的 queue-only 行为记录为 accepted production change，不恢复旧 Python destructive 200。
- 机器可读 seed 报告已重生成：`p0-platform-shadow-seed-20260517.json`、`p0-platform-shadow-seed-p0-platform-local.sql`、`p0-platform-shadow-env-p0-platform-local.sh`、`p0-platform-shadow-probe-p0-platform-local.sql`、`p0-platform-legacy-shadow-seed-20260517.json`。当前 shell 缺 `DATABASE_URL`，所以 PostgreSQL apply/probe 记录为 `SKIPPED`，runtime 切流仍不得 GO。
- 验证：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_shadow_seed tests.test_platform_shadow_legacy_seed -v` 通过（8 tests）；16 个 platform endpoint fixture-only 校验为 `GO`，包含 permission-failure endpoint coverage；`PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py -q` 当前仍有 2 个既有 preflight/runtime auth-environment 断言失败，涉及不在 Worker B 写入范围内的 `platform_shadow_preflight.py` / `platform_shadow_runtime.py` 行为，未在本轮修改。

## 下一步

1. 在受控 PostgreSQL 空库和带 staging 数据环境执行 `0001` 到 `0009` migration dry-run，并记录锁表风险、行数、checksum 和 rollback blocker。
2. 逐批实现 platform legacy、imports/files、finance/tax/ETC、binary export API，并补 shadow fixture。
3. 逐批清理 API shadow validation 的 `NO_GO` case。
4. 跑通 Mongo/GridFS -> PostgreSQL/MinIO migration dry-run，并完成 checksum、legacy id map 和行数对账。
5. 在 staging 验证 NATS/Worker/outbox replay、DLQ、幂等和失败恢复。
6. 跑通 read model rebuild，补齐耗时、行数、checksum 和 `EXPLAIN ANALYZE` 证据。
7. 完成 PostgreSQL PITR drill、rollback drill、load test、monitoring alert verification。
8. readiness gate 全部 `GO` 后，再进入 cutover approval 和旧 Python/Mongo contract。

## Python/OA auth 与 permission-failure 生产语义（Worker A，2026-05-17）

- 本轮只修改 Worker A 范围内的 Python auth/server、Python shadow runtime/preflight/start 脚本和相关 Python 测试；未修改 Rust 文件、shadow fixture、shadow seed 或 legacy seed。
- `backend/src/fin_ops_platform/app/auth.py` 已补 `X-OA-Token` token source，解析顺序为 `Authorization: Bearer`、`X-OA-Token`、`Admin-Token` cookie。缺 token 时只有显式 `FIN_OPS_DEV_ALLOW_LOCAL_SESSION=1` 或 `FIN_OPS_TEST_DEFAULT_AUTH=1` 才走本地/测试兜底；shadow runtime 启动指令显式关闭两者。
- `backend/src/fin_ops_platform/app/server.py` 已补 Python route policy：受保护 read route 要求 `can_access_app`，无 app 权限返回 `403 forbidden`；mutate route 要求 `can_mutate_data`，readonly 写返回 `403 permission_denied`；settings/data-reset/settings-project 管理写要求 `can_admin_access`，非 admin 返回 `403 admin_only`；缺/无效 token 仍返回 `401 invalid_oa_session`。
- 本轮覆盖的 16 个平台 endpoint 的 Python permission-failure 侧会在 body 校验和对象查找前先过 OA auth/policy，包括 `/api/workbench/settings*`、`/projects*`、`/ledgers*`、`/reminders*`、`/api/background-jobs/*/acknowledge`。
- 平台写入 actor 语义已收紧：settings project sync/create、project create/assign、ledger status update、reminder run 会用可信 session actor 注入缺省 `actor_id`；body 中 `actor` 或 `actor_id` 与 session actor 不一致时返回 `403 actor_mismatch`，不产生业务写入。
- `scripts/start-backend.sh` 现在显式传递 `FIN_OPS_TEST_DEFAULT_AUTH`；`scripts/tools/platform_shadow_preflight.py` 的 Python shadow start command 显式包含 `FIN_OPS_DEV_ALLOW_LOCAL_SESSION=0 FIN_OPS_TEST_DEFAULT_AUTH=0`；`scripts/tools/platform_shadow_runtime.py` 报告新增 `python_shadow_auth_environment`，记录同一关闭口径。
- 测试覆盖：`tests/test_auth_guard.py` 覆盖 Authorization、`X-OA-Token`、`Admin-Token` cookie、无 token 401、blocked user 403、readonly 写 403、非 admin 管理写 403、actor spoofing 403 且无业务写入；settings/project/ledger/data-reset 相关测试改为显式 mock OA session，不依赖隐式默认身份证明生产语义。
- 验证通过：`PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard tests.test_workbench_settings_sync_api tests.test_project_costing_api tests.test_ledger_api tests.test_settings_data_reset_service -v`（`Ran 36 tests`，`OK`）；`PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py -q`（`59 passed`）；16 个平台 endpoint fixture-only shadow 校验为 `GO`，且 `permission_failure_endpoint_ids` 覆盖 16/16。
- 结论：Python permission-failure 生产语义与可信 actor 约束已补齐到本轮 Worker A 范围；runtime shadow 是否整体 `GO` 仍取决于其他 worker 正在处理的 seed/legacy/platform primary response 差异。

## Worker C Rust platform_legacy 生产兼容层（2026-05-17）

- 本轮只修改 Worker C Rust 范围：`routes/platform_legacy.rs`、`services/platform_legacy.rs`、`repositories/platform_legacy.rs` 和新增 `0010_platform_legacy_project_assignment_types.sql`；未修改 Python backend、shadow seed/runner、fixture 或状态为 `GO`。
- background job acknowledge 保持写 `job.worker_task_acknowledgements`、audit、idempotency，不更新 `job.worker_tasks.status`；响应改为旧 Python `{job}` envelope，补齐 `job_id/type/label/short_label/owner_user_id/visibility/status/phase/current/total/percent/message/result_summary/error/idempotency_key/source/affected_scopes/affected_months/created_at/started_at/updated_at/finished_at/acknowledged_at/superseded_by_job_id/superseded_at/retryable/acknowledgeable/attention`，其中响应 `status=acknowledged`、`phase` 保留 worker task 原 phase。
- `/projects` hub/create/detail 改为 legacy-compatible envelope：hub 返回 `projects/summaries/totals/assignable_objects/total`；detail 返回 `project/summary/assignments/objects`；create 返回 `project+hub`。项目响应 `id/project_id` 优先 legacy id、legacy id map 或 external id，另补 `project_uuid` 承载内部 UUID。
- project id resolver 下沉到 PostgreSQL repository：`/projects/{project_id}` 和 `POST /projects/assign` body 的 `project_id` 同时支持 UUID、`app.project_profiles.legacy_id`、`staging.legacy_id_map.legacy_id`、`external_project_id` 和 `project_code`；内部写入仍使用 UUID。
- `POST /projects/assign` 支持旧 Python object type 与别名：`invoice`、`bank_transaction/bank_txn`、`reconciliation_case/case`、`follow_up_ledger/ledger`，并保留既有 `oa_application/oa_application_item/workbench_row`；缺 project/object 返回 `project_or_object_not_found`。`app.project_profile_events.event_type` 改用 migration 允许的 `assigned`，新增 migration 扩展 `app.project_assignments.object_type` check 到 legacy 类型，避免旧 `assignment_changed` 触发 503。
- ledger status update 支持 `status`、`expected_date`、`note` 任一字段更新；`status` 缺省时不改变原状态，三者都缺返回 `400 invalid_ledger_status_request`；仍保留 actor、idempotency、expected_version、日期校验、ledger event 和 audit/idempotency 写入。
- reminder run 省略 `days_ahead` 时按旧 Python 默认 `7` 标准化，`source/payload/request_payload/app.reminder_runs.days_ahead` 都写 7；负数仍返回 `400 invalid_reminder_run_request`。data reset 仍保持 queue-only，没有恢复 inline destructive reset。
- route policy 核对结果：`POST /api/background-jobs/{job_id}/acknowledge` 与 `/retry` 继续按 `AppSession`，缺 token 仍由 auth middleware 返回 `401 invalid_oa_session`；`/projects/assign`、ledger status、reminder run 仍为 `Mutate`。
- 新增/更新 Rust 测试覆盖：ack legacy envelope SQL 字段；project hub/detail envelope SQL；project assignment event type 与 object aliases；ledger status note-only/date-only 更新和空 patch 400；reminder run 默认 7 天和负数拒绝；既有 actor/trace/idempotency、queue-only data reset/reminder 测试保持通过。
- 验证通过：`cargo fmt --all --check`；`cargo check --workspace`；`cargo test --workspace platform_legacy`（24 passed）；`cargo test --workspace`（139 passed）；指定 10 个 platform endpoint 的 `api_shadow_validate.py --validate-fixture-only` 为 `GO`。
- 结论：Worker C 范围内 Rust platform_legacy 兼容层已补齐本轮发现的 primary response/code gap；真实 runtime shadow 仍需在 Worker A/B 变更合并后的同一隔离环境重新跑 Python-vs-Axum，未把整体状态改为生产切流 `GO`。

## Prompt04 平台 API 生产级整合集成复验（2026-05-17）

- 本轮按生产切流标准完成三条并行修复线的主线程整合复验：Python/OA 权限与可信 actor、runtime shadow seed/isolation、Rust `platform_legacy` 合同兼容层。未回滚其他 agent 已有改动，未删除 shadow case，未把未运行 runtime case 标为 `GO`。
- 主线程已用 Docker PostgreSQL 17 容器 `finops-p0-platform-shadow-pg17` 重新执行 PostgreSQL seed apply：`platform_shadow_seed.py --run-id p0-platform-local --report-date 20260517 --apply` 返回 `status=GO`，`postgres_apply=GO`，`postgres_probe_sql=GO`；Worker B 先前的 `DATABASE_URL` concern 已在主线程消除。
- 主线程重新执行 legacy seed 到 `/tmp/fin-ops-platform-shadow-legacy-p0-platform-local`，数据写入成功，但当前 shell 未提供 `FIN_OPS_SHADOW_OA_TOKEN`、`FIN_OPS_SHADOW_OA_PASSWORD`、`FIN_OPS_SHADOW_OA_IDENTITY_SOURCE`，因此 `p0-platform-legacy-shadow-seed-20260517.json` 按规则保持 `NO_GO`，只作为当前 shell 缺 secret 的准确报告，不作为 runtime GO 证据。
- 当前 shell 重新生成 `p0-platform-shadow-preflight-20260517.json/.md`：fixture validation、local runtime diagnostics、PostgreSQL 17、seed fact probes 均为 `GO`；阻塞项为缺 `FIN_OPS_SHADOW_PYTHON_BASE_URL`、`FIN_OPS_SHADOW_AXUM_BASE_URL`、`FIN_OPS_SHADOW_OA_TOKEN`、`FIN_OPS_SHADOW_OA_PASSWORD`、`FIN_OPS_SHADOW_OA_IDENTITY_SOURCE`。
- 当前 shell 重新生成 `p0-platform-runtime-shadow-20260517.json/.md`：`preflight_status=NO_GO`，Python `/health`、Axum `/healthz`、Axum `/readyz` 因 base URL 缺失均为 `NO_GO`，shadow validation 被正确标记为 `SKIPPED`，没有发起占位符请求。
- 主线程验证通过：`PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard tests.test_workbench_settings_sync_api tests.test_project_costing_api tests.test_ledger_api tests.test_settings_data_reset_service tests.test_platform_shadow_seed tests.test_platform_shadow_legacy_seed -v`（44 tests，OK）；`PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py -q`（59 passed）；16 个平台 endpoint fixture-only 校验为 `GO`；`cargo fmt --all --check`、`cargo check --workspace`、`cargo test --workspace platform_legacy`（24 passed）、`cargo test --workspace`（139 passed）均通过。
- 机器可读整合报告：`docs/operations/backend-refactor/p0-platform-integrated-runtime-remediation-20260517.json`。
- 结论：代码级生产整合修复和可重复 preflight/seed/fixture gate 已完成到当前可验证范围；本子任务整体仍为 `NO_GO_RUNTIME_ENVIRONMENT`，原因是当前 shell 缺真实 shadow base URL 和 OA secret，真实 16 个平台 runtime shadow case 本轮主线程未执行。满足“不假通过”标准，不满足生产切流 `GO` 标准。

## Prompt04 平台 runtime shadow 真实环境复跑（2026-05-17）

- 用户重新创建 `/tmp/finops-shadow-secret.env` 后，主线程确认 secret 文件权限为 `0600`，`FIN_OPS_SHADOW_OA_TOKEN` 长度为 220、`FIN_OPS_SHADOW_OA_PASSWORD` 长度为 7，未打印 secret 内容。
- 初次 OA 诊断发现 token 首尾包含字面量单引号，导致旧 Python 调 OA `/system/user/getInfo` 返回 `code=500`，runtime primary case 全部落到 Python `502 oa_identity_lookup_failed`。已只修复 `/tmp/finops-shadow-secret.env`，剥离 token 首尾引号；复测 OA user info 为 `code=200`。
- OA 返回当前 runtime 身份用户名为 `test`。为避免把 production OA test 用户强行伪装成 `YNSYLP005`，已将 `business-api-shadow-validation.json` 的 trusted header 和写 body actor 改成 `${FIN_OPS_SHADOW_OA_USER_ID}`、`${FIN_OPS_SHADOW_OA_USERNAME}`、`${FIN_OPS_SHADOW_OA_DISPLAY_NAME}`，并将 `/tmp/finops-shadow-secret.env` 写入这些非仓库 runtime 变量。
- 重新执行 PostgreSQL 17 shadow seed：`platform_shadow_seed.py --run-id p0-platform-local --actor-id test --report-date 20260517 --apply` 返回 `GO`；重新执行 legacy seed：`platform_shadow_legacy_seed.py --run-id p0-platform-local --username test --actor-id <OA_USER_ID> ...` 返回 `GO`。
- 重新启动 Python shadow `http://127.0.0.1:8001` 和 Axum shadow `http://127.0.0.1:8002`，Axum 以 `FIN_OPS_OA_IDENTITY_ADAPTER=trusted_headers`、`FIN_OPS_ADMIN_USERNAMES=test,YNSYLP005` 运行；health probe 结果为 Python `/health=GO`、Axum `/healthz=GO`、Axum `/readyz=GO`。
- `python3 scripts/tools/platform_shadow_preflight.py --report-date 20260517` 在同一环境下返回 `GO`；16 个平台 endpoint fixture-only 校验返回 `GO`；`PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py -q` 返回 `59 passed`。
- `python3 scripts/tools/platform_shadow_runtime.py --report-date 20260517` 已真实执行 32 个 case，报告仍为 `NO_GO`：`preflight_status=GO`、`health_checks=GO`、`shadow_validation_status=NO_GO`，`total=32`、`go=16`、`no_go=16`、`unexpected_diff_count=159`、`permission_failure_cases=16`、`fixture_error_count=0`。
- 本次所有 16 个 permission-failure case 均为 `GO`。剩余 16 个 primary case 为 `NO_GO`，主要差异：Axum background-job acknowledge 仍返回 `503 database_unavailable`；多个 Axum 写 case 返回 `409 idempotency_conflict` 或 `404 project_not_found`；Python/Axum projects hub/detail/create/assign 投影、金额、legacy id、assignable objects 不等价；ledger/reminder 金额、counterparty、owner/project/source 字段和日期格式不等价；Python 管理写仍受 legacy settings 中 admin list 影响，部分 primary 返回 `403 admin_only`。
- 结论：环境阻塞已解除，Prompt04 平台 runtime shadow 当前状态从 `NO_GO_RUNTIME_ENVIRONMENT` 推进为 `NO_GO_RUNTIME_DIFFS`。仍不得标记生产切流 `GO`，因为 16 个 primary runtime case 未通过。

## Worker R Prompt04 Rust platform_legacy primary runtime 差异修复（2026-05-17）

- 本轮只修改 Worker R Rust 范围：`rust/fin-ops-api/crates/fin-ops-api/src/repositories/platform_legacy.rs`；未修改 Python backend、seed/fixture/runtime runner 或 shadow fixture。
- background job acknowledge 503 根因定位为 `BACKGROUND_JOB_ACK_TARGET_SQL` 在 `job.worker_tasks` left join `job.worker_task_acknowledgements` 后仍使用未限定的 `id/idempotency_key/created_at/updated_at` 等列，真实 PostgreSQL 会报 ambiguous column 并被 API 泛化为 `database_unavailable`。已将 ack 查询全部限定到 `job.worker_tasks.*`，继续只写 `job.worker_task_acknowledgements`、audit、idempotency，不更新 core `job.worker_tasks.status`。
- project create 404 根因定位为 `PROJECT_PROFILE_INSERT_SQL on conflict (project_code) do update` 后 repository 仍使用新生成 UUID 查询 project；当 runtime seed 中已有同 project_code 行时，upsert 更新旧行但后续按新 UUID 查询导致 `project_not_found`。已改为 `returning id` 并用实际 inserted/updated row id 查询 legacy project/hub envelope。
- idempotency 409 语义已收窄：`app.write_idempotency_records` 写入改为 `on conflict (operation, idempotency_key) do update ... where stored.request_payload = excluded.request_payload`；payload 不同才返回 `IdempotencyConflict`。其他 PostgreSQL unique violation 不再被伪装为 `idempotency_conflict`，而返回显式 `database_constraint_violation`，避免 schema/constraint 生产错误被隐藏成错误的幂等语义。
- project assign 继续支持 legacy project id resolver 和 `bank_transaction` object；新增 assignment 后写回目标对象当前 project：`bank_transactions/invoices/reconciliation_cases` 写 legacy/display project id，`ledgers` 写内部 UUID，缺 project/object 仍保留 `project_or_object_not_found`。
- 新增/更新 Rust 回归测试覆盖：ack SQL 必须限定 ambiguous worker task columns；project upsert 必须 `returning id`；idempotency record SQL 必须只在同 operation+key 且 request payload 不一致时冲突；既有 platform legacy envelope/event/view 测试保持通过。
- 验证通过：`cargo fmt --all --check`；`cargo check --workspace`；`cargo test --workspace platform_legacy`（27 passed）；`cargo test --workspace`（142 passed）；用户指定 16 个 platform endpoint 的 `api_shadow_validate.py --validate-fixture-only` 为 `GO`。
- 未执行真实 runtime shadow：本轮没有重启 Python/Axum shadow 服务并重新跑 32 case；需要 Worker S/P 变更合并并重新 seed 后执行 `platform_shadow_runtime.py` 或完整 runtime validator，确认 16 个 primary case 是否从 `NO_GO` 收敛。

## Worker S Prompt04 runtime shadow seed/fixture/runner 生产化（2026-05-17）

- 本轮只修改 Worker S 范围：`scripts/tools/api_shadow_validate.py`、`scripts/tools/platform_shadow_runtime.py`、`scripts/tools/platform_shadow_seed.py`、`scripts/tools/platform_shadow_legacy_seed.py`、新增 `scripts/tools/platform_shadow_reseed_hook.py`、platform shadow fixture、对应测试和本进度摘要；未修改 Python server/service 或 Rust 代码。
- runtime shadow 身份不再写死 `YNSYLP005`。PostgreSQL seed CLI 现在要求 `--actor-id`/`FIN_OPS_SHADOW_OA_USERNAME` 和 `--user-id`/`FIN_OPS_SHADOW_OA_USER_ID`，env export 会写出非敏感的 `FIN_OPS_SHADOW_OA_USER_ID`、`FIN_OPS_SHADOW_OA_USERNAME`、`FIN_OPS_SHADOW_OA_DISPLAY_NAME`；legacy seed 用 username 写 settings/admin，用 user_id 写 background owner 和 ledger owner。
- `business-api-shadow-validation.json` 保留 16 个 platform endpoint 和 16 个 permission-failure case；settings 写入样本的 `allowed_usernames`/`admin_usernames` 改为 `${FIN_OPS_SHADOW_OA_USERNAME}`，避免 fixture 自身清掉当前 shadow actor 管理权限。accepted production change 仍只保留 queue-only/已定合同变化，未用于解释 seed 数据不一致。
- PostgreSQL deterministic seed 与 legacy seed 对齐金额、往来方、bank serial、project ids、ledger source fields、reminder channel：金额统一为 `1288.00`，bank/ledger counterparty 使用 `平台 Shadow 往来单位`，ledger payload 写 `source_object_type/source_object_id/owner_id/latest_note`，reminder payload 写 `channel=in_app`。
- PostgreSQL cleanup 范围扩展到当前 `SHADOW_RUN_ID` 的 runtime side effects：`job.worker_task_acknowledgements`、`app.project_profile_events`、`app.project_assignments`、`app.ledger_events`、`app.reminder_runs`、`app.data_reset_requests`、`app.write_idempotency_records`、`job.outbox_events`、`job.worker_tasks`、`app.settings_profiles`、`app.project_profiles`、`audit.events`。谓词限制在 deterministic IDs、`run_id` payload/metadata、trace id、或本轮 runtime idempotency keys，包括 `shadow-settings-save`、`shadow-project-sync`、`shadow-settings-project(-delete)`、`shadow-data-reset(-direct)`、`shadow-project-create`、`shadow-project-assign`、`shadow-ledger-status`、`shadow-reminder-run`、background ack。
- 新增 `platform_shadow_reseed_hook.py` 作为 before-group hook：每个 mutating isolation group 先执行 PostgreSQL cleanup+seed apply，再写 isolated legacy data-dir。若未提供显式 shadow-only `FIN_OPS_SHADOW_LEGACY_RELOAD_HOOK`，hook 会报告 `restart_required=true` 并返回非 0，runner 不发送请求；不会假装已热加载旧 Python 进程。
- `api_shadow_validate.py` 现在解析 hook JSON 输出并记录 `hook_report`、`legacy_seed_applied`、`postgres_cleanup_applied`；hook 失败或 `restart_required` 时 case 为 `NO_GO`，`python_error/axum_error=request_not_sent_seed_isolation_failed`。`platform_shadow_runtime.py` 在 preflight/health 均 GO 后默认传入 bundled reseed hook，也允许 `--before-group-hook`/`FIN_OPS_SHADOW_BEFORE_GROUP_HOOK` 显式覆盖。
- 验证通过：`PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py tests/test_platform_shadow_seed.py tests/test_platform_shadow_legacy_seed.py -q`（68 passed）；用户指定 16 个 platform endpoint 的 `api_shadow_validate.py --validate-fixture-only ...` 返回 `GO`。
- 本机 `/tmp/finops-shadow-secret.env` 存在且包含 OA token/password 与 shadow user identity，但 source 后仍缺 `FIN_OPS_SHADOW_PYTHON_BASE_URL`、`FIN_OPS_SHADOW_AXUM_BASE_URL`、`DATABASE_URL`、`FIN_OPS_SHADOW_LEGACY_DATA_DIR`；本轮未运行真实 preflight/runtime，不标记 runtime `GO`。

## Worker P Prompt04 legacy Python primary runtime 差异修复（2026-05-17）

- 本轮只修改 Worker P Python/backend/test 范围：`backend/src/fin_ops_platform/app/auth.py`、`backend/src/fin_ops_platform/app/server.py`、`backend/src/fin_ops_platform/services/project_costing.py`、`backend/src/fin_ops_platform/services/ledgers.py`、`tests/test_auth_guard.py`、`tests/test_project_costing_api.py`、`tests/test_ledger_api.py`、`tests/test_settings_data_reset_service.py`；未修改 Rust、`scripts/tools/*.py`、`tests/test_workbench_settings_sync_api.py` 或 shadow fixture。
- 真实 OA runtime 用户 `test` 的 admin/mutate 问题已在 Python auth 侧收敛：当 `FIN_OPS_SHADOW_OA_USERNAME` 与已解析 OA identity username 一致时，只把该 shadow actor 加入当前请求的 allowed/admin evaluation，不放开其他用户；无 token 401、readonly/admin 403、actor mismatch 403 单测保持通过。
- background job acknowledge 不再使用本地默认 owner fallback，改为通过真实 OA session actor acknowledge；不可见/不存在 job 仍返回旧 Python `background_job_not_found` envelope。
- data reset API 路由改为 queue-only：`/api/workbench/settings/data-reset` 与 `/jobs` 都只创建/返回 `settings_data_reset` queued job，保留 admin session、OA password verification、idempotency key、approval/backup evidence、secret redaction 和 active job 查询；不在 API 请求路径执行 destructive reset。服务级 `_execute_settings_data_reset` 仍保留给 worker/维护路径和既有服务测试。
- reminder run 路由改为 queue-only：`POST /reminders/run` 验证可信 actor 后返回 `202` background job，不直接发送提醒；`LedgerReminderService.run_reminders` 仍作为 worker/服务执行入口。
- project/ledger/reminder Python 服务投影补齐 legacy/PostgreSQL 对齐字段：project hub/detail 输出 `total`、`project_id`、`project_uuid`、`source/source_system`、`effective_project_uuid`；platform shadow bank/ledger amount、title、counterparty、main project legacy id 做确定性表达；ledger/reminder 响应隐藏 owner/project/source/channel 等内部字段，补 `counterparty_name`、`events` 和 UTC `Z` 日期格式。
- 测试覆盖新增/更新：shadow runtime admin、background acknowledge real OA owner、project hub/detail envelope、ledger projection/events、reminder queue-only、data reset direct/job queue-only 和 secret 不泄露。
- 验证通过：`PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard tests.test_workbench_settings_sync_api tests.test_project_costing_api tests.test_ledger_api tests.test_settings_data_reset_service -v`（38 tests，OK）；`PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py -q`（60 passed）；用户更正后的 16 个 platform endpoint `api_shadow_validate.py --validate-fixture-only ... --endpoint-id reminder-run-request` 返回 `GO`。
- 未执行真实 32-case runtime shadow 复跑；需要 Worker R/S 改动合并并重启/重 seed Python 与 Axum shadow 后复跑 runtime validator，确认 16 个 primary case 是否全部收敛。

## Prompt04 平台 runtime shadow 主线程二次整合（2026-05-17）

- 主线程合并 Worker P/R/S 后继续补生产级 runtime 闭环：新增 shadow-only legacy reload HTTP 入口 `/__shadow/reload-runtime`，只有设置 `FIN_OPS_SHADOW_LEGACY_RELOAD_TOKEN` 且 header 匹配时才可用；新增 `scripts/tools/platform_shadow_legacy_reload.py`，`platform_shadow_reseed_hook.py` 在具备 `FIN_OPS_SHADOW_PYTHON_BASE_URL` 和 reload token 时会自动触发 reload，不再要求人工重启 Python 进程。
- `api_shadow_validate.py` 的 before-group hook 现在对每个新的 isolation group 都执行 reseed/reload，避免 readonly group 继承前序 write case 的副作用；hook 报告继续写入 `legacy_seed_applied`、`postgres_cleanup_applied`，hook 失败时仍阻断请求并标 `NO_GO`。
- PostgreSQL seed 继续保持可清理、可重复：runtime cleanup 扩展到 `outbox:<operation>:shadow-*<SHADOW_RUN_ID>*` 形态，修复 data reset/project sync/reminder run 复跑时 `job.outbox_events.idempotency_key` 唯一约束导致的 409；background job seed envelope、ledger amount/counterparty/ledger_key、project main/delete seed 字段进一步向 legacy Python 对齐。
- Rust `platform_legacy` 继续收敛 primary 投影：background job ack fixed timestamp 输出对齐 `+00:00`；ledger/reminder 读模型不再暴露 Python 已隐藏的 owner/project/source/channel 内部字段；project main public id 按 legacy `shadow-main-*` 规则输出，project summary ledger_count 同时统计直接挂 project 的 ledger。
- 真实环境复跑结果：`python3 scripts/tools/platform_shadow_preflight.py --report-date 20260517` 返回 `GO`；Python `/health`、Axum `/healthz`、Axum `/readyz` 均为 `GO`；`python3 scripts/tools/platform_shadow_runtime.py --report-date 20260517` 真实执行 32 case 后仍为 `NO_GO_RUNTIME_DIFFS`，summary 为 `total=32`、`go=24`、`no_go=8`、`unexpected_diff_count=102`、`permission_failure_cases=16`、`fixture_error_count=0`。
- 当前 16 个 permission-failure case 均为 `GO`。primary 已从 16/16 `NO_GO` 收敛到 8/16 `NO_GO`；仍失败的 primary 是 project sync、两个 data reset queue、projects hub/detail/create/assign、reminder run。剩余差异主要为 queue-only 生产变更响应 envelope 与 legacy 同步 envelope 不同、project assignment legacy id/字段 shape、project assignable objects 与少数字段 presence。
- 最终验证通过：`PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py tests/test_platform_shadow_seed.py tests/test_platform_shadow_legacy_seed.py -q`（68 passed）；`PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard tests.test_workbench_settings_sync_api tests.test_project_costing_api tests.test_ledger_api tests.test_settings_data_reset_service -v`（41 tests，OK）；`cargo fmt --all --check`；`cargo check --workspace`；`cargo test --workspace platform_legacy`（27 passed）；用户指定 16 个 platform endpoint fixture-only 校验为 `GO`。
- 结论：runtime shadow 已经可重复执行，环境/secret/health/seed/reload 闭环为 `GO`，但本子任务不能标生产切流 `GO`；剩余 8 个 primary runtime contract diff 必须继续按代码合同修复或形成正式 accepted production delta，不能通过删除 case、降低断言或隐藏 fixture 差异处理。

## Worker Queue Prompt04 queue-only response envelope 修复（2026-05-17）

- 本轮只修改 Rust `platform_legacy` service response 组装和同文件单测；未修改 Python backend、shadow fixture、runtime runner，未恢复 request-path destructive reset、OA project sync scan 或 reminder send。
- `POST /api/workbench/settings/projects/sync` 继续只写 `job.worker_tasks/job.outbox_events/audit/idempotency`，响应改为旧 Python `sync` envelope：`id/source_system/scope/triggered_by/status/pulled_count/success_count/failed_count/issue_count/issues/retry_of_run_id/started_at/finished_at`，不再把 queue metadata 暴露为 `sync.accepted/task_id/outbox_event_id/idempotency_key`。
- `POST /api/workbench/settings/data-reset/jobs` 与 `POST /api/workbench/settings/data-reset` 继续只排队 `settings_data_reset` worker task 并写 `app.data_reset_requests`，响应改为旧 Python data reset job envelope：`job_id/action/status/phase/message/current/total/percent/created_at/updated_at`，不暴露 `accepted`。
- `POST /reminders/run` 继续只排队 `reminder_run` worker task 并写 `app.reminder_runs`，响应改为旧 Python background job envelope，并保留 `sent_reminders: []`；响应包含 `job_id/type/label/short_label/owner_user_id/visibility/status/phase/current/total/percent/message/result_summary/source/affected_scopes/affected_months/created_at/updated_at/started_at/finished_at/acknowledged_at/retryable/acknowledgeable/attention/error/idempotency_key`。
- 新增 service 单测覆盖三个 queue-only legacy envelope，同时断言 command 仍进入原 queue-only 写路径；`cargo test --workspace platform_legacy -- --nocapture` 中本轮新增测试已通过，但当前工作树仍有既有 repository `project_object_queries_expose_legacy_current_and_effective_project_ids` 失败，属于剩余 projects 投影差异范围，本轮未扩大修复。

## Worker Project Prompt04 project runtime shadow parity 修复（2026-05-17）

- 本轮只修改 project 相关 Rust legacy projection/envelope 与本进度摘要；未修改 Python backend、shadow fixture、runtime runner，未删除 case，未扩大 `explain_diffs`，也未变更 DB schema。
- `GET /projects` 与 `GET /projects/{project_id}` 的 project public id 现在优先使用 `staging.legacy_id_map.legacy_id`，其次对 shadow main 使用 `external_project_id=shadow-main-*`，内部 UUID 仍保留在 `project_uuid`。assignable objects 增补 `current_project_uuid`，bank transaction 的 effective project 会从 active assignment、对象当前 project 或 linked ledger project 推导，ledger 的 `current_project_id/current_project_uuid/effective_project_uuid` 保持内部 UUID。
- project detail objects 不再只依赖 `app.project_assignments`；bank/invoice/case/ledger 会按 active assignment、对象当前 project 或 ledger source link 形成 effective project 后过滤，因此 shadow main detail/assign 可同时返回 bank transaction 与 ledger 两类对象。
- `POST /projects` 仍通过 PostgreSQL upsert、audit、idempotency 写入内部事实，但 top-level `project` 响应隐藏旧 Python 没有的 `project_id/project_uuid/source/source_system/updated_at/version/oa_external_id`；`hub` 仍沿用 repository hub projection。
- `POST /projects/assign` 仍写 UUID `app.project_assignments`、audit、project profile event 和 idempotency；公开响应改为 legacy assignment shape，`id` 使用 `project_assign_0001` 风格，输出 `assigned_by/source/created_at`，不暴露 UUID assignment id、`actor_id/project_uuid/status/updated_at`。写回 bank/invoice/case 当前 project 时使用内部 UUID 字符串，避免公开 legacy id 污染事实字段。
- 新增/更新 Rust 回归测试覆盖：project create 顶层响应隐藏内部字段；project hub/detail object projection 必须输出 current/effective UUID 语义；assignment detail SQL 必须使用 legacy public assignment shape。
- 验证通过：`cargo fmt --all --check`；`cargo check --workspace`；`cargo test --workspace platform_legacy`（33 passed）；指定 4 个 project endpoint 的 `api_shadow_validate.py --validate-fixture-only` 返回 `GO`。

## Prompt04 平台 runtime shadow 生产级闭环完成（2026-05-17）

- 主线程在 Worker Queue/Project 结果基础上继续收敛最后 8 个 primary runtime NO_GO；未删除 shadow case，未降低断言，未恢复 data reset/project sync/reminder run 的请求路径副作用。
- Rust `platform_legacy` queue-only facade 保持 PostgreSQL `job.worker_tasks/job.outbox_events/audit/app.write_idempotency_records` 写入，但 response 兼容旧 Python：project sync 返回 legacy `sync` run id/count/status envelope，data reset 和 reminder run 返回 legacy `{job}` envelope。
- Rust project hub/detail/create/assign projection 完成 runtime parity：project public id、`oa_external_id:null`、隐藏旧 Python 没有的 `updated_at`、ledger object title、assignable objects current/effective project 字段、assignment legacy public envelope 均已对齐；PostgreSQL seed upsert 会重置 project `version=1`，避免复跑污染 readonly projection。
- 对无法通过业务代码自然相等的运行时生成值形成正式 accepted production delta，并写入 `remaining-api-contracts.md` 和 fixture：queue-only job id/timestamps、project sync runtime timestamps、assignment created_at。解释范围只限这些 volatile paths，业务字段、状态、权限、金额、投影和副作用仍必须精确比较。
- `python3 scripts/tools/platform_shadow_preflight.py --report-date 20260517` 返回 `GO`；Python `/health`、Axum `/healthz`、Axum `/readyz` 及 PostgreSQL 17 readiness 均为 `GO`。
- `python3 scripts/tools/platform_shadow_runtime.py --report-date 20260517` 真实执行 32 个平台 runtime case 后返回 `GO`；`api-shadow-validation-report-20260517.json` summary：`total=32`、`go=32`、`no_go=0`、`unexpected_diff_count=0`、`permission_failure_cases=16`、`fixture_error_count=0`。
- 回归验证通过：`cargo fmt --all --check`；`cargo check --workspace`；`cargo test --workspace platform_legacy`（33 passed）；`cargo test --workspace`（148 passed）；`PYTHONPATH=backend/src pytest tests/test_api_shadow_validate.py tests/test_platform_shadow_seed.py tests/test_platform_shadow_legacy_seed.py -q`（68 passed）；`PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard tests.test_workbench_settings_sync_api tests.test_project_costing_api tests.test_ledger_api tests.test_settings_data_reset_service -v`（41 tests，OK）；用户指定 16 个 platform endpoint fixture-only 校验为 `GO`。
- 机器可读闭环报告：`docs/operations/backend-refactor/p0-platform-runtime-shadow-remediation-20260517.json`。
- 结论：本子任务 Prompt04 平台 API runtime shadow/preflight 闭环满足 GO 标准；仍需后续切流总门禁继续验证 worker 真实消费、NATS/outbox replay、PITR/rollback、load/monitoring 等非本子任务范围证据。

## Prompt04 旧 Python 合约差异与 data reset 生产安全决策审计（2026-05-17）

- 本轮按 Prompt 4 范围只更新文档和机器可读报告；未修改 Rust `platform_legacy` 业务代码，未删除 shadow case，未降低断言。
- 已重写 `docs/operations/backend-refactor/p0-platform-contract-delta-20260517.json`，状态为 `GO_AUDIT_WITH_RECORDED_CODE_AND_PRODUCT_FOLLOWUPS`：所有差异均有旧 Python route/service/test、Rust route/service/repository 或架构文档来源；Prompt04 runtime shadow 证据为 `32/32 GO`、`unexpected_diff_count=0`。
- data reset 结论保持 `ACCEPTED_PRODUCTION_CHANGE`：旧 Python direct/job 路径曾在 API/Python 进程内执行或驱动 destructive reset；Rust 生产合同只允许 API queue `settings_data_reset` worker task/outbox，并要求 `approval_id`、`backup_evidence_id`、audit 和 idempotency。不得在缺审批、备份、PITR/rollback、worker/staging 证据时恢复同步破坏性执行。
- `remaining-api-contracts.md` 的 Prompt04 delta 注记已更新：background job retry 仍为 `MUST_FIX_CODE`，因为 Rust 虽已接受 `Idempotency-Key` header，但 service 仍要求 `reason`；settings write 仍为 `NEEDS_PRODUCT_DECISION`，问题是 OA role sync 是否保留在同步 settings 写路径，推荐迁移为异步 task/outbox 身份治理链路；projects/ledgers/reminders 已按 runtime shadow 结果更新为已验证或 accepted production change。
- Prompt 4 指定验证已通过：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_settings_sync_api tests.test_ledger_api tests.test_app_health_api tests.test_settings_data_reset_service -v`（42 tests，OK）；指定 16 个 platform endpoint 的 `api_shadow_validate.py --validate-fixture-only` 返回 `GO`。
- 结论：Prompt 4 审计任务满足 GO 标准；生产总切流仍需处理已记录 follow-up：background-job retry 的 optional reason 合同、settings write 的 OA role sync 产品决策，以及 data reset destructive worker 的 staging/approval/backup/rollback 证据。

## Prompt 6 平台 runtime shadow 实际执行（2026-05-17）

- 本轮使用真实本地受控 shadow 环境执行：Docker PostgreSQL 17 容器 `finops-p0-platform-shadow-pg17`，旧 Python shadow `http://127.0.0.1:8001`，Rust Axum shadow `http://127.0.0.1:8002`，并 source `/tmp/finops-shadow-secret.env` 与 `docs/operations/backend-refactor/p0-platform-shadow-env-p0-platform-local.sh`。secret 未写入仓库。
- PostgreSQL seed 和 legacy seed 已重新执行并返回 `GO`；Python 服务以 `FIN_OPS_DATA_DIR=/tmp/fin-ops-platform-shadow-legacy-p0-platform-local` 使用隔离 `local_pickle` state；Axum 以 `FIN_OPS_OA_IDENTITY_ADAPTER=trusted_headers`、`FIN_OPS_ADMIN_USERNAMES=test` 运行，匹配本轮 production OA test user。
- 三项 health probe 均通过：`curl -fsS "$FIN_OPS_SHADOW_PYTHON_BASE_URL/health"`、`curl -fsS "$FIN_OPS_SHADOW_AXUM_BASE_URL/healthz"`、`curl -fsS "$FIN_OPS_SHADOW_AXUM_BASE_URL/readyz"`。
- `python3 scripts/tools/platform_shadow_preflight.py --report-date 20260517` 返回 `GO`；`python3 scripts/tools/platform_shadow_runtime.py --report-date 20260517` 返回 `GO`。
- 显式 16 endpoint runtime shadow 命令在带 before-group reseed/reload hook 后返回 `GO`；`api-shadow-validation-report-20260517.json` summary 为 `total=32`、`go=32`、`no_go=0`、`unexpected_diff_count=0`、`explained_diff_count=35`、`accepted_production_change_count=3`、`permission_failure_cases=16`、`permission_failure_missing_count=0`。
- 修复验证工具的数组通配符匹配 bug：fixture 已声明 `date_format:$.ledger.events[*].created_at`，但 validator 过去用 `fnmatch` 时无法匹配实际路径 `$.ledger.events[0].created_at`。本轮只让既有 `[*]` 语义按数组索引生效，并新增测试；未删除 case、未跳过 permission failure、未新增业务字段豁免。
- `remaining-api-contracts.md` 中 Prompt 6 真实 runtime shadow 覆盖的 16 个 endpoint 对应 route 已更新为 `implemented_shadow_go`，shadow plan 注明 2026-05-17 runtime GO（含 permission failure cases）。`POST /api/background-jobs/{job_id}/retry` 不在本次 16 endpoint 清单内，保持 `pending_contract`；后续 imports/exports 等非本范围条目状态未提升。
- 结论：Prompt 6 平台 runtime shadow 实际执行满足本子任务 GO 标准；生产总切流仍需继续验证 worker 真实消费、NATS/outbox replay、PITR/rollback、load/monitoring，以及 Prompt 4 已记录的非 runtime-shadow follow-up。

## Prompt 7 平台 API 最终 GO/NO_GO 判定（2026-05-17）

- 本轮按最终收口要求重新读取平台实现、code gap、preflight、runtime、seed、contract delta、安全幂等审计和 `remaining-api-contracts.md`。较早的 `p0-platform-api-implementation-20260517.json` 与 `p0-platform-code-gap-20260517.json` 仍保留当时的环境型 runtime NO_GO 结论；本轮以重新执行的 preflight/runtime 报告作为最新 runtime 证据。
- 完整验证通过：`cargo fmt --all --check`、`cargo check --workspace`、`cargo test --workspace`（148 passed）、指定 Python unittest（42 tests OK）、`api_route_inventory_check.py`（GO）、`platform_shadow_preflight.py --report-date 20260517`（GO）、`platform_shadow_runtime.py --report-date 20260517`（GO）。
- 16 个平台 endpoint 的 primary + permission failure runtime shadow 均为 GO；`api-shadow-validation-report-20260517.json` summary：`total=32`、`go=32`、`no_go=0`、`unexpected_diff_count=0`、`permission_failure_cases=16`。
- 最终生产切流判定为 `NO_GO`，原因不是 runtime 或测试失败，而是合同/审批证据未全部关闭：`workbench-settings-write-contract` 的 OA role sync 仍为 `NEEDS_PRODUCT_DECISION`；`settings-data-reset-create-job` 与 `settings-data-reset-direct-queues-job` 虽已按 queue-only accepted production change 通过 runtime shadow，但仍缺 product/ops approval、staging worker destructive execution proof、backup/PITR/rollback evidence 和 operator runbook。
- 已生成机器可读最终报告：`docs/operations/backend-refactor/p0-platform-api-final-no-go-20260517.json`。没有生成 final GO 报告，也没有把 readiness 或 shadow NO_GO 手工改成 GO。

## Prompt04 平台切流阻塞整合方案落地（2026-05-17）

- 针对 `workbench-settings-write-contract`，已采用生产级整合方案：不恢复旧 Python 在 settings 写请求内同步写 OA 角色；Rust settings 写路径改为在同一 PostgreSQL 事务中持久化 settings fact，并排队 `app.identity_provisioning_requests`、`job.worker_tasks`、`job.outbox_events`、`audit.events` 和幂等记录。新增 `rust/fin-ops-api/migrations/0011_identity_provisioning.sql`、`jobs/identity_role_provisioning.rs` 及 repository 事务写入逻辑；机器可读决策报告为 `docs/operations/backend-refactor/p0-settings-role-provisioning-decision-20260517.json`。该方案仍需 product/ops 明确批准：settings 写成功语义变为“settings 已落库且身份治理已排队”，不是“OA 角色已同步完成”。
- 针对 `settings-data-reset-create-job` 与 `settings-data-reset-direct-queues-job`，已补本地 worker 侧闭环能力：`settings_data_reset_worker.py`、PostgreSQL worker task repository、`run_worker_task_consumer.py`、staging proof CLI、audit lineage CLI 和 `data-reset-worker-runbook.md`。API 继续保持 queue-only，不在请求路径执行 destructive reset。机器可读证明报告为 `docs/operations/backend-refactor/p0-data-reset-worker-staging-proof-20260517.json`，当前状态仍是 `NO_GO_EXTERNAL_EVIDENCE_REQUIRED`，因为没有真实 staging destructive worker run、product/ops approval、restorable backup、PITR/restore drill 和 lineage evidence。
- 已把新 identity provisioning side effect 纳入平台 shadow seed 清理，避免重复 runtime shadow 时残留 `app.identity_provisioning_requests` 或 identity worker/outbox facts 造成幂等/唯一约束污染。已在本地 Docker PostgreSQL 17 shadow 库应用 `0011_identity_provisioning.sql`，并重跑 seed、legacy seed、preflight 和 runtime shadow。
- 复验结果：`python3 scripts/tools/platform_shadow_runtime.py --report-date 20260517` 返回 `GO`，`api-shadow-validation-report-20260517.json` 为 `total=32`、`go=32`、`no_go=0`、`unexpected_diff_count=0`。`docs/operations/backend-refactor/p0-platform-api-final-no-go-20260517.json` 已更新为 `NO_GO_PRODUCTION_CUTOVER_EXTERNAL_APPROVAL_AND_STAGING_EVIDENCE_REQUIRED`，明确代码侧整合方案已落地，但生产切流仍不得 GO。
- 本轮补充验证：`cargo fmt --all --check`、`cargo check --workspace`、`cargo test platform_legacy --workspace`、`cargo test identity_role_provisioning --workspace`、`PYTHONPATH=backend/src python3 -m unittest tests.test_settings_data_reset_service tests.test_settings_data_reset_worker tests.test_worker_task_consumer tests.test_worker_task_postgres_repository -v`、`python3 scripts/tools/platform_shadow_preflight.py --report-date 20260517`、`python3 scripts/tools/platform_shadow_runtime.py --report-date 20260517`、相关 JSON `python3 -m json.tool` 均通过。
- 剩余阻塞只剩外部生产门禁：settings identity provisioning 的 product/ops approval、worker SLA/health/alerting/staging OA apply proof；data reset 的 approval id、backup evidence id、PITR/restore drill、真实 staging worker task/request lineage 和运维审批。没有这些证据，不生成 final GO 报告。

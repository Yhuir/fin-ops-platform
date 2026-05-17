# 剩余 API 合同、事实源和 schema blocker

本文冻结 `api-route-inventory-route-level.json` 中仍为 `pending_contract` 或 `blocked_fact_source` 的 50 条 route。本文只定义后续实现边界，不代表 route 已迁移、已可切流或 shadow 已通过。

## 冻结原则

- 不访问 OA 源数据库；涉及 OA 写入或同步的 route 必须通过 job/outbox 和已冻结的 PostgreSQL 投影。
- 不猜字段；事实源未冻结时保持 `blocked_fact_source`。
- 不实现半成品 route；合同冻结只为后续 prompt 提供 route/service/repository 边界。
- 写操作必须要求 OA actor、`Idempotency-Key`、`expected_version` 或等价乐观锁，并在同一 PostgreSQL 事务内写业务事实、`audit.events`、`job.outbox_events`。
- read model/search/统计缓存只通过 outbox/Worker 失效或重建，不在请求路径全量重算。
- binary/export route 必须单独冻结文件格式、Content-Disposition、分页和对象访问边界。

## 字段约定

| 字段 | 含义 |
| --- | --- |
| status | 必须保持在 inventory 中的当前状态，直到 Axum route、shadow fixture 和 readiness evidence 全部通过。 |
| source contract | 可读取或写入的事实源；未知时明确 blocker。 |
| target tables | 已存在或待新增 PostgreSQL 表；待新增即 schema blocker。 |
| write command | 后续实现的命令边界；只读 route 写 `none`。 |
| audit event | 应写入 `audit.events.event_type` 的建议值；只读 route 写 `none`。 |
| outbox event | 应写入 `job.outbox_events.event_type` 的建议值；无异步副作用写 `none`。 |
| invalidation | read model/search/cache 失效范围；不能在请求路径重算。 |
| idempotency key | 写操作必需；只读 route 可写 `none`。 |
| permission | Axum auth/RBAC 要求。 |
| rollback | 可回滚或不可回滚时的补偿边界。 |
| shadow plan | 后续 `business-api-shadow-validation.json` 的 fixture 计划。 |
| schema gap | `yes` 表示需要 migration；`no` 表示只需 route/service/repository 或 shadow fixture。 |

## 平台 legacy 合同

| # | route | status | owner | risk | source contract | target tables | write command | audit event | outbox event | invalidation | idempotency key | permission | rollback | shadow plan | schema gap |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `POST /api/background-jobs/{job_id}/acknowledge` | implemented_shadow_go | platform-ops | medium | `job.worker_tasks` + `job.worker_task_acknowledgements`；acknowledged 保持 UI/通知层状态，不污染核心 task status。 | `job.worker_tasks`、`job.worker_task_acknowledgements`、`audit.events`、`app.write_idempotency_records`。 | `acknowledge_background_job(job_id, actor, reason)`。 | `background_job.acknowledged`。 | none。 | none；只影响通知已读状态。 | `background_job.ack:{job_id}:{actor}`。 | `can_access_app`，仅 owner 或 admin 可 ack。 | 删除 ack 记录或写 `acknowledged=false` 补偿记录。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）。 | no |
| 2 | `POST /api/background-jobs/{job_id}/retry` | pending_contract | platform-ops | medium | `job.worker_tasks`、`job.dead_letters`；只允许 retry `failed`/`dead_lettered` 且任务类型有重放协议。 | 现有 `job.worker_tasks`、`job.outbox_events`、`job.dead_letters` 足够；若要保存 retry lineage，需新增 `superseded_by_task_id`。 | `retry_worker_task(job_id, actor, reason, replay_mode)`。 | `background_job.retry_requested`。 | `worker_task.retry_requested` 或按原 task_type 发布重放 command。 | 由 task payload 的 `affected_months/affected_scopes` 决定。 | `background_job.retry:{job_id}:{actor}:{reason_hash}`。 | owner 或 admin；system task 仅 admin。 | 新任务创建后不可删除旧事实；失败时可取消新 task。 | 不在 Prompt 6 的 16 个 runtime endpoint 清单内；不得标记 GO。 | no |
| 3 | `POST /api/workbench/settings` | implemented_shadow_go | platform-ops | high | 旧 Python settings 写入合同；Rust 返回 legacy settings projection，不暴露内部 `{version, settings}` envelope。 | `app.settings_profiles`、`app.project_profiles`、`audit.events`、`app.write_idempotency_records`。 | `save_workbench_settings(actor, expected_version, patch)`。 | `settings.updated`。 | `settings.changed`。 | workbench、cost_statistics、search 按配置影响范围失效。 | `settings.save:{actor}:{expected_version}:{patch_hash}`。 | `can_admin_access`。 | 用 previous snapshot 写反向 patch；保留审计。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）。 | no |
| 4 | `POST /api/workbench/settings/projects/sync` | implemented_shadow_go | platform-ops | high | 项目同步请求只生成 worker task/outbox；不得从 OA 源库实时读取。 | `job.worker_tasks`、`job.outbox_events`、`audit.events`、`app.write_idempotency_records`、`app.settings_profiles`。 | `request_project_sync(actor, scope, source_watermark)`。 | `project.sync.requested`。 | `finops.jobs.project.sync`。 | cost_statistics、search、workbench project filter 失效。 | `project.sync:{scope}:{source_watermark}`。 | `can_admin_access`。 | 取消 queued task；已完成同步通过新同步批次补偿。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）；queue-only 为已记录生产安全差异。 | no |
| 5 | `POST /api/workbench/settings/projects` | implemented_shadow_go | platform-ops | high | 项目设置 facts 写 PostgreSQL project profile。 | `app.project_profiles`、`audit.events`、`app.write_idempotency_records`。 | `upsert_project_profile(actor, project_id, expected_version, patch)`。 | `project_profile.upserted`。 | `project_profile.changed`。 | cost_statistics、search、workbench project filter。 | `project.profile.upsert:{project_id}:{expected_version}:{patch_hash}`。 | `can_admin_access`。 | 写反向 patch 或新版本恢复。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）。 | no |
| 6 | `DELETE /api/workbench/settings/projects/{project_id}` | implemented_shadow_go | platform-ops | high | 项目删除为软删除/停用。 | `app.project_profiles`、`audit.events`、`app.write_idempotency_records`。 | `deactivate_project_profile(actor, project_id, expected_version)`。 | `project_profile.deactivated`。 | `project_profile.changed`。 | cost_statistics、search、workbench project filter。 | `project.profile.delete:{project_id}:{expected_version}`。 | `can_admin_access`。 | 重新激活前一版本。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）。 | no |
| 7 | `POST /api/workbench/settings/data-reset/jobs` | implemented_shadow_go | platform-ops | high | data reset API 只创建治理化 worker job；请求路径不执行 destructive reset。 | `app.data_reset_requests`、`job.worker_tasks`、`job.outbox_events`、`audit.events`、`app.write_idempotency_records`。 | `create_data_reset_job(actor, scope, approval_id, backup_evidence_id)`。 | `data_reset.request.requested`。 | `finops.jobs.settings.data_reset`。 | 由 reset scope 决定；完成后触发 read model rebuild。 | `data_reset.request:{scope}:{approval_id}`。 | `can_admin_access` 且二次确认。 | queued 可取消；running 后只允许按 runbook restore/补偿。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）；queue-only 为已记录生产安全差异。 | no |
| 8 | `POST /api/workbench/settings/data-reset` | implemented_shadow_go | platform-ops | high | 立即执行 data reset 不迁移为同步破坏性 API；Rust 按生产安全合同排队 worker task。 | `app.data_reset_requests`、`job.worker_tasks`、`job.outbox_events`、`audit.events`、`app.write_idempotency_records`。 | `execute_data_reset_job(task_id)`，仅 worker/maintenance context 使用。 | `data_reset.request.requested`。 | `finops.jobs.settings.data_reset`。 | all affected scopes。 | `data_reset.execute:{task_id}:{approval_id}`。 | admin + approved maintenance context。 | 只能 restore backup 或 replay import；不可物理删除无审计。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）；queue-only 为已记录生产安全差异。 | no |
| 9 | `GET\|POST /projects` | implemented_shadow_go | platform-ops | high | legacy project route 已冻结到 PostgreSQL project profile 投影；不得用 OA 或 Python state 猜测。 | `app.project_profiles`、POST 写 `audit.events`、`app.write_idempotency_records`。 | GET none；POST `create_project_profile`。 | POST: `project_profile.upserted`。 | POST: `project_profile.changed`。 | cost_statistics、search、workbench project filter。 | POST: `project.create:{external_project_id}:{payload_hash}`。 | GET `can_access_app`；POST `can_admin_access`。 | POST 软删除或状态回退。 | Prompt 6 覆盖 `projects-hub-list` 与 `projects-create-manual-profile`，均真实 runtime shadow GO（含 permission failure）。 | no |
| 10 | `GET /projects/{project_id}` | implemented_shadow_go | platform-ops | high | project detail 来源为 PostgreSQL project profile。 | `app.project_profiles`。 | none。 | none。 | none。 | none。 | none。 | `can_access_app`。 | none。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）。 | no |
| 11 | `POST /projects/assign` | implemented_shadow_go | platform-ops | high | assignment 写 PostgreSQL project assignment facts，并校验 project/object facts。 | `app.project_profiles`、`app.project_assignments`、`app.project_profile_events`、`audit.events`、`app.write_idempotency_records`。 | `assign_project(actor, source_object, project_id, expected_version)`。 | `project.assigned`。 | `project_assignment.changed`。 | workbench、search、cost_statistics。 | `project.assign:{object_type}:{object_id}:{project_id}:{expected_version}`。 | `can_mutate_data`。 | 写反向 assignment event 恢复旧项目。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）。 | no |
| 12 | `GET /ledgers` | implemented_shadow_go | platform-ops | high | ledger list 来源为 PostgreSQL ledger facts/read model，view 语义对齐旧 Python `LedgerReminderService.list_ledgers`。 | `app.ledgers`。 | none。 | none。 | none。 | none。 | none。 | `can_access_app`。 | none。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）。 | no |
| 13 | `GET /ledgers/{ledger_id}` | implemented_shadow_go | platform-ops | high | ledger detail 来源为 PostgreSQL ledger facts + event timeline。 | `app.ledgers`、`app.ledger_events`。 | none。 | none。 | none。 | none。 | none。 | `can_access_app`。 | none。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）。 | no |
| 14 | `POST /ledgers/{ledger_id}/status` | implemented_shadow_go | platform-ops | high | ledger status mutation 写 ledger facts/events。 | `app.ledgers`、`app.ledger_events`、`audit.events`、`app.write_idempotency_records`。 | `change_ledger_status(actor, ledger_id, expected_version, status)`。 | `ledger.status_changed`。 | `ledger.changed`。 | ledger read model、search。 | `ledger.status:{ledger_id}:{expected_version}:{status}`。 | `can_mutate_data`。 | 写状态回退 event。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）。 | no |
| 15 | `GET /reminders` | implemented_shadow_go | platform-ops | high | reminders 来源为 PostgreSQL reminder read model。 | `app.reminders`。 | none。 | none。 | none。 | none。 | none。 | `can_access_app`。 | none。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）。 | no |
| 16 | `POST /reminders/run` | implemented_shadow_go | platform-ops | high | reminder execution 是 job-producing route，请求路径不发送真实通知。 | `app.reminder_runs`、`job.worker_tasks`、`job.outbox_events`、`audit.events`、`app.write_idempotency_records`。 | `request_reminder_run(actor, scope, run_at)`。 | `reminder.run.requested`。 | `finops.jobs.reminder.run`。 | reminders read model。 | `reminder.run:{scope}:{run_at}`。 | `can_mutate_data` 或 admin，按提醒范围确定。 | 取消 queued task；完成后以新 run 补偿。 | Prompt 6 真实 runtime shadow 于 2026-05-17 验证 GO（primary + permission failure）；queue-only 为已记录生产安全差异。 | no |
| 17 | `POST /imports/preview` | blocked_fact_source | platform-ops | high | legacy preview 写 Python session；目标必须以对象文件和 staging parse rows 为源。 | 现有 `app.import_batches`、`app.import_files`、`staging.import_parse_results/issues`，可能需 preview session 表。 | `create_import_preview(actor, file_object_id, template_code)`。 | `import.preview_requested`。 | `import.parse_requested`。 | none；preview 不改业务 facts。 | `import.preview:{file_object_id}:{template_code}:{sha256}`。 | `can_mutate_data`。 | 删除 preview batch 或置 `failed/cancelled`。 | fixture 使用 uploaded/preflight file_object 和 parser result。 | yes |
| 18 | `POST /imports/confirm` | blocked_fact_source | platform-ops | high | 只能确认已冻结 preview/staging rows；不能从 Python session 写 facts。 | 现有 import/facts 表；可能需补 confirm run 表。 | `confirm_import_preview(actor, batch_id, expected_version)`。 | `import.batch_confirmed`。 | `import.batch_confirmed`、`read_model.rebuild_requested`。 | affected months: workbench、search、cost、tax。 | `import.confirm:{batch_id}:{expected_version}`。 | `can_mutate_data`。 | `revert_import_batch`，保留原始 rows 和审计。 | fixture 覆盖重复确认、坏行保留、affected scopes。 | no |
| 19 | `POST /imports/files/preview` | blocked_fact_source | platform-ops | high | file preview 不能依赖 legacy file session；输入必须来自 `app.file_objects`。 | 现有 `app.file_objects/import_files/staging.import_parse_results`，可能需 session projection。 | `create_file_preview(actor, file_object_id, template_code)`。 | `import_file.preview_requested`。 | `import.parse_requested`。 | none。 | `import_file.preview:{file_object_id}:{template_code}:{sha256}`。 | `can_mutate_data`。 | 取消 preview task 或标记 failed。 | fixture 覆盖 object metadata、parse issues、row counts。 | yes |
| 20 | `POST /imports/files/confirm` | blocked_fact_source | platform-ops | high | 只能确认 frozen preview rows；不读取 Python session。 | 现有 import/facts 表。 | `confirm_file_preview(actor, file_id, expected_version)`。 | `import_file.confirmed`。 | `import.batch_confirmed`、`read_model.rebuild_requested`。 | affected months。 | `import_file.confirm:{file_id}:{expected_version}`。 | `can_mutate_data`。 | 通过 batch revert 补偿。 | fixture 覆盖 confirm counts、duplicate handling、audit。 | no |
| 21 | `POST /imports/files/retry` | blocked_fact_source | platform-ops | high | retry 只能针对 parse failed task/file_object，不能重用 legacy session。 | 现有 `app.import_files`、`job.worker_tasks/outbox_events`。 | `retry_import_file_parse(actor, file_id, reason)`。 | `import_file.retry_requested`。 | `import.parse_requested`。 | none，直到 confirm。 | `import_file.retry:{file_id}:{reason_hash}`。 | `can_mutate_data`。 | 取消 queued retry task。 | fixture 覆盖 failed parse -> retry task。 | no |
| 22 | `POST /imports/batches/{batch_id}/revert` | blocked_fact_source | platform-ops | high | revert 必须基于 batch 写入的 facts lineage；不能删除无 lineage 数据。 | 现有 import/facts 表，可能需补 fact lineage/revert events。 | `revert_import_batch(actor, batch_id, expected_version, reason)`。 | `import.batch_reverted`。 | `import.batch_reverted`、`read_model.rebuild_requested`。 | affected months。 | `import.revert:{batch_id}:{expected_version}`。 | `can_mutate_data`，高风险可要求 admin。 | revert 本身是补偿；失败时保留 partial marker 并阻断切流。 | fixture 覆盖可回滚 batch、不可回滚 blocker。 | yes |
| 23 | `GET /imports/files/sessions/{session_id}` | blocked_fact_source | platform-ops | high | legacy session 没有 PostgreSQL fact；不能返回伪造 session。 | 待新增 preview session 表，或映射到 `app.import_batches.legacy_session_id`。 | none。 | none。 | none。 | none。 | none。 | `can_access_app`，只能看本人或 admin。 | none。 | fixture 冻结 legacy_session_id -> batch/file projection。 | yes |
| 24 | `POST /matching/run` | blocked_fact_source | platform-ops | high | matching run 是异步任务，只能读 PostgreSQL facts/read_model。 | 现有 `job.worker_tasks/outbox_events`、`read_model.workbench_candidate_matches`。 | `request_matching_run(actor, scope_month, reason)`。 | `matching.run_requested`。 | `workbench_matching.requested`。 | candidate_matches、workbench/search。 | `matching.run:{scope_month}:{source_watermark}`。 | `can_mutate_data`。 | 取消 queued task；完成后以新 run 覆盖候选，不删历史。 | fixture 覆盖 task/outbox 和 stale scope。 | no |
| 25 | `GET /matching/results` | blocked_fact_source | platform-ops | high | matching results 来源未冻结；目标应来自 candidate match read model。 | `read_model.workbench_candidate_matches`，可能需 run summary 表。 | none。 | none。 | none。 | none。 | none。 | `can_access_app`。 | none。 | fixture 覆盖 scope_month、status、score 排序。 | yes |
| 26 | `GET /matching/results/{result_id}` | blocked_fact_source | platform-ops | high | result detail 来源未冻结；不能回读 Python state。 | `read_model.workbench_candidate_matches`，可能需 detail payload schema。 | none。 | none。 | none。 | none。 | none。 | `can_access_app`。 | none。 | fixture 覆盖 result detail payload、source rows。 | yes |

### Prompt04 平台 runtime shadow 结论（2026-05-17）

机器可读证据：`docs/operations/backend-refactor/p0-platform-runtime-shadow-20260517.json` 与 `docs/operations/backend-refactor/api-shadow-validation-report-20260517.json`。本批次 16 个平台 endpoint 在受控 local shadow 环境中完成真实 Python/Axum 双边运行，包含 16 个 primary case 与 16 个 permission-failure case；结果为 `GO`，未删除 shadow case，未跳过权限 case，未放宽 fixture 断言。

本次只把 Prompt 6 真实 runtime shadow 覆盖的 16 个平台 endpoint 对应 route 更新为 `implemented_shadow_go`。`POST /api/background-jobs/{job_id}/retry` 不在本次 16 个 endpoint 清单内，保持 `pending_contract`，不得借本次报告标记 GO。finance/tax/ETC、import、matching、binary export 等未在 Prompt 6 真实 runtime shadow 范围内的 route 保持原状态。data reset、project sync、reminder run 等 queue-only 生产安全差异继续以已记录 accepted production delta 为准，切流前仍需 worker/staging 证据、备份/恢复演练和运行监控证据。

## finance / tax / ETC 合同

| # | route | status | owner | risk | source contract | target tables | write command | audit event | outbox event | invalidation | idempotency key | permission | rollback | shadow plan | schema gap |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 27 | `PATCH /api/bank-details/transactions/categories` | pending_contract | finance-ops | high | `app.bank_transactions` + active `app.bank_transaction_categories`；人工分类优先于自动分类。 | 现有 `app.bank_transaction_categories`、`app.bank_transaction_category_events`、`audit.events`。 | `upsert_bank_transaction_category(actor, txn_month, txn_id, category_type, expected_version, patch)`。 | `bank_transaction.category_changed`。 | `bank_transaction.category_changed`。 | workbench、search、cost_statistics、no_oa affected scope。 | `bank.category:{txn_id}:{category_type}:{expected_version}`。 | `can_mutate_data`；readonly export 用户禁止。 | 写 cancel/replaced category event 恢复旧有效分类。 | fixture 覆盖分类变更、重复提交、下游 stale。 | no |
| 28 | `GET /api/turnover-ledger/relations/{relation_id}/extra` | pending_contract | finance-ops | high | turnover extra snapshot 事实源未冻结；不得默认返回空 extra。 | 待新增 `app.turnover_relation_extras` 或扩展 `app.turnover_relations.raw_payload` 的冻结字段。 | none。 | none。 | none。 | none。 | none。 | `can_access_app`。 | none。 | fixture 先冻结 extra JSON schema 和缺省语义。 | yes |
| 29 | `PUT /api/turnover-ledger/relations/{relation_id}/extra` | pending_contract | finance-ops | high | extra 写入需基于冻结 extra fact。 | 待新增 `app.turnover_relation_extras/events`。 | `update_turnover_relation_extra(actor, relation_id, expected_version, patch)`。 | `turnover_relation.extra_updated`。 | `turnover_relation.changed`。 | turnover ledger read model、workbench/search。 | `turnover.extra:{relation_id}:{expected_version}:{patch_hash}`。 | `can_mutate_data`。 | 写反向 patch 恢复上一版本。 | fixture 覆盖 patch merge、审计、重复提交。 | yes |
| 30 | `POST /api/turnover-ledger/relations/confirm` | pending_contract | finance-ops | high | 人工确认 relation state；输入必须来自 bank/category facts 或 frozen suggestion。 | 现有 `app.turnover_relations` 可承载基础 relation；可能需 relation events。 | `confirm_turnover_relation(actor, relation_key, source_rows, expected_version)`。 | `turnover_relation.confirmed`。 | `turnover_relation.confirmed`。 | turnover ledger、workbench、search、cost_statistics。 | `turnover.confirm:{relation_key}:{expected_version}`。 | `can_mutate_data`。 | `withdraw_turnover_relation` 软撤回。 | fixture 覆盖 confirmed relation 出现在关联台/台账。 | yes |
| 31 | `POST /api/turnover-ledger/relations/{relation_id}/withdraw` | pending_contract | finance-ops | high | 只撤回 PostgreSQL active turnover relation，不删除源流水。 | 现有 `app.turnover_relations`，可能需 relation events。 | `withdraw_turnover_relation(actor, relation_id, expected_version, reason)`。 | `turnover_relation.withdrawn`。 | `turnover_relation.withdrawn`。 | turnover ledger、workbench、search、cost_statistics。 | `turnover.withdraw:{relation_id}:{expected_version}`。 | `can_mutate_data`。 | 重新 confirm 生成新版本，不复用旧 active row。 | fixture 覆盖撤回后状态、stale scopes。 | yes |
| 32 | `POST /api/etc/import/preview` | blocked_fact_source | tax-ops | high | ETC preview 解析文件，不得依赖本地临时路径或 legacy preview state。 | 现有 `app.file_objects/import_files/staging.import_parse_results`，可能需 ETC preview session 表。 | `create_etc_import_preview(actor, file_object_ids, template_code)`。 | `etc_import.preview_requested`。 | `etc.import_parse_requested`。 | none。 | `etc.preview:{manifest_hash}:{template_code}`。 | `can_mutate_data`。 | 取消 preview task 或标记 failed。 | fixture 覆盖 file metadata、parse rows、warnings。 | yes |
| 33 | `POST /api/etc/import/confirm` | blocked_fact_source | tax-ops | high | 只能确认已冻结 ETC preview/staging rows。 | 现有 `app.invoices` ETC columns、`app.import_batches`；可能需 ETC import run 表。 | `confirm_etc_import(actor, preview_id, expected_version)`。 | `etc_import.confirmed`。 | `etc_import.confirmed`、`read_model.rebuild_requested`。 | tax_offset、cost_statistics、workbench、search。 | `etc.confirm:{preview_id}:{expected_version}`。 | `can_mutate_data`。 | batch revert；不可删除源文件对象。 | fixture 覆盖 duplicate ETC invoice、counts、affected months。 | yes |
| 34 | `GET /api/etc/reconciliation-tasks/ready-for-import` | blocked_fact_source | tax-ops | high | legacy task state/local pickle 未迁移；无 PostgreSQL source。 | 待新增 `app.etc_reconciliation_tasks`、`app.etc_reconciliation_files`。 | none。 | none。 | none。 | none。 | none。 | `can_access_app`。 | none。 | fixture 先冻结 ready criteria 和 task status。 | yes |
| 35 | `GET /api/etc/reconciliation-tasks` | blocked_fact_source | tax-ops | high | 同上。 | 同上。 | none。 | none。 | none。 | none。 | none。 | `can_access_app`。 | none。 | fixture 覆盖 list filters、pagination、status。 | yes |
| 36 | `POST /api/etc/reconciliation-tasks` | blocked_fact_source | tax-ops | high | 创建 task 需对象文件、账单期间、发票范围事实。 | 待新增 `app.etc_reconciliation_tasks/files/events`，现有 job/outbox。 | `create_etc_reconciliation_task(actor, payload)`。 | `etc_reconciliation_task.created`。 | `etc.reconciliation_requested`。 | ETC task read model、tax_offset。 | `etc.task.create:{payload_hash}`。 | `can_mutate_data`。 | 取消 queued/running task；完成后创建补偿 task。 | fixture 覆盖创建 task/outbox，不执行外部读取。 | yes |
| 37 | `GET|DELETE /api/etc/reconciliation-tasks/{task_id}` | blocked_fact_source | tax-ops | high | detail/delete 均依赖 ETC task fact；delete 必须软取消。 | 待新增 `app.etc_reconciliation_tasks/events`。 | GET none；DELETE `cancel_etc_reconciliation_task(actor, task_id, expected_version)`。 | DELETE: `etc_reconciliation_task.cancelled`。 | DELETE: `etc.reconciliation_cancelled`。 | ETC task read model。 | DELETE: `etc.task.cancel:{task_id}:{expected_version}`。 | GET `can_access_app`；DELETE `can_mutate_data`。 | 重新创建 task；保留取消审计。 | fixture 覆盖 detail、cancel 状态流转。 | yes |
| 38 | `GET|PATCH|DELETE /api/etc/reconciliation-tasks/{task_id}/*` | blocked_fact_source | tax-ops | high | 子资源包括票根文本/文件、信用卡账单、补充证据、refresh matches；事实源均未冻结。 | 待新增 `app.etc_reconciliation_task_items/files/evidences/events`。 | PATCH/DELETE 按子资源执行 `update_etc_task_artifact` 或 `remove_etc_task_artifact`。 | `etc_reconciliation_task.artifact_changed`。 | `etc.reconciliation_artifact_changed` 或 `etc.refresh_matches_requested`。 | ETC task read model、tax_offset/workbench 视子资源而定。 | `etc.task.artifact:{task_id}:{artifact_type}:{expected_version}`。 | `can_mutate_data`；GET `can_access_app`。 | 写反向 artifact event；对象文件不物理删除。 | fixture 分子资源冻结最小 payload，再逐项 shadow。 | yes |
| 39 | `POST /api/etc/batches/draft` | blocked_fact_source | tax-ops | high | OA draft 创建不可直接访问 OA 源；必须通过 job/outbox 和 staging payload。 | 现有 `app.invoices` ETC batch 字段，需新增 `app.etc_oa_drafts`。 | `request_etc_batch_draft(actor, batch_scope)`。 | `etc_batch.draft_requested`。 | `etc.oa_draft_requested`。 | ETC batch read model。 | `etc.batch.draft:{batch_scope}:{source_watermark}`。 | `can_mutate_data`。 | 取消 queued draft task；已提交 OA draft 只能写撤销/作废 follow-up。 | fixture 只验证 task/outbox，不连 OA。 | yes |
| 40 | `POST /api/etc/batches/{batch_id}/draft` | blocked_fact_source | tax-ops | high | 同上，scope 为指定 batch。 | 同上。 | `request_etc_existing_batch_draft(actor, batch_id)`。 | `etc_batch.draft_requested`。 | `etc.oa_draft_requested`。 | ETC batch read model。 | `etc.batch.draft:{batch_id}`。 | `can_mutate_data`。 | 同上。 | fixture 覆盖 batch_id 存在和状态检查。 | yes |
| 41 | `POST /api/etc/batches/{batch_id}/confirm-submitted` | blocked_fact_source | tax-ops | high | submitted 状态是 invoice/batch fact，不可只改返回值。 | `app.invoices` ETC columns；可能需 `app.etc_batch_events`。 | `confirm_etc_batch_submitted(actor, batch_id, expected_version, submitted_at)`。 | `etc_batch.submitted_confirmed`。 | `etc_batch.submission_status_changed`。 | tax_offset、cost_statistics、ETC batch read model。 | `etc.batch.confirm_submitted:{batch_id}:{expected_version}`。 | `can_mutate_data`。 | `mark_not_submitted` 反向事件。 | fixture 覆盖状态流转、重复提交。 | yes |
| 42 | `POST /api/etc/batches/{batch_id}/mark-not-submitted` | blocked_fact_source | tax-ops | high | submitted 回滚必须保留审计。 | `app.invoices` ETC columns；可能需 `app.etc_batch_events`。 | `mark_etc_batch_not_submitted(actor, batch_id, expected_version, reason)`。 | `etc_batch.submission_reverted`。 | `etc_batch.submission_status_changed`。 | tax_offset、cost_statistics、ETC batch read model。 | `etc.batch.mark_not_submitted:{batch_id}:{expected_version}`。 | `can_mutate_data`。 | 再次 confirm-submitted。 | fixture 覆盖回滚状态和 audit。 | yes |
| 43 | `DELETE /api/etc/batches/{batch_id}` | blocked_fact_source | tax-ops | high | 删除/取消必须软状态变更，不删除 invoices。 | `app.invoices` ETC columns；可能需 `app.etc_batch_events`。 | `cancel_etc_batch(actor, batch_id, expected_version, reason)`。 | `etc_batch.cancelled`。 | `etc_batch.cancelled`。 | tax_offset、cost_statistics、ETC batch read model。 | `etc.batch.cancel:{batch_id}:{expected_version}`。 | `can_mutate_data`。 | 新建补偿 batch 或恢复状态事件。 | fixture 覆盖不可取消状态 blocker。 | yes |
| 44 | `POST /api/etc/invoices/revoke-submitted` | blocked_fact_source | tax-ops | high | invoice submitted revoke 必须定位 invoice facts。 | `app.invoices`；可能需 `app.invoice_inventory_events` 或 ETC invoice events。 | `revoke_etc_invoice_submitted(actor, invoice_ids, expected_version, reason)`。 | `etc_invoice.submission_revoked`。 | `etc_invoice.submission_status_changed`。 | tax_offset、cost_statistics、workbench/search。 | `etc.invoice.revoke_submitted:{invoice_ids_hash}:{expected_version}`。 | `can_mutate_data`。 | confirm-submitted 补偿事件。 | fixture 覆盖部分失败、逐 invoice error。 | yes |
| 45 | `POST /api/tax-offset/certified-import/preview` | pending_contract | tax-ops | medium | 已认证导入 preview 解析 Excel，不得保存在 legacy app state。 | 现有 `app.file_objects/import_files/staging.import_parse_results`，可能需 certified preview session。 | `create_tax_certified_preview(actor, file_object_id, month)`。 | `tax_certified_import.preview_requested`。 | `tax_certified_import.parse_requested`。 | none。 | `tax_certified.preview:{file_object_id}:{month}:{sha256}`。 | `can_mutate_data`。 | 取消 preview task。 | fixture 覆盖 parse rows、duplicate invoice、warnings。 | yes |
| 46 | `POST /api/tax-offset/certified-import/confirm` | pending_contract | tax-ops | medium | 只能确认 preview rows 并写 `app.invoice_certifications`。 | 现有 `app.invoice_certifications`、`app.import_batches`；可能需 import run 表。 | `confirm_tax_certified_import(actor, preview_id, expected_version)`。 | `tax_certified_import.confirmed`。 | `tax_certified_import.confirmed`、`read_model.rebuild_requested`。 | tax_offset、cost_statistics、workbench/search。 | `tax_certified.confirm:{preview_id}:{expected_version}`。 | `can_mutate_data`。 | revoke certification import batch。 | fixture 覆盖 certification counts、重复确认。 | no |
| 47 | `POST /api/workbench/exception/preview` | pending_contract | finance-ops | high | preview 依赖 exception projection 和 candidate state；目标应只读 frozen read model/facts。 | 现有 `app.workbench_exception_cases`、`read_model.workbench_rows/candidate_matches`；可能需 preview result schema。 | none；preview 不写业务 facts。 | none。 | none。 | none。 | none。 | `can_mutate_data`，但不产生事实写入。 | none。 | fixture 覆盖 preview candidates、no-write guarantee。 | yes |

## binary export 合同

| # | route | status | owner | risk | source contract | target tables | write command | audit event | outbox event | invalidation | idempotency key | permission | rollback | shadow plan | schema gap |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 48 | `GET /api/turnover-ledger/export` | pending_contract | finance-ops | high | 只读 `app.bank_transactions` + active categories + frozen turnover relation/extra facts；不能读取 legacy app state。 | 现有 bank/category；extra/FIFO 需新增 schema 后才能 GO。 | none。 | 可选 `export.turnover_ledger_requested`，若记录下载审计。 | none，除非大导出异步化。 | none。 | none；若异步导出用 `export.turnover:{scope}:{query_hash}`。 | `can_access_app`；只读导出用户允许。 | none；导出无业务事实写入。 | fixture 固定 XLSX sheet、列、排序、Content-Disposition、脱敏规则。 | yes |
| 49 | `GET /api/cost-statistics/export` | pending_contract | cost-ops | medium | `read_model.cost_statistics_read_models` + detail rows；不得请求路径 rebuild。 | 现有 read model；若需保存导出任务，使用 `job.worker_tasks`。 | none；大导出可 `request_cost_export`。 | 可选 `export.cost_statistics_requested`。 | none 或 `cost_statistics.export_requested`。 | none。 | none；异步时 `cost.export:{scope}:{query_hash}:{source_version}`。 | `can_access_app`；只读导出用户允许。 | none。 | fixture 固定 workbook 样式、detail flags、大结果分页。 | no |
| 50 | `GET /imports/batches/{batch_id}/download` | blocked_fact_source | platform-ops | high | 下载必须来自 `app.file_objects` object-storage metadata；不能返回本地路径或 legacy session file。 | 现有 `app.import_batches/import_files/file_objects`；可能需 batch archive manifest 表。 | none；若需要临时打包则 `request_import_batch_archive`。 | 可选 `import_batch.download_requested`。 | none 或 `import_batch.archive_requested`。 | none。 | none；异步打包时 `import.batch.archive:{batch_id}:{source_version}`。 | `can_access_app`；只读导出用户允许；必须校验 batch 可见性。 | none；临时 archive 可过期清理。 | fixture 校验 metadata、Content-Disposition、redacted access grant，不记录对象访问敏感值。 | yes |

## schema blocker 汇总

| blocker | 覆盖 route | 需要的 schema/合同 |
| --- | --- | --- |
| notification ack state | 1 | `job.task_notifications` 或 ack 表，避免污染 `job.worker_tasks.status`。 |
| settings/project facts | 3-6、9-11 | `app.settings_profiles`、`app.project_profiles`、project assignment facts/events。 |
| data reset governance | 7-8 | `app.data_reset_requests`、审批、backup evidence、scope 和 task lineage。 |
| ledger/reminder facts | 12-16 | `app.ledgers`/ledger read model、`app.reminders`/reminder runs。 |
| import preview/session/revert lineage | 17-23 | preview session projection、parse run、revert lineage 和 fact source mapping。 |
| matching result source | 24-26 | matching run summary 或 candidate detail payload 合同。 |
| turnover extra/events | 28-31、48 | `app.turnover_relation_extras/events`，以及 FIFO/allocation lot 口径。 |
| ETC task/batch events | 32-44 | ETC preview session、reconciliation task/files/evidences、batch event 表。 |
| tax certified preview | 45-46 | preview session 可选；confirm 可复用 `app.invoice_certifications`。 |
| exception preview projection | 47 | preview result schema 和 candidate state source。 |
| binary archive/download | 48-50 | XLSX/zip manifest、Content-Disposition、对象访问授权 envelope。 |

## 后续实现批次

### Batch P4-09A：platform legacy

范围：background job ack/retry、settings/project/data reset、projects、ledgers、reminders、imports preview/confirm/retry/revert/session、matching run/results。

验收：

- 先补 schema blocker，再实现 route/service/repository。
- 所有写操作用 `Idempotency-Key` 和 `audit.events`。
- job/outbox route 只创建任务，不执行长任务。
- shadow fixture 只使用 PostgreSQL/staging facts，不访问 OA 源或 app Mongo。

### Batch P4-09B：finance / tax / ETC

范围：bank category write、turnover relation extra/confirm/withdraw、ETC import/reconciliation/batch/invoice writes、tax certified preview/confirm、workbench exception preview。

验收：

- 分类、turnover、ETC、tax 写操作必须输出 affected months/scopes。
- outbox 事件必须触发 workbench、search、cost_statistics、tax_offset 的最小失效范围。
- 未冻结的 ETC task 子资源继续 blocked，不用默认空值掩盖差异。

### Batch P4-09C：binary export

范围：turnover ledger XLSX、cost statistics XLSX、import batch download/archive。

验收：

- 冻结 workbook sheet、列、排序、数字/日期格式、文件名和 Content-Disposition。
- 大结果必须分页或异步 job，不在请求路径一次性拉全量。
- 对象访问 grant 必须脱敏；不返回内部对象存储凭据或本地路径。

## inventory 状态要求

本次合同冻结后，`api-route-inventory-route-level.json` 中上述 route 仍必须保持原状态：

- `pending_contract`：18 条。
- `blocked_fact_source`：32 条。

只有后续实现 prompt 同时补齐 schema、Axum route、shadow fixture、api inventory evidence 和 readiness gate GO 后，才能改变对应 route 的 migration status。

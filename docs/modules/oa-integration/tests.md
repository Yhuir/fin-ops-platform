# OA 集成测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 必须保护的行为 | 代表测试入口 |
| --- | --- | --- |
| OA identity / APP authorization | `Admin-Token` -> canonical username；OA role/permission（含 `finops:app:view`）只作信息；canonical ACL-only tier、direct API 403、即时撤权 | `tests/test_auth_guard.py`、`tests/test_session_api.py`、`tests/test_oa_identity_service.py`、`web/src/test/SessionApi.test.ts`、`web/src/test/SessionGate.test.tsx` |
| OA Mongo 只读 adapter | 付款申请/报销/项目映射、字段变体、断连空结果、read status、backoff、附件发票 cache；附件先经统一不可信文件签名/类型/资源边界，安全版本变化使旧 cache 精确失效 | `tests/test_mongo_oa_adapter.py`、`tests/test_oa_attachment_invoice_service.py`、`tests/test_untrusted_document_policy.py` |
| 日常报销付款明细 identity | 每个 schedule item 稳定内部 ID、原 row index、项目/金额、附件 `source_expense_item_id`；历史数据通过 projection version bump 幂等重投 | `tests/test_mongo_oa_adapter.py`、`tests/test_oa_projection_sql_runtime.py`、`tests/test_workbench_query_service.py` |
| 表单专属费用类型 | 支付申请精确读取可配置 `category`；日常报销子项精确读取 `purposeType`；无关同名字段不覆盖，空/未知值不伪造“其他”；v8 历史重投幂等 | `tests/test_mongo_oa_adapter.py`、`tests/test_oa_projection_sync_service.py`、`tests/test_oa_projection_sql_runtime.py` |
| OA 投影与 sync worker | canonical 投影原子 upsert、结构化附件、cache-before-OA/OA-before-cache 双顺序 indexed identity bridge、legacy row id 迁移、权威快照单一删除 owner 与 relation 清理、formal relation 事务内重新验证 canonical 成员、零页面 fan-out、retention cutoff、API enqueue 不 inline sync、缺 queue fail-closed、AppHealth 状态只读 durable facts、生产 timer 周期性 enqueue `oa.sync` | `tests/test_oa_projection_sql_runtime.py`、`tests/test_oa_pending_payment_source_snapshot_repository.py`、`tests/test_oa_pending_payment_postgres_integration.py`、`tests/test_workbench_relation_command_service.py`、`tests/test_workbench_relation_repository.py`、`tests/test_worker_oa_sync.py`、`tests/test_runtime_worker_registry.py`、`tests/test_runtime_queue_ops.py`、`tests/test_deploy_runtime_examples.py`、`tests/test_app_status_overview_service.py`、`tests/test_app_health_api.py` |
| OA 待付款 | canonical rows/filter/detail API、权限、loading/empty/error、写后 normal GET | `tests/test_oa_pending_payment_canonical_query.py`、`tests/test_oa_pending_payment_api.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` |
| OA 手动搜索/导入 | fast search、完成状态限制、精确附件刷新复用 canonical promotion、in-progress 零提升、promotion 失败逐 row 返回、幂等导入、删除 marker、Workbench invalidation | `tests/test_oa_manual_import_service.py`、`tests/test_oa_manual_import_api.py`、`tests/test_oa_attachment_invoice_promotion_service.py`、`web/src/test/SettingsOaManualSearchImportTable.test.tsx` |
| OA applicant credentials | admin-only、保存/list/delete、password 不回显、repository 加密/解密、settings response 不泄漏 | `tests/test_oa_applicant_credentials_service.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_postgres_oa_applicant_credentials_repository.py`、`web/src/test/SettingsPage.test.tsx` |
| 目标 OA 申请人登录 | RSA 加密、HTTP/网络/无效 JSON/无 token 失败、错误不泄露 password、缺凭据不尝试登录 | `tests/test_target_oa_applicant_token_provider.py` |
| 进项发票 OA 反提 | preview hash、idempotency、目标申请人、草稿创建失败恢复、version conflict、人工 submitted/not_submitted、提交历史脱敏 | `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx` |
| ETC OA 草稿 / 人工状态 | 草稿 payload、撤销本地绑定、manual status、删除本地批次不删除真实 OA、前端 OA review URL 清洗 | `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`web/src/test/EtcApi.test.ts`、`web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/EtcOaNavigation.test.ts` |
| Runtime OA role projection | fixed selector、unique menu/三 role/exact 三 binding、只替换 dedicated members、disabled/missing/drift/timeout fail closed、compensation | `tests/test_oa_role_sync_service.py`、`tests/test_app_settings_service.py`、`tests/test_workbench_settings_sync_api.py` |
| Deploy ACL verification | 自动 profile、普通发布 005-only、retired env rejection、steady-state `eligible=true`、secret-safe artifact、OA exact topology | `tests/test_settings_access_control_preflight.py`、`tests/test_deploy_oa_script.py` |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_mongo_oa_adapter.py`、`tests/test_oa_manual_import_service.py`、`tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_etc_backend.py`、`tests/test_oa_role_sync_service.py` | 保护 OA 字段映射、完成状态、反提状态机、ETC 人工确认，以及 fixed-menu exact-set/assignment 规则。 |
| 2. Service-layer tests | 适用 | `tests/test_target_oa_applicant_token_provider.py`、`tests/test_oa_applicant_credentials_service.py`、`tests/test_oa_projection_sql_runtime.py`、`tests/test_oa_pending_payment_postgres_integration.py`、`tests/test_rehydrate_workbench_read_models.py`、`tests/test_oa_pending_payment_canonical_query.py` | 保护 service/repository/worker 编排、双顺序附件身份桥、repair 指纹门禁、凭据脱敏、外部 OA 登录失败、canonical snapshot 和零页面 fan-out。 |
| 3. API contract tests | 适用 | `tests/test_oa_applicant_credentials_api.py`、`tests/test_oa_manual_import_api.py`、`tests/test_input_invoice_usage_api.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_auth_guard.py`、`tests/test_session_api.py`、`tests/test_workbench_settings_sync_api.py` | 保护 response shape、canonical ACL-only 权限、direct denial、502/503 sync/compensation、retired runtime 字段缺失与 version conflict。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_oa_projection_sql_runtime.py`、`tests/test_worker_oa_sync.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`、`tests/test_mongo_oa_adapter.py` | 保护 OA sync worker、projection repository、Mongo read status/backoff、App Status worker/readiness 注册。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/SessionApi.test.ts`、`web/src/test/SessionGate.test.tsx`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/InputInvoiceUsage*.test.tsx`、`web/src/test/EtcApi.test.ts`、`web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/SettingsPage.test.tsx` | 保护 session bootstrap、权限态、OA 待付款 loading/empty/error/detail、反提 drawer、ETC OA 操作、设置页凭据和手动导入。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_oa_projection_sql_runtime.py`、`tests/test_input_invoice_usage_api.py`、`tests/test_etc_backend.py`、`tests/test_oa_manual_import_api.py` | 保护 OA sync -> canonical snapshot -> 页面 normal GET、进项反提 -> 草稿 -> 人工确认、ETC 业务批次 -> OA 草稿 -> 人工确认、手动导入 -> canonical 可见。 |
| 7. Existing feature regression tests | 适用 | 上述全部，加 `tests/test_platform_runtime_boundary_guards.py`、`tests/test_deploy_oa_script.py`、`tests/test_deploy_oa_nginx_config.py` | OA 集成横跨所有页面，任何改动都要先判断 session、权限、read model、Workbench、发票生命周期、税金/成本是否受影响。 |

## 本轮新增回归

- `web/src/test/SessionGate.test.tsx`
  - `keeps validating and retries after a transient OA session timeout`

该测试补齐 OA iframe / 前端 bootstrap 的短暂超时回归：首次 `/api/session/me` 超时不能立刻显示“会话校验失败”，应保持验证态并自动重试；重试成功后进入业务页面。

- `tests/test_target_oa_applicant_token_provider.py`
  - `test_http_error_uses_oa_message_without_exposing_password`
  - `test_network_failure_invalid_json_and_missing_token_are_failures`

这两个测试补齐目标 OA 申请人登录的外部失败分支：HTTP error、网络不可达、无效 JSON、缺 token 都必须失败，且错误信息不能泄漏目标申请人密码。

## 历史 bug 回归库

| 场景 | 回归入口 | 保护点 |
| --- | --- | --- |
| OA permission/业务 role 被误当作 APP admission | `tests/test_session_api.py`、`tests/test_auth_guard.py`、`tests/test_permissions_write_entry_inventory.py` | permission-bearing `YNSYLP006` 缺席 canonical ACL 仍 denied；OA 信息字段不能 grant APP access；retired env/path 不得恢复。 |
| Runtime 在 drift 下宽清理或部分更新 OA | `tests/test_oa_role_sync_service.py`、`tests/test_app_settings_service.py` | unique menu/三 role/exact binding 在 DML 前验证；runtime 只替换三 dedicated members，disabled/missing/drift/timeout rollback。 |
| 稳态发布误恢复一次性 cleanup 或放行 cutover artifact | `tests/test_deploy_oa_script.py` | 历史 SQL/写路径必须不存在；ACL activation 只接受 `eligible=true`，topology/env 漂移零写阻断。 |
| OA session 首次校验因代理/OA 慢响应短暂超时 | `web/src/test/SessionGate.test.tsx` | 首次 `request_timeout` 保持“正在验证 OA 会话...”并自动重试，不能立刻落到错误页；成功重试后进入业务页面。 |
| OA Mongo 短暂断连导致页面误认为 fresh | `tests/test_mongo_oa_adapter.py` | 断连返回空结果但 read status 为 error，并进入 backoff。 |
| OA upsert 隐式删除使 relation 清理丢失 row id | `tests/test_oa_pending_payment_source_snapshot_repository.py::OaPendingPaymentSourceSnapshotRepositoryTests::test_commit_preserves_deleted_row_ids_when_other_completed_oa_remains`、`tests/test_oa_projection_sql_runtime.py::OAProjectionSqlRuntimeTests::test_postgres_oa_projection_repository_migrates_legacy_expense_relations_without_scope_cleanup`、`tests/test_oa_pending_payment_postgres_integration.py::OaPendingPaymentPostgresIntegrationTests::test_authoritative_snapshot_cancels_relation_when_one_of_multiple_completed_oa_disappears` | upsert 只写投影和迁移 identity；权威快照是唯一 stale completed 删除 owner，必须把删除 row id 交给正式 relation command，并在同一 PostgreSQL 事务取消失效 relation。 |
| 自动匹配用事务外旧 plan 重建已删除 OA relation | `tests/test_workbench_relation_repository.py::test_canonical_relation_member_lock_reports_deleted_member_and_locks_existing_rows`、`tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_formal_plan_fails_before_relation_lock_when_canonical_member_was_deleted`、`tests/test_oa_pending_payment_postgres_integration.py::OaPendingPaymentPostgresIntegrationTests::test_stale_matching_plan_cannot_recreate_relation_after_oa_disappears` | formal relation command 必须在同一 UoW 内先锁定并验证 typed canonical members，再取得 relation advisory lock；OA 已删除时 fail closed 且零 relation 写入，禁止依赖页面刷新或后续补偿清理。 |
| OA lifecycle alias 导致附件发票 cross-OA blocker | `tests/test_audit_object_identity_tool.py::AuditObjectIdentityToolTests::test_active_oa_source_alias_downgrades_lifecycle_duplicate`、`tests/test_postgres_migrations.py::PostgresMigrationDiscoveryTests::test_expected_migration_files_are_present_and_ordered`、`tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_sql_contains_required_schemas_and_tables` | `flowRequestId/processId` 缺失的进行中文档与带 `flowRequestId` 的已完成文档内容一致时，只能通过 `app.oa_source_aliases.status='active'` 的显式 alias canonicalize；未批准 alias 仍 blocking，且不得删除 OA 投影/cache。 |
| 进行中 OA 通过人工刷新提前解析附件 | `tests/test_mongo_oa_adapter.py::MongoOAAdapterTests::test_manual_attachment_refresh_keeps_in_progress_attachment_as_metadata_only`、`tests/test_oa_manual_import_service.py::OAManualImportServiceTests::test_refresh_attachments_does_not_promote_in_progress_records` | completed-only 约束必须位于 adapter 构建入口；人工刷新不得下载/OCR/生成发票，返回 `not_completed`，但保留附件引用供完成态后解析。 |
| 铁路电子客票票价后紧邻长客票号 | `tests/test_oa_attachment_invoice_service.py::OAAttachmentInvoiceServiceTests::test_parse_invoice_text_stops_railway_price_before_following_ticket_number` | `票价: ¥145.00` 压平文本后不得把下一行电子客票号拼入金额；parser version 变化使旧错误 cache 在精确重解析时失效。 |
| ongoing/completed 同源 OA 的正式发票提升冲突 | `tests/test_oa_attachment_invoice_promotion_service.py::OAAttachmentInvoicePromotionServiceTests::test_active_lifecycle_alias_allows_completed_oa_to_reuse_ongoing_invoice`、`tests/test_oa_attachment_invoice_promotion_service.py::PostgresOAAttachmentInvoiceRepositoryTests::test_resolves_only_active_oa_source_aliases_in_one_query` | promotion 只接受 active alias；历史 `derived_from_oa_id=父OA ID:item:...` 先归一父 OA ID，同一 canonical OA 允许完成态补充来源边；不同 canonical OA 仍 `source_context_conflict`，alias 必须每批集合查询。 |
| 历史完成态别名导致 relation distribution 丢 OA summary | `tests/test_oa_projection_sync_service.py::OaProjectionSyncServiceTests::test_oa_sync_treats_legacy_completed_workflow_aliases_as_completed`、`tests/test_workbench_relation_sql_projection.py::WorkbenchRelationSqlProjectionTests::test_rebuild_keeps_oa_summary_for_legacy_completed_workflow_status` | `workflow_status=已完成/approved/2` 等历史完成态必须在 OA projection 边界被视为完成，触发 source version 重建后，`workbench_relation` 能生成 `linked_oa`，下游待找发票不需要 fallback 推断。 |
| OA sync API 在 HTTP 进程内直接同步 | `tests/test_oa_projection_sql_runtime.py` | 手动 sync API 只 enqueue worker job，不 inline sync。 |
| HTTP 进程内 OA polling/hot rebuild 污染 projection sync 链路 | `tests/test_oa_projection_sql_runtime.py::OAProjectionSqlRuntimeTests::test_http_server_does_not_support_in_process_oa_polling`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_in_process_oa_polling_and_hot_rebuild_entrypoints_are_removed` | `FIN_OPS_OA_POLLING_ENABLED` 不再启动进程内 polling；`OASyncService`、polling、dirty rebuild、hot rebuild 私有入口必须不存在，OA 变更统一通过 durable `oa.sync` worker 链路处理。 |
| 周期性自动读取 Mongo 缺少 durable producer | `tests/test_runtime_queue_ops.py::RuntimeQueueOpsTests::test_enqueue_oa_sync_cli_writes_durable_event`、`tests/test_deploy_runtime_examples.py::DeployRuntimeExampleTests::test_oa_sync_enqueue_timer_uses_durable_queue_cli` | 生产周期性同步由 `finops-enqueue-oa-sync.timer` enqueue `oa.sync:all`，worker 消费后读取 Mongo；不得用 API 进程 polling 替代。 |
| AppHealth OA 上次读取时间被 projection row `synced_at` 覆盖 | `tests/test_operations_dashboard_service.py::OperationsDashboardServiceTests::test_build_payload_reports_inventory_performance_and_runtime_metrics`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_sync_status_endpoint_reads_durable_queue_status` | Operations Dashboard 的 OA 同步时间优先使用 `app.oa_sync_runs(sync_type='oa_projection')` 成功 run；`/api/oa-sync/status` 从 outbox/worker/latest run 组合状态，不读进程内内存状态。 |
| OA 附件 OCR 残缺号码或未知证据被创建为正式发票 | `tests/test_oa_attachment_invoice_service.py::OAAttachmentInvoiceServiceTests::test_parse_files_does_not_return_unknown_evidence_with_invoice_number`、`tests/test_object_identity_policy.py::FinancialObjectIdentityPolicyTests::test_oa_attachment_invoice_evidence_classification_is_centralized`、`tests/test_invoice_attachment_recognition_service.py`、`tests/test_import_service.py::ImportNormalizationServiceTests::test_oa_attachment_allow_create_requires_formal_invoice_evidence`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_attachment_invoice_cache_update_ignores_incomplete_ocr_identity` | 附件解析候选层、附件识别层、app cache update 路径和底层 `allow_create=True` 都必须要求正式发票 evidence type 或明确正式发票 document kind；残缺号码、非正式票据、未知证据、多义命中直接忽略，不得把未知 OCR 提升为 `app.invoices`。 |
| OA 附件发票 promotion 默认污染统一发票池 | `tests/test_app_settings_service.py`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_attachment_invoice_cache_update_does_not_create_missing_invoice_by_default`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_attachment_invoice_cache_update_disabled_mode_skips_promotion`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_attachment_invoice_cache_update_create_missing_mode_promotes_formal_invoice`、`web/src/test/SettingsPage.test.tsx` | 默认 `link_existing_only` 只允许关联已有正式发票；`disabled` 完全跳过 promotion；只有 `create_missing` 显式开启时才允许正式发票缺失后创建 `app.invoices`。 |
| 幂等人工附件刷新无法修复历史关联 | `tests/test_oa_attachment_invoice_promotion_service.py::OAAttachmentInvoicePromotionServiceTests::test_manual_refresh_reconciles_matching_when_canonical_invoices_are_unchanged`、`tests/test_oa_manual_import_service.py::OAManualImportServiceTests::test_refresh_attachments_is_targeted_to_selected_row_ids` | 精确 `refresh-attachments` 必须保持零重复 invoice write，同时为所选 completed OA 补发既有五个月 matching window；普通自动 sync 不获得该强制语义。 |
| 目标申请人凭据泄漏到 settings response | `tests/test_oa_applicant_credentials_api.py` | save/list/settings/delete response 不包含 password。 |
| 进项 OA 反提缺凭据仍创建本地 batch | `tests/test_input_invoice_usage_oa_reverse_service.py` | 缺凭据时不创建 batch，不伪造 OA 草稿成功。 |
| ETC OA 草稿 review URL 带 draft/filter 参数 | `web/src/test/EtcOaNavigation.test.ts` | 前端打开稳定 OA 表单列表，不携带 draft id 和 auto edit 参数。 |

## 关键 smoke flows

发布前或 staging 应至少人工/自动 smoke：

1. OA iframe 打开 `/fin-ops/?embedded=oa` -> `/api/session/me` 成功 -> 只读用户看不到写入口，全操作用户可写，管理员可进设置高风险入口；permission-bearing denied 用户即使仍看见旧 menu DOM，direct APP session/API 也必须拒绝。
2. OA sync `2026-05` -> 投影写入 -> Workbench / OA 待付款 / 进项使用 / App Status 显示 fresh 或 refreshing 一致。
3. 设置页保存目标 OA 申请人凭据 -> 进项发票选择 -> 创建 OA 草稿 -> OA 页面可见 draft -> 用户人工确认 submitted/not_submitted。
4. ETC 业务批次创建 OA 草稿 -> 撤销本地绑定或人工确认 submitted -> 删除本地批次不删除真实 OA 草稿/流程。
5. OA Mongo 临时不可用 -> 页面/API 不把旧投影伪装为 fresh，App Status 暴露 blocked/degraded。
6. ACL role projection 后用新的 `/system/menu/getRouters` 或新 OA shell session 验证 menu；旧 DOM/旧 token 不作证据。需要专项复验时显式使用 candidate-bound 双身份 artifact、hash 和 post-deploy restore；标准发布不重复 006 验证。

P2/P3 一秒级闭环中，这些真实 OA 场景对应 `.planning/P2P3-CLOSURE-PLAN.md` 的 P2P3-013 staging gate。通过条件不是本地 mock 绿灯，而是真实 OA 登录、角色同步、目标申请人、草稿 URL、附件、人工 submitted/not_submitted、投影 freshness 和 App Status 语义均有 staging/production 证据。缺凭据、缺测试对象、只跑本地 stub 或只返回 `auth_missing` 时，状态保持 `staging-gated`。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_mongo_oa_adapter \
  tests.test_worker_oa_sync \
  tests.test_oa_identity_service \
  tests.test_oa_applicant_credentials_service \
  tests.test_oa_applicant_credentials_api \
  tests.test_postgres_oa_applicant_credentials_repository \
  tests.test_target_oa_applicant_token_provider \
  tests.test_input_invoice_usage_oa_reverse_service \
  tests.test_input_invoice_usage_api \
  tests.test_oa_pending_payment_projection_rows \
  tests.test_oa_pending_payment_api \
  tests.test_oa_projection_sql_runtime \
  tests.test_oa_manual_import_service \
  tests.test_oa_manual_import_api \
  tests.test_oa_role_sync_service \
  tests.test_deploy_oa_script \
  tests.test_deploy_oa_nginx_config \
  -v

cd web && npm test -- --run \
  src/test/SessionApi.test.ts \
  src/test/SessionGate.test.tsx \
  src/test/OaPendingPaymentsPage.test.tsx \
  src/test/InputInvoiceUsagePage.test.tsx \
  src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx \
  src/test/SettingsPage.test.tsx \
  src/test/SettingsOaManualSearchImportTable.test.tsx \
  src/test/EtcApi.test.ts \
  src/test/EtcTicketManagementPage.test.tsx \
  src/test/EtcOaNavigation.test.ts

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

ACL role sync 回归由 `tests.test_oa_role_sync_service` 和 `tests.test_app_settings_service` 保护：fixed selector、唯一 menu/三 role/exact 三 binding、固定 admin、target assignments、connect/read/write timeout、generic/no-op 零调用、真实变化一次 target、已知 DB failure 最多一次 compensation、compensation failure fail closed。`tests.test_settings_access_control_preflight` 与 `tests.test_deploy_oa_script` 保护自动 profile、steady-state-only ACL activation 与旧 cleanup 链保持删除。真实 OA 三角色成员和 fresh router 只由 ACL 发布前 read-only preflight 与发布后 full→read→denied/restore evidence证明。

Nightly CI 应至少覆盖：

- 后端 OA adapter / projection / sync / credentials / API contract tests。
- 前端 session、设置、进项 OA 反提、OA 待付款、ETC OA action mapper tests。
- `bash scripts/verify.sh docs`。

真实 OA/Mongo/staging smoke 不应塞进普通 nightly，除非有隔离测试环境和安全凭据。

## 未测风险

- 真实 OA 登录接口、RSA 公钥、`openssl`、目标申请人账号状态、OA 草稿页面 URL 和 OA 返回 token shape 只能由 staging/生产前 smoke 证明。
- 真实 OA Mongo 字段变体、历史附件、超大月份和索引性能不能由 stub 完全覆盖。
- 真实 OA 菜单角色同步、同域 cookie、iframe 下载/跳转、Nginx 代理行为需要部署环境验证。
- 真实 Postgres/RabbitMQ/Redis/systemd worker drain 和 App Status heartbeat 需要运行环境验证。
- 全页面全角色矩阵成本高，当前由代表性 API/UI 权限测试和 `permissions-and-audit` 模块统一覆盖。

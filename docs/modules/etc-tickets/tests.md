# ETC票据管理 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_etc_backend.py`、`tests/test_import_service.py` | 覆盖人工确认状态推进、历史已提交业务批次创建、批次上报金额优先、散票折叠规则、ETC 发票进入 canonical invoice 时强发票号 identity 优先于弱 fingerprint、旧 canonical invoice 加载时清理弱 fingerprint、任意阶段业务批次删除、已提交批次本地 reset 后发票释放规则。 |
| 2. Service-layer tests | 适用 | `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`tests/test_import_service.py`、`tests/test_postgres_core_repository.py`、`tests/test_historical_etc_business_batch_migration_service.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_pair_relation_service.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_cleanup_orphan_etc_reconciliation_tasks_tool.py` | 覆盖 ETC business batch service 调用对账任务闭环、durable import job 活跃时对账任务不被启动恢复打断、runtime worker 从 `EtcImportResult.items` 回查 ETC 发票并同步 canonical invoice、业务批次已成功导入但 task 停在 ready 时创建 OA 草稿前的一致性补偿、ETC canonical invoice dedup 不用弱 fingerprint 合并同日同额不同发票号、repository 写入时 source unique key 与 weak fingerprint 互斥、历史迁移 service 编排、repository 落库金额/数量派生、审计、已提交批次 reset 链路、importing/closed/submission link 等任意阶段任务删除、删除后的 reconciliation task 以 `deleted` tombstone 防止部署重启复活、summary active relation 取消且不恢复旧 OA+流水二栏关系、ETC OA 检测 worker/adapter 不再注册，以及对象存储失败时对账任务上传状态不留下半写入 source file。 |
| 3. API contract tests | 适用 | `tests/test_etc_backend.py` | 覆盖 `manual-oa-status` 后响应、submitted bucket、月份筛选按开票/通行日期匹配且 counts 与 items 使用同一筛选口径、Workbench row shape、`DELETE /api/etc/business-batches/{id}` 对已提交批次返回本地 reset 结果、`DELETE /api/etc/reconciliation-tasks/{id}` 通过绑定业务批次执行同一删除链路、旧 task-only submission/import metadata 链路也不再返回 submitted confirmation guard、业务批次删除后重启不会重新出现在 `/api/etc/reconciliation-tasks`、ETC 导入确认失败 job 不阻塞同 session 重试、ETC `oa-status/refresh` 已移除且 business batch payload 不再输出 `oaDetection*` 字段，以及 ETC 源文件上传在对象存储不可写时返回 `reconciliation_file_storage_unavailable`/503。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_postgres_repositories_boundaries.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 Workbench projection 从业务批次表生成 open `etc_invoice_summary`、隐藏散票、匹配 OA 时追加汇总行、active relation 已存在时 open 区过滤陈旧 ETC summary、已提交批次 reset 后 summary 消失且散票恢复、包含 summary 的 active relation 取消后 OA/银行流水不恢复二栏配对，durable ETC import job 活跃 session 阻止 task hydration recovery，failed/acknowledged/cancelled 导入 job 不被同 session 幂等复用，deleted reconciliation task 重启后不 rehydrate 且 Postgres formal file rows 被清理，runtime import worker 与 API import confirm 使用同一 canonical invoice 同步口径，并验证展示金额与结构化 `amount_value`/numeric 金额列同时存在以支持金额搜索。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/CandidateGroupGrid.test.tsx`、`web/src/test/EtcApi.test.ts` | 覆盖单一批次列表、未提交/已提交 tab、tab 计数与当前月份/车牌/关键词筛选下的可见列表一致、页面初始化/刷新只读取任务且不会自动 POST 创建空任务、人工确认按钮、确认后刷新任务/已提交 bucket、无自动检测入口、草稿后显示待人工确认状态、任意阶段删除入口不因 OA/导入状态禁用、已提交批次删除确认文案、local reset 调用、ETC summary 展开明细按钮，以及大 ZIP 预览上传不会被普通 API timeout 提前截断。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_etc_backend.py` | 覆盖导入/批次/人工提交/创建 OA 草稿/对账任务闭环/关联台展示/已提交批次本地 reset、任务入口删除绑定业务批次并取消 summary relation 的关键路径，并覆盖 durable import restart 后业务批次与 linked task 的一致性恢复。 |
| 7. Existing feature regression tests | 适用 | `tests/test_etc_backend.py`、`tests/test_object_storage_repository.py`、`tests/test_oa_projection_sql_runtime.py`、`tests/test_mongo_oa_adapter.py`、`tests/test_postgres_migrations.py`、`tests/test_rabbitmq_staging_preflight.py`、`web/src/test/EtcTicketManagementPage.test.tsx` | 覆盖既有 ETC 页面旧入口、OA 匹配汇总行、删除/文件/补充凭证交互、OA projection/Mongo adapter 删除 ETC 专用候选查询后不影响非 ETC OA 能力、对象存储 repository 暴露 backend/bucket 给 PostgreSQL 文件写入，migration 清单连续，RabbitMQ staging preflight 不再要求 ETC OA detection worker，防止旧撤销提交入口、旧检测入口和旧删除状态阻塞重新暴露。 |

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v
PYTHONPATH=backend/src python3 -m unittest tests.test_import_service tests.test_postgres_core_repository -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards tests.test_rabbitmq_staging_preflight -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v
PYTHONPATH=backend/src python3 -m unittest tests.test_object_storage_repository tests.test_file_object_storage tests.test_etc_reconciliation_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_deleted_task_does_not_rehydrate_from_postgres_retained_row_or_reuse_id tests/test_etc_backend.py::EtcApiTests::test_deleted_business_batch_route_tombstones_task_after_postgres_rehydrate tests/test_postgres_repositories_boundaries.py::test_ops_tax_etc_deleted_reconciliation_task_clears_formal_file_rows tests/test_cleanup_orphan_etc_reconciliation_tasks_tool.py -q
python -m pytest tests/test_historical_etc_business_batch_migration_service.py tests/test_migrate_historical_etc_business_batches_tool.py
python -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_active_import_session_is_not_recovered_after_hydration tests/test_etc_backend.py::EtcApiTests::test_business_batch_oa_draft_recovers_linked_task_after_durable_import_restart
python -m pytest tests/test_etc_reconciliation_service.py tests/test_etc_backend.py tests/test_import_service.py -q

cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx src/test/CandidateGroupGrid.test.tsx
cd web && npm run build
```

## 未测风险

- `tests.test_etc_backend` 中依赖本机真实票据样例的用例在样例缺失时会 skip；核心 ETC 业务批次和 Workbench projection 路径不依赖这些样例。

# ETC票据管理 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- `etc_business_batches` 继续作为用户可见业务批次事实源，`etc_reconciliation_tasks` 继续作为导入、核对、来源文件和提交闭环的 workflow 状态，不物理合并为单表/单实体。
- 历史已在关联台 paired 的 ETC 批次可通过专用 migration service 转入新业务批次模型；迁移必须复用 `EtcService`、pair relation service、现有 state/repository 持久化和 Workbench invalidation，不允许临时 SQL 直接改 read model。
- `etc_invoice_summary` 在 open 区和 paired 区都必须保留可展开 ETC 发票明细；已存在 active pair relation 的 ETC 外部批次不得继续泄漏到 open 区。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-11 - ETC新建批次闭环与task-only列表收敛

- 目标：消除刷新、重新部署或删除后仍在未提交列表看到多条“新建ETC批次”的问题，并保证新建批次和删除批次都走同一套后端闭环语义。
- 影响范围：`EtcBusinessBatchApplicationService.create_batch_payload`、`POST /api/etc/business-batches` 契约、ETC 页面批次列表与 workflow 选择逻辑、前端 API mapper/mock、ETC 模块测试和运维清理说明。
- 关键决策：用户可见列表只以 `/api/etc/business-batches*` 为事实源，`etc_reconciliation_tasks` 只作为 workflow/internal 状态或异常恢复线索；“新建批次”由后端 application service 复用 reconciliation task service 创建 task，再复用 business batch service 创建 active business batch，并返回统一 business batch payload；若 business batch 创建失败，本次新建 task 立即通过 service 删除/tombstone，避免历史同类 task-only 行再次复活。生产已存在 orphan task 使用 `cleanup_orphan_etc_reconciliation_tasks` dry-run/execute 清理，不直接 SQL 改表。
- 文档影响：更新 `docs/dev/api-contracts.md`、本模块 `README.md`、`state-machine.md`、`tests.md` 和 `docs/operations/etc-business-batches.md`。
- 测试覆盖：新增后端 API/service 回归覆盖省略 `taskId` 创建 linked task + active business batch、业务批次创建失败时 tombstone 新 task；新增前端回归覆盖 orphan reconciliation task 不进入左侧批次列表、新建批次调用 `createEtcBusinessBatch({})`、workflow 内 standalone task 删除入口继续可用；更新前端 mock 以匹配后端闭环。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_deleted_task_does_not_rehydrate_from_postgres_retained_row_or_reuse_id tests/test_postgres_repositories_boundaries.py::test_ops_tax_etc_deleted_reconciliation_task_clears_formal_file_rows tests/test_cleanup_orphan_etc_reconciliation_tasks_tool.py -q`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npm test -- --run src/test/EtcApi.test.ts`。
- 未测风险：尚未在生产库执行 orphan task 清理；必须先核对 `/api/etc/business-batches?status=active` 与 `/api/etc/reconciliation-tasks`，再对没有 active business batch 绑定的 task id 逐个 dry-run/execute。真实浏览器 smoke、前端 build 和 docs verify 由最终验证阶段执行。
- 后续事项：发布后 smoke 需确认新建批次接口返回 linked `taskId` 且左侧未提交列表只显示 business batch；若历史 orphan task 仍存在，按运维 runbook 清理。

## 2026-06-11 - 首轮测试闭环

- 目标：完成 `etc-tickets` 模块 codebase 影响面分析、七类测试矩阵补强、状态机更新和主控依赖图登记。
- 影响范围：ETC 票据管理页面/API mapper，`/api/etc*` business batch/reconciliation task/import/source file/legacy routes，`EtcService`、`EtcBusinessBatchApplicationService`、`EtcReconciliationTaskService`、import worker、Workbench SQL projection、App Status 和相关测试。
- 关键决策：维持 documented-risk 状态；已有测试覆盖业务批次状态、删除/reset、source file、canonical invoice、导入 job、Workbench `etc_invoice_summary`、前端交互和历史迁移工具，本轮不新增重复测试。
- 文档影响：更新本模块 `README.md`、`tests.md`、`state-machine.md`，并在 `docs/dev/testing-closure-dependency-map.md` 登记模块细化。
- 测试覆盖：确认 `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`tests/test_import_service.py`、`tests/test_postgres_core_repository.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_pair_relation_service.py`、`tests/test_platform_runtime_boundary_guards.py`、ETC cleanup/migration tool tests、`web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/EtcApi.test.ts`、`web/src/test/CandidateGroupGrid.test.tsx`。
- 验证命令：见 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实大 ZIP/票根网混合包、真实对象存储/Nginx 上传、真实 OA 草稿系统、生产历史迁移 dry-run/execute、Workbench/税金/成本/search 全量重建最终页面 smoke。
- 后续事项：由 `settings` 模块继续测试闭环；ETC 相关真实环境 smoke 保留在发布前 gate。

## 2026-06-10 - ETC删除后部署重启复活修复

- 目标：修复用户已删除未提交 ETC 批次后，下一次部署/重启进入 ETC 页面又出现 task-only 空批次的问题。
- 影响范围：`EtcReconciliationTaskService.delete_task`、PostgreSQL ETC repository 的 reconciliation state 持久化、业务批次删除 API 触发的绑定 task 清理、生产 orphan task 清理工具。
- 关键决策：`etc_reconciliation_tasks` 删除不再从 snapshot 物理移除，而是写入 `status=deleted` tombstone。用户可见列表、详情和 ready-for-import 候选过滤 deleted task；tombstone 保留 task counter 和删除事实，避免 Postgres 只 upsert 不 delete 的正式表在重启后重新 hydrate 旧行。生产历史残留由 `cleanup_orphan_etc_reconciliation_tasks.py` 按显式 `--task-id` dry-run/execute 清理，工具复用 service 删除边界，不直接 SQL 修改业务表。
- 文档影响：更新 ETC 状态机、测试矩阵和本实施记录；产品口径、页面入口和 OA 口径不变。
- 测试覆盖：新增 service 级 Postgres-like retained row 重启不复活/ID 不复用测试；新增业务批次删除 API 后重启不复活测试；新增 Postgres repository deleted task 清理 formal file rows 测试；新增生产清理工具 dry-run 阻塞 active business batch 和 execute 幂等测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_deleted_task_does_not_rehydrate_from_postgres_retained_row_or_reuse_id tests/test_etc_backend.py::EtcApiTests::test_deleted_reconciliation_task_route_does_not_reappear_after_postgres_rehydrate tests/test_etc_backend.py::EtcApiTests::test_deleted_business_batch_route_tombstones_task_after_postgres_rehydrate tests/test_postgres_repositories_boundaries.py::test_ops_tax_etc_deleted_reconciliation_task_clears_formal_file_rows tests/test_cleanup_orphan_etc_reconciliation_tasks_tool.py -q`。
- 未测风险：本记录不代表已对生产库执行清理；生产清理仍需先 dry-run 核对 task id，再 execute。

## 2026-06-10 - ETC导入/OA草稿本地持久化失败根因修复

- 目标：修复确认 ETC ZIP 导入后前端显示“导入失败”，以及 OA 草稿已在 OA 系统创建且附件已上传但前端仍显示“接口处理失败”的问题。
- 影响范围：`ImportNormalizationService` canonical invoice identity、PostgreSQL invoice repository、runtime import worker 的 ETC 导入结果同步、PostgreSQL migration、RabbitMQ/worker 部署样例。
- 关键决策：ETC 发票有稳定发票号/强 canonical identity 时，弱 `invoice:<卖方>:<日期>:<金额>` fingerprint 不得写入 `app.invoices.data_fingerprint`，也不得留在 raw payload 中重新加载；弱 fingerprint 只用于没有强 identity 的历史/异常发票候选。API 路径和 runtime worker 路径都必须按 `EtcImportResult.items[*].invoice_number` 回查 ETC service 并同步 canonical invoice，避免后台导入成功但本地发票同步缺失。导入确认同一 session 只复用 queued/running 或近期 succeeded 的 job，failed/acknowledged/cancelled 旧 job 不得阻塞用户重新点击确认导入。ETC OA 自动检测已废弃，部署样例和 RabbitMQ preflight 不再包含 `etc_business.oa_detection.refresh` 或 `etc-business-oa-detection` worker。
- 文档影响：更新 ETC 模块测试矩阵、状态机记录和运维检查；产品口径和页面 API shape 不变。
- 测试覆盖：新增旧 canonical invoice 加载时清理弱 fingerprint 的 business core 回归；新增 Postgres repository 写入边界测试；新增 runtime worker 从 `EtcImportResult.items` 回查发票的 service/boundary 回归；新增同一导入 session 失败后可重试且成功后仍幂等复用 job 的 API 回归；更新 migration discovery 和 RabbitMQ preflight 测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_import_service tests.test_postgres_core_repository -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards tests.test_rabbitmq_staging_preflight -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v`。
- 未测风险：未在真实浏览器重新上传生产 ZIP；自动化已覆盖触发线上异常的持久化唯一键路径和后台导入同步路径。生产部署后需要执行 migration `0065_invoice_canonical_identity_fingerprint_invariant.sql`，并停用旧 `fin-ops-worker@etc-business-oa-detection.service`。

## 2026-06-10 - ETC任务删除旧阻塞清理与空任务追因

- 目标：修复点击删除仍返回 `ETC batch has submitted confirmation metadata and cannot be deleted.`，并解释/防止部署后误以为页面自动新建空批次的问题。
- 影响范围：`DELETE /api/etc/reconciliation-tasks/{id}`、旧 `/api/etc/batches/{id}` 兼容删除入口、`EtcService` import/submission batch 删除、ETC 页面任务选择状态和初始化请求。
- 关键决策：批次删除统一为本地清理链路，不再因 `confirmed_at`、submitted status、OA/workbench link、import invoice assignment 等旧 submission/import batch guard 阻塞。任务删除会先解析绑定业务批次、导入批次和提交批次，再清理本地导入、核对、提交元数据和 ETC 发票；真实 OA 草稿/流程仍不删除。页面初始化只允许 GET 读取现有任务，不能自动 POST 创建空任务；部署后出现的“空批次”是已有持久化 task-only 记录，不是页面自动创建。
- 文档影响：更新 API 契约和测试矩阵，明确任意阶段本地删除/reset 语义。
- 测试覆盖：新增后端回归覆盖旧 task-only submission metadata 删除不再命中 submitted confirmation guard；调整 reconciliation service 测试覆盖 importing、submission link、closed 状态删除；前端测试覆盖页面初始化不自动创建任务。
- 验证命令：`python -m pytest tests/test_etc_backend.py -q`；`python -m pytest tests/test_etc_reconciliation_service.py tests/test_workbench_pair_relation_service.py -q`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npm test -- --run src/test/EtcApi.test.ts`；`cd web && npm run build`。
- 未测风险：未在真实浏览器点击生产页面；自动化已覆盖实际报错路径和页面初始化请求行为。

## 2026-06-10 - ETC旧批次删除入口桥接修复

- 目标：修复页面点击删除时旧 `/api/etc/batches/{submissionBatchId}` 路径命中提交确认元数据 guard，返回 `ETC batch has submitted confirmation metadata and cannot be deleted.` 的问题。
- 影响范围：`EtcService` 业务批次 linked id 查询、旧 ETC batch 删除 API 兼容入口、ETC 页面删除按钮的业务批次匹配逻辑、前端测试 mock。
- 关键决策：删除仍以 `etc_business_batches` 业务批次删除服务为唯一入口；旧 submission/import/external id 只做兼容解析，解析到业务批次后转交 `DELETE /api/etc/business-batches/{id}` 同一条本地清理链路，不在旧 submission batch 删除逻辑里新增绕过分支。
- 文档影响：状态机和 API 长期口径不变，本记录补充兼容修复背景。
- 测试覆盖：新增后端旧 submission batch id 删除桥接业务批次 reset 回归；新增前端 legacy submission row 点击删除时走业务批次删除接口、不走旧 batch 删除接口的交互回归。
- 验证命令：`python -m pytest tests/test_etc_backend.py -q`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npm run build`。
- 未测风险：未在真实浏览器手动点击生产页面；自动化已覆盖旧 id 入口和当前页面按钮请求路径。

## 2026-06-09 - ETC canonical invoice弱指纹冲突修复

- 目标：修复 ETC ZIP 导入显示失败，以及创建 OA 草稿时 OA 系统已成功创建/附件已上传但前端仍显示接口失败的问题。
- 影响范围：`FinancialObjectIdentityPolicy.identify_etc_invoice_mapping`、`ObjectDedupDecisionService.decide_invoice_import`、ETC 发票同步到 canonical `app.invoices` 的去重语义。
- 关键决策：ETC 发票存在强发票号 identity 时，canonical invoice 只使用该强 identity；普通“卖方 + 日期 + 金额”的弱 suspected fingerprint 只保留在审计字段，不写入 `data_fingerprint`，也不参与强 identity 未命中后的 fallback 合并。这样同一批内多张同卖方、同日、同金额但不同发票号的 ETC 发票不会被 `invoices_data_fingerprint_uidx` 误判为重复。
- 文档影响：更新 ETC 模块测试矩阵；页面口径和 API shape 不变。
- 测试覆盖：新增 `ImportNormalizationService` 回归，覆盖 ETC 发票号变化时不靠弱 fingerprint 合并旧发票，以及同卖方/同日/同金额/不同发票号的 ETC 发票可保留为两张 canonical invoice；历史 repair parsed seed 幂等用例恢复通过。
- 验证命令：`pytest tests/test_import_service.py -q`；`pytest tests/test_etc_backend.py::EtcApiTests::test_historical_etc_repair_reconcile_is_idempotent_from_seed_bundle -q`；`pytest tests/test_etc_reconciliation_service.py tests/test_etc_backend.py tests/test_import_service.py -q`。
- 未测风险：本次未执行真实生产写入；生产上已经存在的失败 background job 仍会保留失败记录，但部署后重新触发导入/创建草稿链路不应再因同类 weak fingerprint 唯一键冲突失败。

## 2026-06-09 - ETC durable导入恢复与OA草稿一致性修复

- 目标：修复确认导入 ETC ZIP 后后台 job 成功写入业务批次，但 linked `etc_reconciliation_tasks` 被服务启动恢复回 `ready_for_import`，随后点击“创建草稿”抛出通用接口失败的问题。
- 影响范围：`EtcReconciliationTaskService` 导入恢复时机、`BackgroundJobService` active source 查询、`Application` service 组装顺序、`EtcBusinessBatchApplicationService.create_oa_draft_payload`。
- 关键决策：`IMPORTING -> READY_FOR_IMPORT` 不再由 task service 构造函数无条件执行；Application 在 background job service 初始化并标记陈旧 job 后，按仍活跃的 `etc_invoice_import` session 显式恢复真正中断的 task。创建 OA 草稿前先验证 linked task 已 imported/closed；若业务批次已有成功导入 attempt 和发票，但 task 仍停在 ready/importing，则复用 `mark_imported` 做幂等一致性补偿，不绕过状态机。
- 文档影响：更新 ETC 模块测试矩阵；产品口径、页面口径和 API shape 不变。
- 测试覆盖：新增 active import session 不被 hydration recovery 打断的 service 状态机测试；新增 durable import restart 半状态下创建 OA 草稿会补齐 linked task 并记录 OA draft 的业务闭环测试。
- 验证命令：`pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_active_import_session_is_not_recovered_after_hydration tests/test_etc_backend.py::EtcApiTests::test_business_batch_oa_draft_recovers_linked_task_after_durable_import_restart -q`；`pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_interrupted_importing_task_recovers_to_ready_after_hydration tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_delete_task_rejects_importing_closed_and_submission_links tests/test_etc_backend.py::EtcApiTests::test_task_aware_etc_import_confirm_imports_sum_matched_invoices_only tests/test_etc_backend.py::EtcApiTests::test_etc_confirm_returns_background_job_and_imports_asynchronously tests/test_etc_backend.py::EtcApiTests::test_task_aware_etc_import_empty_allowlist_does_not_import_original_zip -q`。
- 未测风险：`pytest tests/test_etc_reconciliation_service.py tests/test_etc_backend.py -q` 仍有既存历史 repair 用例 `test_historical_etc_repair_reconcile_is_idempotent_from_seed_bundle` 失败，失败点为 canonical invoice 数量 `1 != 2`，与本次 durable import/task 状态修复无关。

## 2026-06-09 - ETC源文件上传与大ZIP预览超时修复

- 目标：修复上传信用卡账单 PDF 时后端对象存储写入链路抛出未结构化异常，前端只显示通用“接口处理失败”的问题；同时修复 ETC ZIP 批量预览上传被普通 API 60 秒 timeout 截断的问题。
- 影响范围：`S3ObjectStorageRepository`、`EtcReconciliationTaskService.store_uploaded_source_file`、ETC 对账任务上传 API、业务批次源文件上传 API、ETC 前端 API helper 的大文件上传/预览/确认超时配置。
- 关键决策：继续复用现有对象存储 repository、PostgreSQL state store 和 ETC reconciliation service；不在前端绕过上传失败。对象存储不可写时返回 `reconciliation_file_storage_unavailable`/503，且任务 source files、版本号和审计事件必须回滚到上传前状态。ETC ZIP 上传预览使用大文件专用 timeout，不取消超时保护；本机同批 6 个真实 ZIP 解析耗时低于 1 秒，生产报错主要来自上传耗时被前端 60 秒截断。
- 文档影响：更新 API 契约、测试矩阵和运维告警；产品口径不变。
- 测试覆盖：新增 S3 repository backend/bucket contract 测试、信用卡账单上传结构化存储错误测试、业务批次源文件上传结构化存储错误测试、票根网 TXT 文件上传正常解析测试、TXT 文件上传结构化存储错误测试、保留文本路由结构化存储错误测试、ETC ZIP 预览上传超过普通 60 秒仍保持请求的前端 API 测试，并回归对象存储和 ETC reconciliation service 测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_object_storage_repository tests.test_file_object_storage tests.test_etc_reconciliation_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_etc_business_batch_source_files_append_to_reconciliation_task tests.test_etc_backend.EtcApiTests.test_credit_card_statement_upload_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_etc_business_batch_source_file_upload_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_ticket_root_upload_route_imports_txt_file_with_clipboard_parser tests.test_etc_backend.EtcApiTests.test_ticket_root_txt_file_upload_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_ticket_root_text_route_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_reconciliation_mutations_require_expected_version_and_reject_ready_patch -v`；`cd web && npm test -- --run src/test/EtcApi.test.ts src/test/ImportCenterPage.test.tsx src/test/EtcTicketManagementPage.test.tsx`。
- 未测风险：`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v` 仍有既存历史修复用例 `test_historical_etc_repair_reconcile_is_idempotent_from_seed_bundle` 失败，失败点在历史发票导入去重数量，与本次对象存储上传链路无关。

## 2026-06-09 - 历史ETC批次迁移与open区泄漏防线

- 目标：把历史 1-4 批 ETC 配对事实转入新业务批次模型，并确保已进入 active pair relation 的 ETC summary 不再散落到关联台未配对区。
- 影响范围：`EtcService.create_historical_submitted_business_batch`、`HistoricalEtcBusinessBatchMigrationService`、`migrate_historical_etc_business_batches.py`、Workbench SQL projection、Workbench groups repository、关联台 ETC summary 展开明细。
- 关键决策：迁移按旧 OA/银行/ETC relation 作为真实事实源，不补齐第 1 批缺失的去年发票；业务批次上报金额和 ETC 发票合计差额写入 `amount_breakdown`。Workbench projection 负责新 generation 的 open 排除，repository 在 groups 查询层再基于 active relation 过滤陈旧 generation 中的 open ETC summary，避免旧 read model 泄漏。
- 文档影响：更新 ETC 模块实施记录、测试矩阵和关联台状态机；产品口径不变。
- 测试覆盖：新增历史迁移 service/tool 测试、ETC service 历史业务批次测试、Workbench SQL projection/repository open 排除测试、CandidateGroupGrid ETC summary 展开明细测试、dedup fallback 回归测试。
- 验证命令：`python -m pytest tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_excludes_open_etc_summary_groups_already_linked_by_active_relation tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_pins_workbench_groups_page_to_active_generation tests/test_postgres_migrations.py::PostgresMigrationSqlTests::test_sql_has_required_extensions_and_indexes tests/test_postgres_migrations.py::PostgresMigrationDiscoveryTests::test_expected_migration_files_are_present_and_ordered`。
- 生产验证：生产库历史 1-4 批已生成 `etc_business_batch_hist_20260114_187293`、`etc_business_batch_hist_20260215_154900`、`etc_business_batch_hist_20260312_193545`、`etc_business_batch_hist_20260413_241125`；关联台 open 查询只保留第 5 批 `etc_20260520_001`，paired 查询可看到 1/43/27/44 张 ETC 明细。
- 未测风险：新增索引迁移 `0062_workbench_relation_etc_external_batch_idx.sql` 需要由 owner/migrator 角色在部署流程执行；runtime 账号只读验证通过但无权创建该索引。

## 2026-06-09 - 业务批次筛选计数口径修复

- 目标：修复 ETC 页面筛选后出现“已提交显示 1，但列表为空”的不一致状态。
- 影响范围：`GET /api/etc/business-batches`、`EtcBusinessBatchApplicationService` 列表筛选、ETC 页面 tab 计数、测试 API mock。
- 关键决策：修复后端筛选契约，让 `counts` 和 `items` 共享同一组 scope、月份、车牌和关键词筛选；ETC 月份筛选按开票日期、通行开始日期和通行结束日期共同匹配。前端不做临时覆盖计数，继续消费后端事实。
- 文档影响：更新产品口径、API 契约和测试矩阵。
- 测试覆盖：新增 API 契约测试验证已提交批次按通行月份可见且不匹配月份 counts/items 同为 0；新增前端交互测试验证 tab 计数与当前筛选下列表一致。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_business_batch_application_service.py backend/src/fin_ops_platform/app/server.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npm run build`；`git diff --check`。
- 未测风险：未执行真实浏览器联调；自动化已覆盖接口契约和 ETC 页面筛选交互。

## 2026-06-09 - 已提交批次本地删除与发票释放闭环

- 目标：允许用户删除已提交 ETC 业务批次用于重新走流程，同时确保删除只影响本地 ETC 批次合并关系，不撤销真实 OA 或重开已闭环对账任务。
- 影响范围：`EtcService.delete_business_batch`、`DELETE /api/etc/business-batches/{id}`、ETC 页面 submitted bucket 删除入口、Workbench open 区 ETC summary/散票投影。
- 关键决策：后端对象不合并为单实体；`etc_business_batches` 继续作为用户可见业务批次事实源，`etc_reconciliation_tasks` 继续作为 workflow 状态。已提交批次删除写入 `submitted_business_batch_reset` 审计，业务批次进入 `deleted`，提交批次本地退出 submitted 状态，ETC 发票恢复 `unsubmitted/current_batch_id=null`，旧 OA 和 closed task 保留。
- 文档影响：更新产品口径、API 契约、状态机、测试矩阵和运维检查，明确这是本地 reset，不是 OA 撤销。
- 测试覆盖：新增 service 级已提交删除释放发票测试、API + Workbench 闭环测试、前端已提交批次删除确认与 local reset 调用测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_service.py backend/src/fin_ops_platform/app/server.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx`；`cd web && npm run build`。
- 未测风险：未执行真实浏览器联调；自动化已覆盖本地 reset、Workbench summary 消失和散票恢复合同。

## 2026-06-09 - 历史已提交批次数据修复与金额搜索闭环

- 目标：将历史批次 `etc_business_batch_0004` 从人工已提交但任务未闭环的中间状态修复为已提交闭环，并让关联台可按 `1673` 命中汇总 ETC 发票。
- 影响范围：`app.etc_business_batches`、`app.etc_reconciliation_tasks`、Workbench SQL read model 的 `workbench_rows`、`workbench_group_rows` 和 `workbench_groups`。
- 关键决策：对账任务按正式 `oa_submitted_confirmed -> closed` 语义补齐，不在前端隐藏未提交任务；`etc_invoice_summary` 保留展示金额 `amount=1,673.30`，同时提供结构化 `amount_value=1673.30` 给 read model numeric 列和搜索文本。
- 文档影响：更新 `tests.md` 与 `state-machine.md` 的 read model 金额字段说明；长期业务口径未变化。
- 测试覆盖：加强 `tests.test_workbench_sql_runtime`，覆盖 ETC summary `amount_value` 和 repository 写入 `workbench_rows.amount`、`workbench_group_rows.searchable_text`。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/workbench_sql_projection.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`。
- 未测风险：未重新跑前端构建；本次没有改 ETC 页面 UI 代码。
- 后续事项：如果 all 聚合同步重建继续耗时，应由 worker 异步刷新并配合 generation retention 清理旧生成版本。

## 2026-06-09 - ETC人工已提交闭环与关联台summary修复

- 目标：修复人工点击“已提交”后批次仍留在未提交区、关联台未配对区找不到上报金额 ETC 汇总发票的问题。
- 影响范围：ETC 业务批次人工确认、`app.etc_business_batches` 持久化、Workbench SQL projection、ETC 页面人工确认交互。
- 关键决策：`etc_invoice_summary` 不再只依赖旧 `app.invoices + etc_submission_batches` 隐藏发票路径；已提交业务批次本身也是 summary 来源，并按业务批次 scope 生成一条汇总行，金额优先取 submission/business batch 上报金额，散票只作为展开明细和兜底金额来源。
- 文档影响：更新 `state-machine.md` 和 `tests.md`；长期业务口径未变化。
- 测试覆盖：新增 SQL projection 业务批次来源测试、repository 业务批次金额/数量落库测试，并加强前端人工确认后刷新任务和 submitted bucket 的交互测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime ...`；`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_etc_business_manual_submitted_closes_the_linked_reconciliation_task tests.test_etc_backend.EtcApiTests.test_etc_business_manual_submitted_creates_open_workbench_summary_with_reported_amount -v`；`cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx -t "manually confirms a draft-created business batch as submitted without refresh entry"`。
- 未测风险：尚需在最终验证阶段运行完整 ETC 页面测试、完整 SQL runtime 测试和前端 build。

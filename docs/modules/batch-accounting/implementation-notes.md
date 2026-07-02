# 批量账务 实施记录

## 2026-07-02 - 写后关联台 read model durable refresh 补齐

- 目标：修复 submit/withdraw API 变快后，生产 smoke 中撤回关系事实已成功但未提交 bucket/关联台 active generation 不收敛的问题；避免旧 `_schedule_workbench_read_model_persist` 作为唯一发布链路导致 SQL read model 不刷新。
- 影响范围：`Application._execute_batch_accounting_relation_lifecycle_event(...)`、批量账务 API 测试、模块边界文档和 GSD 调试记录；不改变前端 API shape，不把 `workbench_read_model` 慢域重新放回请求线程。
- 关键决策：批量账务写后 lifecycle 仍排除同步 `workbench_read_model` 重建；同时新增显式 durable I/O：通过 `ReadModelRefreshGateway.enqueue_many("workbench", affected_scope_keys, reason="batch_accounting_relation_changed", metadata=...)` 投递 Workbench read model refresh。生产 SQL active generation 收敛依赖 runtime worker；旧 local persist 仅保留 best-effort/compat。
- 测试覆盖：新增 `test_batch_accounting_lifecycle_enqueues_workbench_refresh_without_synchronous_rebuild`，断言 wrapper 仍向通用 lifecycle 传 `excluded_domains={"workbench_read_model"}`，并把 normalized month scope 投递到 `workbench` refresh gateway。
- 验证命令：见本轮最终说明。
- 未测风险：本地单测只验证边界 I/O；真实 enqueue-to-fresh、Worker drain 和关联台 paired 可见性必须由部署后的 1273.06 生产 smoke 证明。

## 2026-07-02 - submit/withdraw 旧持久化链路删除与 scope 收窄

- 目标：修复 1273.06 生产链路中提交/撤回 command 已完成但 API 长时间等待、偶发 timeout/blocked 后用户误以为失败的问题；避免批量账务关系变化默认触发 all scope 派生刷新。
- 影响范围：`BatchAccountingApiRoutes` submit/withdraw side effect、`Application._batch_accounting_routes(...)` wiring、`BatchAccountingService` mutation result / relation metadata、批量账务 API 回归测试、模块边界文档和关联台关系边界文档；不改变前端 API endpoint，不新增独立 read model。
- 关键决策：批量账务 relation 事实持久化只属于 `WorkbenchRelationCommandService` repository。route 不再在 command 成功后再次调用旧 `_schedule_workbench_pair_relation_persist(...)`，也不再保留 snapshot rollback restore；该旧链路既重复写关系事实，又把接口热路径拖慢。写后 lifecycle 只使用 service 输出的 `affected_scope_keys`，并以 `include_all=False` 执行。
- Scope 设计：submit 从本次银行/OA/附件发票 row payload 日期计算具体月份，并持久化到 relation `special_metadata.affected_scope_keys`；withdraw 优先使用该 metadata，老关系缺字段时用 SQL 窄 submit context 反查 row 日期。没有窄 loader 时不得退回整页 Workbench loader，只能按 relation month/all fallback；只有无法解析任何具体月份时才允许回退 `all`。
- Lifecycle 设计：批量账务 route 注入专用 lifecycle wrapper，调用通用 `_execute_derived_data_lifecycle_event(..., excluded_domains={"workbench_read_model"})`。`workbench_read_model` 仍通过 `_schedule_workbench_read_model_persist` 异步重建，避免撤回/提交 API 同步等待关联台 Workbench 视图发布。
- 旧链路删除：删除 batch accounting route 构造参数里的 `schedule_pair_relation_persist`、`pair_relation_snapshot`、`restore_pair_relation_snapshot`，删除 `Application` 中仅服务该旧回滚链路的 batch-accounting restore helper；测试改为断言旧 persist 被接回时会失败。
- 测试覆盖：`test_submit_does_not_call_legacy_pair_relation_persist_and_scopes_lifecycle_to_months`、`test_submit_records_concrete_affected_scope_keys_for_cross_month_relation`、`test_withdraw_legacy_relation_derives_scope_keys_from_narrow_context`、`test_withdraw_legacy_relation_uses_sql_narrow_loader_for_scope_backfill`，并更新 submit/withdraw API response 的 `affected_scope_keys`/barrier target 和 `excluded_domains` 断言。
- 验证命令：见本轮最终说明。
- 未测风险：本地单测不能替代部署后 1273.06 撤回->重提->已提交 bucket->关联台 paired 的真实生产 smoke 和真实 p95；生产上仍受 PostgreSQL cache、worker drain 和并发影响。

## 2026-07-02 - submit/已提交读取性能边界收窄

- 目标：修复 1273.06 生产链路中撤回、重新提交和已提交读取耗时过长的问题；避免单次 submit command 和已提交 bucket 继续复用整页候选读取，导致“写入已成功但用户等待很久/误以为失败”。
- 影响范围：`BatchAccountingService` 的 submit/list context、`Application._batch_accounting_service(...)` 依赖注入、Workbench SQL read repository、`WorkbenchRelationReadFacade` / repository port、批量账务 API 回归测试和模块边界文档；不改变前端 API shape，不新增独立 batch-accounting read model。
- 关键决策：命令热路径必须有独立 I/O。submit 只读取本次 `bank_row_id`、`oa_row_ids` 和对应 OA 附件发票；已提交 bucket 用年份级 batch-accounting relation DTO 和银行行窄 payload。旧 `load_batch_accounting_workbench_payload(bank_year)` 保留为未提交列表候选读口，不允许继续污染 submit/已提交热路径。
- 旧链路删除：SQL runtime 下 submit 不再调用全量候选 loader；已提交 bucket 不再按 12 个月循环读取 relation DTO，也不再用整页 Workbench 候选 payload 补齐 OA/发票明细。
- 测试覆盖：`test_submit_uses_sql_read_model_loader_when_available` 现在断言 submit 使用 narrow command loader 且 full loader 不可被调用；`test_submitted_list_relation_bucket_uses_workbench_relation_distribution` 断言已提交 bucket 使用年份级 relation list，不再出现 month scan。
- 验证命令：见本轮最终说明。
- 未测风险：关联台 paired 可见仍依赖 `workbench` active generation worker 发布；本地单测不能替代部署后的 1273.06 撤回->重提->关联台 paired 生产 smoke 和真实 p95 观测。

## 2026-07-02 - submit/withdraw 写前 relation read model gate 删除

- 目标：修复撤回后立即重新提交时，command 事实源已经可写但 `workbench_relation` read model 仍在 refreshing 导致 `batch_accounting_read_model_not_fresh` 的慢链路/误失败。
- 影响范围：`BatchAccountingService.submit(...)`、`withdraw(...)`、后端 API 回归测试和本模块测试矩阵；不改变列表 GET freshness 诊断、不改变 relation command service、dirty scope 或前端 API shape。
- 关键决策：写安全边界属于 canonical `WorkbenchRelationCommandService`，submit/withdraw 在写前只按本次 row ids 查询 active relation 冲突和版本；`workbench_relation` read model freshness 是读侧诊断/刷新边界，不能作为普通写阻断污染命令链路。
- 旧链路删除：删除 submit/withdraw 热路径里按 row ids 调用 relation facade `get_by_row_ids(require_fresh=True)` 并用 `_ensure_relation_read_model_fresh(...)` 拒绝写入的旧链路；对应 helper 已移除，避免以后被重新接入。
- 测试覆盖：`test_submit_checks_active_relations_only_for_selected_rows_without_relation_read_model_gate`、`test_submit_uses_canonical_write_safety_when_relation_read_model_is_not_fresh`、`test_withdraw_uses_canonical_write_safety_when_relation_read_model_is_not_fresh`。
- 验证命令：见本轮最终说明。
- 未测风险：生产真实耗时仍受 PostgreSQL、worker drain 和 workbench active generation 发布影响；发布后需跑 1273.06 撤回->重提->关联台已配对 smoke。

## 2026-07-02 - active batch relation 进入关联台 paired 投影

- 目标：修复生产 smoke 中 `CASE-BATCH-txn_imported_1393` 已成功写入 active `batch_accounting` relation，但关联台 `workbench_groups` 把它发布为 open `existing_case_candidate`，导致“批量账务已提交但关联台已配对区域不可见”。
- 影响范围：`WorkbenchCandidateGroupingService` paired 判定、Workbench SQL projection 回归测试、批量账务/关联台边界文档；不改变 batch accounting submit/withdraw API shape，不新增 read model。
- 关键决策：`relation_mode=batch_accounting` + `special_metadata.source=batch_accounting` 是明确的批量账务 active relation I/O，不能依赖旧 `manual_confirmed -> fully_linked` 展示 code 巧合。Grouping 层把 batch-accounting relation code 作为 paired 判据，再由既有 required row type 规则判断完整性。
- 旧链路删除：阻断 active batch relation 掉入 open `existing_case_candidate` 候选链路；前端和 API 不做补丁式筛选。
- 测试覆盖：新增 `tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_sql_projection_keeps_active_batch_accounting_multi_oa_invoice_relation_paired`，覆盖多 OA、多 OA 附件发票、金额不一致的生产形态；保留既有 OA+银行 batch relation paired 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_sql_projection_keeps_active_batch_accounting_oa_bank_relation_paired tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_sql_projection_keeps_active_batch_accounting_multi_oa_invoice_relation_paired -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_candidate_grouping -v`。
- 未测风险：本地测试不替代部署后的真实 worker drain 和生产 `/api/workbench/groups` paired smoke；仍需发布后验证 1273.06 链路在关联台已配对区可见。

## 2026-07-02 - 提交成功后后台同步假失败修复

- 目标：修复“日常报销批量账务管理”提交 API 已成功写入 relation，但后置 `workbench_relation` operation barrier blocked/timeout 或列表 reload 中断时，页面把结果显示成“操作失败”的假失败。
- 影响范围：`BatchAccountingPage` submit/withdraw post-command flow、页面 Vitest、模块 README / boundary I/O / tests 文档；不改变后端 relation command service、dirty scope、worker 或 API response shape。
- 关键决策：命令边界和读侧收敛边界分离。`POST /api/batch-accounting/submit` / withdraw 成功后，页面最多短等 barrier 并尝试 reload；后置同步失败只返回“关联关系仍在后台同步”，不能覆盖 command 成功。真实 command/API 失败仍走原错误路径。
- 旧链路删除：删除前端把 post-command barrier/reload 异常直接冒泡到 `runOperation` 失败态的链路，避免“成功写入但弹操作失败”污染用户链路。
- 测试覆盖：新增 `BatchAccountingPage.test.tsx::keeps a successful submit successful when the relation barrier is still blocked`；后端 `tests.test_batch_accounting_api` 继续覆盖 command service、freshness precondition、rollback 和 DTO。
- 验证命令：`npm --prefix web test -- --run src/test/BatchAccountingPage.test.tsx`；`PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api -v`。
- 未测风险：真实生产登录态提交 smoke 和真实 operation barrier 长尾仍需发布后验证；本轮修复的是错误语义和等待上限，不替代后续对 `/api/batch-accounting` GET p95 的 SQL/读路径专项优化。

## 2026-07-01 - 未提交首屏 relation I/O 收窄

- 目标：降低 `/api/batch-accounting` 未提交首屏耗时，避免为了 `submitted_count` 和关系排除加载过多 `workbench_relation` DTO。
- 影响范围：`BatchAccountingService` 未提交列表 read path、`WorkbenchRelationReadFacade`、`WorkbenchRelationReadModelRepositoryPort`、PostgreSQL read model repository、read model manifest、SQL Workbench batch loader 和后端回归测试。
- 关键决策：不新增独立 batch-accounting read model，不加缓存；复用现有 `workbench_relation` fresh/status/enqueue 边界。未提交列表只把批量账务银行候选和日常报销 OA 候选传给 relation facade；`submitted_count` 走 `count_batch_accounting_relations_by_year` 轻量 I/O，不再扫描 12 个月完整 submitted relation payload。
- 旧链路删除：未提交首屏不再扫描 12 个月 submitted relation DTO，不再把 Workbench 全量 open OA rows 送进 relation facade。已提交 bucket 因页面需要关系明细，仍保留完整 DTO 读取。
- 文档影响：更新 README、boundary I/O、tests、本实施记录、`docs/dev/api-contracts.md`、`docs/app-architecture/pages.md`、`docs/app-architecture/runtime-and-ownership.md`、`docs/architecture/module-boundaries/read-model-contracts.md` 和 `docs/modules/workbench-relations/boundary-io.md`。
- 测试覆盖：新增 `test_unsubmitted_relation_lookup_is_scoped_to_batch_candidates`、`test_unsubmitted_list_uses_relation_count_instead_of_month_relation_scan`、`test_batch_accounting_count_uses_repository_count_without_loading_rows`，并更新 SQL runtime/manifest/port 测试。
- 验证命令：`pytest -q tests/test_batch_accounting_api.py tests/test_workbench_relation_read_facade.py tests/test_read_model_manifest.py tests/test_workbench_sql_runtime.py tests/test_platform_runtime_boundary_guards.py`、`bash scripts/verify.sh docs`、`git diff --check`。
- 生产 smoke：部署 `main-54ed8296-20260701165026` 后，authenticated `GET /api/batch-accounting?bank_year=2026&bucket=unsubmitted&bank_page_size=200&oa_page_size=200` p95 从约 `1249.872ms` 降到 `457.508ms`；7/7 次返回 `200`，read model 均为 `fresh`。
- 未测风险：全量 Playwright 前端回归未在本轮重跑；长期生产 p95 仍会随 DB cache、并发和 OA 权限缓存波动。

## 2026-06-30 - 右侧 OA 候选移除年份过滤

- 目标：右侧 OA 栏改为展示没有 active `workbench_relation` 配对关系的日常报销 OA 主单，不再通过 OA 年份输入或 `oa_year` 参数过滤候选。
- 影响范围：`BatchAccountingService` 候选规则、SQL Workbench payload loader、batch accounting route/API DTO、`BatchAccountingPage` 页面控件、SLO probe、API/页面/SQL loader 回归测试和模块/API 文档。
- 关键决策：保留左侧银行流水年份作为银行候选范围；删除前端 `OA年份` 控件和 submit/fetch 的 `oa_year` 字段；后端 route 不再传 `oa_year`，service/repository 不再接收 OA 年份；旧 query 参数即使出现也不得影响 OA 候选结果。提交 metadata 只保留实际选中 OA 推导出的 `oa_years` 审计信息，不再写单值 `oa_year`。
- 文档影响：同步 README、boundary I/O、state-machine、tests、business flow 和 API contract。
- 测试覆盖：后端 API 覆盖旧 `oa_year` 不过滤候选、跨年 OA 提交和 metadata；SQL runtime 覆盖 OA/invoice 查询不再带年份范围；前端组件/API 覆盖无 `OA年份` 控件、GET/POST 不发送 `oa_year`、跨年 OA 默认可选并可提交。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_batch_accounting_loader_reads_only_active_workbench_generations -v`；`cd web && npm test -- --run src/test/BatchAccountingApi.test.ts src/test/BatchAccountingPage.test.tsx`；`cd web && npx playwright test e2e/batch-accounting-flow.spec.ts --project=chromium`。
- 未测风险：未跑真实 PostgreSQL 大历史 OA 数据量和 worker drain；当前实现沿用既有显式分页和 relation freshness 边界。

## 2026-06-24 - 模块闭环审计与生产证据 defer

- 目标：对照模块化 IO 完成定义审计 batch-accounting 当前状态，判断是否可以进入 full closed。
- 影响范围：`.planning/refactors/modular-io-boundaries/analysis/batch-accounting-module-closure-audit-and-production-evidence-defer.md`、autonomous queue/state/journal/next prompt；不改 runtime。
- 关键决策：本地 IO/route/service/legacy/read-model freshness/operation barrier/test/docs 证据已足够支撑本地实现闭环，但缺少真实 PostgreSQL、worker drain、App Status 收敛、生产历史 relation/case-id collision 和真实大年份数据证据。因此不标 full closed，记录 `production-evidence-deferred`，且不依赖本地 `PGSQL_URL` 或 staging 数据库。
- 文档影响：本实施记录和 autonomous 状态更新；模块状态机定义不变。
- 测试覆盖：无 runtime 改动；本 slice 只跑 docs/diff 校验。前序切片已跑 API/service/static/app check。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实生产 worker/read model drain、历史数据 dry-run、高行数浏览器性能仍需未来只读生产验证或人工批准的受控写入 runbook。
- 后续事项：回到 read model pilot 闭环，推进 `read-models:bank-detail-module-closure-audit-and-production-evidence-defer`，GoHotPath 仍不得启动。

## 2026-06-24 - App-level repair helper 删除

- 目标：删除没有运行时调用者的 `Application._repair_batch_accounting_relation_case_ids(...)`，避免 `server.py` 保留一个可写 pair relation persist、derived lifecycle event 和 Workbench read model persist 的旧兼容入口。
- 影响范围：`server.py`、`tests/test_batch_accounting_api.py` 的 GET 只读回归、`tests/test_platform_runtime_boundary_guards.py` 的 batch-accounting route/repair guard、相关 refactor 架构文档。
- 关键决策：删除 app-level wrapper，不删除 `BatchAccountingService.repair_legacy_case_id_collisions(...)`；service-level repair 仍由 command service 边界和现有历史修复测试保护。
- 文档影响：新增 `.planning/refactors/modular-io-boundaries/analysis/batch-accounting-repair-compat-removal.md`；更新长期 backend-refactor 文档，移除 `server.py` repair helper 仍存在的旧事实。
- 测试覆盖：静态 guard 防止 `def _repair_batch_accounting_relation_case_ids` 回归；GET 回归改为证明 app-level repair helper 不存在且列表仍正常；service repair tests 继续覆盖 command-service delegation 和 fail-fast。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_route_handlers_do_not_bypass_service_boundaries tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_repair_has_no_direct_pair_write_fallback -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api.BatchAccountingApiTests.test_unsubmitted_list_does_not_run_legacy_relation_repair tests.test_batch_accounting_api.BatchAccountingApiTests.test_repair_legacy_case_id_collision_delegates_relation_write_to_command_service tests.test_batch_accounting_api.BatchAccountingApiTests.test_repair_legacy_case_id_collision_requires_relation_command_service_without_direct_pair_fallback tests.test_batch_accounting_api.BatchAccountingApiTests.test_repair_legacy_case_id_collision_restores_lost_batch_relation_from_history -v`。
- 未测风险：未执行真实生产历史 collision dry-run；service-level repair 能力仍保留，生产写入型 repair 仍需人工审批和 runbook。
- 后续事项：推进 `batch-accounting:module-closure-audit-and-production-evidence-defer`，审计 batch-accounting 是否只剩生产证据/长期外部环境风险。

## 2026-06-24 - Submit/withdraw route side-effect port 抽取

- 目标：把 `POST /api/batch-accounting/submit` 和 `POST /api/batch-accounting/{relation_id}/withdraw` 的 DTO/service/error mapping 与写后 scope/lifecycle/read model persist orchestration 从 `server.py` inline handler 抽到 `BatchAccountingApiRoutes`，让 `server.py` 只保留 mutation session、JSON body 和 response mapping。
- 影响范围：`backend/src/fin_ops_platform/app/routes_batch_accounting.py`、`server.py` 的 submit/withdraw wrapper、`tests/test_platform_runtime_boundary_guards.py` 的 batch-accounting route owner guard。
- 关键决策：`BatchAccountingService` 仍是 submit/withdraw 业务状态转换和 canonical command service 写入边界；`BatchAccountingApiRoutes` 只通过显式注入的 callback 调用 pair relation persist、derived lifecycle event、Workbench read model persist、submit rollback snapshot restore，不依赖 `Application` 或直接写 relation internals。
- 文档影响：新增 `.planning/refactors/modular-io-boundaries/analysis/batch-accounting-submit-withdraw-route-side-effect-port.md`；本模块状态机定义不变，只记录 route ownership 变化。
- 测试覆盖：静态 guard 现在要求 submit/withdraw `server.py` wrapper 委托 `BatchAccountingApiRoutes`，并要求 route owner 委托 `BatchAccountingService` 且不得 direct relation write；API 回归覆盖金额差异错误、合法提交、撤回原因、non-fresh withdraw 和 submit persist failure rollback。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_route_handlers_do_not_bypass_service_boundaries -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api.BatchAccountingApiTests.test_submit_amount_mismatch_requires_difference_note tests.test_batch_accounting_api.BatchAccountingApiTests.test_submit_amount_mismatch_rejects_whitespace_note tests.test_batch_accounting_api.BatchAccountingApiTests.test_submit_creates_batch_accounting_relation_with_current_invoice_rows tests.test_batch_accounting_api.BatchAccountingApiTests.test_withdraw_requires_reason_and_batch_accounting_relation -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api.BatchAccountingApiTests.test_submit_rolls_back_relation_when_pair_relation_persist_scheduling_fails -v`。
- 未测风险：真实 PostgreSQL/worker drain、真实大年份和浏览器 overlay flow 未在本 slice 重跑；本次不改变 API shape、worker contract 或前端代码，生产验证不是完成条件。
- 后续事项：继续推进 `batch-accounting:repair-compat-quarantine`，把 `_repair_batch_accounting_relation_case_ids` 的 owner、调用者、删除条件和防污染 guard 明确化。

## 2026-06-24 - GET route owner 抽取

- 目标：把 `GET /api/batch-accounting` 的 query normalization 和 list error mapping 从 `server.py` inline route body 抽到 `BatchAccountingApiRoutes`，让 `server.py` 只保留 route wrapper、依赖 wiring 和 JSON response mapping。
- 影响范围：`backend/src/fin_ops_platform/app/routes_batch_accounting.py`、`server.py` 的 GET wrapper、`tests/test_platform_runtime_boundary_guards.py` 的 route owner inventory 和 batch-accounting route boundary guard。
- 关键决策：本 slice 只关闭 GET read-only route owner 抽取；`BatchAccountingService.build_payload(..., use_sql_read_model=True)` 仍是 read contract owner；submit/withdraw mutation handler、repair compat path、read model freshness 语义、权限、API response shape 和前端行为不变。
- 文档影响：新增 `.planning/refactors/modular-io-boundaries/analysis/batch-accounting-get-route-owner-extraction.md`；本实施记录说明 batch-accounting 模块仍未整体关闭。
- 测试覆盖：静态 guard 覆盖 `routes_batch_accounting.py` 注册与 delegation；API 回归覆盖 SQL read model loader、GET 不执行 legacy repair、显式分页和 stale/missing read model status。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_route_handlers_do_not_bypass_service_boundaries -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api.BatchAccountingApiTests.test_unsubmitted_list_uses_sql_read_model_loader_when_available tests.test_batch_accounting_api.BatchAccountingApiTests.test_unsubmitted_list_does_not_run_legacy_relation_repair tests.test_batch_accounting_api.BatchAccountingApiTests.test_unsubmitted_list_explicit_pagination_protects_first_screen_slo tests.test_batch_accounting_api.BatchAccountingApiTests.test_unsubmitted_list_exposes_relation_read_model_missing_status -v`。
- 未测风险：本 slice 不连接生产 PostgreSQL、不 drain worker、不验证真实大年份性能；因为没有改变 SQL/queue/worker/read model 发布语义，生产验证不是完成条件。
- 后续事项：继续推进 `batch-accounting:submit-withdraw-route-side-effect-port`，把 mutation HTTP DTO/error mapping 与写后 lifecycle/read model barrier 从 `server.py` 收敛到明确边界。

## 2026-06-23 - Route handler 边界守卫

- 目标：防止 `/api/batch-accounting*` route 重新绕过 `BatchAccountingService`，在 GET 列表路径执行 legacy repair/write/read model schedule，或在 submit/withdraw route 里直接调用 relation write internals。
- 影响范围：`tests/test_platform_runtime_boundary_guards.py` 的静态边界守卫；不改变 `server.py` runtime、API shape、业务语义、read model、worker 或前端。
- 关键决策：route 只负责 HTTP/session/DTO/error mapping 和写后 lifecycle/read model scheduling；业务读写边界属于 `BatchAccountingService`，canonical relation 写入属于 `WorkbenchRelationCommandService`。`_repair_batch_accounting_relation_case_ids` 保留为显式 compat-only repair path，禁止回到 GET list path。
- 文档影响：同步本模块 tests、state-machine、本实施记录，并在 `.planning/refactors/modular-io-boundaries/analysis/batch-accounting-legacy-route-contract.md` 记录全局/模块状态机 definition unchanged。
- 测试覆盖：新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_batch_accounting_route_handlers_do_not_bypass_service_boundaries`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_route_handlers_do_not_bypass_service_boundaries -v`；本轮最终验证还会覆盖 batch accounting API/static guards、app check、docs check、diff/secret scan。
- 未测风险：本轮不连接生产 PostgreSQL，不执行真实 worker drain；因为没有 runtime 行为或 API/read model 发布变更，生产验证不作为本 slice 完成条件。
- 后续事项：推进 `server-py:route-owner-inventory`，继续 inventory 残留 route owner 和少量边界守卫。

## 2026-06-21 - 左侧流水时间展示格式修复

- 目标：修复“日常报销批量账务管理”左侧“批量账务流水”列表把 `2026-04-10T17:12:02+08:00` 这类 ISO 时区字符串直接展示给用户的问题，让时间 chip 和可访问名称统一显示为 `YYYY-MM-DD HH:mm:ss`。
- 影响范围：`BatchAccountingPage` 展示层 formatter、`BatchAccountingPage.test.tsx` 页面交互回归。
- 关键决策：只做 UI 展示归一化，不改 `GET /api/batch-accounting` DTO、不改后端事实源、不做时区换算，避免把生产已带本地时区的交易时间二次转换。
- GSD/UI 决策：采用 GSD fast 小步修复；左栏时间仍保留为 compact meta tag，宽度、颜色、列表布局和分页交互不变，只清理原始 ISO 分隔符和时区后缀，保证扫读稳定。
- 测试覆盖：组件测试把首条银行流水 mock 改成带 `T/+08:00` 的问题输入，并断言左栏显示正常时间、原始字符串不出现在可见 chip 中，按钮 accessible name 也使用正常时间。
- 文档影响：本轮不改变业务状态、API contract、read model/worker 或测试矩阵，只新增本实施记录。
- 未测风险：真实登录态浏览器截图和生产历史不同银行返回的非标准时间格式仍需手工 smoke；当前 formatter 对既有空值和普通 `YYYY-MM-DD HH:mm:ss` 保持原样。

## 2026-06-20 - GET 列表加载失败刷新恢复

- 目标：补齐批量账务首屏 `GET /api/batch-accounting` 暂时失败后的 Browser 恢复链路，防止 API 503 被页面误显示成普通“暂无流水”空态，或恢复后残留失败文案。
- 影响范围：`BatchAccountingPage` 错误态空态 guard、`web/e2e/fixtures/apiMocks.ts` 批量账务临时失败 mock、`web/e2e/batch-accounting-flow.spec.ts`、`web/src/test/BatchAccountingPage.test.tsx` 和本模块/全局测试文档。
- 关键决策：不改变批量账务业务逻辑、submit/withdraw 语义或 relation freshness 规则；刷新仍复用页面现有 `loadData`，错误态只阻止普通空态展示。
- 测试覆盖：组件测试覆盖首次 GET 503 显示“批量账务数据加载暂时失败，请刷新后重试。”且不显示普通空态，点击刷新后业务银行行恢复；Browser 测试覆盖真实 Chromium 中首屏 503、用户手动刷新直到 200/fresh、银行/OA 行恢复、提交按钮保持未选择时禁用、成功恢复后无可见错误残留和无隐藏浏览器错误。
- 未测风险：真实网络中断、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、生产历史批量账务 relation 和大年份性能仍需 staging/runtime smoke。

## 2026-06-19 - relation read model stale Browser 防 false-empty

- 目标：把批量账务 `workbench_relation` non-fresh 诊断从组件/API 覆盖补到真实 Chromium，防止页面把 stale relation read model 下的当前可用 rows 误显示成普通空态，或在只读诊断场景意外触发 submit/withdraw mutation。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/batch-accounting-flow.spec.ts`、本模块测试/覆盖文档和 read-models shared 覆盖文档。
- 关键决策：不改产品逻辑。保留既有语义：GET payload 透出 `read_model_status` / `read_model_stale_reasons` / `read_model_scope_keys` / `refresh_enqueued`；普通 read model non-fresh 不全局禁用具备 canonical write safety 的操作，mutation 是否允许仍由权限/session、canonical relation、idempotency、owner 状态和后端写安全决定。
- 测试覆盖：`batch-accounting-flow` 新增 `read_model_status=stale` Browser 用例，断言 warning/reason/scope 可见、银行/OA rows 保留、不显示 `当前年份暂无批量账务流水`、选择后 submit 按 canonical write safety 保持可用，且 submit/withdraw mutation 计数为 0。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、`docs/modules/read-models/e2e-coverage.md`、`docs/modules/read-models/tests.md` 和 `docs/dev/testing.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、生产历史 relation distribution 和真实大年份数据仍走 `infra-smoke` / staging 或生产批准 smoke，不写成本地 deterministic Browser covered。

## 2026-06-16 - P2/P3 前端首屏分页接入

- 目标：让批量账务页面实际消费后端显式分页 contract，避免未提交 bucket 首屏一次性拉取大年份范围全部银行/OA 候选。
- 影响范围：`BatchAccountingPage`、`web/src/features/batchAccounting/api.ts`、`web/src/features/batchAccounting/types.ts`、`web/src/app/styles.css`、`web/src/test/BatchAccountingPage.test.tsx` 和本模块文档。
- 关键决策：前端固定首屏页大小 200；未提交 bucket 分别发送 `bank_page/bank_page_size` 和 `oa_page/oa_page_size`，银行/OA 独立翻页；已提交 bucket 只分页银行关系列表，OA 明细来自当前可见 relation bucket。切换 bucket 或年份会重置页码和选择，避免旧页选择误提交。
- 文档影响：更新本模块 `README.md`、`tests.md`、`implementation-notes.md` 和 P2/P3 closure ledger；长期 API contract 仍兼容未传分页参数的旧调用方，本轮无需改长期接口文档。
- 测试覆盖：新增 `BatchAccountingPage.test.tsx::uses backend pagination for bank and OA first screens`，覆盖 205 行 synthetic bank/OA payload、首屏 200 行、第二页 5 行、不可见旧页行、请求参数包含 `bank_page_size=200` / `oa_page_size=200`；既有页面测试同步断言初始 GET 使用分页参数。
- 验证命令：`npm --prefix web test -- --run src/test/BatchAccountingPage.test.tsx -t "uses backend pagination"`；`npm --prefix web test -- --run src/test/BatchAccountingPage.test.tsx`。
- 未测风险：真实生产 PostgreSQL EXPLAIN、真实登录态浏览器渲染耗时、超长文本视觉回归和大 XLSX 下载仍属 P2/P3 staging/manual gate。

## 2026-06-16 - withdraw direct pair fallback 删除

- 目标：删除 `BatchAccountingService.withdraw` 在缺少 `WorkbenchRelationCommandService` 时回退到 `WorkbenchPairRelationService.withdraw_latest_for_row_ids(...)` 的兼容路径，确保批量账务撤回不会绕过统一 relation command boundary。
- 影响范围：`BatchAccountingService._withdraw_unlocked`、`tests/test_batch_accounting_api.py`、`tests/test_platform_runtime_boundary_guards.py` 和本模块测试矩阵。
- 关键决策：生产 `Application._batch_accounting_service()` 已注入 `WorkbenchRelationCommandService`；缺少 command service 代表 wiring 错误，应返回 `batch_accounting_relation_command_unavailable`，不能 direct pair mutation。
- 文档影响：本模块 `tests.md` 增加 withdraw command boundary 回归入口；长期 API/架构口径已要求 withdraw 走 command service，本轮无需改长期事实源。
- 测试覆盖：新增 `test_withdraw_requires_relation_command_service_without_direct_pair_fallback` 和 `test_batch_accounting_withdraw_has_no_direct_pair_write_fallback`；完整 batch accounting/backend relation boundary/frontend 回归通过。
- 验证命令：见 Phase 11 verification。
- 未测风险：真实 PostgreSQL 历史批量账务 relation 和真实 worker drain 仍需 staging 或发布前 smoke。

## 2026-06-14 - 撤回历史显示归属过滤

- 目标：批量账务撤回复用 Workbench relation history 时，不再把 OA 附件 case_id / `existing_case` 显示归属恢复成 active relation。
- 影响范围：`WorkbenchPairRelationService` 的可恢复 relation snapshot 边界、`BatchAccountingService.withdraw` 回归断言和本模块文档。
- 关键决策：读侧仍可按 case_id 展示 OA 与附件发票的归属关系；写侧撤回只恢复真实 active relation snapshot，display-only 归属不进入 relation repository。
- 测试覆盖：更新 `tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_withdraw_does_not_restore_display_only_oa_invoice_snapshot_as_active_relation`。
- 发布前审计：2026-06-14 已在生产执行只读 SQL 审计，`active_display_only_relation_count=0`、`display_only_history_before_relation_count=3`、`affected_history_case_count=3`；历史污染由运行时过滤覆盖，不需要 backfill。
- 未测风险：未执行生产写入型 repair；本次审计结论为无需写入型 backfill。


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 批量账务 Spec-first E2E 本地闭环状态为 `spec-first-covered`：`BATCH-E2E-001..009` 已映射到 Browser、组件、API、后端和 integration 覆盖；`BATCH-E2E-010` 真实基础设施 worker drain 明确保留为 staging/runtime risk。
- 批量账务不拥有独立 read model；列表和 mutation 前置判断依赖 `workbench_relation` read model freshness。
- `GET /api/batch-accounting` 必须保持只读，不能为了修复历史关系在 GET 路径写入。
- `read_model_status !== "fresh"` 时前端必须显示 warning，不能把空关系当作真实未提交；写操作是否可提交由后端 canonical write safety、权限/session、DB 和 owner/version/idempotency 判定，普通 relation distribution 追赶中不应作为长期全局禁用理由。
- 批量账务 submit relation 写入必须通过 `WorkbenchRelationCommandService.confirm_relation(...)`；缺少 command service 时 fail fast，不回退 direct `WorkbenchPairRelationService.replace_with_confirmed_relation(...)`。
- 提交/撤回成功后的前端 `workbenchRelationUpdated` 只是刷新提示，不替代后端 dirty scope、worker、operation barrier 和 readiness。页面会短等 `workbench_relation` barrier 并尝试重新加载；若后置同步等待或 reload 未及时完成，只能提示后台同步，不能把已成功的 command 改写成失败。
- 历史 case id collision 修复保留在 service 显式路径和 mutation/repair 语义中，不能重新散落到列表读取。
- `GET /api/batch-accounting` 支持可选显式分页。未传分页参数的旧调用方仍保持旧 response shape；批量账务前端未提交 bucket 默认带 `bank_page/bank_page_size` 和 `oa_page/oa_page_size`，后端裁剪对应列表并返回 `pagination`，`page_size>200` 返回 `invalid_paging`。

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

## 2026-06-19 - 成功写流可见错误残留 guard

- 目标：防止批量账务 submit/withdraw 已成功、bucket 也已刷新，但页面仍残留“操作失败/同步失败/read model 失败”等可见错误提示。
- 影响范围：`web/e2e/batch-accounting-flow.spec.ts`、`tests/test_playwright_e2e_strict_diagnostics.py`、本模块测试矩阵和全局测试文档。
- 关键决策：不改变产品逻辑或 deterministic mock；在提交成功、撤回成功和回到未提交 bucket 后复用 `expectNoUnexpectedSuccessUiErrors(...)` 做用户可见错误残留检查。
- 文档影响：更新本模块 `tests.md`、`e2e-coverage.md` 和全局 testing closure state。
- 测试覆盖：`web/e2e/batch-accounting-flow.spec.ts` 加强 submit/withdraw 成功路径；静态诊断防止后续移除该 guard。
- 验证命令：`cd web && npx playwright test e2e/batch-accounting-flow.spec.ts --project=chromium`；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`。
- 未测风险：真实生产批量账务写入仍需真实认证、业务审批和可回滚 scenario；本轮只覆盖 deterministic Browser flow 的可见错误残留。

## 2026-06-19 - Spec-first E2E covered 校准

- 目标：把批量账务从全局 Spec-first `partial` 校准为页面级 covered，明确本地自动化覆盖和真实基础设施风险边界。
- 影响范围：`docs/modules/batch-accounting/e2e-spec.md`、`docs/modules/batch-accounting/e2e-coverage.md`、`web/e2e/batch-accounting-flow.spec.ts`、本模块 README/tests/implementation notes 和全局 Spec-first inventory。
- 关键决策：
  - 新增 `BATCH-E2E-001..010`，覆盖页面 ready、首屏分页、提交、差额说明、撤回、non-fresh 诊断、command boundary、relation fan-out、权限、窄屏和真实 infra worker drain。
  - Browser 增量不改变业务流程，只为现有窄桌面和 submit/withdraw 流加入严格浏览器错误捕获，防止“操作成功但弹窗/console/request 失败”被漏掉。
  - 不把真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实大年份、高行数和下游最终显示写成本地 CI covered；这些继续由 `infra-smoke`、staging 或生产前 smoke 验证。
- 测试覆盖：更新 `web/e2e/batch-accounting-flow.spec.ts`。
- 验证命令：`cd web && npx playwright test e2e/batch-accounting-flow.spec.ts --project=chromium`。
- 未测风险：真实 worker drain、真实历史 legacy relation、真实大年份/长 OA 文本浏览器性能和下游页面最终显示仍需 staging/runtime smoke。

## 2026-06-16 - P2/P3 显式分页首屏保护

- 目标：补齐批量账务 P2/P3 大数据首屏本地证据，避免后续大年份范围把全部银行/OA 候选一次性返回给首屏。
- 影响范围：`BatchAccountingService.build_payload(...)`、`Application._handle_api_batch_accounting(...)`、`tests/test_batch_accounting_api.py`、本模块 README/tests 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 关键决策：分页只在请求显式带参数时生效，默认响应保持兼容；通用 `page/page_size` 同时作用于 bank/OA 列表，`bank_*` 和 `oa_*` 支持后续独立分页；submitted bucket 在 bank list 分页时只返回可见 bank row 的 relation payload，避免显式分页仍携带全量关系详情。
- 文档影响：更新本模块 `README.md`、`tests.md`、`implementation-notes.md` 和 P2/P3 closure ledger。
- 测试覆盖：新增 `BatchAccountingApiTests.test_unsubmitted_list_explicit_pagination_protects_first_screen_slo`，用 250 行 synthetic bank/OA 候选验证 200 行上限、第二页、summary total 保留和 `invalid_paging`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api.BatchAccountingApiTests.test_unsubmitted_list_explicit_pagination_protects_first_screen_slo -v`。
- 未测风险：前端默认请求尚未传分页参数，真实浏览器长表格、独立 bank/OA 分页交互和生产 PostgreSQL EXPLAIN 仍需后续 smoke 或 UI 改造。

## 2026-06-16 - relation non-fresh 与 canonical write safety 证据收敛

- 目标：收敛 P2/P3 中“relation non-fresh 与 canonical write safety 文案/旧测试命名未统一”的缺口，确认批量账务不再把普通 relation distribution non-fresh 当作默认写阻断条件。
- 影响范围：本模块测试矩阵、`workbench-relations` 测试矩阵、`.planning/P2P3-CLOSURE-PLAN.md`；不改变业务代码。
- 关键决策：保留当前语义：GET/read facade 负责透出 `workbench_relation` freshness 诊断和入队刷新；submit/withdraw 写安全由 `WorkbenchRelationCommandService`、canonical relation、idempotency、owner 状态、权限/session、DB 可写性决定。只有显式 freshness precondition 才让 non-fresh 阻断 mutation。
- 文档影响：本次只做 P2/P3 closure ledger 和测试入口表述收敛，不改变 API 或长期架构口径。
- 测试覆盖：复用现有 `test_unsubmitted_list_exposes_relation_read_model_missing_status`、`test_submitted_list_exposes_relation_read_model_stale_status`、`test_submit_delegates_relation_write_to_command_service`、`test_submit_requires_relation_command_service_without_direct_pair_fallback`、`test_withdraw_delegates_relation_write_to_command_service`、`test_withdraw_requires_relation_command_service_without_direct_pair_fallback` 以及 runtime boundary guard。
- 验证命令：见 `.planning/P2P3-CLOSURE-PLAN.md` 的 P2P3-018 verification commands。
- 未测风险：真实 worker drain、生产历史半迁移和下游页面最终显示仍需 staging/production smoke；本项只收敛本地语义与测试入口。
- 后续事项：如果未来 mutation API 显式启用 freshness precondition，必须新增带 `read_model_status` / `read_model_stale_reasons` / `refresh_enqueued` 的 API contract 测试。

## 2026-06-14 - submit/withdraw 操作后 freshness barrier

- 目标：批量账务提交/撤回后隐藏短暂 read model 收敛时间，避免用户在 relation distribution 未 fresh 时看到旧 bucket 或继续重复操作。
- 影响范围：`BatchAccountingPage` submit/withdraw、`GlobalOperationOverlayProvider`、`operationBarrier` API client。
- 关键决策：写 API 成功不是页面可继续操作的完成点；前端等待 `workbench_relation` barrier 对 affected months fresh，再 reload 当前 payload 并关闭 overlay。前端事件仍只作为刷新提示，不是同步事实。
- 文档影响：更新本模块 `README.md`、`tests.md`、`implementation-notes.md`。
- 测试覆盖：更新 `web/src/test/BatchAccountingPage.test.tsx`，并由 `GlobalOperationOverlayContext.test.tsx`、`OperationBarrierApi.test.ts` 覆盖共享 overlay/barrier 行为。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产登录态 operation-to-fresh latency 需要发布后度量。

## 2026-06-12 - legacy repair relation command fallback 删除

- 目标：删除 `BatchAccountingService.repair_legacy_case_id_collisions` 直接调用 `WorkbenchPairRelationService.create_active_relation/record_history` 的历史修复写入口。
- 影响范围：`BatchAccountingService.repair_legacy_case_id_collisions`、`tests/test_batch_accounting_api.py`、`tests/test_platform_runtime_boundary_guards.py` 和本模块文档。
- 关键决策：repair 仅在确实需要恢复 relation 时要求 `WorkbenchRelationCommandService`；缺 command service 代表 wiring 错误，应返回 `batch_accounting_relation_command_unavailable`。恢复 relation 使用 `confirm_relation(..., history_operation_type="repair_batch_accounting_relation_id_collision")`，保留 legacy case id、repair source、repaired_at 和 amount metadata。
- 文档影响：更新 `README.md`、`tests.md`、`implementation-notes.md`，并同步 `workbench-relations` 模块。
- 测试覆盖：新增 `test_repair_legacy_case_id_collision_delegates_relation_write_to_command_service`、`test_repair_legacy_case_id_collision_requires_relation_command_service_without_direct_pair_fallback` 和 `test_batch_accounting_repair_has_no_direct_pair_write_fallback`；完整 batch accounting API/service 回归通过。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py -q`。
- 未测风险：真实 PostgreSQL 历史数据中 legacy relation / 半迁移 / 重复 case id 的全量回放仍需 staging 或生产前 dry-run。
- 后续事项：继续收口 no-OA legacy repair/consolidation。

## 2026-06-12 - submit relation command fallback 删除

- 目标：删除 `BatchAccountingService.submit` 在缺少 relation command service 时的 direct pair relation fallback，避免批量账务提交绕过统一 relation 事实源。
- 影响范围：`BatchAccountingService._submit_unlocked`、`tests/test_batch_accounting_api.py`、`tests/test_platform_runtime_boundary_guards.py` 和本模块文档。
- 关键决策：生产 `Application._batch_accounting_service()` 已注入 `WorkbenchRelationCommandService`；缺少 command service 代表 wiring 错误，应返回 `batch_accounting_relation_command_unavailable`，不能调用 `replace_with_confirmed_relation(...)`。legacy collision repair 后续已在同日迁移到 command service。
- 文档影响：更新 `README.md`、`tests.md`、`implementation-notes.md`，并同步 `workbench-relations` 模块。
- 测试覆盖：新增 `test_submit_requires_relation_command_service_without_direct_pair_fallback`；新增 runtime boundary guard 防止 `_submit_unlocked` 重新出现 direct pair write fallback。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_submit_delegates_relation_write_to_command_service tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_submit_requires_relation_command_service_without_direct_pair_fallback tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_submit_amount_mismatch_with_note_persists_relation_and_history -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_batch_accounting_submit_has_no_direct_pair_write_fallback -q`。
- 未测风险：本阶段不迁移 `repair_legacy_case_id_collisions`；该路径后续已在同日迁移到 command service。
- 后续事项：继续收口 no-OA legacy repair/consolidation。

## 2026-06-11 - relation read model missing/stale 闭环

- 目标：修复批量账务页面出现 `关联台关系读模型 missing/read_model_missing` 时只能提示刷新、但列表读取和 mutation fresh gate 没有形成完整闭环的问题。
- 影响范围：`BatchAccountingService` relation facade 调用、`GET /api/batch-accounting` freshness payload、submit/withdraw 错误合同、`BatchAccountingPage` non-fresh warning 和 feedback。
- 关键决策：GET 列表保持只读，但所有 relation distribution 读取都通过现有 `WorkbenchRelationReadFacade` 的 `require_fresh` 边界入队刷新；当时 submit/withdraw 仍要求 relation read model fresh，该写前 gate 已由 2026-07-02 canonical write safety 修复删除；前端只展示后端 status/reason/scope，不把 domain event 当事实源。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md` 和 `docs/dev/api-contracts.md`。
- 测试覆盖：新增/更新后端 API/service 测试覆盖 missing/stale 入队、submit/withdraw fresh gate；新增前端交互测试覆盖刷新未入队提示和 mutation non-fresh reason/scope feedback。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api tests.test_workbench_relation_read_facade -v`
  - `cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx -t "relation read model refresh is not enqueued|mutation is rejected as non-fresh"`
- 未测风险：真实 PostgreSQL/RabbitMQ/systemd worker drain 和生产历史 dirty scope 收敛仍需 staging 或发布前 smoke；单元测试验证的是 facade/gateway 调用合同和页面行为。
- 后续事项：最终合入前继续运行模块全量后端、前端和 docs verify。

## 2026-06-11 - 首轮测试闭环文档化

- 目标：用 CodeGraph 审计批量账务页面、API、service、relation read model、worker/App Status 和测试入口，补齐模块文档闭环。
- 影响范围：`BatchAccountingPage`、`batchAccounting/api.ts`、`BatchAccountingService`、`WorkbenchRelationReadFacade`、`WorkbenchRelationSqlProjectionBuilder`、`workbench-relation` worker、App Status domain/job 映射、domain event。
- 关键决策：批量账务 mutation 必须依赖 fresh relation read model；GET 保持只读；前端事件不作为事实源；历史 collision repair 通过显式 service 回归保护。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`，并在全局测试闭环依赖地图中补充 batch-accounting 细化。
- 测试覆盖：后端 `tests/test_batch_accounting_api.py` 覆盖业务/API/service 回归；relation facade/projection/registry/App Status/lifecycle tests 覆盖 read model 和 worker；前端 `BatchAccountingPage.test.tsx` 覆盖页面交互和 stale 禁用。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api tests.test_workbench_relation_read_facade tests.test_workbench_relation_sql_projection tests.test_runtime_worker_registry tests.test_app_status_overview_service tests.test_derived_data_lifecycle_service -v`
  - `cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx src/test/domainEvents.test.ts src/test/useActiveFinanceDomainEvent.test.tsx`
  - `bash scripts/verify.sh docs`
- 未测风险：真实生产 PostgreSQL 历史批量账务关系、真实 RabbitMQ/Redis/systemd `workbench-relation` worker drain、大数据浏览器性能和下游页面最终展示仍需 staging/发布前 smoke。
- 后续事项：后续改动若触及 relation freshness、DTO shape、提交/撤回规则或 Workbench relation fan-out，必须先按 `tests.md` 选择窄范围回归，再升级到跨模块验证。

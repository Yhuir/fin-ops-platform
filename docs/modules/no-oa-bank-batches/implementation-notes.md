# 免OA流水批量处理 实施记录

> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 免 OA 流水批量处理首轮测试闭环状态为 `documented-risk`：已有测试覆盖 business core、application/service、API contract、read model/worker、前端交互、Workbench integration 和旧功能回归。
- 本模块是 Bankdetail 高风险子域。后续不要把 no-OA 机械拆成脱离 Bankdetail 的独立事实源。
- `GET /api/no-oa-bank-batches` 和 detail 读路径不得在 missing/stale 时同步重建全量批次；必须返回 read model status 并 enqueue refresh。
- PostgreSQL list 读路径允许返回 fresh empty rows，但必须由 `job.read_model_dirty_scopes` 无 active blocker 且 `read_model.app_status_readiness` 记录为 fresh 共同证明；不能把无 rows 直接当 fresh。
- no-OA read model 支持 `all` 和月份 scope；月份 refresh 只读目标月银行流水，只替换目标月批次，合并保留其它月份 snapshot。
- Bankdetail/effective category 依赖未 fresh 时属于依赖等待，应保持 no-OA readiness 为 `refreshing` 并由 runtime worker defer/retry，不能记录为 `failed` blocker。
- Workbench confirm-link 的 internal transfer 特例必须最终写 no-OA submitted batch 和 `relation_mode=no_oa_bank_batch`，不得绕过批次写普通 `manual_confirmed`。
- no-OA legacy migration、submitted repair、category drift cleanup 和 submitted single-side consolidation 必须通过 `WorkbenchRelationCommandService` 写 relation；缺 command service 时 fail fast，不回退 direct pair mutation。
- no-OA submit/withdraw 的长期目标是 facts/audit/dirty/outbox 同事务；当前目标契约由 `tests/test_bankdetail_write_uow_contract.py` 保护，真实收敛前保持 `documented-risk`。
- `GET /api/no-oa-bank-batches` 支持可选显式分页 `page/page_size` 或 `pageSize`；只有请求带分页参数时才裁剪 `batches` 并返回 `pagination`，旧调用方不带分页参数时保持原 shape。no-OA 前端默认以 `page=1&page_size=200` 读取列表并渲染分页控件；切换月份、状态 bucket 或页码时必须清空选择、详情缓存和详情错误。`page_size` 上限为 200，超限必须 fail closed 为 `invalid_paging`。
- 前端 stale polling、route unmount cleanup、category/rules events 刷新 list/detail/tag drawer 都是页面行为契约。submit-selection、submit、withdraw、tag-selection 保存等写操作必须用全屏 operation overlay 等待 `no_oa_bank_batch` barrier fresh 后再释放。
- relation-backed 的旧 `stale/category drift` 只作为内部兼容状态。只要 SQL read model payload 仍属于 submitted bucket 或可撤回，API/前端必须按 `submitted` 呈现、保留撤回入口，并清除复核类 blocked reason；页面不得显示“分类已变更，需复核”。

## 2026-06-17 - relation-backed stale 可见状态收敛

- 目标：修复免 OA 流水批量处理页面在已提交 bucket 中显示“分类已变更，需复核”的误导状态；已提交批次按已提交展示并可撤回，未提交 draft 继续按未提交提交。
- 影响范围：`NoOaBankBatchApplicationService.summary/resolve_labels(...)`、`web/src/features/noOaBankBatches/api.ts`、`web/src/pages/NoOaBankBatchPage.tsx`、no-OA application/API/page tests。
- 关键决策：
  - 不改 persisted batch fact，不新增 relation 写路径；只在 API 出口和前端 DTO mapper 做用户可见投影。
  - `status=stale` 且 `status_bucket=submitted` 或 `can_withdraw=true` 时，对页面投影为 `status=submitted,status_bucket=submitted,can_withdraw=true,can_submit=false`，并清空复核类 blocked reason。
  - 真实 `conflict` 仍显示阻断提示且不可提交；这次不把 conflict 伪装成未提交。
  - 关联台 paired/open 闭环沿用既有 integration tests：提交后进入 paired，撤回后回到 open/unmatched。
- 测试覆盖：
  - `NoOaBankBatchApplicationServiceTests.test_sql_read_model_relation_backed_stale_batch_is_presented_as_submitted`
  - `web/src/test/NoOaBankBatchApi.test.ts::maps relation-backed stale batches as submitted`
  - `web/src/test/NoOaBankBatchPage.test.tsx::presents relation-backed stale batches as submitted without review prompts`
  - `NoOaBankBatchWorkbenchIntegrationTests.test_no_oa_salary_batch_relation_pairs_then_cancel_returns_to_open`
  - `NoOaBankBatchWorkbenchIntegrationTests.test_no_oa_internal_transfer_relation_groups_bank_rows_until_cancelled`
- 七类测试覆盖：
  - Business core unit tests：本轮未改 no-OA 批次状态转换或 relation command payload。
  - Service-layer tests：适用，覆盖 SQL read model stale/submitted projection 与 summary 计数。
  - API contract tests：适用，前端 API mapper 覆盖旧 payload 兼容；HTTP route shape 未变。
  - Read model/cache/background job tests：本轮未改 worker/dirty scope；既有 stale SQL source version 和 Workbench integration 保护。
  - Frontend component and interaction tests：适用，覆盖不显示复核提示、显示已提交和撤回按钮。
  - End-to-end business-flow integration tests：适用，复用 no-OA submit -> Workbench paired、withdraw -> open 的后端 integration。
  - Existing feature regression tests：适用，保留 conflict 阻断、read-only 门禁、operation overlay、分页和旧 API mapper 回归。
- 未测风险：真实生产历史中无 active relation 的旧 stale 行如何清理仍需数据巡检；真实 worker drain 和大数据月份仍按既有 staging/生产 smoke 覆盖。

## 2026-06-17 - read-only 写入口权限门禁

- 目标：把免 OA 页提交、撤回、tag scope 保存和批量选择接入 session `can_mutate_data`，避免 read_export_only 用户在浏览器层看到或触发写操作。
- 影响范围：`web/src/pages/NoOaBankBatchPage.tsx`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/e2e/permissions-role-matrix.spec.ts`。
- 关键决策：不改变 no-OA API contract；后端权限仍是安全边界，前端只做可见行为门禁。只读用户仍可查看批次、明细和标签范围。
- 文档影响：更新本模块 `tests.md`、`state-machine.md`，并由 `docs/modules/permissions-and-audit/` 记录全局权限矩阵事实。
- 测试覆盖：新增 read-export unit regression；Playwright role matrix 覆盖 no-OA read-only 提交/撤回/tag scope 保存禁用。
- 验证命令：`cd web && npm test -- --run src/test/NoOaBankBatchPage.test.tsx`；`cd web && npx playwright test e2e/permissions-role-matrix.spec.ts`。
- 未测风险：真实生产长标签树、大月份和长列表滚动/视觉遮挡仍需 staging/生产登录态 smoke。

## 2026-06-17 - Browser e2e 选择提交到撤回闭环

- 目标：补齐免 OA 流水批量处理的真实浏览器主路径，防止后续页面维护时破坏选择未提交流水、提交、等待 read model fresh、进入已提交、撤回和历史只读。
- 影响范围：`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块测试矩阵与全局测试闭环文档。
- 关键决策：
  - 使用 deterministic API mocks 固定一个 `fee` 手续费批次，状态从 `draft` -> `submitted` -> `withdrawn` 随浏览器操作流转。
  - e2e 断言用户可见 UI 合约和 HTTP mutation request body，不断言页面没有渲染的 submitted/withdrawn actor 字段。
  - 写操作成功后必须经过 `/api/operation-barrier/status`，再进入后续 bucket 验证，避免只测 API 成功不测 freshness closure。
- 测试覆盖：
  - `web/e2e/no-oa-bank-batches-flow.spec.ts`
  - `cd web && npm run e2e:smoke`
- 七类测试覆盖：
  - Business core unit tests：本轮未改业务状态机，由既有 service tests 保护。
  - Service-layer tests：本轮未改 service 写边界，由既有 application/UoW tests 保护。
  - API contract tests：本轮未改后端 contract；e2e 额外断言 `submit-selection` 和 `withdraw` 请求体。
  - Read model/cache/background job tests：适用前端 freshness closure，e2e 断言 operation barrier 被调用；真实 worker drain 仍属未测风险。
  - Frontend component and interaction tests：适用并新增真实 Chromium 页面选择、bucket、dialog、toast 和只读状态。
  - End-to-end business-flow integration tests：适用并新增 selected-row submit -> barrier -> withdraw -> history browser flow。
  - Existing feature regression tests：适用并防止按钮、bucket 数量、请求体和 freshness barrier 回归。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd no-oa-bank-batch worker drain、大数据长列表、网络恢复和生产历史半迁移仍需 staging/生产 smoke。

## 2026-06-16 - P2/P3 显式分页首屏保护

- 目标：为免 OA list 建立可执行首屏上限，避免后续大数据月份把全部批次一次性返回给首屏。
- 影响范围：`NoOaBankBatchApplicationService.list_batches_payload(...)`、`NoOaBankBatchApiRoutes.list_batches(...)`、`web/src/features/noOaBankBatches/api.ts`、`web/src/pages/NoOaBankBatchPage.tsx`、no-OA route/service/API/page tests。
- 关键决策：
  - 显式请求 `page/page_size` 或 `pageSize` 时，list 只返回当前页 `batches`，但 `summary` 仍基于完整过滤结果，`pagination.total` 返回完整命中数。
  - 不带分页参数时保持旧 response shape，避免破坏旧调用方和既有测试。
  - 前端默认发送 `page=1&page_size=200`，用后端 `pagination` 渲染上一页/下一页控件；月份、状态 bucket 或页码变化会清空当前选择、详情缓存和详情错误，避免旧页状态污染新页操作。
  - `page_size>200`、非正数或非法整数统一返回 `invalid_paging`，route facade 映射为结构化 400。
- 测试覆盖：
  - `NoOaBankBatchApplicationServiceTests.test_list_batches_explicit_pagination_protects_first_screen_slo`
  - `NoOaBankBatchRoutesTests.test_list_batches_invalid_paging_returns_structured_400`
  - `web/src/test/NoOaBankBatchApi.test.ts`
  - `web/src/test/NoOaBankBatchPage.test.tsx::uses backend pagination for no OA first-screen batches`
- 七类测试覆盖：
  - Business core unit tests：本轮未改 no-OA 批次生成业务规则。
  - Service-layer tests：适用，覆盖 250-row synthetic list、`page_size=200`、第二页和超限 fail closed。
  - API contract tests：适用，覆盖 `invalid_paging` 结构化 400。
  - Read model/cache/background job tests：本轮未改 freshness、dirty scope 或 worker。
  - Frontend component and interaction tests：适用，覆盖 API client 参数/响应映射、首屏 200-row 分页、下一页重载、旧页批次不残留和分页控件 CSS contract。
  - End-to-end business-flow integration tests：本轮未改跨页写流程。
  - Existing feature regression tests：适用，通过 no-OA application/routes/API/page 全量目标测试保护既有 list/submit/withdraw contract。
- 未测风险：真实 PostgreSQL 大数据 EXPLAIN、真实浏览器长列表滚动/视觉遮挡和生产登录态 API p95 仍需 staging/生产 smoke。

## 2026-06-14 - 写操作后 freshness barrier

- 目标：免 OA 批次提交、撤回和标签保存后隐藏 read model 收敛窗口，避免页面提前显示旧批次、旧候选或允许重复提交。
- 影响范围：`NoOaBankBatchPage` 写操作、`GlobalOperationOverlayProvider`、`operationBarrier` API client。
- 关键决策：写 API 成功后等待 `no_oa_bank_batch` barrier 对 affected months/current scope fresh，再重新加载 list/detail/tag selection。前端 domain event 仍只做刷新提示，不作为同步完成证据。
- 文档影响：更新本模块 `README.md`、`tests.md`、`implementation-notes.md`。
- 测试覆盖：更新 `web/src/test/NoOaBankBatchPage.test.tsx`，并由 `GlobalOperationOverlayContext.test.tsx`、`OperationBarrierApi.test.ts` 覆盖共享 overlay/barrier 行为。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产登录态 operation-to-fresh latency 需要发布后度量。

## 2026-06-11 - 首轮测试闭环审计

- 目标：把 `no-oa-bank-batches` 从测试闭环 `pending` 推进到可维护的 `documented-risk` 状态。
- 影响范围：免 OA 页面、tag-selection、list/detail、submit-selection、batch submit、bulk submit、withdraw、internal transfer from Workbench、no-OA read model、no-oa-bank-batch worker、App Status、Bankdetail tag/rule events。
- CodeGraph 审计：
  - `NoOaBankBatchPage` 调用 `fetchNoOaBankBatches`、`fetchNoOaBankBatchDetail`、`fetchNoOaBankBatchTagSelection`、`saveNoOaBankBatchTagSelection`、`submitNoOaBankBatchSelection`、`submitNoOaBankBatch`、`withdrawNoOaBankBatch`，并在 read model 非 fresh 时后台轮询。
  - `NoOaBankBatchApiRoutes` 是 HTTP route facade，负责 payload/session 映射和 error status；业务落在 `NoOaBankBatchApplicationService`。
  - `NoOaBankBatchApplicationService` 覆盖 list read model fallback、tag selection、submit/withdraw、after_mutation、durable queue enqueue 和 Workbench 影响。
  - `NoOaBankBatchService` 覆盖 draft/submitted/withdrawn/stale/conflict、internal transfer、legacy relation migration、pair relation metadata 和 snapshot/audit。
  - `NoOaBankBatchReadModelRefreshService` 只处理 `no_oa_bank_batch.read_model.refresh`，stale source version event 会 skip。
  - worker registry 和 App Status registry 已登记 `no-oa-bank-batch` worker、`no_oa_bank_batch` read model 和 `no_oa_bank_batch.read_model.refresh` event。
- 关键测试覆盖：
  - Business core：`tests/test_no_oa_bank_batch_service.py`。
  - Application/service：`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_bankdetail_write_uow_contract.py`。
  - API/route：`tests/test_no_oa_bank_batch_api.py`、`tests/test_no_oa_bank_batch_routes.py`、`tests/test_no_oa_bank_batch_tag_selection_api.py`。
  - Read model/worker：`tests/test_no_oa_bank_batch_workbench_integration.py`、`tests/test_no_oa_bank_batch_read_model_refresh.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`。
  - Frontend：`web/src/test/NoOaBankBatchApi.test.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、domain event tests。
  - Integration/regression：`tests/test_no_oa_bank_batch_workbench_integration.py` 覆盖 Workbench internal transfer、manual relation 分流、mixed conflict、submitted/withdraw/open 恢复。
- 文档影响：
  - 补齐 `README.md` 模块边界和代码入口。
  - 将 `tests.md` 迁入测试闭环标准结构。
  - 补齐 `state-machine.md`。
- 未测风险：
  - 真实 PostgreSQL 历史 no-OA 批次、legacy relation、半迁移状态和重复 relation 的全量回放。
  - 真实 RabbitMQ/Redis/systemd worker drain 和网络抖动恢复。
  - 大数据月份、长标签树、长银行流水列表的浏览器性能和视觉遮挡。
  - Bankdetail/no-OA 写 UoW 真实事务内收敛尚未完全由本地 fixture 证明。
- 后续事项：
  - 修改 submit/withdraw 前，优先补 service/UoW/API characterization test。
  - 修改 read model freshness 前，必须运行 no-OA read model integration 和 worker refresh tests。
  - 修改前端 stale polling、route activation 或 domain event 时，必须运行 no-OA page tests 和 `useActiveFinanceDomainEvent` tests。

## 2026-06-11 - 内部往来双入口闭环

- 目标：修复同一组内部往来在免 OA 页面和关联台两个入口之间可能出现重复 active relation、旧未提交/冲突批次残留、历史 `manual_confirmed` 占用后不进入免 OA 已提交区域的问题。
- 决策：
  - 关联台仍允许作为内部往来提交入口，但成功事实必须委托并收敛到 no-OA submitted batch。
  - 如果免 OA 页面已经提交同一组 `row_ids`，关联台再次 confirm-link 复用 existing submitted batch 和同一个 `case_id`，保持幂等。
  - 存量两行、全银行流水、同金额、不同账户、收支成对且有效分类均为 `internal_transfer` 的 `manual_confirmed` active relation，刷新时迁移为 submitted no-OA internal transfer batch。
  - Workbench pair relation service 增加 active row 独占保护，不同 active case 不能共享同一 row。
  - PostgreSQL no-OA snapshot 保存必须删除新 snapshot 中缺席的旧 batch row，防止 SQL read model 继续返回旧 unsubmitted/conflict。
- 验收测试：
  - `test_manual_confirmed_internal_transfer_relation_migrates_to_submitted_no_oa_batch`
  - `test_workbench_confirm_after_no_oa_submit_reuses_existing_internal_transfer_fact`
  - `test_create_active_relation_rejects_active_row_reuse_by_different_case_id`
  - `test_save_no_oa_bank_batches_replaces_absent_read_model_rows`

## 2026-06-12 - Relation command service 写入口收敛

- 目标：把 no-OA submit、submit-selection、Workbench internal transfer submit 和 withdraw 的 relation 写入收敛到 `WorkbenchRelationCommandService`，避免 no-OA 页面和 Workbench 形成独立事实源。
- 决策：
  - `NoOaBankBatchService` 保留为批次领域状态机，只产出 `relation_command_payload_for_batch(...)`，不再直接调用 `create_active_relation` 或 `cancel_relation`。
  - `NoOaBankBatchApplicationService` 负责调用 relation command service，并在失败时回滚 no-OA batch snapshot 与 relation snapshot。
  - relation 占用和写入使用 canonical relation command/write safety；`submit_selected_rows` 不再读取 pair service list。
  - relation distribution/read model non-fresh 不阻断 batch submit；提交后继续刷新 no-OA、Workbench 和 downstream read model。
  - no-OA legacy migration、submitted repair、category drift cleanup 后续已在 Phase 7L 迁入 relation command service。
- 验收测试：
  - `test_submit_batch_delegates_relation_write_to_command_service`
  - `test_withdraw_batch_delegates_relation_cancel_to_command_service`
  - `test_internal_transfer_from_workbench_delegates_relation_write_to_command_service`
  - `test_submit_batch_marks_submitted_and_exposes_relation_command_payload_idempotently`
  - `test_submit_uses_canonical_relation_when_relation_read_model_is_not_fresh`
  - `test_no_oa_salary_batch_relation_pairs_then_cancel_returns_to_open`
  - `test_no_oa_internal_transfer_relation_groups_bank_rows_until_cancelled`

## 2026-06-12 - Read model refresh 不再隐式修复 relation

- 目标：把 `no_oa_bank_batch.read_model.refresh` 从 relation 写入口中剥离，避免 worker 在重建 no-OA projection 时顺手创建/取消 pair relation，形成隐藏事实源写入。
- 决策：
  - `NoOaBankBatchService.build_batches(...)` 增加 `apply_relation_repairs` 参数；默认保持 legacy 兼容行为。
  - `NoOaBankBatchApplicationService.refresh_batches(...)` 暴露同名参数，并且只有启用 repair 时才根据 `last_legacy_migration_result` 触发 relation/workbench persist。
  - `NoOaBankBatchReadModelRefreshService` 固定调用 `refresh_batches(apply_relation_repairs=False)`；worker 只保存 no-OA snapshot，不保存 pair relation，不执行 legacy migration/repair/consolidation。
  - legacy migration、submitted repair、category drift cleanup 仍是待迁移兼容路径，后续应收敛为显式 repair command/离线 repair 工具。
- 验收测试：
  - `test_refresh_does_not_repair_workbench_relations_from_read_model_path`
  - `test_no_oa_read_model_refresh_does_not_run_relation_repairs`

## 2026-06-12 - Legacy relation repair 写入口收敛

- 目标：把 no-OA legacy relation migration、submitted relation repair、category drift cleanup 和 submitted single-side consolidation 从 direct pair service mutation 收敛到 `WorkbenchRelationCommandService`。
- 决策：
  - `NoOaLegacyRelationMigrationService` 通过 command service cancel legacy relation，再 confirm `relation_mode=no_oa_bank_batch`；缺 command service 时抛 `no_oa_relation_command_unavailable`。
  - `NoOaBankBatchService` 的 legacy/repair/consolidation 路径通过 `_confirm_no_oa_relation(...)` / `_cancel_no_oa_relation(...)` 委托 command service，不再调用 `_pair_relation_service.create_active_relation/cancel_relation/record_history`。
  - `Application` 为 no-OA batch service 注入 `WorkbenchRelationCommandService(require_fresh_relations=False)`，使显式 repair 路径复用统一 command/history/snapshot 边界，同时避免 read model worker 隐式 repair。
  - 已有 current submitted no-OA batch 与 legacy active relation 命中同一 row set 时，迁移复用 existing submitted batch 的 `relation_case_id`，避免新建 legacy batch case 后与旧 submitted batch 形成两个 active relation。
  - submitted repair 遇到 row 已被非 no-OA active relation 占用时跳过重建 no-OA relation，保留 active row 独占事实，并在 migration result 的 `skipped` 中记录 blocking case。
- 验收测试：
  - `test_submitted_internal_transfer_with_active_non_no_oa_relation_does_not_duplicate_as_unsubmitted_conflict`
  - `test_legacy_salary_relation_migrates_to_submitted_no_oa_batch_idempotently`
  - `test_existing_submitted_single_row_salary_batches_consolidate_by_month_and_account`
  - `test_consolidated_submitted_salary_batch_repairs_stale_single_row_relations`
  - `test_submitted_single_side_batch_prunes_rows_that_no_longer_match_category`
  - `test_submitted_batch_that_becomes_stale_clears_active_relation`
  - `test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback`
- 验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_service.py tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback -q
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_service.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_workbench_integration.py -q
```

- 七类测试覆盖：
  - Business core unit tests：适用并覆盖 legacy migration、submitted repair、category drift、single-side consolidation、active row occupation 和同 row set case reuse。
  - Service-layer tests：适用并覆盖 no-OA service 到 relation command service 的委托、缺 command fail-fast 和 read model worker 不隐式 repair。
  - API contract tests：本阶段未改 HTTP response shape；通过 no-OA API 回归保护旧 contract。
  - Read model/cache/background job tests：适用并继续覆盖 worker refresh 不写 relation。
  - Frontend component and interaction tests：本阶段未改前端，未新增。
  - End-to-end business-flow integration tests：适用并通过 no-OA workbench integration 回归保护 no-OA/Workbench 同一 relation fact。
  - Existing feature regression tests：适用并保留 legacy salary/internal transfer、stale/category drift、snapshot round-trip 和 API 回归。
- 剩余风险：
  - 真实 PostgreSQL 历史数据的全量回放和 repair dry-run 仍需 staging/生产前 smoke。
  - relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
  - 前端跨页面即时反馈仍需完整浏览器 smoke；domain event 仍只是刷新提示，不是事实源。

## 2026-06-13 - fresh empty rows readiness 证明

- 目标：修复当前月份没有免 OA 候选时 API 持续返回 missing/refresh_enqueued，导致页面一直“同步中”或 authenticated HTTP SLO freshness gate 失败。
- 影响范围：`PostgresReadModelRepository.list_no_oa_bank_batch_rows(...)`、no-OA list API 读取语义、HTTP SLO 默认 no-OA 探针。
- 关键决策：list 查询无 rows 时，只有 dirty scope 已 fresh 且 `read_model.app_status_readiness` 对 `no_oa_bank_batch/all` 为 fresh，才返回 `[]`；否则保持 `None`，让上层继续返回 refreshing 并入队真实刷新。
- 文档影响：更新本实施记录和测试矩阵。
- 测试覆盖：`tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests::test_no_oa_repository_returns_fresh_empty_rows_when_readiness_is_fresh`、`test_no_oa_repository_keeps_missing_when_readiness_is_absent_or_refreshing`。
- 验证命令：见最终交付说明。
- 未测风险：需要发布后用真实生产 readiness 行验证当前月份 empty state 不再被误判为 missing。
- 后续事项：若后续把 no-OA scope 从 `all` 拆到月份维度，必须同步更新 readiness 证明条件和测试。

## 2026-06-14 - no-OA 月度刷新和 Bankdetail 依赖状态闭环

- 目标：修复生产 App Status 中 Bankdetail 已同步但免 OA 批次长期 failed/blocker 的链路，避免 no-OA worker 因依赖 read model 暂未 fresh 被误标失败，并把刷新范围从全量收敛到月份。
- 根因：
  - `NoOaBankBatchReadModelRefreshService` 没有把 runtime event 的 `scope_key` 传给 application service，月份 dirty scope 实际读取 `all`。
  - `NoOaBankBatchApplicationService.refresh_batches(...)` 对同一批 rows 重复读取 Bankdetail effective categories，放大依赖读取和刷新时延。
  - `NoOaBankBatchService.build_batches(...)` 原本按完整 snapshot 替换；如果直接传入月度 rows，会误删其它月份批次。
  - `ReadModelReadinessReporter.record_event_failure(...)` 把 `bank_detail_read_model_not_fresh` 这类依赖等待记录为 `failed`，即使 runtime worker 后续会 defer/retry，也会污染 App Status current-effective blocker。
- 决策：
  - `no_oa_bank_batch` scope policy 明确只允许 `all` 或 `YYYY-MM`，防止 legacy/非法 scope 进入 durable queue。
  - Worker refresh 按 event scope 读取银行流水；月份 scope 只重建目标月份，并把其它月份现有批次合并回完整 snapshot 后保存。
  - effective category 对同一批 rows 只读一次；读完后显式装饰 row payload。
  - `*_read_model_not_fresh` 在 readiness 层记录为 `refreshing`，保留 last_error 诊断，但不升级为 failed blocker。
  - 月份查询空结果时，若目标月份 dirty scope 仍 pending/processing/failed，不允许用 `all` readiness 伪装 fresh empty；目标月自身 fresh 或 `all` fresh 且目标月无 dirty blocker 才能返回真实 `[]`。
- 验收测试：
  - `test_dependency_not_fresh_exception_records_refreshing_not_failed`
  - `test_month_scope_refresh_reads_only_month_and_preserves_other_month_batches`
  - `test_refresh_reads_effective_categories_once_for_same_rows`
  - `test_no_oa_bank_batch_policy_accepts_all_and_month_scopes_only`
  - `test_no_oa_repository_does_not_treat_all_fresh_as_month_fresh_when_month_is_dirty`
  - `test_no_oa_repository_accepts_month_fresh_without_all_readiness_record`
- 七类测试覆盖：
  - Business core unit tests：本次未改业务批次生成规则，只改 refresh scope 和合并方式；由 no-OA read model refresh/integration 测试覆盖。
  - Service-layer tests：适用，覆盖 application service 对 scope_key、category provider 和 batch service 的调用。
  - API contract tests：本次未改 HTTP response shape。
  - Read model/cache/background job tests：适用，覆盖 dependency non-fresh、dirty scope、readiness、worker 月度 refresh 和 repository fresh-empty gate。
  - Frontend component and interaction tests：本次未改前端。
  - End-to-end business-flow integration tests：适用，通过 no-OA workbench integration 回归保护 no-OA/Workbench relation 事实。
  - Existing feature regression tests：适用，通过 runtime worker/readiness/gateway/App Status/no-OA 回归保护旧链路。

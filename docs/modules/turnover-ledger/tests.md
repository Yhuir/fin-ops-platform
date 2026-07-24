# 外部往来款管理 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口、回归范围和未测风险。实现后按实际影响更新矩阵。

## 2026-07-22 人工闭环冻结流水规则要求

- Business core：`tests/test_workbench_relation_grouping.py` 覆盖 OA/发票四种 requirement 组合、OR 聚合、未知/空/缺失规则 fail closed，并保护 `batch_accounting`、ETC 显式完成合同不受影响。
- Service layer：`tests/test_turnover_ledger_uow_contract.py` 证明 selected rows 只读一次、canonical rules provider 只读一次、metadata 冻结 tag/source/version；缺行、重复行、无效 rules 和合并带入未选 bank member 都在 command 前失败且不半写入。
- API contract：`tests/test_turnover_ledger_api.py` 固定生产 composition 注入 canonical rules provider；既有权限、版本冲突、幂等 replay/conflict 和 response shape 测试继续保护公开合同，本次没有新增 DTO 字段。
- Read model / worker：`tests/test_workbench_sql_runtime.py` 固定 `turnover_manual_closure` bank-only 且要求 OA 时，active relation 仍以同一个 case 投影到未配对区；本次不改变 schema、scope、queue 或 worker。
- Frontend：`WorkbenchApi` mapper 覆盖显式 false 与字段缺失；`RelationGroupGrid` 同时渲染 OA/发票待补提示。前端生产代码和交互 I/O 未改变。
- End-to-end integration：`tests/test_turnover_workbench_integration.py` 覆盖截图业务链：外部往来确认 -> canonical active relation -> bank-only/OA-required 留在未配对 -> 补齐要求后可配对 -> 撤回恢复；另覆盖双 false 直接配对。
- Existing feature regression：no-OA 规则保存不再扫描/回写 turnover relation；普通 manual relation、deterministic matching、batch accounting、ETC、合并和撤回保持既有行为。旧 `_sync_turnover_rule_relation_requirements` 及其专用测试语义已删除，不保留兼容分支。

## 2026-07-20 写命令重复 I/O 回归

- Service/UoW：`test_bank_row_selection_reuses_the_version_checked_rows_for_relation_preview` 证明版本校验与 closure preview 只触发一次 selected-row I/O；幂等测试证明事务内 reserve 仍覆盖首次、replay、冲突和 in-progress，replay 不重新执行 stale precondition。
- Workbench command：`test_prepared_withdraw_reuses_lock_relation_snapshot_and_freshness` 证明启用 read-model precondition 的通用 service 在 preparation + withdraw 间也只执行一次 lock、一次 scoped relation load 和一次 freshness；不同 case fail closed。Turnover 生产 composition 使用 canonical 模式，不查询派生 relation read model。
- API/composition：`test_turnover_affected_months_uses_one_bulk_fact_read` 与 builder wiring guard 防止恢复逐笔月份读取、独立 stale port 或 preview 二次读取。
- Outbox owner：`test_turnover_relation_command_repository_leaves_refresh_fanout_to_the_turnover_uow` 防止 relation repository 恢复 scope 解析和重复 outbox；durable PostgreSQL 测试继续证明 UoW 必需事件完整。
- 不适用：本轮未改 HTTP response shape、权限、业务金额/状态机、前端或 worker/read-model schema；这些继续由现有 API、权限、前端与生产可逆闭环回归覆盖。

## 2026-07-13 跨月关系 freshness scope 回归

- Service/read model：`tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_write_precondition_preserves_explicit_cross_month_scope_hints` 证明 `month_scope=all` 时仍以全部精确月份校验 relation read model，允许 fresh empty/unlinked 集合进入正常业务校验。
- 跨模块 UoW adapter：`tests/test_turnover_ledger_uow_contract.py::TurnoverLedgerUoWContractTests::test_turnover_manual_closure_precondition_keeps_cross_month_scope_keys` 证明 Turnover boundary 不丢失 `affected_months` I/O。
- 不适用：HTTP response shape、权限、关系状态机、worker、projection schema 和前端均未改变；继续由既有 API、read model、E2E 和生产可逆场景回归覆盖。

## 影响面清单

外部往来款不是孤立页面。修改时必须先确认影响面：

| 影响面 | 当前事实源 | 需要保护的行为 |
| --- | --- | --- |
| 页面和 API client | `web/src/pages/TurnoverLedgerPage.tsx`、`web/src/features/turnoverLedger/api.ts` | grouped table、标签抽屉、补充信息 drawer、人工闭环 drawer、导出 dialog、loading/empty/error/stale、权限禁用 |
| Current-page access convergence | `TurnoverLedgerPage.tsx` normal grouped GET | tag-selection、extra、confirm、withdraw 成功 targets 为空，零 operation barrier；只 reload 当前 grouped payload，失败不假装同步，成功后不能残留操作失败/同步失败/read model 失败等可见错误提示 |
| API contract | `backend/src/fin_ops_platform/app/server.py`、`backend/src/fin_ops_platform/app/routes_turnover_ledger.py`、`docs/dev/api-contracts.md` | `GET /api/turnover-ledger`、tag-selection、bank-row-tags batch、extra、confirm、withdraw、export-preview/export |
| Business core | `TurnoverRelationService`、`TurnoverLedgerService`、`TurnoverLedgerExtraService` | 外部往来标签准入、同组一收一支、零差额、同对方、同语义、人工闭环、撤回、extra 校验、内部转账排除 |
| Write UoW | `TurnoverLedgerWriteFacade`、`TurnoverLedgerWriteUnitOfWork`、`turnover_ledger_write_adapters.py` | stale precondition、idempotency、relation/extra/settings/bankdetail canonical 写入、零 read-model dirty/outbox、rollback、Workbench relation command service 委托 |
| Read model / worker | `TurnoverLedgerQueryService`、`TurnoverLedgerSqlProjectionBuilder`、`TurnoverLedgerReadModelRefreshService` | fresh/stale/missing/refreshing、source versions、group breakdown、Workbench relation 状态投影、worker complete dirty scope |
| 跨页面影响 | Workbench pair relation、Bank Details、Cost Statistics、Search、App Status | 手动闭环进入 Workbench active pair relation；撤回/分类变化后下游不能读旧 relation；App Status 不能误判 green |
| 前端跨页事件 | `web/src/features/domainEvents.ts` | `turnoverRelationUpdated`、`workbenchRelationUpdated`、`turnoverLedgerExtraUpdated` 只提示已可见页面 normal GET；不替代 canonical source-version/freshness gate |

## 现有测试入口

后端核心测试：

- `tests/test_turnover_relation_service.py`
- `tests/test_turnover_ledger_service.py`
- `tests/test_turnover_ledger_extra_service.py`
- `tests/test_turnover_ledger_source_versions.py`
- `tests/test_turnover_ledger_export_service.py`

后端 API / UoW / read model / worker：

- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `tests/test_turnover_ledger_query_service.py`
- `tests/test_turnover_ledger_read_model_refresh.py`
- `tests/test_turnover_ledger_read_model_refresh_producer.py`
- `tests/test_turnover_workbench_integration.py`
- `tests/test_workbench_turnover_grouping.py`
- `tests/test_app_status_overview_service.py`
- `tests/test_runtime_worker_registry.py`

前端：

- `web/src/test/TurnoverLedgerApi.test.ts`
- `web/src/test/TurnoverLedgerPage.test.tsx`
- `web/src/test/domainEvents.test.ts`
- `web/e2e/turnover-ledger-flow.spec.ts`
- `docs/modules/turnover-ledger/e2e-spec.md`
- `docs/modules/turnover-ledger/e2e-coverage.md`

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 当前结论 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_turnover_relation_service.py`、`tests/test_turnover_ledger_service.py`、`tests/test_turnover_ledger_extra_service.py` | 已覆盖四类 family、候选/确定候选、人工闭环、重复/跨对方/非零差额/同方向拒绝、撤回、内部转账排除、extra 字段校验、分组金额和利息。 |
| 2. Service-layer tests | 适用 | `tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_ledger_api.py`、`tests/test_turnover_workbench_integration.py`、`tests/test_workbench_pair_relation_service.py` | 已覆盖 UoW transaction、rollback、普通写零 dirty/outbox、stale precondition、idempotency、settings/extra/bankdetail/relation ports、Workbench relation command 委托、缺 command fail-fast、OA-bank relation 合并与撤回恢复、`cash_closure_case_id` 撤回不回退 legacy pair service。 |
| 3. API contract tests | 适用 | `tests/test_turnover_ledger_api.py` | 已覆盖 route owner、列表/grouped/tag-selection/bank-row-tags/extra/confirm/withdraw/export、权限、错误、版本冲突、idempotency replay/conflict、stale conflict、relation freshness 诊断、导出上限结构化错误、HTML response routing error。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_turnover_ledger_query_service.py`、`tests/test_turnover_ledger_read_model_refresh.py`、`tests/test_turnover_ledger_read_model_refresh_producer.py`、`tests/test_turnover_ledger_source_versions.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` | 已覆盖 stale SQL read model 不伪装 fresh、missing required SQL read model 返回 refreshing、legacy fallback、source versions、projection 保存、Workbench relation fresh 状态写入 grouped payload、Workbench relation non-fresh 不保存半成品、worker handler、refresh producer 只 enqueue 不 direct clear、registry/App Status 登记。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/TurnoverLedgerApi.test.ts`、`web/e2e/turnover-ledger-flow.spec.ts` | 已覆盖 API mapper、首屏失败恢复、防 false-empty、tag/extra drawer、grouped table、manual closure、stale 禁写、提交前 normal GET/rebind、写后零 barrier与 normal GET、Cost 独立访问、toolbar 撤回、导出和零可见错误。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_turnover_workbench_integration.py`、`tests/test_workbench_turnover_grouping.py`、`web/src/test/TurnoverLedgerPage.test.tsx`、`web/e2e/turnover-ledger-flow.spec.ts` | 已覆盖 deterministic 不进入 Workbench、manual closure canonical relation、失败不半写、legacy relation隔离；Browser 覆盖 tag-selection/confirm/withdraw 零 barrier与当前页 GET、独立进入 Cost 后 exact dependency-ordered fresh 和闭环成本行，且成功后零可见错误。 |
| 7. Existing feature regression tests | 适用 | 上述全部，加 `tests/test_workbench_turnover_grouping.py`、`web/src/test/domainEvents.test.ts`、`web/e2e/turnover-ledger-flow.spec.ts` | 已保护旧 grouped shape、legacy flat/read model 兼容、标签准入 selected codes、导出字段、Workbench open grouping、Bankdetail tag batch、旧 relation/system relation 拒绝、domain event contract、成本统计下游 fresh read model 展示，以及真实浏览器里 tag selection、closure/recovery 不破坏表格选择、toolbar 状态和“成功但报错提示仍显示”的回归。 |

当前首轮闭环未发现必须立即新增的 P0 测试。已有 turnover 测试覆盖密度高，本轮不为了覆盖率新增低价值测试。

## 2026-06-25 - route-owner local closure audit test note

`server-py:turnover-ledger-route-owner-local-closure-audit` 已完成为 analysis-only：

- Business core unit tests：不适用；本轮不改外部往来业务规则。
- Service-layer tests：不适用；本轮不改 services/facades/repositories。
- API contract tests：间接适用；本轮复用上一个 implementation slice 的完整 `tests.test_turnover_ledger_api` 证据，本 audit 未改 API。
- Read model/cache/background job tests：不适用；本轮不改 read model、dirty/outbox、worker 或 cache。
- Frontend component and interaction tests：不适用；本轮不改前端。
- End-to-end business-flow integration tests：不适用；本轮不改业务流。
- Existing feature regression tests：适用；复跑 platform Guard，证明 `server.py` 不再拥有 `_handle_api_turnover_ledger*` route callbacks，且 route owner inventory 仍注册。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v
bash scripts/verify.sh docs
git diff --check
```

未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；本 audit 不能声明模块全局 closed。

## 2026-06-25 - relation withdraw route-owner collapse test note

`server-py:turnover-ledger-relation-withdraw-route-callback-collapse` 已完成：

- Business core unit tests：不适用；本 slice 不改 relation withdraw 的业务规则。
- Service-layer tests：适用但未新增；既有 withdraw request boundary/write facade/UoW 回归继续覆盖 relation detail precheck、expected_versions、affected-months、stale precondition、idempotency 和 refresh side effects。
- API contract tests：适用；复跑 withdraw targeted regressions 和完整 `tests.test_turnover_ledger_api`，证明 idempotency replay/conflict、queue failure rollback、UoW no-direct-clear、unknown relation/error mapping 和 response shape 保持。
- Read model/cache/background job tests：间接适用；withdraw 成功后的 refresh 由既有 API/UoW tests 覆盖，本 slice 未改 worker、dirty/outbox 或 read model writer。
- Frontend component and interaction tests：不适用；未改前端 API mapper、toolbar withdraw UI 或 operation overlay。
- End-to-end business-flow integration tests：间接适用但未新增；本 slice 只迁移 HTTP mapping，不改变 relation withdraw business flow。
- Existing feature regression tests：适用；更新 platform Guard，防止 `_handle_api_turnover_ledger_withdraw(...)` 回到 `server.py`，并确认 turnover ledger route callbacks 已全部迁出。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_withdraw_relation_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_withdraw_handler_delegates_precheck_expected_versions_and_affected_months_to_request_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_withdraw_request_boundary_facade_wires_relation_detail_and_affected_months_resolver tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_withdraw_idempotency_key_replays_without_duplicate_withdraw_or_refresh tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_withdraw_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_withdraw_relation_queue_failure_rolls_back_relation_withdraw tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_withdraw_relation_uow_path_does_not_clear_read_model_directly -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；下一步需要 route-owner local closure audit。

## 2026-06-25 - closure withdraw route-owner collapse test note

`server-py:turnover-ledger-closure-withdraw-route-callback-collapse` 已完成：

- Business core unit tests：不适用；本 slice 不改 withdraw cash closure case 的业务规则。
- Service-layer tests：适用但未新增；既有 closure request boundary/write facade/UoW 回归继续覆盖 Workbench relation command service wiring、idempotency 和 refresh side effects。
- API contract tests：适用；复跑 closure withdraw targeted regressions 和完整 `tests.test_turnover_ledger_api`，证明 cash closure case id 兼容、provider override、response shape 和 closure/withdraw wiring 保持。
- Read model/cache/background job tests：间接适用；closure withdraw 成功后的 refresh 由既有 API/UoW tests 覆盖，本 slice 未改 worker、dirty/outbox 或 read model writer。
- Frontend component and interaction tests：不适用；未改前端 API mapper、toolbar withdraw UI 或 operation overlay。
- End-to-end business-flow integration tests：间接适用但未新增；本 slice 只迁移 HTTP mapping，不改变 closure withdraw business flow。
- Existing feature regression tests：适用；更新 platform Guard，防止 `_handle_api_turnover_ledger_closure_withdraw(...)` 回到 `server.py`，并确认 relation withdraw callback 仍保留。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_closure_withdraw_handler_uses_closure_boundary_without_relation_withdraw_inline tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_cash_closure_withdraw_route_uses_closure_boundary tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；relation withdraw callback 是后续边界。

## 2026-06-25 - closure confirm route-owner collapse test note

`server-py:turnover-ledger-closure-confirm-route-callback-collapse` 已完成：

- Business core unit tests：不适用；本 slice 不改 manual zero-difference closure 的金额、分组、row type 或状态规则。
- Service-layer tests：适用但未新增；既有 closure request boundary/write facade/UoW 回归继续覆盖 Workbench relation command service wiring、affected-months、stale precondition、idempotency 和 refresh side effects。
- API contract tests：适用；复跑 closure confirm targeted regressions 和完整 `tests.test_turnover_ledger_api`，证明 permission、response shape 和 closure/withdraw wiring 保持。
- Read model/cache/background job tests：间接适用；closure confirm 成功后的 `turnover_ledger:all` refresh 由既有 API/UoW tests 覆盖，本 slice 未改 worker、dirty/outbox 或 read model writer。
- Frontend component and interaction tests：不适用；未改前端 API mapper、manual closure UI 或 operation overlay。
- End-to-end business-flow integration tests：间接适用但未新增；本 slice 只迁移 HTTP mapping，不改变 closure business flow。
- Existing feature regression tests：适用；更新 platform Guard，防止 `_handle_api_turnover_ledger_closure_confirm(...)` 回到 `server.py`，并确认 withdraw callbacks 仍保留。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_closure_confirm_handler_delegates_affected_months_boundary_to_request_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_and_withdraw_require_mutation_permission_and_write_audit -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；closure withdraw 与 relation withdraw callbacks 是后续边界。

## 2026-06-25 - confirm route-owner collapse test note

`server-py:turnover-ledger-confirm-route-callback-collapse` 已完成：

- Business core unit tests：不适用；本 slice 不改确认关系的金额、分组、标签或状态规则。
- Service-layer tests：适用但未新增；既有 confirm request boundary/write facade/UoW 回归继续覆盖 affected-months、stale precondition、idempotency、rollback 和 refresh side effects。
- API contract tests：适用；复跑 confirm targeted regressions 和完整 `tests.test_turnover_ledger_api`，证明 expected_versions、idempotency replay/conflict、queue failure rollback、UoW no-direct-clear 和 response shape 保持。
- Read model/cache/background job tests：间接适用；confirm 成功后的 `turnover_ledger:all` refresh 由既有 API/UoW tests 覆盖，本 slice 未改 worker、dirty/outbox 或 read model writer。
- Frontend component and interaction tests：不适用；未改前端 API mapper、manual closure UI 或 operation overlay。
- End-to-end business-flow integration tests：间接适用但未新增；本 slice 只迁移旧 relation confirm callback，不改 closure confirm/withdraw 业务流。
- Existing feature regression tests：适用；更新 platform Guard，防止 `_handle_api_turnover_ledger_confirm(...)` 回到 `server.py`，并确认 closure/withdraw callbacks 仍保留。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_relation_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_handler_delegates_affected_months_boundary_to_request_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_request_boundary_facade_owns_affected_months_resolution_and_response_field tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_request_expected_versions_reach_write_command tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_idempotency_key_replays_without_duplicate_confirm_or_refresh tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_relation_queue_failure_rolls_back_relation_confirm tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_relation_uow_path_does_not_clear_read_model_directly -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；closure confirm/withdraw 与 relation withdraw callbacks 是后续边界。

## 2026-06-25 - relation-extra route-owner collapse test note

`server-py:turnover-ledger-relation-extra-route-callback-collapse` 已完成：

- Business core unit tests：不适用；本 slice 不改 extra 字段业务校验、金额、标签、闭环或撤回规则。
- Service-layer tests：适用但未新增；既有 relation extra request boundary/write facade 回归继续覆盖 normalization、stale precondition、idempotency、extra save 和 refresh side effects。
- API contract tests：适用；复跑 relation-extra targeted regressions 和完整 `tests.test_turnover_ledger_api`，证明 GET default、PUT persist、invalid payload、readonly、idempotency replay/conflict 和 response shape 保持。
- Read model/cache/background job tests：间接适用；relation extra 成功后的 `turnover_ledger:all` refresh 由既有 API tests 覆盖，本 slice 未改 worker、dirty/outbox 或 read model writer。
- Frontend component and interaction tests：不适用；未改前端 API mapper、extra drawer、页面交互或 operation overlay。
- End-to-end business-flow integration tests：不适用；未改 confirm/withdraw/closure flow。
- Existing feature regression tests：适用；更新 platform Guard，防止 `_handle_api_turnover_ledger_relation_extra_update(...)` 回到 `server.py`，并确认 confirm/closure/withdraw callbacks 仍保留。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_handler_delegates_expected_versions_idempotency_and_stale_boundary tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_get_returns_default_structure_and_put_persists tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_put_rejects_invalid_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_put_rejects_readonly_user tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_relation_extra_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_relation_extra_idempotency_key_replays_without_duplicate_save_or_refresh -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；confirm/closure/withdraw callbacks 是后续边界。

## 2026-06-25 - bank-row-tags route-owner collapse test note

`server-py:turnover-ledger-bank-row-tags-route-callback-collapse` 已完成：

- Business core unit tests：不适用；本 slice 不改外部往来标签规则或分类业务规则。
- Service-layer tests：适用但未新增；既有 bank-row-tags request boundary/write facade 回归继续覆盖 target validation、affected months、idempotency、legacy fallback、category update 和 refresh side effects。
- API contract tests：适用；复跑 bank-row-tags targeted regressions 和完整 `tests.test_turnover_ledger_api` 140 个用例，证明 POST status/error/response shape、非 turnover row 拒绝、idempotency replay/conflict 和 category/refresh 行为保持。
- Read model/cache/background job tests：间接适用；bank-row-tags 成功后的 bank detail/workbench/turnover refresh 由既有 API tests 覆盖，本 slice 未改 worker、dirty/outbox 或 read model writer。
- Frontend component and interaction tests：不适用；未改前端 API mapper、页面交互或 operation overlay。
- End-to-end business-flow integration tests：不适用；未改 confirm/withdraw/closure flow。
- Existing feature regression tests：适用；更新 platform Guard，防止 `_handle_api_turnover_ledger_bank_row_tags_batch(...)` 回到 `server.py`，并确认 relation-extra/confirm/closure/withdraw callbacks 仍保留。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_turnover_bank_row_tag_batch_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_bank_row_tags_handler_delegates_validation_affected_months_and_flags_to_request_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_bank_row_tag_batch_save_updates_category_and_reflects_to_bank_details tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_bank_row_tag_batch_rejects_non_turnover_rows_without_refresh_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_bank_row_tags_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_bank_row_tags_idempotency_key_replays_without_duplicate_category_update_relation_rebuild_or_refresh -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；relation-extra/confirm/closure/withdraw callbacks 是后续边界。

## 2026-06-25 - tag-selection write route-owner collapse test note

`server-py:turnover-ledger-tag-selection-write-route-callback-collapse` 已完成：

- Business core unit tests：不适用；本 slice 不改外部往来标签准入业务规则。
- Service-layer tests：适用但未新增；既有 tag-selection write facade/request-boundary 回归继续覆盖 settings persistence、idempotency、refresh enqueue 和 rollback。
- API contract tests：适用；复跑 tag-selection targeted regressions 和完整 `tests.test_turnover_ledger_api` 140 个用例，证明 PUT status/error/response shape、版本冲突、idempotency replay/conflict 和 queue failure rollback 行为保持。
- Read model/cache/background job tests：间接适用；tag-selection 成功后的 `turnover_ledger:all` refresh/rollback 由既有 API tests 覆盖，本 slice 未改 worker、dirty/outbox 或 read model writer。
- Frontend component and interaction tests：不适用；未改前端 API mapper、页面交互或 operation overlay。
- End-to-end business-flow integration tests：不适用；未改 confirm/withdraw/closure flow。
- Existing feature regression tests：适用；更新 platform Guard，防止 `_handle_api_turnover_ledger_tag_selection_update(...)` 回到 `server.py`，并确认其他 turnover ledger mutation callbacks 仍保留。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_ledger_tag_selection_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_ledger_tag_selection_get_put_and_version_conflict tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_tag_selection_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_tag_selection_idempotency_key_replays_without_duplicate_settings_save_or_refresh tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_turnover_ledger_tag_selection_queue_failure_rolls_back_settings_save -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；bank-row-tags、relation-extra、confirm、closure、withdraw callbacks 是后续边界。

## 2026-06-25 - read/export GET route-owner collapse test note

`server-py:turnover-ledger-read-export-route-callback-collapse` 已完成：

- Business core unit tests：不适用；本 slice 不改外部往来金额、标签准入、闭环、撤回、extra 或分组业务规则。
- Service-layer tests：适用；复跑 `tests/test_turnover_ledger_api.py` 和 `tests/test_platform_runtime_boundary_guards.py`，证明 route owner 直接承担 read/write HTTP 边界且旧 read facade 不得恢复。
- API contract tests：适用；复跑 `tests/test_turnover_ledger_api.py` 140 个用例，覆盖列表/grouped、tag-selection、extra、export、权限/error、idempotency/stale 和写路径回归。更新 `test_export_limit_returns_structured_error`，把导出上限错误注入点改到新的 `TurnoverLedgerApiRoutes` route-owner boundary。
- Read model/cache/background job tests：间接适用；本 slice 未改 worker、dirty/outbox 或 read model writer，但 API 回归继续覆盖 grouped metadata、stale refresh enqueue 和 read model freshness 诊断。
- Frontend component and interaction tests：不适用；未改前端 API mapper、页面交互、operation overlay 或 Browser flow。
- End-to-end business-flow integration tests：不适用；未改 confirm/withdraw/tag-selection 写业务流。
- Existing feature regression tests：适用；新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_ledger_read_export_routes_use_route_owner`，防止 read/export GET callback 回到 `server.py`，并确认 mutation callbacks 仍保留给后续写路径审计。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_read_model_refresh_producer -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；mutation callbacks 是下一轮边界。

## 2026-06-24 - repository port extraction test note

`read-models:turnover-ledger-repository-port-extraction` 已完成。测试合同执行结果：

- Business core unit tests：默认不适用，除非实现改动外部往来标签、金额、闭环、撤回或 extra 规则。
- Service-layer tests：适用，已新增 port guard，证明 `TurnoverLedgerReadModelRepositoryPort` 只暴露 manifest 登记的三项 read model 方法。
- API contract tests：默认不适用，除非实现改动 `/api/turnover-ledger` response shape、状态码、错误字段或权限。
- Read model/cache/background job tests：适用，已运行 `tests/test_turnover_ledger_query_service.py` 和 `tests/test_turnover_ledger_read_model_refresh.py`，保护 fresh/stale/missing、projection save、worker complete dirty scope。
- Frontend component and interaction tests：默认不适用，除非实现改动 grouped payload、stale 诊断、operation overlay 或前端 API mapper。
- End-to-end business-flow integration tests：默认不适用；repository port 首切不改变 confirm/withdraw/tag-selection 业务流。
- Existing feature regression tests：适用，必须保持 manifest/architecture guard 对无关 read model 方法污染的防护。

下一 slice 是 `read-models:turnover-ledger-refresh-freshness-operation-barrier-audit`，需要审计 fresh gate、force refresh、all fan-out/query proof、Workbench relation source-version proof、operation barrier targets、legacy read contamination 和 app-owned helper 分类。

## 2026-06-24 - freshness/barrier audit test note

`read-models:turnover-ledger-refresh-freshness-operation-barrier-audit` 已完成为 analysis-only slice：

- 复用现有 turnover query/read model refresh/API/UoW/operation barrier 测试作为 fresh gate、source-version proof、worker complete dirty scope、write response target 和 outbox-blocking 证据。
- 未新增测试，因为本轮不改运行时代码。
- 2026-07-05 已关闭 producer/clear boundary gap：旧 app-owned clear helper、producer direct clear I/O 和 relation mutation legacy invalidation adapter 已删除；`tests/test_turnover_ledger_read_model_refresh_producer.py` 与 `tests/test_platform_runtime_boundary_guards.py` 防止恢复。

## 2026-06-24 - refresh producer and clear port extraction test note

`read-models:turnover-ledger-refresh-producer-clear-port-extraction` 已完成：

- Business core unit tests：不适用；本 slice 不改外部往来金额、分类、闭环、撤回或 extra 规则。
- Service-layer tests：适用，新增 `tests/test_turnover_ledger_read_model_refresh_producer.py`，覆盖 scope normalization、gateway enqueue、gateway unavailable 和 turnover-specific repository clear best-effort。
- API contract tests：默认不适用；API response shape、状态码和错误字段未变。已运行目标 turnover API 回归证明 tag-selection、relation-extra 和 relation mutation refresh 行为保持。
- Read model/cache/background job tests：适用，复跑 `tests/test_turnover_ledger_query_service.py`、`tests/test_turnover_ledger_read_model_refresh.py` 和 platform boundary guard。
- Frontend component and interaction tests：不适用；没有前端代码或 operation overlay contract 变化。
- End-to-end business-flow integration tests：不适用；本 slice 只迁移 refresh/clear producer 边界，未改变 confirm/withdraw/tag-selection 业务流。
- Existing feature regression tests：适用，更新 `tests/test_turnover_ledger_api.py`、`tests/test_bank_auto_tag_rules_api.py` 和 `tests/test_platform_runtime_boundary_guards.py`，防止旧 app-owned helper 返回并防止 clear 再走 broad workbench repository。

## 2026-06-24 - local implementation closure audit test note

`read-models:turnover-ledger-local-implementation-closure-audit` 已完成为 analysis/accounting slice：

- Business core unit tests：不适用；本轮不改金额、分类、分组、闭环、撤回、标签或 extra 规则。
- Service-layer tests：适用但未新增；复用 `tests/test_turnover_ledger_read_model_refresh_producer.py`、`tests/test_turnover_ledger_query_service.py`、`tests/test_turnover_ledger_read_model_refresh.py`、UoW/API regressions 和 platform boundary guard 作为本地边界证据。
- API contract tests：适用但未新增；本轮不改 HTTP shape/status/error/permission/freshness target，复用 `tests/test_turnover_ledger_api.py` 的合同回归。
- Read model/cache/background job tests：适用但未新增；复用 producer/query/worker/manifest/runtime worker registry/operation barrier tests 证明 gateway、scope policy、worker event 和 dirty scope complete 行为。
- Frontend component and interaction tests：适用为证据；本轮不改前端，复用现有 TurnoverLedgerPage/API/operation barrier tests 证明写后等待 `turnover_ledger` barrier 和 stale grouped payload 阻断。
- End-to-end business-flow integration tests：适用为证据；本轮不改业务流，复用 turnover/workbench integration 和 Browser E2E 文档证据。
- Existing feature regression tests：适用，复用 platform runtime boundary guards，证明旧 app-owned refresh/clear helper 不得回归。

结论：本地实现支持已 accounted，剩余是 production evidence deferred；仍需真实 PostgreSQL/worker/App Status/high-row/browser evidence，不能把本结论理解为模块全局 closed。

## 2026-06-25 - grouped query metadata boundary fix test note

`read-models:turnover-ledger-grouped-query-metadata-boundary-fix` 修复了 `view=grouped` 把 SQL/read-model payload 转 grouped payload 时丢弃顶层 freshness metadata 的问题。

- Business core unit tests：不适用；本 slice 不改外部往来金额、标签、闭环、撤回、extra 或分组业务规则。
- Service-layer tests：适用；复跑 `tests/test_turnover_ledger_query_service.py`，保护 `TurnoverLedgerQueryService` 的 fresh/stale/missing gateway 合同。
- API contract tests：适用；新增 `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_get_turnover_ledger_grouped_preserves_fresh_sql_read_model_metadata` 和 `test_get_turnover_ledger_grouped_preserves_stale_sql_refresh_metadata`，证明 grouped GET 保留 `read_model_status`、`refresh_enqueued`、`refresh_reason`、`source_versions` 等顶层 metadata，避免生产 API smoke 无法观测 refresh enqueue。
- Read model/cache/background job tests：适用；stale grouped read model 用例证明 source-version mismatch 仍通过 `ReadModelQueryGateway` enqueue `turnover_ledger:all`，但 response 不再隐藏 enqueue metadata。
- Frontend component and interaction tests：本 slice 未改前端；现有前端 stale grouped warning/operation barrier 测试仍是消费侧保护。若后续调整前端对 metadata 的展示，再补 Vitest/Playwright。
- End-to-end business-flow integration tests：不适用；本 slice 不改 confirm/withdraw/tag-selection/extra 写链路。
- Existing feature regression tests：适用；保留 `test_get_turnover_ledger_grouped_view_returns_groups`，证明 grouped shape 仍有 `groups`、`summary_row`、`flow_rows`、`allocation_lots`。

生产 Row286 已证明当前 release 的 grouped GET 可以隐藏 enqueue；本地修复后仍需要单独 deploy/re-smoke 边界验证生产 `turnover_ledger_grouped` response metadata 和 aggregate no-hidden-enqueue 行为。

## 2026-06-25 - refresh source-version persistence contract fix test note

`read-models:turnover-ledger-refresh-source-version-persistence-contract-fix` 修复了 turnover projection 在 `list_grouped_ledger()` 触发 `TurnoverRelationService.rebuild_from_bank_rows(...)` 内存重建后才捕获 source versions，导致 worker 持久化的 `turnover_relation_snapshot_version` 与 API fresh gate expected source versions 不一致的问题。

- Business core unit tests：不适用；本 slice 不改外部往来分组、金额、标签、闭环、撤回或 extra 业务规则。
- Service-layer tests：适用；新增 `tests/test_turnover_ledger_read_model_refresh.py::TurnoverLedgerReadModelRefreshServiceTests::test_projection_source_versions_are_captured_before_relation_rebuild_side_effects`，证明 projection 保存的 top-level 和 row-level `source_versions` 在 grouped ledger 内存重建副作用前捕获，和 API expected source version 合同对齐。
- API contract tests：适用为回归；复跑 `tests/test_turnover_ledger_api.py`，证明 grouped metadata/API shape 不因 source-version 捕获时序变化而改变。
- Read model/cache/background job tests：适用；复跑 `tests/test_turnover_ledger_read_model_refresh.py`、`tests/test_turnover_ledger_query_service.py`、`tests/test_turnover_ledger_read_model_refresh_producer.py`，保护 projection save、fresh/stale gateway 和 refresh producer enqueue-only 合同。
- Frontend component and interaction tests：不适用；本 slice 不改前端展示、操作 overlay、API mapper 或交互。
- End-to-end business-flow integration tests：不适用；本 slice 不改 confirm/withdraw/tag-selection/extra 写链路。
- Existing feature regression tests：适用；`tests/test_turnover_ledger_api.py` 和 read facade/query service 全量回归继续保护旧 grouped shape、metadata、stale/missing 行为。

生产 Row289 已证明 API/projection provider 当前 hash 一致，但 persisted row source_versions 仍旧；本地修复后必须单独 deploy/re-smoke，并用生产 focused grouped probe 证明 `read_model_status=fresh` 或明确分类剩余 enqueue。

## 场景覆盖清单

| 场景 | 代表测试 |
| --- | --- |
| grouped GET 暂时失败恢复 | `web/src/test/TurnoverLedgerPage.test.tsx::recovers grouped ledger after a transient load failure when refreshed`、`web/e2e/turnover-ledger-flow.spec.ts::recovers grouped ledger after a transient load failure when refreshed` |
| 外部往来标签准入默认选择和版本冲突 | `test_turnover_ledger_tag_selection_get_put_and_version_conflict` |
| tag-selection queue failure rollback | `test_turnover_ledger_tag_selection_queue_failure_rolls_back_settings_save`、`test_tag_selection_outbox_failure_rolls_back_settings_save_and_audit` |
| grouped read model stale/missing | `test_stale_sql_read_model_is_not_returned_as_fresh_and_enqueues_refresh`、`test_missing_required_sql_read_model_returns_empty_refreshing_payload_and_enqueues_miss` |
| grouped table 金额和真实 flow rows | `test_grouped_ledger_places_flow_amounts_by_turnover_action_type_and_exposes_breakdowns`、`test_expands_Jia_Xiaohua_with_real_flow_rows_instead_of_allocation_lot_rows` |
| 人工零差额闭环 | `test_closure_request_boundary_returns_affected_scopes_without_barrier_targets`、`test_target_zero_difference_closure_facade_writes_only_canonical_workbench_relation`、`test_target_withdraw_relation_facade_enqueues_zero_refreshes`、`test_target_withdraw_relation_has_zero_queue_io`，以及既有合并、冲突、幂等、撤回恢复测试；共同保护 canonical-only 写入、信息性月份和零 read-model target |
| SQL runtime 银行流水闭环事实源 | `test_sql_bank_detail_turnover_rows_keep_legacy_source_ids_for_manual_closure`、`test_sql_turnover_rows_tolerate_early_startup_before_app_settings_service_is_bound` |
| 前端闭环提交前最新版本保护 | `refreshes the grouped ledger before manual closure and submits latest bank row versions`、`blocks manual closure when a selected flow disappears after the fresh ledger reload`、`shows grouped read model stale warning and blocks manual closure` |
| 非法闭环拒绝 | `test_confirm_zero_difference_closure_rejects_duplicate_row_ids`、`test_confirm_zero_difference_closure_rejects_cross_counterparty_rows`、`test_confirm_zero_difference_closure_rejects_non_zero_difference`、`test_confirm_zero_difference_closure_rejects_same_direction_pair` |
| stale/idempotency | `test_target_confirm_request_expected_versions_reach_write_command`、`test_target_confirm_idempotency_key_replays_without_duplicate_confirm_or_refresh`、`test_withdraw_stale_precondition_rejects_changed_relation_before_mutation_or_refresh`、`test_manual_closure_uses_canonical_relation_when_workbench_relation_read_model_is_stale` |
| relation extra | `test_relation_extra_get_returns_default_structure_and_put_persists`、`test_target_relation_extra_stale_expected_version_rejects_without_save_or_refresh`、`test_relation_extra_outbox_failure_does_not_return_best_effort_success` |
| Bankdetail tag batch fan-out | `test_turnover_bank_row_tag_batch_refreshes_all_required_scopes`、`test_target_turnover_bank_row_tag_batch_queue_failure_rolls_back_category_save` |
| Workbench 回归 | `test_deterministic_turnover_relation_does_not_group_bank_rows_in_workbench`、`test_bank_only_turnover_manual_closure_rows_stay_open_until_three_way_complete`、`test_three_pane_turnover_manual_closure_rows_render_as_paired_case`、`test_sql_projection_keeps_turnover_manual_closure_bank_only_case_open_until_three_way_complete`、`test_manual_pair_relation_occupied_bank_row_is_not_overridden_by_turnover_relation`、`test_withdraw_restores_previous_relations_from_turnover_manual_closure_history`、`test_turnover_workbench_pair_port_delegates_manual_closure_withdraw_to_relation_command_service`、`test_turnover_workbench_pair_port_withdraw_restores_merged_oa_bank_relations`、`test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure_withdraw`、`test_turnover_workbench_pair_port_delegates_cash_closure_withdraw_to_relation_command_service`、`test_turnover_workbench_pair_port_requires_relation_command_service_for_cash_closure_withdraw`、`test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service` |
| 前端闭环 chip 和 toolbar | `shows Workbench relation feedback from the grouped ledger payload`、`allows manual closure confirmation when selected rows are only linked to OA`、`withdraws a selected linked manual closure from the table toolbar`、`web/e2e/turnover-ledger-flow.spec.ts` |
| Worker / App Status | `test_worker_handler_rebuilds_scope_and_completes_dirty_scope`、`test_domain_registry_covers_frontend_routes`、`test_required_worker_missing_marks_critical_domain_blocked` |
| Workbench relation 状态投影 | `test_projection_enriches_rows_with_fresh_workbench_relation_context`、`test_projection_does_not_save_when_workbench_relation_context_is_not_fresh`、`maps ledger, detail, confirm, and withdraw responses from snake_case`、`shows Workbench relation feedback from the grouped ledger payload` |
| `bank_detail` dependency fan-out 不阻塞 all-scope 台账 | `RuntimeWorkerTests.test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`ReadModelRefreshGatewayTests.test_bank_detail_all_shard_reason_does_not_bump_active_scope` |
| fresh missing bank tag rows 不阻塞 all-scope 台账 | `BankTransactionTagReadFacadeTests.test_get_by_transaction_ids_keeps_fresh_status_when_some_rows_are_not_projected`、`BankTransactionTagReadFacadeTests.test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows` |
| blocking dirty scope 粒度不阻塞 all-scope 台账 | `BankTransactionTagReadFacadeTests.test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes` |
| bank detail tag facade 下游版本合同 | `BankTransactionTagReadFacadeTests.test_get_by_transaction_ids_returns_standardized_fresh_tagged_rows`、`BankTransactionTagReadFacadeTests.test_bulk_get_for_rows_preserves_versions_for_downstream_preconditions` |
| 前端 stale 写禁用 | `shows grouped read model stale warning and blocks manual closure`、`web/e2e/turnover-ledger-flow.spec.ts::shows stale grouped ledger data without allowing manual closure` |
| 前端 access-to-fresh closure | tag-selection、extra、manual closure confirm/withdraw 成功后不进入全局 operation barrier；manual closure confirm 提交前仍刷新 grouped ledger 并绑定最新 flow-row versions，提交后只重跑当前页面正常 GET。其他页面不由 Turnover 写链投递，访问或重新可见时各自 freshness gate；`web/e2e/turnover-ledger-flow.spec.ts` 覆盖写成功、当前页面 GET 收敛、Cost 独立访问及 withdraw recovery，并检查零 fan-out/零可见错误残留 |
| 手动闭环后同对方剩余流水保留 | `test_manual_closure_keeps_remaining_same_counterparty_rows_in_auto_relation`、`test_grouped_ledger_keeps_unselected_same_counterparty_flows_after_manual_closure` |
| 现代闭环 canonical 单事实写入 | `test_preview_zero_difference_closure_does_not_mutate_relation_or_audit_snapshots`、`test_turnover_relation_write_port_previews_closure_without_persisting_relation`、`test_target_zero_difference_closure_facade_writes_only_canonical_workbench_relation`、`test_manual_closure_uses_canonical_relation_when_workbench_relation_read_model_is_stale` |
| 新旧撤回路由隔离 | `test_legacy_turnover_relation_id_requires_explicit_relation_metadata`、`test_turnover_workbench_pair_port_rejects_cash_closure_with_invoice_members`、`test_turnover_cash_closure_withdraw_rejects_upgraded_case_and_keeps_relation_active`、`test_bank_turnover_scenario_uses_canonical_closure_withdraw_contract` |

## 历史 bug 回归库

| 风险/历史问题 | 当前保护 |
| --- | --- |
| deterministic 被误当作已闭环并进入 Workbench | `tests/test_turnover_workbench_integration.py`、`tests/test_workbench_turnover_grouping.py` |
| grouped 视图把 allocation lot 当真实流水导出或展示 | `tests/test_turnover_ledger_export_service.py`、`web/src/test/TurnoverLedgerPage.test.tsx` |
| 外部往来 export-preview/export 对超大 group 或展开后超大 flow rows 同步生成预览/XLSX，拖慢 API 线程和内存；或前端下载路径/页面弹窗吞掉后端超限消息 | `tests/test_turnover_ledger_export_service.py::TurnoverLedgerExportServiceTests::test_export_rejects_group_count_above_sync_row_limit`、`tests/test_turnover_ledger_export_service.py::TurnoverLedgerExportServiceTests::test_export_rejects_flattened_flow_rows_above_sync_row_limit`、`tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_export_limit_returns_structured_error`、`web/src/test/TurnoverLedgerApi.test.ts::surfaces backend row-limit messages from failed export downloads`、`web/src/test/TurnoverLedgerPage.test.tsx::shows backend export row-limit messages inside the export dialog` |
| stale read model 下仍允许确认/撤回/extra 写入 | `web/src/test/TurnoverLedgerPage.test.tsx` stale 写禁用测试，后端 stale precondition 测试 |
| manual closure 抽屉缓存旧 row version，POST 使用旧 `expected_versions` 被后端拒绝，导致关联台没有生成配对/open 组 | `refreshes the grouped ledger before manual closure and submits latest bank row versions`、`blocks manual closure when a selected flow disappears after the fresh ledger reload` |
| 已被 `turnover_manual_closure` 关联台关系占用的 flow row 在表格中被选中后，toolbar 仍只提供“确认闭环”，用户无法从当前选择直接撤回手工闭环，且可能误点普通闭环路径 | `withdraws a selected linked manual closure from the table toolbar` |
| 已关联 OA 的银行流水被 `workbench_relation_status=linked` 误当成外部往来闭环，导致“确认闭环”被禁用，并显示模糊的“关联台已关联/已关联业务单据/未闭环”等旧 chip | `allows manual closure confirmation when selected rows are only linked to OA`、`shows Workbench relation feedback from the grouped ledger payload` |
| 流水 1 已配对 OA1、流水 2 已配对 OA2、流水 3 未配对时，外部往来确认闭环未把 5 项放入同一个 active case，或撤回闭环时误删/不恢复原 OA-bank relation | `test_turnover_manual_closure_merges_existing_oa_bank_relations`、`test_withdraw_restores_previous_relations_from_turnover_manual_closure_history`、`test_manual_closure_merges_existing_oa_bank_relations_and_withdraw_restores_them`、`test_turnover_workbench_pair_port_withdraw_restores_merged_oa_bank_relations` |
| 已经存在其他 `turnover_manual_closure` 的流水被再次确认闭环，替换掉原闭环关系而不是提示先撤回 | `test_turnover_manual_closure_rejects_rows_already_in_turnover_closure`、`test_confirm_zero_difference_closure_rejects_partial_existing_closure_overlap` |
| Turnover 本地已经有同一批流水的手动闭环 relation，但 Workbench canonical active case 缺失，导致外部往来提示已闭环而关联台没有配对 | `test_confirm_zero_difference_closure_reuses_exact_existing_closure_rows`、`test_manual_closure_repairs_orphaned_turnover_closure_without_workbench_case` |
| 手动闭环已知 affected months 时仍投递普通 `workbench:all`，导致月 shard 尚未 fresh 时 all 聚合写出 `workbench_all_scope_parent_inconsistent` failed generation，App Health 阻断且关联台不刷新 | `test_target_zero_difference_closure_facade_writes_turnover_and_workbench_pair_relation` |
| 同一批流水已经处于普通 Turnover `confirmed` relation 但尚未形成手动闭环时，确认闭环被 active turnover relation overlap 误拒绝，导致 Workbench `turnover_manual_closure` 链路没有执行 | `test_confirm_zero_difference_closure_upgrades_existing_confirmed_relation_for_same_rows` |
| 同一对方多笔外部往来中只选择两笔确认闭环后，`rebuild_from_bank_rows()` 删除了包含已闭环 row 的整个自动 relation，导致未选流水从外部往来页消失 | `test_manual_closure_keeps_remaining_same_counterparty_rows_in_auto_relation`、`test_grouped_ledger_keeps_unselected_same_counterparty_flows_after_manual_closure` |
| SQL bank detail row 或 grouped read model flow row 缺 `category_version` / `category_version=0` 占位时，转换出的 turnover flow row、保存的 grouped projection 或写入前置校验没有回退到 `manual_category_version` 或基础 `version`，导致后端 stale precondition 误报“银行流水状态已变化”；或者版本语义改变后未 bump `turnover_ledger_schema_version`，旧 projection 被继续当 fresh 返回 | `test_sql_bank_detail_turnover_row_uses_manual_category_version_when_category_version_missing`、`test_sql_bank_detail_turnover_row_falls_back_to_bank_row_version_when_category_versions_missing`、`test_sql_bank_detail_turnover_row_uses_manual_category_version_when_category_version_is_zero`、`test_sql_bank_detail_turnover_row_falls_back_to_bank_row_version_when_category_version_is_zero`、`test_grouped_ledger_uses_manual_version_when_category_version_is_zero`、`test_grouped_ledger_uses_bank_row_version_when_category_versions_are_zero`、`test_source_versions_include_all_turnover_and_cross_module_inputs`、`test_bank_row_stale_precondition_uses_manual_version_when_category_version_is_zero`、`test_bank_row_stale_precondition_uses_base_version_when_category_versions_are_zero`、`test_manual_closure_api_accepts_sql_rows_with_zero_category_version`、`test_sql_bank_detail_turnover_row_prefers_category_version_over_manual_version` |
| `BankTransactionTagReadFacade` 从 fresh `bank_detail` read model 给 turnover worker 提供标签事实时丢弃 `category_version`、`manual_category_version`、`version`，导致 fresh `turnover_ledger` grouped payload 仍提交 `expected_versions=0`，后端当前 bank row 版本为 `1/2` 时正确拒绝为 stale | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_returns_standardized_fresh_tagged_rows`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_bulk_get_for_rows_preserves_versions_for_downstream_preconditions` |
| 关联台撤回或补链后，流水台 grouped payload 仍只显示 turnover 本地状态，无法反馈 Workbench active relation 当前事实；或 Workbench relation read model stale 时发布新的 turnover read model，导致 stale relation 伪装 fresh | `test_projection_enriches_rows_with_fresh_workbench_relation_context`、`test_projection_marks_workbench_bank_pair_as_cash_closure_when_group_zeroes_out`、`test_projection_does_not_save_when_workbench_relation_context_is_not_fresh`、`shows Workbench relation feedback from the grouped ledger payload` |
| SQL runtime 下闭环写路径读取 legacy import snapshot，而不是 `bank_detail` SQL read model，导致生产已有流水仍报 `unknown_transaction_id` 或 stale，且 Workbench relation 没有写入 | `test_sql_bank_detail_turnover_rows_keep_legacy_source_ids_for_manual_closure` |
| Postgres 事务写路径绕过 read model scope policy，确认/撤回外部往来时向成本统计投递裸月份或裸 `all`，导致 `cost_statistics` dead-letter 和 App Status failed | `test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction`、`test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear` |
| 写操作成功后 `turnover_ledger` 仍 refreshing 时页面提前可操作或展示旧分组 | `web/src/test/TurnoverLedgerPage.test.tsx` operation overlay 回归、`web/src/test/OperationBarrierApi.test.ts` |
| queue/outbox 失败后 API 返回成功导致 read model 永久旧 | `tests/test_turnover_ledger_uow_contract.py` rollback tests |
| relation extra legacy full snapshot fallback 误吞持久化问题 | `tests/test_turnover_ledger_api.py` dedicated store / no full snapshot fallback tests |
| 外部往来 API 写 Bankdetail facts 后漏刷 Workbench/Turnover | `test_turnover_bank_row_tag_batch_refreshes_all_required_scopes` |
| 银行标签配置损坏为只有 label 的历史定义，旧确认记录缺外部往来 action，导致台账/关联台无法重建关系 | `tests/test_bank_transaction_category_service.py::BankTransactionCategoryServiceTests.test_legacy_category_record_uses_current_external_definition_semantics`、`tests/test_bank_details_sql_runtime.py::BankDetailSqlProjectionBuilderTests.test_rebuild_enriches_legacy_confirmation_from_current_external_tag_definition` |
| `turnover_ledger:all` 遇到 `bank_detail_read_model_not_fresh` 后自动补投 `bank_detail:all`，与 bank detail 月份 fan-out 互相 bump，页面长期 refreshing 且无数据 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_bank_detail_all_shard_reason_does_not_bump_active_scope` |
| fresh `bank_detail` read model 里缺少部分 transaction id 时被误判为 non-fresh，`downstream_bank_tag_read` 持续刷新月份 shard，台账 all scope 永久 pending | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows` |
| 多个月份中一个 `bank_detail` 月份 pending 时，facade 重刷所有月份，导致已 fresh 月份被快速父重试反复打 pending，台账 all scope 等不到同时 fresh | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes` |
| 测试使用 `TemporaryDirectory(ignore_cleanup_errors=True)` 掩盖后台 job executor 未关闭，导致外部往来写入链路可能在临时目录释放时仍有异步写入残留 | `tests/test_turnover_ledger_api.py` 已切换为严格 `TemporaryDirectory()`；受影响用例在退出临时目录前调用 `app.shutdown_background_jobs()`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api tests.test_historical_etc_business_batch_migration_service -v` 覆盖 136 个严格清理回归 |
| 现代 `/closures/confirm` 同时写 Turnover relation/event 和 Workbench relation，导致 own source version 变化并触发昂贵全量 projection；或 projection 从 `turnover:*` case id 猜出不存在的 relation id，使前端误走旧撤回接口 | canonical-only domain/UoW/integration tests、`test_legacy_turnover_relation_id_requires_explicit_relation_metadata`、write-operation smoke canonical capture/withdraw contract，以及 runtime worker registry/manifest 回归共同保护 |

新增线上或手工发现 bug 时，必须先在本节补复现测试名称，再修实现。

## 关键 Smoke Flow

本地自动化重点保护：

1. 银行明细已确认外部往来分类 -> tag-selection 生效 -> 空 targets -> 当前 grouped normal GET 重新加载。Browser 覆盖保存请求体、零 barrier、reload 和零可见错误。
2. grouped table 选择同组多条真实 flow rows -> 提交前 normal GET并重绑最新 row versions -> Turnover domain 无副作用校验 -> 只写 canonical Workbench pair relation -> 当前页 GET 显示闭环；随后独立访问成本统计，由其两阶段 gate 展示闭环成本行。Browser 覆盖该主链、`收支闭环`、`外部往来闭环成本项目` 和零可见错误。
3. 现代手动闭环统一按 `cash_closure_case_id` 调用 `/api/turnover-ledger/closures/withdraw`，只撤回同一 Workbench case，并恢复确认前的 OA-bank relation；只有元数据显式携带旧 `turnover_relation_id` 的历史闭环才走 `/relations/{id}/withdraw`。已升级为包含发票或其他业务 row type 时必须从关联台撤回；任何失败都不得产生 Turnover 半写入。`web/e2e/turnover-ledger-flow.spec.ts` 已覆盖已闭环 flow row toolbar 撤回和 grouped payload 移除“收支闭环”。
4. extra 保存 -> relation row 更新 -> `turnoverLedgerExtraUpdated` 只作为局部刷新提示。Browser 已覆盖 flow row 打开补充信息 Drawer、GET detail/extra、PUT 保存、当前 Turnover GET 重载、零 operation barrier，并记录 opener/save latency。
5. grouped ledger `read_model_status=stale` -> 页面显示非最新 warning、保留当前 flow rows；即使选中两条真实流水，确认闭环仍禁用，Browser smoke 断言零 confirm mutation。
6. tag-selection / bank-row-tags / confirm / withdraw / extra 只保存各自 canonical facts/version/audit；任一事务失败必须 rollback，成功时必须零 read-model queue I/O。
7. tag-selection / extra / confirm / withdraw -> 只阻塞写请求；manual closure 提交前执行 grouped normal GET/rebind，无法解析精确月份 fail closed；写成功后零 operation barrier并 reload 当前页。Browser 断言不会调用 `POST /api/operation-barrier/status`。

真实环境 smoke 仍需在发布前执行：

- 真实 PostgreSQL 历史数据上刷新 `turnover_ledger` read model。
- 真实 RabbitMQ/Redis/systemd worker drain。
- 浏览器导出 XLSX 文件打开检查；本地已覆盖超过 20,000 行同步导出 fail-closed，但不覆盖真实下载/打开耗时。
- 大数据 grouped table 性能和滚动检查。

## 模块验证命令

后端目标验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_api tests.test_turnover_ledger_export_service tests.test_turnover_relation_service tests.test_turnover_ledger_extra_service tests.test_workbench_turnover_grouping tests.test_turnover_ledger_source_versions tests.test_turnover_ledger_read_model_refresh tests.test_turnover_ledger_read_model_refresh_producer tests.test_turnover_ledger_uow_contract tests.test_turnover_workbench_integration -v
```

前端目标验证：

```bash
cd web && npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx src/test/GlobalOperationOverlayContext.test.tsx src/test/OperationBarrierApi.test.ts src/test/domainEvents.test.ts
cd web && npx playwright test e2e/turnover-ledger-flow.spec.ts
```

文档验证：

```bash
bash scripts/verify.sh docs
```

严格临时目录清理验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api tests.test_historical_etc_business_batch_migration_service -v
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 通过 backend unittest discovery、frontend Vitest、frontend build 和 deterministic Playwright smoke 覆盖本模块。Browser smoke 保护 grouped GET 失败恢复、tag-selection、relation extra Drawer 保存、confirm/withdraw 零 barrier、当前页 reload、Cost 独立访问、grouped recovery 和零可见错误；后端 guards 保护普通写零 fan-out。

## 未测风险

- 真实生产 PostgreSQL 历史数据中的重复、缺字段、半迁移状态，不能由本地 fixture 完全证明。
- 真实 RabbitMQ/Redis/systemd worker drain、网络抖动和 worker 重启恢复需要 staging 或生产前 smoke。
- 大数据量 grouped table、导出 XLSX 文件、浏览器视觉遮挡、mutation 级网络失败和真实下载打开耗时需要真实浏览器/样本验证；本地 Playwright smoke 只覆盖小样本 grouped GET 失败恢复和 confirm/withdraw 主链路。
- 外部往来写路径仍保留 legacy fallback 分支；常规 manual closure/withdraw 已通过 command service 收敛，未来删除 fallback 前需要单独回归。
- 自动标签规则恢复只证明银行明细 read model 可从当前定义补齐历史确认语义；真实生产仍需刷新对应 `bank_detail`、`turnover_ledger`、`workbench_relation`、`workbench` scopes 后验证 open 区可见。

## 2026-07-20 - 有界 SQL 查询、all-scope freshness 与旧链删除

- Business core：业务规则未新增；真实 PostgreSQL integration 覆盖显式 grouped 金额、旧 flat 金额 fallback、borrow-in/borrow-out、family/status、空筛选、四类 family summary 和分页等价。
- Service/API：query repository miss 或依赖缺失统一 fail-closed/enqueue；API grouped/list/freshness/权限和所有写入口回归。
- Read model/job：`tests/test_turnover_ledger_postgres_integration.py` 覆盖规范化 payload-only 持久化、mixed versions、all 聚合月份 pending/processing/failed；source-version schema 固定为 v6。
- Frontend：本轮没有前端实现变化，继续运行 TurnoverLedger API/Page/operation barrier 既有测试。
- E2E：本地已有 confirm/withdraw 主链；生产发布后执行安全可逆写样本和 operation barrier 验证。
- Regression：manifest/architecture/platform guards 证明 query live fallback、direct clear port、raw payload读取和 Python 全量汇总不回归；交叉 Page Audit 保护共享事实消费者。
- 真实 PostgreSQL命令：创建 visibly disposable `fin_ops_test_turnover_phase25`，应用 0001–0113，运行 `tests.test_turnover_ledger_postgres_integration` 后自动删除测试库。
- 剩余风险：生产历史 shard 需要 v6 正式重建后再证明 40 样本 p95、worker drain 和可逆写后可见性；不得用直接 SQL 标记 fresh。

## 2026-07-20 - canonical relation delta 投影

- Business core：金额、分组和状态机不变；既有 turnover domain 测试继续适用。
- Service/read model/job：`tests/test_turnover_ledger_read_model_refresh.py` 证明只有精确 month、`relation_deltas + row_ids` 事件进入窄投影，`all` 和非 relation 事件仍走完整 rebuild；窄投影不调用 ledger own-source builder。
- Repository/真实 PostgreSQL：`tests/test_postgres_repositories_boundaries.py` 证明 overlap SQL 和无 scope delete；`tests/test_turnover_ledger_postgres_integration.py` 证明只更新 overlap payload、保留非目标业务 payload，并把同月所有 row/table source versions 推进到一致值。
- API/Frontend：response shape、operation barrier targets 与 UI 不变，不新增专项测试；既有 API/Page/E2E 回归继续保护。
- Existing regression：manifest port contract、full projection、query freshness、Workbench relation canonical bundle 与跨页面 Audit 均需复跑。
- 生产门：确认/撤回各三轮，command p95 `<=1000ms`、response-to-fresh p95 `<=2000ms`、hard max `<=3000ms`；最终 fixture unlinked、queue drained、直接与交叉 Audit 通过。

## 2026-07-22 - 历史 requirement snapshot 可逆修复

- Business core：repair 回归覆盖 active Turnover 旧 source、缺 tag/version、真实规则覆盖旧写死 requirements，以及 ordinary missing snapshot、ETC、batch 和 inactive 豁免合同。
- Service：forward fingerprint 同时绑定完整 metadata preimage 与 intended after image；partial execute、partial rollback、幂等重放和任一 drift 首写前零写入均有测试。rollback 通过现有 command 原地精确恢复 metadata，不 cancel/recreate relation。
- Read model：Workbench month/all 升级 v6 后，旧 v5 generation 与派生 cache key 均不能冒充 fresh；生产 repair、rehydrate 和可逆写证据必须停在受控 operator checkpoint 执行。

## 2026-07-25 - Turnover 专属 relation eligibility

- `tests/test_turnover_ledger_postgres_integration.py` 证明 `turnover_manual_closure` 继续推进 Turnover 自身 canonical proof，但不推进共享 relation source version。
- `tests/test_audit_page_business_read_model_tool.py` 证明 Turnover Audit 的共享 edge 子集排除该专属 mode；Turnover row/source freshness 与 Workbench 主 generation 仍覆盖真实 closure。

# 关联台关系事实源 实施记录

## 2026-06-13 - fresh scope partial row 缺失不阻断下游读模型

目标：修复 invoice usage / output collection read model 在读取 `workbench_relation` distribution 时，因为同一 fresh scope 中个别 row 缺失而把整页判为 non-fresh 的问题。

结论：

- `workbench_relation` scope 本身仍是 freshness 事实源；scope missing/stale/refreshing 必须继续阻断并入队。
- 对 `get_by_row_ids`，如果已返回 row 所属 scope 都是 fresh，部分请求 row 不存在时返回 fresh 的已有 rows；调用方把缺失 row 视为无 relation / unlinked。
- 这样不会伪造 relation fact，也不会绕过 stale scope；只是避免 fresh scope 中一个无关系或已缺席 row 让整个月份下游 read model 长期 refreshing。

验证：

- `tests/test_workbench_relation_read_facade.py::WorkbenchRelationReadFacadeTests::test_repository_treats_missing_row_in_fresh_scope_as_unlinked_context`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_read_facade tests.test_workbench_relation_sql_projection -q`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api tests.test_invoice_usage_collection_sql_runtime -q`

## 2026-06-12 Phase 7O Downstream candidate closure

目标：把 `WorkbenchRelationReadFacade` 分发的 `relation_status='candidate'` 显式传递到各下游页面，同时保持所有业务金额、状态、占用和冲突判断只使用 `linked`。

结论：

- OA 待付款、待找发票、销项发票收款、银行明细、进项发票使用情况均保留 candidate relation status 并在前端显示“候选”或“候选oa/候选发票”。
- `InvoiceRelationQueryContext`、pending invoice live service 和 pending invoice SQL projection 统一保留 `relationStatus/relation_status`；candidate 不再被映射成默认 active/linked。
- OA 待付款的 `paidTotal` / 支付状态、销项发票收款的 `receivedTotal` / 收款状态、待找发票的 `can_create_invoice` / paid pending 状态均只按 linked 关系计算。
- 银行明细 relation tag 由 distribution 生成，candidate 显示为 `候选oa` / `候选发票`，同时保留机器字段 `relation_status='candidate'`。
- 成本、税金、搜索等不一定展示候选 chip 的下游不能把 candidate 当 confirmed relation 参与金额或状态计算；搜索 pending invoice projection 已保留 candidate relation status 且 linked-only 计算付款汇总，成本统计 live service 和 SQL projection 均显式排除 Workbench open/proposed candidate 成本行。

验证：

- `PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py tests/test_input_invoice_usage_service.py tests/test_input_invoice_usage_api.py tests/test_invoice_usage_collection_sql_runtime.py tests/test_oa_pending_payment_api.py tests/test_output_invoice_collection_service.py tests/test_bank_details_service.py tests/test_pending_invoice_service.py tests/test_search_pending_sql_runtime.py tests/test_cost_statistics_service.py tests/test_cost_statistics_sql_runtime.py -q`
- `PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_read_models_use_workbench_relation_distribution tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_details_relation_tags_only_read_relation_distribution_facade -q`
- `cd web && npm test -- --run src/test/BankDetailsApi.test.ts src/test/BankDetailsPage.test.tsx src/test/OaPendingPaymentsPage.test.tsx src/test/OutputInvoiceCollectionsPage.test.tsx src/test/PendingInvoicesApi.test.ts`
- `cd web && npm test -- --run src/test/PendingInvoicesPage.test.tsx`
- `cd web && npm run build`

## 2026-06-12 Phase 7N Workbench relation candidate distribution

目标：把关联台未配对区 open/proposed 自动候选也纳入 `WorkbenchRelationReadFacade` 的统一只读分发，避免进项发票使用情况等下游页面直接读取旧候选链路或看不到候选关系。

结论：

- `workbench_relation` SQL projection 同时分发 active/paired linked 关系和 open/proposed candidate 关系。
- distribution group/row payload 保留 `relation_status`，下游 mapper 不再把所有 group 硬编码为 `status=active`。
- `relation_status=candidate` 只表示关联台候选展示上下文，不写入 `app.workbench_pair_relations`，不作为 confirmed fact、支付完成判断或 row 占用事实。
- 进项发票使用情况继续通过 `WorkbenchRelationReadFacade` 消费关系上下文，展示 candidate 证据，但支付状态只按 linked 关系计算。

验证：

- `tests/test_workbench_relation_sql_projection.py::WorkbenchRelationSqlProjectionTests::test_rebuild_distributes_open_reconciliation_decision_as_candidate_relation`
- `tests/test_workbench_relation_read_facade.py::WorkbenchRelationReadFacadeTests::test_distribution_mapper_preserves_candidate_relation_status`
- `tests/test_input_invoice_usage_service.py::InputInvoiceUsageQueryServiceTests::test_candidate_relations_are_displayed_without_marking_invoice_paid`

## 2026-06-12 Phase 7M Workbench withdraw command 边界与 candidate split

目标：把关联台 `withdraw-link` preview/submit 从 `WorkbenchWriteFacade -> WorkbenchPairRelationService` direct path 迁到 `WorkbenchRelationCommandService`，同时支持未配对区纯自动候选 group 的统一按钮 split/suppress。

结论：

- `WorkbenchRelationCommandService.preview_withdraw_relation` 返回 locked preview：`operation_type=withdraw_relation`、`preview_id`、`submit_expected_versions`、before/after relations。
- `WorkbenchRelationCommandService.withdraw_relation` 校验 preview id 和 expected versions；不匹配时返回 `workbench_relation_preview_conflict`，避免 stale submit 撤回当前新关系。
- `WorkbenchWriteFacade.preview_withdraw_link` 只负责 HTTP payload 组装和三栏 preview groups；relation 判断委托 command service。
- active relation 无 history 时撤到无关联，不再由 facade 合成 OA 附件恢复关系。
- withdraw preview after 中未进入 restored relation 的 row 必须逐行独立展示；facade/server grouping 不能继续按旧 `case_id` 合并这些 row。
- `split_candidate` 不进入 relation command service，不写 relation history；它复用 `WorkbenchCandidateMatchService.mark_candidates_suppressed(..., suppressed_reason="manual_override")`，并触发 workbench refresh。

验证：

- `tests/test_workbench_relation_command_service.py`
- `tests/test_workbench_auth_context_idempotency.py`
- `tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_preview_after_groups_unrestored_bank_invoice_rows_individually`
- `tests/test_workbench_v2_api.py -k withdraw_link`
- `tests/test_workbench_write_characterization.py -k withdraw_link`
- `web/src/test/WorkbenchSelection.test.tsx`
- `web/src/test/WorkbenchSelectionModel.test.ts`
- `npm --prefix web run build`

## 2026-06-11 Phase 0 架构盘点

目标：设计 `workbench_relations` 后端模块，把 OA、银行流水、正式发票、OA 附件发票之间的配对/解除配对/撤回/关闭/挂接关系收敛到同一事实源，避免页面、service 和 read model 各自维护独立事实。

本阶段只做架构盘点和文档设计，不改业务代码。

## 结论

推荐中间方案：抽出正式 `workbench_relations` 后端模块，但复用现有事实源和实现。

不新建第二套 relation fact table；canonical write model 仍是 `app.workbench_pair_relations` 和 `app.workbench_pair_relation_history`。`workbench_relation` read model 继续负责跨页面 distribution。`WorkbenchRelationReadFacade` 继续作为下游页面唯一读入口。`WorkbenchPairRelationService` 保留为纯领域规则对象。

需要新增或迁移的边界：

- `WorkbenchRelationCommandService`
- `PostgresWorkbenchRelationRepository`
- relation mode/state registry
- affected scope calculator
- command result DTO / error contract
- architecture guard tests

## 现状证据

- `docs/modules/reconciliation-workbench/README.md` 已定义 Workbench active pair relation 是 OA、银行流水、发票跨页面关系的唯一已配对事实。
- `docs/architecture/persistence-and-read-models.md` 已定义 `workbench_relation` distribution read model 和 `WorkbenchRelationReadFacade` 下游唯一读取入口。
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py` 目前持有 relation load/save/history/dirty scope 和 downstream refresh 入队逻辑。
- `backend/src/fin_ops_platform/app/server.py` 目前持有 `_workbench_pair_relation_service`、persist helper、confirm preview、repair、ETC cancel、OA invoice offset auto pair 等 relation 业务逻辑。
- `tests/test_platform_runtime_boundary_guards.py` 已禁止部分下游 relation 读绕过 facade，但尚未禁止 relation 写入口绕过 command service。

## 设计决策

1. 只抽 relation lifecycle，不抽 OA、发票、银行流水源事实。
2. 先抽 repository，再建 command service，再迁移写入口，最后删除旧 helper。
3. 写入口必须 fail fast 处理 non-fresh relation read model、version conflict、active row overlap 和 idempotency conflict。
4. history 是审计事实，迁移时必须保留 before/after、actor、reason、affected months、source versions。
5. 前端事件只能做刷新提示，所有页面最终以 mount/refetch 后端状态为准。
6. 旧逻辑删除是上线验收项，不是可选优化。

## 分阶段计划

### Phase 1：Repository 抽离

新增 `PostgresWorkbenchRelationRepository`，从 `PostgresWorkbenchRepository` 搬迁：

- relation load/save。
- relation history replace/load。
- dirty scope 推导。
- transaction-bound downstream refresh enqueue。

验收：

- 行为等价。
- 现有 repository/postgres runtime 测试通过。
- `PostgresWorkbenchRepository` relation 方法只允许短期代理到新 repository。

### Phase 2：Command service

新增 `WorkbenchRelationCommandService`，统一封装：

- confirm/cancel/withdraw。
- attach existing/create manual invoice relation。
- no-OA submit/withdraw。
- turnover closure/withdraw。
- batch accounting submit/withdraw。
- ETC repair/delete。
- input invoice OA reverse。

验收：

- 领域规则仍由 `WorkbenchPairRelationService` 执行。
- command service 统一返回 relation、changed case ids、affected months、version、read model refresh result。
- non-fresh/version/idempotency/overlap/audit 测试齐全。

### Phase 3：迁移写入口

按风险小到大迁移：

1. workbench confirm/cancel。
2. batch accounting submit/withdraw。
3. pending invoice attach/create。
4. no-OA submit/withdraw/internal transfer confirm-link。
5. turnover closure/withdraw。
6. ETC repair/delete 和 historical migration。
7. input invoice OA reverse。

验收：

- 所有生产写入口不再直接持有 `WorkbenchPairRelationService`。
- `server.py` 只保留 HTTP mapping 和 dependency wiring。
- 旧 helper 删除。

### Phase 4：读入口和 freshness

审计所有 relation 读入口：

- 下游页面只通过 `WorkbenchRelationReadFacade` 或 request-scoped context。
- 写 API 再次校验 fresh 或 write model version。
- API response 显式返回 read model 状态。

验收：

- boundary guard tests 扩展并通过。
- 非 fresh 时不把空 rows 当真实未提交。

### Phase 5：前端反馈闭环

确认所有相关页面在 relation mutation 后重新拉取后端状态：

- 关联台。
- bank detail。
- pending invoice。
- input/output invoice。
- OA pending。
- no-OA。
- turnover。
- batch accounting。
- cost/tax/search。

验收：

- event 只触发刷新提示。
- stale/refreshing/failure 有用户可见反馈或阻断写入。

### Phase 6：迁移、repair、回滚

覆盖：

- Mongo snapshot / shadow read。
- historical relation history。
- ETC repair tools。
- no-OA legacy relation migration。
- data reset。

验收：

- migration dry-run/report 能发现重复 active row、缺失 history、orphan relation。
- 回滚路径不产生第二事实源。

### Phase 7：删除旧逻辑和守卫

删除：

- `server.py` relation persist/sync/apply/repair business helper。
- direct pair service write ports。
- repository 兼容代理。

新增守卫：

- 禁止 downstream service 直接接收 pair service。
- 禁止 relation 写入口绕过 command service。
- 禁止 `server.py` 新增 relation 业务流程。

### Phase 8：全量验证和文档收口

更新：

- module docs。
- app architecture。
- API contracts。
- testing closure map。

执行：

- backend focused tests。
- frontend focused tests。
- read model worker tests。
- e2e/integration smoke。

## 风险

- 并发下 row overlap 仅靠当前内存服务不够，需要 command service 在事务内补锁或引入 row occupation 约束。
- pending invoice/no-OA/turnover/batch accounting 现有 idempotency 口径不同，需要统一但不能破坏旧 API。
- `server.py` 当前 relation 逻辑多，删除必须分阶段，避免一次性重构造成行为回归。
- app Mongo snapshot、shadow read、repair 工具仍处在迁移观察期，不能被误删。
- frontend event 覆盖范围不等于事实一致性，必须以后端 read model refetch 验证。

## Phase 0 验收

- 已新增 `workbench-relations` 资源模块文档。
- 已登记模块索引。
- 已记录事实源、目标边界、旧逻辑删除清单、迁移顺序和测试矩阵。
- 未修改业务代码。

## 2026-06-12 Phase 7F no-OA read model repair 隐式写入口剥离

目标：阻止 `no_oa_bank_batch.read_model.refresh` 在重建 no-OA read model 时顺手执行 legacy relation migration/repair/consolidation，避免 worker 成为隐藏 relation 写入口。

改动：

- `NoOaBankBatchService.build_batches(...)` 增加 `apply_relation_repairs` 参数，默认保持旧兼容行为。
- `NoOaBankBatchApplicationService.refresh_batches(...)` 暴露 `apply_relation_repairs`，并且只有启用 repair 时才根据 `last_legacy_migration_result` 触发 relation/workbench persist。
- `NoOaBankBatchReadModelRefreshService` 固定调用 `refresh_batches(apply_relation_repairs=False)`，worker 只保存 no-OA snapshot。
- `tests/test_no_oa_bank_batch_read_model_refresh.py` 新增 regression，证明已提交 no-OA 批次缺失 relation 时，worker 不创建 pair relation、不保存 relation mutation。
- `tests/test_platform_runtime_boundary_guards.py` 新增源码级 guard，防止 no-OA worker 重新启用 relation repair 或直接调用 pair relation 写入。

剩余风险：

- no-OA legacy migration、submitted repair、category drift cleanup 本体仍存在 direct pair write 兼容路径；后续应迁移为显式 `WorkbenchRelationCommandService` repair command 或离线 repair 工具。

## 2026-06-12 Phase 7G Workbench confirm/cancel direct fallback 删除

目标：删除关联台 `confirm-link` / `cancel-link` 主写入口在 command service 缺失时回退到 `WorkbenchPairRelationService` 直接写 pair snapshot 的 legacy fallback。

改动：

- `WorkbenchWriteFacade.confirm_link` 非 UoW 路径缺 command service 时返回 `workbench_relation_command_unavailable`。
- `WorkbenchWriteFacade.cancel_link` 非 UoW 路径缺 command service 时返回 `workbench_relation_command_unavailable`。
- `_confirm_link_with_uow` 和 `_cancel_link_with_uow` 的 handler 必须通过 transaction-bound relation command service 写入；不再调用 `_persist_pair_relations_in_transaction` 旧 hook。
- 保留 idempotency replay/in-progress 在 UoW handler 前的行为，避免稳定重放被错误映射为 command 缺失。
- `tests/test_workbench_write_characterization.py` 的 UoW fake 改为记录 transaction-bound relation repository 写入，而不是旧 persist hook。
- `tests/test_platform_runtime_boundary_guards.py` 新增 `test_workbench_confirm_and_cancel_link_have_no_direct_pair_write_fallback`。

剩余风险：

- Workbench-adjacent 写入口中的个人暂借款、exception closed apply、server OA offset auto pair 和 OA 附件上下文 repair 后续已分别在 Phase 7H/7I/7J 迁移；`server.py` 仍有 relation 读/展示/persist helper，后续需继续抽离。

## 2026-06-12 Phase 7H 个人暂借款 relation 写入口收敛

目标：把关联台个人暂借款还清 `confirm_personal_advance_repayment` 的 special relation 写入收敛到 `WorkbenchRelationCommandService`，删除 facade 内 direct `replace_with_confirmed_relation`。

改动：

- `WorkbenchRelationCommandService` relation mode registry 增加 `personal_advance_repayment_settlement`。
- `WorkbenchWriteFacade.confirm_personal_advance_repayment` 在创建 exception case 前要求 relation command service 可用；缺失时返回 `workbench_relation_command_unavailable`，不先写本地 exception case。
- 个人暂借款 relation 通过 `confirm_relation(..., replace_existing=True, history_operation_type="confirm_personal_advance_repayment")` 写入，保留原有 `amount_check`、`special_metadata.cost_policy=exclude_all` 和 response shape。
- relation command non-fresh/idempotency/active overlap 等错误复用统一 command error mapping，并回滚 exception/pair snapshot。
- `tests/test_workbench_auth_context_idempotency.py` 新增 command 委托和缺 command fail-fast 测试。
- `tests/test_platform_runtime_boundary_guards.py` 新增个人暂借款禁止 direct pair fallback 的源码级 guard。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_personal_advance_repayment_delegates_relation_write_to_command_service tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_personal_advance_repayment_fails_fast_without_relation_command_service -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_confirm_personal_advance_repayment_creates_settled_case_and_pair_relation tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_confirm_personal_advance_repayment_rejects_unbalanced_amounts tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_confirm_personal_advance_repayment_rejects_missing_bank_credit_or_debit tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_confirm_personal_advance_repayment_rejects_invoice_rows -q
```

剩余风险：

- Workbench exception closed apply 后续已在 Phase 7I 迁移，server OA offset auto pair 和 OA 附件上下文 repair 后续已在 Phase 7J 迁移，batch accounting repair 后续已在 Phase 7K 迁移；no-OA legacy repair/consolidation 仍有 direct pair write，后续需迁移为 command service 或显式 repair 工具。

## 2026-06-12 Phase 7I Workbench exception apply relation 写入口收敛

目标：把 `WorkbenchExceptionApplicationService.apply(...)` 中 closed exception 产生的 `normal_match` / `oa_exempt` relation 写入收敛到 `WorkbenchRelationCommandService`，避免 exception application 自己成为第二个 relation 写事实源。

改动：

- `WorkbenchRelationCommandService` relation mode registry 增加 `normal_match` 和 `oa_exempt`。
- `WorkbenchExceptionApplicationService` 接收明确的 `relation_command_service` 依赖；closed action 在创建本地 exception case 前先调用 command service write precondition，缺 command 或 relation read model non-fresh 时 fail fast。
- `_create_pair_relation(...)` 改为调用 `confirm_relation(..., history_operation_type="workbench_exception_apply")`，保留 `amount_check`、`exception_case_id`、`rule_version`、`evidence`、`oa_exemption`、`display_tags` 和 `special_metadata.source=workbench_exception_application`。
- `WorkbenchWriteFacade.apply_exception` 捕获 `WorkbenchRelationCommandError` 并恢复 exception/pair/candidate/override snapshots，避免 command 失败后留下半写入 case。
- `Application._configure_workbench_exception_application_service` 注入 `_workbench_relation_command_service()`。
- `tests/test_platform_runtime_boundary_guards.py` 新增源码级 guard，防止 exception apply 重新出现 direct pair write fallback。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_exception_application_service.py::WorkbenchExceptionApplicationServiceTests::test_apply_closed_exception_delegates_pair_relation_to_command_service tests/test_workbench_exception_application_service.py::WorkbenchExceptionApplicationServiceTests::test_apply_three_party_closed_creates_closed_case_and_pair_relation tests/test_workbench_exception_application_service.py::WorkbenchExceptionApplicationServiceTests::test_apply_auto_oa_exempt_writes_structured_relation_fields tests/test_workbench_exception_application_service.py::WorkbenchExceptionApplicationServiceTests::test_apply_manual_oa_exempt_writes_confirmer_timestamp_and_note -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_exception_application_uses_relation_command_boundary -q
```

已观察结果：

- exception application targeted：4 passed。
- relation command service：9 passed。
- boundary guard targeted：1 passed。

七类测试覆盖：

- Business core unit tests：适用并覆盖 closed exception relation mode、OA exemption metadata 和缺 direct pair write。
- Service-layer tests：适用并覆盖 exception application 到 relation command service 的委托、preflight 和 snapshot rollback。
- API contract tests：适用并通过后续 Workbench API 回归覆盖旧 response shape；本阶段未新增 HTTP 字段。
- Read model/cache/background job tests：适用并由 command service freshness precondition 与 boundary guard 覆盖，不让 exception apply 绕过 relation read model。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并保留 exception apply relation targeted 回归；真实跨页面 worker drain 仍待后续 smoke。
- Existing feature regression tests：适用并保留三方闭环、自动/手动免 OA structured fields 和 command service 全量单测。

剩余风险：

- server OA offset auto pair 和 OA 附件上下文 repair 后续已在 Phase 7J 迁移；no-OA legacy repair/consolidation 和 batch accounting repair 仍有 direct pair write，后续需迁移为 command service 或显式 repair 工具。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7J server active relation repair direct mutation 收敛

目标：删除 `server.py` 中 OA invoice offset auto pair 和 OA 附件上下文 repair 对 `WorkbenchPairRelationService.create_active_relation/cancel_relation/record_history` 的直接写入，改由 `WorkbenchRelationCommandService` 统一写 relation 和 history。

改动：

- `WorkbenchRelationCommandService` relation mode registry 增加 `oa_invoice_offset_auto_match`。
- `WorkbenchPairRelationService.replace_with_confirmed_relation(...)` 增加 `operation_type`、`history_created_by` 和 `history_note` 参数；默认保持 `confirm_link`，command service 可以在 repair 场景保留专用审计 operation/reason。
- `WorkbenchRelationCommandService.confirm_relation(...)` 增加 `relation_created_by` 和 `history_note`，使 repair 可以保留原 relation `created_by/note`，同时用 `system_repair` 和 repair reason 写 audit history。
- `_sync_oa_invoice_offset_auto_pair_relations(...)` 改为通过 `confirm_relation(...)` 创建/修正 `oa_invoice_offset_auto_match`，通过 `cancel_relation(...)` 撤销当前 payload 涉及但不再存在的自动关系；仍保留原有 scanned row 保护和外层 persist/lifecycle。
- `_repair_active_relations_with_oa_attachment_context(...)` 改为通过 `confirm_relation(..., replace_existing=True, history_operation_type="repair_missing_oa_attachment_context")` 修复同一 case 的 row_ids/row_types/amount_check，保留原 relation metadata 和 repair history 语义。
- `tests/test_platform_runtime_boundary_guards.py` 新增 server active relation repair command boundary guard。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_confirm_relation_allows_oa_invoice_offset_auto_match_mode tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_replace_existing_confirm_uses_requested_history_operation_type tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_server_active_relation_repairs_use_relation_command_boundary -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_get_api_workbench_auto_pairs_offset_applicant_oa_with_attachment_invoice tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_invoice_offset_sync_does_not_cancel_relations_outside_current_payload tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_oa_invoice_offset_sync_only_uses_attachment_source_link_not_case_id tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_read_model_repairs_active_relation_missing_oa_attachment_invoice -q
```

已观察结果：

- command/boundary targeted：3 passed。
- Workbench API targeted：4 passed。

七类测试覆盖：

- Business core unit tests：适用并覆盖 `oa_invoice_offset_auto_match` mode registry、replace-existing repair history operation。
- Service-layer tests：适用并覆盖 command service replace-existing history override、relation_created_by/history_note 分离。
- API contract tests：适用并通过 Workbench API targeted 回归覆盖 OA offset auto closed payload、当前 payload 范围保护、附件上下文 repair。
- Read model/cache/background job tests：适用；本阶段保留原有 read-build repair 触发点，但写入已通过 command service 和统一 history。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并通过 Workbench API targeted 路径覆盖从 payload build 到 relation repair/group 展示；真实 worker drain 仍待后续 smoke。
- Existing feature regression tests：适用并保留 OA offset source link、防止跨 payload 误取消、missing attachment repair 回归。

剩余风险：

- `server.py` 仍保留 relation 读/展示/persist helper；Phase 7J 只移除 direct pair mutation，不等于 server relation 业务完全抽离。
- no-OA legacy repair/consolidation 仍有 direct pair write。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7K batch accounting legacy repair 写入口收敛

目标：把 `BatchAccountingService.repair_legacy_case_id_collisions(...)` 从 direct `WorkbenchPairRelationService.create_active_relation/record_history` 迁到 `WorkbenchRelationCommandService.confirm_relation(...)`，避免批量账务历史修复路径绕过统一 relation lifecycle。

改动：

- repair 仅在确实需要恢复 relation 时要求 `relation_command_service`；缺 command service 时抛 `batch_accounting_relation_command_unavailable`，不再 direct pair fallback。
- 恢复 relation 通过 `confirm_relation(..., history_operation_type="repair_batch_accounting_relation_id_collision")` 写入，保留 `legacy_case_id`、`repair_source=batch_accounting_case_id_collision`、`repaired_at`、amount check 和 owner metadata。
- 现有不恢复 withdrawn relation、不覆盖当前非 batch relation、metadata stale 时使用真实 bank row 的业务规则保持不变。
- `tests/test_platform_runtime_boundary_guards.py` 新增 batch accounting repair command boundary guard。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_repair_legacy_case_id_collision_delegates_relation_write_to_command_service tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_repair_legacy_case_id_collision_requires_relation_command_service_without_direct_pair_fallback tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_batch_accounting_repair_has_no_direct_pair_write_fallback -q
PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py -q
```

已观察结果：

- repair targeted：3 passed。
- batch accounting API/service：35 passed。

七类测试覆盖：

- Business core unit tests：适用并保留 legacy collision repair 的恢复/不恢复/不覆盖/stale metadata 规则。
- Service-layer tests：适用并覆盖 repair command delegation、缺 command fail-fast 和 direct fallback 删除。
- API contract tests：本阶段未改 HTTP response shape；Application 已注入 command service。
- Read model/cache/background job tests：适用并保留 repair result 的 changed case ids / affected rows / affected months 供 Application 调度。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并保留 batch accounting service/API 回归；真实 worker drain 仍待后续 smoke。
- Existing feature regression tests：适用并保留 legacy case id collision 全套回归。

剩余风险：

- no-OA legacy repair/consolidation 后续已在 Phase 7L 迁入 command service。
- `server.py` 仍保留 relation 读/展示/persist helper；Phase 7J/7K 只移除 direct pair mutation，不等于 server relation 业务完全抽离。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7L no-OA legacy repair/consolidation 写入口收敛

目标：把 `NoOaLegacyRelationMigrationService` 和 `NoOaBankBatchService.build_batches(..., apply_relation_repairs=True)` 中的 legacy relation migration、submitted relation repair、category drift cleanup、submitted single-side consolidation 从 direct pair service mutation 迁到 `WorkbenchRelationCommandService`。

改动：

- `NoOaLegacyRelationMigrationService` 新增明确的 `relation_command_service` 依赖；legacy cancel 与 no-OA confirm 均通过 command service 执行，缺 command service 时抛 `no_oa_relation_command_unavailable`。
- `NoOaBankBatchService` 新增 `_confirm_no_oa_relation(...)` 和 `_cancel_no_oa_relation(...)` command helper，legacy/repair/consolidation 路径不再调用 `_pair_relation_service.create_active_relation/cancel_relation/record_history`。
- `Application` 和 no-OA application service 测试 fixture 注入 `WorkbenchRelationCommandService(require_fresh_relations=False)`，用于显式 repair 路径复用统一 command/history/snapshot 边界。
- 已有 current submitted no-OA batch 与 legacy active relation 命中同一 row set 时，迁移复用 existing submitted batch 的 relation case，避免创建第二条 active relation。
- submitted repair 遇到 row 已被非 no-OA active relation 占用时跳过重建 no-OA relation，并记录 skipped reason，避免 repair 抢占其他 active fact。
- `tests/test_platform_runtime_boundary_guards.py` 新增 no-OA legacy repair/consolidation direct pair write guard。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_service.py tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback -q
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_service.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_workbench_integration.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py tests/test_workbench_relation_command_service.py tests/test_workbench_v2_api.py tests/test_batch_accounting_api.py -q
```

已观察结果：

- no-OA service + targeted guard：28 passed。
- no-OA service/application/read-model/API/workbench integration：68 passed。
- platform runtime boundary guard + relation command + workbench v2 + batch accounting：233 passed。

七类测试覆盖：

- Business core unit tests：适用并覆盖 legacy migration、submitted repair、category drift、single-side consolidation、active row occupation 和 existing submitted batch case reuse。
- Service-layer tests：适用并覆盖 no-OA legacy/repair 到 command service 的委托、缺 command fail-fast 和 direct fallback 删除。
- API contract tests：本阶段未改 HTTP response shape；no-OA API 回归保护旧 contract。
- Read model/cache/background job tests：适用并继续覆盖 no-OA worker refresh 不执行 relation repair。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并通过 no-OA workbench integration 保护 Workbench/no-OA 同一 active relation fact。
- Existing feature regression tests：适用并保留 legacy salary/internal transfer、stale/category drift、consolidation、Workbench v2 和 batch accounting 回归。

剩余风险：

- `server.py` 仍保留 relation 读/展示/persist helper；本阶段只收敛 no-OA legacy/repair 写入口。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 真实 PostgreSQL 历史 no-OA 数据全量回放、repair dry-run 和前端跨页面浏览器 smoke 仍需 staging/发布前验证。

## 2026-06-12 PostgreSQL history dry-run/replay

目标：在不写生产数据库的前提下，回放检查 `app.workbench_pair_relations`、`app.workbench_pair_relation_history` 和 `workbench_relation` readiness，确认历史数据是否存在会阻断后续 row occupation 约束或 command service 并发治理的脏数据。

改动：

- 新增 `backend/src/fin_ops_platform/tools/workbench_relation_history_replay.py`，作为只读 dry-run 工具。
- 工具只执行 `select`，输出 JSON 报告；`--fail-on-issues` 仅用于 CI/release gate，人工生产巡检默认不加。
- 检查项覆盖 active row 多 case 占用、row_ids/row_types 长度不一致、active relation 空 row、relation 内重复 row、未注册 relation mode、payload case_id mismatch、relation/history 不一致和 `workbench_relation` readiness 非 fresh。
- 未注册 mode 的严重级别区分 active 与历史非 active：active 未注册 mode 是 error；cancelled/withdrawn/superseded 等历史非 active 未注册 mode 是 warning，避免把旧兼容历史误判为当前事实冲突。
- 新增 `tests/test_workbench_relation_history_replay_tool.py`，覆盖 dry-run 不写库、issue 输出、`--fail-on-issues` 和 active/历史非 active mode severity。

生产 dry-run 结果：

- 运行位置：生产服务器当前 release 环境，使用 `/etc/fin-ops/fin-ops.common.env` 和 `/etc/fin-ops/fin-ops.secrets.env` 中的 PostgreSQL 连接信息。
- 报告已保存到服务器 root-only 路径：`/opt/fin-ops/data/manual-hotfix-backups/20260612_workbench_relation_history_replay/report.json`。
- `relation_count=154`，`active_relation_count=49`，`history_case_count=24`，`readiness_row_count=6`。
- `issue_count=175`，其中 `error_count=0`，`warning_count=175`。
- warning 分布：`relation_without_history=132`，`unknown_relation_mode=41`，`orphan_history_case=2`。
- `workbench_relation` readiness 覆盖 2025-12 到 2026-05 共 6 个 scope，状态均为 `fresh`，schema 为 `2026-06-workbench-relation-object-identity-v1`。

判读：

- 没有发现 active row 被多个 active case 占用。
- 没有发现 row_ids/row_types 长度不一致。
- 没有发现 active 未注册 relation mode。
- 41 条未注册 mode 均为 cancelled 历史数据，分布为 `internal_transfer_pair=14`、`salary_personal_auto_match=27`，不是当前 active fact 冲突。
- 132 条缺 history 是审计完整性问题，其中 active 缺 history 包含 `manual_confirmed=1`、`no_oa_bank_batch=28`、`oa_invoice_offset_auto_match=1`；其余为 cancelled 历史数据。
- 2 条 orphan history 表示 history 存在但当前 relation 表无对应 case，应纳入后续审计 backfill/repair 设计。

后续建议：

- 不需要因为 row occupation 冲突紧急修复生产数据；后续可以先设计 PostgreSQL 并发占用锁或唯一约束的 shadow/dry-run gate。
- 需要单独设计 audit history backfill：先只生成 proposed history rows 和 before/after 摘要，再人工确认是否写入，不能在 replay 工具中自动修复。
- `internal_transfer_pair` 和 `salary_personal_auto_match` 是否加入历史 allowlist，应作为兼容展示/审计决策处理，不应重新开放为新增 active write mode。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_history_replay_tool.py -q
```

七类测试覆盖：

- Business core unit tests：适用并覆盖 active/历史非 active mode severity、active row occupation 和 row shape issue 分类。
- Service-layer tests：适用并覆盖 PostgreSQL relation/history/readiness 只读巡检 orchestration。
- API contract tests：本阶段未改 HTTP/API contract，不适用。
- Read model/cache/background job tests：适用并覆盖 `workbench_relation` readiness missing/not fresh 报告。
- Frontend component and interaction tests：本阶段未改前端，不适用。
- End-to-end business-flow integration tests：本阶段是生产历史只读巡检，不改业务 flow；不适用。
- Existing feature regression tests：适用并通过只读测试保护 replay 工具不会写库或修复数据。

## 2026-06-11 Phase 1 Repository 抽离

目标：先把 PostgreSQL relation 专属 load/save/history/dirty scope/downstream refresh 逻辑从 `PostgresWorkbenchRepository` 抽出，保持外部行为等价，为后续 command service 做持久化边界准备。

改动：

- 新增 `backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py`。
- `PostgresWorkbenchRelationRepository` 承接：
  - `load_workbench_pair_relations`。
  - `save_workbench_pair_relations`。
  - `app.workbench_pair_relation_history` replace/load。
  - relation dirty scope 推导。
  - `workbench_relation` 与 downstream read model 的事务内 dirty/outbox 入队。
- `PostgresWorkbenchRepository` 保留同名方法作为短期兼容代理，内部只转调新 repository，不再持有 relation SQL 主实现。
- `PostgresStateStore` 直接注入并使用 `PostgresWorkbenchRelationRepository` 读写 pair relations。
- `postgres_repositories.__init__` 导出新 repository。
- `tests/test_postgres_repositories_boundaries.py` 新增新 repository 直接读取测试、旧 repository 代理测试和旧 repository 禁止 relation SQL 的守卫。
- `tests/test_postgres_repositories_boundaries.py` 同时覆盖新 repository 写入 relation、history、dirty scope 和 outbox refresh。
- `tests/test_platform_runtime_boundary_guards.py` 将新 relation repository 加入事务内 durable queue writer 允许列表；业务 service 仍不允许直接写 outbox/dirty scope。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_core.py tests/test_app_postgres_mode.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py -q
```

结果：

- `tests/test_postgres_repositories_boundaries.py`：16 passed。
- repository/postgres/read facade/projection 聚焦组合：19 passed，存在既有 SWIG deprecation warnings。
- `tests/test_platform_runtime_boundary_guards.py`：27 passed，存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：本阶段未改领域规则，不适用；已有 `WorkbenchPairRelationService` 测试继续作为后续 Phase 2 基线。
- Service-layer tests：适用并已覆盖 repository 抽离、旧 repository 代理和 durable queue writer 允许边界。
- API contract tests：本阶段未改 HTTP/API contract，不适用。
- Read model/cache/background job tests：适用并通过 read facade/projection 与 boundary guard 聚焦测试保护。
- Frontend component and interaction tests：本阶段未改前端，不适用。
- End-to-end business-flow integration tests：本阶段只抽 repository，不改变业务流程；后续写入口迁移阶段必须补。
- Existing feature regression tests：适用并通过 postgres mode、read facade、projection 和 boundary tests 做回归保护。

剩余风险：

- 旧 `PostgresWorkbenchRepository` 代理仍存在，Phase 7 必须删除或进一步收紧守卫。
- 事务内 queue 入队 helper 只是从旧 repository 搬迁，尚未统一成 command service 的 affected scope calculator。
- 并发、幂等、version conflict 和 write freshness 仍待 Phase 2/3 处理。

## 2026-06-11 Phase 2 Command service 基座

目标：新增统一 relation 写入 command service 基座，先不迁移业务入口，确保后续 workbench、pending invoice、no-OA、turnover、batch accounting、ETC 和 input invoice OA reverse 可以收敛到同一个写边界。

改动：

- 新增 `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`。
- 新增 `VALID_WORKBENCH_RELATION_MODES`，明确 active write fact 允许的 relation modes，并排除 `automatic_decision`。
- 新增 `WorkbenchRelationCommandError`，统一携带 `error_code`、`message` 和 structured `payload`。
- 新增 `WorkbenchRelationCommandService`，当前最小支持：
  - `confirm_relation`。
  - `cancel_relation`。
  - `cancel_by_case_id` 兼容别名。
  - relation read model freshness precondition。
  - idempotency key replay/conflict。
  - active row conflict fail fast。
  - audit history before/after、actor、note/reason、affected row ids。
  - changed case snapshot save。
- 新增 `tests/test_workbench_relation_command_service.py`，先以 RED 确认 command service 不存在，再实现最小通过。

设计取舍：

- 继续复用 `WorkbenchPairRelationService` 执行 row 去重、row type 对齐、active relation lookup、relation normalize 和 history normalize。
- command service 只做 orchestration、freshness、mode policy、idempotency、repository save 和 command result/error contract。
- 本阶段不迁移 `server.py` 或页面 service，不改变 API contract。
- 本阶段的 affected months 先按 `month_scope` 生成；完整 affected scope calculator 仍留到写入口迁移和 downstream refresh 收口阶段。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_pair_relation_service.py tests/test_workbench_relation_command_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_platform_runtime_boundary_guards.py -q
```

结果：

- pair relation + command service：15 passed。
- repository boundary + runtime boundary guard：43 passed，存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：适用并覆盖 mode registry、automatic decision 不可写 active fact、active row conflict、幂等 replay。
- Service-layer tests：适用并覆盖 command service 调 repository save、changed case、freshness precondition、history 写入。
- API contract tests：本阶段未改 HTTP/API contract，不适用。
- Read model/cache/background job tests：适用并覆盖 non-fresh read model precondition；实际 dirty/outbox 仍由 Phase 1 repository tests 保护。
- Frontend component and interaction tests：本阶段未改前端，不适用。
- End-to-end business-flow integration tests：本阶段只建立 command service，尚未迁移写入口；Phase 3 起必须补。
- Existing feature regression tests：适用并通过 pair relation、repository boundary 和 runtime boundary guard 回归保护。

剩余风险：

- 现有生产写入口仍未接入 command service；`server.py` 和多个 service 仍直接持有 `WorkbenchPairRelationService`。
- command service 目前使用内存 idempotency fallback；生产迁移时必须接入 durable idempotency store 或各 owner 现有 idempotency port。
- 并发 row occupation 仍只靠领域对象内存检查；生产 PostgreSQL 写入口迁移时需要 transaction/advisory lock 或 row occupation 约束。
- `withdraw_relation` 业务语义尚未单独建模；当前 Phase 2 只提供 cancel/cancel_by_case_id 基座。

## 2026-06-11 Phase 3 核心写入口迁移

目标：先迁移 workbench confirm/cancel 和 batch accounting submit/withdraw 两条核心生产写入口，让它们通过 `WorkbenchRelationCommandService` 写 canonical relation，同时保持旧 API response shape 和现有 UoW/idempotency 外壳。

改动：

- `WorkbenchRelationCommandService` 扩展：
  - `confirm_relation` 支持 `replace_existing`、`before_relations` 和 `history_operation_type`，用于承接原 `replace_with_confirmed_relation` 语义。
  - `cancel_relation` 支持自定义 history operation type。
  - 新增 `withdraw_relation`，封装原 `withdraw_latest_for_row_ids`，用于 batch accounting withdraw 恢复前一组 OA+发票关系。
  - 新增 `CallbackWorkbenchRelationRepository`，作为 Phase 3 过渡期 runtime mirror adapter；后续 Phase 7 删除兼容镜像。
- `WorkbenchWriteFacade`：
  - confirm/cancel 仍保留原有参数校验、金额检查、internal transfer 分流、idempotency/UoW 和 response mapping。
  - 真正 relation 写入改为调用 `WorkbenchRelationCommandService.confirm_relation/cancel_relation`。
  - 非 UoW 路径继续调用 pair relation persist scheduler，保证旧 runtime mirror 和本地持久化兼容；UoW 路径使用 `PostgresWorkbenchRelationRepository`。
- `Application`：
  - `_workbench_write_facade` 注入 `relation_command_service_factory`。
  - `_batch_accounting_service` 注入 `relation_command_service`。
  - `_workbench_uow_repository_factory` 的 `pair_relations` 从 `PostgresWorkbenchRepository` 切到 `PostgresWorkbenchRelationRepository`。
- `BatchAccountingService`：
  - submit 调用 command service，并将正式 relation mode 从旧的 `manual_confirmed` 调整为 `batch_accounting`。
  - withdraw 调用 command service 的 `withdraw_relation`。
  - repair legacy case id collision 仍保留旧 pair service 兼容路径，等待 Phase 7 删除。

测试：

- 新增 `tests/test_workbench_auth_context_idempotency.py::test_confirm_and_cancel_link_delegate_relation_writes_to_command_service_without_uow`，防止 workbench confirm/cancel 直接调用 pair service 写方法。
- 新增 `tests/test_batch_accounting_api.py::test_submit_delegates_relation_write_to_command_service`。
- 新增 `tests/test_batch_accounting_api.py::test_withdraw_delegates_relation_write_to_command_service`。
- 更新 batch accounting 旧断言，正式 relation mode 现在为 `batch_accounting`。
- 更新 workbench async persist 旧断言，替换式确认需要同时持久化被取消的旧 case 和新 case。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_auth_context_idempotency.py tests/test_workbench_relation_command_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_idempotency_contract.py tests/test_workbench_postgres_idempotency_repository.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_v2_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_platform_runtime_boundary_guards.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_pair_relation_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
```

已观察结果：

- workbench auth/idempotency + command service：11 passed。
- batch accounting API：32 passed。
- workbench idempotency/postgres idempotency：26 passed。
- workbench v2 API：148 passed。
- repository boundary + runtime boundary guard：43 passed。
- pair relation/read facade/sql projection：14 passed。
- 存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：适用并覆盖 command service mode registry、active conflict、idempotency replay，以及 batch accounting `batch_accounting` mode。
- Service-layer tests：适用并覆盖 workbench write facade、batch accounting service、command service、repository boundary 和 UoW repository wiring。
- API contract tests：适用并通过 workbench v2 API、workbench idempotency API、batch accounting API 回归；response shape 保持兼容。
- Read model/cache/background job tests：适用并通过 read facade/sql projection、dirty/outbox repository boundary、workbench async persist 断言。
- Frontend component and interaction tests：本阶段未改前端，未新增；batch accounting 前端阻断仍留给 Phase 5 聚焦验证。
- End-to-end business-flow integration tests：部分覆盖 workbench confirm/cancel 与 batch accounting submit/withdraw；跨页面全闭环仍未完成。
- Existing feature regression tests：适用并通过 workbench v2、idempotency、batch accounting、repository boundary 和 runtime guard 回归。

剩余风险：

- pending invoice、no-OA、turnover、ETC、input invoice OA reverse 仍未迁移。
- `WorkbenchWriteFacade` 与 `BatchAccountingService` 内仍保留无 command service 的兼容 fallback；生产 Application 已注入 command service，Phase 7 必须删除 fallback 和 runtime mirror adapter。
- batch accounting repair legacy case id collision 仍直接写 pair service。
- workbench withdraw、cash special、personal advance 等非 Phase 3 写入口仍未迁移。
- 并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。

## 2026-06-12 Phase 4 待找发票 relation 写入口迁移

目标：迁移 pending invoice manual invoice confirm、attach existing 单条和批量 relation 写入口，确保待找发票页面不再直接把 `WorkbenchPairRelationService` 当 relation 写事实源。

改动：

- `PendingInvoiceApplicationService` 新增 `relation_command_service` 依赖，并由 `Application` 注入 `WorkbenchRelationCommandService`。
- manual invoice confirm、attach existing confirm、batch attach confirm 均通过 `WorkbenchRelationCommandService.confirm_relation(...)` 写 active relation。
- 删除 pending invoice 旧的 direct relation write fallback；缺少 command service 时返回 `pending_invoice_relation_command_unavailable`。
- 写前 active relation 读取改为只通过 `WorkbenchRelationReadFacade.get_by_row_ids(...)` 的 distribution payload，不再 fallback 到 `active_relations_for_row_ids`。
- manual invoice confirm 在创建发票前调用 command service 的 relation write precondition；relation read model stale 时 fail fast，不产生孤儿发票，并把 pending invoice command 标记为 `failed_recoverable`。
- `WorkbenchRelationCommandService` 新增窄接口 `assert_write_precondition(...)`，复用既有 freshness/status/error payload 语义。
- relation mode registry 保留生产兼容值 `pending_invoice_attach_existing_invoice`，同时继续接受迁移期 alias `pending_invoice_attach_existing`。

测试：

- 新增/更新 `tests/test_pending_invoice_service.py`：
  - manual invoice confirm 必须委托 command service。
  - attach existing 单条必须委托 command service。
  - attach existing 批量必须委托 command service。
  - relation read model stale 时 manual invoice confirm fail fast，不创建发票、不写 relation，并记录 `failed_recoverable`。
  - 默认 pending invoice application service 测试也通过 command service repository adapter 写 relation，避免旧 direct write 成为成功路径。
- `tests/test_platform_runtime_boundary_guards.py` 继续防止 downstream service 直接调用 `active_relations_for_row_ids` 读取 relation。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_pending_invoice_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_read_models_use_workbench_relation_distribution -q
python3 -m compileall -q backend/src/fin_ops_platform/services/pending_invoice_service.py backend/src/fin_ops_platform/services/workbench_relation_command_service.py
```

已观察结果：

- pending invoice service：41 passed。
- pending invoice API：23 passed，存在既有 SWIG deprecation warnings。
- relation command/read/projection：11 passed，存在既有 SWIG deprecation warnings。
- downstream relation distribution guard：1 passed，存在既有 SWIG deprecation warnings。
- compileall 通过。

七类测试覆盖：

- Business core unit tests：适用并覆盖 pending invoice manual/attach 幂等、冲突、合并既有付款 relation、stale 前置失败。
- Service-layer tests：适用并覆盖 application service 委托 command service、command repository 可恢复状态、relation repository adapter 写回。
- API contract tests：适用并通过 pending invoice API 旧 shape 回归；HTTP 层 non-fresh response shape 仍需专项覆盖。
- Read model/cache/background job tests：适用并覆盖 pending write 前 relation read model freshness precondition 与 downstream distribution boundary guard。
- Frontend component and interaction tests：本阶段未改前端，未新增；后续跨页面即时反馈阶段补。
- End-to-end business-flow integration tests：部分覆盖 pending invoice attach/manual -> relation -> detail/API；真实跨页面 worker drain 仍未完成。
- Existing feature regression tests：适用并通过 pending invoice service/API、relation read/projection 和 boundary guard 回归。

剩余风险：

- no-OA、turnover、ETC、input invoice OA reverse 仍未迁移到 command service。
- pending invoice HTTP 层尚未单独断言 stale relation read model response shape。
- relation command service 的 PostgreSQL 并发 row occupation 仍未引入锁或唯一占用约束。
- 前端跨页面刷新仍主要依赖 mutation 后 refetch/event 提示，尚未做全页面闭环 e2e。

## 2026-06-12 Phase 5 no-OA relation 写入口迁移

目标：迁移 no-OA submit/withdraw/internal transfer confirm-link relation 写入口，确保免 OA 页面、关联台 internal transfer 特例和 Workbench 展示都读写同一 relation fact。

改动：

- `NoOaBankBatchApplicationService` 新增 `relation_command_service` 依赖，并由 `Application` 注入 `WorkbenchRelationCommandService`。
- no-OA submit、submit-selection、internal transfer from workbench 和 withdraw 均通过 `WorkbenchRelationCommandService.confirm_relation/cancel_relation` 写入或撤销 active relation。
- `NoOaBankBatchService.submit_batch/withdraw_batch` 不再直接创建或取消 pair relation，只负责批次状态机、audit 和 relation command payload 生成。
- `submit_selected_rows` 的 active relation 占用输入改为复用 `WorkbenchRelationReadFacade` distribution，不再直接读取 pair service list。
- `WorkbenchRelationCommandService.confirm_relation` 扩展 `evidence`、`display_tags`、`oa_exemption`、`exception_case_id`、`rule_version` 等 owner metadata，以保留 no-OA 批次展示和审计字段。
- no-OA API 在 relation read model non-fresh 时 fail fast 返回 409，并透传 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys`、`refresh_enqueued`。
- `Application._apply_workbench_relation_command_snapshot` 改为原地更新 runtime pair service，避免应用服务持有旧对象引用造成 response/persist/rollback 不一致。
- 架构守卫移除 no-OA submit/submit-selection 的旧 direct relation read 豁免。

保留兼容路径：

- no-OA legacy relation migration、submitted relation repair、category drift cleanup 和历史归并仍保留 direct pair service 操作；这些属于迁移/修复路径，后续 Phase 需要迁移到专用 command/repair port 或降级为离线工具。

测试：

- `tests/test_no_oa_bank_batch_application_service.py`
  - submit 必须委托 command service。
  - withdraw 必须委托 command service。
  - internal transfer from workbench 必须委托 command service。
- `tests/test_no_oa_bank_batch_service.py`
  - domain service submit 只更新批次状态并暴露 relation command payload，不再写 relation fact。
- `tests/test_no_oa_bank_batch_api.py`
  - submit/withdraw 持久化 batch + relation snapshot。
  - persistence failure rollback batch 和 relation snapshot。
  - relation read model stale 时 409 fail-fast 并保留 freshness payload。
- `tests/test_no_oa_bank_batch_workbench_integration.py`
  - salary/internal transfer no-OA submit 后 Workbench paired 区读到 `relation_mode=no_oa_bank_batch`，withdraw 后回 open。
- `tests/test_platform_runtime_boundary_guards.py`
  - 下游 relation distribution guard 继续通过，no-OA 常规写入口不再享受旧 direct read 豁免。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_workbench_integration.py tests/test_no_oa_bank_batch_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_read_models_use_workbench_relation_distribution tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_downstream_relation_query_services_do_not_accept_pair_relation_service tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_details_relation_tags_only_read_relation_distribution_facade -q
```

已观察结果：

- no-OA service/application/API/workbench integration：64 passed，存在既有 SWIG deprecation warnings。
- relation boundary guards：3 passed，存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：适用并覆盖 no-OA 状态机继续保持在 domain service，relation write payload 与批次 metadata/evidence/display tags 一致。
- Service-layer tests：适用并覆盖 application service 委托 command service、snapshot rollback、after_mutation 和 boundary guard。
- API contract tests：适用并覆盖 submit/withdraw success、persistence failure、version conflict 既有回归和 relation read model stale 409 response shape。
- Read model/cache/background job tests：适用并覆盖 no-OA 读取 active relation 走 `WorkbenchRelationReadFacade` distribution、写后 affected months 和 Workbench rebuild enqueue 既有回归。
- Frontend component and interaction tests：本阶段未改前端，未新增；后续跨页面即时反馈闭环仍需页面侧验证。
- End-to-end business-flow integration tests：适用并覆盖 no-OA submit/withdraw 在 Workbench paired/open 间切换，以及关联台 internal transfer 双入口收敛。
- Existing feature regression tests：适用并通过 no-OA API、workbench integration、relation command/read boundary 回归。

剩余风险：

- no-OA legacy migration/repair 仍直接操作 pair relation service，后续需迁移到专用 command/repair port。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈仍需专门 Phase 覆盖，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 6 turnover relation 写入口迁移

目标：迁移 turnover manual zero-difference closure/withdraw 的 Workbench relation 写入口，确保外部往来页面不再把 `WorkbenchPairRelationService` 当作常规写事实源。

改动：

- `TurnoverLedgerWorkbenchPairPort` 新增 `relation_command_service_factory` 和 `relation_facade` 依赖；manual closure 通过 `WorkbenchRelationCommandService.confirm_relation(...)` 写 `turnover_manual_closure` relation。
- turnover withdraw 通过 `WorkbenchRelationCommandService.cancel_relation(...)` 撤回 `turnover:{relation_id}` case，并保留 `turnover_manual_closure_withdraw` history operation。
- manual closure 写入前调用 command service freshness precondition；`workbench_relation` read model non-fresh 时 fail fast，不先刷新 turnover snapshot，也不产生 Turnover/Workbench 半写入。
- withdraw 前优先通过 `WorkbenchRelationReadFacade` distribution 校验当前 active relation 仍是 bank-only `turnover_manual_closure`；已升级为三栏关系时仍要求去关联台处理完整关系。
- `Application` 的 turnover closure/withdraw primary facade 和 legacy fallback facade 都注入 `_turnover_workbench_relation_command_service` 与 `_workbench_relation_read_facade()`。
- `server.py` 只新增依赖组装和 HTTP error payload 映射，不新增 relation 业务流程。

保留兼容路径：

- `TurnoverLedgerWorkbenchPairPort` 在缺少 command service 的测试或 legacy runtime 中仍保留 direct pair service fallback；生产 Application 已注入 command service，后续 Phase 需要删除或降级该 fallback。

测试：

- `tests/test_turnover_ledger_uow_contract.py`
  - manual closure 必须委托 command service。
  - manual closure withdraw 必须委托 command service。
- `tests/test_turnover_workbench_integration.py`
  - relation read model stale 时 manual closure 返回 409，且 Turnover snapshot 和 Workbench pair snapshot 均不变。
- `tests/test_turnover_ledger_api.py`
  - Application closure/withdraw primary 和 fallback wiring 必须同时注入 command service factory 与 relation facade。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_turnover_ledger_uow_contract.py tests/test_turnover_workbench_integration.py tests/test_turnover_ledger_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_platform_runtime_boundary_guards.py -q
python3 -m compileall -q backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py backend/src/fin_ops_platform/app/server.py
bash scripts/verify.sh docs
git diff --check
```

已观察结果：

- turnover UoW/workbench/API：208 passed，31 subtests passed。
- relation command/read/projection：12 passed。
- repository boundary + runtime boundary guard：43 passed。
- compileall、docs verify、diff check 均通过。
- 存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：本阶段未改变 turnover 业务规则本身；沿用既有 turnover relation service 测试。
- Service-layer tests：适用并覆盖 pair port 委托 command service、withdraw command service cancel、read model stale fail-fast 和 Application dependency wiring。
- API contract tests：适用并覆盖 stale relation read model 409 response payload，以及 turnover API 旧 shape 回归。
- Read model/cache/background job tests：适用并覆盖 `WorkbenchRelationReadFacade` non-fresh precondition、relation command/read/projection 和 dirty/outbox repository boundary。
- Frontend component and interaction tests：本阶段未改前端，未新增；前端 stale 禁用已有 turnover page 测试保护。
- End-to-end business-flow integration tests：适用并覆盖 turnover closure stale fail-fast 不半写入，以及既有 Workbench grouping/manual closure 集成。
- Existing feature regression tests：适用并通过 turnover API/UoW/workbench integration、relation 基座和 boundary guard 回归。

剩余风险：

- turnover legacy fallback 仍保留 direct pair service fallback，后续删除前需要单独回归。
- ETC 删除/修复、input invoice OA reverse、no-OA repair、batch accounting repair 仍未完全迁入 command/repair port。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7A ETC relation 写入口迁移

目标：迁移 ETC 业务批次删除、历史 repair、historical business batch migration 和 existing batch link 的 Workbench relation 写入口，避免 ETC 页面或工具继续把 `WorkbenchPairRelationService` 当作生产写事实源。

改动：

- `WorkbenchRelationCommandService` 新增 `cancel_relations_for_row_ids(...)`、`update_relation_metadata_for_case_id(...)`，并把 `etc_batch_invoice_link` 纳入合法 relation mode registry。
- `Application._cancel_etc_summary_relations_for_batch(...)` 改为优先调用 command service row-id batch cancel；旧 facade fallback 只用于测试/迁移兼容，生产 wiring 走 command service。
- `DELETE /api/etc/business-batches/{id}` 和通过 reconciliation task 删除绑定业务批次时，已提交批次在本地 reset 前先调用 relation write precondition；`workbench_relation` read model 非 fresh 时返回 409，不删除 business batch，也不取消 relation。
- `HistoricalEtcRepairService` 历史补关联通过 `confirm_relation(...)` 写 `etc_batch_invoice_link`；`HistoricalEtcBusinessBatchMigrationService` 和 `ExistingEtcBatchLinkService` 通过 command service 更新 relation metadata。
- `migrate_historical_etc_business_batches.py` 和 `link_existing_etc_batches.py` execute 路径注入 `Application._workbench_relation_command_service()`。
- `tests/test_platform_runtime_boundary_guards.py` 增加 ETC summary 删除的 command boundary 守卫，防止 `server.py` 回退到 direct pair mutation。

保留兼容路径：

- `HistoricalEtcRepairService`、`HistoricalEtcBusinessBatchMigrationService`、`ExistingEtcBatchLinkService` 仍保留缺少 command service 时的 direct pair fallback，用于老测试和迁移兼容；生产 Application/tool wiring 已注入 command service。下一阶段需要删除这些 fallback 或降级为显式 repair-only port。
- 这些服务仍用 pair service 读取/校验历史 active relation，写入已迁入 command service；后续可改为 read facade + command precondition，减少 pair service 读依赖。

测试：

- `tests/test_workbench_relation_command_service.py`
  - row-id batch cancel 记录 changed cases、affected months 和 `etc_summary_unmerged` history。
  - relation metadata update 检查 freshness 并记录 before/after history。
  - mode registry 包含 `etc_batch_invoice_link`，继续拒绝 `automatic_decision` 写入 active fact。
- `tests/test_etc_backend.py`
  - ETC summary relation cancel 必须委托 workbench relation command service，禁止 direct `cancel_active_relations_for_row_ids` 成功路径。
  - 已提交 ETC business batch delete 在 relation read model stale 时 fail fast，且 batch 和 relation 均不变化。
  - 历史 repair、existing batch link、submitted business batch reset 和 reconciliation task delete 保持旧业务回归。
- `tests/test_historical_etc_business_batch_migration_service.py`
  - historical migration metadata update 必须通过 command service。
- `tests/test_platform_runtime_boundary_guards.py`
  - ETC summary delete helper 必须使用 command boundary，并且 API/task delete helper 必须有 relation freshness preflight。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_etc_summary_relation_delete_uses_workbench_relation_command_boundary -q
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_historical_etc_business_batch_migration_service.py tests/test_migrate_historical_etc_business_batches_tool.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_platform_runtime_boundary_guards.py -q
python3 -m compileall -q backend/src/fin_ops_platform/services/workbench_relation_command_service.py backend/src/fin_ops_platform/services/historical_etc_repair_service.py backend/src/fin_ops_platform/services/historical_etc_business_batch_migration_service.py backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py backend/src/fin_ops_platform/tools/link_existing_etc_batches.py
bash scripts/verify.sh docs
git diff --check
```

已观察结果：

- command service：9 passed。
- ETC relation boundary guard：1 passed。
- ETC backend：129 passed，4 skipped。
- historical migration service/tool：4 passed。
- relation command/read/projection：14 passed。
- repository boundary + runtime boundary guard：44 passed。
- compileall、docs verify、diff check 均通过。
- 存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：适用并覆盖 command service row-id cancel、metadata update、mode registry 和 stale/fresh precondition。
- Service-layer tests：适用并覆盖 ETC repair/link/migration 委托 command service、history operation type 和 changed case persistence。
- API contract tests：适用并覆盖已提交 ETC business batch delete 在 relation read model stale 时返回 409 且不产生半写入。
- Read model/cache/background job tests：适用并覆盖 command result affected months、Workbench relation invalidation 和 stale fail-fast，不把 stale read model 当成无关系。
- Frontend component and interaction tests：本阶段未改前端，未新增；ETC 页面仍需在最终闭环阶段验证 409 stale message 和 mutation 后 refetch。
- End-to-end business-flow integration tests：适用并覆盖业务批次删除入口和 reconciliation task 删除入口的 summary relation cancel 回归；跨页面最终一致性还需专门 smoke。
- Existing feature regression tests：适用并保留历史 repair、existing link、business batch reset 和 relation boundary guard 回归。

剩余风险：

- ETC legacy fallback 仍存在，下一阶段需要删除或收口为显式 repair port。
- input invoice OA reverse 仍未迁入 command service。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7B ETC legacy relation fallback 删除

目标：删除 ETC repair/link/migration service 中缺少 command service 时的 direct `WorkbenchPairRelationService` mutation fallback，避免工具或测试环境静默写旧事实源。

改动：

- `HistoricalEtcRepairService` 在需要导入历史发票或创建历史 submitted batch 之前要求 `WorkbenchRelationCommandService.confirm_relation(...)` 可用；缺失时抛 `workbench_relation_command_unavailable`，不先写本地 ETC batch 或 active relation。
- `HistoricalEtcBusinessBatchMigrationService` 在创建 historical business batch 前要求 `update_relation_metadata_for_case_id(...)` 可用；缺失时 fail fast，不创建 business batch。
- `ExistingEtcBatchLinkService` 在导入 canonical ETC 发票或创建 submitted batch 前要求 `update_relation_metadata_for_case_id(...)` 可用；缺失时 fail fast，不创建 submitted batch。
- 删除三个 service 的 direct `create_active_relation(...)` / `update_relation_metadata_for_case_id(...)` fallback，并新增 boundary guard 防止回退。

保留边界：

- 这些 service 仍用 `pair_relation_service.get_active_relation_by_case_id(...)` 做历史 active relation 读校验；这是读/校验遗留，不再承担写入 fallback。后续如需完全去 pair read 依赖，应迁到 `WorkbenchRelationReadFacade` 或专用 repair read port。

测试：

- `tests/test_etc_backend.py`
  - historical repair 缺 command service 时 fail fast，且不创建 submitted batch 或 active relation。
  - existing ETC link 缺 command service 时 fail fast，且不创建 submitted batch。
  - existing ETC link 幂等回归显式注入 command service，不依赖 fallback。
- `tests/test_historical_etc_business_batch_migration_service.py`
  - historical migration 缺 command service 时 fail fast，且不创建 business batch。
- `tests/test_platform_runtime_boundary_guards.py`
  - ETC repair/link/migration service 不得保留 direct pair mutation fallback。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py::EtcApiTests::test_historical_etc_repair_requires_relation_command_service_before_local_writes tests/test_etc_backend.py::EtcApiTests::test_existing_etc_batch_link_requires_relation_command_service_before_local_writes tests/test_etc_backend.py::EtcApiTests::test_existing_etc_batch_link_is_idempotent_and_does_not_create_parallel_relation -q
PYTHONPATH=backend/src python3 -m pytest tests/test_historical_etc_business_batch_migration_service.py::HistoricalEtcBusinessBatchMigrationServiceTests::test_migration_requires_relation_command_service_before_business_batch_write -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_etc_repair_and_link_services_do_not_keep_direct_relation_write_fallbacks -q
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_historical_etc_business_batch_migration_service.py tests/test_migrate_historical_etc_business_batches_tool.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py -q
python3 -m compileall -q backend/src/fin_ops_platform/services/historical_etc_repair_service.py backend/src/fin_ops_platform/services/historical_etc_business_batch_migration_service.py backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py backend/src/fin_ops_platform/app/server.py
bash scripts/verify.sh docs
git diff --check
```

已观察结果：

- ETC targeted repair/link：3 passed。
- historical migration missing command：1 passed。
- boundary guard：1 passed。
- ETC backend：131 passed，4 skipped。
- historical migration service/tool：5 passed。
- relation command/read/projection：14 passed。
- platform runtime boundary guard：29 passed。
- compileall、docs verify、diff check 均通过。
- 存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：适用并覆盖缺 command 时不写 relation active fact。
- Service-layer tests：适用并覆盖 repair/link/migration service fail-fast 和 no half-write。
- API contract tests：本阶段未改 HTTP 契约；沿用 Phase 7A submitted delete stale 409。
- Read model/cache/background job tests：适用并通过 boundary guard 防止旧写事实源绕过 read model invalidation。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并保留 ETC repair/link/migration 目标回归；完整跨页面 smoke 仍待后续。
- Existing feature regression tests：适用并保留 existing link 幂等、historical repair/migration 成功路径。

剩余风险：

- input invoice OA reverse 仍未迁入 command service。
- no-OA/turnover/batch accounting legacy repair 或 fallback 仍待收口。
- ETC repair/link/migration 仍用 pair service 做 active relation 读校验；后续可迁到 read facade/repair read port。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7C input invoice OA reverse relation writer 迁移

目标：把进项发票使用页 OA reverse evidence detected 后的 relation 写入从 direct `WorkbenchPairRelationService.create_active_relation(...)` 迁入 `WorkbenchRelationCommandService.confirm_relation(...)`，避免 OA reverse 成为独立写事实源。

改动：

- `WorkbenchInputInvoiceUsageOaReverseRelationWriter` 只接收 relation command service；写入 relation mode 为 `input_invoice_oa_reverse`。
- writer 传递 `case_id`、`row_ids/row_types`、`actor_id`、`month_scope`、`special_metadata`、`evidence`、`idempotency_key` 和 `history_operation_type` 给 command service，由 command service 统一处理 freshness、active row conflict、idempotency、history 和 snapshot save。
- 缺少 `confirm_relation(...)` 时抛 `workbench_relation_command_unavailable`，不静默跳过，也不回退 direct pair mutation。
- `Application._input_invoice_usage_oa_reverse_service()` 注入 `self._workbench_relation_command_service()`；`/api/input-invoice-usage/oa-reverse/batches/{id}/oa-status/refresh` 捕获 `WorkbenchRelationCommandError` 并返回 409、details。
- API command stale/conflict 时不保存本地 batch 的 detected 状态，避免 relation 未写入但本地 OA reverse 状态已推进。

测试：

- `tests/test_input_invoice_usage_oa_reverse_service.py`
  - writer 委托 command service 并保留 mode、actor、month、metadata、idempotency 和 history operation。
  - 缺 command service 时 fail fast。
- `tests/test_input_invoice_usage_api.py`
  - OA status refresh 遇到 relation read model stale/conflict 返回 409，且本地 batch 仍停在 detecting 状态。
- `tests/test_platform_runtime_boundary_guards.py`
  - OA reverse writer 不得保留 `_pair_relation_service`、`active_relations_for_row_ids`、`create_active_relation`，Application 不得再注入 `WorkbenchPairRelationService`。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_input_invoice_usage_oa_reverse_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_input_invoice_usage_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py -q
```

已观察结果：

- input invoice OA reverse service：13 passed。
- input invoice usage API：13 passed。
- platform runtime boundary guard：30 passed；存在既有 SWIG deprecation warnings。

七类测试覆盖：

- Business core unit tests：适用并覆盖 writer mode、row identity、month scope、idempotency key 和缺 command fail-fast。
- Service-layer tests：适用并覆盖 OA reverse service 到 relation command service 的写入边界。
- API contract tests：适用并覆盖 relation command stale/conflict 409 response 和 no half-write。
- Read model/cache/background job tests：适用并由 command service freshness precondition 与 boundary guard 覆盖，不让 writer 绕过 workbench relation read model。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并通过 API flow 覆盖 create draft -> evidence refresh -> relation command failure rollback；跨页面 read model smoke 仍待后续。
- Existing feature regression tests：适用并保留 OA reverse preview/draft/manual/submitted history、input invoice usage API 和 boundary guard 回归。

剩余风险：

- no-OA/turnover/batch accounting legacy repair 或 fallback 仍待收口。
- ETC repair/link/migration 仍用 pair service 做 active relation 读校验；后续可迁到 read facade/repair read port。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7D batch accounting submit direct fallback 删除

目标：删除 `BatchAccountingService.submit` 在缺少 `WorkbenchRelationCommandService` 时回退到 `WorkbenchPairRelationService.replace_with_confirmed_relation(...)` 的兼容路径，确保批量账务提交不会绕过统一 relation command boundary。

改动：

- `_submit_unlocked` 缺少 relation command service 时抛 `batch_accounting_relation_command_unavailable`，不再 direct pair write。
- 保留 `confirm_relation(...)` command path 的 `relation_mode=batch_accounting`、`replace_existing=True`、`history_operation_type=confirm_link`、before relations 和 metadata。
- 新增 boundary guard，防止 `_submit_unlocked` 重新出现 `replace_with_confirmed_relation`、`create_active_relation` 或 `record_history` direct fallback。
- legacy case id collision repair 暂不混入本刀，仍作为显式 repair 路径，后续需要迁到专用 command/repair port 或降级为离线工具。

测试：

- `tests/test_batch_accounting_api.py`
  - submit 继续委托 relation command service。
  - submit 缺 command service 时 fail fast，且不会调用 pair service direct write。
  - 金额差异备注提交回归保持历史和 relation metadata。
- `tests/test_platform_runtime_boundary_guards.py`
  - `BatchAccountingService._submit_unlocked` 不得保留 direct pair write fallback。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_submit_delegates_relation_write_to_command_service tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_submit_requires_relation_command_service_without_direct_pair_fallback tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_submit_amount_mismatch_with_note_persists_relation_and_history -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_batch_accounting_submit_has_no_direct_pair_write_fallback -q
```

已观察结果：

- batch accounting targeted：3 passed。
- boundary guard targeted：1 passed。

七类测试覆盖：

- Business core unit tests：适用并覆盖提交缺 command 的 fail-fast 业务 invariant。
- Service-layer tests：适用并覆盖 submit command delegation 和 direct fallback 删除。
- API contract tests：本阶段未改 HTTP response shape；Application 生产 wiring 已注入 command service。
- Read model/cache/background job tests：适用并继续由 relation command service/freshness gate 保护，不让 submit 绕过 dirty/read model 边界。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并保留 submit relation targeted 回归；真实跨页面 worker drain 仍待后续 smoke。
- Existing feature regression tests：适用并保留金额差异备注提交历史回归。

剩余风险：

- batch accounting legacy case id collision repair 仍 direct pair write，后续应迁到专用 command/repair port 或离线工具。
- no-OA/turnover legacy repair 或 fallback 仍待收口。
- ETC repair/link/migration 仍用 pair service 做 active relation 读校验；后续可迁到 read facade/repair read port。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

## 2026-06-12 Phase 7E turnover legacy fallback direct write 删除

目标：删除 `TurnoverLedgerWorkbenchPairPort` 在缺少 relation command service 时的 direct `WorkbenchPairRelationService` 写 fallback，避免 turnover legacy fallback facade 绕过统一 relation command boundary。

改动：

- manual closure confirm 缺 command service 时抛 `workbench_relation_command_unavailable`，不再读取 active pair relation 或调用 `replace_with_confirmed_relation(...)`。
- manual closure write precondition 缺 command service 时 fail fast。
- manual closure withdraw 缺 command service 时抛 `workbench_relation_command_unavailable`，不再调用 direct `cancel_relation(case_id)` 或本地 pair snapshot persist。
- 保留 `WorkbenchRelationReadFacade` 的 withdrawability 校验：已补齐三栏 relation 仍要求到关联台撤回完整关系。
- 新增 boundary guard，防止 `TurnoverLedgerWorkbenchPairPort` 重新出现 direct pair write fallback。

测试：

- `tests/test_turnover_ledger_uow_contract.py`
  - manual closure confirm/withdraw 继续委托 relation command service。
  - manual closure confirm/withdraw 缺 command service 时 fail fast，且 blocking pair service 不被读写。
- `tests/test_turnover_ledger_api.py`
  - 全量 turnover API 回归保持通过，包括 legacy fallback facade 的应用层行为。
- `tests/test_platform_runtime_boundary_guards.py`
  - `TurnoverLedgerWorkbenchPairPort` 不得保留 direct pair write fallback。

验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_turnover_ledger_uow_contract.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_turnover_ledger_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_workbench_pair_port_has_no_direct_pair_write_fallback -q
```

已观察结果：

- turnover UoW contract：69 passed。
- turnover ledger API：130 passed，31 subtests passed。
- boundary guard targeted：1 passed。

七类测试覆盖：

- Business core unit tests：适用并保留 turnover relation core tests；本阶段改写入口边界，不改闭环业务规则。
- Service-layer tests：适用并覆盖 port command delegation、缺 command fail-fast 和 direct fallback 删除。
- API contract tests：适用并通过 turnover API 全量回归，保持旧 API shape。
- Read model/cache/background job tests：适用并继续通过 command service/freshness gate 保护 dirty/read model 边界。
- Frontend component and interaction tests：本阶段未改前端，未新增。
- End-to-end business-flow integration tests：适用并保留 turnover API 和 Workbench relation targeted 回归；真实 worker drain 仍待 staging smoke。
- Existing feature regression tests：适用并保留 legacy fallback facade 应用层行为、withdraw 和 API 回归。

剩余风险：

- no-OA legacy migration/repair/consolidation 仍在 `build_batches(...)` 中 direct pair write，后续需要专用 command/repair port 或离线工具设计。
- batch accounting legacy case id collision repair 仍 direct pair write，后续应迁到专用 command/repair port 或离线工具。
- ETC repair/link/migration 仍用 pair service 做 active relation 读校验；后续可迁到 read facade/repair read port。
- relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
- 前端所有相关页面的即时反馈闭环仍需专门 Phase 验证，domain event 仍只能作为刷新提示。

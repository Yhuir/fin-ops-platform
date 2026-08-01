# 外部往来款管理 实施记录

## 2026-07-24 - 访问时 closure exact delta 与轻量 gate

- Turnover GET 先读取原子 `all` scope source/dirty proof；non-fresh 在 page SQL 前返回空 rows。sole canonical manual-closure mismatch 且 change rows 能安全给出 case/status/row ids/months 时，只入队 exact month relation delta；其它 drift fail closed 为 full-`all`。
- `all` 公开 source proof 改由 `turnover_ledger_scopes:all` + 全部 current-effective child dirty 收敛负责，允许精确月 delta 后跨月行版本不同；单月不一致与无法定位的变化仍完整重建。严格 global generation CAS 保留。
- 一次性 PostgreSQL 17 实例应用全部 migrations 后，空 generation、mixed child rows、dirty 聚合、delta 保存/CAS、canonical relation bundle 共 7 项真实集成通过；同时修复 nullable `published_source_version` 的 bigint 参数类型和无 rows 时 `version_proof` 不产行的问题。

## 2026-07-22 - 银行流水批量标签共享原子写边界

- 外部往来批量标签不再通过 PostgreSQL 分类全量 snapshot 保存；改为复用 `BankTransactionCategoryMutationWriter.persist_many(...)`，在 Turnover UoW 的同一事务内批量写 canonical category/event/audit，并一次输出所有精确月份 refresh 与 matching dirty。
- UoW 在事务或 queue 失败时恢复本次 bank-detail in-memory snapshot，提交后清除 pending snapshot；禁止数据库已回滚但进程 cache 留下新标签。
- 删除旧 snapshot writer 与 active `unknown` 撤销表示，不新增第二套 adapter、fallback、worker 或表；Turnover 页面/API 合同不变。
- 回归覆盖批量去重、一次 enqueue、queue failure rollback、bank-details 下游可见性及现有 Turnover API/UoW 行为。

## 2026-07-20 - 写命令重复 I/O 收口

- 第二轮生产证据：release `ffdcfcdcb` 三轮业务与恢复均通过，response-to-fresh/visible p95 为 `1210.886/1805.972ms`，但 command p95 仍为 `5443.004ms`，热态约 `1.09–1.34s`。一次性 PostgreSQL 对同一请求的 17/15 条 SQL trace 证明，relation repository 仍自行执行 3 条 scope 解析和 1 次 outbox batch，Turnover UoW 随后又执行第二次 outbox batch。
- 第二轮实施：Turnover 专属 relation command factory 明确构造 `PostgresWorkbenchRelationRepository(..., enqueue_refreshes=False)`；canonical relation/history 仍由 repository 原子保存，全部 read-model refresh 只由 Turnover UoW 单 owner 输出。关联台自己的 repository composition 不变。
- 生产证据：relation-only projection 上线后，三轮可逆操作的 response-to-fresh p95 已降到 `934.515ms`、response-to-visible p95 `1699.211ms`；但 command p95 仍为 `3662.382ms`，稳定样本约 `1.13–1.32s`，未过 `1000ms` 门槛。
- 根因：closure request 逐笔读取 canonical bank facts 解析月份；同一 selected bank rows 又被 expected-version 与 preview 分别读取；Turnover UoW 对幂等键先事务外查询、再事务内 reserve；cash-closure 撤回先读 current relation 做资格判断，command 内再次 lock/load/freshness。
- 实施：月份改用既有 `ImportService.list_transactions_by_ids(...)` 单次批量事实读取；`TurnoverLedgerBankRowSelectionPort` 在单请求 facade 生命周期复用一份不可变副本给版本校验和 preview；幂等统一由事务内 reserve 判断首次、冲突、in-progress 和 replay；withdraw preparation 在同一事务内完成 case lock、scoped snapshot 和 freshness，并由实际 withdraw 复用。
- 隔离：不新增 API、表、worker、cache service、queue 或 fallback；Workbench 普通调用不传 preparation，行为不变。旧事务外幂等预查、旧 `TurnoverLedgerBankRowStalePreconditionPort` 与 cash-closure current relation 二次加载已删除。
- 验证：定向 API/UoW/Workbench command 测试 `253` 项通过；真实 PostgreSQL、完整回归与更新 SHA 的生产可逆探针在本轮后续记录补充。

## 2026-07-20 - 确认/撤回写后可见性链路收窄

- 生产基线：列表读取 40 样本 shell/grouped/tag/Page Audit p95 分别为 `115.781ms`、`325.701ms`、`150.911ms`、`303.462ms`，均为 fresh；但可逆确认/撤回的命令耗时分别约 `1.3–1.5s` / `2.3–2.8s`，response-to-fresh 约 `5.8–8.9s`，因此只读性能通过而写后可见性不通过。
- 真实原因一：PostgreSQL confirm/withdraw port 在每条命令中加载全部 turnover 银行行、重建全部 domain relation、保存整个 relation snapshot 与 audit log，产生与本次操作无关的 I/O。
- 真实原因二：turnover projection 在 canonical relation 已提交后，仍用 `WorkbenchRelationReadFacade(require_fresh=True)` 等待 `workbench_relation` read model；形成 workbench-relation worker → turnover worker 的串行依赖。
- 实施边界：stale precondition 和 domain input refresh 只读取目标 bank row IDs；同一事务只 upsert 命令结果 relation、append 本次命令后新增且 relation-id 匹配的 audit event，并写既有 scoped outbox。projection 通过单条 bounded canonical-source bundle SQL 从同一快照读取 active `app.workbench_pair_relations` 和 source summary，不增加新表、worker、cache、queue 或 API。
- 旧代码删除：移除生产无调用方的 `TurnoverLedgerRelationRepositoryAdapter`、confirm/withdraw 的全量 `_rebuild_relation_snapshot` / `_save_relation_snapshot`，以及 turnover projection 对 workbench-relation read model 的 freshness wait。全量 snapshot writer 只保留给明确的 import/restore/local snapshot owner，不再进入页面确认/撤回链。
- 本地验证：turnover API/UoW/domain/projection/runtime wiring 共 `303` 项通过；真实 PostgreSQL 应用全量 migrations 后验证单关系 upsert + 单 audit append 不覆盖另一关系及其历史，临时数据库已删除。生产精确 SHA 复测结果在同日后续记录补充。

## 2026-07-13 - 跨月确认保留 relation freshness 精确 scope

- 生产可逆场景发现：两条跨月 open 流水的 `affected_months` 被压缩成 `month_scope=all` 后，写前 freshness 查询丢失精确月份；因为尚无 relation rows，合法的 fresh empty 集合被误判为 missing 并返回 409。
- 修复：Turnover adapter 把全部 affected months 作为 `scope_keys_hint` 交给既有 `WorkbenchRelationCommandService`，command boundary 去重后传入 read facade。继续 fail closed 校验每个精确月份，不绕过 freshness、不读 live relation 表、不增加 fallback。
- 旧逻辑结论：没有第二条确认链需要删除；污染点是既有边界的有损 `all` 压缩，已由精确 scope I/O 取代。

## 2026-07-05 - Worker / Read Model 抖动收敛

- 目标：降低外部往来款 read model worker 在 source_versions 已明显变化时仍先等待 Workbench relation fresh gate 的抖动，减少无意义 relation read I/O 和 dependency defer。
- 影响范围：`TurnoverLedgerSqlProjectionBuilder._unchanged_scope_result(...)` 的 unchanged skip 判定；不改变外部往来款业务分组、relation/closure 写入、affected-month scope、API payload shape、worker event type、dirty scope 或 readiness 合同。
- 关键决策：skip 判定先比较当前基础 `source_versions` 与已持久化版本；基础版本不同直接进入 rebuild，不再先调用 `WorkbenchRelationReadFacade.get_by_row_ids(... require_fresh=True)` 做 unchanged check。只有基础版本一致时才读取 Workbench relation source_versions 来判断能否安全 skip。
- 旧逻辑清理：禁止在基础版本已不一致的情况下把 relation fresh gate 当作 skip 前置条件；这会把本来应重建的 event 变成跨 read model 等待抖动。
- 测试覆盖：`tests/test_turnover_ledger_read_model_refresh.py::TurnoverLedgerReadModelRefreshServiceTests::test_projection_rebuilds_without_relation_check_when_base_source_versions_changed`。
- 验证命令：`python3 -m pytest tests/test_turnover_ledger_read_model_refresh.py::TurnoverLedgerReadModelRefreshServiceTests::test_projection_rebuilds_without_relation_check_when_base_source_versions_changed -q`。
- 未测风险：本地测试不证明真实生产历史数据下所有 turnover scope p95；发布后仍需 direct read model SLO、authenticated turnover API SLO 和受控写操作 fan-out 验证。

## 2026-06-30 - 外部往来闭环免发票 requirement 同步修复

- 目标：修复用户已在流水规则标签管理中把外部往来款借入/归还借款设置为不需要发票后，历史 `turnover:*` 关系仍停留在关联台未配对区的问题。
- 根因：生产里的目标关系是旧 `relation_mode=manual_confirmed` 且 `special_metadata={}` 的 `turnover:*` active relation。Workbench 按普通两栏手工关系 fail closed，不会读取当前规则设置临时推断“无需发票”。这是 relation fact 合同缺失，不是前端展示缺陷。
- 关键决策：新闭环写入端 `TurnoverLedgerWorkbenchPairPort` 必须在 `turnover_manual_closure` relation metadata 中写入 `requires_oa=true`、`requires_invoice=false`、`paired_requirement_source` 和版本。规则保存后由 `NoOaBankBatchApplicationService.update_tag_selection(...)` 通过 `WorkbenchRelationCommandService.update_relation_metadata_for_case_id(...)` 同步旧 `turnover:* manual_confirmed` active relation，升级为 `turnover_manual_closure` 并补齐 requirement metadata。Workbench 分区只读 relation metadata；metadata 缺失的旧关系仍 fail closed。
- 旧逻辑删除/隔离：不放宽普通 `manual_confirmed` 两栏关系，不允许 Workbench 查询当前 settings 兜底，不直接修改 relation 表。旧 `turnover:* manual_confirmed` 只在规则保存同步链路中迁移；没有匹配外部往来规则的 relation 不被改动。
- 测试覆盖：`tests/test_workbench_turnover_grouping.py::WorkbenchTurnoverGroupingTests::test_two_pane_turnover_manual_closure_with_no_invoice_requirement_is_paired`、`tests/test_no_oa_bank_batch_tag_selection_api.py::NoOaBankBatchTagSelectionApiTests::test_tag_rule_update_upgrades_legacy_turnover_relation_from_persistent_repository`、`tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_update_relation_metadata_for_case_id_can_upgrade_relation_mode`、`tests/test_turnover_ledger_uow_contract.py::TurnoverLedgerUoWContractTests::test_turnover_workbench_pair_port_delegates_manual_closure_to_relation_command_service`、`tests/test_turnover_workbench_integration.py::TurnoverWorkbenchIntegrationTests::test_manual_closure_accepts_three_bank_rows_and_keeps_workbench_case_open_until_invoice_exists`。
- 验证命令：`PYTHONPATH=backend/src:. pytest tests/test_no_oa_bank_batch_tag_selection_api.py tests/test_workbench_candidate_grouping.py tests/test_workbench_turnover_grouping.py tests/test_no_oa_bank_batch_application_service.py tests/test_workbench_relation_command_service.py tests/test_workbench_relation_command_repository_adapter.py tests/test_turnover_workbench_integration.py tests/test_turnover_ledger_uow_contract.py -q`。

## 2026-06-25 - route-owner local closure audit

- 目标：执行 `server-py:turnover-ledger-route-owner-local-closure-audit`，确认所有 `/api/turnover-ledger*` route callbacks 已从 `server.py` 迁出。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、本实施记录；不改变外部往来业务、写入、read model freshness、operation barrier、Workbench relation command 边界、导出或前端行为。
- 关键决策：`server.py` 不再定义任何 `_handle_api_turnover_ledger*` route callback；剩余 turnover ledger app surfaces 分类为 composition-root、write facade/request-boundary provider、local runtime support、read model/source-version/platform adapter、legacy fallback invalidation/persistence adapter 和 Workbench source-version provider。它们不是 route-owner gap，但后续可作为独立 cleanup candidate。
- 文档影响：新增 modular IO route-owner local closure audit analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录；外部往来状态机定义不变。
- 测试覆盖：本轮为 analysis-only；复用 platform Guard 证明 removed handler list 不回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v`；`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；本结论不等于外部往来模块全局 closed。
- 后续事项：执行 `planning:post-turnover-ledger-route-owner-next-boundary-selection`。

## 2026-06-25 - relation withdraw route-owner collapse

- 目标：执行 `server-py:turnover-ledger-relation-withdraw-route-callback-collapse`，把 `POST /api/turnover-ledger/relations/{relation_id}/withdraw` HTTP mapping 从 `server.py` 收到 `TurnoverLedgerApiRoutes.route(...)`。
- 影响范围：relation withdraw 的 relation-id extraction、session/body/actor/tenant/idempotency/stale-precondition/error mapping；不改变 withdraw request boundary、write facade、affected-months、refresh、权限或 read model freshness。
- 关键决策：route owner 通过 `withdraw_request_boundary_provider` 显式调用 `TurnoverLedgerWithdrawRequestBoundaryFacade`；`server.py` 不再定义任何 `_handle_api_turnover_ledger*` route callback；不直接 import `app.auth`，不解析 cookie/header 细节，不接收 whole `Application`。
- 文档影响：新增 modular IO relation withdraw route callback collapse analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；外部往来状态机定义不变。
- 测试覆盖：更新 withdraw source-inspect tests 和 platform Guard；复跑 targeted withdraw regressions 与完整 `tests.test_turnover_ledger_api`。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_withdraw_relation_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_withdraw_handler_delegates_precheck_expected_versions_and_affected_months_to_request_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_withdraw_request_boundary_facade_wires_relation_detail_and_affected_months_resolver tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_withdraw_idempotency_key_replays_without_duplicate_withdraw_or_refresh tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_withdraw_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_withdraw_relation_queue_failure_rolls_back_relation_withdraw tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_withdraw_relation_uow_path_does_not_clear_read_model_directly -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；下一步需要 route-owner local closure audit 分类剩余 app surfaces。
- 后续事项：执行 `server-py:turnover-ledger-route-owner-local-closure-audit`。

## 2026-06-25 - closure withdraw route-owner collapse

- 目标：执行 `server-py:turnover-ledger-closure-withdraw-route-callback-collapse`，把 `POST /api/turnover-ledger/closures/withdraw` HTTP mapping 从 `server.py` 收到 `TurnoverLedgerApiRoutes.route(...)`。
- 影响范围：closure withdraw 的 session/body/actor/tenant/idempotency/error mapping；不改变 closure request boundary、write facade、Workbench relation command service、refresh、权限、read model freshness 或 relation withdraw 写路径。
- 关键决策：route owner 复用 closure request-boundary port；server 注入使用 lambda 动态解析，保留 app 构建后测试/运行时替换 `_turnover_ledger_closure_request_boundary_facade` 的兼容语义；不直接 import `app.auth`，不解析 cookie/header 细节，不接收 whole `Application`。
- 文档影响：新增 modular IO closure withdraw route callback collapse analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；外部往来状态机定义不变。
- 测试覆盖：新增 closure withdraw source-inspect test 并更新 platform Guard；复跑 targeted closure withdraw regressions 与完整 `tests.test_turnover_ledger_api`。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_closure_withdraw_handler_uses_closure_boundary_without_relation_withdraw_inline tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_cash_closure_withdraw_route_uses_closure_boundary tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；relation withdraw callback 仍未迁移。
- 后续事项：执行 `server-py:turnover-ledger-relation-withdraw-route-callback-collapse`。

## 2026-06-25 - closure confirm route-owner collapse

- 目标：执行 `server-py:turnover-ledger-closure-confirm-route-callback-collapse`，把 `POST /api/turnover-ledger/closures/confirm` HTTP mapping 从 `server.py` 收到 `TurnoverLedgerApiRoutes.route(...)`。
- 影响范围：closure confirm 的 bank-row-id validation、session/body/actor/tenant/idempotency/stale-precondition/error mapping；不改变 closure request boundary、write facade、Workbench relation command service、affected-months、refresh、权限、read model freshness 或 withdraw 写路径。
- 关键决策：route owner 复用 mutation session/body/tenant/precondition ports，并通过 `closure_request_boundary_provider` 显式调用 `TurnoverLedgerClosureRequestBoundaryFacade`；不直接 import `app.auth`，不解析 cookie/header 细节，不接收 whole `Application`。
- 文档影响：新增 modular IO closure confirm route callback collapse analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；外部往来状态机定义不变。
- 测试覆盖：新增 closure confirm source-inspect test 并更新 platform Guard；复跑 targeted closure confirm regressions 与完整 `tests.test_turnover_ledger_api`。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_closure_confirm_handler_delegates_affected_months_boundary_to_request_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_and_withdraw_require_mutation_permission_and_write_audit -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；closure withdraw、relation withdraw callbacks 仍未迁移。
- 后续事项：执行 `server-py:turnover-ledger-closure-withdraw-route-callback-collapse`。

## 2026-06-25 - confirm route-owner collapse

- 目标：执行 `server-py:turnover-ledger-confirm-route-callback-collapse`，把 `POST /api/turnover-ledger/relations/confirm` HTTP mapping 从 `server.py` 收到 `TurnoverLedgerApiRoutes.route(...)`。
- 影响范围：relation confirm 的 bank-row-id validation、session/body/actor/tenant/idempotency/stale-precondition/error mapping；不改变 confirm request boundary、write facade、affected-months、refresh、权限、read model freshness 或 closure/withdraw 写路径。
- 关键决策：route owner 复用 mutation session/body/tenant/precondition ports，并通过 `confirm_relation_request_boundary_provider` 显式调用 `TurnoverLedgerConfirmRequestBoundaryFacade`；不直接 import `app.auth`，不解析 cookie/header 细节，不接收 whole `Application`。
- 文档影响：新增 modular IO confirm route callback collapse analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；外部往来状态机定义不变。
- 测试覆盖：更新 confirm source-inspect tests 和 platform Guard；复跑 targeted confirm regressions 与完整 `tests.test_turnover_ledger_api`。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_relation_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_handler_delegates_affected_months_boundary_to_request_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_request_boundary_facade_owns_affected_months_resolution_and_response_field tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_request_expected_versions_reach_write_command tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_idempotency_key_replays_without_duplicate_confirm_or_refresh tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_relation_queue_failure_rolls_back_relation_confirm tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_confirm_relation_uow_path_does_not_clear_read_model_directly -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；closure confirm、closure withdraw、relation withdraw callbacks 仍未迁移。
- 后续事项：执行 `server-py:turnover-ledger-closure-confirm-route-callback-collapse`。

## 2026-06-25 - relation-extra route-owner collapse

- 目标：执行 `server-py:turnover-ledger-relation-extra-route-callback-collapse`，把 `PUT /api/turnover-ledger/relations/{relation_id}/extra` HTTP mapping 从 `server.py` 收到 `TurnoverLedgerApiRoutes.route(...)`。
- 影响范围：relation-extra PUT 的 payload object validation、session/body/actor/tenant/idempotency/stale-precondition/error mapping；不改变 extra normalization、write facade、refresh、权限、read model freshness 或 confirm/closure/withdraw 写路径。
- 关键决策：route owner 复用 mutation session/body ports，并通过 `relation_extra_request_boundary_provider` 显式调用 `TurnoverLedgerRelationExtraRequestBoundaryFacade`；tenant 与 stale precondition response payload 也以显式端口注入；不直接 import `app.auth`，不解析 cookie/header 细节，不接收 whole `Application`。
- 文档影响：新增 modular IO relation-extra route callback collapse analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；外部往来状态机定义不变。
- 测试覆盖：更新 relation-extra source-inspect tests 和 platform Guard；复跑 targeted relation-extra regressions 与完整 `tests.test_turnover_ledger_api`。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_handler_delegates_expected_versions_idempotency_and_stale_boundary tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_get_returns_default_structure_and_put_persists tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_put_rejects_invalid_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_put_rejects_readonly_user tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_relation_extra_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_relation_extra_idempotency_key_replays_without_duplicate_save_or_refresh -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；confirm、closure、withdraw callbacks 仍未迁移。
- 后续事项：执行 `server-py:turnover-ledger-confirm-route-callback-collapse`。

## 2026-06-25 - bank-row-tags route-owner collapse

- 目标：执行 `server-py:turnover-ledger-bank-row-tags-route-callback-collapse`，把 `POST /api/turnover-ledger/bank-row-tags/batch` HTTP mapping 从 `server.py` 收到 `TurnoverLedgerApiRoutes.route(...)`。
- 影响范围：bank-row-tags batch 的 body shape validation、session/body/actor/tenant/idempotency/error mapping；不改变 target validation、affected-months、legacy fallback、idempotency、refresh、权限、read model freshness 或其他 turnover ledger 写路径。
- 关键决策：route owner 复用 mutation session/body/tenant ports，并通过 `bank_row_tags_request_boundary_provider` 显式调用 `TurnoverLedgerBankRowTagsRequestBoundaryFacade`；不直接 import `app.auth`，不解析 cookie/header 细节，不接收 whole `Application`。
- 文档影响：新增 modular IO bank-row-tags route callback collapse analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；外部往来状态机定义不变。
- 测试覆盖：更新 bank-row-tags source-inspect tests 和 platform Guard；复跑 targeted bank-row-tags regressions 与完整 `tests.test_turnover_ledger_api`。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_turnover_bank_row_tag_batch_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_bank_row_tags_handler_delegates_validation_affected_months_and_flags_to_request_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_bank_row_tag_batch_save_updates_category_and_reflects_to_bank_details tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_bank_row_tag_batch_rejects_non_turnover_rows_without_refresh_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_bank_row_tags_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_bank_row_tags_idempotency_key_replays_without_duplicate_category_update_relation_rebuild_or_refresh -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；relation-extra、confirm、closure、withdraw callbacks 仍未迁移。
- 后续事项：执行 `server-py:turnover-ledger-relation-extra-route-callback-collapse`。

## 2026-06-25 - tag-selection write route-owner collapse

- 目标：执行 `server-py:turnover-ledger-tag-selection-write-route-callback-collapse`，把 `PUT /api/turnover-ledger/tag-selection` HTTP mapping 从 `server.py` 收到 `TurnoverLedgerApiRoutes.route(...)`。
- 影响范围：tag-selection PUT 的 session/body/actor/tenant/idempotency/error mapping；不改变 tag-selection settings 业务规则、审计、refresh、idempotency、权限、read model freshness 或其他 turnover ledger 写路径。
- 关键决策：route owner 通过显式端口接收 mutation session resolver、session error detector、JSON body loader、tenant provider 和 tag-selection request-boundary provider；不直接 import `app.auth`，不解析 cookie/header 细节，不接收 whole `Application`。
- 文档影响：新增 modular IO tag-selection route callback collapse analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；外部往来状态机定义不变。
- 测试覆盖：更新 tag-selection source-inspect test 和 platform Guard；复跑 targeted tag-selection regressions 与完整 `tests.test_turnover_ledger_api`。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_ledger_tag_selection_handler_does_not_inline_legacy_fallback_side_effects tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_ledger_tag_selection_get_put_and_version_conflict tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_tag_selection_idempotency_key_conflict_rejects_different_payload tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_tag_selection_idempotency_key_replays_without_duplicate_settings_save_or_refresh tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_turnover_ledger_tag_selection_queue_failure_rolls_back_settings_save -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；bank-row-tags、relation-extra、confirm、closure、withdraw callbacks 仍未迁移。
- 后续事项：执行 `server-py:turnover-ledger-bank-row-tags-route-callback-collapse`。

## 2026-06-25 - write route callback audit

- 目标：执行 `server-py:turnover-ledger-write-route-callback-audit`，审计 read/export GET collapse 后剩余的 `/api/turnover-ledger*` 写路径 callbacks。
- 影响范围：tag-selection PUT、bank-row-tags batch POST、relation extra PUT、relation confirm POST、closure confirm POST、closure withdraw POST、relation withdraw POST；本轮不改运行时代码。
- 关键决策：下一实现边界选择 `server-py:turnover-ledger-tag-selection-write-route-callback-collapse`。tag-selection PUT 是最薄的写 callback，只做 session/body/actor/tenant/idempotency/error 映射并委托 `TurnoverLedgerTagSelectionRequestBoundaryFacade`；bank-row-tags、relation-extra、confirm、closure、withdraw 涉及目标校验、stale precondition、affected months、Workbench relation command 或 operation visibility，后续分组迁移。
- 文档影响：新增 modular IO write route callback audit analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt 和本实施记录；外部往来状态机定义不变。
- 测试覆盖：本轮为 analysis-only，未改代码；下一实现边界需更新 tag-selection source-inspect tests、platform Guard 和 API 回归。
- 验证命令：提交前运行 `bash scripts/verify.sh docs` 与 `git diff --check`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；mutation callbacks 仍未完成迁移。
- 后续事项：执行 `server-py:turnover-ledger-tag-selection-write-route-callback-collapse`。

## 2026-06-25 - read/export GET route-owner collapse

- 目标：执行 `server-py:turnover-ledger-read-export-route-callback-collapse`，把外部往来 read/export/GET HTTP mapping 从 `server.py` 收到 `TurnoverLedgerApiRoutes.route(...)`。
- 影响范围：`GET /api/turnover-ledger`、`GET /api/turnover-ledger/export-preview`、`GET /api/turnover-ledger/export`、`GET /api/turnover-ledger/tag-selection`、`GET /api/turnover-ledger/relations/{relation_id}`、`GET /api/turnover-ledger/relations/{relation_id}/extra` 的 HTTP 参数解析、错误映射和 response adapter；不改变 grouped payload、read model freshness、导出字段、权限、闭环、撤回、tag-selection PUT、bank-row-tags、extra PUT 或 Workbench relation 写边界。
- 关键决策：`TurnoverLedgerApiRoutes` 作为 route owner 接收 `json_response`、`export_response`、`tag_selection_provider` 三个显式端口；`Application` 只保留端口组装、XLSX response 平台 adapter 和未迁移的 mutation callbacks。
- 文档影响：新增 modular IO analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；外部往来业务状态机定义不变。
- 测试覆盖：新增 `test_turnover_ledger_read_export_routes_use_route_owner` 静态 Guard，更新 export limit API 测试注入点到 route owner；复跑 read facade、turnover ledger API 和 route-owner inventory Guard。
- 验证命令：`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_read_facade -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_turnover_ledger_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、真实 Browser、admin/write evidence 和生产写入闭环仍未执行；mutation callbacks 仍需后续审计，不能声明外部往来模块全局 closed。
- 后续事项：执行 `server-py:turnover-ledger-write-route-callback-audit`。

## 2026-06-25 - turnover ledger route-owner audit

- 目标：执行 `server-py:turnover-ledger-route-owner-audit`，审计 `/api/turnover-ledger*` 在 `server.py` 的剩余 route ownership。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、turnover-ledger 实施记录；不改变外部往来业务、写入、read model freshness、operation barrier、Workbench relation command 边界、导出或前端行为。
- 关键决策：read/export/GET callbacks 是围绕 `TurnoverLedgerReadFacade`、`TurnoverLedgerApiRoutes` 和 settings payload 的薄 HTTP wrapper，可先做 route-owner collapse；mutation callbacks 仍承担 session/body/idempotency/stale precondition/error mapping，后续单独审计。
- 文档影响：新增 modular IO turnover ledger route-owner audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt；外部往来状态机定义不变。
- 测试覆盖：本轮为分析/状态机闭合，未改运行时代码；下一实现边界需覆盖 `tests/test_turnover_ledger_api.py`、`tests/test_turnover_ledger_read_facade.py` 和 `tests/test_platform_runtime_boundary_guards.py`。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `turnover-ledger` worker drain、真实闭环/撤回 Browser 样本、admin/write evidence 仍为最终验证范围。
- 后续事项：执行 `server-py:turnover-ledger-read-export-route-callback-collapse`。

> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 外部往来款管理 Spec-first E2E 本地闭环状态为 `spec-first-covered`：`TURNOVER-E2E-001..009` 已映射到 Browser、组件、API、后端和 integration 覆盖；`TURNOVER-E2E-010` 真实基础设施 worker drain 明确保留为 staging/runtime risk。
- 后续只有发现明确 P0/P1 缺口、真实 bug 或业务规则变化时，再按 `e2e-spec.md` 和 `tests.md` 中七类矩阵补测试。
- 手动零差额闭环写入 Workbench active pair relation 作为共同事实源；系统 `deterministic` 只表示自动识别出的零差额组合，不是已闭环事实。外部往来闭环 relation 在关联台保留同一个 `turnover_manual_closure` active case/evidence；新写入关系必须从所选流水的有效规则标签冻结真实 `requires_oa`、`requires_invoice`、source 和 version。纯银行闭环若要求 OA/发票则以同一 case 留在未配对区，全部要求满足后才进入 paired。metadata 缺失的旧闭环关系 fail closed，只能由受控 repair 补齐；规则保存不得追溯改写。若闭环确认前已有 OA-bank relation，可在其全部银行成员均属于本次选择时合并为同一个包含 `oa` + `bank` rows 的 active case。
- PostgreSQL SQL runtime 下外部往来闭环的银行流水事实源必须是 `bank_detail` SQL read model，并保留 Workbench 使用的 legacy/source row id；不能再从 legacy import snapshot 推导可闭环流水。
- 手动零差额闭环支持同组多流水；至少一收一支且收支合计差额为 `0.00`。已确认后不能追加流水，漏选时先撤回原闭环关系再重新选择。
- 外部往来页撤回只允许 row types 子集为 `{oa, bank}` 的 `turnover_manual_closure`；若已在关联台补齐发票或其他业务 row type，必须去关联台撤回完整关系。
- `readModelStatus !== "fresh"` 时前端必须显示诊断并避免把旧 grouped payload 当作最终业务结论；manual closure 这类依赖页面所选 flow row versions 的写操作必须先阻断或等待 fresh 后重新加载并重绑定，后端 stale precondition、canonical write safety、权限/session、DB 和 idempotency/version 继续作为最终兜底。写 API 成功后必须用全屏 operation overlay 等待 `turnover_ledger` barrier fresh 并重新加载。
- 写路径应优先保持 `TurnoverLedgerWriteFacade` / `TurnoverLedgerWriteUnitOfWork` 边界；legacy fallback 只作为兼容风险存在，不能继续扩大。
- 涉及 Workbench relation 的 manual closure/withdraw 即使经过 legacy fallback facade，也必须通过 `WorkbenchRelationCommandService`；缺 command service 时 fail fast，不允许 direct pair relation write fallback。
- 外部往来闭环和 OA/发票关联是两个不同事实：OA/发票关联 chip 只展示，不参与“确认闭环/撤回闭环”的决定链路；前端只展示正向 chip，“已关联 OA”“已关联 发票”“收支闭环”。未闭环不显示 chip。确认闭环可合并所选银行流水已有的 OA-bank active relation；撤回闭环只撤回同一 `cash_closure_case_id` 的 Workbench active case，并恢复确认前的 OA-bank relation。
- 前端 domain event 只作为刷新提示；跨页面一致性仍由后端 dirty/outbox、read model freshness 和 worker readiness 保证。
- export-preview/export 是同步生成路径；group 总数或展开后的 formal rows 超过 20,000 时必须返回 `turnover_ledger_export_row_limit_exceeded`，不能继续生成大预览或 XLSX。

## 2026-06-24 - Read model local implementation closure audit

- 目标：执行 modular IO slice `read-models:turnover-ledger-local-implementation-closure-audit`，确认外部往来台账 read model 本地实现是否还存在旧链路污染或未分类 authoritative 行为。
- 影响范围：外部往来 query service、repository port、SQL projection builder、refresh producer、worker refresh service、write UoW、legacy fallback adapters、bank detail side-effect callback、frontend operation barrier usage 和测试/状态文档；不改变外部往来 grouped payload、闭环、撤回、标签、extra、导出、权限、审计或前端行为。
- 关键决策：未发现剩余本地 implementation gap。`Application` 已不拥有 turnover refresh/clear helper；事务内写路径通过 dirty outbox writer 和 scope policy；非事务刷新通过 `TurnoverLedgerReadModelRefreshProducer`；worker 只消费 `turnover_ledger.read_model.refresh` 并 complete dirty scope。`BankDetailsApplicationService` 内部同名 wrapper 只作为 producer callback 缺失时的 local/isolated compat fallback，正常 server factory 已注入 producer。
- 测试覆盖：本轮是 analysis/accounting only，复用 turnover producer/query/refresh/API、manifest、runtime worker registry、operation barrier、platform boundary guard 和前端 operation barrier 测试证据。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-turnover-ledger-local-implementation-closure-audit.md`。
- 未测风险：真实 PostgreSQL rows/source_versions/readiness、真实 turnover worker drain、真实 App Status/dirty/outbox 状态、高行数 grouped ledger 性能和 authenticated browser smoke 仍 deferred；这不是外部往来模块全局 closed。

## 2026-06-24 - Read model refresh producer and clear port extraction

- 目标：执行 modular IO slice `read-models:turnover-ledger-refresh-producer-clear-port-extraction`，移除 `Application` 拥有的 turnover read model refresh/clear helper。
- 影响范围：外部往来 read model refresh producer、turnover legacy fallback wiring、bank detail category side-effect wiring、relation mutation invalidation 和相关测试；不改变外部往来 grouped payload、闭环、撤回、标签、extra、导出、权限、审计或前端行为。
- 关键决策：`TurnoverLedgerReadModelRefreshProducer` 是非事务 turnover read model refresh/clear 的显式边界。refresh 仍走 `ReadModelRefreshGateway.enqueue_many("turnover_ledger", ...)`；best-effort clear 只走 `_turnover_ledger_sql_read_repository` 暴露的 `clear_turnover_ledger_rows()`，不再通过 broad `_workbench_sql_read_repository`。
- 测试覆盖：新增 producer 单测，更新 turnover API regression 和 platform runtime boundary guard，证明旧 app helper 不能返回为权威实现。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-turnover-ledger-refresh-producer-clear-port-extraction.md`。
- 未测风险：本 slice 不执行真实 PostgreSQL/worker/App Status/high-row/browser 验证；`turnover_ledger` 仍需 local implementation closure audit 后才能进入 production evidence defer。

## 2026-06-24 - Read model freshness and barrier audit

- 目标：执行 modular IO slice `read-models:turnover-ledger-refresh-freshness-operation-barrier-audit`，审计外部往来台账 read model fresh gate、force refresh、operation barrier 和旧链路污染。
- 影响范围：外部往来 SQL fresh gate、scope policy、manifest/App Status/worker registry、Workbench relation source-version proof、operation barrier tests 和 `Application` turnover read model clear/refresh helper；不改变运行时代码。
- 关键决策：现有 `TurnoverLedgerQueryService` 已走 `ReadModelQueryGateway`，`turnover_ledger` scope policy 是 month/all，manifest/App Status/worker registry 已登记，projection 在 Workbench relation 不 fresh 时不保存半成品，写后 barrier 已有 `turnover_ledger:all` 阻断证据。但 `Application._enqueue_turnover_ledger_read_model_refreshes(...)` 和 `_clear_turnover_ledger_read_model_best_effort(...)` 仍是 app-owned helper，且 clear 仍通过 broad workbench SQL repository，必须先抽出或改走 turnover-specific port。
- 测试覆盖：本轮是 analysis/accounting only；下一实现 slice 必须新增/更新 refresh producer / clear port guard。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-turnover-ledger-refresh-freshness-operation-barrier-audit.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；`turnover_ledger` 不能声明 local closure。

## 2026-06-24 - Read model repository port extraction

- 目标：执行 modular IO slice `read-models:turnover-ledger-repository-port-extraction`，让外部往来台账 read model 的查询和 projection 保存通过窄 repository port。
- 影响范围：`TurnoverLedgerReadModelRepositoryPort`、PostgreSQL state-store turnover read wiring、`TurnoverLedgerQueryService` 注入、worker projection builder 注入和 query service tests；不改变外部往来 grouped payload、闭环、撤回、标签、extra、导出、权限或前端行为。
- 关键决策：port 只暴露 `list_turnover_ledger_view`、`save_turnover_ledger_rows`、`clear_turnover_ledger_rows`。`PostgresReadModelRepository` 继续是 SQL/table owner；`Application` 不再把 turnover query service 接到 broad workbench SQL read repository。
- 测试覆盖：新增 port guard，证明 cost/tax/search/no-OA/bank-detail 等无关 read model 方法不会通过 turnover port 暴露；复跑 turnover query/refresh 回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-turnover-ledger-repository-port-extraction.md`。
- 未测风险：本 slice 不证明 fresh gate、force refresh、operation barrier、生产 worker drain 或真实 PostgreSQL SLO；下一轮必须执行 turnover freshness/barrier/legacy contamination audit。

## 2026-06-22 - 外部往来闭环关联台三栏分区纠偏

- 目标：修复贾小花三笔纯银行外部往来闭环进入关联台“已配对”区域的问题。
- 真实原因：2026-06-21 的修复把 `turnover_manual_closure` active relation ownership 和 Workbench paired zone completeness 混为一谈；`WorkbenchCandidateGroupingService` 对 bank-only turnover group 放行到 paired，SQL projection 进入 paired serializer 后又把 chip 覆盖成“完全关联”。
- 关键决策：`turnover_manual_closure` 继续写 Workbench active relation，外部往来页继续显示“收支闭环”并支持撤回；关联台分区必须遵守 relation metadata requirement，bank-only / OA+bank-only 未满足 paired 条件时留在 canonical `case:<case_id>` open 待处理区，满足后进入 paired。generation consistency 允许 active relation row 出现在 canonical open owner，禁止的是非 canonical open/temp owner。
- 文档影响：同步产品规格、app architecture、关联台和外部往来模块文档。
- 测试覆盖：新增/更新 `test_manual_zero_difference_closure_creates_open_bank_only_workbench_relation_until_invoice_exists`、`test_manual_closure_accepts_three_bank_rows_and_keeps_workbench_case_open_until_invoice_exists`、`test_bank_only_turnover_manual_closure_rows_stay_open_until_three_way_complete`、`test_two_pane_turnover_manual_closure_rows_stay_open_until_invoice_exists`、`test_three_pane_turnover_manual_closure_rows_render_as_paired_case`、`test_sql_projection_keeps_turnover_manual_closure_bank_only_case_open_until_three_way_complete`。

## 2026-06-21 - 外部往来闭环关联台 paired 可见性修复（已被 2026-06-22 纠偏）

- 目标：修复贾小花三笔外部往来手动闭环确认后，外部往来台账能检测到闭环关系，但关联台没有显示同一个 paired case，App Status 继续显示 Workbench generation consistency failed 的问题。
- 真实原因：前序修复已经让本地 Turnover relation 和 Workbench active relation 写入成功；剩余阻断来自 Workbench read model 分组规则。SQL/legacy projection 给银行行写入 `relation_mode=turnover_manual_closure` 和 relation code `turnover_manual_closure`，但 grouping 未把这个 code 当 paired，并按旧 “bank-only open” 规则把 active relation rows 发布到 open/temp，触发 `active_relation_open_membership` consistency failure。
- 关键决策（历史错误）：`turnover_manual_closure` 多银行 active relation 曾被视为外部往来完整闭环并展示在 paired 区；该 paired zone 口径已在 2026-06-22 撤销，当前规则要求未满足 paired 条件时留在 open 待处理区。
- 文档影响：同步产品规格、app architecture、关联台和外部往来模块文档。
- 测试覆盖（历史，已由 2026-06-22 三栏分区测试替换）：当时新增/更新过 bank-only paired 断言；当前不再作为有效测试口径。

## 2026-06-21 - Manual closure Workbench all 普通刷新阻断

- 目标：修复外部往来页确认贾小花三笔 manual zero-difference closure 后，页面 loading 变慢、关联台不刷新，App Health 显示 `workbench_all_scope_parent_inconsistent` 阻断的问题。
- 影响范围：`TurnoverLedgerWriteFacade.confirm_zero_difference_closure(...)` dirty/outbox scope、Workbench 月 shard/aggregate-only all 收敛链路、外部往来闭环后跨页可见性。
- 真实原因：闭环 API 响应的硬等待目标已经在 2026-06-17 收窄为 `turnover_ledger:all` + 受影响月份 `workbench_relation`，但写 UoW 仍额外投递普通 `workbench:all` / `workbench_relation:all` refresh。普通 `workbench:all` 会触发 all-scope shard/聚合路径，在受影响月 shard 尚未 fresh 时写出 `workbench_all_scope_parent_inconsistent` failed generation，导致运行状态阻断、队列 failed/backlog，关联台跨页刷新看不到新 case。
- 关键决策：已知 affected months 时，manual closure confirm 只投递受影响月份的 `workbench` / `workbench_relation` scope；`workbench:all` 继续由现有月 shard 发布后的 aggregate-only 事件更新。只有无法推导月份时才保留普通 `all` fallback。
- 文档影响：更新本实施记录和 `tests.md`；不改变 API 响应字段或前端交互契约。
- 测试覆盖：更新 `tests/test_turnover_ledger_uow_contract.py::TurnoverLedgerUoWContractTests::test_target_zero_difference_closure_facade_writes_turnover_and_workbench_pair_relation`，断言闭环确认在已知月份时不投递普通 `workbench:all` / `workbench_relation:all`。
- 未测风险：本地测试未连接真实生产 worker 队列清理既有 failed job；发布后仍需通过 App Health/queue drain 验证历史 failed/backlog 已清空或被重试处理。

## 2026-06-21 - 孤儿 turnover 闭环恢复 Workbench active case

- 目标：修复外部往来款页面选择贾小花三条同组流水确认闭环时，后端返回 `Bank transaction already belongs to an active turnover closure.`，但关联台没有显示这三条流水处于同一个 active case 的不一致。
- 真实原因：外部往来本地 `TurnoverRelationService` 已有同一批流水的 `manual_zero_difference_group` confirmed relation，所以本地台账可计算“已闭合计”；但 Workbench canonical active relation 中缺少对应 `turnover:{relation_id}` case，关联台自然不显示配对。再次确认时，本地 `_ensure_no_manual_closure_overlap()` 在 Workbench command service 写入前直接拒绝，导致无法修复这个孤儿闭环。
- 关键决策：同一批 `bank_row_ids` 已存在本地 manual closure 时，允许 `confirm_zero_difference_closure()` 复用同一个 `relation_id` 继续执行下游 Workbench `turnover_manual_closure` 写入，用于恢复缺失 active case；部分重叠或 Workbench 中已有其他 active `turnover_manual_closure` 仍必须拒绝，避免覆盖真实闭环。
- 文档影响：更新本实施记录和 `tests.md`；业务口径、API shape、read model/worker 状态机不变。
- 测试覆盖：新增/更新 `test_confirm_zero_difference_closure_reuses_exact_existing_closure_rows`、`test_confirm_zero_difference_closure_rejects_partial_existing_closure_overlap`、`test_manual_closure_repairs_orphaned_turnover_closure_without_workbench_case`。
- 未测风险：本地没有直连生产库对截图中的贾小花真实 row id 执行 mutation；已用同形态三流水、孤儿 turnover closure 和 Workbench 缺 active case 的集成测试覆盖服务端路径。

## 2026-06-21 - 普通 confirmed relation 升级为手动闭环

- 目标：修复外部往来款页面选择 `txn_imported_1277`、`txn_imported_1292`、`txn_imported_1344` 三条同组流水确认闭环时，后端返回 `Bank transaction already belongs to an active turnover relation` 的问题。
- 真实原因：不是金额不平、前端误允许选择或 Workbench OA-bank 合并失败。错误文案来自 `TurnoverRelationService._ensure_no_active_confirmed_overlap()`；这三条流水已经处于 Turnover 本地普通 `confirmed` relation，但尚未带 `manual_zero_difference_group` 闭环 evidence。`confirm_zero_difference_closure()` 在检查已闭环关系前先用通用 active confirmed overlap 规则拦截，导致同一 row 集合不能从普通 confirmed relation 升级为手动闭环，Workbench `turnover_manual_closure` 写入链路也没有执行。
- 关键决策：手动零差额闭环先拒绝已存在的 manual closure overlap；普通 `confirmed` relation 只有在 `bank_row_ids` 与本次选择完全一致时允许升级并复用同一 `relation_id`，部分重叠仍按 `turnover_relation_conflict` 拒绝，避免绕过“漏选需先撤回再重选”的闭环约束。
- 文档影响：更新本实施记录和 `tests.md`；既有业务口径、API shape、read model/worker 状态机不变。
- 测试覆盖：新增 `test_confirm_zero_difference_closure_upgrades_existing_confirmed_relation_for_same_rows`，并运行 `tests.test_turnover_relation_service`、`tests.test_turnover_workbench_integration`、`tests.test_turnover_ledger_uow_contract`。
- 未测风险：本地未连接真实生产 PostgreSQL 对截图三笔原始流水执行写入；已用同形态三流水和普通 confirmed relation 复现服务端拦截点，并用 Workbench/UoW 回归保护下游合并链路。

## 2026-06-20 - grouped ledger 加载失败刷新恢复

- 目标：补齐外部往来款首屏 `GET /api/turnover-ledger` 暂时失败后的 Browser 恢复链路，防止 API 503 被页面误显示成普通“暂无往来款台账”空态，或恢复后残留失败文案。
- 影响范围：`TurnoverLedgerPage` 刷新入口、`TurnoverLedgerGroupedTable` 错误态空态 guard、`web/e2e/fixtures/apiMocks.ts` turnover ledger 临时失败 mock、`web/e2e/turnover-ledger-flow.spec.ts`、`web/src/test/TurnoverLedgerPage.test.tsx` 和本模块/全局测试文档。
- 关键决策：不改变外部往来业务逻辑、manual closure、withdraw、tag-selection 或 read model freshness 规则；新增 `刷新台账` 只复用现有 `loadLedger`，错误态只阻止普通空态展示。
- 测试覆盖：组件测试覆盖首次 GET 503 显示“往来款台账加载暂时失败，请刷新后重试。”且不显示普通空态，点击刷新后 grouped table 恢复；Browser 测试覆盖真实 Chromium 中首屏 503、用户手动刷新直到 200/fresh、grouped rows 恢复、未选择时确认闭环保持禁用、成功恢复后无可见错误残留和无隐藏浏览器错误。
- 未测风险：真实网络中断、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、生产历史外部往来关系和大数据 grouped table 性能仍需 staging/runtime smoke。

## 2026-06-19 - 成功写流可见错误残留 guard

- 目标：防止外部往来 tag-selection、manual closure、成本统计 fan-out 或 withdraw 已成功，但页面仍残留“操作失败/同步失败/read model 失败”等可见错误提示。
- 影响范围：`web/e2e/turnover-ledger-flow.spec.ts`、`tests/test_playwright_e2e_strict_diagnostics.py`、本模块测试矩阵和全局测试文档。
- 关键决策：不改变产品逻辑或 deterministic mock；在标签保存、确认闭环、成本统计下游展示和撤回成功节点复用 `expectNoUnexpectedSuccessUiErrors(...)`，把“成功但报错提示仍显示”作为 Browser 回归失败。
- 文档影响：更新本模块 `tests.md`、`e2e-coverage.md` 和全局 testing closure state。
- 测试覆盖：`web/e2e/turnover-ledger-flow.spec.ts` 加强 tag-selection、manual closure、cost fan-out 和 withdraw 成功路径；静态诊断防止后续移除该 guard。
- 验证命令：`cd web && npx playwright test e2e/turnover-ledger-flow.spec.ts --project=chromium`；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`。
- 未测风险：真实生产外部往来写入仍需真实认证、业务审批和可回滚 scenario；本轮只覆盖 deterministic Browser flow 的可见错误残留。

## 2026-06-19 - Spec-first E2E covered 校准

- 目标：把外部往来款管理从旧测试闭环 `documented-risk` 校准为页面级 Spec-first E2E covered，明确本地自动化覆盖和真实基础设施风险边界。
- 影响范围：`docs/modules/turnover-ledger/e2e-spec.md`、`docs/modules/turnover-ledger/e2e-coverage.md`、`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、本模块 README/tests/implementation notes 和全局 Spec-first inventory。
- 关键决策：
  - 新增 `TURNOVER-E2E-001..010`，覆盖页面 ready、标签准入保存、manual closure、成本统计 downstream fan-out、withdraw recovery、Workbench/OA 合并边界、stale 防 false-empty、extra、导出/权限和真实 infra worker drain。
  - Browser 增量覆盖标签准入保存：断言 `PUT /api/turnover-ledger/tag-selection` body、`turnover_ledger:all` operation barrier、ledger reload、成功反馈和零浏览器错误。
  - 不把真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实 search UI、真实 XLSX 打开和生产历史数据写成本地 CI covered；这些继续由 `infra-smoke`、staging 或生产前 smoke 验证。
- 测试覆盖：更新 `web/e2e/turnover-ledger-flow.spec.ts` 和 deterministic mock 的 turnover tag-selection mutable state。
- 验证命令：`cd web && npx playwright test e2e/turnover-ledger-flow.spec.ts --project=chromium`。
- 未测风险：真实 worker drain、真实大月份、真实 XLSX 打开、生产半迁移历史数据和 legacy fallback 删除专项仍需 staging/runtime smoke。

## 2026-06-19 - Browser e2e 补 turnover 到成本统计 fan-out

- 目标：把外部往来 manual closure 的 Browser E2E 从本页 confirm/withdraw 扩展到下游成本统计，避免“周转页显示成功但成本统计仍读旧 read model 或浏览器有隐藏报错”。
- 影响范围：`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、外部往来和成本统计测试矩阵、全局 Spec-first E2E inventory。
- 关键决策：
  - 测试不改变产品逻辑，只新增 opt-in deterministic mock `turnoverCostFanout` 表示 closure 已确认后成本统计 fresh read model 包含对应成本行。
  - Browser 流在确认闭环并等待 operation barrier 后跳到成本统计，断言 `/api/cost-statistics/explorer` 返回 `read_model_status=fresh`，按项目/费用类型/流水表展示 `外部往来闭环成本项目`、`外部往来款付款`、`浏览器 e2e 归还借款` 和 `建设银行`，再回外部往来完成撤回。
  - 新增严格浏览器错误捕获：`pageerror`、`console.error`、非 abort `requestfailed` 和未预期 dialog 均会失败。
- 文档影响：更新本文件、`tests.md`、成本统计模块测试/覆盖/实施记录和全局 testing closure 文档。
- 测试覆盖：更新 `web/e2e/turnover-ledger-flow.spec.ts` 和 `web/e2e/fixtures/apiMocks.ts`。
- 验证命令：`cd web && npx playwright test e2e/turnover-ledger-flow.spec.ts --project=chromium`。
- 未测风险：本地仍是 mocked Browser E2E，不证明真实 PostgreSQL/RabbitMQ/Redis/systemd `turnover-ledger` 与 `cost-statistics` worker drain；真实环境需要 staging/production smoke。

## 2026-06-17 - 手动闭环后保留同对方未选流水

- 真实原因：`TurnoverRelationService.rebuild_from_bank_rows()` 先把同业务类型、同对方的所有流水建成一个自动 relation，再用已确认手动闭环 row ids 过滤自动 relation。只要自动 relation 和已闭环两笔有交集，整个同对方自动 relation 都被删除，导致房克丽名下其他未选流水从外部往来页消失。
- 关键决策：已确认手动关系只排除它自己的 active row ids；自动 relation 重建输入必须先跳过这些 active row ids，剩余同对方流水继续参与自动分组。撤回后的 `withdrawn` relation 不算 active，相关流水可重新进入自动分组。
- 回归保护：新增 `test_manual_closure_keeps_remaining_same_counterparty_rows_in_auto_relation` 和 `test_grouped_ledger_keeps_unselected_same_counterparty_flows_after_manual_closure`，覆盖“四笔同对方流水，闭环两笔后 grouped payload 仍保留四笔 flow rows”。

## 2026-06-17 - 写成功后 read model 同步误报失败修复

- 真实原因：外部往来 manual closure 写入已经成功，但 API 返回的 hard `freshness_targets` 包含 `workbench:all`；生产 `workbench:all` 聚合处于 `workbench_all_scope_parent_inconsistent` blocked，前端把 post-write operation barrier blocked 冒泡给 `GlobalOperationOverlayProvider`，于是用户看到“操作失败”，但 canonical relation 和 Workbench active case 已经建立。
- 关键决策：外部往来写操作的 hard operation visibility targets 只保留本页可见性与关联台关系可见性：`turnover_ledger:all` 和受影响月份 `workbench_relation`。`workbench` 月份/all active generation、成本统计、搜索等 downstream read model 仍由 UoW dirty/outbox 刷新，但不再作为本页面写操作 overlay 释放条件。
- 前端边界：POST 成功之前的 fresh gate、stale precondition、权限/session、DB/idempotency 错误继续作为操作失败；POST 成功之后的 operation barrier blocked/timeout 或 grouped reload 失败降级为“操作已提交，后台同步尚未完成，请稍后刷新。” warning，不得弹“操作失败”。
- 回归保护：更新 closure freshness target contract 测试和页面交互测试，新增“提交成功后 barrier blocked 不显示操作失败”的组件用例。

## 2026-06-17 - 收支闭环 chip 与关联台撤回链路统一

- 目标：外部往来款管理不再显示“已关联业务单据”“未闭环”“部分已闭环”“候选关联”等旧 chip；只显示正向事实 chip：“已关联 OA”“已关联 发票”“收支闭环”。已经在关联台形成同一组银行收支闭环的流水，在外部往来页也应显示“收支闭环”，并可从同一组流水直接撤回。
- 影响范围：`TurnoverLedgerSqlProjectionBuilder` grouped projection、外部往来写 facade/request boundary、`server.py` turnover closure withdraw route、前端 turnover ledger API mapper、grouped table、toolbar 选择逻辑、e2e fixtures、模块/API 文档。
- 关键决策：
  - chip 事实源收敛到后端 projection 字段：`linked_oa`、`linked_invoice`、`cash_closure_linked`、`cash_closure_case_id/source/relation_id`。前端不得再从 `workbench_relation_status/mode` 或 row id 规则推断泛化业务单据 chip 或负向闭环 chip。
  - `cash_closure_linked=true` 的来源包括外部往来页创建的 `turnover_manual_closure`，以及关联台已经把同一往来组银行收入/支出配成同一个零差额 Workbench case 的关系；后者只在 Workbench relation read model fresh 且 relation 内 bank rows 可完整落回当前 group 时投影。
  - toolbar 使用单个主按钮：未闭环选择显示“确认闭环”；全部选择同一 `cash_closure_case_id` 且 `cash_closure_linked=true` 时显示“撤回闭环”。同次选择禁止混合已闭环/未闭环，也禁止跨多个 closure case 撤回。
  - 外部往来本页创建的 `turnover_manual_closure` 保留既有 `/api/turnover-ledger/relations/{relation_id}/withdraw`；关联台来源的 `cash_closure_case_id` 通过新增 `/api/turnover-ledger/closures/withdraw`，经 `TurnoverLedgerWriteFacade`、`TurnoverLedgerWorkbenchPairPort` 委托 `WorkbenchRelationCommandService.withdraw_relation(case_id=...)`，不直接改 pair snapshot。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md`、本实施记录、`docs/dev/api-contracts.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：新增/更新 `test_projection_marks_workbench_bank_pair_as_cash_closure_when_group_zeroes_out`、`test_turnover_cash_closure_withdraw_route_uses_closure_boundary`、`test_turnover_workbench_pair_port_delegates_cash_closure_withdraw_to_relation_command_service`、`test_turnover_workbench_pair_port_requires_relation_command_service_for_cash_closure_withdraw`、`withdrawTurnoverClosure` API mapper 测试、`withdraws a selected linked manual closure from the table toolbar`、`shows Workbench relation feedback from the grouped ledger payload` 和 `web/e2e/turnover-ledger-flow.spec.ts`。
- 验证命令：`pytest tests/test_turnover_ledger_read_model_refresh.py tests/test_turnover_ledger_api.py tests/test_workbench_relation_read_facade.py -q`；`cd web && npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx`；`cd web && npx playwright test e2e/turnover-ledger-flow.spec.ts`；`cd web && npm run build`；`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：本地 e2e 使用 mock 后端和小样本，不能证明真实生产历史 Workbench relation 分布中所有半迁移 case 都能被投影为同组零差额闭环；发布后仍需对真实数据执行 worker drain/requeue，并用实际页面选择同一组闭环流水 smoke 一次。

## 2026-06-17 - bank detail tag facade 版本字段透传修复

- 目标：修复生产发布 `44bcd1f7` 并重建 read model 后，外部往来款管理页选择 `txn_imported_1269` 与 `txn_imported_1361` 点击“确认闭环”仍报“银行流水状态已变化，请刷新后重试。”的问题。
- 真实原因：生产 release 已经是新版本，`turnover_ledger:all` read model 也可以处于 fresh；失败不是旧部署或页面没有刷新。真正问题在跨 read-model 边界：`TurnoverLedgerSqlProjectionBuilder` 通过 `BankTransactionTagReadFacade.bulk_get_for_rows(...)` 读取 fresh `bank_detail` 标签事实时，facade 的 `_standardize_bank_detail_row` / `_provider_compatible_category` 丢弃了 `category_version`、`manual_category_version`、`version`。因此 turnover worker 从 fresh bank_detail 重建出的 grouped flow rows 仍带 `category_version=0`，前端按 fresh/rebind 规则提交 `expected_versions=0`，后端 precondition 再读当前 bank detail 版本 `1/2` 时正确拒绝为 stale。
- 影响范围：`BankTransactionTagReadFacade` 到 `TurnoverLedgerSqlProjectionBuilder` 的 downstream tag provider contract；不改变手动闭环金额规则、Workbench relation 写入口、stale precondition 或 read model freshness gate。
- 关键决策：bank detail tag facade 必须把版本字段作为 publishable downstream contract 透传；继续保留 `TurnoverLedgerBankRowStalePreconditionPort` 的严格版本校验，不用放宽并发保护掩盖投影字段错误。
- 生产验证：在 active release 热修复 facade、重启 API 与 `fin-ops-worker@turnover-ledger`，重新入队 `turnover_ledger:all` 并等 dirty/outbox pending 清零；生产 read model 中刘涵静 `txn_imported_1269/1361` 版本从 `0` 变为 `1`，贾小花 `txn_imported_1277/1292/1344` 版本为 `2`；非写入 precondition probe 对 `txn_imported_1269/1361` 通过。
- 测试覆盖：新增 `BankTransactionTagReadFacadeTests.test_bulk_get_for_rows_preserves_versions_for_downstream_preconditions`，并更新 `test_get_by_transaction_ids_returns_standardized_fresh_tagged_rows` 锁定 standardized row 的版本字段。
- 未测风险：本轮没有在生产直接执行确认闭环写操作；只执行了非写入 precondition probe。生产热修复会在下一次正式发布时被 release 内容覆盖，必须把本地变更提交、推送并重新发布成新 release。

## 2026-06-17 - grouped read model 版本投影与 schema 失效修复

- 目标：修复生产外部往来款管理页选择 `txn_imported_1269` 与 `txn_imported_1361` 两笔 240,000 确认闭环时仍报“银行流水状态已变化，请刷新后重试。”的问题，并说明上一轮为什么没改好。
- 真实原因：生产前后端都已部署上一轮修复；问题不是旧代码、OA 关联 chip 或金额不平。Chrome 登录态检查显示 grouped API 对这两条 flow row 仍返回 `category_version=0`，且没有 `manual_category_version` / `version`。上一轮修复了 live bank detail 转换、前端 mapper 和 stale precondition，但漏掉了 saved `turnover_ledger` grouped read model 投影；同时 `TURNOVER_LEDGER_SCHEMA_VERSION` 没有 bump，旧 projection 被 API 当 fresh 返回。前端按 fresh/rebind 规则重拉后仍只能提交 `expected_versions=0`，后端 live precondition 读取非零真实版本后正确拒绝为 stale。
- 影响范围：`TurnoverLedgerService` grouped flow row 投影、`turnover_ledger_schema_version` source version、写入 stale precondition 共享版本 helper、本模块测试矩阵和 read-models 记录。
- 关键决策：抽出共享 `turnover_bank_row_version`，按 `category_version`、`manual_category_version`、`version` 顺序取第一个非零数值；`TurnoverLedgerService` 在 bank rows、classified flow rows、unclassified flow rows 都使用同一语义，并保留 fallback 字段供前端 mapper 兜底。将 `TURNOVER_LEDGER_SCHEMA_VERSION` bump 到 `2026-06-turnover-ledger-v2`，发布后让旧 `turnover_ledger` read model stale/rebuild。继续保留后端 stale precondition，不放宽并发保护。
- 为什么 e2e 没测出：现有 e2e 使用新建 fixture 和新投影 payload，覆盖了前端 fresh/rebind、confirm/withdraw 和 API mapper，但没有模拟“生产已存在的 SQL grouped read model 在 schema version 未变时继续被视为 fresh”。因此上一轮测试没有触达旧 projection 只含 `category_version=0` 的路径。
- 文档影响：更新本模块 `state-machine.md`、`tests.md`、本实施记录和 read-models 模块记录；业务口径不变。
- 测试覆盖：新增 `test_grouped_ledger_uses_manual_version_when_category_version_is_zero`、`test_grouped_ledger_uses_bank_row_version_when_category_versions_are_zero`；更新 `test_source_versions_include_all_turnover_and_cross_module_inputs` 锁定 schema version bump；保留 UoW stale precondition fallback 回归。
- 未测风险：本地测试证明 projection 和 source version 语义；生产仍需发布后等待 `turnover_ledger:all` worker 重建，并用真实登录态对 `txn_imported_1269/1361` 做一次手工 smoke。

## 2026-06-17 - SQL bank row 0 占位版本导致闭环 stale 误报

- 目标：修复外部往来款管理页选择 `txn_imported_*` SQL bank detail 流水确认手动零差额闭环时，后端误报“银行流水状态已变化，请刷新后重试。”的问题。
- 影响范围：SQL bank detail row -> turnover flow row 映射、`TurnoverLedgerBankRowStalePreconditionPort` 写入前置版本校验、前端 grouped row mapper、manual closure API/e2e 回归。
- 根因：上一轮修复覆盖了前端 fresh reload 和缺失版本字段，但真实 SQL 读模型里 `category_version=0` 是占位值；前端已按 `manual_category_version` / `version` 提交真实 `expected_versions`，后端 stale precondition 却仍把 `category_version=0` 当当前版本，导致误判 stale。
- 关键决策：统一使用 `turnover_bank_row_version` 选择银行流水版本，按 `category_version`、`manual_category_version`、`version` 顺序取第一个非零数值；只有所有候选都为空或为 0 时才保留 0。前端 mapper 使用同一语义，避免页面提交体和后端校验再次分叉。
- 文档影响：更新本模块 `tests.md` 与本实施记录；业务口径、API 字段 shape 和状态机不变。
- 测试覆盖：新增/更新 `test_sql_bank_detail_turnover_row_uses_manual_category_version_when_category_version_is_zero`、`test_sql_bank_detail_turnover_row_falls_back_to_bank_row_version_when_category_version_is_zero`、`test_bank_row_stale_precondition_uses_manual_version_when_category_version_is_zero`、`test_bank_row_stale_precondition_uses_base_version_when_category_versions_are_zero`、`test_manual_closure_api_accepts_sql_rows_with_zero_category_version`、`web/src/test/TurnoverLedgerApi.test.ts`，并继续保留 Playwright 对 confirm payload 的校验。
- 未测风险：本地未连接真实生产 PostgreSQL 数据重放截图中的原始三笔记录；已用相同 row id 和版本字段形态构造 API 集成复现。

## 2026-06-17 - OA 关联展示与外部往来闭环关系拆分

- 目标：修复外部往来款管理页把某条流水已关联 OA 的状态显示成“关联台已关联”，并把它误用于确认/撤回闭环判断的问题；同时支持流水 1/OA1、流水 2/OA2、流水 3 共同确认成一个外部往来闭环 active case。
- 影响范围：`TurnoverLedgerWorkbenchPairPort`、`WorkbenchRelationCommandService`、`WorkbenchPairRelationService` withdraw restore history、`TurnoverLedgerGroupedTable`、`TurnoverLedgerPage`、turnover/workbench integration tests、本模块文档和关联台关系状态机。
- 关键决策：
  - `turnover_manual_closure` 可以包含 `oa` + `bank` rows，但外部往来页只能合并 row types 子集为 `{oa, bank}` 且实际包含 OA 的既有 relation；包含 `invoice`、纯 bank-only 既有 relation、已有 `turnover_manual_closure` 或其他 row type 时拒绝并要求按对应 owner 先处理。
  - 确认闭环使用 `confirm_relation(..., replace_existing=True, before_relations=...)` 替换既有 OA-bank relation，并在 metadata 中保留本次选择的 `turnover_closure_bank_row_ids`。
  - 撤回闭环使用 `withdraw_relation`，底层 `WorkbenchPairRelationService` 识别 `turnover_manual_closure_confirm` 历史并恢复被标记为 `restorable_on_withdraw` 的 OA-bank relation；不再使用普通 `cancel_relation` 作为外部往来撤回语义。
  - 前端 group chip 只统计闭环关系；行内 chip 只保留正向事实：“已关联 OA”“已关联 发票”“收支闭环”。OA/发票 chip 仅展示，不禁用确认闭环，也不显示撤回闭环。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md`、本实施记录和 `docs/modules/workbench-relations/state-machine.md`；长期产品口径不新增独立文档。
- 测试覆盖：新增/更新 `test_turnover_manual_closure_merges_existing_oa_bank_relations`、`test_turnover_manual_closure_rejects_rows_already_in_turnover_closure`、`test_turnover_workbench_pair_port_withdraw_restores_merged_oa_bank_relations`、`test_withdraw_restores_previous_relations_from_turnover_manual_closure_history`、`test_manual_closure_merges_existing_oa_bank_relations_and_withdraw_restores_them`、`allows manual closure confirmation when selected rows are only linked to OA`、`shows Workbench relation feedback from the grouped ledger payload`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_service tests.test_workbench_relation_command_service tests.test_turnover_ledger_uow_contract tests.test_turnover_workbench_integration -v`；`cd web && npm test -- --run src/test/TurnoverLedgerPage.test.tsx`。
- 未测风险：本地测试没有用真实生产 PostgreSQL 数据和真实浏览器截图证明所有历史 OA id 命名都可被前端识别为 OA；后端关系恢复以 row type 为准，UI 的“已关联 OA”chip 仍依赖 projected row ids/mode 中可识别 OA 线索。

## 2026-06-16 - P2/P3 外部往来同步导出上限

- 目标：收敛外部往来 export-preview/export 大数据同步生成风险，避免超过 20,000 个 group 或展开后超过 20,000 行时继续构造预览/XLSX。
- 影响范围：`TurnoverLedgerExportService`、turnover export API error mapping、外部往来导出 service/API 测试、模块测试矩阵和 P2/P3 闭环台账。
- 关键决策：导出上限为 20,000 行；先根据 grouped payload `pagination.total` 拒绝明显超大 group，再根据 formal rows 数拒绝单 group 大量 flow rows。普通参数错误仍保持 `invalid_turnover_ledger_export_request`。
- 文档影响：更新 `tests.md`、本实施记录和 `.planning/P2P3-CLOSURE-PLAN.md`；产品/API 长期文档未扩展，因为这是性能保护边界。
- 测试覆盖：新增 `tests/test_turnover_ledger_export_service.py::TurnoverLedgerExportServiceTests::test_export_rejects_group_count_above_sync_row_limit`、`test_export_rejects_flattened_flow_rows_above_sync_row_limit` 和 `tests/test_turnover_ledger_api.py::TurnoverLedgerApiTests::test_export_limit_returns_structured_error`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_export_service.TurnoverLedgerExportServiceTests.test_export_rejects_group_count_above_sync_row_limit tests.test_turnover_ledger_export_service.TurnoverLedgerExportServiceTests.test_export_rejects_flattened_flow_rows_above_sync_row_limit tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_export_limit_returns_structured_error -v`。
- 未测风险：真实 PostgreSQL grouped query、浏览器下载/打开文件和长表格视觉性能仍需 staging/manual smoke；本地只证明超大同步导出不会继续生成文件。

## 2026-06-16 - P2/P3 严格临时目录清理证据

- 目标：把外部往来 API 测试从 `TemporaryDirectory(ignore_cleanup_errors=True)` 放宽清理切回严格清理，避免后台 job executor 异步写入残留被测试吞掉。
- 影响范围：`tests/test_turnover_ledger_api.py`；业务实现、API contract、read model scope 和前端行为不变。
- 关键决策：保留严格 `TemporaryDirectory()`；对会启动后台 job 的用例在临时目录退出前调用 `app.shutdown_background_jobs()`，必要时使用 `try/finally`，不通过放宽 cleanup 隐藏资源边界问题。
- 文档影响：更新本实施记录、`tests.md` 和 P2/P3 closure ledger；长期业务口径不变。
- 测试覆盖：`tests.test_turnover_ledger_api` 覆盖外部往来 API、UoW、idempotency、stale precondition、read model refresh 和 Workbench relation 回归；同时运行 `tests.test_historical_etc_business_batch_migration_service` 验证相关历史 ETC migration 严格清理。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api tests.test_historical_etc_business_batch_migration_service -v`，结果 136 tests passed。
- 未测风险：这只证明本地测试资源释放和后台 job 边界；真实 worker/systemd/RabbitMQ drain 与一秒级生产 SLO 仍需 staging/production gate。

## 2026-06-16 - 已关联手工闭环 flow-row toolbar 撤回

- 目标：补齐外部往来表格选择已关联 `turnover_manual_closure` flow row 后的操作闭环，避免 toolbar 仍只暴露普通“确认闭环”入口。
- 影响范围：`TurnoverLedgerPage` selection toolbar、`TurnoverLedgerPage.test.tsx`、P2/P3 closure ledger；后端 withdraw API contract 不变。
- 关键决策：表格 checkbox 仍是 flow-row 选择入口；若当前选择包含已关联 Workbench row，普通“确认闭环”禁用。只有所选 flow rows 全部属于同一个 `turnover_manual_closure` relation 时，toolbar 启用“撤回闭环”，复用现有 `/api/turnover-ledger/relations/{id}/withdraw`，优先等待后端返回的 `freshness_targets`，然后 reload grouped ledger 并发送 turnover/workbench domain events。
- 文档影响：更新本模块 `tests.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：新增 `web/src/test/TurnoverLedgerPage.test.tsx::withdraws a selected linked manual closure from the table toolbar`；完整 `TurnoverLedgerPage.test.tsx` 继续覆盖抽屉撤回、manual closure、stale 阻断和 operation overlay。
- 验证命令：`npm --prefix web test -- --run src/test/TurnoverLedgerPage.test.tsx`。
- 未测风险：未用真实浏览器大数据表格截图验证 toolbar 换行动效；生产真实 withdraw SLO 仍需登录态 mutating scenario 证明。

## 2026-06-16 - Postgres 事务入队补齐成本统计 scope policy

- 目标：阻止外部往来确认/撤回在 PostgreSQL 事务写路径中绕过 `ReadModelRefreshGateway`，继续向 `cost_statistics.read_model.refresh` 投递裸月份或裸 `all`。
- 影响范围：`TurnoverLedgerDirtyOutboxWriter`、`TurnoverLedgerWriteUnitOfWork`、Postgres facade refresh request、成本统计下游 read model 和 App Status readiness。
- 关键决策：事务内写入仍使用 `enqueue_read_model_refresh_in_transaction` 保持同一业务事务；在调用前复用 `DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY` 做 normalize/validate。`source_versions` 优先按实际入队 event 的 canonical `scope_key` 记录。
- 文档影响：更新 turnover-ledger、read-models、cost-statistics 模块记录，并在 P2/P3 closure ledger 登记生产 dry-run 证据。
- 测试覆盖：新增 `test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction`；更新 `test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear` 断言 Postgres path 入队 `active/all` canonical cost scopes。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v`。
- 未测风险：生产已有 9 条 legacy cost statistics runtime 状态仍需受控 `scripts/check-read-model-scope-contracts.py --apply` 清理；本次未执行生产写入、重启或部署。
- 后续事项：发布后先 dry-run，再执行批准后的 scope contract repair apply，并复查 `/health/ready`、dirty/outbox/readiness。

## 2026-06-16 - SQL bank detail category version fallback

- 目标：修复外部往来页确认闭环时，SQL bank detail row 缺 `category_version` 但有 `manual_category_version` 或基础 `version` 时，后端 stale precondition 误报“银行流水状态已变化”的问题。
- 真实原因：`TurnoverLedgerBankRowStalePreconditionPort` 已按 `category_version -> manual_category_version -> version` 判断当前版本，但 `Application._turnover_bank_transaction_row_from_bank_detail(...)` 从 `bank_detail` SQL read model 转换 turnover flow row 时没有把 fallback 后的版本统一输出为 `category_version`。前端刷新后提交的是最新 `categoryVersion`，后端当前 row 却缺该字段，导致 expected/current 比较失败。
- 影响范围：`bank_detail` SQL read model -> turnover flow row 转换边界；不改变手动闭环业务规则、Workbench relation 写入口、dirty/outbox、operation barrier 或前端提交流。
- 关键决策：在转换边界统一写出 `category_version`，优先级保持 `category_version -> manual_category_version -> version`，无效值归零；不放宽 stale precondition，不新增 fallback 写路径。
- 文档影响：更新本实施记录和测试矩阵；长期业务口径不变。
- 测试覆盖：新增 `test_sql_bank_detail_turnover_row_uses_manual_category_version_when_category_version_missing`、`test_sql_bank_detail_turnover_row_falls_back_to_bank_row_version_when_category_versions_missing`、`test_sql_bank_detail_turnover_row_prefers_category_version_over_manual_version`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`；`cd web && npm test -- --run src/test/TurnoverLedgerPage.test.tsx src/test/TurnoverLedgerApi.test.ts`。
- 未测风险：本地自动化覆盖转换和前端 fresh/rebind 回归；真实生产历史数据仍需在发布后通过正常 `bank_detail` / `turnover_ledger` read model refresh 和手工 smoke 验证。

## 2026-06-16 - Workbench relation feedback projection

- 目标：补齐关联台反向影响外部往来款管理页的可见反馈。此前手工闭环会写 Workbench active pair relation 并触发刷新事件，但 turnover grouped payload 没有承载 canonical Workbench relation 状态；关联台侧撤回或补链后，流水台刷新也只能看到 turnover 本地状态。
- 影响范围：`TurnoverLedgerSqlProjectionBuilder`、standalone worker 依赖注入、`web/src/features/turnoverLedger/api.ts`、`TurnoverLedgerGroupedTable`。
- 关键决策：
  - projection 阶段通过 `WorkbenchRelationReadFacade.get_by_row_ids(require_fresh=True)` 读取 fresh 的 relation distribution，把 `workbench_relation_status`、`workbench_relation_case_ids`、`workbench_relation_mode`、`workbench_relation_source`、`workbench_relation_row_ids` 写入 grouped payload。
  - Workbench relation context 不 fresh 时抛 `workbench_relation_read_model_not_fresh`，不保存半成品 turnover read model，避免 stale relation 被包装成 fresh turnover 数据。
  - 前端只做 snake_case/camelCase 映射和状态 chip 展示，不把 domain event 或本地 React state 当事实源。
- 文档影响：更新本模块 README、state-machine、tests 和 implementation notes；长期业务口径不变。
- 测试覆盖：新增 `test_projection_enriches_rows_with_fresh_workbench_relation_context`、`test_projection_does_not_save_when_workbench_relation_context_is_not_fresh`；更新 `web/src/test/TurnoverLedgerApi.test.ts` 和 `web/src/test/TurnoverLedgerPage.test.tsx`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_read_model_refresh -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`；`cd web && npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx`。
- 未测风险：真实/staging 环境仍需验证 worker 顺序和页面可见性：先刷新 `workbench_relation` scope，再刷新 `turnover_ledger`，浏览器在 operation barrier fresh 后应看到 relation chip。

## 2026-06-16 - Bank detail dependency loop caused empty turnover ledger

- 目标：修复外部往来款管理页无数据、App Status 长时间显示银行明细同步中的问题。
- 真实原因：`bank_detail` 月份 read model 本身已经有外部往来流水和自动标签结果；页面无数据是因为 `turnover_ledger:all` worker 被银行明细 freshness 依赖循环阻塞。第一层问题是 downstream all-scope `bank_detail_read_model_not_fresh` 被旧 runtime worker 自动补投成 `bank_detail:all`，把 fan-out command 当成稳定 dependency。第二层问题是 `BankTransactionTagReadFacade` 曾把 fresh `bank_detail` read model 中缺失的 transaction id 误判成 read model `missing`。第三层问题是多个月份里只要一个月份 pending，facade 曾把所有月份都作为 `downstream_bank_tag_read` refresh target，刚刷完的月份被下一轮重打 pending，导致 all scope 永久等不到所有月份同时 fresh。
- 影响范围：runtime worker dependency scope 推导、read model refresh gateway active coalescing、bank tag read facade missing-row 与 blocking-scope contract；不改变外部往来 grouped ledger 业务计算、手动闭环写入、Workbench relation 写入口或前端 empty state。
- 关键决策：从架构上禁止 downstream all-scope dependency defer 推导 `bank_detail:all`；只允许从 source scope 推导具体月份。`bank_detail_all_shard` 作为 ensure/wakeup reason 参与 active coalescing，避免重复 bump 正在处理的月份 shard。fresh read model 的 missing transaction id 只作为诊断信息，downstream 外部往来计算按无标签行处理，不再补投 refresh 或抛 not fresh。非 fresh 依赖读取只补投 dirty/blocking scope，不重刷已经 fresh 的月份。
- 测试覆盖：`RuntimeWorkerTests.test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`ReadModelRefreshGatewayTests.test_bank_detail_all_shard_reason_does_not_bump_active_scope`、`BankTransactionTagReadFacadeTests.test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows`、`BankTransactionTagReadFacadeTests.test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes`，并运行外部往来和免 OA read model dependency 回归。
- 生产验证要求：发布后观察 `job.read_model_dirty_scopes` / `job.outbox_events` 中 `bank_detail` 月份 shard、`turnover_ledger:all` 和 `no_oa_bank_batch:all` 收敛；页面必须由 fresh read model 显示数据，不能用手工改 readiness 或直接 SQL 填 rows。

## 2026-06-15 - SQL runtime closure source alignment

- 目标：修复生产环境外部往来页选中三笔银行流水确认闭环失败，且关联台 open 区没有生成同一个关系组的问题。
- 真实原因：不是关联台渲染丢关系，也不是 deterministic 候选应自动显示为已配对。生产 SQL runtime 的 `bank_detail` read model 已有这三笔流水及当前自动标签版本，但闭环写路径仍从 legacy import snapshot 读取可闭环银行流水；该快照在当前 SQL 部署下为空或不含目标行，所以后端在 stale/unknown bank row precondition 阶段拒绝写入，`TurnoverRelationService.confirm_zero_difference_closure` 和 `WorkbenchRelationCommandService.confirm_relation` 都没有执行。
- 第二个必须修复的边界：`bank_detail` SQL read model 的 durable `transaction_id` 可能是 UUID，而关联台 row id 使用 legacy/source id，例如 `txn_imported_*`。闭环写入必须把 legacy/source id 保留为 `id` 与 `source_bank_row_id`，否则即使 relation 写成功也可能无法和关联台行聚合。
- 关键决策：`Application._turnover_bank_transaction_rows()` 在 SQL runtime 下改为读取 `bank_detail_sql_read_repository.list_bank_detail_tagged_rows_by_month(...)`；使用 app settings 中的外部往来选中标签集过滤；`read_model_status` 允许 `fresh` 和 `refreshing`，但 `refreshing` payload 中只接受当前 `bank-auto-tag-rules:{version}` 的行，避免把旧规则版本行拿去闭环；应用启动早期 settings service 尚未绑定时返回空集合，不让 startup wiring 崩溃。
- 文档影响：更新本模块实施记录和测试矩阵；银行标签恢复和设置入口收口记录在 `bank-details`、`settings` 模块。
- 测试覆盖：新增 `test_sql_bank_detail_turnover_rows_keep_legacy_source_ids_for_manual_closure` 覆盖 SQL read model row -> turnover closure -> Workbench active relation，新增 `test_sql_turnover_rows_tolerate_early_startup_before_app_settings_service_is_bound` 覆盖启动早期安全返回。
- 生产验证：已用现有 application facade 对目标三笔 legacy bank row ids 写入 manual zero-difference closure，并验证 `workbench_relation` read facade 返回 `fresh`，三笔行都 linked 到同一个 `turnover:{relation_id}` open group。
- 未测风险：未在本轮执行标准发布脚本全量重发 release；生产采取当前 release 单文件 hotfix 并重启服务，后续正式发布应带上本地变更和完整验证。

## 2026-06-15 - Manual closure selected-row fresh gate

- 目标：解决外部往来页选择多条银行流水打开闭环抽屉后，点击确定时使用旧 `categoryVersion` 生成 `expected_versions`，后端返回“银行流水状态已变化，请刷新后重试。”，导致 turnover relation 和 Workbench relation 都未写入、关联台 open 区没有关系组的问题。
- 影响范围：`TurnoverLedgerPage` manual closure 提交流、stale grouped read model 行为、`web/src/test/TurnoverLedgerPage.test.tsx`。
- 真实原因：不是关联台渲染丢失配对关系；闭环 POST 在 `TurnoverLedgerBankRowStalePreconditionPort` 前置版本检查被拒绝，后续 `confirm_zero_difference_closure`、`WorkbenchRelationCommandService.confirm_relation`、`freshness_targets` 等链路都没有执行。
- 关键决策：不新增后端旁路、不放宽 expected_versions。前端在 manual closure 点击确定前先等待 `turnover_ledger:all` fresh，再重新拉取 grouped payload，按原始 bank row ids 在原 group 的 latest `flow_rows` 中重绑，重新计算零差额并用最新 `categoryVersion` 提交。刷新后任一流水缺失、离开原 group 或不再零差额，则关闭抽屉并提示重新选择，不发 POST。当前 grouped read model 非 fresh 时，页面“确认闭环”入口禁用。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 与本实施记录。
- 测试覆盖：新增/更新 `web/src/test/TurnoverLedgerPage.test.tsx` 中 `refreshes the grouped ledger before manual closure and submits latest bank row versions`、`blocks manual closure when a selected flow disappears after the fresh ledger reload`、`shows grouped read model stale warning and blocks manual closure`。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产库上的 worker drain 和跨页面视觉刷新仍需 staging/生产前 smoke；本次本地测试已覆盖请求体版本、阻断旧选择、后端 UoW/API/workbench relation contract。

## 2026-06-15 - Manual closure Workbench visibility barrier

- 目标：外部往来页面确认多笔 manual zero-difference closure 后，关联台 `open` 区必须能在同一次跨页刷新中看到同一个 `case:turnover:{relation_id}` open group，避免先刷新到旧 Workbench generation。
- 影响范围：`TurnoverLedgerConfirmRequestBoundaryFacade` 响应契约、`TurnoverLedgerPage` operation barrier 等待、turnover closure API mapper、关联台跨页刷新事件时序。
- 关键决策：relation 写入和 Workbench 分组架构保持不变；真实缺口是闭环 API 只让前端等待 turnover ledger，未暴露/等待 Workbench 可见性目标。当时 manual closure confirm 响应新增 `freshness_targets`，包含 `turnover_ledger:all`、受影响月份 `workbench_relation`、受影响月份 `workbench` 和 `workbench:all`；该 hard target 范围已在 2026-06-17 被收窄为 `turnover_ledger:all` + 受影响月份 `workbench_relation`，`workbench` 月份/all 仅后台收敛，不再作为外部往来 overlay 释放条件。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 与本实施记录；关联台模块测试矩阵同步补充跨页刷新等待保护。
- 测试覆盖：新增/更新 `tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_workbench_integration.py`、`web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/TurnoverLedgerPage.test.tsx`。
- 验证命令：见本轮最终执行记录。
- 未测风险：未运行真实生产库全量 Workbench active generation 回放；该风险与数据回放相关，不影响本次响应/等待契约。

## 2026-06-14 - 写操作后 freshness barrier

- 目标：外部往来 tag-selection、extra、manual closure confirm/withdraw 后隐藏 read model 收敛窗口，避免页面提前显示旧分组或允许重复操作。
- 影响范围：`TurnoverLedgerPage` 写操作、`GlobalOperationOverlayProvider`、`operationBarrier` API client。
- 关键决策：写 API 成功后等待 `turnover_ledger` barrier fresh，再 reload grouped payload 并关闭 overlay。前端事件只做刷新提示，不能替代 barrier/read boundary。
- 文档影响：更新本模块 `README.md`、`tests.md`、`implementation-notes.md`。
- 测试覆盖：更新 `web/src/test/TurnoverLedgerPage.test.tsx`，并由 `GlobalOperationOverlayContext.test.tsx`、`OperationBarrierApi.test.ts` 覆盖共享 overlay/barrier 行为。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产登录态 operation-to-fresh latency 需要发布后度量。

## 2026-06-11 - 外部往来多流水闭环与 Workbench 三栏规则

> 历史记录：本节中的 bank-only open 分区决策在 2026-06-22 重新成为当前有效口径；当前规则以 `2026-06-22 - 外部往来闭环关联台三栏分区纠偏` 为准。

- 目标：取消外部往来手动闭环只能选择两笔银行流水的限制，并让外部往来闭环完全复用 Workbench active pair relation 事实源。
- 影响范围：`TurnoverRelationService`、`TurnoverLedgerWriteFacade`、`TurnoverLedgerWorkbenchPairPort`、Workbench candidate grouping、server relation display payload、外部往来页 closure drawer、关联台本地 optimistic update。
- 关键决策：
  - 两笔闭环保留旧 `manual_zero_difference_pair` evidence；三笔及以上使用 `manual_zero_difference_group`。
  - `turnover_manual_closure` bank-only active relation 只能留在关联台 open，不再享受 exactly 2 bank rows paired 例外。
  - 外部往来页撤回前检查 `turnover:{relation_id}` 是否仍是 bank-only turnover relation；若已升级为三栏关系，返回 `turnover_closure_withdraw_requires_workbench`。
  - confirm 和 withdraw 都通过 UoW dirty/outbox 刷新 `turnover_ledger`、`workbench`、`workbench_relation`、`cost_statistics`、`search`。
- 文档影响：同步更新产品规格、API contract、app architecture、本模块 README/state-machine/tests/implementation-notes，以及关联台模块状态和测试矩阵。
- 测试覆盖：新增/更新 `tests/test_turnover_relation_service.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_workbench_integration.py`、`tests/test_workbench_turnover_grouping.py`、`web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`。
- 验证命令：见本轮最终执行记录；目标后端和前端测试均已覆盖多流水、bank-only open、withdraw cancel/reject 和 optimistic update。
- 未测风险：未运行真实生产库 Workbench active generation 全量回放；真实大数据滚动和视觉检查仍需浏览器/staging smoke。

## 2026-06-11 - 首轮测试闭环审计

- 目标：把 `turnover-ledger` 从测试闭环 `pending` 推进到可维护的 `documented-risk` 状态。
- 影响范围：外部往来页面、tag-selection、bank-row-tags batch、relation extra、manual closure、withdraw、export、turnover read model、turnover-ledger worker、Workbench pair relation、App Status、前端 domain events。
- CodeGraph 审计：
  - `TurnoverLedgerPage` 调用 `fetchTurnoverLedgerGrouped`、`fetchTurnoverLedgerTagSelection`、`confirmTurnoverClosure`、`saveTurnoverRelationExtra`、`withdrawTurnoverRelation`；stale read model 只显示诊断，写操作由后端 stale precondition/canonical write safety 决定，成功后通过 operation barrier 等待 fresh。
  - `TurnoverLedgerApiRoutes` 仍承接 read/write route 形状；read path 已通过 `TurnoverLedgerReadFacade` 包住。
  - `TurnoverLedgerQueryService` 通过 `ReadModelQueryGateway` 处理 `turnover_ledger` scope `all` 的 fresh/stale/missing/refreshing。
  - `TurnoverLedgerWriteFacade` 和 `TurnoverLedgerWriteUnitOfWork` 覆盖 extra、bank-row-tags、confirm、zero-difference closure、withdraw、tag-selection 的 stale precondition、idempotency、dirty/outbox。
  - `TurnoverLedgerReadModelRefreshService`、`TurnoverLedgerSqlProjectionBuilder`、`runtime_worker_registry.py` 和 App Status registry 已登记 `turnover-ledger` worker、`turnover_ledger` read model 和 `turnover_ledger.read_model.refresh` event。
- 关键测试覆盖：
  - Business core：`tests/test_turnover_relation_service.py`、`tests/test_turnover_ledger_service.py`、`tests/test_turnover_ledger_extra_service.py`。
  - Service/UoW：`tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_ledger_api.py`。
  - API contract：`tests/test_turnover_ledger_api.py`、`tests/test_turnover_ledger_read_facade.py`。
  - Read model/worker：`tests/test_turnover_ledger_query_service.py`、`tests/test_turnover_ledger_read_model_refresh.py`、`tests/test_turnover_ledger_source_versions.py`。
  - Frontend：`web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/domainEvents.test.ts`。
  - Integration/regression：`tests/test_turnover_workbench_integration.py`、`tests/test_workbench_turnover_grouping.py`。
- 文档影响：
  - 补齐 `README.md` 模块边界和代码入口。
  - 将 `tests.md` 迁入测试闭环标准结构。
  - 补齐 `state-machine.md`。
- 未测风险：
  - 真实 PostgreSQL 历史数据、半迁移/脏数据、大数据 EXPLAIN 和锁等待。
  - 真实 RabbitMQ/Redis/systemd worker drain 和网络抖动恢复。
  - 浏览器真实下载 XLSX、视觉遮挡和大数据滚动性能。
  - legacy fallback 删除前仍需要专门回归。
- 后续事项：
  - 若修改写路径，优先补 `tests/test_turnover_ledger_uow_contract.py` 或 API characterization，再改实现。
  - 若修改 grouped row shape，必须同时更新后端 API contract、前端 mapper/page tests 和 export tests。
  - 若修改 Workbench pair relation 语义，必须同步运行 Workbench turnover grouping 和 manual closure integration tests。

## 2026-06-12 - Workbench relation 写入口收敛

- 目标：让外部往来 manual zero-difference closure/withdraw 的 Workbench relation 写入走统一 `WorkbenchRelationCommandService`，避免 turnover 页面直接持有独立 relation 写事实源。
- 关键决策：
  - Turnover manual relation 仍归 turnover 模块；跨页面 OA/银行/发票配对关系归 `workbench_relations` 模块。
  - closure 写 Workbench relation 使用 `confirm_relation(case_id="turnover:{relation_id}", relation_mode="turnover_manual_closure")`。
  - withdraw 撤回 Workbench relation 使用 `cancel_relation(case_id="turnover:{relation_id}")`，history operation 为 `turnover_manual_closure_withdraw`。
  - 手动闭环写入使用 canonical relation command/write safety；`workbench_relation` distribution/read model non-fresh 不阻断写入，写后继续刷新 Workbench 和 downstream read model。
  - 已补齐成三栏 relation 的 bank row 不能从 turnover 页面撤回，仍要求到关联台撤回完整关系。
- 影响范围：`TurnoverLedgerWorkbenchPairPort`、`TurnoverLedgerWriteFacade`、Application turnover facade wiring、turnover API error payload、workbench-relations 模块文档。
- 测试覆盖：
  - `test_turnover_workbench_pair_port_delegates_manual_closure_to_relation_command_service`
  - `test_turnover_workbench_pair_port_delegates_manual_closure_withdraw_to_relation_command_service`
  - `test_manual_closure_uses_canonical_relation_when_workbench_relation_read_model_is_stale`
  - `test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service`
- 验证命令：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_turnover_ledger_uow_contract.py tests/test_turnover_workbench_integration.py tests/test_turnover_ledger_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_platform_runtime_boundary_guards.py -q
python3 -m compileall -q backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py backend/src/fin_ops_platform/app/server.py
bash scripts/verify.sh docs
git diff --check
```

- 已观察结果：turnover UoW/workbench/API 208 passed、31 subtests passed；relation command/read/projection 12 passed；repository boundary/runtime guard 43 passed；compileall、docs verify、diff check 均通过。存在既有 SWIG deprecation warnings。
- 未测风险：
  - 真实 PostgreSQL 历史数据、worker drain、前端跨页面即时反馈仍需 staging 或后续 Phase 验证。

## 2026-06-12 - Workbench relation legacy fallback direct write 删除

- 目标：删除 `TurnoverLedgerWorkbenchPairPort` 在缺少 relation command service 时的 direct pair relation write fallback，避免 legacy fallback facade 绕过统一 relation 事实源。
- 影响范围：`turnover_ledger_write_adapters.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_platform_runtime_boundary_guards.py` 和本模块文档。
- 关键决策：manual closure confirm/withdraw 需要 Workbench relation command service。缺少 command service 时抛 `workbench_relation_command_unavailable`，不读写 `WorkbenchPairRelationService` fallback，也不调用本地 pair snapshot persist。withdrawability 仍可用 `WorkbenchRelationReadFacade` 校验 bank-only relation。
- 文档影响：更新 `README.md`、`tests.md`、`implementation-notes.md`，并同步 `workbench-relations` 模块。
- 测试覆盖：新增 port 级 fail-fast 测试覆盖 confirm/withdraw 缺 command；新增 runtime boundary guard 防止 `TurnoverLedgerWorkbenchPairPort` 重新出现 `replace_with_confirmed_relation`、direct `cancel_relation(case_id)` 或 `_persist_pair_relations(...)`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_turnover_ledger_uow_contract.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_turnover_ledger_api.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_turnover_workbench_pair_port_has_no_direct_pair_write_fallback -q`。
- 未测风险：真实 PostgreSQL 历史数据和 worker drain 仍需 staging 或发布前 smoke；本阶段未改前端。
- 后续事项：继续收口 no-OA legacy migration/repair/consolidation，它仍在 `build_batches(...)` 中执行 direct pair relation mutation，需要单独设计 repair port 或离线工具。

## 2026-06-24 - Read model repository port pilot selection

- 目标：作为 `read-models:next-pilot-selection-after-cost-statistics` 的结果，把 `turnover_ledger` 选为第十个非 Go read model 模块化 IO 实现试点。
- 决策：下一条边界为 `read-models:turnover-ledger-repository-port-extraction`。
- 理由：外部往来 grouped read model 直接影响用户确认/撤回闭环前看到的业务事实，并向 Workbench relation、Workbench、成本统计和搜索产生跨页一致性影响；它已有 `ReadModelQueryGateway`、worker refresh service 和清晰的 manifest repository contract，适合先抽窄 repository port。
- 首切范围：新增 `TurnoverLedgerReadModelRepositoryPort`，只暴露 `list_turnover_ledger_view`、`save_turnover_ledger_rows`、`clear_turnover_ledger_rows`，并让 query/projection read model 路径使用该 port。
- 非目标：不改变外部往来业务状态、grouped payload shape、manual closure/withdraw 语义、Workbench relation command 写路径、API shape、worker event、queue、Redis/cache、权限、审计、前端行为或 Go/Fiber/Go Worker 状态。

## 2026-06-25 - grouped query metadata preservation

- 触发事实：生产 Row285/Row286 证明 `GET /api/turnover-ledger?view=grouped&page=1&page_size=50` 返回 HTTP 200 和 grouped data，但顶层 `read_model_status`、`refresh_enqueued`、`refresh_reason` 等 metadata 全部缺失；同一次 GET 仍创建 `turnover_ledger.read_model.refresh` / `turnover_ledger:all` dirty scope，且正常收敛到 done。
- 根因：`TurnoverLedgerQueryService` / `ReadModelQueryGateway` 可生成 freshness/enqueue metadata，但 `TurnoverLedgerApiRoutes._flat_payload_to_grouped(...)` 重组 grouped payload 时只返回 `summary/family_summaries/groups/pagination/filters`，丢弃了 SQL/read-model payload 的顶层 metadata。
- 决策：保持 grouped 业务 shape 不变，但 `_flat_payload_to_grouped(...)` 必须保留除 legacy `rows` 外的原顶层字段，再覆盖 grouped 相关字段。这样 fresh SQL payload 继续返回 grouped data，同时 stale/source-version mismatch payload 的 `refresh_enqueued` 可被 API smoke 和前端 stale 逻辑观测。
- 测试：新增 grouped fresh/stale API 回归；stale grouped SQL read model 仍 enqueue `turnover_ledger:all`，但 response 不再隐藏 `refresh_enqueued=true` 和 `refresh_reason=source_version_mismatch`。
- 非目标：本 slice 不改变 legacy local fallback、manual closure/withdraw/tag-selection/extra 写链路，不运行生产 deploy。生产复验需独立 runbook。

## 2026-06-25 - refresh source-version capture before relation rebuild

- 触发事实：生产 Row288 部署 grouped metadata fix 后，focused grouped GET 正确暴露 `read_model_status=refreshing`、`refresh_enqueued=true`、`refresh_reason=source_version_mismatch`，stale reason 为 `turnover_relation_snapshot_version_mismatch`；Row289 只读诊断进一步证明 API expected source versions 和 `TurnoverLedgerSqlProjectionBuilder` provider 当前 source versions 一致，但 persisted turnover read model 顶层/行级 source_versions 仍是旧 relation snapshot hash，且 App Status 仍 fresh。
- 根因：`TurnoverLedgerSqlProjectionBuilder.rebuild_turnover_ledger_read_model_scope(...)` 先调用 `_collect_rows(ledger_service)`；`TurnoverLedgerService.list_grouped_ledger()` / `list_ledger()` 会触发 `TurnoverRelationService.rebuild_from_bank_rows(...)` 并在内存里替换 relation snapshot。projection 随后才调用 `source_versions_provider()`，导致 worker 持久化的 `turnover_relation_snapshot_version` 描述的是内存重建后的 snapshot，而 API fresh gate expected source versions 描述的是进入查询前的持久化 snapshot。
- 决策：projection 必须在 `_collect_rows(...)` 之前捕获 source_versions，之后仍允许 `_with_workbench_relation_context(...)` 追加 Workbench relation source_versions。这样 worker 保存的 top-level/row-level source_versions 与 API fresh gate 对齐，不改变 grouped rows 的业务生成逻辑。
- 测试：新增 source-version 捕获时序回归，模拟 grouped ledger collection 改变 relation snapshot，断言保存的 payload 和 row `source_versions` 仍使用重建前版本。
- 非目标：本 slice 不改变外部往来自动关系重建、manual closure/withdraw、Workbench relation 写入、grouped payload 业务字段、API metadata shape 或生产部署。

## 2026-06-26 - write target affected-month scope narrowing

- 触发事实：生产受控写样本显示 turnover relation/closure 写后存在 `turnover_ledger:all`、`workbench:all`、`cost_statistics:all` 等宽 scope 长尾，影响写后 freshness SLO。
- 根因：普通 turnover 写路径已经能解析 affected months，但 `TurnoverLedgerWriteFacade` 仍把 turnover ledger 以及 downstream workbench/cost/search refresh requests 默认扩成 `all` 或混入 `all`；manual closure 前端提交前 fresh gate 也默认等 `turnover_ledger:all`。
- 决策：bank-row-tags、relation confirm、manual closure confirm、relation withdraw 在已知 affected months 时只 refresh affected month scopes；`all` 只保留为 manifest fan-out command、tag-selection/extra 等全局或未知月份路径，以及 cash closure withdraw 等写前无法解析 affected months 的例外。
- 前端边界：manual closure 点击确认前按所选 flow rows 的交易/借款/还款日期提取月份并等待对应 `turnover_ledger:<month>` fresh；无法提取月份时才退回 `all`。写成功后的 operation barrier 使用后端返回 targets。
- 测试覆盖：`tests/test_turnover_ledger_api.py`、`tests/test_turnover_ledger_uow_contract.py`、`tests/test_read_model_write_targets.py`、`web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/TurnoverLedgerPage.test.tsx`。
- 未测风险：本条为本地代码和合同修复；仍需要发布后用生产 turnover/workbench/no-OA 写样本重跑 write-operation SLO，并在恢复样本后复核 dirty/outbox/readiness 全 fresh。

## 2026-07-02 - Turnover read model bulk persistence performance slice

- 触发事实：生产 1s read model SLO 仍显示 `turnover_ledger:all` 超过 1s；按 worker 实际依赖注入远端 profile，`rebuild_turnover_ledger_read_model_scope("all")` rebuild+save 约 `1.48s`，主要不再是 Workbench relation context。
- 决策：不改变外部往来 grouped row shape、不改变 affected-month scope narrowing、不恢复 `all` 默认刷新；先把 `read_model.turnover_ledger_rows` 保存加入 repository multi-values 批量写白名单，降低 projection 持久化成本。
- 测试覆盖：`tests/test_postgres_repositories_boundaries.py::test_read_model_bulk_insert_prefers_multi_values_path_for_allowlisted_tables` 覆盖 turnover rows bulk path；复跑 `tests/test_turnover_ledger_read_model_refresh.py`。
- 发布后证据：release `pscip-l4-bulk-persistence-abcca6f78` 中 `turnover_ledger:all` 5s run enqueue-to-fresh `849.545ms`、handler `313.264ms`；1s run enqueue-to-fresh `495.031ms`、handler `215.518ms`，已达到当前 read model 1s SLO。
- 未闭合：真实 turnover manual closure/withdraw 写操作在 24h write-operation audit 中仍为 missing sample；本 slice 只证明 direct read model refresh 性能，不证明真实写操作后的 operation barrier 和 downstream fan-out 闭环。

## 2026-07-05 - 模块化 close：旧 app/read/clear 链路删除

- 目标：按 Grill me / Ponytail 审计外部往来款管理边界与 I/O，关闭仍可能污染新链路的旧代码逻辑。
- 影响范围：`Application` composition root、`TurnoverLedgerReadModelRefreshProducer`、`TurnoverLedgerWriteAdapters`、`BankDetailsApplicationService` auto-tag finalizer wiring、turnover API/read-model producer/boundary tests 和模块文档。
- 关键决策：
  - 删除 `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`；read path 由 `TurnoverLedgerApiRoutes` route owner 直接进入 `TurnoverLedgerQueryService` / read model。
  - 删除 `TurnoverLedgerRelationMutationInvalidationLegacyAdapter`、`Application._after_turnover_relation_mutation(...)` 和 `_turnover_ledger_relation_mutation_invalidation_adapter(...)`，不再保留旧的 persist -> clear -> enqueue side-effect order。
  - `TurnoverLedgerReadModelRefreshProducer` 只保留 `enqueue(...)`，移除 `read_repository_provider` 和 `clear_best_effort()`；银行明细模块不再注入 `clear_turnover_ledger_read_model`，仅通过 refresh producer enqueue 外部往来 read model refresh。
  - relation-extra stale precondition 的 current reader 从旧 read facade 改为 `self._turnover_ledger_api_routes.get_relation_extra`，I/O 边界保持在 route owner/request-boundary facade。
- 测试覆盖：
  - 更新 `tests/test_turnover_ledger_api.py`，把旧 mutation invalidation 行为测试替换为删除防线，并更新 relation-extra current reader contract。
  - 更新 `tests/test_turnover_ledger_read_model_refresh_producer.py`，覆盖 producer enqueue-only contract。
  - 更新 `tests/test_platform_runtime_boundary_guards.py`，禁止 read facade 文件、producer direct clear、legacy invalidation adapter 和 server 旧 helper 恢复。
  - 更新 `tests/test_bank_details_sql_runtime.py`，证明 bank auto-tag finalizer 不再直接清外部往来 read model，只保留明确 refresh enqueue。
- 未测风险：本轮不连接真实 PostgreSQL/RabbitMQ/Redis/systemd，不验证生产历史数据、真实 worker drain、真实 XLSX 下载或大数据浏览器性能；这些仍归 staging/infra smoke。

## 2026-07-06 - provider-backed 分类旧回退删除与 1s SLO 收敛

- 触发事实：生产 `read_model_slo_smoke --apply --critical-only --target-ms 1000` 中 `turnover_ledger:2026-02` handler `1015.759ms`、enqueue-to-fresh `1056.525ms` 超过目标。远端 breakdown 显示 `collect_rows_all` 约 `777ms`，其中 `BankTransactionTagReadFacade.bulk_get_for_rows(...)` 后仍对 910 笔流水逐笔执行 legacy `category_service.get(...)` fallback。
- 根因：生产 worker 已通过 fresh `bank_detail` read model 获取有效分类事实，但 `TurnoverLedgerService._categories_for_rows(...)` 仍保留 provider 后的旧 category service fallback；这是旧链路污染 provider-backed read model hot path。
- 决策：provider 存在时直接信任 provider records，不再逐笔回读 legacy category service；只有无 provider 的 local/legacy path 保留 `bulk_get(...)` 后的 manual fallback。将 `TURNOVER_LEDGER_SCHEMA_VERSION` bump 到 `2026-07-turnover-ledger-v3`，发布后旧投影必须重建。
- 测试覆盖：新增 `tests/test_turnover_ledger_service.py::TurnoverLedgerServiceTests::test_provider_backed_grouped_ledger_does_not_per_row_read_legacy_categories`；更新 `tests/test_turnover_ledger_source_versions.py` schema version 期望。
- 未测风险：真实生产 1s SLO 需发布后重跑；跨月往来关系仍不能简单按月份窄读银行流水，否则会丢失后续还款/收款事实。

## 2026-07-10 - Audit 证明闭环：撤回关系去污染与 leaf 余额重算

- 触发事实：生产 9 页只读 Audit 中，外部往来台账剩余三条 business-field mismatch；两条是只有结算 leaf 的组被 Audit 错误按 pending amount `0` 校验，另一条是已撤回人工 relation 与恢复的系统 relation 同时进入 grouped totals，导致同一还款流水重复累计。
- 决策：relation snapshot/audit log 继续保留 `withdrawn` 历史，但 grouped 当前台账不再消费 withdrawn relation。Audit 从 bank-detail canonical leaves 分方向重算余额：有本金时结算最多冲减到零，纯结算组保留负余额；同时继续分别校验待还、已还、待收、已收字段，不以放宽断言掩盖重复聚合。
- 版本：`TURNOVER_LEDGER_SCHEMA_VERSION` 升至 `2026-07-turnover-ledger-v4`，发布后必须通过正式 read-model gateway 重建受影响 scope；禁止直接改 `read_model.turnover_ledger_rows`。
- 测试：新增撤回后 grouped totals/flow leaf 不重复的业务核心回归，并扩展 Audit SQL 合同测试覆盖 `expected_balance`。

## 2026-07-11 - Audit consumer 证明：保留 case-member 映射

- 触发事实：旧 turnover payload 只有 `workbench_relation_case_ids` 与 `workbench_relation_row_ids` 两个 union，无法证明每个 case 对应哪些 typed members；shared relation 正确不能推出 ledger/flow consumer 没有漏配对。
- 决策：复用 builder 已存在的内部 relation detail，公开为 `workbench_relations` 结构化 summaries；不新增表、worker 或事实源。Audit 以 ledger aggregate row 和每条 flow row 为 anchor，与 linked shared groups 做 `(anchor, case, row_id, row_type)` 双向 equality。
- 版本：`TURNOVER_LEDGER_SCHEMA_VERSION` 升至 `2026-07-turnover-ledger-v5`；发布后必须通过正式 gateway 重建旧 scope，禁止直接写 read model。
- 测试：扩展 turnover projection/source-version tests 和 page Audit omission fixture；真实 PostgreSQL/生产数据仍由后续只读发布 gate 验证。

## 2026-07-20 - 页面读取有界化、子 scope freshness 与旧链最终收口

- 生产基线：页面 shell p95 `117.557ms`、grouped API p95 `284.012ms`、标签选项 p95 `177.869ms`、Page Audit p95 `323.220ms`，20/20 2xx/fresh/0 enqueue；生产只有 21 行，旧全量 SELECT 自身约 `0.169ms`，所以当前固定耗时主要不在 PostgreSQL。
- 设计取舍：不增加 Redis cache、新表、新 worker、第二 read model、前端轮询或共享 gateway 分支。只修 turnover owner 内已证实的增长风险、freshness 缺口和旧代码。
- 查询：family/status/scope/direction、总 summary、family summaries、total 改在 PostgreSQL 固定 CTE 中完成；第二条 data query 只读取当前页 `payload`，不再全量搬运/解析所有 rows 或 `raw_payload`。筛选为空但 projection 存在时返回 fresh 空结果。
- 一致性：`all` query 聚合所有 turnover child dirty scopes；failed 优先为 stale，其次 pending/processing 为 refreshing，全部 clean 才为 fresh。mixed row source versions 只能在该证明 fresh 后规范为 expected versions。
- 旧链删除：删除 query service `legacy_payload_builder`、`settings_provider`、`postgres_required` 分叉；删除 repository/port/wrapper/manifest 的 `clear_turnover_ledger_rows`；删除 Python 全量 summary/family/source-version helper 和 raw payload fallback。
- 持久化：v6 projection 只把完整 DTO 写入 `payload`，`raw_payload` 写 `{}`；`TURNOVER_LEDGER_SCHEMA_VERSION` 升到 `2026-07-turnover-ledger-v6`，发布后必须经正式 gateway/worker 重建。
- 测试：新增真实 PostgreSQL integration，覆盖金额/方向/分页/空筛选/mixed versions/child dirty/raw payload；query/service/API/manifest/architecture/platform guard 和前端既有测试共同保护契约。
- 发布条件：部署精确 main SHA，等待所有 turnover 月份 v6 fresh/drained，再执行 40 样本性能、直接/交叉 Audit 和安全可逆 confirm→fresh→withdraw→fresh。若写样本不安全，不得制造 canonical 业务数据。

## 2026-07-20 - 确认/撤回后 projection source version 收敛修复

- 生产证据：`fc87df7b6` 发布后的 40 轮只读门通过（shell p95 `109.507ms`、grouped p95 `302.389ms`、tag-selection p95 `157.568ms`、Page Audit p95 `324.403ms`），但可逆确认后 grouped 在 15 秒内持续 `refreshing`；自动撤回后业务行已恢复未关联，freshness 仍反复出现 `turnover_relation_snapshot_version_mismatch`。durable dirty/outbox 已归零且 Page Audit 为 `integrity=pass/freshness=fresh/queue=drained`，因此不是 worker 积压。
- 根因：`turnover_relation_snapshot_version` 旧实现散列整个 relation snapshot，包含不参与当前 grouped projection 的 `withdrawn` 关系和 audit history。确认再撤回后当前业务输入已经恢复，但历史记录必然增长，API 与 worker 的 source-version gate 因而无法回到操作前值，并在每次读取时重复 enqueue。
- 修复：source version 只散列会改变当前台账的 canonical `confirmed` relations，并按 `relation_id` 稳定排序；audit history 和 withdrawn history 继续完整持久化、参与审计，但不再污染当前 projection freshness。确认改变版本，撤回完成后版本回到操作前值。
- 版本：`TURNOVER_LEDGER_SCHEMA_VERSION` 升至 `2026-07-turnover-ledger-v7`，强制旧 read model 通过正式 gateway/worker 重建；不新增 cache、表、queue、worker、API 或 fallback。
- 版本：`TURNOVER_LEDGER_SCHEMA_VERSION` 升至 `2026-07-turnover-ledger-v8`；基础 source vector 新增 canonical active `turnover_manual_closure` count/max-updated proof，修复统一关系事实变化未被页面 freshness gate 识别的问题。旧投影只通过正式 gateway/worker 重建。
- 测试：新增 source-version 回归覆盖 confirmed 变化、relation 顺序稳定、withdrawn/audit-only 不变；相关 source/query/projection/UoW/API 237 项通过。真实 PostgreSQL repository integration 在前一发布收口已 4/4 通过；本次复跑尝试因当前本地 runtime PostgreSQL 用户无 `CREATE DATABASE` 且对既有 `fin_ops_test.schema_migrations` 无权限而未执行，本修复不改变 repository/SQL。
- 生产验收：必须发布 v7 后重新执行两轮安全可逆 confirm→fresh→withdraw→fresh；command p95 `<=1000ms`、response-to-fresh p95 `<=2000ms`、任一 hard max `<=3000ms`，最终无 active relation 残留、两条 fixture 均未关联、直接与交叉 Audit 通过，才可关闭本页。

## 2026-07-20 - 写后可见性 hot path 去重

- 生产证据：release `486507219` 已把 target-scoped operation barrier 降到只读样本 `117–234ms`，AppHealth p95 `318.8ms`；两轮可逆写探针仍显示确认 response-to-visible `8.65–14.62s`、撤回 `5.46–7.97s`。剩余耗时来自 command transaction 与同一 turnover worker 串行处理两个受影响月份，不再来自 barrier 查询。
- 根因：每个月份 projection 都从 canonical facts 重建整本 grouped ledger 后再过滤 scope；一次跨月确认/撤回会让同一个 worker 对相同 source version 连续做两次完全相同的基础计算。同时 unchanged 检查和 relation-only refresh 会重复读取同一 scope 的 page 1。
- 修复：projection builder 只保留最近一个、由完整 own source_versions 精确绑定的基础 rows 计算结果，让同版本的相邻 month shard 复用；source version 任一字段变化立即重算。首次 read-model page 在同一次 rebuild 内复用。该 memoization 不新增表、Redis、TTL、fallback、worker 或 API，不跨进程，也不改变 canonical facts、freshness 或页面 payload。
- 旧链删除：移除同一次 rebuild 对 page 1 的第二次 repository 查询，以及相邻同版本 month shard 对整本 ledger 的第二次 canonical grouped 计算；保留每个 scope 独立的 relation context、source-version 标记和原子保存。
- 测试：覆盖同版本两个月只计算一次、source version 改变必须计算两次、relation-only refresh page 1 只读取一次；生产门仍为两轮可逆 confirm→fresh→withdraw→fresh、最终 fixture 恢复与跨页面 Audit。

## 2026-07-20 - Relation-only 整月重写旧链删除

- 生产证据：release `8c6ffcb744fde08ea4c2053ac8562380bef15a4f` 的三轮可逆探针业务正确且最终 fixture 恢复，但首轮 confirm response-to-fresh `5801.700ms`，后续为 `1288.451–1938.478ms`；recent handler 显示 `workbench_relation` p95 `862.121ms`、`turnover_ledger` p95 `1406.471ms`。两个 turnover month scope 由单 worker 顺序执行，旧 projection 每次读取整月全部 payload、重套 context、delete scope 并整月写回，形成冷态串行长尾。
- 现有事件合同已经在同一事务 outbox 中携带 `row_ids`、`case_ids` 和 `relation_deltas`，无需增加 queue、worker、cache、projection 表或共享 gateway 分支。
- 修复：`TurnoverLedgerReadModelRefreshService` 只有在精确 month 且 `relation_deltas + row_ids` 完整时调用 relation-delta projection；repository 按 `scope_month + bank_row_ids overlap` 读取目标 grouped rows，从 canonical relation bundle 重套上下文，以一个月级 SQL 统一推进 source-version proof，再只 upsert 目标 rows。新增 GIN index 支撑 overlap 查询。
- 旧链删除：relation-only hot path 不再调用 `_existing_scope_rows(...)` 分页读全月，也不再调用 `save_turnover_ledger_rows(...)` 的 delete/rewrite scope。完整 rebuild 只保留给 own-source 变化、`all`、首次构建或 mixed-version 安全恢复。
- 隔离：改动只在 `turnover_ledger` worker/projection/repository port；canonical Workbench relation、其他页面 API/read model/worker 和 refresh gateway 不变。
- 测试：worker dispatch、projection 窄 enrichment、repository 无 delete、真实 PostgreSQL overlap payload/统一版本证明与原 full projection 回归。生产仍需精确 SHA 部署后重跑三轮可逆写、读取/Audit 和 queue drain 门。

## 2026-07-20 - Manual closure command 历史写入热点收口

- 后续生产定位：projection 相邻月份复用后，withdraw response-to-fresh 已降到 `1277–1489ms`，但 confirm 仍约 `6166–6206ms`；同步 command 仍为 `1516–7234ms`。AppHealth 显示 confirm/withdraw command 每次执行 `75–86` 条 SQL，数据库时间是同步命令主要耗时。
- 真实根因位于共享 owner `workbench-relations`：manual closure 通过正式 command/UoW 保存 relation 时，旧 repository 会逐条重写该 case 的完整审计历史；反复确认/撤回使历史增长，命令成本随历史长度线性增加。
- 修复保持 turnover 页面 I/O 和状态机不变，只在 owner repository 内把 history replacement 改为同事务的单次批量删除 + 单次批量写入，并删除逐 case/逐 event 旧循环。没有新增页面专用事实源、缓存、worker、API 或 fallback，不改变其他页面的 relation 语义。
- 本地证据：25 条历史的 statement-count 测试通过；独立 PostgreSQL 17 空库应用 0001–0114 后，25 条 history 和全部 relation foreign key 正确落库；command/UoW/API 回归通过。
- 生产门不变：发布精确 SHA 后，两轮 confirm/withdraw 都必须满足 command p95 `<=1000ms`、response-to-fresh p95 `<=2000ms`、任一 hard max `<=3000ms`；最终 fixture 未关联、queue drained、页面及跨页面 Audit 通过，才能声明外部往来页面完成。

## 2026-07-20 - 现代闭环收敛为 canonical 单事实写入

- 生产对照：单 worker 下，撤回只改变 Workbench relation context，response-to-fresh 为 `1.28–1.49s`；确认同时持久化重复 Turnover relation，改变 `turnover_relation_snapshot_version` 后触发全量台账重建，response-to-fresh 为 `4.89–6.21s`。secondary 实验没有收益并造成竞争，已完整删除。
- 新合同：`POST /api/turnover-ledger/closures/confirm` 仍通过 Turnover domain 校验所选银行流水的方向、语义、对方和零差额，但只把 `turnover_manual_closure` 写入 canonical `app.workbench_pair_relations`；不再写 `app.turnover_relations` / `app.turnover_relation_events`，响应不再伪装存在持久化的 `turnover_relation`。撤回统一按 `workbench_pair_relation.case_id` 调用 `/closures/withdraw`。
- 保留边界：通用 `/api/turnover-ledger/relations/confirm` 与 `/relations/{id}/withdraw` 仍服务“建议关系确认/补充信息”功能，继续拥有 Turnover relation 与 audit；本轮没有误删其真实 consumer。
- 安全：canonical withdraw 在同一事务重新读取 active relation，只有至少两条 bank member 且 row types 限于 `oa/bank` 才允许；加入 invoice 或其他业务成员后必须回关联台撤回。确认/撤回继续原子写 relation history、dirty/outbox、幂等与 stale precondition。
- 性能机制：现代确认不再改变 turnover own source versions，和撤回一样走既有 `_refresh_existing_scope_rows`，只从 canonical relation source bundle 重套 context；没有新表、缓存、队列、worker、fallback 或同步 read-model 写入。

## 2026-07-20 - Shared workbench_relation relation-only delta

- release `75565d67e` 的生产证据确认 turnover own delta 已收敛到 recent p95 `126.677ms`，但共享 `workbench_relation` recent p95/p99 仍为 `3178.564/5376.672ms`，跨月 scope 串行使第三轮撤回 response-to-fresh 达 `6703.945ms`。
- 根因不是页面 API 或 barrier：旧通用 partial projection仍先执行整月 source-version CTE，并以 `month_scope = scope OR row_ids overlap`加载整月 active relations；显式 relation delta没有独立 I/O边界。
- 修复只在完整 `relation_deltas + row_ids + exact month` 事件启用：repository从既有 scope source proof只推进 impacted pair-relation timestamp；projection按 affected ids读取 active relation、pending claim和对应 source objects，再复用既有 partial save。普通 row-only、首次 scope、schema mismatch、force/`all` 继续安全 full路径。
- 删除的是 relation-only热路径中的整月 source-version/relation扫描；没有新增事实源、缓存、worker、表、API或 fallback。共享 relation业务语义与其它页面 refresh targets不变，跨页正确性由 Workbench/Bank Detail/成本/OA Audit回归保护。

## 2026-07-20 - Command 重复 I/O 与 refresh owner 最终收口

- 同步 command 的剩余重复 I/O 已删除：月份按所选银行行批量解析；expected-version 与 closure preview 复用 request-scoped selected rows；幂等只保留事务内 reserve；cash-closure withdraw 复用已锁定 relation preparation。
- Turnover 专属 `PostgresWorkbenchRelationRepository` 以 `enqueue_refreshes=False` 组装，只负责 canonical relation/history；dirty scope 与 durable outbox 由 `TurnoverLedgerWriteUnitOfWork` 唯一输出。共享关联台和其他页面 repository composition 不变，避免以全局开关改变其他页面行为。
- 旧链删除证明：Turnover UoW 事务外 idempotency get、独立 stale-precondition row read、cash-closure current relation 二次加载，以及 relation repository 的重复 scope 派生/refresh fan-out 均不再进入该页面 command 链；architecture guard 防止恢复双 owner。
- 本地门：目标 API/UoW/Workbench command `254 passed`；disposable PostgreSQL 17 实际应用 0001–0115 后 `10 passed + 6 subtests`；lint、docs、`git diff --check` 通过。
- 生产 release `main-188a9fdc-20260720170432`（SHA `188a9fdc3f91c84f7870bbc167e11bee59db14c4`）稳定窗口三轮可逆写全部通过：command p95/max `604.266ms`，response-to-fresh p95/max `699.225ms`，response-to-visible p95/max `1006.562ms`；最终 test fixture `unlinked` 且无需 recovery。
- 发布邻接首轮曾记录 confirm `4542.127ms`，数据库执行占 `4343.046ms`；同窗口 readiness/Audit 也出现数据库竞争长尾。该证据保留为平台容量风险；release/queue/worker 稳定后的正式门通过，不在页面边界内新增 Redis、warmup 旧链、跨请求 cache 或共享鉴权分支。
- 最终读取门：shell/grouped/tag-selection/Page Audit 各 40 个正式样本全部通过，p95 分别 `98.970/283.792/160.112/342.569ms`；grouped 40/40 fresh、0 enqueue。写操作后的页面直接 Audit 及关联台、银行明细、成本统计、OA 待付款交叉 Audit 均为 `pass/fresh/drained`、0 issue。

## 2026-07-22 - 人工闭环冻结真实流水规则要求

- 真实原因：Turnover 人工闭环写 adapter 曾硬编码 `requires_oa=false`、`requires_invoice=false`，同时 Workbench 分组对 `turnover_manual_closure` 存在 active 即无条件 complete 的旧 bypass。两条旧逻辑叠加，使规则标签明确要求 OA 的 bank-only closure 直接进入已配对。
- 最小设计：复用现有 selected-row port 和 `build_bank_relation_requirement_metadata(...)`，每次确认只读取一次 selected rows、一次 canonical rules payload；从 `effective_category_code`（缺失时回退 `category_code`）冻结 tag code、OA/发票要求、source 和 version。不新增 service、repository、表、worker、cache、API DTO 或前端请求。
- 安全边界：合并 preview 完成后，最终 typed bank members 必须是 selected ids 的子集；缺行、重复行、无效 rules、未知 tag 或未选 bank member 都在 relation command 前 fail closed。事务、幂等、权限、版本、dirty/outbox 与撤回合同保持原 owner。
- 旧链删除：删除 Workbench 对 turnover active relation 的无条件完成 bypass；删除 legacy no-OA 规则保存后扫描并回写既有 Turnover relation requirement 的同步方法、常量和专用测试语义。规则保存只维护当前规则，不追溯污染已冻结 relation；存量缺快照关系继续 fail closed，留给受控 repair。
- 隔离与性能：改动仅位于 Turnover composition/write adapter、Workbench 纯分区 policy 与 legacy no-OA service 的旧链清理；普通 manual/deterministic、batch accounting、ETC、其它页面 API/read model/worker I/O 不变。request 热路径保持固定 I/O 次数，且不增加逐流水或逐 relation 查询。

## 2026-07-22 - 历史冻结要求修复与 Workbench v6

- 复用现有 requirement repair ops 增加 forward/rollback 四种固定模式；Turnover 目标从 fresh bank tags 和 canonical rules 重算，fingerprint 绑定 original preimage 与 intended after，支持中断后的安全续跑。
- rollback 仅选择同一 fingerprint 的 durable repair history，经 `WorkbenchRelationCommandService` 以显式 exact-metadata replace 原地恢复；默认 metadata update 继续保持 merge，relation ownership、members、lifecycle 与 created fields 不变。
- Workbench month/all schema 升至 v6，groups/initial cache 继续从 month schema 派生；不新增表、migration、service、worker、read model、cache 或同步刷新链。真实 execute、rollback、rehydrate、Audit 和 SLO 只在备份、previous release 与审批齐全的生产 checkpoint 执行。

## 2026-07-26 - 确认闭环所选行精确 OCC

- 根因：确认闭环旧链在提交前重新加载整个 Turnover 页面，服务端又用 Bank Detail scoped payload 的整体 freshness 作为写前门禁。即使所选流水本身未变化，无关 relation/category source drift 也会把精确 ID 查询判空，最终误报“银行流水状态已变化”。
- 修复：删除前端确认前整页 reload 和服务端 whole-page status gate；grouped schema 升至 `2026-07-turnover-ledger-v9` 并为每条 bank flow 输出 opaque `selection_version`。UoW 在同一写事务内复用所选 Bank Detail 投影行，锁定 canonical bank row，并比较 bank update、活动分类/确认版本与当前自动规则版本。
- 候选生产验证补充根因：Bank Detail v11 虽读取了 canonical `updated_at`，但未把逐行值写入持久 payload；修正 payload 后，共享 `BankTransactionTagReadFacade` 的标准化 DTO 与 provider DTO 仍丢弃更新时间和规则版本，Turnover grouped 因此仍缺少 selection proof。最终修复把 Bank Detail schema 升至 v12，持久化并经共享 read facade 传递 `bank_transaction_updated_at` / `category_rule_version`，再由 Turnover flow 生成 opaque token；同时把 `TURNOVER_LEDGER_SCHEMA_VERSION` 升至 v11，确保已经发布的 v9/v10 投影不会继续冒充 fresh。
- 失败合同：任一所选事实变化返回 `409 turnover_relation_conflict`；精确证明边界不可用返回 `503 turnover_bank_row_selection_unavailable`，两者均发生在 canonical relation command 前。页面级 stale 不再参与所选行写前判断。
- 保持不变：`turnover_manual_closure` 仍只由 `WorkbenchRelationCommandService` 写入 canonical relation；confirm/withdraw 零跨页 fan-out，各页面访问时各自收敛。未新增表、migration、read model、worker、queue、cache 或 fallback。
- 交互：提交期间按钮立即显示“确认中…”并 disabled/`aria-busy`；流水行之间增加 1px 细分割线，往来方分组边界不变。

## 2026-07-29 - 闭环金额收敛为 active case 结算合同

- 根因：旧链一部分按 Turnover status/组级余额累计 `closed_amount`，另一部分把 `turnover_manual_closure` mode 直接当作闭环；这会让未进入 active relation 的零余额组、非零 active case 或跨 case 抵消被误标为已闭合。
- 修复：direct canonical query 以单个 active case 为结算单元，要求完整且唯一的银行成员、同一业务语义、现金差额与 `principal-settlement` 余额同时为零才标记闭环；非零 case 标记“已配对未结清”，不同 case 不净额抵消。`closed_amount` 仅作兼容并固定为 `0.00`。
- 同步修复无 `turnover_action_type` 时借出/业务应收 flow 的主款方向：按 `business_type + cash direction` 判定 principal/settlement，避免支出本金被误算成结清发生额。
- 旧链删除：删除 route 中不可达的 flat-to-grouped 旧聚合和 service 中基于 status/历史 principal 的 closed 累计；前端不再从旧金额 fallback 推断闭环。
- 边界保持：不新增表、read model、worker、cache、queue、API endpoint 或跨页 I/O；统一事实源仍是银行 canonical facts 与 active `app.workbench_pair_relations`。
- 首次生产发布后 grouped direct query 的服务端 p95 为 `1376.777ms`，其中数据库 p95 仅 `225.422ms`；函数级证据定位到共享有效标签计算对同一行文本按每条规则重复规范化。修复在既有 `BankTransactionAutoCategoryService` 内把行文本和规则条件各规范化一次后复用，不改变标签优先级、匹配证据或 API 结构，也不引入缓存/read model。1014 行同构基准由约 `531.6ms` 降至 `169.3ms`；最终生产 p95 以再次部署后的稳定窗口为准。

## 2026-08-01 - 页面 GET 删除全量 Python 分类旧链

- 生产证据：grouped API 串行 p95 `821.585ms`，并发 4 p95 `2542.039ms`；App Health 显示每请求约 21 条 SQL、DB p95 `1180.561ms`，而生产仅 64 条页面流水/21 个分组。旧链每次加载全部银行流水和完整分类 snapshot，再在 Python 对全部流水重跑自动规则，最后丢弃非往来标签行。
- 修复：在同一个 `REPEATABLE READ READ ONLY` transaction 内复用 Bank Details canonical classifier，只查询 App Settings 当前选中 tag codes 的 effective rows；设置只读一次，选择合同通过 `AppSettingsService.turnover_ledger_selected_tag_codes_from_settings(...)` 无 I/O 映射。原有 relation、FIFO、金额、分组、筛选、分页和导出计算不变。
- 首次生产业务校验发现集合查询已命中 64 条有效分类行，但 raw tag definition 不持有人工确认的逐行 `turnover_family`，适配层因此把全部行过滤为空。修复复用同一 request 内已配置的 `BankTransactionCategoryService.category_semantics_for_code(...)`，并从 canonical third label 推导 family；不恢复 Python rematch、全量分类 snapshot 或额外 I/O。
- 旧链删除：生产 query service 不再构造 `ImportNormalizationService`、`BankTransactionEffectiveCategoryProvider`，不再加载全量 category snapshot，也不再对全量银行流水执行 Python 自动匹配。未新增表、索引、缓存、worker、projection、依赖或第二事实源。
- 验收：本地业务/service/API 回归与 set-based SQL 合同通过；最终查询数和 p95 必须由精确 SHA 部署后的 App Health 与并发 4 SLO probe 复验。

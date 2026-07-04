# 关联台关系事实源 测试矩阵

Spec-first Browser e2e 审计入口：

- `e2e-spec.md`：关系事实源跨页面 Browser e2e 验收合同。
- `e2e-coverage.md`：Spec ID 到现有 Playwright/Vitest/API/integration 的映射和缺口。

## 2026-07-03 - confirm link OA 附件上下文对称补齐

- 变更类型：Workbench confirm 写入边界修复；不改变 HTTP response shape、权限、审计字段、relation payload schema 或 read model freshness 合同。
- 根因：确认写入前只支持“选中 OA+银行时补齐 OA 附件发票”，没有支持对称的“选中银行+OA 附件发票时补齐对应 OA”。Workbench 旧分组可显示 OA，但 canonical active relation 只落银行+发票，导致下游 `workbench_relation` distribution 和待找发票 OA 栏缺成员。
- 新增/更新测试：`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_confirm_link_includes_existing_oa_attachment_context_when_bank_and_invoice_selected`；`tests/test_workbench_oa_attachment_repair_context_executor.py::WorkbenchOaAttachmentRepairContextExecutorTests::test_repair_adds_missing_parent_oa_when_relation_has_bank_and_attachment_invoice`；`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_read_model_repairs_active_relation_missing_parent_oa_for_attachment_invoice`；`tests/test_workbench_relation_sql_projection.py::WorkbenchRelationSqlProjectionTests::test_rebuild_indexes_cross_month_relation_members_in_current_scope` 新增银行行 `linked_oa` / `linked_input_invoices` 断言。
- 七类测试决策：service-layer tests、API/write-entry integration tests、read model/cache/background job tests、existing feature regression tests 适用并覆盖；business core 不新增，因为金额/status 规则不变；frontend component 不新增，因为 API payload shape 和 UI 显示合同不变；Browser E2E 不新增，本地后端 integration 覆盖本次缺口，真实 worker drain 仍走 nightly/staging。
- 验证命令：见本轮最终说明。
- 未测风险：本地 fake 不证明真实生产 `workbench_relation` / `pending_invoice` worker drain 时延；发布后仍需用固定 145 类样本触发 Workbench payload repair，并确认 pending invoice fresh rows 显示 OA。

## 2026-07-04 - OA 自带附件发票撤回不可拆分

- 变更类型：Workbench withdraw relation 状态机修复；不改变 HTTP response shape、权限、read model schema 或 dirty/outbox 合同。
- 根因：withdraw 状态转换只依赖 `restorable_on_withdraw` 历史快照；完整 OA+银行+OA 附件发票 relation 没有可恢复 history 时，会把父 OA、自带附件发票和银行流水全部取消成独立行。业务上 OA 附件发票是来源 OA 的 source binding，不是用户可撤回的普通配对关系。
- 新增/更新测试：`tests/test_workbench_pair_relation_service.py::WorkbenchPairRelationServiceTests::test_withdraw_preserves_oa_attachment_binding_without_history`；`test_withdraw_rejects_plain_oa_attachment_binding_relation`；`tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_preview_withdraw_relation_blocks_plain_oa_attachment_binding`；`test_withdraw_relation_rejects_plain_oa_attachment_binding_submit`；`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_withdraw_link_without_history_preserves_oa_attachment_invoice_binding`；`test_withdraw_link_blocks_plain_oa_attachment_invoice_binding`；`web/src/test/WorkbenchSelection.test.tsx::paired zone withdraw preview blocks immutable OA attachment invoice binding`。
- 七类测试决策：business core unit tests 覆盖 pair service 状态转换；service-layer tests 覆盖 command service preview/submit guard；API contract tests 覆盖 preview `can_submit=false` 和 submit error；frontend component/interaction tests 覆盖弹窗提示和禁用确认；existing feature regression tests 保留普通无 history relation 撤到无关联、display-only/history 污染不恢复。read model/cache/background job tests 不新增，因为 relation dirty/outbox 合同和 projection schema 不变；E2E 本地不新增，生产固定 145 样本验证作为发布后证据。
- 验证命令：见本轮最终说明。
- 未测风险：本地 fake 无法证明生产环境该 145 样本的 worker drain 和 all-scope active generation 最终一致性；发布后必须用生产 admin token 执行固定样本确认/撤回/再撤回阻断验证。

## 2026-07-03 - Workbench withdraw UoW legacy snapshot restore 删除

- 变更类型：Workbench relation write-path boundary cleanup；不改变业务状态机、HTTP/API response shape、权限、审计、dirty/outbox/readiness 或 read model payload。
- 覆盖证据：UoW withdraw 成功路径不得调用 `WorkbenchPairRelationService.snapshot()`；rollback、idempotency、relation command write 和 dirty/outbox enqueue 由 `WorkbenchWriteUnitOfWork` 单一事务边界承担。
- 新增/更新测试：`tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_link_uow_path_does_not_read_legacy_pair_snapshot`；同时复跑 `tests/test_workbench_uow_contract.py`。
- 七类测试决策：service-layer tests、API contract/write-entry regression、existing feature regression 适用并覆盖；read model/cache/background job 通过既有 UoW contract 复跑覆盖 dirty/outbox target shape；business core 不新增，因为不改 relation 状态转换；frontend interaction 不新增，因为页面行为不变；E2E 本地不新增，生产固定 scenario/ticket apply 是发布后证据。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_auth_context_idempotency.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_uow_contract.py -q`；`python3 -m py_compile backend/src/fin_ops_platform/services/workbench_write_facade.py tests/test_workbench_auth_context_idempotency.py`。
- 未测风险：本地 fake 不证明真实生产 HTTP wall time；发布后必须比较 write step elapsed 和 `workbench_relation` enqueue-to-done。

## 2026-07-03 - Workbench relation source-object 补读快路径

- 变更类型：read model projection hot-path implementation；不改变业务关系状态机、HTTP/API response shape、权限、审计、dirty/outbox/readiness 或 payload schema。
- 覆盖证据：普通同月 relation rebuild 中 `bank_transactions`、`oa_applications`、`invoices` 各只允许读取一次；跨月 relation 继续索引缺失成员，但第二次只按显式 row id 补读缺失成员所属源表。
- 新增/更新测试：`tests/test_workbench_relation_sql_projection.py::WorkbenchRelationSqlProjectionTests::test_rebuild_writes_linked_and_unlinked_relation_rows` 新增源表读取次数断言；`test_rebuild_indexes_cross_month_relation_members_in_current_scope` 新增跨月补读限定断言。
- 七类测试决策：service-layer tests、read model/cache/background job tests、existing feature regression tests 适用并覆盖；business core 不新增，因为不改 confirm/withdraw/状态转换/金额规则；API contract 不新增，因为 response shape 不变；frontend interaction 不新增，因为页面行为不变；E2E 不新增到本地矩阵，生产固定 scenario/ticket write-operation apply 是发布后证据。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_sql_projection.py -q`；`python3 -m py_compile backend/src/fin_ops_platform/services/workbench_relation_sql_projection.py`。
- 未测风险：本地 fake 不能证明生产 PostgreSQL planner、RabbitMQ pickup 和真实写后 fan-out 的 p95；发布后必须复跑固定 Workbench withdraw scenario。

## 2026-07-03 - Workbench withdraw submit canonical snapshot 去重

- 变更类型：relation command service write-path performance；不改变业务状态机、API response shape、权限、审计、dirty/outbox/readiness 或 relation payload。
- 覆盖证据：`withdraw_relation(...)` 提交路径复用同一个 loaded pair-service snapshot 做 preview lock 和状态转换，只执行一次 relation read model fresh check；public `preview_withdraw_relation(...)` 仍保留给独立 preview 请求。
- 新增/更新测试：`tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_withdraw_relation_submit_reuses_loaded_snapshot_for_preview_lock`；同时复跑 `test_withdraw_link_preview_and_submit_delegate_to_relation_command_service` 和 `test_withdraw_link_uses_uow_transaction_when_available`。
- 七类测试决策：business core、service-layer、API contract/写入口回归、existing feature regression 适用并覆盖；read model/cache/background job 不新增，因为 dirty/outbox 目标不变；frontend interaction 不新增，因为页面行为不变；E2E 本地不新增，生产固定 scenario/ticket apply 是发布后证据。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_link_preview_and_submit_delegate_to_relation_command_service tests/test_workbench_write_characterization.py::WorkbenchWriteCharacterizationTests::test_withdraw_link_uses_uow_transaction_when_available tests/test_workbench_relation_sql_projection.py -q`。
- 未测风险：本地 fake 不证明真实生产 transaction wall time；发布后必须比较 write step elapsed、`workbench_relation` event created/processed 和 post API probe。

## 现有可复用测试

- `tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_confirm_link_targets_resolved_row_months_when_row_ids_do_not_encode_month`：confirm 写入使用 row 内容推导 affected month shards，覆盖 `txn_imported_*` 这类 row id 不含月份时不能退回空 scope / `all`。
- `tests/test_workbench_auth_context_idempotency.py::WorkbenchAuthContextIdempotencyTests::test_withdraw_link_targets_preview_row_months_when_relation_scope_is_all`：withdraw 对历史 `month_scope=all` 的 relation 使用 preview rows 推导 affected month shards，返回 operation-scoped freshness targets。
- `web/src/test/WorkbenchSelection.test.tsx::workbench action never waits on global relation scope when action response lacks precise targets`：前端遇到旧/异常 action response 只带 `workbench_relation:all` 时不调用 operation barrier 等全局 relation scope，不再误报同步等待超时。
- `tests/test_workbench_pair_relation_service.py`：领域规则、row 去重、row type 对齐、active overlap、cancel、withdraw 可恢复关系策略、ETC 删除不恢复旧二栏 relation。
- `tests/test_workbench_relation_command_service.py`：command service confirm/cancel/withdraw 基座、withdraw preview lock、row-id batch cancel、metadata update、freshness precondition、idempotency、mode registry 和 active row conflict。
- `tests/test_platform_runtime_boundary_guards.py`：legacy pair runtime 依赖边界 guard，覆盖 no-OA legacy migration、ETC repair/link/migration、Workbench exception application 和 batch accounting 不得重新接收或保存 `pair_relation_service`，必须通过 `WorkbenchRelationCommandService` canonical read/write 边界。
- `tests/test_workbench_auth_context_idempotency.py`：workbench confirm/cancel/withdraw actor/tenant/idempotency、withdraw 写入委托 command service、withdraw route 复用 request-local OA session actor/tenant，以及 legacy candidate / reconciliation decision 纯候选 `split_candidate` suppress 边界。
- `tests/test_workbench_reconciliation_engine.py::WorkbenchReconciliationEngineTests::test_paired_free_decision_creates_active_relation`、`test_withdrawn_auto_pair_row_set_is_not_auto_created_again`：free paired decision 通过 command service 自动正式化；用户撤回同一 row set 后不再自动重建。
- `tests/test_workbench_reconciliation_decision_store.py::WorkbenchReconciliationDecisionStoreTests::test_upsert_does_not_revive_suppressed_decision`：decision upsert 不复活已 suppressed 的用户取消建议。
- `tests/test_workbench_write_characterization.py`：confirm/withdraw UoW、idempotency、rollback、stale precondition、目标月 Workbench refresh，以及已知 affected month 时 `all` 只能走 aggregate-only 收敛，不能触发 full all shard fan-out。
- `tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_confirm_link_preview_for_already_active_relation_returns_withdraw_preview`：confirm preview 基于 canonical active relation 判定已配对 row-set，返回 withdraw preview，而不是继续允许 confirm。
- `tests/test_write_operation_slo_audit.py`：Workbench confirm/withdraw canonical UoW 后的 write operation SLO profile，覆盖 `workbench_relation`、下游 read model reason、bank+invoice 非成本 profile、以及 `--since` 过滤生产修复前旧样本。
- `tests/test_workbench_relation_sql_projection.py`：`workbench_relation` distribution、linked/unlinked rows、open automatic decision 不再作为 downstream candidate group、正式发票和 OA 附件发票 identity 去重。
- `tests/test_workbench_relation_read_facade.py`：freshness-gated facade、missing 入队刷新、unlinked 过滤、relation status 不被硬编码为 active。
- `tests/test_platform_runtime_boundary_guards.py`：下游读模型不得直接 join `app.workbench_pair_relations`，银行明细关系标签必须走 facade，ETC summary 删除、server OA offset auto pair、OA 附件上下文 repair、batch accounting legacy repair 和 no-OA legacy repair/consolidation 不得退回 direct pair relation mutation。
- `tests/test_batch_accounting_api.py`、`tests/test_platform_runtime_boundary_guards.py`、`web/src/test/BatchAccountingPage.test.tsx`：批量账务 relation freshness 诊断、submit/withdraw command service 委托、submit/withdraw/repair 缺 command fail-fast、direct pair fallback 禁止和 canonical write safety。
- `tests/test_no_oa_bank_batch_*`：no-OA submit/withdraw、internal transfer confirm-link、command service 写入委托、relation read model freshness 诊断、Workbench paired/open 收敛。
- `tests/test_turnover_*`：turnover manual closure/withdraw command service 委托、relation read model freshness 诊断、Application wiring guard 和 workbench pair relation 集成。
- `tests/test_pending_invoice_service.py`：待找发票 attach/create 幂等、relation detail 读 distribution、manual/attach relation 写入委托 command service、relation read model freshness 诊断。
- `tests/test_etc_backend.py`：ETC 删除、历史修复、existing batch link、summary relation command service 委托、缺 command fail-fast 和 canonical write safety。
- `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py`：进项发票 OA reverse evidence detected 后通过 relation command service 写 `input_invoice_oa_reverse`，缺 command fail-fast，command stale/conflict 返回 409 且不推进本地 batch。
- `tests/test_workbench_relation_history_replay_tool.py`：PostgreSQL history replay 只读巡检，覆盖 active row 多 case 占用、row shape、未注册 mode severity、display-only relation mode/history 污染、非可恢复 history before_relations、relation/history 差异、readiness 状态和 `--fail-on-issues`。
- `tests/test_audit_workbench_relation_display_tool.py`：Workbench relation display 只读巡检，覆盖 active relation 成员缺失、active scope 拆组、同 row 多 visible owner、payload case/mode mismatch、`all` generation 旧于成员月份 generation，以及 `--fail-on-issues` 不执行写入。
- `web/e2e/workbench-relation-fanout.spec.ts`：真实 Chromium 中从银行明细待处理关系入口进入关联台，执行 confirm preview/submit/operation barrier，再回银行明细验证 `有oa` / `有发票` 标签；共享 `confirmWorkbenchRelation` flow 和银行明细下游成功节点都使用 `expectNoUnexpectedSuccessUiErrors`，防止写入成功后页面仍显示“操作失败”、同步失败、read model 失败或 barrier timeout。
- `web/e2e/bank-details-export-download.spec.ts`：真实 Chromium 中先执行 Workbench confirm，再回银行明细导出全部银行；断言请求携带当前筛选、浏览器产生 download event，文件内容包含 linked relation 字段，并检查成功后没有导出失败/同步失败/read model 失败残留。
- `web/e2e/pending-invoices-export-download.spec.ts`：真实 Chromium 中先执行 Workbench confirm，再回待找发票搜索目标对方户名并导出；断言 export-preview/export 携带当前筛选和排序、不带分页，浏览器产生 download event，文件内容包含 OA、进项发票和 linked relation 字段，并检查成功后没有导出失败/同步失败/read model 失败残留。
- `web/e2e/workbench-relations-candidate-semantics.spec.ts`：历史 browser 回归用于保护未正式确认的自动匹配不驱动 linked-only 状态；新 relation distribution 只向下游分发 active linked/unlinked 业务口径。
- `web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts`：真实 Chromium 中验证 relation-backed 待找发票 read model 非 fresh 时显示诊断；`refreshing` 保留已有行和选择发票入口，`stale` 空 rows 仍显示读模型警告并禁用导出。
- `web/e2e/output-invoice-red-relation-fanout.spec.ts`：真实 Chromium 中验证销项收款红蓝票 relation 写入后重新读取 rows，并在 drawer 的已有依据中展示人工 relation source/evidence。
- `web/e2e/input-invoice-relation-fanout.spec.ts`：真实 Chromium 中验证进项发票使用页面消费 relation distribution；未正式化前不驱动 `已支付`，Workbench confirm 后重新进入页面显示 linked 证据和 `已支付`，OA reverse drawer 中旧 candidate 兼容数据归入未关联；进项、OA pending、税金和成本下游成功节点都会检查无操作失败/同步失败/read model 失败残留。
- `web/e2e/workbench-relations-tax-offset-fanout.spec.ts`：真实 Chromium 中先进入税金抵扣页确认 relation 影响前无目标进项计划行，再从 Workbench confirm，回到税金抵扣页验证重新请求 `/api/tax-offset`、显示 relation 影响后的 fresh 进项计划行且无读模型错误，并检查无成功后的错误残留。
- `web/e2e/workbench-relations-oa-pending-fanout.spec.ts`：真实 Chromium 中先进入 OA 待付款确认未正式化匹配仍为 `支付少了`，再从 Workbench confirm，回到 OA 待付款验证 rows 重新读取、状态变为 `已支付` 并显示 `关联台已确认`，并检查无成功后的错误残留。
- `web/e2e/workbench-withdraw-flow.spec.ts`：真实 Chromium 中先建立 paired group，再从关联台自身执行 withdraw preview/submit；断言 submit 带回 `operation_type`、`preview_id`、`expected_versions`，弹窗内 busy 锁定，等待 `workbench_relation` barrier 和 Workbench fresh refetch 后恢复 open group，并检查成功后无操作失败/同步失败/read model 失败残留。
- `web/e2e/workbench-candidate-split-flow.spec.ts`：真实 Chromium 中从未配对自动建议点击任意 row，preview 判定内部兼容 operation `split_candidate`，submit 后等待 `workbench_relation` barrier 和 Workbench fresh refetch 并隐藏建议；该用例保护 automatic decision 不被误当作 active relation withdraw，不写 relation lifecycle，并检查成功后无错误残留。
- `web/e2e/workbench-exception-flow.spec.ts`：真实 Chromium 中覆盖异常处理 apply/cancel 和 ignore/unignore 的 barrier/fresh refetch；每个成功节点都会检查无操作失败/同步失败/read model 失败残留。
- `web/e2e/workbench-network-recovery-flow.spec.ts`：真实 Chromium 中覆盖 confirm-link transient network retry 成功、confirm/split/withdraw duplicate-submit guard 成功；成功节点检查无错误残留，409 stale preview 继续作为 negative path 断言错误可见。
- `web/e2e/batch-accounting-flow.spec.ts`：真实 Chromium 中从批量账务未提交 bucket 选择银行流水和 OA，submit 后等待 `workbench_relation` operation barrier，再进入已提交 bucket 验证 relation 与 OA 明细；随后 withdraw 等待同一 freshness barrier 并恢复未提交状态。
- `web/e2e/turnover-ledger-flow.spec.ts`：真实 Chromium 中从外部往来款 grouped table 选择同组两条 flow rows，confirm manual closure 后等待 `turnover_ledger` / `workbench_relation` / `workbench` freshness targets，再从 toolbar withdraw 并验证未闭环恢复。

## 七类测试适用性

### 1. Business core unit tests

适用。新增或更新：

- mode/state registry 合法 mode、非法 mode、automatic decision 不允许写 active fact。
- history replay 对 active 未注册 mode 报 error，对历史非 active 未注册 mode 报 warning。
- active row occupation、case reuse、duplicate row、conflicting row type。
- cancel、withdraw、supersede、repair 状态转换。
- withdraw 可恢复策略：真实 active before relation 可恢复，display/candidate/unowned history 不可恢复，同 row-set snapshot 不可恢复。
- idempotent replay 同 request 返回同 relation。
- 正式发票与 OA 附件发票强 identity 去重不被绕过。

### 2. Service-layer tests

适用。新增或更新：

- `PostgresWorkbenchRelationRepository` load/save/history/dirty scope 行为等价。
- `workbench_relation_history_replay` 只读读取 relation、history 和 readiness，不执行 repair/write。
- `WorkbenchRelationCommandService` confirm/cancel/withdraw/attach/no-OA/turnover/batch accounting/ETC/input reverse/OA offset 写入；withdraw 必须覆盖 preview lock、expected_versions conflict、恢复上一状态、普通无 history 撤到无关联，以及 OA 自带附件发票 binding 不可撤回。Phase 7A 已补 ETC row-id batch cancel 和 relation metadata update，Phase 7B 已补 ETC repair/link/migration 缺 command fail-fast，Phase 7C 已补 input invoice OA reverse command delegation 和缺 command fail-fast，Phase 7D 已补 batch accounting submit 缺 command fail-fast，Phase 7E 已补 turnover legacy fallback 缺 command fail-fast，Phase 7J 已补 OA offset mode 和 replace-existing repair history，Phase 7K 已补 batch accounting legacy repair command delegation 和缺 command fail-fast，Phase 7L 已补 no-OA legacy migration/repair/consolidation command delegation 和缺 command fail-fast。
- `repair_workbench_pair_relation_integrity` 必须覆盖 active relation 旧 row id 清理、OA 附件发票明细项 `oa-exp-*:item:*` 回挂父 OA、只读取 active generation、以及 repair 后 `amount_check` 重算；不能只改 `row_ids` 后保留旧 `invoice_total`。
- `PendingInvoiceApplicationService` manual invoice、attach existing 单条/批量必须委托 `WorkbenchRelationCommandService`，不得直接调用 pair service 写入。
- transaction rollback 不产生半写入。
- affected scopes 和 downstream refresh enqueue 完整。
- audit before/after、actor、reason、affected months 不丢。
- repository 不直接绕过 `ReadModelRefreshGateway` contract，事务内 writer 满足等价 contract。

### 3. API contract tests

适用。新增或更新：

- workbench confirm/cancel。
- workbench withdraw 必须和 confirm/cancel 一样解析 request-local OA session actor/tenant，并把 actor/tenant 传入 UoW replay/run command 与 relation command service；不得落到 fallback actor。
- workbench withdraw 统一按钮不能把 automatic decision 当作 active relation 撤回；无 active relation 且命中 legacy candidate 或 reconciliation decision 时，preview/submit 必须锁定为 `split_candidate` 并 suppress 候选事实源。
- workbench confirm/withdraw 写入后必须刷新 affected month scopes；affected month 已知时，Workbench `all` 页面只能通过 aggregate-only refresh 从 active month shards 收敛，不能用普通 `all` refresh 触发全量 shard fan-out 阻塞目标写链路。只有完全无法推导 affected month 时才允许普通 `all` fallback。
- pending invoice attach/create 已覆盖 application service command delegation、canonical write safety 和 API 旧 shape 回归；读侧 non-fresh response shape 仍由 read model/facade 测试保护。
- no-OA submit/withdraw 已覆盖 success、rollback、version conflict 和 relation freshness 诊断；legacy migration/repair/consolidation 已覆盖 command delegation、active row occupation、single-source case reuse 和 read model worker 不隐式 repair。
- turnover manual closure/withdraw 已覆盖 command service 委托、缺 command fail-fast、relation freshness 诊断、API wiring guard 和 Workbench 集成。
- batch accounting submit/withdraw 必须委托 command service，并覆盖缺 command service 时不得 direct pair fallback。
- batch accounting relation read model non-fresh 必须作为读侧诊断透出；普通 non-fresh 不应全局禁用具备 canonical write safety 的 mutation。显式 freshness precondition 失败时必须返回 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys` 和 `refresh_enqueued`。
- ETC repair/delete 可见入口；已提交业务批次删除必须在本地 reset 前检查 `workbench_relation` fresh，非 fresh 返回 409 且不删除 batch 或 relation。
- input invoice OA reverse evidence detected 写入：success、command service unavailable、relation read model stale/conflict 409、no half-write。

每个写 API 至少覆盖 success、missing fields、illegal state、permission/actor mapping、version conflict、idempotent repeat、canonical write safety failure；显式启用 freshness precondition 的 API 还必须覆盖 non-fresh relation read model 和 refresh_enqueued response。

### 4. Read model/cache/background job tests

适用。新增或更新：

- relation 写入后 `workbench_relation` 与 `workbench` dirty/outbox 入队；`workbench` 必须覆盖 affected month scopes，且已知 affected month 时 `all` 必须作为 aggregate-only refresh 入队；完全无法推导 affected month 时才允许普通 `all` fallback。ETC summary delete command result 必须返回 changed case ids 和 affected months 并驱动 Workbench relation invalidation。
- relation 写入后 `pending_invoice` dirty/outbox 必须按银行流水月份投递 shard scope（例如 `expense:all:2026-02`），不能投递会扩展到多个月份的基础 scope（例如 `expense:all`）。
- relation 写入后 downstream dirty/outbox 必须按 row domain 路由：银行明细只刷银行流水月份，发票生命周期/进项使用/销项收款/税抵扣只刷发票或 OA 相关月份，`search` / `workbench_relation` 保留跨域 broad scope；`cost_statistics` 只由未知 row type、bank+OA、no-OA batch 或 turnover 成本关系触发，bank+invoice 不应刷新成本统计。旧数据缺少事实表月份时必须保留 `read_model.workbench_rows` fallback。
- relation 写入后 downstream dirty/outbox 必须使用 `high` priority，避免用户写操作后的真实同步被普通后台刷新排队拖慢；只有无法从 relation/bank/invoice/OA 事实拿到月份时才允许查 `read_model.workbench_rows` legacy fallback。
- search read model 保存必须走批量写入路径，避免 relation 写后 `search.read_model.refresh` 因逐行写 `read_model.search_index_rows` 成为当前 P2/P3 一秒级写后同步门禁的长尾。
- search read model projection 必须保留 `workbench_group_rows.group_id`，`/api/search` 的 SQL read model hit 必须返回 linked group `jump_target`，避免 relation 写后 search fresh 但用户无法跳回已关联组。
- relation UoW 写入的 workbench refresh outbox 必须保留 downstream metadata、invoice usage scope types 和 pending invoice scope keys，避免 audit/SLO 只能看到 `action_name`。
- downstream `bank_detail`、`pending_invoice`、`input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`no_oa_bank_batch`、`turnover_ledger`、`search`、`cost_statistics`、`tax_offset` scope 覆盖。
- worker rebuild 后 relation distribution fresh。
- open/proposed unmatched automatic decision 不得分发为 downstream relation group；`WorkbenchRelationReadFacade` 对下游业务只提供 active linked relation 与 unlinked rows。paired automatic decision 若满足正式化条件，必须先通过 command service 写入 active relation 后才进入 linked。
- OA 待付款、待找发票、进项发票使用情况、销项发票收款、银行明细必须覆盖未正式化自动决策不进入 linked-only 业务计算的 regression；成本统计等非 relation chip 页面也不能消费未正式化 decision 金额。
- read facade missing/stale/source mismatch 返回非 fresh，不伪装空关系；但 scope 已 fresh 时，`get_by_row_ids` 中个别请求 row 缺失应由调用方按无 relation/unlinked 处理，不能阻断整页 read model。
- App Status registry 仍能观测 `workbench_relation`。
- PostgreSQL history replay 必须报告 readiness missing/not fresh，不能把 read model 状态缺失当成 pass。
- Workbench relation display audit 必须报告 active relation 与 active Workbench generation 不一致，覆盖缺失、拆组、重复 visible owner、payload mismatch 和 all-scope 滞后；工具只能读库，不能修复或入队。

### 5. Frontend component and interaction tests

适用。新增或更新：

- 关联台、待找发票、no-OA、turnover、batch accounting mutation success 后 refetch/invalidate。
- bank detail、cost statistics 等监听 `workbenchRelationUpdated` 只作为刷新提示。
- bank detail、OA 待付款、待找发票、销项发票收款只应把 active linked relation 展示为已关联 chip；未正式化自动决策不能由金额或页面本地状态推断成候选或已关联。
- relation read model non-fresh 时页面展示 freshness 诊断，不能把非 fresh 空关系当真实空；普通 non-fresh 不应全局禁用具备 canonical write safety 的无关操作。
- API 失败时不更新本地事实，不把 event 当成功。

### 6. End-to-end business-flow integration tests

适用。至少覆盖：

- 在关联台 confirm/withdraw 后，bank detail、pending invoice、invoice usage/OA pending、tax offset 或 batch accounting 通过后端 read model 看到同一 relation；当前 Browser e2e 已覆盖 bank detail relation tag fan-out、银行明细 linked relation 字段真实下载、进项发票使用 candidate/linked relation fan-out、税金抵扣页 relation 后重新读取 fresh tax offset read model、关联台自身 withdraw preview lock/submit/barrier/open recovery、automatic candidate split 防误 withdraw 和候选隐藏、pending invoice row status fan-out、batch accounting submit/withdraw 后等待 relation barrier 并进入对应 bucket，以及 turnover manual closure confirm/withdraw 后等待 turnover/workbench barriers 并恢复 grouped payload。成功写流必须额外断言页面没有残留“操作失败”、同步失败、read model 失败或 barrier timeout 文案，避免“关系已建立但用户看到错误弹窗”的假成功。
- 在关联台 confirm -> withdraw 后，用真实登录态 HTTP 响应、relation audit、durable outbox/readiness 和 `write_operation_slo_audit --since <scenario-start>` 证明不是假同步；旧失败样本不得混入新发布 gate。
- no-OA submit/withdraw 与关联台 internal transfer confirm-link 对同一组 row 收敛到同一 case，并在 Workbench paired/open 之间恢复。
- turnover closure submit/withdraw 影响 workbench_relation、cost/search；必须覆盖 canonical write safety 下不产生半写入。当前 Browser e2e 已覆盖小样本 confirm/withdraw 的 barrier 与页面恢复，复杂 OA-bank merge、cost/search 最终显示仍由后端 integration 和后续目标 smoke 保护。
- pending invoice attach existing 后，发票页和银行页关系一致。
- batch accounting submit/withdraw 后，workbench_relation 恢复。

### 7. Existing feature regression tests

适用。必须保护：

- 旧 API response shape 不丢字段。
- 新增 `relationStatus` / `relation_status` 字段不能破坏旧页面筛选、排序、分页、导出；旧 linked/no-relation 样式和详情按钮位置必须保持。
- 旧页面筛选、排序、分页、导出不因 relation module 抽离变空。
- 旧 Mongo snapshot/shadow read/repair tools 迁移观察期可读。
- App Health/readiness 仍能展示 workbench relation worker。
- 权限和 audit 不被新 command service 绕过。

## 架构守卫测试

后续必须继续扩展架构守卫：

- downstream query/read service 禁止接受 `pair_relation_service`。
- 页面 service 禁止 `from app.workbench_pair_relations`。
- `server.py` 禁止新增 relation business helper，允许列表只保留 route/dependency wiring。
- relation 写入口必须依赖 `WorkbenchRelationCommandService` 或明确的 command port；ETC 业务批次删除、历史 repair、historical migration、existing link、input invoice OA reverse、server OA offset auto pair、OA 附件上下文 repair、batch accounting legacy repair 和 no-OA legacy repair/consolidation 不得在生产 wiring 或 service fallback 中直接调用 pair service mutation。
- `PostgresWorkbenchRepository` 不再拥有 relation SQL 实现。
- turnover closure/withdraw 的 Application wiring 不得回退到只注入 `pair_relation_service`。

## 验证命令建议

分阶段最小命令：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_pair_relation_service.py tests/test_workbench_relation_read_facade.py tests/test_workbench_relation_sql_projection.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_history_replay_tool.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_audit_workbench_relation_display_tool.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py::EtcApiTests::test_etc_summary_relation_cancel_delegates_to_workbench_relation_command_service tests/test_etc_backend.py::EtcApiTests::test_submitted_etc_business_batch_delete_uses_canonical_relation_when_read_model_is_stale -q
PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py tests/test_no_oa_bank_batch_api.py tests/test_turnover_ledger_api.py tests/test_pending_invoice_service.py -q
cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx
cd web && npm run build
cd web && npm run e2e:smoke
```

全量闭环前必须补充目标 e2e 或 integration smoke，证明一个页面 mutation 后其他页面通过后端事实重新读取到一致 relation。

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会运行全量后端 unittest、前端 Vitest、前端 build、deterministic Playwright smoke 和 docs check。当前 Playwright smoke 覆盖 app shell / AppHealth / session permission gate，并覆盖关联台 confirm 后银行明细 relation tags、银行明细 linked relation 字段真实下载、未正式化自动匹配不驱动 linked-only 状态、relation-backed 待找发票 read model 非 fresh 诊断、销项收款红蓝票 relation 写入后 rows refresh 和人工依据展示、进项发票使用 linked relation fan-out、税金抵扣 relation 后重新读取 fresh tax offset read model、OA pending linked fan-out、关联台自身 withdraw preview lock/submit/barrier/open recovery、自动建议取消防误 withdraw、exception apply/cancel/ignore/unignore recovery、transient network retry、409 stale preview、confirm/split/withdraw duplicate-submit guard、待找发票行状态跨页面同步、批量账务 submit/withdraw -> `workbench_relation` barrier -> bucket recovery，以及外部往来 manual closure confirm/withdraw -> turnover/workbench barriers -> grouped recovery；共享成功写流 guard 会在 confirm 主链路后检查页面无操作失败/同步失败/read model 失败残留，银行明细、待找发票、进项使用、成本统计、OA pending、税金抵扣下游 fan-out 以及 Workbench withdraw/split/exception/network-recovery 成功节点也会在目标业务结果出现后复查无错误残留。真实 download event 覆盖银行明细、待找发票、销项收款和进项使用的 relation 字段导出；后端 unittest 覆盖 relation 写入 high priority 入队 `search`、search projection group jump target 和 `/api/search` SQL read model hit。更复杂真实基础设施同步仍主要由后端 integration、Vitest、运行时 SLO 工具和 staging smoke 保护。

## 未测风险

- 本地 deterministic Browser/API relation Spec IDs 已覆盖：confirm -> bank details relation tags、银行明细 relation 字段真实下载、银行明细账户/日期/关键字/分类筛选导出和 `read_export_only` 下载权限、未正式化自动匹配不驱动 linked-only 状态、relation-backed pending invoice non-fresh 诊断、销项收款红蓝票 relation 写入后 rows refresh 和人工依据展示、进项发票使用 linked relation fan-out、税金抵扣 relation 后重新读取 fresh tax offset read model、OA pending linked fan-out、关联台自身 withdraw preview/submit -> open recovery、自动建议取消防误 withdraw 和隐藏、网络失败重试、409 stale preview、confirm/split/withdraw 重复提交防护、confirm -> pending invoice row status、batch accounting submit/withdraw -> bucket recovery、turnover manual closure confirm/withdraw -> grouped recovery、银行明细/待找发票/销项收款/进项使用 relation 字段下载均已覆盖；search API/runtime fan-out 已覆盖但没有独立 Browser route。剩余风险为未来 Browser search UI、新 relation 撤销入口、真实网络抖动、真实 XLSX 完整解析、生产 display audit 和真实 worker drain。
- 真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、生产历史 relation 半迁移、大数据 active generation 回放和真实导出/滚动性能仍需 staging 或生产只读 smoke。
- 关联台关系 fan-out 影响银行明细、待找发票、进项/销项、no-OA、turnover、batch accounting、成本、搜索等多个页面；新增 relation mode 或 write contract 时必须同步补目标 API/服务/前端/e2e 回归。

## 2026-07-03 - Workbench relation UoW batch enqueue tests

- 新增测试：`tests/test_workbench_uow_contract.py::WorkbenchUoWContractTests::test_relation_write_uow_uses_batch_read_model_refresh_writer_when_available`，覆盖 relation UoW 在 writer 支持批量时只提交一次 target list，并保持 `source_versions` / `outbox_event_ids` response shape。
- 新增测试：`tests/test_workbench_uow_contract.py::WorkbenchUoWContractTests::test_read_model_refresh_writer_uses_batch_repository_interface_when_available`，覆盖 `RuntimeQueueReadModelRefreshWriter` 对生产 repository 批量接口的 wiring。
- 新增测试：`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_enqueue_read_model_refreshes_in_transaction_batches_dirty_scope_and_outbox_writes`，覆盖批量 dirty/outbox SQL 合同。
- 覆盖类别：service-layer tests、read model/cache/background job tests、existing feature regression。API contract 与 frontend component 未新增，因为外部 HTTP shape 和页面交互不变；E2E business-flow 仍需生产固定 scenario/ticket 复跑。

## 2026-07-03 - OA completed status aliases in relation distribution

- 根因：`workbench_relation` projection 从 `app.oa_applications` 生成 `linked_oa` summary 时复用 OA 完成态 SQL；旧 SQL 只接受空值或 `completed`，历史数据中 `workflow_status=已完成/approved/2` 时，canonical relation 虽包含 OA row id，但 `_summaries_by_id` 没有 OA 源对象，下游待找发票按银行 row id 读取 relation distribution 时 OA 列为空。
- 修复：完成态别名集中在 OA projection 边界，`OA_PROJECTION_SYNC_VERSION=2026-07-03-completed-workflow-status-aliases-v1` 触发 `workbench_relation` 与依赖它的下游 read model 重建；待找发票不新增 fallback 推断。
- 新增测试：`tests/test_workbench_relation_sql_projection.py::WorkbenchRelationSqlProjectionTests::test_rebuild_keeps_oa_summary_for_legacy_completed_workflow_status`、`tests/test_oa_projection_sync_service.py::OaProjectionSyncServiceTests::test_oa_sync_treats_legacy_completed_workflow_aliases_as_completed`。
- 覆盖类别：business core unit tests、read model/cache/background job tests、existing feature regression。API contract/frontend/E2E 未新增，因为 HTTP shape 和页面交互不变，既有 pending invoice relation distribution 测试继续覆盖消费边界。

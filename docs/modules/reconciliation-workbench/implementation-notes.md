# 关联台 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- `oa_bank_exact_sum` 属于后端自动候选规则，必须同时覆盖 legacy candidate mode 和 decision/free engine mode；不能只在 `server.py` 或前端补展示逻辑。
- Workbench matching 仍保留 legacy candidate 与 SQL decision 两条生产相关链路。新增规则时先复用现有 service/helper/test 工具，后续再单独规划匹配逻辑收敛。
- 旧逻辑清理不和业务规则变更混做。`WorkbenchMatchingRules`、`WorkbenchFreeMatchingEngine`、`WorkbenchReconciliationEngine`、工资/内部转账 legacy rule code 仍有 orchestrator、worker、免 OA、分组和异常投影调用或兼容引用，不能无测试删除。
- OA 附件解析缓存不是正式发票事实源。正式发票必须先 promotion 到 Invoice repository / `app.invoices`，Workbench 发票栏和 relation projection 只读取 canonical invoice/read model；旧 OA query service 只保留 OA detail 附件摘要。

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

## 2026-06-17 - 未配对自动 decision 撤回关联拆分

- 目标：修复未配对区银行流水+发票自动匹配候选点击“撤回关联”返回 `Workbench relation is not active or does not exist.` 的问题。
- 影响范围：`WorkbenchWriteFacade.preview_withdraw_link` / `withdraw_link`、`WorkbenchReconciliationDecisionStore` suppress 边界、`candidate_match_changed` 派生数据刷新事件、Application wiring、本模块测试矩阵。
- 关键决策：未配对区统一按钮仍由后端 preview 判定操作类型。优先查 canonical active relation；不存在 active relation 时，先兼容 legacy `WorkbenchCandidateMatchService`，再查当前 SQL `read_model.workbench_reconciliation_decisions` 中 active open/paired decision。命中 decision 时返回 `split_candidate` preview，submit suppress decision 并刷新 decision 所属月份，而不是把它当作可撤回 active relation。
- 真实原因：截图中选中的两行是 `automatic_decision` 展示组，事实源是 `read_model.workbench_reconciliation_decisions`；它没有写入 `app.workbench_pair_relations`，也不在 legacy candidate snapshot 中。旧 withdraw preview 因而只得到 relation command 的 not-found 错误，没有落到当前页面实际使用的 decision store。
- 文档影响：更新本模块 `tests.md`、本实施记录和 app runtime ownership 文档。
- 测试覆盖：新增 facade decision preview split、decision submit suppress 回归，新增 HTTP preview/submit contract 回归，并保留 legacy candidate split 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_withdraw_link_preview_splits_reconciliation_decision_when_no_active_relation tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_withdraw_link_submit_suppresses_reconciliation_decision_candidate tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_withdraw_link_splits_pure_candidate_group_without_relation_history -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_withdraw_link_preview_splits_reconciliation_decision_without_active_relation -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_reconciliation_decision_store -v`。
- 未测风险：本地测试使用 fake store/live rows，不直接回放生产 active generation；发布后仍需用真实数据抽样确认该自动 decision 被 suppress 后页面刷新为独立未配对行。

## 2026-06-16 - server.py boundary 守卫证据

- 目标：收敛 P2/P3 中 `server.py` broad dispatch / transitional delegate 风险，判断是否需要在本轮为关联台、税金抵扣、成本统计相关路径做大范围迁移。
- 影响范围：平台 runtime boundary guard、关联台 relation command boundary、downstream relation read model、read model refresh gateway；本轮不改业务代码。
- 关键决策：不在 P2/P3 性能闭环中扩大 `server.py` 重构。现有守卫已覆盖 service 不 import HTTP/auth、不直连 Redis/RabbitMQ、downstream relation read model 必须走 distribution/facade、server active relation repair 必须走 relation command boundary、Workbench write facade 使用显式依赖，以及 read model refresh producer 必须走 scope gateway 边界。
- 文档影响：更新 `.planning/P2P3-CLOSURE-PLAN.md`，本模块记录守卫证据；长期架构方向不变，`server.py` 仍只应承担 route/dependency wiring 和 HTTP 映射。
- 测试覆盖：复用 `tests/test_platform_runtime_boundary_guards.py` 中 8 个 boundary guard。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_services_do_not_import_http_auth_boundary_or_parse_cookie_token_headers tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_real_redis_and_rabbitmq_clients_are_confined_to_platform_adapters tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_downstream_relation_read_models_use_workbench_relation_distribution tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_downstream_relation_query_services_do_not_accept_pair_relation_service tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_active_relation_repairs_use_relation_command_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_write_and_matching_services_do_not_import_external_clients_directly tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_write_facade_uses_granular_constructor_dependencies tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_read_model_refresh_producers_use_scope_gateway_boundary -v`。
- 未测风险：该证据不能证明 `server.py` 已完成所有长期瘦身；它只证明当前 P2/P3 目标相关的关键边界未回退。后续若做长期重构，需要单独 phase 和更宽回归。

## 2026-06-16 - all-scope groups page 性能护栏证据

- 目标：把 P2/P3 一秒级同步审计中发现的 Workbench all-scope/full-scope 慢查询风险，收敛成首屏 groups API 的本地回归护栏。
- 影响范围：`PostgresReadModelRepository.get_workbench_groups_page` 查询 contract、关联台测试矩阵、P2/P3 closure ledger；不改变生产数据、不执行 repair 或 deploy。
- 关键决策：当前首屏 groups API 必须保留 repository page 入口，`page_size` 上限为 200，并使用 SQL `limit/offset`。生产 `pg_stat_statements` 中的历史慢 SQL 继续作为投影/发布/full-scope profiling 风险处理，不能等同于当前首屏 API 无界读取。
- 文档影响：更新本模块 `tests.md`、read-models `tests.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：新增 `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_bounds_all_scope_groups_page_query`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_bounds_all_scope_groups_page_query -v`。
- 未测风险：本地单测不证明真实生产 `workbench_rows/groups/group_rows` 投影和发布路径 P95 <= 1000ms；该部分仍需 staging/生产只读 profiling 和受控 SLO smoke。

## 2026-06-15 - Matching completed scope source-version 自愈闭环

- 目标：补齐规则版本发布后的后台闭环，确保 196、6868.55 这类历史 completed matching scope 在 `workbench_matching_rules_version` 变化后会自动重新入队并重建候选/decision。
- 影响范围：`WorkbenchMatchingDirtyScopeWorker`、`WorkbenchReconciliationDirtyQueue`、`PostgresReadModelRepository` matching dirty scope SQL、`RuntimeQueueRepository` transaction-bound JSONB adapter、Workbench all-scope aggregate source_versions、本模块文档。
- 关键决策：不新增前端补救逻辑，不手工 SQL 修指定月份，不把 OA/银行/发票事实池合并；把“completed scope 的 matching source_versions 是否覆盖当前版本”作为 durable queue/service 边界内的常驻 worker 自检。repository 使用 `for update skip locked` 原子挑出 stale completed rows 并转回 `dirty`，worker 之后按既有 claim/complete/fail 生命周期处理。
- 真实原因补充：前一轮修复把 `workbench_matching_rules_version` 纳入 month active generation freshness，但生产 `job.workbench_matching_dirty_scopes` 中 2026-01/02/03 等 scope 仍是旧版本 `completed`，常驻 worker 只 claim `dirty/retry`，因此不会自动重跑；重投后还暴露出 `RuntimeQueueRepository` 在绑定真实 `PostgresTransaction` 时没有把 read model refresh payload 包装成 JSONB，导致 decision expire 同事务入队失败；`all` active generation 还缺少 matching 版本传播，导致全局视图缺少 freshness 证明。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 和 runtime worker 治理文档。
- 测试覆盖：新增 worker claim 前 stale completed scope 自检测试、dirty queue 内存重投测试、repository 原子 SQL 测试、RuntimeQueue transaction-bound JSONB adapter 测试，并扩展 all-scope 聚合版本传播测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_queue.py tests/test_workbench_matching_dirty_scope_worker.py tests/test_workbench_reconciliation_dirty_queue.py tests/test_workbench_sql_runtime.py tests/test_workbench_reconciliation_decision_store.py -q`。
- 未测风险：本地测试未直接连接生产库；发布后需通过正常部署和 worker/read model contract 让生产 scope 重投，再只读验证目标月份分组。

## 2026-06-15 - 预约付款日期消歧与 Workbench active generation 刷新闭环

- 目标：修复 6868.55 多个月同金额同对方 OA-bank 不能自动配对，以及 196 等自动候选规则变更后旧 active generation 继续发布旧分组的问题。
- 影响范围：`WorkbenchFreeMatchingEngine`、legacy `WorkbenchMatchingRules`、`PostgresReadModelRepository` reconciliation decision 写入/过期、Workbench SQL projection/source version provider、本模块文档。
- 关键决策：不把 OA、银行流水、发票合并成一个源事实池；保留三类源事实和 `app.workbench_pair_relations` canonical relation 边界，只在后端匹配 service 中用统一候选/决策逻辑比较三栏事实。明确“预约 X 月 X 日转款/付款/支付/打款”是 OA-bank 强消歧证据，但必须与银行真实交易日期一致，且仍要求金额、方向和业务文本证据；无预约日期的重复同金额候选继续保持 conflict/open。
- 真实原因：6868.55 原先在五个月窗口内形成多 OA、多银行同金额同对方候选，互相不唯一，所以被安全地发布为 open；196 类问题叠加了 matching rule version 未进入 SQL active generation `source_versions`，以及 reconciliation decision 写入/过期只刷新 relation、不刷新主 `workbench` month generation，导致旧 generation 可以继续被 API 当 fresh。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 和本实施记录，并同步 read-models/workbench-relations 边界说明。
- 测试覆盖：新增/更新 free engine、legacy matching rules、decision repository 和 SQL runtime freshness 测试，覆盖预约日期消歧、无日期保持冲突、decision upsert/stale expire/missing expire 双刷新、matching rule version freshness。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_free_matching_engine tests.test_workbench_matching_rules tests.test_workbench_reconciliation_decision_store tests.test_workbench_sql_runtime -v`。
- 未测风险：未执行生产库写入或真实 active generation rebuild；发布后需要按运维 runbook 对受影响月份重建/刷新 Workbench active generation，并只读抽样验证 196 与 6868.55 分组。

## 2026-06-15 - 确认/撤回操作级 2 秒 SLO 与后台 cross-page SLO 拆分

- 目标：生产写操作验证显示 withdraw HTTP 成功且最终 fresh，但 `workbench` month shard 和下游 read model 仍有 2.7-11s 长尾，导致全屏 overlay 暴露给用户。将“当前关联台可见状态 2 秒内可用”的阻塞目标收敛为 canonical relation/operation projection + `workbench_relation` fresh，把 Workbench generation 和跨页面 fan-out 改为后台追赶与单独 SLO 监控。
- 影响范围：`WorkbenchWriteFacade` confirm/withdraw response contract、`ReconciliationWorkbenchPage` operation barrier fallback、Workbench 前端 mock、`write_operation_slo_audit` operation profile。
- 关键决策：确认/撤回写 API 返回的 `freshness_targets` 只包含受影响月份的 `workbench_relation`；同一写 API 返回的 `operation_projection` 是后端事务后真实 after-state，前端应用它更新受影响 group 后释放 overlay。`workbench_relation_confirm/withdraw` SLO profile 只代表操作级阻塞目标；新增 `*_cross_page` profile 保留 `workbench`、bank detail、invoice lifecycle、pending invoice、input usage、cost/search/tax 等后台追赶监控。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 和本实施记录，并同步 read-models 模块说明。
- 测试覆盖：`tests/test_workbench_auth_context_idempotency.py` 覆盖 response blocking targets；`tests/test_write_operation_slo_audit.py` 覆盖操作级与 cross-page profile 分离；`web/src/test/WorkbenchSelection.test.tsx` 覆盖 overlay barrier 只提交 `workbench_relation` target 且用后端 projection 更新 UI。
- 验证命令：见本轮最终执行记录。
- 未测风险：本地自动化证明 contract；生产 2 秒证明必须发布后用真实登录态再次执行受控 confirm/withdraw scenario。

## 2026-06-14 - 写操作全屏 overlay 与真实 freshness barrier

- 目标：把关联台确认、撤回、异常、忽略等写操作从前端本地 optimistic 重排切换为“写 API 成功后等待真实后端 freshness”的闭环，避免几秒内暴露旧关系或假同步。
- 影响范围：`ReconciliationWorkbenchPage` 写操作 gate、`GlobalOperationOverlayProvider`、`web/src/features/operationBarrier/api.ts`、`/api/operation-barrier/status`、`OperationFreshnessBarrierService`。
- 关键决策：前端不再用本地 `applyLocal*` / `updateWorkbenchAfter*` 逻辑伪造 paired/open 结果；写操作统一进入全屏 overlay，先等待 `workbench_relation` barrier，再重新读取 Workbench active generation，只有页面 payload fresh 后释放。barrier 只读 runtime snapshot，不写 readiness、不重建 read model。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md`、`implementation-notes.md`，并同步 read-models、app-shell、app-architecture、批量账务、免 OA、往来款模块文档。
- 测试覆盖：新增 `GlobalOperationOverlayContext.test.tsx`、`OperationBarrierApi.test.ts`、`test_operation_freshness_barrier.py`；更新 `WorkbenchSelection.test.tsx` 覆盖写操作后等待 barrier 与 fresh reload，不再依赖本地 optimistic 重排。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产登录态下的 P50/P95/P99 operation-to-fresh latency 仍需发布后用 approved mutating scenario 或安全 synthetic fixture 度量。

## 2026-06-14 - 撤回可恢复关系策略收敛

- 目标：彻底修复 withdraw preview/submit 中未恢复 row 仍在“操作后”显示成同一行的问题，避免未标记 manual history、自动候选或同 row-set snapshot 污染撤回链路。
- 影响范围：`WorkbenchPairRelationService`、`WorkbenchRelationCommandService` relation mode registry、Workbench withdraw preview API、PostgreSQL relation history replay dry-run。
- 关键决策：可恢复关系由统一策略 `workbench_relation_modes` 判定；真实 active before relation 写入 confirm history 时才由 PairRelationService 标记 `special_metadata.restorable_on_withdraw=true`。外部传入的 display/candidate/history snapshot 不再因为 `relation_mode != existing_case` 就默认恢复；同一 row-set snapshot 永不恢复。
- 清理：移除 withdraw preview 的 OA 附件无 history 合成恢复路径；OA 附件 ID 解析 helper 仅保留给 active relation repair 使用，不再参与撤回恢复。
- 测试覆盖：新增/更新 PairRelationService、Workbench v2 API、relation command service 和 history replay 工具测试，覆盖 owned active snapshot 可恢复、未拥有 manual snapshot 不恢复、同 row-set 不恢复、API after groups 拆行、发布前 dry-run 报告非可恢复 history。
- 文档影响：更新本模块 `README.md`、`tests.md`、`implementation-notes.md`，并同步 Workbench relation 模块测试/实施说明。
- 未测风险：真实生产数据 dry-run 需要发布前在目标环境执行；本轮本地 fake connection 覆盖审计输出结构，不读取生产库。

## 2026-06-14 - 撤回预览显示归属与可恢复关系边界收敛

- 目标：修复 withdraw preview/submit 把 `existing_case` 显示归属当成可恢复 relation，导致“操作后”银行流水+发票或 OA+发票仍显示在同一行的问题。
- 影响范围：`WorkbenchPairRelationService`、Workbench withdraw preview/submit API、批量账务 withdraw 回归、前端 Workbench mock 和本模块/批量账务文档。
- 关键决策：`relation_mode=existing_case` 默认是读侧 display ownership，不是 relation repository 的可恢复事实；只有真实 active relation snapshot 或显式 `restorable_on_withdraw` 的关系才能在撤回时恢复。历史中已污染的 `existing_case` before_relations 由运行时过滤，避免破坏旧数据。
- 文档影响：更新本模块 `README.md`、`tests.md`、`implementation-notes.md`，并同步批量账务模块 `README.md`、`state-machine.md`、`tests.md`、`implementation-notes.md`。
- 测试覆盖：新增/更新 pair relation service、Workbench v2 API 和 batch accounting API 回归，覆盖新历史写入过滤、旧污染历史过滤、银行+发票撤回后分行、真实上一 relation 仍可恢复。
- 验证命令：见本轮最终执行记录。
- 发布前审计：2026-06-14 已在生产执行只读 SQL 审计，`active_display_only_relation_count=0`、`display_only_history_before_relation_count=3`、`affected_history_case_count=3`，运行时过滤覆盖历史污染，不需要 backfill。
- 未测风险：未执行生产写入型 repair；本次审计结论为无需写入型 backfill。

## 2026-06-13 - Workbench 发票事实源收敛与列交互修复

- 目标：修复关联台三栏列布局、详情 icon 和 selection 高亮问题，同时把 OA 附件正式发票统一 promotion 到 Invoice repository / `app.invoices`，Workbench 发票栏不再从 OA 附件解析缓存临时生成发票行。
- 影响范围：`ImportNormalizationService.upsert_oa_attachment_invoice`、OA attachment cache update callback、Workbench SQL projection、legacy `WorkbenchQueryService`、Workbench relation SQL projection、前端 Workbench columns/selection。
- 关键决策：`app.oa_attachment_invoice_cache` 只保留解析缓存职责；正式发票事实必须以 canonical `Invoice` 写入 import service/repository，并通过 `source_links.source_type='oa_attachment_invoice'` 保留 OA/附件/费用项来源。Workbench SQL 发票行、relation projection、tax/cost 下游都从 canonical invoice/read model 读取。旧 `WorkbenchQueryService` 只在 OA detail 中展示附件解析摘要，不再发布 `source_kind=oa_attachment_invoice` 的 invoice row。
- 文档影响：更新本模块测试矩阵、税金抵扣/成本统计模块记录和运维监控说明。
- 测试覆盖：新增/更新 OA 附件 promotion、Workbench SQL projection、relation projection、legacy query service 不发布发票行、前端列布局和 selection hook 回归。
- 验证命令：见本轮最终执行记录。
- 未测风险：未对真实生产历史 `app.oa_attachment_invoice_cache` 做全量 backfill/dry-run；发布前应对存量 OA 附件正式发票做只读抽样，确认 canonical `app.invoices.source_links` 已补齐。

## 2026-06-12 - 关联台撤回 preview 分组与后台刷新交互收敛

- 目标：修复撤回 preview “操作后”三栏仍按旧 `case_id` 合并的问题；提交成功后先做本地 optimistic update，后台刷新期间只锁定刚操作 row/group，避免全页面不可操作。
- 影响范围：`Application._relation_groups`、`WorkbenchWriteFacade._withdraw_relation_preview_payload`、`ReconciliationWorkbenchPage` 写操作 gate/pending row lock、`AppHealthStatusProvider` source mapping、Workbench 前端 mock。
- 关键决策：withdraw preview after 中没有进入 after relation 的 row 使用逐行独立 group，并清理 preview-only 旧 relation 展示字段；Workbench active generation stale/loading 只提示刷新，不映射为 `oaSync=dirty`，不全局禁用无关写；真正的 OA sync dirty/refreshing、无权限和 App Health blocked 继续阻断写。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 和 `implementation-notes.md`。
- 测试覆盖：新增 backend facade preview 分组回归；新增前端 workbench stale 放行、OA dirty 阻断、提交后 pending group 局部锁；更新 App Health provider source mapping 断言。
- 验证命令：`PYTHONPATH=backend/src python -m unittest tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_withdraw_preview_after_groups_unrestored_bank_invoice_rows_individually`；`cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx -t "workbench stale refresh does not globally disable selected group actions|OA dirty sync still disables selected group actions"`；`cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx -t "confirm link locks only the operated group while the background refresh is pending"`；`cd web && npm test -- --run src/test/AppHealthStatusContext.test.tsx -t "reports yellow when the backend says the workbench read model is stale"`。
- 未测风险：尚未做真实浏览器截图/生产数据 smoke；后续如对所有 action 都加入更细粒度 row-scope stale 判断，需要继续补跨 group 并发交互测试。

## 2026-06-12 - 关联台 group 级统一撤回/拆分闭环

- 目标：已配对区和未配对区点击任意 row 都带入完整 group；统一撤回按钮先打开三栏 preview，再由后端判定 `withdraw_relation` 或 `split_candidate`。
- 影响范围：`WorkbenchRelationCommandService` withdraw preview/submit、`WorkbenchWriteFacade.withdraw-link` preview/submit、`WorkbenchCandidateMatchService` suppress 边界、前端 selection model/API mapper/关联预览提交。
- 关键决策：relation 撤回只通过 `WorkbenchRelationCommandService`，submit 使用 `operation_type`、`preview_id`、`submit_expected_versions` 锁定 preview。active relation 有 history 时恢复上一状态；无 history 时撤到无关联。纯自动候选不写 relation history，而是 suppress candidate 为 `manual_override`。
- 文档影响：更新本模块 `README.md`、`tests.md`，并同步 `workbench-relations` 模块文档。
- 测试覆盖：新增 `WorkbenchSelectionModel.test.ts`；更新 `WorkbenchSelection.test.tsx` group context/submit payload；新增 command service withdraw preview lock 和 facade withdraw/split tests；更新 API 无 history 撤回口径和 rollback characterization。
- 验证命令：`python -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_auth_context_idempotency.py -q`；`python -m pytest tests/test_workbench_v2_api.py -k "withdraw_link" tests/test_workbench_write_characterization.py -k "withdraw_link" tests/test_workbench_candidate_match_service.py -q`；`npm --prefix web test -- WorkbenchSelection.test.tsx WorkbenchSelectionModel.test.ts --run`；`npm --prefix web run build`。
- 未测风险：未做真实浏览器/staging smoke；多 group 禁止目前依赖后端 preview/前端单 group button 规则，后续如开放批量选择需要补更专门的交互测试。

## 2026-06-12 - server active relation repair command 写入口收敛

- 目标：删除 `server.py` 中 OA invoice offset auto pair 和 OA 附件上下文 repair 对 `WorkbenchPairRelationService` 的直接写入，避免 Workbench payload build/repair 路径成为第二个 relation 写事实源。
- 影响范围：`Application._sync_oa_invoice_offset_auto_pair_relations`、`_repair_active_relations_with_oa_attachment_context`、`WorkbenchRelationCommandService` mode registry/history override、runtime boundary guard。
- 关键决策：本阶段只迁移 direct mutation，保留原有 read-build repair 触发点、scanned row 保护、外层 persist/lifecycle 行为；server relation 读/展示/persist helper 后续继续抽离。
- 文档影响：更新本模块 `implementation-notes.md`、`tests.md` 和 `workbench-relations` 模块文档。
- 测试覆盖：新增 `test_confirm_relation_allows_oa_invoice_offset_auto_match_mode`、`test_replace_existing_confirm_uses_requested_history_operation_type`、`test_server_active_relation_repairs_use_relation_command_boundary`，并运行 OA offset auto pair、source link、防误取消、missing attachment repair 回归。
- 验证命令：见 `workbench-relations` Phase 7J 记录。
- 未测风险：no-OA legacy repair/consolidation 和 batch accounting repair 仍待后续切片迁移或降级为 repair port。

## 2026-06-12 - Workbench exception apply relation command 写入口收敛

- 目标：删除 `WorkbenchExceptionApplicationService` closed apply 直接创建 pair relation 的写入口，把 `normal_match` / `oa_exempt` 纳入统一 relation command lifecycle。
- 影响范围：`WorkbenchExceptionApplicationService.apply`、`WorkbenchRelationCommandService` mode registry、`WorkbenchWriteFacade.apply_exception` rollback/error mapping、Application wiring、runtime boundary guard。
- 关键决策：closed action 在创建本地 exception case 前先执行 relation command preflight；缺 command service 或 relation read model non-fresh 时 fail fast，不留下半写入 case。成功路径通过 `confirm_relation(..., history_operation_type="workbench_exception_apply")` 写 relation，保留 OA exemption/evidence/display tags 等展示字段。
- 文档影响：更新本模块 `README.md`、`tests.md` 和 `workbench-relations` 模块文档。
- 测试覆盖：新增 `test_apply_closed_exception_delegates_pair_relation_to_command_service` 和 `test_workbench_exception_application_uses_relation_command_boundary`，并运行三方闭环、自动/手动免 OA structured fields 回归。
- 验证命令：见 `workbench-relations` Phase 7I 记录。
- 未测风险：`server.py` active relation repair、no-OA legacy repair/consolidation 和 batch accounting repair 仍待后续切片迁移或降级为 repair port。

## 2026-06-12 - 个人暂借款 relation command 写入口收敛

- 目标：删除 `confirm_personal_advance_repayment` 直接调用 `WorkbenchPairRelationService.replace_with_confirmed_relation` 的写入口，把 `personal_advance_repayment_settlement` 纳入统一 relation command lifecycle。
- 影响范围：`WorkbenchWriteFacade.confirm_personal_advance_repayment`、`WorkbenchRelationCommandService` mode registry、Workbench personal advance API 回归、runtime boundary guard。
- 关键决策：缺少 relation command service 时先 fail fast，不创建 exception case；成功路径通过 `confirm_relation(..., replace_existing=True)` 写 relation，保留原有 amount summary、cost exclude metadata 和 response shape。
- 文档影响：更新本模块 `README.md`、`tests.md` 和 `workbench-relations` 模块文档。
- 测试覆盖：新增 `test_personal_advance_repayment_delegates_relation_write_to_command_service`、`test_personal_advance_repayment_fails_fast_without_relation_command_service`、`test_workbench_personal_advance_repayment_uses_relation_command_boundary`，并运行既有个人暂借款 API 成功/失败回归。
- 验证命令：见 `workbench-relations` Phase 7H 记录。
- 未测风险：其他 exception application relation mode 族仍待单独迁移，不能与个人暂借款混为同一切片。

## 2026-06-12 - confirm/cancel relation command 写入口收敛

- 目标：删除关联台 `confirm-link` / `cancel-link` 在缺少 `WorkbenchRelationCommandService` 时回退到 `WorkbenchPairRelationService` 直接写 pair snapshot 的 legacy fallback。
- 影响范围：`WorkbenchWriteFacade.confirm_link`、`_confirm_link_with_uow`、`cancel_link`、`_cancel_link_with_uow`、Workbench idempotency/UoW characterization tests、workbench relation boundary guard。
- 关键决策：非 UoW 路径缺 relation command service 返回 `workbench_relation_command_unavailable`；UoW handler 中也必须通过 transaction-bound command repository 写入，不再调用 `_persist_workbench_pair_relations_in_transaction` 旧 hook。idempotency replay/in-progress 判断仍优先于 handler 内 command 可用性。
- 文档影响：更新本模块 `README.md`、`tests.md` 和 `workbench-relations` 模块实施记录。
- 测试覆盖：`test_confirm_and_cancel_link_fail_fast_without_relation_command_service`、`test_workbench_confirm_and_cancel_link_have_no_direct_pair_write_fallback`，并更新 `tests/test_workbench_write_characterization.py` 的 UoW fakes 以记录 command repository 写入。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_auth_context_idempotency.py tests/test_workbench_write_characterization.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_confirm_and_cancel_link_have_no_direct_pair_write_fallback -q`。
- 未测风险：个人暂借款、exception application、server active relation repair 等 Workbench-adjacent relation 写入口仍待后续切片迁移。

## 2026-06-11 - 外部往来 bank-only 闭环保持 open

- 目标：修正外部往来手动闭环在关联台的分区语义，移除 `bank-only + turnover_manual_closure + exactly 2 bank rows` 进入 paired 的例外。
- 影响范围：Workbench candidate grouping、server pair relation display payload、Workbench read model schema version、外部往来 closure integration、关联台本地 optimistic update。
- 关键决策：`turnover_manual_closure` 仍是 Workbench active pair relation 事实源，但 bank-only 只表示外部往来款内部闭环和行占用；关联台 paired 仍要求 OA + 银行 + 发票三栏完整。外部往来页只可撤回 bank-only open relation，三栏 paired relation 必须在关联台撤回。
- 文档影响：更新本模块 `state-machine.md`、`tests.md` 和本实施记录；同时同步 turnover-ledger 模块与产品/API 文档。
- 测试覆盖：`tests/test_workbench_turnover_grouping.py` 覆盖 bank-only open；`tests/test_turnover_workbench_integration.py` 覆盖 confirm 后 open、bank-only withdraw cancel、三栏升级后拒绝外部往来页撤回；`web/src/test/WorkbenchSelection.test.tsx` 覆盖 turnover bank-only optimistic update 不进 paired。同步 bump Workbench SQL/legacy read model schema version，避免旧 active generation/cache 继续被当成 fresh。
- 验证命令：见本轮最终执行记录。
- 未测风险：未运行真实生产库 active generation 全量回放；发布前如存量 `turnover_manual_closure` paired 数据较多，应做只读抽样确认分区变化符合业务预期。

## 2026-06-11 - active relation 重复 OA 去重防线

- 目标：修复关联台 paired 详情中出现两个一模一样 OA 的问题，并防止后续 active relation payload 再携带重复 row id 或跨 active case 复用同一 row。
- 影响范围：`WorkbenchPairRelationService`、`Application._relation_groups`、relation integrity repair、pending invoice attach existing relation 合并逻辑、Workbench/Pending invoice 相关测试和模块文档。
- 关键决策：真实原因不是前端误渲染两条不同 OA，而是 active relation 的 `row_ids` 中存在重复 OA row id，后端 grouping 原样展开导致同一 OA summary 出现两次。修复点放在 relation 写入 normalize、snapshot normalize、repair plan 和 query grouping 四层；同一 row id 若出现冲突 row type 直接失败。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 和本实施记录。
- 测试覆盖：新增/更新 `tests/test_workbench_pair_relation_service.py`、`tests/test_workbench_pair_relation_integrity_repair.py`、`tests/test_workbench_api.py`，并通过 pending invoice service/API 回归保护 relation 合并路径。
- 验证命令：`pytest tests/test_workbench_pair_relation_service.py tests/test_workbench_pair_relation_integrity_repair.py tests/test_workbench_api.py -q`；`pytest tests/test_pending_invoice_service.py tests/test_pending_invoice_api.py -q`。
- 未测风险：未对生产历史库执行全量 repair dry-run；发布前如怀疑存量 relation payload 已污染，应先跑只读 repair plan 并抽样 paired 详情。
- 后续事项：后续所有写 active relation 的模块必须复用 pair relation service/repository，不在页面或 server handler 中手拼可重复 row payload。

## 2026-06-11 - 测试闭环矩阵与状态机补齐

- 目标：执行测试闭环 master goal 的 reconciliation-workbench 模块轮次，审计关联台页面/API/read model/worker/下游 fan-out 测试覆盖。
- 影响范围：本模块 `tests.md`、`state-machine.md`、`implementation-notes.md`；未改变产品业务口径。
- 关键决策：关联台最小闭环命令覆盖候选规则、matching orchestrator、query facade/cache、dirty queue/worker、active generation 关键 SQL runtime、核心 API action 和前端 Workbench API/selection/grid；完整历史回归由 nightly `verify.sh all` 和按改动选择的扩展命令承担。
- 文档影响：补齐影响面清单、场景覆盖清单、七类测试适用性、历史 bug 回归库、关键 smoke flows、验证命令和未测风险。
- 测试覆盖：沿用现有 Workbench 后端和前端测试；本轮未新增代码测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_rules tests.test_workbench_free_matching_engine tests.test_workbench_matching_orchestrator -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_workbench_dirty_queue_wiring tests.test_workbench_matching_dirty_scope_worker -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_groups_page_pins_versions_counts_and_rows_to_single_active_generation tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_workbench_refresh_handler_rebuilds_scope_and_marks_dirty_scope_done tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_workbench_refresh_status_api_exposes_dirty_scopes_and_worker_lag -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_keeps_oa_bank_exact_sum_candidate_in_one_open_group tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_and_cancel_link_defer_read_model_persistence_to_background -v`；`cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/WorkbenchApiRuntimePath.test.ts src/test/WorkbenchSelection.test.tsx src/test/CandidateGroupGrid.test.tsx`。
- 未测风险：不运行真实生产库 active generation 全量回放；前端视觉/大数据性能需要浏览器或 staging smoke。
- 后续事项：下一模块继续处理 `bank-details`。

## 2026-06-10 - OA 与多银行流水合计候选

- 目标：支持 1 条 OA 与唯一一组 2 到 6 条同方向银行流水按分精度合计等于 OA 金额时自动形成 OA-bank 候选，继续等待发票。
- 影响范围：`WorkbenchMatchingRules` legacy candidate mode、`WorkbenchFreeMatchingEngine` decision mode、matching orchestrator、candidate grouping、Workbench API payload/read model invalidation。
- 关键决策：
  - 规则名为 `oa_bank_exact_sum`。
  - 单笔 `oa_bank_exact_amount` 优先；若已生成单笔 OA-bank 精确候选，不再生成多银行合计候选。
  - 每条银行流水必须复用现有 OA-bank evidence，不允许只靠金额。
  - 同一 OA 存在多个等额银行流水组合时不自动选择。
  - legacy candidate 生成 `candidate_type=oa_bank`、`status=incomplete`，让 OA 和多条银行流水进入同一个 open candidate group。
  - decision mode 生成 `WorkbenchDecision(match_shape=oa_bank, rule_code=oa_bank_exact_sum, payment_amount_closed=True)`，供 SQL decision/read model/worker 链路消费。
- 文档影响：已更新 `docs/product-specs/reconciliation-and-workbench.md`、本模块 `state-machine.md` 与 `tests.md`。
- 测试覆盖：
  - `tests/test_workbench_matching_rules.py` 覆盖 legacy 规则正例、唯一性、证据要求、单笔精确优先。
  - `tests/test_workbench_free_matching_engine.py` 覆盖 decision mode 正例、歧义、证据要求、单笔精确优先。
  - `tests/test_workbench_matching_orchestrator.py` 覆盖 legacy candidate 持久化、decision store 持久化和 read model invalidation。
  - `tests/test_workbench_v2_api.py` 覆盖 Workbench API payload/grouping 中 OA 与多条银行流水保持同一个 open candidate group。
- 验证命令：见 `tests.md` 的 Workbench 相关验证命令。
- 未测风险：未新增前端组件测试；当前变更沿用既有 open candidate group shape。未做真实生产库 worker dry-run。
- 后续事项：可单独评估 legacy candidate 与 decision/free engine 的规则收敛；不要和本规则混入无关旧逻辑删除。

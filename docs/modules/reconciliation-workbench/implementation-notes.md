# 关联台 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- `oa_bank_exact_sum` 属于后端自动候选规则，必须同时覆盖 legacy candidate mode 和 decision/free engine mode；不能只在 `server.py` 或前端补展示逻辑。
- Workbench matching 仍保留 legacy candidate 与 SQL decision 两条生产相关链路。新增规则时先复用现有 service/helper/test 工具，后续再单独规划匹配逻辑收敛。
- 旧逻辑清理不和业务规则变更混做。`WorkbenchMatchingRules`、`WorkbenchFreeMatchingEngine`、`WorkbenchReconciliationEngine`、工资/内部转账 legacy rule code 仍有 orchestrator、worker、免 OA、分组和异常投影调用或兼容引用，不能无测试删除。

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

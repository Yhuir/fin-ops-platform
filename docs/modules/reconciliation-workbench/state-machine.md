# 关联台状态机

> 修改 `关联台` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。关联台使用 active generation 原子发布模型；不要机械套成普通 read model gateway。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| Candidate group | `open` | active workbench generation、候选规则、exception/open relation projection | 候选未完整闭环，等待发票/OA/银行/人工确认。可通过 confirm/exception/no-OA/turnover 等动作流转。 |
| Candidate group | `paired` | active pair relation、closed exception relation、active generation paired zone | confirm 成功、closed exception、免 OA/往来款等 relation 写入后进入。 |
| Candidate group | `ignored` | exception/ignore case fact | 用户忽略发票或异常 case 后进入；unignore 后回到 open。 |
| Pair relation | `active` | `app.workbench_pair_relations` / repository | confirm、特殊规则、免 OA、turnover、batch accounting 等写入。 |
| Pair relation | `withdrawn` / cancelled | relation audit/history、撤回动作 | cancel/withdraw 后进入；必须恢复或重建受影响 open group。 |
| Exception case | `open` | exception case service/projection | preview/apply 等动作创建，影响 open zone row display。 |
| Exception case | `closed` | exception relation/projection | 三方闭合、OA 免单等处理完成后进入 paired/processed 展示。 |
| ETC summary | `open etc_invoice_summary` | ETC 业务批次 + active generation projection | 已提交 OA 的 ETC 批次折叠为一条发票汇总行，等待普通三项配对。 |
| Matching candidate | `fresh` / `dirty` / `failed` | workbench matching dirty queue、candidate match service | lifecycle mark dirty 后由 worker 重建；失败进入 retry/failed。 |

关键规则：

- `oa_bank_exact_sum`：1 条 OA 与唯一一组 2 到 6 条同方向银行流水，且每条银行流水均有 OA-bank 业务证据，金额按分精度唯一闭合时，生成 open OA-bank candidate；缺少发票时不得进入三方 paired。
- 单笔 `oa_bank_exact_amount` 优先于多流水合计；存在多个等额银行流水组合、任一流水缺少证据、或已有更高优先级候选时，不自动选择。
- 已有 active relation 的 ETC summary 不得继续出现在 open 区；paired 区仍可展示展开明细。
- active relation 的 `row_ids` 是集合语义：同一 relation 内重复 row id 必须在写入/normalize/repair/query grouping 层去重；同一 row id 不能跨不同 active case 复用。重复 row id 的真实结果是列表详情重复渲染同一个 OA/银行/发票，不代表存在两条业务事实。
- 关联台确认/撤回是跨页面事实，必须产生 affected scopes/months、审计和下游 refresh 信号。
- 外部往来 `relation_mode=turnover_manual_closure` 是 Workbench active pair relation 事实源，但不是 bank-only paired 例外；仅银行流水的外部往来闭环必须留在 open，只有 OA + 银行 + 发票三栏都存在时才进入 paired。

禁止流转：

- 禁止前端本地合并底层 OA/银行/发票事实来伪造 paired/open。
- 禁止 read model 非 fresh 时把空 open rows 当成真实无候选。
- 禁止 ETC 批次人工确认后直接进入 paired；必须仍经过普通 OA/银行/发票关系确认。
- 禁止 failed generation、building generation 或 stale Redis payload 被展示为 fresh。
- 禁止 active relation payload 保留重复 row id，或以不同 active case 复用同一 row id 来表达多付款/多发票场景；这类场景必须合并到同一 relation 并通过 summaries/+N 展开。

## UI 状态

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | 初次请求 `/api/workbench*`、分页/详情加载 | 显示加载，不保留旧页面 snapshot 作为事实。 |
| refreshing | `read_model_status=refreshing`、OA sync refreshing、dirty scope processing | 可展示旧 active generation 和刷新提示；OA sync refreshing 需要阻断写入，Workbench active generation 后台刷新不全局禁用无关 group。 |
| stale | `read_model_status=stale`、failed/dirty scope、source mismatch | 页面必须提示陈旧；不能把空 rows 解释成真实业务结论。Workbench active generation stale 不等同于 OA dirty，不应把页面所有写操作全局禁用。 |
| error | API/action/read model unavailable 或 failed | 展示业务错误；不暴露底层 SQL 细节。 |
| empty | fresh active generation 中目标 zone/group 为空 | 只有 fresh 后才能认为 open/paired 为空。 |
| operation pending | `GlobalOperationOverlayProvider` 包裹中的确认、撤回、异常、忽略等写操作 | 写 API 成功后继续等待 `workbench_relation` barrier 和 Workbench active generation fresh；期间全屏阻塞，避免用户继续操作旧关系。失败时展示错误并保持阻塞，用户确认后返回页面。 |
| permission disabled/hidden | session 权限、App Health write safety gate、OA sync write gate | 无写权限、`overall.write_safety.blocks_mutations=true` 或 OA sync dirty/refreshing 时禁用确认/撤回；普通 read model blocked/red 只提示读侧故障并交给具体写 API precondition，不全局禁用无关 group。 |

前端 domain event：

- `workbenchRelationUpdated` 由关联台确认/撤回等动作发出，提示当前浏览器页面刷新。
- 关联台订阅 `turnoverRelationUpdated`、`workbenchRelationUpdated`、`bankTransactionCategoryUpdated` 后重新加载或刷新局部状态。
- 事件只做刷新提示，不证明后端 relation/read model 已 fresh。

## Read Model / Worker 状态

| 状态 | 判定 | 后续动作 |
| --- | --- | --- |
| `fresh` | active generation source/schema/version 一致，且没有 active dirty scope | 页面可展示和 Redis 可缓存。 |
| `refreshing` | dirty scope pending/processing，或 refresh handler 正在重建 | 页面展示刷新状态，worker 继续处理。 |
| `stale` | active generation 落后、failed generation newer、dirty scope failed、source mismatch | 入队/重试 refresh；不能缓存 stale payload。 |
| `failed` | generation consistency failure 或 refresh handler failed | App Health/refresh status 暴露失败，运维修复后重跑 worker。 |
| `unavailable` | SQL/read model/runtime dependency 不可用 | route 返回可恢复错误或 unavailable 状态。 |

Refresh 触发来源：

- 导入确认、OA 同步、发票/银行/ETC 变化和设置变化。
- 关联台确认/撤回、exception apply/cancel、ignore/unignore。
- 下游模块如 no-OA、turnover、batch accounting 通过 relation/dirty outbox 影响关联台。
- worker `workbench.read_model.refresh` 发布 active generation；matching dirty worker 重建候选。
- `startup_stale_scan` 默认关闭；启用时只标记 stale matching dirty scopes；它不直接 invalidating workbench read model。
- PostgreSQL formal read path 必须恢复 `job.workbench_matching_dirty_scopes.status='completed'` 的 scope run，供 `WorkbenchCandidateMatchService.is_scope_fresh(...)` 判断 freshness；否则 opt-in 启动补扫会因为缺少 scope run 证明而把已完成月份重新标 dirty。

失败恢复：

1. 查 `/api/workbench/refresh-status`、App Health、dirty scopes、outbox 和 worker heartbeat。
2. 如果是 matching dirty scope，重试 `workbench-matching` worker；不要回退 legacy dirty scope。
3. 如果是 active generation inconsistency，修复 generation 或重建 scope；不得手工把 failed 改 fresh。
4. 如果是页面交互问题，先确认写 API response 的 affected months、operation barrier target、`/api/workbench*` 的 `read_model_status` 和 active generation freshness，再看 domain event/selection 状态。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-14 | 关联台写操作从本地 optimistic 重排改为全屏 operation overlay，等待 `workbench_relation` barrier 与 Workbench active generation fresh 后释放 | `ReconciliationWorkbenchPage` 写操作 gate、`GlobalOperationOverlayProvider`、`/api/operation-barrier/status` | `web/src/test/WorkbenchSelection.test.tsx`；`web/src/test/GlobalOperationOverlayContext.test.tsx`；`web/src/test/OperationBarrierApi.test.ts`；`tests/test_operation_freshness_barrier.py` |
| 2026-06-12 | 关联台撤回 preview 操作后未恢复 row 逐行独立展示，并拆分 Workbench stale 与 OA dirty 写阻断 | `Application._relation_groups`、`WorkbenchWriteFacade` withdraw preview、App Health source mapping、前端 optimistic update/pending row lock | `tests/test_workbench_auth_context_idempotency.py`；`web/src/test/WorkbenchSelection.test.tsx`；`web/src/test/AppHealthStatusContext.test.tsx` |
| 2026-06-11 | 补齐测试闭环状态机 | open/paired/exception/dirty/active generation/UI/read model 状态边界 | 待本轮 Workbench 验证 |
| 2026-06-11 | active pair relation 增加 row id 去重和跨 active case 复用防线，修复 paired 详情重复 OA 展示 | WorkbenchPairRelationService、server relation grouping、integrity repair、pending invoice attach relation 合并 | `tests/test_workbench_pair_relation_service.py`、`tests/test_workbench_pair_relation_integrity_repair.py`、`tests/test_workbench_api.py`、`tests/test_pending_invoice_service.py` |
| 2026-06-11 | 外部往来 bank-only 手动闭环移除 paired 例外，只有 OA + 银行 + 发票三栏完整才进入 paired | WorkbenchCandidateGroupingService、server relation display payload、关联台本地 optimistic update | `tests/test_workbench_turnover_grouping.py`、`tests/test_turnover_workbench_integration.py`、`web/src/test/WorkbenchSelection.test.tsx` |
| 2026-06-10 | 新增 `oa_bank_exact_sum` 自动候选：1 条 OA 可与唯一一组 2..6 条银行流水合计闭合付款金额，并保持待发票 open candidate group | Workbench matching rules、free decision engine、candidate grouping、API payload/read model invalidation | `tests.test_workbench_matching_rules`；`tests.test_workbench_free_matching_engine`；`tests.test_workbench_matching_orchestrator`；`tests.test_workbench_v2_api` |
| 2026-06-09 | 已有 active relation 的 ETC summary 在 open 区增加 projection/repository 双重排除，并保留 paired 区展开明细 | Workbench open/paired 查询、历史 ETC 批次迁移、陈旧 active generation 防线 | `tests.test_workbench_sql_runtime`；生产库只读验证 |
| 2026-06-08 | 已提交 ETC 批次在 open 区投影折叠 `etc_invoice_summary`，等待普通三项配对 | 关联台 open/paired 分区、Workbench projection | `tests.test_etc_backend` |

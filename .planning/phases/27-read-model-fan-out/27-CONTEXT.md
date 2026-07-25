# Phase 27: 按页面访问收敛 Read Model、消除写后全局 Fan-out 并完成全页面生产性能验证 - Context

**Gathered:** 2026-07-22
**Status:** Executing final production validation
**Source:** User-approved architecture plus repository/code/runtime inventory

<domain>
## Phase Boundary

本阶段把普通业务写入与派生页面重建解耦：写请求只原子提交 canonical facts、精确 source version 和 audit；页面在 route 进入/重进、查询变化、浏览器手动刷新或明确重试时，通过现有 freshness/status/enqueue 边界判断是否需要精确重建当前依赖 scope。阶段覆盖 17 个正式页面、15 个正式 read model、全部 mutating feature API、全部可写 Drawer、非页面资源依赖、旧 lifecycle/fan-out 删除、七类测试、远程 main 发布、正式部署和部署后逐页面逐操作正确性/性能观测。

本阶段不新增消息总线、CDC、事件溯源、第二套缓存、每页 SSE、前端事实源或通用增量框架；不把没有正式 read model 的页面机械改造成 read-model 页面；不改变 Phase 26 已冻结的 turnover relation 业务语义和历史修复安全合同。
</domain>

<decisions>
## Locked Decisions

### Correctness

- “访问页面时重建”精确定义为：route enter/re-entry、业务 scope/query 变化、浏览器手动刷新或用户明确重试时检查 freshness；只有 stale/missing 的依赖 scope 才重建，fresh 直接读。focus、hidden→visible 与 BFCache 恢复不触发业务 I/O。
- 页面只有在服务端 source-version proof 与 projection version 一致时才能声明 fresh；queue 空、最近构建时间、前端事件或缓存命中都不能证明正确。
- stale payload 可以作为明确标注的上次结果展示，但不能伪装 fresh；确认、撤回、导出、后续写等严格消费者必须等待 fresh 或 fail closed。
- Worker 发布必须执行 source-version CAS；旧任务不得覆盖新事实。

### Write Path

- 普通写请求只提交 canonical facts、精确 source version 和 audit；不创建所有下游页面 refresh jobs，不等待全局 operation barrier。
- 写入类型只允许四类：canonical fact mutation、projection semantic rule、read-time/display rule、explicit batch/repair。
- 成本统计标签准入规则属于 read-time rule：保存后重新查询过滤，不重建 cost read model。
- 银行自动标签保存属于 projection semantic rule：普通保存不扫描全历史；显式 reapply 才允许分片批量重建。
- 全历史、部署回填、数据重置和人工 repair 必须与普通保存分离，有明确权限、进度、失败恢复和审计。

### Scope And Performance

- 普通写禁止 bare `all` fallback；无法证明精确 scope 时 fail closed，不以 `all` 掩盖未知。
- 一个 `model + scope + target_version` 最多一个 current-effective job；依赖链只为当前页面 DAG 中 stale 节点入队。
- 性能目标继续按普通写、freshness gate、已 fresh 首屏和 stale-to-fresh 分段测量；其中普通 stale scope p99≤3s 是后续性能目标，不是本阶段 DONE 门槛。超过 3 秒记录为 `performance_follow_up`，不得为追逐该数值新增基础设施或复杂增量链路。
- 本阶段功能硬门是：页面 route 访问/重进、查询变化、手动刷新或明确重试后，在现有有界验证超时内最终 fresh，payload 与 canonical facts、关系、版本和 scope 完整一致；永久 refreshing、无法重试、queue/worker 不收敛或 stale-as-fresh 仍然失败。
- 任意规模的全历史 rebuild 不承诺 3 秒；它单独验证吞吐、当前 scope 优先、分片并发、可恢复和不阻塞普通保存。

### Frontend And Drawers

- 页面和 Drawer 只调用自己的 query/command owner；不得直接访问 queue、repository 或其他页面 API。
- 普通业务页面不使用 finance domain event、window 自定义刷新事件或业务 BroadcastChannel 唤醒 freshness check。
- hidden 页面不后台重建；重新可见/focus 时也不自动检查。两个已打开窗口互不自动刷新，用户在目标窗口 route 重进、查询变化或手动刷新后独立检查。
- 只读详情/导出 Drawer 只加载自己的 identity/scope，不重建整页；没有正式 read model 的查询保持现有 owner，不为统一而新增 read model。

### Architecture And Cleanup

- 复用 `READ_MODEL_MANIFEST`、`ReadModelQueryGateway`、`ReadModelRefreshGateway`、scope policy registry、PostgreSQL durable queue、现有 workers 和页面现有 query owner；删除 PageRuntime focus/visibility/BFCache 与业务 BroadcastChannel 刷新协调。
- Workbench 保留 active-generation 原子发布，不机械改成普通 read model。
- 每个垂直切片迁移后立即删除该切片旧 lifecycle、`all` fallback、direct enqueue、operation-barrier wait 和 live fallback；不保留长期新旧双路径或隐藏兼容分支。
- Phase 26 与本阶段重叠的 turnover/workbench 文件只能在其冻结合同基础上修改；不得覆盖、回退或绕过 Phase 26 安全规则。

### Delivery

- 编码前必须通过全量覆盖硬门：17 pages、15 read models、所有 mutating APIs、所有可写 Drawer、所有 lifecycle/enqueue 调用均有 owner/处理/删除/测试映射，unmapped=0。
- 当前行为基线 `719c9a34` 已在 `origin/main` 并作为 release `main-719c9a34-20260725101310` 激活，migration `0125` 与正式 Workbench rehydrate 已完成。若最终审计没有产生行为代码变化，不创建、不推送、不部署 no-op 应用版本。
- 最终验证必须逐页面、逐操作、逐可写 Drawer 检查正确性、耗时、freshness、queue amplification、重试/刷新恢复和无关页面零污染。先完成整轮诊断并登记全部问题，再统一修复、定向验证并至多发布一个必要的候选；禁止发现一个问题就部署一次。
</decisions>

<canonical_refs>
## Canonical References

- `AGENTS.md`
- `ARCHITECTURE.md`
- `docs/app-architecture/pages.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/architecture/module-boundaries/canonical-facts.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/modules/permissions-and-audit/write-entry-inventory.md`
- `docs/modules/read-models/boundary-io.md`
- `docs/modules/runtime-workers/boundary-io.md`
- `docs/modules/domain-events-lifecycle/boundary-io.md`
- `docs/operations/runtime-worker-governance.md`
- `deploy/oa/README.md`
- `.planning/phases/00-cross-page-dependency-baseline/*`
- `.planning/phases/26-oa/26-CONTEXT.md`
- `web/src/app/pageRegistry.tsx`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/read_model_query_gateway.py`
- `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
</canonical_refs>

<specifics>
## Acceptance Specifics

- 覆盖矩阵必须从当前 page registry 和 API/Drawer 源码生成/校验，不沿用 Phase 0 已过时的 no-OA 页面行。
- 成本规则保存、收据编号设置、Workbench 列布局等不应重建业务投影的写入必须有零 refresh 回归测试。
- 银行规则、支付/待找规则等投影语义变化必须用 owner rule version 判断 stale，不以 UI refresh scope 或 mutable snapshot 证明正确。
- 生产验证报告必须按 page_key 和 operation_id 记录可取得的样本数、原始/汇总耗时、HTTP 状态、fresh 收敛时间、jobs created、unrelated dirty deltas 和最终 Audit 状态。样本量不足时不得虚称 p95/p99；超过 3 秒但正确收敛的项标为 `performance_follow_up`。
- 生产验证只能使用授权、可回滚或只读场景；写场景必须沿用现有 controlled operation runner/idempotency/audit/rollback 合同，不临时发明生产脚本。
</specifics>

<deferred>
## Deferred Ideas

- 跨设备或已打开页面的实时推送；只有未来出现明确实时需求时再单独评估。
- 通用 delta projection framework；3 秒优化已从本阶段移出，后续只有在独立性能任务证明现有简单链路不足时才评估。
- 将所有直接查询页面物化为 read model；当前没有需求且会增加维护成本。
</deferred>

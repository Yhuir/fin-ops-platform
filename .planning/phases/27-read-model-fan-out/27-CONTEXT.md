# Phase 27: 按页面访问收敛 Read Model、消除写后全局 Fan-out 并完成全页面生产性能验证 - Context

**Gathered:** 2026-07-22
**Status:** Ready for planning
**Source:** User-approved architecture plus repository/code/runtime inventory

<domain>
## Phase Boundary

本阶段把普通业务写入与派生页面重建解耦：写请求只原子提交 canonical facts、精确 source version 和 audit；页面、可见窗口或 Drawer 真正访问数据时，通过现有 freshness/status/enqueue 边界判断是否需要精确重建当前依赖 scope。阶段覆盖 17 个正式页面、15 个正式 read model、全部 mutating feature API、全部可写 Drawer、非页面资源依赖、旧 lifecycle/fan-out 删除、七类测试、远程 main 发布、正式部署和部署后逐页面逐操作性能验证。

本阶段不新增消息总线、CDC、事件溯源、第二套缓存、每页 SSE、前端事实源或通用增量框架；不把没有正式 read model 的页面机械改造成 read-model 页面；不改变 Phase 26 已冻结的 turnover relation 业务语义和历史修复安全合同。
</domain>

<decisions>
## Locked Decisions

### Correctness

- “访问页面时重建”精确定义为：route enter、focus、hidden→visible 或业务 scope 变化时检查 freshness；只有 stale/missing 的依赖 scope 才重建，fresh 直接读。
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
- SLO：普通写 p95≤500ms/p99≤1s；freshness gate p95≤100ms；已 fresh 页面首屏 p95≤500ms；普通 stale scope 访问到 fresh p95≤1.5s/p99≤3s。
- 任意规模的全历史 rebuild 不承诺 3 秒；它单独验证吞吐、当前 scope 优先、分片并发、可恢复和不阻塞普通保存。

### Frontend And Drawers

- 页面和 Drawer 只调用自己的 query/command owner；不得直接访问 queue、repository 或其他页面 API。
- 同浏览器 BroadcastChannel/domain event 只用于唤醒 freshness check，不携带事实、不作为正确性来源。
- hidden 页面不后台重建；重新可见时检查。两个可见窗口各自检查。
- 只读详情/导出 Drawer 只加载自己的 identity/scope，不重建整页；没有正式 read model 的查询保持现有 owner，不为统一而新增 read model。

### Architecture And Cleanup

- 复用 `READ_MODEL_MANIFEST`、`ReadModelQueryGateway`、`ReadModelRefreshGateway`、scope policy registry、PostgreSQL durable queue、现有 workers、PageRuntime/focus/visibility/BroadcastChannel 模式。
- Workbench 保留 active-generation 原子发布，不机械改成普通 read model。
- 每个垂直切片迁移后立即删除该切片旧 lifecycle、`all` fallback、direct enqueue、operation-barrier wait 和 live fallback；不保留长期新旧双路径或隐藏兼容分支。
- Phase 26 与本阶段重叠的 turnover/workbench 文件只能在其冻结合同基础上修改；不得覆盖、回退或绕过 Phase 26 安全规则。

### Delivery

- 编码前必须通过全量覆盖硬门：17 pages、15 read models、所有 mutating APIs、所有可写 Drawer、所有 lifecycle/enqueue 调用均有 owner/处理/删除/测试映射，unmapped=0。
- 本地所有发布门通过后才允许 commit；commit 后 push 全部变更到远程 `main`；精确 main SHA CI/验证满足部署条件后执行 `./scripts/deploy-oa.sh`。
- 部署后必须逐页面、逐操作、逐可写 Drawer 验证正确性、耗时、freshness、queue amplification 和无关页面零污染。任何失败回到修复→验证→commit→push→redeploy 循环。
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
- 生产性能报告必须按 page_key 和 operation_id 记录 count、p50/p95/p99/max、HTTP 状态、fresh 收敛时间、jobs created、unrelated dirty deltas 和最终 Audit 状态。
- 生产验证只能使用授权、可回滚或只读场景；写场景必须沿用现有 controlled operation runner/idempotency/audit/rollback 合同，不临时发明生产脚本。
</specifics>

<deferred>
## Deferred Ideas

- 跨设备真正实时推送；只有部署后实测 focus/access freshness 不能满足业务需求时再评估。
- 通用 delta projection framework；只有精确 scope SQL/index 优化后仍无法达到 p99 3 秒时再评估。
- 将所有直接查询页面物化为 read model；当前没有需求且会增加维护成本。
</deferred>

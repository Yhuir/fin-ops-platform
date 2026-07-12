# Phase 20: 三组可逆关系写操作的 Fan-out、Worker、Freshness 与 System Audit 生产级闭环 - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Phase Boundary

建立一个可复用、受控、生产级的关系写操作 closure runner，并用三组关系形状执行 confirm → fan-out → worker drain → freshness → affected-page result → System Audit → withdraw → 同等反向证明的可逆闭环。三组关系形状为 bank+invoice、bank+turnover、以及完整 cross-page bank+OA+invoice。阶段只处理测试/验证编排、必要的正式 I/O 端口和被证明已失去 caller 的旧测试/运行链；不复制 17 套页面测试，不把 System Audit 变成写操作，不新增第二套 relation/freshness/queue 事实源，也不扩张到全部 24 个 write-operation profiles。

</domain>

<decisions>
## Implementation Decisions

### Canonical mutation and relation ownership
- 所有 confirm/withdraw 必须经正式 Workbench action API、`WorkbenchRelationCommandService` 与 `WorkbenchWriteUnitOfWork` 写 `app.workbench_pair_relations`；测试不得直接 SQL 写 relation、read model、dirty scope、outbox 或 readiness。
- canonical relation 写入、同事务 refresh intents、audit/idempotency/version contracts 保持现有 owner；Phase 20 不引入 `UnifiedFactSource`、第二 command service 或测试专用生产后门。
- 三组场景使用正式 row identities 和可回滚 test-owned fixtures；不得选择或改写未明确归属的真实业务对象。
- withdraw 必须使用 confirm 返回的 relation/preview/version I/O，并证明恢复到场景捕获的 before state；禁止以 cleanup SQL 冒充撤回。

### Fan-out, worker, and freshness proof
- 复用 `write_operation_e2e_smoke`、`write_operation_slo_audit`、operation impact matrix、PostgreSQL durable queue 和现有 freshness/status contracts；只在这些正式 owner 缺少组合能力时扩展，不新增平行 runner。
- 每次 mutation 以 scenario start/trace/operation profile 过滤真实 outbox/dirty 证据，要求全部 required scope expectations 出现并达到 done；允许合同声明的可选或额外合法 scope，但缺 required scope 必须失败。
- Worker 证明以 PostgreSQL durable queue、dirty scope、readiness/source versions 为事实源；RabbitMQ 仅作为可选 wakeup/transport observation。
- 页面读取必须经过现有 fresh gate；stale/refreshing/failed 不能被旧 payload、Redis 或 Browser fixture 标成 fresh。

### Audit and user-visible result
- 每个 confirm 和 withdraw 收敛后必须调用现有 admin-only read-only `page=app-health-operations` System Audit；Audit 只读、使用单一 `REPEATABLE READ READ ONLY` snapshot，不 enqueue、refresh、repair 或写测试状态。
- closure pass 同时要求 write success、required operation expectations pass、queue drained、target read models fresh、受影响页面/consumer 关键 relation 结果正确、以及新的 System Audit `integrity=pass/freshness=fresh/queue=drained`。
- System Audit 证明当前 App 内部 snapshot，不扩大为外部 bank/OA/invoice/ETC completeness；external unknown 不阻塞本阶段内部 closure。
- Browser/API 验证按 affected-page matrix 复用 consumer assertions，不做 17×operation；relation non-consumer 保持 not-applicable/isolation 证明。

### Legacy removal and production safety
- 对现有 write smoke、scenario discovery、relation fan-out fixtures、旧 no-OA/legacy action path、直接 relation service 写入和测试专用伪 fresh helper做 whole-repo caller/text scan。
- 只有无正式 production/test owner、与新 closure runner 重复或绕过 canonical/queue/freshness/Audit owner 的路径才删除；保留的 migration/audit/runbook adapter必须明确 non-hot-path owner、I/O 和删除条件。
- 禁止通过 compatibility fallback、隐藏 direct SQL、mock-only success、宽松 skip/retry、手工 mark-fresh 或直接 read model mutation让场景变绿。
- 真实 staging/production apply 必须走现有 auth、approval ticket、bounded scenario 和 dry-run/preflight；代码实现与 deterministic/disposable-PostgreSQL验证可以自动执行，任何真实业务 mutation 必须使用已批准且 test-owned 的可逆对象。

### the agent's Discretion
- 在不改变业务合同的前提下，决定 closure result DTO 的最小新增字段、场景 JSON 的组合方式、测试 helper 放置位置和三组场景的数据构造。
- 优先删除重复 orchestration 并扩展现有 runner；只有现有函数职责已明显越界时才提取单一高内聚 helper。

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/src/fin_ops_platform/tools/write_operation_e2e_smoke.py` 已拥有受控 auth/approval、scenario schema、mutating HTTP steps、post API probes 和 write-operation SLO wait。
- `backend/src/fin_ops_platform/tools/write_operation_slo_audit.py` 已登记 24 个 operation profiles、117 个 required/optional scope expectations，并支持 `--since` 因果时间窗。
- `docs/dev/write-operation-impact-matrix.json` 与 `tests/test_write_operation_impact_matrix.py` 已把 operation、source/target pages、canonical relation sources、read models 和 production gate policy机械绑定。
- `OperationsAuditService -> PostgresOperationsAuditRepository.audit_system(...)` 已提供唯一 System Audit owner和单一只读 snapshot。
- `WorkbenchRelationCommandService`、`WorkbenchWriteUnitOfWork`、`RuntimeQueueReadModelRefreshWriter` 和 scope policy registry 已是正式 mutation/fan-out owner。
- 现有 Playwright relation fan-out specs 已覆盖 bank details、pending invoice、input/output invoice、OA pending、cost 和 tax isolation，可复用页面结果断言而不是复制业务逻辑。

### Established Patterns
- Workbench 使用 active generation 原子发布；普通 read model 使用 manifest、durable dirty/outbox、worker、freshness/status/query gateway。
- confirm/withdraw 前端只等待操作级 `workbench_relation` barrier；`workbench` 与跨页 read models 后台追赶，由 cross-page SLO/System Audit验收。
- 生产写 smoke 默认 dry-run，apply 必须显式 auth、PostgreSQL URL、scenario 和 approval reference；零样本、缺 scope、HTML shell、write failure 或 timeout均 fail closed。
- Audit、runtime observation 和 external evidence 是独立 evidence planes；Phase 20只把 mutation结果与内部 System Audit组合，不污染任一 owner。

### Integration Points
- CLI/scenario load/run/report：`write_operation_e2e_smoke.py`。
- Operation expectation selection/evaluation：`write_operation_slo_audit.py`。
- Safe scenario discovery/policy：`write_operation_scenario_discovery.py`。
- System Audit service/repository：`operations_audit_service.py`、`services/postgres_repositories/operations_audit.py`。
- Relation mutation：Workbench action routes/facade、`workbench_relation_command_service.py`、Workbench UoW/relation repository。
- Deterministic Browser consumer proof：`web/e2e/*relation-fanout*.spec.ts` 与共享 Workbench flow fixtures。

</code_context>

<specifics>
## Specific Ideas

- 用户要求完整生产级方案，但禁止过度设计；完成三组可逆关系场景后停止，不扩展成 17×operation。
- 用户要求模块化、清晰 I/O、禁止污染 I/O，并要求全量识别和删除会污染新链路的旧逻辑。
- “完美闭环”意味着 confirm 与 withdraw 都必须形成新的因果证据和新的 System Audit ID，不能引用操作前或历史绿色报告。

</specifics>

<deferred>
## Deferred Ideas

- 其余 21 个非本阶段 write-operation profile 的真实基础设施认证。
- 外部 bank/OA/invoice/ETC complete-snapshot evidence 注册与来源真实性证明。
- 17 个页面乘以全部写操作的笛卡尔 Browser 套件。

</deferred>

# Phase 19: 全页面 Audit 证明、跨页关系一致性、readiness 语义与旧链路移除 - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning
**Source:** 用户确认的主控目标 + 当前 `main` 代码与长期文档

<domain>
## Phase Boundary

本阶段建立能够机械证明所有已注册页面 App 内部数据、关键展示字段、共享关系和页面消费关系完整正确的统一 Audit 合同；统一 read model current-effective readiness/freshness/queue 语义；原子迁移并删除并行旧 Audit runtime 链路；最后通过受控发布和生产只读证据闭环。

Audit 只负责只读证明。数据 refresh、rebuild 和 repair 仍由现有正式 gateway、durable queue、worker 和 repository owner 负责。

</domain>

<decisions>
## Implementation Decisions

### 证明边界

- `Audit 通过` 必须分别报告 `integrity`、`freshness`、`queue`、`external` 和证据版本。
- App 内部证明与银行/OA/发票外部来源证明必须分开；缺少外部 control total/watermark/hash 时输出 `external_unknown`，不得宣称端到端完整。
- 所有实际注册页面必须有明确 Audit contract；unknown/unregistered page 必须 fail closed。
- 所有页面 expected set 必须有独立 canonical 依据，不能仅从被审计 projection 推导。
- relation proof 必须证明 canonical relation、共享 relation distribution、每个 consumer page projection 三层双向 equality。
- Workbench active generation 是 consumer proof 的一部分。
- Audit 结果必须绑定当前 audit revision、source/read-model/relation/config/generation 版本；任一相关版本变化后旧绿色结果失效。
- 系统级证明必须使用同一 `REPEATABLE READ READ ONLY` snapshot。

### Readiness 与 queue

- `fan_out_command/all` 不是可查询物化父 scope，不保存长期当前页面 readiness。
- 当前 fan-out 失败由 durable dirty scope/outbox/event state 暴露；后续成功和 drain 后自然解除。
- 历史 fan-out parent readiness 只能作为历史诊断，不能成为 current-effective blocker。
- `queryable_parent_aggregate`、active generation 或其他真实可查询 parent 继续要求 readiness。
- App Status、Audit、operation barrier 和 SLO smoke 必须复用同一 manifest policy。
- 禁止直接 SQL mark-fresh。

### 架构与复杂度

- 保持 route → service → proof/repository 的单向依赖。
- `server.py` 只做权限、参数和 HTTP 映射；业务编排在 service；SQL 在 repository/proof query owner。
- 优先拆分现有 2400 行 `page_business_audit.py` 的真实职责，不建立插件系统、factory、通用 DSL 或第二套 registry。
- 复用现有 `read_only_audit_snapshot`、`evaluate_audit_issues`、read model manifest、scope policy、refresh gateway、durable queue 和 Workbench active generation。
- 迁移完成后删除旧 runtime 路径，不保留 fallback 或双轨。

### 发布与数据操作

- 本地实现、测试、文档和只读生产调查在本目标范围内。
- 生产发布、生产写入、repair/rebuild、权限变更或不可逆操作前必须提供 dry-run、影响范围、幂等性、回滚和停止条件，并取得针对该操作的明确授权。
- 生产发布只走 `./scripts/deploy-oa.sh`；生产 admin token 只通过 `scripts/with-production-admin-token.sh` 加载。

### the agent's Discretion

- 在不改变以上合同的前提下选择最少的 Python 模块和数据结构名称。
- 基于现有 schema/ports 决定每个页面 consumer edge 的规范读取方式。
- 基于实际依赖图决定受控 rebuild 是否需要及其精确顺序。

</decisions>

<canonical_refs>
## Canonical References

### Repository and architecture

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/index.md`
- `docs/app-architecture/README.md`
- `docs/app-architecture/pages.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/architecture/module-boundaries/README.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/architecture/module-boundaries/canonical-facts.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`

### Directly affected modules

- `docs/modules/permissions-and-audit/boundary-io.md`
- `docs/modules/app-health-operations/boundary-io.md`
- `docs/modules/read-models/boundary-io.md`
- `docs/modules/runtime-workers/boundary-io.md`
- `docs/modules/workbench-relations/boundary-io.md`
- 每个注册页面模块的 `README.md`、`boundary-io.md`、`tests.md`
- `docs/operations/runtime-worker-governance.md`

### Current code owners

- `web/src/app/pageRegistry.tsx`
- `backend/src/fin_ops_platform/services/postgres_repositories/page_business_audit.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/invoice_read_model_audit.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation_audit.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/audit_report.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/read_model_readiness.py`
- `backend/src/fin_ops_platform/services/runtime_monitoring.py`
- `backend/src/fin_ops_platform/services/app_status_overview_service.py`
- `backend/src/fin_ops_platform/tools/read_model_slo_smoke.py`
- `web/src/components/common/PageAuditIcon.tsx`
- `web/src/components/common/PageBusinessAuditIcon.tsx`

</canonical_refs>

<specifics>
## Required Regression Counterexample

建立固定回归：canonical/shared relation 中存在 invoice I 与 bank B；进项发票使用页面包含 I 且金额/版本正确，但遗漏 B 或 relation summary。旧 Audit 可以通过；新 Audit 必须以明确的 missing consumer edge 失败。

</specifics>

<deferred>
## Deferred Ideas

- 不引入与当前证明合同无关的通用数据质量平台。
- 不把 Audit 变成自动写数据或自动 repair 系统。
- 不在缺少外部控制证据时虚构外部完整性结论。

</deferred>

---

*Phase: 19-audit-readiness*
*Context gathered: 2026-07-11*

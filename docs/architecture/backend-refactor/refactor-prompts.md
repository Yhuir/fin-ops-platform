# 后端架构重构 Prompt 库

## 用途

本文档保存 Python-first 后端架构重构过程中经过审查的可执行 prompt。状态、完成度和下一步上下文维护在 `migration-state-log.md`。

## 使用规则

- 执行任何 prompt 前，必须先读取 `migration-state-log.md`。
- 任何执行型 prompt 前，必须先生成并审查 prompt 本身。
- 每次只生成一个 prompt；不得一次性生成所有后续 prompt。
- 下一条 prompt 必须基于上一条 prompt 的 verified 输出、状态机中的下一步上下文和真实代码发现生成。
- prompt 必须包含 Pre-Flight、Allowed Scope、Forbidden Scope、Tests、Post-Flight。
- prompt 必须声明是否影响 Merge Gate 或 Traffic Gate。
- prompt 执行后必须更新 `migration-state-log.md`。
- prompt 执行后必须精准更新受执行结果影响的架构文档；这些回写是下一条 prompt 的输入事实源，不是可选总结。
- 如果执行后没有完成状态机和相关文档回写，不得生成或执行下一条 prompt。
- prompt 执行完成后的最终回复必须告诉用户下一步建议做什么。
- 未经用户确认，不得把 prompt 标记为 `verified`。
- 不得记录 DB password、JWT secret、OA token、cookie 实值或生产 URL。
- 后续 prompt 必须遵守 Macro-Inventory 与 Micro-JIT-Planning：先全局只读文件级分拣，再按单模块准时制深挖；不得一次性生成所有模块的详细设计或执行 prompt。

Post-Flight 必须写明：

- 本 prompt 最终状态。
- 变更文件。
- 验证命令和结果。
- 新发现的架构事实、风险和阻断。
- 已更新哪些长期文档。
- 下一条 prompt 生成或执行前必须读取的上下文。

## PF-P000 - Fresh Documentation Baseline

状态：`verified`

### 目标

建立 fresh 的 Python-only 后端架构重构文档体系，移除旧 Axum/PostgreSQL 和全量语言替换方向，不修改业务代码。

### Prompt

```text
Role: 你是一位精通 Python 后端架构、Clean Architecture、Read Model/CQRS、Redis/RabbitMQ/PostgreSQL 边界和技术文档治理的架构负责人。

Context:
用户要求从 fresh 开始制定新的后端架构重构计划。新计划只做 Python 后端内部架构模块化重构，不把 Python 后端换成其他语言，也不为热点路径创建新语言后端。

Pre-Flight:
读取：
- README.md
- ARCHITECTURE.md
- AGENTS.md
- docs/index.md
- docs/architecture/index.md
- docs/architecture/persistence-and-read-models.md
- docs/architecture/system-overview.md
- docs/architecture/deployment.md
- backend/src/fin_ops_platform/app/
- backend/src/fin_ops_platform/services/
- tests/

Allowed Scope:
- 删除或改写 docs/architecture/backend-refactor/ 下旧 Axum/PostgreSQL/语言替换文档。
- 删除 docs/exec-plans/active/backend-axum-postgres-refactor.md。
- 新增 Python-first 架构重构文档。
- 更新 docs/index.md、docs/architecture/index.md、docs/exec-plans/active/README.md。

Forbidden Scope:
- 不修改 Python 业务代码。
- 不创建 backend-go。
- 不创建任何其他语言的新后端项目。
- 不修改 Nginx、Vite、部署配置或生产配置。
- 不执行 Traffic Gate。

Tests:
- git diff --check。
- 确认 backend-go 不存在。
- 确认 backend-refactor 目录只保留新方向文档。
- 搜索 Axum、Rust、NATS、SQLx、语言替换、新语言后端等旧方向词，确保只出现在非目标或已移除语境。

Post-Flight:
- 更新 migration-state-log.md。
- 记录变更文件、架构决策、验证命令和结果。
- 状态只能到 implemented，等待用户确认后才能 verified。
```

### 验收标准

- `docs/architecture/backend-refactor/README.md` 是新计划入口。
- `target-architecture.md` 明确 Python-first，不创建新语言后端。
- `module-refactor-plan.md` 明确模块职责和推进顺序。
- `runtime-call-chain.md` 明确静态和动态调用链要求。
- `read-model-and-external-services.md` 明确外部服务模块化和 read model 契约。
- `migration-roadmap.md` 明确分阶段路线。
- `ai-execution-rules.md` 明确 AI 执行规则。
- `migration-state-log.md` 建立 fresh 状态机。
- 本文档建立 fresh prompt 库。
- 旧 Axum 执行计划已删除。

## PF-P001 - Architecture Inventory / Dynamic Call Chain Discovery

状态：`verified`

### 目标

执行 Macro-Inventory，全局只读扫描当前 Python 后端，生成 `architecture-inventory.md`，为后续 Micro-JIT 单模块深挖提供事实输入。

### Prompt

```text
Role: 你是一位精通 Python 遗留系统重构、Clean Architecture、CQRS/Read Model、PostgreSQL/Redis/RabbitMQ 边界和大型代码库盘点的架构负责人。

Context:
当前仓库正在执行 Python-first 后端架构模块化重构。PF-P000 已 verified。当前阶段只能做 Macro-Inventory：全局只读文件级分拣、API ownership、file ownership、静态调用链、动态运行时序和风险清单。不得修改业务代码，不得开始任何单模块 Micro-JIT 重构。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/index.md
- docs/architecture/backend-refactor/README.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/architecture/backend-refactor/module-refactor-plan.md
- docs/architecture/backend-refactor/runtime-call-chain.md
- docs/architecture/backend-refactor/read-model-and-external-services.md
- docs/architecture/backend-refactor/migration-roadmap.md
- docs/architecture/backend-refactor/ai-execution-rules.md

必须扫描：
- backend/src/fin_ops_platform/app/**/*.py
- backend/src/fin_ops_platform/services/**/*.py
- backend/src/fin_ops_platform/postgres/**/*.sql
- backend/src/fin_ops_platform/tools/**/*.py
- backend/src/fin_ops_platform/app/worker.py
- tests/**/*.py
- docs/product-specs/**/*.md
- docs/dev/**/*.md

工具要求：
- 优先使用 CodeGraph 做结构化上下文、调用者/被调用者和影响半径分析。
- 使用 `rg --files`、`rg`、`wc -c` 补齐全量文件扫描、API path 字符串、event type、Redis key、RabbitMQ/outbox、read model table 和测试覆盖。
- 不得只依赖通配符或文件名推断模块边界；关键结论必须回链到代码文件、测试或文档。

Allowed Scope:
- 新增 `docs/architecture/backend-refactor/architecture-inventory.md`。
- 根据扫描结果，只允许小范围修订以下文档中的事实性归属和下一步上下文：
  - docs/architecture/backend-refactor/module-refactor-plan.md
  - docs/architecture/backend-refactor/runtime-call-chain.md
  - docs/architecture/backend-refactor/migration-state-log.md
- 可在 `architecture-inventory.md` 中记录后续应补的模块文档，但本轮不创建每个模块的详细重构执行计划。

Forbidden Scope:
- 不修改 Python 业务代码。
- 不修改 tests。
- 不修改数据库 migration。
- 不修改前端、Nginx、Vite、部署配置或生产配置。
- 不创建 backend-go，不创建任何其他语言的新后端。
- 不执行 Micro-JIT 单模块重构。
- 不一次性写所有模块的最终详细设计。
- 不执行 Merge Gate 或 Traffic Gate。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产 URL。

Required Inventory Output:
`architecture-inventory.md` 必须至少包含以下章节：

1. Executive Summary
   - 本次扫描范围。
   - 发现的模块遗漏、错归属、高风险耦合。
   - 后续 Micro-JIT 推荐顺序。

2. API Path Ownership
   - 每个 API path / route pattern。
   - HTTP method。
   - handler 位置。
   - 目标候选模块。
   - 测试文件。
   - 未归属或重复归属标记。

3. File Ownership
   - 每个 app/service/repository/worker/tool/test 文件。
   - 文件大小。
   - 当前职责摘要。
   - 目标候选模块或 platform。
   - 是否超过 20KB。
   - 是否为高风险文件。

4. Target Candidate Modules
   至少覆盖：
   - Platform / Infrastructure
   - Workbench
   - Workbench Matching Engine，候选独立模块
   - Turnover Ledger
   - Batch Accounting
   - Bankdetail
   - Invoices
   - Imports
   - Tax / Cost / ETC
   - Search / Pending Query
   - Ops / Runtime

5. Workbench Deep Inventory
   必须显式扫描并归属：
   - services/workbench_candidate_grouping.py
   - services/workbench_sql_projection.py
   - services/workbench_query_service.py
   - services/workbench_free_matching_engine.py
   - services/workbench_matching_rules.py
   - services/live_workbench_service.py
   - services/workbench_exception_case_service.py
   - services/workbench_special_pair_rule_service.py
   - services/workbench_matching_orchestrator.py
   - services/workbench_exception_application_service.py
   - services/workbench_pair_relation_service.py
   - services/workbench_special_rule_detectors.py
   - services/workbench_exception_projection.py
   - services/workbench_candidate_match_service.py

6. Workbench Matching Engine Candidate Evaluation
   必须覆盖：
   - workbench_candidate_grouping.py
   - workbench_free_matching_engine.py
   - workbench_matching_rules.py
   - workbench_matching_orchestrator.py
   - workbench_candidate_match_service.py
   - workbench_amount_check_service.py
   结论必须回答：
   - 是否有稳定输入。
   - 是否有稳定输出。
   - 是否直接拥有 facts 写入。
   - 是否直接拥有 Workbench read model active generation 发布权。
   - 是否与 Workbench 写操作共享不可拆 transaction。
   - 是否建议升格为独立顶层模块，或暂时作为 Workbench 内部子域。

7. Turnover Ledger Inventory
   必须覆盖：
   - /api/turnover-ledger*
   - app/routes_turnover_ledger.py
   - app/server.py 中 `_handle_api_turnover_ledger*`
   - turnover_ledger_service.py
   - turnover_relation_service.py
   - turnover_ledger_extra_service.py
   - turnover_ledger_export_service.py
   - turnover_relation_changed
   - tests/test_turnover_ledger_api.py
   - tests/test_turnover_ledger_service.py
   - tests/test_turnover_relation_service.py
   - tests/test_turnover_ledger_export_service.py
   - tests/test_workbench_turnover_grouping.py

8. Batch Accounting Inventory
   必须覆盖：
   - /api/batch-accounting*
   - app/server.py 中 `_handle_api_batch_accounting*`
   - BatchAccountingService
   - load_batch_accounting_workbench_payload
   - batch_accounting_relation_changed
   - tests/test_batch_accounting_api.py
   - tests/test_workbench_v2_api.py 中 batch accounting 相关用例
   - tests/test_workbench_persist_scheduler.py
   - tests/test_derived_data_lifecycle_service.py

9. External Dependency Matrix
   对每个模块列出：
   - PostgreSQL facts。
   - PostgreSQL read model。
   - Redis。
   - RabbitMQ/outbox/durable queue。
   - OA Mongo。
   - MinIO/S3。
   - OA Auth/session。
   - local state / pickle / legacy snapshot。

10. Runtime Sequence Candidates
    只输出全局候选，不做最终模块详设：
    - 高频读链路。
    - 写请求 transaction/outbox/dirty scope 链路。
    - worker refresh 链路。
    - SSE/App Health 链路。
    - 可能同步全量重算或 fallback 的链路。

11. Risk Register
    至少包含：
    - orphan files。
    - duplicate ownership。
    - direct cross-module imports。
    - legacy full snapshot / pickle / local state。
    - request path synchronous rebuild。
    - read model stale/freshness 风险。
    - Redis/RabbitMQ 直接散落调用。
    - 大文件拆分风险。

12. Recommended Micro-JIT Order
    给出下一批模块深挖顺序和理由，但不得生成这些模块的执行 prompt。

Module Boundary Rules:
- 一个 API path 只能归属一个模块。
- 一个文件可以标记 secondary influence，但必须有唯一 primary owner。
- 独立模块必须至少具备清晰 API/usecase 边界、独立 facts/event/read model ownership 或稳定输入输出。
- 只有内部算法、无独立 API、无独立 facts ownership 的区域，优先作为所属模块子域。
- Turnover Ledger 和 Batch Accounting 默认作为独立模块审计；如发现反证，必须列出代码事实。
- Workbench Matching Engine 默认作为候选独立模块审计；是否升格必须由证据决定。

Tests / Verification:
- `git diff --check`
- `test ! -e backend-go`
- `test -f docs/architecture/backend-refactor/architecture-inventory.md`
- `rg -n "Turnover Ledger|Batch Accounting|Workbench Matching Engine|API Path Ownership|File Ownership|External Dependency Matrix|Risk Register" docs/architecture/backend-refactor/architecture-inventory.md`
- `rg -n "Go Fiber|backend-go|Axum|Rust|新语言后端|语言替换|Hot Path" docs/architecture/backend-refactor`，确认这些词只出现在非目标、禁止项或旧方向说明中。
- 不运行 Python unit tests，除非你实际修改了业务代码；本轮禁止修改业务代码。

Post-Flight:
- 更新 `migration-state-log.md`：
  - 将 PF-P001 状态设为 implemented。
  - 记录生成的 `architecture-inventory.md`。
  - 记录验证命令和结果。
  - 记录模块遗漏/错归属审计摘要。
  - 记录下一条建议 prompt：基于 `architecture-inventory.md` 生成第一个 Micro-JIT 单模块深挖 prompt。
- 不得把 PF-P001 标记为 verified；必须等待用户确认。
```

### Gate Scope

- Merge Gate：不涉及。本 prompt 只生成文档盘点，不 merge。
- Traffic Gate：不涉及。本 prompt 不修改任何生产路径、部署或路由。
- Micro-JIT：不涉及。本 prompt 只允许 Macro-Inventory。

### 审查结论

- 范围符合当前 Python-first 重构方向。
- Prompt 明确要求读取状态机和架构文档，能防止旧 Go/语言替换方向复活。
- Prompt 明确禁止业务代码、测试、migration、部署配置变更，符合 Macro-Inventory 只读原则。
- Prompt 明确要求生成 `architecture-inventory.md`，并覆盖 Turnover Ledger、Batch Accounting、Workbench 大文件和 Workbench Matching Engine 候选模块评估。
- Prompt 明确要求后续 Micro-JIT 只能基于本次产物继续，符合“一次只生成一个 prompt”的状态机规则。

## PF-P001-C1 - Production Coverage Correction

状态：`verified`

### 目标

对 PF-P001 的 Macro-Inventory 做生产级覆盖面修正，补齐非 `services/` 核心文件、Shared Domain、App Entry、Auth、Migration Runtime、Backfill Jobs 和巨型测试门禁文件的 Primary Owner。

### Prompt

```text
/goal
生成并执行 PF-P001 的生产级覆盖面修正，不改业务代码，不标记 verified。最终目标是让 architecture-inventory.md 明确覆盖 domain/、app/main.py、app/auth.py、PostgreSQL migration runtime、backfill jobs 和巨型测试文件，并为每个补录项指定 Primary Owner。

Role: 你是一位精通 Python 遗留系统重构、Clean Architecture、平台边界、安全鉴权、数据库迁移和测试门禁治理的后端架构负责人。

Context:
当前仓库正在执行 Python-first 后端架构模块化重构。PF-P001 已执行但尚未 verified。用户指出 PF-P001 对非 services/ 目录覆盖不足，要求不要做最小修正，而是做生产级覆盖面修正。

Pre-Flight:
必须读取：
- AGENTS.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/architecture-inventory.md
- docs/architecture/backend-refactor/module-refactor-plan.md
- docs/architecture/backend-refactor/runtime-call-chain.md

必须扫描：
- backend/src/fin_ops_platform/domain/*.py
- backend/src/fin_ops_platform/app/*.py
- backend/src/fin_ops_platform/postgres/*.py
- backend/src/fin_ops_platform/postgres/migrations/*.sql
- tests/*.py

Allowed Scope:
- 更新 docs/architecture/backend-refactor/architecture-inventory.md。
- 更新 docs/architecture/backend-refactor/migration-state-log.md。
- 更新 docs/architecture/backend-refactor/refactor-prompts.md，记录本 prompt。

Required Corrections:
1. 将 domain/ 下全部文件补入清单，并明确 Primary Owner 为 Platform / Shared Domain。
2. 将 app/main.py 补入清单，并明确 Primary Owner 为 Platform / App Entry。
3. 将 app/auth.py 补入清单，并明确 Primary Owner 为 Platform / Auth。
4. 将 app/bank_account_balance_backfill.py 和 app/bank_detail_backfill.py 补入清单，并明确 Primary Owner 为 Platform / Ops Backfill，Bankdetail 为 Secondary influence。
5. 将 postgres/migrate.py、postgres/__main__.py、postgres/__init__.py 补入清单，并明确 Primary Owner 为 Platform / DB Migration Runtime。
6. 将以下巨型测试文件补入测试门禁热点，并明确 Primary Owner：
   - tests/test_workbench_v2_api.py -> Workbench
   - tests/test_etc_backend.py -> Tax / Cost / ETC
   - tests/test_workbench_sql_runtime.py -> Workbench
7. 生产级补强：同时列出至少 50KB 以上测试热点文件，作为后续 Merge Gate 输入。
8. 在 Risk Register 中补充 Shared Domain、Auth、Migration Runtime、Backfill Jobs、巨型测试门禁遗漏风险。
9. 在 Recommended Micro-JIT Order 中把 PF-P002 的范围扩展为 Platform / Ops / Runtime Boundary + Shared Domain + App Entry + Auth + Migration Runtime + Backfill Jobs。

Forbidden Scope:
- 不修改 Python 业务代码。
- 不修改 tests。
- 不修改 SQL migration。
- 不修改部署配置。
- 不创建新语言后端。
- 不执行 Merge Gate 或 Traffic Gate。
- 不标记 PF-P001 verified。

Tests:
- git diff --check
- rg -n "domain/models.py|domain/enums.py|app/main.py|app/auth.py|postgres/migrate.py|test_workbench_v2_api.py|test_etc_backend.py|test_workbench_sql_runtime.py" docs/architecture/backend-refactor/architecture-inventory.md
- rg -n "PF-P001-C1|Production Coverage Correction|omission correction|Shared Domain|Platform / Auth|DB Migration Runtime|测试门禁热点" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/architecture-inventory.md

Post-Flight:
- 将 PF-P001-C1 状态记录为 implemented。
- 记录验证命令和结果。
- 保持 PF-P001 / PF-P001-C1 等待用户审查确认，不得 verified。
- 最终回复告诉用户下一步：审查 architecture-inventory.md，确认后标记 PF-P001 verified，再生成 PF-P002。
```

### 执行结论

- 已按 prompt 执行，更新 `architecture-inventory.md`。
- 已补齐 Shared Domain、App Entry、Auth、DB Migration Runtime、Ops Backfill 和测试门禁热点。
- 未修改业务代码、测试、SQL migration 或部署配置。
- 用户已确认 PF-P001 verified；本修正作为 PF-P001 的 verified 范围一并锁定。

## PF-P002 - Platform / Ops / Runtime Boundary Deep Dive

状态：`verified`

### 目标

基于 PF-P001 verified 的 `architecture-inventory.md`，对 Platform / Ops / Runtime Boundary 做第一个 Micro-JIT 深挖。PF-P002 只做代码事实审计、边界图、风险清单和后续可执行重构计划，不修改业务代码。

本 prompt 已重写为生产级覆盖面版本。它不得只扫描 `runtime_*` 和 `state_store.py`，必须覆盖 DB 事务核心、settings/access control、OA identity/projection、shadow/dual state store、ops tools、observability 和基建测试门禁。

### Prompt

```text
/goal
执行 PF-P002 - Platform / Ops / Runtime Boundary Deep Dive。目标是在不修改业务代码的前提下，审计并锁定 Platform/Ops/Runtime 底座边界，产出 platform-runtime-boundary-audit.md，作为后续所有业务模块 Micro-JIT 的底座事实源。

Role:
你是一位精通 Python 遗留系统重构、Clean Architecture、运行时平台边界、安全鉴权、PostgreSQL outbox/dirty scope、Redis/RabbitMQ adapter、worker runtime 和生产可观测性的后端架构负责人。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P001 已 verified，并已通过 PF-P001-C1 生产级覆盖面修正。下一步只能深挖 Platform / Ops / Runtime Boundary，不能开始 Workbench、Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 等业务模块重构。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/architecture-inventory.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/architecture/backend-refactor/module-refactor-plan.md
- docs/architecture/backend-refactor/runtime-call-chain.md
- docs/architecture/backend-refactor/read-model-and-external-services.md
- docs/architecture/backend-refactor/ai-execution-rules.md
- docs/dev/runtime-bootstrap.md
- docs/dev/runtime-infrastructure.md
- docs/dev/backend.md
- docs/product-specs/settings-and-access-control.md
- docs/product-specs/oa-integration.md
- docs/product-specs/app-health-and-background-jobs.md

必须扫描：
- backend/src/fin_ops_platform/app/main.py
- backend/src/fin_ops_platform/app/auth.py
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/app/worker.py
- backend/src/fin_ops_platform/app/rabbitmq_dispatcher.py
- backend/src/fin_ops_platform/app/rabbitmq_topology.py
- backend/src/fin_ops_platform/app/oa_attachment_audit.py
- backend/src/fin_ops_platform/app/*_backfill.py
- backend/src/fin_ops_platform/domain/*.py
- backend/src/fin_ops_platform/postgres/*.py
- backend/src/fin_ops_platform/postgres/migrations/*.sql
- backend/src/fin_ops_platform/services/postgres_connection.py
- backend/src/fin_ops_platform/services/postgres_repositories/core.py
- backend/src/fin_ops_platform/services/postgres_repositories/oa_projection.py
- backend/src/fin_ops_platform/services/runtime_*.py
- backend/src/fin_ops_platform/services/state_store.py
- backend/src/fin_ops_platform/services/postgres_state_store.py
- backend/src/fin_ops_platform/services/runtime_bootstrap.py
- backend/src/fin_ops_platform/services/state_store_factory.py
- backend/src/fin_ops_platform/services/state_store_protocol.py
- backend/src/fin_ops_platform/services/shadow_state_store.py
- backend/src/fin_ops_platform/services/dual_state_store.py
- backend/src/fin_ops_platform/services/shadow_read_rehearsal.py
- backend/src/fin_ops_platform/services/state_store_diff.py
- backend/src/fin_ops_platform/services/cutover_preflight.py
- backend/src/fin_ops_platform/services/runtime_queue.py
- backend/src/fin_ops_platform/services/runtime_redis.py
- backend/src/fin_ops_platform/services/rabbitmq_runtime.py
- backend/src/fin_ops_platform/services/background_job_service.py
- backend/src/fin_ops_platform/services/app_health_service.py
- backend/src/fin_ops_platform/services/app_health_alert_service.py
- backend/src/fin_ops_platform/services/runtime_monitoring.py
- backend/src/fin_ops_platform/services/api_performance_metrics.py
- backend/src/fin_ops_platform/services/audit.py
- backend/src/fin_ops_platform/services/operations_dashboard.py
- backend/src/fin_ops_platform/services/app_settings_service.py
- backend/src/fin_ops_platform/services/access_control_service.py
- backend/src/fin_ops_platform/services/settings_data_reset_service.py
- backend/src/fin_ops_platform/services/mongo_oa_adapter.py
- backend/src/fin_ops_platform/services/oa_identity_service.py
- backend/src/fin_ops_platform/services/oa_role_sync_service.py
- backend/src/fin_ops_platform/services/oa_projection_sync.py
- backend/src/fin_ops_platform/services/object_storage.py
- backend/src/fin_ops_platform/tools/**/*.py
- tests/test_auth*.py
- tests/test_session*.py
- tests/test_runtime*.py
- tests/test_runtime_infrastructure*.py
- tests/test_state_store.py
- tests/test_shadow_*.py
- tests/test_dual_state_store.py
- tests/test_state_store_diff.py
- tests/test_postgres_state_store_integration.py
- tests/test_postgres_connection.py
- tests/test_postgres_repositories_core.py
- tests/test_mongo_oa_adapter.py
- tests/test_postgres_migrations.py
- tests/test_app_settings_service.py
- tests/test_settings_data_reset_service.py
- tests/test_oa_identity_service.py
- tests/test_oa_role_sync_service.py
- tests/test_oa_projection_sql_runtime.py
- tests/test_app_health*.py
- tests/test_audit_service.py
- tests/test_api_performance_metrics.py

工具要求：
- 优先使用 CodeGraph 做结构化调用链、callers/callees、impact 分析。
- 使用 `rg` 补齐 import、字符串、env var、Redis key、RabbitMQ/outbox、pickle/local state、auth cookie/header、bootstrap mode 的字面扫描。
- 对每个关键结论必须给出代码文件或测试文件证据。

Allowed Scope:
- 新增 `docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`。
- 必要时更新：
  - docs/architecture/backend-refactor/runtime-call-chain.md
  - docs/architecture/backend-refactor/read-model-and-external-services.md
  - docs/architecture/backend-refactor/module-refactor-plan.md
  - docs/architecture/backend-refactor/migration-state-log.md
  - docs/architecture/backend-refactor/refactor-prompts.md
- 只允许文档和审计结果更新。

Forbidden Scope:
- 不修改 Python 业务代码。
- 不修改 tests。
- 不修改 SQL migration。
- 不修改前端、Nginx、Vite、Caddy、部署配置或生产配置。
- 不创建新语言后端。
- 不执行 Workbench、Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 业务模块迁移。
- 不执行 Merge Gate 或 Traffic Gate。
- 不把 PF-P002 标记为 verified，必须等待用户确认。

Required Audit Output:
`platform-runtime-boundary-audit.md` 必须至少包含以下章节：

1. Executive Summary
   - 本次审计范围。
   - Platform/Ops/Runtime 当前边界判断。
   - 必须先解决的阻断和后续可执行重构顺序。

2. File Ownership and Boundary Map
   - Shared Domain、App Entry、Auth、DB Connection、DB Transaction / Repository Core、DB Migration Runtime、Ops Backfill、Ops Tools、Settings、Access Control、OA Identity、OA Role Sync、OA Projection、Runtime Queue、Redis Adapter、RabbitMQ Transport、State Store、Shadow/Dual State Store、Worker Runtime、App Health、Observability、Audit、Performance Metrics、OA Adapter、Object Storage。
   - 每个文件的 Primary Owner、允许依赖、禁止依赖。

3. DB Transaction / Repository Core Boundary
   必须审计：
   - `postgres_connection.py`
   - `postgres_repositories/core.py`
   - `runtime_queue.py`
   - `postgres/migrate.py`
   输出：
   - PostgreSQL connection / pool / context 如何进入 API、worker 和 tests。
   - transaction helper、repository helper、outbox/dirty scope 写入是否可以被模块统一复用。
   - 写操作同事务提交 facts、audit、dirty scope、outbox 的当前支持点和缺口。
   - 禁止业务模块私自创建 connection、绕过 transaction helper 或手写不可追踪 transaction 的规则。

4. Settings / Access Control Boundary
   必须审计：
   - `app_settings_service.py`
   - `access_control_service.py`
   - `settings_data_reset_service.py`
   - settings/access-control 相关 tests。
   输出：
   - settings、feature/config、access control 的 primary owner。
   - auth context 与 access control 的调用关系。
   - 数据重置/配置下发是否属于 Ops 边界，是否需要独立测试门禁。

5. OA Identity / Role / Projection Boundary
   必须审计：
   - `oa_identity_service.py`
   - `oa_role_sync_service.py`
   - `oa_projection_sync.py`
   - `postgres_repositories/oa_projection.py`
   - `mongo_oa_adapter.py`
   输出：
   - OA identity / role / projection 如何成为 auth context 的事实来源。
   - OA Mongo 只读边界和 PostgreSQL OA projection 边界。
   - 角色同步、用户身份缓存、权限判断之间的依赖方向。

6. Redis / RabbitMQ Direct Dependency Audit
   必须输出两张表：
   - 允许的 platform adapter 调用：例如集中在 `runtime_redis.py`、`runtime_queue.py`、`rabbitmq_runtime.py`、`app/rabbitmq_dispatcher.py`、`app/rabbitmq_topology.py` 等边界内的调用。
   - 禁止或可疑的业务层直接调用：任何业务 service、handler、repository 直接 import Redis/RabbitMQ client、直接操作 transport、绕过 outbox/queue repository 的调用。
   如果没有确认违规，也必须写明“未发现已确认违规”，并列出扫描模式和证据。

7. Legacy State / Snapshot / Pickle Production Path Audit
   必须审计：
   - `state_store.py`
   - `postgres_state_store.py`
   - `runtime_bootstrap.py`
   - `state_store_factory.py`
   - `state_store_protocol.py`
   - `shadow_state_store.py`
   - `dual_state_store.py`
   - `shadow_read_rehearsal.py`
   - `state_store_diff.py`
   - `cutover_preflight.py`
   - `app/server.py`
   - `app/worker.py`
   输出：
   - production request path 是否仍可能调用 local state、full snapshot、pickle、legacy fallback。
   - production worker path 是否仍可能调用 local state、full snapshot、pickle、legacy fallback。
   - shadow/dual/diff/rehearsal 机制是否可能进入 production 默认路径。
   - shadow 状态机安全退出机制和允许使用场景。
   - 明确允许路径：test、migration、shadow、legacy explicit mode。
   - 明确禁止路径：production request/worker 默认路径。

8. Auth Context Propagation Audit
   必须审计：
   - `app/auth.py`。
   - `/api/session/me`。
   - `access_control_service.py`。
   - `oa_identity_service.py`。
   - `oa_role_sync_service.py`。
   - server/router handler 如何获取 user context。
   - usecase/service 是否收到统一 auth context，是否读取 raw request/cookie/token。
   输出：
   - 当前 auth context 传导链。
   - 统一身份上下文接口建议。
   - 禁止模块私自解析 token/cookie 的规则。
   - 必须运行或补齐的 auth/session 测试门禁。

9. Shared Domain / App Entry / DB Migration Runtime / Backfill / Ops Tools Boundary
   必须审计：
   - `domain/models.py`、`domain/enums.py` 是否保持纯值对象/枚举。
   - `app/main.py` 是否只负责 app entry。
   - `postgres/migrate.py` 是否作为 migration runtime 独立验证。
   - `app/*_backfill.py` 是否需要后续模块 smoke gate。
   - `tools/**/*.py` 是否直接操作 runtime queue、read model convergence、state store、migration 或 production data。

10. Observability / Audit / Performance Metrics Boundary
    必须审计：
    - `app_health_service.py`
    - `app_health_alert_service.py`
    - `runtime_monitoring.py`
    - `api_performance_metrics.py`
    - `audit.py`
    - `background_job_service.py`
    - `operations_dashboard.py`
    输出：
    - App Health、alerts、runtime metrics、API performance metrics、audit events 的 owner 和调用链。
    - 后续模块重构必须暴露哪些指标、日志和审计字段。
    - 哪些可观测性调用允许在业务模块内使用，哪些必须通过 platform port。

11. Runtime Sequence Diagrams
   至少给出 Mermaid sequence diagram：
   - HTTP request -> auth -> handler -> usecase 的平台边界。
   - write request -> transaction -> outbox -> dirty scope 的平台边界。
   - outbox/RabbitMQ/worker -> read model refresh 的平台边界。
   - App Health / SSE / worker heartbeat 的平台边界。
   - DB migration runtime / ops backfill 的平台边界。

12. Test Gate Matrix
   必须列出：
   - auth/session tests。
   - DB connection / transaction / repository core tests。
   - settings/access control tests。
   - OA identity / role / projection tests。
   - runtime queue/outbox tests。
   - Redis/RabbitMQ fake/integration tests。
   - state store / legacy snapshot / shadow / dual / diff tests。
   - PostgreSQL migration runtime tests。
   - ops tools / backfill smoke tests。
   - App Health / worker tests。
   每个测试标明：必跑、条件跑、后续需补。

13. Refactor Readiness and Next Step
   - 列出哪些边界可以直接进入代码重构。
   - 列出哪些边界仍需补测试或补事实。
   - 给出下一条 prompt 建议，但不得生成下一条 prompt。

Mandatory Checks:
- 必须审计 DB connection、transaction helper、repository core、outbox/dirty scope 的统一写边界，并输出当前支持点和缺口。
- 必须审计 settings/access control 和 auth context 的关系，不能只看 `app/auth.py`。
- 必须审计 OA identity / role / projection 的事实来源，明确 OA Mongo 与 PostgreSQL projection 的边界。
- 必须审计所有 Redis/RabbitMQ 直接依赖点，并输出“允许的 platform adapter 调用”和“禁止的业务层直接调用”清单。
- 必须审计 `state_store.py`、`postgres_state_store.py`、`runtime_bootstrap.py`、shadow/dual/diff 相关文件的生产路径，明确 legacy snapshot/local state/pickle 是否还能进入 production request/worker path。
- 必须审计 `app/auth.py` 到 handler/usecase 的 auth context 传导链，明确统一身份上下文接口和测试门禁。
- 必须审计 ops tools、backfill scripts、observability/audit/performance metrics 的平台边界。
- 必须把 prompt 执行后的真实发现回写到 `migration-state-log.md` 和受影响架构文档。

Tests / Verification:
- `git diff --check`
- `test -f docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`
- `rg -n "DB Transaction / Repository Core Boundary|Settings / Access Control Boundary|OA Identity / Role / Projection Boundary|Redis / RabbitMQ Direct Dependency Audit|Legacy State / Snapshot / Pickle Production Path Audit|Auth Context Propagation Audit|Observability / Audit / Performance Metrics Boundary|Test Gate Matrix|Refactor Readiness" docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`
- `rg -n "允许的 platform adapter 调用|禁止或可疑的业务层直接调用|production request path|production worker path|auth context|shadow|dual|DB transaction|OA identity" docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`
- `git diff --name-only` 确认只修改 `docs/architecture/backend-refactor/` 下文档。
- 不运行 Python unit tests，除非你修改了代码；本 prompt 禁止修改代码。

Post-Flight:
- 更新 `migration-state-log.md`：
  - 将 PF-P002 状态设为 implemented。
  - 记录新增或修改文件。
  - 记录验证命令和结果。
  - 记录 DB transaction/core repository、settings/access control、OA identity/projection、Redis/RabbitMQ、legacy state/snapshot、shadow/dual state store、auth context、ops tools、observability/test gates 的审计摘要。
  - 记录下一条建议 prompt，但不得生成下一条 prompt。
- 更新受影响的架构文档，尤其是 runtime-call-chain、read-model-and-external-services 或 module-refactor-plan 中被审计结果改变的事实。
- 最终回复必须告诉用户下一步建议做什么。
- 不得把 PF-P002 标记为 verified；必须等待用户确认。
```

### Gate Scope

- Merge Gate：不涉及。本 prompt 只生成平台边界审计文档，不 merge。
- Traffic Gate：不涉及。本 prompt 不修改部署、网关、auth 实现或 worker 消费方式。
- Micro-JIT：涉及。PF-P002 是第一个 Micro-JIT 深挖 prompt，但只做 Platform/Ops/Runtime 审计，不改代码。

### 审查结论

- 范围符合 `architecture-inventory.md` 推荐顺序。
- 已重写为生产级覆盖面版本，补齐 DB transaction/core repository、settings/access control、OA identity/projection、shadow/dual state store、ops tools、observability 和基建测试门禁。
- 已把 Redis/RabbitMQ 直接依赖、legacy state/snapshot 生产路径、auth context 传导链列为 mandatory checks。
- 已把每次 prompt 执行后回写状态机和受影响架构文档列为 Post-Flight 硬约束。
- 本 prompt 不开始任何业务模块迁移，不执行 Merge Gate 或 Traffic Gate。

### 执行结论

- 已执行 PF-P002，并生成 `platform-runtime-boundary-audit.md`。
- 已更新状态机、运行时调用链文档、外部服务契约入口和本文档状态。
- 未修改 Python 业务代码、tests、SQL migration、前端、网关或部署配置。
- 用户已确认 PF-P002 verified。

## PF-P003 - Platform Runtime Boundary Enforcement / Guard Tests

状态：`verified`

### 目标

基于 PF-P002 verified 的 `platform-runtime-boundary-audit.md`，把平台边界风险转成可执行的 guard tests 和最小平台代码约束。PF-P003 可以改少量 Platform / App Shell / Runtime Boundary 代码和平台测试，但不得开始任何业务模块迁移。

### Prompt

```text
/goal
执行 PF-P003 - Platform Runtime Boundary Enforcement / Guard Tests。

目标：基于 PF-P002 verified 的平台边界审计，在 Python 平台底座内补强机械 guard 和测试门禁。只处理 Platform / Ops / Runtime Boundary，不开始任何业务模块迁移。

Role:
你是一位精通 Python 遗留系统重构、Clean Architecture、运行时安全边界、测试门禁、PostgreSQL transaction/outbox、Auth Context 和生产可观测性的后端架构负责人。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P001 和 PF-P002 均已 verified。PF-P002 已产出 `platform-runtime-boundary-audit.md`，结论是平台边界已有雏形，但缺少机械约束：production storage backend guard、legacy snapshot/full snapshot 禁用、Auth Context 传递契约、Unit of Work / transaction boundary、Redis/RabbitMQ direct import 静态门禁、OA Mongo adapter 业务层隔离门禁、external OA MySQL / `pymysql` 直连门禁、handler / usecase raw SQL 边界门禁。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/dev/backend.md
- docs/dev/runtime-bootstrap.md
- docs/dev/runtime-infrastructure.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/architecture-inventory.md
- docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/architecture/backend-refactor/module-refactor-plan.md
- docs/architecture/backend-refactor/runtime-call-chain.md
- docs/architecture/backend-refactor/read-model-and-external-services.md
- docs/architecture/backend-refactor/ai-execution-rules.md

必须扫描：
- backend/src/fin_ops_platform/app/main.py
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/app/auth.py
- backend/src/fin_ops_platform/app/worker.py
- backend/src/fin_ops_platform/services/runtime_bootstrap.py
- backend/src/fin_ops_platform/services/state_store_factory.py
- backend/src/fin_ops_platform/services/postgres_state_store.py
- backend/src/fin_ops_platform/services/postgres_connection.py
- backend/src/fin_ops_platform/services/runtime_queue.py
- backend/src/fin_ops_platform/services/runtime_redis.py
- backend/src/fin_ops_platform/services/rabbitmq_runtime.py
- backend/src/fin_ops_platform/services/mongo_oa_adapter.py
- backend/src/fin_ops_platform/services/oa_projection_sync.py
- backend/src/fin_ops_platform/services/oa_role_sync_service.py
- backend/src/fin_ops_platform/services/postgres_repositories/oa_projection.py
- backend/src/fin_ops_platform/services/postgres_repositories/core.py
- backend/src/fin_ops_platform/services/api_performance_metrics.py
- tests/test_runtime_bootstrap.py
- tests/test_state_store_factory_preflight.py
- tests/test_app_postgres_mode.py
- tests/test_auth_guard.py
- tests/test_session_api.py
- tests/test_runtime_queue.py
- tests/test_runtime_redis.py
- tests/test_rabbitmq_runtime.py
- tests/test_postgres_connection.py
- tests/test_postgres_repositories_core.py
- tests/test_mongo_oa_adapter.py
- tests/test_oa_projection_sql_runtime.py
- tests/test_worker_oa_sync.py

工具要求：
- 优先使用 CodeGraph 做结构化调用链和影响半径分析。
- 使用 `rg` 扫描直接 import、env var、pickle/full snapshot、Redis/RabbitMQ client、MongoOAAdapter、pymysql、PostgresConnection raw SQL、direct SQL outbox/dirty scope 写入。
- 不得猜测部署环境、DB schema、auth 字段或外部服务行为；不清楚就读取事实源或将状态设为 blocked。

Allowed Scope:
- 允许修改以下平台代码，且必须保持最小 diff：
  - backend/src/fin_ops_platform/app/main.py
  - backend/src/fin_ops_platform/app/server.py
  - backend/src/fin_ops_platform/app/auth.py
  - backend/src/fin_ops_platform/services/runtime_bootstrap.py
  - backend/src/fin_ops_platform/services/state_store_factory.py
  - backend/src/fin_ops_platform/services/postgres_state_store.py
  - backend/src/fin_ops_platform/services/runtime_queue.py
  - backend/src/fin_ops_platform/services/runtime_redis.py
  - backend/src/fin_ops_platform/services/rabbitmq_runtime.py
- 允许新增或修改平台测试：
  - tests/test_platform_runtime_boundary_guards.py
  - tests/test_runtime_bootstrap.py
  - tests/test_state_store_factory_preflight.py
  - tests/test_app_postgres_mode.py
  - tests/test_auth_guard.py
  - tests/test_session_api.py
  - tests/test_runtime_queue.py
  - tests/test_runtime_redis.py
  - tests/test_rabbitmq_runtime.py
- 允许更新：
  - docs/architecture/backend-refactor/migration-state-log.md
  - docs/architecture/backend-refactor/refactor-prompts.md
  - docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
  - docs/architecture/backend-refactor/runtime-call-chain.md
  - docs/architecture/backend-refactor/read-model-and-external-services.md

Forbidden Scope:
- 不修改 Workbench、Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 业务模块代码。
- 不修改业务 service 文件，除非它们是 PF-P002 明确归属 Platform 的 runtime/auth/settings/observability 文件。
- 不修改 SQL migration。
- 不修改前端、Nginx、Vite、Caddy、部署配置或生产配置。
- 不创建新语言后端。
- 不执行 Merge Gate 或 Traffic Gate。
- 不重构 `app/server.py` 的业务 handler，只允许补平台 guard、auth context 辅助或 readiness 相关最小改动。
- 不在 PF-P003 中迁移既有业务模块里的 `MongoOAAdapter` 调用、`pymysql` 调用或 raw SQL；如果发现当前已有违规，记录为 `PF-P003 findings / known violations`，后续交给对应业务模块 Micro-JIT prompt 处理。
- 不为了让静态测试通过而扩大 allowlist；allowlist 必须有明确 owner、理由和退出计划。
- 不把 PF-P003 标记为 verified，必须等待用户确认。

TDD / Execution Order:
1. 先写或补测试，锁定 PF-P002 的平台 guard 期望。
2. 运行目标测试，确认新增测试能暴露缺口；如果现有代码已经满足，也记录为已满足，不强行改代码。
3. 做最小平台代码改动。
4. 重跑目标测试和文档检查。
5. 更新状态机和受影响架构文档。

Required Guard Work:

1. Production Runtime Guard
   - 在 release runtime 或显式生产 guard 条件下，禁止 `FIN_OPS_APP_STORAGE_BACKEND` 缺失或非 `postgres`。
   - 在 release runtime 或显式生产 guard 条件下，禁止 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT=1/true/yes/on`。
   - 在 production bootstrap 下禁止 `bootstrap_mode=legacy` 进入生产 readiness。
   - 不得破坏本地开发和现有单元测试默认 local state 行为；测试必须覆盖 release/prod guard 和 local/dev permissive 两类场景。

2. Legacy Snapshot / Pickle Guard
   - 测试 `LegacySnapshotBootstrap.load_full_snapshot()` 拒绝 production reason。
   - 测试 `LEGACY_SNAPSHOT_ALLOWLIST` 仍为空或只允许 migration/shadow/test 显式项。
   - 增加静态 guard test：生产 app/server 主路径不得新增 direct `ApplicationStateStore.load()`、`PostgresStateStore.load()` 或 `LegacySnapshotBootstrap.load_full_snapshot()` 调用。
   - 对 pickle/local `.pkl` 只能采用 allowlist 分类，不得为了测试通过删除旧 legacy 实现。

3. Auth Context Contract Guard
   - 明确 `OARequestSession` 或新的轻量 Auth Context 是 handler -> usecase 的唯一身份上下文来源。
   - 增加静态 guard test：`services/` 业务模块不得 import `fin_ops_platform.app.auth`，不得直接解析 Authorization/Cookie/Admin-Token。
   - 不要求本轮重写所有 handler；只锁定未来模块不得私自解析 token/cookie。

4. Unit of Work / Transaction Boundary Guard
   - 增加静态 guard test：业务模块不得绕过 `RuntimeQueueRepository` 直接写 `job.outbox_events` 或 `job.read_model_dirty_scopes`。
   - 允许平台 repository、runtime queue、ops tools 和 tests 按 allowlist 出现相关 SQL。
   - 如果发现当前业务代码已经违规，先记录到 `platform-runtime-boundary-audit.md` 的 PF-P003 findings；只有能在平台范围内安全修正时才改代码，否则将 PF-P003 标为 blocked，不要扩大到业务模块。

5. Redis / RabbitMQ Direct Import Guard
   - 增加静态 guard test：`backend/src/fin_ops_platform/app` 和 `backend/src/fin_ops_platform/services` 下真实 Redis client import 只允许出现在 `services/runtime_redis.py`。
   - 增加静态 guard test：真实 RabbitMQ `pika` import 只允许出现在 `services/rabbitmq_runtime.py`。
   - 允许 tests 和 integration tests import fake/optional client，但生产 source 不允许新增直接 client import。

6. OA Mongo Adapter Direct Use Guard
   - 增加静态 guard test：生产 API request path 和业务模块不得直接 import 或实例化 `MongoOAAdapter`。
   - 允许 `services/mongo_oa_adapter.py`、`services/oa_projection_sync.py`、明确的 worker source adapter、legacy/shadow/migration/ops 路径和 tests 按 allowlist 使用。
   - 如果发现业务模块只是为了调用 `MongoOAAdapter` 的纯函数或 parser version 常量而 import adapter，记录为 known violation，并建议后续抽到 shared/domain utility；本轮不迁移业务代码。
   - 明确 production request path 应读取 PostgreSQL OA projection；OA Mongo 只作为 worker/source sync 或 legacy 路径。

7. External OA MySQL / pymysql Direct Import Guard
   - 增加静态 guard test：真实 `pymysql` import 只允许出现在 `services/oa_role_sync_service.py` 和明确的 Platform/Ops allowlist 中。
   - 禁止 handler、业务 service、业务 repository 直接 import `pymysql`、创建 MySQL connection 或绕过 `OARoleSyncService` 直连外部 OA DB。
   - Tests 可以使用 fake/stub 或明确测试 allowlist；不得记录真实 OA DB host、账号、密码或 token。

8. Handler / Usecase Raw SQL Boundary Guard
   - 增加静态 guard test：`backend/src/fin_ops_platform/app/` handler 层不得直接调用 `PostgresConnection.execute()`、`fetch_one()`、`fetch_all()` 或 transaction raw SQL 拼接业务表 SQL。
   - 增加静态 guard test：除 `services/postgres_repositories/`、runtime queue、platform repository、ops/backfill/tools 和 tests allowlist 之外，业务 service/usecase 不得新增 direct `PostgresConnection` raw SQL。
   - 当前遗留业务 service 中已有 raw SQL 不在 PF-P003 内重构；必须记录为 known violations，并在后续单模块 Micro-JIT 中迁入 repository。
   - 所有新增写 usecase 的目标规则仍是 facts、audit、dirty scope、outbox 在同一 transaction boundary 内提交。

9. Verification / Documentation Guard
   - 更新 `platform-runtime-boundary-audit.md`，追加 PF-P003 guard findings 和剩余风险。
   - 更新 `migration-state-log.md`，记录变更文件、测试命令、结果和下一步建议。
   - 更新 `refactor-prompts.md`，将 PF-P003 状态设为 implemented。

Tests / Verification:
必须至少运行：
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap tests.test_state_store_factory_preflight tests.test_app_postgres_mode -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard tests.test_session_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_runtime_redis tests.test_rabbitmq_runtime -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `git status --short --branch`

如果其中任一测试失败：
- 先按失败原因修复平台范围内问题。
- 如果修复需要改业务模块、SQL migration、部署配置或外部服务配置，停止并将 PF-P003 标记为 blocked，记录原因。

Post-Flight:
- 更新 `migration-state-log.md`：
  - 将 PF-P003 状态设为 implemented 或 blocked。
  - 记录变更文件。
  - 记录每条测试命令和结果。
  - 记录 production runtime guard、legacy snapshot/pickle guard、auth context guard、transaction/outbox/dirty scope guard、Redis/RabbitMQ import guard、OA Mongo adapter direct use guard、external OA MySQL/pymysql import guard、handler/usecase raw SQL boundary guard 的结果。
  - 记录下一条建议 prompt，但不得生成下一条 prompt。
- 更新 `refactor-prompts.md` 的 PF-P003 状态。
- 更新受影响架构文档。
- 最终回复必须告诉用户下一步建议做什么。
- 未经用户确认，不得把 PF-P003 标记为 verified。
```

### Gate Scope

- Merge Gate：不涉及。本 prompt 执行后仍停在工作分支，不 merge。
- Traffic Gate：不涉及。本 prompt 不修改网关、生产配置或流量路由。
- Micro-JIT：涉及，但只处理 Platform / Ops / Runtime Boundary 机械门禁，不处理业务模块。

### 审查结论

- 范围符合 PF-P002 的下一步建议：先补平台机械门禁，再进入业务模块。
- Prompt 明确允许少量平台代码和平台测试改动，禁止业务模块迁移。
- Prompt 使用 TDD 顺序，要求先补 guard tests，再做最小平台实现。
- Prompt 已补齐 PF-P002 中 OA Mongo、external OA MySQL / `pymysql` 和 handler / usecase raw SQL boundary 的机械门禁遗漏。
- Prompt 明确不执行 Merge Gate 或 Traffic Gate。
- Prompt 明确 PF-P003 执行后只能到 implemented 或 blocked，必须等待用户确认才能 verified。

### 执行结果

- 已执行，用户已确认，当前状态为 `verified`。
- 新增 `tests/test_platform_runtime_boundary_guards.py`。
- 修改 `backend/src/fin_ops_platform/app/server.py`，在 readiness summary 中加入 release / explicit production runtime guard。
- 指定测试已通过：`git diff --check`、PF-P003 guard tests、runtime bootstrap/state store/app postgres mode tests、auth/session tests、runtime queue/Redis/RabbitMQ tests、`python3 -m fin_ops_platform.app.main --check`。
- 本 prompt 未执行 Merge Gate、未执行 Traffic Gate、未开始任何业务模块迁移。

## PF-P003-MG - Platform Runtime Boundary Guard Merge Gate

状态：`verified`

### 目标

对 PF-P003 及此前已 verified 的 Python-first backend-refactor 文档和平台 guard 变更执行 Merge Gate 前置检查。PF-P003-MG 只处理范围检查、关键测试复跑、commit/merge 准备和状态机回写，不执行 Traffic Gate，不开始业务模块迁移。

### Prompt

```text
/goal
执行 PF-P003-MG - Platform Runtime Boundary Guard Merge Gate。

目标：只处理 PF-P003 平台运行时边界 guard 及此前已 verified 的 backend-refactor 文档变更的 Merge Gate。确认变更范围、复跑关键测试、准备 commit/merge 到 main 的安全检查，并更新状态机。不得执行 Traffic Gate，不得开始任何业务模块迁移。

Role:
你是一位精通 Python 后端重构、Git Merge Gate、测试门禁、Clean Architecture 和生产变更风险控制的架构负责人。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P000、PF-P001、PF-P001-C1、PF-P002、PF-P003 均已 verified。当前分支是 `codex/python-first-refactor-reset`。PF-P003 已新增平台运行时 guard 和静态边界测试，但尚未执行 Merge Gate。PF-P003-MG 的职责是确认这些已 verified 变更可以作为平台边界基线进入 main；它不是 Traffic Gate，也不是业务模块迁移 prompt。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/README.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/architecture/backend-refactor/module-refactor-plan.md
- docs/architecture/backend-refactor/architecture-inventory.md
- docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
- docs/architecture/backend-refactor/ai-execution-rules.md
- tests/test_platform_runtime_boundary_guards.py
- backend/src/fin_ops_platform/app/server.py

必须确认：
- `migration-state-log.md` 中 PF-P003 状态为 `verified`。
- 当前分支不是直接在 `main` 上做未审查重构；如果已经在 `main`，不得执行无意义 merge，只做范围检查、验证和状态机更新。
- 当前变更只包含已 verified 的 backend-refactor 文档、平台 App Shell guard、平台 guard tests，以及必要的文档索引更新。
- 当前变更不包含业务模块迁移、SQL migration、前端、Nginx、Vite、Caddy、部署配置或生产配置。
- 必须排查 untracked files，区分应纳入本次提交的新增文件与测试/本地运行产生的临时文件。

Allowed Scope:
- 允许执行 git 范围检查：
  - `git status --short --branch`
  - `git diff --name-status`
  - `git ls-files --others --exclude-standard`
  - `git diff --check`
  - `git diff -- backend/src/fin_ops_platform/app/server.py`
  - `git diff -- tests/test_platform_runtime_boundary_guards.py`
  - `git diff -- docs/architecture/backend-refactor`
- 允许复跑 PF-P003 关键测试。
- 允许小范围更新：
  - docs/architecture/backend-refactor/migration-state-log.md
  - docs/architecture/backend-refactor/refactor-prompts.md
  - docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
- 如果范围和测试均通过，允许创建一个清晰 commit，commit message 建议：
  - `feat(platform): establish runtime boundary guards and baseline tests`
  commit body 必须注明本次提交同时包含 Python-first backend-refactor 文档和状态机更新。
- 如用户明确要求并确认，可以把当前分支 merge 到 `main`；未经用户确认，不得自行切 main 或执行 merge。

Forbidden Scope:
- 不修改 Workbench、Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 业务模块代码。
- 不为了通过 Merge Gate 新增或修改业务逻辑。
- 不修改 SQL migration。
- 不修改前端、Nginx、Vite、Caddy、部署配置或生产配置。
- 不执行 Traffic Gate。
- 不切 staging 或 production 流量。
- 不运行会触碰生产外部服务的命令。
- 不使用 `git add .` 或 `git add -A`。
- 不提交 `.pkl`、`.sqlite`、`__pycache__/`、`.pytest_cache/`、测试输出目录、IDE 临时文件或其他本地生成物。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产敏感 URL。
- 未经用户确认，不得把 PF-P003-MG 标记为 `verified`。

Required Merge Gate Checks:
1. Verified Precondition
   - 确认 PF-P003 已 verified。
   - 如 PF-P003 未 verified，停止并将 PF-P003-MG 标记为 blocked。

2. Branch and Diff Scope
   - 输出当前分支。
   - 输出 changed files。
   - 输出 untracked files。
   - 确认变更范围只包含：
     - `backend/src/fin_ops_platform/app/server.py`
     - `tests/test_platform_runtime_boundary_guards.py`
     - `docs/architecture/backend-refactor/**`
     - 必要文档索引文件（如果存在，必须解释原因）
   - 如发现业务模块、SQL migration、前端、网关、部署或生产配置变更，停止并标记 blocked。
   - 如发现 `.pkl`、`.sqlite`、`__pycache__/`、`.pytest_cache/`、测试输出目录、IDE 临时文件或其他本地生成物，必须排除提交；如果无法确定来源，停止并标记 blocked。
   - 对每个准备提交的 untracked file，必须说明它为什么属于本次 Merge Gate 范围。

3. Guard Behavior Review
   - 复核 `server.py` 的 production runtime guard 只影响 readiness，不改变业务 handler 行为。
   - 复核 guard 默认不破坏 local/dev 行为，只有 release runtime 或 `FIN_OPS_PRODUCTION_RUNTIME_GUARD` 显式启用时生效。
   - 复核静态 guard tests 使用 allowlist + known violations，不把业务迁移塞进 PF-P003。

4. Verification
   必须运行：
   - `git diff --check`
   - `git ls-files --others --exclude-standard`
   - `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
   - `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap tests.test_state_store_factory_preflight tests.test_app_postgres_mode -v`
   - `PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard tests.test_session_api -v`
   - `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_runtime_redis tests.test_rabbitmq_runtime -v`
   - `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
   - `git status --short --branch`

5. Commit / Merge Preparation
   - 只有范围检查和测试全部通过，才允许准备 commit。
   - commit 前必须向用户说明 staged files。
   - 必须精准执行 `git add <具体文件路径>`，严禁使用 `git add .` 或 `git add -A`。
   - staged files 必须逐一对应 PF-P003-MG 允许范围；执行 `git diff --cached --name-status` 后再 commit。
   - 如果用户没有明确要求 merge 到 main，只创建/准备 commit，不执行 merge。
   - 如果用户要求 merge 到 main，必须先执行 upstream sync 安全锁：
     - fetch 最新 origin。
     - 确认本地 main 与 origin/main 的关系。
     - 确认当前分支已经包含最新 main；如果不包含，先将最新 main 同步到当前分支，方式可以是 merge main into current branch 或按团队规范 rebase main。
     - 如同步 main 发生冲突，停止并标记 blocked，不得强行解决或使用 destructive command。
     - 同步 main 后必须重新运行第 4 步完整 Verification 测试集，通过后才允许继续 merge 到 main。
   - merge 到 main 前必须再次确认不会执行 Traffic Gate，不会修改网关、部署或生产配置。

Post-Flight:
- 更新 `migration-state-log.md`：
  - 将 PF-P003-MG 状态设为 `implemented` 或 `blocked`。
  - 记录 changed files、范围检查结果、测试命令和结果。
  - 记录 untracked files 排查结果和 staged files。
  - 记录是否创建 commit、commit id（如有）。
  - 记录是否执行 upstream sync、是否执行 merge；默认不执行 Traffic Gate。
  - 记录下一步建议：用户确认 PF-P003-MG verified 后，才允许生成第一个业务模块 Micro-JIT prompt。
- 更新 `refactor-prompts.md` 的 PF-P003-MG 状态。
- 最终回复必须明确：
  - 是否通过 Merge Gate 检查。
  - 是否已 commit。
  - 是否已 merge 到 main。
  - 下一步建议做什么。
- 未经用户确认，不得把 PF-P003-MG 标记为 `verified`。
```

### Gate Scope

- Merge Gate：涉及。PF-P003-MG 是平台 guard 基线进入 main 前的范围检查、测试复跑和 commit/merge 准备 prompt。
- Traffic Gate：不涉及。不得修改网关、生产配置或流量路由。
- Micro-JIT：不涉及业务模块。不得开始 Workbench 或任何业务模块重构。

### 审查结论

- PF-P003 已由用户确认 `verified`，满足生成 PF-P003-MG 的前置条件。
- PF-P003-MG 的边界是 Merge Gate，不是 Traffic Gate；它不允许切 staging/prod 流量。
- Prompt 明确限制变更范围，只允许已 verified 的 backend-refactor 文档、平台 App Shell guard 和平台 guard tests 进入检查。
- Prompt 要求先做范围检查、untracked 排查和测试复跑，再考虑 commit；commit message 使用 `feat(platform)` 语义，避免把生产代码和测试变更误标成 docs。
- Prompt 明确禁止 `git add .` 和 `git add -A`，必须精准 stage 文件，防止测试临时文件、本地 `.pkl`、缓存目录混入主干。
- Prompt 要求 merge 前执行 upstream sync 安全锁；如果同步了最新 main，必须重新跑完整 Verification 测试集。
- 未经用户确认不得 merge 到 `main`，也不得将 PF-P003-MG 标记为 `verified`。

### 执行结果

- 已执行，用户已确认，当前状态为 `verified`。
- 范围检查通过：变更只包含已 verified 的 backend-refactor 文档、平台 App Shell guard 和平台 guard tests。
- untracked 检查通过：新增文件均属于本次允许范围，没有 `.pkl`、`.sqlite`、cache、测试输出或 IDE 临时文件混入。
- 指定测试已通过：`git diff --check`、`git ls-files --others --exclude-standard`、PF-P003 guard tests、runtime bootstrap/state store/app postgres mode tests、auth/session tests、runtime queue/Redis/RabbitMQ tests、`python3 -m fin_ops_platform.app.main --check`。
- 使用精确文件列表 stage，禁止 `git add .` 和 `git add -A`。
- 本 prompt 已创建本地 commit，并在用户确认后本地 merge 到 `main`。
- merge 前已 fetch origin，确认本地 `main` 与 `origin/main` 一致，且功能分支包含最新 main。
- merge 后已在 `main` 上复跑 PF-P003-MG 指定验证集并通过。
- 尚未 push `main` 到 origin。
- 本 prompt 未执行 Traffic Gate、未修改网关、部署或生产配置、未开始任何业务模块迁移。

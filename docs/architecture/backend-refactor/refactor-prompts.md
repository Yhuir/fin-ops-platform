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
- prompt 生成、prompt 审查、状态机更新、对应实现和该实现的 Merge Gate 必须在同一条 `codex/` 功能分支内完成。
- Merge Gate 的单位是可合并的模块任务、platform 边界任务或明确命名的模块切片，不是单个 prompt；同一任务可以包含多个 prompt。
- 测试锁定、发现、实现和文档回写 prompt 可以在同一功能分支连续完成；每个 prompt 仍必须先由用户确认 `verified`，再进入下一个 prompt 或最终 Merge Gate。
- 如果选择不为某个中间 prompt 单独生成 MG，后续 MG 必须明确写明它统一覆盖哪些已 verified prompt 和完整 diff。
- 当前模块任务/切片尚未经过最终 MG 并合入 `main` 前，不得生成下一个无关模块的执行 prompt。
- Merge Gate 合入并复验 `main` 后，下一条 prompt 必须从最新 `main` 新建分支再生成；不得在 `main` 或旧功能分支上继续生成下一个模块的 prompt。
- 不得把下一条 prompt 放在 prompt-only 分支，同时把对应实现放到另一条分支。纯流程文档分支若会约束后续实现，必须先合入 `main` 或同步到对应实现分支。

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
- 已 push `main` 到 origin。
- 本 prompt 未执行 Traffic Gate、未修改网关、部署或生产配置、未开始任何业务模块迁移。

## PF-P004 - Workbench Read Model Query Discovery / Boundary Plan

状态：`verified`

### 目标

生成 Workbench `query/read-model` 子域的事实级发现文档和后续执行边界。PF-P004 是第一个业务模块 Micro-JIT，但只做发现、调用链、API 契约、测试矩阵和重构切片计划；不得修改业务代码、测试、SQL migration、前端或部署配置。

### Prompt

```text
/goal
执行 PF-P004 - Workbench Read Model Query Discovery / Boundary Plan。

目标：只对 Workbench `query/read-model` 子域做生产级发现、调用链梳理、API contract 锁定、风险审计和后续执行切片计划。产出文档，不改业务代码。不得开始 Workbench 写操作、matching/candidates、pair relation、exception、reconciliation 或其他业务模块迁移。

Role:
你是一位精通 Python 后端、Read Model、CQRS、Clean Architecture、PostgreSQL 查询优化和大型遗留系统渐进式重构的架构负责人。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P000、PF-P001、PF-P001-C1、PF-P002、PF-P003、PF-P003-MG 均已 verified；平台运行时边界 guard 已合入并 push 到 `origin/main`，但没有部署服务器，也没有执行 Traffic Gate。现在进入第一个业务模块 Micro-JIT：Workbench Read Model Query。根据 `architecture-inventory.md`，Workbench 顶层模块暂不拆成多个顶层模块，但内部必须先从 `query/read-model` 子域开始，固定 summary、groups、group detail、row detail、refresh status、SSE 和 worker refresh 的真实调用链与测试边界。

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
- docs/architecture/backend-refactor/read-model-and-external-services.md
- docs/architecture/backend-refactor/runtime-call-chain.md
- docs/architecture/backend-refactor/ai-execution-rules.md
- docs/product-specs/workbench.md
- docs/dev/reconciliation-workbench-v2-data-contracts.md

必须使用 CodeGraph 优先做结构化调用链分析：
- 用 `codegraph_context` 获取 Workbench Query / Read Model 上下文。
- 用 `codegraph_search` 或 `codegraph_trace` 定位以下入口和关键路径：
  - `backend/src/fin_ops_platform/app/server.py` 中 `_handle_api_workbench_summary`
  - `_handle_api_workbench_groups`
  - `_handle_api_workbench_group_detail`
  - `_handle_api_workbench_refresh_status`
  - `_handle_api_workbench_events`
  - `_handle_api_workbench`
  - `_handle_api_workbench_row_detail`
  - `backend/src/fin_ops_platform/app/routes_workbench.py`
  - `WorkbenchQueryService`
  - `WorkbenchSqlProjectionBuilder`
  - `WorkbenchReadModelService`
  - `WorkbenchReadModelRefreshService`
  - `PostgresReadModelRepository.load_workbench_read_models`
  - `PostgresReadModelRepository.save_workbench_read_models`
- 用 `codegraph_explore` 一次性读取相关符号源码，避免逐个文件重复读取。

必须用 `rg` 补充 literal facts：
- `/api/workbench/summary`
- `/api/workbench/groups`
- `/api/workbench/groups/detail`
- `/api/workbench/refresh-status`
- `/api/workbench/events`
- `/api/workbench`
- `read_model.workbench_`
- `workbench_generations`
- `workbench_groups`
- `workbench_group_rows`
- `workbench_rows`
- `workbench_snapshots`
- `workbench.read_model`
- `workbench_read_model`
- Redis/page cache key 相关字符串
- dirty scope / source version / outbox event 相关字符串

必须显式读取或通过 CodeGraph 覆盖：
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `backend/src/fin_ops_platform/app/routes_workbench.py`
- `backend/src/fin_ops_platform/services/workbench_query_service.py`
- `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
- `backend/src/fin_ops_platform/services/workbench_read_model_service.py`
- `backend/src/fin_ops_platform/services/workbench_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `backend/src/fin_ops_platform/services/runtime_queue.py`
- `backend/src/fin_ops_platform/services/runtime_redis.py`
- `tests/test_workbench_sql_runtime.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_workbench_query_service.py`
- `tests/test_workbench_read_model_service.py`
- `web/src/features/workbench/api.ts`
- `web/src/features/workbench/types.ts`

Allowed Scope:
- 新增或更新 `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`。
- 按真实发现更新：
  - `docs/architecture/backend-refactor/runtime-call-chain.md`
  - `docs/architecture/backend-refactor/module-refactor-plan.md`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
- 允许只读运行 CodeGraph、`rg`、`git status`、`git diff --check`。
- 允许只做文档级验证，不运行业务测试；如果运行任何测试，必须只使用本地测试环境，不能触碰生产外部服务。

Forbidden Scope:
- 不修改 Python 业务代码。
- 不修改 tests。
- 不修改 SQL migration。
- 不修改前端代码。
- 不修改 Nginx、Vite、Caddy、部署配置或生产配置。
- 不开始 Workbench 写操作迁移，包括 confirm/cancel、ignore/unignore、exception apply/revert、reconciliation write、pair relation write。
- 不开始 Workbench matching/candidates 重构。
- 不开始 Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 或 Ops 模块迁移。
- 不执行 Merge Gate。
- 不执行 Traffic Gate。
- 不切 staging 或 production 流量。
- 不运行会触碰生产 DB、Redis、RabbitMQ、OA Mongo、OA MySQL、MinIO/S3 的命令。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产敏感 URL。
- 未经用户确认，不得把 PF-P004 标记为 `verified`。

Required Discovery Output:
在 `workbench-read-model-query-plan.md` 中至少输出以下内容：

1. Scope Boundary
   - 明确本轮 in-scope endpoint：
     - `GET /api/workbench/summary`
     - `GET /api/workbench/groups`
     - `GET /api/workbench/groups/detail`
     - `GET /api/workbench/refresh-status`
     - `GET /api/workbench/events`
     - 兼容期 `GET /api/workbench`
     - row detail 查询
   - 明确 out-of-scope endpoint / action：
     - confirm/cancel
     - ignore/unignore
     - exception write
     - reconciliation write
     - matching/candidates generation
     - Batch / Turnover writes

2. API Contract Matrix
   - 对每个 in-scope endpoint 输出：
     - handler 函数
     - service/repository 调用
     - 主要 query params
     - response contract
     - read model status 语义
     - cache/freshness 语义
     - 对应前端调用位置
     - 后端 response 与 `web/src/features/workbench/api.ts`、`web/src/features/workbench/types.ts` 的契约一致性
     - 前后端字段偏差、类型不符、前端未使用的冗余字段或需要人工确认的字段
     - 对应测试文件或测试缺口
   - 字段审计只能分类为 `frontend-used`、`backend-only`、`contract-mismatch`、`unknown / needs confirmation`，不得在 PF-P004 中删除字段。

3. Runtime Call Chain
   - 输出 Mermaid sequence diagrams：
     - summary 首屏读取链路。
     - groups 分页/筛选/搜索/排序链路。
     - group detail / row detail 链路。
     - refresh-status 和 SSE 链路。
     - worker refresh event -> builder -> active generation 发布链路。
   - 每张图必须体现 auth/session、handler、service、repository、Redis cache、PostgreSQL read model、dirty scope/source_version、worker refresh 或 SSE 的实际关系。

4. Read Model Data Boundary
   - 列出 Workbench read model 相关表、generation、status、source_versions、schema version 和 Redis key 约束。
   - 明确哪些路径读 active generation，哪些路径可能仍读 snapshot 或 legacy fallback。
   - 明确 `all` scope 和 `YYYY-MM` scope 的差异。
   - 明确 building/failed generation 是否可能进入用户读路径。

5. Current Risk and Optimization Findings
   - 标记是否存在请求线程同步 rebuild、facts 扫描、OA sync、N+1 SQL、snapshot 大 JSON 读取、Redis cache key 缺版本、fallback 到 legacy state、SSE 中执行昂贵计算等风险。
   - 标记 SSE 是否存在长连接线程阻塞耗尽、客户端断开后循环未退出、Redis PubSub 或等价订阅未释放、连接/订阅资源泄露、缺少 heartbeat/timeout/backpressure/cancellation 的风险。
   - 检查核心慢查询和热点接口是否缺失 `request_database_timing`、`api_performance_metrics.py` 或等价平台可观测性埋点，至少覆盖 summary、groups 分页/筛选/搜索/排序、group detail、row detail、refresh-status、SSE 和 worker refresh。
   - 对每个风险给出证据文件/函数和建议处理阶段。
   - 不允许在 PF-P004 中修复这些风险，只记录到计划。

6. Test Matrix
   - 列出下一阶段真正改代码前必须先锁定的 characterization tests。
   - 至少覆盖：
     - `tests/test_workbench_sql_runtime.py`
     - `tests/test_workbench_v2_api.py`
     - `tests/test_workbench_query_service.py`
     - `tests/test_workbench_read_model_service.py`
     - `tests/test_platform_runtime_boundary_guards.py`
   - 区分“PF-P004 文档验证可运行命令”和“PF-P005 代码执行必须运行命令”。
   - 对巨型测试文件必须给出可先运行的 targeted test 方法或类；不得只写“跑全部测试”。

7. Next Execution Slices
   - 设计后续 PF-P005+ 的最小执行切片，但不得执行：
     - Slice A：只补/固定 Workbench query characterization tests。
     - Slice B：薄化 handler 到 query facade，不改变 response。
     - Slice C：收口 read model repository / cache / freshness boundary。
     - Slice D：优化明显的请求线程重算或 fallback 风险。
   - 每个 slice 必须有 rollback、测试入口和禁止范围。

8. Guard Compatibility
   - 明确 PF-P003 的 8 类平台 guard 对 Workbench query/read-model 的约束：
     - production runtime
     - legacy snapshot / pickle
     - auth context
     - outbox / dirty scope
     - Redis / RabbitMQ direct import
     - OA Mongo adapter direct use
     - external OA MySQL / `pymysql`
     - handler / usecase raw SQL boundary

Mandatory Checks:
- `git status --short --branch`
- `git diff --check`
- `test -f docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- `rg -n "Scope Boundary|API Contract Matrix|Runtime Call Chain|Read Model Data Boundary|Current Risk|Test Matrix|Next Execution Slices|Guard Compatibility" docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- `rg -n "summary|groups|groups/detail|refresh-status|events|active generation|source_version|Redis|SSE|worker refresh|worker.py|contract-mismatch|frontend-used|PubSub|request_database_timing|api_performance_metrics" docs/architecture/backend-refactor/workbench-read-model-query-plan.md`

Post-Flight:
- 更新 `migration-state-log.md`：
  - 将 PF-P004 状态设为 `implemented` 或 `blocked`。
  - 记录读取/分析过的关键文件、CodeGraph 使用情况、变更文件、验证命令和结果。
  - 记录发现的关键风险和下一条建议 prompt。
- 更新 `refactor-prompts.md` 的 PF-P004 状态。
- 如真实发现改变了模块边界或调用链，更新 `module-refactor-plan.md` 或 `runtime-call-chain.md`。
- 最终回复必须明确：
  - PF-P004 是否只做文档发现。
  - 是否修改了业务代码、测试或 SQL migration。
  - 发现的最高风险。
  - 下一步建议做什么。
- 未经用户确认，不得把 PF-P004 标记为 `verified`。
```

### Gate Scope

- Merge Gate：不涉及。PF-P004 不准备合入主干，不执行 commit/merge 门禁。
- Traffic Gate：不涉及。PF-P004 不修改生产路径、部署、网关或流量路由。
- Micro-JIT：涉及，但只处理 Workbench Read Model Query 的发现和边界计划，不执行代码重构。

### 审查结论

- PF-P004 的方向符合 `architecture-inventory.md` 推荐顺序：平台 guard 已 verified 并 push 后，优先处理 Workbench query/read-model。
- Prompt 把范围限制在只读 endpoint、read model freshness、worker refresh 和 SSE/readiness 相关链路，明确排除写操作、matching/candidates 和其他业务模块。
- Prompt 明确优先使用 CodeGraph 做结构化调用链分析，并用 `rg` 补充 path、event、table、Redis key 和测试事实。
- Prompt 已补齐 4 个深水区侦察盲点：强制覆盖 `app/worker.py`、前后端契约偏差/冗余字段比对、SSE 长连接资源泄露风险、慢查询与 read model freshness 可观测性基线。
- Prompt 的产物是 `workbench-read-model-query-plan.md`，不是代码改造。
- PF-P004 执行完成后只能到 `implemented` 或 `blocked`，必须等待用户确认才能 `verified`。

### 执行结果

- 已执行，用户已确认，当前状态为 `verified`。
- 已新增 `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`。
- 已按真实发现更新 `runtime-call-chain.md` 的 Workbench `query/read-model` 事实链路。
- 已回写 `migration-state-log.md` 的当前状态、CodeGraph / 文件覆盖、关键发现、验证结果和下一条 prompt 上下文。
- 本轮只做文档发现和计划；未修改 Python 业务代码、tests、SQL migration、前端、网关或部署配置。
- 最高风险记录：row detail 多级 fallback、兼容期 `GET /api/workbench` legacy fallback、SSE 长连接断连/线程占用、`all` scope worker refresh completion 语义需要先用 characterization tests 锁定。
- 下一步建议：执行已生成并审查的 `PF-P005 - Workbench Query Characterization Tests`。

## PF-P005 - Workbench Query Characterization Tests

状态：`verified`

### 目标

在任何 Workbench handler、facade、repository 或 cache/freshness 重构之前，先用 characterization tests 锁定当前 `query/read-model` 子域的外部契约、fallback 顺序、freshness 语义、SSE 事件、worker refresh 幂等边界和 Redis versioned cache 行为。PF-P005 是 test-first 阶段，不允许修改生产代码。

### Prompt

```text
/goal
执行 PF-P005 - Workbench Query Characterization Tests。

目标：只为 Workbench `query/read-model` 子域补充和固定 characterization tests。测试必须描述当前系统真实行为，为后续 handler/facade/repository 重构提供安全网。不得修改生产代码，不得开始行为重构。

Role:
你是一位精通 Python unittest、遗留系统 characterization testing、Read Model/CQRS、PostgreSQL repository fake、SSE 测试和后端重构测试门禁的资深工程师。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P004 已 verified，并产出 `workbench-read-model-query-plan.md`。PF-P004 发现的最高风险是：row detail 多级 fallback 可能绕过 active generation、兼容期 `GET /api/workbench` 仍可能 fallback legacy builder、SSE long polling 缺少断连/heartbeat 测试、`all` scope worker refresh completion 语义需要锁定。PF-P005 只做测试锁定，不修复这些风险。本 prompt 已补充遗留兼容接口、backend-only / contract-mismatch 字段保留、测试状态隔离和确定性测试规则。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/workbench-read-model-query-plan.md
- docs/architecture/backend-refactor/runtime-call-chain.md
- docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
- docs/architecture/backend-refactor/read-model-and-external-services.md
- docs/architecture/backend-refactor/ai-execution-rules.md
- docs/product-specs/workbench.md
- docs/dev/reconciliation-workbench-v2-data-contracts.md

必须优先使用 CodeGraph 做结构化测试和调用链定位：
- 用 `codegraph_context` 获取 Workbench query/read-model tests、handlers、repositories、refresh service 的上下文。
- 用 `codegraph_search` 定位以下符号和测试锚点：
  - `_handle_api_workbench_summary`
  - `_handle_api_workbench_groups`
  - `_handle_api_workbench_group_detail`
  - `_handle_api_workbench_refresh_status`
  - `_handle_api_workbench_events`
  - `_handle_api_workbench`
  - `_handle_api_workbench_row_detail`
  - `_get_api_workbench_row_detail_payload`
  - `_handle_api_workbench_from_sql_read_model`
  - `_build_api_workbench_payload`
  - `WorkbenchReadModelRefreshService`
  - `RuntimeQueueRepository.enqueue_read_model_refresh`
  - `PostgresReadModelRepository.get_workbench_summary`
  - `PostgresReadModelRepository.get_workbench_groups_page`
  - `PostgresReadModelRepository.get_workbench_group_detail`
  - `PostgresReadModelRepository.get_workbench_refresh_status`
  - 现有 `test_workbench_summary_api_uses_sql_summary_contract`
  - 现有 `test_workbench_groups_api_uses_sql_groups_contract`
  - 现有 Redis versioned cache、active generation、failed generation tests
- 用 `codegraph_explore` 一次性读取相关测试类和 fakes，避免重复逐文件读取。

必须用 `rg` 补充 literal facts：
- `/api/workbench/summary`
- `/api/workbench/groups`
- `/api/workbench/groups/detail`
- `/api/workbench/refresh-status`
- `/api/workbench/events`
- `/api/workbench`
- `/api/workbench/rows`
- `workbench.read_model.refresh`
- `read_model_status`
- `source_version`
- `active_generation_id`
- `workbench:groups`
- `X-Accel-Buffering`
- `heartbeat`
- `LiveWorkbenchService`
- `_resolve_rows_from_cached_read_models`
- `_handle_api_workbench_from_sql_read_model`
- `_build_api_workbench_payload`

必须显式读取或通过 CodeGraph 覆盖：
- `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `backend/src/fin_ops_platform/services/workbench_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/services/runtime_queue.py`
- `tests/test_workbench_sql_runtime.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_workbench_query_service.py`
- `tests/test_workbench_read_model_service.py`
- `tests/test_platform_runtime_boundary_guards.py`

Allowed Scope:
- 允许修改或新增 test-only 文件，优先使用现有测试文件：
  - `tests/test_workbench_sql_runtime.py`
  - `tests/test_workbench_v2_api.py`
  - `tests/test_workbench_query_service.py`
  - `tests/test_workbench_read_model_service.py`
  - 必要时新增 `tests/test_workbench_query_characterization.py`，但只有当现有文件放不下时才新增。
- 允许新增或调整 `tests/` 下必要的 fake、fixture、helper；不得引入新依赖。
- 严禁编写产生测试状态污染（State Bleed）的测试。新增的 PostgreSQL / Redis / fake runtime 状态测试必须在事务隔离、唯一 scope key、独立 fake 实例或显式 `tearDown` 清理内运行，不能破坏 `tests/test_workbench_sql_runtime.py` 现有测试集稳定性。
- 允许按真实测试发现更新：
  - `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
- 允许运行本地 unit tests 和静态检查。

Forbidden Scope:
- 不修改 `backend/src/fin_ops_platform/` 下任何生产代码。
- 不修改 SQL migration。
- 不修改前端代码。
- 不修改 Nginx、Vite、Caddy、部署配置或生产配置。
- 不薄化 handler。
- 不新增 query facade。
- 不重构 repository SQL。
- 不删除或改变 legacy fallback。
- 不修改 Workbench 写路径，包括 confirm/cancel、ignore/unignore、exception apply/revert、reconciliation write、pair relation write。
- 不开始 Workbench matching/candidates 重构。
- 不开始 Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 或 Ops 模块迁移。
- 不执行 Merge Gate。
- 不执行 Traffic Gate。
- 不访问生产 DB、Redis、RabbitMQ、OA Mongo、OA MySQL、MinIO/S3。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产敏感 URL。
- 未经用户确认，不得把 PF-P005 标记为 `verified`。

Characterization Test Rule:
- 测试必须锁定当前行为，而不是理想行为。
- 如果 PF-P004 的预期和当前代码真实行为不一致，优先调整测试为当前行为并把 discrepancy 记录到文档；不要修改生产代码。
- 如果当前行为明显危险但无法安全地作为现状锁定，必须将 PF-P005 标记为 `blocked`，记录原因、最小复现和建议下一步。
- 每新增一组测试，都要能解释它保护后续哪个重构切片。
- 对 PF-P004 标记为 `backend-only` 或 `contract-mismatch` 的字段，characterization tests 必须原样保留字段断言；不得只断言前端当前使用字段。
- 对稳定字段，必须断言 key 和当前值；对易变诊断字段（例如时间戳、worker lag、duration、generated_at、随机 id、动态 count），必须断言 key 存在、类型、范围或语义，不得硬断言不稳定精确值。
- 对后续可能删除的冗余字段，在 expected payload 或测试注释中标记 `TODO: PF-P006 verify safe to remove`；PF-P005 不允许自作主张删除 expected payload 字段。

Test Isolation and Determinism Rules:
- 不得依赖测试执行顺序。
- 不得复用会污染其它测试的通用 month / scope / Redis key；需要使用测试专属 scope key 或清理策略。
- PostgreSQL generation、dirty scope、outbox、worker heartbeat 测试必须事务隔离或显式清理。
- Redis / fake Redis / runtime queue fake 必须每个测试独立实例，或在 `tearDown` 中清理本测试写入的 key。
- 不得使用真实外部服务。
- 不得在测试中引入真实 sleep、无限 generator 或不可控线程等待。
- SSE 和 worker refresh tests 必须使用 bounded generator、fake status provider、可控 source_version、显式 timeout 或可控 clock。

Required Test Work:

1. Baseline Test Inventory
   - 列出现有可复用 test class / helper / fake。
   - 列出本轮实际选择运行的 targeted unittest 命令。
   - 不得只写“跑全部测试”。

2. Summary Characterization
   - 锁定 `GET /api/workbench/summary` fresh response contract。
   - 锁定 missing summary 返回 `202 refreshing` 并 enqueue refresh reason。
   - 锁定 source_version stale 时 response 和 enqueue refresh 行为；如果现有测试夹具不支持，记录 gap。

3. Groups Characterization
   - 锁定 `GET /api/workbench/groups` fresh response contract。
   - 锁定 Redis versioned cache hit 行为。
   - 锁定 stale/refreshing 时不使用旧 Redis payload。
   - 锁定 search/filter/sort/detail_level 关键 query params 至少一个组合。

4. Group Detail Characterization
   - 锁定 `GET /api/workbench/groups/detail` wrapper contract。
   - 锁定 group detail 读取 active generation 的现有行为。
   - 如果 missing/stale 语义不明确，写测试固定当前行为并记录后续风险。

5. Row Detail Characterization
   - 锁定 `_get_api_workbench_row_detail_payload` 的 fallback 顺序。
   - 至少覆盖 live service 命中、live service miss 后 cached read model fallback、最终 route service fallback 中可测试的路径。
   - 锁定 override 应用顺序；如无法稳定测试，记录 gap。

6. Legacy Compatibility Characterization
   - 锁定兼容期 `GET /api/workbench` / `_handle_api_workbench` 的当前 response contract。
   - 明确断言在什么条件下使用 SQL read model。
   - 明确断言在什么条件下返回 refreshing / unavailable。
   - 明确断言在什么条件下 fallback 到 `_build_api_workbench_payload` legacy builder。
   - fallback payload 中当前存在的 `backend-only` / `contract-mismatch` 字段必须保留断言，不能只断言前端字段。

7. Refresh Status Characterization
   - 锁定 dirty scope / source_version 到 read_model_status 的映射。
   - 锁定 outbox backlog、worker lag、building/failed/active generation metadata 的 response contract。
   - 锁定 failed generation 不进入用户读路径的测试必须继续通过。

8. SSE Characterization
   - 锁定 `/api/workbench/events` response headers 至少包含 `text/event-stream`、`Cache-Control: no-cache, no-transform`、`X-Accel-Buffering: no`。
   - 锁定 heartbeat event 或当前等价输出。
   - 尝试用 fake status provider / bounded generator 锁定断连或停止条件；如果现有实现不支持安全测试，记录为 PF-P006 风险，不得改生产代码。

9. Worker Refresh Characterization
   - 锁定 month scope refresh 使用 source_version，旧 source_version 不覆盖新 active generation。
   - 锁定 `all` scope 只从 active month shards 聚合。
   - 锁定 `all` scope enqueue shards / aggregate event / completion 语义的当前行为；如果当前行为存在不明确点，记录 discrepancy。

10. Guard Compatibility
   - 运行 `tests/test_platform_runtime_boundary_guards.py`，确认 PF-P003 8 类 guard 没有被本轮测试改动破坏。
   - 不得为了让 Workbench tests 方便而放宽 guard tests。

Mandatory Checks:
- `git status --short --branch`
- `git diff --check`
- 运行本轮新增/修改 tests 的 targeted unittest 命令。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- `rg -n 'PF-P005|Workbench Query Characterization|状态：`implemented`|状态：`blocked`' docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md`
- `rg -n "Legacy Compatibility|Test Isolation|Determinism|State Bleed|backend-only|contract-mismatch|_handle_api_workbench|_build_api_workbench_payload" docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/migration-state-log.md`
- 如果更新 `workbench-read-model-query-plan.md`，运行：
  - `rg -n "PF-P005|Characterization|Test Matrix|Row detail|SSE|all scope|Redis" docs/architecture/backend-refactor/workbench-read-model-query-plan.md`

Post-Flight:
- 更新 `migration-state-log.md`：
  - 将 PF-P005 状态设为 `implemented` 或 `blocked`。
  - 记录新增/修改的 test 文件。
  - 记录实际运行的每条测试命令和结果。
  - 记录未覆盖或 blocked 的测试点。
  - 记录下一条建议 prompt。
- 更新 `refactor-prompts.md` 的 PF-P005 状态和执行结果。
- 如测试事实修正了 PF-P004 的判断，更新 `workbench-read-model-query-plan.md`。
- 最终回复必须明确：
  - PF-P005 是否只改测试和文档。
  - 是否修改了任何生产代码、SQL migration、前端或部署配置。
  - 哪些 targeted tests 已通过。
  - 哪些风险仍未覆盖。
  - 下一步建议做什么。
- 未经用户确认，不得把 PF-P005 标记为 `verified`。
```

### Gate Scope

- Merge Gate：不涉及。PF-P005 不 commit、不 merge、不推送 main。
- Traffic Gate：不涉及。PF-P005 不修改生产路径、网关、worker 启动方式或部署拓扑。
- Test Gate：涉及。PF-P005 是 Workbench Query / Read Model 后续重构的测试门禁。

### 审查结论

- PF-P005 符合 PF-P004 的下一步建议：先测试锁定，再重构实现。
- Prompt 明确 test-only，禁止修改生产代码，避免把 characterization 阶段变成隐式实现阶段。
- Prompt 覆盖 PF-P004 的四个最高风险：row detail fallback、legacy `GET /api/workbench` fallback、SSE 长连接、`all` scope worker refresh。
- Prompt 已补齐遗留系统测试细节：legacy endpoint fallback 打底、backend-only / contract-mismatch 字段保留断言、State Bleed 防范和 deterministic test 约束。
- Prompt 要求运行 PF-P003 platform guard tests，防止为了 Workbench 测试便利而放宽平台边界。
- Prompt 明确如果测试无法在现有实现上通过，必须记录 discrepancy 或 blocked，不允许直接改生产逻辑。
- PF-P005 执行完成后只能到 `implemented` 或 `blocked`，必须等待用户确认才能 `verified`。

### 执行结果

- 已执行，用户已确认，当前状态为 `verified`。
- 本轮只修改测试和重构文档；未修改生产代码、SQL migration、前端、网关、部署或生产配置。
- 已在 `tests/test_workbench_sql_runtime.py` 新增 7 个 characterization tests，覆盖：
  - 兼容期 `GET /api/workbench` SQL read-model path 的 backend-only / contract-mismatch 字段保留。
  - legacy bootstrap 且 SQL runtime 非强制时 fallback `_build_api_workbench_payload`。
  - PostgreSQL production runtime 缺失 SQL read repository 时返回 `503 read_model_unavailable`，且不 fallback legacy builder。
  - Summary missing payload 返回 `202 refreshing` 并 enqueue `api_summary_miss`。
  - Summary stale source_versions 当前 response contract、backend-only 字段和 enqueue 行为。
  - Groups refresh status stale/refreshing 时绕过旧 Redis JSON payload，读取 DB page，并 enqueue `api_groups_source_versions_stale`。
  - SSE headers、stream flag、首个 refresh event 和 deterministic heartbeat event。
- 已复用 `tests/test_workbench_v2_api.py` 现有 row detail targeted tests 覆盖 row detail 兼容路径。
- 记录的 discrepancy：PF-P004 文档预期中的 stale reason 名称与当前实现不完全一致；当前实现实际输出 `builder_mismatch` 以及多个 parser/rules version missing reasons。
- 记录的现状行为：Groups stale/refreshing 会绕过旧 Redis JSON payload，但仍会将 fresh DB payload 写入 Redis；PF-P006 需要判断是否保留。
- 验证已通过：
  - 新增 PF-P005 tests targeted run：7 tests passed。
  - Workbench query/read-model targeted suite：24 tests passed。
  - Row detail targeted suite：4 tests passed。
  - `tests.test_platform_runtime_boundary_guards`：9 tests passed。
  - `tests.test_workbench_sql_runtime` 全文件：102 tests passed。
- 下一步建议：执行已生成并审查的 `PF-P005-MG - Workbench Query Characterization Tests Merge Gate`。

## PF-P005-MG - Workbench Query Characterization Tests Merge Gate

状态：`verified`

### 目标

把 PF-P005 已 verified 的 Workbench Query Characterization Tests 安全合入 `main`。本 prompt 是 Merge Gate，不是业务实现 prompt，也不是 Traffic Gate。它只负责范围审计、上游同步、精准提交、合并前后验证和状态机回写。

### Prompt

```text
/goal
执行 PF-P005-MG - Workbench Query Characterization Tests Merge Gate。

目标：将 PF-P005 已 verified 的 Workbench query/read-model characterization tests 与相关文档安全合入 main。只处理 Merge Gate，不执行 Traffic Gate，不开始 PF-P006 生产代码重构。

Role:
你是一位严格执行 Git merge gate、测试门禁和生产变更范围审计的资深工程师。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P005 已由用户确认 verified，PF-P005 的产物是 Workbench query/read-model characterization tests 和文档回写。本轮要把这套 test-only 安全网合入 main，作为后续 PF-P006 handler/facade/repository 重构的基线。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/workbench-read-model-query-plan.md
- docs/architecture/backend-refactor/runtime-call-chain.md
- docs/architecture/backend-refactor/ai-execution-rules.md

必须确认：
- `migration-state-log.md` 中 `PF-P005 - Workbench Query Characterization Tests` 状态为 `verified`。
- 当前 active prompt 是 `PF-P005-MG - Workbench Query Characterization Tests Merge Gate`。
- 本轮是 Merge Gate，不是 Traffic Gate。
- 本轮不允许修改生产代码，不允许开始 PF-P006。

Allowed Scope:
- 允许做 Git 范围审计：
  - `git status --short --branch`
  - `git diff --name-only`
  - `git diff --stat`
  - 必要时检查 `git diff -- <具体文件>`
- 允许提交并合并 PF-P005 已 verified 的变更。
- 允许更新：
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
- 允许在执行过程中因为状态机回写而产生文档小改动。
- 如果当前已经在 `main`，不得做无意义 merge；只做范围检查、必要 commit、验证和状态机更新。

Expected Changed Files:
本次合入范围只能包含以下文件：
- `tests/test_workbench_sql_runtime.py`
- `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- `docs/architecture/backend-refactor/runtime-call-chain.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`

注意：`tests/test_workbench_v2_api.py` 只是 PF-P005 复用并运行的现有 row detail targeted tests，不是本次已修改文件。若 `git status` 显示它被修改，PF-P005-MG 必须先阻断并审查修改来源，不得静默加入白名单或提交。

如果出现其它 changed 或 untracked 文件：
- 必须先判断是否属于 PF-P005 / PF-P005-MG。
- 临时文件、缓存文件、`.pkl`、`.sqlite`、`__pycache__`、测试输出、导出物、日志文件一律不得提交。
- 不得使用 `git add .` 或 `git add -A`。
- 只能用 `git add <具体文件>` 精准 staging。

Forbidden Scope:
- 不修改 `backend/src/fin_ops_platform/` 下任何生产代码。
- 不修改 SQL migration。
- 不修改前端代码。
- 不修改 Nginx、Vite、Caddy、部署配置或生产配置。
- 不新增或修改 Workbench handler/facade/repository 生产实现。
- 不删除 legacy fallback。
- 不修改 Workbench 写路径。
- 不开始 Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 或 Ops 模块迁移。
- 不执行 Traffic Gate。
- 不部署服务器。
- 不 push 到生产服务器。
- 不访问生产 DB、Redis、RabbitMQ、OA Mongo、OA MySQL、MinIO/S3。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产敏感 URL。
- 未经用户确认，不得把 PF-P005-MG 标记为 `verified`。

Upstream Sync Rule:
- 在 merge 到 main 前，必须确认 `main` 和 `origin/main` 关系。
- 必须先同步最新 `origin/main`。
- 如果当前工作分支不是基于最新 main，必须先把最新 main 合入或 rebase 到当前分支，并处理冲突。
- 如果同步了 main 的新提交，必须重新执行本 prompt 的 Mandatory Checks。
- 严禁在存在未解决冲突或未重跑验证时 merge 到 main。

Commit / Merge Rules:
- Commit message 建议使用：
  - `test(workbench): lock query read model characterization baseline`
- Commit body 必须说明：
  - PF-P005 新增 Workbench query/read-model characterization tests。
  - 本次只包含 tests 和 docs。
  - 未修改生产代码、SQL migration、前端或部署配置。
- 如果当前在 feature branch：
  1. 精准 staging 允许文件。
  2. commit。
  3. checkout main。
  4. pull / fast-forward 最新 origin/main。
  5. merge feature branch。
  6. 在 main 上重跑 Mandatory Checks。
- 如果当前已经在 main：
  - 不执行无意义 merge。
  - 完成范围检查、精准 staging、commit、Mandatory Checks 和状态机回写即可。
- Push 到 origin/main 需要用户明确允许；本 prompt 不默认 push。

Mandatory Checks:
- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --name-only`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- Row detail targeted tests：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_prefers_cached_read_model_before_query_service_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_prefers_month_read_model_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_without_cache_returns_404_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_row_detail_supports_oa_bank_and_invoice -v`
- `rg -n 'PF-P005|PF-P005-MG|状态：`verified`|状态：`planned`' docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md`
- `rg -n "test_workbench_api_sql_contract_preserves_backend_only_fields|test_workbench_groups_api_stale_refresh_status_bypasses_redis_payload|test_workbench_events_stream_exposes_no_buffering_headers_and_heartbeat" tests/test_workbench_sql_runtime.py`

Post-Flight:
- 更新 `migration-state-log.md`：
  - 记录 PF-P005-MG 执行结果。
  - 如果 commit / merge 已完成，记录 commit hash、merge 方式和 main 上验证结果。
  - 将 PF-P005-MG 状态设为 `implemented` 或 `blocked`，不得直接设为 `verified`。
  - 记录下一步建议：用户确认后标记 PF-P005-MG verified；随后生成 PF-P006。
- 更新 `refactor-prompts.md` 的 PF-P005-MG 状态和执行结果。
- 最终回复必须明确：
  - 是否只合入 tests/docs。
  - 是否修改了任何生产代码、SQL migration、前端或部署配置。
  - 是否已 commit、merge、push。
  - 哪些验证在 feature branch 和 main 上通过。
  - 是否执行 Traffic Gate。
  - 下一步建议做什么。
```

### Gate Scope

- Merge Gate：涉及。PF-P005-MG 只负责 PF-P005 test-only / docs-only 变更的 main 合入门禁。
- Traffic Gate：不涉及。PF-P005-MG 不切流、不部署、不修改网关、不改变 worker 启动方式。
- Test Gate：涉及。PF-P005-MG 必须在合入前后确认 Workbench SQL runtime、row detail targeted tests 和 PF-P003 platform guard tests 通过。

### 审查结论

- PF-P005-MG 的边界正确：只处理 PF-P005 已 verified 变更的 merge gate，不开始 PF-P006。
- Prompt 明确了 expected changed files，覆盖当前 untracked 的 `workbench-read-model-query-plan.md`，并禁止提交临时文件、`.pkl`、`.sqlite`、`__pycache__`、测试输出和导出物。
- Prompt 明确 `tests/test_workbench_v2_api.py` 只是复用测试，不在当前白名单中；如果它被修改，必须阻断并重新审查。
- Prompt 明确禁止 `git add .` / `git add -A`，要求精准 staging。
- Prompt 明确把 `git ls-files --others --exclude-standard` 列为 Mandatory Check，避免漏审未跟踪文件。
- Prompt 包含 upstream sync rule，要求在 merge main 前同步最新 `origin/main`；如同步后发生变化，必须重新跑验证。
- Prompt 明确 commit message 语义应使用 `test(workbench): ...`，因为本轮包含测试代码而不是纯 docs。
- Prompt 明确不执行 Traffic Gate、不 push 生产服务器、不访问生产外部服务。
- PF-P005-MG 执行完成后只能到 `implemented` 或 `blocked`，必须等待用户确认才能 `verified`。

### 执行结果

- 已执行，用户已确认，当前状态为 `verified`。
- PF-P005 tests/docs 变更已精准 stage 并提交，提交为 `2bb3ac17`：
  - `test(workbench): lock query read model characterization baseline`
- 已切回 `main` 并 fast-forward merge `codex/workbench-read-model-query-plan`。
- `main` 未 push 到 `origin/main`。
- 未执行 Traffic Gate，未部署服务器，未访问生产外部服务。
- 合入范围只包含 tests/docs；未修改生产代码、SQL migration、前端、网关、部署或生产配置。
- `tests/test_workbench_v2_api.py` 未被修改，只作为 row detail targeted tests 复用。
- `git ls-files --others --exclude-standard` 合入 main 后无输出。
- main 上验证已通过：
  - `git diff --check`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`，102 tests passed
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`，9 tests passed
  - Row detail targeted tests，4 tests passed
  - PF-P005 / PF-P005-MG 文档门禁 `rg`
  - 新增 characterization test 锚点 `rg`
- 下一步建议：先 push `main` 到 `origin/main` 让测试基线生效；随后生成并审查 `PF-P006 - Workbench Query Facade Extraction (Slice B)`，不要直接执行 PF-P006。

## PF-P006 - Workbench Query Facade Extraction (Slice B)

状态：`verified`

### 目标

在 PF-P005 characterization tests 已合入并推送远端的基础上，执行 Workbench `query/read-model` 子域的第一轮生产代码最小切片：抽取 Query Facade，薄化 summary / groups / group detail / refresh-status handler 的 orchestration。PF-P006 是实现型 prompt，但必须保持外部行为完全不变。

### Prompt

```text
/goal
执行 PF-P006 - Workbench Query Facade Extraction (Slice B)。

目标：在不改变任何 API response contract、status code、freshness 语义、Redis key 格式、refresh enqueue reason、legacy fallback 或前端契约的前提下，从 `backend/src/fin_ops_platform/app/server.py` 中抽取 Workbench Query Facade，薄化 Workbench `query/read-model` 只读 handler。不得执行 Merge Gate 或 Traffic Gate。

Role:
你是一位精通 Python 遗留系统重构、Clean Architecture、CQRS / Read Model、Redis cache 边界、HTTP handler 薄化和 characterization-test-driven refactoring 的资深后端工程师。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P005-MG 已 verified，并已 push 到 `origin/main`。PF-P005 新增的 Workbench query/read-model characterization tests 已成为本轮行为安全网。PF-P006 对应 `workbench-read-model-query-plan.md` 的 Slice B：薄化 Handler 到 Query Facade。PF-P006 只能移动和收口已有 orchestration，不能改变业务行为。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/workbench-read-model-query-plan.md
- docs/architecture/backend-refactor/runtime-call-chain.md
- docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
- docs/architecture/backend-refactor/read-model-and-external-services.md
- docs/architecture/backend-refactor/ai-execution-rules.md
- docs/product-specs/workbench.md
- docs/dev/reconciliation-workbench-v2-data-contracts.md

必须优先使用 CodeGraph：
- 用 `codegraph_context` 获取 Workbench query/read-model handlers、PF-P005 tests、repository 和 runtime queue 的结构化上下文。
- 用 `codegraph_search` 定位：
  - `_handle_api_workbench_summary`
  - `_handle_api_workbench_groups`
  - `_handle_api_workbench_group_detail`
  - `_handle_api_workbench_refresh_status`
  - `_enqueue_workbench_read_model_refresh`
  - `_workbench_read_model_scope_key`
  - `_expected_workbench_source_versions`
  - `_workbench_source_versions_stale_reasons`
  - `_workbench_groups_redis_cache_key_from_version`
  - `_emit_workbench_read_model_status_metric`
  - `PostgresReadModelRepository.get_workbench_summary`
  - `PostgresReadModelRepository.get_workbench_groups_page`
  - `PostgresReadModelRepository.get_workbench_group_detail`
  - `PostgresReadModelRepository.get_workbench_refresh_status`
  - `test_workbench_api_sql_contract_preserves_backend_only_fields`
  - `test_workbench_summary_api_missing_payload_enqueues_refreshing_contract`
  - `test_workbench_summary_api_stale_source_versions_preserves_backend_only_fields`
  - `test_workbench_groups_api_stale_refresh_status_bypasses_redis_payload`
  - `test_workbench_events_stream_exposes_no_buffering_headers_and_heartbeat`
- 用 `codegraph_explore` 一次性读取上述 handler 和 PF-P005 test source，避免重复读取。

必须用 `rg` 补充 literal facts：
- `/api/workbench/summary`
- `/api/workbench/groups`
- `/api/workbench/groups/detail`
- `/api/workbench/refresh-status`
- `api_summary_miss`
- `api_summary_source_versions_stale`
- `api_groups_source_versions_stale`
- `builder_mismatch`
- `workbench:groups:version`
- `X-Accel-Buffering`
- `TODO: PF-P006 verify safe to remove`

Baseline Checks Before Editing:
- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- Row detail targeted tests：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_prefers_cached_read_model_before_query_service_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_prefers_month_read_model_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_without_cache_returns_404_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_row_detail_supports_oa_bank_and_invoice -v`

Allowed Scope:
- 允许新增一个小而清晰的 facade 模块，例如：
  - `backend/src/fin_ops_platform/services/workbench_query_facade.py`
- 允许最小修改：
  - `backend/src/fin_ops_platform/app/server.py`
  - `tests/test_workbench_sql_runtime.py`
  - 必要时新增 `tests/test_workbench_query_facade.py`
  - 本轮执行结果相关的 backend-refactor 文档
- 允许把 summary / groups / group detail / refresh-status 的 read-model orchestration 从 `Application` handler 移到 facade。
- 允许 facade 通过显式依赖接收：
  - SQL read repository
  - runtime queue repository
  - Redis helper
  - expected source version provider
  - stale reason calculator
  - status metric emitter
  - cache key / normalization helpers
- Facade 初始化必须接收细粒度依赖（Granular Dependencies），例如具体的 `PostgresReadModelRepository`、runtime queue repository / enqueue callable、Redis helper、expected source version provider、stale reason calculator、metric emitter 或纯 helper callable。
- 绝对禁止把 `Application`、`RuntimeRepositories`、`RuntimeRepositoryContext`、`ApplicationStateStore`、`StateStoreProtocol` 或其他全局 runtime container 作为上帝对象注入给 Facade。
- 允许保留 thin wrapper methods 在 `Application` 上，以降低调用点风险。

Facade Boundary Rules:
- Facade 不得 import `Application`。
- Facade 不得 import HTTP `Response` 或负责 socket / handler / routing。
- Facade 不得解析 cookie、token 或 auth header。
- Facade 不得直接 import Redis/RabbitMQ clients；只能使用传入的 runtime helper / repository 边界。
- Facade 不得拼 raw SQL；SQL 仍在 `services/postgres_repositories/`。
- Facade 返回轻量 result object 或 `(status_code, payload, headers?)` 等结构，handler 负责转成 `_json_response`。
- Handler 仍负责 HTTP raw params 的边界入口；复杂 normalization 可以移动，但必须保持现有错误格式。
- Facade 不得通过 constructor、method 参数或闭包持有 `Application`、`RuntimeRepositories`、`RuntimeRepositoryContext`、`ApplicationStateStore` 或状态存储协议实例。若某个 helper 当前只能从这些对象取得，必须在 `server.py` 中拆出更小的 callable / adapter 后再传入 Facade。
- 带 HTTP 路由上下文的 observability wrapper 必须留在 `server.py` handler 层包裹 Facade 调用，例如 `request_database_timing` 这类依赖 path、method、request context 的统计边界不得下沉到 Facade。
- 纯业务 / read-model 状态指标可以移动到 Facade 或以 metric emitter 注入，例如 `_emit_workbench_read_model_status_metric`，但必须保持指标名、标签语义和触发条件不变。

Required Implementation Work:
1. Baseline confirmation
   - 先运行 baseline tests，确认当前分支干净。
   - 如果 baseline 失败，停止并标记 `blocked`。

2. Facade design
   - 设计最小 facade API，优先覆盖：
     - summary
     - groups
     - group detail
     - refresh-status
   - 不要一次性处理 compatibility `GET /api/workbench`、row detail 或 SSE。
   - 如果发现必须移动 helper，优先移动纯函数或添加 server wrapper，避免大范围改动。

3. TDD / safety net
   - PF-P005 app-level characterization tests 是主安全网。
   - 严禁在 `tests/test_workbench_sql_runtime.py` 中用 `mock.patch`、monkeypatch 或全局替换绕过 `WorkbenchQueryFacade`。
   - PF-P005 characterization tests 必须继续以黑盒方式覆盖 `Application handler -> WorkbenchQueryFacade -> repository / queue / redis fake` 的真实集成链路。
   - Facade unit tests 只能作为补充，不能替代 app-level HTTP handler characterization tests，也不能把现有测试降级为 mock facade 的拼装测试。
   - 如果 facade 暴露新的 public methods，补充低成本 facade unit tests，使用 fake repository / fake queue / fake Redis。
   - 不要复制巨型端到端测试。

4. Extraction
   - 分小步迁移 handler orchestration。
   - 每完成一个 handler 或一组 helper 移动，运行相关 targeted tests。
   - 保持 response payload、status code、stale reason、enqueue reason 和 Redis cache behavior 不变。

5. Documentation
   - 更新 `migration-state-log.md`、`refactor-prompts.md` 和必要的 `workbench-read-model-query-plan.md`。
   - 如果发现 PF-P005 记录的风险或 discrepancy 有新事实，必须回写。

Forbidden Scope:
- 不修改 `GET /api/workbench` legacy compatibility endpoint 的行为。
- 不修改 `_build_api_workbench_payload` legacy builder。
- 不修改 row detail fallback。
- 不修改 `/api/workbench/events` SSE 长连接逻辑。
- 不修改 worker refresh、builder、repository SQL 或 SQL migration。
- 不修改 Workbench 写路径，包括 confirm/cancel、ignore/unignore、exception apply/revert、reconciliation write、pair relation write。
- 不开始 Workbench matching/candidates 重构。
- 不开始 Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 或 Ops 模块迁移。
- 不修改前端、网关、部署配置或生产配置。
- 不执行 Merge Gate。
- 不执行 Traffic Gate。
- 不 push。
- 不得把 PF-P005 的 `tests/test_workbench_sql_runtime.py` 改成 mock facade 的测试。
- 不得向 Facade 注入 `Application`、`RuntimeRepositories`、`RuntimeRepositoryContext`、`ApplicationStateStore` 或任何全局状态容器。
- 不得把 `request_database_timing` 或其他依赖 HTTP path/method/request context 的 wrapper 移入 Facade。
- 不访问生产 DB、Redis、RabbitMQ、OA Mongo、OA MySQL、MinIO/S3。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产敏感 URL。
- 未经用户确认，不得把 PF-P006 标记为 `verified`。

Behavior Preservation Rules:
- 不改变 API response contract。
- 不改变 HTTP status code。
- 不改变 `read_model_status`、`read_model_stale_reasons` 或 stale reason 命名；当前 `builder_mismatch` 等现状必须保持。
- 不改变 refresh enqueue reasons：例如 `api_summary_miss`、`api_summary_source_versions_stale`、`api_groups_source_versions_stale`。
- 不改变 Redis cache key 格式或 version semantics。
- 不改变 groups stale/refreshing 现状：当前行为是绕过旧 Redis JSON payload，但仍会写入 fresh DB payload；本轮只能保留，不做语义判断。
- 不删除 PF-P005 标记的 backend-only / contract-mismatch 字段；`TODO: PF-P006 verify safe to remove` 本轮只能保留或迁移注释，不能移除字段。
- 如果任何 expected payload 需要修改，默认视为行为改变，必须停止并记录 discrepancy。

Mandatory Checks After Editing:
- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --name-only`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- Row detail targeted tests：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_prefers_cached_read_model_before_query_service_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_prefers_month_read_model_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_without_cache_returns_404_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_row_detail_supports_oa_bank_and_invoice -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `rg -n "class WorkbenchQueryFacade|WorkbenchQueryFacade|handle_summary|handle_groups|handle_group_detail|handle_refresh_status" backend/src/fin_ops_platform tests`
- `rg -n "WorkbenchQueryFacade\\([^\\n]*(Application|RuntimeRepositories|RuntimeRepositoryContext|ApplicationStateStore|StateStoreProtocol|state_store)" backend/src/fin_ops_platform tests` 必须无输出；如有输出，视为上帝对象注入风险，必须修正。
- `rg -n "mock\\.patch\\(.+WorkbenchQueryFacade|patch\\(.+workbench_query_facade|monkeypatch.+WorkbenchQueryFacade|WorkbenchQueryFacade.*Mock|Mock.*WorkbenchQueryFacade" tests/test_workbench_sql_runtime.py` 必须无输出；如有输出，视为 characterization test fidelity 破坏，必须修正。
- `test ! -f backend/src/fin_ops_platform/services/workbench_query_facade.py || ! rg -n "request_database_timing" backend/src/fin_ops_platform/services/workbench_query_facade.py` 必须通过；`request_database_timing` 这类 HTTP route timing wrapper 必须保留在 handler / app shell 边界。
- `rg -n "api_summary_miss|api_summary_source_versions_stale|api_groups_source_versions_stale|builder_mismatch|TODO: PF-P006 verify safe to remove" backend/src/fin_ops_platform tests docs/architecture/backend-refactor`

Post-Flight:
- 更新 `migration-state-log.md`：
  - 将 PF-P006 状态设为 `implemented` 或 `blocked`。
  - 记录变更文件。
  - 记录实际运行的每条验证命令和结果。
  - 记录是否新增 facade unit tests。
  - 记录任何 discrepancy、blocked 点或行为保持结论。
  - 记录下一步建议：用户确认后标记 PF-P006 verified；随后生成 PF-P006-MG 或 Slice C prompt。
- 更新 `refactor-prompts.md` 的 PF-P006 状态和执行结果。
- 如本轮发现修正了 Workbench query/read-model 计划，更新 `workbench-read-model-query-plan.md`。
- 最终回复必须明确：
  - 是否修改了生产代码。
  - 是否只影响 Workbench query/read-model read path。
  - 是否修改 SQL migration、前端、网关、部署配置。
  - 哪些 tests 通过。
  - 是否执行 Merge Gate / Traffic Gate。
  - 下一步建议做什么。
```

### Gate Scope

- Merge Gate：不涉及。PF-P006 只实现并验证，不 commit/merge 到 main。
- Traffic Gate：不涉及。PF-P006 不部署、不切流、不修改网关或 worker 启动方式。
- Test Gate：涉及。PF-P006 必须在 PF-P005 characterization tests 和 PF-P003 platform guards 保护下完成。

### 审查结论

- PF-P006 的方向合理：它是 `workbench-read-model-query-plan.md` 中 Slice B，紧接 PF-P005 测试基线之后开始最小生产代码重构。
- 范围应严格限于 summary / groups / group detail / refresh-status handler orchestration，不能顺手处理 legacy `GET /api/workbench`、row detail、SSE、worker 或 repository SQL。
- Facade 必须与 `Application` 和 HTTP `Response` 解耦，否则只是把 `server.py` 的耦合搬到另一个文件。
- Facade 不能接收 `Application`、`RuntimeRepositories`、`RuntimeRepositoryContext`、`ApplicationStateStore` 等上帝对象；PF-P006 已增加静态检查来拦截这类注入。
- PF-P005 app-level characterization tests 不能被 mock facade 降级；PF-P006 已要求继续覆盖 handler 到 facade 再到 fake repository / queue / redis 的黑盒链路。
- `request_database_timing` 这类依赖 HTTP path/method/request context 的观测边界留在 handler 层；纯 read-model 状态指标可以移动或注入到 Facade。
- Prompt 已明确保持 PF-P005 锁定的现有行为，包括 backend-only 字段、stale reason、enqueue reason、Redis cache key 和 groups stale/refreshing 写缓存现状。
- Prompt 已把 `python -m compileall`、`tests.test_workbench_sql_runtime`、PF-P003 guards、row detail targeted tests 和 `app.main --check` 作为 mandatory checks。
- PF-P006 生成后不得直接执行，必须等待用户确认。

### 执行结果

- PF-P006 已执行并由用户确认，当前状态为 `verified`。
- 新增 `backend/src/fin_ops_platform/services/workbench_query_facade.py`，将 summary / groups / group detail / refresh-status orchestration 收口到 `WorkbenchQueryFacade`。
- `backend/src/fin_ops_platform/app/server.py` 中对应四个 handler 已薄化为参数校验、Facade 调用和 `_json_response` 包装。
- 新增 `tests/test_workbench_query_facade.py`，先确认 RED：缺少 `fin_ops_platform.services.workbench_query_facade` 导致测试失败；随后实现 Facade 并通过测试。
- 未修改 SQL migration、前端、网关、部署配置或生产配置。
- 未执行 Merge Gate、Traffic Gate 或 push。
- 已通过验证：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`
  - `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
  - Row detail targeted tests
  - `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
  - Facade 上帝对象注入、mock facade、`request_database_timing` 边界静态检查
- 下一步：执行已生成并审查的 `PF-P006-MG - Workbench Query Facade Merge Gate`。

## PF-P006-MG - Workbench Query Facade Merge Gate

状态：`verified`

### 目标

把 PF-P006 已 verified 的 Workbench Query Facade extraction 安全合入 `main`。本 prompt 是 Merge Gate，不是业务实现 prompt，也不是 Traffic Gate。它只负责范围审计、上游同步、精准提交、合并前后验证和状态机回写。

### Prompt

```text
/goal
执行 PF-P006-MG - Workbench Query Facade Merge Gate。

目标：将 PF-P006 已 verified 的 Workbench Query Facade extraction 安全合入 main。只处理 Merge Gate，不执行 Traffic Gate，不开始 Slice C，不修改业务行为。

Role:
你是一位精通 Python 后端重构、Git Merge Gate、Clean Architecture、测试门禁和生产变更风险控制的架构负责人。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P006 已 verified，已完成 Workbench query/read-model 的 Slice B：抽取 `WorkbenchQueryFacade`，薄化 summary / groups / group detail / refresh-status handler。PF-P006-MG 的职责是确认这些已 verified 变更可以进入 main；它不是 Traffic Gate，也不是下一轮业务重构 prompt。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/workbench-read-model-query-plan.md
- docs/architecture/backend-refactor/runtime-call-chain.md
- docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
- docs/architecture/backend-refactor/ai-execution-rules.md

必须确认：
- `migration-state-log.md` 中 `PF-P006 - Workbench Query Facade Extraction (Slice B)` 状态为 `verified`。
- 当前 active prompt 是 `PF-P006-MG - Workbench Query Facade Merge Gate`。
- 本轮是 Merge Gate，不是 Traffic Gate。
- 本轮不允许开始 Slice C，不允许修改 Workbench cache/freshness 语义、SSE、row detail、legacy `GET /api/workbench` 或写路径。

Allowed Scope:
- 允许做 Git 范围审计：
  - `git status --short --branch`
  - `git ls-files --others --exclude-standard`
  - `git diff --name-only`
  - `git diff --stat`
  - 必要时检查 `git diff -- <具体文件>`
- 允许提交并合并 PF-P006 已 verified 的变更。
- 允许更新：
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
- 允许在执行过程中因为状态机回写而产生文档小改动。
- 如果当前已经在 `main`，不得做无意义 merge；只做范围检查、必要 commit、验证和状态机更新。

Expected Changed Files:
本次合入范围只能包含以下文件：
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_query_facade.py`
- `tests/test_workbench_query_facade.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`

Verification-only files:
- `tests/test_workbench_sql_runtime.py` 只作为 PF-P005 characterization baseline 和 PF-P006-MG 验证目标，本轮不在 Expected Changed Files 白名单内。若该文件出现 changed / staged 状态，必须先阻断并审查原因；不得为了通过 Merge Gate 而临时加入白名单。

如果出现其它 changed 或 untracked 文件：
- 必须先判断是否属于 PF-P006 / PF-P006-MG。
- 临时文件、缓存文件、`.pkl`、`.sqlite`、`__pycache__`、测试输出、导出物、日志文件一律不得提交。
- 不得使用 `git add .` 或 `git add -A`。
- 只能用 `git add <具体文件>` 精准 staging。

Forbidden Scope:
- 不修改除 Expected Changed Files 以外的生产代码。
- 不修改 SQL migration。
- 不修改前端代码。
- 不修改 Nginx、Vite、Caddy、部署配置或生产配置。
- 不修改 `GET /api/workbench` legacy compatibility endpoint。
- 不修改 row detail fallback。
- 不修改 SSE / events 长连接行为。
- 不修改 worker refresh、builder、repository SQL。
- 不修改 Workbench 写路径，包括 confirm/cancel、ignore/unignore、exception apply/revert、reconciliation write、pair relation write。
- 不开始 Workbench matching/candidates 重构。
- 不开始 Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 或 Ops 模块迁移。
- 不执行 Traffic Gate。
- 不部署服务器。
- 不 push 到生产服务器。
- 不访问生产 DB、Redis、RabbitMQ、OA Mongo、OA MySQL、MinIO/S3。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产敏感 URL。
- 未经用户确认，不得把 PF-P006-MG 标记为 `verified`。

Upstream Sync Rule:
- 在 merge 到 main 前，必须确认 `main` 和 `origin/main` 关系。
- 必须先同步最新 `origin/main`。
- 如果当前工作分支不是基于最新 main，必须先把最新 main 合入或 rebase 到当前分支，并处理冲突。
- 如果同步了 main 的新提交，必须重新执行本 prompt 的 Mandatory Checks。
- 严禁在存在未解决冲突或未重跑验证时 merge 到 main。

Commit / Merge Rules:
- Commit message 建议使用：
  - `refactor(workbench): extract query read model facade`
- Commit body 必须说明：
  - PF-P006 新增 Workbench Query Facade，并薄化 summary / groups / group detail / refresh-status handler。
  - 本次只影响 Workbench query/read-model read path。
  - 未修改 SQL migration、前端、网关、部署配置或生产配置。
  - PF-P005 characterization tests、facade unit tests 和 platform guards 均已通过。
- 如果当前在 feature branch：
  1. 精准 staging 允许文件。
  2. commit。
  3. checkout main。
  4. pull / fast-forward 最新 origin/main。
  5. merge feature branch。
  6. 在 main 上重跑 Mandatory Checks。
- 如果当前已经在 main：
  - 不执行无意义 merge。
  - 完成范围检查、精准 staging、commit、Mandatory Checks 和状态机回写即可。
- Push 到 origin/main 需要用户明确允许；本 prompt 不默认 push。

Mandatory Checks:
- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --name-only`
- `git diff --stat`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- `git diff --quiet -- tests/test_workbench_sql_runtime.py` 必须通过；该文件本轮只允许作为验证目标，不允许作为变更文件。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- Row detail targeted tests：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_prefers_cached_read_model_before_query_service_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_prefers_month_read_model_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_without_cache_returns_404_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_row_detail_supports_oa_bank_and_invoice -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- Facade 上帝对象注入静态检查：
  - `rg -n "WorkbenchQueryFacade\\([^\\n]*(Application|RuntimeRepositories|RuntimeRepositoryContext|ApplicationStateStore|StateStoreProtocol|state_store)" backend/src/fin_ops_platform tests` 必须无输出。
- Facade mock 静态检查：
  - `rg -n "mock\\.patch\\(.+WorkbenchQueryFacade|patch\\(.+workbench_query_facade|monkeypatch.+WorkbenchQueryFacade|WorkbenchQueryFacade.*Mock|Mock.*WorkbenchQueryFacade" tests/test_workbench_sql_runtime.py` 必须无输出。
- Observability 边界静态检查：
  - `test ! -f backend/src/fin_ops_platform/services/workbench_query_facade.py || ! rg -n "request_database_timing" backend/src/fin_ops_platform/services/workbench_query_facade.py`
- 文档状态检查：
  - `rg -n "PF-P006|PF-P006-MG|状态：`verified`|状态：`planned`" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/workbench-read-model-query-plan.md`

Post-Flight:
- 更新 `migration-state-log.md`：
  - 记录 PF-P006-MG 执行结果。
  - 如果 commit / merge 已完成，记录 commit hash、merge 方式和 main 上验证结果。
  - 将 PF-P006-MG 状态设为 `implemented` 或 `blocked`，不得直接设为 `verified`。
  - 记录下一步建议：用户确认后标记 PF-P006-MG verified；随后用户决定是否 push origin/main 或生成 Slice C prompt。
- 更新 `refactor-prompts.md` 的 PF-P006-MG 状态和执行结果。
- 最终回复必须明确：
  - 是否只合入 PF-P006 expected files。
  - 是否修改了 SQL migration、前端、网关、部署或生产配置。
  - 是否已 commit、merge、push。
  - 哪些验证在 feature branch 和 main 上通过。
  - 是否执行 Traffic Gate。
  - 下一步建议做什么。
```

### Gate Scope

- Merge Gate：涉及。PF-P006-MG 只负责 PF-P006 已 verified 变更的 main 合入门禁。
- Traffic Gate：不涉及。PF-P006-MG 不切流、不部署、不修改网关、不改变 worker 启动方式。
- Test Gate：涉及。PF-P006-MG 必须在合入前后确认 facade unit tests、Workbench SQL runtime、row detail targeted tests、PF-P003 platform guards 和 `app.main --check` 通过。

### 审查结论

- PF-P006-MG 的边界正确：只处理 PF-P006 已 verified 变更的 merge gate，不开始 Slice C。
- Expected Changed Files 覆盖本轮实际变更：`server.py`、新增 facade、facade unit tests 和三份 backend-refactor 文档。
- Prompt 明确禁止 `git add .` / `git add -A`，要求精准 staging，并显式检查 untracked files。
- Prompt 保留 PF-P006 的三条核心静态门禁：禁止 Facade 上帝对象注入、禁止 mock facade 降级 characterization tests、禁止 `request_database_timing` 下沉 Facade。
- Prompt 包含 upstream sync rule；如果 main/origin/main 有新提交，必须同步并重跑 Mandatory Checks。
- Prompt 明确不执行 Traffic Gate、不部署服务器、不访问生产外部服务、不默认 push。
- PF-P006-MG 执行完成后只能到 `implemented` 或 `blocked`，必须等待用户确认才能 `verified`。

### 执行结果

- 已执行 PF-P006-MG，并由用户确认标记为 `verified`。
- Feature branch `codex/workbench-query-facade-prompt` 上精准 staging 了 Expected Changed Files，未使用 `git add .` 或 `git add -A`。
- 创建 commit：`8937bb15 refactor(workbench): extract query read model facade`。
- `main` 和 `origin/main` 执行前均为 `fd75f9ee`，通过 fast-forward 将 `8937bb15` 合入 `main`。
- 合入范围只包含 PF-P006 Expected Changed Files。
- 未修改 SQL migration、前端、网关、部署配置或生产配置。
- 未执行 Traffic Gate、未部署服务器；随后按用户确认已 push 到 `origin/main`。
- Feature branch 与 `main` 上均通过 mandatory checks：facade unit tests、compileall、`tests.test_workbench_sql_runtime`、`tests.test_platform_runtime_boundary_guards`、row detail targeted tests、`app.main --check`、`tests/test_workbench_sql_runtime.py` 无 diff 检查、Facade god-object injection 检查、Facade mock 检查、`request_database_timing` 边界检查。
- `git push origin main` 已通过，`origin/main` 从 `fd75f9ee` 更新到 `87d738de`。
- 下一步：审查并执行 `PF-P007 - Workbench Query Cache and Freshness Boundary (Slice C)`；不得直接开始 Slice D、Traffic Gate、部署或生产变更。

## PF-P007 - Workbench Query Cache and Freshness Boundary (Slice C)

状态：`verified`

### 目标

在 PF-P006 已抽出 `WorkbenchQueryFacade` 且 PF-P006-MG 已 verified / pushed 的基础上，执行 Workbench `query/read-model` 子域的 Slice C：收口 Read Model Repository / Cache / Freshness Boundary。目标是统一 active generation、source_version、Redis key、stale/refreshing 语义，并保持外部 API contract 不变。

### Prompt

```text
/goal
执行 PF-P007 - Workbench Query Cache and Freshness Boundary (Slice C)。

目标：在不改变 Workbench query/read-model API contract 的前提下，收口 cache 与 freshness 边界，统一 active generation、source_version、Redis key、stale/refreshing 语义。只做 Slice C，不执行 Merge Gate，不执行 Traffic Gate，不开始 Slice D。

Role:
你是一位精通 Python 后端、Read Model freshness、Redis 版本化缓存、Clean Architecture 和遗留系统 TDD 重构的架构工程师。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P005 characterization tests 已合入远端，PF-P006 已抽出 `WorkbenchQueryFacade` 并薄化 summary / groups / group detail / refresh-status handler，PF-P006-MG 已 verified 并 push 到 `origin/main`。PF-P007 对应 `workbench-read-model-query-plan.md` 的 Slice C：收口 Read Model Repository / Cache / Freshness Boundary。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/workbench-read-model-query-plan.md
- docs/architecture/backend-refactor/runtime-call-chain.md
- docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
- docs/architecture/backend-refactor/ai-execution-rules.md
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/services/workbench_query_facade.py
- tests/test_workbench_query_facade.py
- tests/test_workbench_sql_runtime.py

必须确认：
- `migration-state-log.md` 中 PF-P006-MG 状态为 `verified`。
- 当前 active prompt 是 `PF-P007 - Workbench Query Cache and Freshness Boundary (Slice C)`。
- 本轮是实现型 prompt，不是 Merge Gate，也不是 Traffic Gate。
- 本轮不允许开始 Slice D，不允许修改 legacy `GET /api/workbench` fallback、row detail fallback、SSE 断连行为、worker refresh、builder、repository SQL 重写或任何写路径。
- 如果当前在 `main`，必须先创建新分支，建议分支名：`codex/workbench-query-cache-freshness`。不得在 `main` 上直接实现业务代码。

Required Discovery:
执行前必须用代码和测试确认以下现状，并在执行结果中记录：
- Groups stale/refreshing 时是否仍绕过旧 Redis JSON payload。
- Fresh DB payload 是否仍会写入 Redis；如果会，判断它是否只在 freshness 通过后发生。
- Redis cache key 是否包含 active generation / read model version / schema version / detail_level / search / filter / sort 等必要维度。
- Summary / groups / group detail / refresh-status 的 stale/refreshing/unavailable 响应语义是否一致。
- API 是否只读取 active generation，不读取 building / failed generation。
- PF-P005 backend-only / contract-mismatch 字段是否仍被保留。

Allowed Scope:
- 允许新增或调整 Workbench query/read-model cache/freshness tests。
- 允许最小调整：
  - `backend/src/fin_ops_platform/services/workbench_query_facade.py`
  - 与 Workbench query cache/freshness 直接相关的细粒度 helper / fake / adapter 调度。
  - 必要时只做很小范围的 `server.py` 调用点修正，以保持 handler thin。
- 允许更新：
  - `tests/test_workbench_query_facade.py`
  - `tests/test_workbench_sql_runtime.py`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
  - `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- 必须先补测试，再实现；如果无法写出会失败的测试，必须记录原因并停止实现。

Required Test Work:
至少补齐以下测试或证明已有测试等价覆盖：
1. Redis freshness gating：
   - stale / refreshing / unavailable 时不得读取旧 Redis JSON payload 作为用户响应。
   - 只有 freshness 通过并成功读取 DB payload 后，才允许写入 Redis。
2. Redis cache key contract：
   - key 必须包含 active generation 或 read model version，以及 schema version、detail_level、search/filter/sort 等维度。
   - 不允许不同 freshness state、filter 或 detail level 共享同一 key。
3. Active generation boundary：
   - API 只读 active generation。
   - building / failed generation 只能出现在诊断或 refresh-status 元数据中，不能进入用户 payload。
4. Source version semantics：
   - source_versions stale 时返回 stale/refreshing contract，并 enqueue refresh。
   - 不得把过期 read model 包装成 fresh。
5. Contract preservation：
   - 保留 PF-P005 标记的 backend-only / contract-mismatch 字段。
   - 不删除 `TODO: PF-P006 verify safe to remove` 类字段或语义，除非另有专门 prompt。

Forbidden Scope:
- 不修改 SQL migration。
- 不修改前端代码。
- 不修改 Nginx、Vite、Caddy、部署配置或生产配置。
- 不修改 legacy `GET /api/workbench` fallback。
- 不修改 row detail fallback。
- 不修改 SSE / events 长连接行为。
- 不修改 worker refresh、builder、repository SQL 重写、RabbitMQ、Outbox、Dirty Scope 事实源。
- 不修改 Workbench 写路径，包括 confirm/cancel、ignore/unignore、exception apply/revert、reconciliation write、pair relation write。
- 不开始 Slice D 或 Workbench matching/candidates 重构。
- 不开始 Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 或 Ops 模块迁移。
- 不执行 Traffic Gate。
- 不部署服务器。
- 不 push 到 `origin/main`。
- 不访问生产 DB、Redis、RabbitMQ、OA Mongo、OA MySQL、MinIO/S3。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产敏感 URL。
- 未经用户确认，不得把 PF-P007 标记为 `verified`。

Mandatory Checks:
- `git status --short --branch`
- `git diff --name-only`
- `git diff --stat`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- Row detail targeted tests：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_prefers_cached_read_model_before_query_service_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_prefers_month_read_model_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_without_cache_returns_404_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_row_detail_supports_oa_bank_and_invoice -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- Facade 上帝对象注入静态检查：
  - `rg -n "WorkbenchQueryFacade\\([^\\n]*(Application|RuntimeRepositories|RuntimeRepositoryContext|ApplicationStateStore|StateStoreProtocol|state_store)" backend/src/fin_ops_platform tests` 必须无输出。
- Facade mock 静态检查：
  - `rg -n "mock\\.patch\\(.+WorkbenchQueryFacade|patch\\(.+workbench_query_facade|monkeypatch.+WorkbenchQueryFacade|WorkbenchQueryFacade.*Mock|Mock.*WorkbenchQueryFacade" tests/test_workbench_sql_runtime.py` 必须无输出。
- Observability 边界静态检查：
  - `test ! -f backend/src/fin_ops_platform/services/workbench_query_facade.py || ! rg -n "request_database_timing" backend/src/fin_ops_platform/services/workbench_query_facade.py`
- 文档状态检查：
  - `rg -n "PF-P006-MG|PF-P007|状态：`verified`|状态：`planned`" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/workbench-read-model-query-plan.md`

Post-Flight:
- 更新 `migration-state-log.md`：
  - 记录 PF-P007 执行结果。
  - 记录变更文件、测试命令和结果、发现的 cache/freshness 事实、风险和下一步建议。
  - 将 PF-P007 状态设为 `implemented` 或 `blocked`，不得直接设为 `verified`。
- 更新 `refactor-prompts.md` 的 PF-P007 状态和执行结果。
- 更新 `workbench-read-model-query-plan.md` 的 Slice C 执行结果和 Slice D 输入。
- 最终回复必须明确：
  - 是否只修改了 Slice C 范围内文件。
  - 是否修改了 SQL migration、前端、网关、部署或生产配置。
  - 是否执行 Traffic Gate。
  - 哪些验证通过。
  - 下一步建议做什么。
```

### Gate Scope

- Merge Gate：不涉及。PF-P007 只实现并验证，不 commit/merge 到 `main`。
- Traffic Gate：不涉及。PF-P007 不切流、不部署、不修改网关或 worker 启动方式。
- Test Gate：涉及。PF-P007 必须先补 cache/freshness tests，再做最小实现，并保留 PF-P005/PF-P006/PF-P003 既有门禁。

### 审查结论

- PF-P007 的边界正确：它只处理 Slice C 的 cache/freshness boundary，不开始 Slice D。
- Prompt 明确要求在非 `main` 分支执行，避免在主干直接做业务代码重构。
- Prompt 继承了 PF-P006 的 Facade 边界：禁止上帝对象注入、禁止 mock facade 降级 characterization tests、禁止把 `request_database_timing` 下沉到 facade。
- Prompt 明确保留 PF-P005 backend-only / contract-mismatch 字段，不允许借 Slice C 清理 API contract。
- Prompt 明确不修改 SQL migration、前端、网关、部署配置、worker、builder、写路径，不执行 Traffic Gate。
- PF-P007 执行完成后只能到 `implemented` 或 `blocked`，必须等待用户确认才能 `verified`。

### 执行结果

- 执行分支：`codex/workbench-query-cache-freshness`。
- 状态：`implemented`，等待用户确认，不得直接标记 `verified`。
- 测试先行：新增 facade unit test 复现 refresh-status 为 `refreshing` 时仍写 Redis payload 的缺口。
- 实现：`WorkbenchQueryFacade.groups(...)` 只有在 freshness gate 允许使用 groups Redis cache 且 DB payload 为 fresh 时才写 Redis JSON payload。
- HTTP characterization 更新：stale / refreshing refresh-status 下不读取旧 Redis JSON payload，也不把 fresh-looking DB payload 写入 Redis。
- TTL 评估：版本化 key 已具备 immutable cache 语义，但本轮保留现有 bounded TTL，避免缺少 Redis memory / cardinality 指标时改变运行时驻留策略。
- 未修改 SQL migration、前端、网关、部署配置、生产配置、SSE、worker、builder、repository SQL 或 Workbench 写路径。
- 用户已确认 PF-P007 verified。
- 后续：执行已生成并审查的 `PF-P007-MG - Workbench Query Cache and Freshness Merge Gate`。

## PF-P007-MG - Workbench Query Cache and Freshness Merge Gate

状态：`verified`

### 目标

将 PF-P007 已 verified 的 Workbench query cache/freshness gate 改动，以及同分支内同步固化的 prompt/实现分支共址工作流文档，安全合入 `main`。本 prompt 只处理 Merge Gate，不执行 Traffic Gate，不部署服务器，不开始 Slice D。

### Prompt

```text
/goal
执行 PF-P007-MG - Workbench Query Cache and Freshness Merge Gate。

目标：只处理 PF-P007 已 verified 变更进入 `main` 的 Merge Gate。确认变更范围、复跑关键测试、精准 commit、同步最新 main、合入 main 并在 main 上复验。不得执行 Traffic Gate，不得部署服务器，不得开始 Slice D 或任何新的业务重构。

Role:
你是一位严格执行 Git merge gate、测试门禁、范围审计和 Python 后端重构交付纪律的资深工程师。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P007 已由用户确认 verified，完成 Workbench query/read-model 的 Slice C：stale / refreshing / unavailable freshness gate 未通过时，不读取旧 Redis JSON payload，也不把 fresh-looking DB payload 写入 Redis。当前分支还包含用户要求固化的“prompt / 状态机 / 实现 / Merge Gate 同分支，MG 合入 main 后从最新 main 新建下一分支”的工作流文档修正。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/workbench-read-model-query-plan.md
- docs/architecture/backend-refactor/ai-execution-rules.md
- backend/src/fin_ops_platform/services/workbench_query_facade.py
- tests/test_workbench_query_facade.py
- tests/test_workbench_sql_runtime.py

必须确认：
- `migration-state-log.md` 中 PF-P007 状态为 `verified`。
- 当前 active prompt 是 `PF-P007-MG - Workbench Query Cache and Freshness Merge Gate`。
- 当前分支必须是 `codex/workbench-query-cache-freshness` 或同一 PF-P007 功能分支；不得在 `main` 上直接执行 merge gate 准备。
- 本轮只处理 Merge Gate，不是 Traffic Gate。
- 本轮不允许开始 Slice D，不允许修改 legacy `GET /api/workbench` fallback、row detail fallback、SSE、worker refresh、builder、repository SQL 重写或任何写路径。

Expected Changed Files:
本轮允许合入的文件仅限：
- backend/src/fin_ops_platform/services/workbench_query_facade.py
- tests/test_workbench_query_facade.py
- tests/test_workbench_sql_runtime.py
- docs/architecture/backend-refactor/ai-execution-rules.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/workbench-read-model-query-plan.md

如出现其它 changed / staged / untracked 文件，必须阻断并说明来源；不得临时扩大白名单。

Required Scope Checks:
1. 确认代码 diff 只做了 PF-P007 cache/freshness gate：
   - `WorkbenchQueryFacade.groups(...)` 只有在 freshness gate 允许使用 groups Redis cache 且 payload 为 fresh 时才写 Redis JSON payload。
   - stale / refreshing / unavailable 时不读取旧 Redis JSON payload，也不写入新的 Redis JSON payload。
2. 确认文档 diff 只记录：
   - PF-P007 verified / PF-P007-MG planned。
   - PF-P007 执行结果、测试结果和 TTL 决策。
   - prompt/状态机/实现/Merge Gate 同分支工作流。
3. 确认没有修改：
   - SQL migration。
   - 前端代码。
   - Nginx、Vite、Caddy、部署配置或生产配置。
   - SSE / worker / builder / repository SQL。
   - Workbench 写路径。

Mandatory Checks Before Commit:
- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --name-only`
- `git diff --stat`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- Row detail targeted tests：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_prefers_cached_read_model_before_query_service_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_prefers_month_read_model_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_without_cache_returns_404_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_row_detail_supports_oa_bank_and_invoice -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- Facade 上帝对象注入静态检查：
  - `rg -n "WorkbenchQueryFacade\\([^\\n]*(Application|RuntimeRepositories|RuntimeRepositoryContext|ApplicationStateStore|StateStoreProtocol|state_store)" backend/src/fin_ops_platform tests` 必须无输出。
- Facade mock 静态检查：
  - `rg -n "mock\\.patch\\(.+WorkbenchQueryFacade|patch\\(.+workbench_query_facade|monkeypatch.+WorkbenchQueryFacade|WorkbenchQueryFacade.*Mock|Mock.*WorkbenchQueryFacade" tests/test_workbench_sql_runtime.py` 必须无输出。
- Observability 边界静态检查：
  - `test ! -f backend/src/fin_ops_platform/services/workbench_query_facade.py || ! rg -n "request_database_timing" backend/src/fin_ops_platform/services/workbench_query_facade.py`

Commit / Merge Preparation:
- 严禁使用 `git add .` 或 `git add -A`。
- 必须精准 staging Expected Changed Files。
- 建议 commit message：
  - `refactor(workbench): enforce query cache freshness gate`
- commit 前后都必须确认 `git status --short --branch`。
- commit 后执行 `git fetch origin main`。
- merge 到 `main` 前必须确认当前分支包含最新 `origin/main`；如果 `origin/main` 有新提交，必须先 rebase 或 merge 最新 main 到当前分支，解决冲突后重新运行 Mandatory Checks。
- 切到 `main` 后先确认 `main` 与 `origin/main` 关系；不得覆盖远端主干。
- 合入 `main` 后必须在 `main` 上重新运行 Mandatory Checks。

Forbidden Scope:
- 不执行 Traffic Gate。
- 不部署服务器。
- 不 push 到 `origin/main`，除非用户在 PF-P007-MG 执行期间明确允许。
- 不修改生产配置或网关配置。
- 不开始 Slice D 或任何新业务模块重构。
- 不访问生产 DB、Redis、RabbitMQ、OA Mongo、OA MySQL、MinIO/S3。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产敏感 URL。
- 未经用户确认，不得把 PF-P007-MG 标记为 `verified`。

Post-Flight:
- 更新 `migration-state-log.md`：
  - 记录 PF-P007-MG 执行结果。
  - 记录 commit、merge 方式、变更范围、验证命令和结果。
  - 将 PF-P007-MG 状态设为 `implemented` 或 `blocked`，不得直接设为 `verified`。
  - 记录下一步建议：用户确认后标记 PF-P007-MG verified；push origin/main 需要用户明确确认；下一条 prompt 必须从最新 main 新建分支生成。
- 更新 `refactor-prompts.md` 的 PF-P007-MG 状态和执行结果。
- 必要时更新 `workbench-read-model-query-plan.md`，但不得开始 Slice D 设计或实现。
- 最终回复必须明确：
  - 是否只合入 Expected Changed Files。
  - 是否修改了 SQL migration、前端、网关、部署或生产配置。
  - 是否执行 Traffic Gate。
  - 哪些验证在 feature branch 和 main 上通过。
  - 是否 push 到 origin/main。
  - 下一步建议做什么。
```

### Gate Scope

- Merge Gate：涉及。PF-P007-MG 只负责 PF-P007 已 verified 变更的 main 合入门禁。
- Traffic Gate：不涉及。PF-P007-MG 不切流、不部署、不修改网关、不改变 worker 启动方式。
- Test Gate：涉及。PF-P007-MG 必须在合入前后确认 facade unit tests、Workbench SQL runtime、row detail targeted tests、PF-P003 platform guards 和 `app.main --check` 通过。

### 审查结论

- PF-P007-MG 的边界正确：只处理 PF-P007 cache/freshness gate 与同分支工作流文档修正的合入。
- Expected Changed Files 已包含本分支真实变更：facade、两个 Workbench 测试文件、三份状态/prompt/计划文档，以及 `ai-execution-rules.md`。
- Prompt 明确禁止 Traffic Gate、部署、push origin/main 默认执行、Slice D 和任何新业务重构。
- Prompt 保留 PF-P006/PF-P007 的关键门禁：上帝对象注入、mock facade、observability wrapper 边界、Redis freshness gate。
- Prompt 明确了 untracked 文件检查、精准 staging、禁止 `git add .`、上游同步和 main 上复验。
- PF-P007-MG 执行完成后只能到 `implemented` 或 `blocked`，必须等待用户确认才能 `verified`。

### 执行结果

- 状态：`verified`，已由用户确认。
- Feature branch：`codex/workbench-query-cache-freshness`。
- Commit：`08ccad92 refactor(workbench): enforce query cache freshness gate`。
- Merge 方式：`main` fast-forward 合入 `08ccad92`；`git push origin main` 已通过。
- 合入范围只包含 Expected Changed Files。
- Feature branch mandatory checks 全部通过。
- main 上 mandatory checks 全部通过。
- 未执行 Traffic Gate，未部署服务器。
- 后续：下一条 prompt 必须从最新 `main` 新建分支生成，不得在 `main` 或旧功能分支继续实现 Slice D。

## PF-P008 - Workbench Query Fallback / SSE / Observability Characterization (Slice D-A)

状态：`verified`

### 目标

生成 Workbench Query Slice D 的第一步测试锁定 prompt。PF-P008 只补充或整理 characterization tests 与文档，锁定 legacy `GET /api/workbench` fallback、row detail fallback、SSE 长连接行为和观测性基线；不做生产代码优化，不删除 fallback，不修改 SSE 行为。

### Prompt

```text
/goal
执行 PF-P008 - Workbench Query Fallback / SSE / Observability Characterization (Slice D-A)。

目标：只为 Workbench Query Slice D 增加和整理 characterization tests，锁定当前 fallback、SSE 和 observability 行为，为后续逐项优化提供安全网。不得直接优化或删除 fallback，不得修改生产代码。

Role:
你是一位精通 Python 遗留系统 characterization testing、Read Model freshness、SSE 长连接测试、可观测性基线和 Clean Architecture 的资深后端工程师。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P005 已建立 Workbench query/read-model characterization tests；PF-P006 已抽出 `WorkbenchQueryFacade` 并薄化 summary / groups / group detail / refresh-status handler；PF-P007 已收口 groups Redis cache/freshness gate；PF-P007-MG 已 verified 并同步到 `origin/main`。当前进入 Slice D 的第一步，但本 prompt 只做测试锁定，不实现 fallback 优化。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/workbench-read-model-query-plan.md
- docs/architecture/backend-refactor/runtime-call-chain.md
- docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
- docs/architecture/backend-refactor/read-model-and-external-services.md
- docs/architecture/backend-refactor/ai-execution-rules.md
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/services/workbench_query_facade.py
- backend/src/fin_ops_platform/services/live_workbench_service.py
- backend/src/fin_ops_platform/services/workbench_query_service.py
- tests/test_workbench_sql_runtime.py
- tests/test_workbench_v2_api.py
- tests/test_workbench_query_facade.py
- tests/test_api_performance_metrics.py
- web/src/features/workbench/api.ts
- web/src/features/workbench/types.ts

必须确认：
- `migration-state-log.md` 中 PF-P007-MG 状态为 `verified`。
- 当前 active prompt 是 `PF-P008 - Workbench Query Fallback / SSE / Observability Characterization (Slice D-A)`。
- 当前分支必须是 `codex/workbench-query-slice-d-prompt` 或同一 PF-P008 功能分支；不得在 `main` 上执行。
- 本轮是 characterization-test prompt，不是业务实现 prompt、不是 Merge Gate、不是 Traffic Gate。
- 本轮不得修改生产代码；如果发现必须改生产代码才能测试，必须停止并记录为 blocked。

Required Discovery:
执行前必须用代码、CodeGraph 或 targeted search 确认并在执行结果中记录：
1. Legacy `GET /api/workbench`：
   - `_handle_api_workbench(...)`。
   - `_handle_api_workbench_from_sql_read_model(...)`。
   - `_build_api_workbench_payload(...)`。
   - `_requires_sql_read_model_runtime()` 和 `api_sql_repository_unavailable` refresh enqueue 行为。
2. Row detail：
   - `_handle_api_workbench_row_detail(...)`。
   - `_get_api_workbench_row_detail_payload(...)`。
   - `LiveWorkbenchService.get_row_detail(...)`。
   - `_resolve_rows_from_cached_read_models(...)`。
   - `_workbench_api_routes.get_row_detail(...)`。
   - `_workbench_override_service.apply_to_row(...)` 应用顺序。
3. SSE：
   - `_handle_api_workbench_events(...)`。
   - `_workbench_refresh_status_payload_for_scope(...)`。
   - `_workbench_refresh_status_event_name(...)`。
   - `AppHealthService.serialize_sse_event(...)`。
   - 当前 SSE 是 polling refresh status，不是 Redis PubSub。
4. Observability：
   - `Application.handle_request(...)` 的 `request_database_timing()` 包裹。
   - `ApiPerformanceRecorder.record_request(...)`。
   - Workbench query path 是否在 app shell 层保留 route/method/status/database timing。

Allowed Scope:
- 允许新增或调整 Workbench query/read-model characterization tests。
- 优先修改：
  - `tests/test_workbench_sql_runtime.py`
  - `tests/test_workbench_v2_api.py`
  - `tests/test_api_performance_metrics.py`（仅当需要补 app-shell observability 基线）
- 允许更新文档：
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
  - `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- 允许复用现有 fake repository、fake Redis、fake queue、patch helpers。
- 允许在测试中用 bounded generator、patched sleep 或手动关闭 stream 来锁定当前 SSE 可测试行为。

Required Test Work:
至少补齐以下测试或证明已有测试等价覆盖，并在 Post-Flight 中逐项记录：
1. Legacy `GET /api/workbench` compatibility：
   - SQL read model hit 时必须直接返回 SQL payload，且不得调用 legacy builder。
   - SQL read model missing 时必须 enqueue refresh 并返回 `202 refreshing`。
   - PostgreSQL production runtime / require SQL read model 时，repository 不可用不得 fallback legacy builder，必须返回 `503 read_model_unavailable` 并 enqueue `api_sql_repository_unavailable`。
   - legacy / non-production runtime 下当前允许 fallback legacy builder 的行为必须被明确锁定，不能在本轮改掉。
2. Row detail fallback：
   - 优先使用 `LiveWorkbenchService.get_row_detail(...)`。
   - live miss 后优先读取 cached read model。
   - opaque OA row id 在没有 cached read model 时不得触发 full OA sync，必须保持 404/KeyError 行为。
   - route service fallback 的触发条件必须被锁定。
   - `apply_to_row(...)` 必须在最终 payload 返回前应用一次，且字段完整度保持当前契约。
3. SSE characterization：
   - Response 必须保留 `Content-Type: text/event-stream`、`Cache-Control: no-cache, no-transform`、`Connection: keep-alive`、`X-Accel-Buffering: no`。
   - 必须锁定至少一个 refresh status event 和一个 `heartbeat` event 的格式。
   - event name mapping 必须覆盖 fresh / refreshing / stale / failed 或记录已有测试覆盖。
   - 必须确认当前 SSE 不使用 Redis PubSub；不得新增 PubSub。
   - 如无法可靠测试客户端断开后的 generator cancellation，不得改生产代码，只能在 `workbench-read-model-query-plan.md` 记录为后续实现风险。
4. Observability baseline：
   - Workbench query request 经过 `Application.handle_request(...)` 时，`ApiPerformanceRecorder` 能记录 method、route path、status code、duration 和 database timing。
   - `request_database_timing` 必须仍在 app shell 层，不得移动到 `WorkbenchQueryFacade`。
   - 不要求本轮新增细粒度 SQL 子查询标签；只锁定当前 app-shell 观测基线和缺口。
5. Contract preservation：
   - PF-P005 标记的 backend-only / contract-mismatch 字段必须继续保留。
   - 不得因为写测试而清理字段、改 response shape 或改前端 mapper。

Forbidden Scope:
- 不修改生产代码，包括 `backend/src/fin_ops_platform/app/server.py`、`workbench_query_facade.py`、`live_workbench_service.py`、`workbench_query_service.py`。
- 不修改 SQL migration。
- 不修改前端代码。
- 不修改 Nginx、Vite、Caddy、部署配置或生产配置。
- 不删除 legacy `GET /api/workbench` fallback。
- 不收口 row detail fallback。
- 不改变 SSE event stream、sleep interval、headers、heartbeat、event names 或 cancellation 行为。
- 不修改 worker refresh、builder、repository SQL 重写、RabbitMQ、Outbox、Dirty Scope 事实源。
- 不修改 Workbench 写路径，包括 confirm/cancel、ignore/unignore、exception apply/revert、reconciliation write、pair relation write。
- 不开始 Workbench matching/candidates、Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 或 Ops 模块迁移。
- 不执行 Merge Gate。
- 不执行 Traffic Gate。
- 不部署服务器。
- 不 push 到 `origin/main`。
- 不访问生产 DB、Redis、RabbitMQ、OA Mongo、OA MySQL、MinIO/S3。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产敏感 URL。
- 未经用户确认，不得把 PF-P008 标记为 `verified`。

Mandatory Checks:
- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --name-only`
- `git diff --stat`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- Row detail targeted tests：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_prefers_cached_read_model_before_query_service_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_prefers_month_read_model_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_without_cache_returns_404_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_row_detail_supports_oa_bank_and_invoice -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_api_performance_metrics -v`
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- Production code immutability check：
  - `test -z "$(git diff --name-only -- backend/src/fin_ops_platform web postgres deploy)"`
  - 必须确认生产代码、前端、migration、deploy 没有 diff；本轮只允许测试和文档变化。
- Facade 上帝对象注入静态检查：
  - `rg -n "WorkbenchQueryFacade\\([^\\n]*(Application|RuntimeRepositories|RuntimeRepositoryContext|ApplicationStateStore|StateStoreProtocol|state_store)" backend/src/fin_ops_platform tests` 必须无输出。
- Facade mock 静态检查：
  - `rg -n "mock\\.patch\\(.+WorkbenchQueryFacade|patch\\(.+workbench_query_facade|monkeypatch.+WorkbenchQueryFacade|WorkbenchQueryFacade.*Mock|Mock.*WorkbenchQueryFacade" tests/test_workbench_sql_runtime.py` 必须无输出。
- Observability 边界静态检查：
  - `test ! -f backend/src/fin_ops_platform/services/workbench_query_facade.py || ! rg -n "request_database_timing" backend/src/fin_ops_platform/services/workbench_query_facade.py`

Post-Flight:
- 更新 `migration-state-log.md`：
  - 记录 PF-P008 执行结果。
  - 记录变更文件、测试命令和结果、fallback/SSE/observability 事实、风险和下一步建议。
  - 将 PF-P008 状态设为 `implemented` 或 `blocked`，不得直接设为 `verified`。
- 更新 `refactor-prompts.md` 的 PF-P008 状态和执行结果。
- 更新 `workbench-read-model-query-plan.md` 的 Slice D-A 测试锁定结果和后续 Slice D-B 实现输入。
- 最终回复必须明确：
  - 是否只修改了测试和文档。
  - 是否修改了生产代码、SQL migration、前端、网关、部署或生产配置。
  - 是否执行 Merge Gate 或 Traffic Gate。
  - 哪些验证通过。
  - 哪些 Slice D 风险仍未关闭。
  - 下一步建议做什么。
```

### Gate Scope

- Merge Gate：不涉及。PF-P008 只生成和执行 characterization tests，不 commit/merge 到 `main`。
- Traffic Gate：不涉及。PF-P008 不切流、不部署、不修改网关、不改变 SSE 代理配置。
- Test Gate：涉及。PF-P008 必须先锁定 legacy fallback、row detail fallback、SSE 和 observability 当前行为，再允许后续实现型 prompt 缩小风险。

### 审查结论

- PF-P008 边界正确：它把 Slice D 拆成“先测试锁定，再实现优化”的生产级流程，避免直接删除 legacy path 或改 SSE。
- Prompt 明确禁止生产代码变更，因此不会在本轮改变用户可见行为。
- Prompt 覆盖 Slice D 的四个高风险点：legacy `GET /api/workbench` fallback、row detail 多级 fallback、SSE 长连接 / heartbeat / no-buffering header、app-shell observability。
- Prompt 保留 PF-P005/PF-P006/PF-P007 约束：不删 backend-only 字段、不 mock facade 降级黑盒测试、不把 `request_database_timing` 下沉到 facade。
- Prompt 明确不执行 Merge Gate、Traffic Gate、部署或 push。
- PF-P008 执行完成后只能到 `implemented` 或 `blocked`，必须等待用户确认才能 `verified`。

### 执行结果

- 状态：`verified`，已由用户确认。
- 执行分支：`codex/workbench-query-slice-d-prompt`。
- 变更文件：
  - `tests/test_workbench_sql_runtime.py`
  - `tests/test_api_performance_metrics.py`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
  - `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- 新增测试：
  - `test_workbench_events_stream_maps_statuses_without_redis_pubsub`
  - `test_row_detail_prefers_live_service_and_applies_override_without_fallback`
  - `test_row_detail_route_fallback_applies_override_after_live_and_cache_miss`
  - `test_application_handle_request_records_workbench_route_and_database_timing`
- 已有测试继续锁定 legacy `GET /api/workbench` SQL hit / miss / production unavailable / legacy fallback 行为，以及 opaque OA row detail 不触发 full OA sync。
- 未修改生产代码、SQL migration、前端、网关、部署或生产配置。
- 未执行 Merge Gate，未执行 Traffic Gate，未 push `origin/main`。
- 后续：不单独执行 PF-P008-MG；用户明确允许在同一功能分支继续生成 Slice D-B 实现 prompt。后续 PF-P009-MG 必须统一覆盖 PF-P008 测试基线与 PF-P009 生产代码变更。

## PF-P009 - Workbench Query Fallback and SSE Mitigation (Slice D-B)

状态：`verified`

### 目标

生成 Workbench Query Slice D 的第二步实现 prompt。PF-P009 在 PF-P008 已 verified 的测试护城河下，逐项缩小 legacy `GET /api/workbench` fallback、row detail fallback 和 SSE streaming generator 资源风险；不得一次性删除 legacy path，不得改变 API response contract，不执行 Merge Gate 或 Traffic Gate。

### Prompt

```text
/goal
执行 PF-P009 - Workbench Query Fallback and SSE Mitigation (Slice D-B)。

目标：在 PF-P008 已 verified 的 characterization tests 保护下，逐项收口 Workbench Query fallback 与 SSE 资源风险。必须保持现有 API response contract、status code、freshness 语义、row detail 字段完整度、SSE event name / header / heartbeat 契约；不得一次性删除 legacy path。

Role:
你是一位精通 Python 遗留系统渐进式重构、Read Model freshness、SSE streaming、Clean Architecture、TDD 和生产风险控制的资深后端工程师。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P005 已建立 Workbench query/read-model characterization baseline；PF-P006 已抽取 `WorkbenchQueryFacade`；PF-P007 已收口 groups cache/freshness gate；PF-P008 已由用户确认 verified，补齐 legacy fallback、row detail fallback、SSE 和 observability characterization tests。PF-P008 尚未单独合入 main，用户明确允许在同一功能分支继续 Slice D-B；后续如需合入 main，必须由 PF-P009-MG 统一覆盖 PF-P008 + PF-P009 的完整差异。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/workbench-read-model-query-plan.md
- docs/architecture/backend-refactor/runtime-call-chain.md
- docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
- docs/architecture/backend-refactor/read-model-and-external-services.md
- docs/architecture/backend-refactor/ai-execution-rules.md
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/services/workbench_query_facade.py
- backend/src/fin_ops_platform/services/live_workbench_service.py
- backend/src/fin_ops_platform/services/workbench_query_service.py
- backend/src/fin_ops_platform/services/api_performance_metrics.py
- tests/test_workbench_sql_runtime.py
- tests/test_workbench_v2_api.py
- tests/test_workbench_query_facade.py
- tests/test_api_performance_metrics.py

必须确认：
- 当前分支是 `codex/workbench-query-slice-d-prompt` 或同一 Slice D 功能分支；不得在 `main` 上执行。
- `migration-state-log.md` 中 PF-P008 状态为 `verified`。
- 当前 active prompt 是 `PF-P009 - Workbench Query Fallback and SSE Mitigation (Slice D-B)`。
- PF-P008 的测试变更尚未单独合入 main；本轮完成后必须由 PF-P009-MG 统一处理 main 合入。
- 本轮是实现型 prompt，不是 Merge Gate，不是 Traffic Gate。
- 执行前必须先跑 PF-P008 关键 tests，确认测试护城河当前为绿。

Required Discovery:
执行前必须用 CodeGraph 或 targeted source reading 确认以下真实调用链，并在执行结果中记录：
1. Legacy `GET /api/workbench`：
   - `_handle_api_workbench(...)`
   - `_handle_api_workbench_from_sql_read_model(...)`
   - `_requires_sql_read_model_runtime()`
   - `_enqueue_workbench_read_model_refresh(...)`
   - `_build_api_workbench_payload(...)`
   - 当前 SQL hit / SQL missing / production unavailable / legacy fallback 的分支条件。
2. Row detail：
   - `_handle_api_workbench_row_detail(...)`
   - `_get_api_workbench_row_detail_payload(...)`
   - `LiveWorkbenchService.get_row_detail(...)`
   - `_resolve_rows_from_cached_read_models(...)`
   - `_workbench_api_routes.get_row_detail(...)`
   - `_workbench_override_service.apply_to_row(...)`
   - opaque OA row id、month hint、cached read model miss 与 route fallback 的真实触发条件。
3. SSE：
   - `_handle_api_workbench_events(...)`
   - `_workbench_refresh_status_payload_for_scope(...)`
   - `_workbench_refresh_status_event_name(...)`
   - `AppHealthService.serialize_sse_event(...)`
   - 当前 generator sleep / heartbeat / finite test loop / client close 的可测试边界。
4. Observability：
   - `Application.handle_request(...)`
   - `request_database_timing()`
   - `ApiPerformanceRecorder.record_request(...)`
   - 确认 `request_database_timing` 仍属于 app shell 层，不能下沉到 facade。

TDD / Safety Net:
1. 先运行 PF-P008 已验证测试，确认当前基线为绿。
2. 对每个将要改变的行为，必须先新增或调整 targeted failing test；如果现有 PF-P008 test 已足够覆盖，必须在执行结果中说明“不需要新增测试”的原因。
3. 不得通过 mock 掉 `WorkbenchQueryFacade` 来绕开 HTTP handler -> facade -> repository/service fake 的真实链路。
4. 不得删除 PF-P008 对 fallback 顺序、SSE event mapping、observability baseline 的断言。

Allowed Scope:
- 允许最小范围修改：
  - `backend/src/fin_ops_platform/app/server.py`
  - `backend/src/fin_ops_platform/services/workbench_query_facade.py`（仅当 fallback policy 或 facade 边界确实需要）
  - `tests/test_workbench_sql_runtime.py`
  - `tests/test_workbench_v2_api.py`
  - `tests/test_workbench_query_facade.py`
  - `tests/test_api_performance_metrics.py`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
  - `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- 允许抽取小型 helper 来表达 fallback policy，但必须保持局部、可读、可测。
- 允许在 production PostgreSQL runtime / require SQL read model 条件下进一步禁止请求线程调用 legacy builder。
- 允许收紧 row detail fallback 触发条件，使 opaque OA row id、缺少 active/read-model 上下文的请求不会触发昂贵 full sync 或不透明 route fallback。
- 允许给 SSE generator 增加 `GeneratorExit` / `close()` / cancellation cleanup 的最小处理；如果当前 HTTP server abstraction 无法可靠感知客户端断开，必须记录为 limitation，不得伪造已解决。
- 允许保留既有 `X-Accel-Buffering: no`、heartbeat 和 event name mapping，并只修复资源释放边界。
- 允许补低基数 observability 记录，但不得引入新监控系统或高基数字段。

Required Implementation Work:
至少完成或证明无需改动以下项，并在 Post-Flight 中逐项记录：
1. Legacy `GET /api/workbench` fallback mitigation：
   - production PostgreSQL runtime / `_requires_sql_read_model_runtime()` 为 true 时，不得在 SQL read model missing 或 repository unavailable 时调用 legacy builder。
   - SQL missing 必须继续 enqueue refresh 并返回当前契约中的 `202 refreshing`。
   - repository unavailable 必须继续返回当前契约中的 `503 read_model_unavailable` 并 enqueue `api_sql_repository_unavailable`。
   - legacy / non-production runtime 的兼容 fallback 不得一次性删除；如保留，必须有显式 policy 和 tests。
2. Row detail fallback mitigation：
   - 保持 live service hit 优先。
   - cached read model miss 后，只允许在明确安全的条件下进入 route fallback。
   - opaque OA row id 无 cached read model 时不得触发 full OA sync。
   - `apply_to_row(...)` 必须仍只对最终 payload 应用一次。
   - 不得丢失 backend-only / contract-mismatch 字段。
3. SSE mitigation：
   - 保持 SSE headers、heartbeat、event name mapping 和 polling refresh status 语义。
   - 不引入 Redis PubSub。
   - 给 streaming generator 增加可测试的 close / cancellation cleanup；如果不可实现，必须在计划文档中记录 limitation 和后续 Traffic/infra 前置条件。
   - 不改变 sleep interval，除非 tests 和文档明确证明不会改变前端体验。
4. Observability preservation：
   - `request_database_timing` 必须留在 `Application.handle_request(...)` app shell 层。
   - Workbench query route 的 `ApiPerformanceRecorder` 基线必须继续通过。
   - 如新增模块级指标，只能使用低基数字段，不得记录 user id、OA token、cookie、原始 SQL 或敏感数据。

Forbidden Scope:
- 不修改 SQL migration。
- 不修改前端代码。
- 不修改 Nginx、Vite、Caddy、部署配置或生产配置。
- 不修改 worker refresh、read model builder、read model repository SQL、RabbitMQ、Outbox、Dirty Scope 事实源。
- 不修改 Workbench 写路径，包括 confirm/cancel、ignore/unignore、exception apply/revert、reconciliation write、pair relation write。
- 不开始 Workbench matching/candidates、Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 或 Ops 模块迁移。
- 不把 `request_database_timing` 移入 `WorkbenchQueryFacade`。
- 不把 `Application`、`RuntimeRepositories`、`ApplicationStateStore`、`StateStoreProtocol` 或其他上帝对象注入 facade。
- 不用 `mock.patch` 屏蔽 `WorkbenchQueryFacade` 来让测试通过。
- 不删除 legacy `GET /api/workbench` fallback 的所有兼容路径；本轮只允许按 policy 收口。
- 不改变 SSE event name、payload shape、headers 或 heartbeat contract。
- 不执行 Merge Gate。
- 不执行 Traffic Gate。
- 不部署服务器。
- 不 push 到 `origin/main`。
- 不访问生产 DB、Redis、RabbitMQ、OA Mongo、OA MySQL、MinIO/S3。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产敏感 URL。
- 未经用户确认，不得把 PF-P009 标记为 `verified`。

Mandatory Checks:
- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --name-only`
- `git diff --stat`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- Row detail targeted tests：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_prefers_cached_read_model_before_query_service_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_prefers_month_read_model_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_without_cache_returns_404_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_row_detail_supports_oa_bank_and_invoice -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_api_performance_metrics -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- Allowed production diff check：
  - `git diff --name-only -- backend/src/fin_ops_platform | rg -v '^(backend/src/fin_ops_platform/app/server.py|backend/src/fin_ops_platform/services/workbench_query_facade.py)$'` 必须无输出；如果其他生产文件变化，必须停止并说明原因。
- No forbidden surface diff：
  - `test -z "$(git diff --name-only -- web postgres deploy)"`
- Facade 上帝对象注入静态检查：
  - `rg -n "WorkbenchQueryFacade\\([^\\n]*(Application|RuntimeRepositories|RuntimeRepositoryContext|ApplicationStateStore|StateStoreProtocol|state_store)" backend/src/fin_ops_platform tests` 必须无输出。
- Facade mock 静态检查：
  - `rg -n "mock\\.patch\\(.+WorkbenchQueryFacade|patch\\(.+workbench_query_facade|monkeypatch.+WorkbenchQueryFacade|WorkbenchQueryFacade.*Mock|Mock.*WorkbenchQueryFacade" tests/test_workbench_sql_runtime.py` 必须无输出。
- Observability 边界静态检查：
  - `test ! -f backend/src/fin_ops_platform/services/workbench_query_facade.py || ! rg -n "request_database_timing" backend/src/fin_ops_platform/services/workbench_query_facade.py`
- SSE PubSub 静态检查：
  - `! rg -n "PubSub|pubsub|subscribe\\(" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_query_facade.py`

Post-Flight:
- 更新 `migration-state-log.md`：
  - 记录 PF-P009 执行结果。
  - 记录变更文件、测试命令和结果、fallback/SSE/observability 事实、剩余风险和下一步建议。
  - 将 PF-P009 状态设为 `implemented` 或 `blocked`，不得直接设为 `verified`。
- 更新 `refactor-prompts.md` 的 PF-P009 状态和执行结果。
- 更新 `workbench-read-model-query-plan.md` 的 Slice D-B 实现结果、仍未关闭风险和下一步输入。
- 最终回复必须明确：
  - 是否修改了生产代码；具体修改哪些文件。
  - 是否保持 API response contract、SSE contract 和 observability app-shell 边界。
  - 是否执行 Merge Gate 或 Traffic Gate。
  - 哪些验证通过。
  - 哪些 Slice D 风险仍未关闭。
  - 下一步建议：用户确认 PF-P009 verified 后，生成 PF-P009-MG；PF-P009-MG 必须统一覆盖 PF-P008 + PF-P009 的完整 diff。
```

### Gate Scope

- Merge Gate：不涉及。PF-P009 是实现型 prompt，不 commit/merge 到 `main`。后续必须生成 PF-P009-MG，统一合并 PF-P008 + PF-P009 的完整 diff。
- Traffic Gate：不涉及。PF-P009 不切流、不部署、不修改网关。
- Test Gate：涉及。PF-P009 必须先保留 PF-P008 测试护城河，再用 TDD 收口 fallback / SSE 风险。

### 审查结论

- 跳过单独的 PF-P008-MG 是合理的，但只在“同一功能分支继续 Slice D-B，后续由 PF-P009-MG 统一合并 PF-P008 + PF-P009”的前提下成立。
- PF-P009 边界正确：它是 Slice D-B 的实现 prompt，不是 Merge Gate / Traffic Gate。
- Prompt 明确要求 production fallback mitigation、row detail fallback mitigation、SSE cancellation cleanup 和 observability preservation，且都必须被 PF-P008/PF-P009 tests 覆盖。
- Prompt 保留生产级限制：不一次性删除 legacy path，不改变 API/SSE contract，不动 worker/builder/repository SQL/write path，不访问生产外部服务。
- 执行 PF-P009 前必须确认 PF-P008 状态为 `verified`，并先跑测试基线。

### 执行结果

- 状态：`verified`，已由用户确认。
- 执行分支：`codex/workbench-query-slice-d-prompt`。
- 生产代码变更：
  - `backend/src/fin_ops_platform/app/server.py`
  - Workbench SSE generator 增加 active stream registry 和 `finally` cleanup；保持 SSE headers、event names、heartbeat 和 polling refresh status 语义不变。
  - Row detail 在 production PostgreSQL runtime 下，live miss + cached read model miss 后不再进入可能触发 full sync 的 route fallback；legacy / non-production runtime 的兼容 fallback 保留。
  - `_requires_sql_read_model_runtime(...)` 改为 `getattr` 读取 `_bootstrap_mode`，避免局部构造的 `Application` helper 调用抛 AttributeError。
- 测试变更：
  - `tests/test_workbench_sql_runtime.py`
  - 新增 `test_workbench_events_stream_close_releases_active_stream_slot`。
  - 新增 `test_row_detail_production_sql_runtime_blocks_route_fallback_after_live_and_cache_miss`。
- 文档变更：
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
  - `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- TDD：
  - RED：新增两个 targeted tests 先失败，分别证明 SSE active stream cleanup 缺失、production SQL runtime row detail 仍进入 route fallback。
  - GREEN：生产代码最小改动后，同一 targeted tests 通过。
- 验证：
  - `git status --short --branch`、`git ls-files --others --exclude-standard`、`git diff --name-only`、`git diff --stat`、`git diff --check`：通过；无 untracked files，diff 范围符合 PF-P009。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`：通过，107 tests passed。
  - Row detail targeted tests：通过，4 tests passed。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_api_performance_metrics tests.test_platform_runtime_boundary_guards -v`：通过，15 tests passed。
  - `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`：通过。
  - `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`：通过，status `ready`。
  - Allowed production diff、No forbidden surface diff、Facade 上帝对象注入、Facade mock、Observability 边界、SSE PubSub 静态检查均通过。
- 不需要为 legacy `GET /api/workbench` 再改生产代码：既有 PF-P008 tests 已覆盖 production SQL missing / repository unavailable / legacy runtime fallback policy。
- 未修改 `WorkbenchQueryFacade`、SQL migration、前端、网关、部署、worker、builder、read model repository SQL、RabbitMQ、Outbox、Dirty Scope 或 Workbench 写路径。
- 未执行 Merge Gate，未执行 Traffic Gate，未部署服务器，未 push `origin/main`。
- 后续：执行已生成并审查的 `PF-P009-MG`；该 MG 必须统一覆盖 PF-P008 + PF-P009 的完整 diff。

## PF-P009-MG - Workbench Query Fallback and SSE Mitigation Merge Gate

状态：`verified`

### 目标

将 PF-P008 已 verified 的 Workbench Query fallback / SSE / observability characterization tests，以及 PF-P009 已 verified 的 Workbench Query fallback and SSE mitigation 生产代码、测试和文档，作为同一个 Slice D 可合并任务安全合入 `main`。本 prompt 是 Merge Gate，不是实现 prompt，不执行 Traffic Gate，不部署服务器，不默认 push。

### Prompt

```text
/goal
执行 PF-P009-MG - Workbench Query Fallback and SSE Mitigation Merge Gate。

目标：只处理 PF-P008 + PF-P009 已 verified 变更进入 `main` 的 Merge Gate。确认完整 diff 范围、复跑关键测试、精准 commit、同步最新 main、合入 main 并在 main 上复验。不得执行 Traffic Gate，不得部署服务器，不开始 Slice E 或任何新业务重构。

Role:
你是一位严格执行 Git Merge Gate、测试门禁、范围审计和 Python 后端重构交付纪律的资深工程师。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P008 已 verified，补齐 Workbench Query Slice D-A 的 fallback / SSE / observability characterization tests。PF-P009 已 verified，完成 Slice D-B：production PostgreSQL runtime 下 row detail route fallback gate，以及 Workbench SSE generator active stream cleanup。PF-P008 没有单独合入 main，因此本 Merge Gate 必须统一覆盖 PF-P008 + PF-P009 的完整 diff。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/workbench-read-model-query-plan.md
- docs/architecture/backend-refactor/ai-execution-rules.md
- backend/src/fin_ops_platform/app/server.py
- tests/test_workbench_sql_runtime.py
- tests/test_api_performance_metrics.py

必须确认：
- `migration-state-log.md` 中 PF-P008 状态为 `verified`。
- `migration-state-log.md` 中 PF-P009 状态为 `verified`。
- 当前 active prompt 是 `PF-P009-MG - Workbench Query Fallback and SSE Mitigation Merge Gate`。
- 当前分支必须是 `codex/workbench-query-slice-d-prompt` 或同一 Slice D 功能分支；不得在 `main` 上直接执行 merge gate 准备。
- 本轮只处理 Merge Gate，不是 Traffic Gate。
- 本轮不允许开始 Slice E、Workbench 写路径、matching/candidates、worker refresh、builder、repository SQL 重写或任何新模块迁移。

Expected Changed Files:
本轮允许合入的文件仅限：
- backend/src/fin_ops_platform/app/server.py
- tests/test_workbench_sql_runtime.py
- tests/test_api_performance_metrics.py
- docs/architecture/backend-refactor/ai-execution-rules.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/workbench-read-model-query-plan.md

如出现其它 changed / staged / untracked 文件，必须阻断并说明来源；不得临时扩大白名单。

Required Scope Checks:
1. 确认 PF-P008 测试锁定 diff 只包含：
   - SSE status event mapping / heartbeat / no-buffering / non-Redis PubSub characterization。
   - Row detail live / cached read model / route fallback 顺序和 `apply_to_row` characterization。
   - `Application.handle_request` 的 route-level API performance recorder / database timing characterization。
   - 相关状态机、prompt 库和 Slice D 计划回写。
2. 确认 PF-P009 生产代码 diff 只包含：
   - Workbench SSE generator active stream registry 和 `finally` cleanup。
   - production PostgreSQL runtime 下 row detail route fallback gate。
   - `_requires_sql_read_model_runtime(...)` 的 safe `getattr` 读取。
3. 确认 PF-P009 测试 diff 只包含：
   - `test_workbench_events_stream_close_releases_active_stream_slot`。
   - `test_row_detail_production_sql_runtime_blocks_route_fallback_after_live_and_cache_miss`。
4. 确认文档 diff 只记录：
   - PF-P008 verified。
   - PF-P009 verified。
   - PF-P009-MG planned。
   - MG 粒度规则：一个模块任务/切片可由多个 prompt 组成，最终 MG 覆盖完整 diff。
5. 确认没有修改：
   - SQL migration。
   - 前端代码。
   - Nginx、Vite、Caddy、部署配置或生产配置。
   - Worker refresh、builder、read model repository SQL、RabbitMQ、Outbox、Dirty Scope。
   - Workbench 写路径。
   - `WorkbenchQueryFacade`。

Mandatory Checks Before Commit:
- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --name-only`
- `git diff --stat`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- Row detail targeted tests：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_prefers_cached_read_model_before_query_service_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_prefers_month_read_model_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_without_cache_returns_404_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_row_detail_supports_oa_bank_and_invoice -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_api_performance_metrics tests.test_platform_runtime_boundary_guards -v`
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- Allowed production diff check：
  - `git diff --name-only -- backend/src/fin_ops_platform | rg -v '^backend/src/fin_ops_platform/app/server.py$'` 必须无输出。
- No forbidden surface diff：
  - `test -z "$(git diff --name-only -- web postgres deploy)"`
- Facade 上帝对象注入静态检查：
  - `rg -n "WorkbenchQueryFacade\\([^\\n]*(Application|RuntimeRepositories|RuntimeRepositoryContext|ApplicationStateStore|StateStoreProtocol|state_store)" backend/src/fin_ops_platform tests` 必须无输出。
- Facade mock 静态检查：
  - `rg -n "mock\\.patch\\(.+WorkbenchQueryFacade|patch\\(.+workbench_query_facade|monkeypatch.+WorkbenchQueryFacade|WorkbenchQueryFacade.*Mock|Mock.*WorkbenchQueryFacade" tests/test_workbench_sql_runtime.py` 必须无输出。
- Observability 边界静态检查：
  - `test ! -f backend/src/fin_ops_platform/services/workbench_query_facade.py || ! rg -n "request_database_timing" backend/src/fin_ops_platform/services/workbench_query_facade.py`
- SSE PubSub 静态检查：
  - `! rg -n "PubSub|pubsub|subscribe\\(" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_query_facade.py`

Commit / Merge Preparation:
- 严禁使用 `git add .` 或 `git add -A`。
- 必须精准 staging Expected Changed Files。
- 建议 commit message：
  - `refactor(workbench): mitigate query fallback and sse stream cleanup`
- commit 前后都必须确认 `git status --short --branch`。
- commit 后执行 `git fetch origin main`。
- merge 到 `main` 前必须确认当前分支包含最新 `origin/main`；如果 `origin/main` 有新提交，必须先 rebase 或 merge 最新 main 到当前分支，解决冲突后重新运行 Mandatory Checks。
- 切到 `main` 后先确认 `main` 与 `origin/main` 关系；不得覆盖远端主干。
- 合入 `main` 后必须在 `main` 上重新运行 Mandatory Checks。

Forbidden Scope:
- 不执行 Traffic Gate。
- 不部署服务器。
- 不 push 到 `origin/main`，除非用户在 PF-P009-MG 执行期间明确允许。
- 不修改生产配置或网关配置。
- 不开始 Slice E 或任何新业务模块重构。
- 不访问生产 DB、Redis、RabbitMQ、OA Mongo、OA MySQL、MinIO/S3。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产敏感 URL。
- 未经用户确认，不得把 PF-P009-MG 标记为 `verified`。

Post-Flight:
- 更新 `migration-state-log.md`：
  - 记录 PF-P009-MG 执行结果。
  - 记录 commit、merge 方式、变更范围、验证命令和结果。
  - 将 PF-P009-MG 状态设为 `implemented` 或 `blocked`，不得直接设为 `verified`。
  - 记录下一步建议：用户确认后标记 PF-P009-MG verified；push origin/main 需要用户明确确认；下一条 prompt 必须从最新 main 新建分支生成。
- 更新 `refactor-prompts.md` 的 PF-P009-MG 状态和执行结果。
- 必要时更新 `workbench-read-model-query-plan.md`，但不得开始 Slice E 设计或实现。
- 最终回复必须明确：
  - 是否只合入 Expected Changed Files。
  - 是否修改了 SQL migration、前端、网关、部署或生产配置。
  - 是否执行 Traffic Gate。
  - 哪些验证在 feature branch 和 main 上通过。
  - 是否 push 到 origin/main。
  - 下一步建议做什么。
```

### Gate Scope

- Merge Gate：涉及。PF-P009-MG 负责 PF-P008 + PF-P009 已 verified 变更的 main 合入门禁。
- Traffic Gate：不涉及。PF-P009-MG 不切流、不部署、不修改网关、不改变 worker 启动方式。
- Test Gate：涉及。PF-P009-MG 必须在合入前后确认 Workbench SQL runtime、row detail targeted tests、facade/API performance/platform guards、compileall 和 `app.main --check` 通过。

### 审查结论

- PF-P009-MG 的边界正确：它统一覆盖同一 Slice D 分支内 PF-P008 测试锁定和 PF-P009 实现改动的完整 diff。
- Expected Changed Files 覆盖当前真实 diff：`server.py`、两个测试文件、四份 backend-refactor 文档。
- Prompt 明确禁止 Traffic Gate、部署、默认 push、Slice E 和任何新业务重构。
- Prompt 保留本轮关键门禁：untracked 检查、精准 staging、禁止 `git add .` / `git add -A`、上游同步、feature branch 与 main 双重复验。
- Prompt 明确执行完成后只能到 `implemented` 或 `blocked`，必须等待用户确认才能 `verified`。

### 执行结果

- Feature branch：`codex/workbench-query-slice-d-prompt`。
- 功能提交：`b58bd5a0 refactor(workbench): mitigate query fallback and sse stream cleanup`。
- Merge：本地 `main` 已通过 fast-forward merge 合入 feature branch，当前到达 `b58bd5a0`。
- 变更范围：只包含 Expected Changed Files；未修改 SQL migration、前端、网关、部署配置、生产配置、Worker refresh、builder、read model repository SQL、RabbitMQ、Outbox、Dirty Scope、Workbench 写路径或 `WorkbenchQueryFacade`。
- Feature branch 验证通过：`git status --short --branch`、`git ls-files --others --exclude-standard`、`git diff --name-only`、`git diff --stat`、`git diff --check`、`tests.test_workbench_sql_runtime -v`、row detail targeted tests、`tests.test_workbench_query_facade tests.test_api_performance_metrics tests.test_platform_runtime_boundary_guards -v`、`compileall`、`app.main --check`、production diff / forbidden surface / Facade god object / Facade mock / observability boundary / SSE PubSub 静态检查。
- `main` 复验通过：`git status --short --branch`、`git ls-files --others --exclude-standard`、`git diff --check`、`git diff --name-only origin/main..HEAD`、`git diff --stat origin/main..HEAD`、`tests.test_workbench_sql_runtime -v`、row detail targeted tests、`tests.test_workbench_query_facade tests.test_api_performance_metrics tests.test_platform_runtime_boundary_guards -v`、`compileall`、`app.main --check`、production diff / forbidden surface / Facade god object / Facade mock / observability boundary / SSE PubSub 静态检查。
- 未执行 Traffic Gate、未部署服务器、未修改网关或生产配置、未 push `origin/main`。
- 状态：`verified`，已由用户确认。下一步允许 push `origin/main`；push 完成后必须从最新 `main` 新建分支，再生成并审查下一条 prompt。

## PF-P010 - Workbench Query Repository and Active Generation Boundary (Slice E)

状态：`planned`

### 目标

在 PF-P005 到 PF-P009 已建立的 Workbench Query 安全网下，继续收口 query/read-model 的 repository 和 active generation 边界。PF-P010 只处理 `PostgresReadModelRepository` 的 Workbench 读路径、active generation/source_version 选择、group/detail 查询一致性和必要的观测性检查；不进入写路径、worker rebuild、builder 或 matching/candidates。

### Prompt

```text
/goal
执行 PF-P010 - Workbench Query Repository and Active Generation Boundary (Slice E)。

目标：只处理 Workbench Query Slice E：repository active generation/source_version 读边界、groups/summary/group detail/refresh status 的一致性测试和最小实现修正。必须先用测试锁定行为，再做小步修改。不得执行 Merge Gate、Traffic Gate、部署或 push。

Role:
你是一位精通 Python 后端、PostgreSQL read model、CQRS/active generation、遗留系统 characterization tests 和低风险重构的资深工程师。

Context:
当前仓库执行 Python-first 后端架构模块化重构。PF-P005 已建立 Workbench query/read-model characterization baseline；PF-P006 已抽取 `WorkbenchQueryFacade`；PF-P007 已收口 groups cache/freshness gate；PF-P008/PF-P009 已锁定并缓解 fallback 与 SSE cleanup 风险；PF-P009-MG 已 verified 并已 push 到 `origin/main`。本轮从最新 `main` 新建分支 `codex/workbench-query-slice-e-prompt`，只生成和执行 Slice E，不开始其它模块。

Pre-Flight:
必须先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- backend/README.md
- docs/architecture/backend-refactor/migration-state-log.md
- docs/architecture/backend-refactor/refactor-prompts.md
- docs/architecture/backend-refactor/workbench-read-model-query-plan.md
- docs/architecture/backend-refactor/platform-runtime-boundary-audit.md
- docs/architecture/backend-refactor/architecture-inventory.md
- docs/architecture/backend-refactor/ai-execution-rules.md
- backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
- backend/src/fin_ops_platform/app/server.py
- backend/src/fin_ops_platform/services/workbench_query_facade.py
- tests/test_workbench_sql_runtime.py
- tests/test_workbench_query_facade.py
- tests/test_platform_runtime_boundary_guards.py

必须使用 CodeGraph 或等价结构分析确认以下真实调用关系，不得凭记忆：
- `PostgresReadModelRepository.get_workbench_summary(...)`
- `PostgresReadModelRepository.get_workbench_groups_page(...)`
- `PostgresReadModelRepository.get_workbench_group_detail(...)`
- `PostgresReadModelRepository.get_workbench_refresh_status(...)`
- `PostgresReadModelRepository.workbench_groups_cache_version(...)`
- 上述方法的 handler / facade callers 和现有 tests。

必须确认：
- 当前 active prompt 是 `PF-P010 - Workbench Query Repository and Active Generation Boundary (Slice E)`。
- 当前分支是 `codex/workbench-query-slice-e-prompt` 或同一 Slice E 分支；不得在 `main` 上执行。
- PF-P009-MG 已 verified 且 `origin/main` 已同步。
- 本轮不是 Merge Gate，也不是 Traffic Gate。

Allowed Scope:
- 修改 `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` 中 Workbench query/read-model repository 读路径相关代码。
- 修改 `tests/test_workbench_sql_runtime.py`，新增或调整针对 active generation/source_version/group detail/groups page 的 targeted tests。
- 如必须，可修改 `tests/test_workbench_query_facade.py` 以锁定 facade 对 repository status/source_versions 的透传，但不得 mock 掉 repository 边界。
- 如必须，可在 `backend/src/fin_ops_platform/app/server.py` 做极小 app-shell 调整，但必须证明不是业务行为变化，且不得改变 response contract。
- 更新 `migration-state-log.md`、`refactor-prompts.md`、`workbench-read-model-query-plan.md`。

Forbidden Scope:
- 不修改 SQL migration。
- 不修改前端代码、Nginx、Vite、Caddy、部署配置或生产配置。
- 不修改 Workbench 写路径、actions、matching/candidates、candidate grouping、free matching engine、exception/confirm/cancel handlers。
- 不修改 worker refresh consumer、projection builder、Outbox、Dirty Scope、RabbitMQ、Redis cache key 语义或 TTL 策略。
- 不删除 legacy fallback；如发现需要删除，必须标记 `blocked` 并提出独立 prompt。
- 不改变 API response contract、status code、field names、fresh/stale/refreshing/unavailable 语义。
- 不把 HTTP request context 的 `request_database_timing` 下沉到 facade/repository。
- 不引入新的外部依赖。
- 不执行 Merge Gate、Traffic Gate、部署或 push。

Required Test Work:
必须采用 TDD。实现前先新增或调整 targeted tests，覆盖以下至少 4 类风险；如果某类已有等价覆盖，必须在执行结果中明确列出测试名和原因：

1. Active generation isolation:
   - `get_workbench_groups_page(...)` 只读取当前 active generation。
   - 旧 generation、building generation、failed generation 中的数据不得混入 groups page/count/row counts。

2. Group detail consistency:
   - `get_workbench_group_detail(...)` 必须只返回 active generation 中的 group。
   - 如果 group 只存在于非 active generation，API/repository 应按当前契约返回 missing/not found/refreshing，而不是读旧数据。

3. Summary / source_versions consistency:
   - `get_workbench_summary(...)` 返回的 `source_versions`、`read_model_status`、generation metadata 必须与 active generation 对齐。
   - stale / refreshing / unavailable 语义不得因为 repository 修正而漂移。

4. Groups page count/filter/search consistency:
   - page rows、total、row counts、filter/search/sort 使用同一 active generation 和同一 filter 条件。
   - 不允许 page query 使用 active generation，但 count query 或 row-count query 跨 generation。

5. Observability check:
   - 检查 groups page/count/filter/search 是否缺少可定位慢查询的观测点。
   - 本轮若只记录 gap，不做生产指标改造，必须把 gap 写入 `workbench-read-model-query-plan.md`；不得为了指标改造扩大范围。

Required Implementation Work:
- 只做让上述 tests 通过所需的最小代码改动。
- 优先复用现有 repository helper，例如 active generation lookup、scope filter、source_versions 读取、filter normalization。
- 如果发现现有 SQL 大块重复但不影响当前风险，不做大规模抽象。
- 如果发现需要 SQL migration 才能保证一致性，必须停止并标记 `blocked`，不得偷偷改迁移。
- 如果发现性能问题需要 `EXPLAIN` 或索引设计，先记录风险和后续 prompt，不在本轮改 schema。

Mandatory Checks:
- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --name-only`
- `git diff --stat`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_platform_runtime_boundary_guards -v`
- Row detail targeted tests：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_row_detail_prefers_cached_read_model_before_query_service_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_prefers_month_read_model_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_opaque_oa_row_detail_without_cache_returns_404_without_full_oa_sync tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_row_detail_supports_oa_bank_and_invoice -v`
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/services/postgres_repositories/read_models.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_query_facade.py`
- 禁止面静态检查：
  - `test -z "$(git diff --name-only -- web postgres deploy)"`
  - `! rg -n "PubSub|pubsub|subscribe\\(" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_query_facade.py`
  - `! rg -n "mock\\.patch\\(.+WorkbenchQueryFacade|patch\\(.+workbench_query_facade|monkeypatch.+WorkbenchQueryFacade|WorkbenchQueryFacade.*Mock|Mock.*WorkbenchQueryFacade" tests/test_workbench_sql_runtime.py`

Post-Flight:
- 更新 `migration-state-log.md`：
  - 记录 PF-P010 执行结果。
  - 记录变更文件、测试命令和结果、CodeGraph/调用链发现、active generation/source_version 事实、风险和阻断。
  - 将 PF-P010 状态设为 `implemented` 或 `blocked`，不得直接设为 `verified`。
- 更新 `refactor-prompts.md` 的 PF-P010 状态和执行结果。
- 更新 `workbench-read-model-query-plan.md` 的 Slice E 执行结果、仍未关闭风险和下一步输入。
- 最终回复必须说明：
  - 是否修改生产代码。
  - 是否只改 allowed scope。
  - 是否执行 Merge Gate / Traffic Gate / push。
  - 哪些 tests 通过。
  - 下一步建议做什么。
```

### Gate Scope

- Merge Gate：不涉及。PF-P010 是 Slice E 执行型 prompt，不合入 `main`。
- Traffic Gate：不涉及。PF-P010 不切流、不部署、不修改网关。
- Test Gate：涉及。PF-P010 必须先用 tests 锁定 active generation/source_version 边界，再做最小实现。

### 审查结论

- PF-P010 的边界合理：它延续 Slice D 后仍未关闭的 repository / active generation 风险，不直接进入 Workbench 写路径或 matching/candidates。
- Prompt 明确要求 CodeGraph/结构分析，不允许凭记忆修改 repository SQL。
- Prompt 强制 TDD，并把 active generation isolation、group detail consistency、summary/source_versions consistency、groups count/filter/search consistency 和 observability gap 作为必检项。
- Prompt 禁止 SQL migration、前端、worker rebuild、builder、cache key、Outbox/Dirty Scope、Traffic Gate、部署和 push。
- 执行完成后只能进入 `implemented` 或 `blocked`，必须等待用户确认才能 `verified`。

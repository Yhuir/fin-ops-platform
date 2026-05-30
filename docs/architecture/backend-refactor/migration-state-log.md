# 后端架构重构 AI 状态机

## 用途

本文档维护 Python-first 后端架构重构的上下文检查点。每次 Codex、Gemini 或人工执行 prompt 后，都必须更新本文档，记录当前完成度、验证结果、风险和下一条 prompt 需要知道的上下文。

本文档不是完整 prompt 库。完整 prompt 存放在 `refactor-prompts.md`。

## 事实源

当前架构事实源按优先级读取：

1. `README.md`
2. `target-architecture.md`
3. `module-refactor-plan.md`
4. `runtime-call-chain.md`
5. `read-model-and-external-services.md`
6. `migration-roadmap.md`
7. `ai-execution-rules.md`
8. `refactor-prompts.md`

如果本文档和上述文档冲突，以上述架构文档为准，并立即修正本文档。

## 全局硬规则

- 当前计划是 Python-first 模块化重构。
- 不创建新语言后端。
- 不全量重写 Python 后端。
- 不引入任何其他语言的新后端。
- 不在 `main` 上直接做重构开发。
- 每个模块必须先梳理静态调用链和动态运行时序。
- 外部服务必须通过 port/adapter 或稳定服务边界访问。
- 写操作必须在同一 PostgreSQL transaction 中提交 facts、audit、dirty scope 和 outbox。
- Read Model 必须遵守 source version、building/active generation、幂等刷新、版本化缓存 key 和 consistency checker。
- 当前模块未完成测试和验收前，不进入下一个模块。
- 每次只生成一个 prompt；下一条 prompt 必须基于上一条 prompt 的真实输出和本文档的下一步上下文生成。
- 每次 prompt 完成后，最终回复必须告诉用户下一步建议做什么。
- 每次 prompt 执行后，必须精准回写本文档和受执行结果影响的架构文档；未完成回写前不得生成或执行下一条 prompt。
- 先执行 Macro-Inventory，再执行 Micro-JIT-Planning。
- Macro-Inventory 只做全局文件级分拣和架构事实清单，不修改业务代码。
- Micro-JIT-Planning 每次只深挖一个模块，不一次性生成所有模块详细设计。
- Merge Gate 和 Traffic Gate 分离。
- Merge Gate 是 merge 到 `main` 前后的验证流程，不等于上线。
- Python-only 模块化重构通常不要求 staging；涉及网关切流、auth/session、SSE 或 worker 消费方式变更时才需要 Traffic Gate。
- 没有 staging 环境时，不得默认执行高风险 Traffic Gate；如用户明确要求生产 canary，必须先记录风险、回滚方案和观测指标。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产敏感 URL。

## 当前状态

| 字段 | 当前值 |
| --- | --- |
| 当前阶段 | Platform Runtime Boundary Guard Merge Gate 已 verified |
| 当前 active prompt | 无 |
| 最近 verified prompt | `PF-P003-MG - Platform Runtime Boundary Guard Merge Gate` |
| 当前分支 | `main` |
| 最近验证 | 用户已确认 `PF-P003-MG` verified；已本地 merge 到 main；main 上指定测试均已通过；未 push，未执行 Traffic Gate |
| 下一条允许任务 | 决定是否 push `main` 到 origin；或生成第一个业务模块 Micro-JIT prompt |

## Prompt 执行日志

### PF-P000 - Fresh Documentation Baseline

状态：`verified`

#### 范围

- 移除旧 Axum/PostgreSQL 后端替换计划。
- 不恢复旧语言替换状态机。
- 建立 Python-first 架构重构文档。
- 建立 AI 状态机和 prompt 库。
- 更新文档索引。

#### 变更文件

- `docs/architecture/backend-refactor/README.md`
- `docs/architecture/backend-refactor/target-architecture.md`
- `docs/architecture/backend-refactor/module-refactor-plan.md`
- `docs/architecture/backend-refactor/runtime-call-chain.md`
- `docs/architecture/backend-refactor/read-model-and-external-services.md`
- `docs/architecture/backend-refactor/migration-roadmap.md`
- `docs/architecture/backend-refactor/ai-execution-rules.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/index.md`
- `docs/index.md`
- `docs/exec-plans/active/README.md`
- `docs/exec-plans/active/backend-axum-postgres-refactor.md` 删除
- `docs/architecture/backend-refactor/data-model-and-read-models.md` 删除

#### 架构决策

- 当前方向是 Python-only 模块化重构，不做全量语言替换，不引入新语言后端。
- 不创建新语言后端。
- Read Model、Redis、RabbitMQ、PostgreSQL、OA Mongo、MinIO/S3 都必须模块化。
- 每个模块必须先完成静态调用链和动态运行时序。
- 状态日志和 prompt 库分离：本文档记录状态，`refactor-prompts.md` 保存完整 prompt。
- Turnover Ledger 是独立业务模块，不归入 Workbench 或 Bankdetail。
- Batch Accounting 是独立业务模块，不归入 Workbench。
- Workbench 先保持一个顶层模块，但必须在模块内部继续拆分 query/read-model、matching/candidates、pair-relations/actions、exceptions、special/reconciliation、shared-normalization 子域。
- Workbench Matching Engine 是候选独立模块，必须在 PF-P001 中根据文件级归属、函数级调用链、输入输出、事务边界和 read model ownership 决定是否升格。
- PF-P001 必须生成 `architecture-inventory.md`，作为后续 Micro-JIT 单模块 prompt 的输入。

#### 验证

- 已调用 CodeGraph 做过一次全局上下文探索，并阅读了 `backend/src/fin_ops_platform/app/`、`services/`、PostgreSQL migrations、read model、Redis/RabbitMQ 相关代码和文档入口。
- 当前只完成了目标架构和调用链分析方法的文档化，尚未完成逐模块真实运行时调用链盘点。
- `git diff --check`：通过。
- `test ! -e backend-go`：通过，确认旧目录不存在。
- `find docs/architecture/backend-refactor -maxdepth 1 -type f`：已确认只剩新方向文档。
- `rg "Axum|SQLx|NATS|JetStream|Rust|backend-go|语言替换|新语言后端"`：旧方向词只出现在“已移除/非目标/禁止项”语境，不是当前计划。
- 未运行 Python 测试：本轮只改文档。

#### 未完成事项 / 风险

- 尚未对所有模块做 CodeGraph 调用链盘点。
- 运行时调用链文档当前是规则、模板和优先级，不是最终的代码事实清单。
- 目标优化架构已形成高层草案，但需要 PF-P001 用代码事实校准模块边界和热点路径。
- 已发现并修复文档层面的高优先级遗漏：Turnover Ledger 和 Batch Accounting 必须独立模块化；Workbench 大文件和 Workbench Matching Engine 必须在 PF-P001 中逐一盘点。

#### 下一条 Prompt 上下文

PF-P000 建立了 fresh 的 Python-first 重构文档体系，并补充了 AI 状态机和 prompt 库。用户已确认 PF-P000 verified。PF-P001 已生成并审查，下一步允许执行 PF-P001。PF-P001 只做 Macro-Inventory：全局文件级分拣、API ownership、file ownership、静态调用链、动态运行时序、外部依赖矩阵和第一批优化候选，不改业务代码。PF-P001 必须生成 `architecture-inventory.md`；必须覆盖 Turnover Ledger、Batch Accounting、Workbench 全量大文件和 Workbench Matching Engine 候选独立模块评估；必须输出模块遗漏/错归属审计。PF-P001 verified 后，后续 prompt 才能进入 Micro-JIT 单模块深挖。

### PF-P001 - Architecture Inventory / Dynamic Call Chain Discovery

状态：`verified`

#### 范围

- 执行 Macro-Inventory，全局只读文件级分拣。
- 生成 `docs/architecture/backend-refactor/architecture-inventory.md`。
- 输出 API path ownership、file ownership、external dependency matrix、read model ownership、runtime sequence candidates 和 risk register。
- 覆盖 Turnover Ledger、Batch Accounting、Workbench 全量大文件和 Workbench Matching Engine 候选模块评估。
- 只允许小范围修订模块计划、调用链文档和状态机中的事实性归属。

#### 禁止范围

- 不修改 Python 业务代码。
- 不修改 tests。
- 不修改数据库 migration。
- 不修改前端、Nginx、Vite、部署配置或生产配置。
- 不创建新语言后端。
- 不执行 Micro-JIT 单模块重构。
- 不执行 Merge Gate 或 Traffic Gate。

#### 产物

- `docs/architecture/backend-refactor/architecture-inventory.md`
- `docs/architecture/backend-refactor/module-refactor-plan.md`
- `docs/architecture/backend-refactor/runtime-call-chain.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/migration-state-log.md`

#### 执行摘要

- 生成 `architecture-inventory.md`，完成 Macro-Inventory 的 API path ownership、文件族 ownership、外部依赖矩阵、Read Model / runtime sequence candidates 和风险清单。
- 确认 Turnover Ledger 和 Batch Accounting 是独立模块。
- 确认 Workbench Matching Engine 目前暂不升格为顶层模块，先作为 Workbench 内部 `matching/candidates` 子域推进。
- 识别 `server.py`、`services/postgres_repositories/read_models.py`、`state_store.py`、`runtime_queue.py`、`turnover_ledger_service.py`、`batch_accounting_service.py` 等高风险文件。
- 识别 `/projects`、`/ledgers`、`/reminders`、`/reconciliation/cases`、`/matching/*` 为 Legacy / Review，需要后续确认归属。
- Omission correction：补录 `etc_reconciliation_service.py`、`etc_reconciliation_zip_filter.py`、`project_detail_export_service.py`、`search_service.py`、`workbench_special_rule_detectors.py` 到高风险大文件清单，并补充 Tax / Cost / ETC 与 Search / Pending Query 的显式盘点。
- Production coverage correction：补录 `domain/__init__.py`、`domain/models.py`、`domain/enums.py`、`app/main.py`、`app/auth.py`、`app/bank_account_balance_backfill.py`、`app/bank_detail_backfill.py`、`postgres/__init__.py`、`postgres/__main__.py`、`postgres/migrate.py`，并为 Shared Domain、App Entry、Auth、DB Migration Runtime、Ops Backfill 指定 Primary Owner。
- Production coverage correction：补录测试门禁热点，至少覆盖 `tests/test_workbench_v2_api.py`、`tests/test_etc_backend.py`、`tests/test_workbench_sql_runtime.py`，并扩展到 50KB 以上高风险测试文件。

#### 验证

- `git diff --check`：通过。
- `test ! -e backend-go`：通过。
- `test -f docs/architecture/backend-refactor/architecture-inventory.md`：通过。
- `rg -n "Turnover Ledger|Batch Accounting|Workbench Matching Engine|API Path Ownership|File Ownership|External Dependency Matrix|Risk Register" docs/architecture/backend-refactor/architecture-inventory.md`：通过，关键章节存在。
- `rg -n "etc_reconciliation_service|etc_reconciliation_zip_filter|project_detail_export_service|search_service|workbench_special_rule_detectors" docs/architecture/backend-refactor/architecture-inventory.md`：通过，omission correction 文件均已收录。
- `rg -n "domain/models.py|domain/enums.py|app/main.py|app/auth.py|postgres/migrate.py|test_workbench_v2_api.py|test_etc_backend.py|test_workbench_sql_runtime.py" docs/architecture/backend-refactor/architecture-inventory.md`：通过，生产级覆盖面修正文件均已收录。
- `rg -n "PF-P001-C1|Production Coverage Correction|Shared Domain|Platform / Auth|DB Migration Runtime|测试门禁热点" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/architecture-inventory.md`：通过，prompt、状态和 inventory 均有记录。
- `rg -n "Go Fiber|backend-go|Axum|Rust|新语言后端|语言替换|Hot Path" docs/architecture/backend-refactor`：已检查，相关词只出现在禁止项、非目标或历史方向说明语境。
- 未运行 Python unit tests：本轮只改文档，且禁止修改业务代码。

#### 下一条 Prompt 上下文

PF-P001 已由用户确认 verified。下一步允许执行 `PF-P002 - Platform / Ops / Runtime Boundary Deep Dive`，但只能做 Platform/Ops/Runtime 边界审计和文档产出，不得开始业务模块迁移。

### PF-P001-C1 - Production Coverage Correction

状态：`verified`

#### 范围

- 对 PF-P001 的 Macro-Inventory 做生产级覆盖面修正。
- 补齐非 `services/` 核心目录显式归属。
- 固化测试门禁热点。
- 不修改业务代码、测试、SQL migration 或部署配置。

#### 产物

- `docs/architecture/backend-refactor/architecture-inventory.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/migration-state-log.md`

#### 执行摘要

- 已将 `domain/` 全部文件归入 Platform / Shared Domain。
- 已将 `app/main.py` 归入 Platform / App Entry。
- 已将 `app/auth.py` 归入 Platform / Auth。
- 已将 bank detail 相关 backfill 脚本归入 Platform / Ops Backfill，Bankdetail 为 secondary influence。
- 已将 PostgreSQL migration Python runtime 归入 Platform / DB Migration Runtime。
- 已新增测试门禁热点，覆盖 Workbench、Tax / Cost / ETC、Platform / OA Adapter、Platform / State Store、Bankdetail 等大测试文件。

#### 下一条 Prompt 上下文

PF-P001-C1 是 PF-P001 的生产级覆盖面修正，不是新的业务重构阶段。用户已确认 PF-P001 verified，因此 PF-P001-C1 作为 PF-P001 verified 范围一并锁定。PF-P002 必须读取 `architecture-inventory.md`，并将 Shared Domain、App Entry、Auth、DB Migration Runtime、Ops Backfill、runtime queue、outbox、dirty scope、Redis/RabbitMQ/OA Mongo/MinIO 和 legacy snapshot/local state 全部纳入 Platform/Ops 深挖范围。

### PF-P002 - Platform / Ops / Runtime Boundary Deep Dive

状态：`verified`

#### 范围

- 基于 PF-P001 verified 的 `architecture-inventory.md` 做第一个 Micro-JIT 深挖。
- 只审计 Platform / Ops / Runtime Boundary，不修改代码。
- 产出 `docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`。
- 将 Shared Domain、App Entry、Auth、DB Migration Runtime、Ops Backfill、runtime queue、outbox、dirty scope、Redis/RabbitMQ、OA Mongo、MinIO/S3、legacy snapshot/local state 纳入同一底座审计。
- PF-P002 prompt 已重写为生产级覆盖面版本：不得只扫描 `runtime_*` 和 `state_store.py`，必须覆盖 DB transaction/core repository、settings/access control、OA identity/projection、shadow/dual state store、ops tools、observability 和基建测试门禁。

#### 必检项

- 审计 DB connection、transaction helper、repository core、outbox/dirty scope 的统一写边界。
- 审计 settings/access control 与 auth context 的关系。
- 审计 OA identity / role / projection 的事实来源，明确 OA Mongo 与 PostgreSQL projection 的边界。
- 审计所有 Redis/RabbitMQ 直接依赖点，并输出“允许的 platform adapter 调用”和“禁止的业务层直接调用”清单。
- 审计 `state_store.py`、`postgres_state_store.py`、`runtime_bootstrap.py` 以及 shadow/dual/diff 相关文件的生产路径，明确 legacy snapshot/local state/pickle 是否还能进入 production request/worker path。
- 审计 `app/auth.py` 到 handler/usecase 的 auth context 传导链，明确统一身份上下文接口和测试门禁。
- 审计 ops tools、backfill scripts、observability/audit/performance metrics 的平台边界。
- 执行后必须回写本文档和受影响架构文档。

#### 禁止范围

- 不修改 Python 业务代码。
- 不修改 tests。
- 不修改 SQL migration。
- 不修改部署、网关或生产配置。
- 不开始 Workbench、Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 业务模块迁移。
- 不执行 Merge Gate 或 Traffic Gate。

#### 验收标准

- `refactor-prompts.md` 已包含完整 PF-P002 prompt。
- PF-P002 prompt 包含 Pre-Flight、Allowed Scope、Forbidden Scope、Required Audit Output、Mandatory Checks、Tests、Post-Flight、Gate Scope 和审查结论。
- PF-P002 prompt 明确产物为 `platform-runtime-boundary-audit.md`。
- PF-P002 prompt 明确执行后只能到 `implemented`，等待用户确认后才能 `verified`。
- PF-P002 prompt 必须扫描 `postgres_connection.py`、`postgres_repositories/core.py`、`app_settings_service.py`、`access_control_service.py`、`settings_data_reset_service.py`、`oa_identity_service.py`、`oa_role_sync_service.py`、`oa_projection_sync.py`、`postgres_repositories/oa_projection.py`、shadow/dual/diff state store 文件、`tools/**/*.py`、observability/audit/performance metrics 文件和相关测试。

#### 变更文件

- `docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`
- `docs/architecture/backend-refactor/README.md`
- `docs/architecture/backend-refactor/runtime-call-chain.md`
- `docs/architecture/backend-refactor/read-model-and-external-services.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/migration-state-log.md`

#### 执行摘要

- 使用 CodeGraph 和 `rg` 审计了 Platform / Ops / Runtime 边界。
- 确认 PostgreSQL 连接池、事务入口和 query timing 集中在 `services/postgres_connection.py`。
- 确认 durable outbox、dirty scope、source_version、worker heartbeat 集中在 `services/runtime_queue.py`。
- 确认 Redis 真实客户端导入集中在 `services/runtime_redis.py`，RabbitMQ `pika` 真实客户端导入集中在 `services/rabbitmq_runtime.py`。
- 确认 `app/worker.py` 是 worker 组合根，负责组装 OA sync、read model refresh、import job、workbench matching 等 runtime handler。
- 确认 `app/auth.py`、`OAIdentityService`、`AccessControlService` 构成当前 OA token/cookie -> identity -> access decision 主链路。
- 确认 `OAProjectionSyncService` 从 OA source adapter 读取记录，写 PostgreSQL OA projection，并标记 Workbench、Search、Pending Invoice dirty。
- 确认 production bootstrap 默认不读取 full snapshot，但 `FIN_OPS_APP_STORAGE_BACKEND` 缺失时会回落到 `ApplicationStateStore`，生产必须显式锁定 `postgres`。
- 确认 `state_store.py`、ETC service 本地 `.pkl` fallback 和 Mongo Binary pickle 兼容路径仍存在，必须限定在 legacy、migration、shadow、test 或本地排障路径。
- 确认当前尚无全局 Unit of Work 强制 facts、audit、dirty scope、outbox 同事务，后续 Platform prompt 需要补机械门禁。

#### 验证

- `git diff --check`：通过。
- `test -f docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`：通过。
- `rg -n "DB Transaction / Repository Core Boundary|Settings / Access Control Boundary|OA Identity / Role / Projection Boundary|Redis / RabbitMQ Direct Dependency Audit|Legacy State / Snapshot / Pickle Production Path Audit|Auth Context Propagation Audit|Observability / Audit / Performance Metrics Boundary|Test Gate Matrix|Refactor Readiness" docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`：通过。
- `rg -n "允许的 platform adapter 调用|禁止或可疑的业务层直接调用|production request path|production worker path|auth context|shadow|dual|DB transaction|OA identity" docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`：通过。
- `git status --short --branch`：确认本轮和前序变更均位于 `docs/architecture/backend-refactor/`，没有业务代码、tests、SQL migration、前端、网关或部署配置改动。
- 未运行 Python unit tests：本轮只改文档，且 PF-P002 禁止修改代码。

#### 下一条 Prompt 上下文

PF-P002 已由用户确认 verified。PF-P003 已生成并审查，目标是把 PF-P002 的平台风险转成机械 guard 和测试门禁，只补强 production storage backend guard、legacy snapshot/full snapshot 禁用、auth context 传递契约、Unit of Work / transaction boundary、Redis/RabbitMQ direct import 静态门禁；仍不得开始业务模块迁移。

### PF-P003 - Platform Runtime Boundary Enforcement / Guard Tests

状态：`verified`

#### 范围

- 基于 PF-P002 verified 的 `platform-runtime-boundary-audit.md`，在 Python 平台底座内补机械 guard 和测试门禁。
- 允许极小范围修改 Platform / App Shell / Runtime Boundary 代码和平台测试。
- 不开始 Workbench、Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 等业务模块迁移。
- 不执行 Merge Gate 或 Traffic Gate。

#### 目标

- 固化 production storage backend guard。
- 固化 full snapshot / pickle / legacy bootstrap 禁用规则。
- 固化 Auth Context 传递契约和禁止 usecase 私自解析 token/cookie 的静态门禁。
- 固化 Unit of Work / transaction boundary 的最小机械检查。
- 固化 Redis/RabbitMQ direct client import 的静态测试。
- 固化 OA Mongo adapter direct use 的静态测试和 allowlist。
- 固化 external OA MySQL / `pymysql` direct import 的静态测试和 allowlist。
- 固化 handler / usecase raw SQL boundary 的静态测试和 known violations 记录。

#### 变更文件

- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`

#### 验证

- TDD red phase：首次运行 `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v` 失败，原因包括 production runtime guard 尚未实现，以及静态测试 allowlist 分类过严。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：通过，9 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap tests.test_state_store_factory_preflight tests.test_app_postgres_mode -v`：通过，34 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard tests.test_session_api -v`：通过，12 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_runtime_redis tests.test_rabbitmq_runtime -v`：通过，49 tests。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`：通过，输出 readiness summary；本地 guard disabled，status 为 ready。
- `git diff --check`：通过。
- `git status --short --branch`：通过，确认本轮代码改动仅包含平台 App Shell 与新增平台 guard test；文档改动仍集中在 `docs/architecture/backend-refactor/`。

#### 执行摘要

- 在 `Application.readiness_summary()` 增加 `production_runtime_guard`，当 release runtime 或 `FIN_OPS_PRODUCTION_RUNTIME_GUARD=1` 时，若 storage backend 不是 `postgres`、bootstrap mode 是 `legacy`、或 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT` 启用，则 readiness `status=not_ready`。
- 新增 `tests/test_platform_runtime_boundary_guards.py`，固化 8 类平台机械门禁：production runtime、legacy snapshot/pickle、auth context、outbox/dirty scope、Redis/RabbitMQ direct import、OA Mongo adapter direct use、external OA MySQL / `pymysql`、handler/usecase raw SQL boundary。
- 静态测试采用 allowlist + known violation 机制，防止 PF-P003 扩大到业务模块迁移。
- `cost_tax_sql_projection.py` 仍作为 `MongoOAAdapter` parser version / pure utility 依赖的 known violation，后续 Tax / Cost / ETC Micro-JIT 中应迁出到 shared/domain utility。
- raw SQL 当前按 repository、projection、runtime、ops/backfill 分类通过；业务模块 Micro-JIT 必须逐步把未归入 repository 的 SQL 收口。

#### 下一条 Prompt 上下文

PF-P003 已由用户确认 verified。下一步只能执行 `PF-P003-MG - Platform Runtime Boundary Guard Merge Gate`，只做本平台 guard 分支的范围检查、关键测试复跑、commit/merge 准备和状态机回写，不进入 Workbench 或其他业务模块。

### PF-P003-MG - Platform Runtime Boundary Guard Merge Gate

状态：`verified`

#### 范围

- 只处理 PF-P003 及此前已 verified 的 Python-first backend-refactor 文档和平台 guard 变更的 Merge Gate。
- 确认 PF-P003 已 verified。
- 检查当前分支变更范围，确保不存在业务模块迁移、Traffic Gate、生产配置或网关切流。
- 排查 untracked files，禁止临时文件或本地生成物混入提交。
- 复跑 PF-P003 关键测试与基础 diff 检查。
- 如果范围和测试通过，可准备 commit；commit message 必须体现生产代码和测试变更，不得误标为 docs-only。
- 如用户明确要求 merge 到 `main`，必须先同步最新 main 并重跑完整验证；如果当前已经在 `main`，不得执行无意义 merge，只做范围检查、验证和状态机更新。

#### 禁止范围

- 不开始 Workbench、Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax / Cost / ETC、Search 业务模块迁移。
- 不修改业务逻辑以“顺手修复”测试。
- 不修改 SQL migration、前端、Nginx、Vite、Caddy、部署配置或生产配置。
- 不执行 Traffic Gate。
- 不把任何生产流量切到新路径。
- 不使用 `git add .` 或 `git add -A`。
- 不提交 `.pkl`、`.sqlite`、`__pycache__/`、`.pytest_cache/`、测试输出目录、IDE 临时文件或其他本地生成物。
- 未经用户确认，不得将 PF-P003-MG 标记为 verified。

#### 验收标准

- `refactor-prompts.md` 已包含完整 PF-P003-MG prompt。
- PF-P003-MG prompt 明确 Pre-Flight、Allowed Scope、Forbidden Scope、Tests、Post-Flight 和 Gate Scope。
- PF-P003-MG 明确只执行 Merge Gate，不执行 Traffic Gate。
- PF-P003-MG 明确 commit message 使用 `feat(platform)` 或等价非 docs-only 语义。
- PF-P003-MG 明确排查 untracked files，精准 stage 文件，禁止 `git add .` 和 `git add -A`。
- PF-P003-MG 明确 merge 前必须执行 upstream sync 安全锁，并在同步 main 后重跑完整验证。
- PF-P003-MG 明确执行完成后只能到 `implemented` 或 `blocked`，必须等待用户确认才能 `verified`。

#### 执行摘要

- 已确认 PF-P003 状态为 `verified`。
- 当前分支为 `codex/python-first-refactor-reset`，不是 `main`。
- 变更范围检查通过：tracked 改动只包含 `backend/src/fin_ops_platform/app/server.py` 和 `docs/architecture/backend-refactor/**`。
- untracked 文件检查通过：仅包含 `docs/architecture/backend-refactor/architecture-inventory.md`、`docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`、`tests/test_platform_runtime_boundary_guards.py`，均属于此前 verified 的 backend-refactor 文档和平台 guard test 范围。
- 未发现 `.pkl`、`.sqlite`、`__pycache__/`、`.pytest_cache/`、测试输出目录、IDE 临时文件或其他本地生成物需要提交。
- 已复核 `server.py` production runtime guard 只影响 readiness summary，不改变业务 handler 行为。
- 已复核 guard 默认不破坏 local/dev 行为；只有 release runtime 或显式 `FIN_OPS_PRODUCTION_RUNTIME_GUARD` 启用时才严格要求 PostgreSQL backend、非 legacy bootstrap、禁用 full snapshot。
- 已复核静态 guard tests 使用 allowlist + known violations，未把业务模块迁移塞进 PF-P003。
- 已创建本地 commit 并本地 merge 到 `main`；merge 前已 fetch origin，确认本地 `main` 与 `origin/main` 一致，且 `main` 是功能分支祖先。
- 未执行额外 upstream sync 到功能分支，因为 fetch 后确认功能分支已包含最新 main。
- 未执行 Traffic Gate，未修改网关、部署或生产配置。

#### 变更文件

- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `docs/architecture/backend-refactor/README.md`
- `docs/architecture/backend-refactor/ai-execution-rules.md`
- `docs/architecture/backend-refactor/architecture-inventory.md`
- `docs/architecture/backend-refactor/migration-roadmap.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/module-refactor-plan.md`
- `docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`
- `docs/architecture/backend-refactor/read-model-and-external-services.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/runtime-call-chain.md`
- `docs/architecture/backend-refactor/target-architecture.md`

#### 验证

- `git diff --check`：通过。
- `git ls-files --others --exclude-standard`：仅列出本次允许范围内的 3 个新增文件。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：通过，9 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap tests.test_state_store_factory_preflight tests.test_app_postgres_mode -v`：通过，34 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard tests.test_session_api -v`：通过，12 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_runtime_redis tests.test_rabbitmq_runtime -v`：通过，49 tests。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`：通过，本地 readiness `status=ready`，`production_runtime_guard.enabled=false`。
- `git status --short --branch`：通过，范围与 PF-P003-MG 允许列表一致。

#### Main Merge 验证

- `git fetch origin`：通过。
- `git rev-parse main` 与 `git rev-parse origin/main`：merge 前一致。
- `git merge-base --is-ancestor main codex/python-first-refactor-reset`：通过，功能分支包含最新 main。
- `git switch main`：通过。
- `git merge --no-ff codex/python-first-refactor-reset -m "Merge branch 'codex/python-first-refactor-reset': establish platform runtime guards"`：通过，生成本地 merge commit `58535cab`。
- `git diff --check`：在 main 上通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：在 main 上通过，9 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap tests.test_state_store_factory_preflight tests.test_app_postgres_mode -v`：在 main 上通过，34 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard tests.test_session_api -v`：在 main 上通过，12 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_runtime_redis tests.test_rabbitmq_runtime -v`：在 main 上通过，49 tests。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`：在 main 上通过，本地 readiness `status=ready`，`production_runtime_guard.enabled=false`。
- `git status --short --branch`：main 工作区干净，领先 `origin/main` 4 个本地提交。

#### Commit / Merge

- Staged files 必须使用精确 `git add <path>`；不得使用 `git add .` 或 `git add -A`。
- Feature commit：`b31ee8aa feat(platform): establish runtime boundary guards and baseline tests`。
- Local merge commit：`58535cab Merge branch 'codex/python-first-refactor-reset': establish platform runtime guards`。
- 已本地 merge 到 `main`。
- 未 push `main` 到 origin。
- 未执行 Traffic Gate。

#### 下一条 Prompt 上下文

PF-P003-MG 已由用户确认 verified，已本地合入 `main`，并在 `main` 上通过指定验证。下一步可以决定是否 push `main` 到 origin；也可以生成第一个业务模块 Micro-JIT prompt。下一条业务模块 prompt 必须读取 `architecture-inventory.md` 和 `platform-runtime-boundary-audit.md`，并继续遵守 PF-P003 固化的 8 类平台 guard。

## 维护规则

### Prompt 前

AI 必须先读取：

- 本文档。
- `refactor-prompts.md`。
- 当前 prompt 相关架构文档。
- 当前模块相关代码和测试。

### Prompt 后

AI 必须更新：

- 当前状态。
- prompt 状态。
- 变更文件。
- 验证命令和结果。
- 风险和阻断。
- 下一条 prompt 上下文。

### 状态规则

允许状态：

- `planned`
- `in_progress`
- `implemented`
- `verified`
- `blocked`
- `rolled_back`

没有测试结果和用户确认，不得标记 `verified`。

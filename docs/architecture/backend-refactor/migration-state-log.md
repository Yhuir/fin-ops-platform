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
- prompt 生成、prompt 审查、状态机更新、对应实现和该实现的 Merge Gate 必须在同一条 `codex/` 功能分支内完成。
- Merge Gate 合入并复验 `main` 后，下一条 prompt 必须从最新 `main` 新建分支再生成；不得在 `main` 或旧功能分支上继续生成下一个模块的 prompt。
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
| 当前阶段 | `PF-P007-MG - Workbench Query Cache and Freshness Merge Gate` 已生成，等待执行 |
| 当前 active prompt | `PF-P007-MG - Workbench Query Cache and Freshness Merge Gate` (`planned`) |
| 最近 verified prompt | `PF-P007 - Workbench Query Cache and Freshness Boundary (Slice C)` |
| 当前分支 | `codex/workbench-query-cache-freshness` |
| 最近验证 | 用户已确认 PF-P007 verified；PF-P007 已在 feature branch 通过 mandatory checks；未 commit、未 merge、未 push、未部署服务器；未执行 Traffic Gate |
| 下一条允许任务 | 执行 `PF-P007-MG`；不得直接开始 Slice D、Traffic Gate、部署或生产变更 |

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
- 已 push `main` 到 origin。
- 未执行 Traffic Gate。

#### Post-Push 记录

- `git push origin main`：通过，`origin/main` 已更新到 `3075986d`。
- `git rev-parse --short HEAD` 与 `git rev-parse --short origin/main`：均为 `3075986d`。
- 本次 push 只推送 Git 远端主干；未推送或重启服务器，未修改部署配置，未执行 Traffic Gate。

#### 下一条 Prompt 上下文

PF-P003-MG 已由用户确认 verified，已本地合入 `main`，已 push 到 `origin/main`，并在 `main` 上通过指定验证。用户确认下一步做 `Workbench Read Model Query`。下一条业务模块 prompt 必须读取 `architecture-inventory.md` 和 `platform-runtime-boundary-audit.md`，并继续遵守 PF-P003 固化的 8 类平台 guard。

### PF-P004 - Workbench Read Model Query Discovery / Boundary Plan

状态：`verified`

#### 范围

- 作为第一个业务模块 Micro-JIT 的发现和边界计划 prompt。
- 只处理 Workbench `query/read-model` 子域的真实代码事实、API contract、运行时调用链、风险、测试矩阵和后续执行切片。
- 必须覆盖 `/api/workbench/summary`、`/api/workbench/groups`、`/api/workbench/groups/detail`、`/api/workbench/refresh-status`、`/api/workbench/events`、兼容期 `GET /api/workbench` 和 row detail 查询的只读边界。
- 必须梳理 worker refresh 到 `read_model.workbench_*` active generation 发布的动态时序。
- 必须显式覆盖 `app/worker.py`，避免只看到 API 到 builder 的半条 read model 链路。
- 必须比对后端 response 与 `web/src/features/workbench/api.ts`、`web/src/features/workbench/types.ts`，标记契约偏差、类型不符和前端未使用字段。
- 必须检查 SSE 长连接线程占用、断连退出、订阅释放、heartbeat/timeout/backpressure/cancellation 等资源风险。
- 必须检查 Workbench query/read-model 的可观测性基线，包括慢查询、DB timing、endpoint latency、Redis/cache、worker lag/backlog 和 freshness 状态。
- 产物应为 `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`，并可按真实发现更新 `runtime-call-chain.md`、`module-refactor-plan.md`、本文档和 `refactor-prompts.md`。

#### 禁止范围

- 不修改 Python 业务代码。
- 不修改 tests。
- 不修改 SQL migration。
- 不修改前端、网关、部署配置或生产配置。
- 不开始 Workbench 写操作、pair relation、exception、reconciliation、matching/candidates 或其他业务模块迁移。
- 不执行 Merge Gate 或 Traffic Gate。
- 不运行需要生产外部服务的命令。

#### 预期产物

- `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- `docs/architecture/backend-refactor/runtime-call-chain.md`（如 PF-P004 发现真实调用链，需要补 Workbench 章节）
- `docs/architecture/backend-refactor/module-refactor-plan.md`（如 PF-P004 校准子域顺序或边界）
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/migration-state-log.md`

#### 验收标准

- `refactor-prompts.md` 已包含完整 PF-P004 prompt。
- PF-P004 prompt 明确 Pre-Flight、Allowed Scope、Forbidden Scope、Required Discovery Output、Mandatory Checks、Verification、Post-Flight 和 Gate Scope。
- PF-P004 prompt 明确必须优先使用 CodeGraph 梳理静态调用链，再用 `rg` 补充 path、event、table、Redis key 和测试覆盖。
- PF-P004 prompt 明确补齐 4 个深水区侦察盲点：`app/worker.py`、前后端契约一致性、SSE 资源风险、可观测性埋点。
- PF-P004 prompt 明确只做发现和文档计划，不做业务代码或测试改动。
- PF-P004 prompt 明确执行完成后只能到 `implemented` 或 `blocked`，必须等待用户确认后才能 `verified`。

#### 下一条 Prompt 上下文

PF-P004 已执行完成，并已由用户确认 `verified`。本轮只做文档发现和计划，没有修改业务代码、测试、SQL migration、前端或部署配置。

#### 变更文件

- `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- `docs/architecture/backend-refactor/runtime-call-chain.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/migration-state-log.md`

#### CodeGraph / 文件覆盖

- 使用 CodeGraph 梳理 Workbench Query / Read Model 上下文，覆盖 `WorkbenchReadModelService`、`WorkbenchSqlProjectionBuilder`、`WorkbenchQueryService`、`WorkbenchReadModelRefreshService`。
- 使用 CodeGraph 定位 `server.py` 中 `_handle_api_workbench_summary`、`_handle_api_workbench_groups`、`_handle_api_workbench_group_detail`、`_handle_api_workbench_refresh_status`、`_handle_api_workbench_events`、`_handle_api_workbench`、`_handle_api_workbench_row_detail`。
- 覆盖 `app/worker.py` 中 `workbench.read_model.refresh` handler 注册链路。
- 覆盖 `PostgresReadModelRepository` 的 summary、groups page、group detail、refresh-status 和 save generation 边界。
- 使用 literal search 补充 API path、Redis key、`read_model.workbench_*` 表、dirty scope、outbox、source_version 和前端契约事实。

#### 关键发现

- Summary 和 groups 已基本走 SQL read model，missing/stale 时 enqueue refresh，不应在请求线程同步 rebuild。
- Groups Redis page cache 只在 refresh status fresh 时使用，key 需要继续保持 active generation / source_version 版本边界。
- Group detail 的 stale/missing 语义不如 summary/groups 明确，需要 PF-P005 先补 characterization tests。
- Row detail 仍存在 `LiveWorkbenchService`、cached read model、`WorkbenchQueryService` route 多级 fallback，是最高风险读路径之一。
- 兼容期 `GET /api/workbench` 仍可能 fallback legacy builder，需要先冻结响应契约再收口。
- SSE 当前是 refresh status polling，不是 Redis PubSub；没有 PubSub 订阅释放问题，但存在长连接线程占用、断连退出和 heartbeat 契约测试缺口。
- Worker refresh 通过 `app/worker.py` 注册 `workbench.read_model.refresh`，由 dirty scope source_version 和 outbox event 驱动 builder 写 building generation 并切 active generation。
- `all` scope 只应从 active month shards 聚合，相关 dirty scope completion 语义需要 PF-P005 用测试锁定。

#### 验证

- `git status --short --branch`：通过，当前仅文档文件变更。
- `git diff --check`：通过。
- `test -f docs/architecture/backend-refactor/workbench-read-model-query-plan.md`：通过。
- `rg -n "Scope Boundary|API Contract Matrix|Runtime Call Chain|Read Model Data Boundary|Current Risk|Test Matrix|Next Execution Slices|Guard Compatibility" docs/architecture/backend-refactor/workbench-read-model-query-plan.md`：通过。
- `rg -n "summary|groups|groups/detail|refresh-status|events|active generation|source_version|Redis|SSE|worker refresh|worker.py|contract-mismatch|frontend-used|PubSub|request_database_timing|api_performance_metrics" docs/architecture/backend-refactor/workbench-read-model-query-plan.md`：通过。
- 未运行 Python unit tests：PF-P004 禁止修改业务代码和测试，本轮只做文档发现。

#### 下一条 Prompt 上下文

PF-P004 已 verified。PF-P005 已生成并审查，下一步允许执行 PF-P005。PF-P005 只能先补/固定 Workbench query/read-model 的 characterization tests，重点覆盖 summary、groups、group detail、row detail fallback、refresh-status、SSE、worker refresh `all` scope 和 Redis versioned cache。PF-P005 不得开始 handler 薄化、repository 重构、legacy fallback 删除或 Traffic Gate。

### PF-P005 - Workbench Query Characterization Tests

状态：`verified`

#### 范围

- 作为 Workbench `query/read-model` 子域真正改代码前的测试锁定阶段。
- 只允许新增或调整 characterization tests、必要的 test fakes / fixtures，以及执行结果相关文档。
- 必须基于 PF-P004 的 `workbench-read-model-query-plan.md`，锁定现有行为，而不是按理想架构改写行为。
- 必须覆盖 summary、groups、group detail、row detail fallback、refresh-status、SSE、worker refresh `YYYY-MM` / `all` scope、Redis versioned cache、active generation 和 PF-P003 guard compatibility。
- 必须覆盖兼容期 `GET /api/workbench` / `_handle_api_workbench` legacy endpoint，锁定 SQL read model、refreshing/unavailable 和 legacy builder fallback 条件。
- 对 PF-P004 标记为 `backend-only` 或 `contract-mismatch` 的字段，测试必须保留字段断言；不得只断言前端当前使用字段。易变诊断字段只能断言 key/type/语义，不硬断言不稳定精确值。
- 必须防止测试状态污染（State Bleed）：PostgreSQL、Redis、dirty scope、outbox、generation 和 worker heartbeat 测试必须事务隔离、唯一 scope key、独立 fake 或显式清理。
- SSE 和 worker tests 必须 deterministic：不得使用真实 sleep、无限 generator 或不可控线程等待。
- 如果当前行为与 PF-P004 预期不一致，PF-P005 必须记录 discrepancy；不得修改生产代码来让测试通过。

#### 禁止范围

- 不修改 Python 生产代码。
- 不修改 SQL migration。
- 不修改前端、网关、部署配置或生产配置。
- 不薄化 handler，不新增 query facade，不重构 repository，不删除 legacy fallback。
- 不修改 Workbench 写路径、matching/candidates、pair relation、exception、reconciliation 或其他业务模块。
- 不执行 Merge Gate 或 Traffic Gate。
- 不访问生产 DB、Redis、RabbitMQ、OA Mongo、OA MySQL、MinIO/S3。

#### 预期产物

- 更新或新增 Workbench query/read-model characterization tests。
- 可按测试事实更新 `workbench-read-model-query-plan.md` 的测试矩阵或风险记录。
- 更新 `refactor-prompts.md` 和本文档。

#### 变更文件

- `tests/test_workbench_sql_runtime.py`
- `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`

#### 执行结果

- 已实现，用户已确认，当前状态为 `verified`。
- 本轮只修改测试和重构文档；未修改 `backend/src/fin_ops_platform/` 生产代码、SQL migration、前端、网关、部署或生产配置。
- 已在 `tests/test_workbench_sql_runtime.py` 新增 7 个 characterization tests：
  - 兼容期 `GET /api/workbench` SQL read-model path 保留 `diagnostics`、`invoice_inventory`、`active_generation_id`、`read_model_version`、`rows_page`、`read_model_generated_at` 等 backend-only / contract-mismatch 字段。
  - 兼容期 `GET /api/workbench` 在 legacy bootstrap 且 SQL runtime 非强制时 fallback `_build_api_workbench_payload`。
  - PostgreSQL production runtime 缺失 SQL read repository 时返回 `503 read_model_unavailable`，并 enqueue `api_sql_repository_unavailable`，不 fallback legacy builder。
  - Summary missing payload 返回 `202 refreshing`，并 enqueue `api_summary_miss`。
  - Summary stale source_versions 保留 backend-only 字段，并锁定当前 stale reasons 为 `builder_mismatch`、`bank_auto_tag_rules_version_missing` 等现状行为。
  - Groups refresh status stale/refreshing 时绕过旧 Redis cached payload，读取 DB page，并 enqueue `api_groups_source_versions_stale`。
  - SSE response 锁定 `text/event-stream`、`Cache-Control: no-cache, no-transform`、`X-Accel-Buffering: no` 和 deterministic heartbeat event。
- 已复用 `tests/test_workbench_v2_api.py` 现有 row detail targeted tests 覆盖 live/cached/404/多来源 row detail 路径。
- 发现并记录一个现状差异：PF-P004 预期中的 stale reason 名称不是当前实现实际输出；当前实现使用 `builder_mismatch`，同时会补齐多个 parser/rules version missing reasons。
- 发现并记录一个现状行为：Groups 在 refresh status stale/refreshing 时不会读取旧 Redis JSON payload，但仍会把 fresh DB payload 写回 Redis；PF-P006 需要判断是否继续保留。

#### 验收标准

- PF-P005 prompt 已写入 `refactor-prompts.md`。
- PF-P005 prompt 明确 Pre-Flight、Allowed Scope、Forbidden Scope、Required Test Work、Mandatory Checks、Post-Flight 和 Gate Scope。
- PF-P005 prompt 明确禁止生产代码改动。
- PF-P005 prompt 明确如果新增测试不能在现有实现上通过，必须先判断是否测试假设错误；不能直接改生产逻辑。
- PF-P005 prompt 明确 legacy compatibility、backend-only / contract-mismatch 字段保留、State Bleed 防范和 deterministic tests 规则。
- PF-P005 prompt 明确执行后只能到 `implemented` 或 `blocked`，必须等待用户确认后才能 `verified`。

#### 验证

- 新增 PF-P005 tests targeted run：通过，7 tests passed。
- Workbench query/read-model targeted suite：通过，24 tests passed。
- Row detail targeted suite：通过，4 tests passed。
- PF-P003 platform runtime boundary guards：通过，9 tests passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`：通过，102 tests passed。
- `git diff --check`：通过。
- `rg` 文档门禁：通过。

#### 未覆盖 / 风险

- 本轮未新增生产代码，未修复 row detail fallback、group detail stale/missing 语义、legacy fallback 或 SSE cancellation。
- SSE 只锁定 headers、首个 event 和 heartbeat；当前实现的长连接断开退出仍需 PF-P006 在不引入真实 sleep / 无限等待的前提下继续设计。
- Worker refresh `all` scope 已由现有 tests 覆盖关键路径，本轮未新增 worker 生产路径测试。
- `tests/test_workbench_query_service.py` 和 `tests/test_workbench_read_model_service.py` 未新增测试；现有 row detail 和 SQL runtime targeted tests 已覆盖本轮选择的高风险读路径。

#### 下一条 Prompt 上下文

PF-P005 已 verified。PF-P005-MG 已生成并审查，下一步允许执行 PF-P005-MG。PF-P005-MG 只允许做范围检查、上游同步、精准 staging、commit、merge 到 main 前后验证和状态机回写；不得开始 handler/facade/repository 生产代码重构，不得执行 Traffic Gate。

### PF-P005-MG - Workbench Query Characterization Tests Merge Gate

状态：`verified`

#### 范围

- 只处理 PF-P005 已 verified 的 test-only / docs-only 变更合入主干门禁。
- 必须确认 PF-P005 状态为 `verified`。
- 必须确认本次变更范围只包含：
  - `tests/test_workbench_sql_runtime.py`
  - `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
  - `docs/architecture/backend-refactor/runtime-call-chain.md`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
- 必须把未跟踪文件纳入范围审计，严禁误提交临时文件、缓存文件、`.pkl`、`.sqlite`、导出物或测试产物。
- 必须显式执行 `git ls-files --others --exclude-standard` 审计 untracked files。
- `tests/test_workbench_v2_api.py` 只是 PF-P005 复用并运行的现有测试文件，不在当前白名单中；如果它被修改，PF-P005-MG 必须阻断并重新审查。
- 必须精准 `git add <具体文件>`，严禁 `git add .` 或 `git add -A`。
- 必须先同步最新 `origin/main` / `main`，如果同步后发生变化，必须重新执行 PF-P005-MG 验证测试。
- 如果当前已经在 `main`，不得做无意义 merge，只做范围检查、必要 commit、验证和状态机更新。

#### 禁止范围

- 不修改生产代码。
- 不修改 SQL migration。
- 不修改前端、网关、部署配置或生产配置。
- 不开始 PF-P006 handler/facade/repository 重构。
- 不执行 Traffic Gate。
- 不部署服务器，不推送生产，不访问生产外部服务。

#### 预期验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- Row detail targeted tests。
- `rg` 检查 PF-P005 / PF-P005-MG 状态和文档门禁。

#### 执行结果

- 已执行，用户已确认，当前状态为 `verified`。
- PF-P005 变更已精准 stage 并提交，提交为 `2bb3ac17`（`test(workbench): lock query read model characterization baseline`）。
- 当前分支已切回 `main`，并通过 fast-forward merge 将 `codex/workbench-read-model-query-plan` 合入 `main`。
- `main` 未 push 到 `origin/main`。
- 未执行 Traffic Gate，未部署服务器，未访问生产外部服务。
- 合入范围只包含 tests/docs：
  - `tests/test_workbench_sql_runtime.py`
  - `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
  - `docs/architecture/backend-refactor/runtime-call-chain.md`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
- 未修改生产代码、SQL migration、前端、网关、部署或生产配置。
- `git ls-files --others --exclude-standard`：合入前仅出现允许的新文档；合入 main 后无 untracked files。
- `tests/test_workbench_v2_api.py` 未修改，只作为 row detail targeted tests 复用。

#### main 上验证结果

- `git status --short --branch`：`main...origin/main [ahead 1]`。
- `git ls-files --others --exclude-standard`：无输出。
- `git diff --name-only`：无输出。
- `git diff --check`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`：通过，102 tests passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：通过，9 tests passed。
- Row detail targeted tests：通过，4 tests passed。
- PF-P005 / PF-P005-MG 文档门禁 `rg`：通过。
- 新增 characterization test 锚点 `rg`：通过。

#### 下一条 Prompt 上下文

PF-P005-MG 已 verified。`main` 已 push 到 `origin/main`，远端测试基线已生效，`main` 与 `origin/main` 均为 `fd75f9ee`。PF-P006 已生成并审查，下一步必须等待用户确认后才能执行 PF-P006。PF-P006 从 Workbench Query Facade Extraction (Slice B) 开始，目标是在 PF-P005 characterization tests 保护下薄化 summary/groups/group detail/refresh-status handler；不得直接执行。

### PF-P006 - Workbench Query Facade Extraction (Slice B)

状态：`verified`

#### 范围

- 在 PF-P005 characterization tests 保护下，做 Workbench `query/read-model` 子域的第一轮生产代码最小切片。
- 目标是抽取 Query Facade，薄化以下只读 handler 的 orchestration：
  - `_handle_api_workbench_summary`
  - `_handle_api_workbench_groups`
  - `_handle_api_workbench_group_detail`
  - `_handle_api_workbench_refresh_status`
- handler 仍负责 HTTP 参数入口、Response 包装和 server 层错误边界；facade 负责 read repository、freshness、refresh enqueue、Redis page cache 和 payload contract 的调度。
- Facade 不得 import `Application` 或 HTTP `Response`，必须通过显式依赖、callable 或轻量 data/result object 与 `server.py` 解耦，避免反向依赖。
- Facade 必须使用细粒度依赖注入；不得接收 `Application`、`RuntimeRepositories`、`RuntimeRepositoryContext`、`ApplicationStateStore`、`StateStoreProtocol` 或其他全局 runtime container，避免把 `server.py` 的耦合搬到新的上帝对象。
- HTTP route/request 上下文相关的 observability wrapper（例如 `request_database_timing`）必须留在 `server.py` handler 层；纯 Workbench read-model 状态指标（例如 `_emit_workbench_read_model_status_metric`）可以移动或通过 metric emitter 注入 Facade，但指标语义必须保持。

#### 禁止范围

- 不改写 `GET /api/workbench` legacy compatibility endpoint。
- 不改写 row detail fallback。
- 不改写 SSE / events 长连接行为。
- 不改写 worker refresh、builder、repository SQL 或 SQL migration。
- 不修改 Workbench 写路径、matching/candidates、pair relations、exceptions、reconciliation。
- 不修改前端、网关、部署配置或生产配置。
- 不执行 Merge Gate 或 Traffic Gate。

#### 执行约束

- 必须先跑 PF-P005 已建立的 baseline tests。
- 必须保持 API response contract、status code、stale reason、Redis key 格式、refresh enqueue reason 和 backend-only / contract-mismatch 字段不变。
- 如果 extraction 导致测试需要改 expected payload，默认视为行为变更，必须停止并记录 discrepancy，不得为了让测试通过而顺手改契约。
- 不得用 mock/patch 绕过 `WorkbenchQueryFacade` 来修改 `tests/test_workbench_sql_runtime.py`；PF-P005 characterization tests 必须继续覆盖 `Application handler -> WorkbenchQueryFacade -> repository / queue / redis fake` 的真实链路。
- 如果新建 facade public methods，优先补充低成本 facade unit tests；不得复制巨型端到端测试。

#### 变更文件

- `backend/src/fin_ops_platform/services/workbench_query_facade.py`：新增 `WorkbenchQueryFacade` 和 `WorkbenchQueryResult`，收口 summary / groups / group detail / refresh-status orchestration。
- `backend/src/fin_ops_platform/app/server.py`：四个 Workbench query/read-model handler 改为薄 wrapper，继续负责 HTTP 参数校验和 `_json_response` 包装。
- `tests/test_workbench_query_facade.py`：新增低成本 facade unit tests，验证细粒度依赖和 Redis cache hit 行为。
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`

#### 执行结果

- PF-P006 已按 TDD 执行：先新增 `tests/test_workbench_query_facade.py`，确认因 `ModuleNotFoundError: fin_ops_platform.services.workbench_query_facade` 失败，再实现 facade。
- `Application` 没有注入给 Facade；`RuntimeRepositories` / `RuntimeRepositoryContext` 没有作为 Facade constructor 参数传入。
- `tests/test_workbench_sql_runtime.py` 未改成 mock facade 测试；PF-P005 黑盒 characterization tests 仍覆盖 handler 到 facade 再到 fake repository / queue / redis 的路径。
- `request_database_timing` 未进入 `workbench_query_facade.py`；HTTP route timing wrapper 仍归 handler/app shell 边界。
- 未修改 SQL migration、前端、网关、部署配置或生产配置。
- 未执行 Merge Gate、Traffic Gate 或 push。

#### 预期验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- Row detail targeted tests。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- 静态检查 Facade 上帝对象注入风险：`WorkbenchQueryFacade(...)` 不得出现 `Application`、`RuntimeRepositories`、`RuntimeRepositoryContext`、`ApplicationStateStore`、`StateStoreProtocol` 或 `state_store` 依赖。
- 静态检查测试保真度：`tests/test_workbench_sql_runtime.py` 不得 mock/patch `WorkbenchQueryFacade` 或 `workbench_query_facade`。
- 静态检查 observability 边界：如存在 `workbench_query_facade.py`，`request_database_timing` 不得进入该文件。

#### 已执行验证

- `git status --short --branch`：通过；显示预期变更文件和两个新增文件。
- `git ls-files --others --exclude-standard`：输出 `backend/src/fin_ops_platform/services/workbench_query_facade.py`、`tests/test_workbench_query_facade.py`，均为本轮预期新增文件，不是临时产物。
- `git diff --check`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`：通过，2 tests passed。
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`：通过，102 tests passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：通过，9 tests passed。
- Row detail targeted tests：通过，4 tests passed。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`：通过，status `ready`。
- `rg -n "WorkbenchQueryFacade\\([^\\n]*(Application|RuntimeRepositories|RuntimeRepositoryContext|ApplicationStateStore|StateStoreProtocol|state_store)" backend/src/fin_ops_platform tests`：无输出，符合上帝对象注入门禁。
- `rg -n "mock\\.patch\\(.+WorkbenchQueryFacade|patch\\(.+workbench_query_facade|monkeypatch.+WorkbenchQueryFacade|WorkbenchQueryFacade.*Mock|Mock.*WorkbenchQueryFacade" tests/test_workbench_sql_runtime.py`：无输出，符合测试保真门禁。
- `test ! -f backend/src/fin_ops_platform/services/workbench_query_facade.py || ! rg -n "request_database_timing" backend/src/fin_ops_platform/services/workbench_query_facade.py`：通过，符合 observability 边界。

#### 下一条 Prompt 上下文

PF-P006 已由用户确认 `verified`。PF-P006-MG 已生成并审查，下一步允许执行 `PF-P006-MG - Workbench Query Facade Merge Gate`。PF-P006-MG 只处理本轮 facade extraction 的范围审计、上游同步、精准提交、合并前后验证和状态机回写；不得执行 Traffic Gate，不得部署服务器，不得直接进入 Slice C。

### PF-P006-MG - Workbench Query Facade Merge Gate

状态：`verified`

#### 范围

- 只处理 PF-P006 已 verified 的 Workbench Query Facade extraction 合入 `main` 的 Merge Gate。
- 允许范围审计、上游同步检查、精准 staging、commit、merge 到 main 前后验证和状态机回写。
- 不执行 Traffic Gate、不部署服务器、不修改生产配置、不访问生产外部服务。
- 不开始 Slice C、Workbench cache/freshness 语义改造、SSE、row detail、legacy `GET /api/workbench` 或任何写路径重构。

#### Expected Changed Files

PF-P006-MG 允许合入的文件仅限：

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_query_facade.py`
- `tests/test_workbench_query_facade.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`

`tests/test_workbench_sql_runtime.py` 是 PF-P005 characterization baseline 和 PF-P006-MG 验证目标，不属于本轮 Expected Changed Files。若该文件出现 changed / staged 状态，PF-P006-MG 必须阻断并审查原因，不得临时加入白名单。

如出现其它 changed / untracked 文件，必须先阻断并审查来源；不得静默加入白名单。

#### 必须保留的门禁

- 不得使用 `git add .` 或 `git add -A`，只能精准 `git add <具体文件>`。
- 必须运行 `git ls-files --others --exclude-standard`，并确认未跟踪文件只包含本轮预期新增文件。
- 必须确认 `tests/test_workbench_sql_runtime.py` 未被改成 mock facade 测试。
- 必须确认 `WorkbenchQueryFacade` 没有注入 `Application`、`RuntimeRepositories`、`RuntimeRepositoryContext`、`ApplicationStateStore`、`StateStoreProtocol` 或 `state_store`。
- 必须确认 `request_database_timing` 未进入 `workbench_query_facade.py`。
- merge 到 `main` 前必须同步最新 `origin/main`；如同步带来变化，必须重新执行 mandatory checks。
- Push 到 `origin/main` 需要用户明确允许；PF-P006-MG 不默认 push。

#### 预期验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --name-only`
- `git diff --stat`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- `git diff --quiet -- tests/test_workbench_sql_runtime.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- Row detail targeted tests。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- Facade 上帝对象注入静态检查。
- Facade mock 静态检查。
- `request_database_timing` 边界静态检查。

#### 下一条 Prompt 上下文

PF-P006-MG 已由用户确认 `verified`。`main` 已 push 到 `origin/main`，远端基线包含 PF-P006-MG 与 PF-P007 planning 文档。下一步允许执行已生成并审查的 `PF-P007 - Workbench Query Cache and Freshness Boundary (Slice C)`；不得直接开始 Slice D、Traffic Gate、部署或生产变更。

#### 执行结果

- Feature branch：`codex/workbench-query-facade-prompt`。
- Commit：`8937bb15 refactor(workbench): extract query read model facade`。
- Merge 方式：`main` 与 `origin/main` 执行前均为 `fd75f9ee`，`main` 通过 fast-forward 合入 `8937bb15`。
- 合入范围只包含 Expected Changed Files：`server.py`、`workbench_query_facade.py`、`test_workbench_query_facade.py` 和三份 backend-refactor 文档。
- 未修改 SQL migration、前端、网关、部署配置或生产配置。
- 未执行 Traffic Gate，未部署服务器；随后按用户确认已 push 到 `origin/main`。

#### Feature branch 验证结果

- `git status --short --branch`：仅 PF-P006 expected files。
- `git ls-files --others --exclude-standard`：仅本轮预期新增 `workbench_query_facade.py` 和 `test_workbench_query_facade.py`。
- `git diff --name-only` / `git diff --stat` / `git diff --check`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`：通过，2 tests passed。
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`：通过，102 tests passed。
- `git diff --quiet -- tests/test_workbench_sql_runtime.py`：通过，该文件无变更。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：通过，9 tests passed。
- Row detail targeted tests：通过，4 tests passed。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`：通过，status `ready`。
- Facade 上帝对象注入静态检查：无输出，通过。
- Facade mock 静态检查：无输出，通过。
- `request_database_timing` 边界静态检查：通过。

#### 远端同步结果

- `git push origin main`：通过，`origin/main` 从 `fd75f9ee` 更新到 `87d738de`。
- 本次 push 只推送 Git 远端主干；未推送或重启服务器，未修改部署配置，未执行 Traffic Gate。

### PF-P007 - Workbench Query Cache and Freshness Boundary (Slice C)

状态：`verified`

#### 范围

- 只处理 Workbench query/read-model 的 cache 与 freshness 边界。
- 允许在 PF-P006 已抽出的 `WorkbenchQueryFacade` 周边补测试并做最小实现。
- 目标是统一 active generation、source_version、Redis key、stale/refreshing 语义。
- 不执行 Traffic Gate、不部署服务器、不修改生产配置、不访问生产外部服务。
- 不开始 Slice D，不修改 legacy `GET /api/workbench`、row detail fallback、SSE 断连语义、worker refresh、builder 或写路径。

#### 预期产物

- 补齐或调整 Workbench cache/freshness 相关测试。
- 如测试要求，最小调整 `WorkbenchQueryFacade` 或其细粒度 helper / adapter 调度。
- 更新 `workbench-read-model-query-plan.md` 中 Slice C 的执行结果和后续 Slice D 输入。
- 更新本文档和 `refactor-prompts.md`。

#### 预期验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- Row detail targeted tests。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- Facade god-object injection / mock / observability 边界静态检查。

#### 执行结果

- 执行分支：`codex/workbench-query-cache-freshness`。
- 变更范围包含 Slice C 允许文件：`workbench_query_facade.py`、`tests/test_workbench_query_facade.py`、`tests/test_workbench_sql_runtime.py`，以及用户要求同步固化的 backend-refactor 工作流文档。
- 新增 facade unit test 先复现缺口：refresh-status 为 `refreshing` 时，旧实现虽然不读旧 Redis JSON payload，但仍会把 fresh-looking DB payload 写回 Redis。
- 最小实现：`WorkbenchQueryFacade.groups(...)` 写 Redis JSON payload 时同时要求 `can_use_groups_redis_cache` 为 true；因此 stale / refreshing / unavailable freshness gate 未通过时，只返回 DB payload，不写入可复用缓存。
- HTTP characterization 同步更新：`test_workbench_groups_api_stale_refresh_status_bypasses_redis_payload` 明确断言不读取旧 Redis JSON payload，也不写入新 Redis JSON payload。
- Redis key active generation / schema version / detail/search/filter/sort 维度继续由既有 tests 锁定。
- TTL 评估：当前 key 已强版本化，理论上可放宽 TTL；PF-P007 保留现有 `60-900s` bounded TTL 和默认 `600s`，避免在没有 Redis memory / cardinality 指标前改变缓存驻留策略。后续若要调长 TTL，应独立用 Redis maxmemory、eviction、key cardinality 和 hit-rate 指标决策。
- 按用户要求固化分支共址工作流：prompt 生成/审查、状态机、实现和对应 Merge Gate 必须在同一功能分支内完成；MG 合入 main 后，下一条 prompt 必须从最新 main 的新分支开始。
- 未修改 SQL migration、前端、网关、部署配置、生产配置、SSE、worker、builder、repository SQL 或 Workbench 写路径。
- 未执行 Traffic Gate，未部署服务器，未访问生产外部服务。

#### 验证结果

- `git status --short --branch`：`codex/workbench-query-cache-freshness...origin/main`，仅 PF-P007 允许范围文件有变更。
- `git ls-files --others --exclude-standard`：无输出。
- `git diff --name-only` / `git diff --stat`：包含 `workbench_query_facade.py`、`tests/test_workbench_query_facade.py`、`tests/test_workbench_sql_runtime.py`、三份 PF-P007 状态文档，以及本轮用户要求固化的 `ai-execution-rules.md`。
- `git diff --check`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`：通过，3 tests passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`：通过，102 tests passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：通过，9 tests passed。
- Row detail targeted tests：通过，4 tests passed。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`：通过，status `ready`。
- Facade 上帝对象注入静态检查：无输出，通过。
- Facade mock 静态检查：无输出，通过。
- `request_database_timing` 边界静态检查：通过。
- 文档状态检查：通过，PF-P006-MG 保持 `verified`，PF-P007 为 `implemented`。

#### 下一条 Prompt 上下文

PF-P007 已由用户确认 `verified`。PF-P007-MG 已生成并审查，下一步允许执行 `PF-P007-MG - Workbench Query Cache and Freshness Merge Gate`。PF-P007-MG 只处理本轮 cache/freshness gate 改动和同分支工作流文档修正的合入门禁；不得执行 Traffic Gate，不得部署服务器，不得直接进入 Slice D。

### PF-P007-MG - Workbench Query Cache and Freshness Merge Gate

状态：`planned`

#### 范围

- 只处理 PF-P007 已 verified 变更进入 `main` 的 Merge Gate。
- 允许范围审计、上游同步检查、精准 staging、commit、合并前验证、合入 `main`、main 上复验和状态机回写。
- 不执行 Traffic Gate、不部署服务器、不修改生产配置、不访问生产外部服务。
- 不开始 Slice D、legacy `GET /api/workbench` fallback、row detail fallback、SSE、worker、builder、repository SQL 或任何写路径重构。

#### Expected Changed Files

PF-P007-MG 允许合入的文件仅限：

- `backend/src/fin_ops_platform/services/workbench_query_facade.py`
- `tests/test_workbench_query_facade.py`
- `tests/test_workbench_sql_runtime.py`
- `docs/architecture/backend-refactor/ai-execution-rules.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`

如出现其它 changed / untracked 文件，必须先阻断并审查来源；不得静默加入白名单。

#### 必须保留的门禁

- 不得使用 `git add .` 或 `git add -A`，只能精准 `git add <具体文件>`。
- 必须运行 `git ls-files --others --exclude-standard`，并确认没有未跟踪文件混入。
- 必须确认 PF-P007 的 cache/freshness 行为：stale / refreshing / unavailable 时不读取旧 Redis JSON payload，也不写入新的 Redis JSON payload。
- 必须确认 `WorkbenchQueryFacade` 没有注入 `Application`、`RuntimeRepositories`、`RuntimeRepositoryContext`、`ApplicationStateStore`、`StateStoreProtocol` 或 `state_store`。
- 必须确认 `tests/test_workbench_sql_runtime.py` 没有 mock/patch Facade。
- 必须确认 `request_database_timing` 未进入 `workbench_query_facade.py`。
- merge 到 `main` 前必须同步最新 `origin/main`；如同步带来变化，必须重新执行 mandatory checks。
- Push 到 `origin/main` 需要用户明确允许；PF-P007-MG 不默认 push。

#### 预期验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --name-only`
- `git diff --stat`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`
- Row detail targeted tests。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- Facade 上帝对象注入静态检查。
- Facade mock 静态检查。
- `request_database_timing` 边界静态检查。

#### 下一条 Prompt 上下文

PF-P007-MG 是 Merge Gate，不是 Traffic Gate。执行完成后只能进入 `implemented` 或 `blocked`，必须等待用户确认后才能标记 `verified`。PF-P007-MG verified 且 `main` 推送完成后，下一步必须从最新 `main` 创建新分支，再生成下一条 prompt；不得在旧功能分支继续开始 Slice D。

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

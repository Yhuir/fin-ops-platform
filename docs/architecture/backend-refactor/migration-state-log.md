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
- Merge Gate 的粒度是一个可合并的模块任务、platform 边界任务或明确命名的模块切片，不是每个 prompt；同一任务可以由多个已确认 `verified` 的 prompt 组成。
- 测试锁定 prompt、发现 prompt 和实现 prompt 可以在同一功能分支连续推进；只有该模块任务/切片达到可合并状态后，才生成对应的 `*-MG`。
- 不得因为跳过单个 prompt 的 MG 而跳过最终 MG；最终 MG 必须覆盖该功能分支内尚未合入 `main` 的全部 prompt diff。
- 未完成当前模块任务/切片的 MG 并合入 `main` 前，不得进入下一个模块或无关切片。
- Merge Gate 合入并复验 `main` 后，下一条 prompt 必须从最新 `main` 新建分支再生成；不得在 `main` 或旧功能分支上继续生成下一个模块的 prompt。
- 每次 prompt 完成后，最终回复必须告诉用户下一步建议做什么。
- 每次 prompt 执行后，必须精准回写本文档和受执行结果影响的架构文档；未完成回写前不得生成或执行下一条 prompt。
- 后续所有新生成的执行 prompt 正文必须以 `/goal` 开头。
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
| 当前阶段 | `PF-P121 - Turnover Ledger Facade None Fallback Characterization Tests` 已执行并验证通过 |
| 当前 active prompt | `PF-P121 - Turnover Ledger Facade None Fallback Characterization Tests` |
| 最近 verified prompt | `PF-P121 - Turnover Ledger Facade None Fallback Characterization Tests` |
| 当前分支 | `codex/turnover-ledger-remaining-boundary-p120` |
| 最近验证 | `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，61 tests；`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests |
| 下一条允许任务 | 生成并审查 `PF-P122 - Turnover Ledger Facade None Fallback Cleanup Planning` |

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

状态：`verified`

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

PF-P007-MG 已由用户确认 `verified`，并已同步到 `origin/main`。本次 verified 状态只代表 Merge Gate 完成，不代表 Traffic Gate 或部署完成。下一步必须从最新 `main` 创建新分支，再生成下一条 prompt；不得在旧功能分支继续开始 Slice D。

#### 执行结果

- Feature branch：`codex/workbench-query-cache-freshness`。
- Commit：`08ccad92 refactor(workbench): enforce query cache freshness gate`。
- Merge 方式：`main` 与 `origin/main` 执行前均为 `be04b10c`，`main` 通过 fast-forward 合入 `08ccad92`。
- 合入范围只包含 Expected Changed Files：`workbench_query_facade.py`、`test_workbench_query_facade.py`、`test_workbench_sql_runtime.py`、`ai-execution-rules.md`、`migration-state-log.md`、`refactor-prompts.md`、`workbench-read-model-query-plan.md`。
- 未修改 SQL migration、前端、网关、部署配置、生产配置、SSE、worker、builder、repository SQL 或 Workbench 写路径。
- `git push origin main` 已通过，`origin/main` 已包含 PF-P007 和 PF-P007-MG 结果。
- 未执行 Traffic Gate，未部署服务器。

#### Feature branch 验证结果

- `git status --short --branch` / `git ls-files --others --exclude-standard` / `git diff --name-only` / `git diff --stat` / `git diff --check`：通过，范围只包含 Expected Changed Files，无 untracked 混入。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`：通过，3 tests passed。
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`：通过，102 tests passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：通过，9 tests passed。
- Row detail targeted tests：通过，4 tests passed。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`：通过，status `ready`。
- Facade 上帝对象注入静态检查：无输出，通过。
- Facade mock 静态检查：无输出，通过。
- `request_database_timing` 边界静态检查：通过。

#### main 上验证结果

- `git status --short --branch`：`main...origin/main [ahead 1]`。
- `git ls-files --others --exclude-standard`：无输出。
- `git diff --check`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`：通过，3 tests passed。
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`：通过，102 tests passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：通过，9 tests passed。
- Row detail targeted tests：通过，4 tests passed。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`：通过，status `ready`。
- Facade 上帝对象注入静态检查：无输出，通过。
- Facade mock 静态检查：无输出，通过。
- `request_database_timing` 边界静态检查：通过。

### PF-P008 - Workbench Query Fallback / SSE / Observability Characterization (Slice D-A)

状态：`verified`

#### 范围

- 只生成和审查 Workbench Query Slice D 的第一步：fallback、SSE 和 observability characterization tests。
- 锁定兼容期 `GET /api/workbench` 的 SQL read model / legacy builder fallback 行为。
- 锁定 row detail 的 `LiveWorkbenchService`、cached read model、`WorkbenchQueryService` route fallback 顺序和字段一致性。
- 锁定 `GET /api/workbench/events` SSE headers、event name、heartbeat 和有限迭代行为；记录客户端断开 / generator cancellation 未覆盖的缺口。
- 锁定 `request_database_timing` / API performance recorder 对 Workbench query 关键路径的观测性基线。

#### 分支

- `codex/workbench-query-slice-d-prompt`

#### 变更文件

- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`

#### 计划约束

- PF-P008 不是实现型 fallback 优化 prompt。
- PF-P008 不得修改生产代码，不得删除 legacy path，不得改变 SSE 行为。
- PF-P008 不执行 Merge Gate，不执行 Traffic Gate，不部署服务器，不 push `origin/main`。
- PF-P008 只能增加或整理 tests 与文档；执行完成后状态只能为 `implemented` 或 `blocked`，必须等待用户确认才能 `verified`。

#### 下一条 Prompt 上下文

PF-P008 已由用户确认 `verified`。本轮不单独执行 PF-P008-MG；按照“同一功能分支可承载一个或多个连续实现，最后统一 MG”的工作流，下一步允许在当前分支生成并审查 PF-P009。PF-P009-MG 必须在后续统一覆盖 PF-P008 测试基线与 PF-P009 生产代码变更，不得跳过 main 合入门禁。

#### 执行结果

- 分支：`codex/workbench-query-slice-d-prompt`。
- 变更文件：
  - `tests/test_workbench_sql_runtime.py`
  - `tests/test_api_performance_metrics.py`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
  - `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- 新增 characterization：
  - SSE status event mapping：`fresh -> workbench.read_model.completed`、`refreshing/stale -> workbench.read_model.progress`、`failed -> workbench.read_model.failed`，并用 exploding Redis helper 锁定当前 SSE 不走 Redis PubSub。
  - Row detail live hit 优先级和 `apply_to_row` 最终应用。
  - Row detail live miss + cached read model miss 后 route service fallback 触发条件和 `apply_to_row` 最终应用。
  - `Application.handle_request` 对 Workbench groups route 的 `ApiPerformanceRecorder` / `request_database_timing` 基线。
- 已有等价覆盖继续作为 PF-P008 输入：
  - legacy `GET /api/workbench` SQL hit 不调用 legacy builder。
  - SQL read model missing 返回 `202 refreshing` 并 enqueue `api_miss`。
  - PostgreSQL production runtime 下 repository unavailable 返回 `503 read_model_unavailable` 并 enqueue `api_sql_repository_unavailable`。
  - legacy / non-production runtime 下仍允许 fallback legacy builder。
  - opaque OA row detail 无 cached read model 时返回 404，且不触发 full OA sync。
- 未修改 `backend/src/fin_ops_platform/` 生产代码、SQL migration、前端、网关、部署或生产配置。
- 未执行 Merge Gate，未执行 Traffic Gate，未 push `origin/main`。

#### 验证结果

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`：通过，105 tests passed。
- Row detail targeted tests：通过，4 tests passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade -v`：通过，3 tests passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_api_performance_metrics -v`：通过，3 tests passed。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：通过，9 tests passed。
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`：通过。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`：通过，status `ready`。
- Production code immutability check：通过，`backend/src/fin_ops_platform`、`web`、`postgres`、`deploy` 无 diff。
- Facade 上帝对象注入静态检查：无输出，通过。
- Facade mock 静态检查：无输出，通过。
- `request_database_timing` 边界静态检查：通过。

#### 仍未关闭风险

- SSE 客户端断开后的 generator cancellation / 线程占用仍未通过生产代码关闭；本轮只锁定当前可测试行为。
- legacy `GET /api/workbench` fallback 仍存在；本轮只锁定行为，不收口。
- row detail 多级 fallback 仍存在；本轮只锁定顺序和 override 应用，不收口到 active generation。
- Observability 仍只有 app-shell route 级基线；未新增 groups page/count/filter/search 子查询细粒度标签。

#### 下一条 Prompt 上下文

PF-P008 是 Slice D-A 的测试锁定，已 verified，但尚未合入 main。用户明确允许跳过单独的 PF-P008-MG，在同一功能分支继续生成 Slice D-B 实现 prompt。PF-P009 必须复用 PF-P008 测试护城河，先补充任何必要的 failing tests，再逐项收口 legacy fallback、row detail fallback 和 SSE 资源风险。PF-P009 不得一次性删除 legacy path，不得改变 API response contract，不得执行 Merge Gate / Traffic Gate / 部署 / push。PF-P009 完成后若要合入 main，必须生成 PF-P009-MG，统一验证并合并 PF-P008 + PF-P009 的完整 diff。

### PF-P009 - Workbench Query Fallback and SSE Mitigation (Slice D-B)

状态：`verified`

#### 范围

- 在 PF-P008 verified 的测试护城河下，逐项缩小 Workbench query/read-model 的请求线程 fallback 风险。
- 处理 legacy `GET /api/workbench` 在 production PostgreSQL runtime 下的 legacy builder fallback 边界。
- 处理 row detail 多级 fallback 的触发条件和 `apply_to_row` 一次性应用边界。
- 缓解 SSE streaming generator 的资源释放 / cancellation 风险；如果当前 HTTP abstraction 无法可靠感知客户端断开，必须记录 limitation，不得伪造完成。
- 保持 app-shell observability，不把 `request_database_timing` 下沉到 facade；只在必要时补低基数模块级指标。

#### 禁止范围

- 不开始 Workbench 写路径、matching/candidates、Turnover Ledger、Batch Accounting 或其他模块迁移。
- 不修改 SQL migration、前端、网关、部署配置或生产配置。
- 不修改 worker refresh、builder、read model repository SQL、RabbitMQ、Outbox、Dirty Scope 事实源。
- 不执行 Merge Gate、Traffic Gate、部署或 push。
- 不访问生产 DB、Redis、RabbitMQ、OA Mongo、OA MySQL、MinIO/S3。

#### 验收标准

- PF-P009 prompt 已写入 `refactor-prompts.md` 并完成审查。
- PF-P009 必须声明 PF-P008 已 verified 但未单独合入 main，本分支后续需要 PF-P009-MG 统一合并。
- PF-P009 必须包含 Pre-Flight、TDD、Allowed Scope、Forbidden Scope、Mandatory Checks、Post-Flight 和 Gate Scope。
- PF-P009 必须明确执行后只能到 `implemented` 或 `blocked`，未经用户确认不得标记 `verified`。

#### 执行结果

- 分支：`codex/workbench-query-slice-d-prompt`。
- 生产代码变更：
  - `backend/src/fin_ops_platform/app/server.py`
  - `Application.__init__` 增加 Workbench SSE active stream registry 和 lock。
  - `_handle_api_workbench_events(...)` 在 generator 第一次迭代时记录 active stream，并在 `close()` / generator finalization 时释放 active slot。
  - `_get_api_workbench_row_detail_payload(...)` 增加 `_workbench_row_detail_route_fallback_allowed(...)` gate：production PostgreSQL runtime 下，live miss + cached read model miss 后，仅当 route query service 已有本地 row record 时才允许 route fallback；否则返回 404。
  - `_requires_sql_read_model_runtime(...)` 改为使用 `getattr` 读取 `_bootstrap_mode`，让局部 helper / tests 在未完整初始化的 `Application` 上保持 legacy-compatible false。
- 测试变更：
  - `tests/test_workbench_sql_runtime.py`
  - 新增 `test_workbench_events_stream_close_releases_active_stream_slot`，锁定 Workbench SSE generator close cleanup。
  - 新增 `test_row_detail_production_sql_runtime_blocks_route_fallback_after_live_and_cache_miss`，锁定 production PostgreSQL runtime 下 row detail 不进入可能触发 full sync 的 route fallback。
- 文档变更：
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
  - `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`
- 不需要为 legacy `GET /api/workbench` 再改生产代码：PF-P008 现有 tests 已证明 production PostgreSQL runtime 下 SQL missing 返回 `202 refreshing`，repository unavailable 返回 `503 read_model_unavailable`，non-production / legacy runtime 才保留 legacy builder fallback。
- 未修改 `WorkbenchQueryFacade`，未移动 `request_database_timing`，未修改 SQL migration、前端、网关、部署、worker、builder、repository SQL、RabbitMQ、Outbox、Dirty Scope 或 Workbench 写路径。
- 未执行 Merge Gate，未执行 Traffic Gate，未部署服务器，未 push `origin/main`。

#### TDD 记录

- RED：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_workbench_events_stream_close_releases_active_stream_slot tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_row_detail_production_sql_runtime_blocks_route_fallback_after_live_and_cache_miss -v` 失败，原因分别为 SSE active stream registry 未记录、production SQL runtime 仍进入 route fallback。
- GREEN：同一 targeted command 通过。

#### 验证结果

- PF-P008 baseline pre-flight：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`：通过，105 tests passed。
  - Row detail targeted tests：通过，4 tests passed。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_api_performance_metrics tests.test_platform_runtime_boundary_guards -v`：通过，15 tests passed。
- PF-P009 implementation checks：
  - 新增 targeted tests：通过，2 tests passed。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`：通过，107 tests passed。
  - Row detail targeted tests：通过，4 tests passed。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_api_performance_metrics tests.test_platform_runtime_boundary_guards -v`：通过，15 tests passed。
- 最终 mandatory checks：
  - `git status --short --branch`：当前分支 `codex/workbench-query-slice-d-prompt...origin/main [ahead 1]`，存在本轮未提交工作区 diff。
  - `git ls-files --others --exclude-standard`：无输出。
  - `git diff --name-only` / `git diff --stat`：只包含允许范围内的生产代码、tests 和 backend-refactor 文档。
  - `git diff --check`：通过。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`：通过，107 tests passed。
  - Row detail targeted tests：通过，4 tests passed。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_api_performance_metrics tests.test_platform_runtime_boundary_guards -v`：通过，15 tests passed。
  - `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`：通过。
  - `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`：通过，status `ready`。
  - Allowed production diff check：通过；`backend/src/fin_ops_platform` 下除 `app/server.py` 外无其他生产文件 diff。
  - No forbidden surface diff：通过；`web`、`postgres`、`deploy` 无 diff。
  - Facade 上帝对象注入静态检查：无输出，通过。
  - Facade mock 静态检查：无输出，通过。
  - Observability 边界静态检查：通过；`request_database_timing` 未进入 `WorkbenchQueryFacade`。
  - SSE PubSub 静态检查：无输出，通过。

#### 仍未关闭风险

- Workbench SSE generator 现在对 `close()` / generator finalization 有可测试 cleanup，但当前 `ThreadingHTTPServer` streaming loop 仍无法在 `sleep(5)` 期间主动感知客户端断开；这属于 HTTP server abstraction limitation，后续如要强实时释放线程需要独立 infra/handler 设计。
- App Health SSE 不是 PF-P009 范围，仍保持原行为。
- Row detail 在 legacy / non-production runtime 下仍保留 route fallback；这是兼容期行为，不在本轮一次性删除。
- Observability 保持 app-shell route-level baseline；未新增 groups page/count/filter/search 子查询细粒度标签。

#### 下一条 Prompt 上下文

PF-P009 已由用户确认 `verified`。下一步应执行已生成并审查的 `PF-P009-MG - Workbench Query Fallback and SSE Mitigation Merge Gate`。PF-P009-MG 必须统一覆盖 PF-P008 测试锁定和 PF-P009 生产代码变更的完整 diff；不得执行 Traffic Gate、部署或默认 push。

### PF-P009-MG - Workbench Query Fallback and SSE Mitigation Merge Gate

状态：`verified`

#### 范围

- 只处理 PF-P008 + PF-P009 在当前功能分支上的完整 diff 合入 `main` 的 Merge Gate。
- 覆盖 PF-P008 的 fallback / SSE / observability characterization tests。
- 覆盖 PF-P009 的 Workbench SSE cleanup、production SQL runtime row detail fallback gate 和相关 tests/docs。
- 执行范围检查、untracked 检查、精准 staging、feature branch 验证、上游同步、commit、合入 `main` 和 main 上复验。

#### 禁止范围

- 不开始新的业务模块或 Slice E。
- 不修改 PF-P008/PF-P009 范围之外的生产代码。
- 不执行 Traffic Gate、部署或生产切流。
- 不默认 push `origin/main`；push 必须等用户明确确认。
- 不访问生产 DB、Redis、RabbitMQ、OA Mongo、OA MySQL、MinIO/S3。

#### 验收标准

- PF-P009-MG prompt 已写入 `refactor-prompts.md` 并完成审查。
- PF-P009-MG 必须确认 PF-P008 和 PF-P009 均为 `verified`。
- PF-P009-MG 必须列出完整 Expected Changed Files，包含 PF-P008 测试/文档、PF-P009 生产代码/测试/文档，以及同分支流程规则文档。
- PF-P009-MG 必须包含禁止 `git add .` / `git add -A`、untracked 文件检查、上游同步、feature branch 和 main 双重复验、Post-Flight 状态回写。
- 未经用户确认，不得把 PF-P009-MG 标记为 `verified`。

#### 执行结果

- Feature branch：`codex/workbench-query-slice-d-prompt`。
- 功能提交：`b58bd5a0 refactor(workbench): mitigate query fallback and sse stream cleanup`。
- Merge：`main` 已通过 fast-forward merge 合入 `codex/workbench-query-slice-d-prompt`，当前本地 `main` 到达 `b58bd5a0`。
- 变更范围：仅包含 Expected Changed Files：`backend/src/fin_ops_platform/app/server.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_api_performance_metrics.py`、`docs/architecture/backend-refactor/ai-execution-rules.md`、`docs/architecture/backend-refactor/migration-state-log.md`、`docs/architecture/backend-refactor/refactor-prompts.md`、`docs/architecture/backend-refactor/workbench-read-model-query-plan.md`。
- Feature branch 验证通过：
  - `git status --short --branch`
  - `git ls-files --others --exclude-standard`
  - `git diff --name-only`
  - `git diff --stat`
  - `git diff --check`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
  - Row detail targeted tests
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_api_performance_metrics tests.test_platform_runtime_boundary_guards -v`
  - `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`
  - `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
  - production diff、forbidden surface diff、Facade god object、Facade mock、observability boundary、SSE PubSub 静态检查。
- `main` 复验通过：
  - `git status --short --branch`
  - `git ls-files --others --exclude-standard`
  - `git diff --check`
  - `git diff --name-only origin/main..HEAD`
  - `git diff --stat origin/main..HEAD`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
  - Row detail targeted tests
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_api_performance_metrics tests.test_platform_runtime_boundary_guards -v`
  - `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services`
  - `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
  - production diff、forbidden surface diff、Facade god object、Facade mock、observability boundary、SSE PubSub 静态检查。
- 未执行 Traffic Gate、未部署服务器、未修改网关或生产配置、未 push `origin/main`。
- 剩余限制：`ThreadingHTTPServer` streaming loop 仍不能在 `sleep(5)` 期间主动感知客户端断开；本轮只保证 generator close/finalization cleanup 可测试。App Health SSE 不在 PF-P009 范围内，保持原行为。

#### 下一条 Prompt 上下文

PF-P009-MG 已由用户确认 `verified`。`git push origin main` 已通过，`origin/main` 从 `f01ba926` 更新到 `dfd42c16`。本次 push 只推送 Git 远端主干；未推送或重启服务器，未修改部署配置，未执行 Traffic Gate。已从最新 `main` 创建新分支 `codex/workbench-query-slice-e-prompt`，下一条 prompt 为 `PF-P010 - Workbench Query Repository and Active Generation Boundary (Slice E)`。

### PF-P010 - Workbench Query Repository and Active Generation Boundary (Slice E)

状态：`verified`

#### 范围

- 只处理 Workbench query/read-model 的 repository 与 active generation/source_version 读边界。
- 深挖 `PostgresReadModelRepository.get_workbench_summary(...)`、`get_workbench_groups_page(...)`、`get_workbench_group_detail(...)`、`get_workbench_refresh_status(...)`、`workbench_groups_cache_version(...)` 及其测试。
- 明确补入 row detail cached read model 的 active generation/source_version 一致性测试。
- 明确防范 repository 多 SQL 查询的 TOCTOU 风险：同一次方法调用内 page/count/row-count/detail 必须使用同一个固定 active generation id。
- 先补 characterization / guard tests，再做最小实现修正。
- 检查 groups page/count/filter/search 的 repository 慢查询与观测性粒度，但不得把 HTTP request context 的 `request_database_timing` 下沉到 facade/repository。

#### 禁止范围

- 不开始 Workbench 写路径、matching/candidates、candidate grouping、free matching engine 或 action handler 重构。
- 不修改 worker rebuild、builder、Outbox、Dirty Scope、RabbitMQ、Redis cache key 语义、前端、SQL migration、部署或网关配置。
- 不执行 Merge Gate、Traffic Gate、部署或 push。

#### 验收标准

- PF-P010 prompt 已写入 `refactor-prompts.md` 并完成审查。
- PF-P010 必须要求执行前使用 CodeGraph 或等价结构分析确认 repository 方法、caller 和测试覆盖。
- PF-P010 必须包含 TDD：先新增或调整 targeted failing tests，再做实现。
- PF-P010 执行完成后只能标记 `implemented` 或 `blocked`，未经用户确认不得标记 `verified`。

#### 执行结果

- 已使用 CodeGraph/结构分析确认 Slice E 的主要调用点：`PostgresReadModelRepository.get_workbench_summary(...)`、`get_workbench_groups_page(...)`、`get_workbench_group_detail(...)`、`get_workbench_refresh_status(...)`、`workbench_groups_cache_version(...)`，以及 row detail cached read model fallback 链路。
- 已按 TDD 先新增 targeted failing tests，再做最小实现；red 阶段覆盖 groups page/source_versions TOCTOU、summary source_versions pinning、group detail active generation、row detail stale cached read model。
- `PostgresReadModelRepository` 现在通过 generation id 精确读取 active generation 的 `source_versions`，避免同一方法内 active generation id 与 source_versions 分别读取造成混读。
- row detail cached read model fallback 增加 active/freshness gate：production SQL runtime 下会跳过 building/failed/stale/refreshing/unavailable 或 source_versions 不匹配的 cached read model，避免旧 generation 游离行被返回。
- 未修改 SQL migration、前端、部署、网关、Worker refresh、builder、Outbox、Dirty Scope、RabbitMQ、Redis cache key/TTL 或 Workbench 写路径。

#### 变更文件

- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_workbench_sql_runtime.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-read-model-query-plan.md`

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_platform_runtime_boundary_guards -v`：Pass。
- Row detail targeted tests：Pass。
- `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/services/postgres_repositories/read_models.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_query_facade.py`：Pass。
- 禁止面静态检查：Pass。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`：Pass。

#### 开放风险 / 待处理

- PF-P010 已通过 PF-P010-MG fast-forward 合入本地 `main`。
- 本轮只记录 groups page/count/filter/search 子查询级慢查询观测性 gap，未新增 repository 级性能指标。
- PF-P010 已由用户确认 `verified`；PF-P010-MG 已由用户确认 `verified`。

#### 下一条 Prompt 上下文

PF-P010 已由用户确认 `verified`。PF-P010-MG 已由用户确认 `verified`，并已 push 到 `origin/main`。未执行 Traffic Gate 或部署。

### PF-P010-MG - Workbench Query Repository and Active Generation Merge Gate

状态：`verified`

#### 范围

- 只处理 PF-P010 已 verified 变更进入 `main` 的 Merge Gate。
- 覆盖 Slice E 的 repository active generation/source_versions 修正、row detail cached read model freshness gate、targeted tests 和三份 backend-refactor 文档回写。
- 执行范围检查、untracked 检查、精准 staging、feature branch 验证、上游同步、commit、合入 `main` 和 main 上复验。

#### 禁止范围

- 不开始 Workbench 写路径、matching/candidates、worker rebuild、builder、Outbox、Dirty Scope、Redis/RabbitMQ、前端、SQL migration、网关或部署变更。
- 不执行 Traffic Gate、部署、生产切流或访问生产外部服务。
- 不默认 push `origin/main`；push 必须等用户明确确认。
- 不开始下一条业务 slice 或其它模块迁移。

#### 验收标准

- PF-P010-MG prompt 已写入 `refactor-prompts.md` 并完成审查。
- PF-P010-MG 必须确认 PF-P010 为 `verified`。
- PF-P010-MG 必须列出完整 Expected Changed Files。
- PF-P010-MG 必须包含禁止 `git add .` / `git add -A`、untracked 文件检查、上游同步、feature branch 和 main 双重复验、Post-Flight 状态回写。
- 未经用户确认，不得把 PF-P010-MG 标记为 `verified`。

#### 执行结果

- Feature branch：`codex/workbench-query-slice-e-prompt`。
- 功能提交：`3edaf335 refactor(workbench): pin query read models to active generation`。
- Merge：本地 `main` 已通过 fast-forward merge 合入 feature branch，当前包含 Slice E 变更和 PF-P010-MG planned 文档。
- 变更范围：只包含 Expected Changed Files：`backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`、`backend/src/fin_ops_platform/app/server.py`、`tests/test_workbench_sql_runtime.py`、`docs/architecture/backend-refactor/migration-state-log.md`、`docs/architecture/backend-refactor/refactor-prompts.md`、`docs/architecture/backend-refactor/workbench-read-model-query-plan.md`。
- Feature branch 验证通过：
  - `git status --short --branch`
  - `git ls-files --others --exclude-standard`
  - `git diff --name-only`
  - `git diff --stat`
  - `git diff --check`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_platform_runtime_boundary_guards -v`
  - Row detail targeted tests
  - `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/services/postgres_repositories/read_models.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_query_facade.py`
  - `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
  - production diff / forbidden surface / Facade mock / SSE PubSub 静态检查。
- `main` 复验通过：
  - `git status --short --branch`
  - `git ls-files --others --exclude-standard`
  - `git diff --check`
  - `git diff --name-only origin/main..HEAD`
  - `git diff --stat origin/main..HEAD`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_platform_runtime_boundary_guards -v`
  - Row detail targeted tests
  - `PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/services/postgres_repositories/read_models.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_query_facade.py`
  - `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
  - production diff / forbidden surface / Facade mock / SSE PubSub 静态检查。
- 未执行 Traffic Gate、未部署服务器、未修改网关或生产配置。
- 用户已确认 PF-P010-MG 为 `verified`，并已执行 `git push origin main`。

#### 下一条 Prompt 上下文

PF-P010-MG 已由用户确认 `verified`，并已同步到 `origin/main`。下一条 prompt 必须从最新 `main` 新建分支生成；不得在 `main` 上直接开始新业务 slice。

### PF-P011 - Workbench Matching Engine / Writes Discovery and Planning

状态：`verified`

#### 范围

- 只做 Workbench 写路径、pair-relations/actions、exceptions、matching/candidates、dirty scope、worker matching refresh 的 discovery/planning。
- 必须使用 CodeGraph 或等价结构分析梳理静态调用链和动态运行时序。
- 必须读取 Workbench 写路径 handler、service、repository、worker、runtime queue 和现有测试。
- 必须产出 `docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`，作为后续 Workbench 写路径/匹配引擎 Micro-JIT 的事实源。

#### 禁止范围

- 不修改 Python 业务代码。
- 不修改 tests。
- 不修改 SQL migration。
- 不修改前端、网关、部署、生产配置或外部服务配置。
- 不执行 Merge Gate、Traffic Gate、部署、push 或生产访问。
- 不开始实现 Workbench 写路径、matching/candidates、exception、pair relation 或 worker 重构。

#### 验收标准

- PF-P011 prompt 已写入 `refactor-prompts.md` 并完成审查。
- PF-P011 必须明确执行前读取本文档、prompt 库、模块计划、inventory、platform runtime boundary 审计和 Workbench query 计划。
- PF-P011 必须输出 action/API matrix、API 幂等性审计、file ownership、call chain、Mermaid runtime sequence、transaction/outbox/dirty scope 边界审计、内存级后台触发源审计、external dependency 审计、测试缺口和下一条 slice 建议。
- PF-P011 执行完成后只能标记 `implemented` 或 `blocked`，未经用户确认不得标记 `verified`。

#### 下一条 Prompt 上下文

PF-P011 已执行并产出 `docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`。本轮使用 CodeGraph 和源码扫描覆盖 Workbench 写 API、pair-relations/actions、exceptions、matching/candidates、dirty scope、worker refresh、in-memory loop 和现有测试。核心结论：

- Workbench 写路径仍集中在 `server.py` App Shell；handler 之后由 pair relation / exception / override services 变更内存或 snapshot，再通过 state store / repository 持久化。
- `RuntimeQueueRepository.enqueue_read_model_refresh(...)` 本身具备 dirty scope + outbox 同事务和 source_version 递增能力，但 Workbench 写 API 当前没有显式 Unit of Work 覆盖 facts、audit/history、dirty scope、outbox。
- API 级幂等性不一致：exception application service 有 idempotency key；confirm/cancel/ignore/unignore HTTP 重复提交行为需要 characterization tests 锁定。
- Stale write / blind overwrite 行为未锁定：由于 read model 异步刷新，后续 PF-P012 必须 characterization 已被其他请求修改过的 row/pair/exception 再被写入时的当前冲突处理行为。
- Workbench matching/candidates 仍应作为 Workbench 内部子域推进，不应直接升格为独立顶层模块。
- 存在 HTTP 进程 dirty worker、standalone worker dirty loop、async pair relation persist、async read model persist、OA sync hot rebuild 等 in-memory trigger，需要在后续测试中锁定并发/重叠行为。

变更文件：

- `docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`

验证：

- `git status --short --branch`：通过，当前只显示 backend-refactor 文档改动和新增 `workbench-writes-and-matching-plan.md`。
- `git ls-files --others --exclude-standard`：通过，唯一 untracked 文件是 `docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`。
- `git diff --name-only`：通过，tracked diff 只包含 `migration-state-log.md` 和 `refactor-prompts.md`。
- `git diff --stat`：通过，tracked diff 只包含 backend-refactor 文档。
- `git diff --check`：通过。
- `rg -n "PF-P011|Workbench Matching Engine / Writes|workbench-writes-and-matching-plan" docs/architecture/backend-refactor`：通过。
- `test -f docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`：通过。
- 非文档变更检查：通过，未出现 `backend/src`、`tests`、`web`、`postgres`、`deploy` 变更。

下一条 prompt 建议：`PF-P012 - Workbench Write API Characterization Tests`。PF-P012 应先补写 API 幂等性、stale write / optimistic state assertion、持久化顺序/回滚、derived lifecycle/read model scheduling failure、in-memory dirty worker trigger 和 platform boundary guard 的 characterization tests，不得直接重构实现。

用户已确认 PF-P011 `verified`。该确认只代表 discovery/planning 文档和状态机回写通过，不代表 Workbench 写路径已重构或可合入 `main`。

### PF-P012 - Workbench Write API Characterization Tests

状态：`verified`

#### 范围

- 只新增或调整 Workbench 写路径 characterization tests，锁定当前行为。
- 覆盖 PF-P011 发现的最高风险缺口：duplicate-submit / retry、stale write / optimistic state assertion、持久化顺序/回滚、derived lifecycle/read model scheduling failure、in-memory dirty worker trigger、platform boundary guard。
- 允许更新 `migration-state-log.md`、`refactor-prompts.md` 和 `workbench-writes-and-matching-plan.md` 中由测试发现直接影响的事实。

#### 禁止范围

- 不修改 Python 业务实现。
- 不修改 SQL migration。
- 不修改前端、网关、部署、生产配置或外部服务配置。
- 不执行 Merge Gate、Traffic Gate、部署、push 或生产访问。
- 不开始 Workbench write facade、Unit of Work、matching engine 或 repository 重构。

#### 验收标准

- PF-P012 prompt 已写入 `refactor-prompts.md` 并完成审查。
- PF-P012 必须先读取 PF-P011 产物 `workbench-writes-and-matching-plan.md`。
- PF-P012 执行时只能写 characterization tests，测试必须描述当前真实行为，不允许把期望行为伪装成现状。
- PF-P012 执行完成后只能标记 `implemented` 或 `blocked`，未经用户确认不得标记 `verified`。

#### 执行结果

PF-P012 已执行完成。本轮只新增/调整 tests 与 backend-refactor 文档；未修改 `backend/src` 业务实现、SQL migration、前端、网关、部署或生产配置。

新增/修改测试：

- 新增 `tests/test_workbench_write_characterization.py`，独立承载 Workbench 写路径 characterization tests，避免继续膨胀 `tests/test_workbench_v2_api.py`。
- 更新 `tests/test_platform_runtime_boundary_guards.py`，新增 Workbench write/matching services 直接 import Redis/RabbitMQ/MongoOAAdapter/pymysql 的静态门禁。

锁定的当前真实行为：

- Duplicate submit：
  - `confirm-link` 显式同一 `case_id` 重复提交：两次均 `200`，同一 active relation 保留，但会重复记录 `confirm_link` history 并重复调度 persistence/read model。
  - `confirm-link` 不传 `case_id` 重复提交：两次均 `200`，自动生成 `CASE-AUTO-0001` 与 `CASE-AUTO-0002`，第二次替换 active relation。
  - `cancel-link` 重复提交：第一次 `200`，第二次 `404 workbench_pair_relation_not_found`。
  - `ignore-row` 重复提交：两次均 `200`，复用同一 ignored exception case；`unignore-row` 第二次为 `404 workbench_row_not_found`。
  - `mark-exception` legacy HTTP wrapper 重复提交：两次均 `200`，复用同一 exception case。
  - `exception/apply` 重复提交：第二次 `200` 且 `idempotent=True`，复用同一 case。
- Stale write / optimistic state assertion：
  - `confirm-after-ignore`：当前为 blind write，`confirm-link` 仍 `200` 创建 pair relation，ignored case 仍保持 `ignored`。
  - `ignore-after-confirm`：当前为 blind write，`ignore-row` 仍 `200` 创建 ignored case，原 active relation 仍保持 active。
  - `cancel-after-replaced`：cancel 只按当前 active row relation 执行，会取消替换后的 `CASE-NEW`。
  - `exception-after-relation`：当前有明确冲突保护，返回 `409 active_pair_relation_conflict`，active relation 保留。
- Persistence ordering / failure：
  - `_schedule_workbench_read_model_persist` 抛错时，异常会向外传播，且 pair relation fact 已经在内存服务中变更；这证明当前没有单一 UoW 覆盖 facts 与 read model scheduling。
- In-memory trigger：
  - HTTP process dirty worker 必须显式 opt-in，`interval_seconds <= 0` 不启动；启动后最小 interval 为 `60.0`，重复调用不会重复启动线程。
  - standalone matching dirty loop 在 `max_iterations=1` 时只执行一次并不会进入 sleep，避免测试 hang。
- Platform boundary：
  - Workbench write/matching services 当前没有直接 import Redis、RabbitMQ、MongoOAAdapter 或 pymysql。

验证：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：通过，13 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：通过，10 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v`：通过，147 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_exception_application_service -v`：通过，11 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_service tests.test_workbench_exception_case_service -v`：通过，12 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_orchestrator tests.test_workbench_candidate_match_service tests.test_workbench_reconciliation_dirty_queue -v`：通过，34 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_platform_runtime_boundary_guards -v`：通过，23 tests。

用户已确认 PF-P012 `verified`。该确认只代表 characterization tests、platform guard 和文档回写通过，不代表 Workbench 写路径已经完成重构或具备目标语义。

#### 下一条 Prompt 上下文

PF-P013 已生成并审查，下一步允许在用户确认后执行。PF-P013 必须保持 PF-P012 锁定的当前行为不变，只抽 thin facade/usecase 边界；不得在同一 prompt 中修复 stale write 或重写 Unit of Work。Stale write 与 UoW 修复应作为后续明确语义变更 prompt，基于 PF-P012 的 characterization tests 逐项调整。

### PF-P013 - Workbench Write Facade Extraction

状态：`verified`

#### 范围

- 在 `backend/src/fin_ops_platform/services/` 下建立 Workbench 写路径 thin facade / usecase 边界，例如 `workbench_write_facade.py`。
- 第一轮只允许抽取最小可验证切片：`confirm-link` 与 `cancel-link` 的 handler 编排边界，以及它们共享的 payload/result 转换辅助。
- `server.py` handler 继续负责 HTTP body 解析、request id、auth/freshness gate、HTTP response construction 和带 HTTP route context 的 timing/observability wrapper。
- Facade 只能通过细粒度依赖注入访问现有 services/repositories/schedulers，不得接收 `Application`、`RuntimeRepositories`、`ApplicationStateStore` 或 `self` 这类上帝对象。
- 必须保持 PF-P012 锁定的 duplicate-submit、stale write、scheduling failure、history/audit 和 dirty/read model scheduling 当前行为不变。

#### 禁止范围

- 不修复 stale write / optimistic locking / blind write 语义。
- 不引入 Workbench Unit of Work，不重写 transaction、repository、dirty scope、outbox 或 read model refresh 机制。
- 不迁移 `mark-exception`、`exception/apply`、`ignore-row`、`unignore-row`，除非只是为了保持 confirm/cancel 共享 helper 的最小 wiring 且不改变行为。
- 不修改 SQL migration、前端、网关、部署、生产配置或外部服务配置。
- 不执行 Merge Gate、Traffic Gate、部署、push 或生产访问。

#### 验收标准

- PF-P013 prompt 已写入 `refactor-prompts.md` 并完成审查。
- 执行时必须先跑或补充最小 characterization tests，证明 handler -> facade -> current service/repository/fake 链路仍被黑盒测试覆盖。
- 严禁在 `tests/test_workbench_write_characterization.py` 中 mock 掉整个 facade。
- 必须运行 PF-P012 已通过的 Workbench write/matching 相关 unittest 与 platform guard。
- 执行完成后只能标记 `implemented` 或 `blocked`；未经用户确认不得标记 `verified`。

#### 执行结果

PF-P013 已执行完成。本轮做了行为保持型 thin facade 抽取，只覆盖 `confirm-link` 与 `cancel-link`。

新增/修改代码：

- 新增 `backend/src/fin_ops_platform/services/workbench_write_facade.py`：
  - 新增 `WorkbenchWriteFacade`。
  - 新增 `WorkbenchWriteResult`。
  - 将 confirm/cancel 的非 HTTP 编排移入 facade，包括 payload validation、pair relation mutation、history/audit 触发、dirty/read model scheduling callback、confirm 持久化失败回滚 callback。
- 修改 `backend/src/fin_ops_platform/app/server.py`：
  - 新增 `_workbench_write_facade()`，只注入细粒度依赖和 callback。
  - 新增 `_workbench_write_response()`，保留 HTTP response construction 在 App Shell。
  - 新增 `_restore_workbench_pair_relation_snapshot()`，保留 pair relation service 替换和 legacy snapshot restore 行为。
  - `_handle_live_workbench_confirm_link()` 与 `_handle_live_workbench_cancel_link()` 改为委托 facade。
- 修改 `tests/test_platform_runtime_boundary_guards.py`：
  - 将 `workbench_write_facade.py` 纳入 Workbench write/matching external client import guard。
  - 新增 constructor signature guard，禁止 `Application`、`RuntimeRepositories`、`ApplicationStateStore`、`state_store` 等上帝对象注入。

保持不变的范围：

- 未迁移 `mark-exception`、`exception/apply`、`ignore-row`、`unignore-row`。
- 未修复 stale write / optimistic locking / blind write。
- 未引入 Workbench Unit of Work。
- 未重写 repository、transaction manager、dirty scope、outbox、read model refresh 或 worker。
- 未修改 SQL migration、前端、网关、部署或生产配置。
- 未执行 Merge Gate、Traffic Gate、deploy、push 或生产访问。

验证：

- TDD red：新增 facade 门禁后，`test_workbench_write_and_matching_services_do_not_import_external_clients_directly` 失败，原因是 `workbench_write_facade.py is missing`；`test_workbench_write_facade_uses_granular_constructor_dependencies` 因模块不存在报错。
- TDD green：实现 facade 后，上述两个 targeted tests 通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：通过，13 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v`：通过，147 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_exception_application_service -v`：通过，11 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_service tests.test_workbench_exception_case_service -v`：通过，12 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_orchestrator tests.test_workbench_candidate_match_service tests.test_workbench_reconciliation_dirty_queue -v`：通过，34 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_platform_runtime_boundary_guards -v`：通过，24 tests。
- `python3 -m compileall -q backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py`：通过。

#### 下一条 Prompt 上下文

用户已确认 PF-P013 `verified`。该确认只代表 confirm/cancel thin facade 抽取、行为保持测试、platform guard 和文档回写通过，不代表 Workbench 写路径全部完成重构，也不代表 stale write / Unit of Work 已修复。

#### 下一条 Prompt 上下文

PF-P013-MG 已生成并审查。下一步允许在用户确认后执行 PF-P013-MG。PF-P013-MG 必须覆盖 PF-P012 + PF-P013 尚未合入 `main` 的完整 diff；不得执行 Traffic Gate，不得部署，不得修改生产配置，不得混入 PF-P014 或任何新功能。

### PF-P013-MG - Workbench Write Facade Merge Gate

状态：`verified`

#### 范围

- 只处理 PF-P012 + PF-P013 的完整 Merge Gate。
- 确认 PF-P012 与 PF-P013 均已由用户确认 `verified`。
- 检查当前分支 diff 是否只包含：
  - Workbench write characterization tests。
  - Workbench write facade 与 `server.py` confirm/cancel 最小 wiring。
  - platform runtime guard 中与 Workbench write facade 相关的静态门禁。
  - backend-refactor 文档和状态机回写。
- 执行 merge 前必须做 upstream sync：确认当前分支包含最新 `main`；如同步了 main，必须重新运行 MG 验证。
- 允许在验证通过后 commit、合并到 `main`，并在 `main` 上复跑指定验证。

#### 禁止范围

- 不新增或修改业务功能。
- 不执行 PF-P014。
- 不迁移 `mark-exception`、`exception/apply`、`ignore-row`、`unignore-row`。
- 不修复 stale write / optimistic locking / blind write。
- 不引入 Workbench Unit of Work。
- 不修改 SQL migration、前端、网关、部署或生产配置。
- 不执行 Traffic Gate、deploy 或生产访问。
- 不使用 `git add .` 或 `git add -A`；必须精准 add 文件。

#### 验收标准

- PF-P013-MG prompt 已写入 `refactor-prompts.md` 并完成审查。
- 执行时必须运行 PF-P012 + PF-P013 指定测试和静态检查。
- 必须检查 `git ls-files --others --exclude-standard`，防止临时文件混入。
- 如果当前已经在 `main`，不得做无意义 merge；只执行范围检查、必要验证、commit 或状态机更新。
- 未经用户确认，不得把 PF-P013-MG 标记为 `verified`。

#### 下一条 Prompt 上下文

PF-P013-MG 已执行并合入本地 `main`。本轮覆盖 PF-P012 + PF-P013 的完整 diff：Workbench 写操作特征测试、confirm/cancel write facade、`server.py` 最小 wiring、platform guard 更新、文档和状态机更新。

执行记录：

- 功能分支：`codex/workbench-writes-matching-discovery`。
- 功能提交：`a50b1525` (`refactor(workbench): extract confirm cancel write facade`)。
- 本地 main merge commit：`ab74c28a` (`Merge branch 'codex/workbench-writes-matching-discovery': workbench write facade`)。
- upstream sync：`origin/main` 已 fast-forward 检查，合并前 `main` 已是最新；功能分支合并 `main` 时 `Already up to date`。
- push：未执行。当前本地 `main` ahead `origin/main`，等待用户单独确认。
- Traffic Gate / deploy / 生产配置：未执行、未修改。

验证结果：

- `git status --short --branch`：本地 `main` ahead `origin/main`，无工作区改动。
- `git ls-files --others --exclude-standard`：无输出。
- `git diff --check`：通过。
- `python3 -m compileall -q backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：13 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v`：147 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_platform_runtime_boundary_guards -v`：24 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_exception_application_service -v`：11 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_service tests.test_workbench_exception_case_service -v`：12 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_orchestrator tests.test_workbench_candidate_match_service tests.test_workbench_reconciliation_dirty_queue -v`：34 tests OK。

PF-P013-MG 已由用户确认 `verified`。下一步执行 `git push origin main`；push 后必须从最新 `main` 新建分支，再生成并审查 `PF-P014 - Workbench Exception Facade Extraction`。

#### Push 记录

- 已执行 `git push origin main`。
- 远端 `origin/main` 已从 `b897a3b6` 更新到 `f37c32ca`。
- push 后从最新 `main` 新建分支：`codex/workbench-exception-facade-prompt`。

### PF-P014 - Workbench Exception Facade Extraction

状态：`verified`

#### 范围

- 只做 Workbench exception/ignore 写路径的 facade extraction。
- 目标入口：
  - `POST /api/workbench/actions/mark-exception`
  - `POST /api/workbench/exception/apply`
  - `POST /api/workbench/actions/cancel-exception`
  - `POST /api/workbench/actions/ignore-row`
  - `POST /api/workbench/actions/unignore-row`
- 保留 `server.py` 的 HTTP body 解析、freshness guard、request id、HTTP response wrapper 和 route dispatch。
- 将上述入口的非 HTTP 编排逻辑迁入 facade 边界，继续使用细粒度依赖注入。
- 延续 PF-P012 锁定的 duplicate submit、stale write、blind write、read model scheduling failure 等当前行为，不改变 API 语义。

#### 禁止范围

- 不引入 Workbench Unit of Work。
- 不修复 stale write / optimistic locking / blind write。
- 不改变事务模型、dirty scope / outbox 语义或 read model scheduling 顺序。
- 不迁移 `update-bank-exception`、`oa-bank-exception`、cash special、personal advance repayment、withdraw-link 等其它写入口。
- 不修改 SQL migration、前端、网关、部署或生产配置。
- 不执行 Merge Gate、Traffic Gate、deploy、push 或生产访问。

#### 验收标准

- PF-P014 prompt 已写入 `refactor-prompts.md` 并完成审查。
- 执行 PF-P014 时必须先读取状态机、prompt 库和 `workbench-writes-and-matching-plan.md`。
- 执行 PF-P014 时必须保持 `server.py` handler 为薄入口，不允许在 facade 中注入 `Application`、`RuntimeRepositories`、`ApplicationStateStore`、`state_store` 等上帝对象。
- 执行 PF-P014 后必须运行 Workbench write characterization、Workbench v2 API、exception service、exception case、platform runtime boundary guards 等指定测试。
- 未经用户确认，不得把 PF-P014 标记为 `verified`。

#### 下一条 Prompt 上下文

PF-P014 已执行。已迁移到 `WorkbenchWriteFacade` 的入口：

- `POST /api/workbench/actions/mark-exception`
- `POST /api/workbench/exception/apply`
- `POST /api/workbench/actions/cancel-exception`
- `POST /api/workbench/actions/ignore-row`
- `POST /api/workbench/actions/unignore-row`

本轮保持当前语义：未引入 Workbench Unit of Work，未修复 stale write / optimistic locking / blind write，未改变 dirty scope、read model scheduling 或 derived lifecycle 顺序。

仍未迁移的 Workbench 写入口：

- `update-bank-exception`
- `oa-bank-exception`
- cash special APIs
- personal advance repayment APIs
- withdraw-link APIs
- matching run / dirty worker APIs

验证结果：

- RED：新增 `test_workbench_write_facade_exposes_exception_write_entrypoints` 后先失败，缺少 `apply_exception`、`mark_exception`、`cancel_exception`、`ignore_row`、`unignore_row`。
- GREEN：实现 facade entrypoints 后该 guard 通过。
- `python3 -m compileall -q backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：13 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v`：147 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_exception_application_service -v`：11 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_exception_case_service -v`：8 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_service -v`：4 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_platform_runtime_boundary_guards -v`：25 tests OK。
- `git diff --check`：通过。
- `git ls-files --others --exclude-standard`：无输出。

用户已确认 PF-P014 `verified`。PF-P014 的确认只代表 exception/ignore facade extraction、行为保持测试、platform guard 和文档回写通过，不代表 Workbench 写路径已经具备目标 Unit of Work，也不代表 stale write / optimistic locking 已修复。

下一步允许执行 `PF-P014-MG - Workbench Exception Facade Merge Gate`。PF-P014-MG 必须覆盖 PF-P014 的完整 diff；不得执行 Traffic Gate，不得部署，不得修改生产配置，不得混入 PF-P015、Unit of Work、stale write 修复或任何新业务功能。

### PF-P014-MG - Workbench Exception Facade Merge Gate

状态：`verified`

#### 范围

- 只处理 PF-P014 的完整 Merge Gate。
- 确认 PF-P014 已由用户确认 `verified`。
- 检查当前分支 diff 是否只包含：
  - Workbench exception/ignore facade extraction。
  - `server.py` 中对应 handler 的最小 wiring。
  - platform runtime guard 中与 Workbench write facade exception entrypoints 相关的静态门禁。
  - backend-refactor 文档和状态机回写。
- 执行 merge 前必须做 upstream sync：确认当前分支包含最新 `main`；如同步了 main，必须重新运行 MG 验证。
- 允许在验证通过后 commit、合并到 `main`，并在 `main` 上复跑指定验证。

#### 禁止范围

- 不新增或修改业务功能。
- 不执行 PF-P015。
- 不引入 Workbench Unit of Work。
- 不修复 stale write / optimistic locking / blind write。
- 不改变事务模型、dirty scope / outbox、derived lifecycle 或 read model scheduling 顺序。
- 不迁移 `update-bank-exception`、`oa-bank-exception`、cash special、personal advance repayment、withdraw-link、matching run / dirty worker 等其它入口。
- 不修改 SQL migration、前端、网关、部署或生产配置。
- 不执行 Traffic Gate、deploy 或生产访问。
- 不使用 `git add .` 或 `git add -A`；必须精准 add 文件。

#### 验收标准

- PF-P014-MG prompt 已写入 `refactor-prompts.md` 并完成审查。
- 执行时必须运行 PF-P014 指定测试和静态检查。
- 必须检查 `git ls-files --others --exclude-standard`，防止临时文件混入。
- 如果当前已经在 `main`，不得做无意义 merge；只执行范围检查、必要验证、commit 或状态机更新。
- 未经用户确认，不得把 PF-P014-MG 标记为 `verified`。

#### 下一条 Prompt 上下文

PF-P014-MG 已执行并合入本地 `main`。本轮覆盖 PF-P014 的完整 diff：Workbench exception/ignore facade extraction、`server.py` 对应 handler 最小 wiring、platform guard 更新、文档和状态机更新。

执行记录：

- 功能分支：`codex/workbench-exception-facade-prompt`。
- 功能提交：`4031a1d5` (`refactor(workbench): extract exception write facade`)。
- 本地 main merge commit：`6fb77dc3` (`Merge branch 'codex/workbench-exception-facade-prompt': workbench exception facade`)。
- upstream sync：`origin/main` 与本地 `main` 均为 `f37c32ca`，且 `origin/main` 是功能分支祖先；合并前 `git pull --ff-only origin main` 显示 `Already up to date`。
- push：已执行，`main` 与 `origin/main` 已同步；不在状态机中硬编码最终 push 记录提交 hash，避免状态记录追逐自身更新提交。
- Traffic Gate / deploy / 生产配置：未执行、未修改。

功能分支验证结果：

- `git ls-files --others --exclude-standard`：无输出。
- diff scope gate：通过，只包含 PF-P014 允许文件。
- forbidden surface check：通过，未触碰 `web/`、`postgres/`、`deploy/`、`backend-go/`、`runtime_redis.py`、`rabbitmq_runtime.py`。
- `git diff --check`：通过。
- `python3 -m compileall -q backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：13 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v`：147 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_exception_application_service -v`：11 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_exception_case_service -v`：8 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_service -v`：4 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_platform_runtime_boundary_guards -v`：25 tests OK。

main 复验结果：

- `git status --short --branch`：`main...origin/main [ahead 3]`，无工作区改动。
- `git ls-files --others --exclude-standard`：无输出。
- `git diff --check`：通过。
- `python3 -m compileall -q backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：13 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v`：147 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_exception_application_service -v`：11 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_exception_case_service -v`：8 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_service -v`：4 tests OK。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_platform_runtime_boundary_guards -v`：25 tests OK。

用户已确认 PF-P014-MG `verified`，且已执行 `git push origin main`。`main` 与 `origin/main` 已同步。下一步必须从最新 `main` 新建分支，再生成并审查 `PF-P015 - Workbench Remaining Write Facade Discovery and Planning`；不得直接在当前 `main` 上进入 PF-P015 / Unit of Work。

### PF-P015 - Workbench Remaining Write Facade Discovery and Planning

状态：`verified`

#### 范围

- 只做 Workbench 剩余写入口的 discovery / planning 和文档回写。
- 必须盘点 PF-P014 后仍未迁移的写入口：
  - `withdraw-link` / `withdraw-link-preview`
  - cash special：`confirm-cash-pass-through`、`confirm-cash-ticket-purchase`、`cancel-cash-special`
  - `update-bank-exception`
  - `oa-bank-exception`
  - `confirm-personal-advance-repayment`
  - matching run / matching dirty worker / standalone worker dirty loop
- 必须输出每个入口的 handler、service、facts、audit/history、dirty scope、outbox/read model scheduling、当前测试覆盖和风险。
- 必须包含 `UoW Readiness Assessment`：评估未来 Unit of Work 需要包住哪些 facts、audit、dirty scope、outbox、read model scheduling，以及当前 blocker。

#### 禁止范围

- 不修改 Python 业务代码。
- 不抽 facade。
- 不新增或修改 tests。
- 不设计具体 UoW API。
- 不实现 UoW、repository、transaction manager、outbox 或 dirty scope 变更。
- 不修复 stale write / optimistic locking / blind write。
- 不修改 SQL migration、前端、网关、部署或生产配置。
- 不执行 Merge Gate、Traffic Gate、deploy、push 或生产访问。

#### 验收标准

- PF-P015 prompt 已写入 `refactor-prompts.md` 并完成审查。
- PF-P015 prompt 明确要求使用 CodeGraph 或等价结构分析覆盖剩余写入口。
- PF-P015 prompt 明确产物为 `docs/architecture/backend-refactor/workbench-remaining-write-facade-plan.md`，并允许同步更新 `workbench-writes-and-matching-plan.md`。
- PF-P015 prompt 明确执行后只能到 `implemented` 或 `blocked`；未经用户确认不得标记 `verified`。

#### 下一条 Prompt 上下文

PF-P015 已执行并产出 `docs/architecture/backend-refactor/workbench-remaining-write-facade-plan.md`。本轮只修改文档，未修改 Python 业务代码、测试、SQL migration、前端、部署或生产配置；未执行 Merge Gate、Traffic Gate、push 或生产访问。

主要发现：

- `withdraw-link` 适合后续移动到 `WorkbenchWriteFacade`，但应先补 duplicate submit、stale preview submit 和 scheduling failure characterization tests。
- cash special 三个入口缺少 targeted black-box tests，必须先补测试，不能直接抽 facade。
- `update-bank-exception` 和 `confirm-personal-advance-repayment` 都是 UoW 热点，当前测试不足，不能直接进入 UoW 或抽取。
- `oa-bank-exception` 已有较多行解析和 read model invalidation 测试，但仍缺 duplicate-submit 和 failure propagation tests。
- `/matching/run` 是 legacy `MatchingService`，不应进入 Workbench write facade。
- matching dirty worker 属于 worker/runtime boundary，不是 HTTP write facade 候选。

UoW readiness：

- 未来 UoW 必须覆盖 pair relation facts/history、exception cases/history、overrides、candidate consumption、dirty scope/outbox 和 read model source versions。
- 当前 blocker 是 in-memory service 先变更、Application snapshot/persist callbacks 后置、derived lifecycle/read model scheduling 与 facts commit 分离、async thread 配置和测试缺口。

用户已确认 PF-P015 `verified`。下一条 prompt 已生成并审查：`PF-P016 - Workbench Remaining Write Characterization Tests`。PF-P016 应先锁定剩余入口 duplicate-submit、stale/conflict、persistence failure、dirty/read model scheduling failure 当前行为；仍不得修复 stale write、抽 facade 或实现 UoW。

### PF-P016 - Workbench Remaining Write Characterization Tests

状态：`verified`

#### 范围

- 只新增或调整 Workbench 剩余写入口的 characterization tests 和必要文档回写。
- 必须覆盖 PF-P015 发现的高风险缺口：
  - `withdraw-link` preview stale submit、duplicate submit、scheduling failure。
  - cash special 三个入口：success、duplicate submit、stale/conflict、scheduling failure。
  - `update-bank-exception`：duplicate submit、stale/conflict、failure propagation。
  - `oa-bank-exception`：duplicate submit、failure propagation。
  - `confirm-personal-advance-repayment`：duplicate submit、stale/conflict、persistence / scheduling failure。
  - matching dirty worker mixed runtime boundary 的必要补充测试，如当前测试已经足够，必须在文档中说明理由。

#### 禁止范围

- 不修改生产业务代码。
- 不抽 facade。
- 不设计或实现 UoW。
- 不修复 stale write、duplicate submit、blind write、rollback 或调度失败语义。
- 不修改 SQL migration、前端、网关、部署或生产配置。
- 不执行 Merge Gate、Traffic Gate、deploy、push 或生产访问。

#### 验收标准

- PF-P016 prompt 已写入 `refactor-prompts.md` 并完成审查。
- PF-P016 prompt 明确只允许 tests 和文档变更。
- PF-P016 prompt 明确测试必须锁定当前行为，而不是改成理想行为。
- PF-P016 prompt 明确执行后只能到 `implemented` 或 `blocked`；未经用户确认不得标记 `verified`。

#### 变更文件

- `tests/test_workbench_write_characterization.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-remaining-write-facade-plan.md`
- `docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`

#### 执行结果

- 新增 Workbench 剩余写入口 characterization tests，覆盖 `withdraw-link`、cash special 三个入口、`update-bank-exception`、`oa-bank-exception`、`confirm-personal-advance-repayment` 的 duplicate-submit、stale/conflict、persistence 或 scheduling failure 当前行为。
- 未修改 `backend/src/fin_ops_platform/**/*.py` 生产代码。
- matching dirty worker 本轮未新增测试；PF-P012/PF-P015 已覆盖 HTTP worker opt-in、standalone loop max iteration、DB dirty queue claim/complete/fail、failure retry 和 startup wiring。本轮新增内容集中在剩余 HTTP write API 行为锁定。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：通过，29 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_dirty_queue_wiring -v`：通过，17 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_oa_bank_exception_accepts_invoice_rows_for_legacy_compatibility -v`：通过，1 test。
- 仍需在收尾前运行 `git diff --check` 和 untracked 检查。

#### 残余风险

- PF-P016 只锁定当前行为，不修复 stale write、duplicate submit、副作用重复调度、facts 与 dirty/outbox 非同事务问题。
- `tests/test_workbench_v2_api.py` 未被修改；已有 invoice compatibility 测试 `test_oa_bank_exception_accepts_invoice_rows_for_legacy_compatibility` 继续作为该兼容行为的事实源。

#### 下一条 Prompt 上下文

用户已确认 PF-P016 `verified`。PF-P017 已生成并审查，下一步允许执行 PF-P017。PF-P017 应继续以行为保持方式抽离 `withdraw-link`、cash special、bank exception、OA-bank exception、personal advance repayment；不得在 PF-P017 中引入 UoW、修复 stale write 或改变事务/调度语义。

### PF-P017 - Workbench Remaining Write Facade Extraction

状态：`verified`

#### 范围

- 只做行为保持型 facade extraction。
- 将以下剩余 Workbench 写入口的非 HTTP 编排从 `Application` / `server.py` 迁入 `WorkbenchWriteFacade`：
  - `withdraw-link/preview`
  - `withdraw-link`
  - `confirm-cash-pass-through`
  - `confirm-cash-ticket-purchase`
  - `cancel-cash-special`
  - `update-bank-exception`
  - `oa-bank-exception`，包含 invoice compatibility path
  - `confirm-personal-advance-repayment`
- 保留 `server.py` 的 HTTP body parsing、freshness guard、request_id、route timing wrapper 和 response wrapping。
- 继续使用细粒度依赖注入，禁止向 facade 注入 `Application`、`RuntimeRepositories`、`ApplicationStateStore`、`state_store` 或外部客户端。

#### 禁止范围

- 不实现或设计 Unit of Work。
- 不修复 stale write、duplicate submit、blind write、rollback 或 scheduling failure 当前语义。
- 不修改 SQL migration、前端、网关、部署、CI/CD 或生产配置。
- 不迁移 `/matching/run`、matching dirty worker、runtime worker loop 或 worker topology。
- 不访问生产环境，不执行 Merge Gate、Traffic Gate、push 或 deploy。

#### 验收标准

- PF-P017 prompt 已写入 `refactor-prompts.md` 并完成审查。
- PF-P017 prompt 明确要求先跑 PF-P016/PF-P012 行为锁定测试，再做抽离。
- PF-P017 prompt 明确禁止在 characterization tests 中 mock 掉 facade。
- PF-P017 prompt 明确执行后只能到 `implemented` 或 `blocked`；未经用户确认不得标记 `verified`。

#### 下一条 Prompt 上下文

用户已确认 PF-P017 `verified`。PF-P017-MG 已生成并审查，下一步允许执行 PF-P017-MG。PF-P017-MG 必须统一覆盖 PF-P015/PF-P016/PF-P017 的完整 diff；不得在 PF-P017-MG 前进入 UoW、stale write 修复或其它语义改造。

#### 变更文件

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-remaining-write-facade-plan.md`
- `docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`

#### 执行结果

- `server.py` 的目标 HTTP handlers 已薄化为 body parsing、freshness guard、request_id 透传、facade 调用和 response wrapping。
- `WorkbenchWriteFacade` 新增并承接：
  - `preview_withdraw_link`
  - `withdraw_link`
  - `confirm_cash_pass_through`
  - `confirm_cash_ticket_purchase`
  - `cancel_cash_special`
  - `update_bank_exception`
  - `oa_bank_exception`
  - `confirm_personal_advance_repayment`
- 保留 legacy private wrapper 兼容已有 tests 对 `_handle_live_workbench_oa_bank_exception` 等方法的直接调用，但 wrapper 只委托 facade。
- 未修改 SQL migration、前端、网关、部署、CI/CD 或生产配置。
- 未引入 UoW，未修复 stale write、duplicate submit、rollback 或 scheduling failure 当前语义。

#### 验证

- 抽离前基线：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：通过，29 tests。
- 抽离后：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：通过，29 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_dirty_queue_wiring -v`：通过，17 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_oa_bank_exception_accepts_invoice_rows_for_legacy_compatibility -v`：通过，1 test。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_personal_advance_repayment_creates_settled_case_and_pair_relation -v`：通过，1 test。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_and_cancel_link_defer_read_model_persistence_to_background -v`：通过，1 test。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_oa_bank_exception_invalidates_only_changed_scopes_and_rebuilds_in_background -v`：通过，1 test。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：通过，12 tests。
- `python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_write_facade.py`：通过。
- `git diff --check`：通过。
- `git ls-files --others --exclude-standard`：无输出。

#### 残余风险

- PF-P017 只完成行为保持型 facade extraction，不代表 Workbench 写路径已经获得目标一致性语义。
- duplicate submit、stale write、facts 与 dirty/outbox 非同事务、scheduling failure after mutation 等风险仍按 PF-P016 characterization 保持原样。
- `/matching/run`、matching dirty worker 和 worker topology 未进入本轮 facade 边界。

### PF-P017-MG - Workbench Remaining Write Facade Merge Gate

状态：`verified`

#### 范围

- 只处理 PF-P015/PF-P016/PF-P017 的 Merge Gate。
- 统一覆盖当前分支相对 `main` 的完整 diff：
  - `backend/src/fin_ops_platform/app/server.py`
  - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
  - `tests/test_workbench_write_characterization.py`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
  - `docs/architecture/backend-refactor/workbench-remaining-write-facade-plan.md`
  - `docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`
- 负责范围检查、untracked 检查、完整验证、精准提交/合并准备、合并到 main、main 上复验和状态机回写。

#### 禁止范围

- 不开始 UoW、transaction manager、outbox/dirty scope 语义改造。
- 不修复 stale write、duplicate submit、optimistic locking、rollback 或 scheduling failure 当前语义。
- 不执行 Traffic Gate、部署、生产访问、生产配置修改或服务器推送。
- 不修改 SQL migration、前端、网关、CI/CD 或 worker topology。
- 不使用 `git add .` 或 `git add -A`。

#### 验收标准

- PF-P017-MG prompt 已写入 `refactor-prompts.md` 并完成审查。
- PF-P017-MG prompt 明确 PF-P015/PF-P016/PF-P017 均已 verified。
- PF-P017-MG prompt 明确 allowed diff scope 覆盖当前实际完整 diff。
- PF-P017-MG prompt 明确执行完成后只能到 `implemented` 或 `blocked`；未经用户确认不得标记 `verified`。

#### 执行结果

- 功能分支：`codex/workbench-remaining-write-facade-planning`
- 功能分支合入前 HEAD：`291d5805`
- 本地 `main` merge commit：`355bb8af`
- 合入范围：PF-P015/PF-P016/PF-P017 的完整 diff，包括 Workbench remaining write facade、对应 characterization tests、remaining write planning 文档与状态机/prompt 记录。
- Diff scope 检查：只包含 PF-P017-MG allowed files；未发现前端、SQL migration、网关、CI/CD、worker topology、生产配置或 `backend-go` 变更。
- Untracked 检查：`git ls-files --others --exclude-standard` 无输出；未使用 `git add .` 或 `git add -A`。
- Push：已推送 `origin/main`，远端 `main` 最终更新到 `06c6fd43`。
- Traffic Gate：未执行；未部署、未切流、未访问生产服务器。
- User confirmation：2026-05-30 用户确认 `PF-P017-MG verified`。

#### Main 复验

- `python3 -m compileall -q backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py`：Pass
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，29 tests
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_dirty_queue_wiring -v`：Pass，17 tests
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_oa_bank_exception_accepts_invoice_rows_for_legacy_compatibility -v`：Pass
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_personal_advance_repayment_creates_settled_case_and_pair_relation -v`：Pass
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_and_cancel_link_defer_read_model_persistence_to_background -v`：Pass
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_oa_bank_exception_invalidates_only_changed_scopes_and_rebuilds_in_background -v`：Pass
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_exception_application_service -v`：Pass，11 tests
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_exception_case_service -v`：Pass，8 tests
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_service -v`：Pass，4 tests
- `PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_platform_runtime_boundary_guards -v`：Pass，25 tests

#### 下一条 Prompt 上下文

PF-P017-MG 已 verified 并推送 `origin/main`。已从最新 `main` 新建分支 `codex/workbench-uow-boundary-design`，并生成/审查 PF-P018。下一步允许执行 PF-P018。PF-P018 只做 UoW 边界设计与测试策略，不直接改事务语义或修复 stale write。

### PF-P018 - Workbench Write Unit of Work Boundary Design

状态：`verified`

#### 范围

- 只做 Workbench 写路径 Unit of Work 边界设计。
- 产出 `docs/architecture/backend-refactor/workbench-write-uow-boundary-design.md`。
- 基于 PF-P012/PF-P016 的 characterization 结果和 PF-P013/PF-P014/PF-P017 的 facade extraction 结果，梳理未来 UoW 必须包住的 facts、audit/history、dirty scope、outbox/read model scheduling、source_version、idempotency/stale write precondition。
- 输出后续测试 prompt 的拆分建议和验收门槛。

#### 禁止范围

- 不实现 UoW、transaction manager、repository rewrite、outbox writer、dirty scope writer 或 source_version 更新逻辑。
- 不修改 Workbench 生产代码、测试代码、SQL migration、前端、网关、部署、CI/CD 或生产配置。
- 不修复 stale write、duplicate submit、blind write、rollback 或 scheduling failure 当前语义。
- 不执行 Merge Gate、Traffic Gate、push、deploy 或生产访问。

#### 验收标准

- PF-P018 prompt 已写入 `refactor-prompts.md` 并完成审查。
- PF-P018 明确它是设计/文档 prompt，不是实现 prompt。
- PF-P018 明确必须读取 `WorkbenchWriteFacade`、`server.py`、derived lifecycle、runtime queue、Postgres repository 基础设施和 characterization tests。
- PF-P018 明确必须输出逐 API 的 UoW boundary matrix、transaction sequence、failure mode matrix、test strategy 和 blocker list。
- PF-P018 执行完成后只能到 `implemented` 或 `blocked`；未经用户确认不得标记 `verified`。

#### 下一条 Prompt 上下文

PF-P018 已执行并由用户确认 `verified`，产物是 `workbench-write-uow-boundary-design.md`。PF-P019 已生成并审查。下一步允许执行 PF-P019。PF-P019 应只新增目标契约测试，不实现 UoW，不修改生产逻辑。

#### 变更文件

- `docs/architecture/backend-refactor/workbench-write-uow-boundary-design.md`
- `docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`

#### 执行结果

- 已新增 UoW 边界设计文档，覆盖 Current State Inventory、UoW Boundary Matrix、目标 transaction sequence、Postgres/repository boundary、read model/dirty scope/outbox contract、failure mode matrix、test strategy 和 blocker list。
- 已确认当前最关键 blocker：`RuntimeQueueRepository.enqueue_read_model_refresh()` 自己开启事务，不能直接加入 Workbench facts transaction；实现前需要 transaction-bound dirty/outbox writer 或等价拆分。
- 已确认未来 UoW 必须将 facts、audit/history、dirty scope、outbox、source_version 和 durable idempotency 放入同一 PostgreSQL transaction。
- 未修改任何 `.py` 文件、tests、SQL migration、前端、部署、CI/CD 或生产配置。
- 未执行 Merge Gate、Traffic Gate、push、deploy 或生产访问。

#### 验证

- `git status --short --branch`：Pass，只显示 4 个允许文档变更。
- `git ls-files --others --exclude-standard`：Pass，只显示新增允许文档 `workbench-write-uow-boundary-design.md`。
- `git diff --name-only`：Pass，只显示允许文档。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `git diff --name-only | rg -v '^(docs/architecture/backend-refactor/workbench-write-uow-boundary-design\.md$|docs/architecture/backend-refactor/workbench-writes-and-matching-plan\.md$|docs/architecture/backend-refactor/migration-state-log\.md$|docs/architecture/backend-refactor/refactor-prompts\.md$)'`：Pass，无输出。

未经用户确认不得标记 `verified`。

### PF-P019 - Workbench UoW Contract Tests

状态：`verified`

#### 范围

- 只新增 Workbench UoW 目标契约测试。
- 允许新增 `tests/test_workbench_uow_contract.py`。
- 允许更新 backend-refactor 文档和状态机。
- PF-P019 是 TDD red phase：新增目标契约测试预期在当前实现上失败；失败必须指向缺失的 UoW / transaction-bound dirty-outbox writer / stale-write guard / durable idempotency，而不是语法错误、导入路径错误或测试夹具错误。

#### 禁止范围

- 不实现 UoW、transaction manager、repository rewrite、outbox writer、dirty scope writer、source_version writer、durable idempotency store 或 stale-write guard。
- 不修改任何生产 `.py` 文件。
- 不修改 SQL migration、前端、网关、部署、CI/CD 或生产配置。
- 不修改现有 characterization tests 的期望来适配目标语义。
- 不执行 Merge Gate、Traffic Gate、push、deploy 或生产访问。

#### 验收标准

- 已新增 `tests/test_workbench_uow_contract.py`，共 16 个目标契约测试。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Expected Red，运行 16 个测试，14 个失败、2 个通过。失败均指向缺失的 `fin_ops_platform.services.workbench_uow.WorkbenchWriteUnitOfWork` 或 transaction-bound read model refresh writer，不是语法错误、夹具错误或外部依赖错误。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，29 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_dirty_queue_wiring -v`：Pass，17 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- 本轮未修改任何生产 `.py` 文件、SQL migration、前端、部署或 CI/CD。
- PF-P019 已由用户确认 `verified`。

#### 下一条 Prompt 上下文

PF-P019 已由用户确认 `verified`。新增测试显示当前最先阻塞点是 transaction-bound dirty/outbox writer 和 `WorkbenchWriteUnitOfWork` 目标接口缺失。PF-P020 已生成并审查，下一步允许执行 PF-P020：先让 read model refresh dirty scope/outbox writer 能复用外层 PostgreSQL transaction，再进入完整 UoW 实现。

### PF-P020 - Workbench Transaction-bound Dirty/Outbox Writer

状态：`verified`

#### 范围

- 只实现 runtime queue 层的 transaction-bound read model refresh dirty/outbox writer。
- 优先让 PF-P019 中 3 个 platform transaction-bound writer tests 变绿。
- 允许在 `RuntimeQueueRepository` 上新增 `enqueue_read_model_refresh_in_transaction(transaction=...)` 或等价最小接口。
- 允许让现有 `enqueue_read_model_refresh()` 打开事务后委托 transaction-bound 方法，以保持现有 public API 兼容。
- 允许补充 `tests/test_runtime_queue.py` 中的 focused unit tests。
- 允许更新 backend-refactor 状态机、prompt 库和 UoW 设计文档。

#### 禁止范围

- 不实现 `WorkbenchWriteUnitOfWork`。
- 不新增 `workbench_uow.py`。
- 不把任何 Workbench facade / server handler 接入 UoW。
- 不修 stale write / optimistic locking。
- 不实现 durable idempotency store。
- 不修改 Workbench 生产写路径、SQL migration、前端、部署、CI/CD 或生产配置。
- 不修改 PF-P019 target tests 来绕过红灯。
- 不执行 Merge Gate、Traffic Gate、push、deploy 或生产访问。

#### 验收标准

- 已在 `RuntimeQueueRepository` 上新增 `enqueue_read_model_refresh_in_transaction(transaction=...)`，并让现有 `enqueue_read_model_refresh()` 打开 transaction 后委托该方法。
- 已新增 `tests.test_runtime_queue` 的 3 个 focused tests，覆盖 supplied transaction、source_version/outbox payload contract、旧 public API 委托。
- Red step：PF-P019 的 3 个 writer tests 执行前均按预期失败，失败原因是缺少 transaction-bound writer。
- `tests.test_runtime_queue`：Pass，31 tests。
- PF-P019 writer group：Pass，3 tests。
- `tests.test_workbench_uow_contract`：Expected Red，16 tests，11 failures，5 ok；剩余失败均指向缺失 `WorkbenchWriteUnitOfWork` / UoW 语义。
- `tests.test_workbench_write_characterization`：Pass，29 tests。
- `tests.test_workbench_dirty_queue_wiring`：Pass，17 tests。
- `tests.test_platform_runtime_boundary_guards`：Pass，12 tests。
- 本轮未新增 `workbench_uow.py`，未修改 `server.py`、`workbench_write_facade.py`、Workbench facts repositories、SQL migration、前端、部署或 CI/CD。
- PF-P020 已由用户确认 `verified`。

#### 下一条 Prompt 上下文

PF-P020 已由用户确认 `verified`。PF-P021 已生成并审查，下一步允许执行 PF-P021：只建立最小 `WorkbenchWriteUnitOfWork.run(command, handler)` skeleton，并接入 PF-P020 的 transaction-bound writer；仍不得一次性迁移全部 Workbench 写路径，不得在同一 prompt 中修 stale write 或 durable idempotency。

### PF-P021 - Workbench Minimal Unit of Work Skeleton

状态：`verified`

#### 范围

- 只新增最小 `backend/src/fin_ops_platform/services/workbench_uow.py`。
- 只实现 `WorkbenchWriteUnitOfWork.__init__(connection, repository_factory, read_model_refresh_writer, idempotency_store)` 与 `run(command, handler)` skeleton。
- `run()` 必须打开一个 PostgreSQL transaction，创建 transaction-bound repository context，执行 handler，然后用 read model writer 在同一 transaction 中写 dirty scope/outbox。
- 只允许让 PF-P019 中 UoW atomicity contract 子集转绿。
- 允许更新 backend-refactor 状态机、prompt 库和 UoW 设计文档。

#### 禁止范围

- 不迁移任何 Workbench `server.py` handler。
- 不修改 `workbench_write_facade.py`。
- 不修改 Workbench facts repositories。
- 不修 stale write / optimistic locking。
- 不实现 durable idempotency store 或 idempotency replay。
- 不实现完整 Workbench write usecase。
- 不修改 SQL migration、前端、部署、CI/CD 或生产配置。
- 不修改 PF-P019 target tests 来绕过红灯。
- 不执行 Merge Gate、Traffic Gate、push、deploy 或生产访问。

#### 验收标准

- PF-P021 prompt 已写入 `refactor-prompts.md` 并完成审查。
- PF-P021 必须要求先跑 PF-P019 的 UoW skeleton/atomicity tests 作为红灯。
- PF-P021 必须保持 PF-P020 writer group、runtime queue、Workbench characterization、dirty queue wiring 和 platform guard tests 绿色。
- PF-P021 必须明确 `tests.test_workbench_uow_contract` 全量仍可保持 Expected Red，但剩余失败只能是 stale write / durable idempotency 目标语义，不得再是缺失 `WorkbenchWriteUnitOfWork`。
- PF-P021 执行完成后只能到 `implemented` 或 `blocked`；未经用户确认不得标记 `verified`。

#### 变更文件

- `backend/src/fin_ops_platform/services/workbench_uow.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-write-uow-boundary-design.md`
- `docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`

#### 执行摘要

- 新增最小 `WorkbenchWriteUnitOfWork` 与 `WorkbenchWriteUnitOfWorkContext`。
- `WorkbenchWriteUnitOfWork.run(command, handler)` 打开 `connection.transaction()`，通过 `repository_factory(transaction)` 创建 transaction-bound repository context，调用 handler，并在同一 transaction 内调用 `read_model_refresh_writer.enqueue_refresh(...)` 写 read model dirty/outbox。
- 返回 payload 会补充 `source_versions` 和 `outbox_event_ids`。
- handler 或 writer 抛错时不吞异常，交由 transaction context rollback。
- 本轮未修改 `server.py`、`workbench_write_facade.py`、Workbench facts repositories、PF-P019 tests、SQL migration、前端、部署或 CI/CD。

#### 验证

- PF-P021 指定的 4 个 UoW atomicity tests：Pass，4 tests。
- PF-P020 writer group：Pass，3 tests。
- `tests.test_workbench_uow_contract`：Expected Red，16 tests，7 failures，9 ok；剩余 failures 均为 stale write / durable idempotency 目标语义，不再是缺失 `WorkbenchWriteUnitOfWork` 或 UoW atomicity skeleton。
- `tests.test_runtime_queue`：Pass，31 tests。
- `tests.test_workbench_write_characterization`：Pass，29 tests。
- `tests.test_workbench_dirty_queue_wiring`：Pass，17 tests。
- `tests.test_platform_runtime_boundary_guards`：Pass，12 tests。
- PF-P021 已由用户确认 `verified`。

#### 下一条 Prompt 上下文

PF-P021 已由用户确认 `verified`。PF-P021-MG 已生成并审查，下一步允许执行 PF-P021-MG。PF-P021-MG 必须统一覆盖 PF-P019/PF-P020/PF-P021 这条 UoW 基础切片中尚未合入 `main` 的完整 diff，并明确处理 `tests/test_workbench_uow_contract.py` 仍有 expected-red failures 的 CI 合入风险。不得在 PF-P021-MG 前继续迁移更多 Workbench 写路径。

### PF-P021-MG - Workbench Minimal Unit of Work Skeleton Merge Gate

状态：`verified`

#### 范围

- 只处理 UoW 基础切片的 Merge Gate。
- 覆盖当前分支相对 `main` 的完整 diff：
  - `backend/src/fin_ops_platform/services/runtime_queue.py`
  - `backend/src/fin_ops_platform/services/workbench_uow.py`
  - `tests/test_runtime_queue.py`
  - `tests/test_workbench_uow_contract.py`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
  - `docs/architecture/backend-refactor/workbench-write-uow-boundary-design.md`
  - `docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`
- 只允许做范围检查、验证、必要的 upstream sync、merge to main、main 上复验和状态机回写。

#### 硬门禁

- 必须确认 PF-P019、PF-P020、PF-P021 均已 `verified`。
- 必须确认不包含 `server.py`、`workbench_write_facade.py`、Workbench facts repositories、SQL migration、前端、网关、部署或 CI/CD 变更。
- 必须确认 `tests/test_workbench_uow_contract.py` 的 expected-red failures 不会破坏默认 CI；如果默认 CI 或 `python -m unittest discover` 会执行该文件并失败，PF-P021-MG 必须 `blocked`，不得 merge。
- 不执行 Traffic Gate、生产访问、部署或 push，除非用户在 MG 执行后另行明确要求。
- 未经用户确认，不得将 PF-P021-MG 标记为 `verified`。

#### 下一条 Prompt 上下文

PF-P021-MG 已执行并被阻断。Blocker：仓库 README、`backend/README.md` 和 `docs/dev/testing.md` 的默认测试入口都是 `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`；`tests/test_workbench_uow_contract.py` 符合默认 discover 规则，且当前 16 tests，7 failures，9 ok，会导致默认 CI 失败。根据 MG 硬门禁，本轮未 merge 到 `main`。

#### 执行结果

- 未 merge 到 `main`。
- 未执行 Traffic Gate、部署、生产访问或 push。
- Branch/diff scope：通过，当前分支相对 `main` 只包含 PF-P019/PF-P020/PF-P021 UoW 基础切片预期文件。
- `git diff --check main...HEAD`：通过。
- `test ! -e backend-go`：通过。
- 默认 CI 风险审计：blocked。`README.md`、`backend/README.md`、`docs/dev/testing.md` 均记录默认后端测试为 `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_uow_contract.py' -v`：Fail，16 tests，7 failures，9 ok。
- PF-P021 targeted UoW tests：Pass，4 tests。
- PF-P020 writer group：Pass，3 tests。
- `tests.test_runtime_queue`：Pass，31 tests。
- `tests.test_workbench_write_characterization`：Pass，29 tests。
- `tests.test_workbench_dirty_queue_wiring`：Pass，17 tests。
- `tests.test_platform_runtime_boundary_guards`：Pass，12 tests。

#### 下一条 Prompt 上下文

下一步必须先生成并审查一个修正 prompt，处理 `tests/test_workbench_uow_contract.py` 的默认 CI 策略。建议方向：将尚未实现的 target contract cases 用显式、可审查的 `unittest.expectedFailure` 或等价机制隔离，使默认 CI 不失败，同时保留手动 target contract suite 和 unexpected success 信号。修正前不得 merge，不得继续迁移 Workbench 写路径。

#### 重新执行结果（PF-P021-CI 后）

- 已 merge 到本地 `main`，merge commit：`387ee0d1 feat(workbench): establish transaction-bound uow skeleton`。
- 未执行 Traffic Gate、部署、生产访问或 push。
- `git fetch origin` 后确认 `main` 与 `origin/main` 无分歧；合入前当前 UoW 分支只比 `origin/main` 超前。
- Branch/diff scope：通过，合入 diff 只包含 PF-P019/PF-P020/PF-P021/PF-P021-CI 预期文件。
- `git diff --check main...HEAD`（合入前）：通过。
- `test ! -e backend-go`：通过。
- 默认测试入口审计：`README.md`、`backend/README.md`、`docs/dev/testing.md` 均记录默认后端测试为 `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`。
- 默认 CI blocker 已解除：`tests/test_workbench_uow_contract.py` 现在被默认 discover 执行时退出码为 0，并显示 `expected failures=7`。

合入前验证：

- PF-P021 targeted UoW tests：Pass，4 tests。
- PF-P020 writer group：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests，`expected failures=7`。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_uow_contract.py' -v`：Pass，16 tests，`expected failures=7`。
- `tests.test_runtime_queue`：Pass，31 tests。
- `tests.test_workbench_write_characterization`：Pass，29 tests。
- `tests.test_workbench_dirty_queue_wiring`：Pass，17 tests。
- `tests.test_platform_runtime_boundary_guards`：Pass，12 tests。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`：Pass，1947 tests，`skipped=25`，`expected failures=7`。

main 上复验：

- PF-P021 targeted UoW tests：Pass，4 tests。
- PF-P020 writer group：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests，`expected failures=7`。
- `tests.test_runtime_queue`：Pass，31 tests。
- `tests.test_workbench_write_characterization`：Pass，29 tests。
- `tests.test_workbench_dirty_queue_wiring`：Pass，17 tests。
- `tests.test_platform_runtime_boundary_guards`：Pass，12 tests。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`：Pass，1947 tests，`skipped=25`，`expected failures=7`。

PF-P021-MG 已由用户确认 `verified`，并已推送到 `origin/main`。当前 `main...origin/main` 为 `0 0`。下一条 prompt 已按规则从最新 `main` 新建分支 `codex/workbench-uow-integration-planning` 后生成；不得直接在 `main` 或旧分支继续实现。

### PF-P021-CI - Workbench UoW Contract Test CI Isolation

状态：`verified`

#### 范围

- 只处理 `tests/test_workbench_uow_contract.py` 中尚未实现目标契约的 expected-red cases 如何与默认 `unittest discover` 共存。
- 建议使用 `unittest.expectedFailure` 标记 7 个尚未实现的 stale write / durable idempotency target tests。
- 保留 9 个已通过的 writer、UoW atomicity 和 worker/source_version tests 为普通绿色测试。
- 允许更新 backend-refactor 状态机、prompt 库和 UoW 设计文档。

#### 禁止范围

- 不修改生产代码。
- 不修改 `runtime_queue.py`、`workbench_uow.py`、`server.py`、`workbench_write_facade.py` 或 Workbench facts repositories。
- 不删除 target tests。
- 不使用 `unittest.skip` 或条件跳过隐藏债务。
- 不改变 expected-red target tests 的断言语义。
- 不执行 Merge Gate、Traffic Gate、部署、push 或生产访问。

#### 验收标准

- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_uow_contract.py' -v` 必须退出码为 0，并显示 7 个 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v` 必须退出码为 0，并显示 7 个 expected failures。
- PF-P021 targeted UoW tests 与 PF-P020 writer group 保持普通 pass，不被标记为 expectedFailure。
- 现有 runtime queue、Workbench write characterization、dirty queue wiring 和 platform guard tests 保持绿色。
- PF-P021-CI 执行完成后只能到 `implemented` 或 `blocked`；未经用户确认不得标记 `verified`。

#### 执行结果

- 只修改了 `tests/test_workbench_uow_contract.py` 和 backend-refactor 文档；未修改生产代码、默认测试入口、README、部署或 CI/CD 配置。
- 以下 7 个尚未实现的 target contract tests 已标记为 `unittest.expectedFailure`：
  - `test_withdraw_submit_rejects_stale_preview_relation_version`
  - `test_cancel_link_rejects_stale_replaced_relation`
  - `test_ignore_row_rejects_when_row_already_confirmed`
  - `test_cash_special_rejects_changed_relation_version`
  - `test_confirm_link_idempotency_key_replays_first_result_without_duplicate_history`
  - `test_exception_apply_idempotency_key_replays_first_result_without_duplicate_case_or_outbox`
  - `test_cash_special_idempotency_key_does_not_append_duplicate_history`
- 已通过的 9 个 writer、UoW atomicity 和 worker/source_version tests 保持普通 pass，未标记 expectedFailure。

#### 变更文件

- `tests/test_workbench_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-write-uow-boundary-design.md`
- `docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`

#### 验证结果

- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_uow_contract.py' -v`：Pass，16 tests，`expected failures=7`。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests，`expected failures=7`。
- PF-P021 targeted UoW 4 tests：Pass，普通绿色测试。
- PF-P020 writer group 3 tests：Pass，普通绿色测试。
- `tests.test_runtime_queue`：Pass，31 tests。
- `tests.test_workbench_write_characterization`：Pass，29 tests。
- `tests.test_workbench_dirty_queue_wiring`：Pass，17 tests。
- `tests.test_platform_runtime_boundary_guards`：Pass，12 tests。
- 本轮未执行 merge、Traffic Gate、部署、push 或生产访问。

#### 下一条 Prompt 上下文

PF-P021-CI 已由用户确认 `verified`。下一步重新执行 `PF-P021-MG - Workbench Minimal Unit of Work Skeleton Merge Gate`，确认默认 CI blocker 已解除后再考虑 merge 到 `main`。在 PF-P021-MG 通过前，不得继续迁移 Workbench 写路径。

### PF-P022 - Workbench Write UoW Integration Planning / Stale Write and Idempotency Strategy

状态：`verified`

#### 范围

- 只做 Workbench 写路径接入 UoW 的规划和策略设计。
- 梳理真实写 API、`WorkbenchWriteFacade` 方法、UoW 接入点、facts/audit/history/dirty/outbox 事务包裹范围。
- 明确 stale write / optimistic locking 策略，包括所需 expected version 字段、冲突状态码、响应契约和兼容路径。
- 明确 durable idempotency 策略，包括 storage owner、key 语义、request fingerprint、result replay、mismatched replay conflict、retention/TTL 和事务语义。
- 将 `tests/test_workbench_uow_contract.py` 中 7 个 `expectedFailure` 目标测试拆分为后续可执行的转绿阶段。
- 产出或更新 `docs/architecture/backend-refactor/workbench-uow-integration-plan.md`，并按需要回写 UoW 边界设计和 Workbench 写路径计划。

#### 禁止范围

- 不修改生产代码。
- 不修改测试代码、测试断言或 `unittest.expectedFailure` 标记。
- 不修改 SQL migration 或数据库 schema。
- 不修改前端、部署、CI/CD、Nginx、worker 运行配置。
- 不执行 stale write、durable idempotency 或真实写 API 的实现。
- 不执行 merge、push、Traffic Gate、部署或生产访问。

#### 验收标准

- `refactor-prompts.md` 已写入完整 PF-P022 prompt。
- `migration-state-log.md` 当前 active prompt 指向 PF-P022 planned。
- prompt 明确要求 Pre-Flight、Allowed Scope、Forbidden Scope、Required Output、Verification 和 Post-Flight。
- prompt 明确要求 7 个 expectedFailure 目标测试的分阶段转绿计划。
- prompt 只允许 backend-refactor 文档变更；不允许生产代码、测试、SQL migration 或部署配置变更。

#### 审查结论

- PF-P022 的方向合理：PF-P021 只建立了 minimal UoW skeleton，尚未迁移真实 Workbench 写路径；直接实现 stale write 或 idempotency 会过早扩大 blast radius。
- 当前更安全的下一步是规划真实写 API 如何分批接入 UoW，并先确定 7 个 target contract tests 的转绿顺序、所需数据契约和潜在 schema 需求。
- PF-P022 不应修复任何 `expectedFailure` 测试；它只为后续 PF-P023/PF-P024/PF-P025 等执行 prompt 提供事实源。

#### 下一条 Prompt 上下文

PF-P022 已由用户确认 `verified`。PF-P022 的主要产物是 `workbench-uow-integration-plan.md`，结论是下一步不应直接迁移真实写路径，而应先执行已生成并审查的 `PF-P023 - Workbench Stale Write Contract and Compatibility Tests`。

#### 执行结果

- 新增 `docs/architecture/backend-refactor/workbench-uow-integration-plan.md`。
- 回写 `docs/architecture/backend-refactor/workbench-write-uow-boundary-design.md`，记录 PF-P022 产物和后续分步策略。
- 回写 `docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`，记录真实写路径接入顺序。
- 更新 `docs/architecture/backend-refactor/refactor-prompts.md` 的 PF-P022 执行结果。
- 未修改生产代码、测试代码、SQL migration、前端、部署、CI/CD、Nginx 或 worker 运行配置。

关键发现：

- 真实 Workbench 写 API 仍未接入 `WorkbenchWriteUnitOfWork`。
- 当前写入口仍是 `server.py` handler -> `WorkbenchWriteFacade` -> App Shell callback。
- `confirm_link` / `cancel_link` 是第一批真实 UoW 迁移候选，但仍需先补 stale write contract 与 durable idempotency store contract。
- Durable idempotency 需要持久化 store；纯内存 store 不能支撑多进程、重启或 HTTP retry。
- Stale write 需要统一 `expected_versions`，并让前端/读模型 payload 暴露 relation/case/row/source version。
- 7 个 `unittest.expectedFailure` 目标测试应拆成多个小切片转绿，不能一次性全部实现。

验证结果：

- `git status --short --branch`：已执行。
- `git rev-list --left-right --count main...origin/main`：已执行。
- `git ls-files --others --exclude-standard`：已执行。
- `git diff --name-only`：已执行。
- `git diff --check`：已执行。
- `test ! -e backend-go`：已执行。
- allowlist diff check：已执行。
- 未运行 Python tests：PF-P022 是 docs-only planning，且没有修改生产代码或测试。

#### 下一条 Prompt 上下文

用户已确认 PF-P022 `verified`。PF-P023 已生成并审查，下一步允许执行 PF-P023。PF-P023 应先补 expected relation/case/row versions、withdraw preview/submit 版本契约和 409 conflict response tests；仍不得直接迁移生产写路径。

### PF-P023 - Workbench Stale Write Contract and Compatibility Tests

状态：`verified`

#### 范围

- 只做 Workbench stale write / optimistic locking 的测试契约和兼容性测试。
- 覆盖 expected relation/case/row/source version 的 command/payload contract。
- 覆盖 withdraw preview -> submit 的 relation identity/version 传递契约。
- 覆盖 409 conflict response shape。
- 必须保持默认 CI 绿色；尚未实现的目标语义必须用 `unittest.expectedFailure` 或等价显式机制保留，不能用 skip 隐藏。

#### 禁止范围

- 不修改生产代码。
- 不迁移任何真实 Workbench 写 API 到 UoW。
- 不实现 stale write guard。
- 不实现 durable idempotency store。
- 不新增或修改 SQL migration。
- 不修改前端、部署、CI/CD、Nginx、worker 运行配置。
- 不执行 Merge Gate、Traffic Gate、部署、生产访问或 push。

#### 验收标准

- `tests/test_workbench_uow_contract.py` 保留 7 个 `expectedFailure` 目标契约测试，并补强 stale cancel、ignore、cash special 三条测试，断言 stale conflict 发生时 handler 不得执行。
- 新增 `tests/test_workbench_stale_write_contract.py`，包含 1 个普通通过的 write payload compatibility test，以及 2 个 `expectedFailure` 目标测试：
  - withdraw preview 未来必须暴露 stable relation identity/version 和 `submit_expected_versions`；
  - future `WorkbenchWriteConflict` 必须能产生稳定 409 JSON payload。
- 没有修改生产代码、SQL、前端、部署、worker 或真实写路径迁移代码。
- 默认 CI 兼容性保持绿色，`expectedFailure` 未被替换成 skip。

#### 审查结论

- PF-P023 已把 stale write / optimistic locking 的目标语义固定为机械测试门禁，但仍未实现 production stale guard。
- 已确认 API/preview 缺口：withdraw preview 当前没有暴露 `active_relation.version` 或 `submit_expected_versions`；当前 UoW 也没有 `WorkbenchWriteConflict` 响应对象。
- 当前 `expected_versions` payload 向后兼容：现有 withdraw submit 会忽略新增字段并保持现有成功响应 shape。
- PF-P023 不处理 durable idempotency；该工作仍应留给 PF-P024。

#### 下一条 Prompt 上下文

PF-P023 已由用户确认 `verified`。下一步允许执行已生成并审查的 `PF-P024 - Workbench Durable Idempotency Store Contract`。PF-P024 继续处理 3 个 durable idempotency `expectedFailure` 目标测试和 schema/repository readiness；仍不得直接迁移真实 Workbench 写路径。

### PF-P024 - Workbench Durable Idempotency Store Contract

状态：`verified`

#### 范围

- 只做 durable idempotency store 的测试契约、schema/readiness 设计和文档回写。
- 覆盖 3 个 durable idempotency target tests：
  - `confirm_link` same key/fingerprint replay，不重复 history/outbox；
  - `exception_apply` same key/fingerprint replay，不重复 case/outbox；
  - `cash_special` same key/fingerprint replay，不重复 relation history。
- 覆盖 idempotency record 目标字段、request fingerprint、tenant/actor/key 隔离、committed replay、fingerprint mismatch conflict、in-progress/reserved 语义。
- 必须保持默认 CI 绿色；尚未实现的目标语义必须使用 `unittest.expectedFailure`，不得使用 skip 隐藏。

#### 禁止范围

- 不修改生产代码。
- 不新增或修改 SQL migration。
- 不实现 durable idempotency store。
- 不实现 replay 逻辑。
- 不迁移 `confirm_link`、`exception_apply`、cash special 或任何真实 Workbench 写 API 到 UoW。
- 不修改前端、部署、CI/CD、Nginx、worker 运行配置。
- 不执行 Merge Gate、Traffic Gate、部署、生产访问或 push。

#### 执行结果

- 已补强 `tests/test_workbench_uow_contract.py` 中 3 个 durable idempotency target tests，使 command 契约显式携带 `tenant_id`、`actor_id`、`request_fingerprint` 和业务 payload。
- 已新增 `tests/test_workbench_idempotency_contract.py`，覆盖 durable idempotency record、request fingerprint、same key different fingerprint 409 conflict、committed replay、同事务 reserve/commit 顺序，以及 HTTP 写接口兼容额外 `idempotency_key` / `request_idempotency_key` 字段。
- 新增 target contract tests 使用 `unittest.expectedFailure` 保留目标语义；没有使用 skip、条件 skip 或环境变量规避。
- 当前默认 CI 兼容性保持绿色；新目标语义尚未实现，因此仍表现为 expected failures。
- 未修改生产代码、SQL migration、前端、部署、worker 或真实 Workbench 写路径。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：通过，6 tests，`expected failures=5`。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：通过，16 tests，`expected failures=7`。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization tests.test_workbench_stale_write_contract tests.test_workbench_uow_contract tests.test_workbench_idempotency_contract tests.test_workbench_dirty_queue_wiring tests.test_runtime_queue -v`：通过，102 tests，`expected failures=14`。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：通过，3 tests，`expected failures=2`。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_dirty_queue_wiring -v`：通过，17 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue -v`：通过，31 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：通过，12 tests。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_uow_contract.py' -v`：通过，16 tests，`expected failures=7`。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_idempotency_contract.py' -v`：通过，6 tests，`expected failures=5`。
- `git diff --check`：通过。
- `test ! -e backend-go`：通过。
- scope allowlist check：通过；除允许的 PF-P024 tests/docs 之外无其他改动。`tests/test_workbench_idempotency_contract.py` 是本轮允许新增文件。

#### 审查结论

- PF-P024 是 PF-P023 后的正确下一步：stale write contract 已锁定，下一步应先把 durable idempotency 的 record/replay/fingerprint/conflict 契约固定为机械测试门禁。
- PF-P024 不应写 SQL migration 或实现 store；真实 store 实现应进入后续 prompt。
- PF-P024 不应把任何 Workbench 写 API 接入 UoW；真实迁移必须等待 stale write 与 durable idempotency contracts 都稳定。
- PF-P024 执行后确认的实现缺口：尚无 `WorkbenchIdempotencyRecord`、`workbench_request_fingerprint`、`WorkbenchIdempotencyKeyConflict`、durable idempotency repository、同事务 reserve/commit/replay 生产逻辑，也没有对应 SQL migration。
- PF-P024 已由用户确认 `verified`。

#### 下一条 Prompt 上下文

PF-P024 已由用户确认 `verified`。PF-P025 已生成并审查，下一步只允许执行 PF-P025。PF-P025 应优先处理 durable idempotency 的实现前置，而不是直接迁移真实 Workbench 写 API。

### PF-P025 - Workbench Durable Idempotency Repository and Fingerprint Skeleton

状态：`verified`

#### 范围

- 只实现 Workbench durable idempotency 的可复用基础原语：
  - `WorkbenchIdempotencyRecord`
  - `workbench_request_fingerprint`
  - `WorkbenchIdempotencyKeyConflict`
  - repository port / skeleton 或 in-memory contract adapter
- 让 PF-P024 中 record、fingerprint、conflict 相关目标测试转绿。
- 可新增 repository skeleton contract tests，但不得要求真实 PostgreSQL migration。
- 保持 UoW replay / reserve / commit 集成测试为 `expectedFailure`，除非 prompt 明确允许最小 skeleton wiring；本轮默认不接入真实写路径。
- 必须澄清 PF-P024 中 `record.identity` action-scoped 断言与 durable persistence unique key `(tenant_id, actor_id, idempotency_key)` 的命名边界，避免后续实现混用。

#### 禁止范围

- 不迁移 `confirm_link`、`cancel_link`、`exception_apply`、cash special、ignore、withdraw 或任何真实 Workbench 写 API。
- 不修改 `app/server.py` 的 Workbench handler 行为。
- 不实现完整 `WorkbenchWriteUnitOfWork.run()` idempotency replay / reserve / commit 流程。
- 不新增或修改 SQL migration。
- 不把 repository 接到真实 PostgreSQL 表。
- 不修改前端、部署、CI/CD、Nginx、worker 运行配置。
- 不执行 Merge Gate、Traffic Gate、部署、生产访问、merge 或 push。

#### 验收标准

- `tests/test_workbench_idempotency_contract.py` 中 record、fingerprint、conflict 测试应转为普通通过测试。
- 任何仍未实现的 UoW replay / reserve / commit 目标语义必须继续用 `unittest.expectedFailure` 显示保留，不得 skip。
- `tests/test_workbench_uow_contract.py` 仍保持默认 CI 绿色。
- production 代码变更只允许在 Workbench UoW/idempotency primitive 边界内。
- 不得改变真实 Workbench 写 API 的响应和副作用。

#### 执行结果

- 新增 `backend/src/fin_ops_platform/services/workbench_idempotency.py`，实现 durable idempotency primitive 和 in-memory repository skeleton。
- `backend/src/fin_ops_platform/services/workbench_uow.py` 仅 re-export idempotency primitive；未修改 `WorkbenchWriteUnitOfWork.run()` 的 replay / reserve / commit 行为。
- `tests/test_workbench_idempotency_contract.py` 中 record、fingerprint、conflict 相关目标测试已转为普通通过测试。
- 新增 repository skeleton contract test：覆盖 reserve、commit、replay-safe payload、same key different fingerprint conflict 检测和敏感字段过滤。
- 已拆分 identity 命名：
  - `unique_identity = (tenant_id, actor_id, idempotency_key)` 用于 durable persistence unique key；
  - `action_identity = (tenant_id, action_name, idempotency_key)` 用于 action-scoped routing identity；
  - `identity` 保持 action identity 兼容，避免破坏既有 PF-P024 测试语义。
- 未新增 SQL migration，未接真实 PostgreSQL 表，未迁移任何真实 Workbench 写 API。

#### 验证

- RED 验证：移除 record/fingerprint/conflict expectedFailure 后，4 个目标测试因缺少 `WorkbenchIdempotencyRecord`、`workbench_request_fingerprint`、`WorkbenchIdempotencyKeyConflict`、repository skeleton 失败。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：通过，7 tests，`expected failures=2`。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：通过，16 tests，`expected failures=7`。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：通过，3 tests，`expected failures=2`。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：通过，29 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_dirty_queue_wiring -v`：通过，17 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue -v`：通过，31 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：通过，12 tests。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_idempotency_contract.py' -v`：通过，7 tests，`expected failures=2`。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_uow_contract.py' -v`：通过，16 tests，`expected failures=7`。
- `git diff --check`：通过。
- `test ! -e backend-go`：通过。
- scope allowlist check：通过；除 PF-P025 允许的 Workbench UoW/idempotency tests/docs 文件外无其他改动。

#### 审查结论

- PF-P025 是 PF-P024 后的正确下一步：它补齐实现前置 primitive，避免直接把复杂写路径接入 UoW。
- 真实 durable PostgreSQL repository、SQL migration 和 UoW replay/commit 集成仍应进入后续 prompt。
- PF-P025 通过后，再评估是否进入 `PF-P026 - Workbench UoW Idempotency Integration Skeleton` 或先补 `PF-P025-MG`，取决于本分支是否达到可合并切片边界。
- PF-P025 执行后确认的剩余缺口：UoW 仍不会调用 idempotency `get/reserve/commit`，不会 replay committed records，不会拒绝 fingerprint conflict；durable PostgreSQL repository / SQL migration 仍未实现。
- PF-P025 已由用户确认 `verified`。

#### 下一条 Prompt 上下文

PF-P025 已由用户确认 `verified`。PF-P026 已生成并审查，下一步只允许执行 PF-P026。PF-P026 仍不应迁移真实 Workbench 写 API，只应把 PF-P025 的 primitive 以 fake/in-memory repository contract 方式接入 `WorkbenchWriteUnitOfWork.run()`，让 UoW replay / reserve / commit 集成测试转绿。

### PF-P026 - Workbench UoW Idempotency Integration Skeleton

状态：`verified`

#### 范围

- 只把 PF-P025 的 idempotency primitive 接入 `WorkbenchWriteUnitOfWork.run()`。
- 只使用 fake/in-memory repository contract，不接真实 PostgreSQL idempotency 表。
- 目标是让 UoW committed replay、same key different fingerprint conflict、reserve/commit 顺序相关测试转绿。
- 可以移除已经转绿的 durable idempotency `expectedFailure` 标记，但不得删除测试或弱化断言。

#### 禁止范围

- 不迁移 `confirm_link`、`cancel_link`、`exception_apply`、cash special、ignore、withdraw 或任何真实 Workbench 写 API。
- 不修改 `app/server.py`。
- 不修改 `workbench_write_facade.py`。
- 不新增或修改 SQL migration。
- 不实现真实 PostgreSQL durable idempotency repository。
- 不修改前端、部署、CI/CD、Nginx、worker 运行配置。
- 不执行 Merge Gate、Traffic Gate、部署、生产访问、merge 或 push。

#### 验收标准

- `tests/test_workbench_idempotency_contract.py` 中 UoW replay / reserve / commit 集成测试应转为普通通过测试。
- `tests/test_workbench_uow_contract.py` 中 durable idempotency 相关目标测试如已被本轮实现覆盖，应移除 `expectedFailure` 并转为普通通过测试。
- stale write / optimistic locking 相关 expectedFailure 不属于 PF-P026，必须保留。
- 不改变真实 Workbench HTTP API 行为。
- 不引入数据库 migration。

#### 审查结论

- PF-P026 是 PF-P025 后的正确下一步：先把 primitive 接到 UoW skeleton，再考虑真实写路径迁移。
- PF-P026 仍然不是业务 API 迁移 prompt；它只处理 UoW 层的幂等集成骨架。
- PF-P026 完成后，应评估本分支是否已经达到可合并切片，优先考虑生成 `PF-P026-MG`，而不是继续无限扩展。

#### 执行结果

- `WorkbenchWriteUnitOfWork.run()` 已接入 idempotency get/reserve/commit/replay skeleton。
- 对带 `idempotency_key` 的 command，UoW 会先查询 idempotency store。
- 已 committed 且 fingerprint 相同的记录会直接 replay stored response，并带回 `source_versions` 与 `outbox_event_ids`。
- 已存在记录但 fingerprint 不同会抛出 `WorkbenchIdempotencyKeyConflict`，不调用 handler，不写 dirty/outbox。
- 新请求会在 transaction 内 reserve，执行 handler，写 dirty/outbox/source_versions 后 commit idempotency record。
- 兼容 PF-P024/PF-P025 fake store shape 和 `InMemoryWorkbenchIdempotencyRepository`。

#### 已转绿的 expectedFailure

- `tests/test_workbench_idempotency_contract.py`
  - `test_uow_replays_committed_same_fingerprint_without_handler_or_outbox`
  - `test_uow_reserves_and_commits_idempotency_record_inside_same_transaction_after_outbox`
- `tests/test_workbench_uow_contract.py`
  - `test_confirm_link_idempotency_key_replays_first_result_without_duplicate_history`
  - `test_exception_apply_idempotency_key_replays_first_result_without_duplicate_case_or_outbox`
  - `test_cash_special_idempotency_key_does_not_append_duplicate_history`

#### 新增目标测试

- `test_uow_rejects_same_key_with_different_fingerprint_without_handler_or_outbox` 锁定 same key / different fingerprint 不调用 handler、不写 dirty/outbox，并返回稳定 conflict 语义。

#### 仍保留的 expectedFailure

- `test_withdraw_submit_rejects_stale_preview_relation_version`
- `test_cancel_link_rejects_stale_replaced_relation`
- `test_ignore_row_rejects_when_row_already_confirmed`
- `test_cash_special_rejects_changed_relation_version`

这些属于 stale write / optimistic locking，不属于 PF-P026 范围。

#### 验证结果

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests，4 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests，2 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，29 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_dirty_queue_wiring -v`：Pass，17 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue -v`：Pass，31 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_idempotency_contract.py' -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_uow_contract.py' -v`：Pass，16 tests，4 expected failures。

#### 下一条 Prompt 上下文

PF-P026 已由用户确认 `verified`。PF-P026-MG 已生成并审查，下一步只允许执行 PF-P026-MG。PF-P026-MG 统一覆盖 PF-P023/PF-P024/PF-P025/PF-P026 这组 Workbench UoW/idempotency 基础切片，并纳入同分支尚未合入的 PF-P022 规划文档 diff。不得生成 PF-P027，不得迁移真实 Workbench 写 API。

### PF-P026-MG - Workbench UoW Idempotency Integration Merge Gate

状态：`verified`

#### 范围

- 只处理当前分支上 Workbench UoW/idempotency 基础切片合入 `main` 的 Merge Gate。
- 核心覆盖 PF-P023、PF-P024、PF-P025、PF-P026。
- 同时纳入同分支尚未合入的 PF-P022 UoW integration planning 文档 diff，避免 merge scope 漏文件。
- 允许执行范围检查、上游同步、必要验证、merge 到本地 `main`、main 上复验和状态机回写。

#### 禁止范围

- 不迁移真实 Workbench 写 API。
- 不修改 `server.py` 或 `workbench_write_facade.py`。
- 不新增 SQL migration。
- 不实现真实 PostgreSQL idempotency repository。
- 不修 stale write / optimistic locking。
- 不执行 Traffic Gate、部署、生产访问或 push。
- 不生成 PF-P027。

#### 验收标准

- PF-P023、PF-P024、PF-P025、PF-P026 均已 `verified`。
- 当前分支相对 `main` 的 diff 只包含 Workbench UoW/idempotency 基础切片及 backend-refactor 文档。
- 所有目标测试、安全网、default discover 兼容检查通过。
- `tests/test_workbench_uow_contract.py` 仅保留 4 个 stale write / optimistic locking expectedFailure。
- 合入 `main` 后必须在 `main` 上复验通过。

#### 审查结论

- PF-P026-MG 是当前分支的正确下一步：PF-P023 到 PF-P026 已形成可合并的 UoW/idempotency 基础切片。
- 本 MG 不应继续扩大实现范围，不应进入真实 API migration 或 stale write 实现。
- 由于当前切片没有切生产流量，也没有改变真实 Workbench HTTP handler，Traffic Gate 不适用。

#### 执行结果

- 已合入本地 `main`。
- Merge commit：`8c0013bf feat(workbench): establish uow idempotency foundation`。
- 合入覆盖 PF-P023、PF-P024、PF-P025、PF-P026，并纳入同分支前置 PF-P022 UoW integration planning 文档。
- 未执行 Traffic Gate、部署、生产访问或 push。
- 未迁移真实 Workbench 写 API。
- 未修改 `server.py` 或 `workbench_write_facade.py`。
- 未新增 SQL migration。
- 未实现真实 PostgreSQL idempotency repository。
- 未修 stale write / optimistic locking。

#### 合入前验证

- Scope allowlist：通过。
- `git diff --check main...HEAD`：通过。
- `test ! -e backend-go`：通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests，2 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests，4 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_stale_write_contract.py' -v`：Pass，3 tests，2 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_idempotency_contract.py' -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_uow_contract.py' -v`：Pass，16 tests，4 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，29 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_dirty_queue_wiring -v`：Pass，17 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue -v`：Pass，31 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。

#### Main 上复验

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests，2 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests，4 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_stale_write_contract.py' -v`：Pass，3 tests，2 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_idempotency_contract.py' -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -p 'test_workbench_uow_contract.py' -v`：Pass，16 tests，4 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，29 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_dirty_queue_wiring -v`：Pass，17 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue -v`：Pass，31 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。

#### 仍保留的 expectedFailure

- `tests/test_workbench_stale_write_contract.py`
  - `test_withdraw_preview_exposes_relation_identity_and_version_for_submit_expected_versions`
  - `test_target_workbench_write_conflict_response_shape_is_stable`
- `tests/test_workbench_uow_contract.py`
  - `test_withdraw_submit_rejects_stale_preview_relation_version`
  - `test_cancel_link_rejects_stale_replaced_relation`
  - `test_ignore_row_rejects_when_row_already_confirmed`
  - `test_cash_special_rejects_changed_relation_version`

这些均属于 stale write / optimistic locking 目标语义，不属于 PF-P026-MG 本轮合入范围。

#### 下一条 Prompt 上下文

PF-P026-MG 已由用户确认 `verified`，并要求执行 `git push origin main`。push 完成后，下一轮必须从最新 `main` 新建分支，再生成下一条 prompt。建议下一条 prompt 为 `PF-P027 - Workbench Stale Write Boundary Discovery and Planning`，先做 stale write / optimistic locking 的 discovery、边界设计和测试转绿顺序规划，不直接迁移真实 Workbench 写 API。

PF-P026-MG 已 push 到 `origin/main`。已从最新 `main` 创建分支 `codex/workbench-stale-write-planning`。PF-P027 已生成并审查，下一步只允许执行 PF-P027，不得直接实现 stale write，不得迁移真实 Workbench 写 API。

### PF-P027 - Workbench Stale Write Boundary Discovery and Planning

状态：`verified`

#### 范围

- 只做 Workbench stale write / optimistic locking 的 discovery、动态调用链梳理、边界设计和测试转绿顺序规划。
- 聚焦 PF-P026-MG 后仍保留的 stale write / optimistic locking expectedFailure。
- 产出 `docs/architecture/backend-refactor/workbench-stale-write-boundary-plan.md`。
- 更新本文档和 `refactor-prompts.md`。

#### 禁止范围

- 不修改生产代码。
- 不迁移真实 Workbench 写 API。
- 不修改 `server.py` 或 `workbench_write_facade.py`。
- 不新增 SQL migration。
- 不实现 `WorkbenchWriteConflict`。
- 不实现 stale precondition / expected_versions 校验。
- 不执行 Merge Gate、Traffic Gate、部署、生产访问、merge 或 push。

#### 验收标准

- 明确剩余 expectedFailure 的当前行为、目标行为、依赖数据、缺口和分批转绿顺序。
- 输出 withdraw preview/submit、cancel link、ignore row、cash special 的静态调用链和动态运行时序。
- 明确是否需要先实现 conflict primitive、read model payload version identity、repository current-state reader、UoW precondition port。
- 明确后续 prompt 的推荐顺序。

#### 审查结论

- PF-P027 是 PF-P026-MG 后的正确下一步。
- 本 prompt 仍不能直接改真实 API，因为 stale write 会改变用户可见写入语义，必须先把边界、兼容策略、409 response contract 和测试转绿顺序定清楚。

#### 执行结果

- 新增 `workbench-stale-write-boundary-plan.md`，作为 Workbench stale write / optimistic locking 后续切片事实源。
- 确认当前 `_workbench_write_freshness_guard()` 只检查 OA sync dirty scopes / rebuild scheduled，不等价于 facts 级乐观锁。
- 确认 withdraw、cancel link、ignore row、cash special 的 stale write 风险都发生在 facade/service 按当前 facts 执行写入前缺少 expected_versions 对比。
- 确认 `WorkbenchWriteUnitOfWork.run()` 当前已有 transaction、dirty/outbox writer 和 idempotency skeleton，但尚未执行 stale precondition。
- 建议下一条 prompt 为 `PF-P028 - Workbench Write Conflict Primitive and Expected Versions Contract`，先实现 pure primitive / contract，优先转绿统一 409 response shape，不迁移真实 Workbench 写 API。

#### CodeGraph 覆盖

- `_handle_api_workbench_withdraw_link_preview` -> `WorkbenchWriteFacade.preview_withdraw_link`
- `_handle_api_workbench_withdraw_link` -> `_workbench_write_freshness_guard` -> `WorkbenchWriteFacade.withdraw_link`
- `_handle_api_workbench_cancel_link` -> `_workbench_write_freshness_guard` -> `_handle_live_workbench_cancel_link` -> `WorkbenchWriteFacade.cancel_link`
- `_handle_api_workbench_ignore_row` -> `_workbench_write_freshness_guard` -> `_handle_workbench_ignore_row_payload` -> `WorkbenchWriteFacade.ignore_row`
- `_handle_api_workbench_confirm_cash_pass_through` -> `_workbench_write_freshness_guard` -> `WorkbenchWriteFacade.confirm_cash_pass_through`
- `_handle_api_workbench_confirm_cash_ticket_purchase` -> `_workbench_write_freshness_guard` -> `WorkbenchWriteFacade.confirm_cash_ticket_purchase`
- `_handle_api_workbench_cancel_cash_special` -> `_workbench_write_freshness_guard` -> `WorkbenchWriteFacade.cancel_cash_special`
- `WorkbenchWriteUnitOfWork.run()`、`WorkbenchWriteFacade`、`WorkbenchPairRelationService`、`WorkbenchOverrideService` 当前 public surface。

#### 变更文件

- `docs/architecture/backend-refactor/workbench-stale-write-boundary-plan.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`

#### 验证

- `git status --short --branch`：通过，当前在 `codex/workbench-stale-write-planning`。
- `git rev-list --left-right --count main...origin/main`：`0 0`，main 与 origin/main 对齐。
- `git ls-files --others --exclude-standard`：执行，检查 untracked files。
- `git diff --name-only`：仅限 backend-refactor 文档。
- `git diff --check`：通过。
- `test ! -e backend-go`：通过。
- Scope allowlist：通过，仅允许 PF-P027 三个文档文件。

PF-P027 是 docs-only discovery/planning，不运行 Workbench test suite；测试基线引用 PF-P026-MG 在 main 上的复验结果。

#### 下一条 Prompt 上下文

PF-P027 已由用户确认 `verified`。PF-P028 已生成并审查，下一步只允许执行 `PF-P028 - Workbench Write Conflict Primitive and Expected Versions Contract`。PF-P028 应只实现 `WorkbenchWriteConflict` primitive、409 response payload contract 和 expected_versions contract 文档/测试，优先转绿 `test_target_workbench_write_conflict_response_shape_is_stable`；不得迁移真实 Workbench 写 API，不得修 withdraw submit/cancel/ignore/cash special 的真实写路径。

### PF-P028 - Workbench Write Conflict Primitive and Expected Versions Contract

状态：`verified`

#### 范围

- 只建立 Workbench stale write 的统一 conflict primitive 和 expected_versions 契约。
- 优先让 `tests/test_workbench_stale_write_contract.py::WorkbenchStaleWriteContractTests::test_target_workbench_write_conflict_response_shape_is_stable` 从 expectedFailure 转为普通通过。
- 可以新增 `workbench_write_conflict.py`，并从 `workbench_uow.py` re-export `WorkbenchWriteConflict` 以兼容现有测试导入。
- 可以补充纯函数/primitive 单元测试，但不得接入真实写 API。
- 更新本文档和 `refactor-prompts.md`。

#### 禁止范围

- 不迁移真实 Workbench 写 API。
- 不修改 `server.py` handler 路由行为。
- 不修改 `workbench_write_facade.py` 的真实写入逻辑。
- 不实现 repository current-state reader。
- 不实现 UoW stale precondition。
- 不新增 SQL migration。
- 不修改前端。
- 不执行 Merge Gate、Traffic Gate、部署、merge 或 push。

#### 验收标准

- `WorkbenchWriteConflict` 有稳定字段、默认中文 message、409 status 和 response payload。
- `WorkbenchWriteConflict.to_response_payload()` 的 shape 与 PF-P027 文档一致。
- `WorkbenchWriteConflict` 与 `WorkbenchIdempotencyKeyConflict` 的职责边界清楚，不能复用 idempotency error code。
- 只移除 `test_target_workbench_write_conflict_response_shape_is_stable` 的 expectedFailure；其它 stale write expectedFailure 必须继续保留。
- 相关测试通过。

#### 审查结论

- PF-P028 是 PF-P027 后的正确最小实现切片。
- 它可以先建立统一 409 conflict contract，降低后续 cancel/ignore/cash/withdraw API 迁移时的 response 分歧风险。
- PF-P028 仍不能修真实 stale write，因为真实修复需要 transaction-bound facts current-state reader 和 UoW precondition，必须拆到后续 prompt。

#### 执行结果

- 新增 `WorkbenchWriteConflict` primitive，放在 `backend/src/fin_ops_platform/services/workbench_write_conflict.py`。
- `workbench_uow.py` re-export `WorkbenchWriteConflict`，保持 `fin_ops_platform.services.workbench_uow.WorkbenchWriteConflict` 可用。
- `WorkbenchWriteConflict.to_response_payload()` 固化 409 response shape：`workbench_write_conflict`、默认中文 message、`conflict.action/reason/expected/actual`。
- 只移除了 `test_target_workbench_write_conflict_response_shape_is_stable` 的 `unittest.expectedFailure`。
- 未迁移真实 Workbench 写 API。
- 未修改 `server.py` 或 `workbench_write_facade.py`。
- 未实现 UoW stale precondition、repository current-state reader 或 SQL migration。

#### 变更文件

- `backend/src/fin_ops_platform/services/workbench_write_conflict.py`
- `backend/src/fin_ops_platform/services/workbench_uow.py`
- `tests/test_workbench_stale_write_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract.WorkbenchStaleWriteContractTests.test_target_workbench_write_conflict_response_shape_is_stable -v`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests，1 expected failure。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests，4 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `git diff --check`：通过。
- `test ! -e backend-go`：通过。
- Scope allowlist：通过。

#### 仍保留的 expectedFailure

- `tests/test_workbench_stale_write_contract.py`
  - `test_withdraw_preview_exposes_relation_identity_and_version_for_submit_expected_versions`
- `tests/test_workbench_uow_contract.py`
  - `test_withdraw_submit_rejects_stale_preview_relation_version`
  - `test_cancel_link_rejects_stale_replaced_relation`
  - `test_ignore_row_rejects_when_row_already_confirmed`
  - `test_cash_special_rejects_changed_relation_version`

#### 下一条 Prompt 上下文

PF-P028 已由用户确认 `verified`。PF-P029 已生成并审查，下一步只允许执行 `PF-P029 - Workbench Withdraw Preview Version Identity Contract`。PF-P029 只让 withdraw preview response 暴露 `active_relation` identity/version 和 `submit_expected_versions`，优先转绿 `test_withdraw_preview_exposes_relation_identity_and_version_for_submit_expected_versions`；仍不得迁移 withdraw submit、cancel link、ignore row 或 cash special 真实写 API。

### PF-P029 - Workbench Withdraw Preview Version Identity Contract

状态：`verified`

#### 范围

- 只处理 withdraw preview response contract。
- 让 `/api/workbench/actions/withdraw-link/preview` 返回稳定的 `active_relation` identity/version 和 `submit_expected_versions`。
- 优先让 `tests/test_workbench_stale_write_contract.py::WorkbenchStaleWriteContractTests::test_withdraw_preview_exposes_relation_identity_and_version_for_submit_expected_versions` 从 expectedFailure 转为普通通过。
- 可以在 `workbench_write_facade.py` 中新增小型 helper，用于构造 withdraw preview 的 active relation identity/version。
- 更新本文档和 `refactor-prompts.md`。

#### 禁止范围

- 不迁移 withdraw submit。
- 不修改 cancel link、ignore row 或 cash special 写路径。
- 不实现 stale precondition / optimistic locking enforcement。
- 不修改 `WorkbenchWriteUnitOfWork.run()` 语义。
- 不新增 repository current-state reader。
- 不新增 SQL migration。
- 不修改前端。
- 不执行 Merge Gate、Traffic Gate、部署、merge 或 push。

#### 验收标准

- withdraw preview response 包含 `active_relation.case_id`。
- withdraw preview response 包含 integer `active_relation.version`。
- withdraw preview response 包含 `submit_expected_versions = {"relation:<case_id>": <version>}`。
- 只移除 `test_withdraw_preview_exposes_relation_identity_and_version_for_submit_expected_versions` 的 expectedFailure；UoW stale write expectedFailure 必须继续保留。
- 真实 withdraw submit 仍保持当前兼容行为：携带 `expected_versions` 不破坏成功响应，但不会执行 stale rejection。

#### 审查结论

- PF-P029 是 PF-P028 后的正确最小实现切片。
- 它只补齐两阶段 withdraw 的 preview response contract，为后续 submit stale guard 提供前端可回传的版本身份。
- PF-P029 不能修真实 stale write，因为 submit 拒绝 stale 需要 transaction-bound facts current-state reader 和 UoW precondition，应放到后续 prompt。

#### 执行结果

- 修改 `WorkbenchWriteFacade.preview_withdraw_link()`，withdraw preview response 新增：
  - `active_relation.case_id`
  - `active_relation.version`
  - `submit_expected_versions`
- 新增 `_withdraw_preview_active_relation_identity()` helper。
- 当前 pair relation facts 尚未提供 durable facts-level version，因此 helper 在缺少 relation `version` 时返回兼容期 preview-only integer token `1`。
- 已在 `workbench-stale-write-boundary-plan.md` 记录：PF-P029 的 preview-only token 只建立前端 submit contract，不能作为最终 optimistic locking 事实源。
- 只移除了 `test_withdraw_preview_exposes_relation_identity_and_version_for_submit_expected_versions` 的 `unittest.expectedFailure`。
- 未迁移 withdraw submit。
- 未修改 cancel link、ignore row 或 cash special 写路径。
- 未实现 UoW stale precondition、repository current-state reader 或 SQL migration。

#### 变更文件

- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_workbench_stale_write_contract.py`
- `docs/architecture/backend-refactor/workbench-stale-write-boundary-plan.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract.WorkbenchStaleWriteContractTests.test_withdraw_preview_exposes_relation_identity_and_version_for_submit_expected_versions -v`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests，4 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，29 tests。
- `git diff --check`：通过。
- `test ! -e backend-go`：通过。
- Scope allowlist：通过。

#### 仍保留的 expectedFailure

- `tests/test_workbench_uow_contract.py`
  - `test_withdraw_submit_rejects_stale_preview_relation_version`
  - `test_cancel_link_rejects_stale_replaced_relation`
  - `test_ignore_row_rejects_when_row_already_confirmed`
  - `test_cash_special_rejects_changed_relation_version`

#### 下一条 Prompt 上下文

PF-P029 已由用户确认 `verified`。PF-P030 已生成并审查，下一步只允许执行 `PF-P030 - Workbench UoW Stale Precondition Port Skeleton`。PF-P030 只建立 fake/in-memory stale precondition port 和 UoW target contract，不迁移真实 Workbench 写 API。PF-P030 必须继续保留真实 submit/cancel/ignore/cash special 当前行为 characterization，直到对应 API migration prompt。

### PF-P030 - Workbench UoW Stale Precondition Port Skeleton

状态：`verified`

#### 范围

- 只建立 Workbench UoW 层 stale precondition port skeleton。
- 使用 fake/in-memory current-state provider 或 command-carried target state 验证 UoW contract。
- 目标是把 `tests/test_workbench_uow_contract.py` 中 4 个 stale write target expectedFailure 转为普通通过。
- 只验证 UoW 在 handler 执行前拒绝 stale write，并抛出 `WorkbenchWriteConflict`。
- 更新本文档和 `refactor-prompts.md`。

#### 禁止范围

- 不迁移任何真实 Workbench 写 API。
- 不修改 `server.py`。
- 不修改 `workbench_write_facade.py`。
- 不读取或写入 PostgreSQL facts。
- 不新增 repository current-state reader 的真实数据库实现。
- 不新增 SQL migration。
- 不改变 Workbench HTTP response shape。
- 不修改前端。
- 不执行 Merge Gate、Traffic Gate、部署、merge 或 push。

#### 验收标准

- `WorkbenchWriteUnitOfWork.run()` 在 handler 前执行 stale precondition 检查。
- fake/in-memory precondition source 能表达 relation version mismatch、relation replaced、row already confirmed、cash special relation changed。
- stale precondition 失败时抛出 `WorkbenchWriteConflict`，且 handler 不执行、dirty/outbox 不写入、idempotency 不 commit。
- `tests/test_workbench_uow_contract.py` 中 4 个 stale write tests 转为普通通过。
- 真实 Workbench 写 API 当前行为 characterization 必须继续通过，证明没有迁移真实 API。

#### 审查结论

- PF-P030 是 PF-P029 后的正确最小 UoW 层切片。
- 它只建立 UoW target contract 和 fake/in-memory port，为后续真实 repository current-state reader 做接口准备。
- PF-P030 仍不能迁移真实 submit/cancel/ignore/cash special，因为真实迁移需要对应 API prompt、facts reader、兼容策略和回归门禁。

#### 执行结果

- 新增 `backend/src/fin_ops_platform/services/workbench_stale_precondition.py`。
- `WorkbenchWriteUnitOfWork.run()` 在 transaction 内、handler 执行前调用 `assert_workbench_stale_preconditions(command)`。
- stale precondition 当前只使用 fake/in-memory command state：
  - `command.expected_versions`
  - `command.payload.current_relation_case_id`
  - `command.payload.current_relation_version`
  - `command.payload.current_row_status`
- 支持并验证：
  - relation version mismatch -> `stale_relation_version`
  - relation identity changed -> `stale_relation_identity`
  - row status changed -> `stale_row_status`
- stale 时抛出 `WorkbenchWriteConflict`，handler 不执行；withdraw stale target test 同时断言 dirty/outbox 不写、idempotency 不 reserve/commit、transaction rollback。
- 未迁移任何真实 Workbench 写 API。
- 未修改 `server.py` 或 `workbench_write_facade.py`。
- 未实现真实 PostgreSQL facts current-state reader 或 SQL migration。

#### 变更文件

- `backend/src/fin_ops_platform/services/workbench_stale_precondition.py`
- `backend/src/fin_ops_platform/services/workbench_uow.py`
- `tests/test_workbench_uow_contract.py`
- `docs/architecture/backend-refactor/workbench-stale-write-boundary-plan.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`

#### 验证

- Baseline：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：初始为 16 tests，4 expected failures。
- RED：移除 4 个 expectedFailure 后，4 个 stale tests 均因未抛出异常失败。
- GREEN：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，29 tests。
- `git diff --check`：通过。
- `test ! -e backend-go`：通过。
- Scope allowlist：通过。

#### 仍保留的限制

- 当前 stale precondition source 不是 PostgreSQL facts reader。
- 真实 submit/cancel/ignore/cash special HTTP 写路径尚未迁移进 UoW stale precondition。
- PF-P030 只证明 UoW target contract 可行，不能视为生产 stale write 已修复。

#### 下一条 Prompt 上下文

PF-P030 已由用户确认 `verified`。PF-P030-MG 已生成并审查，下一步只允许执行 `PF-P030-MG - Workbench Stale Write Foundation Merge Gate`。PF-P030-MG 统一覆盖 PF-P027、PF-P028、PF-P029、PF-P030 在当前分支上的完整 diff；不得直接进入真实 API migration，也不得跳过 Merge Gate。

### PF-P030-MG - Workbench Stale Write Foundation Merge Gate

状态：`verified`

#### 范围

- 只处理当前分支 `codex/workbench-stale-write-planning` 的 Merge Gate。
- 统一覆盖 PF-P027、PF-P028、PF-P029、PF-P030 的完整 diff。
- 检查 stale write foundation 是否满足合入 main 的生产级门禁。
- 如验证通过，允许 commit 当前 MG 文档变更并按用户确认执行 merge 到 `main`。

#### 禁止范围

- 不进入真实 Workbench API migration。
- 不生成或执行 PF-P031。
- 不修改业务逻辑、测试逻辑或 SQL migration。
- 不执行 Traffic Gate、部署、生产访问或服务器操作。
- 不默认 push；push 必须等用户确认。
- 不使用 `git add .` 或 `git add -A`。

#### 验收标准

- 当前分支包含最新 `main`。
- Diff scope 只包含 PF-P027 到 PF-P030 允许的 stale write foundation 文件。
- 没有 `backend-go`。
- 没有临时文件、`.pkl`、`.sqlite`、`__pycache__` 或 untracked 脏文件混入。
- 指定 Workbench stale/UoW/idempotency/write characterization 测试全部通过。
- 合入 main 后必须在 main 上重跑同一套验证。
- 合入后仍不代表生产 Traffic Gate 或真实 API migration 完成。

#### 审查结论

- PF-P030-MG 是当前分支进入下一个真实 API migration 前的必要门禁。
- 该分支已经包含 production code 变更，因此 commit message 应使用 `feat(workbench): ...` 或等价语义，不能使用纯 docs 前缀描述整个合入。
- 没有 staging 环境不阻塞本 Merge Gate，因为本分支没有切换流量、没有部署拓扑变更、没有网关或 auth/session 变更。

#### 执行结果

- 已合入本地 `main`。
- Merge commit：`3f4c3927 feat(workbench): establish stale write foundation`。
- 合入覆盖 PF-P027、PF-P028、PF-P029、PF-P030 的完整 stale write foundation diff。
- 未 push。
- 未执行 Traffic Gate、部署、生产访问或服务器操作。
- 未迁移真实 Workbench 写 API。
- 未修改 `backend/src/fin_ops_platform/app/server.py`。
- 未新增 SQL migration。
- 未修改前端、部署、网关、auth/session 或 worker routing。
- 没有 `backend-go`。

#### 合入前验证

- `git status --short --branch`：当前分支干净。
- `git rev-list --left-right --count main...origin/main`：`0 0`。
- `git ls-files --others --exclude-standard`：无输出。
- `git diff --name-only`：无输出。
- `git diff --name-only main...HEAD`：只包含 PF-P027 到 PF-P030 允许的 stale write foundation 文件。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，29 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。

#### Main 上复验

- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，29 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。

#### 下一条 Prompt 上下文

PF-P030-MG 已合入本地 `main` 并完成 main 上复验，且已由用户确认 `verified`。`git push origin main` 已完成，`main` 与 `origin/main` 对齐。下一步必须从最新 `main` 新建分支，再生成并审查 `PF-P031 - Workbench Cancel Link Stale Guard Migration`。真实 Workbench API migration 仍未开始；PF-P031 是第一条真实写 API stale guard 迁移候选，生成后仍需单独审查，不得直接执行。

### PF-P031 - Workbench Cancel Link Stale Guard Migration

状态：`verified`

#### 范围

- 只迁移 Workbench `cancel link` 的 stale guard。
- 目标：当请求携带 `expected_versions` 且当前 row active relation 已从用户预期 relation 替换为其它 relation 时，返回 `409 workbench_write_conflict`，并且不得取消新的 active relation。
- 保持未携带 `expected_versions` 的 legacy cancel link 行为不变。
- 复用 PF-P028/PF-P030 已建立的 `WorkbenchWriteConflict` 和 stale precondition primitive。

#### 禁止范围

- 不迁移 `ignore row`。
- 不迁移 `cash special`。
- 不迁移 `withdraw submit`。
- 不修改前端、SQL migration、部署、网关、auth/session 或 worker routing。
- 不执行 Traffic Gate、部署、生产访问或 push。
- 不生成或执行 PF-P032。

#### 验收标准

- 先写或补充针对真实 HTTP/facade cancel link 行为的测试，再实现。
- 新增测试必须覆盖 stale expected relation identity 返回 409 且不取消当前 active relation。
- 现有 duplicate cancel/current behavior characterization 仍通过，除非 prompt 内明确将其拆成 legacy/no-expected-versions 与 guarded/expected-versions 两种行为。
- 指定 Workbench write characterization、UoW contract、stale write contract、idempotency contract 和 platform runtime guard 测试通过。

#### 审查结论

- PF-P031 是 PF-P030-MG 后的正确下一步，因为 stale write 计划把 cancel link 列为第一条真实写 API 迁移候选。
- PF-P031 必须保持小切片，只处理 cancel link；其它 stale write 写路径留给后续 PF-P032/PF-P033/PF-P034。
- 当前分支已从最新 `main` 创建：`codex/workbench-cancel-link-stale-guard`。

#### 执行结果

- 已实现 cancel link stale guard。
- 当 `cancel-link` 请求携带 `expected_versions` 且当前 row active relation 已从 expected relation 替换为其它 relation 时，返回 `409 workbench_write_conflict`。
- stale guard 在 mutation 前执行；冲突时不会调用 `cancel_relation_for_row_id` 取消当前新 relation。
- 未携带 `expected_versions` 的 legacy cancel link 行为保持不变。
- 未迁移 `ignore row`、`cash special` 或 `withdraw submit`。
- 未修改 `server.py`、前端、SQL migration、部署、网关、auth/session 或 worker routing。
- 未执行 Traffic Gate、部署、生产访问或 push。

#### 变更文件

- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_workbench_write_characterization.py`
- `docs/architecture/backend-refactor/workbench-stale-write-boundary-plan.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`

#### RED/GREEN 记录

- RED：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_cancel_link_with_expected_relation_rejects_replaced_active_relation -v` 失败，当前代码返回 200 并取消 `CASE-CANCEL-NEW`。
- GREEN：同一测试通过，返回 409 且 `CASE-CANCEL-NEW` 保持 active。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，30 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。

#### 下一条 Prompt 上下文

PF-P031 已完成实现和验证，并已由用户确认 `verified`。PF-P031-MG 已生成并审查，下一步只允许执行 `PF-P031-MG - Workbench Cancel Link Stale Guard Merge Gate`。不要直接进入 PF-P032，不要迁移 ignore row、cash special 或 withdraw submit。

### PF-P031-MG - Workbench Cancel Link Stale Guard Merge Gate

状态：`verified`

#### 范围

- 只处理当前分支 `codex/workbench-cancel-link-stale-guard` 的 Merge Gate。
- 统一覆盖 PF-P031 prompt 规划提交和 cancel link stale guard 实现提交。
- 检查本分支是否可以合入 `main`。
- 如验证通过，允许合入本地 `main` 并在 `main` 上复验。

#### 禁止范围

- 不进入 PF-P032。
- 不迁移 `ignore row`、`cash special` 或 `withdraw submit`。
- 不修改前端、SQL migration、部署、网关、auth/session 或 worker routing。
- 不执行 Traffic Gate、部署、生产访问或服务器操作。
- 不默认 push；push 必须等用户确认。
- 不使用 `git add .` 或 `git add -A`。

#### 验收标准

- 当前分支包含最新 `main`。
- Diff scope 只包含 PF-P031 允许文件：
  - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
  - `tests/test_workbench_write_characterization.py`
  - `docs/architecture/backend-refactor/workbench-stale-write-boundary-plan.md`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
- 没有 `backend-go`。
- 没有 untracked 临时文件、`.pkl`、`.sqlite`、`__pycache__` 或真实业务样本混入。
- PF-P031 指定测试在合入前和合入后的 `main` 上全部通过。
- 合入后仍不代表 Traffic Gate、部署或下一条真实写 API 迁移完成。

#### 审查结论

- PF-P031-MG 是当前分支的正确下一步：PF-P031 已形成一个可合并的小切片。
- 本 MG 不应扩大实现范围，不应进入 PF-P032。
- 本分支没有部署拓扑、网关、auth/session、worker routing 或前端变更，因此不需要 Traffic Gate。

#### 执行结果

- 已合入本地 `main`。
- Merge commit：`e81bd551 feat(workbench): merge cancel link stale guard`。
- 合入覆盖 PF-P031 prompt 规划提交和 cancel link stale guard 实现提交。
- 未 push。
- 未执行 Traffic Gate、部署、生产访问或服务器操作。
- 未进入 PF-P032。
- 未迁移 `ignore row`、`cash special` 或 `withdraw submit`。
- 未修改前端、SQL migration、部署、网关、auth/session 或 worker routing。
- 没有 `backend-go`。

#### 合入前验证

- `git status --short --branch`：当前分支干净。
- `git rev-list --left-right --count main...origin/main`：`0 0`。
- `git ls-files --others --exclude-standard`：无输出。
- `git diff --name-only`：无输出。
- `git diff --name-only main...HEAD`：只包含 PF-P031 允许文件。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，30 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。

#### Main 上复验

- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，30 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。

#### 下一条 Prompt 上下文

PF-P031-MG 已合入本地 `main` 并完成 main 上复验，且已由用户确认 `verified`。`git push origin main` 已完成，`main` 与 `origin/main` 对齐。下一步必须从最新 `main` 新建分支，再生成并审查 `PF-P032 - Workbench Ignore Row Stale Guard Migration`。PF-P032 应只迁移 ignore row stale guard，不得顺手迁移 cash special 或 withdraw submit；生成后仍需单独审查，不得直接执行。

### PF-P032 - Workbench Ignore Row Stale Guard Migration

状态：`verified`

#### 范围

- 只迁移 Workbench `ignore row` 的 stale guard。
- 目标：当请求携带 `expected_versions` 且 invoice row 已不再处于可忽略的 open/unpaired 状态时，返回 `409 workbench_write_conflict`，并且不得创建 ignored case 或 override。
- 保持未携带 `expected_versions` 的 legacy ignore row 行为不变。
- 复用 PF-P028/PF-P030/PF-P031 已建立的 `WorkbenchWriteConflict`、stale precondition primitive 和 Workbench write facade 约束。

#### 禁止范围

- 不迁移 `cash special`。
- 不迁移 `withdraw submit`。
- 不修改前端、SQL migration、部署、网关、auth/session 或 worker routing。
- 不执行 Traffic Gate、部署、生产访问或 push。
- 不生成或执行 PF-P033。

#### 验收标准

- 先写或补充针对真实 HTTP/facade ignore row 行为的测试，再实现。
- 新增测试必须覆盖 stale expected row open 返回 409 且不创建 ignored case / override。
- 现有 legacy no-expected-versions ignore behavior characterization 仍通过，除非 prompt 内明确拆分 guarded 与 legacy 行为。
- 指定 Workbench write characterization、UoW contract、stale write contract、idempotency contract 和 platform runtime guard 测试通过。

#### 审查结论

- PF-P032 是 PF-P031-MG 后的正确下一步，因为 stale write 计划把 ignore row 列为 cancel link 后的下一条真实写 API 迁移候选。
- PF-P032 必须保持小切片，只处理 ignore row；cash special 和 withdraw submit 留给后续 prompt。
- 当前分支已从最新 `main` 创建：`codex/workbench-ignore-row-stale-guard`。

#### 变更文件

- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_workbench_write_characterization.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-stale-write-boundary-plan.md`

#### 执行结果

- RED：新增 `test_ignore_row_with_expected_open_rejects_confirmed_row` 后，当前实现返回 200 并创建 ignored case/override，测试失败。
- GREEN：`WorkbenchWriteFacade.ignore_row` 在携带 `expected_versions` 时复用 stale precondition primitive，发现当前 invoice row 已有 active relation 时返回 `409 workbench_write_conflict`，并在 mutation 前退出。
- Legacy no-expected-versions ignore row characterization 保持不变。
- 未迁移 `cash special`。
- 未迁移 `withdraw submit`。
- 未修改 `server.py`、前端、SQL migration、部署、网关、auth/session 或 worker routing。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，31 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。

#### 下一条 Prompt 上下文

PF-P032 已完成实现和验证，并已由用户确认 `verified`。PF-P032-MG 不单独执行，明确延后到累计 Merge Gate：`PF-P032-MG deferred; cumulative MG will cover PF-P032 through PF-P034`。下一步允许继续在当前功能分支生成并执行 PF-P033；PF-P033 只迁移 `cash special` stale guard，不得迁移 `withdraw submit`。

### PF-P033 - Workbench Cash Special Stale Guard Migration

状态：`verified`

#### 范围

- 只迁移 Workbench cash special stale guard。
- 覆盖三个真实写入口：
  - `confirm-cash-pass-through`
  - `confirm-cash-ticket-purchase`
  - `cancel-cash-special`
- 目标：当请求携带 `expected_versions` 且当前 active relation identity/version 不再匹配用户看到的 relation 时，返回 `409 workbench_write_conflict`，并且不得更新或清空 `special_metadata`。
- 保持未携带 `expected_versions` 的 legacy cash special 行为不变。
- 复用 PF-P028/PF-P030/PF-P031/PF-P032 已建立的 `WorkbenchWriteConflict`、stale precondition primitive 和 Workbench write facade 约束。

#### 禁止范围

- 不迁移 `withdraw submit`。
- 不修改 `ignore row` 或 `cancel link` 已完成 guard 的语义。
- 不修改前端、SQL migration、部署、网关、auth/session 或 worker routing。
- 不执行 Traffic Gate、部署、生产访问或 push。
- 不生成或执行 PF-P034。

#### 验收标准

- 先写或补充针对真实 HTTP/facade cash special 行为的测试，再实现。
- 新增测试必须覆盖 stale expected relation 返回 409 且不更新 / 不清空 special metadata。
- 三个 cash special 入口必须共享同一 stale guard 语义，避免三个入口各写一套冲突判断。
- 现有 legacy no-expected-versions cash special characterization 仍通过。
- 指定 Workbench write characterization、UoW contract、stale write contract、idempotency contract 和 platform runtime guard 测试通过。

#### 审查结论

- PF-P033 是 PF-P032 verified 后的正确下一步，因为 stale write 计划把 cash special 放在 ignore row 之后、withdraw submit 之前。
- PF-P033 必须保持小切片，只处理 cash special 三个入口；withdraw submit 留给 PF-P034。
- 当前系统没有明确 durable relation version 字段时，本轮必须先完成 relation identity guard；如代码中可读取当前 relation version，则同时校验 version。不得伪造版本字段或新增 SQL migration。
- PF-P032-MG 已明确延后，最终累计 MG 必须覆盖 PF-P032 到 PF-P034 的完整 diff。

#### 变更文件

- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_workbench_write_characterization.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-stale-write-boundary-plan.md`

#### 执行结果

- RED：新增 `test_cash_special_with_stale_expected_relation_rejects_all_entrypoints` 后，三个 cash special 入口都会返回 200，并更新或清空当前 active relation 的 `special_metadata`。
- GREEN：`confirm_cash_pass_through`、`confirm_cash_ticket_purchase`、`cancel_cash_special` 在携带 `expected_versions` 时复用同一个 `_cash_special_stale_conflict` helper；当前 active relation identity 不匹配时返回 `409 workbench_write_conflict`，并在 metadata mutation 前退出。
- Legacy no-expected-versions cash special characterization 保持不变。
- 未迁移 `withdraw submit`。
- 未修改 `server.py`、前端、SQL migration、部署、网关、auth/session 或 worker routing。
- PF-P032-MG 仍然 deferred；累计 MG 将覆盖 PF-P032 到 PF-P034。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，32 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。

#### 下一条 Prompt 上下文

PF-P033 已完成实现和验证，并已由用户确认 `verified`。PF-P032-MG 和 PF-P033-MG 均不单独执行，继续延后到累计 Merge Gate；最终累计 MG 必须覆盖 PF-P032 到 PF-P034 的完整 diff。下一步允许执行 PF-P034；PF-P034 只迁移 `withdraw submit` stale guard，不得扩大到其它 Workbench 写路径。

### PF-P034 - Workbench Withdraw Submit Stale Guard Migration

状态：`verified`

#### 范围

- 只迁移 Workbench `withdraw submit` stale guard。
- 覆盖真实写入口：
  - `POST /api/workbench/actions/withdraw-link`
  - `WorkbenchWriteFacade.withdraw_link`
- 目标：当 submit 请求携带 `expected_versions`，且当前 active relation identity/version 不再匹配 preview 时暴露的 relation 时，返回 `409 workbench_write_conflict`，并且不得撤销当前 relation、不得恢复历史 relation、不得触发本次 pair relation persist 或 read-model scheduling。
- 保持未携带 `expected_versions` 的 legacy withdraw 行为不变。
- 复用 PF-P028/PF-P029/PF-P030/PF-P031/PF-P032/PF-P033 已建立的 `WorkbenchWriteConflict`、preview `submit_expected_versions`、stale precondition primitive 和 Workbench write facade 约束。

#### 禁止范围

- 不修改 `cancel link`、`ignore row` 或 `cash special` 已完成 guard 的语义。
- 不修改 withdraw preview response shape，除非发现 submit 无法使用现有 `submit_expected_versions`，且必须解释原因。
- 不修改前端、SQL migration、部署、网关、auth/session 或 worker routing。
- 不执行 Traffic Gate、部署、生产访问或 push。
- 不生成或执行累计 MG。
- 不迁移其它 Workbench 写路径。

#### 验收标准

- 先写或补充针对真实 HTTP/facade withdraw submit 行为的测试，再实现。
- 新增测试必须覆盖 stale preview submit 返回 409 且不撤销当前 relation / 不恢复旧 relation。
- 现有 legacy no-expected-versions withdraw characterization 仍通过。
- `test_withdraw_submit_accepts_expected_versions_payload_without_breaking_existing_success_shape` 这类 expected_versions 正常匹配路径仍通过。
- 指定 Workbench write characterization、UoW contract、stale write contract、idempotency contract 和 platform runtime guard 测试通过。

#### 审查结论

- PF-P034 是 PF-P033 verified 后的正确下一步，因为 withdraw submit 是 Workbench stale guard group 中最后且风险最高的真实写 API。
- PF-P034 必须保持小切片，只处理 withdraw submit；不得顺手修改其它 Workbench 写路径。
- 当前 preview 使用兼容性 `version=1` 暴露 submit contract；PF-P034 应优先完成 relation identity guard。如当前 relation 可读取真实 version，则同时校验 version；不得伪造 PostgreSQL 版本字段或新增 SQL migration。
- PF-P034 完成后应生成累计 Merge Gate，统一覆盖 PF-P032 到 PF-P034 的完整 diff。

#### 变更文件

- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_workbench_write_characterization.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-stale-write-boundary-plan.md`

#### 执行结果

- RED：新增 `test_withdraw_submit_with_stale_preview_expected_versions_rejects_replacement_relation` 后，旧 preview 的 submit 返回 200，并撤销 replacement relation 后恢复旧 relation。
- GREEN：`WorkbenchWriteFacade.withdraw_link` 在携带 `expected_versions` 时复用 `_withdraw_link_stale_conflict` helper；当前 active relation identity 不匹配时返回 `409 workbench_write_conflict`，并在 `withdraw_latest_for_row_ids` 前退出。
- Legacy no-expected-versions withdraw characterization 保持不变。
- Preview `submit_expected_versions` 契约保持不变。
- 未修改 `cancel link`、`ignore row` 或 `cash special` 已完成 guard 的语义。
- 未修改 `server.py`、前端、SQL migration、部署、网关、auth/session 或 worker routing。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，33 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。

#### 下一条 Prompt 上下文

PF-P034 已完成实现和验证，并已由用户确认 `verified`。下一步应执行 `PF-P034-MG - Workbench Stale Guard Group Merge Gate`，统一覆盖 PF-P032 ignore row、PF-P033 cash special、PF-P034 withdraw submit 的完整 diff；不得执行 Traffic Gate、部署或 push。

### PF-P034-MG - Workbench Stale Guard Group Merge Gate

状态：`verified`

#### 范围

- 累计验证 PF-P032 到 PF-P034 的完整 diff。
- 覆盖提交：
  - `353a30a7 docs(backend-refactor): plan workbench ignore row stale guard`
  - `6fbe97e5 feat(workbench): reject stale ignore row writes`
  - `af61744b docs(backend-refactor): plan workbench cash special stale guard`
  - `adc438b3 feat(workbench): reject stale cash special writes`
  - `a04231c9 docs(backend-refactor): plan workbench withdraw submit stale guard`
  - `f4b7029d feat(workbench): reject stale withdraw submit`
- 只允许 Workbench stale guard group 相关变更：
  - ignore row stale guard
  - cash special stale guard
  - withdraw submit stale guard
  - 对应 characterization tests
  - 对应状态机 / prompt 库 / stale-write 计划文档

#### 预期变更文件

- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_workbench_write_characterization.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-stale-write-boundary-plan.md`

#### 禁止范围

- 不修改 `server.py`。
- 不修改前端。
- 不新增 SQL migration。
- 不修改部署、网关、auth/session 或 worker routing。
- 不引入 Go / `backend-go`。
- 不执行 Traffic Gate、部署、生产访问或 push。
- 不开始 PF-P035 或其它 Workbench 写路径迁移。

#### 验收标准

- 确认 PF-P032、PF-P033、PF-P034 均已 verified。
- 确认相对 `main` 的 diff 只包含预期 5 个文件。
- 完整验证目标测试全部通过。
- 如果合入本地 `main`，必须先同步最新 `main`，解决冲突后重跑同一套验证。
- 未经用户确认，不得把 PF-P034-MG 标记为 `verified`。

#### 审查结论

- PF-P034-MG 是正确的下一步，因为 Workbench stale guard group 的三条真实写 API 小切片已全部实现并 verified。
- MG 应统一覆盖 PF-P032 到 PF-P034，而不是只检查最后一个 prompt。
- 本 MG 只做 Merge Gate，不是 Traffic Gate，不等于上线，不应 push 远端或生产服务器。

#### 执行结果

- 执行分支：`codex/workbench-ignore-row-stale-guard`。
- 合入目标：本地 `main`。
- 远端基线：合入前 `main...origin/main` 为 `0 0`。
- 分支提交范围：PF-P032/PF-P033/PF-P034 实现与文档提交，加上 `1802761e docs(backend-refactor): plan workbench stale guard merge gate` 作为本 MG 的 prompt 文档提交。
- 实际变更文件：
  - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
  - `tests/test_workbench_write_characterization.py`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
  - `docs/architecture/backend-refactor/workbench-stale-write-boundary-plan.md`
- Scope / hygiene：
  - `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
  - `git diff --check`：Pass。
  - `test ! -e backend-go`：Pass。
  - 未修改 `server.py`、前端、SQL migration、部署、网关、auth/session 或 worker routing。
- 功能分支验证：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，33 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- 本地 `main` 合入复验：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，33 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- 已执行本地 merge：`git merge --no-ff codex/workbench-ignore-row-stale-guard`。
- 用户确认：PF-P034-MG verified。
- 未执行：Traffic Gate、部署、生产访问。

#### 下一条 Prompt 上下文

PF-P034-MG 已完成本地 merge gate、合入本地 `main`，已由用户确认 `verified`，并已同步到 `origin/main`。后续 prompt 必须从最新 `main` 新建分支生成，不得直接在 `main` 上实现。

### PF-P035 - Workbench Confirm Link UoW Integration Slice

状态：`verified`

#### 范围

- 从最新 `main` 新建分支：`codex/workbench-confirm-link-uow`。
- 只迁移 `POST /api/workbench/actions/confirm-link` / `WorkbenchWriteFacade.confirm_link` 到 `WorkbenchWriteUnitOfWork`。
- 必须保持旧前端未携带 `idempotency_key` / `expected_versions` 时的 response shape 与 characterization 行为。
- 必须先补/调整测试，再实现。
- 如果真实 PostgreSQL repository 或 transaction-bound facts writer 不足以安全完成 `confirm-link` UoW 集成，必须停止并记录 blocker，不得扩大到其它 API 或伪造事务保证。

#### 预期读取文件

- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-uow-integration-plan.md`
- `docs/architecture/backend-refactor/workbench-write-uow-boundary-design.md`
- `docs/architecture/backend-refactor/workbench-writes-and-matching-plan.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/services/workbench_uow.py`
- `backend/src/fin_ops_platform/services/workbench_idempotency.py`
- `backend/src/fin_ops_platform/services/workbench_stale_precondition.py`
- `backend/src/fin_ops_platform/services/workbench_write_conflict.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `backend/src/fin_ops_platform/services/runtime_queue.py`
- `tests/test_workbench_write_characterization.py`
- `tests/test_workbench_uow_contract.py`
- `tests/test_workbench_idempotency_contract.py`
- `tests/test_workbench_stale_write_contract.py`
- `tests/test_platform_runtime_boundary_guards.py`

#### 审查结论

- PF-P035 是 PF-P034-MG 后的合理下一步，因为 `confirm-link` 是 Workbench 写路径的核心入口，也是 UoW 目标矩阵中的第一批迁移对象。
- 本 prompt 必须小切片推进，不得顺手迁移 `cancel-link`、exception、ignore/unignore、cash special、withdraw、personal advance repayment 或 matching/candidates。
- 该 prompt 是实现 prompt，不是 Merge Gate；完成后只能标记 `implemented`，等待用户确认后再决定是否生成对应 MG。

#### 执行结果

- 状态：`implemented`，等待用户确认后才可标记 `verified`。
- 完成范围：
  - `WorkbenchWriteFacade.confirm_link` 在通过现有 validation、row expansion 和 amount check 后接入 `WorkbenchWriteUnitOfWork`。
  - `Application._workbench_write_facade()` 只负责组装细粒度依赖，新增 confirm-link UoW factory、transaction-bound pair relation persistence、transaction-bound reconciliation decision consumption。
  - `RuntimeQueueReadModelRefreshWriter` 将 UoW dirty/outbox/source_version 写入代理到 `RuntimeQueueRepository.enqueue_read_model_refresh_in_transaction()`。
  - legacy 非 PostgreSQL / 无 UoW 环境仍保留原 confirm-link response shape 与 legacy 调度行为。
- 变更文件：
  - `backend/src/fin_ops_platform/app/server.py`
  - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
  - `backend/src/fin_ops_platform/services/workbench_uow.py`
  - `tests/test_workbench_write_characterization.py`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
  - `docs/architecture/backend-refactor/workbench-uow-integration-plan.md`
  - `docs/architecture/backend-refactor/workbench-write-uow-boundary-design.md`
- 验证结果：
  - `git status --short --branch`：Pass，当前分支 `codex/workbench-confirm-link-uow`，仅本轮文件变更。
  - `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
  - `git diff --check`：Pass。
  - `test ! -e backend-go`：Pass。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，36 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- 剩余风险：
  - confirm-link 的 idempotency 仍依赖当前 `InMemoryWorkbenchIdempotencyRepository` primitive；真实 PostgreSQL durable idempotency store / SQL migration 仍未实现。
  - actor/tenant 仍使用现有默认值；后续需要接入真实 auth context 后再提升到生产级审计身份。
  - 本轮没有迁移 cancel-link、exception、ignore/unignore、cash special、withdraw 或其它 Workbench 写路径。
- 下一条 Prompt 上下文：
  - 用户已确认 PF-P035 verified。
  - PF-P035-MG 已延后：`PF-P035-MG deferred; cumulative MG will cover PF-P035 through PF-P036`。
  - 当前允许生成并执行 PF-P036；PF-P036 只迁移 `cancel-link` 到 UoW，不得迁移其它 Workbench 写路径。

### PF-P036 - Workbench Cancel Link UoW Integration Slice

状态：`verified`

#### 范围

- 继续使用当前分支：`codex/workbench-confirm-link-uow`。
- PF-P035-MG 已延后，累计 MG 当前计划覆盖 PF-P035 到 PF-P036 的完整 diff。
- 只迁移 `POST /api/workbench/actions/cancel-link` / `WorkbenchWriteFacade.cancel_link` 到 `WorkbenchWriteUnitOfWork`。
- 必须保留 PF-P031/PF-P032/PF-P033/PF-P034 已完成的 stale guard 行为，尤其是 cancel-link expected relation conflict。
- 不得迁移 exception、ignore/unignore、cash special、withdraw、personal advance repayment、query/read-model 或 matching/candidates。

#### 预期读取文件

- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-uow-integration-plan.md`
- `docs/architecture/backend-refactor/workbench-write-uow-boundary-design.md`
- `docs/architecture/backend-refactor/workbench-stale-write-boundary-plan.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/services/workbench_uow.py`
- `backend/src/fin_ops_platform/services/workbench_idempotency.py`
- `backend/src/fin_ops_platform/services/workbench_stale_precondition.py`
- `backend/src/fin_ops_platform/services/workbench_write_conflict.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `tests/test_workbench_write_characterization.py`
- `tests/test_workbench_uow_contract.py`
- `tests/test_workbench_idempotency_contract.py`
- `tests/test_workbench_stale_write_contract.py`
- `tests/test_platform_runtime_boundary_guards.py`

#### 审查结论

- PF-P036 是 PF-P035 后合理的小批次延续，因为 `confirm-link` 与 `cancel-link` 都属于 pair relation facts/history 写路径，适合由同一个累计 MG 覆盖。
- PF-P036 必须复用 PF-P035 建立的 UoW 组装模式和 transaction-bound persistence，不得引入新的上帝对象依赖。
- PF-P036 完成后仍不得直接合入 main；应等待用户确认后生成累计 MG，除非用户明确要求再追加一个紧密相关的小切片。

#### 执行结果

- 状态：`verified`，用户已确认 PF-P036 可落锁。
- 完成范围：
  - `WorkbenchWriteFacade.cancel_link` 在解析请求、读取 active relation、执行 stale expected relation guard 后接入 `WorkbenchWriteUnitOfWork`。
  - cancel-link 使用 transaction-bound pair relation persistence 和 UoW dirty/outbox/source_version writer。
  - `WorkbenchWriteUnitOfWork.replay_committed(command)` 支持在 relation lookup 前进行 idempotency replay/conflict probe，避免第二次 cancel 因 active relation 已不存在而退化为 404。
  - legacy 无 idempotency key 的 duplicate cancel 行为保持不变：第二次 cancel 仍返回 not found。
- 变更文件：
  - `backend/src/fin_ops_platform/app/server.py`
  - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
  - `backend/src/fin_ops_platform/services/workbench_uow.py`
  - `tests/test_workbench_write_characterization.py`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
  - `docs/architecture/backend-refactor/workbench-uow-integration-plan.md`
  - `docs/architecture/backend-refactor/workbench-write-uow-boundary-design.md`
- 验证结果：
  - `git status --short --branch`：Pass，当前分支 `codex/workbench-confirm-link-uow`，仅本轮文件变更。
  - `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
  - `git diff --check`：Pass。
  - `test ! -e backend-go`：Pass。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，41 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- 剩余风险：
  - cancel-link 的 idempotency 仍依赖当前 `InMemoryWorkbenchIdempotencyRepository` primitive；真实 PostgreSQL durable idempotency store / SQL migration 仍未实现。
  - actor/tenant 仍使用默认值，后续仍需接入真实 auth context。
  - 本轮没有迁移 exception、ignore/unignore、cash special、withdraw、personal advance repayment 或其它 Workbench 写路径。
- 下一条 Prompt 上下文：
  - PF-P035-MG 仍 deferred；累计 MG 当前计划覆盖 PF-P035 到 PF-P036。
  - `PF-P036-MG - Workbench Pair Relation UoW Cumulative Merge Gate` 已生成并审查。
  - 下一步只允许执行 PF-P036-MG；不得直接迁移下一条 Workbench 写 API。

### PF-P036-MG - Workbench Pair Relation UoW Cumulative Merge Gate

状态：`verified`

#### 范围

- 这是累计 Merge Gate，只覆盖 PF-P035 `confirm-link` UoW 和 PF-P036 `cancel-link` UoW 的完整 diff。
- 必须确认 PF-P035 和 PF-P036 均为 `verified`。
- 必须确认 PF-P035-MG 是 deferred，且本 MG 是该 deferred gate 的替代累计门禁。
- 允许合入的生产代码范围仅限 Workbench pair relation UoW integration：
  - `backend/src/fin_ops_platform/app/server.py`
  - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
  - `backend/src/fin_ops_platform/services/workbench_uow.py`
  - `tests/test_workbench_write_characterization.py`
- 允许合入的文档范围仅限本轮 prompt、状态机和 Workbench UoW 设计/执行结果文档。

#### 明确禁止

- 不迁移 exception、ignore/unignore、cash special、withdraw、personal advance repayment、matching/candidates、query/read-model 或其它 Workbench 写路径。
- 不新增 SQL migration，不新增 PostgreSQL durable idempotency repository。
- 不修改前端、网关、部署、auth/session、worker routing。
- 不执行 Traffic Gate、部署、生产访问或 `git push origin main`。
- 严禁把 untracked 临时文件、`.pkl`、`.sqlite`、`__pycache__`、测试输出或 `backend-go` 带入提交。
- 严禁使用 `git add .` 或 `git add -A`。

#### 验证门禁

PF-P036-MG 执行时必须先检查 branch/diff scope、untracked files 和 changed files 白名单，再在功能分支和本地 `main` 合入后分别执行 Workbench write characterization、UoW contract、idempotency contract、stale write contract 和 platform runtime guard 测试。

#### 审查结论

- PF-P035 与 PF-P036 同属 Workbench pair relation facts/history 写路径，使用累计 MG 合并是合理的。
- 当前仍存在生产级 idempotency 缺口：真实 PostgreSQL durable idempotency store 尚未实现。因此 MG 只能证明 pair relation UoW transaction boundary 进入 main，不代表 Workbench 写路径全部生产完成。
- PF-P036-MG 不应继续扩大业务范围。通过后用户确认 `verified`，再由用户决定是否 `git push origin main`。

#### 执行结果

- 状态：`verified`，用户已确认 PF-P036-MG 可落锁。
- 功能分支验证：
  - `git status --short --branch`：Pass，位于 `codex/workbench-confirm-link-uow`。
  - `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
  - `git diff --name-status main...HEAD`：Pass，只包含 PF-P035 到 PF-P036 预期的 8 个文件。
  - `git diff --check main...HEAD`：Pass。
  - `test ! -e backend-go`：Pass。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，41 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- Upstream sync：
  - `git fetch origin`：Pass。
  - `git checkout main`：Pass。
  - `git pull --ff-only origin main`：Pass，`Already up to date`。
  - `git merge-base --is-ancestor main codex/workbench-confirm-link-uow`：Pass，功能分支包含最新 main。
- 本地 main 合入：
  - `git merge --no-ff codex/workbench-confirm-link-uow -m "Merge branch 'codex/workbench-confirm-link-uow': workbench pair relation uow"`：Pass。
  - merge commit：`7e311921`。
- main 复验：
  - `git status --short --branch`：Pass，`main...origin/main [ahead 6]`。
  - `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
  - `git diff --check HEAD~1..HEAD`：Pass。
  - `test ! -e backend-go`：Pass。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，41 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，16 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_stale_write_contract -v`：Pass，3 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- 用户确认：
  - 用户已确认 PF-P036-MG `verified`。
  - 本轮允许执行 `git push origin main`。
- 未执行：
  - 未执行 Traffic Gate。
  - 未部署，未访问生产。
- 剩余风险：
  - Workbench idempotency 仍不是 PostgreSQL durable store。
  - actor/tenant 仍未接真实 auth context。
  - PF-P036-MG 只覆盖 pair relation `confirm-link` / `cancel-link` UoW，不代表 Workbench 写路径全部完成。
- 下一条 Prompt 上下文：
  - `git push origin main` 完成后，下一条 prompt 必须从最新 `main` 新建分支生成。
  - 建议下一条 prompt 是 `PF-P037 - Workbench Durable Idempotency PostgreSQL Store Planning`。
  - PF-P037 应只做 durable idempotency schema/repository 规划和风险拆解，不直接迁移更多 Workbench 写 API。

### PF-P037 - Workbench Durable Idempotency PostgreSQL Store Planning

状态：`verified`

#### 范围

- 从最新 `main` 新建分支：`codex/workbench-durable-idempotency-planning`。
- 只规划 Workbench durable idempotency PostgreSQL store。
- 产出或更新 `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`。
- 必须基于当前事实：`WorkbenchWriteUnitOfWork` 已接入 idempotency get/reserve/commit/replay，但当前生产组装仍使用 `InMemoryWorkbenchIdempotencyRepository`。
- 必须覆盖 schema、unique identity、row lock/concurrency、reserve/commit/replay/failed semantics、repository API、transaction integration、migration/testing strategy、rollout order 和 cleanup/retention。

#### 禁止范围

- 不写 SQL migration。
- 不实现 PostgreSQL repository。
- 不修改 `server.py`、`workbench_uow.py`、`workbench_idempotency.py` 或业务代码。
- 不迁移更多 Workbench 写 API。
- 不执行 Merge Gate、Traffic Gate、部署或生产访问。

#### 审查结论

- PF-P037 是 PF-P036-MG 后合理的下一步：真实 `confirm-link` / `cancel-link` 已进入 UoW，但 idempotency 仍是进程内存实现，不具备跨进程、重启后的生产级 replay/conflict 能力。
- 在继续迁移 exception、ignore、cash special、withdraw 等更多写路径前，应先把 durable idempotency 的表结构、并发语义和事务边界设计清楚。
- PF-P037 应是 planning prompt，不应直接实现；实现应拆到后续 PF-P038/PF-P039 等小切片。

#### 执行结果

- 状态：`verified`，用户已确认 PF-P037 可落锁。
- 产物：
  - `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`
- 读取/覆盖范围：
  - 状态机、prompt 库、UoW integration plan、UoW boundary design、platform runtime audit。
  - `workbench_idempotency.py`、`workbench_uow.py`、`server.py` 中 UoW factory。
  - PostgreSQL migration 目录、`0009_runtime_infrastructure.sql`、`0016_runtime_outbox_envelope_fields.sql`、当前最新 `0042_bank_detail_candidate_projection.sql`。
  - `tests/test_workbench_idempotency_contract.py`、`tests/test_workbench_uow_contract.py`、`tests/test_postgres_migrations.py`。
  - CodeGraph 覆盖 `WorkbenchWriteUnitOfWork.run`、`replay_committed`、`WorkbenchIdempotencyRecord`、`InMemoryWorkbenchIdempotencyRepository`、`workbench_request_fingerprint` 相关依赖。
- 设计结论：
  - 推荐表名 `app.workbench_idempotency_records`。
  - durable unique identity 继续使用 `(tenant_id, actor_id, idempotency_key)`；`action_name` 保留为诊断字段，不进入唯一键。
  - 当前 UoW 的 transaction-outside get 与 transaction-inside reserve 存在 durable store TOCTOU 风险，后续实现应通过 transaction-bound `reserve_or_get_locked(...)` 消除。
  - 建议拆分 replay reader 与 transaction-bound writer，以支持 cancel-link 在 active relation lookup 前 replay committed result。
  - 后续 SQL migration 建议为 `0043_workbench_idempotency_records.sql`，但 PF-P037 未创建该 migration。
- 未执行：
  - 未写 SQL migration。
  - 未实现 `PostgresWorkbenchIdempotencyRepository`。
  - 未修改生产代码或 tests。
  - 未迁移更多 Workbench 写 API。
  - 未执行 Merge Gate、Traffic Gate、部署或 push。
- 验证结果：
  - `git status --short --branch`：Pass，当前分支 `codex/workbench-durable-idempotency-planning`，仅文档变更。
  - `git ls-files --others --exclude-standard`：Pass，仅新增预期产物 `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`。
  - `git diff --check`：Pass。
  - `test ! -e backend-go`：Pass。
  - `test -f docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`：Pass。
  - `rg -n "PostgreSQL|idempotency|unique|reserved|committed|failed|source_versions|outbox_event_ids|TOCTOU|PF-P038" docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`：Pass，关键术语均覆盖。
- 下一条 Prompt 上下文：
  - 用户已确认 PF-P037 verified。
  - `PF-P038 - Workbench Durable Idempotency Migration and Contract Tests` 已生成并审查。
  - PF-P038 应新增 migration 和测试门禁，但仍不应切 production wiring 或迁移更多 Workbench 写 API。

### PF-P038 - Workbench Durable Idempotency Migration and Contract Tests

状态：`verified`

#### 范围

- 只允许新增 durable idempotency PostgreSQL migration 和默认绿测试门禁。
- 目标 migration：`backend/src/fin_ops_platform/postgres/migrations/0043_workbench_idempotency_records.sql`。
- 必须更新 migration discovery / schema contract tests。
- 可新增默认绿的 migration contract test，验证 table、constraints、unique index、JSONB 字段、grants 和 action_name 不进入 unique key。
- 不实现 `PostgresWorkbenchIdempotencyRepository`。
- 不切生产 wiring，不启用 PostgreSQL store，不迁移更多 Workbench 写 API。

#### 审查结论

- PF-P038 是 PF-P037 后合理的小切片：先把 durable idempotency 的 schema 和测试门禁落地，避免 repository implementation 在没有 schema contract 的情况下先行。
- PF-P038 必须保持默认 CI 绿色；任何未来 repository 行为测试如果尚未实现，必须使用明确的 future/expectedFailure 机制或推迟到 PF-P039。
- PF-P038 完成后不应直接进入更多 API 迁移；下一步应生成 `PF-P039 - Workbench Durable Idempotency Repository Integration`。

#### 执行结果

- 新增 migration：`backend/src/fin_ops_platform/postgres/migrations/0043_workbench_idempotency_records.sql`。
- 更新 migration discovery 和 schema contract tests：`tests/test_postgres_migrations.py`。
- 未新增 repository 文件；未实现 `PostgresWorkbenchIdempotencyRepository`。
- 未修改 `server.py`、`workbench_uow.py`、`workbench_idempotency.py` 或 production wiring。
- 未迁移更多 Workbench 写 API。

#### 变更文件

- `backend/src/fin_ops_platform/postgres/migrations/0043_workbench_idempotency_records.sql`
- `tests/test_postgres_migrations.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`

#### 验证

- RED：`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v` 在 migration 缺失时失败，失败点为缺少 `0043_workbench_idempotency_records.sql`。
- GREEN：`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v`：Pass。
- `git status --short --branch`：Pass，仅包含本轮预期变更和新增 migration。
- `git ls-files --others --exclude-standard`：Pass，仅列出本轮新增 `0043_workbench_idempotency_records.sql`。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass。
- `rg -n "0043_workbench_idempotency_records|app.workbench_idempotency_records|workbench_idempotency_identity_uidx|tenant_id, actor_id, idempotency_key|reserved|committed|failed" backend/src/fin_ops_platform/postgres/migrations/0043_workbench_idempotency_records.sql tests/test_postgres_migrations.py`：Pass。

#### 未关闭风险

- PostgreSQL repository 仍未实现。
- Durable idempotency 尚未接入 UoW production wiring。
- 真实 PostgreSQL 并发锁语义、expired reserved policy 和 replay integration 留给 PF-P039 之后的小切片。

#### 下一条 Prompt 上下文

- 下一条建议 prompt：`PF-P039 - Workbench Durable Idempotency Repository Integration`。
- PF-P039 应实现 PostgreSQL repository integration，但仍必须避免顺手迁移更多 Workbench 写 API，除非 prompt 明确授权。
- 用户已确认 PF-P038 verified。

### PF-P039 - Workbench Durable Idempotency Repository Integration

状态：`verified`

#### 范围

- 基于 PF-P038 的 `app.workbench_idempotency_records` schema，实现 PostgreSQL durable idempotency repository。
- 允许新增 `backend/src/fin_ops_platform/services/postgres_repositories/workbench_idempotency.py`。
- 允许为 UoW 增加 transaction-bound idempotency adapter seam，使 `reserve` / `commit` 与 facts、dirty scope、outbox 处于同一个 PostgreSQL transaction。
- 允许增加 disabled-by-default 的 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY` wiring，但默认行为必须继续使用 `InMemoryWorkbenchIdempotencyRepository`。
- 不迁移更多 Workbench 写 API。
- 不修改 migration schema，除非测试发现 PF-P038 schema 不能支撑必须语义；如需改 schema，PF-P039 必须停止并记录 blocker。

#### 审查结论

- PF-P039 是 PF-P038 后合理的下一步：schema 已有测试门禁，下一步应实现 repository 和 UoW transaction-bound 集成 seam。
- 重点风险是当前 UoW 的 transaction-outside replay probe 与 transaction-inside reserve/commit。PF-P039 prompt 必须要求测试证明 reserve/commit 使用同一个 transaction object，而不是在 repository 内打开新事务。
- PF-P039 仍不应迁移 ignore、cash special、withdraw、exception 等更多写 API；它只增强已存在 UoW idempotency 基础设施。
- PF-P039 完成后应生成 cumulative Merge Gate，覆盖 PF-P038 + PF-P039 的完整 diff。

#### 执行结果

- 新增 PostgreSQL durable idempotency repository：
  - `backend/src/fin_ops_platform/services/postgres_repositories/workbench_idempotency.py`
  - `PostgresWorkbenchIdempotencyRepository.get_committed_or_reserved(...)`
  - `reserve(...)`
  - `commit(...)`
  - `mark_failed(...)`
  - `has_fingerprint_conflict(...)`
  - `for_transaction(transaction)`
- `WorkbenchWriteUnitOfWork.run()` 新增 transaction-bound idempotency seam：
  - pre-transaction replay probe 仍用于已提交 replay。
  - transaction 内通过 `for_transaction(transaction)` 绑定 idempotency store。
  - `reserve` / `commit` 使用绑定后的 store，与 facts、dirty scope 和 outbox 使用同一个 UoW transaction object。
- `server.py` 新增 disabled-by-default wiring：
  - 未设置 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY` 或值为 `0` 时，继续使用 `InMemoryWorkbenchIdempotencyRepository`。
  - 仅当 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY` 为 `1/true/yes/on` 且 storage backend 为 PostgreSQL 时，构造 `PostgresWorkbenchIdempotencyRepository`。
- 新增 tests：
  - `tests/test_workbench_postgres_idempotency_repository.py`
  - `tests/test_workbench_uow_contract.py::test_idempotency_reserve_and_commit_use_transaction_bound_store`
- 未修改 `0043_workbench_idempotency_records.sql`。
- 未迁移 ignore、cash special、withdraw、exception 等更多 Workbench 写 API。
- 未默认启用 durable idempotency。
- 未执行 Merge Gate、Traffic Gate、部署或 push。

#### 变更文件

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/__init__.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench_idempotency.py`
- `backend/src/fin_ops_platform/services/workbench_uow.py`
- `tests/test_workbench_postgres_idempotency_repository.py`
- `tests/test_workbench_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`

#### 验证

- RED：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_postgres_idempotency_repository tests.test_workbench_uow_contract.WorkbenchUoWContractTests.test_idempotency_reserve_and_commit_use_transaction_bound_store -v` 在 repository 缺失、UoW 未绑定 transaction store 时失败。
- GREEN：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_postgres_idempotency_repository tests.test_workbench_uow_contract.WorkbenchUoWContractTests.test_idempotency_reserve_and_commit_use_transaction_bound_store -v`：Pass。
- `git status --short --branch`：Pass，位于 `codex/workbench-durable-idempotency-planning`，仅包含本轮预期变更和新增文件。
- `git ls-files --others --exclude-standard`：Pass，仅列出本轮新增 `workbench_idempotency.py` 和 `test_workbench_postgres_idempotency_repository.py`。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，17 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_postgres_idempotency_repository -v`：Pass，5 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，41 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v`：Pass，20 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- `rg -n "PostgresWorkbenchIdempotencyRepository|workbench_idempotency_records|for_transaction|FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY|InMemoryWorkbenchIdempotencyRepository" backend/src/fin_ops_platform tests docs/architecture/backend-refactor`：Pass。

#### 未关闭风险

- Durable idempotency 仍为显式 feature flag 控制，默认生产行为未切换。
- 真实 actor/tenant 仍未接 auth context，当前 UoW command 仍可能落到默认 `system/default`。
- `reserved` 记录的 expired takeover、失败重试策略、清理任务和观测指标仍未实现。
- 真实 PostgreSQL 并发行为尚未在外部数据库上跑 integration test，本轮使用 fake/contract-style 测试锁定 repository 与 UoW seam。

#### 用户确认

- 用户已确认 PF-P039 `verified`。

#### 下一条 Prompt 上下文

- `PF-P039-MG - Workbench Durable Idempotency Cumulative Merge Gate` 已生成并审查。
- PF-P039-MG 必须统一覆盖当前功能分支中尚未合入 `main` 的 durable idempotency 累计 diff，至少包含 PF-P038 + PF-P039。
- 执行前必须用 `git diff --name-status main...HEAD` 以真实 diff 为准，不能只凭记忆列文件。
- PF-P039-MG 不应执行 Traffic Gate，不应部署，不应默认启用 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。

### PF-P039-MG - Workbench Durable Idempotency Cumulative Merge Gate

状态：`verified`

#### 范围

- 只处理当前功能分支的 durable idempotency 累计 Merge Gate。
- 必须确认 PF-P038 和 PF-P039 均已 `verified`。
- 必须覆盖当前分支相对 `main` 的完整 diff；当前已知 diff 至少包含：
  - `backend/src/fin_ops_platform/app/server.py`
  - `backend/src/fin_ops_platform/postgres/migrations/0043_workbench_idempotency_records.sql`
  - `backend/src/fin_ops_platform/services/postgres_repositories/__init__.py`
  - `backend/src/fin_ops_platform/services/postgres_repositories/workbench_idempotency.py`
  - `backend/src/fin_ops_platform/services/workbench_uow.py`
  - `tests/test_postgres_migrations.py`
  - `tests/test_workbench_postgres_idempotency_repository.py`
  - `tests/test_workbench_uow_contract.py`
  - durable idempotency 相关架构文档和状态机 / prompt 库。
- 必须执行 upstream sync、范围检查、测试验证、本地合入 `main` 和 `main` 复验。

#### 禁止范围

- 不执行 Traffic Gate。
- 不部署，不访问生产，不 push 生产服务器。
- 不默认启用 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。
- 不迁移更多 Workbench 写 API。
- 不修改业务逻辑，除非 Merge Gate 验证发现必须修复的阻断；如需修复，必须记录并重新跑完整验证。
- 不使用 `git add .` 或 `git add -A`。

#### 审查结论

- PF-P039-MG 是 PF-P038/PF-P039 后合理的下一步：schema、repository 和 UoW seam 已完成，需要通过累计 Merge Gate 把 durable idempotency 基础切片合入 `main`。
- 当前分支还包含 durable idempotency 规划文档，因此执行 MG 时必须以 `main...HEAD` 的真实 diff 为准，不得只检查 PF-P038/PF-P039 名义上的文件。
- 本 MG 不代表上线；它只是把默认关闭的基础能力和测试门禁合入主干。

#### 下一步

- 用户已确认 PF-P039-MG `verified`，且已执行 `git push origin main`。
- 下一条 prompt 必须从最新 `main` 新建分支生成。

#### 执行结果

- 功能分支：`codex/workbench-durable-idempotency-planning`。
- 本地合入目标：`main`。
- Merge commit：`8c9aa130`。
- 合入方式：
  - `git fetch origin`：Pass。
  - `git checkout main`：Pass。
  - `git pull --ff-only origin main`：Pass，`Already up to date`。
  - `git checkout codex/workbench-durable-idempotency-planning`：Pass。
  - `git merge-base --is-ancestor main HEAD`：Pass，功能分支包含最新 `main`。
  - `git checkout main`：Pass。
  - `git merge --no-ff codex/workbench-durable-idempotency-planning -m "Merge branch 'codex/workbench-durable-idempotency-planning': workbench durable idempotency foundation"`：Pass，无冲突。
- 合入后 `main` 状态：
  - 合入完成时 `main...origin/main [ahead 8]`。

#### Feature Branch 验证

- `git status --short --branch`：Pass，位于 `codex/workbench-durable-idempotency-planning`。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --name-status main...HEAD`：Pass，仅包含 durable idempotency 范围。
- `git diff --check main...HEAD`：Pass。
- `git log --oneline main..HEAD`：Pass，覆盖 durable idempotency planning、migration、repository integration 和 MG planning commits。
- `test ! -e backend-go`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v`：Pass，20 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，17 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_postgres_idempotency_repository -v`：Pass，5 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，41 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- `rg -n "PostgresWorkbenchIdempotencyRepository|workbench_idempotency_records|for_transaction|FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY|InMemoryWorkbenchIdempotencyRepository" backend/src/fin_ops_platform tests docs/architecture/backend-refactor`：Pass，228 matches。

#### Main 复验

- `git status --short --branch`：Pass，`main...origin/main [ahead 8]`。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check HEAD~1..HEAD`：Pass。
- `test ! -e backend-go`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v`：Pass，20 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，17 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_postgres_idempotency_repository -v`：Pass，5 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，41 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。

#### 未执行（MG 阶段）

- 未执行 Traffic Gate。
- 未部署。
- 未访问生产。
- 未默认启用 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。
- MG 执行阶段未自动 push；用户确认 verified 后已执行 `git push origin main`。

#### 用户确认

- 用户已确认 PF-P039-MG `verified`。
- 已执行 `git push origin main`，远端已包含 PF-P039-MG 合入内容。
- 本次 push 只推送 Git 远端主干；未部署、未访问生产、未执行 Traffic Gate，且未默认启用 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。

#### 剩余风险

- Durable idempotency 仍为显式 feature flag 控制，默认生产行为未切换。
- 真实 actor/tenant 仍未接 auth context。
- `reserved` 记录 expired takeover、清理任务、失败重试策略和生产观测指标仍未实现。
- 未执行真实 PostgreSQL 并发 integration test。

#### 下一条 Prompt 上下文

- 下一条 prompt 必须从最新 `main` 新建分支生成。
- 下一条建议 prompt 应继续围绕 durable idempotency 的 rollout readiness 或 Workbench 剩余写 API UoW 接入。
- 不得在当前 `main` 或旧功能分支上直接继续开发。

### PF-P040 - Workbench Durable Idempotency Rollout Readiness and Integration Contract Tests

状态：`verified`

#### 范围

- 从最新 `main` 创建分支：`codex/workbench-durable-idempotency-rollout-readiness`。
- 只处理 Workbench durable idempotency 启用前的 rollout readiness、integration-style contract tests 和文档化门禁。
- 允许新增一份 rollout readiness 文档。
- 允许新增或补充默认绿色的 fake/integration-style contract tests。
- 不默认启用 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。
- 不部署、不执行 Traffic Gate、不访问生产。
- 不迁移更多 Workbench 写 API。

#### 审查结论

- PF-P040 是 PF-P039-MG 后合理的下一步：durable repository 和 UoW seam 已合入主干，但 feature flag 仍关闭。继续迁移更多写 API 前，应先明确启用前的门禁、回滚方式、真实 PostgreSQL integration 缺口、actor/tenant auth context 缺口和 reserved/failed/cleanup 策略。
- PF-P040 不应直接打开 feature flag，也不应把 merge 等同于上线。
- PF-P040 产物应让后续“是否可以在测试环境/生产环境启用 durable idempotency”有机械检查依据，而不是凭经验判断。

#### 执行结果

- 新增 rollout readiness 文档：`docs/architecture/backend-refactor/workbench-durable-idempotency-rollout-readiness.md`。
- 新增默认绿色测试：`tests/test_workbench_durable_idempotency_rollout.py`。
- RED：新增测试先因 rollout readiness 文档缺失失败，证明 PF-P040 的缺口被测试捕获。
- GREEN：补齐文档后，rollout tests 全部通过。
- 用测试锁定：
  - 未设置 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY` 时仍使用 `InMemoryWorkbenchIdempotencyRepository`。
  - 显式设置 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY=1` 时才构造 `PostgresWorkbenchIdempotencyRepository`。
- 用 readiness matrix 固化当前状态：
  - `ready`：default-off safety、opt-in feature flag wiring、transaction-bound reserve/commit、committed replay、same-key different-fingerprint conflict、payload sanitization、rollback。
  - `documented-risk`：migration apply readiness。
  - `blocked`：reserved/in-progress duplicate policy、expired reserved takeover、failed reservation policy、cleanup/retention、actor/tenant auth context。
  - `future-test-needed`：real PostgreSQL row-lock concurrency、observability/metrics/logging。
- 未默认启用 durable idempotency。
- 未迁移更多 Workbench 写 API。
- 未修改 `0043_workbench_idempotency_records.sql`。
- 未执行 Merge Gate、Traffic Gate、部署或 push。

#### 变更文件

- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-rollout-readiness.md`
- `tests/test_workbench_durable_idempotency_rollout.py`

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_durable_idempotency_rollout -v`：先失败，失败原因是 PF-P040 readiness 文档缺失；补文档后通过，3 tests。
- `git status --short --branch`：Pass，位于 `codex/workbench-durable-idempotency-rollout-readiness`，仅包含 PF-P040 预期文档和测试变更。
- `git ls-files --others --exclude-standard`：Pass，仅包含本轮新增 rollout readiness 文档和 rollout test。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，17 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_postgres_idempotency_repository -v`：Pass，5 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_durable_idempotency_rollout -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- `rg -n "FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY|PostgresWorkbenchIdempotencyRepository|rollout readiness|expired reserved|actor|tenant|rollback" docs/architecture/backend-refactor backend/src/fin_ops_platform tests`：Pass。
- 未经用户确认不得将本 prompt 标记为 `verified`。

#### 未关闭风险

- `actor/tenant auth context` 仍未接真实身份，durable unique identity 仍可能落到默认 `system/default`。
- `reserved/in-progress duplicate policy` 尚未实现。
- `expired reserved takeover` 尚未实现。
- `failed reservation policy` 尚未实现。
- `cleanup/retention` 尚未实现。
- `real PostgreSQL row-lock concurrency` 尚未验证。
- `observability/metrics/logging` 尚未补齐。

#### 下一步

- 用户已确认 PF-P040 `verified`。
- PF-P040-MG deferred：后续 cumulative MG 将覆盖 PF-P040 起同一 durable idempotency rollout blocker 主题的完整 diff。
- 已生成并审查 `PF-P041 - Workbench Durable Idempotency Actor/Tenant Context Contract`；下一步允许执行 PF-P041。

### PF-P041 - Workbench Durable Idempotency Actor/Tenant Context Contract

状态：`verified`

#### 范围

- 只处理 Workbench durable idempotency identity 的 actor/tenant auth context contract。
- 目标是让 Workbench UoW command / idempotency identity 不再默认落到 `actor_id="system"`、`tenant_id="default"`，而是从 OA session / auth context 显式传入。
- 必须先写 failing tests，再做最小实现。
- 不打开 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。
- 不迁移更多 Workbench 写 API。
- 不处理 reserved/in-progress、expired takeover、failed policy、cleanup/retention 或真实 PostgreSQL concurrency。
- 不执行 Merge Gate、Traffic Gate、部署或 push。

#### 审查结论

- PF-P041 是 PF-P040 后合理的下一步：PF-P040 readiness matrix 已将 `actor/tenant auth context` 标为 feature flag 打开前 blocker。
- CodeGraph / 源码确认当前 `_WorkbenchConfirmLinkCommand` 和 `_WorkbenchCancelLinkCommand` 默认 `tenant_id="default"`、`actor_id="system"`。
- 源码确认 `server.py` 的 `_enforce_route_access()` 会解析 OA session 并校验权限，但当前只返回 auth error / None，成功 session 未传到 Workbench 写 handler / facade。
- PF-P041 必须禁止把 session 存到 `Application` 全局可变字段；该系统存在 threaded request 风险，auth context 应作为请求局部参数显式传递。
- PF-P041 不应顺手改变历史 audit / `created_by` 语义，除非测试证明这是 actor context contract 必需且范围可控。

#### 执行结果

- 新增 `tests/test_workbench_auth_context_idempotency.py`。
- RED：新增测试先因 `WorkbenchWriteFacade.confirm_link()` / `cancel_link()` 不接受 `actor_id` / `tenant_id`，以及 Workbench handler 不接受 `headers` 而失败。
- GREEN：实现请求局部 auth context 传递后测试通过。
- `app/auth.py` 新增纯 helper：
  - `actor_id_for_session(session)`：优先使用 `OAUserIdentity.user_id`，回退 `username` / `system`。
  - `tenant_id_for_session(session)`：当前返回显式单租户 `default`。
- `server.py` 中 Workbench confirm/cancel handler 显式接收 headers，解析请求局部 OA session 后把 actor/tenant 传给 live write path。
- `WorkbenchWriteFacade.confirm_link()` / `cancel_link()` 新增细粒度 `actor_id` / `tenant_id` 参数。
- `_WorkbenchConfirmLinkCommand` / `_WorkbenchCancelLinkCommand` 在 UoW 路径显式填充 actor/tenant，供 durable idempotency identity 和 request fingerprint 使用。
- 未启用 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。
- 未迁移更多 Workbench 写 API。
- 未修改 deployment/env/gateway/frontend/worker 或 PostgreSQL migration。
- 未执行 Merge Gate、Traffic Gate、部署或 push。

#### 变更文件

- `backend/src/fin_ops_platform/app/auth.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_workbench_auth_context_idempotency.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-rollout-readiness.md`

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency -v`：先失败，失败原因是 actor/tenant/header 参数不存在；实现后通过，3 tests。
- `git status --short --branch`：Pass，位于 `codex/workbench-durable-idempotency-rollout-readiness`，仅包含 PF-P041 预期代码、测试和文档变更。
- `git ls-files --others --exclude-standard`：Pass，仅包含本轮新增 `tests/test_workbench_auth_context_idempotency.py`。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，17 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，41 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_durable_idempotency_rollout -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- `rg -n "actor_id=\"system\"|created_by=\"system\"|tenant_id=\"default\"|OARequestSession|resolve_oa_request_session|FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY" backend/src/fin_ops_platform/app backend/src/fin_ops_platform/services tests docs/architecture/backend-refactor`：Pass，剩余 `created_by="system"` / `tenant_id="default"` 均为本轮明确不迁移的 audit 语义、单租户默认、测试或历史文档语境。
- 用户已确认 PF-P041 `verified`。

#### 未关闭风险

- 当前 `tenant_id` 仍是显式单租户 `default`，系统尚无真实多租户来源。
- `reserved/in-progress duplicate policy` 尚未实现。
- `expired reserved takeover` 尚未实现。
- `failed reservation policy` 尚未实现。
- `cleanup/retention` 尚未实现。
- `real PostgreSQL row-lock concurrency` 尚未验证。
- `observability/metrics/logging` 尚未补齐。

#### 下一步

- 用户已确认 PF-P041 `verified`。
- 已生成并审查 `PF-P042 - Workbench Durable Idempotency Reserved/In-Progress Policy`；下一步允许执行 PF-P042。

### PF-P042 - Workbench Durable Idempotency Reserved/In-Progress Policy

状态：`verified`

#### 范围

- 只处理 Workbench durable idempotency 的 same-key same-fingerprint `reserved` / in-progress duplicate policy。
- 建立 deterministic in-progress primitive，使已有 `reserved` 记录不会让重复请求再次执行 handler、dirty scope 或 outbox。
- 允许引入最小 reserve outcome contract，用于区分“本请求新建 reservation”和“已有 reservation 被命中”。
- 保持 committed replay、different-fingerprint conflict 和 actor/tenant identity 语义不退化。
- 不打开 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。
- 不处理 expired reserved takeover、failed retry policy、cleanup/retention、observability 或真实 PostgreSQL concurrency integration test。
- 不迁移更多 Workbench 写 API。
- 不执行 Merge Gate、Traffic Gate、部署或 push。

#### 审查结论

- PF-P042 是 PF-P041 verified 后合理的下一步：rollout readiness matrix 中 `reserved/in-progress duplicate policy` 仍是打开 durable idempotency feature flag 前的 blocker。
- 当前 `WorkbenchWriteUnitOfWork.run()` 对同 key 同 fingerprint 的 `reserved` 记录只会跳过 committed replay，然后继续进入 handler，存在重复写风险。
- 当前 `PostgresWorkbenchIdempotencyRepository.reserve()` 可返回冲突行，但没有显式告诉 UoW 这条 row 是新建 reservation 还是已有 in-progress reservation，因此 PF-P042 应优先建立可测试的 reserve outcome seam。
- PF-P042 不应伪装解决所有并发问题：expired takeover、failed retry 和真实 PostgreSQL row-lock concurrency 仍应留给后续 prompt。

#### 验收标准

- `refactor-prompts.md` 已包含完整 PF-P042 prompt，且 prompt 正文以 `/goal` 开头。
- PF-P042 prompt 包含 Pre-Flight、Allowed Scope、Forbidden Scope、Required Test Work、Required Implementation Work、Required Documentation、Required Verification、Post-Flight 和 Stop Conditions。
- PF-P042 prompt 明确禁止启用 durable idempotency feature flag、部署、Traffic Gate、push 和迁移更多 Workbench 写 API。
- PF-P042 prompt 明确 PF-P040-MG 仍 deferred，后续 cumulative MG 覆盖 PF-P040 起的完整 diff。

#### 变更文件

- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-rollout-readiness.md`

#### 验证

- RED：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract tests.test_workbench_uow_contract tests.test_workbench_postgres_idempotency_repository -v` 先失败，失败原因是缺少 `WorkbenchIdempotencyInProgress` / `WorkbenchIdempotencyReservation`，且 existing reserved 仍会执行 handler。
- GREEN：PF-P042 最小实现后，新增和相关测试通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，11 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，18 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_postgres_idempotency_repository -v`：Pass，6 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，41 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_durable_idempotency_rollout -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency -v`：Pass，4 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `rg -n "idempotency_key_in_progress|WorkbenchIdempotencyInProgress|WorkbenchIdempotencyReservation|reserved/in-progress|FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY" backend/src/fin_ops_platform/services tests docs/architecture/backend-refactor`：Pass。
- `git status --short --branch`：Pass，仅包含 PF-P042 预期代码、测试和文档变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。

#### 执行结果

- 新增 `WorkbenchIdempotencyInProgress`，稳定返回 `idempotency_key_in_progress` 409 payload。
- 新增 `WorkbenchIdempotencyReservation(record, created)` reserve outcome。
- `InMemoryWorkbenchIdempotencyRepository.reserve()` 不再覆盖已有 same identity reservation。
- `PostgresWorkbenchIdempotencyRepository.reserve()` 使用 insert-if-absent + existing row `for update` SQL contract 区分 new/existing reservation。
- `WorkbenchWriteUnitOfWork.run()` 对 transaction 外已有 `reserved` 和 transaction 内 existing reservation 都返回 in-progress，不执行 handler、dirty scope、outbox 或 commit。
- confirm-link / cancel-link facade 将 in-progress primitive 映射为稳定 409 payload。
- rollout readiness 中 `reserved/in-progress duplicate policy` 已从 `blocked` 调整为 `ready`。
- 未启用 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。
- 未迁移更多 Workbench 写 API。
- 未修改 SQL migration、部署、网关、worker、前端。
- 未执行 Merge Gate、Traffic Gate、部署或 push。

#### 变更文件

- `backend/src/fin_ops_platform/services/workbench_idempotency.py`
- `backend/src/fin_ops_platform/services/workbench_uow.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench_idempotency.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_workbench_idempotency_contract.py`
- `tests/test_workbench_uow_contract.py`
- `tests/test_workbench_postgres_idempotency_repository.py`
- `tests/test_workbench_auth_context_idempotency.py`
- `tests/test_workbench_durable_idempotency_rollout.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-rollout-readiness.md`

#### 未关闭风险

- `expired reserved takeover` 尚未实现。
- `failed reservation policy` 尚未实现。
- `cleanup/retention` 尚未实现。
- `real PostgreSQL row-lock concurrency` 尚未验证。
- `observability/metrics/logging` 尚未补齐。
- 当前 `tenant_id` 仍是显式单租户 `default`，系统尚无真实多租户来源。

#### 下一步

- 用户已确认 PF-P042 `verified`。
- 已生成并审查 `PF-P043 - Workbench Durable Idempotency Expired Reserved Takeover Policy`；下一步允许执行 PF-P043。
- PF-P042 仍不触发 MG；cumulative MG 将覆盖 PF-P040 起同一 durable idempotency rollout blocker 主题的完整 diff。

### PF-P043 - Workbench Durable Idempotency Expired Reserved Takeover Policy

状态：`verified`

#### 范围

- 只处理 Workbench durable idempotency 的 expired `reserved` takeover policy。
- 明确过期 `reserved` 与 active `reserved` 的分流：
  - active `reserved` same-fingerprint 继续返回 `idempotency_key_in_progress`。
  - expired `reserved` same-fingerprint 可以被同一请求安全接管并继续执行 handler。
  - expired `reserved` different-fingerprint 仍不得绕过 `idempotency_key_conflict`。
- 允许最小扩展 reserve outcome / repository contract，使 UoW 能区分 existing-active、existing-expired-taken-over、created。
- 不打开 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。
- 不处理 failed reservation retry policy、cleanup/retention、observability 或真实 PostgreSQL concurrency integration test。
- 不迁移更多 Workbench 写 API。
- 不执行 Merge Gate、Traffic Gate、部署或 push。

#### 审查结论

- PF-P043 是 PF-P042 verified 后合理的下一步：rollout readiness matrix 中 `expired reserved takeover` 仍是打开 durable idempotency feature flag 前的 blocker。
- PF-P042 已解决 active `reserved` 重复请求不应再次执行 handler 的问题；如果不补 expired takeover，崩溃后残留的 `reserved` 会永久阻塞同一 key 的安全重试。
- PF-P043 不应把“过期接管”和“失败重试策略”混在一起：`failed` 状态的重试语义仍应留给后续 prompt。
- PF-P043 不应伪装完成真实 PostgreSQL 并发验证；默认 CI 仍以 fake/contract tests 为主，真实 row-lock concurrency 单独跟踪。

#### 验收标准

- `refactor-prompts.md` 已包含完整 PF-P043 prompt，且 prompt 正文以 `/goal` 开头。
- PF-P043 prompt 包含 Pre-Flight、Allowed Scope、Forbidden Scope、Required Test Work、Required Implementation Work、Required Documentation、Required Verification、Post-Flight 和 Stop Conditions。
- PF-P043 prompt 明确禁止启用 durable idempotency feature flag、部署、Traffic Gate、push 和迁移更多 Workbench 写 API。
- PF-P043 prompt 明确 PF-P040-MG 仍 deferred，后续 cumulative MG 覆盖 PF-P040 起的完整 diff。
- PF-P043 prompt 明确 active `reserved` 语义不得回退，same-key different-fingerprint conflict 不得被 expired takeover 绕过。

#### 变更文件

- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-rollout-readiness.md`

#### 验证

- RED：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract tests.test_workbench_uow_contract tests.test_workbench_postgres_idempotency_repository -v` 先失败，失败原因是缺少 `is_workbench_idempotency_reserved_expired`、reserve outcome 无 `taken_over_expired`，且 UoW 将 expired reserved 误判为 in-progress。
- GREEN：PF-P043 最小实现后，新增和相关测试通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，14 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，20 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_postgres_idempotency_repository -v`：Pass，7 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，41 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_durable_idempotency_rollout -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency -v`：Pass，4 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `rg -n "expired reserved|taken_over|takeover|WorkbenchIdempotencyReservation|FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY" backend/src/fin_ops_platform/services tests docs/architecture/backend-refactor`：Pass。
- `git status --short --branch`：Pass，仅包含 PF-P043 预期代码、测试和文档变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。

#### 执行结果

- 新增 deterministic expiration helper：只有 status 为 `reserved` 且 `expires_at <= now` 才视为 expired。
- 扩展 `WorkbenchIdempotencyReservation(record, created, taken_over_expired)`。
- `InMemoryWorkbenchIdempotencyRepository.reserve()` 支持 same-fingerprint expired reserved takeover，并保持 active reservation 不覆盖。
- `PostgresWorkbenchIdempotencyRepository.reserve()` 使用 insert-if-absent + locked existing row + conditional takeover SQL contract 表达 expired takeover。
- `WorkbenchWriteUnitOfWork.run()` 对 expired same-fingerprint reserved 进入 transaction-bound takeover path；active reserved 继续返回 in-progress。
- same-key different-fingerprint 即使 expired 仍继续返回 `idempotency_key_conflict`。
- rollout readiness 中 `expired reserved takeover` 已从 `blocked` 调整为 `ready`。
- 未启用 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。
- 未迁移更多 Workbench 写 API。
- 未修改 SQL migration、部署、网关、worker、前端。
- 未执行 Merge Gate、Traffic Gate、部署或 push。

#### 变更文件

- `backend/src/fin_ops_platform/services/workbench_idempotency.py`
- `backend/src/fin_ops_platform/services/workbench_uow.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench_idempotency.py`
- `tests/test_workbench_idempotency_contract.py`
- `tests/test_workbench_uow_contract.py`
- `tests/test_workbench_postgres_idempotency_repository.py`
- `tests/test_workbench_durable_idempotency_rollout.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-rollout-readiness.md`

#### 未关闭风险

- `failed reservation policy` 尚未实现。
- `cleanup/retention` 尚未实现。
- `real PostgreSQL row-lock concurrency` 尚未验证。
- `observability/metrics/logging` 尚未补齐。
- 当前 `tenant_id` 仍是显式单租户 `default`，系统尚无真实多租户来源。

#### 下一步

- 用户已确认 PF-P043 `verified`。
- 已生成并审查 `PF-P044 - Workbench Durable Idempotency Failed Reservation Policy`；下一步允许执行 PF-P044。
- PF-P043 仍不触发 MG；cumulative MG 将覆盖 PF-P040 起同一 durable idempotency rollout blocker 主题的完整 diff。

### PF-P044 - Workbench Durable Idempotency Failed Reservation Policy

状态：`verified`

#### 范围

- 只处理 Workbench durable idempotency 的 `failed` record policy。
- 建立 deterministic failed same-fingerprint response，避免同一 idempotency key 在失败后盲目重跑 handler。
- 继续保持 same-key different-fingerprint conflict。
- 允许最小新增 failed primitive / helper / repository contract test。
- 不打开 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。
- 不处理 cleanup/retention、observability 或真实 PostgreSQL concurrency integration test。
- 不迁移更多 Workbench 写 API。
- 不执行 Merge Gate、Traffic Gate、部署或 push。

#### 审查结论

- PF-P044 是 PF-P043 verified 后合理的下一步：rollout readiness matrix 中 `failed reservation policy` 仍是打开 durable idempotency feature flag 前的 blocker。
- 当前源码已有 `status="failed"` 和 `mark_failed()`，但 UoW 对 failed record 没有稳定 replay/reject 语义；如果不锁定策略，后续 request path 可能对失败记录产生盲重放或不一致 retry。
- PF-P044 的保守策略应是：same-fingerprint failed record 返回稳定 failed idempotency response，默认不自动重试；如果未来需要 retry，必须用新 idempotency key 或后续显式 retry policy。
- PF-P044 不应混入 cleanup/retention、observability 或真实 PostgreSQL 并发 integration test；这些仍是独立 gate。

#### 执行结果

- 新增 `WorkbenchIdempotencyFailed`，稳定返回 `idempotency_key_failed`、HTTP 409 语义和 `retryable=false`。
- `WorkbenchWriteUnitOfWork.run()` 对 same-key same-fingerprint `failed` record 直接返回 failed primitive，不执行 handler、不打开 transaction、不写 dirty scope/outbox/reserve/commit。
- `WorkbenchWriteUnitOfWork.run()` 对 same-key different-fingerprint `failed` record 继续走 `idempotency_key_conflict`。
- `WorkbenchWriteUnitOfWork.replay_committed()` 也识别 failed record，使 cancel-link 可在 active relation lookup 前返回稳定 failed response。
- `InMemoryWorkbenchIdempotencyRepository.mark_failed()` 对 request / response payload 执行 sanitizer。
- `PostgresWorkbenchIdempotencyRepository.mark_failed()` 继续使用 fake SQL contract，锁定 sanitized response payload 和 no nested transaction。
- confirm-link / cancel-link Facade 捕获 failed primitive 并返回稳定 409 payload，不落入 generic persistence unavailable 分支。
- `workbench-durable-idempotency-rollout-readiness.md` 中 `failed reservation policy` 已从 `blocked` 调整为 `ready`。
- 本轮未启用 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`，未修改 migration，未迁移更多 Workbench 写 API。

#### 验收标准

- `refactor-prompts.md` 已包含完整 PF-P044 prompt，且 prompt 正文以 `/goal` 开头。
- PF-P044 prompt 包含 Pre-Flight、Allowed Scope、Forbidden Scope、Required Test Work、Required Implementation Work、Required Documentation、Required Verification、Post-Flight 和 Stop Conditions。
- PF-P044 prompt 明确禁止启用 durable idempotency feature flag、部署、Traffic Gate、push 和迁移更多 Workbench 写 API。
- PF-P044 prompt 明确 PF-P040-MG 仍 deferred，后续 cumulative MG 覆盖 PF-P040 起的完整 diff。
- PF-P044 prompt 明确 failed same-fingerprint 不自动重试，different-fingerprint 继续 conflict。

#### 变更文件

- `backend/src/fin_ops_platform/services/workbench_idempotency.py`
- `backend/src/fin_ops_platform/services/workbench_uow.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-rollout-readiness.md`
- `tests/test_workbench_durable_idempotency_rollout.py`
- `tests/test_workbench_idempotency_contract.py`
- `tests/test_workbench_postgres_idempotency_repository.py`
- `tests/test_workbench_uow_contract.py`
- `tests/test_workbench_write_characterization.py`

#### 验证

- RED：新增 failed primitive / UoW / Facade 测试先失败，失败点集中在缺少 `WorkbenchIdempotencyFailed`、failed record 仍执行 handler、Facade 未映射 409。
- `git status --short --branch`：Pass，变更范围仅限 PF-P044 允许文件。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪临时文件。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，18 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，22 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_postgres_idempotency_repository -v`：Pass，8 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，43 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_durable_idempotency_rollout -v`：Pass，3 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency -v`：Pass，4 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
- `rg -n "idempotency_key_failed|WorkbenchIdempotencyFailed|mark_failed|failed reservation|FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY" backend/src/fin_ops_platform/services tests docs/architecture/backend-refactor`：Pass。

#### 下一步

- 用户已确认 PF-P044 `verified`。
- 已生成并审查 `PF-P044-MG - Workbench Durable Idempotency Rollout Cumulative Merge Gate`。
- PF-P044-MG 只做 PF-P040 到 PF-P044 完整 diff 的 Merge Gate，不触发 Traffic Gate、部署或打开 feature flag。

### PF-P044-MG - Workbench Durable Idempotency Rollout Cumulative Merge Gate

状态：`verified`

#### 范围

- 覆盖 PF-P040 到 PF-P044 的完整 diff。
- 当前分支：`codex/workbench-durable-idempotency-rollout-readiness`。
- 当前分支相对 `main` 的提交范围：
  - `908ba91c docs(backend-refactor): plan durable idempotency rollout readiness`
  - `a72adac4 test(workbench): add durable idempotency rollout readiness`
  - `377fcbc0 docs(workbench): plan idempotency actor context contract`
  - `cd3753d5 feat(workbench): propagate auth context to idempotency commands`
  - `3a9c01e5 docs(workbench): plan idempotency in-progress policy`
  - `fd574862 feat(workbench): handle idempotency in-progress reservations`
  - `ec86d127 docs(workbench): plan expired reserved takeover prompt`
  - `7aeb4138 feat(workbench): handle expired idempotency reservations`
  - `db905884 docs(workbench): plan failed idempotency policy prompt`
  - `01e29dce feat(workbench): handle failed idempotency records`
- 预期 diff 文件：
  - `backend/src/fin_ops_platform/app/auth.py`
  - `backend/src/fin_ops_platform/app/server.py`
  - `backend/src/fin_ops_platform/services/postgres_repositories/workbench_idempotency.py`
  - `backend/src/fin_ops_platform/services/workbench_idempotency.py`
  - `backend/src/fin_ops_platform/services/workbench_uow.py`
  - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`
  - `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`
  - `docs/architecture/backend-refactor/workbench-durable-idempotency-rollout-readiness.md`
  - `tests/test_workbench_auth_context_idempotency.py`
  - `tests/test_workbench_durable_idempotency_rollout.py`
  - `tests/test_workbench_idempotency_contract.py`
  - `tests/test_workbench_postgres_idempotency_repository.py`
  - `tests/test_workbench_uow_contract.py`
  - `tests/test_workbench_write_characterization.py`

#### 审查结论

- PF-P044-MG 是 PF-P040 到 PF-P044 这组 durable idempotency rollout blocker 切片的合理 Merge Gate。
- 本 MG 是 Merge Gate，不是 Traffic Gate：不得部署、不得访问生产、不得修改环境变量、不得打开 `FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY`。
- 合入 main 后仍不能视为 durable idempotency 可上线打开；`cleanup/retention`、真实 PostgreSQL row-lock concurrency、observability/metrics/logging 和 migration apply/runbook 仍是后续 gate。
- MG 执行时必须做 upstream sync；如果 main 更新导致 rebase/merge 冲突，必须解决冲突并重跑完整验证后才允许合入。

#### 验收标准

- `refactor-prompts.md` 已包含完整 PF-P044-MG prompt，且正文以 `/goal` 开头。
- PF-P044-MG prompt 明确只处理 Merge Gate，不执行 Traffic Gate、部署、生产访问或 feature flag 打开。
- PF-P044-MG prompt 明确检查 expected changed files、untracked files、upstream sync、main 复验和状态机更新。
- PF-P044-MG prompt 明确禁止 `git add .` / `git add -A`，必须精准 stage 文件。
- PF-P044-MG prompt 明确未经用户确认不得标记 `verified`。

#### 变更文件

- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/workbench-durable-idempotency-plan.md`

#### 验证

- `git diff --check`：Pass。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪临时文件。
- `test ! -e backend-go`：Pass。
- 文档检索：Pass，`refactor-prompts.md` 已包含 PF-P044-MG，正文以 `/goal` 开头；状态机已标记 PF-P044 `verified` 且 PF-P044-MG `planned`。

#### 执行结果

- Feature branch pre-flight：Pass。
  - 当前分支曾为 `codex/workbench-durable-idempotency-rollout-readiness`。
  - `git status --short --branch`：Pass，工作区干净。
  - `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
  - `git diff --check`：Pass。
  - `test ! -e backend-go`：Pass。
  - `git diff --name-only main...HEAD`：Pass，只包含 PF-P044-MG expected changed files。
- Upstream sync / merge：Pass。
  - `git checkout main`：Pass。
  - `git pull origin main`：Pass，`main` 已是最新 `origin/main`。
  - `git merge --no-ff codex/workbench-durable-idempotency-rollout-readiness -m "Merge branch 'codex/workbench-durable-idempotency-rollout-readiness': workbench durable idempotency rollout guards"`：Pass。
  - Merge commit：`5fb40888`。
- Main post-merge verification：Pass。
  - `git status --short --branch`：Pass，`main...origin/main [ahead 12]`。
  - `git diff --check`：Pass。
  - `test ! -e backend-go`：Pass。
  - `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v`：Pass，22 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_idempotency_contract -v`：Pass，18 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_postgres_idempotency_repository -v`：Pass，8 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v`：Pass，43 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_durable_idempotency_rollout -v`：Pass，3 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency -v`：Pass，4 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v`：Pass，12 tests。
  - `rg -n "FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY|PostgresWorkbenchIdempotencyRepository|WorkbenchIdempotencyFailed|WorkbenchIdempotencyInProgress|taken_over_expired|actor_id_for_session|tenant_id_for_session|cleanup/retention|row-lock concurrency|observability" backend/src/fin_ops_platform tests docs/architecture/backend-refactor`：Pass。
- 未执行：Traffic Gate、部署、生产访问、staging 访问、网关/worker routing 修改、环境变量修改、`FIN_OPS_WORKBENCH_DURABLE_IDEMPOTENCY` 打开、push。
- 仍保留为后续 gate / blocker：
  - `cleanup/retention`。
  - `real PostgreSQL row-lock concurrency`。
  - `observability/metrics/logging`。
  - migration apply/runbook。
- 用户已确认 PF-P044-MG 可标记为 `verified`；本次状态更新将随 `git push origin main` 推送到远端。

#### 下一步

- 执行 `git push origin main`。
- push 完成后，从最新 `main` 新建分支。
- 若继续拆 durable idempotency rollout blocker，下一条 prompt 应聚焦 cleanup/retention、real PostgreSQL concurrency 或 observability 中的一个。

### PF-P045 - Main Delta Rebaseline / Refactor Plan Resync

状态：`verified`

#### 范围

- 先将本地 `main` 推送到 `origin/main`，使基线对齐。
- 从最新 `main` 新建 `codex/main-delta-rebaseline-p045`。
- 对 `PF-P044-MG` 后进入 main 的后端 delta 做增量盘点。
- 更新重构状态机、prompt 库、架构资产清单、模块计划和 AI 执行规则。
- 不改业务代码，不执行 Traffic Gate，不部署，不访问生产。

#### 关键发现

- `main` 已推送并对齐 `origin/main`：`f68d2683 Preserve turnover ledger group breakdowns from flat read models`。
- `ccbf7c2d..f68d2683` 包含 20 个后端/部署/测试/文档相关提交。
- Delta 影响约 178 个后端相关文件，约 28k insertions / 4.5k deletions。
- 新增/强化的重点模块：
  - Turnover Ledger：query service、SQL projection、source versions、read model refresh、grouped payload breakdown。
  - Bankdetail / No OA Batch：route facade、application service、tag semantics、No OA Batch read model/worker/selection。
  - Invoices：Pending Invoice lifecycle、Output Invoice Collections、Input Invoice Usage OA reverse、OA Pending Payments read model。
  - Tax / Cost / ETC：cost statistics runtime、ETC business batch、tax offset plans/query/runtime。
  - Platform / Runtime：runtime worker registry、RabbitMQ/staging preflight、deploy worker env examples。
  - Workbench：matching dirty scope worker 需要纳入后续 runtime boundary 事实源。
- 未发现需要推翻 Python-first 计划或创建新语言后端的证据。

#### 已固化的低耦合规则

- 优先复用已有封装、service、repository、platform helper 和测试工具，不重复造轮子。
- `server.py` / `routes_*` 只做路由、HTTP 映射、依赖组装和调用。
- 不允许机械拆文件；不能把 `server.py` 函数原样搬到 service 就算完成。
- service 不依赖整个 `Application` 对象，只接收明确依赖。
- service 不直接读 HTTP cookie/header，不 import `app.auth`。
- worker runner 不知道 HTTP response，不构造页面 payload。
- repository 可以知道 SQL 表结构；业务 service 不散落 SQL。
- 业务写操作继续遵守 facts、audit、dirty scope、outbox 同事务底线。

#### 变更文件

- `docs/architecture/backend-refactor/ai-execution-rules.md`
- `docs/architecture/backend-refactor/architecture-inventory.md`
- `docs/architecture/backend-refactor/module-refactor-plan.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`

#### 验证

- `git push origin main`：Pass，`1736acca..f68d2683 main -> main`。
- `git status --short --branch`：Pass，`main...origin/main` 对齐后新建分支。
- `git rev-parse --short HEAD` 与 `git rev-parse --short origin/main`：Pass，均为 `f68d2683`。
- `git log --oneline ccbf7c2d..HEAD -- backend/src/fin_ops_platform backend/README.md docs/architecture/backend-refactor docs/dev docs/operations docs/product-specs tests deploy/oa`：Pass，识别 20 个相关提交。
- `git diff --name-status ccbf7c2d..HEAD -- backend/src/fin_ops_platform backend/README.md docs/architecture/backend-refactor docs/dev docs/operations docs/product-specs tests deploy/oa`：Pass，完成 delta 文件归属盘点。
- CodeGraph context：Pass，确认 Turnover Ledger 和 app entry 仍为相关入口。
- 未运行 Python 测试：本轮只做文档和重构计划再校准，不改业务代码。

#### 下一步

- 用户已确认 PF-P045 `verified`。
- 已生成并审查 `PF-P045-MG - Main Delta Rebaseline Merge Gate`。
- 下一条实际模块 prompt 必须读取 PF-P045 delta 事实，不能继续基于 PF-P044-MG 之前的旧状态生成。

### PF-P045-MG - Main Delta Rebaseline Merge Gate

状态：`verified`

#### 范围

- 覆盖 PF-P045 的文档-only diff。
- 当前分支：`codex/main-delta-rebaseline-p045`。
- 当前分支相对 `main` 的预期提交：
  - `02e75d9b docs(backend-refactor): rebaseline main delta for PF-P045`
- 预期 diff 文件：
  - `docs/architecture/backend-refactor/ai-execution-rules.md`
  - `docs/architecture/backend-refactor/architecture-inventory.md`
  - `docs/architecture/backend-refactor/module-refactor-plan.md`
  - `docs/architecture/backend-refactor/migration-state-log.md`
  - `docs/architecture/backend-refactor/refactor-prompts.md`

#### 审查结论

- PF-P045-MG 是文档分支的 Merge Gate，只决定是否把 main delta rebaseline 文档合入 `main`。
- 本 MG 不执行 Traffic Gate、部署、生产访问、staging 访问或 feature flag 打开。
- 本 MG 不执行任何模块业务重构，不生成下一条模块实现 prompt。
- 合入后，后续模块 prompt 必须读取 PF-P045 的 delta 事实和低耦合规则。

#### 验收标准

- `refactor-prompts.md` 已包含完整 PF-P045-MG prompt，正文以 `/goal` 开头。
- PF-P045-MG prompt 明确只允许文档 diff。
- PF-P045-MG prompt 明确执行 branch/diff scope、untracked files、upstream sync、main 复验和状态机更新。
- PF-P045-MG prompt 明确禁止 `git add .` / `git add -A`。
- PF-P045-MG prompt 明确未经用户确认不得标记 `verified`。

#### 变更文件

- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`

#### 验证

- `git status --short --branch`：Pass，当前分支为 `codex/main-delta-rebaseline-p045`。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。

#### 执行结果

- Feature branch pre-flight：Pass。
  - 当前分支为 `codex/main-delta-rebaseline-p045`。
  - `git status --short --branch`：Pass，工作区干净。
  - `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
  - `git diff --check`：Pass。
  - `test ! -e backend-go`：Pass。
  - `git diff --name-only main...HEAD`：Pass，只包含 PF-P045-MG expected changed files。
  - `git log --oneline main..HEAD`：Pass，包含 `2272cabd` 和 `02e75d9b`。
  - `rg -n "PF-P045|Main Delta Rebaseline|低耦合|不允许机械拆文件|server.py|routes_\\*" docs/architecture/backend-refactor`：Pass。
- Upstream sync / merge：Pass。
  - `git checkout main`：Pass。
  - `git pull origin main`：Pass，`main` 已是最新 `origin/main`。
  - `git merge --no-ff codex/main-delta-rebaseline-p045 -m "Merge branch 'codex/main-delta-rebaseline-p045': main delta rebaseline docs"`：Pass。
  - Merge commit：`8f98f8ec`。
- Main post-merge verification：Pass。
  - `git status --short --branch`：Pass，`main...origin/main [ahead 3]`。
  - `git diff --check`：Pass。
  - `test ! -e backend-go`：Pass。
  - `rg -n "PF-P045|Main Delta Rebaseline|低耦合|不允许机械拆文件|server.py|routes_\\*" docs/architecture/backend-refactor`：Pass。
- 未执行：Traffic Gate、部署、生产访问、staging 访问、网关/worker routing 修改、环境变量修改、feature flag 打开。
- 用户已确认 PF-P045-MG `verified`。
- 已执行 `git push origin main`，`main` 与 `origin/main` 对齐到 `de513774`。

#### 下一步

- 已从最新 `main` 新建 `codex/turnover-ledger-discovery-p046`。
- 下一条 prompt 已生成并审查：`PF-P046 - Turnover Ledger Discovery and Planning / Main Delta-Aware Boundary Scan`。
- PF-P046 必须读取 PF-P045 delta 事实，只做 discovery/planning 和文档回写，不修改业务代码。

### PF-P046 - Turnover Ledger Discovery and Planning / Main Delta-Aware Boundary Scan

状态：`verified`

#### 范围

- 从 PF-P045 main delta 事实出发，深挖 Turnover Ledger 模块边界。
- 梳理 API/action matrix、文件 ownership、静态调用链、动态运行时序、read model freshness、source version、dirty scope、outbox、Workbench/Bankdetail 影响链。
- 生成或更新 Turnover Ledger 专项 discovery/planning 文档。
- 只做文档回写，不修改业务代码，不新增测试实现，不进入 Merge Gate。

#### 必须覆盖

- `/api/turnover-ledger`
- `/api/turnover-ledger/export-preview`
- `/api/turnover-ledger/export`
- `/api/turnover-ledger/bank-row-tags/batch`
- `/api/turnover-ledger/relations/*`
- `app/routes_turnover_ledger.py`
- `app/server.py` 中 Turnover Ledger handler/source version/stale reason/extras 相关入口。
- `services/turnover_ledger_query_service.py`
- `services/turnover_ledger_read_model_refresh.py`
- `services/turnover_ledger_source_versions.py`
- `services/turnover_ledger_sql_projection.py`
- `services/turnover_ledger_service.py`
- `services/turnover_relation_service.py`
- `services/turnover_ledger_extra_service.py`
- `services/turnover_ledger_export_service.py`
- 相关 PostgreSQL repository、dirty scope/outbox/derived lifecycle、tests 和 migration。

#### 生成结果要求

- `refactor-prompts.md` 已包含完整 PF-P046 prompt，正文以 `/goal` 开头。
- PF-P046 明确禁止修改业务代码、测试实现、SQL migration、前端、部署和生产配置。
- PF-P046 明确不执行 Traffic Gate、不部署、不访问生产、不进入 Merge Gate。
- PF-P046 明确后续下一步应是 Turnover Ledger characterization tests prompt，而不是直接 extraction/refactor。

#### 执行结果

- 已使用 CodeGraph 和只读源码扫描梳理 Turnover Ledger：
  - route/server handler 到 `TurnoverLedgerApiRoutes`、`TurnoverLedgerQueryService`、`TurnoverLedgerService`、`TurnoverRelationService` 的调用链。
  - SQL read model / source_versions / runtime queue / worker refresh / projection builder 的运行时序。
  - relation confirm/withdraw、bank-row-tags batch、extra update、tag-selection update 的副作用链。
- 已新增 `turnover-ledger-discovery.md`，覆盖 API/action matrix、file ownership、static call chain、dynamic runtime sequence、freshness/source_version audit、transaction/outbox audit、cross-module influence、low-coupling targets、PF-P047 测试计划和 risk register。
- 已更新 `architecture-inventory.md`，加入 PF-P046 Turnover Ledger discovery update。
- 已更新 `module-refactor-plan.md`，加入 Turnover 后续切片建议。
- 已更新 `runtime-call-chain.md`，加入 Turnover query/write/worker 三条运行时序。
- 已更新 `README.md` 文档索引。

#### 变更文件

- `docs/architecture/backend-refactor/README.md`
- `docs/architecture/backend-refactor/architecture-inventory.md`
- `docs/architecture/backend-refactor/module-refactor-plan.md`
- `docs/architecture/backend-refactor/runtime-call-chain.md`
- `docs/architecture/backend-refactor/turnover-ledger-discovery.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`

#### 验证

- `git status --short --branch`：Pass，当前分支为 `codex/turnover-ledger-discovery-p046`。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪临时文件；仅新增预期文档。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `test -f docs/architecture/backend-refactor/turnover-ledger-discovery.md`：Pass。
- `rg -n 'PF-P046|Turnover Ledger|turnover_ledger|grouped breakdown|source_version|dirty scope|outbox|Workbench projection|Bankdetail' docs/architecture/backend-refactor`：Pass。
- 未运行 Python 单元测试：本轮只做 discovery/planning 文档，不修改业务代码或测试实现。

#### 风险 / 阻断

- 当前没有阻断 PF-P047 的发现。
- Turnover 写路径尚未具备显式 Turnover Unit of Work；relation facts/audit、Workbench invalidation、read model clear/enqueue 仍由 handler finalizer 编排。
- `turnover_ledger_extras` 仍存在 legacy full snapshot fallback，需要 PF-P047 characterization 后再处理。
- `/api/turnover-ledger/bank-row-tags/batch` 是 Turnover API 但写 Bankdetail category facts，后续必须明确 service port 与事务边界。

#### 下一步

- 用户已确认 PF-P046 `verified`。
- 已生成并审查 `PF-P047 - Turnover Ledger Characterization Tests`。
- 下一步允许执行 PF-P047；PF-P047 只写/补 Turnover Ledger characterization tests 和必要文档回写，不做 production refactor。

### PF-P047 - Turnover Ledger Characterization Tests

状态：`verified`

#### 范围

- 基于 PF-P046 的 `turnover-ledger-discovery.md`，为 Turnover Ledger 当前行为补充 characterization tests。
- 只允许新增或扩展 Turnover Ledger 相关测试，以及必要状态机/prompt 文档回写。
- 不允许重构 production code，不允许 extraction，不允许引入 Turnover UoW，不允许修改事务语义。

#### 必须锁定的行为

- Query freshness：
  - fresh SQL read model 返回当前 payload，不触发 legacy rebuild。
  - source_versions mismatch 返回 refreshing/stale payload，并 enqueue `api_stale`。
  - SQL read model miss 且 PostgreSQL required 时返回 empty refreshing payload，并 enqueue `api_miss`。
- Grouped breakdown：
  - flat SQL read model rows 经过 route facade 转 grouped payload 时，保留 `pending_repayment_amount`、`repaid_amount`、`pending_collection_amount`、`collected_amount`、`closed_amount`。
  - 原生 grouped payload 的 `summary_row`、`flow_rows`、`allocation_lots`、`lot_rows` 在 normalization 后不丢字段。
- Relation writes：
  - confirm/withdraw 当前 response shape、relation/audit side effects、read model clear/enqueue 行为。
  - non-manual relation withdraw 当前阻断行为。
  - 失败发生在 mutation 前时，不应 enqueue Turnover read model refresh。
- Extra writes：
  - extra update 当前 persistence 和 refresh scheduling 行为。
  - legacy full snapshot fallback 路径必须被明确锁定或标记为 removal candidate，不得静默忽略。
- Bank row tag batch：
  - turnover-eligible target validation。
  - Bankdetail category facts update 对 Turnover 和 Workbench projection invalidation 的当前影响。
  - conflict/error response shape。
- Export：
  - export preview/export 对 grouped payload 的 summary + flow row 展平行为。
  - row limit、family filter、空数据当前行为。
- Cross-module source versions：
  - relation snapshot、extras、tag selection、bank category snapshot、auto tag rules 和 OA projection sync version 改变时，expected source_versions 改变。
  - 相关 Workbench turnover grouping tests 必须保留在验证集。

#### 禁止范围

- 不修改 Turnover Ledger production code。
- 不修改 `server.py` handler 逻辑。
- 不修改 service/repository/worker 实现。
- 不修改 SQL migration。
- 不修改前端、部署、Nginx、worker routing、环境变量或生产配置。
- 不执行 Traffic Gate、部署、生产访问或 staging 访问。
- 不进入 Merge Gate。

#### 验收标准

- `refactor-prompts.md` 已包含完整 PF-P047 prompt，正文以 `/goal` 开头。
- PF-P047 prompt 明确读取 PF-P046 discovery 文档。
- PF-P047 prompt 明确先锁行为，不做重构。
- PF-P047 prompt 明确测试状态隔离要求，避免 PostgreSQL/Redis/state store 污染其他测试。
- PF-P047 prompt 明确执行后只能标记 `implemented` 或 `blocked`；未经用户确认不得标记 `verified`。

#### 下一步

- 用户已确认 PF-P047 `verified`。
- 已生成并审查 `PF-P048 - Turnover Ledger Query/Route Facade Extraction Planning`。
- 下一步允许执行 PF-P048；PF-P048 只做 query/route facade extraction planning，不做 production refactor。

#### 执行结果

- 已补充 Turnover Ledger characterization tests，只修改测试和重构文档，不修改 production code。
- 新增/扩展测试覆盖：
  - `tests/test_turnover_ledger_query_service.py`：SQL read model miss 时 PostgreSQL-required 返回 empty refreshing payload 并 enqueue `api_miss`；PostgreSQL optional 时走 legacy builder 并注入 `source_versions`。
  - `tests/test_turnover_ledger_api.py`：flat read model grouped breakdown backend-only 字段、relation extra refresh side effects、legacy full snapshot fallback、confirm/withdraw read model clear/enqueue side effects、system withdraw no side effect、non-turnover bank-row-tags batch failure no side effect。
  - `tests/test_turnover_ledger_export_service.py`：preview limit、totals、empty grouped payload shape。
  - `tests/test_turnover_ledger_source_versions.py`：source_versions 包含所有 Turnover/cross-module inputs，并随 relation、extras、tag selection、bank category、auto tag rules、OA projection sync 变化。
- 验证通过：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_api tests.test_turnover_ledger_export_service tests.test_turnover_ledger_source_versions -v`：Pass，33 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_api tests.test_turnover_ledger_export_service tests.test_turnover_relation_service tests.test_turnover_ledger_extra_service tests.test_workbench_turnover_grouping tests.test_turnover_ledger_source_versions -v`：Pass，79 tests。
- 初始全量目标集曾暴露一个既有测试污染/读取 local pickle 的偶发问题；单测单独运行通过，后续通过改用 in-memory audit log 断言和更明确的 recorder 隔离规避了该 characterization 测试中的 state store 读污染。
- 未执行 Traffic Gate、部署、生产访问、staging 访问、网关/worker routing 修改、环境变量修改或 feature flag 打开。

### PF-P048 - Turnover Ledger Query/Route Facade Extraction Planning

状态：`verified`

#### 范围

- 基于 PF-P046 discovery 和 PF-P047 characterization tests，规划 Turnover Ledger query/route facade extraction 的最小安全切片。
- 只允许读取代码、测试和文档，并更新 Turnover Ledger planning 文档、状态机和 prompt 库。
- 不允许修改 production code，不允许新增测试实现，不允许开始 extraction/refactor。

#### 必须覆盖

- `server.py` 中 Turnover query/export/detail/extra GET 相关 handler 的保留职责和可迁移职责。
- `routes_turnover_ledger.py` 中 route facade 当前职责：
  - query service delegation；
  - grouped normalization；
  - flat read model -> grouped compatibility；
  - export service composition；
  - relation detail/extra read mapping。
- `TurnoverLedgerQueryService`、`TurnoverLedgerExportService`、`TurnoverLedgerExtraService` 的依赖边界。
- PF-P047 新增测试如何作为下一步 extraction/refactor 的护栏。

#### 禁止范围

- 不修改 `backend/src/fin_ops_platform/**` production code。
- 不修改 tests。
- 不修改 SQL migration。
- 不修改前端、部署、Nginx、worker routing、环境变量或生产配置。
- 不引入 Turnover Unit of Work。
- 不迁移 relation confirm/withdraw、bank-row-tags batch 或 mutation side effects。
- 不执行 Merge Gate。
- 不执行 Traffic Gate、部署、生产访问或 staging 访问。

#### 预期产物

- 更新 `turnover-ledger-discovery.md` 或新增专项 planning 小节，明确：
  - Query/route facade extraction target shape；
  - dependencies to inject；
  - files to touch in the next implementation prompt；
  - tests to run；
  - exact stop conditions；
  - what must remain in `server.py`；
  - what must not be moved yet。
- 更新 `migration-state-log.md` 和 `refactor-prompts.md`。

#### 下一步

- 用户已确认 PF-P048 `verified`。
- 已生成并审查 `PF-P049 - Turnover Ledger Query/Route Facade Extraction`。
- 下一步允许执行 PF-P049；PF-P049 只做 read-only query/route facade extraction，不做 mutation/UoW。

#### 执行结果

- 已完成 Turnover Ledger query/route facade extraction planning，只更新重构文档，不修改 production code、tests、SQL migration、前端或部署。
- 已在 `turnover-ledger-discovery.md` 新增 `PF-P048 Query/Route Facade Extraction Planning` 小节，明确：
  - PF-P049 的目标是 read-only query/route facade extraction，不是 mutation UoW；
  - `server.py` 保留 HTTP dispatch、参数解析、auth/session、异常到 HTTP 映射和 `Response` 构造；
  - 新 helper/facade 只能依赖 `TurnoverLedgerApiRoutes` 等细粒度依赖，不允许注入 `Application` 或 runtime god object；
  - PF-P049 允许触碰的文件和必须排除的 mutation/worker/repository/migration/frontend/deploy 文件；
  - PF-P047 79-test command 作为下一步 implementation 的测试门禁；
  - extra GET/PUT 边界、legacy fallback、export response header 和 grouped compatibility 风险。
- 当前建议 PF-P049 最小实现顺序：
  1. 引入 read-only Turnover Ledger route/query facade helper；
  2. 复用现有 `_turnover_ledger_api_routes` 进行委托；
  3. 只替换 list、export-preview、export、relation GET、extra GET handler 的内部委托；
  4. 保持 `server.py` 的 HTTP response mapping；
  5. 不触碰 extra PUT、confirm、withdraw、bank-row-tags batch 或 tag-selection write。
- 验证：
  - `git status --short --branch`：Pass，仅文档变更。
  - `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
  - `git diff --check`：Pass。
  - `test ! -e backend-go`：Pass。
  - `rg -n "PF-P048|Query/Route Facade Extraction|Turnover Ledger|server.py|TurnoverLedgerApiRoutes|PF-P049" docs/architecture/backend-refactor`：Pass。
- 未执行 Merge Gate、Traffic Gate、部署、生产访问、staging 访问、网关/worker routing 修改、环境变量修改或 feature flag 打开。

### PF-P049 - Turnover Ledger Query/Route Facade Extraction

状态：`verified`

#### 范围

- 基于 PF-P048 的规划，实施 Turnover Ledger read-only query/route facade extraction。
- 只允许显式化 HTTP read boundary，保持当前业务行为和响应契约。
- 允许新增一个轻量 read-only app-boundary helper/facade，或在 `routes_turnover_ledger.py` 中增加等价轻量边界。

#### 允许修改

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
- 可选：`backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`
- 只有在 import/helper 名称变化确实需要时，才允许最小修改 Turnover Ledger targeted tests。
- `migration-state-log.md`、`refactor-prompts.md` 和必要执行结果文档。

#### 禁止范围

- 不修改 Turnover mutation handlers：
  - `_handle_api_turnover_ledger_tag_selection_update`
  - `_handle_api_turnover_ledger_bank_row_tags_batch`
  - `_handle_api_turnover_ledger_relation_extra_update`
  - `_handle_api_turnover_ledger_confirm`
  - `_handle_api_turnover_ledger_withdraw`
- 不引入 Turnover Unit of Work。
- 不修改 stale write、durable idempotency、dirty scope/outbox 语义。
- 不修改 query legacy fallback。
- 不修改 `TurnoverLedgerQueryService`、`TurnoverLedgerExportService`、`TurnoverLedgerExtraService`、worker、repository、SQL migration、前端或部署配置。
- 不执行 Merge Gate、Traffic Gate、部署、生产访问或 staging 访问。

#### 验收标准

- `server.py` 的 read-only Turnover handlers 更薄，只保留 HTTP 参数解析、错误到 HTTP 映射和 `Response` 构造。
- 新 helper/facade 不知道 `Response`、HTTP headers/cookies，也不 import `app.auth`。
- 新 helper/facade 不接收 `Application`、`state_store`、`RuntimeRepositories` 或其他 god object。
- PF-P047 79-test command 必须通过。

#### 下一步

- 用户已确认 PF-P049 `verified`。
- 已生成并审查 `PF-P050 - Turnover Ledger Read Facade Handler Cleanup`。
- 下一步允许执行 PF-P050；PF-P050 只能做 read-only handler cleanup，不做 mutation/UoW。

#### 执行结果

- 已实施 Turnover Ledger read-only query/route facade extraction。
- TDD RED：
  - 新增 `tests/test_turnover_ledger_read_facade.py` 后，`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_read_facade -v` 因缺少 `fin_ops_platform.app.turnover_ledger_read_facade` 失败，证明新 helper 边界测试有效。
- Production 变更：
  - 新增 `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`，`TurnoverLedgerReadFacade` 只接收 `routes` 细粒度依赖，返回 plain Python payload 或 `(filename, bytes)`，不构造 `Response`，不读取 headers/cookies，不 import auth。
  - `backend/src/fin_ops_platform/app/server.py` 初始化 `_turnover_ledger_read_facade`，并只把以下 read-only handlers 的内部委托改为 facade：
    - `_handle_api_turnover_ledger`
    - `_handle_api_turnover_ledger_export_preview`
    - `_handle_api_turnover_ledger_export`
    - `_handle_api_turnover_ledger_relation`
    - `_handle_api_turnover_ledger_relation_extra`
- 未修改 mutation handlers：
  - `_handle_api_turnover_ledger_tag_selection_update`
  - `_handle_api_turnover_ledger_bank_row_tags_batch`
  - `_handle_api_turnover_ledger_relation_extra_update`
  - `_handle_api_turnover_ledger_confirm`
  - `_handle_api_turnover_ledger_withdraw`
- 验证：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_read_facade -v`：Pass，2 tests。
  - `python3 -m compileall -q backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py backend/src/fin_ops_platform/services`：Pass。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_api tests.test_turnover_ledger_export_service tests.test_turnover_relation_service tests.test_turnover_ledger_extra_service tests.test_workbench_turnover_grouping tests.test_turnover_ledger_source_versions tests.test_turnover_ledger_read_facade -v`：Pass，81 tests。
- 未修改 `TurnoverLedgerQueryService`、`TurnoverLedgerExportService`、`TurnoverLedgerExtraService`、`TurnoverLedgerService`、`TurnoverRelationService`、repository、worker、runtime queue、SQL migration、frontend、deployment、Nginx、Vite、environment variables 或 production config。
- 未执行 Merge Gate、Traffic Gate、部署、生产访问或 staging 访问。

### PF-P050 - Turnover Ledger Read Facade Handler Cleanup

状态：`verified`

#### 范围

- 基于 PF-P049 已抽出的 `TurnoverLedgerReadFacade`，继续做一个窄 read-only cleanup。
- 只允许整理 `server.py` 中 Turnover read-only handlers 的重复 query parsing / helper shape / response mapping 形态。
- 不允许引入新业务逻辑或改变 API response contract。

#### 允许修改

- `backend/src/fin_ops_platform/app/server.py`，仅限 read-only Turnover handlers 及其私有小 helper。
- `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`，仅限为 cleanup 保持更清晰的 read-only facade 方法名或 typed helper。
- `tests/test_turnover_ledger_read_facade.py` 或 existing Turnover API tests，只有在 cleanup 增加可观察边界时才允许最小测试。
- 重构文档和状态机。

#### 禁止范围

- 不修改 mutation handlers、UoW、repository、worker、runtime queue、SQL migration、frontend、deployment 或 production config。
- 不修改 `TurnoverLedgerApiRoutes` 的 grouped compatibility、export composition 或 legacy fallback 语义。
- 不删除 legacy fallback。
- 不执行 Merge Gate、Traffic Gate、部署、生产访问或 staging 访问。

#### 验收标准

- `server.py` read-only Turnover handler 更一致、更薄，但仍负责 HTTP parsing/error mapping/Response 构造。
- PF-P049 facade 仍不接收 `Application`、`state_store`、`RuntimeRepositories` 或 HTTP headers/cookies。
- PF-P047/PF-P049 targeted tests 必须通过。

#### 下一步

- 用户已确认 PF-P050 `verified`。
- 已生成并审查 `PF-P050-MG - Turnover Ledger Discovery / Characterization / Read Facade Cumulative Merge Gate`。
- 下一步允许执行 PF-P050-MG，统一覆盖 PF-P046 到 PF-P050 的完整 diff。

#### 执行结果

- `backend/src/fin_ops_platform/app/server.py` 新增 Turnover Ledger read-only 专用 query helper：
  - `_turnover_ledger_query_value`
  - `_turnover_ledger_query_int`
- `backend/src/fin_ops_platform/app/server.py` 新增 `_turnover_ledger_export_response`，集中保留 XLSX HTTP response mapping。
- `_handle_api_turnover_ledger`、`_handle_api_turnover_ledger_export_preview`、`_handle_api_turnover_ledger_export` 改用上述 helper，减少重复 `query.get(...)[0]` 和 export response 组装。
- 未修改 read facade 业务委托语义；`TurnoverLedgerReadFacade` 仍只接收 route facade，不依赖 `Application`、`state_store`、`RuntimeRepositories`、HTTP headers/cookies 或 auth。
- 未修改 mutation handlers、UoW、repository、worker、runtime queue、SQL migration、frontend、deployment、production config、Traffic Gate 或生产访问。

#### 验证

- `python3 -m compileall -q backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py backend/src/fin_ops_platform/services`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_read_facade -v`：Pass，2 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_api tests.test_turnover_ledger_export_service tests.test_turnover_relation_service tests.test_turnover_ledger_extra_service tests.test_workbench_turnover_grouping tests.test_turnover_ledger_source_versions tests.test_turnover_ledger_read_facade -v`：Pass，81 tests。
- `git status --short --branch`：仅本轮允许文件有修改。
- `git ls-files --others --exclude-standard`：无输出。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `rg -n "PF-P050|Turnover Ledger Read Facade Handler Cleanup|TurnoverLedgerReadFacade|_handle_api_turnover_ledger" docs/architecture/backend-refactor backend/src/fin_ops_platform/app tests`：Pass。

### PF-P050-MG - Turnover Ledger Discovery / Characterization / Read Facade Cumulative Merge Gate

状态：`verified`

#### 范围

- 只处理 Turnover Ledger read-side cumulative Merge Gate。
- 覆盖 PF-P046、PF-P047、PF-P048、PF-P049、PF-P050 的完整 diff。
- 允许执行范围检查、上游同步、必要验证、精确暂存、commit、合入 `main` 前后复验。
- 不执行 Traffic Gate、部署、生产访问、staging 访问或 feature flag 打开。

#### 必须确认

- PF-P046 到 PF-P050 均已 `verified`。
- 当前分支是 `codex/turnover-ledger-discovery-p046`。
- diff 只包含 Turnover Ledger discovery/planning、characterization tests、read-only facade extraction、read-only handler cleanup 和对应文档。
- 不包含 mutation/UoW/repository/worker/runtime queue/SQL migration/frontend/deployment/production config 变更。

#### 预期 diff 文件

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`
- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_export_service.py`
- `tests/test_turnover_ledger_query_service.py`
- `tests/test_turnover_ledger_read_facade.py`
- `tests/test_turnover_ledger_source_versions.py`
- `docs/architecture/backend-refactor/README.md`
- `docs/architecture/backend-refactor/architecture-inventory.md`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/module-refactor-plan.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/runtime-call-chain.md`
- `docs/architecture/backend-refactor/turnover-ledger-discovery.md`

#### 验证要求

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git log --oneline origin/main..HEAD`
- `git diff --name-only origin/main...HEAD`
- `git diff --check origin/main...HEAD`
- `test ! -e backend-go`
- `python3 -m compileall -q backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py backend/src/fin_ops_platform/services`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_api tests.test_turnover_ledger_export_service tests.test_turnover_relation_service tests.test_turnover_ledger_extra_service tests.test_workbench_turnover_grouping tests.test_turnover_ledger_source_versions tests.test_turnover_ledger_read_facade -v`

#### 下一步

- 用户已确认 PF-P050-MG `verified`。
- 已执行 `git push origin main`。
- 下一步从最新 `main` 新建分支生成下一条 prompt。

#### 执行结果

- 已执行 PF-P050-MG。
- 已在 `codex/turnover-ledger-discovery-p046` 上完成 diff scope 检查和合并前验证。
- 已确认 `origin/main...HEAD` diff 只包含 PF-P046 到 PF-P050 的 Turnover Ledger discovery、characterization tests、read-only facade extraction、read-only handler cleanup 和相关文档。
- 已确认 expected changed files 白名单完全匹配，无额外文件。
- 已确认无 untracked files，未夹带 `.pkl`、`.sqlite`、`__pycache__` 或测试输出。
- 已确认 `main` 与 `origin/main` 在合并前 0/0 对齐。
- 已将 `codex/turnover-ledger-discovery-p046` 合入本地 `main`，merge commit 为 `abd55c00`。
- `git push origin main` 已通过，`main` 与 `origin/main` 将在本状态收口提交推送后保持对齐。
- 未执行 Traffic Gate、部署、生产访问、staging 访问、网关/worker routing 修改、环境变量修改或 feature flag 打开。

#### 合并前验证

- `git status --short --branch`：Pass，当前分支 `codex/turnover-ledger-discovery-p046` 且工作区干净。
- `git ls-files --others --exclude-standard`：Pass，无输出。
- `git log --oneline origin/main..HEAD`：Pass，列出 PF-P046 到 PF-P050 分支提交。
- `git diff --name-only origin/main...HEAD`：Pass，14 个文件均在白名单内。
- `git diff --stat origin/main...HEAD`：Pass。
- `git diff --check origin/main...HEAD`：Pass。
- `test ! -e backend-go`：Pass。
- expected changed files compare：Pass，无差异。
- `python3 -m compileall -q backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py backend/src/fin_ops_platform/services`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_read_facade -v`：Pass，2 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_api tests.test_turnover_ledger_export_service tests.test_turnover_relation_service tests.test_turnover_ledger_extra_service tests.test_workbench_turnover_grouping tests.test_turnover_ledger_source_versions tests.test_turnover_ledger_read_facade -v`：Pass，81 tests。
- `rg -n "PF-P046|PF-P047|PF-P048|PF-P049|PF-P050|PF-P050-MG|Turnover Ledger" docs/architecture/backend-refactor backend/src/fin_ops_platform/app tests`：Pass。

#### main 上复验

- `git status --short --branch`：Pass，`main...origin/main [ahead 12]`。
- `git ls-files --others --exclude-standard`：Pass，无输出。
- `git diff --check`：Pass。
- `test ! -e backend-go`：Pass。
- `python3 -m compileall -q backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_turnover_ledger.py backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py backend/src/fin_ops_platform/services`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_read_facade -v`：Pass，2 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_api tests.test_turnover_ledger_export_service tests.test_turnover_relation_service tests.test_turnover_ledger_extra_service tests.test_workbench_turnover_grouping tests.test_turnover_ledger_source_versions tests.test_turnover_ledger_read_facade -v`：Pass，81 tests。
- `rg -n "PF-P046|PF-P047|PF-P048|PF-P049|PF-P050|PF-P050-MG|Turnover Ledger" docs/architecture/backend-refactor backend/src/fin_ops_platform/app tests`：Pass。

### PF-P051 - Turnover Ledger Write Path Discovery and UoW Boundary Planning

状态：`verified`

#### 范围

- 只做 Turnover Ledger 写路径 discovery/planning 和文档回写。
- 基于 PF-P046 到 PF-P050 已合入的 read-side facade 基线，盘点 mutation path、side effects、事务边界和未来 UoW 包裹范围。
- 不修改生产代码，不实现 UoW，不迁移 handler，不改 repository 行为，不改 worker/runtime queue，不改 SQL migration，不改 frontend，不执行 Traffic Gate。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。
- prompt 要求执行前读取状态机、prompt 库、Turnover discovery、架构计划和相关代码/测试。
- prompt 要求使用 CodeGraph 梳理静态调用链和动态运行时序。

#### 生成时已确认的 CodeGraph 事实

- `_handle_api_turnover_ledger_confirm` 调用 `_turnover_mutation_session`、`TurnoverLedgerApiRoutes.confirm_relation`、`_bank_transaction_category_affected_months` 和 `_after_turnover_relation_mutation`。
- `_handle_api_turnover_ledger_withdraw` 调用 `_turnover_mutation_session`、`TurnoverLedgerApiRoutes.get_relation`、`TurnoverLedgerApiRoutes.withdraw_relation`、`_bank_transaction_category_affected_months` 和 `_after_turnover_relation_mutation`。
- `_handle_api_turnover_ledger_bank_row_tags_batch` 调用 `_turnover_mutation_session`、`BankTransactionCategoryService.apply_turnover_updates`、`save_bank_transaction_categories`、`TurnoverLedgerApiRoutes.snapshot`、`TurnoverRelationService.rebuild_from_bank_rows` 和 `_after_turnover_relation_mutation`。
- `_handle_api_turnover_ledger_relation_extra_update` 调用 `TurnoverLedgerApiRoutes.update_relation_extra`、`_persist_turnover_ledger_extras_best_effort`、`_clear_turnover_ledger_read_model_best_effort` 和 `_enqueue_turnover_ledger_read_model_refreshes`。
- `_handle_api_turnover_ledger_tag_selection_update` 调用 `AppSettingsService.update_turnover_ledger_tag_selection`、`_clear_turnover_ledger_read_model_best_effort` 和 `_enqueue_turnover_ledger_read_model_refreshes`。
- `_after_turnover_relation_mutation` 调用 `_persist_turnover_relations_best_effort`、`_invalidate_workbench_after_bank_transaction_categories`、`_clear_turnover_ledger_read_model_best_effort` 和 `_enqueue_turnover_ledger_read_model_refreshes`。

#### 下一步

- 已根据自动工作流授权和验证结果将 PF-P051 标记为 `verified`。
- 下一条建议 prompt：`PF-P052 - Turnover Ledger Write Path Characterization Tests`。
- PF-P052 应先锁定 duplicate/stale/failure 当前行为，不应直接实现 UoW。

#### 执行结果

- 已执行 PF-P051。
- 新增 `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`。
- 更新 `docs/architecture/backend-refactor/turnover-ledger-discovery.md`，记录 PF-P051 产物和下一步建议。
- 已确认 Turnover Ledger 写路径当前仍由 `server.py` 编排，写 handler 包括 tag selection PUT、bank-row-tags batch、relation extra PUT、confirm 和 withdraw。
- 已确认 `_after_turnover_relation_mutation` 负责 relation snapshot persistence、Workbench invalidation、read model clear 和 refresh enqueue。
- 已确认 `RuntimeQueueRepository.enqueue_read_model_refresh_in_transaction()` 已提供 transaction-bound dirty scope + outbox primitive，但当前 Turnover 写路径未使用外层 transaction-bound 调用。
- 已确认 Bankdetail category facts、Turnover relation facts/audit、extras、settings mutation、read model clear 和 outbox enqueue 目前分散在多个 service/helper 中。
- 已确认下一步不应直接实现 UoW；应先补 API-level characterization tests。
- 未修改 production code、tests、SQL migration、worker、frontend、deployment 或生产配置。

#### 验证

- `git status --short --branch`：Pass，当前分支 `codex/turnover-ledger-write-uow-p051`，仅本轮文档文件有修改。
- `git ls-files --others --exclude-standard`：Pass，仅本轮新增计划文档。
- `git diff --check`：Pass。
- `rg -n "PF-P051|Turnover Ledger Write Path|UoW|_after_turnover_relation_mutation|bank-row-tags|tag selection|relation extra" docs/architecture/backend-refactor`：Pass。

### PF-P052 - Turnover Ledger Write Path Characterization Tests

状态：`verified`

#### 范围

- 只补 Turnover Ledger 写路径 characterization tests。
- 锁定 tag selection PUT、bank-row-tags batch、relation extra PUT、confirm 和 withdraw 的当前 duplicate/stale/failure side-effect 行为。
- 不修改 production code，不实现 UoW，不改变真实 API 语义，不迁移 handler，不改 repository、worker、SQL migration、frontend、deployment 或生产配置。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。
- prompt 要求执行前读取状态机、prompt 库、Turnover discovery、PF-P051 write UoW 计划和现有 Turnover API/service tests。

#### 审查结论

- PF-P052 是 PF-P051 后合理的下一条 prompt：PF-P051 已确认写路径 side effects 和事务边界未收敛，不能直接进入 UoW 实现。
- PF-P052 保持 test-only 边界，用现有 `tests/test_turnover_ledger_api.py`、`tests/test_turnover_relation_service.py` 和测试 helper 锁定当前行为。
- PF-P052 明确禁止通过删除测试、放宽断言或修改业务代码来获得绿色。

#### 下一步

- PF-P052 已按自动工作流标记为 `verified`。
- 下一条建议 prompt：`PF-P053 - Turnover Ledger Write UoW Contract Tests`。
- PF-P053 应先定义目标契约测试，不应迁移真实 Turnover Ledger 写 API。

#### 执行结果

- 已执行 PF-P052。
- 仅修改 `tests/test_turnover_ledger_api.py` 以及本轮文档。
- 新增 `_FailingQueueRecorder` 测试 fake。
- 新增 tag selection PUT 队列失败 characterization：当前行为是 settings 已保存、read model 已 clear，随后 queue failure 抛出。
- 新增 bank-row-tags batch 队列失败 characterization：当前行为是 Bankdetail category facts 已保存，派生刷新尝试包含 Bankdetail/Workbench/Turnover，随后 queue failure 抛出。
- 新增 relation extra PUT persistence failure characterization：当前行为是 best-effort 成功、内存 extra 可读、read model clear 和 refresh enqueue 继续执行。
- 新增 confirm duplicate characterization：第一次成功后重复 confirm 返回 `relation_row_conflict`，不会第二次触发 Turnover refresh。
- 新增 confirm relation persistence failure characterization：当前 relation snapshot persistence failure 被 warning 吞掉，API 仍返回成功并继续 refresh enqueue。
- 新增 duplicate withdraw characterization：当前重复 withdraw 仍返回 200，追加第二条 withdraw audit，并再次触发 Turnover refresh。
- 未实现 UoW，未迁移 handler，未修改 production code、repository、runtime queue、worker、SQL migration、frontend、deployment 或生产配置。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，27 tests。

### PF-P053 - Turnover Ledger Write UoW Contract Tests

状态：`verified`

#### 范围

- 只新增 Turnover Ledger 写路径 UoW 目标契约测试。
- 不实现 `TurnoverLedgerWriteUnitOfWork`。
- 不迁移真实 Turnover Ledger 写 API。
- 不修改 production code、repository、runtime queue、worker、SQL migration、frontend、deployment 或生产配置。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。
- prompt 要求执行前读取 PF-P051/PF-P052 事实源和现有 Workbench UoW expectedFailure 策略。

#### 审查结论

- PF-P053 是 PF-P052 后合理的下一条 prompt：当前行为已经被 API-level characterization tests 锁定，下一步应先定义目标 UoW 契约。
- PF-P053 必须保持 contract-test-only，可以使用 `unittest.expectedFailure` 保存尚未实现的目标语义，默认 CI 不应失败。
- PF-P053 不得通过引入 production skeleton 或修改 handler 来让契约测试转绿。

#### 下一步

- PF-P053 已按自动工作流标记为 `verified`。
- 下一条建议 prompt：`PF-P054 - Turnover Ledger Minimal UoW Skeleton`。
- PF-P054 只应建立最小 skeleton 和 fake-port contract wiring，不应迁移真实 Turnover Ledger 写 API。

#### 执行结果

- 已执行 PF-P053。
- 新增 `tests/test_turnover_ledger_uow_contract.py`。
- 新增 7 个 `unittest.expectedFailure` 目标契约测试，覆盖：
  - confirm relation facts/audit/dirty/outbox 同事务；
  - confirm dirty/outbox failure rollback；
  - withdraw stale/duplicate precondition conflict；
  - relation extra outbox failure 不得 best-effort success；
  - tag selection outbox failure rollback；
  - bank-row-tags batch 通过 explicit Bankdetail port 并在 outbox failure 时 rollback；
  - UoW constructor 不接受 `Application` god object。
- 未实现 `TurnoverLedgerWriteUnitOfWork`，未迁移 handler，未修改 production code、repository、runtime queue、worker、SQL migration、frontend、deployment 或生产配置。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，7 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，27 tests。

### PF-P054 - Turnover Ledger Minimal UoW Skeleton

状态：`verified`

#### 范围

- 只新增最小 `TurnoverLedgerWriteUnitOfWork` skeleton。
- 只让 PF-P053 fake-port contract tests 从 expectedFailure 转为普通通过。
- 不接入真实 Turnover Ledger 写 API，不迁移 handler，不修改真实 repository/runtime queue/worker/SQL migration/frontend/deployment/生产配置。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。
- prompt 要求先运行 PF-P053 contract tests 观察 expected failures，再实现最小 skeleton 并移除对应 expectedFailure。

#### 审查结论

- PF-P054 是 PF-P053 后合理的下一步：目标契约已存在，下一步可以建立纯底座 skeleton，但不能碰真实写路径。
- PF-P054 应只实现 UoW 的事务 wrapper、stale precondition 调用、handler context、dirty/outbox writer 调用和 granular constructor dependency。

#### 下一步

- PF-P054 已按自动工作流标记为 `verified`。
- 下一条建议 prompt：`PF-P054-MG - Turnover Ledger Write UoW Foundation Cumulative Merge Gate`。
- PF-P054-MG 应覆盖 PF-P051 到 PF-P054 的完整 diff。

#### 执行结果

- 已执行 PF-P054。
- 新增 `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`。
- 实现最小 `TurnoverLedgerWriteUnitOfWork.run(command, handler)` skeleton：
  - 打开 `connection.transaction()`；
  - 在 handler 前执行 stale precondition；
  - 向 handler context 暴露 transaction 和 granular ports；
  - handler 成功后调用 transaction-bound dirty/outbox writer；
  - dirty/outbox failure 向外传播，交由 transaction context rollback；
  - constructor 只接收 granular dependencies，不接收 `Application` god object。
- `tests/test_turnover_ledger_uow_contract.py` 中 7 个目标测试已从 `expectedFailure` 转为普通通过。
- 未接入真实 Turnover Ledger 写 API，未修改 `server.py`、真实 repository、runtime queue、worker、SQL migration、frontend、deployment 或生产配置。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，7 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，27 tests。

### PF-P054-MG - Turnover Ledger Write UoW Foundation Cumulative Merge Gate

状态：`verified`

#### 范围

- Cumulative Merge Gate，覆盖 PF-P051 到 PF-P054 的完整 diff。
- 验证 Turnover Ledger 写路径 discovery、characterization tests、UoW contract tests 和 minimal skeleton 可以安全合入 `main`。
- 不执行 Traffic Gate，不部署，不访问生产，不修改真实外部服务或生产配置。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- PF-P054-MG 已按自动工作流标记为 `verified`。
- Merge commit：`1b03b1ed`。
- 已执行 `git push origin main`。
- 下一条建议 prompt：`PF-P055 - Turnover Ledger Write Facade / UoW Integration Planning`。

#### 执行结果

- 已在功能分支 `codex/turnover-ledger-write-uow-p051` 执行 scope、untracked、diff 和 targeted tests 检查。
- 已确认 diff 只包含 PF-P051 到 PF-P054 允许范围：
  - backend-refactor 文档；
  - `tests/test_turnover_ledger_api.py`；
  - `tests/test_turnover_ledger_uow_contract.py`；
  - `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`。
- 已确认没有 `server.py`、real repository、runtime queue、worker、SQL migration、frontend、deployment、Nginx 或生产配置 diff。
- 已合入 `main`。
- 已在 `main` 上复验。
- 已 push `origin/main`。

#### 验证

- `git status --short --branch`：Pass，合入前功能分支干净；合入后 `main` ahead 并已 push。
- `git ls-files --others --exclude-standard`：Pass。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract tests.test_turnover_ledger_api tests.test_turnover_relation_service tests.test_turnover_ledger_extra_service -v`：Pass，70 tests。

### PF-P055 - Turnover Ledger Write Facade / UoW Integration Planning

状态：`verified`

#### 范围

- 只做 Turnover Ledger 写路径真实 API 接入规划。
- 盘点哪些 handler 可以先接入 `TurnoverLedgerWriteUnitOfWork`，以及需要哪些 repository/port adapter。
- 不迁移真实 handler，不修改 production code，不改变 API 语义。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- PF-P055 已按自动工作流标记为 `verified`。
- 下一条建议 prompt：`PF-P056 - Turnover Ledger Relation Extra Write Facade Tests`。

#### 执行结果

- 已执行 PF-P055。
- 更新 `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`，新增 `Real API Integration Plan`。
- 已为 5 个写入口建立 readiness matrix：
  - relation extra PUT；
  - confirm relation；
  - withdraw relation；
  - tag selection PUT；
  - bank-row-tags batch。
- 规划结论：relation extra PUT 是第一候选真实接入点；bank-row-tags batch 风险最高，应最后处理。
- 未修改 production code、tests、handler、repository、runtime queue、worker、SQL migration、frontend、deployment 或生产配置。

#### 验证

- `git status --short --branch`：Pass。
- `git ls-files --others --exclude-standard`：Pass。
- `git diff --check`：Pass。
- `rg -n "Real API Integration Plan|Readiness Matrix|PF-P055|confirm|withdraw|bank-row-tags|tag selection|relation extra" docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md`：Pass。

### PF-P056 - Turnover Ledger Relation Extra Write Facade Tests

状态：`verified`

#### 范围

- 只为未来 `TurnoverLedgerWriteFacade.update_relation_extra()` 增加 facade-level tests。
- 使用 fake granular dependencies 和现有 `TurnoverLedgerWriteUnitOfWork` skeleton 锁定 relation extra PUT 的目标边界。
- 不迁移真实 handler，不修改 `server.py`，不改变真实 API 行为。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- PF-P056 已按自动工作流标记为 `verified`。
- 下一条建议 prompt：`PF-P057 - Turnover Ledger Relation Extra Write Facade Implementation`。

#### 验收标准

- 新增或更新的测试只覆盖 relation extra write facade 目标契约。
- 不接入真实 Turnover Ledger API，不修改 runtime queue、worker、SQL migration、frontend、deployment 或生产配置。
- 如生产 facade 尚不存在，允许使用 `unittest.expectedFailure` 锁定目标契约，但不得通过放宽断言隐藏真实失败。

#### 执行结果

- 已在 `tests/test_turnover_ledger_uow_contract.py` 增加 4 条 `TurnoverLedgerWriteFacade.update_relation_extra()` target contract tests。
- 4 条新增 tests 均为 `unittest.expectedFailure`，用于锁定未来 PF-P057 实现目标：
  - facade constructor 拒绝 `Application` god object；
  - relation extra write 与 dirty/outbox 在同一 UoW transaction；
  - dirty/outbox failure 回滚 extra write，不返回 best-effort success；
  - command/result 不携带 HTTP cookie/header/response/auth coupling。
- 未修改 `server.py`、真实 API、runtime queue、worker、SQL migration、frontend、deployment 或生产配置。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，11 tests，4 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，27 tests。

### PF-P057 - Turnover Ledger Relation Extra Write Facade Implementation

状态：`verified`

#### 范围

- 新增最小 `TurnoverLedgerWriteFacade`，只覆盖 `update_relation_extra()`。
- 将 PF-P056 的 4 条 relation extra facade target tests 从 `expectedFailure` 转为普通通过。
- 不接入真实 `server.py` handler，不改变真实 API 行为。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- PF-P057 已按自动工作流标记为 `verified`。
- 下一条建议 prompt：`PF-P058 - Turnover Ledger Relation Extra Handler Integration Characterization`。

#### 验收标准

- 生产代码只允许新增或最小修改 Turnover Ledger write facade 相关 service 文件。
- `tests/test_turnover_ledger_uow_contract.py` 只允许移除 PF-P056 4 条 tests 的 `expectedFailure`，不得弱化断言。
- `server.py`、runtime queue、worker、SQL migration、frontend、deployment 和生产配置无 diff。

#### 执行结果

- 新增 `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`。
- 实现最小 `TurnoverLedgerWriteFacade.update_relation_extra()`：
  - constructor 只接收 `uow`；
  - 不接收 `Application`；
  - 不读取 HTTP cookie/header；
  - 不 import `app.auth`；
  - 通过现有 `TurnoverLedgerWriteUnitOfWork` 写 extra fact 并 enqueue Turnover dirty/outbox。
- `tests/test_turnover_ledger_uow_contract.py` 中 PF-P056 的 4 条 tests 已移除 `expectedFailure` 并转为普通通过。
- 未修改 `server.py`、真实 handler、runtime queue、worker、SQL migration、frontend、deployment 或生产配置。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，11 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，27 tests。

### PF-P058 - Turnover Ledger Relation Extra Handler Integration Characterization

状态：`verified`

#### 范围

- 只补真实 `PUT /api/turnover-ledger/relations/{id}/extra` handler 接入 facade 前的 characterization。
- 聚焦 queue/refresh failure、persistence side effect、response/error 当前行为。
- 不迁移真实 handler，不修改 `server.py`。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- PF-P058 已按自动工作流标记为 `verified`。
- 下一条建议 prompt：`PF-P059 - Turnover Ledger Relation Extra Handler Minimal Wiring`。

#### 验收标准

- 新增测试只在 `tests/test_turnover_ledger_api.py` 锁定 relation extra handler 当前行为。
- 不修改 production code、runtime queue、worker、SQL migration、frontend、deployment 或生产配置。

#### 执行结果

- 在 `tests/test_turnover_ledger_api.py` 新增 `test_relation_extra_queue_failure_happens_after_extra_update_and_read_model_clear`。
- 已锁定当前真实 handler 行为：
  - refresh queue failure 抛出 `RuntimeError("queue unavailable")`；
  - extra 已写入内存 service，后续 GET 可读；
  - read model clear 已发生；
  - queue attempt 为 `("turnover_ledger", "all", "turnover_relation_extra_changed")`。
- 未修改 production code、`server.py`、runtime queue、worker、SQL migration、frontend、deployment 或生产配置。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，28 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，11 tests。

### PF-P059 - Turnover Ledger Relation Extra Handler Wiring Readiness / Adapter Boundary

状态：`verified`

#### 范围

- 只审计 relation extra handler 接入 facade/UoW 前所需的真实 adapter 边界。
- 明确是否已有可用 PostgreSQL transaction connection、extra repository adapter 和 dirty/outbox writer adapter。
- 不修改 production code，不迁移 `server.py` handler。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- PF-P059 已按自动工作流标记为 `verified`。
- 下一条建议 prompt：`PF-P060 - Turnover Ledger Relation Extra Repository and Dirty Outbox Adapter Contracts`。

#### 验收标准

- 文档明确能否安全进行真实 handler wiring。
- 如果缺少真实 transaction boundary，必须将下一步调整为 adapter/repository skeleton，而不是直接接入 handler。

#### 执行结果

- 已更新 `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`，新增 `Relation Extra Handler Wiring Readiness`。
- 结论：不允许直接 wiring。
- 已确认可复用：
  - `PostgresConnection.transaction()`；
  - Workbench UoW 的 runtime connection lookup 模式；
  - `queue_repository.enqueue_read_model_refresh_in_transaction(...)`；
  - `PostgresWorkbenchRepository(transaction)` 的现有 Turnover extras snapshot 能力。
- 已确认缺口：
  - 缺少细粒度 `save_extra(extra, *, transaction)` repository port；
  - 缺少 Turnover-specific dirty/outbox writer adapter；
  - 缺少保持当前 `row` response shape 的 relation row provider；
  - 不得用 fake/no-op production transaction 假装完成 UoW 接入。

#### 验证

- `git status --short --branch`：Pass。
- `git ls-files --others --exclude-standard`：Pass。
- `git diff --check`：Pass。
- `rg -n "Relation Extra Handler Wiring Readiness|PF-P059|no-op transaction|fake transaction|adapter" docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md`：Pass。

### PF-P060 - Turnover Ledger Relation Extra Repository and Dirty Outbox Adapter Contracts

状态：`verified`

#### 范围

- 增加 relation extra repository adapter 与 Turnover dirty/outbox writer adapter 的 contract tests 和最小 skeleton。
- 不修改 `server.py`，不接入真实 handler。
- 不迁移 confirm、withdraw、tag selection 或 bank-row-tags。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- PF-P060 已按自动工作流标记为 `verified`。
- 下一条建议 prompt：`PF-P061 - Turnover Ledger Relation Extra Row Provider and Handler Wiring Plan`。

#### 验收标准

- adapter 使用 transaction-bound dependency，不调用非事务 queue enqueue。
- repository adapter 不依赖 `Application`。
- 默认 targeted tests 通过。

#### 执行结果

- 新增 `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`。
- 实现：
  - `TurnoverLedgerExtraRepositoryAdapter`；
  - `TurnoverLedgerDirtyOutboxWriter`。
- 在 `tests/test_turnover_ledger_uow_contract.py` 新增 adapter contract tests，验证：
  - repository adapter 使用传入 transaction；
  - repository adapter 拒绝 `Application` god object；
  - dirty/outbox writer 逐个 scope 调用 `enqueue_read_model_refresh_in_transaction(...)`；
  - dirty/outbox writer 拒绝只有非事务 enqueue 的 queue repository。
- 未修改 `server.py`、真实 handler、runtime queue、worker、SQL migration、frontend、deployment 或生产配置。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，15 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，28 tests。

### PF-P061 - Turnover Ledger Relation Extra Row Provider Contract

状态：`verified`

#### 范围

- 给 `TurnoverLedgerWriteFacade.update_relation_extra()` 增加 row provider contract，以保持真实 API 当前 `row` response shape。
- 不修改 `server.py`，不接入真实 handler。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- PF-P061 已按自动工作流标记为 `verified`。
- 下一条建议 prompt：`PF-P062 - Turnover Ledger Relation Extra Handler Minimal Wiring`，除非先做 cumulative MG。

#### 验收标准

- facade 可通过细粒度 row provider 返回 `row`。
- row provider 不依赖 `Application`，不读取 HTTP。
- targeted tests 通过。

#### 执行结果

- `TurnoverLedgerWriteFacade` 支持可选 `row_provider`。
- 新增 contract test 验证：
  - row provider 接收 `relation_id` 和 `extra`；
  - facade result 包含 `extra` 和 `row`；
  - result 不携带 HTTP response/status/cookie/header/auth coupling。
- 未修改 `server.py`、真实 handler、runtime queue、worker、SQL migration、frontend、deployment 或生产配置。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，16 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，28 tests。

### PF-P062 - Turnover Ledger Relation Extra Normalization Boundary Contract

状态：`verified`

#### 范围

- 先补齐 `TurnoverLedgerWriteFacade` 的 relation extra normalization boundary。
- 确保 facade 保存的是 normalized extra，不是 raw payload。
- 明确真实 handler wiring 被推迟，避免绕过现有 API validation/normalization。
- 不迁移 confirm、withdraw、tag selection 或 bank-row-tags。
- 不修改 `server.py`。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。
- 原 handler wiring 草案已被代码事实修正：现有 `TurnoverLedgerExtraService.upsert()` 会做默认值合并、金额/日期校验和格式化，当前 facade 直接保存 raw payload，不能直接接入 handler。

#### 下一步

- 生成并审查 `PF-P063 - Turnover Ledger Relation Extra Pure Normalizer Adapter`。

#### 验收标准

- `TurnoverLedgerWriteFacade` 可通过细粒度 normalizer 保存 normalized extra。
- normalizer validation error 必须阻止 repository save 和 dirty/outbox enqueue。
- UoW contract tests 必须通过。
- 现有 28 条 Turnover API tests 必须通过。

#### 执行结果

- `TurnoverLedgerWriteFacade` 新增可选 `extra_normalizer` 细粒度依赖。
- `update_relation_extra()` 现在保存 normalized extra，并将 normalized extra 传给 row provider。
- 新增 contract tests 覆盖：
  - raw payload 不会直接保存；
  - row provider 收到 normalized extra；
  - normalizer validation error 会阻止 transaction、repository save 和 dirty/outbox enqueue。
- 未修改 `server.py`，未接入真实 handler。

#### 验证

- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，19 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，28 tests。

#### 下一条 Prompt 上下文

PF-P062 只建立 facade normalization boundary。真实 handler wiring 前还缺一个 pure normalizer adapter：必须复用现有 `TurnoverLedgerExtraService` 的 validation/defaulting 规则，但不能调用会提前修改内存状态的 `upsert()` 作为 facade normalizer。PF-P063 应先建立该 pure normalizer adapter 或明确等价方案，然后再考虑 handler minimal wiring。

### PF-P063 - Turnover Ledger Relation Extra Pure Normalizer Adapter

状态：`verified`

#### 范围

- 为 relation extra 建立可复用现有 validation/defaulting 规则的 pure normalizer。
- normalizer 不得修改内存状态，不得持久化，不得 enqueue。
- 不修改 `server.py`，不接真实 handler。
- 不迁移 confirm、withdraw、tag selection 或 bank-row-tags。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- 生成并审查 `PF-P064 - Turnover Ledger Relation Extra Handler Minimal Wiring`。

#### 验收标准

- `TurnoverLedgerExtraService` 或 adapter 暴露 pure normalize 能力，行为与现有 `upsert()` 归一化一致但无状态副作用。
- `TurnoverLedgerWriteFacade(extra_normalizer=...)` 可使用该 adapter 保存 normalized extra。
- UoW contract tests、Turnover API tests 必须通过。

#### 执行结果

- `TurnoverLedgerExtraService` 新增 `normalize_update(...)` pure 方法，复用现有 validation/defaulting/formatting 规则但不修改 snapshot。
- `TurnoverLedgerExtraNormalizerAdapter` 可作为 `TurnoverLedgerWriteFacade(extra_normalizer=...)` 的细粒度依赖。
- 新增 tests 覆盖 pure normalizer 无状态副作用、adapter 注入 facade、invalid payload 不保存不 enqueue。
- 未修改 `server.py`，未接入真实 handler。

#### 验证

- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，22 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_extra_service -v`：Pass，10 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，28 tests。

#### 下一条 Prompt 上下文

PF-P063 已补齐 handler wiring 前的 pure normalizer。PF-P064 可以只做 `PUT /api/turnover-ledger/relations/{id}/extra` 的最小 handler wiring：仅在 PostgreSQL runtime 且存在 transaction-bound queue 时创建 facade；非 PostgreSQL/依赖不齐继续 legacy path；不得迁移其它 Turnover Ledger 写 API。

### PF-P064 - Turnover Ledger Relation Extra Handler Minimal Wiring

状态：`verified`

#### 范围

- 只让 `PUT /api/turnover-ledger/relations/{id}/extra` 在 PostgreSQL runtime 且依赖齐备时走 `TurnoverLedgerWriteFacade`。
- 非 PostgreSQL runtime 或依赖不齐时保持 legacy path。
- 不迁移 confirm、withdraw、tag selection 或 bank-row-tags。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- 生成并审查 `PF-P064-MG - Turnover Ledger Relation Extra UoW Cumulative Merge Gate`。

#### 验收标准

- `server.py` diff 只限 relation extra handler wiring 和必要 helper/import。
- 现有 28 条 Turnover API tests、UoW contract tests、Extra service tests 必须通过。

#### 执行结果

- `server.py` 新增 relation extra facade helper 和 row provider helper。
- `PUT /api/turnover-ledger/relations/{id}/extra` 在 helper 返回 facade 时走 `TurnoverLedgerWriteFacade`；否则保持 legacy path。
- PostgreSQL runtime helper 需要真实 `state_store._connection` 和 transaction-bound queue repository；依赖不齐时返回 `None`。
- 新增 API test 验证 facade override path 不执行 legacy best-effort persistence、read model clear 或非事务 enqueue。
- 未迁移 confirm、withdraw、tag selection、bank-row-tags。

#### 验证

- `git diff --check`：Pass。
- `git ls-files --others --exclude-standard`：Pass，无输出。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，29 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，22 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_extra_service -v`：Pass，10 tests。

#### 下一条 Prompt 上下文

PF-P055 到 PF-P064 已形成可合并的 relation extra UoW integration slice。下一步生成 cumulative MG，必须检查完整 branch diff、untracked files、scope 白名单、文档状态，并在 main 上复验后再 push。

### PF-P064-MG - Turnover Ledger Relation Extra UoW Cumulative Merge Gate

状态：`verified`

#### 范围

- 覆盖当前分支中 PF-P055 到 PF-P064 的完整 diff。
- 只允许 Turnover Ledger relation extra UoW/facade/adapter/handler wiring、相关 tests 和文档状态机改动。
- 不触发 Traffic Gate，不部署，不访问生产，不修改 Nginx/生产配置。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- 执行 PF-P064-MG。

#### 验收标准

- branch scope 与白名单一致，无 untracked 临时文件。
- targeted tests 在功能分支通过。
- merge 到最新 main 后在 main 上复验通过。
- main 验证失败则停止，不得 push。

#### 分支预检结果

- `git status --short --branch`：Pass，位于 `codex/turnover-ledger-write-integration-p055`。
- `git ls-files --others --exclude-standard`：Pass，无输出。
- `git diff --check`：Pass。
- `git diff --name-status main...HEAD`：Pass，只包含 MG 白名单文件。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，29 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，22 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_extra_service -v`：Pass，10 tests。

#### main 合入与复验结果

- 已通过 `--no-ff` merge 合入 `main`。
- `git status --short --branch`：Pass，`main...origin/main [ahead 23]`。
- `git ls-files --others --exclude-standard`：Pass，无输出。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，29 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，22 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_extra_service -v`：Pass，10 tests。
- 未执行 Traffic Gate、部署、生产访问、Nginx 或生产配置修改。

#### 下一条 Prompt 上下文

Relation extra UoW integration slice 已合入 main。push 后必须从最新 main 新建下一条 `codex/` 分支。Turnover Ledger 写路径剩余候选包括 tag selection、bank-row-tags、confirm/withdraw 关系写路径的 UoW 收敛；下一条 prompt 应基于 `turnover-ledger-write-uow-plan.md` 选择下一个最小写路径切片。

### PF-P065 - Turnover Ledger Tag Selection Settings Port Discovery and Planning

状态：`verified`

#### 范围

- 只盘点 `PUT /api/turnover-ledger/tag-selection` 写路径。
- 聚焦 AppSettings save/audit 与 Turnover dirty/outbox 同事务所需的 settings port / repository seam。
- 不修改业务代码，不迁移 handler，不实现 UoW。
- 不触碰 bank-row-tags、confirm、withdraw 或其它模块。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- 生成并审查 `PF-P066 - Turnover Ledger Tag Selection Characterization and Settings Port Contract Tests`。

#### 验收标准

- 文档明确 tag selection 当前调用链、事务断点、现有测试覆盖和下一步 characterization/contract test prompt。
- 不产生 production code diff。

#### 执行结果

- 已盘点 handler -> AppSettingsService -> state_store/Postgres settings repository -> audit -> read model refresh 调用链。
- 已确认当前事务断点：
  - settings save 在 `AppSettingsService.update_turnover_ledger_tag_selection(...)` 内完成；
  - read model clear/enqueue 在 handler 后置执行；
  - PostgreSQL `PostgresOpsTaxEtcRepository.save_settings(...)` 没有 transaction 参数；
  - queue failure 当前发生在 settings save 之后。
- 已确认现有 tests 覆盖成功、version conflict、invalid tag 和 queue failure after save。
- 未修改 production code 或 tests。

#### 验证

- `git diff --check`：Pass。
- `git ls-files --others --exclude-standard`：Pass，无输出。
- 文档 `rg` 检查：Pass。

#### 下一条 Prompt 上下文

PF-P066 应先做 characterization / contract tests：锁定 tag selection 当前 API 行为，并增加 settings port / pure normalization target contracts。不得直接实现 production UoW 或迁移 handler。

### PF-P066 - Turnover Ledger Tag Selection Characterization and Settings Port Contract Tests

状态：`verified`

#### 范围

- 增强 tag selection 当前行为 characterization tests。
- 增加 settings port / pure normalization target contract tests。
- 不修改 production code，不迁移 handler，不实现 UoW。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- 生成并审查 `PF-P067 - Turnover Ledger Tag Selection Pure Settings Normalizer Skeleton`。

#### 验收标准

- tests 锁定当前 queue failure after save 行为和 future UoW target contract。
- 默认 test suite 必须保持绿色；未实现目标可使用 `unittest.expectedFailure`，但必须解释后续转绿路径。

#### 执行结果

- 强化 `test_turnover_ledger_tag_selection_get_put_and_version_conflict`：
  - success 只 enqueue 一次并 clear 一次；
  - conflict 和 invalid tag 不额外 enqueue/clear。
- 新增 `test_tag_selection_pure_normalizer_returns_next_selection_without_mutating_settings_snapshot` expectedFailure：
  - 锁定未来 `AppSettingsService.normalize_turnover_ledger_tag_selection_update` pure target。
- 未修改 production code。

#### 验证

- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，29 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，23 tests，1 expectedFailure。

#### 下一条 Prompt 上下文

PF-P067 应实现最小 pure settings normalizer skeleton，让 PF-P066 的 expectedFailure 转绿。不得迁移 handler，不得实现 transaction-bound settings repository 或 UoW production wiring。

### PF-P067 - Turnover Ledger Tag Selection Pure Settings Normalizer Skeleton

状态：`verified`

#### 范围

- 在 `AppSettingsService` 中建立 pure tag selection normalizer。
- 将 PF-P066 expectedFailure 转为普通通过测试并补强行为断言。
- 不迁移 handler，不实现 transaction-bound settings repository，不接 UoW production wiring。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- 生成并审查 `PF-P068 - Turnover Ledger Tag Selection Settings Port / Adapter Skeleton`。

#### 验收标准

- pure normalizer 复用现有 validation/version 规则，返回 next selection/audit metadata，不保存、不 mutate `_snapshot`。
- 默认 tests 绿色，不再有本 slice 的 expectedFailure。

#### 执行结果

- `AppSettingsService.normalize_turnover_ledger_tag_selection_update(...)` 已实现。
- `update_turnover_ledger_tag_selection(...)` 已复用 pure normalizer，同时保留当前 save/configure/audit 行为。
- PF-P066 expectedFailure 已转为普通通过测试，并补强 next selection、audit metadata、public payload、snapshot 不变和真实 update 保存行为断言。

#### Verification

- `git status --short --branch`: Pass，仅 PF-P067 允许文件变更。
- `git ls-files --others --exclude-standard`: Pass，无未跟踪文件。
- `git diff --check`: Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`: Pass，23 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`: Pass，29 tests。

#### Commit

- `2195f2fd feat(turnover-ledger): add tag selection pure normalizer`

### PF-P068 - Turnover Ledger Tag Selection Settings Port / Adapter Skeleton

状态：`verified`

#### 范围

- 建立 tag selection settings port / adapter skeleton，让未来 UoW 能把 settings fact save 纳入同一 transaction。
- 只允许 fake/in-memory contract 与最小 production adapter skeleton。
- 不迁移 handler，不接入 production UoW，不改变当前 queue failure split-brain 行为。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- 生成并审查 `PF-P069 - Turnover Ledger Tag Selection Transaction-bound Repository Writer`。

#### 验收标准

- UoW contract tests 覆盖 settings port 使用 supplied transaction 保存 next snapshot。
- Adapter 只接收细粒度 repository factory / writer，不接收 `Application` 或 state store god object。
- 默认 Turnover API tests 保持绿色。

#### 执行结果

- 新增 `TurnoverLedgerTagSelectionSettingsAdapter` skeleton。
- 新增 fake UoW contract，锁定 settings port 与 dirty/outbox 共用 supplied transaction。
- 新增 adapter contract，锁定 `repository_factory(transaction)` 保存 settings snapshot 和 audit metadata。
- 未修改 `server.py`，未迁移 handler，未改变现有 tag selection 生产路径。

#### Verification

- `git status --short --branch`: Pass，仅 PF-P068 允许文件变更。
- `git ls-files --others --exclude-standard`: Pass，无未跟踪文件。
- `git diff --check`: Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`: Pass，26 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`: Pass，29 tests。

#### Commit

- `0920b5b1 feat(turnover-ledger): add tag selection settings adapter`

### PF-P069 - Turnover Ledger Tag Selection Transaction-bound Repository Writer

状态：`verified`

#### 范围

- 为 `app.app_settings` 增加 transaction-bound writer/repository seam，供 PF-P068 adapter 使用。
- 只允许修改 repository/writer 和 contract tests。
- 不迁移 handler，不接入 production UoW，不改变当前 tag selection API 行为。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- 生成并审查 `PF-P070 - Turnover Ledger Tag Selection UoW Integration Planning`。

#### 验收标准

- 事务绑定 writer 使用 supplied transaction 执行 `app.app_settings` upsert。
- 现有 `save_settings(...)` 行为不变。
- 默认 Turnover API tests 保持绿色。

#### 执行结果

- `PostgresOpsTaxEtcRepository.save_settings_in_transaction(...)` 和 `save_app_settings_in_transaction(...)` 已增加。
- `save_settings(...)` 复用同一 SQL helper，保持现有 public behavior。
- `TurnoverLedgerTagSelectionSettingsAdapter` 可通过 `repository_factory(transaction)` 调用 `save_app_settings(...)` 或 `save_settings("app_settings", ...)`。
- durable audit persistence 仍是后续缺口；本轮只保留 audit metadata 传递，不宣称 audit 已同事务落库。

#### Verification

- `git status --short --branch`: Pass，仅 PF-P069 允许文件变更。
- `git ls-files --others --exclude-standard`: Pass，无未跟踪文件。
- `git diff --check`: Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`: Pass，27 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`: Pass，29 tests。

#### Commit

- `eba61433 feat(turnover-ledger): add transaction-bound settings writer`

### PF-P070 - Turnover Ledger Tag Selection UoW Integration Planning

状态：`verified`

#### 范围

- 规划 tag selection handler 迁移到 UoW 前的测试、adapter wiring、durable audit 缺口和风险。
- 只更新文档，不改生产逻辑，不新增实现测试。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- 生成并审查 `PF-P071 - Turnover Ledger Tag Selection UoW Compatibility and Target Tests`。

#### 验收标准

- 输出 tag selection UoW integration sequence。
- 明确下一条实现/测试 prompt。
- 明确 durable audit 处理策略和当前不可伪装完成的范围。

#### 执行结果

- 已记录 current legacy runtime sequence：handler auth/JSON -> settings save/in-memory audit -> read model clear -> queue enqueue。
- 已记录 target UoW runtime sequence：handler HTTP mapping -> facade pure normalize -> UoW settings port -> dirty/outbox same transaction。
- 已明确 PF-P071 必须先补 compatibility/target tests，不得直接迁移 handler。
- durable audit persistence 明确保留为后续 Platform / Audit 缺口。

#### Verification

- `git status --short --branch`: Pass，仅 PF-P070 文档文件变更。
- `git ls-files --others --exclude-standard`: Pass，无未跟踪文件。
- `git diff --check`: Pass。
- `rg -n "PF-P070|tag selection UoW integration|durable audit|PF-P071" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`: Pass。

#### Commit

- `471c43aa docs(turnover-ledger): plan tag selection uow migration`

### PF-P071 - Turnover Ledger Tag Selection UoW Compatibility and Target Tests

状态：`verified`

#### 范围

- 只补 tag selection UoW 迁移前的 compatibility / target tests。
- 不修改 production code，不迁移 handler。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- 生成并审查 `PF-P072 - Turnover Ledger Tag Selection Facade Skeleton`。

#### 验收标准

- 当前 API compatibility tests 继续绿色。
- 未来 UoW target tests 明确区分普通通过和 `expectedFailure`。
- 默认 test suite 绿色。

#### 执行结果

- 补强 tag selection success response shape 断言，覆盖 `version`、`selected_tag_codes` 和 `active_tags` 关键字段。
- 保留 version conflict `409`、invalid tag `400` 和 no extra enqueue/clear side effect 的现有断言。
- 新增 2 个 future handler target tests，并以 `unittest.expectedFailure` 保持默认 CI 绿色：
  - queue/outbox failure 后 settings save 应回滚；
  - future UoW path 成功时不应直接调用 read model clear。
- 补强 fake UoW tag selection result 的 HTTP 解耦断言。

#### Verification

- `git status --short --branch`: Pass，仅 PF-P071 允许文件变更。
- `git ls-files --others --exclude-standard`: Pass，无未跟踪文件。
- `git diff --check`: Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`: Pass，31 tests，2 expectedFailure。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`: Pass，27 tests。

#### Commit

- `051f7476 test(turnover-ledger): lock tag selection uow targets`

### PF-P072 - Turnover Ledger Tag Selection Facade Skeleton

状态：`verified`

#### 范围

- 在 `TurnoverLedgerWriteFacade` 中新增 tag selection service-layer method。
- 使用 PF-P067 pure normalizer 和 UoW `settings_port`。
- 不迁移 `server.py` handler。

#### 已生成 Prompt

- 已写入 `docs/architecture/backend-refactor/refactor-prompts.md`。
- prompt 正文以 `/goal` 开头。

#### 下一步

- 生成并审查 `PF-P073 - Turnover Ledger Tag Selection Handler UoW Wiring`。

#### 验收标准

- UoW contract tests 覆盖 facade 使用 pure normalizer、settings port、dirty/outbox。
- relation extra facade 现有 tests 保持绿色。
- API handler expectedFailure 仍保留，直到 PF-P073 handler wiring。

#### 执行结果

- `TurnoverLedgerWriteFacade.update_tag_selection(...)` 已新增。
- facade 使用 injected `tag_selection_normalizer` 或 `app_settings_service.normalize_turnover_ledger_tag_selection_update(...)`。
- UoW handler 内调用 `context.settings_port.save_tag_selection_settings(...)` 并返回 service-layer `public_payload`。
- 新增 facade success、outbox rollback、normalizer error prevents UoW side effects tests。
- PF-P071 API handler target expectedFailure 仍保留，等待 PF-P073 handler wiring。

#### Verification

- `git status --short --branch`: Pass，仅 PF-P072 允许文件变更。
- `git ls-files --others --exclude-standard`: Pass，无未跟踪文件。
- `git diff --check`: Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`: Pass，30 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`: Pass，31 tests，2 expectedFailure。

### PF-P073 - Turnover Ledger Tag Selection Handler UoW Wiring

状态：`verified`

#### 范围

- 只迁移 `PUT /api/turnover-ledger/tag-selection` 到 `TurnoverLedgerWriteFacade.update_tag_selection(...)`。
- 将 PF-P071 的 2 个 handler target `expectedFailure` 转为普通通过测试。
- 不迁移其它 Turnover Ledger 写路径，不执行 Traffic Gate。

#### 执行结果

- `server.py` handler 现在优先构造 tag selection write facade；PostgreSQL path 使用 transaction-bound settings adapter 和 dirty/outbox writer。
- Local state store path 增加最小 transaction shim，queue failure 时恢复 normalized app settings snapshot。
- 成功路径不再直接调用 `_clear_turnover_ledger_read_model_best_effort()`，refresh 由 UoW dirty/outbox writer 负责。
- `tests/test_turnover_ledger_api.py` 中 2 个 PF-P071 handler target tests 已移除 `unittest.expectedFailure` 并转为普通通过。

#### Verification

- `git status --short --branch`: Pass，仅 PF-P073 允许文件变更。
- `git ls-files --others --exclude-standard`: Pass，无未跟踪文件。
- `git diff --check`: Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`: Pass，31 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`: Pass，30 tests。

#### 下一步

- 生成 cumulative MG，覆盖 PF-P065 到 PF-P073 的 tag selection UoW slice。

### PF-P074 - Turnover Ledger Relation Extra UoW Completion Tests

状态：`verified`

#### 范围

- 只补 relation extra UoW completion 前的 API-level characterization / target tests。
- 不修改 production code。
- 不迁移 handler。

#### 执行结果

- 新增 2 个 future target tests，并以 `unittest.expectedFailure` 保持默认 CI 绿色：
  - queue/outbox failure 应回滚 relation extra save；
  - successful UoW path 不应直接 clear read model。
- 补强 facade override response shape 断言，确保 `{"extra": ..., "row": ...}` 仍由 handler 返回。
- 保留 current legacy queue failure behavior test，继续记录 legacy path 当前会先保存 extra、clear read model，再遇到 queue failure。

#### Verification

- `git status --short --branch`: Pass，仅 PF-P074 允许文件变更。
- `git ls-files --others --exclude-standard`: Pass，无未跟踪文件。
- `git diff --check`: Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`: Pass，33 tests，2 expectedFailure。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`: Pass，30 tests。

#### 下一步

- 生成并审查 `PF-P075 - Turnover Ledger Relation Extra Handler UoW Completion`。

### PF-P075 - Turnover Ledger Relation Extra Handler UoW Completion

状态：`verified`

#### 范围

- 只完成 `PUT /api/turnover-ledger/relations/{id}/extra` 的 local/dev/test UoW path。
- 保持 PostgreSQL transaction-bound path 不降级。
- 不迁移 tag selection、bank row tags、confirm、withdraw 或其它 Turnover 写路径。

#### 执行结果

- `_turnover_ledger_relation_extra_write_facade()` 现在在 local/dev/test path 中也会返回 `TurnoverLedgerWriteFacade`。
- 新增 local relation extra transaction shim：
  - queue/outbox failure 时恢复 in-memory extra snapshot；
  - queue/outbox failure 时恢复 local state store extras snapshot；
  - 成功路径通过 local dirty/outbox writer enqueue refresh，不再直接 clear read model。
- 新增 local extra repository wrapper，只向 facade/UoW 暴露细粒度 `save_extra(...)` 能力。
- PF-P074 的 2 个 relation extra target tests 已移除 `unittest.expectedFailure` 并转为普通通过。
- 保留 legacy fallback behavior test，通过强制 facade unavailable 继续锁定旧路径行为。

#### Verification

- `git status --short --branch`: Pass，仅 PF-P075 允许文件变更。
- `git ls-files --others --exclude-standard`: Pass，无未跟踪文件。
- `git diff --check`: Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`: Pass，33 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`: Pass，30 tests。
- `rg -n "relation_extra|turnover_relation_extra_changed|_turnover_ledger_relation_extra_write_facade|_local_turnover_ledger|clear_turnover_ledger_read_model|expectedFailure|PF-P075" backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py docs/architecture/backend-refactor`: Pass。

#### 下一步

- 生成并审查 `PF-P075-MG - Turnover Ledger Relation Extra UoW Cumulative Merge Gate`，统一覆盖 PF-P074 + PF-P075。

### PF-P075-MG - Turnover Ledger Relation Extra UoW Cumulative Merge Gate

状态：`verified`

#### 范围

- 覆盖 PF-P074 + PF-P075 的 relation extra UoW completion slice。
- 只执行 Merge Gate，不执行 Traffic Gate、部署、Nginx 修改或生产访问。

#### 执行结果

- 分支 `codex/turnover-ledger-next-uow-slice-p074` 已合入 `main`。
- 合入前后 Turnover Ledger targeted tests 均通过。
- PF-P074 的 relation extra target tests 已转绿并进入 main。

#### Verification on main

- `git status --short --branch`: Pass，`main...origin/main [ahead 6]`（push 前）。
- `git ls-files --others --exclude-standard`: Pass，无未跟踪文件。
- `git diff --check HEAD~1..HEAD`: Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`: Pass，33 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`: Pass，30 tests。

#### 下一步

- 执行 `git push origin main`。
- push 后必须从最新 `main` 新建 `codex/` 分支，再生成下一条 Turnover Ledger 写路径 prompt。

### PF-P076 - Turnover Ledger Bank Row Tags UoW Compatibility and Target Tests

状态：`verified`

#### 范围

- 只补 `POST /api/turnover-ledger/bank-row-tags/batch` 的 compatibility / target tests。
- 不修改 production code。
- 不迁移 handler。

#### 执行结果

- 新增 2 个 future target tests，并以 `unittest.expectedFailure` 保持默认 CI 绿色：
  - queue/outbox failure 应回滚 bank category save；
  - successful UoW path 不应直接 clear read model。
- 新增普通通过测试，锁定 bank-row-tags success path 必须刷新 Bankdetail affected month、Workbench affected month 和 Turnover Ledger all scope。
- 保留 current queue failure split-brain behavior test，继续记录当前会先保存 category、重建 relation、clear read model，再遇到 queue failure。

#### Verification

- `git status --short --branch`: Pass，仅 PF-P076 允许文件变更。
- `git ls-files --others --exclude-standard`: Pass，无未跟踪文件。
- `git diff --check`: Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`: Pass，36 tests，2 expectedFailure。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`: Pass，30 tests。
- `rg -n "bank-row-tags|bank_row_tag|bank_row_tags|expectedFailure|PF-P076|_handle_api_turnover_ledger_bank_row_tags_batch|_clear_turnover_ledger_read_model_best_effort" tests/test_turnover_ledger_api.py docs/architecture/backend-refactor`: Pass。

#### 下一步

- 生成并审查 `PF-P077 - Turnover Ledger Bank Row Tags Facade / Port Skeleton`。

### PF-P077 - Turnover Ledger Bank Row Tags Facade / Port Skeleton

状态：`verified`

#### 范围

- 只建立 bank-row-tags service-layer facade / UoW skeleton。
- 不修改 `server.py`。
- 不迁移真实 handler。

#### 执行结果

- `TurnoverLedgerWriteCommand` 增加 `refresh_requests`，保持无显式 refresh request 时的默认 `turnover_ledger` 行为兼容。
- `TurnoverLedgerWriteUnitOfWork.run(...)` 支持显式 multi-refresh requests。
- `TurnoverLedgerWriteFacade.update_bank_row_tags_batch(...)` 调用 `context.bankdetail_port.apply_turnover_category_updates(...)` 并返回 service-layer payload。
- 新增 UoW contract tests 覆盖 bankdetail port 调用、dirty/outbox rollback 和 Bankdetail/Workbench/Turnover 三类 refresh requests。
- 未修改真实 API handler；PF-P076 的 2 个 API target tests 仍为 expectedFailure。

#### Verification

- `git status --short --branch`: Pass，仅 PF-P077 允许文件变更。
- `git ls-files --others --exclude-standard`: Pass，无未跟踪文件。
- `git diff --check`: Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`: Pass，33 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`: Pass，36 tests，2 expectedFailure。
- `rg -n "update_bank_row_tags_batch|bankdetail_port|refresh_requests|bank_transaction_category_changed|workbench_scope_invalidated|PF-P077" backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py tests/test_turnover_ledger_uow_contract.py docs/architecture/backend-refactor`: Pass。

#### 下一步

- 生成并审查 `PF-P078 - Turnover Ledger Bank Row Tags Handler UoW Wiring`，只迁移 bank-row-tags handler。

### PF-P078 - Turnover Ledger Bank Row Tags Handler UoW Wiring

状态：`verified`

#### 范围

- 只迁移 `POST /api/turnover-ledger/bank-row-tags/batch` 的 local/dev/test path 到 `TurnoverLedgerWriteFacade.update_bank_row_tags_batch(...)`。
- 将 PF-P076 的 2 个 bank-row-tags API target tests 从 `unittest.expectedFailure` 转为普通通过。
- 保留 legacy split-brain behavior test，并通过显式 facade fallback seam 覆盖旧路径。
- 不迁移 relation extra、tag selection、confirm/cancel、withdraw、No OA、Bankdetail 独立 API 或其它 Turnover 写路径。

#### 执行摘要

- 新增 `_turnover_ledger_bank_row_tags_write_facade()`，默认 local/dev/test path 使用 `TurnoverLedgerWriteFacade` + `TurnoverLedgerWriteUnitOfWork`。
- 新增 local transaction shim，queue/outbox failure 时恢复 bank transaction categories snapshot 与 turnover relations snapshot，并回写 local state store。
- 新增 local bankdetail port，内部只调用既有 `BankTransactionCategoryService.apply_turnover_updates(...)` 并重建 Turnover relation。
- 成功路径不再直接调用 `_clear_turnover_ledger_read_model_best_effort()`；Bankdetail、Workbench、Turnover Ledger refresh enqueue 由 UoW explicit refresh requests 执行。
- PostgreSQL production path 暂保留 legacy fallback：当前缺少明确 transaction-bound Bankdetail category adapter，PF-P078 未猜测 SQL 或生产事务契约。

#### 变更文件

- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_turnover_ledger_api.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`：Pass，仅 PF-P078 允许文件变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，36 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，33 tests。
- `rg -n "update_bank_row_tags_batch|_turnover_ledger_bank_row_tags_write_facade|bank-row-tags|bank_row_tags|expectedFailure|PF-P078|_clear_turnover_ledger_read_model_best_effort" backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py docs/architecture/backend-refactor`：Pass。

#### 下一条 Prompt 上下文

PF-P076、PF-P077、PF-P078 构成 bank-row-tags UoW slice。下一步应生成并执行 `PF-P078-MG - Turnover Ledger Bank Row Tags UoW Cumulative Merge Gate`，覆盖当前分支自最新 main 以来的完整 diff。MG 必须确认 production code diff 只涉及 `server.py` 的 bank-row-tags handler/UoW seam，不执行 Traffic Gate，不部署，不访问生产。

### PF-P079 - Turnover Ledger Confirm Relation Facade Contract Tests

状态：`verified`

#### 范围

- 只为未来 `TurnoverLedgerWriteFacade.confirm_relation(...)` 增加 facade-level target contract tests。
- 不修改 production code。
- 不迁移 confirm handler、withdraw handler 或其它 Turnover 写路径。

#### 执行摘要

- 新增 `_RecordingConfirmRelationPort` fake，作为细粒度 relation port/repository，不模拟 `Application`。
- 新增 3 条 `unittest.expectedFailure` target tests：
  - confirm facade 使用 relation port 并返回 service-layer payload；
  - dirty/outbox failure 必须 rollback relation confirm；
  - confirm facade 必须 enqueue `turnover_ledger` / `all` / `turnover_relation_changed`。
- 当前 `TurnoverLedgerWriteFacade.confirm_relation(...)` 尚未实现，因此 expectedFailure 是默认 CI 隔离，不是 skip 或删除目标契约。

#### 变更文件

- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`：Pass，仅 PF-P079 允许文件变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，36 tests，3 expectedFailure。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，36 tests。
- `rg -n "confirm_relation|confirm relation|expectedFailure|PF-P079|turnover_relation_changed|TurnoverLedgerWriteFacade" tests/test_turnover_ledger_uow_contract.py docs/architecture/backend-refactor`：Pass。

#### 下一条 Prompt 上下文

PF-P079 已锁定 confirm relation facade target contract。下一步应生成并执行 `PF-P080 - Turnover Ledger Confirm Relation Facade Skeleton`，只实现 `TurnoverLedgerWriteFacade.confirm_relation(...)` 的最小 service-layer skeleton，让 PF-P079 的 3 条 expectedFailure 转为普通通过；仍不得迁移真实 `server.py` handler。

### PF-P080 - Turnover Ledger Confirm Relation Facade Skeleton

状态：`verified`

#### 范围

- 只实现 `TurnoverLedgerWriteFacade.confirm_relation(...)` 的最小 service-layer skeleton。
- 将 PF-P079 的 3 条 confirm relation target tests 从 `unittest.expectedFailure` 转为普通通过。
- 不修改 `server.py`，不迁移真实 confirm handler。

#### 执行摘要

- `TurnoverLedgerWriteFacade.confirm_relation(...)` 现在接收 `bank_row_ids`、`actor_id`、`tenant_id`、`note`、`affected_months`。
- facade 通过现有 `TurnoverLedgerWriteUnitOfWork` 调用 `context.relation_repository.confirm_relation(..., transaction=context.transaction)`。
- confirm facade 使用 explicit refresh request：`turnover_ledger` / `all` / `turnover_relation_changed`。
- PF-P079 的 3 条 target tests 已转为普通通过。

#### 变更文件

- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`：Pass，仅 PF-P080 允许文件变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，36 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，36 tests。
- `rg -n "def confirm_relation|test_target_confirm_relation|expectedFailure|PF-P080|turnover_relation_changed" backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py tests/test_turnover_ledger_uow_contract.py docs/architecture/backend-refactor`：Pass。

#### 下一条 Prompt 上下文

PF-P079/PF-P080 完成了 confirm relation facade-level skeleton。下一步应生成 `PF-P081 - Turnover Ledger Confirm Relation Handler UoW Wiring Readiness`，先审计真实 handler 接入所需的 local transaction shim、relation repository/port、affected months、legacy fallback test 和 Workbench influence blocker；不得在没有 readiness 结论前直接迁移 handler。

### PF-P081 - Turnover Ledger Confirm Relation Handler UoW Wiring Readiness

状态：`verified`

#### 范围

- 只审计 `POST /api/turnover-ledger/relations/confirm` 真实 handler 接入 UoW 的 readiness。
- 不修改 production code，不新增 tests，不迁移 handler。

#### 执行摘要

- 已记录 confirm 当前运行时序：handler rebuild relations -> route confirm -> relation service facts/audit -> `_after_turnover_relation_mutation` persistence / Workbench invalidation / read model clear / refresh enqueue。
- 结论：local/dev/test path readiness 高，可复用 local transaction shim 和 `TurnoverLedgerApiRoutes.confirm_relation(...)` 作为 temporary relation port。
- 结论：PostgreSQL production path readiness 低，缺少明确 transaction-bound relation repository/adapter，不得猜 SQL，后续必须保留 legacy fallback。
- 结论：Workbench influence port 仍是 cross-module blocker，不应在 confirm handler wiring 中强行迁移。

#### 变更文件

- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`：Pass，仅 PF-P081 允许文件变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `rg -n "PF-P081|Confirm Relation Handler UoW Wiring Readiness|Current Runtime Sequence|Wiring Readiness Matrix|Decision|Blockers" docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md`：Pass。

#### 下一条 Prompt 上下文

下一步应生成 `PF-P082 - Turnover Ledger Confirm Relation Handler UoW Target Tests`，只补 API-level target tests，锁定 local/dev/test UoW rollback/no-direct-clear 行为；不得直接进行 handler wiring。

### PF-P082 - Turnover Ledger Confirm Relation Handler UoW Target Tests

状态：`verified`

#### 范围

- 只为 `POST /api/turnover-ledger/relations/confirm` 增加 API-level compatibility / target tests。
- 不修改 production code，不迁移 handler，不改 service/facade。
- 保留 legacy split-brain 行为测试，并用 `unittest.expectedFailure` 锁定 future UoW target behavior。

#### 执行摘要

- 新增当前行为 characterization：queue failure 当前发生在 relation confirm/audit 和 Turnover read model clear 之后，记录现有 split-brain 风险。
- 新增 2 条 future target tests，当前用 `unittest.expectedFailure` 隔离默认 CI：
  - queue/outbox failure must roll back relation confirm/audit；
  - successful UoW path must not call `_clear_turnover_ledger_read_model_best_effort()` directly。
- 未修改 `server.py` 或任何 production code。

#### 变更文件

- `tests/test_turnover_ledger_api.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`：Pass，仅 PF-P082 允许文件变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，39 tests，2 expectedFailure。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，36 tests。

#### 下一条 Prompt 上下文

下一步应生成 `PF-P083 - Turnover Ledger Confirm Relation Local Handler UoW Wiring`。PF-P083 只能迁移 local/dev/test confirm handler path 到 UoW；必须保留 PostgreSQL production legacy fallback；必须让 PF-P082 的 2 条 expectedFailure 转为普通通过；不得迁移 withdraw、cancel、No OA、Bankdetail 独立 API 或 Workbench influence port。

### PF-P083 - Turnover Ledger Confirm Relation Local Handler UoW Wiring

状态：`verified`

#### 范围

- 只迁移 `POST /api/turnover-ledger/relations/confirm` 的 local/dev/test path 到 `TurnoverLedgerWriteFacade.confirm_relation(...)`。
- 保留 PostgreSQL production legacy fallback，不猜测 relation SQL。
- 不迁移 withdraw、No OA、Bankdetail 独立 API 或 Workbench influence port。

#### 执行摘要

- 新增 `_turnover_ledger_confirm_write_facade()` seam，支持测试通过 `_turnover_ledger_confirm_write_facade_override = None` 强制 legacy fallback。
- 新增 local confirm transaction shim：dirty/outbox failure 时恢复 `TurnoverRelationService.snapshot()` 并回写 local state store；成功时保存最新 relation snapshot。
- 新增 local confirm relation repository，复用既有 `TurnoverLedgerApiRoutes.confirm_relation(...)` 和 `TurnoverRelationService.rebuild_from_bank_rows(...)`，未引入 `Application` god-object service 依赖。
- `_handle_api_turnover_ledger_confirm` 在 facade 存在时走 UoW，成功路径不再直接调用 `_after_turnover_relation_mutation(...)` / `_clear_turnover_ledger_read_model_best_effort()`。
- PF-P082 的 2 条 target tests 已从 `unittest.expectedFailure` 转为普通通过；legacy split-brain compatibility test 仍通过显式 fallback seam 保留。

#### 变更文件

- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_turnover_ledger_api.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`：Pass，仅 PF-P083 允许文件变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，39 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，36 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py`：Pass。

#### 下一条 Prompt 上下文

PF-P079 到 PF-P083 构成 confirm relation UoW slice：facade contract、facade skeleton、handler readiness、API target tests、local/dev/test handler wiring 已完成。下一步应生成 `PF-P083-MG - Turnover Ledger Confirm Relation UoW Cumulative Merge Gate`，统一覆盖本分支自最新 main 以来的 PF-P079 到 PF-P083 完整 diff。MG 不执行 Traffic Gate，不部署，不访问生产。

### PF-P083-MG - Turnover Ledger Confirm Relation UoW Cumulative Merge Gate

状态：`verified`

#### 范围

- 覆盖 PF-P079 到 PF-P083 的 confirm relation UoW slice 累计 diff。
- 只执行 Merge Gate，不执行 Traffic Gate。
- 合并前后运行 Turnover Ledger targeted tests 和 compileall。

#### 执行摘要

- 合并前 diff 仅包含白名单文件：
  - `backend/src/fin_ops_platform/app/server.py`
  - `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
  - `tests/test_turnover_ledger_api.py`
  - `tests/test_turnover_ledger_uow_contract.py`
  - backend-refactor 三份文档。
- 当前分支已通过 no-untracked、diff-check、targeted tests 和 compileall。
- 已合入本地 `main`，merge commit：`a1ba5532`。
- `main` 上 targeted verification 已通过。
- 已执行 `git push origin main`，`origin/main` 更新到 `8a8007cf`。
- 未执行 Traffic Gate、部署、Nginx 修改、生产配置修改或生产访问。

#### 验证

- `git status --short --branch`：Pass，合并前分支干净；main 合并后 ahead origin/main。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `git diff --name-only main...HEAD`：Pass，仅 7 个白名单文件。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，39 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，36 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass。

#### 下一条 Prompt 上下文

push `origin/main` 后，从最新 main 新建 `codex/` 分支。下一条建议 prompt 是 `PF-P084 - Turnover Ledger Withdraw Relation Facade Contract Tests`：只为 withdraw relation 建立 facade-level contract tests，不迁移 handler，不猜测 PostgreSQL relation SQL，不进入 Traffic Gate。

### PF-P084 - Turnover Ledger Withdraw Relation Facade Contract Tests

状态：`verified`

#### 范围

- 只为未来 `TurnoverLedgerWriteFacade.withdraw_relation(...)` 增加 facade-level target contract tests。
- 不修改 production code，不迁移真实 HTTP handler，不改 schema。
- 使用 `unittest.expectedFailure` 保持默认 CI 绿色。

#### 执行摘要

- 新增 `_RecordingWithdrawRelationPort`，记录 `withdraw_relation(relation_id, actor_id, note, transaction)` 调用。
- 新增 3 条 future target tests：
  - withdraw facade 必须调用细粒度 relation port 并返回 service-layer payload；
  - dirty/outbox failure 必须 rollback withdraw relation facts/audit；
  - withdraw facade 必须 enqueue `turnover_ledger` / `all` / `turnover_relation_changed`。
- 新增 tests 均为 `unittest.expectedFailure`，因为 `TurnoverLedgerWriteFacade.withdraw_relation(...)` 尚未实现。
- 未修改 production code。

#### 变更文件

- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`：Pass，仅 PF-P084 允许文件变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，39 tests，3 expectedFailure。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，39 tests。

#### 下一条 Prompt 上下文

下一步应生成 `PF-P085 - Turnover Ledger Withdraw Relation Facade Skeleton`，只实现 `TurnoverLedgerWriteFacade.withdraw_relation(...)` 的最小 service-layer skeleton，让 PF-P084 的 3 条 expectedFailure 转为普通通过；仍不得迁移真实 `server.py` withdraw handler。

### PF-P085 - Turnover Ledger Withdraw Relation Facade Skeleton

状态：`verified`

#### 范围

- 只实现 `TurnoverLedgerWriteFacade.withdraw_relation(...)` 的最小 service-layer skeleton。
- 将 PF-P084 的 3 条 withdraw relation target tests 从 `unittest.expectedFailure` 转为普通通过。
- 不修改 `server.py`，不迁移真实 HTTP handler。

#### 执行摘要

- `TurnoverLedgerWriteFacade.withdraw_relation(...)` 现在接收 `relation_id`、`actor_id`、`tenant_id`、`note`、`affected_months`。
- facade 通过现有 `TurnoverLedgerWriteUnitOfWork` 调用 `context.relation_repository.withdraw_relation(..., transaction=context.transaction)`。
- withdraw facade 使用 explicit refresh request：`turnover_ledger` / `all` / `turnover_relation_changed`。
- PF-P084 的 3 条 target tests 已转为普通通过。

#### 变更文件

- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`：Pass，仅 PF-P085 允许文件变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，39 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，39 tests。
- `python3 -m compileall backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass。

#### 下一条 Prompt 上下文

PF-P084/PF-P085 完成了 withdraw relation facade-level contract 和 skeleton。下一步应生成 `PF-P086 - Turnover Ledger Withdraw Relation Handler UoW Wiring Readiness`，先审计真实 withdraw handler 接入所需的 local transaction shim、relation repository/port、affected months、legacy fallback test 和 system-generated relation rejection；不得在没有 readiness 结论前直接迁移 handler。

### PF-P086 - Turnover Ledger Withdraw Relation Handler UoW Wiring Readiness

状态：`verified`

#### 范围

- 只做 withdraw relation handler 接入 UoW 前的 readiness 审计和文档回写。
- 不修改 production code，不新增/修改测试，不迁移真实 handler。
- 明确 local/dev/test wiring、PostgreSQL production fallback、manual/system relation guard、affected_months 计算、legacy compatibility tests 和下一条 handler target tests 的边界。

#### 预期产物

- `turnover-ledger-write-uow-plan.md` 增加 PF-P086 readiness 结论。
- `refactor-prompts.md` 增加 PF-P086 prompt。
- 本状态机记录 PF-P086 状态、范围、验证和下一步上下文。

#### 执行摘要

- 已记录当前 withdraw handler runtime sequence：
  `auth/session -> load body -> get_relation -> source manual guard -> collect bank_row_ids -> routes.withdraw_relation -> relation_service.withdraw_relation -> affected_months -> _after_turnover_relation_mutation -> response`。
- 已确认 legacy 路径中 relation facts/audit 与 dirty/outbox/read-model invalidation 仍不是同一事务。
- 已确认 local/dev/test 可仿照 confirm seam 增加 withdraw facade seam、local transaction shim 和 relation repository wrapper。
- 已确认 PostgreSQL production path 仍必须保留 legacy fallback，不得猜测 relation SQL。
- 已锁定 PF-P087 的测试边界：rollback target、no direct read-model clear target、system-generated guard no-facade、affected_months compatibility。

#### 变更文件

- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`：Pass，仅 PF-P086 允许文档变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `rg -n "PF-P086|Withdraw Relation Handler UoW Wiring Readiness|Current Runtime Sequence|Wiring Readiness Matrix|Compatibility|PF-P087|system_relation_cannot_withdraw|affected_months" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`：Pass。

#### 下一条 Prompt 上下文

下一步应生成 `PF-P087 - Turnover Ledger Withdraw Relation Handler UoW Target Tests`：只为真实 `POST /api/turnover-ledger/relations/{id}/withdraw` handler 增加 local/dev/test UoW target tests，仍不直接迁移 handler。

### PF-P087 - Turnover Ledger Withdraw Relation Handler UoW Target Tests

状态：`verified`

#### 范围

- 只为 withdraw relation HTTP handler 增加/调整 API 层 characterization 和 future target tests。
- 不修改 production code，不迁移 handler，不改 UoW/facade 实现。
- 未实现的目标语义必须使用 `unittest.expectedFailure` 保持默认 CI 绿色。

#### 预期产物

- `tests/test_turnover_ledger_api.py` 增加 withdraw handler UoW target tests。
- `turnover-ledger-write-uow-plan.md` 记录 PF-P087 测试锁定结果。
- `refactor-prompts.md` 和本文档记录 PF-P087 执行结果。

#### 执行摘要

- 补强 `test_withdraw_duplicate_submit_currently_allows_second_withdraw_and_reenqueues`，断言 withdraw response 的 `affected_months` 为 `["2026-02", "2026-03"]`。
- 新增普通通过的 legacy characterization：`test_withdraw_relation_queue_failure_happens_after_relation_withdraw_and_read_model_clear`，锁定当前 queue failure 发生在 relation withdraw/audit 和 read model direct clear 之后。
- 新增 2 条 future target tests，并以 `unittest.expectedFailure` 保持默认 CI 绿色：
  - `test_target_withdraw_relation_queue_failure_rolls_back_relation_withdraw`；
  - `test_target_withdraw_relation_uow_path_does_not_clear_read_model_directly`。
- 补强 `test_withdraw_rejects_system_generated_relation`，断言 system-generated rejection 不触发 withdraw audit。
- 未修改 production code。

#### 变更文件

- `tests/test_turnover_ledger_api.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，42 tests，2 expectedFailure。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，39 tests。
- `git status --short --branch`：Pass，仅 PF-P087 允许文件变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `rg -n "test_target_withdraw_relation|expectedFailure|system_relation_cannot_withdraw|affected_months|PF-P087|withdraw_relation" tests/test_turnover_ledger_api.py docs/architecture/backend-refactor`：Pass。

#### 下一条 Prompt 上下文

下一步应生成 `PF-P088 - Turnover Ledger Withdraw Relation Handler UoW Wiring`：只把 local/dev/test withdraw handler 接入 PF-P085 facade/UoW，让 PF-P087 的 target tests 转为普通通过；仍保留 PostgreSQL production legacy fallback，不迁移其它写路径。

### PF-P088 - Turnover Ledger Withdraw Relation Handler UoW Wiring

状态：`verified`

#### 范围

- 只将 local/dev/test withdraw relation handler path 接入 `TurnoverLedgerWriteFacade.withdraw_relation(...)`。
- 将 PF-P087 的 2 条 withdraw handler target tests 从 `unittest.expectedFailure` 转为普通通过。
- 保留 PostgreSQL production legacy fallback，不迁移其它写路径。

#### 预期产物

- `backend/src/fin_ops_platform/app/server.py` 增加 withdraw 专用 facade seam、local transaction shim 和 relation repository wrapper。
- `tests/test_turnover_ledger_api.py` 移除 PF-P087 2 条 target tests 的 `expectedFailure`。
- 文档记录 PF-P088 执行结果。

#### 执行摘要

- 新增 `_turnover_ledger_withdraw_write_facade()`，支持 `_turnover_ledger_withdraw_write_facade_override`，并保留 `state_store.storage_backend == "postgres"` production legacy fallback。
- 新增 `_local_turnover_ledger_withdraw_connection(...)`，dirty/outbox failure 时 restore 并保存 previous relation snapshot，成功时保存最新 snapshot。
- 新增 `_local_turnover_ledger_withdraw_relation_repository()`，复用 `TurnoverLedgerApiRoutes.withdraw_relation(...)`，不重新实现 relation mutation 规则。
- `_handle_api_turnover_ledger_withdraw(...)` 现在在 facade 可用时调用 `TurnoverLedgerWriteFacade.withdraw_relation(...)`；只有 legacy fallback path 才调用 `_after_turnover_relation_mutation(...)`。
- PF-P087 的 2 条 target tests 已从 `unittest.expectedFailure` 转为普通通过。
- legacy split-brain characterization 通过 `_turnover_ledger_withdraw_write_facade_override = None` 保留。

#### 变更文件

- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_turnover_ledger_api.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，42 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，39 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py`：Pass。
- `git status --short --branch`：Pass，仅 PF-P088 允许文件变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `rg -n "_turnover_ledger_withdraw_write_facade|_local_turnover_ledger_withdraw|test_target_withdraw_relation|expectedFailure|PF-P088|_clear_turnover_ledger_read_model_best_effort" backend/src/fin_ops_platform/app/server.py tests/test_turnover_ledger_api.py docs/architecture/backend-refactor`：Pass。

#### 下一条 Prompt 上下文

下一步应生成 `PF-P088-MG - Turnover Ledger Withdraw Relation UoW Cumulative Merge Gate`，统一覆盖 PF-P084 到 PF-P088 的完整 diff；不得继续迁移其它 Turnover 写路径。

### PF-P088-MG - Turnover Ledger Withdraw Relation UoW Cumulative Merge Gate

状态：`verified`

#### 范围

- 统一覆盖 PF-P084、PF-P085、PF-P086、PF-P087、PF-P088 的完整 diff。
- 只执行 Merge Gate，不执行 Traffic Gate、部署、生产访问或配置变更。
- 合并前后验证 Turnover Ledger targeted suites 和 compileall。

#### 预期变更文件白名单

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 下一条 Prompt 上下文

PF-P088-MG 通过并 push `origin/main` 后，必须从最新 main 新建下一条 `codex/` 分支。下一条候选任务应继续 Turnover Ledger 写路径中尚未迁移到 UoW 的剩余 relation/ledger 写入口；如果选择不明确，应停止并总结。

#### 执行摘要

- PF-P084 到 PF-P088 的 withdraw relation UoW slice 已合入本地 `main`。
- Merge commit: `30eb3192`。
- 合并前和 main 上均完成 Turnover Ledger targeted verification。
- 未执行 Traffic Gate、部署、Nginx 修改、生产配置修改或生产访问。

#### Verification on main

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，42 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，39 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass。
- `rg -n "_turnover_ledger_withdraw_write_facade|_local_turnover_ledger_withdraw|test_target_withdraw_relation|PF-P088|PF-P088-MG|turnover_relation_changed" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py tests/test_turnover_ledger_api.py tests/test_turnover_ledger_uow_contract.py docs/architecture/backend-refactor`：Pass。

### PF-P089 - Turnover Ledger Remaining Write Path Rebaseline / Next Slice Selection

状态：`verified`

#### 范围

- 修正 PF-P088-MG 后状态机顶部的 stale push 记录：`main` 已 push 且与 `origin/main` 对齐。
- 只读扫描 Turnover Ledger 现有 routes、handlers、write facade、UoW、API tests 和 UoW contract tests。
- 输出 Turnover Ledger route matrix 和 write-path UoW status matrix。
- 判断 Turnover Ledger 是否仍有未迁移到 UoW 的写路径；如果有，选择下一条最小 Micro-JIT slice；如果没有，明确 Turnover Ledger 写路径进入模块收口候选。
- 不修改 production code、tests、SQL migration、worker、frontend、deployment 或生产配置。

#### 允许变更文件

- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验收标准

- `git status --short --branch`：Pass，当前分支不是 `main`，仅三份允许文档变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪临时文件。
- `git diff --check`：Pass。
- `rg -n "PF-P089|Remaining Write Path Rebaseline|Route Matrix|UoW Status Matrix|Remaining Gap Analysis|Next Slice Decision|main...origin/main|Turnover Ledger PostgreSQL Write Port Contract Tests" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`：Pass。

#### 下一条 Prompt 上下文

PF-P089 已 verified。扫描结论：五条 Turnover Ledger 写 path 都已有 facade seam；tag selection 和 relation extra 已具备 PostgreSQL adapter path；bank-row-tags、confirm relation、withdraw relation 在 `storage_backend == "postgres"` 时仍 fallback，因为缺少 transaction-aware Bankdetail port adapter 和 relation repository adapter。下一条最小 prompt 应为 `PF-P090 - Turnover Ledger PostgreSQL Write Port Contract Tests`，只写 contract tests，不实现 adapters，不迁移 handler。

### PF-P090 - Turnover Ledger PostgreSQL Write Port Contract Tests

状态：`verified`

#### 范围

- 只为 Turnover Ledger PostgreSQL write ports 增加 contract tests。
- 锁定未来 production path 需要的 transaction-aware relation repository adapter 和 Bankdetail port adapter。
- 不实现 adapters，不修改 handler，不改变生产路径。
- 不访问真实 PostgreSQL 或任何外部服务，全部使用 fake repository factory / fake transaction。

#### 允许变更文件

- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验收标准

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，45 tests，5 expectedFailure。
- `git status --short --branch`：Pass，当前分支不是 `main`，仅允许文件变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪临时文件。
- `git diff --check`：Pass。
- `rg -n "PF-P090|PostgreSQL Write Port Contract|TurnoverLedgerRelationRepositoryAdapter|TurnoverLedgerBankdetailPortAdapter|expectedFailure" tests/test_turnover_ledger_uow_contract.py docs/architecture/backend-refactor`：Pass。

#### 下一条 Prompt 上下文

PF-P090 已 verified。新增 5 条 expectedFailure target contract tests，锁定 `TurnoverLedgerRelationRepositoryAdapter` 和 `TurnoverLedgerBankdetailPortAdapter` 的未来生产级接口；新增 1 条普通通过测试，证明 adapter exception 会让 UoW rollback。下一条应生成 `PF-P091 - Turnover Ledger PostgreSQL Write Port Adapter Skeleton`，只实现最小 adapter skeleton 让这 5 条 target tests 转绿，不迁移 handler 的 PostgreSQL path。

### PF-P091 - Turnover Ledger PostgreSQL Write Port Adapter Skeleton

状态：`verified`

#### 范围

- 实现最小 `TurnoverLedgerRelationRepositoryAdapter` 和 `TurnoverLedgerBankdetailPortAdapter`。
- 移除 PF-P090 5 条 target tests 的 `unittest.expectedFailure`，让它们转为普通通过。
- 不迁移 handler，不修改 `server.py`，不接入 PostgreSQL path。

#### 允许变更文件

- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验收标准

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，45 tests，0 expectedFailure。
- `python3 -m compileall backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。
- `git status --short --branch`：Pass，当前分支不是 `main`，仅允许文件变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪临时文件。
- `git diff --check`：Pass。
- `rg -n "TurnoverLedgerRelationRepositoryAdapter|TurnoverLedgerBankdetailPortAdapter|PF-P091|expectedFailure" backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py tests/test_turnover_ledger_uow_contract.py docs/architecture/backend-refactor`：Pass。

#### 下一条 Prompt 上下文

PF-P091 已 verified。已实现最小 `TurnoverLedgerRelationRepositoryAdapter` 与 `TurnoverLedgerBankdetailPortAdapter`，PF-P090 的 5 条 adapter target tests 已转为普通通过。下一条应生成 PostgreSQL facade readiness / API-level target tests prompt；不得直接迁移 handler，除非先补测试锁定。

### PF-P092 - Turnover Ledger PostgreSQL Facade Readiness Target Tests

状态：`verified`

#### 范围

- 只新增 API-level target tests，锁定 PostgreSQL storage backend 下 bank-row-tags、confirm relation、withdraw relation 应该进入 facade/UoW path。
- 当前 production handler 尚未 wiring，目标测试可使用 `unittest.expectedFailure` 保持默认 CI 绿色。
- 不修改 production code，不迁移 handler。

#### 允许变更文件

- `tests/test_turnover_ledger_api.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验收标准

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，45 tests，3 expectedFailure。
- `git status --short --branch`：Pass，当前分支不是 `main`，仅允许文件变更。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪临时文件。
- `git diff --check`：Pass。
- `rg -n "PF-P092|PostgreSQL Facade Readiness|postgres.*facade|expectedFailure" tests/test_turnover_ledger_api.py docs/architecture/backend-refactor`：Pass。

#### 下一条 Prompt 上下文

PF-P092 已 verified。新增 3 条 PostgreSQL facade readiness target tests，当前为 `unittest.expectedFailure`，分别覆盖 bank-row-tags batch、confirm relation、withdraw relation 在 `storage_backend == "postgres"` 时应进入 facade/UoW path 且不 direct clear read model。下一条应生成 `PF-P093 - Turnover Ledger PostgreSQL Facade Seam Wiring`，只让这 3 条 target tests 转绿；不得扩展到其它模块。

### PF-P093 - Turnover Ledger PostgreSQL Facade Seam Wiring

状态：`verified`

#### 范围

- 只接入 Turnover Ledger PostgreSQL storage backend 下的三个 write facade seam：
  - `POST /api/turnover-ledger/bank-row-tags/batch`
  - `POST /api/turnover-ledger/relations/confirm`
  - `POST /api/turnover-ledger/relations/{id}/withdraw`
- 只让 PF-P092 的 3 条 target tests 从 `unittest.expectedFailure` 转为普通通过。
- 可以补强测试 fake PostgreSQL connection，使其具备 `.transaction()`，但不得连接真实 PostgreSQL。

#### 允许变更文件

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `tests/test_turnover_ledger_api.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验收标准

- PF-P092 的 3 条 target tests 已移除 `unittest.expectedFailure` 并普通通过。
- PostgreSQL path 使用 `TurnoverLedgerWriteUnitOfWork`、`TurnoverLedgerDirtyOutboxWriter` 和 PF-P091 adapters。
- PostgreSQL facade path 不在 handler 中直接调用 `_clear_turnover_ledger_read_model_best_effort`。
- PostgreSQL facade path 不使用 non-transactional `enqueue_read_model_refresh`。
- 新增 server composition helper 只捕获细粒度依赖，不把 `Application` god object 注入 service/facade/adapter。

#### 变更文件

- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_turnover_ledger_api.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- RED：移除 3 个 `unittest.expectedFailure` 后，3 条 PostgreSQL facade readiness target tests 因 direct read-model clear 失败。
- GREEN：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，45 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，45 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。

#### 下一条 Prompt 上下文

PF-P093 已 verified。本分支从 PF-P089 到 PF-P093 已包含 discovery、contract tests、adapter skeleton、API target tests 和 production handler seam。下一步应生成并审查 `PF-P093-MG - Turnover Ledger PostgreSQL Write Path Cumulative Merge Gate`，不要继续扩大 Turnover Ledger 实现范围。

### PF-P093-MG - Turnover Ledger PostgreSQL Write Path Cumulative Merge Gate

状态：`verified`

#### 范围

- 覆盖当前分支 `codex/turnover-ledger-remaining-write-rebaseline-p089` 从 PF-P089 到 PF-P093 的完整 diff。
- 只做 merge gate：scope audit、untracked audit、diff check、target tests、文档状态检查、commit/merge/push。
- 不新增业务实现，不修改生产配置，不执行 Traffic Gate。

#### 预期变更文件

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 必须验证

- `git status --short --branch`：Pass，分支侧无 dirty/untracked；main merge 后仅 ahead。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `git diff --name-only main...HEAD`：Pass，分支侧只包含预期 7 个文件。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，45 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，45 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。

#### Merge / Push

- 本地 merge 到 `main`：Pass，merge commit `e0056963`。
- `main` 复验：Pass。
- `git push origin main`：Pass，`origin/main` 已与当前 `main` 对齐。

#### 下一条 Prompt 上下文

PF-P093-MG 已 verified，main 已合入、复验并 push 到 `origin/main`。下一步必须从最新 `main` 新建下一条 `codex/` 分支。Turnover Ledger 下一切片应基于当前专项计划重新选择，不得在 `main` 或旧分支继续开发。

### PF-P094 - Turnover Ledger PostgreSQL Repository Ownership Discovery and Cleanup Planning

状态：`verified`

#### 范围

- 只做 discovery/planning 和文档回写。
- 盘点 PF-P093 后新增的 PostgreSQL write seam 中，哪些 persistence helper / repository-like helper 仍在 `server.py`。
- 明确哪些 helper 应下沉到 `services/` 或 `services/postgres_repositories/`，哪些可以保留在 app composition 层。
- 不修改业务代码、测试、SQL migration、前端、部署或生产配置。

#### 必须回答

- `_postgres_turnover_ledger_relation_repository(...)` 和 `_postgres_turnover_ledger_bankdetail_repository(...)` 当前仍让 `server.py` 承担过多 persistence orchestration：它们捕获 service/routes/provider 并决定 Postgres transaction persistence 与 fake/local fallback。
- 需要新增 dedicated service-level write ports，而不是把 nested helper 原样搬到另一个文件。
- 下一步应先写 contract tests，锁定未来 ports 只接收细粒度依赖、不接收 `Application`，并用 supplied transaction 调用 persistence repository factory。
- 下一个最小 Micro-JIT prompt 是 `PF-P095 - Turnover Ledger PostgreSQL Write Port Ownership Contract Tests`。

#### 执行结果

- CodeGraph 定位了 `TurnoverLedgerRelationRepositoryAdapter`、`TurnoverLedgerBankdetailPortAdapter`、`_turnover_ledger_confirm_write_facade` 和 `_turnover_ledger_withdraw_write_facade` 等关键符号。
- 文件级审计确认 `PostgresWorkbenchRepository.save_bank_transaction_categories(...)` 与 `save_turnover_relations(...)` 已可在 supplied transaction object 上执行，但 relation/category service orchestration 仍由 `server.py` nested helper 负责。
- 确认下一步不应继续扩大 handler，而应补 service-level port ownership contract tests。

#### 下一条 Prompt 上下文

PF-P094 已 verified。下一条应生成 `PF-P095 - Turnover Ledger PostgreSQL Write Port Ownership Contract Tests`，只新增/调整 tests，锁定未来 `TurnoverLedgerRelationWritePort` 和 `TurnoverLedgerBankdetailWritePort` 的接口；不得直接抽离 production code。

### PF-P095 - Turnover Ledger PostgreSQL Write Port Ownership Contract Tests

状态：`verified`

#### 范围

- 只新增/调整 tests，锁定 future write ports：
  - `TurnoverLedgerRelationWritePort`
  - `TurnoverLedgerBankdetailWritePort`
- 目标类尚未实现时使用 `unittest.expectedFailure` 保持默认 CI 绿色。
- 不修改 production code，不抽离 `server.py` helper。

#### 执行结果

- 在 `tests/test_turnover_ledger_uow_contract.py` 中新增 4 条 future target contract tests。
- 4 条新增 tests 使用 `unittest.expectedFailure` 保留尚未实现的目标语义，默认 CI 仍保持绿色。
- 锁定 future relation write port 必须拒绝 `Application` god object，使用 supplied transaction 调用 persistence repository factory，并完成 confirm/withdraw 后的 relation snapshot 持久化。
- 锁定 future bankdetail write port 必须拒绝 `Application` god object，执行 category update + relation rebuild，并用 supplied transaction 持久化 category snapshot 与 relation snapshot。
- 本轮未修改 production code，未迁移 `server.py` helper。

#### 允许变更文件

- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`：Pass，仅有 PF-P095 范围内文件改动。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，49 tests，4 expected failures。
- `rg -n "PF-P095|TurnoverLedgerRelationWritePort|TurnoverLedgerBankdetailWritePort|expectedFailure|Repository Ownership" tests/test_turnover_ledger_uow_contract.py docs/architecture/backend-refactor`：Pass。

#### 下一条 Prompt 上下文

PF-P095 已 verified。下一步应生成并审查 `PF-P096 - Turnover Ledger PostgreSQL Write Port Ownership Skeleton`，只实现最小 `TurnoverLedgerRelationWritePort` 和 `TurnoverLedgerBankdetailWritePort` classes，让 PF-P095 的 4 条 expectedFailure target tests 转为普通通过。PF-P096 不得迁移 `server.py` helper，不得修改 API handler，不得新增 SQL migration。

### PF-P096 - Turnover Ledger PostgreSQL Write Port Ownership Skeleton

状态：`verified`

#### 范围

- 在 `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py` 中实现最小 write port classes：
  - `TurnoverLedgerRelationWritePort`
  - `TurnoverLedgerBankdetailWritePort`
- 将 PF-P095 的 4 条 expectedFailure target tests 转为普通通过测试。
- 只做 service-level port skeleton，不迁移 `server.py` helper。

#### 允许变更文件

- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 禁止范围

- 不得修改 `server.py`。
- 不得迁移 `_postgres_turnover_ledger_relation_repository(...)` 或 `_postgres_turnover_ledger_bankdetail_repository(...)`。
- 不得修改 API handler、SQL migration、部署配置或生产配置。

#### 执行结果

- 在 `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py` 中新增：
  - `TurnoverLedgerRelationWritePort`
  - `TurnoverLedgerBankdetailWritePort`
- `TurnoverLedgerRelationWritePort` 使用细粒度 relation service、routes、bank rows provider 和 persistence repository factory；confirm/withdraw 使用 supplied transaction 持久化 relation snapshot。
- `TurnoverLedgerBankdetailWritePort` 使用细粒度 category service、relation service、bank rows provider 和 persistence repository factory；category update 后重建 relation，并用 supplied transaction 持久化 category snapshot 与 relation snapshot。
- PF-P095 的 4 条 target tests 已移除 `unittest.expectedFailure` 并转为普通通过。
- 本轮未修改 `server.py`，未迁移 API handler。

#### 验证

- `git status --short --branch`：Pass，仅有 PF-P096 范围内文件改动。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，49 tests。
- `python3 -m compileall backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。
- `rg -n "TurnoverLedgerRelationWritePort|TurnoverLedgerBankdetailWritePort|PF-P096|expectedFailure" backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py tests/test_turnover_ledger_uow_contract.py docs/architecture/backend-refactor`：Pass。

#### 下一条 Prompt 上下文

PF-P096 已 verified。下一步应生成并审查 `PF-P097 - Turnover Ledger PostgreSQL Write Port Server Composition Wiring`，将 `server.py` PostgreSQL nested helper 的 orchestration 替换为 new ports。PF-P097 应只做 composition wiring，不改变 API response contract，不新增 SQL migration，不扩大到 unrelated Turnover Ledger paths。

### PF-P097 - Turnover Ledger PostgreSQL Write Port Server Composition Wiring

状态：`verified`

#### 范围

- 将 `server.py` PostgreSQL storage backend composition 接入 PF-P096 的：
  - `TurnoverLedgerRelationWritePort`
  - `TurnoverLedgerBankdetailWritePort`
- 替换 `_postgres_turnover_ledger_relation_repository(...)` 与 `_postgres_turnover_ledger_bankdetail_repository(...)` 中仍承担的 service orchestration。
- 保持 local/dev/test fallback path 不变。

#### 允许变更文件

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 禁止范围

- 不得修改 API response contract。
- 不得修改 SQL migration、部署配置或生产配置。
- 不得迁移 unrelated Turnover Ledger paths 或其它业务模块。

#### 执行结果

- PostgreSQL storage backend 下的 `_turnover_ledger_confirm_write_facade(...)` 和 `_turnover_ledger_withdraw_write_facade(...)` 已使用 `TurnoverLedgerRelationWritePort`。
- PostgreSQL storage backend 下的 `_turnover_ledger_bank_row_tags_write_facade(...)` 已使用 `TurnoverLedgerBankdetailWritePort`。
- 删除了 `_postgres_turnover_ledger_relation_repository(...)` 与 `_postgres_turnover_ledger_bankdetail_repository(...)` 的 nested service orchestration。
- 新增/保留薄 helper `_postgres_turnover_ledger_persistence_repository(...)`，只根据 supplied transaction 返回 `PostgresWorkbenchRepository(transaction)` 或 state store，不知道 routes、category service 或 relation operation。
- `TurnoverLedgerRelationWritePort.confirm_relation(...)` 的 rebuild 顺序调整为 confirm operation 前执行，以保持旧 helper 行为。
- 未改变 API response contract，未修改 SQL migration。

#### 验证

- `git status --short --branch`：Pass，仅有 PF-P097 范围内文件改动。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，45 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，49 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。
- `rg -n "TurnoverLedgerRelationWritePort|TurnoverLedgerBankdetailWritePort|_postgres_turnover_ledger_relation_repository|_postgres_turnover_ledger_bankdetail_repository|PF-P097" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py tests/test_turnover_ledger_api.py tests/test_turnover_ledger_uow_contract.py docs/architecture/backend-refactor`：Pass。

#### 下一条 Prompt 上下文

PF-P097 已 verified。当前分支已覆盖 PF-P094 到 PF-P097：repository ownership discovery、write port contract tests、write port skeleton、server composition wiring。下一步应生成并审查 `PF-P097-MG - Turnover Ledger Repository Ownership Cumulative Merge Gate`，覆盖当前分支相对 main 的完整 diff；MG 不得新增业务实现。

### PF-P097-MG - Turnover Ledger Repository Ownership Cumulative Merge Gate

状态：`verified`

#### 范围

- 覆盖当前分支 `codex/turnover-ledger-repository-ownership-p094` 相对 `main` 的完整 diff。
- 合并 PF-P094 到 PF-P097 的 repository ownership 切片。
- 只做 scope audit、untracked audit、diff check、targeted tests、文档状态检查、commit/merge/push。

#### 预期变更文件

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 禁止范围

- 不得新增业务实现。
- 不得执行 Traffic Gate、部署、生产配置、Nginx 或 feature flag 修改。

#### 执行结果

- 分支侧 scope audit 通过，`git diff --name-only main...HEAD` 仅包含预期 6 个文件。
- 分支侧无 untracked 临时文件，`git diff --check` 通过。
- 已 merge 到 `main`，merge commit `014b72e0`。
- main 上复验通过。
- 未执行 Traffic Gate，未部署，未修改生产配置。

#### main 复验

- `git status --short --branch`：Pass，main 仅 ahead `origin/main`。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，45 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，49 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。

#### 下一条 Prompt 上下文

PF-P097-MG 已 verified，待 `git push origin main`。push 完成后，必须从最新 main 新建下一条 `codex/` 分支。Turnover Ledger 下一切片应继续沿写路径收敛，优先选择 remaining PostgreSQL write ownership cleanup 或下一组 write path UoW/repository ownership，不得在 main 或旧分支继续开发。

### PF-P098 - Turnover Ledger Remaining Write Path Rebaseline / Next Slice Selection

状态：`verified`

#### 范围

- 基于 PF-P097-MG 后的最新 main，重新盘点 Turnover Ledger 剩余写路径。
- 更新 write path matrix、residual orchestration、service/repository ownership、test gaps 和 next slice decision。
- 只做 discovery/planning 和文档回写。

#### 允许变更文件

- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 禁止范围

- 不得修改 production code。
- 不得修改 tests。
- 不得新增 SQL migration。
- 不得执行 Traffic Gate、部署、生产配置或 Nginx 修改。

#### 执行结果

- 已基于 PF-P097-MG 后的最新 main 重新盘点 Turnover Ledger write paths。
- 确认 tag selection、bank row tags batch、relation extra、confirm、withdraw 都已有 facade/UoW seam。
- 确认 PostgreSQL bank row tags / confirm / withdraw 已接入 PF-P096/PF-P097 的 service-level write ports。
- 确认当前最大剩余 correctness gap 是 withdraw duplicate/stale write：现有 `test_withdraw_duplicate_submit_currently_allows_second_withdraw_and_reenqueues` 明确记录第二次 withdraw 仍会二次 mutation/refresh。
- 确认 `TurnoverLedgerWriteUnitOfWork` 已有 expected_versions / stale_precondition_port seam，但真实 relation write commands 尚未传 expected_versions，server composition 仍注入 no-op stale precondition port。

#### 验证

- `git status --short --branch`：Pass，仅有 PF-P098 文档范围改动。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `rg -n "PF-P098|Remaining Write Path Rebaseline|Next Slice Decision|Write Path Matrix|Residual Orchestration" docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md`：Pass。

#### 下一条 Prompt 上下文

PF-P098 已 verified。下一条应生成并审查 `PF-P099 - Turnover Ledger Withdraw Relation Stale/Duplicate Contract Tests`。PF-P099 只应新增/调整 tests，锁定 withdraw duplicate/stale write 的目标行为；不得修改 production code，不得同时处理 relation extra stale write、fallback cleanup 或 local transaction shim 抽离。

### PF-P099 - Turnover Ledger Withdraw Relation Stale/Duplicate Contract Tests

状态：`verified`

#### 范围

- 新增/调整 tests，锁定 Turnover Ledger withdraw relation duplicate/stale write 目标行为。
- 保留 current behavior characterization。
- 用 `unittest.expectedFailure` 记录尚未实现的 future target behavior。

#### 允许变更文件

- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 禁止范围

- 不得修改 production code。
- 不得同时处理 relation extra stale write、fallback cleanup 或 local transaction shim 抽离。

#### 执行结果

- 保留 current behavior test `test_withdraw_duplicate_submit_currently_allows_second_withdraw_and_reenqueues`。
- 新增 API future target test `test_target_withdraw_duplicate_submit_rejects_without_second_mutation_or_refresh`，使用 `unittest.expectedFailure`。
- 新增 UoW/facade future target test `test_target_withdraw_relation_facade_passes_expected_versions_before_repository`，使用 `unittest.expectedFailure`。
- 两条 target tests 锁定：duplicate/stale withdraw 不得二次 mutation/audit/refresh，facade 应支持 expected_versions 并让 UoW 在 stale 时阻止 repository handler。
- 未修改 production code。

#### 验证

- `git status --short --branch`：Pass，仅有 PF-P099 范围内 tests 改动。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，46 tests，1 expected failure。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，50 tests，1 expected failure。
- `rg -n "PF-P099|withdraw.*duplicate|expected_versions|expectedFailure|stale" tests/test_turnover_ledger_api.py tests/test_turnover_ledger_uow_contract.py docs/architecture/backend-refactor`：Pass。

#### 下一条 Prompt 上下文

PF-P099 已 verified。下一条应生成并审查 `PF-P100 - Turnover Ledger Withdraw Relation Expected Versions Skeleton`，只实现最小 expected_versions/stale guard skeleton，让 PF-P099 的 2 条 expectedFailure target tests 转为普通通过；不得处理 relation extra stale write、fallback cleanup 或 local transaction shim 抽离。

### PF-P100 - Turnover Ledger Withdraw Relation Expected Versions Skeleton

状态：`verified`

#### 范围

- 为 `TurnoverLedgerWriteFacade.withdraw_relation(...)` 增加 optional expected_versions 支持。
- 在 withdraw handler 中拒绝已 withdrawn relation 的 duplicate submit。
- 将 PF-P099 的 2 条 expectedFailure target tests 转为普通通过。

#### 允许变更文件

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 禁止范围

- 不得处理 relation extra stale write。
- 不得清理 fallback path。
- 不得抽离 local transaction shim。
- 不得修改 SQL migration、部署配置或生产配置。

#### 下一条 Prompt 上下文

PF-P100 已 verified。执行结果：

- `TurnoverLedgerWriteFacade.withdraw_relation(...)` 已支持 `expected_versions` 并写入 `TurnoverLedgerWriteCommand.expected_versions`。
- withdraw handler 已在 relation 当前状态为 `withdrawn` 时返回 409 `relation_already_withdrawn`，避免 duplicate submit 二次 mutation/audit/refresh。
- withdraw handler 调用 facade 时会用当前 relation `version` 构造 `relation:{relation_id}` expected version。
- PF-P099 的 2 条 target tests 已从 `unittest.expectedFailure` 转为普通通过。
- 旧的 duplicate-withdraw current behavior characterization 已收敛为当前新契约：第二次 withdraw 返回 409，且 audit/refresh 不增加。

验证：

- `git status --short --branch`：Pass，仅有 PF-P100/PF-P100-MG 范围内变更。
- `git ls-files --others --exclude-standard`：Pass，无 untracked 文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，46 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，50 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass。

下一条应执行 `PF-P100-MG - Turnover Ledger Withdraw Stale/Duplicate Cumulative Merge Gate`，统一覆盖 PF-P098 到 PF-P100 的完整 diff；不得直接进入 relation extra stale write、fallback cleanup 或下一模块。

### PF-P100-MG - Turnover Ledger Withdraw Stale/Duplicate Cumulative Merge Gate

状态：`verified`

#### 范围

- 只执行 Turnover Ledger withdraw stale/duplicate 切片的 cumulative Merge Gate。
- 覆盖 PF-P098、PF-P099、PF-P100 的完整 diff。
- 不新增业务实现，不开始 relation extra stale write、fallback cleanup、local transaction shim 抽离或其它模块。

#### 必须验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `git diff --name-only main...HEAD`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`

#### 下一条 Prompt 上下文

PF-P100-MG 已 verified。执行结果：

- 分支 `codex/turnover-ledger-next-slice-p098` 已合入 `main`。
- merge commit：`fac75b67`。
- main 上复验通过：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，46 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，50 tests。
  - `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass。
- 未执行 Traffic Gate、部署、生产配置或 Nginx 修改。

下一步：推送 `origin/main`。push 完成后，必须从最新 `main` 新建 `codex/` 分支，再生成下一条 Turnover Ledger prompt；不得在 `main` 或旧分支继续开发。

### PF-P101 - Turnover Ledger Relation Extra Stale/Idempotency Discovery and Planning

状态：`verified`

#### 范围

- 只做 Turnover Ledger relation extra stale/idempotency discovery/planning。
- 读取现有 relation extra handler、facade、normalizer、UoW tests、API tests 和服务代码，明确下一条测试锁定 prompt。
- 不修改 production code，不新增 tests，不执行 MG。

#### 目标

- 识别 relation extra 当前是否有 version/updated_at/updated_by 可作为 stale precondition。
- 识别 duplicate PUT / repeated same payload 当前行为和未来 durable idempotency 是否需要独立切片。
- 明确 relation extra stale write 的 API response、expected_versions key、兼容策略和测试边界。
- 更新 `turnover-ledger-write-uow-plan.md` 中 relation extra 剩余 gap。

#### 下一条 Prompt 上下文

PF-P101 已 verified。执行结果：

- 已确认 relation extra response 只有 `updated_at` / `updated_by`，没有 durable integer version。
- 已确认 `TurnoverLedgerWriteFacade.update_relation_extra(...)` 当前没有 `expected_versions` 参数，但 UoW 已具备 command-level expected_versions seam。
- 已确认 repeated same PUT 目前缺少 characterization；根据 service normalizer，重复 PUT 会更新 `updated_at` 并触发 refresh。
- 已确认 durable idempotency 不应和 stale guard 混在一个 prompt 内实现。
- 已更新 `turnover-ledger-write-uow-plan.md` 的 Relation Extra Stale / Idempotency Matrix。

验证：

- `git status --short --branch`：Pass，仅有 PF-P101 文档范围改动。
- `git ls-files --others --exclude-standard`：Pass。
- `git diff --check`：Pass。
- `rg -n "PF-P101|Relation Extra Stale|turnover_relation_extra|expected_versions|idempotency" docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md`：Pass。

下一条应生成并审查 `PF-P102 - Turnover Ledger Relation Extra Stale/Idempotency Characterization Tests`；PF-P102 只写 tests 和文档，不实现 stale guard。

### PF-P102 - Turnover Ledger Relation Extra Stale/Idempotency Characterization Tests

状态：`verified`

#### 范围

- 只新增/调整 Turnover Ledger relation extra stale/idempotency tests 和必要文档回写。
- 不修改 production code。
- 不实现 stale guard 或 durable idempotency store。

#### 测试目标

- 新增 repeated same PUT current behavior characterization。
- 新增 API future target expectedFailure：携带旧 `expected_versions={"turnover_relation_extra:<relation_id>": <old_updated_at>}` 时应返回 409，不保存、不 enqueue。
- 新增 facade/UoW future target expectedFailure：`update_relation_extra(..., expected_versions=...)` 应把 expected_versions 写入 command，并在 stale precondition 前阻止 extra repository save。

#### 下一条 Prompt 上下文

PF-P102 已 verified。执行结果：

- 新增 current behavior characterization：重复 PUT 相同 relation extra payload 当前会返回 200、更新 `extra.updated_at`，并 enqueue 两次 Turnover refresh。
- 新增 API future target `expectedFailure`：旧 `expected_versions={"turnover_relation_extra:<relation_id>": <old_updated_at>}` 应返回 409 `turnover_relation_extra_conflict`，不保存 stale payload，不 enqueue stale refresh。
- 新增 facade/UoW future target `expectedFailure`：`update_relation_extra(..., expected_versions=...)` 应把 expected_versions 写入 command，并在 stale precondition 前阻止 extra repository save。

验证：

- `git status --short --branch`：Pass，仅有 PF-P102 tests/docs 范围改动。
- `git ls-files --others --exclude-standard`：Pass。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，48 tests，1 expected failure。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，51 tests，1 expected failure。
- `rg -n "PF-P102|turnover_relation_extra|test_target_relation_extra|expected_versions|expectedFailure|same PUT|same payload" tests/test_turnover_ledger_api.py tests/test_turnover_ledger_uow_contract.py docs/architecture/backend-refactor`：Pass。

下一条应生成并审查 `PF-P103 - Turnover Ledger Relation Extra Expected Versions Skeleton`，只让 PF-P102 的 2 条 target tests 转为普通通过；不得实现 durable idempotency store。

### PF-P103 - Turnover Ledger Relation Extra Expected Versions Skeleton

状态：`verified`

#### 范围

- 只实现最小 relation extra expected_versions skeleton，让 PF-P102 的 2 条 target tests 转为普通通过。
- 不实现 durable idempotency store。
- 不处理 fallback cleanup 或 local transaction shim extraction。

#### 执行结果

- `TurnoverLedgerWriteFacade.update_relation_extra(...)` 已支持 optional `expected_versions` 参数，并写入 `TurnoverLedgerWriteCommand.expected_versions`。
- relation extra handler 在请求携带 `expected_versions["turnover_relation_extra:<relation_id>"]` 时会读取当前 `extra.updated_at`。
- 当前 `updated_at` 与 expected 不一致时返回 409 `turnover_relation_extra_conflict`，并且不执行 facade、extra save 或 dirty/outbox refresh。
- 未携带 `expected_versions` 的 legacy relation extra PUT 行为保持不变。
- PF-P102 的 2 条 target tests 已从 `unittest.expectedFailure` 转为普通通过。

#### 验证

- `git status --short --branch`：Pass，仅有 PF-P103 范围内 production/tests/docs 改动。
- `git ls-files --others --exclude-standard`：Pass，无未跟踪文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，48 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，51 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass。
- `rg -n "PF-P103|turnover_relation_extra_conflict|turnover_relation_extra:|expected_versions|test_target_relation_extra_facade|test_target_relation_extra_stale|expectedFailure" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py tests/test_turnover_ledger_api.py tests/test_turnover_ledger_uow_contract.py docs/architecture/backend-refactor`：Pass。

#### 下一条 Prompt 上下文

PF-P103 已 verified。下一条必须生成并执行 `PF-P103-MG - Turnover Ledger Relation Extra Expected Versions Cumulative Merge Gate`，统一覆盖 PF-P101 到 PF-P103 的完整 diff；不得直接进入 durable idempotency、fallback cleanup、local transaction shim extraction 或下一模块。

### PF-P103-MG - Turnover Ledger Relation Extra Expected Versions Cumulative Merge Gate

状态：`verified`

#### 范围

- 只执行 Turnover Ledger relation extra expected_versions 切片的 cumulative Merge Gate。
- 覆盖 PF-P101、PF-P102、PF-P103 的完整 diff。
- 不新增业务实现，不开始 durable idempotency、fallback cleanup、local transaction shim extraction 或其它模块。

#### 必须验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `git diff --name-only main...HEAD`
- `git log --oneline main..HEAD`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`

#### 执行结果

- 分支 `codex/turnover-ledger-next-slice-p101` 已合入 `main`。
- merge commit：`18fbb887`。
- MG 覆盖 PF-P101、PF-P102、PF-P103 的完整 diff。
- main 上复验通过。
- 未执行 Traffic Gate、部署、生产配置、Nginx 修改或真实外部服务访问。

#### main 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，48 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，51 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass。

#### 下一条 Prompt 上下文

PF-P103-MG 已 verified。下一步必须先执行 `git push origin main`。push 完成后，必须从最新 `main` 新建下一条 `codex/` 分支，再生成下一条 Turnover Ledger prompt；不得在 `main` 或旧分支继续开发。

### PF-P104 - Turnover Ledger Relation Extra Durable Idempotency Discovery and Planning

状态：`verified`

#### 范围

- 只做 relation extra durable idempotency discovery/planning。
- 优先评估复用 Workbench durable idempotency primitive 和 PostgreSQL repository。
- 不修改 production code、tests、SQL migration、前端或部署配置。

#### 执行结果

- 已确认 relation extra HTTP contract 当前不读取 body `idempotency_key` / `idempotencyKey`，也不读取 `Idempotency-Key` header。
- 已确认 PF-P103 stale guard 使用 `expected_versions["turnover_relation_extra:<relation_id>"]` 和当前 `extra.updated_at`。
- 已确认 Workbench `WorkbenchIdempotencyRecord`、`workbench_request_fingerprint`、`WorkbenchIdempotencyKeyConflict/InProgress/Failed`、`InMemoryWorkbenchIdempotencyRepository` 和 `PostgresWorkbenchIdempotencyRepository` 可作为 Turnover Ledger durable idempotency 的复用候选。
- 已确认 `TurnoverLedgerWriteUnitOfWork` 当前没有 `idempotency_store` seam，也没有 command-level `idempotency_key` / `request_fingerprint`，后续需要小切片引入，不能复制整个 Workbench UoW。
- 已在 `turnover-ledger-write-uow-plan.md` 写入 durable idempotency contract 草案和 PF-P105 测试边界。

#### 验证

- `git status --short --branch`：Pass，仅有 PF-P104 文档范围改动。
- `git ls-files --others --exclude-standard`：Pass。
- `git diff --check`：Pass。
- `rg -n "PF-P104|durable idempotency|idempotency_key|Idempotency-Key|workbench_idempotency|fingerprint|PF-P105" docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md`：Pass。

#### 下一条 Prompt 上下文

PF-P104 已 verified。下一条应生成并审查 `PF-P105 - Turnover Ledger Relation Extra Durable Idempotency Characterization Tests`。PF-P105 只应新增 tests 和文档，先锁定 durable idempotency target behavior；不得直接实现 production idempotency store、UoW seam 或 repository 接线。

### PF-P105 - Turnover Ledger Relation Extra Durable Idempotency Characterization Tests

状态：`verified`

#### 范围

- 只新增 Turnover Ledger relation extra durable idempotency characterization/contract tests。
- 不修改 production code。
- 不实现 idempotency key 参数、store、repository、adapter 或 UoW seam。

#### 执行结果

- 新增 API future target `expectedFailure`：相同 actor/tenant/idempotency key + 相同 payload/fingerprint 的第二次 relation extra PUT 应 replay 第一次 response，不二次 save/enqueue。
- 新增 API future target `expectedFailure`：相同 actor/tenant/idempotency key + 不同 payload/fingerprint 应返回 409 `idempotency_key_conflict`，不保存第二个 payload，不 enqueue 第二次 refresh。
- 新增 facade/UoW future target `expectedFailure`：`TurnoverLedgerWriteFacade.update_relation_extra(..., idempotency_key=...)` 应将 idempotency identity/fingerprint 写入 command，UoW 在 handler 前 reserve/replay/conflict。
- 现有 current behavior characterization 保持普通通过：无 idempotency key 时 repeated same PUT 仍更新 marker 并 enqueue 两次 refresh。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，50 tests，2 expected failures。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，52 tests，1 expected failure。

#### 下一条 Prompt 上下文

PF-P105 已 verified。下一条应生成并审查 `PF-P106 - Turnover Ledger Relation Extra Idempotency Command Skeleton`。PF-P106 只应实现最小 command/facade idempotency fields，让 facade/UoW target command test 转绿；不得直接实现 full replay/conflict HTTP behavior、PostgreSQL repository 接线、fallback cleanup 或 local transaction shim extraction。

### PF-P106 - Turnover Ledger Relation Extra Idempotency Command Skeleton

状态：`verified`

#### 范围

- 只实现 relation extra command/facade idempotency fields。
- 不修改 `server.py`。
- 不实现 API replay/conflict behavior。
- 不接入 idempotency store/repository。
- 不修改 `TurnoverLedgerWriteUnitOfWork.run`。

#### 执行结果

- `TurnoverLedgerWriteCommand` 新增 `idempotency_key` 和 `request_fingerprint` 字段。
- `TurnoverLedgerWriteFacade.update_relation_extra(...)` 新增 optional `idempotency_key` 参数。
- relation extra idempotency command 使用 `workbench_request_fingerprint(...)` 计算 request fingerprint。
- 有 idempotency key 时，command `action_name` 使用 `turnover_relation_extra_update`。
- PF-P105 的 facade/UoW command target test 已从 `unittest.expectedFailure` 转为普通通过。
- PF-P105 的两个 API-level replay/conflict target tests 继续保持 `unittest.expectedFailure`。

#### 验证

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，52 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，50 tests，2 expected failures。
- `python3 -m compileall backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass。

#### 下一条 Prompt 上下文

PF-P106 已 verified。当前分支已完成 PF-P104 discovery、PF-P105 tests、PF-P106 minimal command skeleton，建议下一条生成 `PF-P106-MG - Turnover Ledger Relation Extra Durable Idempotency Contract Cumulative Merge Gate`，统一覆盖 PF-P104 到 PF-P106 的完整 diff；不得继续扩大到 UoW idempotency store seam、API replay/conflict 或 fallback/local transaction shim。

### PF-P106-MG - Turnover Ledger Relation Extra Durable Idempotency Contract Cumulative Merge Gate

状态：`verified`

#### 范围

- 只执行 Turnover Ledger relation extra durable idempotency contract 切片的 cumulative Merge Gate。
- 覆盖 PF-P104、PF-P105、PF-P106 的完整 diff。
- 不新增业务实现，不开始 API replay/conflict、idempotency store/UoW seam、fallback cleanup、local transaction shim extraction 或其它模块。

#### 必须验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `git diff --name-only main...HEAD`
- `git log --oneline main..HEAD`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`

#### 执行结果

- 分支：`codex/turnover-ledger-next-slice-p104`
- Merge commit：`e2c97b89`
- 分支验证：
  - `git status --short --branch`：clean on feature branch
  - `git ls-files --others --exclude-standard`：empty
  - `git diff --check`：Pass
  - `git diff --name-only main...HEAD`：只包含 PF-P104 到 PF-P106 允许文件
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，50 tests，2 expected failures
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，52 tests
  - `python3 -m compileall backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass
- `main` 验证：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，50 tests，2 expected failures
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，52 tests
  - `python3 -m compileall backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass
- Traffic Gate：未执行；本切片只合入代码和测试基线，不部署、不切流、不访问生产。

#### 下一条 Prompt 上下文

PF-P106-MG 已 verified。先提交本次 post-flight 文档更新并 `git push origin main`。push 完成后必须从最新 `main` 新建下一条 `codex/` 分支，再生成并审查下一条 Turnover Ledger relation extra idempotency 后续 prompt。

### PF-P107 - Turnover Ledger Relation Extra Idempotency UoW Store Seam

状态：`verified`

#### 范围

- 只在 Turnover Ledger UoW 层建立 relation extra idempotency store seam。
- 复用现有 Workbench idempotency primitive 和 helper，不新增平行实现。
- 为 `TurnoverLedgerWriteUnitOfWork.run(...)` 增加最小 idempotency reservation/replay/conflict contract tests。
- 不修改 `server.py`，不读取 HTTP header/cookie，不实现 API-level replay/conflict，不让 PF-P105 两个 API expectedFailure 转绿。
- 不新增 SQL migration，不接入真实 PostgreSQL idempotency repository，不改其它 Turnover 写路径语义。

#### 必须验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `python3 -m compileall backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`

#### 下一条 Prompt 上下文

PF-P107 verified。已在 `TurnoverLedgerWriteUnitOfWork` 中建立 optional `idempotency_store` seam，复用 Workbench idempotency helper，在 UoW 层实现 reserve/replay/conflict/in-progress；新增 UoW contract tests 已转绿。`tests/test_turnover_ledger_api.py` 中两个 API-level replay/conflict expectedFailure 仍按计划保留。下一条应生成并审查 `PF-P108 - Turnover Ledger Relation Extra Idempotency HTTP Boundary and Error Mapping`，只处理 handler 读取 body idempotency key、注入 facade/UoW、HTTP replay/conflict/in-progress mapping；不得新增 SQL migration 或跨到其它 Turnover 写路径。

#### 执行结果

- 变更文件：
  - `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`
  - `tests/test_turnover_ledger_uow_contract.py`
- 关键结果：
  - `TurnoverLedgerWriteUnitOfWork.__init__` 新增 optional `idempotency_store` 细粒度依赖，默认不传时保持旧行为。
  - `run(command, handler)` 在 command 带 `idempotency_key` 且 UoW 有 store 时执行 idempotency get/reserve/replay/conflict/in-progress/commit。
  - idempotency reservation/commit 在当前 UoW transaction-bound store 内执行。
  - 复用 `workbench_uow.py` / `workbench_idempotency.py` 既有 primitive；未复制新状态机。
  - API-level replay/conflict expectedFailure 仍保留。
- 验证：
  - `git status --short --branch`：只包含 PF-P107 允许文件
  - `git ls-files --others --exclude-standard`：empty
  - `git diff --check`：Pass
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，50 tests，2 expected failures
  - `python3 -m compileall backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass

### PF-P108 - Turnover Ledger Relation Extra Idempotency HTTP Boundary and Error Mapping

状态：`verified`

#### 范围

- 只处理 Turnover Ledger relation extra HTTP boundary 的 idempotency key extraction 和 error mapping。
- `server.py` 可读取 JSON body 的 `idempotency_key` / `idempotencyKey` 并传给 `TurnoverLedgerWriteFacade.update_relation_extra(...)`。
- postgres facade construction 可复用 `_workbench_write_idempotency_store(...)`，将 durable-capable store 注入 `TurnoverLedgerWriteUnitOfWork`；local path 可使用 in-memory store 维持测试/开发 idempotency 语义，但不得声明为 durable。
- 捕获 Workbench idempotency conflict/in-progress/failed 异常并映射为 HTTP 409 JSON。
- 让 PF-P105 的两个 API-level relation extra idempotency expectedFailure 转为普通通过。

#### 禁止范围

- 不新增 SQL migration，不修改 idempotency repository schema。
- 不改其它 Turnover 写路径。
- 不修改 Workbench 写路径。
- 不执行 Traffic Gate、部署、生产访问或真实外部服务访问。

#### 必须验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`

#### 下一条 Prompt 上下文

PF-P108 verified。Relation extra HTTP endpoint 已支持 body `idempotency_key` / `idempotencyKey`，并通过 facade/UoW 执行 replay/conflict/in-progress；两个 API-level relation extra idempotency target tests 已从 expectedFailure 转为普通通过。下一条应生成 `PF-P108-MG - Turnover Ledger Relation Extra Idempotency Cumulative Merge Gate`，统一覆盖 PF-P107 + PF-P108 完整 diff。

#### 执行结果

- 变更文件：
  - `backend/src/fin_ops_platform/app/server.py`
  - `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
  - `tests/test_turnover_ledger_api.py`
  - `tests/test_turnover_ledger_uow_contract.py`
- 关键结果：
  - relation extra facade construction 为 postgres path 注入 durable-capable idempotency store；local path 使用 in-memory store 保持测试/开发 idempotency 语义。
  - relation extra handler 从 body 读取 `idempotency_key` / `idempotencyKey` 并传入 facade。
  - handler 捕获 `WorkbenchIdempotencyKeyConflict`、`WorkbenchIdempotencyInProgress`、`WorkbenchIdempotencyFailed` 并返回 HTTP 409 JSON。
  - 两个 API-level relation extra idempotency expectedFailure 已转为普通通过。
  - relation extra refresh reason 固定为 `turnover_relation_extra_changed`，避免 idempotency action name 改变读模型刷新契约。
- 验证：
  - `git status --short --branch`：只包含 PF-P108 允许文件
  - `git ls-files --others --exclude-standard`：empty
  - `git diff --check`：Pass
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，50 tests
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests
  - `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass

### PF-P108-MG - Turnover Ledger Relation Extra Idempotency Cumulative Merge Gate

状态：`verified`

#### 范围

- 只执行 relation extra idempotency 切片的 cumulative Merge Gate。
- 统一覆盖 PF-P107、PF-P108 的完整 diff。
- 不新增业务实现，不继续迁移其它 Turnover 写路径，不处理 SQL migration 或 Traffic Gate。

#### 必须验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `git diff --name-only main...HEAD`
- `git log --oneline main..HEAD`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`

#### 下一条 Prompt 上下文

PF-P108-MG 已 verified。先提交本次 post-flight 文档更新并 `git push origin main`。push 完成后必须从最新 `main` 新建下一条 `codex/` 分支，再根据 Turnover Ledger 当前剩余风险生成下一条 prompt。

#### 执行结果

- 分支：`codex/turnover-ledger-next-slice-p107`
- Merge commit：`7edcb0b5`
- 分支验证：
  - `git status --short --branch`：clean on feature branch
  - `git ls-files --others --exclude-standard`：empty
  - `git diff --check`：Pass
  - `git diff --name-only main...HEAD`：只包含 PF-P107/PF-P108 允许文件
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，50 tests
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests
  - `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass
- `main` 验证：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，50 tests
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests
  - `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`：Pass
- Traffic Gate：未执行；本切片不部署、不切流、不访问生产。

### PF-P115 - Turnover Ledger Relation Local Adapter Extraction

状态：`verified`

#### 范围

- 抽离 confirm/withdraw 共用的 local relation transaction/repository adapter。
- 保持 local relation rollback、confirm/withdraw queue failure rollback、affected_months 行为不变。
- 不处理 bank row tags/tag selection local shim。

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`

#### 执行结果

- `TurnoverLedgerLocalRelationConnection` 已迁入 `turnover_ledger_write_adapters.py`，通过明确的 snapshot provider / replace / save callbacks 处理 local transaction rollback 与成功保存。
- `TurnoverLedgerLocalRelationRepository` 已迁入 `turnover_ledger_write_adapters.py`，confirm path 通过显式 `relation_rebuild` callable 触发关系重建，withdraw path 只调用 route adapter。
- `server.py` 已删除 confirm/withdraw 专用 local connection/repository helper，只保留 adapter 组装与依赖传入。
- 未修改 tests、facade/UoW 语义、SQL migration、部署配置或 Traffic Gate。

#### Verification Result

- `git status --short --branch`：Pass，仅包含 PF-P115 允许文件。
- `git ls-files --others --exclude-standard`：Pass，无 untracked 文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，53 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。

#### 下一条 Prompt 上下文

PF-P115 已完成 confirm/withdraw relation local adapter extraction。剩余 local shim 中，tag selection local transaction/settings writer 仍在 `server.py`，范围比 bank row tags 更小，适合作为下一条最小实现切片。下一条应生成并审查 `PF-P116 - Turnover Ledger Tag Selection Local Adapter Extraction`：只抽离 tag selection local connection/settings repository，不处理 bank row tags，不进入 MG。

### PF-P116 - Turnover Ledger Tag Selection Local Adapter Extraction

状态：`verified`

#### 范围

- 抽离 tag selection local transaction/settings writer adapter。
- 保持 local app settings rollback、version conflict、queue failure rollback 和 read model refresh enqueue 行为不变。
- 不处理 bank row tags local shim。

#### 允许文件

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`

#### 执行结果

- `TurnoverLedgerLocalTagSelectionConnection` 已迁入 `turnover_ledger_write_adapters.py`，通过明确的 settings snapshot provider / save / refresh callbacks 处理 local rollback。
- `TurnoverLedgerLocalTagSelectionSettingsWriter` 已迁入 `turnover_ledger_write_adapters.py`，负责保存 next app settings snapshot 并刷新 local app settings service snapshot。
- `server.py` 已删除 `_local_turnover_ledger_tag_selection_connection(...)` 和 `_save_local_turnover_ledger_tag_selection(...)`，只保留 adapter 组装。
- 未修改 tests、facade/UoW 语义、SQL migration、部署配置或 Traffic Gate。

#### Verification Result

- `git status --short --branch`：Pass，仅包含 PF-P116 允许文件。
- `git ls-files --others --exclude-standard`：Pass，无 untracked 文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，53 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。

#### 下一条 Prompt 上下文

PF-P115/PF-P116 已连续抽离 confirm/withdraw relation local adapter 和 tag selection local adapter。当前分支已达到一个小型可合并边界；下一条应生成并审查 `PF-P116-MG - Turnover Ledger Local Relation and Tag Selection Adapter Merge Gate`，统一覆盖 PF-P115 到 PF-P116 完整 diff。bank row tags local shim 仍未处理，因涉及 Bankdetail/category/relation 交叉边界，应在 MG 后从最新 main 新建分支再做 discovery/characterization。

### PF-P116-MG - Turnover Ledger Local Relation and Tag Selection Adapter Merge Gate

状态：`verified`

#### Gate Scope

- 统一覆盖 PF-P115 到 PF-P116 的完整 diff。
- 只包含 confirm/withdraw relation local adapter extraction、tag selection local adapter extraction、prompt/status/专项文档回写。
- 不处理 bank row tags local shim。

#### 允许文件

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `git diff --name-only main...HEAD`
- `git log --oneline main..HEAD`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`

#### 执行结果

- 分支：`codex/turnover-ledger-next-slice-p115`
- Merge commit：`9d5e4904`
- Branch 验证：
  - `git status --short --branch`：clean on feature branch。
  - `git ls-files --others --exclude-standard`：empty。
  - `git diff --check`：Pass。
  - `git diff --name-only main...HEAD`：只包含 PF-P115/PF-P116 允许文件。
  - `git log --oneline main..HEAD`：只包含 PF-P115、PF-P116、PF-P116-MG 相关提交。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，53 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
  - `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。
- `main` 验证：
  - `git status --short --branch`：`main...origin/main [ahead 6]`，无 dirty changes。
  - `git ls-files --others --exclude-standard`：empty。
  - `git diff --check`：Pass。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，53 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
  - `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。
- Traffic Gate：未执行；本 MG 不部署、不切流、不访问生产。

#### 下一条 Prompt 上下文

PF-P116-MG 已合入 main 并通过 main 验证。下一步先提交本次 post-flight 文档并执行 `git push origin main`；push 完成后必须从最新 main 新建 `codex/` 分支。剩余 Turnover Ledger local shim 是 bank row tags，本地路径涉及 Bankdetail/category/relation 交叉边界，下一条应先做 discovery/characterization，不直接抽离实现。

### PF-P117 - Turnover Ledger Bank Row Tags Local Shim Discovery and Characterization Planning

状态：`verified`

#### 范围

- 盘点 bank row tags local connection、local bankdetail port、handler direct fallback 和现有测试覆盖。
- 输出 characterization test gap 和下一条最小测试 prompt。
- 不修改 production code，不抽离 adapter，不新增 SQL migration。

#### 必须扫描

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `rg -n "PF-P117|Bank Row Tags Local Shim|bank row tags local" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 执行结果

##### Bank Row Tags Local Shim Inventory

- `_turnover_ledger_bank_row_tags_write_facade(...)` 的 local path 仍在 `server.py` 内组装：
  - `_local_turnover_ledger_bank_row_tags_connection(state_store)`；
  - `_local_turnover_ledger_bankdetail_port()`；
  - `TurnoverLedgerLocalDirtyOutboxWriter(queue_repository=queue_repository)`。
- `_local_turnover_ledger_bank_row_tags_connection(...)` 捕获两个 snapshot：
  - `_bank_transaction_category_service.snapshot()`；
  - `_turnover_relation_service.snapshot()`。
- local transaction failure path：
  - restore bank category snapshot；
  - restore turnover relation snapshot；
  - save previous category snapshot to state_store；
  - save previous relation snapshot to state_store；
  - re-raise。
- local transaction success path：
  - save current bank category snapshot；
  - save current turnover relation snapshot。
- `_local_turnover_ledger_bankdetail_port(...)` 直接调用：
  - `_bank_transaction_category_service.apply_turnover_updates(...)`；
  - `_turnover_relation_service.rebuild_from_bank_rows(_turnover_bank_transaction_rows())`。
- handler facade None fallback 仍直接执行：
  - `apply_turnover_updates(...)`；
  - `state_store.save_bank_transaction_categories(...)`；
  - `rebuild_from_bank_rows(...)`；
  - `_after_turnover_relation_mutation(affected_months)`，包含 direct read model clear/enqueue。

##### Runtime Sequence

- PostgreSQL facade path：handler validate target rows -> calculate affected months -> facade -> `TurnoverLedgerBankdetailWritePort` -> category update + relation rebuild + persistence repository save -> transaction-bound dirty/outbox。
- Local facade path：handler validate target rows -> calculate affected months -> facade -> local connection snapshot transaction -> local bankdetail port apply category update + relation rebuild -> local dirty/outbox enqueue -> transaction success saves category/relation snapshots。
- Local facade queue failure path：category/relation mutate first -> dirty/outbox enqueue raises -> local connection restores and saves previous category/relation snapshots -> exception propagates。
- Facade None fallback path：handler apply category update directly -> after success save category snapshot -> rebuild relation snapshot -> `_after_turnover_relation_mutation(...)` clears/enqueues read models directly。该路径是 legacy/local compatibility，不是目标架构。

##### Characterization Test Gap

- 已有覆盖：
  - facade None queue failure currently happens after category save；
  - target local facade queue failure rolls back category save；
  - target local/postgres facade path does not directly clear read model；
  - bank row tags facade uses explicit bankdetail port；
  - bankdetail write port rejects Application god object and persists categories/relations through explicit repository。
- 缺口：
  - local facade queue failure 还没有显式断言 relation snapshot 也被 rollback/save previous；
  - local facade success 还没有显式断言 category snapshot 与 relation snapshot 都通过 state_store 保存；
  - local bankdetail port 的 apply -> relation rebuild 顺序未被独立锁定；
  - facade None fallback 的 direct save/rebuild/enqueue 行为只部分锁定，抽离前应明确它是 legacy compatibility，不应被 adapter extraction 误删。

##### Extraction Risk

- 该路径跨 Turnover Ledger 与 Bankdetail/category service，不能把 Bankdetail 业务规则搬进 Turnover adapter。
- 抽离时 adapter 必须接收 category service、relation service、bank rows provider、snapshot save/restore callbacks 等明确依赖，不能接收 `Application`。
- state_store save order 和 relation rebuild timing 会影响测试语义。
- affected_months 仍应由 handler HTTP mapping 层计算并传入 facade；adapter 不应读取 request/header/cookie。

#### 下一条 Prompt 上下文

PF-P117 已确认 bank row tags local shim 仍需测试锁定后再抽离。下一条应生成并审查 `PF-P118 - Turnover Ledger Bank Row Tags Local Shim Characterization Tests`，只补 tests 和文档，不修改 production code。PF-P118 应重点覆盖 local facade relation rollback、local success save category/relation snapshots、local bankdetail port update/rebuild 顺序、facade None fallback legacy direct side effects。

### PF-P118 - Turnover Ledger Bank Row Tags Local Shim Characterization Tests

状态：`verified`

#### 范围

- 只补 bank row tags local shim characterization tests。
- 锁定 local facade queue failure 对 category/relation snapshot 的 rollback。
- 锁定 local facade success 保存 category/relation snapshots。
- 锁定 local bankdetail port apply -> relation rebuild 顺序。
- 锁定 facade None fallback 的 legacy direct side effects。

#### 允许文件

- `tests/test_turnover_ledger_api.py`
- 必要时 `tests/test_turnover_ledger_uow_contract.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`

#### 执行结果

- `tests/test_turnover_ledger_api.py` 新增 3 个 characterization tests：
  - `test_target_turnover_bank_row_tag_batch_queue_failure_rolls_back_relation_snapshot`；
  - `test_target_turnover_bank_row_tag_batch_local_facade_saves_snapshots_and_rebuilds_after_apply`；
  - `test_turnover_bank_row_tag_batch_facade_none_keeps_legacy_direct_side_effects`。
- 已锁定：
  - local facade queue failure 会 rollback category snapshot 和 relation snapshot，并保存 previous snapshots；
  - local facade success 会保存 category/relation snapshots，并保持 apply -> rebuild 顺序；
  - local facade path 不直接 clear read model；
  - facade None fallback 仍保留 direct save/rebuild/direct invalidation 的 legacy compatibility behavior。
- 未修改 production code、facade/UoW 语义、SQL migration、部署配置或 Traffic Gate。

#### Verification Result

- `git status --short --branch`：Pass，仅包含 PF-P118 允许文件。
- `git ls-files --others --exclude-standard`：Pass，无 untracked 文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，56 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。

#### 下一条 Prompt 上下文

PF-P118 已完成 bank row tags local shim 抽离前的测试锁定。下一条可生成并审查 `PF-P119 - Turnover Ledger Bank Row Tags Local Adapter Extraction`：只把 `_local_turnover_ledger_bank_row_tags_connection(...)` 和 `_local_turnover_ledger_bankdetail_port(...)` 迁入 `turnover_ledger_write_adapters.py`，不得改 handler facade None fallback，且不得把 Bankdetail 业务规则搬入 Turnover adapter。

### PF-P119 - Turnover Ledger Bank Row Tags Local Adapter Extraction

状态：`verified`

#### 范围

- 抽离 bank row tags local connection 和 local bankdetail port。
- 保持 PF-P118 锁定的 rollback/save/order/fallback 行为不变。
- 不修改 handler facade None fallback。

#### 允许文件

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`

#### 执行结果

- `TurnoverLedgerLocalBankRowTagsConnection` 已迁入 `turnover_ledger_write_adapters.py`：
  - 通过明确的 category/relation snapshot provider、replace callbacks、save callbacks 保持 local transaction rollback/save 行为。
- `TurnoverLedgerLocalBankdetailPort` 已迁入 `turnover_ledger_write_adapters.py`：
  - 接收 category service、relation service、bank rows provider；
  - 保持 apply category update -> relation rebuild 顺序；
  - 不接收 `Application`，不复制 Bankdetail 业务规则。
- `server.py` 删除 `_local_turnover_ledger_bank_row_tags_connection(...)` 和 `_local_turnover_ledger_bankdetail_port(...)`，只保留 adapter 组装。
- 未修改 handler facade None fallback、facade/UoW 语义、SQL migration、部署配置或 Traffic Gate。

#### Verification Result

- `git status --short --branch`：Pass，仅包含 PF-P119 允许文件。
- `git ls-files --others --exclude-standard`：Pass，无 untracked 文件。
- `git diff --check`：Pass。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，56 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。

#### 下一条 Prompt 上下文

PF-P117/PF-P118/PF-P119 已形成一个可合并切片：bank row tags local shim discovery、characterization tests、local adapter extraction。下一条应生成并审查 `PF-P119-MG - Turnover Ledger Bank Row Tags Local Adapter Cumulative Merge Gate`，统一覆盖 PF-P117 到 PF-P119 完整 diff。

### PF-P119-MG - Turnover Ledger Bank Row Tags Local Adapter Cumulative Merge Gate

状态：`verified`

#### Gate Scope

- 统一覆盖 PF-P117 到 PF-P119 的完整 diff。
- 只包含 bank row tags local shim discovery、characterization tests、local adapter extraction 和文档回写。

#### 允许文件

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `tests/test_turnover_ledger_api.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `git diff --name-only main...HEAD`
- `git log --oneline main..HEAD`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`

#### 执行结果

- 分支：`codex/turnover-ledger-bank-row-tags-local-shim-p117`
- Merge commit：`0aaf9285`
- Branch 验证：
  - `git status --short --branch`：clean on feature branch。
  - `git ls-files --others --exclude-standard`：empty。
  - `git diff --check`：Pass。
  - `git diff --name-only main...HEAD`：只包含 PF-P117/PF-P118/PF-P119 允许文件。
  - `git log --oneline main..HEAD`：只包含 PF-P117、PF-P118、PF-P119、PF-P119-MG 相关提交。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，56 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
  - `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。
- `main` 验证：
  - `git status --short --branch`：`main...origin/main [ahead 8]`，无 dirty changes。
  - `git ls-files --others --exclude-standard`：empty。
  - `git diff --check`：Pass。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，56 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
  - `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。
- Traffic Gate：未执行；本 MG 不部署、不切流、不访问生产。

#### 下一条 Prompt 上下文

PF-P119-MG 已合入 main 并通过 main 验证。下一步先提交本次 post-flight 文档并执行 `git push origin main`；push 完成后必须从最新 main 新建 `codex/` 分支，再根据 Turnover Ledger 剩余重构清单生成下一条 prompt。

### PF-P120 - Turnover Ledger Facade None Fallback Rebaseline and Handler Thinness Planning

状态：`verified`

#### 范围

- 盘点 Turnover Ledger 写 handler 中所有 `facade is None` fallback。
- 评估哪些 fallback 仍是 local/dev/test compatibility，哪些可进入后续 cleanup。
- 输出 handler thinness gap、characterization test gap 和下一条最小 prompt。
- 不修改 production code，不修改 tests。

#### 必须扫描

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `rg -n "PF-P120|Facade None Fallback|Handler Thinness" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 执行结果

Facade None Fallback Matrix：

| 写入口 | fallback 触发条件 | direct side effects | 当前测试覆盖 | 目标状态 |
| --- | --- | --- | --- | --- |
| tag selection update | `_turnover_ledger_tag_selection_write_facade()` 因 `state_store`、`queue_repository` 或 queue API 缺失返回 `None`；当前没有显式 override None 语义。 | handler 直接调用 `AppSettingsService.update_turnover_ledger_tag_selection(...)`，随后直接 clear Turnover Ledger read model 并 enqueue refresh。 | 已覆盖 UoW/local facade path 的 queue rollback 和 no direct clear；缺少 facade None fallback 的 direct update/clear/enqueue characterization。 | local/dev/test 兼容期可暂留，但必须先补 fallback characterization tests，之后再考虑让 local facade construction 更稳定返回 facade 并删除 direct fallback。 |
| bank row tags batch | `_turnover_ledger_bank_row_tags_write_facade()` 因依赖缺失返回 `None`，或测试显式 monkeypatch 为 `None`。 | handler 直接 apply bank category、save category snapshot、rebuild turnover relation、执行 `_after_turnover_relation_mutation(...)`。 | PF-P118 已覆盖显式 facade None direct save/rebuild/invalidation，以及 local facade success/rollback；依赖缺失导致 None 的行为仍未单独锁定。 | 可以作为后续 cleanup 候选，但应先补“queue missing -> facade None”和“override None”区分测试，避免误删 local compatibility。 |
| relation extra update | `_turnover_ledger_relation_extra_write_facade()` 因依赖缺失返回 `None`，或测试显式 monkeypatch 为 `None`。 | handler 直接调用 `TurnoverLedgerApiRoutes.update_relation_extra(...)`，随后 best-effort persist extra、clear read model、enqueue refresh。 | 已覆盖 facade path 不触发 legacy side effects、queue failure after direct update、target rollback；缺少 facade None success direct persist/clear/enqueue 的正向 characterization。 | fallback 暂留；下一步先锁定 direct fallback 正向行为，再最小化 cleanup。 |
| confirm relation | `_turnover_ledger_confirm_write_facade()` 因依赖缺失返回 `None`，或 `_turnover_ledger_confirm_write_facade_override = None`。 | handler 直接 rebuild relation、调用 route confirm、执行 `_after_turnover_relation_mutation(...)`，该 helper 还会触发 workbench invalidation、relation persistence、Turnover Ledger read model clear/enqueue。 | 已覆盖 facade override 跳过 after-mutation、queue failure after direct confirm、target rollback、Postgres facade readiness；缺少 facade None success direct rebuild/after-mutation 的明确 characterization。 | fallback 暂留；后续删除前需锁定 legacy success side effects 与依赖缺失触发条件。 |
| withdraw relation | `_turnover_ledger_withdraw_write_facade()` 因依赖缺失返回 `None`，或 `_turnover_ledger_withdraw_write_facade_override = None`。 | handler 先读取 relation detail、构造 expected_versions；fallback 直接 route withdraw，再执行 `_after_turnover_relation_mutation(...)`。 | 已覆盖 facade override 跳过 after-mutation、queue failure after direct withdraw、target rollback、Postgres facade readiness；缺少 facade None success direct withdraw/after-mutation 的明确 characterization。 | fallback 暂留；后续删除前需锁定 legacy success side effects 与依赖缺失触发条件。 |

Handler Thinness Gap：

- 可保留在 handler 的职责：session/auth 解析、JSON body 解析、HTTP status mapping、response JSON 包装、path/query/body 的基础 shape 校验。
- 应继续迁出的职责：facade construction fallback 决策、local/dev/test direct mutation、snapshot persistence、read model clear/enqueue、Workbench/Bankdetail invalidation orchestration、relation rebuild sequencing。
- 当前最重的 handler fallback 是 bank row tags 和 confirm/withdraw，因为它们仍在 handler 中组合跨模块 side effects；relation extra 和 tag selection 也仍在 handler 中承担直接持久化/刷新调度。

Compatibility Decision：

- 短期保留所有 `facade is None` fallback，因为它们仍承担 local/dev/test 和依赖缺失场景的兼容路径。
- 不应直接删除 fallback；应先补 characterization tests，把“依赖缺失导致 facade None”和“测试显式 override None”分开锁定。
- 后续 cleanup 的优先级：先 tag selection / relation extra 正向 fallback 测试，再 confirm/withdraw success fallback 测试，最后 bank row tags dependency-missing fallback 测试；测试锁定后再分入口最小删除或收敛到稳定 local facade construction。

Characterization Test Gap：

- 缺少 tag selection facade None fallback direct update、read model clear、refresh enqueue 的正向测试。
- 缺少 relation extra facade None fallback direct update、best-effort persist、read model clear、refresh enqueue 的正向测试。
- 缺少 confirm relation facade None success path 的 direct rebuild、route confirm、after-mutation side effect 顺序/结果测试。
- 缺少 withdraw relation facade None success path 的 route withdraw、after-mutation side effect 顺序/结果测试。
- bank row tags 已有显式 override None 测试，但仍缺少 `queue_repository` 缺失/不合格导致 facade construction 返回 None 的兼容测试。

Verification：

- `git status --short --branch`：Pass，当前分支为 `codex/turnover-ledger-remaining-boundary-p120`。
- `git ls-files --others --exclude-standard`：Pass。
- `git diff --check`：Pass。
- `rg -n "PF-P120|Facade None Fallback|Handler Thinness" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`：Pass。

#### 下一条 Prompt 上下文

PF-P120 已确认 fallback 不能直接删除。下一条应生成并审查 `PF-P121 - Turnover Ledger Facade None Fallback Characterization Tests`：只补 tests 和文档，不修改 production code。PF-P121 应覆盖 tag selection、relation extra、confirm relation、withdraw relation 的 facade None 正向兼容行为，并补 bank row tags dependency-missing fallback；不得删除 fallback，不得引入 UoW 语义变更。

### PF-P121 - Turnover Ledger Facade None Fallback Characterization Tests

状态：`verified`

#### 范围

- 为 PF-P120 识别的 `facade is None` fallback 补 characterization tests。
- 只修改 Turnover Ledger API tests 和后端重构文档。
- 不修改 production code，不删除 fallback，不改变 UoW/facade 语义。

#### 必须覆盖

- tag selection facade None success fallback：direct settings update、read model clear、refresh enqueue。
- relation extra facade None success fallback：direct extra update、best-effort persist、read model clear、refresh enqueue。
- confirm relation facade None success fallback：relation rebuild、route confirm、`_after_turnover_relation_mutation(...)` side effects。
- withdraw relation facade None success fallback：route withdraw、`_after_turnover_relation_mutation(...)` side effects。
- bank row tags dependency-missing fallback：当 facade construction 因 queue API 不可用返回 `None` 时，保持 legacy direct side effects。

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`

#### 下一条 Prompt 上下文

PF-P121 已新增 5 个 characterization tests：

- `test_turnover_ledger_tag_selection_facade_none_keeps_legacy_direct_update_and_refresh`
- `test_relation_extra_facade_none_keeps_legacy_direct_update_persist_and_refresh`
- `test_confirm_relation_facade_none_keeps_legacy_rebuild_confirm_and_after_mutation`
- `test_withdraw_relation_facade_none_keeps_legacy_withdraw_and_after_mutation`
- `test_turnover_bank_row_tag_batch_dependency_missing_keeps_legacy_direct_side_effects`

Verification：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，61 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。

当前 fallback 行为已足够进入 cleanup planning。下一条应生成并审查 `PF-P122 - Turnover Ledger Facade None Fallback Cleanup Planning`：只规划最小 cleanup 顺序，决定先移除哪个 fallback 或先稳定哪类 facade construction；不直接修改 production code。

### PF-P109 - Turnover Ledger Remaining Write Path Rebaseline / Fallback Cleanup Decision

状态：`verified`

#### 范围

- 基于 PF-P108-MG 后的最新 main，重新盘点 Turnover Ledger 剩余写路径和 server.py 中的 fallback/local transaction shim。
- 只做 discovery/planning 和文档回写。
- 不修改 production code，不修改 tests，不新增 SQL migration，不执行 Traffic Gate。

#### 必须扫描

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`

#### 必须输出

- 当前 Turnover Ledger 写路径矩阵：tag selection、bank row tags batch、relation extra、confirm、withdraw。
- `server.py` 中仍存在的 local transaction shim / fallback helper 清单。
- 哪些 fallback 是测试/本地兼容必须保留，哪些可作为下一切片 cleanup。
- 下一条 prompt 的精确建议，不得一次性推进多个写路径。

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `rg -n "PF-P109|Remaining Write Path Rebaseline|Fallback Cleanup Decision|local transaction shim|fallback cleanup" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 下一条 Prompt 上下文

PF-P109 盘点结论：

- 五条 Turnover Ledger 写路径均已存在 facade/UoW seam：tag selection、bank row tags batch、relation extra、confirm、withdraw。
- PostgreSQL path 已经朝 transaction-bound dirty/outbox 收敛：通过 `TurnoverLedgerDirtyOutboxWriter.enqueue_refresh(...)` 调用 `enqueue_read_model_refresh_in_transaction(...)`。
- `server.py` 仍保留 local/dev/test 兼容路径和 fallback 编排：
  - `_local_turnover_ledger_tag_selection_connection(...)`
  - `_local_turnover_ledger_bank_row_tags_connection(...)`
  - `_local_turnover_ledger_relation_extra_connection(...)`
  - `_local_turnover_ledger_confirm_connection(...)`
  - `_local_turnover_ledger_withdraw_connection(...)`
  - `_local_turnover_ledger_dirty_outbox_writer(...)`
  - `_persist_turnover_ledger_extras_best_effort(...)`
  - facade 为 `None` 时的 direct service/routes fallback 与 direct read-model clear/enqueue。
- 这些 fallback/shim 仍被现有 local-state API tests 使用，不能直接删除；下一步必须先用 characterization tests 锁定当前兼容语义和可清理边界。
- 下一条 prompt 应生成并审查 `PF-P110 - Turnover Ledger Fallback and Local Shim Characterization Tests`。PF-P110 只应新增/调整测试和文档，不修改 production code，不执行 fallback cleanup。

#### Verification Result

- `git status --short --branch`：Pass，仅包含 PF-P109 文档变更。
- `git ls-files --others --exclude-standard`：Pass，无 untracked 文件。
- `git diff --check`：Pass。
- `rg -n "PF-P109|Remaining Write Path Rebaseline|Fallback Cleanup Decision|local transaction shim|fallback cleanup" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`：Pass。

### PF-P110 - Turnover Ledger Fallback and Local Shim Characterization Tests

状态：`verified`

#### 范围

- 基于 PF-P109 的盘点结果，新增 Turnover Ledger fallback/local shim characterization tests。
- 只允许修改 `tests/test_turnover_ledger_api.py` 和相关文档。
- 不修改 production code，不清理 fallback，不抽离 local transaction shim，不新增 SQL migration。

#### 必须锁定

- facade 可用时，relation extra、confirm、withdraw、tag selection、bank row tags batch 不应触发 handler fallback 的 direct read-model clear/enqueue。
- facade 不可用时，local fallback 仍保持当前兼容返回、queue enqueue 和 local state store persistence 行为。
- `_persist_turnover_ledger_extras_best_effort` 的 dedicated state-store path 与 legacy full snapshot fallback 行为。
- local transaction shim 在 queue/outbox failure 时仍 rollback 对应 local snapshot。

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`

#### 下一条 Prompt 上下文

PF-P110 已补充 fallback/local shim characterization tests：

- 新增 confirm facade override 测试，断言 facade path 不触发 `_after_turnover_relation_mutation(...)`。
- 新增 withdraw facade override 测试，断言 facade path 不触发 `_after_turnover_relation_mutation(...)`，并保留 expected_versions 传递断言。
- 新增 relation extra dedicated persistence 测试，断言存在 `save_turnover_ledger_extras(...)` 时不调用 legacy full snapshot fallback。
- 既有 relation extra legacy full snapshot fallback 测试仍保留，用于下一切片安全改变行为。

Verification：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，53 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`：Pass。

下一条应执行 `PF-P111 - Turnover Ledger Relation Extra Legacy Full Snapshot Fallback Cleanup`。PF-P111 只处理 `_persist_turnover_ledger_extras_best_effort(...)` 的 legacy full snapshot fallback，不清理其它 fallback/local shim。

### PF-P111 - Turnover Ledger Relation Extra Legacy Full Snapshot Fallback Cleanup

状态：`verified`

#### 范围

- 移除或禁用 `_persist_turnover_ledger_extras_best_effort(...)` 中缺少 dedicated `save_turnover_ledger_extras(...)` 时调用 `legacy_bootstrap.load_full_snapshot(...)` 的 fallback。
- 更新对应 characterization test，使其断言不再读取 full snapshot，并通过 persistence warning/无保存行为保留 best-effort 语义。
- 不处理 confirm/withdraw/tag selection/bank row tags fallback，不抽离 local transaction shim。

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`

#### 下一条 Prompt 上下文

PF-P111 已移除 relation extra 缺少 dedicated persistence method 时的 legacy full snapshot fallback。`_persist_turnover_ledger_extras_best_effort(...)` 现在只调用 `save_turnover_ledger_extras(...)`；缺少该方法时只发出 best-effort warning，不再调用 `legacy_bootstrap.load_full_snapshot(...)`，也不再写 full snapshot。

Verification：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，53 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`：Pass。

下一条应执行 `PF-P111-MG - Turnover Ledger Fallback Cleanup Cumulative Merge Gate`，统一覆盖 PF-P109/PF-P110/PF-P111 的完整 diff。

### PF-P111-MG - Turnover Ledger Fallback Cleanup Cumulative Merge Gate

状态：`verified`

#### 范围

- 统一验证并合入 PF-P109、PF-P110、PF-P111 的完整 diff。
- 只覆盖 Turnover Ledger fallback/local shim rebaseline、characterization tests、relation extra legacy full snapshot fallback cleanup。
- 不执行 Traffic Gate，不部署，不访问生产。

#### 允许文件

- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_turnover_ledger_api.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `git diff --name-only main...HEAD`
- `git log --oneline main..HEAD`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`

#### 下一条 Prompt 上下文

PF-P111-MG 已 verified：

- Branch scope：
  - `git status --short --branch`：Pass。
  - `git ls-files --others --exclude-standard`：Pass，无 untracked 文件。
  - `git diff --check`：Pass。
  - `git diff --name-only main...HEAD`：只包含允许文件。
  - `git log --oneline main..HEAD`：只包含 PF-P109/PF-P110/PF-P111 相关提交。
- Branch verification：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，53 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
  - `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`：Pass。
- Merge：
  - 已将 `codex/turnover-ledger-next-slice-p109` 合入 `main`。
- Main verification：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，53 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
  - `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`：Pass。
- Traffic Gate：未执行；本切片不部署、不切流、不访问生产。

下一步：提交本次 post-flight 文档并 `git push origin main`。push 后从最新 `main` 新建下一条 `codex/` 分支，再生成下一条 prompt。

### PF-P112 - Turnover Ledger Local Shim Extraction Discovery and Planning

状态：`verified`

#### 范围

- 盘点 `server.py` 中 Turnover Ledger local transaction shim / local port / local repository helper 的抽离边界。
- 只做 discovery/planning 和文档回写。
- 不修改 production code，不修改 tests，不抽离 helper。

#### 必须扫描

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`

#### 必须输出

- Local shim inventory：每个 `_local_turnover_ledger_*` helper 的职责、输入依赖、输出副作用、测试覆盖。
- Extraction target recommendation：应新建/复用哪个 service/adapter 模块，哪些 helper 先抽，哪些暂留。
- Risk and blocker：是否存在必须先补 tests 的行为。
- 下一条 prompt 推荐：只能推荐一条，优先 tests 或最小 extraction。

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `rg -n "PF-P112|Local Shim Extraction|local shim inventory|Extraction target" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 执行结果

Local shim inventory：

| Helper | 职责 | 依赖 | 副作用 | 测试覆盖 | 抽离判断 |
| --- | --- | --- | --- | --- | --- |
| `_local_turnover_ledger_dirty_outbox_writer` | local queue refresh adapter | `queue_repository.enqueue_read_model_refresh` | enqueue refresh events | 多个 API queue assertions | 最优先抽离；无 Application 依赖。 |
| `_local_turnover_ledger_tag_selection_connection` | local settings rollback transaction | `state_store`、`_app_settings_service` | rollback/save app settings snapshot | tag selection queue failure tests | 可抽，但需先抽 settings snapshot port。 |
| `_local_turnover_ledger_bank_row_tags_connection` | local bank category + relation rollback transaction | category/relation services、state store | rollback/save category and relation snapshot | bank row tags rollback tests | 高风险；依赖多组 Application services，暂缓。 |
| `_local_turnover_ledger_relation_extra_connection` | local relation extra rollback transaction | routes extra snapshot、state store | rollback/save extras snapshot | relation extra rollback tests | 中等风险；可在 dirty outbox 后处理。 |
| `_local_turnover_ledger_confirm_connection` / `_withdraw_connection` | local relation rollback transaction | relation service、state store | rollback/save relation snapshot | confirm/withdraw rollback tests | 可抽为 relation snapshot local transaction adapter，但需连同 relation repository 处理。 |
| local relation/bankdetail/extra repository helpers | 将 local service/routes 包装成 UoW ports | routes/services/bank rows provider | 触发 local mutation/rebuild | UoW/API tests | 应迁入 adapter module，不能保留闭包捕获 Application。 |

Extraction target：

- 先在 `turnover_ledger_write_adapters.py` 中新增 `TurnoverLedgerLocalDirtyOutboxWriter`，替代 `server.py` 的静态 helper。
- 后续再按风险拆 `relation_extra` local transaction + repository、`relation` local transaction + repository、`bankdetail` local transaction + port、`tag_selection` settings transaction。
- 抽离原则：adapter 构造函数接收明确依赖，不接收 `Application`。

Verification：

- `git status --short --branch`：Pass，仅包含 PF-P112 文档变更。
- `git ls-files --others --exclude-standard`：Pass。
- `git diff --check`：Pass。
- `rg -n "PF-P112|Local Shim Extraction|local shim inventory|Extraction target" docs/architecture/backend-refactor/migration-state-log.md docs/architecture/backend-refactor/refactor-prompts.md docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`：Pass。

### PF-P113 - Turnover Ledger Local Dirty Outbox Writer Extraction

状态：`verified`

#### 范围

- 将 `server.py` 中 `_local_turnover_ledger_dirty_outbox_writer(...)` 抽为 `turnover_ledger_write_adapters.py` 中的显式 local adapter。
- 保持现有 queue reason mapping 和返回 events 行为不变。
- 不处理其它 local transaction shim。

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`

#### 执行结果

- 新增 `TurnoverLedgerLocalDirtyOutboxWriter` adapter。
- `server.py` 的 5 个 local path 改为使用该 adapter。
- 删除旧 `_local_turnover_ledger_dirty_outbox_writer(...)` static helper。

Verification：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，53 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。

### PF-P114 - Turnover Ledger Relation Extra Local Adapter Extraction

状态：`verified`

#### 范围

- 抽离 relation extra local transaction / repository adapter，减少 `server.py` 中 relation extra local shim 细节。
- 保持现有 local rollback、dedicated persistence、queue failure 行为不变。
- 不处理 confirm/withdraw/bank row tags/tag selection local shim。

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`

#### 执行结果

- 新增 `TurnoverLedgerLocalRelationExtraConnection`。
- 新增 `TurnoverLedgerLocalExtraRepository`。
- `server.py` relation extra local path 改为组装 adapter，不再内联 relation extra local transaction/repository helper。
- 删除 `_local_turnover_ledger_relation_extra_connection(...)`、`_local_turnover_ledger_extra_repository(...)`、`_save_local_turnover_ledger_relation_extra(...)`。

Verification：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，53 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。

### PF-P114-MG - Turnover Ledger Local Adapter Extraction Cumulative Merge Gate

状态：`verified`

#### 范围

- 统一验证并合入 PF-P112、PF-P113、PF-P114 的完整 diff。
- 覆盖 Turnover Ledger local shim extraction discovery、local dirty outbox adapter、relation extra local adapter。
- 不执行 Traffic Gate，不部署，不访问生产。

#### 允许文件

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/turnover-ledger-write-uow-plan.md`

#### 验证

- `git status --short --branch`
- `git ls-files --others --exclude-standard`
- `git diff --check`
- `git diff --name-only main...HEAD`
- `git log --oneline main..HEAD`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`
- `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`

#### 执行结果

- Branch scope：
  - `git status --short --branch`：Pass。
  - `git ls-files --others --exclude-standard`：Pass。
  - `git diff --check`：Pass。
  - `git diff --name-only main...HEAD`：只包含允许文件。
  - `git log --oneline main..HEAD`：只包含 PF-P112/PF-P113/PF-P114 相关提交。
- Branch verification：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，53 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
  - `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。
- Merge：
  - 已将 `codex/turnover-ledger-next-slice-p112` 合入 `main`。
- Main verification：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v`：Pass，53 tests。
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v`：Pass，56 tests。
  - `python3 -m compileall backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`：Pass。
- Traffic Gate：未执行；本切片不部署、不切流、不访问生产。

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

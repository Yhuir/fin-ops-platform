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
| 当前阶段 | `PF-P021-MG - Workbench Minimal Unit of Work Skeleton Merge Gate` 已执行但被阻断 |
| 当前 active prompt | `PF-P021-MG - Workbench Minimal Unit of Work Skeleton Merge Gate` (`blocked`) |
| 最近 verified prompt | `PF-P021 - Workbench Minimal Unit of Work Skeleton` |
| 当前分支 | `codex/workbench-uow-boundary-design` |
| 最近验证 | PF-P021-MG 发现默认测试入口 `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v` 会发现 `tests/test_workbench_uow_contract.py`；该文件当前 16 tests，7 failures，9 ok，会破坏默认 CI；绿色子集仍通过 |
| 下一条允许任务 | 生成并审查 UoW target contract tests 默认 CI 隔离/expected-failure 策略 prompt；在解决默认 CI 阻断前不得 merge，不得继续迁移 Workbench 写路径 |

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

状态：`blocked`

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

# 后端架构重构 Prompt 库

## 用途

本文档保存 Python-first 后端架构重构过程中经过审查的可执行 prompt。状态、完成度和下一步上下文维护在 `migration-state-log.md`。

## 使用规则

- 执行任何 prompt 前，必须先读取 `migration-state-log.md`。
- 任何执行型 prompt 前，必须先生成并审查 prompt 本身。
- prompt 必须包含 Pre-Flight、Allowed Scope、Forbidden Scope、Tests、Post-Flight。
- prompt 必须声明是否影响 Merge Gate 或 Traffic Gate。
- prompt 执行后必须更新 `migration-state-log.md`。
- 未经用户确认，不得把 prompt 标记为 `verified`。
- 不得记录 DB password、JWT secret、OA token、cookie 实值或生产 URL。

## PF-P000 - Fresh Documentation Baseline

状态：`implemented`

### 目标

建立 fresh 的 Python-first 后端架构重构文档体系，移除旧 Axum/PostgreSQL 和全量 Go replacement 方向，不修改业务代码。

### Prompt

```text
Role: 你是一位精通 Python 后端架构、Clean Architecture、Read Model/CQRS、Redis/RabbitMQ/PostgreSQL 边界和技术文档治理的架构负责人。

Context:
用户要求从 fresh 开始制定新的后端架构重构计划。新计划只做架构模块化重构，不把 Python 后端全量换成 Go。性能特别高的路径未来可以单独评估 Go Fiber accelerator，但不得默认创建 backend-go。

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
- 删除或改写 docs/architecture/backend-refactor/ 下旧 Axum/PostgreSQL/Go replacement 文档。
- 删除 docs/exec-plans/active/backend-axum-postgres-refactor.md。
- 新增 Python-first 架构重构文档。
- 更新 docs/index.md、docs/architecture/index.md、docs/exec-plans/active/README.md。

Forbidden Scope:
- 不修改 Python 业务代码。
- 不创建 backend-go。
- 不创建 Go/Rust 项目。
- 不修改 Nginx、Vite、部署配置或生产配置。
- 不执行 Traffic Gate。

Tests:
- git diff --check。
- 确认 backend-go 不存在。
- 确认 backend-refactor 目录只保留新方向文档。
- 搜索 Axum/Go/Rust/NATS/SQLx/Go replacement 等旧词，确保只出现在非目标或已移除语境。

Post-Flight:
- 更新 migration-state-log.md。
- 记录变更文件、架构决策、验证命令和结果。
- 状态只能到 implemented，等待用户确认后才能 verified。
```

### 验收标准

- `docs/architecture/backend-refactor/README.md` 是新计划入口。
- `target-architecture.md` 明确 Python-first，不创建 `backend-go`。
- `module-refactor-plan.md` 明确模块职责和推进顺序。
- `runtime-call-chain.md` 明确静态和动态调用链要求。
- `read-model-and-external-services.md` 明确外部服务模块化和 read model 契约。
- `migration-roadmap.md` 明确分阶段路线。
- `ai-execution-rules.md` 明确 AI 执行规则。
- `migration-state-log.md` 建立 fresh 状态机。
- 本文档建立 fresh prompt 库。
- 旧 Axum 执行计划已删除。

## PF-P001 - Architecture Inventory / Dynamic Call Chain Discovery

状态：`draft`

说明：PF-P001 尚未生成完整 prompt。PF-P000 经用户确认 `verified` 后，下一步应生成并审查 PF-P001。PF-P001 只允许做全局架构盘点、模块归属、静态调用链和动态时序整理，不得修改业务代码。

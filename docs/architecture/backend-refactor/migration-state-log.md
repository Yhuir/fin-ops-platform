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
- 不创建 `backend-go`。
- 不全量重写 Python 后端。
- 不在没有性能证据的情况下引入 Go Fiber。
- 不在 `main` 上直接做重构开发。
- 每个模块必须先梳理静态调用链和动态运行时序。
- 外部服务必须通过 port/adapter 或稳定服务边界访问。
- 写操作必须在同一 PostgreSQL transaction 中提交 facts、audit、dirty scope 和 outbox。
- Read Model 必须遵守 source version、building/active generation、幂等刷新、版本化缓存 key 和 consistency checker。
- 当前模块未完成测试和验收前，不进入下一个模块。
- Merge Gate 和 Traffic Gate 分离。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产敏感 URL。

## 当前状态

| 字段 | 当前值 |
| --- | --- |
| 当前阶段 | Fresh Python-first 后端架构重构文档建立中 |
| 当前 active prompt | `PF-P000 - Fresh Documentation Baseline` implemented |
| 最近 verified prompt | 无 |
| 当前分支 | `codex/python-first-refactor-reset` |
| 最近验证 | `git diff --check` 通过；未运行代码测试，因为本轮只改文档 |
| 下一条允许任务 | 用户审阅 PF-P000 文档；如确认，可标记 PF-P000 verified，然后生成并审查 `PF-P001 - Architecture Inventory / Dynamic Call Chain Discovery` |

## Prompt 执行日志

### PF-P000 - Fresh Documentation Baseline

状态：`implemented`

#### 范围

- 移除旧 Axum/PostgreSQL 后端替换计划。
- 不恢复旧 Go replacement 状态机。
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

- 当前方向是 Python-first 模块化重构，不做全量语言替换。
- 不创建 `backend-go`。
- Go Fiber 只作为未来热点路径 accelerator 选项，必须先通过 Hot Path Gate。
- Read Model、Redis、RabbitMQ、PostgreSQL、OA Mongo、MinIO/S3 都必须模块化。
- 每个模块必须先完成静态调用链和动态运行时序。
- 状态日志和 prompt 库分离：本文档记录状态，`refactor-prompts.md` 保存完整 prompt。

#### 验证

- `git diff --check`：通过。
- `test ! -e backend-go`：通过。
- `find docs/architecture/backend-refactor -maxdepth 1 -type f`：已确认只剩新方向文档。
- `rg "Axum|SQLx|NATS|JetStream|Rust|backend-go|全量 Python 到 Go|Python 到 Go|Go replacement"`：旧词只出现在“已移除/非目标/禁止项”语境，不是当前计划。
- 未运行 Python 测试：本轮只改文档。

#### 未完成事项 / 风险

- PF-P000 仍待用户审阅确认，不能标记为 `verified`。
- 尚未生成 PF-P001 的完整 prompt。
- 尚未对所有模块做 CodeGraph 调用链盘点。

#### 下一条 Prompt 上下文

PF-P000 建立了 fresh 的 Python-first 重构文档体系。下一步应先由用户确认 PF-P000 是否可标记 `verified`。确认后，生成并审查 `PF-P001 - Architecture Inventory / Dynamic Call Chain Discovery`，该 prompt 只做全局盘点和调用链整理，不改业务代码。

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

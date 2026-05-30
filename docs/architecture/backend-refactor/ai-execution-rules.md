# AI 执行规则

## 目的

本文件约束 Codex、Gemini 或其他 AI agent 执行后端架构重构时的行为。目标是避免旧语言替换方向复活，避免大范围无测试改动，避免在 `main` 上直接重构。

## 全局硬规则

- 当前计划是 Python-first 模块化重构。
- 不创建新语言后端。
- 不全量重写 Python 后端。
- 不引入任何其他语言的新后端。
- 不在 `main` 上直接做重构开发。
- 不跳过测试进入下一个模块。
- 不把 merge 到 `main` 等同于生产切流。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产 URL。

## Prompt 生成规则

任何执行型 prompt 前，必须先生成并审查 prompt 本身。

Prompt 必须一次只生成一个。不得一次性生成整条重构链路的所有 prompt。

原因：

- 下一条 prompt 的输入必须来自上一条 prompt 的真实输出。
- 模块边界、函数名、调用链、测试缺口和风险必须先被固化到文档或状态机，再生成下一步。
- 如果上一条 prompt 发现模块边界错误、测试失败或设计不成立，后续 prompt 必须重写，而不是继续执行旧计划。
- 状态机是生成下一条 prompt 的输入，不是执行结束后的可选总结。

生成 prompt 时必须读取：

- `docs/architecture/backend-refactor/migration-state-log.md`
- `docs/architecture/backend-refactor/refactor-prompts.md`
- `docs/architecture/backend-refactor/README.md`
- `docs/architecture/backend-refactor/target-architecture.md`
- `docs/architecture/backend-refactor/module-refactor-plan.md`
- `docs/architecture/backend-refactor/runtime-call-chain.md`
- `docs/architecture/backend-refactor/read-model-and-external-services.md`
- `docs/architecture/backend-refactor/migration-roadmap.md`
- 本模块相关产品规格和测试。

prompt 必须写明：

- Pre-Flight。
- Allowed Scope。
- Forbidden Scope。
- Tests。
- Post-Flight。
- 是否涉及 Merge Gate。
- 是否涉及 Traffic Gate。

### Post-Flight 回写硬规则

每次 prompt 执行完，必须在进入下一条 prompt 前完成精准回写。回写不是可选总结，而是下一条 prompt 的输入事实源。

必须更新：

- `migration-state-log.md`：prompt 状态、变更文件、验证命令和结果、风险、阻断、下一步上下文。
- `refactor-prompts.md`：当前 prompt 状态，以及后续生成的新 prompt。
- 本次执行结果影响到的架构文档：例如 inventory、runtime call chain、module plan、read model/external service contract、module-specific docs。

不得机械修改无关文档。只更新被本次真实发现影响的事实、规则和下一步输入。

如果 prompt 执行后没有完成回写，下一条 prompt 不得生成或执行。

生成下一条 prompt 的前置条件：

- 上一条 prompt 已经处于 `verified`；或用户明确允许在 `implemented/blocked` 状态下生成旁路 prompt。
- `migration-state-log.md` 已记录上一条 prompt 的变更文件、验证结果、风险和下一步上下文。
- 如果上一条 prompt 产出模块发现、调用链或测试缺口，下一条 prompt 必须显式读取这些产物。
- 每次 prompt 完成后，最终回复必须告诉用户下一步建议做什么。

## Macro-Inventory 与 Micro-JIT-Planning

所有后续 prompt 必须遵守两阶段规划模型。

### Macro-Inventory prompt

Macro-Inventory 是全局只读盘点 prompt。它必须：

- 扫描全量 app routes、server handler、services、repositories、workers、read models、tests 和文件体量。
- 生成 `docs/architecture/backend-refactor/architecture-inventory.md`。
- 给每个 API path、Python 文件、repository/read model/worker/test 归属到目标候选模块或 platform。
- 输出未归属文件、重复归属文件、跨模块直接调用和 legacy fallback 清单。
- 明确 Workbench Matching Engine 是独立模块候选还是 Workbench 内部子域，并列出证据。
- 只产出事实和风险，不修改业务代码。

Macro-Inventory prompt 不得：

- 一次性写所有模块的最终重构代码。
- 一次性写所有模块的最终详细设计。
- 开始任何单模块业务重构。
- 创建新语言后端或部署切流方案。

### Micro-JIT-Planning prompt

Micro-JIT prompt 是单模块深挖和执行 prompt。它必须：

- 只处理一个业务模块或一个明确 platform 边界。
- 读取 `architecture-inventory.md` 中该模块的归属和风险。
- 生成该模块的函数级调用链、动态运行时序、契约测试计划和最小重构计划。
- 先补测试，再重构。
- 完成后更新状态机，作为下一条 prompt 的输入。

Micro-JIT prompt 不得：

- 同时深挖多个业务模块。
- 基于尚未验证的候选模块边界直接改代码。
- 跳过上一条 prompt 的验证结果生成下一条执行 prompt。

## 分支规则

- 新工作使用 `codex/` 前缀分支。
- 每个模块单独分支。
- 不在 `main` 上直接修改业务代码。
- 不把多个业务模块堆在一个分支。
- 不使用 `git reset --hard`、`git clean`、`git checkout --` 清理用户改动，除非用户明确要求。

## 模块执行规则

每个模块的执行 prompt 必须包含：

1. 读取模块产品规格和当前测试。
2. 使用 CodeGraph 生成静态调用链。
3. 整理动态运行时序。
4. 先写或补齐 contract/unit tests。
5. 再做最小重构。
6. 运行模块测试和相关回归。
7. 更新模块调用链文档。
8. 未通过测试不得标记完成。

全局盘点类 prompt 还必须包含：

- 扫描全量 API path、route handler、service、repository、worker、read model 和 tests。
- 输出未归属 API/path/service 清单。
- 对超过 20KB 的 service 文件进行显式归属和风险说明。
- 明确 Turnover Ledger、Batch Accounting、Workbench 这些高风险模块是否存在遗漏或错归属。
- 所有模块结论必须能回链到代码文件、测试或文档事实。

## 状态记录

使用新的 `migration-state-log.md` 维护 AI 状态机。该文件只记录当前状态、prompt 完成度、验证摘要、风险和下一步上下文，不恢复旧 P000/P002/P003 记录。

使用新的 `refactor-prompts.md` 保存每条经过审查的可执行 prompt。状态日志不粘贴完整 prompt，只引用 prompt id。

每个模块完成后必须记录：

- 分支名。
- prompt id 和状态。
- 模块范围。
- 改动文件。
- 测试命令和结果。
- 未覆盖风险。
- 是否需要 Traffic Gate。
- 下一步任务。

状态允许值：

- `planned`：prompt 已生成并审查，未执行。
- `in_progress`：正在执行。
- `implemented`：改动完成但尚未验收。
- `verified`：测试通过且用户确认。
- `blocked`：存在阻断，无法继续。
- `rolled_back`：已回滚。

没有显式测试结果和用户确认，不得标记 `verified`。

## 测试门禁

最低测试要求：

- Python unit tests。
- 模块 contract tests。
- 相关 integration tests。
- 对 read model 或 SQL 热路径，必须补 SQL/read model 测试。
- 对 Redis/RabbitMQ，单元测试使用 fake，集成测试显式依赖环境变量。
- 对性能优化，必须记录基线和优化后指标。

## Merge Gate 与 Traffic Gate

Merge Gate 是代码或文档能否进入 `main` 的前后验证流程，不等于上线。

Merge Gate 至少包含：

- 当前分支验证。
- merge 或 PR 合并到 `main`。
- 在 `main` 上重新运行同一套关键验证。
- 失败时停止下一步，修复或回滚。

Traffic Gate 是生产流量是否可以进入新路径的门禁。普通 Python-only 模块化重构通常不需要 Traffic Gate。

以下情况才需要 Traffic Gate：

- 修改 Nginx、Vite、Caddy 或其他 gateway path routing。
- 修改 auth/session 入口。
- 修改 SSE 代理或长连接行为。
- 修改生产 worker 消费方式、队列后端或部署拓扑。

没有 staging 环境时：

- Python-only 模块重构可以继续，但必须加强本地测试、contract tests、integration tests 和 main 上复验。
- 高风险 Traffic Gate 默认不得执行。
- 如果用户明确要求无 staging 生产 canary，prompt 必须写明风险、最小切流范围、回滚命令、观测指标和人工确认点。

## 性能优化边界

本轮计划只做 Python 系统内架构重构和性能优化。任何 prompt 都不得创建其他语言的新后端，也不得创建 `backend-go`。

允许的性能优化方向：

- SQL、索引和 `EXPLAIN ANALYZE`。
- Read Model 粒度、generation 发布和 freshness。
- Python service/usecase 算法复杂度。
- Redis 短 TTL cache、版本化 key 和 wakeup。
- RabbitMQ/outbox/worker lag。
- 批处理、后台预热和并发控制。

如果这些优化仍不足，必须先回到架构评审，重新检查数据模型、业务口径和调用链，不得直接生成新语言后端方案。

## 文档维护

每次模块重构后必须更新相关文档：

- 模块计划。
- 调用链。
- Read Model/外部服务契约。
- 产品规格或开发文档。

不要把历史 prompt、大段日志或临时代码粘贴进长期文档。

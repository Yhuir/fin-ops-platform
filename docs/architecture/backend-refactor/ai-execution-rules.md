# AI 执行规则

## 目的

本文件约束 Codex、Gemini 或其他 AI agent 执行后端架构重构时的行为。目标是避免旧 Go replacement 方向复活，避免大范围无测试改动，避免在 `main` 上直接重构。

## 全局硬规则

- 当前计划是 Python-first 模块化重构。
- 不创建 `backend-go`。
- 不全量重写 Python 后端。
- 不在没有性能证据的情况下引入 Go Fiber。
- 不在 `main` 上直接做重构开发。
- 不跳过测试进入下一个模块。
- 不把 merge 到 `main` 等同于生产切流。
- 不记录 DB password、JWT secret、OA token、cookie 实值或生产 URL。

## Prompt 生成规则

任何执行型 prompt 前，必须先生成并审查 prompt 本身。

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

## Go Fiber Hot Path Gate

只有用户明确要求生成 Go accelerator prompt，且以下条件满足，才允许进入：

- Python 模块已完成边界重构和测试。
- 性能瓶颈有数据证据。
- SQL/read model/cache/worker 优化已评估。
- API contract 已锁定。
- auth/session/trace id 兼容规则已锁定。
- gateway 回滚方案已锁定。

否则，AI 必须继续在 Python 架构内优化。

## 文档维护

每次模块重构后必须更新相关文档：

- 模块计划。
- 调用链。
- Read Model/外部服务契约。
- 产品规格或开发文档。

不要把历史 prompt、大段日志或临时代码粘贴进长期文档。

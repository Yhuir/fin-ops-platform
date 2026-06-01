# 后端架构重构文档入口

本目录是新的后端架构重构事实源。旧的 Axum、全量语言替换计划已经移除，不再作为当前方向。

## 当前目标

当前重构目标是 **Python-first 架构模块化重构**：

- 保留现有 Python 后端作为默认业务运行时。
- 优先重构模块边界、依赖方向、外部服务封装、测试和运行时调用链。
- 不建立新语言后端，不做全量 Python 语言替换。
- 本轮重构不涉及引入任何其他语言的新后端。
- 性能优化只在现有 Python、PostgreSQL、Read Model、Redis、RabbitMQ 和 worker 边界内推进。

## 阅读顺序

1. `target-architecture.md`：新的 Python-first 目标架构、边界和技术取舍。
2. `module-refactor-plan.md`：模块拆分、职责、验收顺序和测试门禁。
3. `architecture-inventory.md`：PF-P001 产出的全局文件级分拣、API ownership、外部依赖和高风险文件清单。
4. `platform-runtime-boundary-audit.md`：PF-P002 产出的 Platform / Ops / Runtime 边界审计和后续底座约束。
5. `runtime-call-chain.md`：静态调用链、动态运行时序和优化方法。
6. `read-model-and-external-services.md`：Read Model、Redis、RabbitMQ、PostgreSQL、OA Mongo、对象存储等外部服务契约。
7. `turnover-ledger-discovery.md`：PF-P046 产出的 Turnover Ledger 专项 discovery、调用链、风险和下一步测试计划。
8. `migration-roadmap.md`：按阶段推进的重构路线、merge 策略和回滚口径。
9. `ai-execution-rules.md`：Codex/Gemini 执行 prompt 时必须遵守的状态记录、测试和分支规则。
10. `migration-state-log.md`：AI 状态机，记录每次 prompt 的完成度、验证和下一步上下文。
11. `refactor-prompts.md`：可执行 prompt 库，保存后续每条经过审查的 prompt。

## 不再采用的旧方向

以下内容不是当前计划：

- Axum + Rust 后端替换。
- 全量 Python 到其他语言的重写。
- 新老两套业务系统长期并行。
- 一次性大分支重构后整体 merge。
- 为业务模块创建其他语言的新后端。

## 当前系统事实

- 后端：Python，入口在 `backend/src/fin_ops_platform/app/`。
- 业务服务：`backend/src/fin_ops_platform/services/`。
- 当前模块边界必须至少覆盖 Workbench、Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Imports、Tax/Cost/ETC、Search、Ops/Runtime。
- 持久化：PostgreSQL 为生产主读写；OA Mongo 只作为 worker/audit/tooling 的只读源。
- Read Model：工作台、搜索、待找发票、税金、成本、银行明细等页面正在向 SQL read model 收敛。
- 外部服务：Redis 用于短 TTL cache、wakeup 和辅助锁；RabbitMQ 是 outbox envelope transport；PostgreSQL outbox 和 durable queue 是事实源。
- Worker：Python worker 继续处理 OA sync、read model refresh、导入解析、文件迁移和后台任务。

## 重构原则

- 模块按业务边界拆分，不按 `controllers/services/models` 技术层堆叠。
- HTTP 层只做请求解析、鉴权上下文、响应映射和错误码；业务规则进入 usecase/service。
- 每个模块必须有独立测试；当前模块完整通过后，才进入下一个模块。
- 外部服务必须通过 port/adapter 或稳定服务边界访问，业务逻辑不得散落调用 Redis、RabbitMQ、数据库 driver 或 OA adapter。
- 写操作必须在同一 PostgreSQL transaction 中提交 facts、audit、dirty scope 和 outbox。
- Read Model 使用 source version、building/active generation、幂等刷新、版本化缓存 key 和 consistency checker。
- 所有模块重构必须先梳理静态调用链和动态运行时序，再决定是否优化。

## 规划方式

- 先做 Macro-Inventory：全局只读文件级分拣，生成 `architecture-inventory.md`，确认 API path ownership、file ownership、外部依赖和高风险调用链。
- 再做 Micro-JIT-Planning：每次只深挖一个模块，基于 `architecture-inventory.md` 生成该模块的详细计划、测试和最小重构。
- 不一次性生成所有模块的详细设计或执行 prompt。

## 分支和合并规则

- 不在 `main` 上直接进行重构开发。
- 每个模块使用独立 `codex/` 分支。
- 每个模块 merge 前必须通过模块测试和相关回归。
- merge 到 `main` 后必须在 `main` 再运行同一套验证。
- merge 不等于生产切流；Python-only 模块重构默认不需要 Traffic Gate。只有修改网关、auth/session、SSE、worker 消费方式或部署拓扑时，才单独评估 Traffic Gate。

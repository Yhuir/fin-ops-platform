# 后端架构重构路线图

## 总体策略

重构采用小步、可验证、可回滚的方式推进：

- 不在 `main` 上直接开发。
- 不一次性重写后端。
- 不引入任何其他语言的新后端。
- 不一次性生成所有 prompt；每次只生成一个，执行、验证、更新状态机后，再生成下一条。
- 每个模块先完成 discovery、调用链、契约测试，再重构。
- 每个模块 merge 到 `main` 后必须在 `main` 重跑验证。
- 生产流量不因 merge 自动变化。

## 两阶段规划模型

后端重构规划分为两个层级，不得混用。

### Macro-Inventory：全局文件级分拣

这是进入任何模块重构前必须完成的只读阶段。

目标：

- 扫描 `backend/src/fin_ops_platform/app/`、`backend/src/fin_ops_platform/services/`、repository、worker、read model 和 tests。
- 输出 API path ownership、file ownership、external dependency matrix、read model ownership 和高风险调用链。
- 把所有现有文件归属到目标候选模块或 platform，不能留下孤儿文件。
- 明确 Workbench Matching Engine 是独立顶层模块候选，还是 Workbench 内部子域。
- 识别跨模块直接调用、legacy full snapshot、local state/pickle、同步全量刷新和外部服务散落调用。

交付：

- `docs/architecture/backend-refactor/architecture-inventory.md`。
- 反向修订 `module-refactor-plan.md`、`runtime-call-chain.md` 和 `migration-state-log.md`。

禁止：

- 不修改业务代码。
- 不一次性写出所有模块的最终详细重构设计。
- 不开始单模块代码重构。

### Micro-JIT-Planning：单模块准时制深挖

Macro-Inventory verified 后，每次只选择一个模块做微观计划和重构。

每个模块必须按以下顺序推进：

1. 读取 `architecture-inventory.md` 中该模块的文件归属、API path、依赖和风险。
2. 生成该模块的函数级静态调用链和动态运行时序。
3. 锁定 API contract、事务边界、read model ownership、outbox/dirty scope 和外部依赖。
4. 先补 contract/unit/integration tests。
5. 做最小边界重构。
6. 通过模块验证和 Merge Gate。
7. 更新状态机，再生成下一个模块 prompt。

禁止：

- 不基于上一个模块的实际结果提前生成多个模块的执行 prompt。
- 不在一个 prompt 中同时深挖多个业务模块。
- 不把 Macro-Inventory 的候选模块列表直接视为最终目录结构或代码设计。

## 阶段 0：Fresh 文档锁定

目标：

- 移除旧 Axum/语言替换文档。
- 建立 Python-first 目标架构。
- 明确模块划分、外部服务契约、动态调用链和 AI 执行规则。

验收：

- `docs/architecture/backend-refactor/` 下不存在旧方向活跃文档。
- 文档明确不建立 `backend-go`。
- 文档明确本轮只做 Python 架构模块化重构。
- 文档索引不再指向 Axum/PostgreSQL 计划。

## 阶段 1：全局架构盘点

目标：

- 用 CodeGraph 和代码阅读整理当前 API path、handler、service、repository、worker、read model。
- 建立 API path ownership 和 file ownership。
- 找出跨模块直接调用、外部服务散落调用、同步全量构建和 snapshot fallback。
- 明确目标候选模块，并标注哪些模块仍需 Micro-JIT-Planning 后才能最终锁定。

交付：

- `architecture-inventory.md`。
- 每个模块的 API ownership。
- 每个现有文件的目标归属。
- 外部服务 dependency matrix。
- 高风险调用链清单。

验收：

- 不改业务代码。
- 只产出架构事实和问题清单。
- 所有结论能回链到代码文件、测试或产品规格。

## 阶段 2：Platform 边界收敛

目标：

- 在 Python 中固化 shared platform boundary。
- 收敛 auth、db transaction、queue、cache、storage、observability。
- 建立测试 fake/mock。

验收：

- 外部服务调用点可被测试替换。
- 新模块不得直接 import Redis/RabbitMQ/driver/OA raw adapter。
- Python unit tests 覆盖平台边界。

## 阶段 3：Read Model 和异步刷新基线

目标：

- 固化 read model freshness contract。
- 梳理 dirty scope、source version、outbox、RabbitMQ、worker refresh。
- 补齐 consistency checker 和 App Health 暴露。

验收：

- 写操作同事务提交 facts、audit、dirty scope、outbox。
- Worker 幂等刷新。
- API 明确返回 fresh/refreshing/stale/failed/unavailable。
- Redis key 包含 generation/source version。

## 阶段 4：模块逐个重构

建议顺序：

1. Workbench 只读 summary/groups。
2. Workbench detail/group rows。
3. Workbench Matching Engine，若 PF-P001 证明它可以作为独立边界，否则作为 Workbench 内部子域推进。
4. Workbench writes：pair relation、exception、reconciliation。
5. Turnover Ledger。
6. Batch Accounting。
7. Bankdetail。
8. Pending invoices / invoice usage / output collections。
9. Imports。
10. Tax / Cost / ETC。
11. Search / Pending Query，若 PF-P001 证明它应独立。
12. Ops/runtime。

排序理由：

- Workbench 是核心高频路径，最依赖 read model freshness。
- Matching Engine 体量大且性能敏感，但是否独立必须由 PF-P001 的调用链、输入输出和 read model ownership 证明。
- Turnover Ledger 和 Batch Accounting 都有独立 API、service、测试和 relation/event 链路，不能归入 Workbench 或 Bankdetail。
- Turnover Ledger 与 Batch Accounting 都会影响 Workbench 投影，所以应在 Workbench 基线稳定后尽早处理。
- Bankdetail 和 invoices 是 Workbench 的重要事实输入。
- Imports 和 worker 影响多个下游模块。
- Tax/Cost/ETC 聚合重、适合在 read model 基线稳定后推进。

## 阶段 5：Python 内性能优化

只有模块完成 Python-first 重构后，才做性能优化闭环。本阶段不引入新语言后端。

性能优化输入：

- P95/P99 延迟。
- SQL `EXPLAIN ANALYZE`。
- CPU profile。
- memory profile。
- worker lag。
- outbox backlog。
- Redis hit/miss。
- read model generation 发布耗时。

允许优化范围：

- SQL/index/read model。
- Python 算法复杂度、批处理和并发控制。
- Worker 异步刷新和预热。
- Redis 短 TTL、版本化 cache 和 wakeup。
- RabbitMQ/outbox/backlog 处理。
- App Health、consistency checker 和告警。

没有指标证据，不做大范围性能改造。

## Merge Gate

每个模块 merge 前：

- 当前模块 unit tests 通过。
- 相关 contract tests 通过。
- 相关 integration tests 通过或明确记录跳过条件。
- Python 全仓相关回归通过。
- 文档和调用链记录已更新。

merge 到 `main` 后：

- 重新运行同一套验证。
- 如果失败，修复或回滚该 merge。
- 不开始下一个模块，直到 `main` 验证通过。

Merge Gate 是 merge 到 `main` 前后的完整验证流程，不是单纯的 `git merge` 命令，也不代表生产流量已经切换。

## Traffic Gate

普通 Python 模块重构通常不需要 Traffic Gate。

以下情况必须单独 Traffic Gate：

- 修改 Nginx/Vite/Caddy path routing。
- 修改 SSE 代理行为。
- 改变 auth/session 边界。
- 改变生产 worker 消费方式。

Traffic Gate 必须包含：

- staging 或等价环境验证。
- header/cookie/trace id 透传。
- 回滚演练。
- SSE 实时性验证。
- App Health 和监控观察。

当前没有 staging 环境时：

- Python-only 模块化重构可以继续。
- 必须加强本地验证、contract tests、integration tests、main 上复验和生产发布前备份。
- 不得默认执行网关切流、auth/session、SSE 或 worker 消费方式变更的 Traffic Gate。
- 如果用户明确批准生产 canary，必须把切流范围限制到最小 path，写明回滚步骤和观察指标，并在执行前再次确认。

## 回滚口径

- 文档和测试变更：通过普通 git revert 回滚。
- Python 模块重构：回滚对应 merge commit。
- Read model 问题：继续读取旧 active generation，修复 worker 后重建。
- RabbitMQ 问题：回退 PostgreSQL polling/outbox。
- Redis 问题：清空或关闭 Redis，不影响 PostgreSQL read model 正确性。
- 网关或部署拓扑问题：回滚配置并恢复原 Python 路径。

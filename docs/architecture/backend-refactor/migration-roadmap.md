# 后端架构重构路线图

## 总体策略

重构采用小步、可验证、可回滚的方式推进：

- 不在 `main` 上直接开发。
- 不一次性重写后端。
- 不默认引入 Go。
- 每个模块先完成 discovery、调用链、契约测试，再重构。
- 每个模块 merge 到 `main` 后必须在 `main` 重跑验证。
- 生产流量不因 merge 自动变化。

## 阶段 0：Fresh 文档锁定

目标：

- 移除旧 Axum/Go replacement 文档。
- 建立 Python-first 目标架构。
- 明确模块划分、外部服务契约、动态调用链和 AI 执行规则。

验收：

- `docs/architecture/backend-refactor/` 下不存在旧方向活跃文档。
- 文档明确不建立 `backend-go`。
- 文档明确 Go Fiber 只作为未来热点加速器选项。
- 文档索引不再指向 Axum/PostgreSQL 计划。

## 阶段 1：全局架构盘点

目标：

- 用 CodeGraph 和代码阅读整理当前 API path、handler、service、repository、worker、read model。
- 建立模块归属表。
- 找出跨模块直接调用、外部服务散落调用、同步全量构建和 snapshot fallback。

交付：

- `architecture-inventory.md`。
- 每个模块的 API ownership。
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
3. Workbench writes：pair relation、exception、reconciliation。
4. Bankdetail。
5. Pending invoices / invoice usage / output collections。
6. Imports。
7. Tax / Cost / ETC。
8. Search。
9. Ops/runtime。

排序理由：

- Workbench 是核心高频路径，最依赖 read model freshness。
- Bankdetail 和 invoices 是 Workbench 的重要事实输入。
- Imports 和 worker 影响多个下游模块。
- Tax/Cost/ETC 聚合重、适合在 read model 基线稳定后推进。

## 阶段 5：性能优化和 Hot Path Gate

只有模块完成 Python-first 重构后，才评估是否需要 Go Fiber accelerator。

Hot Path Gate 输入：

- P95/P99 延迟。
- SQL `EXPLAIN ANALYZE`。
- CPU profile。
- memory profile。
- worker lag。
- outbox backlog。
- Redis hit/miss。
- read model generation 发布耗时。

Go Fiber accelerator 允许范围：

- 单个明确 API path 或内部计算服务。
- 保持同一 PostgreSQL facts/read model/outbox 契约。
- 保持同一 auth/session/trace id。
- 可 shadow、可灰度、可回切 Python。

没有这些证据，不进入 Go。

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

## Traffic Gate

普通 Python 模块重构通常不需要 Traffic Gate。

以下情况必须单独 Traffic Gate：

- 引入 Go Fiber accelerator。
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

## 回滚口径

- 文档和测试变更：通过普通 git revert 回滚。
- Python 模块重构：回滚对应 merge commit。
- Read model 问题：继续读取旧 active generation，修复 worker 后重建。
- RabbitMQ 问题：回退 PostgreSQL polling/outbox。
- Redis 问题：清空或关闭 Redis，不影响 PostgreSQL read model 正确性。
- Go accelerator 问题：网关 path 回切 Python。

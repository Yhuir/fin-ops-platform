# Canonical Facts Boundaries

日期：2026-06-26

本目录保存本轮 GSD 对业务唯一真相边界的过程性分析和后续执行计划。它不是长期事实源；稳定结论必须同步到 `docs/architecture/module-boundaries/canonical-facts.md` 和对应 `docs/modules/<module>/boundary-io.md`。

## 目标

- 明确 PostgreSQL canonical facts 的模块 owner。
- 区分业务唯一真相、read model 投影、runtime 状态和外部系统事实。
- 为后续小步模块化重构提供 owner、I/O、禁止路径和验收标准。

## 产物

- `ANALYSIS.md`：当前代码和文档中的 canonical facts 全量分析。
- `PLAN.md`：后续模块化重构顺序、验收标准和风险。

## 结论摘要

- 业务唯一真相需要纳入模块化管理。
- 不新增一个集中式 `UnifiedFactSource` 运行时模块。
- 采用 ownership matrix：每类 canonical fact 归属现有业务模块，非 owner 只能通过公开 command/read port、service 或明确 adapter 访问。
- `read-models` 继续管理派生投影、freshness、refresh 和 operation barrier，不拥有源业务事实。

# Remove Read Models Refactor

日期：2026-06-26
状态：analysis / planning only

本目录保存“全量移除 app 页面 read model，页面改为 direct API 读取和组装数据”的 GSD 分析与实施计划。它不是当前生产事实源；稳定架构结论同步到 `docs/architecture/direct-api-read-architecture.md` 和相关长期文档。

## 目标

- 所有业务页面读取改为 route -> service -> repository -> PostgreSQL canonical facts / OA projection / import facts 的 direct API 路径。
- 不再新增、扩展或优化页面级 read model、freshness gate、read model dirty scope、read model refresh worker 或 operation freshness barrier。
- 保留真正需要异步的后台能力，例如导入处理、OA 同步、文件迁移和受控修复工具；这些 worker 不再承担页面 read model refresh。
- 用数据库索引、分页、聚合 SQL、明确 service 边界和针对性测试取代物化读模型架构。

## 产物

- `ANALYSIS.md`：当前 read model 架构影响面、direct API 目标态、风险和需要改的地方。
- `PLAN.md`：分阶段实施顺序、验收标准、测试矩阵和删除条件。
- `GOAL_PROMPT.md`：可直接投喂 Codex `/goal` 的 GSD 主控 prompt；一次生成一个 bounded execution prompt，执行后按完成状态派生下一步。
- `EXECUTION_STATE.md`：主控执行状态、已完成 bounded prompt、验证结果、开放风险和下一条 prompt。

## 关键结论

- 这不是“换一套新的 read layer 框架”。按 ponytail 原则，目标是删除 read model 架构，直接复用现有 route/service/repository/SQL 能力。
- 当前代码仍有大量 read model 依赖；在代码迁移完成前，旧 read model 文档只能作为迁移清单和删除条件，不再作为新设计方向。
- `.planning/` 只保存过程计划；长期事实必须以 `docs/` 为准。

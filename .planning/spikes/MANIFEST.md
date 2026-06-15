# Spike Manifest

## Idea

对现有 `fin-ops-platform` 做只读架构审计，不修改业务代码。审计基于仓库入口文档、长期架构文档、运行治理文档和 `.planning/codebase/` 映射结果，重点判断当前边界是否合理、哪些边界违反目标架构、哪些问题可能导致真实 bug，并给出 P0/P1/P2 改进建议和分阶段重构路线图。

## Requirements

- 只读审计：不修改 `backend/`、`web/` 或长期业务文档。
- 所有风险必须给出证据文件路径和原因。
- 覆盖前后端、service、repository、read model、worker、queue、PostgreSQL、Redis、RabbitMQ、OA Mongo 边界。
- 输出可执行分阶段路线图，但本次不直接改代码。

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|---|---|---|---|---|
| 001 | architecture-audit | standard | Given current docs/codebase maps and source evidence, when auditing runtime/read-model/worker boundaries, then identify boundary correctness, violations, bug risks, and refactor phases without code changes. | PARTIAL | architecture, read-model, worker, queue, postgres, frontend, risk |

## Notes

- `.planning/codebase/` 是本次审计输入之一；本 manifest 不修改其内容。
- 本次 spike 未形成可复用实验约定，暂不新增 `CONVENTIONS.md`。

# 模块化 IO 边界重构工作区

**创建日期:** 2026-06-22
**状态:** Analysis only
**范围:** 全局模块化 IO 重构规划、状态跟踪、审计模板和后续执行提示词模板

## 定位

本目录用于规划一次横跨后端、前端、read model、worker、权限、审计、测试和文档治理的模块化 IO 边界重构。它不是当前生产事实源，也不替代 `AGENTS.md`、`ARCHITECTURE.md`、`docs/app-architecture/`、`docs/modules/`、`docs/dev/` 或 `docs/operations/`。

当前事实仍以代码和长期文档为准。本目录只保存本次重构的 GSD 分析、需求、状态机、路线图、审计清单和可复用 prompt 模板。

## 核心判断

这次重构不是把大文件机械拆小。目标是把业务能力拆成可验证的模块边界，并为每个模块建立明确 IO 合同：

- 输入: API request、command、query、导入数据、外部系统数据、read model 依赖、事件依赖。
- 输出: API response、canonical write facts、audit records、affected scopes/months、domain events、read model refresh requests、frontend domain events。
- 状态: 业务状态、UI 状态、read model freshness、worker 状态、非法状态。
- 事件: domain event、dirty scope、outbox event、frontend broadcast、operation barrier target。
- read model: key、scope、freshness proof、source/schema version、rebuild owner。
- 权限: action、actor、role、read-only/export/admin 差异、审计要求。
- 测试合同: 七类测试适用性、模块内测试、跨模块回归测试、验证命令。
- 模块边界: public API、禁止穿透调用、可接受依赖、禁止依赖。

## 文件地图

| 文件 | 用途 |
| --- | --- |
| `00-REQUIREMENTS.md` | 本次模块化 IO 重构的完整需求文档和验收标准。 |
| `01-CURRENT-STATE-AUDIT.md` | 当前代码边界体检、已完成部分、风险热点和缺口。 |
| `02-MODULE-IO-CONTRACT-TEMPLATE.md` | 每个模块必须补齐的 IO 合同模板。 |
| `03-REFACTOR-STATE-MACHINE.md` | 全局重构状态机、单模块状态机和阶段准入/退出规则。 |
| `04-IMPLEMENTATION-ROADMAP.md` | 不一次性全局重构的分阶段路线，先试点再扩展。 |
| `05-IMPACT-AND-TEST-GATES.md` | 每次改动必须执行的影响分析、七类测试映射和回归闸门。 |
| `06-PILOT-SELECTION.md` | 试点模块选择原则、候选模块和推荐试点顺序。 |
| `07-DOCS-GOVERNANCE.md` | 本目录与长期文档、模块文档、实现记录的同步规则。 |
| `08-AUTONOMOUS-RUNBOOK.md` | 无人值守自动推进循环：分析、实现、验证、审阅、状态更新和继续执行。 |
| `09-DEV-BRANCH-WORKFLOW.md` | 主 repo 直接切 `dev`、对齐 main、commit/push、禁止 main 实现提交的工作流。 |
| `10-AUTONOMOUS-STOP-GATES.md` | 自动运行的硬停止条件、软延迟条件和继续推进规则。 |
| `11-GO-HOT-PATH-CARVE-OUT.md` | Go / Go Fiber / Go Worker 热点模块 carve-out 候选、准入门槛和目标运行时。 |
| `analysis/codebase-scan-2026-06-22.md` | 2026-06-22 代码扫描原始摘要和风险登记。 |
| `analysis/boundary-risk-register.md` | 后续持续维护的边界风险登记表。 |
| `analysis/production-access-status-2026-06-22.md` | 当前 SSH 访问能力、生产验证可做/不可做事项和缺口。 |
| `autonomous/STATE.md` | 自动推进全局状态。 |
| `autonomous/MODULE-QUEUE.md` | 自动推进模块边界队列。 |
| `autonomous/JOURNAL.md` | 自动推进执行日志。 |
| `autonomous/NEXT-PROMPT.md` | 自动推进下一轮 prompt 入口。 |
| `prompts/README.md` | 后续 prompt 模板使用规则。 |
| `prompts/01-module-io-audit.md` | 单模块 IO 审计提示词模板。 |
| `prompts/02-refactor-phase-planning.md` | 单模块重构 phase 规划提示词模板。 |
| `prompts/03-autonomous-start.md` | 可直接喂给 Codex 的无人值守启动 prompt。 |

## 工作规则

1. 任何执行实现前，先更新或确认 `00-REQUIREMENTS.md`、`02-MODULE-IO-CONTRACT-TEMPLATE.md` 和目标模块 `docs/modules/<module>/`。
2. 每次重构必须选择一个明确模块或一个明确共享边界，不能以“全局清理”为单位开工。
3. 每次改动前必须填写影响分析: API、service、repository、read model、worker、frontend、permission、audit、tests、docs。
4. 每个模块完成前必须有 IO 合同和测试合同；没有合同的拆文件不算完成。
5. 共享事实源、read model refresh、operation barrier、App Status、domain events 必须走统一边界，不允许模块自行绕路。
6. 试点通过前，不启动全量模块迁移。
7. 本目录可以保存 prompt 模板，但不保存未经提炼的原始对话。执行结论要沉淀为需求、决策、验收或风险。
8. 不把 SSH 密码、数据库密码、token 或任何 secret 写入本目录、脚本、测试 fixture、commit message 或长期文档；生产验证必须通过受控 runbook 和临时交互登录完成。
9. 当前没有本地 `PGSQL_URL` 和 staging 数据库时，计划必须区分可本地验证、可用 fake/repository stub 验证、必须生产只读验证、必须生产受控写入验证四类。
10. 自动推进不依赖 staging 数据库或本地 `PGSQL_URL`；缺少真实生产 DB/worker 证据时记录 `production-evidence-deferred` 并继续下一个安全模块。
11. 自动推进必须在主 repo `/Users/yu/Desktop/fin-ops-platform` 中直接使用 `dev` 分支；启动前要求工作区干净且 `main` 已 push，然后把 `origin/main` merge 到 `dev`，禁止实现提交 push 到 `main`。
12. 模块迁移不能只新增新链路；必须删除旧链路，或把旧链路隔离成有 owner、调用者清单、删除条件和测试保护的 `compat-only` 路径。
13. 旧代码不得污染新链路: 旧 route/service/repository/frontend API 不得写 canonical facts、dirty scopes、outbox、read model readiness、cache 或 App Status。
14. Read Model 强制刷新是生产级合同: 必须通过统一 gateway/runbook/API contract，具备 scope validation、dedupe/idempotency、freshness proof、operation barrier 和跨页面回归测试。
15. Go / Go Fiber / Go Worker 只作为热点模块 carve-out 技术路线，不作为全量替换 Python 后端的当前主线。
16. 自动推进只能评估 `11-GO-HOT-PATH-CARVE-OUT.md` 中列出的 Go candidate；候选未通过性能证据、IO contract、legacy isolation、shadow run、rollback 和 freshness proof gate 时，只能标记 `go-candidate-deferred`。
17. 所有页面 read model 的目标优化方向是 `Partitioned Scoped Read Model + Scoped Incremental Projection`；Workbench 保留 active generation 原子发布模型。
18. Worker 目标态是逐个迁移到 `Go Worker + PostgreSQL Dual Queue`，其中 PostgreSQL dual queue 指 `job.outbox_events` 和 `job.read_model_dirty_scopes`；RabbitMQ 只能作为未来 wakeup/transport，不能作为事实源。

## 当前结论

需要在 `.planning/` 下建立独立重构目录。现有 `.planning/phases/` 更适合页面级分析，`.planning/debug/` 更适合问题排查；这次工作是跨模块架构治理，应放在独立 `refactors/modular-io-boundaries/` 下，并在后续根据实际执行再决定是否拆成 GSD phase。

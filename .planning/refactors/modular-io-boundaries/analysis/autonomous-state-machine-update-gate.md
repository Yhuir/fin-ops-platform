# Autonomous State Machine Update Gate

**日期:** 2026-06-23
**类型:** prompt/workflow guard clarification
**范围:** 只更新自动推进 prompt、全局重构状态机和 journal；不改业务代码、不改 read model manifest、不推进模块队列。

## 结论

`03-autonomous-start.md` 原本已经要求更新 `STATE.md`、`MODULE-QUEUE.md`、`JOURNAL.md`、`NEXT-PROMPT.md`，但状态机更新规则分散在 review/state update 段落中，容易被执行 agent 误解为只要生成 next prompt 就完成状态机更新。

本轮补强为独立 `State-machine update gate`：

- 每个 slice commit 前必须判断是否改变状态机定义。
- 改变全局 workflow state/transition/guard/stop/defer/completion criteria 时，必须更新 `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`。
- 改变模块业务/UI/read model/worker/operation barrier/force-refresh/permission/legacy-retirement 状态时，必须更新对应 `docs/modules/<module>/state-machine.md`。
- 未改变定义时，也必须在 analysis 文件记录 reviewed files、`definition unchanged` 原因和只更新 progress/accounting 的证据。
- 禁止只更新 `NEXT-PROMPT.md` 而不同步 `STATE.md`、`MODULE-QUEUE.md`、`JOURNAL.md` 和 analysis 证据。

## 状态机影响

- 已审阅全局状态机文件: `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- 已审阅模块状态机文件: 不适用。本轮没有选择业务模块边界，也没有改变任何模块业务状态、UI 状态、read model 状态、worker 状态、operation barrier 状态、force-refresh 状态、permission 状态或 legacy-retirement 状态。
- 全局状态机定义: changed。`AutonomousContinue` 的自动推进规则新增状态机更新闸门，明确 `NEXT-PROMPT.md` 不能替代完整状态机账本。
- 模块状态机定义: definition unchanged。没有业务模块语义变化。
- 当前执行状态: `autonomous-continue-after-cost-tax-ledger-summary-contract` 保持不变。
- 当前队列状态: `read-models:search-and-no-oa-bank-batch-contract` 仍是下一个 pending boundary。
- 成功转换: workflow guard clarification committed -> resume `read-models:search-and-no-oa-bank-batch-contract`。
- defer/block 转换: 若 prompt/global state-machine diff 未通过检查，则保持当前队列不变并修复 docs slice。

## 测试与验证合同

本轮是文档/prompt/workflow guard，不改变 runtime 行为。

- Business core unit tests: 不适用，未改变业务规则、金额、状态转移或权限判断。
- Service-layer tests: 不适用，未改变 service/repository/worker/read model/cache。
- API contract tests: 不适用，未改变 HTTP/API shape。
- Read model/cache/background job tests: 不适用，未改变 read model 或 worker 行为。
- Frontend component and interaction tests: 不适用，未改前端。
- E2E business-flow integration tests: 不适用，未改跨模块运行链路。
- Existing feature regression tests: 使用 `git diff --check` 和 secret scan 保护文档 diff；业务回归测试不适用。

## 验证要求

- `git diff --check -- .planning/refactors/modular-io-boundaries/prompts/03-autonomous-start.md .planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md .planning/refactors/modular-io-boundaries/analysis/autonomous-state-machine-update-gate.md .planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
- secret scan against staged diff.

## 下一步

提交本 workflow guard slice 后继续执行:

`read-models:search-and-no-oa-bank-batch-contract`

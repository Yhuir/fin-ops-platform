# Completion Semantics And Queue Reclassification

**日期:** 2026-06-24
**Boundary:** `planning:completion-semantics-and-queue-reclassification`
**状态:** `planning-closed`
**范围:** 修正自动队列完成语义、状态机规则、runbook、NEXT-PROMPT 和主控 prompt；不改业务代码、不改 runtime 行为、不改 API/read model/worker/前端。

## 触发原因

用户指出当前下一边界不应该是 GoHotPath，因为此前多个重构项并没有完成真正的模块化实现，却被标记为已完成。复核后确认该观点成立。

问题不是前序 slice 没有价值，而是 `closed-autonomous` 被过度泛化：

- 一部分 slice 是 analysis-only。
- 一部分 slice 是 manifest/contract/static guard。
- 一部分 slice 是 regression guard。
- 一部分 slice 是 route/inventory guard。
- 这些都不能等同于模块实现闭环。

## 核心修正

- `MODULE-QUEUE.md` 增加 `Module Closure` 维度，把 slice status 与模块实现闭环拆开。
- 废止把 `closed-autonomous` 当作泛用完成标签的做法。
- 将历史完成项重分类为：
  - `analysis-closed`
  - `contract-guard-closed`
  - `static-guard-closed`
  - `regression-guard-closed`
  - `route-guard-closed`
  - `inventory-guard-closed`
  - `planning-closed`
- 将 Go hot-path candidates 从 `pending` 改为 `blocked-by-prerequisite`。
- 将下一可执行边界改为 `read-models:pilot-gap-audit-and-contract-selection`。
- 新增主控 Goal Prompt: `prompts/04-master-goal-controller.md`。

## 当前真实状态

### Slice closure

历史 queue 中多数项已经完成了分析、合同、guard 或文档状态同步 slice。这些 slice 仍然有效，应作为后续实现的护栏和证据。

### Module implementation closure

模块实现闭环尚未完成。仍然开放的主线包括：

- 试点模块 IO 审计。
- 试点模块测试闸门补齐。
- 试点模块小步迁移。
- read model repository port / SQL owner 实际拆分。
- read model freshness、force refresh 和 operation barrier 的实现级闭环。
- legacy path 删除或 `compat-only` 隔离。
- 试点验收与模板修订。

### Go hot-path readiness

Go candidate 没有通过 admission。根据 `11-GO-HOT-PATH-CARVE-OUT.md`，Go 必须等相关模块满足以下前置条件：

- Module IO contract complete。
- Legacy retirement/quarantine complete。
- Freshness/force refresh/operation barrier contract complete。
- Performance evidence exists。
- Shadow run possible。
- Rollback possible。
- Python-vs-Go equivalence tests planned or available。

当前不满足，因此 GoHotPath 不能是下一主线边界。

## State Machine Impact

- 全局工作流状态: `autonomous-continue-after-planning-state-reconciliation` -> `autonomous-continue-after-completion-semantics-reclassification`。
- 选中边界进入前状态: `planning:completion-semantics-and-queue-reclassification` 为用户确认后的状态纠偏边界。
- 已审阅状态机文件:
  - `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
  - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
  - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
  - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
  - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- 全局状态机定义: changed。新增 slice status 与 module closure 分离规则，新增 Go candidate blocked-by-prerequisite 选择规则。
- 模块状态机定义: 不适用。本轮不改变任何业务模块状态、UI 状态、read model 状态、worker 状态、operation barrier 状态、force-refresh 状态、permission 状态或 legacy-retirement 状态。
- 成功流转: `autonomous-continue-after-planning-state-reconciliation` -> `autonomous-continue-after-completion-semantics-reclassification`。
- 下一边界: `read-models:pilot-gap-audit-and-contract-selection`。
- defer/block 流转: 若 queue/status/prompt 无法一致表达 slice/module closure 分离，则不得继续实现。当前未触发。

## 七类测试映射

| 类别 | 是否适用 | 本轮处理 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改业务规则、金额、状态转换或权限判断。 |
| 2. Service-layer tests | 不适用 | 不改 service/repository/read model/worker。 |
| 3. API contract tests | 不适用 | 不改 HTTP/API shape。 |
| 4. Read model/cache/background job tests | 不适用 | 不改 read model/cache/job 行为。 |
| 5. Frontend component and interaction tests | 不适用 | 无前端变化。 |
| 6. End-to-end business-flow integration tests | 不适用 | 不改业务运行链路。 |
| 7. Existing feature regression tests | 适用 | 使用 docs check、diff check、secret scan 和状态一致性审阅保护 planning 文档变更。 |

## 验证要求

- `bash scripts/verify.sh docs`
- `git diff --check`
- staged diff secret scan
- queue/status/prompt consistency review

## 验证结果

- `bash scripts/verify.sh docs` 通过。
- `git diff --check` 通过。
- diff secret scan 未发现真实凭据；仅命中策略文本中的 `secret` 字样。
- Queue slice status 重新统计:
  - `analysis-closed`: 1/28。
  - `contract-guard-closed`: 9/28。
  - `static-guard-closed`: 1/28。
  - `regression-guard-closed`: 1/28。
  - `route-guard-closed`: 1/28。
  - `inventory-guard-closed`: 1/28。
  - `planning-closed`: 2/28。
  - `production-evidence-deferred`: 1/28。
  - `pending`: 7/28。
  - `blocked-by-prerequisite`: 4/28。
- Module closure 重新统计:
  - `implementation-gap-open`: 14/28。
  - `implementation-pending`: 7/28。
  - `go-admission-not-started`: 4/28。
  - `not-module-closed`: 1/28。
  - `not-applicable`: 2/28。

## 后续执行规则

主控 Goal Prompt 必须按以下优先级选边界：

1. 若 planning/state/queue/prompt 不一致，先做 planning reconciliation。
2. 若存在 `pending` 的 implementation/foundation/read-model boundary，先做它。
3. 若存在 `implementation-gap-open`，必须排出具体实现边界，不能跳到 Go。
4. GoHotPath 只有在前置条件满足时才可从 `blocked-by-prerequisite` 改为 `pending`。
5. 每个 slice 都必须更新 analysis、STATE、MODULE-QUEUE、JOURNAL、NEXT-PROMPT 和必要的状态机定义。

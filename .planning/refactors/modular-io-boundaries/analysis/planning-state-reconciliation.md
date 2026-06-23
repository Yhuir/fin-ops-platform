# Planning State Reconciliation

**日期:** 2026-06-23
**Boundary:** `planning:state-reconciliation-and-roadmap-alignment`
**状态:** `closed-autonomous`
**范围:** 同步 `.planning/ROADMAP.md`、`.planning/refactors/` 与 `modular-io-boundaries/autonomous` 的事实源关系、状态口径和自动推进 prompt；不改业务代码、不改 runtime 行为、不改 API/read model/worker/前端。

## 触发原因

用户指出当前自动推进口径没有按根目录 `.planning/ROADMAP.md` 执行。复核后确认之前的完成度汇报只基于 `modular-io-boundaries/autonomous/MODULE-QUEUE.md`，不能代表整个 `.planning/ROADMAP.md`。

本轮纠偏目标是让后续 Codex 不再混淆三个层级：

1. `.planning/ROADMAP.md`: 页面分析与页面级 phase roadmap。
2. `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`: 模块化 IO 重构 phase roadmap。
3. `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`: 当前无人值守可执行的窄边界队列。

## 当前真实数据

### 根 `.planning/ROADMAP.md`

截至本轮读取：

| 状态 | 数量 | 百分比 |
| --- | ---: | ---: |
| `Complete` | 1 | 5.26% |
| `Implementation complete, apply gated` | 1 | 5.26% |
| `Not started` | 17 | 89.47% |
| 总计 | 19 | 100% |

解释：根 roadmap 是页面分析/计划路线图，不等同于模块化 IO 自动执行队列。若报告“整个 `.planning/ROADMAP.md`”进度，必须使用这个口径。

### Modular IO autonomous queue

本轮纠偏前为 19 个边界：14 个 `closed-autonomous`，1 个 `production-evidence-deferred`，4 个 `pending`。本轮插入并关闭 `planning:state-reconciliation-and-roadmap-alignment` 后，队列变为 20 个边界：15 个 `closed-autonomous`，1 个 `production-evidence-deferred`，4 个 `pending`。

解释：这是模块化 IO 重构自动推进队列，只能代表当前无人值守 slice 进度，不能代表根 roadmap。

### Modular IO phase roadmap

`04-IMPLEMENTATION-ROADMAP.md` 中 Phase 0 文档骨架和 Autonomous Overlay 已经实际成立，但 checkbox 之前未同步；本轮会把已完成的文档骨架和自动推进门槛标记为完成。Phase 1-7、Go Overlay 的多数完成标准仍未闭合，不能声明全局闭环。

## 决策

- 后续自动推进的主执行目标仍是“模块化 IO 边界重构”，以 `modular-io-boundaries` 下的需求、路线图、状态机、测试闸门、runbook、stop gates、Go carve-out 和 autonomous queue 为直接执行规则。
- 根 `.planning/ROADMAP.md` 必须作为输入和进度报告维度读取，不能忽略；但它不是 `modular-io-boundaries` 的 `MODULE-QUEUE.md` 替代品。
- 后续任何完成度报告必须分开列出：
  - Root page-analysis roadmap progress。
  - Modular IO phase roadmap progress。
  - Modular IO autonomous queue progress。
- 禁止用一个未标注来源的百分比代表“整个重构计划”。
- 后续自动 prompt 必须先做 planning-state preflight：如果 `README/status/ROADMAP/STATE/MODULE-QUEUE/NEXT-PROMPT` 互相矛盾，先执行 reconciliation slice，再继续业务边界。

## State Machine Impact

- 全局工作流状态: `AutonomousContinue`，当前执行状态为 `autonomous-continue-after-server-py-route-owner-inventory`。
- 选中边界进入前状态: `planning:state-reconciliation-and-roadmap-alignment` 为临时纠偏边界，未在原队列中登记。
- 已审阅状态机文件:
  - `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
  - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
  - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- 全局状态机定义: changed。自动推进规则新增 planning-state reconciliation gate 和 completion metric source rule。
- 模块状态机定义: 不适用。本轮不改变任何业务模块状态、UI 状态、read model 状态、worker 状态、operation barrier 状态、force-refresh 状态、permission 状态或 legacy-retirement 状态。
- 成功流转: `autonomous-continue-after-server-py-route-owner-inventory` -> `autonomous-continue-after-planning-state-reconciliation`。
- 下一边界: `go-hot-path:workbench-compute-admission`。
- defer/block 流转: 若 roadmap/status/prompt 无法在文档内一致表达，则保持本边界未完成并不继续后续实现。当前未触发。

## 七类测试映射

| 类别 | 是否适用 | 本轮处理 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改业务规则、金额、状态转换或权限判断。 |
| 2. Service-layer tests | 不适用 | 不改 service/repository/read model/worker。 |
| 3. API contract tests | 不适用 | 不改 HTTP/API shape。 |
| 4. Read model/cache/background job tests | 不适用 | 不改 read model/cache/job 行为。 |
| 5. Frontend component and interaction tests | 不适用 | 无前端变化。 |
| 6. End-to-end business-flow integration tests | 不适用 | 不改业务运行链路。 |
| 7. Existing feature regression tests | 适用 | 使用 docs check、diff check 和 prompt/status consistency review 保护 planning 文档变更。 |

## 验证要求

- `bash scripts/verify.sh docs`
- `git diff --check`
- staged diff secret scan

## 验证结果

- `bash scripts/verify.sh docs` 通过。
- `git diff --check` 通过。
- diff secret scan 未发现真实凭据；仅命中策略文本中的 `secret` 字样。
- 重新计算进度口径：
  - Root page-analysis roadmap: `Complete` 1/19，`Implementation complete, apply gated` 1/19，`Not started` 17/19。
  - Modular IO phase roadmap: 18/67 checkbox complete，49/67 open。
  - Modular IO autonomous queue: 15/20 `closed-autonomous`，1/20 `production-evidence-deferred`，4/20 `pending`。

## 后续 prompt 规则

自动推进 prompt 必须执行以下循环：

1. 审阅分析：读取根 roadmap、refactor 全目录、长期文档、当前状态机。
2. 实现：选择一个最小边界，完成代码/测试/docs 或纯文档状态修复。
3. 更新状态机：同步 analysis、STATE、MODULE-QUEUE、JOURNAL、NEXT-PROMPT 和必要的全局/模块 state-machine。
4. 生成并执行下一个 prompt：根据状态机和上一个边界完成度选择下一边界；不可只生成 prompt 后停止，除非 hard stop。

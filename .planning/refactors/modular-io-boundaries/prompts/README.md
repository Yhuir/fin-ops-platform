# Prompt 模板使用规则

本目录保存后续模块化 IO 重构可复用 prompt 模板。它们是执行工具，不是事实源。

## 使用原则

- 每次使用前，先读取目标模块的 `docs/modules/<module>/README.md`、`state-machine.md`、`tests.md`、`e2e-spec.md`、`e2e-coverage.md`。
- 每次使用前，检查当前 git status，避免覆盖用户未提交变更。
- 每次使用前，使用 CodeGraph 或静态扫描确认入口和影响面。
- prompt 输出必须沉淀为合同、计划、测试或风险登记，不保存未经提炼的长对话。
- 任何实现前都必须先完成 IO 合同和测试闸门。

## 模板

| 模板 | 用途 |
| --- | --- |
| `01-module-io-audit.md` | 对一个模块做 IO 合同审计，不改代码。 |
| `02-refactor-phase-planning.md` | 基于已完成 IO 合同，为一个模块生成实现 phase 计划。 |
| `03-autonomous-start.md` | 旧版完整 GSD 自动推进 goal prompt；保留作历史入口，但执行前必须遵守 `MODULE-QUEUE.md` 的新 slice/module closure 语义。 |
| `04-master-goal-controller.md` | 单线程主控 Goal Prompt：自动执行 planning preflight -> 当前 pending 边界 -> 状态更新 -> 下一个 prompt；当前下一步是 `planning:commit-backed-state-reconciliation`。不要把它同时喂给多个 thread。 |
| `05-parallel-thread-prompts.md` | 旧版手动并发 worker prompt/archetype 参考。保留给 T0 动态生成 worker prompt 时参考；不再要求用户手动启动 T1-T9。 |
| `06-t0-meta-orchestrator-goal.md` | 当前推荐入口：只启动一个 T0 `/goal`。T0 自动创建 worker threads、监控、收回 handoff、审阅、更新状态机、继续分发，直到全局闭环或 hard stop。 |

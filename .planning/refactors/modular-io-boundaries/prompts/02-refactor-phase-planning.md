# Prompt 模板: 单模块重构 Phase 规划

使用前提：

- `<module-key>-io-audit.md` 已完成。
- 目标模块 IO 合同已通过人工确认。
- 本次仍只生成计划，不直接实现，除非用户明确授权。

使用方式：

```text
使用 GSD 为 <module-key> 生成模块化 IO 重构 phase 计划。先不改业务代码。

必须读取：
- .planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md
- .planning/refactors/modular-io-boundaries/02-MODULE-IO-CONTRACT-TEMPLATE.md
- .planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md
- .planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md
- .planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md
- .planning/refactors/modular-io-boundaries/analysis/<module-key>-io-audit.md
- docs/modules/<module-key>/README.md
- docs/modules/<module-key>/state-machine.md
- docs/modules/<module-key>/tests.md

任务：
1. 读取当前 git status，保护用户未提交变更。
2. 把 gap list 转成小步迁移计划。
3. 每一步必须有目标、文件、风险、测试、回滚策略。
4. 先安排测试补齐，再安排代码迁移。
5. 明确哪些长期 docs 会更新。
6. 明确哪些七类测试适用。
7. 明确 legacy path 删除、隔离或 compat-only 的顺序和防污染测试。
8. 明确 force refresh、freshness proof、operation barrier 和跨页面同步测试。
9. 明确 partitioned scoped incremental projection 的 partition key、scope key、full rebuild fallback、parent/aggregate 和测试。
10. 如果模块在 Go candidate list 中，只生成 Go admission 计划：性能证据、shadow run、Python-vs-Go equivalence、防双写、rollback、Go Worker/Fiber 形态；未通过 gates 不得进入 Go 实现。
11. 明确没有本地 PGSQL_URL 和 staging 数据库时的验证分层：local static、local fake/stub、production read-only、production controlled-write。
12. 输出到 .planning/refactors/modular-io-boundaries/analysis/<module-key>-refactor-plan.md。

禁止：
- 不做全局重构。
- 不把大文件拆小作为独立目标。
- 不改变业务行为。
- 不删除 legacy path，除非调用点和测试已证明安全。
- 不保留能写 canonical facts、dirty scopes、outbox、read model readiness、cache 或 App Status 的未登记 legacy path。
- 不通过页面级“刷新所有”掩盖 read model scope/freshness 合同错误。
- 不在候选列表之外 Go 化模块。
- 不在 admission gates 通过前实现 Go/Fiber/Go Worker。
- 不让 Fiber handler 承载长时间后台任务。
- 不让 Python worker 和 Go worker authoritative 双写、双 ack 或双 publish。
- 不新增依赖，除非有明确收益和维护理由。
- 不要求用户提供 SSH 密码或任何 secret。
- 不把无法本地执行的真实 DB/worker 验证伪装成已完成。

输出：
- 阶段目标。
- 分步计划。
- 测试计划。
- docs impact。
- legacy 退役/隔离计划。
- Read Model 强制刷新和跨页面 freshness 计划。
- Partitioned scoped incremental projection 计划。
- Go candidate admission 计划或 not applicable。
- 环境限制、生产只读/受控写入验证计划。
- 回滚策略。
- 完成定义。
```

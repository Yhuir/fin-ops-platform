# GSD 工作区说明

`.planning/` 保存 GSD 执行状态、阶段计划、debug 记录、page baseline 和历史工作流产物。它是协作和恢复上下文的工作区，不作为当前需求、架构、API 或验收事实源，也不是当前产品、read model、worker 或部署事实源。

使用规则：

- 当前事实必须优先读取 `AGENTS.md`、`README.md`、`ARCHITECTURE.md`、`docs/index.md`、`docs/app-architecture/`、`docs/modules/`、`docs/product-specs/`、`docs/dev/` 和 `docs/operations/`。
- `.planning/debug/`、`.planning/phases/`、`.planning/quick/`、`.planning/spikes/` 中的记录只能作为历史排查线索。采用其中任何结论前，必须用当前代码、测试和长期文档重新验证。
- 仍有长期价值的结论应提炼到 `docs/` 对应长期事实源；不要把新的原始 prompt 或一次性执行记录复制进主文档树。
- 如果 `.planning/` 内容与当前代码或长期文档冲突，以当前代码和长期文档为准，并按文档维护规则更新长期事实源。

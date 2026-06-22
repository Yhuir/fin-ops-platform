# Refactors 工作区

本目录保存跨模块、跨页面或跨运行时边界的重构规划。它只作为 GSD 工作区，不替代当前代码或长期文档事实源。

## 当前重构主题

| 目录 | 主题 | 状态 |
| --- | --- | --- |
| `modular-io-boundaries/` | 模块化 IO 边界重构：为每个模块建立输入、输出、状态、事件、read model、权限、测试和边界合同。 | Analysis only |

## 使用规则

- 先读具体重构目录的 `README.md`。
- 实现前必须回到 `AGENTS.md`、`ARCHITECTURE.md`、`docs/app-architecture/`、`docs/modules/` 和相关测试确认当前事实。
- 本目录可以保存计划、状态机、风险登记和 prompt 模板；长期事实变化必须同步到 `docs/`。


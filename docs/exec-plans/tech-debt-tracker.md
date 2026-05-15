# 技术债跟踪

本文件记录仍需要跟进但尚未进入具体实施计划的技术债。

## 当前重点

- 将工作台、搜索、成本统计等重查询路径继续收敛到物化读模型。
- 将后台任务状态和健康告警统一到可恢复、可重试的任务体系。
- 执行 Axum + PostgreSQL 后端重构计划，入口见 `active/backend-axum-postgres-refactor.md` 和 `../architecture/backend-refactor/README.md`。
- 将历史本地 pickle/JSON 兼容路径逐步收敛，避免生产依赖本地文件。
- 为导入、OA 同步、ETC 修复等长任务补充更明确的失败恢复文档。

# 架构文档索引

## 总览

- `../../ARCHITECTURE.md`：系统架构总览。
- `system-overview.md`：模块边界和主要数据流。
- `data-model.md`：核心领域实体和状态设计。

## 专题

- `oa-integration.md`：OA 页面壳体、登录复用、菜单权限和部署路径。
- `persistence-and-read-models.md`：当前持久化、read model、缓存失效和性能演进。
- `deployment.md`：部署形态、环境、反向代理和发布边界。
- `backend-refactor/README.md`：Axum + PostgreSQL 后端重构文档入口。
- `backend-refactor/target-architecture.md`：目标生产架构、组件边界和技术选型。
- `backend-refactor/migration-roadmap.md`：分阶段迁移路线、验收标准和回滚口径。
- `backend-refactor/data-model-and-read-models.md`：PostgreSQL 事实表、分区、搜索表、读模型和索引计划。
- `backend-refactor/postgresql-schema-notes.md`：生产 PostgreSQL schema、分区、约束、权限和迁移分组建议。
- `backend-refactor/outbox-and-jobs.md`：Outbox、NATS JetStream、Worker 状态机和任务可靠性设计。
- `backend-refactor/read-models-and-search.md`：读模型增量重建、搜索索引表、缓存失效和一致性策略。

## 历史资料

- 旧方案和阶段性计划已归档到 `../archive/legacy-docs/` 与 `../archive/superpowers/`。

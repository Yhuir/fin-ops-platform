# 文档地图

这棵文档树按“入口短、专题深、过程文档不保留”的原则整理。当前有效文档只放在长期目录里；历史 prompt、旧计划和阶段执行记录不再作为当前需求、架构或验收依据。

## 快速入口

- 项目总览：`../README.md`
- 架构总览：`../ARCHITECTURE.md`
- 设计原则：`../DESIGN.md`
- 可靠性：`../RELIABILITY.md`
- 安全权限：`../SECURITY.md`
- 仓库和 Agent 约定：`../AGENTS.md`

## 长期文档目录

| 目录 | 用途 |
| --- | --- |
| `app-architecture/` | 当前 app 架构、页面、运行时调用链、页面间影响关系 |
| `product-specs/` | 面向产品和业务的需求、口径、验收标准 |
| `architecture/` | 系统边界、数据模型、持久化、部署形态 |
| `dev/` | 开发者入口、接口契约、测试、本地运行 |
| `operations/` | 部署、数据安全、worker/read model、监控告警 |
| `references/` | 仓库布局、外部系统、原始业务源和迁移历史摘要 |
| `refactor-ui/` | `refactor-ui` 分支 UI 平台迁移工作流、状态机、切片 prompt 和表格排版系统 |

## 推荐阅读路径

### 新开发者

1. `../README.md`
2. `../ARCHITECTURE.md`
3. `app-architecture/README.md`
4. `dev/local-development.md`
5. `dev/codebase-development.md`
6. `dev/runtime-development.md`
7. `dev/testing.md`

### 产品和业务梳理

1. `product-specs/index.md`
2. `product-specs/reconciliation-and-workbench.md`
3. `product-specs/imports-and-etc.md`
4. 按业务域继续阅读发票生命周期、银行/往来款、成本/税金、平台设置和健康状态文档。

### 生产部署和运维

1. `../SECURITY.md`
2. `operations/deployment.md`
3. `operations/data-safety.md`
4. `operations/runtime-worker-governance.md`
5. `operations/monitoring.md`

### Python-first 后端架构重构

1. `architecture/backend-refactor/README.md`
2. `architecture/backend-refactor/target-architecture.md`
3. `architecture/backend-refactor/module-refactor-plan.md`
4. `architecture/backend-refactor/runtime-call-chain.md`
5. `architecture/backend-refactor/read-model-and-external-services.md`
6. `architecture/backend-refactor/migration-roadmap.md`
7. `architecture/backend-refactor/ai-execution-rules.md`
8. `architecture/backend-refactor/migration-state-log.md`
9. `architecture/backend-refactor/refactor-prompts.md`

### 当前 App 架构维护

1. `app-architecture/pages.md`
2. `app-architecture/runtime-and-ownership.md`
3. `app-architecture/docs-maintenance.md`

### UI 平台迁移

1. `refactor-ui/README.md`
2. `refactor-ui/refactor_ui_state.md`
3. `refactor-ui/refactor_ui_prompt.md`
4. `refactor-ui/table_layout_system.md`
5. `../DESIGN.md`

### PostgreSQL Runtime

1. `operations/postgresql-runtime.md`
2. `operations/runtime-worker-governance.md`
3. `references/postgresql-migration-history.md`

## 当前技术债

这些事项只在索引中保留提醒；进入实际执行时应沉淀到对应产品、架构、开发或运维文档，长期重构进度记录到 `architecture/backend-refactor/migration-state-log.md`。

- 将工作台、搜索、成本统计等重查询路径继续收敛到物化读模型。
- 将后台任务状态和健康告警统一到可恢复、可重试的任务体系。
- 执行 Python-first 后端重构计划，入口见 `architecture/backend-refactor/README.md`。
- 将历史本地 pickle/JSON 兼容路径逐步收敛，避免生产依赖本地文件。
- 为导入、OA 同步、ETC 修复等长任务补充更明确的失败恢复文档。

## 清理说明

- 历史 Codex prompt、Superpowers plans/specs 和数据库迁移阶段记录已删除。
- 仍有当前价值的结论已合并到 `app-architecture/`、`operations/`、`product-specs/`、`dev/` 或 `references/`。
- 原始业务源只保留在 `references/`，不作为当前验收标准。

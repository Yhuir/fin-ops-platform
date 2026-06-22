# 文档地图

这棵文档树按“入口短、专题深、过程文档不保留”的原则整理。当前有效文档只放在长期目录里；历史 prompt、旧计划和阶段执行记录不再作为当前需求、架构或验收依据。

## 事实源边界

- 当前产品、架构、API、read model、worker、部署和测试事实只以本页列出的长期文档入口为准。
- `.planning/` 是 GSD 执行工作区和历史执行记录，不作为当前需求、架构、API 或验收事实源；仍有价值的结论必须先提炼到 `docs/` 的长期事实源后才能作为依据。
- `docs/refactor-ui/` 是 `refactor-ui` 分支 UI 平台迁移的专项工作区。该目录中的 prompt、master goal、state 或迁移队列只约束对应 UI 迁移流程，不作为当前 `main` 分支的后端、API、read model、worker 或生产运行事实源。
- `docs/modules/*/implementation-notes.md` 只保存提炼后的目标、决策、验收、风险和后续事项；读取到历史记录时，必须回到模块 `README.md`、`state-machine.md`、`tests.md` 以及产品/架构/开发/运维长期事实源确认当前事实。

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
| `business-flows/` | 面向业务读者的页面目的、操作流程、数据流向和页面间影响关系 |
| `modules/` | 按页面和关键功能域组织的维护入口、状态机、测试矩阵和实施记录 |
| `product-specs/` | 面向产品和业务的需求、口径、验收标准 |
| `architecture/` | 系统边界、数据模型、持久化、部署形态 |
| `dev/` | 开发者入口、接口契约、测试、本地运行 |
| `operations/` | 部署、数据安全、worker/read model、监控告警 |
| `references/` | 仓库布局、外部系统、原始业务源和迁移历史摘要 |
| `refactor-ui/` | `refactor-ui` 分支 UI 平台迁移专项工作区；其中 prompt/state 只约束 UI 迁移流程，不替代当前 app 长期事实源 |

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

1. `business-flows/README.md`
2. 按页面阅读 `business-flows/` 下的具体页面流程文档。
3. `product-specs/index.md`
4. `product-specs/reconciliation-and-workbench.md`
5. `product-specs/imports-and-etc.md`
6. 按业务域继续阅读发票生命周期、银行/往来款、成本/税金、平台设置和健康状态文档。

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
4. `modules/README.md`

### 页面和功能模块维护

1. `modules/README.md`
2. 按目标页面或功能域读取对应 `modules/<module>/README.md`
3. 按影响范围继续读取该模块下的 `state-machine.md`、`tests.md`、`implementation-notes.md`
4. 如模块文档链接到产品、架构、开发或运维长期事实源，以长期事实源为准并同步维护

### UI 平台迁移

仅在处理 `refactor-ui` 分支或 UI 平台迁移任务时读取本路径。处理当前 app 后端、API、read model、worker、生产运行或业务状态时，不从该目录的 prompt/state 文件推导事实。

1. `refactor-ui/README.md`
2. `refactor-ui/refactor_ui_state.md`
3. `refactor-ui/refactor_ui_prompt.md`
4. `refactor-ui/baseline_inventory.md`
5. `refactor-ui/platform_stack_migration.md`
6. `refactor-ui/test_migration_strategy.md`
7. `refactor-ui/module_inventory.md`
8. `refactor-ui/refactor_ui_master_goal_prompt.md`
9. `refactor-ui/table_layout_system.md`
9. `../DESIGN.md`

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

# 文档地图

这棵文档树按“入口短、专题深、历史归档”的原则整理。当前有效文档只放在长期目录里；历史 prompt 和旧计划保留在 `docs/archive/`，用于追溯，不作为当前需求或架构依据。

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
| `product-specs/` | 面向产品和业务的需求、口径、验收标准 |
| `architecture/` | 系统边界、数据模型、持久化、部署形态 |
| `dev/` | 开发者入口、接口契约、测试、本地运行 |
| `operations/` | 部署、数据重置、备份恢复、监控告警 |
| `references/` | 仓库布局、源文档、外部系统资料 |
| `exec-plans/` | 当前仍需要跟踪的执行计划和技术债 |
| `archive/` | 历史 prompt、旧计划、旧设计、需求源文档 |

## 推荐阅读路径

### 新开发者

1. `../README.md`
2. `../ARCHITECTURE.md`
3. `dev/local-development.md`
4. `dev/backend.md`
5. `dev/frontend.md`
6. `dev/testing.md`

### 产品和业务梳理

1. `product-specs/index.md`
2. `product-specs/reconciliation.md`
3. `product-specs/workbench.md`
4. 按专题继续阅读导入、异常处理、税金/ETC、成本统计、往来款等文档。

### 生产部署和运维

1. `../SECURITY.md`
2. `operations/deployment.md`
3. `operations/data-reset.md`
4. `operations/backup-and-recovery.md`
5. `operations/monitoring.md`

### Axum/PostgreSQL 后端重构

1. `architecture/backend-refactor/README.md`
2. `architecture/backend-refactor/target-architecture.md`
3. `architecture/backend-refactor/migration-roadmap.md`
4. `architecture/backend-refactor/data-model-and-read-models.md`
5. `operations/backend-refactor/mongo-backup.md`
6. `operations/backend-refactor/postgresql-provisioning.md`
7. `operations/backend-refactor/mongo-to-postgresql-migration.md`

## 归档说明

- `archive/prompts/`：历史 Codex prompt，保留用于追溯。
- `archive/superpowers/`：历史 specs/plans，保留用于追溯。
- `archive/legacy-docs/`：整理前的旧 PRD、roadmap、solution design 和 task breakdown。
- `archive/product-sources/`：原始业务需求源文档。

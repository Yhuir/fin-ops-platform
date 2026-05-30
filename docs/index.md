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
| `database-migration/` | app MongoDB 到 PostgreSQL 的迁移方案、服务器盘点、目标数据设计和执行计划 |
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

### App Mongo 到 PostgreSQL 迁移

1. `database-migration/README.md`
2. `database-migration/00-current-state-inventory.md`
3. `database-migration/code-evidence-index.md`
4. `database-migration/01-production-backup-staging.md`
5. `database-migration/01-target-postgresql-design.md`
6. `database-migration/02-postgresql-schema-migration.md`
7. `database-migration/03-normalized-export-staging-import.md`
8. `database-migration/04-staging-transform-reconciliation.md`
9. `database-migration/05-postgresql-repository-tests.md`
10. `database-migration/06-postgresql-integration-repository-closure.md`
11. `database-migration/07-postgresql-domain-repository-completion.md`
12. `database-migration/08-postgresql-domain-repository-final-closure.md`
13. `database-migration/09-postgresql-repository-extraction-transaction-boundary.md`
14. `database-migration/10-shadow-dualwrite-cutover-preflight.md`
15. `database-migration/11-production-shadow-read-rehearsal.md`
16. `database-migration/12-production-shadow-read-oneoff.md`
17. `database-migration/13-shadow-mismatch-remediation-backfill-repair.md`
18. `database-migration/14-runtime-state-policy-mirror-rehearsal.md`
19. `database-migration/15-production-controlled-mirror-write-rehearsal.md`
20. `database-migration/15A-workbench-p0-remediation.md`
21. `database-migration/16-worktree-postgres-test-onboarding.md`
22. `database-migration/17-pending-invoice-postgres-coverage.md`
23. `database-migration/18-worktree-0008-full-data-revalidation.md`
24. `database-migration/19-main-production-fresh-import-reconcile.md`
25. `database-migration/19A-production-transform-natural-key-remediation.md`
26. `database-migration/20-production-controlled-runtime-mirror-write-rehearsal.md`
27. `database-migration/21-precutover-readonly-p2-closure.md`
28. `database-migration/22-production-read-switch-cutover-plan.md`
29. `database-migration/23-release-runtime-credential-prep.md`
30. `database-migration/24-controlled-read-switch-rehearsal.md`
31. `database-migration/25-controlled-read-switch-execute.md`
32. `database-migration/25A-actual-postgres-store-shadow-remediation.md`
33. `database-migration/25B-workbench-candidate-runtime-snapshot-repair.md`
34. `database-migration/07-shadow-dualwrite-production-cutover.md`
35. `database-migration/02-execution-plan.md`

## 归档说明

- `archive/prompts/`：历史 Codex prompt，保留用于追溯。
- `archive/superpowers/`：历史 specs/plans，保留用于追溯。
- `archive/legacy-docs/`：整理前的旧 PRD、roadmap、solution design 和 task breakdown。
- `archive/product-sources/`：原始业务需求源文档。

# P4-11 切换执行记录 - 20260516 - Blocked

本文对应 P4-11：双写、切读、回滚与旧系统冻结。本次只做切换前门禁和授权状态复核，不执行生产切流，不冻结 app Mongo，不切换 API，不访问 OA 源数据库。

## 执行结论

| 项目 | 结果 |
| --- | --- |
| execution_status | `blocked_not_executed` |
| cutover_phase | none |
| 是否执行影子读 | 否 |
| 是否执行小流量读切换 | 否 |
| 是否执行双写 | 否 |
| 是否执行全量切读 | 否 |
| 是否停止旧写 | 否 |
| 是否冻结 app Mongo | 否 |
| 是否触发回滚 | 否 |
| 是否访问 OA 源数据库 | 否 |
| 是否开放 PostgreSQL 公网 | 否 |

阻断原因：

1. P4-12 正式迁移门禁报告 `formal-migration-go-no-go-20260516.md` 结论为 `NO_GO`，不是 `GO`。
2. 当前对话没有给出“明确授权生产切换”的授权语句。
3. 维护窗口未确认。
4. 回滚路径未完成演练确认。
5. 最新 app Mongo 备份虽已存在并校验通过，但 P4-11 还要求 PostgreSQL PITR、dry-run 对账、文件 checksum、API 影子验证、压测和监控均通过；当前缺少这些证据。

## 读取和复核输入

| 输入 | 结果 |
| --- | --- |
| `docs/exec-plans/active/backend-refactor-prompts/11-cutover-and-rollback.md` | 已读取。明确生产切流必须在门禁通过并获得用户确认后执行。 |
| `docs/exec-plans/active/backend-refactor-prompts/00-current-state-and-gates.md` | 已读取。当前仍列出 dry-run、文件迁移、read model、API 迁移、PITR、压测、影子读、双写、切读、冻结 app Mongo 等未完成项。 |
| `docs/operations/backend-refactor/formal-migration-go-no-go-20260516.md` | 已读取。结论为 `NO_GO`，不允许正式迁移生产数据、冻结 app Mongo、生产 API 切换或进入 P4-11 生产切流。 |
| `docs/operations/backend-refactor/cutover-and-rollback-runbook.md` | 已读取。进入生产影子读前要求 readiness 无阻断、迁移对账无差异、文件 checksum、压测和回滚演练通过。 |
| `docs/architecture/backend-refactor/migration-roadmap.md` | 已读取。切换顺序必须是 `expand -> backfill -> dual write / verify -> switch read -> contract`。 |
| `docs/operations/backend-refactor/mongo-backup.md` | 已读取。正式迁移前需要公告维护窗口、停写或双写策略、冻结点备份。 |
| `docs/operations/backend-refactor/mongo-to-postgresql-migration.md` | 已读取。PostgreSQL 成为事实源后，不允许旧 Mongo 全量覆盖新库。 |
| `docs/operations/backend-refactor/production-readiness-checklist.md` | 已读取。当前仍为 readiness 模板状态，P4-10 结论为 `NO_GO`。 |
| `docs/operations/backend-refactor/migration-validation-report-template.md` | 已读取。对账差异必须可定位到对象、月份、状态、legacy id 或 row_no。 |

## 硬性前置状态

| P4-11 硬性前置 | 当前状态 | 证据 | 是否通过 |
| --- | --- | --- | --- |
| P4-12 输出 `GO` | P4-12 输出 `NO_GO` | `formal-migration-go-no-go-20260516.md` | 否 |
| 用户明确授权生产切换 | 当前无明确授权语句 | 本次用户请求写明“只允许在用户明确授权后执行” | 否 |
| 维护窗口确认 | 未发现维护窗口记录 | P4-12 报告列为阻断项 | 否 |
| 回滚路径确认 | 有 runbook 模板，未发现演练记录 | `cutover-and-rollback-runbook.md`、P4-12 报告 | 否 |
| 最新 app Mongo 备份确认 | 已有最近备份和恢复演练 | `app-mongo-backup-runbook.md` 记录 `2026-05-16 01:29:00 CST` 备份、checksum、恢复测试库和 GridFS 抽样 | 是 |

## 切换执行记录

| 字段 | 值 |
| --- | --- |
| change_id | not_created |
| phase | blocked_before_phase_1 |
| started_at | 2026-05-16 22:27:39 CST |
| ended_at | 2026-05-16 22:27:39 CST |
| operator | Codex |
| approver | none |
| old_backend_version | not_changed |
| new_backend_version | not_promoted |
| worker_version | not_changed |
| web_version | not_changed |
| mongo_backup_id | `/data/backups/fin_ops/2026-05-16_012900` |
| postgres_backup_id | missing |
| feature_flags | not_changed |
| routes_changed | none |
| data_migration | not_executed |
| app_mongo_freeze | not_executed |
| decision | `blocked_not_executed` |

## 观测结果

本次没有执行生产操作，因此没有新的生产指标快照、切流前后对比、用户流量观测或错误率变化。

| 观测项 | 结果 |
| --- | --- |
| API route | 未变更 |
| 前端流量 | 未变更 |
| Axum 承载生产流量 | 否 |
| Python 后端承载状态 | 未变更 |
| PostgreSQL 公网暴露 | 未变更；当前文档记录为只监听 localhost |
| PostgreSQL 写入生产事实表 | 未执行 |
| NATS/Worker 生产任务 | 未变更 |
| read model stale | 未执行生产观测 |
| P0/P1 告警 | 未执行生产观测；P4-12 已列为缺少验证证据 |

## 回滚状态

未执行切流，因此不需要启动回滚。

| 回滚项 | 状态 |
| --- | --- |
| 读路由回滚 | not_needed |
| 双写关闭 | not_needed |
| outbox/差异补偿 | not_needed |
| 文件恢复 | not_needed |
| PostgreSQL 清理 | not_needed，不允许破坏性清理 |
| app Mongo 恢复 | not_needed，不允许删除或覆盖 |

如果后续 P4-12 转为 `GO` 并获得明确授权，P4-11 仍必须从“影子读”开始，不能跳过到全量切读或停止旧写。

## app Mongo 冻结/归档状态

| 项目 | 状态 |
| --- | --- |
| app Mongo 当前角色 | 旧系统事实源和回滚参考 |
| 是否冻结 | 否 |
| 是否归档 | 否 |
| 是否删除 | 否 |
| 最新已知备份 | `/data/backups/fin_ops/2026-05-16_012900` |
| 备份 checksum | `1968e81888dd359ba7d9d8424cdef399744d81a6d5e7305db1f8222404b9422a` |
| 恢复演练 | 已恢复到 `fin_ops_platform_app_restore_test_20260516`，collection count `diff=0` |

进入真正冻结前仍需：

1. P4-12 输出 `GO`。
2. 用户明确授权生产切换。
3. 维护窗口确认。
4. 回滚路径演练通过。
5. PostgreSQL PITR、dry-run 对账、文件 checksum、API 影子验证、压测和监控全部通过。
6. 创建冻结点备份并记录 Mongo collection count、应用版本和配置摘要。

## 禁止事项确认

- 未执行生产切流。
- 未冻结 app Mongo。
- 未删除 app Mongo。
- 未迁移生产数据。
- 未切换 API route。
- 未开启双写。
- 未把 PostgreSQL 设为事实源。
- 未用旧 Mongo 覆盖 PostgreSQL。
- 未访问、备份、导出、恢复、修改、压测或人工查询 OA 源数据库。
- 未开放 PostgreSQL 公网。
- 未写入 secret、URI、密码、token、S3 credential 或 NATS credential。


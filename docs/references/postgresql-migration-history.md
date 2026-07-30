# PostgreSQL 迁移历史摘要

本文保留从 app MongoDB 迁移到 PostgreSQL 的关键结论。原阶段文档、prompt 和报告已删除，不再作为当前开发入口。

## 最终结论

- app 主读写已切到 PostgreSQL primary runtime。
- OA MongoDB 保持外部只读源。
- app Mongo 旧路径曾用于迁移观察期审计、shadow-read 和回滚参考；相关 runtime/rehearsal 工具现已删除。
- PostgreSQL schema version 到达 `0008` 是当时 production read switch 的历史里程碑，不代表当前 schema version。
- 迁移分支已合入 main，并完成 main release redeploy。

## 迁移阶段浓缩

| 阶段 | 结论 |
| --- | --- |
| 盘点和目标设计 | 明确 app Mongo collection、GridFS、OA Mongo 只读边界、PostgreSQL schema、read model/job/audit schema。 |
| staging 导出导入 | 通过规范化 export、staging import、正式表 transform 和 reconcile 校验数量、金额、状态分布。 |
| repository 覆盖 | 将核心 app state、workbench、导入、税金、ETC、银行、往来、background jobs 等 repository 接入 PostgreSQL。 |
| shadow-read / dual-write | 历史迁移期曾通过 shadow-read、runtime policy 和 controlled mirror-write 验证差异，修复 P0/P1 blocker；这些旧 rehearsal 工具已在 canonical facts wave 5 删除。 |
| runtime credential | 准备 PostgreSQL runtime credential 和 service drop-in，完成 no-traffic PostgreSQL mode check。 |
| controlled read switch | same-run gates 通过后切 production service 到 PostgreSQL primary。 |
| main redeploy | main release 重新部署，`/health` 确认 backend=postgres，HTTP smoke 返回期望状态。 |

## 保留的关键生产事实

| 项 | 值 |
| --- | --- |
| production mode | `postgres_primary` |
| storage backend | `postgres` |
| read backend | `postgres` |
| cutover schema milestone | `0008`；当前版本以 migration runner 和 `/health` 为准 |
| OA Mongo | 只读接入，不触碰 `form_data_db.form_data` 写入边界 |
| app Mongo | 离线历史遗留物；不进入 runtime、回滚、审计或当前开发事实链路 |

## 迁移遗留规则

- 不允许把旧 Mongo payload 作为当前业务事实源。
- 不允许用旧 app Mongo 全量覆盖 PostgreSQL。
- 需要修复生产差异时，使用补偿脚本、事务 writer、outbox 重投递和审计记录。
- 需要新增 read model/worker 时，更新 registry、manifest/systemd、tests、docs。
- 需要查迁移前字段或 collection 证据时，优先读当前代码和 PostgreSQL repository；本文只保留历史摘要。

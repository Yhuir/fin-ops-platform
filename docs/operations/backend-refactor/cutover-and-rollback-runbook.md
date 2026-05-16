# 后端重构切换与回滚运行手册

本文描述 Axum + PostgreSQL 后端从旧 Python + App Mongo 路径切换到新路径的阶段、进入条件、执行步骤、验证和回滚。本文不是生产授权；任何生产切流都必须在所有门禁通过后单独获得确认。

## 总原则

- 切换顺序遵循 `expand -> backfill -> dual write / verify -> switch read -> contract`。
- 每个阶段只推进一个风险面：先影子读，再小流量读，再双写，再全量切读，再停止旧写。
- OA 源数据库始终只读接入；不备份、不导出、不恢复、不修改 OA 源库。
- App Mongo 在迁移期保留为旧事实源和回滚参考；迁移完成后冻结归档，不立即删除。
- PostgreSQL 不开放公网；切换不得以开放 PostgreSQL 公网作为解决方案。
- PostgreSQL 成为事实源后，不允许用旧 Mongo 全量覆盖新库，只能走补偿脚本和审计记录。

## 角色

| 角色 | 职责 |
| --- | --- |
| 切换负责人 | 控制阶段推进、暂停和回滚决策。 |
| 后端负责人 | Axum、Python API、worker、migration 和双写逻辑验证。 |
| DBA/运维 | PostgreSQL、Mongo 备份、PITR、容量、网络策略。 |
| 前端/Nginx 负责人 | API route、灰度、回滚路由。 |
| 业务验收人 | 样本对账、页面口径、核销流程确认。 |
| 值班人 | 监控、告警、事故记录和升级。 |

## 切换前硬性门禁

全部满足后才能进入生产影子读：

- [ ] `production-readiness-checklist.md` 无阻断项。
- [ ] App Mongo 全量备份、checksum 和恢复演练通过。
- [ ] PostgreSQL 逻辑备份和 PITR 或等价时间点恢复演练通过。
- [ ] Mongo 到 PostgreSQL 迁移对账无无法解释差异。
- [ ] GridFS 到 MinIO/S3 checksum 抽样通过。
- [ ] Axum API staging 测试、构建、迁移、压测通过。
- [ ] read model 可从事实表重建。
- [ ] 核销确认、撤销、异常处理、数据重置、权限设置有审计日志。
- [ ] 回滚路径已演练，并确认旧 Python 和 App Mongo 在回滚窗口内可用。
- [ ] P0/P1 告警清零或均有已批准的风险接受记录。

## 变更冻结

进入切换窗口前：

1. 公告维护或低峰切换窗口。
2. 冻结 schema migration 以外的生产变更。
3. 暂停非必要批量导入、批量重建和高风险运维操作。
4. 记录旧 Python、Axum、Worker、前端、migration 工具版本和 commit。
5. 记录 App Mongo、PostgreSQL、MinIO/S3、NATS、Redis 的健康状态。
6. 创建切换前备份点并记录备份 ID。

## 阶段 1：影子读

### 进入条件

- 历史数据已 backfill 到 PostgreSQL。
- read model 已按当前事实表重建。
- Axum 查询接口可在生产环境访问依赖，但不承载用户可见结果。
- 差异记录表或差异报告文件已准备。

### 执行步骤

1. 保持用户流量仍访问旧 Python API。
2. 对低风险只读请求复制查询条件，在后台调用 Axum 查询 PostgreSQL。
3. 记录旧结果和新结果的数量、金额、状态分布、关键字段摘要和 trace id。
4. 不把 Axum 影子结果返回给用户。
5. 每日生成差异报告；切换窗口内按小时生成。

### 验证

- API P95/P99 没有因影子读明显上升。
- 影子读失败不影响旧系统响应。
- 差异率低于已批准阈值；金额和状态差异必须逐条解释。
- read model stale 在阈值内。

### 回滚

关闭影子读开关或停止复制查询。无需改用户路由。保留差异样本和 trace id。

## 阶段 2：小流量读切换

### 进入条件

- 影子读连续通过约定验证窗口。
- 低风险只读 API 的差异为 0 或全部解释。
- 读回滚路由已演练。

### 执行步骤

1. 只切换低风险只读 API，例如健康检查、设置读取、导入历史、文件元数据。
2. 先按内部用户、单菜单或小比例流量切到 Axum。
3. 监控 API latency、4xx/5xx、PostgreSQL pool、read model stale、OA sync lag。
4. 保持旧 Python API 可立即接回读流量。

### 验证

- 5xx 未超过告警阈值。
- P95/P99 在 staging 压测目标和生产基线可接受范围内。
- 业务验收样本一致。
- 无 PostgreSQL 慢查询、连接池耗尽或 read model stale P1 告警。

### 回滚

将对应 API route 切回旧 Python。PostgreSQL 保留现场，不清表、不重跑破坏性脚本。

## 阶段 3：双写

### 进入条件

- 读路径小流量稳定。
- 所有关键写操作已实现同一 idempotency key。
- 双写差异报告已可按时间窗口、用户、业务对象和 trace id 查询。
- 旧 Mongo 写路径和 PostgreSQL 写路径均有审计。

### 范围

优先纳入：

- 导入确认。
- 核销确认。
- 核销撤回。
- 异常处理。
- 备注、忽略、免 OA 批次等影响业务事实的写操作。

暂缓纳入：

- 数据重置。
- 大范围批量修复。
- 仍未完成审计和幂等校验的高风险操作。

### 执行步骤

1. 打开双写开关，旧 Mongo 仍作为用户可见主路径。
2. 每个写请求生成或校验同一 idempotency key。
3. 先写当前主事实源，再写 PostgreSQL 或通过事务 outbox 可靠补偿；具体顺序以已评审实现为准。
4. 每次写入记录旧新对象 ID 映射、trace id、用户、动作和结果。
5. 定时生成差异报告，比对数量、金额、状态、审计事件和 read model 重建结果。
6. 发现差异时暂停进入下一阶段。

### 验证

- 双写成功率达到约定阈值。
- 不存在 Mongo 成功但 PostgreSQL 永久失败且未补偿的记录。
- 不存在 PostgreSQL 成功但 Mongo 用户可见结果失败的未解释记录。
- 审计事件两边可按 trace id 对齐。
- read model 可被 outbox 事件正确触发重建。

### 回滚

- 关闭双写开关，保持旧 Python + App Mongo 为主路径。
- 对 PostgreSQL 已写入但未采纳为事实源的数据做差异标记，不直接删除。
- 对 Mongo 成功、PostgreSQL 失败的记录，修复后通过补偿脚本重放。
- 保留差异报告和审计记录。

## 阶段 4：读全量切换

### 进入条件

- 双写连续通过约定验证窗口。
- 全部目标只读 API 差异已清零或有业务批准解释。
- 回滚路由、值班人、告警和值班群已确认。

### 执行步骤

1. 按菜单或 API 组逐步把读流量切到 Axum。
2. 切换顺序建议：
   - 健康检查和设置读取。
   - 文件元数据和导入历史。
   - 单月工作台 read model。
   - 全局搜索。
   - 成本统计和税金抵扣。
   - 核销相关写接口。
   - 数据重置和高风险运维操作。
3. 每切一个 API 组，观察一个稳定窗口再继续。
4. 保持旧 Python 可处理读回滚。

### 验证

- 用户可见页面样本一致。
- API 5xx、P95/P99、PostgreSQL pool、NATS backlog、read model stale、OA sync lag 均在阈值内。
- 业务指标没有异常跳变：待核销金额、异常单数量、导入失败数。

### 回滚

将异常 API 组路由切回旧 Python。保留 Axum 读日志、差异样本、慢查询和相关 read model 版本。

## 阶段 5：停止旧写

### 进入条件

- 读全量切换稳定通过约定窗口。
- 双写差异为 0 或已全部补偿。
- PostgreSQL 备份和恢复状态健康。
- 业务确认 PostgreSQL 可作为新事实源。

### 执行步骤

1. 将旧 Python 写路径改为只读、拒绝或转发到新路径，具体方式以已评审实现为准。
2. 禁止旧系统继续产生新的 App Mongo 业务事实。
3. 创建 App Mongo 冻结点备份。
4. 记录冻结时间、旧系统版本、Mongo collection count、PostgreSQL 对账摘要。
5. 保留旧 Python 读回滚入口到回滚窗口结束。

### 验证

- 新写操作只进入 PostgreSQL 事实表。
- App Mongo collection count 在冻结后不再因业务写入变化。
- PostgreSQL 审计和 outbox 正常。
- read model 可正常增量重建。

### 回滚

如果仍在允许回滚窗口内且 PostgreSQL 尚未独占事实源，可以按变更单决定重新启用旧写并补偿差异。若 PostgreSQL 已成为事实源，不允许旧 Mongo 覆盖 PostgreSQL，只能按审计事件和差异报告执行补偿迁移。

## 阶段 6：收尾和归档

1. 归档迁移日志、差异报告、备份 ID、恢复演练记录和上线审批。
2. 保留 App Mongo 和 GridFS 归档到约定周期结束。
3. 标记旧 Python 后端为回滚窗口服务，不再承载主流量。
4. 删除迁移期兼容开关、旧路径和旧数据保留策略必须另起计划和审批。
5. 更新长期运维文档、架构图和告警看板。

## 差异报告模板

```text
report_id:
window_start:
window_end:
phase:
old_source: python_app_mongo
new_source: axum_postgresql
api_or_job:
sample_size:

counts:
  old:
  new:
  diff:

amounts:
  old_total:
  new_total:
  diff:

status_distribution:
  old:
  new:
  diff:

file_checksums:
  sampled:
  matched:
  mismatched:

read_model:
  scope:
  old_summary:
  new_summary:
  stale_seconds:

unexplained_differences:
  - trace_id:
    object_type:
    old_id:
    new_id:
    field:
    old_value_summary:
    new_value_summary:
    owner:
    status:

decision:
  continue_or_pause:
  approver:
  notes:
```

## 回滚命令模板

以下只作为模板，执行前必须替换为已审批的环境、路由和变更单参数；模板不包含 secret。

仓库内的 `deploy/rollback-route.sh` 和 `deploy/set-feature-flag.sh` 默认只执行 dry-run，并输出将要执行的 JSON 记录。即使传入 `--execute`，脚本也会在缺少 `FIN_OPS_CUTOVER_EXECUTE=1` 时拒绝执行。设置该环境变量只能发生在 P4-12 结论为 `GO`、用户明确授权生产切换、维护窗口和回滚路径均确认之后。

### 读路由回滚

```bash
# 将指定 API 组从 Axum 回旧 Python，具体命令以部署系统为准。
export CHANGE_ID="REPLACE_WITH_CHANGE_ID"
export ROUTE_GROUP="workbench-read"
export TARGET_BACKEND="python"

./deploy/rollback-route.sh \
  --change "$CHANGE_ID" \
  --route-group "$ROUTE_GROUP" \
  --target "$TARGET_BACKEND" \
  --dry-run
```

### 关闭影子读或双写

```bash
# 使用配置系统关闭迁移期开关，具体 key 以实现为准。
export CHANGE_ID="REPLACE_WITH_CHANGE_ID"

./deploy/set-feature-flag.sh \
  --change "$CHANGE_ID" \
  --flag "backend.shadow_read.enabled" \
  --value "false" \
  --dry-run

./deploy/set-feature-flag.sh \
  --change "$CHANGE_ID" \
  --flag "backend.dual_write.enabled" \
  --value "false" \
  --dry-run
```

### 重放 outbox 或差异补偿

```bash
# 只重放已验证的时间窗口和 job type；不得使用无边界全量重放。
export CHANGE_ID="REPLACE_WITH_CHANGE_ID"
export WINDOW_START="YYYY-MM-DDTHH:MM:SS+08:00"
export WINDOW_END="YYYY-MM-DDTHH:MM:SS+08:00"

./tools/replay-outbox \
  --change "$CHANGE_ID" \
  --from "$WINDOW_START" \
  --to "$WINDOW_END" \
  --job-type "read_model_rebuild"
```

### 文件恢复

```bash
# 优先从对象存储版本恢复；必要时从 GridFS 归档恢复到新对象 key。
export CHANGE_ID="REPLACE_WITH_CHANGE_ID"
export FILE_OBJECT_ID="REPLACE_WITH_FILE_OBJECT_ID"

./tools/restore-file-object \
  --change "$CHANGE_ID" \
  --file-object-id "$FILE_OBJECT_ID" \
  --source "object-store-version"
```

## 紧急停止条件

出现以下任一情况，立即暂停推进并进入回滚或故障处理：

- PostgreSQL 不可用、连接池耗尽或发生 deadlock 告警。
- App Mongo、PostgreSQL 或 MinIO/S3 备份状态异常。
- 双写出现金额、状态、核销关系的无法解释差异。
- 文件 checksum mismatch。
- read model stale 超过 P1 阈值并影响页面。
- worker dead letter 出现且影响导入、OA 同步或 read model。
- 审计日志缺失或幂等失效。
- 需要操作 OA 源数据库才能继续。

## 切换记录模板

```text
change_id:
phase:
started_at:
ended_at:
operator:
approver:
old_backend_version:
new_backend_version:
worker_version:
web_version:
mongo_backup_id:
postgres_backup_id:
feature_flags:
routes_changed:
metrics_snapshot_before:
metrics_snapshot_after:
alerts:
differences:
rollback_ready:
decision:
notes:
```

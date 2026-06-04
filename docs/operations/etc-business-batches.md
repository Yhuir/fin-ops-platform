# ETC 业务批次上线与运维检查

本文档覆盖 ETC 业务批次、OA 自动检测和历史迁移的部署、回滚、后台恢复和 smoke 检查。产品事实源见 [`../product-specs/imports-and-etc.md`](../product-specs/imports-and-etc.md)，API 契约见 [`../dev/api-contracts.md`](../dev/api-contracts.md)。

## 发布前检查

- 已备份 App Mongo 数据库、GridFS、部署环境变量、后端版本、前端构建产物和 Nginx 配置。
- `business-batches` 功能开关默认关闭，迁移和索引检查通过后再打开。
- App Mongo detailed collections 已创建 `etc_business_batches` 集合，且满足同一 `task_id` 只有一个 active 批次的存储层约束。
- 如果 Mongo 支持 partial unique index，检查 `unique(task_id, active=true)` 已存在；如果不支持，检查 `task_active_key` 唯一索引已存在，且非 active 批次不会保留该 key。
- 生产部署不得使用本地 state 文件模式承载该功能；如启动参数声明 `FINOPS_STORAGE_MODE=local_state`，只能用于单进程本地开发。
- OA Mongo 只读账号可查询支付申请表单，具备 form id、processStatus、createdAt 的可用索引或等价查询路径。
- 后端配置了 OA 检测查询超时，避免后台任务因慢查询阻塞。

## 迁移 dry-run

正式迁移前必须运行 dry-run。dry-run 至少输出：

- 将创建的业务批次数。
- 将绑定的 `EtcImportBatch`、`EtcBatch` 和发票数。
- 发现的 active 冲突数和明细。
- 修复的脏引用数。
- 跳过的孤儿批次和原因。
- 迁移前后校验数量：任务数、import batch 数、submission batch 数、invoice 数、`current_batch_id` 占用数、submitted 发票数。

dry-run 报告保存到部署日志或 `docs/operations/` 下的发布记录。报告不得改写产品事实源文档。

正式迁移要求：

- 迁移脚本必须幂等，重复运行不得创建第二个业务批次，不得重复追加同一 `import_batch_id`。
- `business_batch_id` 使用确定性映射，优先由 `task_id` 映射；无任务的孤儿批次由 `submission_batch_id` 映射。
- 发现多个 active 批次时，只标记 `migration_conflict`，不得自动选择 winner。
- 迁移失败时保持功能开关关闭，恢复备份或保留现场后回滚应用版本。

## 发布后 smoke

发布后至少检查：

- `GET /health` 返回健康。
- `GET /api/session/me` 返回 JSON，不返回 HTML。
- `GET /api/etc/business-batches` 返回 JSON envelope；无权限时返回结构化 403 JSON。
- `POST /api/etc/business-batches`、`POST /api/etc/business-batches/{id}/etc-import/preview`、`POST /api/etc/business-batches/{id}/etc-import/confirm`、`POST /api/etc/business-batches/{id}/oa-status/refresh` 和 `DELETE /api/etc/business-batches/{id}` 的代理路径都命中后端。
- Nginx `/api/` 与 `/fin-ops-api/` 下的 GET、POST、DELETE 都不返回 HTML 502、官网 HTML 或 React shell。
- 旧 `/api/etc/batches` 在过渡期仍可读取，且不会创建第二个用户可见业务批次。
- 生产日志可按 `requestId`、`businessBatchId`、`taskId`、`externalEtcBatchId` 和 `oaRowId` 检索。

可用 curl 检查响应类型：

```bash
curl -i https://<host>/fin-ops-api/api/etc/business-batches
curl -i -X POST https://<host>/fin-ops-api/api/etc/business-batches/<id>/oa-status/refresh
curl -i -X DELETE https://<host>/fin-ops-api/api/etc/business-batches/<id>
```

响应 `Content-Type` 必须是 JSON 类型。出现 `text/html`、`502 Bad Gateway` HTML、公司官网 HTML 或前端 `index.html` 都视为 Nginx/API smoke 失败。

## OA 检测后台恢复

后端重启后必须恢复以下状态的检测任务：

- `oa_submission_detecting`
- `oa_detection_unavailable`

恢复规则：

- 按 `oa_detection_next_run_at` 调度，不立即无界扫描历史数据。
- 每个 `businessBatchId` 同一时刻只能有一个运行中检测任务。
- `oa_detection_timeout` 不再自动高频轮询；用户点击刷新检测且未超过 `oa_detection_final_retry_until` 时，只触发一次即时检测。
- Mongo 查询超时或权限失败进入 `oa_detection_unavailable`，写 `oa_detection_error` 和审计。
- 后台推进状态时必须校验批次 `version`，不能覆盖用户刚执行的人工兜底或撤销草稿。

运维排查时优先按 `businessBatchId` 查后台任务、审计事件和 OA Mongo 查询日志，再按 `requestId` 查单次 API 调用。

## 回滚

第一阶段不删除 `EtcImportBatch` 和 `EtcBatch`，回滚策略是关闭新业务批次读写入口并恢复旧 API 展示。

回滚顺序：

1. 关闭 `business-batches` 写开关，阻止新增业务批次、补充导入、创建 OA 草稿和人工兜底。
2. 停止或降级 OA 自动检测后台任务，避免继续推进状态。
3. 回滚前端到旧 ETC 页面或隐藏新入口。
4. 回滚后端版本或配置到旧 `/api/etc/batches*` 兼容路径。
5. 如迁移已写入错误数据，先恢复迁移前备份；无法立即恢复时保留 `migration_conflict` 状态并由管理员人工修复。
6. 确认 Nginx `/api/` 与 `/fin-ops-api/` 仍返回 JSON，而不是 HTML 502。

不得只回滚后端而保留新前端入口；否则用户会继续调用已关闭的 `business-batches` 写接口。

## 告警建议

生产至少关注：

- `active_business_batch_exists` 或唯一索引冲突持续出现。
- `oa_detection_unavailable` 连续失败。
- `oa_detection_conflict` 数量异常增加。
- 后台检测任务重启后未恢复 pending 批次。
- `/api/etc/business-batches*` 出现 HTML 响应或 Nginx 502。
- 迁移报告中 `migration_conflict`、脏引用修复或跳过数量超过预期。

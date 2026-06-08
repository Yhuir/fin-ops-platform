# ETC 业务批次上线与运维检查

本文档覆盖 ETC 业务批次、OA 草稿人工确认和历史迁移的部署、回滚、后台恢复和 smoke 检查。产品事实源见 [`../product-specs/imports-and-etc.md`](../product-specs/imports-and-etc.md)，API 契约见 [`../dev/api-contracts.md`](../dev/api-contracts.md)。

## 发布前检查

- 已备份 App Mongo 数据库、GridFS、部署环境变量、后端版本、前端构建产物和 Nginx 配置。
- `business-batches` 功能开关默认关闭，迁移和索引检查通过后再打开。
- App Mongo detailed collections 已创建 `etc_business_batches` 集合，且满足同一 `task_id` 只有一个 active 批次的存储层约束。
- 如果 Mongo 支持 partial unique index，检查 `unique(task_id, active=true)` 已存在；如果不支持，检查 `task_active_key` 唯一索引已存在，且非 active 批次不会保留该 key。
- 生产部署不得使用本地 state 文件模式承载该功能；如启动参数声明 `FINOPS_STORAGE_MODE=local_state`，只能用于单进程本地开发。
- OA 检测 adapter 和 `/oa-status/refresh` 仅作为 legacy 兼容能力保留；ETC 页面创建 OA 草稿后由用户手动确认“已提交”或“未提交”。
- 后端不得在创建 OA 草稿或应用启动恢复时自动为 ETC 业务批次入队 `etc_business.oa_detection.refresh`。

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
- `POST /api/etc/business-batches`、`POST /api/etc/business-batches/{id}/etc-import/preview`、`POST /api/etc/business-batches/{id}/etc-import/confirm`、`POST /api/etc/business-batches/{id}/manual-oa-status` 和 `DELETE /api/etc/business-batches/{id}` 的代理路径都命中后端。
- Nginx `/api/` 与 `/fin-ops-api/` 下的 GET、POST、DELETE 都不返回 HTML 502、官网 HTML 或 React shell。
- 旧 `/api/etc/batches` 在过渡期仍可读取，且不会创建第二个用户可见业务批次。
- 生产日志可按 `requestId`、`businessBatchId`、`taskId`、`externalEtcBatchId` 和 `oaRowId` 检索。

可用 curl 检查响应类型：

```bash
curl -i https://<host>/fin-ops-api/api/etc/business-batches
curl -i -X POST https://<host>/fin-ops-api/api/etc/business-batches/<id>/manual-oa-status
curl -i -X DELETE https://<host>/fin-ops-api/api/etc/business-batches/<id>
```

响应 `Content-Type` 必须是 JSON 类型。出现 `text/html`、`502 Bad Gateway` HTML、公司官网 HTML 或前端 `index.html` 都视为 Nginx/API smoke 失败。

## OA 草稿人工确认

创建 OA 草稿后，ETC 页面只提供人工确认：

- `submitted`：确认 OA 草稿已提交，业务批次进入已提交口径。
- `not_submitted`：确认 OA 草稿未提交，释放本地 ETC 发票占用，批次回到未提交链路。

运行规则：

- `manual-oa-status` 必须校验批次 `version`，不能覆盖并发更新。
- 人工确认必须写入审计原因；前端默认原因是“用户确认 OA 草稿已提交。”或“用户确认 OA 草稿未提交。”。
- 历史 `oa_detection_timeout`、`oa_detection_conflict`、`oa_detection_unavailable` 批次在页面显示为待人工确认，可继续通过 manual status API 闭环。
- 后端 legacy `/oa-status/refresh` 和 worker 代码不得由 ETC 页面、草稿创建或启动恢复自动触发；如运维手动调用 legacy refresh，必须确认不会覆盖用户刚执行的人工确认。

运维排查时优先按 `businessBatchId` 查业务批次状态、审计事件、提交批次和 manual status API `requestId`。

## 回滚

第一阶段不删除 `EtcImportBatch` 和 `EtcBatch`，回滚策略是关闭新业务批次读写入口并恢复旧 API 展示。

回滚顺序：

1. 关闭 `business-batches` 写开关，阻止新增业务批次、补充导入、创建 OA 草稿和人工兜底。
2. 确认 ETC 页面没有自动检测入口，legacy OA 检测后台任务不会由草稿创建或启动恢复触发。
3. 回滚前端到旧 ETC 页面或隐藏新入口。
4. 回滚后端版本或配置到旧 `/api/etc/batches*` 兼容路径。
5. 如迁移已写入错误数据，先恢复迁移前备份；无法立即恢复时保留 `migration_conflict` 状态并由管理员人工修复。
6. 确认 Nginx `/api/` 与 `/fin-ops-api/` 仍返回 JSON，而不是 HTML 502。

不得只回滚后端而保留新前端入口；否则用户会继续调用已关闭的 `business-batches` 写接口。

## 告警建议

生产至少关注：

- `active_business_batch_exists` 或唯一索引冲突持续出现。
- `manual-oa-status` 状态冲突或 version conflict 持续出现。
- `oa_detection_unavailable`、`oa_detection_conflict` 历史兼容状态数量异常增加。
- 后台检测任务被意外入队并推进 ETC 业务批次。
- `/api/etc/business-batches*` 出现 HTML 响应或 Nginx 502。
- 迁移报告中 `migration_conflict`、脏引用修复或跳过数量超过预期。

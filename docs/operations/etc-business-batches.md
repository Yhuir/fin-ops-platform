# ETC 业务批次上线与运维检查

本文档覆盖 ETC 业务批次、OA 草稿人工确认和历史迁移的部署、回滚、后台恢复和 smoke 检查。产品事实源见 [`../product-specs/imports-and-etc.md`](../product-specs/imports-and-etc.md)，API 契约见 [`../dev/api-contracts.md`](../dev/api-contracts.md)。

## 发布前检查

- 已备份 App Mongo 数据库、GridFS、部署环境变量、后端版本、前端构建产物和 Nginx 配置。
- `business-batches` 功能开关默认关闭，迁移和索引检查通过后再打开。
- App Mongo detailed collections 已创建 `etc_business_batches` 集合，且满足同一 `task_id` 只有一个 active 批次的存储层约束。
- 如果 Mongo 支持 partial unique index，检查 `unique(task_id, active=true)` 已存在；如果不支持，检查 `task_active_key` 唯一索引已存在，且非 active 批次不会保留该 key。
- 生产部署不得使用本地 state 文件模式承载该功能；如启动参数声明 `FINOPS_STORAGE_MODE=local_state`，只能用于单进程本地开发。
- ETC 专用 OA 自动检测链路已移除；ETC 页面创建 OA 草稿后由用户手动确认“已提交”或“未提交”。
- 后端不得提供 ETC `oa-status/refresh` 入口，不得注册 ETC OA 检测 worker，不得在创建 OA 草稿或应用启动恢复时自动为 ETC 业务批次入队 `etc_business.oa_detection.refresh`。
- 如果旧生产环境曾启用 `fin-ops-worker@etc-business-oa-detection.service`，发布后必须一次性 `disable --now` 该 unit；仓库部署样例不再包含 `etc-business-oa-detection` worker 或 `etc_business.oa_detection.refresh` dispatcher 事件。
- 对象存储配置必须可供 PostgreSQL 文件写入链路识别 backend 和 bucket；上传信用卡账单、票根网文件和业务批次源文件前，先确认对象存储健康检查、bucket 权限和服务环境变量一致。
- `0065_invoice_canonical_identity_fingerprint_invariant.sql` 必须随发布执行，用于清理历史 canonical invoice 中同时存在强 `source_unique_key` 和弱 `data_fingerprint` 的列值与 raw payload；否则旧快照仍可能在 ETC ZIP 导入或 OA 草稿创建后的本地持久化阶段触发 `invoices_data_fingerprint_uidx`。

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

历史已配对 ETC 批次转入新业务批次模型时使用 `backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py`：

- spec 必须显式提供 `business_batch_id`、`task_id`、旧 `submission_batch_id`、外部 ETC 批次号、active relation `case_id`、上报金额和 scope month。
- dry-run 只校验旧提交批次、active relation 和金额差额；execute 必须通过 `HistoricalEtcBusinessBatchMigrationService` 调用 `EtcService` 和 pair relation service，不允许直接写 read model。
- 差额批次保留旧 OA/银行事实源，差额原因写入业务批次 `amount_breakdown`，不为了凑金额跨批次抢占其他批次发票。
- 迁移后必须只读验证：ETC 管理 submitted bucket 可见业务批次；关联台 paired 区可展开 ETC 明细；同一 `external_etc_batch_id` 不再出现在 open 区。
- `0062_workbench_relation_etc_external_batch_idx.sql` 是 active relation ETC 外部批次索引，应由 schema owner/migrator 在部署迁移阶段执行；运行时 app 账号无权创建该索引时，不得用 runtime 账号手工改 owner。

## 发布后 smoke

发布后至少检查：

- `GET /health` 返回健康。
- `GET /api/session/me` 返回 JSON，不返回 HTML。
- `GET /api/etc/business-batches` 返回 JSON envelope；无权限时返回结构化 403 JSON。
- `POST /api/etc/business-batches` 可省略 `taskId`，成功响应必须返回已绑定 `taskId` 和 `title` 的 business batch；随后 `GET /api/etc/business-batches?status=active` 能看到该批次，且 `/api/etc/reconciliation-tasks` 中的 task-only 记录不得额外混入 ETC 左侧批次列表。
- `POST /api/etc/business-batches`、`PATCH /api/etc/business-batches/{id}`、`POST /api/etc/business-batches/{id}/etc-import/preview`、`POST /api/etc/business-batches/{id}/etc-import/confirm`、`POST /api/etc/business-batches/{id}/manual-oa-status` 和 `DELETE /api/etc/business-batches/{id}` 的代理路径都命中后端。
- Nginx `/api/` 与 `/fin-ops-api/` 下的 GET、POST、DELETE 都不返回 HTML 502、官网 HTML 或 React shell。
- 旧 `/api/etc/batches` 和 `/api/etc/invoices/revoke-submitted` 已删除；任何探针、脚本或前端回滚都不得依赖这些兼容/回退入口。
- 生产日志可按 `requestId`、`businessBatchId`、`taskId`、`externalEtcBatchId` 和 `oaRowId` 检索。

可用 curl 检查响应类型：

```bash
curl -i https://<host>/fin-ops-api/api/etc/business-batches
curl -i -X PATCH https://<host>/fin-ops-api/api/etc/business-batches/<id> -H 'Content-Type: application/json' --data '{"title":"ETC smoke batch","expectedVersion":1}'
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
- 旧版本留下的 `oa_submission_detecting`、`oa_detection_timeout`、`oa_detection_conflict`、`oa_detection_unavailable` 批次由迁移归并为 `oa_confirmation_pending`，继续通过 manual status API 闭环。
- 后端不保留 ETC 专用检测 refresh、worker 或 detector adapter；排查时不得再通过检测接口推进 ETC 业务批次。

运维排查时优先按 `businessBatchId` 查业务批次状态、审计事件、提交批次和 manual status API `requestId`。

## 业务批次本地删除

ETC 批次删除是本地清理操作，不是 OA 撤销。删除入口包括：

- `DELETE /api/etc/business-batches/{id}`：删除用户可见业务批次。
- `DELETE /api/etc/reconciliation-tasks/{id}`：当任务绑定业务批次时，先委托同一套业务批次删除服务，再删除本地任务上传记录。

运行规则：

- 请求必须携带当前 `expectedVersion`；前端必须显示二次确认框。`expectedVersion` 只用于并发保护，不用于流程状态阻塞。
- 不因已确认对账、已创建 OA 草稿、已人工确认提交、`submitted_confirmed` 或 `closed` 状态阻塞删除。
- 未提交批次删除会清理本地导入批次、ETC metadata/PDF/XML 附件关系；不会创建或删除统一发票池中的正式发票。
- 已提交批次删除会将业务批次标记为 `deleted` 并写入 `submitted_business_batch_reset` 审计事件；绑定的 ETC metadata 恢复为 `unsubmitted`，`current_batch_id` 清空，已存在 canonical invoice 的 ETC 提交标记会被释放，关联台 open 区不再生成该批次的 `etc_invoice_summary`。
- 如果 `etc_invoice_summary` 已经参与 active relation，删除批次时取消包含该 summary row 的 active relation，记录 `etc_summary_unmerged` 历史；取消后不得恢复旧 OA+银行流水二栏 active relation，OA 和银行流水各自回到未配对。
- 真实 OA 草稿、OA 流程、已提交 OA 事实不删除、不撤销；若存在绑定 ETC 对账任务，两个删除入口都会删除本地任务和本地上传元数据。
- 删除后 submitted bucket 不再显示该业务批次；只有原本已存在于统一发票池的发票才会回到普通发票视图，等待未来 OA 和银行流水按普通三栏配对规则闭环。

排查时如果用户反馈“删除已提交批次后 1673 汇总仍存在”，优先检查 active relation 是否仍包含 summary row、ETC metadata 是否仍为 `submitted/current_batch_id` 绑定状态、已存在 canonical invoice 是否仍为 `hidden_after_etc_submission` 或 `etc_submission_status=submitted`，再重跑对应 Workbench read model refresh。

## Orphan task 排查与清理

如果刷新、重新部署后 ETC 未提交列表出现多条“新建ETC批次”，先确认这些记录是否是没有 active business batch 绑定的历史 reconciliation task，不要直接 SQL 删除：

```bash
curl -sS -H 'Accept: application/json' 'https://<host>/fin-ops-api/api/etc/business-batches?status=active&page=1&page_size=500'
curl -sS -H 'Accept: application/json' 'https://<host>/fin-ops-api/api/etc/reconciliation-tasks'
```

只读 SQL 核对 orphan task：

```sql
select t.task_id, t.status, t.version, t.created_at, t.updated_at,
       b.business_batch_id, b.status as business_batch_status
from app.etc_reconciliation_tasks t
left join app.etc_business_batches b
  on b.task_id = t.task_id and b.status <> 'deleted'
where t.status <> 'deleted'
  and b.business_batch_id is null
order by t.created_at desc, t.task_id;
```

清理必须使用现有工具逐个 task id 先 dry-run，再 execute；该工具复用 service 删除边界，会写入 deleted tombstone 并清理本地 source/import 关系，不允许绕过 service 直接改表：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.cleanup_orphan_etc_reconciliation_tasks --task-id ETC-RECON-000001
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.cleanup_orphan_etc_reconciliation_tasks --task-id ETC-RECON-000001 --execute --reason cleanup_orphan_etc_task_after_business_batch_delete
```

## 回滚

第一阶段不删除 `EtcImportBatch` 和 `EtcBatch`，回滚策略是关闭新业务批次读写入口并恢复旧 API 展示。

回滚顺序：

1. 关闭 `business-batches` 写开关，阻止新增业务批次、补充导入、创建 OA 草稿和人工兜底。
2. 确认 ETC 页面没有自动检测入口，后端没有 ETC OA 检测后台任务、检测 adapter 或 refresh API。
3. 回滚前端到旧 ETC 页面或隐藏新入口。
4. 回滚后端版本时仍保持 `/api/etc/business-batches*` 主链路；不要恢复旧 `/api/etc/batches*` 兼容路径或 `/api/etc/invoices/revoke-submitted` 回退入口。
5. 如迁移已写入错误数据，先恢复迁移前备份；无法立即恢复时保留 `migration_conflict` 状态并由管理员人工修复。
6. 确认 Nginx `/api/` 与 `/fin-ops-api/` 仍返回 JSON，而不是 HTML 502。

不得只回滚后端而保留新前端入口；否则用户会继续调用已关闭的 `business-batches` 写接口。

## 告警建议

生产至少关注：

- `active_business_batch_exists` 或唯一索引冲突持续出现。
- `manual-oa-status` 状态冲突或 version conflict 持续出现。
- `oa_confirmation_pending` 批次长期无人确认，或旧检测状态迁移后仍有新增记录。
- 日志中出现 ETC `oa-status/refresh`、`etc_business.oa_detection.refresh`、`/api/etc/invoices/revoke-submitted` 或 detector adapter 调用痕迹。
- `/api/etc/business-batches*` 出现 HTML 响应或 Nginx 502。
- 上传信用卡账单、票根网或业务批次源文件返回 `reconciliation_file_storage_unavailable`，或后端日志出现 `ObjectStorageWriteError`。
- 迁移报告中 `migration_conflict`、脏引用修复或跳过数量超过预期。

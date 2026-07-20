# ETC 业务批次上线与运维检查

本文档覆盖 ETC 业务批次、OA 草稿人工确认和历史迁移的部署、回滚、后台恢复和 smoke 检查。产品事实源见 [`../product-specs/imports-and-etc.md`](../product-specs/imports-and-etc.md)，API 契约见 [`../dev/api-contracts.md`](../dev/api-contracts.md)。

## 发布前检查

- 已备份 App Mongo 数据库、GridFS、部署环境变量、后端版本、前端构建产物和 Nginx 配置。
- `business-batches` 功能开关默认关闭，迁移和索引检查通过后再打开。
- App Mongo detailed collections 已创建 `etc_business_batches` 集合，且满足同一 `task_id` 只有一个 active 批次的存储层约束。
- 如果 Mongo 支持 partial unique index，检查 `unique(task_id, active=true)` 已存在；如果不支持，检查 `task_active_key` 唯一索引已存在，且非 active 批次不会保留该 key。
- 生产部署不得使用本地 state 文件模式承载该功能；如启动参数声明 `FINOPS_STORAGE_MODE=local_state`，只能用于单进程本地开发。
- ETC 专用 OA 自动检测链路已移除；ETC 页面创建 OA 草稿后由用户手动确认“已提交”或“未提交”。
- OA 草稿创建请求必须携带稳定 idempotency key；外部 OA I/O 不得持 ETC 业务锁。发布前确认管理员 recovery route 受权限保护，禁止对未知结果直接重试或手工 SQL 改状态。
- 后端不得提供 ETC `oa-status/refresh` 入口，不得注册 ETC OA 检测 worker，不得在创建 OA 草稿或应用启动恢复时自动为 ETC 业务批次入队 `etc_business.oa_detection.refresh`。
- 如果旧生产环境曾启用 `fin-ops-worker@etc-business-oa-detection.service`，发布后必须一次性 `disable --now` 该 unit；仓库部署样例不再包含 `etc-business-oa-detection` worker 或 `etc_business.oa_detection.refresh` dispatcher 事件。
- 对象存储配置必须可供 PostgreSQL 文件写入链路识别 backend 和 bucket；上传信用卡账单、票根网文件和业务批次源文件前，先确认对象存储健康检查、bucket 权限和服务环境变量一致。
- `0065_invoice_canonical_identity_fingerprint_invariant.sql` 必须随发布执行，用于清理历史 canonical invoice 中同时存在强 `source_unique_key` 和弱 `data_fingerprint` 的列值与 raw payload；否则旧快照仍可能在 ETC ZIP 导入或 OA 草稿创建后的本地持久化阶段触发 `invoices_data_fingerprint_uidx`。
- `0103_etc_reconciliation_task_timestamps.sql` 必须随发布执行，用正式 task 行的 typed `created_at/updated_at` 补齐 Phase 19 历史任务 payload 时间戳；该迁移幂等，不能改写 task 状态、版本、scope 或 typed 时间列。
- `0116_workbench_etc_relation_enrichment_hot_path.sql` 必须随发布执行，为 completed OA 精确 ETC marker、submitted business batch external identity/scope 和 active relation `etc_batch_link` 提供窄索引；它不改业务数据，也不引入新表或唯一性猜测。
- `0117_workbench_matching_idempotency_runtime_grant.sql` 只授予 `fin_ops_app_runtime` 对既有 Workbench 幂等表的 `select/insert/update`，使 matching worker 能通过正式 relation command/UoW 提交 ETC enrichment；不授予 delete，也不扩大其他表或页面权限。

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

旧 historical business batch migration 与 existing batch link CLI 已删除。已注册的 submitted ETC 业务批次通过常驻 Workbench matching worker 自动收敛：completed OA 的精确 `etc_batch_id` 唯一命中批次且 OA 已有或同轮创建正式关系时，在同一关系 UoW 内写入 `etc_batch_link`。发布后必须由关联台 Page Audit 证明 marker 一致、external batch owner 唯一、matching/read-model queue drained；不得再运行旧 CLI 或手工写 relation metadata。

## 发布后 smoke

发布后至少检查：

- `GET /health` 返回健康。
- `GET /api/session/me` 返回 JSON，不返回 HTML。
- `GET /api/etc/business-batches` 返回 JSON envelope；无权限时返回结构化 403 JSON。
- 分别请求 `bucket=unsubmitted|staged|submitted`，确认三组互斥且 `counts` 与筛选后的实际集合一致；首屏不得再请求 full `GET /api/etc/reconciliation-tasks`，选择一个批次只读取一次精确 detail。
- `GET /api/etc/reconciliation-tasks` 与 `GET /api/etc/reconciliation-tasks/ready-for-import` 均返回 JSON，不得因历史任务和新任务混合排序返回 500；新建 business batch 后必须同时能读取单 task、任务列表和 ready task 列表。
- `POST /api/etc/business-batches` 可省略 `taskId`，成功响应必须返回已绑定 `taskId` 和 `title` 的 business batch；随后 `GET /api/etc/business-batches?status=active` 能看到该批次，且 `/api/etc/reconciliation-tasks` 中的 task-only 记录不得额外混入 ETC 左侧批次列表。
- `POST /api/etc/business-batches`、`PATCH /api/etc/business-batches/{id}`、`POST /api/etc/business-batches/{id}/etc-import/preview`、`POST /api/etc/business-batches/{id}/etc-import/confirm`、`POST /api/etc/business-batches/{id}/manual-oa-status` 和 `DELETE /api/etc/business-batches/{id}` 的代理路径都命中后端。
- 已创建 OA 草稿的授权批次调用 `GET /api/etc/business-batches/{id}/invoice-pdf` 返回 `application/pdf` 而不是 HTML/JSON；`X-ETC-Invoice-Count` 与 `X-PDF-Page-Count` 相等，保存后用 `pdfinfo` 核对页数。read-export 账号允许下载，未创建草稿返回结构化 409。
- Nginx `/api/` 与 `/fin-ops-api/` 下的 GET、POST、DELETE 都不返回 HTML 502、官网 HTML 或 React shell。
- 旧 `/api/etc/batches` 和 `/api/etc/invoices/revoke-submitted` 已删除；任何探针、脚本或前端回滚都不得依赖这些兼容/回退入口。
- 生产日志可按 `requestId`、`businessBatchId`、`taskId`、`externalEtcBatchId` 和 `oaRowId` 检索。
- 运行 ETC Page Audit：超过 15 分钟的 `oa_draft_creating`、缺 submission/idempotency/prepared audit、pending 缺 draft ID/URL/submission、bucket 错配或 not-submitted 仍占用提交资源时必须失败；Audit 只证明 PostgreSQL 内部事实，不证明 OA 外部真实状态。

可用 curl 检查响应类型：

```bash
curl -i https://<host>/fin-ops-api/api/etc/business-batches
curl -i -X PATCH https://<host>/fin-ops-api/api/etc/business-batches/<id> -H 'Content-Type: application/json' --data '{"title":"ETC smoke batch","expectedVersion":1}'
curl -fS -D /tmp/etc-invoice-pdf.headers -o /tmp/etc-invoice-pdf.pdf https://<host>/fin-ops-api/api/etc/business-batches/<oa-draft-batch-id>/invoice-pdf
pdfinfo /tmp/etc-invoice-pdf.pdf | grep '^Pages:'
curl -i -X POST https://<host>/fin-ops-api/api/etc/business-batches/<id>/manual-oa-status
curl -i -X DELETE https://<host>/fin-ops-api/api/etc/business-batches/<id>
```

JSON API 响应 `Content-Type` 必须是 JSON 类型；`invoice-pdf` 必须是 `application/pdf`。出现 `text/html`、`502 Bad Gateway` HTML、公司官网 HTML 或前端 `index.html` 都视为 Nginx/API smoke 失败。完成后删除 `/tmp/etc-invoice-pdf.*`，不得把真实发票留在共享目录或提交到仓库。

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

若批次长期停在 `oa_draft_creating`，先在 OA 侧按业务标识人工核实，禁止重新点击创建或直接改回 imported：

- 已存在唯一草稿：管理员调用 `POST /api/etc/business-batches/{id}/oa-draft/recover`，提供当前版本、原因、核实证据、完整 draft ID/URL。
- 已确认未创建：同一管理员入口提供当前版本、原因、核实证据和 `confirmedNotCreated=true`，批次进入明确失败后才允许新的用户 intent。
- 无法确认：保持 creating，Audit 继续失败并升级给 OA owner；不得用猜测结果换取绿色状态。

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

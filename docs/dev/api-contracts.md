# API 契约

## 契约原则

- API 返回字段应稳定，前端不能猜测不存在的字段。
- 写操作返回 affected rows/months，便于前端局部刷新。
- 高风险动作应有 preview 或 confirm 两段式接口。
- 后端错误应返回可展示的业务消息，不返回空 body 让前端猜测。
- HTML 响应视为部署或代理错误。

## 主要 API 分组

- `/api/session/*`：OA 会话和当前用户。
- `/api/workbench*`：关联工作台查询、详情、动作、异常、设置。
- `/imports/*`：导入预览、确认、模板、批次和文件会话。
- `/api/no-oa-bank-batches/*`：免 OA 批次。
- `/api/tax-offset*`：税金抵扣和已认证导入。
- `/api/cost-statistics*`：成本统计、下钻和导出。
- `/api/bank-details*`：银行明细和分类。
- `/api/background-jobs*`：后台任务。
- `/api/tasks/*`：PostgreSQL Worker task 状态查询。
- `/api/app-health*`：健康状态。
- `/health`、`/healthz`、`/readyz`、`/metrics`、`/api/app-metadata`：Axum 基础健康和元数据。

## 剩余未迁移合同冻结

`pending_contract` 和 `blocked_fact_source` route 的逐条生产级合同见 `docs/architecture/backend-refactor/remaining-api-contracts.md`。该文档冻结后续实现所需的 source contract、target tables、write command、audit/outbox event、read model invalidation、idempotency、permission、rollback 和 shadow fixture plan，但不改变 API inventory 状态，也不代表 route 已迁移或 shadow gate 已通过。

## 工作台 DTO

工作台 DTO 的详细结构见 `reconciliation-workbench-v2-data-contracts.md`。

## P3-09A 低风险只读 API

本批次只冻结和迁移健康检查、设置读取、session/me 和 app metadata 的只读契约，不迁移导入确认、工作台重查询、核销写操作、数据重置或 OA 源库访问。

### `GET /health`

用途：兼容旧 Python foundation health。Axum 版本不返回旧 demo seed 的真实计数；`seed_counts` 保留字段但值为 0，差异可解释为 Axum 不加载 Python demo seed。

成功响应字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `service` | string | 兼容旧值 `fin-ops-platform-api`。 |
| `version` | string | Axum crate version。 |
| `status` | string | `ready`。 |
| `entrypoints` | string[] | 当前 Axum 已暴露的低风险入口。 |
| `capabilities` | string[] | 当前 Axum 只读能力。 |
| `storage` | object | 目标存储说明，不暴露数据库 URI。 |
| `seed_counts` | object | 兼容旧字段；Axum 不加载 demo seed，默认 0。 |
| `module_boundaries` | object | 兼容旧字段，描述当前模块边界。 |

### `GET /healthz`、`GET /readyz`、`GET /metrics`

`/healthz` 只检查进程存活；`/readyz` 检查 PostgreSQL 必需依赖，并列出 Redis/NATS/S3 可选依赖配置状态；`/metrics` 返回 Prometheus 文本。三者属于 Axum foundation，不是旧 Python `/health` 的完全替代。

`/metrics` 默认不是公网开放接口。Axum 默认要求内部访问标识：`FIN_OPS_METRICS_INTERNAL_HEADER`（默认 `x-fin-ops-internal-request`）的值等于 `FIN_OPS_METRICS_INTERNAL_VALUE`（默认 `1`），或使用管理员 OA session 访问。仅在明确部署到受控内网或本地调试时才可设置 `METRICS_REQUIRE_AUTH=0`。

### Axum 鉴权、RBAC 和 CORS

除 `/health`、`/healthz`、`/readyz`、内部 `/metrics`、`/api/app-metadata` 和 `/api/session/me` 外，Axum business routes 默认要求 OA session。当前路由策略：

| 路由类型 | 要求 |
| --- | --- |
| 业务读接口（如 `/api/workbench*`、`/imports/*`） | `can_access_app = true`。 |
| 业务写接口（`POST` / `PUT` / `PATCH` / `DELETE`） | `can_access_app = true` 且 `can_mutate_data = true`。 |
| 管理类写接口（如 settings data reset） | `can_admin_access = true`。 |
| `/metrics` | 内部标识或管理员 session；默认不裸露。 |

OA token 来源按顺序支持 `Authorization: Bearer ...`、`X-OA-Token` 和同域 `Admin-Token` cookie。生产环境不得记录 token/cookie；审计与 outbox 只记录可信 actor、`actor_type` 和 `request_id`/`trace_id`。

OA identity adapter 未配置时，任何带 token 的受保护 route 必须返回 `503 oa_identity_unavailable`，不得伪造用户。当前 Axum 支持 `FIN_OPS_OA_IDENTITY_ADAPTER=trusted_headers`，用于可信反向代理或测试环境将 OA 解析结果注入 `x-fin-ops-oa-user-id`、`x-fin-ops-oa-username`、`x-fin-ops-oa-roles`、`x-fin-ops-oa-permissions` 等 header；公网部署必须在代理层保证这些 header 不可由外部客户端伪造。

CORS 不使用 permissive 模式。允许的来源由 `FIN_OPS_CORS_ALLOWED_ORIGINS` 逗号分隔配置；本地开发如需允许 `localhost` / `127.0.0.1` / `[::1]`，必须显式设置 `FIN_OPS_CORS_ALLOW_LOCALHOST=1`。

### `GET /api/app-metadata`

用途：返回 Axum API 元数据和本批次兼容的 Python 契约列表。

成功响应：

```json
{
  "service": "fin-ops-api",
  "version": "0.1.0",
  "api": "axum-postgresql",
  "compatible_python_contracts": ["/health", "/api/session/me", "/api/workbench/settings"],
  "readonly": true
}
```

### `GET /api/app-health`

用途：返回前端状态栏和运维页使用的 JSON 快照。`GET /api/app-health/stream` 是同一数据源的 SSE 包装，首批事件为 `app_health` 和 `heartbeat`。

数据来源：

- OA 同步状态：PostgreSQL `app.oa_sync_runs`、`app.oa_sync_watermarks`。
- 后台任务和 matching running/attention 状态：PostgreSQL `job.worker_tasks`。
- 工作台 stale/dirty scope：`read_model.workbench_snapshots.stale=true`。
- session：OA identity adapter 注入的 `AuthenticatedSession`。

成功响应保持旧前端主结构：

```json
{
  "version": 1,
  "status": "ok",
  "generated_at": "2026-05-17T00:00:00Z",
  "session": {"status": "authenticated", "allowed": true},
  "oa_sync": {"status": "synced", "last_synced_at": "2026-05-17T00:00:00Z"},
  "workbench_read_model": {
    "status": "ready",
    "dirty_scopes": [],
    "matching_dirty_scopes": [],
    "matching_running_scopes": [],
    "last_matching_error": null,
    "rebuild_job_ids": []
  },
  "background_jobs": {
    "active": 0,
    "queued": 0,
    "running": 0,
    "attention": 0,
    "primary_running": null,
    "primary_attention": null,
    "active_jobs": [],
    "attention_jobs": [],
    "jobs": []
  },
  "dependencies": {},
  "metrics": {},
  "alerts": {"active": [], "recent_recovered": []}
}
```

Axum 不回读 app Mongo 的 `app_health_alerts` 或 `workbench_matching_dirty_scopes`。当前 matching dirty scope 来自 stale workbench snapshots，matching running/failed 状态来自 `job.worker_tasks` 中 `task_type='workbench_matching'` 的任务。

### `GET /api/session/me`

旧 Python 成功响应字段保持冻结：

```json
{
  "user": {
    "user_id": "oa-user-id",
    "username": "oa-username",
    "nickname": "nickname",
    "display_name": "display name",
    "dept_id": null,
    "dept_name": null,
    "avatar": null
  },
  "roles": [],
  "permissions": [],
  "allowed": true,
  "access_tier": "admin",
  "can_access_app": true,
  "can_mutate_data": true,
  "can_admin_access": true
}
```

Axum 必须通过 OA identity adapter 解析身份并复用旧 Python 成功响应字段。为避免伪造身份：

| 场景 | HTTP | 响应 |
| --- | --- | --- |
| 缺少 Authorization | 401 | `{"error":"invalid_oa_session","message":"缺少 OA 登录态，请从 OA 系统进入。"}` |
| 提供 Authorization 但 Axum 未配置 OA identity adapter | 503 | `{"error":"oa_identity_unavailable","message":"OA 身份服务未配置。"}` |
| 已解析身份但无 `can_access_app` | 200 | `allowed=false`，业务 route 访问另行返回 403。 |

成功响应必须保持旧 Python 字段名，不返回 token、cookie、内部角色映射栈或 secret。

### `GET /api/workbench/settings`

用途：低风险设置读取契约。P3-09A Axum 返回兼容默认投影，不执行项目同步、不保存设置、不触发数据重置。

成功响应字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `projects.active` | array | 活跃项目设置。P3-09A 默认空数组。 |
| `projects.completed` | array | 已完成项目设置。P3-09A 默认空数组。 |
| `projects.completed_project_ids` | string[] | 已完成项目 ID。 |
| `bank_account_mappings` | array | 银行尾号映射。 |
| `access_control.allowed_usernames` | string[] | 兼容旧字段，默认包含旧默认管理员。 |
| `access_control.readonly_export_usernames` | string[] | 只读导出用户名。 |
| `access_control.admin_usernames` | string[] | 管理员用户名。 |
| `access_control.full_access_usernames` | string[] | 完整访问用户名。 |
| `workbench_column_layouts.oa/bank/invoice` | string[] | 工作台列布局默认值。 |
| `oa_retention.cutoff_date` | string | 默认 `2026-01-01`。 |
| `oa_import.form_types/statuses` | string[] | 默认 OA 导入筛选。 |
| `oa_import.available_form_types/available_statuses` | array | 可选项。 |
| `oa_invoice_offset.applicant_names` | string[] | OA 发票冲抵申请人默认值。 |

测试 fixture：`docs/dev/api-fixtures/low-risk-read-apis.json`。

## P3-09B 导入历史、文件元数据和 upload preflight

本批次只迁移导入历史、文件元数据和上传前置校验。Axum 只读 PostgreSQL `app.import_batches`、`app.import_files`、`app.file_objects`，不迁移导入预览、导入确认、重试、撤回或真实文件上传，不访问 OA 源库。

### `GET /imports/templates`

用途：冻结旧 Python `TEMPLATE_DEFINITIONS`，供前端选择导入模板。字段保持旧前端契约：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `templates[].template_code` | string | 模板代码，例如 `invoice_export`、`icbc_historydetail`。 |
| `templates[].label` | string | 中文展示名。 |
| `templates[].file_extensions` | string[] | 允许扩展名。 |
| `templates[].record_type` | string | `invoice` 或 `bank_transaction`。 |
| `templates[].allowed_batch_types` | string[] | 可用 batch type。 |
| `templates[].required_headers` | string[] | 旧 Python 解析器要求的表头。 |

### `GET /imports/batches`

用途：导入历史列表。该接口只返回 batch 元数据，不触发导入动作。

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `status` | string | 可选；`pending`、`completed`、`completed_with_errors`、`reverted`、`failed`。 |
| `batch_type` | string | 可选；必须是 `0002_imports_files.sql` 中定义的 batch type。 |
| `limit` | integer | 可选，默认 50，最大 200。 |
| `offset` | integer | 可选，默认 0。 |

成功响应：

```json
{
  "batches": [
    {
      "id": "0196f550-cc6e-7000-8000-000000000010",
      "batch_type": "bank_transaction",
      "source_type": "manual_upload",
      "source_name": "bank-may.xlsx",
      "status": "completed_with_errors",
      "row_count": 100,
      "success_count": 98,
      "error_count": 2,
      "duplicate_count": 0,
      "suspected_duplicate_count": 1,
      "updated_count": 0,
      "checksum": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "source_system": "app",
      "source_reference": null,
      "source_metadata": {},
      "legacy_session_id": "legacy-session-1",
      "legacy_import_id": null,
      "created_by": "YNSYLP005",
      "updated_by": "YNSYLP005",
      "confirmed_at": null,
      "reverted_at": null,
      "created_at": "2026-05-16T10:00:00Z",
      "updated_at": "2026-05-16T10:05:00Z"
    }
  ],
  "pagination": {
    "limit": 50,
    "offset": 0,
    "returned": 1
  }
}
```

### `GET /imports/batches/{batch_id}`

用途：查看单个导入批次和其关联文件。响应为：

- `batch`：同 `/imports/batches` 单项。
- `files[]`：来自 `app.import_files`，并嵌入可展示的 `file_object` 摘要。

`files[].parse_status` 使用迁移表定义的状态：`pending`、`queued`、`parsing`、`parsed`、`parsed_with_errors`、`failed`、`skipped`。该接口不返回原始文件内容、对象存储 secret、内部解析 traceback。

### `GET /imports/files/{file_id}`

用途：按 `app.import_files.id` 查询单个导入文件记录。响应：

```json
{
  "file": {
    "id": "0196f550-cc6e-7000-8000-000000000011",
    "batch_id": "0196f550-cc6e-7000-8000-000000000010",
    "file_object_id": "0196f550-cc6e-7000-8000-000000000012",
    "file_role": "source",
    "parse_status": "parsed_with_errors",
    "row_count": 100,
    "error_count": 2,
    "template_key": "icbc_historydetail",
    "checksum": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "source_file_id": null,
    "source_path": null,
    "source_metadata": {},
    "legacy_file_id": null,
    "legacy_gridfs_id": null,
    "file_object": {
      "id": "0196f550-cc6e-7000-8000-000000000012",
      "file_name": "bank-may.xlsx",
      "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "byte_size": 4096,
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "storage_provider": "minio",
      "bucket": "fin-ops-local",
      "object_key": "imports/uploads/sha256/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.xlsx",
      "object_version": null,
      "etag": null,
      "storage_class": null,
      "purpose": "import_source",
      "metadata": {}
    },
    "created_at": "2026-05-16T10:00:00Z",
    "updated_at": "2026-05-16T10:05:00Z"
  }
}
```

### `GET /api/files/objects/{file_object_id}`

用途：按 `app.file_objects.id` 查询对象存储元数据。只返回 bucket、object_key、hash、size、content type、legacy GridFS 映射等元数据，不返回下载签名、对象内容或 secret。

### `POST /imports/files/upload-preflight`

用途：上传前置校验和对象键规划。该接口不上传真实文件、不生成预签名 URL、不写 `app.file_objects`；真正对象写入仍需后续授权和服务端上传流程。

请求：

```json
{
  "file_name": "bank-may.xlsx",
  "byte_size": 4096,
  "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "purpose": "import_source"
}
```

校验规则：

- `file_name` 必须以 `.xls` 或 `.xlsx` 结尾。
- `byte_size` 必须大于 0，且不超过当前 API body limit 的默认值 25 MiB。
- `sha256` 必须是 64 位 hex；服务端按小写规范化。
- `purpose` 仅允许 `import_source`。
- 若 PostgreSQL 中已有相同 `sha256` 的 `app.file_objects`，响应 `duplicate=true`、`upload_required=false`，并返回 `existing_file_object`。

成功响应：

```json
{
  "accepted": true,
  "upload_required": true,
  "duplicate": false,
  "existing_file_object": null,
  "file": {
    "file_name": "bank-may.xlsx",
    "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "byte_size": 4096,
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "extension": ".xlsx",
    "purpose": "import_source"
  },
  "object": {
    "storage_provider": "minio_or_s3",
    "bucket": "configured-by-deployment",
    "object_key": "imports/uploads/sha256/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.xlsx",
    "upload_method": "server_mediated",
    "metadata": {
      "contract": "p3-09b-upload-preflight",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "source": "axum-preflight"
    }
  },
  "constraints": {
    "max_byte_size": 26214400,
    "allowed_extensions": [".xls", ".xlsx"],
    "allowed_content_types": [
      "application/vnd.ms-excel",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "application/octet-stream"
    ]
  }
}
```

错误响应：

| HTTP | code | 说明 |
| --- | --- | --- |
| 400 | `invalid_uuid` | 路径参数不是 UUID。 |
| 400 | `invalid_status` / `invalid_batch_type` | 列表筛选值不在迁移表约束中。 |
| 400 | `invalid_file_name` / `unsupported_file_extension` / `invalid_byte_size` / `invalid_sha256` / `unsupported_content_type` / `unsupported_purpose` | upload preflight 校验失败。 |
| 404 | `not_found` | batch、import file 或 file object 不存在。 |
| 503 | `database_unavailable` | PostgreSQL 读取失败；响应不暴露数据库错误栈。 |

测试 fixture：`docs/dev/api-fixtures/import-file-read-apis.json`。

## P3-09C 单月工作台 Read Model 和 Search 只读 API

本批次只迁移工作台单月 read model 命中路径、行详情读取和全局搜索读取。Axum 只读 PostgreSQL `read_model.workbench_snapshots`、`read_model.workbench_rows`、`read_model.search_index_rows`，不迁移核销确认/撤回、异常处理、忽略/取消忽略等写操作，不访问 OA 源库，不在请求路径全量重建 read model。

### `GET /api/workbench?month=YYYY-MM`

用途：读取单月工作台页面快照。该接口只接受单月，`month=all` 在 P3-09C 返回 400，避免请求路径实时拼 all-time 工作台。

成功响应保持旧前端主字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `month` | string | `YYYY-MM`。若 snapshot payload 缺失该字段，Axum 补入请求月份。 |
| `oa_status` | object | 兼容旧前端 OA 状态字段。 |
| `summary` | object | `oa_count`、`bank_count`、`invoice_count`、`paired_count`、`open_count`、`exception_count`。 |
| `invoice_inventory` | object | 可选；旧前端缺失时使用 0。 |
| `paired.groups` | array | 已配对/候选分组。 |
| `open.groups` | array | 未配对分组。 |
| `read_model_status` | object | Axum 增补的投影状态；前端旧 mapper 会忽略未知字段。 |

`read_model_status`：

```json
{
  "scope_key": "workbench:2026-05",
  "scope_type": "month",
  "scope_month": "2026-05-01",
  "schema_version": "2026-05-workbench-v1",
  "stale": false,
  "stale_reason": null,
  "source_versions": {
    "fact_updated_at": "2026-05-16T10:00:00Z"
  },
  "generated_at": "2026-05-16T10:05:00Z",
  "updated_at": "2026-05-16T10:05:00Z",
  "rebuild_task_id": null,
  "api_strategy": "return_ready_snapshot"
}
```

stale 策略：

- `stale=false`：返回 ready snapshot。
- `stale=true`：仍返回旧 snapshot，并通过 `read_model_status.stale/stale_reason/rebuild_task_id` 明确提示；本接口不在请求路径触发全量重建。
- 缺失 snapshot：返回 404 `read_model_not_found`，前端可显示缺失状态或引导后台重建。

### `GET /api/workbench/ignored?month=YYYY-MM`

用途：读取单月已忽略行，来自 `read_model.workbench_snapshots.ignored_rows`。成功响应：

```json
{
  "month": "2026-05",
  "rows": [],
  "read_model_status": {
    "scope_key": "workbench:2026-05",
    "stale": false,
    "api_strategy": "return_ready_snapshot"
  }
}
```

`rows[]` 保持旧 `ApiWorkbenchRow` 字段；响应不会查询 OA 源库，也不会在缺失时拼装 fallback。

### `GET /api/workbench/read-model/status?month=YYYY-MM`

用途：只返回单月工作台 read model 状态，供前端或运维面板判断 stale/missing/rebuild task。

成功响应：

```json
{
  "month": "2026-05",
  "read_model_status": {
    "scope_key": "workbench:2026-05",
    "scope_type": "month",
    "scope_month": "2026-05-01",
    "schema_version": "2026-05-workbench-v1",
    "stale": true,
    "stale_reason": "import.batch_confirmed",
    "source_versions": {},
    "generated_at": "2026-05-16T10:05:00Z",
    "updated_at": "2026-05-16T10:08:00Z",
    "rebuild_task_id": "0196f550-cc6e-7000-8000-000000000222",
    "api_strategy": "return_stale_snapshot_with_status"
  }
}
```

### `GET /api/workbench/rows/{row_id}?month=YYYY-MM`

用途：读取单个工作台行详情，优先带 `month` 命中单月分区。为了兼容旧前端，`month` 可省略；省略时只在 `read_model.workbench_rows` 内按 `row_id` 取最近月份一行，不访问 OA 源库、不扫描事实表、不重建 read model。

响应：

```json
{
  "row": {
    "id": "0196f550-cc6e-7000-8000-000000000111",
    "type": "bank",
    "counterparty_name": "供应商",
    "detail_fields": {},
    "read_model_status": {
      "scope_month": "2026-05-01",
      "row_id": "0196f550-cc6e-7000-8000-000000000111",
      "row_type": "bank",
      "zone_hint": "open",
      "stale": false,
      "stale_reason": null,
      "source_versions": {},
      "generated_at": "2026-05-16T10:05:00Z",
      "updated_at": "2026-05-16T10:05:00Z",
      "api_strategy": "return_ready_row"
    }
  }
}
```

响应会递归移除 `password/token/secret/credential/raw_file/raw_content/stack/traceback` 等敏感键。

### `GET /api/search`

用途：全局搜索只读 API。该接口唯一数据源是 `read_model.search_index_rows`，不跨 `app.bank_transactions`、`app.invoices`、`app.oa_*` 或工作台 snapshot 实时拼模糊搜索。

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `q` | string | 搜索关键词；空关键词返回空结果。 |
| `scope` | string | `all`、`oa`、`bank`、`invoice`；非法值回落 `all`。 |
| `month` | string | `YYYY-MM` 或 `all`；默认 `all`。`all` 只按 `limit` 返回最近月份优先的 bounded 结果。 |
| `project_name` | string | 可选项目名过滤。 |
| `status` | string | 可选；`paired`、`open`、`ignored`、`processed_exception`，映射到 `zone_hint`。 |
| `limit` | integer | 默认 20，最大 100。 |

成功响应保持旧 `SearchService` 分组字段：

```json
{
  "query": "供应商",
  "filters": {
    "scope": "all",
    "month": "2026-05",
    "project_name": null,
    "status": null,
    "limit": 20
  },
  "summary": {
    "total": 1,
    "oa": 0,
    "bank": 1,
    "invoice": 0
  },
  "oa_results": [],
  "bank_results": [
    {
      "row_id": "0196f550-cc6e-7000-8000-000000000111",
      "record_type": "bank",
      "month": "2026-05",
      "zone_hint": "open",
      "matched_field": "searchable_text",
      "title": "供应商",
      "primary_meta": "测试项目 / 100.00 / open",
      "secondary_meta": "测试项目 / P001 / 2026-05",
      "status_label": "未配对",
      "jump_target": {
        "route": "workbench",
        "month": "2026-05",
        "row_id": "0196f550-cc6e-7000-8000-000000000111",
        "record_type": "bank",
        "zone_hint": "open"
      },
      "entity_type": "bank_transaction",
      "entity_id": "0196f550-cc6e-7000-8000-000000000111",
      "source_kind": "app.bank_transactions",
      "stale": false,
      "stale_reason": null,
      "generated_at": "2026-05-16T10:05:00Z",
      "updated_at": "2026-05-16T10:05:00Z"
    }
  ],
  "invoice_results": [],
  "read_model_status": {
    "stale_result_count": 0,
    "api_strategy": "search_index_rows_only"
  }
}
```

索引和查询口径：

- 模糊匹配使用 `searchable_text ilike '%' || q || '%'`，由 `search_index_rows_text_trgm_idx` 的 pg_trgm/GIN 支撑。
- 单月查询加 `scope_month = to_date(:month || '-01')`，可定位分区。
- `scope` 过滤映射到 `entity_type` 集合；API 不回查事实表补字段。
- 搜索结果必须带 `jump_target`，用于前端跳转工作台月份和 row。

错误响应：

| HTTP | code | 说明 |
| --- | --- | --- |
| 400 | `invalid_month` | `month` 不是 `all` 或 `YYYY-MM`。 |
| 400 | `all_time_workbench_not_supported` | 工作台主读接口请求 `month=all`。 |
| 400 | `invalid_row_id` | `row_id` 不是 UUID。 |
| 400 | `invalid_status` | 搜索状态过滤值不合法。 |
| 404 | `read_model_not_found` | 对应 snapshot 或 row 不存在。 |
| 503 | `database_unavailable` | PostgreSQL 读取失败；响应不暴露 SQL 错误栈。 |

测试 fixture：`docs/dev/api-fixtures/workbench-search-read-apis.json`。

## P3-09D 核销、异常、免 OA 和 row override 写 API

本批次只迁移高风险工作台写操作的 PostgreSQL 事实写入路径。生产切换前必须先保留旧 Python 路径，并完成 dry-run 对账报告；不得在没有 dry-run 对账报告时迁移生产写路径。

适用接口：

| API | 用途 |
| --- | --- |
| `POST /api/workbench/actions/confirm-link` | 确认核销关系，写 `app.reconciliation_cases` 和 `app.reconciliation_case_rows`。 |
| `POST /api/workbench/actions/confirm-link/preview` | 核销确认 shadow 预检；只返回校验清单，不写生产事实。 |
| `POST /api/workbench/actions/withdraw-link` | 撤销核销关系，保留历史事实并将 active row binding 置为撤销。 |
| `POST /api/workbench/actions/withdraw-link/preview` | 撤销 shadow 预检；只返回将要锁定和回滚的事实范围，不写生产事实。 |
| `POST /api/workbench/actions/cancel-link` | 兼容旧前端的单行撤销入口，内部按 active case 撤销。 |
| `POST /api/workbench/actions/mark-exception` | 兼容 Python 工作台异常标记入口，落到结构化异常 case。 |
| `POST /api/workbench/actions/update-bank-exception` | 更新银行流水异常分类，落到结构化异常 case。 |
| `POST /api/workbench/actions/oa-bank-exception` | 处理 OA/银行异常，落到结构化异常 case。 |
| `POST /api/workbench/actions/confirm-personal-advance-repayment` | 确认个人暂借款还清，落到结构化异常/结清 case。 |
| `POST /api/workbench/actions/confirm-cash-pass-through` | 确认现金往来过账，在 active 核销 case 上写特殊处理 metadata。 |
| `POST /api/workbench/actions/confirm-cash-ticket-purchase` | 确认现金买票，在 active 核销 case 上写特殊处理 metadata。 |
| `POST /api/workbench/actions/cancel-cash-special` | 取消现金特殊处理，清理 active 核销 case 上的特殊处理 metadata。 |
| `POST /api/workbench/exception/apply` | 创建或处理结构化异常 case。 |
| `POST /api/workbench/actions/cancel-exception` | 撤回已处理异常 case。 |
| `POST /api/workbench/actions/ignore-row` | 写入 `workbench_row_overrides(ignore)` 和对应异常 case。 |
| `POST /api/workbench/actions/unignore-row` | 撤回 active ignore override。 |
| `POST /api/no-oa-bank-batches/{batch_id}/submit` | 提交免 OA 批次并写核销关系。 |
| `POST /api/no-oa-bank-batches/{batch_id}/withdraw` | 撤回免 OA 批次及其 active relation。 |
| `POST /api/no-oa-bank-batches/submit` | 批量提交免 OA 批次；每个 item 必须带独立幂等键和版本。 |

通用请求字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `idempotency_key` | string | 必填。服务端按 `operation + idempotency_key` 去重；同 key 不同 payload 返回 409。 |
| `actor` | string | 兼容字段。生产写入以 OA session 中的 `identity.username`（为空时用 `identity.user_id`）作为可信 actor；请求 body 缺省时由服务端注入，若 body 中存在且与 session actor 不一致，返回 403 `actor_mismatch`。不得写 token、cookie 或密码。 |
| `expected_version` | integer | 更新已有事实时必填，用于 optimistic lock。 |
| `note` / `comment` / `reason` | string | 可选。金额不一致、异常处理和撤销原因必须保留。 |

通用成功响应字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | boolean | 成功时为 `true`。 |
| `action` | string | 写操作名。 |
| `idempotent_replay` | boolean | 重复提交同一幂等键时为 `true`，不会重复写事实、audit 或 outbox。 |
| `affected_row_ids` | string[] | 前端局部刷新用 row id。 |
| `affected_months` | string[] | `YYYY-MM` 数组；用于局部刷新和 read model rebuild scope。 |
| `case_id` / `exception_case_id` / `batch_id` | string | 被写入或更新的核心事实 ID。 |
| `row_version` | integer | 更新后的事实版本；撤销和撤回下一次写入必须携带该版本。 |
| `rebuild_task_id` | string | 本事务创建的 `job.worker_tasks.id`。 |
| `outbox_event_id` | string | 本事务创建的 `job.outbox_events.id`。 |

事务与副作用要求：

- 每个写操作必须在同一个 PostgreSQL transaction 中写业务事实、`audit.events`、`job.worker_tasks`、`job.outbox_events` 和 `app.write_idempotency_records`。
- `audit.events.actor_id`、`job.worker_tasks.created_by` 和 outbox payload 的 `requested_by` 必须来自可信 session actor；`actor_type` / `requested_by_type` 记录为可信身份类型（如 `oa_user`），metadata/payload 记录 `request_id` / `trace_id`，不得记录 token/cookie。
- outbox payload 使用 `read_model.rebuild_requested`，`reason` 必须是 `reconciliation.confirmed`、`reconciliation.revoked`、`exception.updated` 或 `no_oa_batch.updated`。
- read model 和搜索索引只由 outbox/Worker 触发重建；写 API 不直接把 read model 当事实源更新。
- `row_version` 或 `expected_version` 不匹配时返回 409，不做覆盖。
- 金额不一致、active 关系冲突、状态冲突必须返回明确错误码，不得静默替换。
- `confirm-link`、`withdraw-link`、免 OA submit/withdraw 和现金特殊动作只能把 `read_model.workbench_rows` 作为 row id 定位和响应快照；写入前必须回查并锁定 `app.bank_transactions`、`app.invoices`、`app.oa_applications` / `app.oa_application_items` 或 active `app.reconciliation_case_rows`。
- 核销确认必须根据事实表剩余可核销金额计算 `reconciliation_cases.total_amount`、`difference_amount` 和每条 `reconciliation_case_rows.applied_amount`；银行流水/发票的 `written_off_amount` 与 `status` 同事务更新。撤销必须根据 active case rows 的 `applied_amount` 同事务回滚银行流水/发票的 `written_off_amount` 与 `status`。
- 免 OA 批次 submit 必须锁定 batch 与对应银行流水事实，校验 `expected_version`、状态流和 active binding 冲突后写核销 case；withdraw 必须锁定 batch 与 relation case，回滚 active rows 并写 audit/outbox。当前 PostgreSQL schema 的 batch 终态仍使用 `cancelled`，对外语义为 withdraw。
- 免 OA 列表和详情读 API（`GET /api/no-oa-bank-batches`、`GET /api/no-oa-bank-batches/{batch_id}`）不在本批写 API 迁移范围内；如要切换 no-OA 页面读路径，应单独进入后续 read API prompt。

### Python vs Axum shadow/dry-run 对比清单

生产切换前，对以下写 API 使用同一批请求样例执行 Python 实际写入路径的 dry-run/影子副本和 Axum PostgreSQL shadow 环境，不触生产写路径：

| 对比项 | Python 现有路径 | Axum PostgreSQL 路径 | 必须一致 |
| --- | --- | --- | --- |
| row 定位 | 工作台 row id、case id、batch id | `read_model.workbench_rows` 仅定位，事实表回查锁定 | affected row ids、affected months |
| 金额 | Python amount check / relation metadata | `app.*` facts 计算 `total_amount`、`difference_amount`、`applied_amount` | case 总金额、差额、每行 applied amount |
| 状态 | pair relation / batch / exception snapshot | PostgreSQL fact status、case status、binding status | active/cancelled/reverted 语义 |
| 幂等 | request idempotency key | `app.write_idempotency_records` | 同 key 重放不重复写 audit/outbox |
| 冲突 | Python version 或 active relation 冲突 | PostgreSQL `expected_version`、active row unique index | 409 code 可复现 |
| 副作用 | 持久化调度和 read model rebuild | `audit.events`、`job.worker_tasks`、`job.outbox_events` 同事务 | audit actor、outbox reason、scope |
| 特殊动作 | 现金过账/买票/取消、异常标记 | active case metadata 或 exception case | special metadata、exception code、note |

错误响应：

| HTTP | code | 说明 |
| --- | --- | --- |
| 401 | `invalid_oa_session` | 缺少 OA 登录态或 token 无效。 |
| 403 | `permission_denied` / `admin_only` | 当前 session 无写入或管理权限。 |
| 403 | `actor_mismatch` | body 中的兼容 actor 与 session actor 不一致。 |
| 400 | `missing_idempotency_key` | 写请求缺少幂等键。 |
| 400 | `invalid_month` / `invalid_uuid` / `invalid_row_ids` | 请求参数非法。 |
| 400 | `amount_mismatch_note_required` | 金额不一致但缺少备注。 |
| 404 | `workbench_row_not_found` / `reconciliation_case_not_found` / `exception_case_not_found` / `no_oa_bank_batch_not_found` | 目标事实不存在。 |
| 409 | `idempotency_key_reused_with_different_payload` | 同一操作幂等键被不同 payload 复用。 |
| 409 | `reconciliation_row_already_bound` | 行已绑定 active case，不能静默覆盖。 |
| 409 | `version_conflict` | optimistic lock 失败。 |
| 409 | `invalid_write_state` | 状态不允许当前写操作。 |
| 503 | `database_unavailable` | PostgreSQL 写入失败；响应不暴露 SQL 错误栈。 |

## 税金抵扣只读计算

### `POST /api/tax-offset/calculate`

用途：兼容旧 Python 税金抵扣页面的即时测算。Axum 版本只读取 `read_model.tax_offset_read_models.payload`，不写入认证状态、不确认导入、不触发 read model rebuild，也不写 `audit.events` 或 `job.outbox_events`。

请求：

```json
{
  "month": "2026-03",
  "selected_output_ids": ["output-1"],
  "selected_input_ids": ["input-1", "input-2"]
}
```

兼容规则：

- `month` 必须为 `YYYY-MM`，`month=all` 不支持。
- 与 Python `TaxOffsetService.calculate` 一致，`selected_output_ids` 仅作为兼容入参；输出税额来自该月 read model 中全部 `output_items`。
- `selected_input_ids` 只对未锁定认证的 `input_plan_items` 生效；`locked_certified_input_ids` 对应的进项不重复计入计划进项。
- 已认证进项税额来自 `certified_items[].deductible_tax_amount`，缺失时回落到 `tax_amount`。

成功响应：

```json
{
  "month": "2026-03",
  "selected_output_ids": ["output-1", "output-2"],
  "selected_input_ids": ["input-1", "input-2"],
  "summary": {
    "output_tax": "120.00",
    "certified_input_tax": "30.00",
    "planned_input_tax": "80.00",
    "input_tax": "110.00",
    "deductible_tax": "110.00",
    "result_label": "本月应纳税额",
    "result_amount": "10.00"
  }
}
```

错误响应：

| HTTP | code | 说明 |
| --- | --- | --- |
| 400 | `invalid_tax_offset_calculate_request` | body 缺少 `month` / `selected_input_ids`，或月份格式非法。 |
| 401 | `invalid_oa_session` | 缺少 OA 登录态或 token 无效。 |
| 403 | `permission_denied` | 当前 session 无写入权限；当前 Axum route policy 对 POST 仍按 mutation 保护。 |
| 404 | `tax_offset_read_model_not_found` | 对应月份的 tax offset read model 尚未生成。 |
| 503 | `database_unavailable` | PostgreSQL 读取失败；响应不暴露数据库错误栈。 |

## 后台任务列表兼容读取

### `GET /api/background-jobs/active`

用途：返回旧 Python 后台任务列表 envelope，供全局后台任务提示和进度条读取。Axum 版本只读 PostgreSQL `job.worker_tasks` 中 `visibility='system'` 的任务事实，不读取旧 Python `background_jobs`、app Mongo、NATS 或本地 pickle 状态，也不执行确认、重试或重放。

成功响应：

```json
{
  "jobs": [
    {
      "job_id": "77777777-7777-4777-8777-777777777777",
      "type": "etc_invoice_import",
      "label": "导入 ETC发票",
      "short_label": "正在导入 ETC发票 1/2",
      "owner_user_id": null,
      "visibility": "system",
      "status": "running",
      "phase": "running",
      "current": 1,
      "total": 2,
      "percent": 50,
      "message": "后台任务正在执行。",
      "result_summary": {},
      "error": null,
      "idempotency_key": "worker:etc_invoice_import:77777777-7777-4777-8777-777777777777",
      "source": {},
      "affected_scopes": [],
      "affected_months": [],
      "retryable": false,
      "acknowledgeable": false,
      "attention": false,
      "superseded_by_job_id": null,
      "created_at": "2026-05-16T10:00:00Z",
      "started_at": "2026-05-16T10:01:00Z",
      "updated_at": "2026-05-16T10:02:00Z",
      "finished_at": null,
      "acknowledged_at": null,
      "superseded_at": null
    }
  ],
  "active_jobs": [],
  "attention_jobs": []
}
```

兼容规则：

- `jobs` 为 `active_jobs + attention_jobs` 去重后的旧 Python envelope；前端当前只消费 `jobs`。
- `active_jobs` 包含 `queued/running/retrying` 任务以及 8 秒窗口内的非部分成功 `succeeded` 任务；`retrying` 对旧前端映射为 `queued`。
- `attention_jobs` 包含 `failed/dead_lettered` 任务，以及 `status='succeeded'` 且 `result_summary.partial_success=true` 的任务；`dead_lettered` 对旧前端映射为 `failed`。
- `source`、`result_summary` 会递归移除 `password/token/secret/credential/raw_file/raw_content/stack/traceback` 等敏感键。
- `acknowledgeable/attention` 只表达旧前端提示状态；Axum 此路由不提供确认写入，确认/替代状态仍需后续通知表或专门合同。

错误响应：

| HTTP | code | 说明 |
| --- | --- | --- |
| 401 | `invalid_oa_session` | 缺少 OA 登录态或 token 无效。 |
| 403 | `forbidden` / `permission_denied` | 当前 session 无应用访问权限。 |
| 503 | `database_unavailable` | PostgreSQL 读取失败；响应不暴露数据库错误栈。 |

### `GET /api/background-jobs/{job_id}`

用途：按 PostgreSQL `job.worker_tasks.id` 返回旧 Python `{job}` envelope。Axum 只暴露 `visibility='system'` 的 worker task；owner 私有任务在 OA owner 到 UUID owner 映射合同冻结前仍返回 404，避免猜测身份字段。

成功响应：

```json
{
  "job": {
    "job_id": "99999999-9999-4999-8999-999999999999",
    "type": "workbench_matching",
    "label": "自动匹配工作台",
    "short_label": "正在自动匹配工作台",
    "status": "queued",
    "phase": "retrying",
    "message": "等待重试。",
    "current": 0,
    "total": 0,
    "percent": 0,
    "retryable": false,
    "acknowledgeable": false,
    "attention": false
  }
}
```

错误响应：

| HTTP | code | 说明 |
| --- | --- | --- |
| 401 | `invalid_oa_session` | 缺少 OA 登录态或 token 无效。 |
| 403 | `forbidden` / `permission_denied` | 当前 session 无应用访问权限。 |
| 404 | `background_job_not_found` | `job_id` 不是 UUID、task 不存在，或 task 不是 system 可见。 |
| 503 | `database_unavailable` | PostgreSQL 读取失败；响应不暴露数据库错误栈。 |

## Worker Task 状态查询

### `GET /api/tasks/{task_id}/status`

用途：查询 PostgreSQL `job.worker_tasks` 的任务事实和对应 `job.worker_attempts` 执行尝试。该接口只读 PostgreSQL，不触发任务执行、重试、重放或生产切换。

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | UUID | `job.worker_tasks.id`。 |

成功响应：

```json
{
  "task": {
    "task_id": "22222222-2222-4222-8222-222222222222",
    "type": "read_model.rebuild",
    "label": "重建工作台",
    "short_label": "正在重建工作台 3/10",
    "owner_user_id": "33333333-3333-4333-8333-333333333333",
    "visibility": "owner",
    "status": "running",
    "phase": "rebuilding",
    "current": 3,
    "total": 10,
    "percent": 30,
    "message": "后台任务正在执行。",
    "result_summary": {
      "rebuilt": 3
    },
    "error_code": null,
    "error_summary": null,
    "retryable": true,
    "attempt_count": 1,
    "max_attempts": 5,
    "next_attempt_at": null,
    "source": {
      "session_id": "session-1"
    },
    "affected_scopes": ["workbench:2026-05"],
    "affected_months": ["2026-05-01"],
    "created_at": "2026-05-16T10:00:00Z",
    "started_at": "2026-05-16T10:01:00Z",
    "updated_at": "2026-05-16T10:02:00Z",
    "finished_at": null,
    "cancelled_at": null
  },
  "attempts": [
    {
      "attempt_id": "44444444-4444-4444-8444-444444444444",
      "attempt_no": 1,
      "worker_id": "worker-1",
      "nats_stream": "FINOPS_JOBS",
      "nats_consumer": "read-model-workers",
      "nats_sequence": 42,
      "started_at": "2026-05-16T10:01:00Z",
      "heartbeat_at": "2026-05-16T10:02:00Z",
      "finished_at": null,
      "duration_ms": null,
      "status": "running",
      "error_code": null,
      "error_summary": null
    }
  ]
}
```

前端兼容字段：

- `task.short_label`、`current`、`total`、`percent`、`message` 保持旧后台任务列表可展示的最小字段。
- `task.status` 使用目标状态机：`queued`、`running`、`succeeded`、`failed`、`retrying`、`dead_lettered`、`cancelled`。
- `attempts` 不返回 `error_detail`、内部堆栈、traceback 或 secret。
- `source`、`result_summary` 会递归移除 `password/token/secret/credential/raw_file/raw_content/stack/traceback` 等敏感键。

错误响应：

| HTTP | code | 说明 |
| --- | --- | --- |
| 400 | `invalid_task_id` | `task_id` 不是 UUID。 |
| 404 | `task_not_found` | PostgreSQL 中不存在该 task。 |
| 503 | `database_unavailable` | PostgreSQL 读取失败；响应不暴露数据库错误栈。 |

测试 fixture：`docs/dev/api-fixtures/task-status-response.json`。

## Prompt G 业务读 API 和 Shadow Validation

本批次继续迁移剩余业务 API 中可以明确落到 PostgreSQL facts 或 read model 的安全读取路径，并建立 Python vs Axum shadow validation。不得回读 app Mongo；未明确事实源或响应字段的接口保持 Python 路径。

路由 inventory：`docs/dev/api-fixtures/api-route-inventory.json`。

route-level inventory：`docs/dev/api-fixtures/api-route-inventory-route-level.json`。

shadow fixture：`docs/dev/api-fixtures/business-api-shadow-validation.json`。

报告模板：`docs/dev/api-shadow-validation-report-template.md`。

inventory 校验：

```bash
python scripts/tools/api_route_inventory_check.py \
  --inventory docs/dev/api-fixtures/api-route-inventory.json \
  --scan-root . \
  --shadow-fixture docs/dev/api-fixtures/business-api-shadow-validation.json \
  --include-route-prefix /api \
  --include-route-prefix /projects \
  --include-route-prefix /ledgers \
  --include-route-prefix /reminders \
  --include-route-prefix /imports \
  --include-route-prefix /matching
```

该工具会从 Python dispatch、Python `readiness_summary.entrypoints`、Axum `routes/*.rs` 和 `web/src` 中包含实际请求 helper 的 API client 文件发现当前路由/前端引用。前端扫描覆盖 `/api/`、`/imports/`、`/projects/`、`/ledgers/`、`/reminders/`、`/matching/` 字符串，忽略 `web/src/test`、`*.test.*`、`*.spec.*` 和仅作页面导航的路径。工具会展开 `GET|POST` 形式的 method group，并支持 `.../*` 路由前缀匹配；`readiness_summary` 中的 path-only entrypoint 必须被 inventory 中至少一个 Python route 覆盖。schema 缺失、Python/Rust route 未进入 inventory、readiness entrypoint 未进入 inventory、前端引用未标注，或 `--shadow-fixture` 中缺少任一已迁移 Axum route 的 shadow endpoint，均返回 `NO_GO`。

校验输出中的 `route_inventory[]` 是由 domain fixture 生成的 route-level 审计视图。每条记录包含 `python_route`、匹配到的 `rust_routes`、`frontend_refs`、`migration_status`、`risk`、`owner`、`source`、`source_categories` 和 `shadow_endpoint_ids`；已存在 Axum route 但仍需 shadow 的记录标记为 `migrated_shadow_required`，无 Axum route 且来源仍未冻结的记录标记为 `pending_contract` 或 `blocked_fact_source`。任一未迁移 Python route 必须在 domain fixture 的 `blocked_routes` 中给出逐路由 blocker，生成的 route-level inventory 会把该说明落到 `blocker` 字段；缺少 blocker 时 CLI 返回 `NO_GO`。`shadow_endpoint_ids` 必须指向 `business-api-shadow-validation.json` 中覆盖该 Axum route 的 endpoint；已迁移 route 没有 shadow endpoint 时，CLI 会输出 `shadow_coverage_errors[]` 并返回 `NO_GO`，fixture 同步测试也会失败。

更新 route-level fixture 时使用同一检查器生成，不手工编辑：

```bash
python scripts/tools/api_route_inventory_check.py \
  --inventory docs/dev/api-fixtures/api-route-inventory.json \
  --shadow-fixture docs/dev/api-fixtures/business-api-shadow-validation.json \
  --write-route-level-inventory docs/dev/api-fixtures/api-route-inventory-route-level.json
```

每个 inventory domain 必须包含机器可读 `source_categories`，取值范围为：

- `postgres_facts`
- `read_model`
- `job_outbox`
- `object_storage`
- `static_contract`
- `oa_identity`
- `pending_contract`
- `legacy_python_state_blocked`

只要 domain 中存在 `rust_routes`，`source_categories` 必须至少包含一个可切流来源：`postgres_facts`、`read_model`、`job_outbox`、`object_storage`、`static_contract` 或 `oa_identity`。仅有 `legacy_python_state_blocked` / `pending_contract` 的条目不得声明 Rust route，避免把未冻结事实源误判为可迁移。

### 已迁移到 Axum 的业务路径

| API | 来源 | 说明 |
| --- | --- | --- |
| `GET /api/app-health` | PostgreSQL `app.oa_sync_runs`/`app.oa_sync_watermarks`、`job.worker_tasks`、`read_model.workbench_snapshots`、OA identity adapter | 返回旧前端 AppHealth JSON snapshot 主结构；不回读 app Mongo alerts/dirty scope state。 |
| `GET /api/app-health/stream` | PostgreSQL `app.oa_sync_runs`/`app.oa_sync_watermarks`、`job.worker_tasks`、`read_model.workbench_snapshots`、OA identity adapter | SSE 包装同一 app-health snapshot，按旧 Python 合同发送 `app_health` 和 `heartbeat` 事件；shadow validation 只采样首批事件，不回读 app Mongo alerts/dirty scope state。 |
| `GET /api/bank-details/accounts?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` | PostgreSQL `app.bank_transactions` | 账户 key、尾号、余额和日期范围内流水数来自 bank facts；不回读 app Mongo。 |
| `GET /api/bank-details/transactions?account_key=...&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&page=1&page_size=100` | PostgreSQL `app.bank_transactions`、`app.bank_transaction_categories` | 返回旧前端 snake_case 行字段、手工分类、分页和分类计数；`page_size` 上限 500。auto category 和 relation tag 只返回当前 PostgreSQL 可证明的默认/空值，作为 shadow validation 解释项。 |
| `PATCH /api/bank-details/transactions/categories` | PostgreSQL `app.bank_transactions`、`app.bank_transaction_categories`、`app.bank_transaction_category_events`、`audit.events`、`app.write_idempotency_records`、`job.worker_tasks`、`job.outbox_events` | 写入 path 使用 OA session actor、`idempotency_key` 和 `expected_version`；事务内锁定 bank transaction，替换 active category，记录 category event/audit/idempotency，并排队 `read_model.rebuild_requested` 使 workbench、search_index、cost_statistics stale scope 后续重建。不读取 app Mongo 或 OA 源数据库。 |
| `GET /api/no-oa-bank-batches` | PostgreSQL `app.no_oa_bank_batches` | 列表、汇总和状态桶来自 batch facts；`raw_payload` 仅用于旧前端可选展示字段。 |
| `GET /api/no-oa-bank-batches/{batch_id}` | PostgreSQL `app.no_oa_bank_batches`、`app.bank_transactions`、`app.bank_transaction_categories` | 详情行锁定在 batch `scope_month` 和 `bank_transaction_ids` 内，不扫描 app Mongo。 |
| `POST /api/no-oa-bank-batches/{batch_id}/submit` | PostgreSQL `app.no_oa_bank_batches`、transactional workbench write command、job/outbox rebuild marker | 写入 path 必须使用 OA session actor、`expected_version` 和 `idempotency_key`；shadow 样本只能在隔离 staging/local 数据上运行。 |
| `POST /api/no-oa-bank-batches/{batch_id}/withdraw` | PostgreSQL `app.no_oa_bank_batches`、transactional workbench write command、job/outbox rebuild marker | 写入 path 必须使用 OA session actor、`expected_version` 和 `idempotency_key`；shadow 样本只能在隔离 staging/local 数据上运行。 |
| `POST /api/no-oa-bank-batches/submit` | PostgreSQL `app.no_oa_bank_batches`、transactional workbench write command、job/outbox rebuild marker | 批量提交返回 per-item results；每个 item 必须带 `batch_id`、`expected_version`、`idempotency_key`。 |
| `GET /api/turnover-ledger?view=grouped&family=company&page=1&page_size=50` | PostgreSQL `app.bank_transactions`、active `app.bank_transaction_categories.raw_payload.category_code` | 只读 flat/grouped 往来台账视图按 Python `turnover_ledger_service.py` 分类规则从银行流水和手工分类事实实时派生；不读取 app Mongo，不按 `app.turnover_relations` 猜测 Python grouping/lot/extra 字段。relation id、allocation lots、lot rows、人工确认/撤回状态和 relation extra 仍是 shadow 解释项或阻塞项。 |
| `GET /api/turnover-ledger/export-preview?family=company&limit=20` | PostgreSQL `app.bank_transactions`、active `app.bank_transaction_categories.raw_payload.category_code` | 按 Python `turnover_ledger_export_service.py` 生成旧 preview envelope：`columns/rows/totals/pagination/filters`。只读 preview，不生成 XLSX、不写对象存储、不读取 app Mongo。 |
| `GET /api/turnover-ledger/relations/{relation_id}` | PostgreSQL `app.bank_transactions`、active `app.bank_transaction_categories.raw_payload.category_code` | 按 Python SHA1 relation id 规则从同一 facts 派生 relation detail，返回 `relation/row/bank_rows/audit_history` envelope；不读取 app Mongo audit/extras。 |
| `GET /api/tax-offset?month=YYYY-MM` | `read_model.tax_offset_read_models` | 返回 read model payload 原形并附加 `read_model_status`。`month=all` 返回 400。 |
| `POST /api/tax-offset/calculate` | `read_model.tax_offset_read_models` | 从月度 read model payload 计算旧 Python summary；不写入认证状态、不触发 rebuild、不写 audit/outbox。 |
| `GET /api/tax-offset/certified-imports?month=YYYY-MM` | PostgreSQL `app.invoice_certifications`、`app.invoices` | 返回旧 Python `TaxCertifiedInvoiceRecord` 字段；只列出税金认证导入来源，按 `source_file_name/source_row_number/invoice_no/id` 排序。 |
| `POST /api/etc/import` | static contract | 保持旧 Python removed route 合同，始终返回 410 `etc_direct_import_removed`，提示使用 `/api/etc/import/preview` 和 `/api/etc/import/confirm`；不产生数据库、对象存储或 OA side effect。 |
| `GET /api/etc/invoices?status=unsubmitted\|submitted&month=YYYY-MM&page=1&page_size=50` | PostgreSQL `app.invoices` ETC columns、`raw_payload` | 返回旧 Python ETC invoice list envelope：`items/counts/page/pageSize/total`。状态、月份、车牌、关键字和分页在 PostgreSQL 层过滤；`has_pdf/has_xml` 不回查 Python 本地文件或对象存储，当前为 shadow diff 解释项。 |
| `GET /api/etc/batches?status=unsubmitted\|submitted&month=YYYY-MM&page=1&page_size=50` | PostgreSQL `app.invoices` ETC columns、`raw_payload` | 按 `import_batch_id`/`current_batch_id` 从 ETC invoice facts 聚合旧 Python batch list envelope：`items/counts/pagination/selectedBatch/plateSummary/invoiceItems`；不读取 app Mongo，不执行 OA draft 或 reconciliation side effects。 |
| `GET /api/etc/batches/{batch_id}` | PostgreSQL `app.invoices` ETC columns、`raw_payload` | 只读 batch detail：`batch/summary/plateSummary/invoiceItems/supplementItems`。`supplementItems` 当前为空数组，OA/reconciliation 补充凭证写入合同未冻结前不得猜测。 |
| `GET /api/cost-statistics?month=YYYY-MM\|all&project_scope=active\|all` | `read_model.cost_statistics_read_models` | 返回 read model payload 原形并附加 `read_model_status`。 |
| `GET /api/cost-statistics/explorer?month=YYYY-MM\|all&project_scope=active\|all` | `read_model.cost_statistics_read_models` | 与主成本统计读取同源；行排序和金额格式必须由 shadow validation 判定。 |
| `GET /api/cost-statistics/export-preview?month=YYYY-MM\|all&view=time\|project\|expense_type&project_scope=active\|all` | `read_model.cost_statistics_read_models` | 从 `time_rows` 生成旧 Python 预览 envelope：`view/file_name/scope_label/sheet_names/columns/rows/summary`。支持时间视图、费用类型视图和前端项目聚合预览；不读取 app Mongo，不回算 Python workbench 明细。 |
| `GET /api/cost-statistics/projects/{project_name}?month=YYYY-MM\|all&project_scope=active\|all` | `read_model.cost_statistics_read_models` | 从 explorer `time_rows` 按项目名过滤并按 `trade_time, transaction_id` 升序输出旧项目下钻 shape；不回算 Python workbench entries。 |
| `GET /api/cost-statistics/transactions/{transaction_id}?project_scope=active\|all` | PostgreSQL `app.bank_transactions`、`read_model.cost_statistics_read_models`、`read_model.workbench_rows` | 先用 bank transaction fact 定位月份，再从成本 read model 找交易行，并从 workbench row read model 合并 `summary_fields/detail_fields`。 |
| `GET /api/workbench?month=YYYY-MM` | `read_model.workbench_snapshots` | 返回单月工作台 snapshot，不支持 `month=all`，不在请求路径 rebuild，不回读 app Mongo。 |
| `GET /api/workbench/ignored?month=YYYY-MM` | `read_model.workbench_snapshots.ignored_rows` | 返回单月 ignored rows 和 `read_model_status`；缺失 snapshot 返回 404。 |
| `GET /api/workbench/read-model/status?month=YYYY-MM` | `read_model.workbench_snapshots` | Axum-only 状态读取，供前端/运维判断 stale、schema version 和 rebuild task。 |
| `GET /api/workbench/rows/{row_id}?month=YYYY-MM` | `read_model.workbench_rows` | 返回单行 read model payload 和状态；敏感字段按 Axum sanitizer 过滤。 |
| `POST /api/workbench/actions/*`、`POST /api/workbench/exception/apply` | PostgreSQL workbench facts、transactional write command、job/outbox read-model invalidation | 既有 Axum 写命令统一要求 OA actor、`expected_version`、`idempotency_key`；shadow 样本只能在隔离 local/staging fixture 数据上运行。 |
| `GET /api/background-jobs/active` | PostgreSQL `job.worker_tasks` | 返回旧 Python `jobs/active_jobs/attention_jobs` envelope；只读取 system worker task facts，不读取 Python `background_jobs`。 |
| `GET /api/background-jobs/{job_id}` | PostgreSQL `job.worker_tasks` | 返回旧 Python `{job}` envelope；只读取 system worker task detail，不迁移 acknowledge 写入。 |
| `POST /api/background-jobs/{job_id}/retry` | PostgreSQL `job.worker_tasks`、`job.outbox_events`、`audit.events`、`app.write_idempotency_records` | 写入路径只创建 retry worker task/outbox/audit/idempotency 记录，不在请求路径重放外部副作用；请求必须携带 OA actor、`idempotency_key` 和 `reason`。 |
| `GET /api/workbench/settings/data-reset/jobs/active` | PostgreSQL `job.worker_tasks` | 返回旧 Python 轮询 envelope `{job}`；只读取 `task_type='settings_data_reset'` 且 active 的 system task，不创建、不执行 reset。无 active job 返回 `{job:null}`。 |
| `GET /api/workbench/settings/data-reset/jobs/{job_id}` | PostgreSQL `job.worker_tasks` | 返回旧 Python data reset job shape；仅 `task_type='settings_data_reset'` 可见，其他 task 或缺失 task 返回 404 `settings_data_reset_job_not_found`。 |
| `GET /api/files/objects/{file_object_id}` | PostgreSQL `app.file_objects`、object-storage access provider | 返回文件对象元数据和有界 access grant；不返回对象内容、对象存储 secret 或原始 GridFS 内容。 |
| `GET /api/oa-sync/status` | PostgreSQL `app.oa_sync_runs`、`app.oa_sync_watermarks` | 返回最近 OA sync run/watermark 状态，不访问 OA 源库。 |
| `POST /imports/files/retry` | PostgreSQL `app.import_files`、`job.worker_tasks`、`job.outbox_events`、`audit.events`、`app.write_idempotency_records` | 按 `file_id` 请求重试解析，只排队 `import.parse` task；不复用 Python file session，不写业务 facts。 |
| `GET /imports/files/sessions/{session_id}` | PostgreSQL `app.import_batches`、`app.import_files` | 通过 `legacy_collection='import_sessions'` 和 `legacy_id` 投影旧 session envelope；无 PostgreSQL batch fact 时返回 404，不回读 app Mongo 或 Python session state。 |
| `POST /matching/run` | PostgreSQL `job.worker_tasks`、`job.outbox_events`、`audit.events`、`app.write_idempotency_records` | 按 `scope_month` 请求异步重建 workbench candidate matching；只排队 task/outbox，候选结果由 worker 后续写入 read model。 |
| `GET /matching/results`、`GET /matching/results/{result_id}` | `read_model.workbench_candidate_matches` | 只读候选匹配 read model，支持 `scope_month`、`status`、`limit`；不读取 app Mongo，不实时重算。 |

### 仍未迁移的 Prompt G 高风险路径

以下接口在本批次只进入 inventory，不实现 Axum 切换：

- `bank-details`：账户/流水 GET 与分类 PATCH 已迁移为 PostgreSQL facts + audit/idempotency/job/outbox 写入。relation tag 投影和 auto category 没有独立 PostgreSQL/read_model 事实源，生产切流前必须通过 shadow report 显式解释或补齐事实源。
- `turnover-ledger`：`GET /api/turnover-ledger` flat/grouped 只读视图、`GET /api/turnover-ledger/export-preview` 和 `GET /api/turnover-ledger/relations/{relation_id}` 已迁移为 PostgreSQL bank/category facts 实时派生；二进制 `export`、extra GET/PUT、confirm/withdraw、manual relation persistence、FIFO allocation lots 仍必须先从 `turnover_ledger_service.py` 和产品文档追溯合同，不能按 `app.turnover_relations` 猜字段。
- `ETC`：`POST /api/etc/import` 已迁移为静态 410 removed contract；`GET /api/etc/invoices`、`GET /api/etc/batches`、`GET /api/etc/batches/{batch_id}` 已迁移为 PostgreSQL ETC invoice facts 读取。导入 preview/confirm、对账任务、附件/票根文件、OA draft、提交状态写入和批次写操作依赖 job/outbox/object storage 组合合同，未冻结前不得迁移。
- `settings` 项目同步、项目增删、data-reset 创建/执行：属于管理写操作，必须先有 PostgreSQL settings facts、权限、审计、回滚和 job/outbox 合同。data-reset job 状态 GET 已迁移为 `job.worker_tasks` 读取。
- `tax-offset`：GET 与 calculate 已迁移为 `read_model.tax_offset_read_models` 只读路径；certified import preview/confirm 仍未迁移，写入、审计、幂等和 read-model invalidation/outbox 合同需先冻结。
- `cost-statistics`：export-preview 已迁移为 `read_model.cost_statistics_read_models.time_rows` 只读路径；二进制 Excel `export` 仍未迁移，workbook 样式、下载头、导出筛选和后台缓存语义需单独冻结。单项目无 `aggregate_by` 的 Python 项目明细预览依赖 workbench 明细构造，Axum 切流 fixture 应使用前端实际发送的 `aggregate_by=month|year` 聚合预览。
- `workbench`：单月 snapshot、ignored rows、row detail、read-model status 读取已迁移为 `read_model.workbench_snapshots/workbench_rows`。既有 Axum 写命令已进入 inventory 和 shadow fixture，但只能在隔离 local/staging 数据上验证；`POST /api/workbench/exception/preview` 仍阻塞，因为旧 Python preview 依赖 exception projection 和 matching candidate state，独立 read_model 合同未冻结。
- `background-jobs`：active/detail GET 已迁移为 `job.worker_tasks` system task 读取；`retry` 已迁移为 PostgreSQL task/outbox/audit/idempotency 写入；`acknowledge` 写操作未迁移，需先冻结通知表/ack 语义。
- `app-health`：JSON snapshot 和 SSE stream `/api/app-health/stream` 已迁移；app Mongo alerts 和旧 Python dirty scope state 未迁移。Axum matching 状态只读取 `job.worker_tasks` 和 `read_model.workbench_snapshots`。
- `projects`、`ledgers`、`reminders`、`imports preview/confirm/revert`：旧 Python 仍是事实路径；Axum 只迁移了导入 metadata、file-object metadata/access grant、upload preflight、import file retry、import session projection、matching run 请求和 matching results read model 子集。

### Shadow Validation Gate

先校验 fixture 契约完整性：

```bash
python scripts/tools/api_shadow_validate.py \
  --fixture docs/dev/api-fixtures/business-api-shadow-validation.json \
  --validate-fixture-only
```

运行：

```bash
python scripts/tools/api_shadow_validate.py \
  --python-base-url http://127.0.0.1:8001 \
  --axum-base-url http://127.0.0.1:8002 \
  --fixture docs/dev/api-fixtures/business-api-shadow-validation.json \
  --output-dir docs/operations/backend-refactor \
  --include-permission-failures
```

工具会输出 `api-shadow-validation-report-YYYYMMDD.json` 和 `api-shadow-validation-report-YYYYMMDD.md`。每条运行结果会保留 fixture 中的 `source` 说明，并派生 `results[].source_categories`，便于审查该 route 是否只来自 PostgreSQL facts、read_model、job/outbox、object storage、static contract、transactional workbench write 或 OA identity，而不是回读 app Mongo。`source` 会被工具和 readiness gate 机器校验：必须命中至少一个允许来源族；`source_categories` 只允许 `postgres_facts`、`read_model`、`job_outbox`、`object_storage`、`static_contract`、`transactional_workbench_write`、`oa_identity`；`app Mongo` 只能出现在 `no app Mongo read` 这类否定说明中，作为主动来源时报告保持 `NO_GO`。任一未解释 diff 均为 `NO_GO`，包括：

- `expected_status` 与 Python 或 Axum 实际 HTTP status 不一致。
- HTTP status diff。
- JSON 字段缺失或新增。
- 数组排序 diff。
- 金额格式 diff。
- 日期/时间格式 diff。
- 4xx 响应体不符合 `contract_cases.error_shape` 的 error-shape diff。
- 普通值 diff。

只有 endpoint fixture `explain_diffs` 明确列出的差异可解释；解释项仍需在报告中保留，不能静默忽略。

每个 endpoint case 会并发请求 Python 和 Axum，避免后台任务、read model 状态或时间戳类响应因为串行采样窗口过大产生伪差异。

SSE endpoint 可在 fixture 中设置 `response_mode: "sse_first_events"`，并在 `contract_cases.sse_events` 中列出必须采样的事件名。shadow 工具只读取首批事件并关闭连接，用于验证 `/api/app-health/stream` 这类无限流不会卡住验证进程；SSE 事件会被规范化为 `_sse_events[]` 后参与普通字段/排序/日期 diff。

运行时 shadow 命令会先执行同一套 fixture 契约校验。若 endpoint 缺少 `source`、`expected_status`、`contract_cases.query/body/status/error_shape/pagination/empty_result/permission_failure` 等必填项，工具不发送 HTTP 请求，直接生成 `NO_GO` 报告：`fixture_validation.status=NO_GO`、`summary.fixture_error_count>0`，并在 `results[]` 中写入 `fixture_validation` 差异行。未通过契约校验的报告不得作为 cutover 证据。

fixture 校验还会要求 endpoint 样本 `query` 中实际使用的每个 key 都出现在 `contract_cases.query`，且只要样本包含非空 `body`，`contract_cases.body` 就必须非空并描述该请求体。这样可以避免本地/staging shadow 样本和文档化契约悄悄漂移。

readiness gate 只读取 `docs/operations/backend-refactor/` 下的实际证据报告，并忽略 `*-template` 文件。`api_shadow_validation` gate 必须同时存在同名 `api-shadow-validation-report-YYYYMMDD.json` 和 `api-shadow-validation-report-YYYYMMDD.md`；只有 JSON 或只有 Markdown 都保持 `NO_GO`。JSON 的 top-level `status`、`fixture_validation.status`、`fixture_validation.endpoint_count`、`fixture_validation.endpoint_ids`、`fixture_validation.permission_failure_endpoint_ids`、`summary.go/no_go`、`summary.unexpected_diff_count`、`summary.permission_failure_cases`、`summary.permission_failure_required_count`、`summary.permission_failure_missing_count`、`summary.fixture_error_count`、`summary.total` 与每个 endpoint `results[].status/unexpected_diff_count/source/source_categories` 必须一致证明非空结果全部为 `GO`；`filters` 必须存在，`filters.endpoint_ids` 和 `filters.risks` 必须都是空数组，唯一 primary endpoint ID 集合必须等于 `fixture_validation.endpoint_ids`，每个 required permission failure ID 都必须有对应的 `endpoint_id#permission_failure` 结果，`summary.permission_failure_cases` 必须等于实际 permission-failure result 数量，`summary.permission_failure_required_count` 必须等于 required ID 数量，且 `summary.permission_failure_missing_count` 必须为 0。缺少 `fixture_validation`、结果为空、计数缺失或不一致、缺失 filters、局部筛选证据、primary 覆盖不完整、permission-failure 覆盖不完整、伪造或遗漏 endpoint ID、缺少或不合规的 endpoint source/source_categories、存在 fixture error、存在未解释 diff 或任何 endpoint 为 `NO_GO` 时，`api_shadow_validation` gate 仍为 `NO_GO`。同名 Markdown 报告必须包含工具生成的 `Gate: **GO**`，`Gate: **NO_GO**` 会被显式判为阻塞。

fixture 的 `defaults.headers` 会自动合并到每个 endpoint，endpoint 自己的 `headers` 可覆盖默认值。header、path、query 和 JSON body value 支持 `${ENV_VAR}` 形式的环境变量替换，用于本地/staging shadow token、fixture ID、幂等键 run id；报告不输出请求 header，避免泄露敏感值。

使用 `--include-permission-failures` 时，工具会对 `contract_cases.permission_failure` 不是 `not applicable` 的 endpoint 追加 `endpoint_id#permission_failure` 用例，并使用 `defaults.permission_failure.request_headers` 或 endpoint 级 `permission_failure.request_headers` 构造缺失/降权请求；若 required permission-failure case 在两处都没有 `request_headers` object，fixture validation 会在发送 HTTP 前失败，避免报告声称需要权限失败覆盖但实际无法构造请求。该用例必须满足自己的 `expected_status`，否则仍为 `NO_GO`。最终 readiness 证据必须包含 `fixture_validation.permission_failure_endpoint_ids` 中每个 endpoint 的 permission-failure 结果；无筛选的完整 fixture run 若省略 `--include-permission-failures`，只跑 primary case 的报告会直接生成 `NO_GO`。带 `--endpoint-id` 或 `--risk` 的局部诊断报告可以省略 permission-failure case，但这类 scoped report 不能作为 readiness evidence。

所有 4xx 响应都会按当前 case 的 `contract_cases.error_shape` 校验 JSON body。`"string"`、`"number"`、`"boolean"` 表示类型断言，其他非空值表示固定值断言；例如 `{"error":"etc_direct_import_removed","message":"string"}` 要求 `error` 精确等于该 code 且 `message` 为字符串。permission failure case 可通过 `defaults.permission_failure.error_shape` 或 endpoint 级 `permission_failure.error_shape` 覆盖默认错误形状。

`--endpoint-id` 与 `--risk` 可以重复传入，用于局部验证单个端点、业务域端点或高风险端点；报告会记录 `filters.endpoint_ids` 和 `filters.risks`。筛选结果为空时必须返回 `NO_GO`，避免端点 ID 拼写错误被误判为通过。局部验证报告只用于排查，不得作为 readiness gate 的最终证据；最终证据必须是不带筛选的完整 fixture run。

shadow 报告会保留 diff 路径和计数，但对 token、password、secret、credential、cookie、authorization、URL/presigned URL、raw file/content、non-JSON body、stack、traceback 等敏感字段值输出 `[REDACTED]`。这些 diff 仍按普通未解释差异参与 `NO_GO` 判定，不能因为被脱敏而视为已解释。

endpoint `path` 同样支持 `${ENV_VAR}` 替换。包含路径参数的样本（例如 `COST_PROJECT_NAME_PATH`）应预先 URL encode，确保 Python 与 Axum 请求完全一致。

包含写入副作用的 shadow 样本（例如 no-OA submit/withdraw）只能对隔离 local/staging fixture 运行，并且必须配置一次性或可重放的 `idempotency_key`。不得对生产或共享 staging 数据直接执行写 shadow。

## 版本和兼容

当前项目仍保留部分旧接口。新增能力应优先接入 `/api/*` 契约层；旧接口只用于兼容测试或历史页面，不应继续扩展。

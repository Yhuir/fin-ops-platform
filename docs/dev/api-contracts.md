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
- `/api/etc/business-batches*`：ETC 用户可见业务批次、补充导入、OA 草稿、OA 自动检测、人工兜底和撤销草稿。详细合同见 `etc-business-batches-api.md`。
- `/api/tax-offset*`：税金抵扣和已认证导入。
- `/api/cost-statistics*`：成本统计、下钻和导出。
- `/api/bank-details*`：银行明细、自动分类展示和 XLSX 导出。
- `/api/pending-invoices*`：待找发票列表、筛选、关系明细、候选进项发票、规则和导出。详细合同见 `pending-invoices-api.md`。
- `/api/background-jobs*`：后台任务。
- `/api/app-health*`：健康状态。
- `/api/operations/app-health-dashboard`：管理员只读运维观测 Dashboard。

## 银行明细自动标签规则 API

`GET /api/bank-details/auto-tag-rules`

返回银行明细文本类自动标签规则。该接口只读取 `bank_transaction_tags`，不读取平行规则表。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `version` | 当前银行明细标签配置版本，用于保存时乐观锁。 |
| `system_rule` | 固定系统规则，目前为 `internal_transfer`/`内部往来款`，只展示不允许编辑。 |
| `active_rules` | 可用文本类标签，按优先级升序返回。 |
| `archived_rules` | 停用文本类标签，不参与自动命中。 |
| `field_options` | 可用于规则配置的稳定语义字段。 |
| `permissions.can_save` | 当前用户是否可以保存。 |
| `read_model_status` | 可选，说明保存后派生数据是否仍在刷新。 |

`active_rules[*]` 和 `archived_rules[*]` 至少包含：

| 字段 | 说明 |
| --- | --- |
| `code` | 稳定标签身份；新增标签保存前可为空，保存后由后端生成。 |
| `label` | 当前显示名称。 |
| `status` | `active` 或 `archived`。 |
| `priority` / `priority_label` | 可用区优先级；停用区可为空。 |
| `sort_order` | 同优先级内排序号；可用区返回。 |
| `direction` | 适用方向：`income`、`expense`、`any`。 |
| `account_scope` | 兼容保留的适用账户范围字段：`{"type":"any","values":[]}`、`bank_account`、`account_type` 或 `bank`。普通维护 UI 不编辑账户范围，保存时固定写 `{"type":"any","values":[]}`。 |
| `rules.match_fields` | 语义字段列表。 |
| `rules.exact_any` | 精确命中任一字样列表，可为空。旧字段 `exact` 作为兼容别名读取。 |
| `rules.contains_any` | 包含任一字样列表，可为空。旧字段 `contains` 作为兼容别名读取。 |
| `rules.contains_all` | 必须同时包含字样列表，可为空。 |
| `rules.none_of` | 不包含任一字样列表，可为空。旧字段 `excludes` 作为兼容别名读取。 |
| `rules.regex_any` | 兼容保留的正则命中任一列表，可为空。普通维护 UI 不编辑正则，保存时固定写空数组。 |
| `output_primary_label` / `output_sub_label` | 输出标签；子标签可为空。 |
| `rule_summary` | 后端生成的人类可读摘要。 |
| `editable` / `archivable` / `sortable` | 前端交互能力标志。 |

普通 UI 不展示或编辑 `rule_id`、`version`、`stop_on_match`、`review_required`、`route_to`、命中说明、审计字段、账户范围和正则条件。这些系统字段由后端持久化、执行和审计使用。命中解释在结果预览或调试场景展示，不作为规则编辑项。

`field_options` 固定暴露语义字段，不暴露银行原始字段名：`counterparty_name`、`counterparty_account`、`counterparty_bank`、`purpose_text`、`summary_text`、`note_text`、`detail_text`、`all_text`。后端导入和自动分类服务负责把工行、建行、民生、平安等不同银行原始字段映射到这些语义字段。

`PUT /api/bank-details/auto-tag-rules`

请求示例：

```json
{
  "expected_version": 3,
  "active_rules": [
    {
      "code": "salary",
      "label": "人员薪酬",
      "direction": "expense",
      "account_scope": {"type": "any", "values": []},
      "rules": {
        "match_fields": ["summary_text", "purpose_text", "note_text", "detail_text"],
        "exact_any": [],
        "contains_any": ["工资"],
        "contains_all": [],
        "none_of": [],
        "regex_any": []
      }
    },
    {
      "label": "供应商退款",
      "direction": "income",
      "account_scope": {"type": "any", "values": []},
      "rules": {
        "match_fields": ["all_text"],
        "exact_any": [],
        "contains_any": ["退款"],
        "contains_all": [],
        "none_of": ["保证金"],
        "regex_any": []
      }
    }
  ],
  "archived_rules": []
}
```

保存规则：

- `expected_version` 必填；版本不一致返回 `409 bank_transaction_tags_version_conflict`。
- 请求提交完整的可用区和停用区文本规则列表。`internal_transfer` 不在请求体中提交。
- 已存在标签必须携带原 `code`；新建标签不得提交 `code`，由后端生成稳定 `custom_...` code。
- 可用标签 `label` 去首尾空格后不能为空，同一状态区内不可重复。
- 普通维护 UI 保存时，所有规则固定提交 `account_scope={"type":"any","values":[]}` 和 `rules.regex_any=[]`。后端继续兼容读取旧数据中的账户范围和正则字段，但普通维护 UI 不生成这些高级条件。
- 可用标签必须至少填写 `exact_any`、`contains_any` 或 `contains_all` 中的一类；`none_of` 只能为空或配合正向条件使用，不能单独构成命中。
- `match_fields` 只能使用 `field_options` 中的语义字段，且不能为空。
- 停用已被待找发票规则引用的标签返回 `400 bank_transaction_tag_in_use_by_pending_invoice_filter`，响应 `details.references` 给出引用位置。
- 成功后返回与 GET 相同结构，并写审计动作 `bank_auto_tag_rules_updated`。
- 成功保存只标记派生数据 dirty/enqueue 后台刷新，不在 API 请求热路径同步扫描全量银行流水、免 OA 批次、关联台或待找发票 read model。

错误响应保持 JSON envelope：

```json
{
  "error": {
    "code": "invalid_bank_auto_tag_rules_request",
    "message": "自动标签规则无效。",
    "details": {
      "field_errors": [
        { "field": "active_rules[0].rules.match_fields", "message": "匹配字段不能为空。" }
      ]
    }
  }
}
```

## 工作台 DTO

工作台 DTO 的详细结构见 `reconciliation-workbench-v2-data-contracts.md`。

### 工作台 read model 刷新状态

`GET /api/workbench/refresh-status?month=all`

该接口是关联工作台页面判断后台加载是否完成的轻量事实源，不返回 group、行、附件正文或 snapshot payload。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `scope_key` | 当前 read model scope，例如 `all` 或 `2026-05`。 |
| `read_model_status` | `fresh`、`refreshing`、`stale`、`failed`、`unavailable`。 |
| `generated_at` | 最近稳定投影生成时间；未知为 `null`。 |
| `active_generation_id` | 当前稳定可读 generation。未知为 `null`。 |
| `building_generation_id` | 正在构建但不可读的 generation。没有后台构建时为 `null`。 |
| `failed_generation_id` | 最近失败 generation。没有失败时为 `null`。 |
| `read_model_version` | 可用于前端去重的版本，优先等于 `active_generation_id`；未知为 `null`。 |
| `generations` | 最近 generation 摘要，仅包含元数据、计数和错误摘要，不包含业务 payload。 |
| `dirty_scopes` | dirty scope 摘要，包含 `scope_key`、`status`、`updated_at`、`last_error`、`source_version`。 |
| `running_scopes` | 正在执行的 scope 列表；未知或无执行为 `[]`。 |
| `processed_count` / `total_count` | 后台进度。无法可靠计算时返回 `null`，不得返回伪造的 `0`。 |
| `worker_lag_seconds` | 最近 worker heartbeat 延迟；未知为 `null`。 |
| `last_error` | 最近失败摘要；没有失败为 `null`。 |
| `retryable` | 当前状态是否可通过后台任务重试或重新排队。 |

`GET /api/workbench/events?month=all`

SSE 事件流。支持事件：

- `workbench.read_model.refresh_started`
- `workbench.read_model.progress`
- `workbench.read_model.page_available`
- `workbench.read_model.summary_updated`
- `workbench.read_model.completed`
- `workbench.read_model.failed`
- `heartbeat`

事件 payload 与 `/api/workbench/refresh-status` 使用同一状态结构。前端收到完成或 `read_model_version`/`active_generation_id` 变化事件后，只重新读取当前查询上下文的 `summary` 与 `groups` 分页；SSE 不可用时轮询 `/api/workbench/refresh-status`。

## ETC 业务批次 API

ETC 对账任务、ZIP 导入和 OA 草稿提交统一使用 `/api/etc/business-batches*` 作为新增契约层。它取代前端直接拼接 `EtcImportBatch` 和 `EtcBatch` 的展示口径，旧 `/api/etc/batches*` 只作为过渡兼容入口，不应继续扩展。

详细状态枚举、错误码、权限、幂等和撤销草稿/释放发票规则见 [`etc-business-batches-api.md`](etc-business-batches-api.md)。设计依据见 [`../superpowers/specs/2026-05-19-etc-business-batch-oa-auto-detection-design.md`](../superpowers/specs/2026-05-19-etc-business-batch-oa-auto-detection-design.md)。

## AppHealth 运维 Dashboard API

`GET /api/operations/app-health-dashboard`

权限：

- 复用 OA session。
- 仅 `can_admin_access=true` 的管理员可访问。
- 未登录或登录态失效返回现有 `401 invalid_oa_session`。
- 非管理员返回 `403 admin_only`。

该接口独立于 `/api/app-health`。`/api/app-health` 仍用于全局健康状态、SSE、多标签页同步和写操作 gating。

响应结构：

```json
{
  "generated_at": "2026-05-23T10:00:00+08:00",
  "data_inventory": {
    "bank": {
      "total_count": 128,
      "latest_synced_at": "2026-05-23T09:50:00+08:00",
      "status": "available",
      "sources": []
    },
    "invoice": {
      "total_count": 256,
      "latest_synced_at": "2026-05-23T09:48:00+08:00",
      "status": "available",
      "sources": []
    },
    "oa": {
      "total_count": 72,
      "latest_synced_at": "2026-05-23T09:45:00+08:00",
      "status": "available",
      "sources": []
    }
  },
  "request_performance": {
    "window": {
      "type": "process_rolling_window",
      "sample_limit_per_endpoint": 512,
      "reset_on_restart": true
    },
    "endpoints": []
  },
  "runtime_performance": {
    "outbox": {},
    "queues": [],
    "read_models": [],
    "workers": []
  },
  "freshness": {
    "warnings": []
  }
}
```

契约要求：

- Dashboard 只返回页面需要的聚合读数据，不返回业务 payload、snapshot、raw payload、token、数据库 URL 或 RabbitMQ URL。
- `data_inventory.invoice.sources` 固定包含 `standard_import`、`oa_attachment`、`etc`、`manual`。
- `request_performance.endpoints[*]` 包含 `duration_ms`、`database_duration_ms`、`connection_acquire_ms`、`sql_execute_fetch_ms`、`database_query_count` 的 p50/p95/p99。
- `runtime_performance.queues[*]` 基于已知 RabbitMQ route 输出，即使 RabbitMQ Management API 不可用也保留行，数值为 `null`。
- unknown 指标用 `null` 和 `status="unknown"` 表示。前端显示 `--`，不得把 unknown 当成 `0`。

## 版本和兼容

当前项目仍保留部分旧接口。新增能力应优先接入 `/api/*` 契约层；旧接口只用于兼容测试或历史页面，不应继续扩展。

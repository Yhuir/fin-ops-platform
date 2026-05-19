# ETC 业务批次 API 契约

本文档定义 ETC 对账任务、ETC ZIP 导入、OA 草稿和 OA 提交检测的统一 API。产品事实源见 [`../product-specs/tax-offset-and-etc.md`](../product-specs/tax-offset-and-etc.md)，设计依据见 [`../superpowers/specs/2026-05-19-etc-business-batch-oa-auto-detection-design.md`](../superpowers/specs/2026-05-19-etc-business-batch-oa-auto-detection-design.md)。

## 契约目标

- 前端只展示一个用户可见 ETC 业务批次。
- `EtcImportBatch` 和 `EtcBatch` 作为技术子资源保留，不作为页面主批次。
- 创建 OA 草稿后进入后台自动检测，由系统检测 OA 是否进入 `进行中`；人工确认只作为异常兜底。
- 所有写接口使用 `expectedVersion` 做乐观锁，并按业务批次写审计。
- 所有接口返回 JSON envelope，不能把 HTML 502、代理错误页或空 body 透传给前端。

## 统一响应

成功响应：

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "requestId": "req_..."
}
```

错误响应：

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "version_conflict",
    "message": "批次状态已变化，请刷新后重试。",
    "details": {
      "businessBatchId": "etc_business_batch_0001",
      "expectedVersion": 3,
      "actualVersion": 4
    }
  },
  "requestId": "req_..."
}
```

## API 列表

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/etc/business-batches` | 查询当前用户或组织可见的 ETC 业务批次。 |
| `GET` | `/api/etc/business-batches/{businessBatchId}` | 查询业务批次详情、导入记录、OA 草稿和检测状态。 |
| `POST` | `/api/etc/business-batches` | 为对账任务创建或绑定唯一 active 业务批次。 |
| `POST` | `/api/etc/business-batches/{businessBatchId}/source-files` | 追加或登记对账任务源文件。 |
| `POST` | `/api/etc/business-batches/{businessBatchId}/etc-import/preview` | 预览首次或补充 ETC ZIP 导入。 |
| `POST` | `/api/etc/business-batches/{businessBatchId}/etc-import/confirm` | 确认导入预览，合并到同一业务批次。 |
| `POST` | `/api/etc/business-batches/{businessBatchId}/oa-draft` | 创建并打开 OA 草稿，成功后进入自动检测。 |
| `POST` | `/api/etc/business-batches/{businessBatchId}/oa-draft/revoke` | 撤销本地 active 草稿绑定并释放发票。 |
| `POST` | `/api/etc/business-batches/{businessBatchId}/oa-status/refresh` | 触发一次即时 OA 检测。 |
| `POST` | `/api/etc/business-batches/{businessBatchId}/manual-oa-status` | 检测异常后的人工兜底。 |
| `DELETE` | `/api/etc/business-batches/{businessBatchId}` | 删除未提交或已释放的业务批次。 |

旧接口 `/api/etc/reconciliation-tasks`、`/api/etc/import/preview`、`/api/etc/import/confirm`、`/api/etc/batches*` 过渡期保留。新增页面和新能力优先接入 `business-batches`，旧接口只包装到新服务或保留兼容测试。

## 业务批次 DTO

```json
{
  "businessBatchId": "etc_business_batch_0001",
  "taskId": "ETC-RECON-000020",
  "status": "oa_submission_detecting",
  "version": 7,
  "ownerUserId": "u_001",
  "ownerOrgId": "finance",
  "importBatchIds": ["etc_import_batch_0004", "etc_import_batch_0005"],
  "submissionBatchId": "etc_batch_0027",
  "externalEtcBatchId": "etc_20260519_001",
  "oaDraftId": "682b...",
  "oaDraftUrl": "https://www.yn-sourcing.com/oa/#/normal/forms/form/2?formId=2&id=682b...",
  "oaRowId": null,
  "oaProcessStatus": "unknown",
  "oaDetectionStatus": "detecting",
  "invoiceSummary": {
    "count": 37,
    "amount": "1673.30"
  },
  "importAttempts": [],
  "auditEvents": []
}
```

金额字段用字符串或 Decimal 序列化值表达，服务端按分或 Decimal 精确比较，不能使用浮点比较。

## 状态枚举

主流程状态：

| 状态 | 含义 |
| --- | --- |
| `draft` | 业务批次已创建，尚未完成导入。 |
| `reviewing` | 对账任务或导入结果正在复核。 |
| `ready_for_import` | 已具备导入条件。 |
| `importing` | 正在导入 ETC ZIP。 |
| `imported` | 发票已导入，尚未创建有效 OA 草稿。 |
| `oa_draft_creating` | 正在创建 OA 草稿。 |
| `oa_submission_detecting` | OA 草稿已创建，后台正在检测 OA 是否进入 `进行中`。 |
| `oa_submitted` | 系统自动检测到 OA 已进入 `进行中`，批次进入已提交链路。 |
| `closed` | 批次已关闭。 |

异常和人工状态：

| 状态 | 含义 |
| --- | --- |
| `import_failed` | 导入失败，可重试或删除。 |
| `import_partial_failed` | 部分导入失败，必须展示逐项结果。 |
| `oa_draft_failed` | OA 草稿创建失败，可重试或删除。 |
| `not_submitted` | 草稿已释放或用户确认未提交，可补充导入和重建草稿。 |
| `oa_detection_timeout` | 检测超过截止时间，允许刷新、撤销或人工兜底。 |
| `oa_detection_conflict` | 检测到多个候选或候选不满足唯一确认条件。 |
| `oa_detection_unavailable` | OA Mongo 不可用、权限失败或查询超时。 |
| `manually_marked_submitted` | 异常状态下人工标记已提交。 |
| `manually_marked_not_submitted` | 异常状态下人工标记未提交，并释放发票。 |
| `migration_conflict` | 历史迁移发现多个 active 关系，需管理员修复。 |
| `business_batch_invariant_broken` | 业务批次不变量损坏，需管理员修复。 |
| `deleted` | 本地业务批次已删除。 |
| `superseded` | 已被更正或新批次替代。 |

`oa_marker_missing`、`oa_amount_mismatch`、`oa_invoice_count_missing`、`oa_org_unverified` 是 `oaDetectionReason`，不是业务批次 `status`。

active 状态包括 `draft`、`reviewing`、`ready_for_import`、`importing`、`imported`、`import_failed`、`import_partial_failed`、`oa_draft_creating`、`oa_draft_failed`、`oa_submission_detecting`、`oa_detection_timeout`、`oa_detection_conflict`、`oa_detection_unavailable`、`not_submitted`、`manually_marked_not_submitted`、`migration_conflict`、`business_batch_invariant_broken`。非 active 状态包括 `oa_submitted`、`manually_marked_submitted`、`closed`、`deleted`、`superseded`。

## 写接口规则

| 接口 | 请求关键字段 | 前置状态 | 幂等条件 | 成功后状态 |
| --- | --- | --- | --- | --- |
| `POST /business-batches` | `taskId`, `idempotencyKey` | 任务存在且无 active 批次 | `taskId + idempotencyKey` | `draft` |
| `POST /etc-import/preview` | `files`, `expectedVersion` | 允许补充导入状态 | 文件 hash 相同返回同一预览 | 状态不变 |
| `POST /etc-import/confirm` | `previewId`, `expectedVersion`, `idempotencyKey` | 允许补充导入状态 | `previewId + idempotencyKey` | `imported` 或 `import_partial_failed` |
| `POST /oa-draft` | `expectedVersion`, `idempotencyKey` | `imported` 且发票数大于 0 | 已有 active 草稿返回同一草稿 | `oa_submission_detecting` |
| `POST /oa-draft/revoke` | `expectedVersion`, `reason`, `idempotencyKey` | 草稿已创建但未提交 | `businessBatchId + idempotencyKey` | `not_submitted` |
| `POST /oa-status/refresh` | `expectedVersion` | 检测相关状态 | 同一时刻只运行一次检测 | 最新检测状态 |
| `POST /manual-oa-status` | `decision`, `reason`, `candidateOaRowId`, `expectedVersion` | `oa_detection_timeout`、`oa_detection_conflict` 或 `oa_detection_unavailable` | `businessBatchId + decision + expectedVersion` | `manually_marked_submitted` 或 `manually_marked_not_submitted` |
| `DELETE /business-batches/{id}` | `expectedVersion`, `reason` | 未生成有效 OA 草稿，或已进入 `not_submitted` / `manually_marked_not_submitted` | 重复删除返回 `deleted` | `deleted` |

允许补充导入的状态为 `draft`、`reviewing`、`ready_for_import`、`imported`、`import_failed`、`import_partial_failed`、`oa_draft_failed`、`not_submitted`、`manually_marked_not_submitted`。进入 `oa_submission_detecting` 后，金额、发票数和附件集合已固化，必须先撤销草稿/释放发票才能补充导入。

## OA 草稿和自动检测

`POST /oa-draft` 创建草稿成功后，服务端立即持久化：

```text
status = oa_submission_detecting
oa_detection_started_at = now
oa_detection_next_run_at = now + interval
oa_detection_deadline_at = now + 30 minutes
oa_detection_final_retry_until = now + 24 hours
oa_detection_attempts = 0
```

OA 草稿内容必须写入稳定标记：

```text
ETC批量提交
etc_batch_id=etc_20260519_001
business_batch_id=etc_business_batch_0001
```

检测服务只接受 OA 适配器归一化后的 canonical `in_progress`。适配器需要兼容数字 `1`、字符串 `"1"` 和展示值 `进行中`，业务服务不得散写这些字面值比较。

检测候选必须限定 OA 支付申请表单、form id、业务标记、创建时间窗口、申请人或组织边界、金额、发票数量。金额不一致、发票数量缺失、组织无法确认或多候选时不得自动提交。

## 撤销草稿/释放发票

`POST /oa-draft/revoke` 用于草稿已创建但未提交时，释放本地业务批次与当前 OA 草稿的绑定。

请求示例：

```json
{
  "reason": "发现 ETC 导入缺少 516HJ 4 月发票，撤销本地草稿后补充导入。",
  "idempotencyKey": "revoke-etc-business-batch-0001-20260519",
  "expectedVersion": 8
}
```

后端执行顺序：

1. 校验用户有 `finops:app:operate` 且批次在自己或所属组织作用域内。
2. 执行一次即时 OA 检测。
3. 如果检测到 OA 已进入 canonical `in_progress`，拒绝撤销并推进为 `oa_submitted`。
4. 如果未提交，释放 ETC 发票 `current_batch_id`，发票状态回到 `unsubmitted`。
5. 当前 `submissionBatchId` 标记为 inactive 历史草稿，清空 active `oaDraftId`、`oaDraftUrl` 和 `submissionBatchId`。
6. 业务批次进入 `not_submitted`，写审计。

该接口必须幂等。重复调用返回当前 `not_submitted` 状态和首次释放的审计事件。系统不删除 OA 源系统草稿，页面必须提示旧 OA 草稿已从本地释放，不能继续提交旧草稿。

## 人工兜底

`POST /manual-oa-status` 只在 `oa_detection_timeout`、`oa_detection_conflict`、`oa_detection_unavailable` 状态开放。

请求示例：

```json
{
  "decision": "submitted",
  "candidateOaRowId": "oa-pay-682b...",
  "reason": "OA 已进入流程，自动检测超时后人工确认。",
  "expectedVersion": 7
}
```

规则：

- `reason` 必填。
- `decision=submitted` 时，如提供 `candidateOaRowId`，后端必须重新校验 row 存在、表单类型、金额、ETC 标记和流程状态；没有 OA row 也允许，但必须标记来源为 `manual_without_oa_row`。
- `decision=not_submitted` 时，必须释放发票占用、解绑 active 草稿并写审计。
- 普通用户只能处理自己或所属组织可访问批次；跨组织、`migration_conflict` 和 `business_batch_invariant_broken` 只允许管理员处理。

## 错误码

| HTTP | code | 含义 |
| --- | --- | --- |
| `403` | `forbidden_scope` | 用户无权访问或操作该批次。 |
| `404` | `business_batch_not_found` | 批次不存在。 |
| `409` | `version_conflict` | 乐观锁冲突，前端应刷新批次后重试。 |
| `409` | `active_business_batch_exists` | 同一任务已存在 active 批次。 |
| `409` | `operation_in_progress` | 已有导入、建草稿或检测任务运行中。 |
| `422` | `invalid_status_transition` | 当前状态不允许该操作。 |
| `422` | `oa_draft_already_exists` | 已有草稿，不能直接补充导入。 |
| `422` | `oa_already_submitted` | 撤销前即时检测发现 OA 已进入流程。 |
| `422` | `oa_candidate_invalid` | 人工选择的 OA 候选未通过后端校验。 |
| `503` | `oa_detection_unavailable` | OA 只读查询不可用、权限失败或超时。 |

## 权限矩阵

| 接口 | 最小权限 | 作用域 |
| --- | --- | --- |
| `GET /business-batches*` | `finops:app:view` | 只能读取自己或所属组织可见批次；`finops:app:admin` 可跨组织。 |
| `POST /business-batches` | `finops:app:operate` | 只能为自己或所属组织任务创建。 |
| `POST /etc-import/*` | `finops:app:operate` | 只能操作自己或所属组织 active 批次。 |
| `POST /oa-draft` | `finops:app:operate` | 只能操作自己或所属组织 active 批次。 |
| `POST /oa-draft/revoke` | `finops:app:operate` | 只能撤销自己或所属组织 active 批次；已提交后只能管理员走更正流程。 |
| `POST /oa-status/refresh` | `finops:app:view` | 可触发一次只读检测，状态推进仍由后台服务按版本校验执行。 |
| `POST /manual-oa-status` | `finops:app:operate` | 普通用户限自己或所属组织；无 OA row 的高风险提交需额外审计；跨组织只允许 `finops:app:admin`。 |
| `DELETE /business-batches/{id}` | `finops:app:operate` | 普通用户限未提交且自己或所属组织；冲突和不变量损坏只允许 `finops:app:admin`。 |

只拥有 `finops:app:view` 或导出权限的用户不得调用写接口。所有 403 都返回 JSON；高风险写接口的 403 需要写安全审计，普通读取 403 只写访问日志。

# 后端重构盘点与契约梳理

盘点日期：2026-05-16

## 概览

本文件只基于仓库代码和文档做只读盘点，不连接任何数据库，不访问 OA 源库，不推断未在代码中出现的字段。目标是为 Axum + PostgreSQL 重构提供现有 Python 后端、前端调用、app Mongo、GridFS、OA adapter 和迁移批次边界。

当前系统事实：

- Python HTTP 入口集中在 `backend/src/fin_ops_platform/app/server.py` 的 `Application.handle_request`。
- 前端正式 API client 集中在 `web/src/features/*/api.ts`，测试 mock 在 `web/src/test/apiMock.ts`。
- app 状态由 `ApplicationStateStore` 管理，生产模式为 app Mongo detailed collections + GridFS，保留 local pickle/JSON 兼容路径。
- app Mongo 中多数 detailed collections 同时保存可筛选字段和 `payload: Binary(pickle.dumps(...))`，迁移工具应复用现有 Python store/service 导出规范化数据。
- OA Mongo 只应通过 `MongoOAAdapter` 读取，重构和迁移不得备份、导出、写入或操作 OA 源数据库。
- GridFS bucket 为 `import_file_blobs`，目标架构中应迁移到 MinIO/S3，并在 PostgreSQL 保存文件元数据和旧 id 映射。

## API 路由清单

说明：

- `R` 表示读，`W` 表示写或会修改 app 状态，`D` 表示删除/撤回/重置等高风险变更。
- “前端调用”仅标注本次在 `web/src` 中确认的调用点；未确认不代表没有历史页面或外部调用。
- “未来模块”是建议的 Axum `routes/*` 归属，不代表已实现。

### 基础与会话

| 方法 | 路径 | 当前处理 | 读写 | 风险 | 前端调用 | 未来模块 |
| --- | --- | --- | --- | --- | --- | --- |
| `OPTIONS` | `*` | CORS preflight | R | 低 | 浏览器隐式 | middleware |
| `GET` | `/health` | 健康检查 | R | 低 | 未确认 | `health` |
| `GET` | `/foundation/seed` | demo seed | R | 低 | 未确认 | `health` 或 dev-only |
| `GET` | `/api/session/me` | OA token/session/access tier | R | 中：鉴权边界 | `web/src/features/session/api.ts` | `auth` |

### 健康、后台任务和搜索

| 方法 | 路径 | 当前处理 | 读写 | 风险 | 前端调用 | 未来模块 |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/oa-sync/status` | OA sync 状态 | R | 低 | `appHealth/api.ts`, `workbench/api.ts` | `health` |
| `GET` | `/api/app-health` | app health 快照 | R | 低 | `appHealth/api.ts` | `health` |
| `GET` | `/api/app-health/stream` | SSE health stream | R | 中：长连接 | `appHealth/api.ts` | `health` |
| `GET` | `/api/background-jobs/active` | 活跃后台任务 | R | 低 | `backgroundJobs/api.ts` | `jobs` |
| `GET` | `/api/background-jobs/{job_id}` | 单任务详情 | R | 低 | 未确认直接调用；mock 覆盖 | `jobs` |
| `POST` | `/api/background-jobs/{job_id}/acknowledge` | 确认任务 | W | 中 | `backgroundJobs/api.ts` | `jobs` |
| `POST` | `/api/background-jobs/{job_id}/retry` | 重试任务 | W | 高：重放副作用 | `backgroundJobs/api.ts` | `jobs` |
| `GET` | `/api/search` | 全局搜索 | R | 高：可能触发大范围 workbench 构建 | 未确认正式调用；mock 覆盖 | `search` |

### 银行流水明细与分类

| 方法 | 路径 | 当前处理 | 读写 | 风险 | 前端调用 | 未来模块 |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/bank-details/accounts` | 账户余额/流水聚合 | R | 中：聚合查询 | `bankDetails/api.ts` | `bank_details` |
| `GET` | `/api/bank-details/transactions` | 流水列表/分页/关键字 | R | 中：列表查询 | `bankDetails/api.ts` | `bank_details` |
| `PATCH` | `/api/bank-details/transactions/categories` | 手工流水分类 | W | 高：影响工作台、往来款、读模型 | `bankDetails/api.ts` | `bank_details` |

### 工作台、设置、核销和异常

| 方法 | 路径 | 当前处理 | 读写 | 风险 | 前端调用 | 未来模块 |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/workbench` | 月份/all 工作台 | R | 高：可能实时读 OA、构建 read model | `workbench/api.ts` | `workbench` |
| `GET` | `/api/workbench/ignored` | 已忽略行 | R | 中 | `workbench/api.ts` | `workbench` |
| `GET` | `/api/workbench/settings` | 工作台设置 | R | 中：权限/项目/银行映射 | `workbench/api.ts` | `settings` |
| `POST` | `/api/workbench/settings` | 保存设置 | W | 高：权限、项目、OA 导入口径 | `workbench/api.ts` | `settings` |
| `POST` | `/api/workbench/settings/projects/sync` | 同步项目设置 | W | 高：可能依赖 OA/角色同步 | `workbench/api.ts` | `settings` |
| `POST` | `/api/workbench/settings/projects` | 新建手工项目 | W | 中 | `workbench/api.ts` | `settings` |
| `DELETE` | `/api/workbench/settings/projects/{project_id}` | 删除手工项目 | D | 高 | `workbench/api.ts` | `settings` |
| `POST` | `/api/workbench/settings/data-reset/jobs` | 创建数据重置任务 | D | 极高：删除/重建业务数据 | `workbench/api.ts` | `settings` 或 `jobs` |
| `GET` | `/api/workbench/settings/data-reset/jobs/active` | 活跃数据重置任务 | R | 中 | `workbench/api.ts` | `settings` 或 `jobs` |
| `GET` | `/api/workbench/settings/data-reset/jobs/{job_id}` | 数据重置任务详情 | R | 中 | `workbench/api.ts` | `settings` 或 `jobs` |
| `POST` | `/api/workbench/settings/data-reset` | 同步数据重置旧入口 | D | 极高：旧入口，建议收敛 | 未确认正式调用 | `settings` |
| `GET` | `/api/workbench/rows/{row_id}` | 行详情 | R | 中：可能按 row_id 补读 OA | `workbench/api.ts` | `workbench` |
| `POST` | `/api/workbench/exception/preview` | 异常处理预览 | R | 中：复杂规则 | `workbench/api.ts` | `exceptions` |
| `POST` | `/api/workbench/exception/apply` | 应用异常处理 | W | 高：关系/异常/读模型 | `workbench/api.ts` | `exceptions` |
| `POST` | `/api/workbench/actions/confirm-link` | 确认关联 | W | 高：核销核心写 | `workbench/api.ts` | `reconciliation` |
| `POST` | `/api/workbench/actions/confirm-link/preview` | 确认关联预览 | R | 中 | `workbench/api.ts` | `reconciliation` |
| `POST` | `/api/workbench/actions/withdraw-link/preview` | 撤回预览 | R | 中 | `workbench/api.ts` | `reconciliation` |
| `POST` | `/api/workbench/actions/withdraw-link` | 撤回关联 | W | 高：核心状态流转 | `workbench/api.ts` | `reconciliation` |
| `POST` | `/api/workbench/actions/mark-exception` | 标记异常旧动作 | W | 高 | `workbench/api.ts` | `exceptions` |
| `POST` | `/api/workbench/actions/cancel-link` | 取消关联 | W | 高 | `workbench/api.ts` | `reconciliation` |
| `POST` | `/api/workbench/actions/update-bank-exception` | 更新银行异常关系 | W | 高 | `workbench/api.ts` | `exceptions` |
| `POST` | `/api/workbench/actions/oa-bank-exception` | OA/银行异常处理 | W | 高 | `workbench/api.ts` | `exceptions` |
| `POST` | `/api/workbench/actions/confirm-personal-advance-repayment` | 个人垫付还款确认 | W | 高 | `workbench/api.ts` | `reconciliation` |
| `POST` | `/api/workbench/actions/cancel-exception` | 取消异常 | W | 高 | `workbench/api.ts` | `exceptions` |
| `POST` | `/api/workbench/actions/ignore-row` | 忽略行 | W | 高：影响读模型/统计 | `workbench/api.ts` | `workbench` |
| `POST` | `/api/workbench/actions/unignore-row` | 取消忽略 | W | 高：影响读模型/统计 | `workbench/api.ts` | `workbench` |
| `POST` | `/api/workbench/actions/confirm-cash-pass-through` | 现金过账特殊确认 | W | 高 | `workbench/api.ts` | `reconciliation` |
| `POST` | `/api/workbench/actions/confirm-cash-ticket-purchase` | 现金购票特殊确认 | W | 高 | `workbench/api.ts` | `reconciliation` |
| `POST` | `/api/workbench/actions/cancel-cash-special` | 取消现金特殊关系 | W | 高 | `workbench/api.ts` | `reconciliation` |

### 免 OA 银行批次

| 方法 | 路径 | 当前处理 | 读写 | 风险 | 前端调用 | 未来模块 |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/no-oa-bank-batches` | 批次列表/汇总 | R | 中：会刷新批次投影 | `noOaBankBatches/api.ts` | `exceptions` 或 `reconciliation` |
| `GET` | `/api/no-oa-bank-batches/{batch_id}` | 批次详情 | R | 中：会刷新批次投影 | `noOaBankBatches/api.ts` | `exceptions` 或 `reconciliation` |
| `POST` | `/api/no-oa-bank-batches/{batch_id}/submit` | 提交批次 | W | 高：状态流转/工作台重建 | `noOaBankBatches/api.ts` | `exceptions` 或 `reconciliation` |
| `POST` | `/api/no-oa-bank-batches/{batch_id}/withdraw` | 撤回批次 | W | 高：状态流转/工作台重建 | `noOaBankBatches/api.ts` | `exceptions` 或 `reconciliation` |
| `POST` | `/api/no-oa-bank-batches/submit` | 批量提交 | W | 高：批量状态流转 | `noOaBankBatches/api.ts` | `exceptions` 或 `reconciliation` |

### 往来款台账

| 方法 | 路径 | 当前处理 | 读写 | 风险 | 前端调用 | 未来模块 |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/turnover-ledger` | 往来款列表/分组 | R | 中 | `turnoverLedger/api.ts` | `turnover` |
| `GET` | `/api/turnover-ledger/export-preview` | 导出预览 | R | 中 | `turnoverLedger/api.ts` | `turnover` |
| `GET` | `/api/turnover-ledger/export` | Excel 导出 | R | 中：文件响应 | `turnoverLedger/api.ts` | `turnover` |
| `GET` | `/api/turnover-ledger/relations/{relation_id}` | 关系详情 | R | 中 | `turnoverLedger/api.ts` | `turnover` |
| `GET` | `/api/turnover-ledger/relations/{relation_id}/extra` | 利息等扩展信息 | R | 低 | `turnoverLedger/api.ts` | `turnover` |
| `PUT` | `/api/turnover-ledger/relations/{relation_id}/extra` | 更新扩展信息 | W | 中 | `turnoverLedger/api.ts` | `turnover` |
| `POST` | `/api/turnover-ledger/relations/confirm` | 手工确认往来关系 | W | 高：关系写/工作台重建 | `turnoverLedger/api.ts` | `turnover` |
| `POST` | `/api/turnover-ledger/relations/{relation_id}/withdraw` | 撤回手工关系 | W | 高：关系写/工作台重建 | `turnoverLedger/api.ts` | `turnover` |

### 税金抵扣和已认证发票

| 方法 | 路径 | 当前处理 | 读写 | 风险 | 前端调用 | 未来模块 |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/tax-offset` | 月份税金抵扣 | R | 高：依赖发票和 OA 附件发票口径 | `tax/api.ts` | `tax` |
| `POST` | `/api/tax-offset/calculate` | 计算选中抵扣 | R | 中：计算型接口 | `tax/api.ts` | `tax` |
| `POST` | `/api/tax-offset/certified-import/preview` | 已认证发票导入预览 | W | 中：创建预览会话 | `tax/api.ts` | `tax` |
| `POST` | `/api/tax-offset/certified-import/confirm` | 确认已认证发票导入 | W | 高：写认证记录 | `tax/api.ts` | `tax` |
| `GET` | `/api/tax-offset/certified-imports` | 已认证导入记录 | R | 中 | 未确认正式调用；mock 覆盖 | `tax` |

### 成本统计

| 方法 | 路径 | 当前处理 | 读写 | 风险 | 前端调用 | 未来模块 |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/cost-statistics` | 月份成本汇总 | R | 高：依赖工作台/读模型 | `cost-statistics/api.ts` | `cost_statistics` |
| `GET` | `/api/cost-statistics/explorer` | 探索视图 | R | 高：重查询 | `cost-statistics/api.ts` | `cost_statistics` |
| `GET` | `/api/cost-statistics/projects/{project_name}` | 项目下钻 | R | 高：下钻查询 | `cost-statistics/api.ts` | `cost_statistics` |
| `GET` | `/api/cost-statistics/transactions/{transaction_id}` | 流水详情 | R | 中 | `cost-statistics/api.ts` | `cost_statistics` |
| `GET` | `/api/cost-statistics/export-preview` | 导出预览 | R | 高：可能 all-time 汇总 | `cost-statistics/api.ts` | `cost_statistics` |
| `GET` | `/api/cost-statistics/export` | Excel 导出 | R | 高：文件生成/大查询 | `cost-statistics/api.ts` | `cost_statistics` |

### ETC

| 方法 | 路径 | 当前处理 | 读写 | 风险 | 前端调用 | 未来模块 |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/etc/reconciliation-tasks/ready-for-import` | 可导入对账任务 | R | 中 | `etc/api.ts` | `etc` |
| `GET` | `/api/etc/reconciliation-tasks` | 对账任务列表 | R | 中 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/reconciliation-tasks` | 创建对账任务 | W | 中 | `etc/api.ts` | `etc` |
| `GET` | `/api/etc/reconciliation-tasks/{task_id}` | 对账任务详情 | R | 中 | `etc/api.ts` | `etc` |
| `DELETE` | `/api/etc/reconciliation-tasks/{task_id}` | 删除对账任务 | D | 高：删除任务/源文件引用 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/reconciliation-tasks/{task_id}/credit-card-statement` | 上传信用卡账单 | W | 高：文件上传/解析 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/reconciliation-tasks/{task_id}/ticket-root-files` | 上传票根文件 | W | 高：文件上传/解析 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/reconciliation-tasks/{task_id}/ticket-root-texts` | 上传票根文本 | W | 中 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/reconciliation-tasks/{task_id}/supplement-evidences` | 上传补充证据 | W | 高：文件上传/解析 | `etc/api.ts` | `etc` |
| `PATCH` | `/api/etc/reconciliation-tasks/{task_id}/items/{item_id}` | 修改对账项 | W | 高 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/reconciliation-tasks/{task_id}/confirm` | 确认对账任务 | W | 高：生成导入候选/状态流转 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/reconciliation-tasks/{task_id}/reopen` | 重开任务 | W | 高 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/reconciliation-tasks/{task_id}/refresh-matches` | 刷新匹配 | W | 中：可重建匹配 | `etc/api.ts` | `etc` |
| `DELETE` | `/api/etc/reconciliation-tasks/{task_id}/imported-invoices` | 删除已导入发票关联 | D | 高 | `etc/api.ts` | `etc` |
| `DELETE` | `/api/etc/reconciliation-tasks/{task_id}/source-files/{file_id}` | 删除源文件 | D | 高：文件删除 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/import/preview` | ETC ZIP 导入预览 | W | 高：文件上传/预览会话 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/import/confirm` | ETC 导入确认 | W | 高：写 ETC 发票/批次 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/import` | ETC 导入兼容入口 | W | 高：兼容入口 | 未确认正式调用 | `etc` |
| `GET` | `/api/etc/invoices` | ETC 发票列表 | R | 中 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/invoices/revoke-submitted` | 撤销发票提交标记 | W | 高 | `etc/api.ts` | `etc` |
| `GET` | `/api/etc/batches` | ETC 批次列表 | R | 中 | `etc/api.ts` | `etc` |
| `GET` | `/api/etc/batches/{batch_id}` | ETC 批次详情 | R | 中 | `etc/api.ts` | `etc` |
| `DELETE` | `/api/etc/batches/{batch_id}` | 删除 ETC 批次 | D | 高：删除/状态影响 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/batches/draft` | 创建 OA 草稿 | W | 高：外部 OA HTTP 调用，非 MongoOAAdapter | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/batches/{batch_id}/draft` | 为批次创建 OA 草稿 | W | 高：外部 OA HTTP 调用 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/batches/{batch_id}/confirm-submitted` | 确认已提交 | W | 高 | `etc/api.ts` | `etc` |
| `POST` | `/api/etc/batches/{batch_id}/mark-not-submitted` | 标记未提交 | W | 高 | `etc/api.ts` | `etc` |

### 导入、历史工作台和 legacy 路由

| 方法 | 路径 | 当前处理 | 读写 | 风险 | 前端调用 | 未来模块 |
| --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/imports/files/preview` | 多文件导入预览 | W | 高：文件上传/预览会话/GridFS | `imports/api.ts` | `imports` |
| `POST` | `/imports/files/confirm` | 多文件导入确认 | W | 高：写发票/流水/批次 | `imports/api.ts` | `imports` |
| `POST` | `/imports/files/retry` | 导入重试 | W | 高：重跑解析 | `imports/api.ts` | `imports` |
| `GET` | `/imports/files/sessions/{session_id}` | 导入会话详情 | R | 中 | `imports/api.ts` | `imports` |
| `GET` | `/imports/templates` | 模板列表 | R | 低 | `imports/api.ts` | `imports` |
| `GET` | `/imports/batches/{batch_id}` | 导入批次详情 | R | 中 | 未确认正式调用 | `imports` |
| `GET` | `/imports/batches/{batch_id}/download` | 下载原始导入文件 | R | 高：文件流 | 未确认正式调用 | `files` |
| `POST` | `/imports/batches/{batch_id}/revert` | 撤回导入批次 | D | 极高：删除/回滚业务事实 | `imports/api.ts` | `imports` |
| `POST` | `/imports/preview` | 旧导入预览 | W | 高：旧入口 | 未确认正式调用 | `imports` |
| `POST` | `/imports/confirm` | 旧导入确认 | W | 高：旧入口 | 未确认正式调用 | `imports` |
| `POST` | `/matching/run` | 运行匹配 | W | 高：生成匹配结果 | 未确认正式调用 | `workbench` 或 `jobs` |
| `GET` | `/matching/results` | 匹配结果列表 | R | 中 | 未确认正式调用 | `workbench` |
| `GET` | `/matching/results/{result_id}` | 匹配结果详情 | R | 中 | 未确认正式调用 | `workbench` |
| `GET` | `/workbench/prototype` | 原型 HTML | R | 低：legacy | 未确认正式调用 | legacy |
| `GET` | `/workbench` | 旧工作台 payload | R | 高：legacy | 未确认正式调用 | legacy |
| `POST` | `/workbench/actions/confirm` | 旧确认 | W | 高：legacy | 未确认正式调用 | legacy |
| `POST` | `/workbench/actions/difference` | 旧差异处理 | W | 高：legacy | 未确认正式调用 | legacy |
| `POST` | `/workbench/actions/exception` | 旧异常 | W | 高：legacy | 未确认正式调用 | legacy |
| `POST` | `/workbench/actions/offline` | 旧线下处理 | W | 高：legacy | 未确认正式调用 | legacy |
| `POST` | `/workbench/actions/offset` | 旧冲抵 | W | 高：legacy | 未确认正式调用 | legacy |
| `GET` | `/integrations/oa` | OA 集成 dashboard | R | 中：可能读 adapter 状态 | 未确认正式调用 | `oa` |
| `POST` | `/integrations/oa/sync` | OA 同步旧入口 | W | 高：同步状态，不得写 OA 源库 | 未确认正式调用 | `oa` 或 `jobs` |
| `GET` | `/integrations/oa/sync-runs` | OA 同步记录 | R | 中 | 未确认正式调用 | `oa` |
| `GET` | `/integrations/oa/sync-runs/{run_id}` | OA 同步详情 | R | 中 | 未确认正式调用 | `oa` |
| `GET` | `/projects` | 项目 hub | R | 中 | 未确认正式调用 | legacy/projects |
| `POST` | `/projects` | 创建项目 | W | 中 | 未确认正式调用 | legacy/projects |
| `POST` | `/projects/assign` | 项目分配 | W | 高 | 未确认正式调用 | legacy/projects |
| `GET` | `/projects/{project_id}` | 项目详情 | R | 中 | 未确认正式调用 | legacy/projects |
| `GET` | `/ledgers` | 台账列表 | R | 中 | 未确认正式调用 | ledgers |
| `GET` | `/ledgers/{ledger_id}` | 台账详情 | R | 中 | 未确认正式调用 | ledgers |
| `POST` | `/ledgers/{ledger_id}/status` | 更新台账状态 | W | 高 | 未确认正式调用 | ledgers |
| `GET` | `/reminders` | 提醒列表 | R | 中 | 未确认正式调用 | ledgers |
| `POST` | `/reminders/run` | 运行提醒 | W | 中 | 未确认正式调用 | ledgers |
| `GET` | `/reconciliation/cases` | 核销 case 列表 | R | 中 | 未确认正式调用 | reconciliation |
| `GET` | `/reconciliation/cases/{case_id}` | 核销 case 详情 | R | 中 | 未确认正式调用 | reconciliation |

## 前端调用点清单

| 文件 | 调用范围 | 备注 |
| --- | --- | --- |
| `web/src/features/session/api.ts` | `/api/session/me` | 读取 `Admin-Token` cookie 并设置 Authorization。 |
| `web/src/features/appHealth/api.ts` | `/api/oa-sync/status`, `/api/app-health`, `/api/app-health/stream` | health/SSE，带 OA token。 |
| `web/src/features/backgroundJobs/api.ts` | `/api/background-jobs/active`, `/{job_id}/acknowledge`, `/{job_id}/retry` | 任务确认/重试是写操作。 |
| `web/src/features/workbench/api.ts` | `/api/workbench`, `/api/workbench/ignored`, `/api/workbench/settings*`, `/api/workbench/rows/{id}`, `/api/workbench/actions/*`, `/api/workbench/exception/*`, `/api/oa-sync/status` | 工作台主 client，覆盖读模型、设置、关系、异常、忽略、特殊核销。 |
| `web/src/features/bankDetails/api.ts` | `/api/bank-details/accounts`, `/api/bank-details/transactions`, `/api/bank-details/transactions/categories` | 分类更新会触发工作台和往来款相关副作用。 |
| `web/src/features/noOaBankBatches/api.ts` | `/api/no-oa-bank-batches*` | 免 OA 批次列表、详情、提交、撤回、批量提交。 |
| `web/src/features/turnoverLedger/api.ts` | `/api/turnover-ledger*` | 往来款列表、导出、关系详情、扩展信息、确认/撤回。 |
| `web/src/features/imports/api.ts` | `/imports/files/*`, `/imports/templates`, `/imports/batches/{id}/revert` | 注意不是 `/api` 前缀；使用 `apiUrl()` 解析部署前缀。 |
| `web/src/features/tax/api.ts` | `/api/tax-offset*` | 税金抵扣、已认证发票预览/确认。 |
| `web/src/features/cost-statistics/api.ts` | `/api/cost-statistics*` | 月汇总、探索、项目/流水下钻、导出预览和文件导出。 |
| `web/src/features/etc/api.ts` | `/api/etc/*` | ETC 对账任务、文件上传、ZIP 导入、发票/批次、OA 草稿、提交标记。 |
| `web/src/test/apiMock.ts` | 多数 `/api` 和 `/imports` 路由 mock | 可作为前端契约测试参考，但不是后端事实源。 |

未在正式 API client 中确认到调用的现有后端路由包括 `/api/search`、旧 `/workbench/*`、`/integrations/oa/*`、`/projects*`、`/ledgers*`、`/reminders*`、`/reconciliation/cases*`、旧 `/imports/preview`、旧 `/imports/confirm`、`/matching/*`。迁移前需确认是否仍有页面、外部脚本或 OA iframe 菜单依赖。

## 业务模块边界

| 模块 | 当前入口/服务 | 主要依赖 | 未来边界建议 |
| --- | --- | --- | --- |
| auth/session | `app/auth.py`, `OAIdentityService`, `AccessControlService`, `/api/session/me` | OA token、动态用户名设置、权限 tier | 独立 `auth` middleware + `routes/auth.rs`；所有写操作统一要求 actor、trace id。 |
| settings | `/api/workbench/settings*`, `AppSettingsService`, `SettingsDataResetService` | `app_settings`, OA role sync, project costing, data reset, derived lifecycle | `routes/settings.rs`；数据重置走 job command，不直接在普通请求中做重任务。 |
| imports/files | `/imports/files/*`, `/imports/batches/*`, `ImportNormalizationService`, `FileImportService` | `import_batches`, `invoices`, `bank_transactions`, `file_import_*`, GridFS, background jobs | `routes/imports.rs` + `routes/files.rs`；文件对象先迁 MinIO/S3，确认动作幂等。 |
| bank details | `/api/bank-details/*`, `BankDetailsService`, category services | imports facts, category overrides, relation tag projection, read model provider | `routes/bank_details.rs`；分类写入 PostgreSQL 事实和 outbox，读用索引/投影。 |
| workbench | `/api/workbench`, row detail, ignored rows, `WorkbenchQueryService`, `LiveWorkbenchService` | OA adapter, imports, pair relations, overrides, read models, candidate matches, dirty scopes | `routes/workbench.rs`；请求路径只读 `read_model.workbench_rows/snapshots`，OA 同步异步化。 |
| reconciliation | workbench confirm/withdraw/cancel/special actions, legacy `/reconciliation/cases*` | pair relations, amount checks, exceptions, audit, read model invalidation | `routes/reconciliation.rs`；事务内写 case/case_rows/audit/outbox。 |
| exceptions | `/api/workbench/exception/*`, mark/cancel/update bank exception, no-OA batches | exception cases, overrides, pair relations, no-OA batches/audit, read model invalidation | `routes/exceptions.rs`；异常 case 作为核心事实迁移。 |
| tax/ETC | `/api/tax-offset*`, `/api/etc/*`, tax/ETC services | invoices, certified imports, ETC state, ETC reconciliation state/files, OA attachment invoice cache | `routes/tax.rs`, `routes/etc.rs`；税金 read model 可重建，ETC 文件迁对象存储。 |
| cost statistics | `/api/cost-statistics*`, `CostStatisticsService`, read model service | workbench grouped/raw loaders, project settings, cost read models, export generation | `routes/cost_statistics.rs`；查询读 read model，导出走后台任务或限流。 |
| turnover | `/api/turnover-ledger*`, `TurnoverLedgerService`, `TurnoverRelationService` | bank transactions, categories, turnover relations/audit/extras, workbench invalidation | `routes/turnover.rs`；关系写入 PostgreSQL 事实，导出读取投影。 |
| health/jobs | `/api/app-health*`, `/api/background-jobs*`, data reset jobs | background_jobs, app_health_alerts, OA sync state, dirty scopes | `routes/health.rs`, `routes/jobs.rs`；任务状态进入 `job.worker_tasks`。 |
| OA adapter | `MongoOAAdapter`, `IntegrationHubService`, `WorkbenchQueryService` | OA Mongo read-only `form_data` 默认集合、app-side cache | adapter 不进入业务写事务；同步 worker 读 OA 后写 PostgreSQL 归一化表。 |

## app Mongo collection 清单

### 元数据、兼容快照和基础状态

| collection / bucket | 状态对象 | 类型 | payload 格式 | 迁移建议 |
| --- | --- | --- | --- | --- |
| `application_state` | legacy full snapshot | 历史兼容 | `payload` pickle | 迁移期只作回滚参考；不作为目标事实源。 |
| `imports_state` | split `imports` | 历史兼容 | `payload` pickle | 由 detailed collections 取代，归档。 |
| `file_import_sessions_state` | split `file_imports` | 历史兼容 | `payload` pickle | 由 detailed collections 取代，归档。 |
| `matching_state` | split `matching` | 历史兼容 | `payload` pickle | 由 detailed collections 取代，归档。 |
| `app_state_meta` | store metadata | 元数据 | 文档字段 | 迁移 manifest 参考。 |
| `import_file_metadata` | 文件导入元摘要 | 文件元数据摘要 | `payload` pickle | 用于导出清单参考，目标进入 `app.file_objects`/`app.import_files`。 |
| `app_settings` | `AppSettingsService` snapshot | 配置/权限 | 字段 + `payload` pickle | 迁入 PostgreSQL settings 表，权限字段需单独审计。 |

### 导入、发票、银行流水和匹配

| collection | 状态对象 | 类型 | payload 格式 | 迁移建议 |
| --- | --- | --- | --- | --- |
| `imports_meta` | imports meta | 元数据 | `payload` pickle | 导入 staging 参考。 |
| `import_batches` | `imports.batches` | 核心事实/导入批次 | 字段 + `payload` pickle | 迁入 `app.import_batches`。 |
| `invoices` | `imports.invoices` | 核心事实 | 字段 + `payload` pickle | 迁入 `app.invoices`，金额/日期枚举校验。 |
| `bank_transactions` | `imports.transactions` | 核心事实 | 字段 + `payload` pickle | 迁入 `app.bank_transactions`，按月份/日期分区。 |
| `bank_transaction_categories_meta` | categories meta | 元数据 | `payload` pickle | 随分类事实迁移。 |
| `bank_transaction_categories` | transaction category overrides | 核心事实/覆盖 | 字段 + `payload` pickle | 迁入 `app.bank_transaction_categories` 和事件表。 |
| `file_imports_meta` | file imports meta | 元数据 | `payload` pickle | 随导入会话迁移。 |
| `file_import_sessions` | file import sessions | 导入会话 | 字段 + `payload` pickle | 迁入 `app.import_batches`/`app.import_files` 或 staging。 |
| `file_import_files` | file import files | 文件元数据/解析结果 | 字段 + `payload` pickle，含 `stored_file_path` | 迁入 `app.import_files` + `app.file_objects`。 |
| `matching_meta` | matching meta | 元数据 | `payload` pickle | 迁移为任务/审计或归档。 |
| `matching_runs` | matching runs | 任务/历史结果 | 字段 + `payload` pickle | 可迁入 `job.worker_tasks` 或归档为审计。 |
| `matching_results` | matching results | 候选/历史结果 | 字段 + `payload` pickle | 目标建议由 read model/candidate matches 重建。 |

### 工作台、异常、核销和免 OA

| collection | 状态对象 | 类型 | payload 格式 | 迁移建议 |
| --- | --- | --- | --- | --- |
| `workbench_overrides_meta` | overrides meta | 元数据 | `payload` pickle | 随覆盖事实迁移。 |
| `workbench_row_overrides` | row overrides | 核心覆盖事实 | `payload` pickle | 迁入 `app.workbench_row_overrides`。 |
| `workbench_exception_cases_meta` | exception cases meta | 元数据 | `payload` pickle | 随异常事实迁移。 |
| `workbench_exception_cases` | exception cases | 核心事实 | 字段 + `payload` pickle | 迁入 `app.workbench_exception_cases`。 |
| `workbench_pair_relations_meta` | pair relations meta | 元数据 | `payload` pickle | 随核销事实迁移。 |
| `workbench_pair_relations` | pair relations | 核销核心事实 | 字段 + `payload` pickle | 迁入 `app.reconciliation_cases` 和 `app.reconciliation_case_rows`。 |
| `workbench_read_models_meta` | workbench read model meta | 读模型元数据 | `payload` pickle | 不作为事实迁移；目标可重建。 |
| `workbench_read_models` | workbench snapshots | 读模型/缓存 | 字段 + `payload` pickle | 迁移期可比对；目标 `read_model.workbench_*` 重建。 |
| `workbench_candidate_matches_meta` | candidate meta | 读模型元数据 | `payload` pickle | 随候选 read model 或重建。 |
| `workbench_candidate_matches` | candidate matches | 读模型/候选 | 字段 + `payload` pickle | 目标 `read_model.workbench_candidate_matches`。 |
| `workbench_matching_dirty_scopes_meta` | dirty scopes meta | 任务元数据 | `payload` pickle | 迁入 `job.worker_tasks` 或 outbox。 |
| `workbench_matching_dirty_scopes` | dirty scopes | 任务状态 | 字段 + `payload` pickle | 迁入 `job.worker_tasks` 或 outbox。 |
| `no_oa_bank_batches_meta` | no-OA meta | 元数据 | `payload` pickle | 随批次迁移。 |
| `no_oa_bank_batches` | no-OA batches | 核心事实/状态 | 字段 + `payload` pickle | 迁入 `app.no_oa_bank_batches`。 |
| `no_oa_bank_batch_audit_log` | no-OA audit | 审计 | 字段 + `payload` pickle | 迁入 `audit.events`。 |

### 往来款、统计、税金和 OA side cache

| collection | 状态对象 | 类型 | payload 格式 | 迁移建议 |
| --- | --- | --- | --- | --- |
| `turnover_relations_meta` | turnover meta | 元数据 | `payload` pickle | 随往来关系迁移。 |
| `turnover_relations` | turnover relations | 核心事实 | 字段 + `payload` pickle | 迁入 `app.turnover_relations`。 |
| `turnover_relation_audit_log` | turnover audit | 审计 | 字段 + `payload` pickle | 迁入 `audit.events`。 |
| `turnover_ledger_extras_meta` | ledger extras meta | 元数据 | `payload` pickle | 随扩展信息迁移。 |
| `turnover_ledger_extras` | ledger extras | 核心/扩展事实 | 字段 + `payload` pickle | 迁入 turnover 扩展表。 |
| `cost_statistics_read_models_meta` | cost read model meta | 读模型元数据 | `payload` pickle | 不作为事实迁移；可重建。 |
| `cost_statistics_read_models` | cost read models | 读模型/缓存 | 字段 + `payload` pickle | 目标 `read_model.cost_statistics_read_models` 重建。 |
| `tax_offset_read_models_meta` | tax read model meta | 读模型元数据 | `payload` pickle | 不作为事实迁移；可重建。 |
| `tax_offset_read_models` | tax read models | 读模型/缓存 | 字段 + `payload` pickle | 目标 `read_model.tax_offset_read_models` 重建。 |
| `oa_attachment_invoice_cache` | OA 附件发票解析 cache | app-side cache | 字段 + `payload` pickle | app cache，可重建；不得视为 OA 源备份。 |
| `oa_sync_state` | OA sync fingerprints/status | 同步状态 | `payload` pickle | 迁入 `app.oa_sync_*` 或 `job` 水位；只存 app 侧水位。 |

### 税金认证、ETC、任务和健康

| collection | 状态对象 | 类型 | payload 格式 | 迁移建议 |
| --- | --- | --- | --- | --- |
| `tax_certified_imports_meta` | certified import meta | 元数据 | `payload` pickle | 随认证导入迁移。 |
| `tax_certified_import_sessions` | certified sessions | 导入会话 | 字段 + `payload` pickle | 迁入 `app.import_batches`/tax staging。 |
| `tax_certified_import_batches` | certified batches | 核心事实/批次 | 字段 + `payload` pickle | 迁入税金认证批次表。 |
| `tax_certified_import_records` | certified records | 核心事实 | 字段 + `payload` pickle | 迁入 `app.invoice_certifications` 或目标认证表。 |
| `etc_state` | ETC service snapshot | 核心/状态混合 | `payload` pickle | 需拆分 ETC 发票、批次、提交状态和文件引用。 |
| `etc_reconciliation_state` | ETC reconciliation tasks | 任务/状态 | `payload` pickle | 迁入 `job.worker_tasks` + ETC staging/facts。 |
| `historical_etc_repair_bundles` | historical repair bundles | 文件元数据/修复输入 | 字段 + GridFS ref | 文件迁 MinIO/S3，元数据归档或 staging。 |
| `historical_etc_repair_parsed_seeds` | parsed repair seeds | 修复中间结果 | `payload` pickle | 待确认是否仍需迁移；默认归档。 |
| `historical_etc_repair_states` | repair states | 修复任务状态 | `payload` pickle | 迁入 job/audit 或归档。 |
| `background_jobs` | background job snapshots | 任务状态 | 字段 + `payload` pickle | 迁入 `job.worker_tasks`/attempts。 |
| `app_health_alerts` | health alerts | 运维告警状态 | `payload` pickle | 迁入 audit/ops alerts，或接入监控系统。 |
| `import_file_blobs.files/chunks` | GridFS bucket | 文件二进制 | GridFS | 迁移到 MinIO/S3，保留 checksum 和旧 id 映射。 |

## GridFS 文件路径清单

GridFS bucket：`import_file_blobs`。存储引用格式：`gridfs://{file_id}/{file_name}`。

| 使用点 | 代码路径 | GridFS id / metadata | 文件类型 | 迁移目标 |
| --- | --- | --- | --- | --- |
| 导入原始文件 | `ApplicationStateStore.store_import_file`, `FileImportService._store_upload_file` | id 为导入 file_id；metadata 含 `session_id`, `file_id`, `file_name`, `stored_at` | Excel/导入源文件 | MinIO/S3 `imports/{yyyy}/{mm}/{file_object_id}/...` + `app.file_objects`。 |
| 导入文件读取/下载 | `read_import_file`, `/imports/batches/{id}/download` | 读取 `stored_file_path` | 原始导入文件 | 文件 API 从对象存储读取，PostgreSQL 只存元数据。 |
| 导入文件删除 | `delete_import_files`, `SettingsDataResetService` | 删除 GridFS ref | 银行流水/发票导入文件 | 重置操作需软删除或审计删除；迁移前保留 GridFS 归档。 |
| ETC 对账源文件 | `store_etc_reconciliation_file`, `EtcReconciliationTaskService.store_uploaded_source_file` | `etc_reconciliation:{task_id}:{file_id}`；metadata purpose=`etc_reconciliation_source` | 信用卡账单、票根文件、补充证据 | MinIO/S3 attachments/imports，任务状态保留 object key。 |
| ETC 对账源文件读取/删除 | `read_etc_reconciliation_file`, `_handle_api_etc_reconciliation_source_file_delete` | `gridfs://...` | ETC 对账源文件 | 删除需走对象存储版本化或审计删除。 |
| ETC 发票附件 | `store_etc_invoice_file`, `EtcService._store_invoice_file` | `etc_invoice:{invoice_number}:{sanitized_name}`；metadata purpose=`etc_invoice_attachment` | ETC invoice XML/PDF | MinIO/S3 attachments，`app.file_objects` 记录 checksum、content type、旧 id。 |
| ETC 发票附件检查/删除 | `etc_invoice_file_exists`, `delete_etc_invoice_file`, `EtcService` | `gridfs://...` | XML/PDF | 用对象存储 HEAD/DELETE 或软删除替代。 |
| 历史 ETC 修复包 | `save_historical_etc_repair_bundle`, `read_historical_etc_repair_bundle` | `historical_etc_repair:{bundle_id}`；metadata purpose=`historical_etc_repair_seed` | 历史修复输入包 | 迁移到归档 bucket 或 staging；业务是否仍需要待确认。 |
| 本地文件迁移到 GridFS helper | `ApplicationStateStore._migrate_legacy_file_refs_to_gridfs` | 将 local `stored_file_path` 转 GridFS ref | 历史 local 文件 | PostgreSQL 迁移不应再依赖该方向；仅作为读取旧格式参考。 |

## OA adapter 只读边界

当前 OA Mongo adapter：

- 类：`backend/src/fin_ops_platform/services/mongo_oa_adapter.py` 的 `MongoOAAdapter`。
- 配置：`FIN_OPS_OA_MONGO_*` 或 `oa_mongo_config.json`。
- 默认 collection：`form_data`。
- 读取 form：支付申请 `payment_request_form_id` 默认 `2`，日常报销 `expense_claim_form_id` 默认 `32`，项目 `project_form_id` 默认 `17`。
- 已确认 adapter 内部使用 `MongoClient(...)[database][collection].find(...)` 读取，未看到对 OA Mongo 的 insert/update/delete。
- adapter 会缓存 records、available months、项目名称和附件发票解析结果；附件发票解析 cache 写入的是 app Mongo 的 `oa_attachment_invoice_cache`，不是 OA 源库。

只读底线：

- 不得对 OA 源库执行备份、导出、聚合迁移、写入、修复、清理或索引变更。
- Mongo 到 PostgreSQL 迁移只针对 app Mongo；OA 源数据只通过既有只读 adapter 或后续只读同步 worker 读取后归一化进入 PostgreSQL。
- `MongoOAAdapter` 的 app-side cache、水位和解析结果可以迁移或重建，但不能被描述为 OA 源库备份。
- ETC `HttpEtcOAClient` 创建 OA 草稿属于外部 OA HTTP 集成，和 `MongoOAAdapter` 的只读 Mongo 边界不同；迁移时需单独做权限、审计和幂等设计。

当前可能在请求路径触发 OA 读取的入口：

- `GET /api/workbench?month=...`：`WorkbenchQueryService` 通过 adapter 拉取 OA rows；`month=all` 有 retained all scope 特殊逻辑。
- `GET /api/workbench/rows/{row_id}`：行详情可能按 row id 补同步 OA row。
- `GET /api/workbench/ignored?month=...`：构建工作台忽略行时依赖工作台数据。
- `GET /api/search`：通过 grouped/ignored workbench loader 搜索，可能触发工作台构建。
- `GET /api/cost-statistics*`：成本统计服务依赖 workbench grouped/raw loader。
- `GET /api/tax-offset`：税金抵扣使用 OA 附件发票 rows loader。
- `POST /api/workbench/settings/data-reset/jobs`：重置/重建路径会解析 OA 附件发票、列出可用月份。
- `POST /integrations/oa/sync` 和 OA polling worker：会通过 `poll_sync_fingerprints`、`list_available_months` 或 records 读取 OA。

目标状态建议：

- 页面请求不实时扫描 OA Mongo；由 worker 按水位或指定月份读取 OA，写入 PostgreSQL `app.oa_applications`、`app.oa_application_items`、`app.oa_attachments`。
- API 只读 PostgreSQL facts/read models；OA read status 由 `app.oa_sync_runs`/`job.worker_tasks` 提供。

## 迁移批次建议

| 批次 | 范围 | 原因 | 前置/验收 |
| --- | --- | --- | --- |
| 0. 契约冻结和导出工具 | 路由契约、前端 client fixture、app Mongo export manifest | 先固定现有行为，避免迁移期间猜字段 | 生成 API 合约样本；导出不含 secret；不接触 OA 源库备份。 |
| 1. 低风险读接口 | `/health`, `/api/session/me`, `/api/app-health`, `/api/oa-sync/status`, `/api/background-jobs/active`, settings 只读 | 依赖少，可先建立 Axum middleware、鉴权、响应错误格式 | 与 Python 响应做样本对比；权限失败路径覆盖。 |
| 2. 文件元数据和对象存储 | `file_import_files`, GridFS 导入文件、ETC 文件、historical repair bundles | 文件迁移影响面大但业务写关系相对清晰 | MinIO/S3 checksum、旧 GridFS id 映射、抽样下载验证。 |
| 3. 导入事实和基础主数据 | `import_batches`, `invoices`, `bank_transactions`, tax certified records, bank categories | 后续工作台、税金、成本统计都依赖这些事实 | 数量、金额、月份、状态分布对账；金额用 numeric。 |
| 4. 任务和 read model 基础设施 | `background_jobs`, dirty scopes, outbox, worker tasks, read model rebuild | 为后续高风险读写提供异步重建能力 | outbox 与业务事务同提交；任务 retry/dead-letter 可验证。 |
| 5. 可重建读模型 | workbench/cost/tax candidate/read models/search index | 先建立读路径，旧 Mongo read model 只用于比对 | read model 可从事实重建；P95/P99 和 EXPLAIN 有记录。 |
| 6. 工作台读接口 | `/api/workbench`, row detail, ignored, bank details, cost/tax reads | 页面高频读，迁移后应去实时 OA 扫描 | 与旧页面样本对比；all-time 限流或异步。 |
| 7. 核销/异常/免 OA/往来写操作 | workbench actions, exception apply, no-OA submit/withdraw, turnover confirm/withdraw, category PATCH | 核心业务状态，必须事务、幂等、审计 | PostgreSQL 事务写 facts + audit + outbox；撤回不物理删除。 |
| 8. 导入确认、批次撤回和数据重置 | `/imports/files/confirm`, `/imports/batches/{id}/revert`, data reset jobs | 高风险 destructive/批量动作 | 演练回滚；权限、审计、幂等、补偿脚本齐全。 |
| 9. ETC 写操作和 OA 草稿 | ETC import confirm、batch delete/status、OA draft | 涉及文件、外部 OA HTTP、提交状态 | 外部调用隔离、幂等 key、失败补偿和审计。 |
| 10. legacy route 收敛 | 旧 `/workbench`, `/integrations/oa`, `/projects`, `/ledgers`, `/reminders`, `/matching`, `/imports/preview` | 防止双入口长期漂移 | 确认无 OA 菜单/脚本依赖后下线或转发到新 API。 |

## 风险和待确认问题

风险：

- app Mongo detailed collections 大量使用 Python pickle payload；不能用手写 BSON/pickle 猜解析，必须复用 `ApplicationStateStore` 或业务 service 导出规范化 JSON/NDJSON。
- `/api/workbench`, `/api/search`, `/api/cost-statistics*`, `/api/tax-offset` 当前可能在请求路径触发 OA 读取或重建，直接迁移成同步 SQL 聚合会复制造成高延迟风险。
- GridFS 文件与业务状态耦合在 `stored_file_path` 和 pickle payload 中；迁移需先建立文件 manifest、checksum、旧 id 到新 object key 映射。
- 数据重置、批次撤回、ETC 删除、后台任务 retry 是高风险操作，目标系统必须有权限、审计、幂等和回滚/补偿路径。
- legacy 路由仍在后端保留，前端正式 client 未确认调用；外部 OA iframe 菜单或运维脚本可能仍依赖，不能直接删除。
- ETC OA 草稿创建不是 MongoOAAdapter 只读范围，属于外部写集成；需要与 OA 权限、幂等和失败补偿单独对齐。
- read model 旧缓存不应作为事实迁移，但需要在切读前用旧页面样本对比口径，否则成本统计、税金抵扣和工作台分组可能出现可见差异。

待确认：

- `/api/search` 是否有正式页面入口，或仅剩测试 mock。
- 旧 `/workbench/*`、`/integrations/oa/*`、`/projects*`、`/ledgers*`、`/reminders*`、`/matching/*` 是否仍被 OA 菜单、外部脚本或人工运维使用。
- `historical_etc_repair_*` 是否仍需迁移为可操作功能，还是仅归档保留。
- `etc_state` pickle 内部对象拆分到目标 PostgreSQL 表的最终边界，需要从 `EtcService.snapshot()` 和产品口径确认。
- `workbench_pair_relations` 是否允许同一 row 在多个 active case 中存在多关系；目标唯一约束需要产品确认。
- 导入批次撤回、数据重置、ETC 删除的生产权限角色和审批流程需确认。
- 前端各 API client 中部分 request 未统一走 `apiUrl()`；部署到 `/fin-ops-api/` 时是否完全由 Vite/Nginx 代理兜底需确认。
- 目标 Axum 是否保留旧非 `/api` 路由兼容期，还是通过 Nginx 转发到新 `/api` 路由。

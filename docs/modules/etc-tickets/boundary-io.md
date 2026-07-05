# ETC票据管理模块边界与 I/O

日期：2026-07-05

## 模块化状态

- 状态：close
- 当前边界可信度：high
- 目标边界：ETC 票据页面和导入/修复服务通过 ETC application/reconciliation services 处理业务，关联影响通过 workbench relation 和 derived lifecycle 扇出。
- 当前缺口：无页面/API 主链路闭环缺口；历史 repair/migration/backfill 工具作为显式运维入口保留，必须继续 dry-run/owner/allowlist 管控，不得进入常规页面链路。
- 旧代码删除条件：已删除 legacy `/api/etc/batches*`、ETC OA 自动检测 refresh、invoice-id 级 `/api/etc/invoices/revoke-submitted` 回退入口及测试 mock 假后端；历史 ETC migration/repair 工具在完成生产迁移职责且无生产/测试引用后再单独删除。

## 职责边界

### 负责

- ETC 票据管理页面、ETC 发票/批次、识别、对账、历史批次修复。
- ETC 与发票附件、关联台候选之间的业务转换。
- 通过 lifecycle 触发 workbench/invoice/search 相关刷新。

### 不负责

- 不直接拥有 workbench relation 事实源。
- 不直接维护 pending invoice 或 tax offset read model。
- 不在导入流程外绕过 ETC service 写批次。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/操作 | `EtcTicketManagementPage.tsx`、`features/etc/api.ts` | 进入 ETC routes/services；批次列表不发送月份筛选，只按状态 bucket、车牌、关键词读取全部用户可见 business batches；已导入任务详情通过 `/api/etc/invoices?importBatchId=...` 读取 canonical ETC invoice list |
| 批次标题编辑 | `EtcTicketManagementPage.tsx`、`PATCH /api/etc/business-batches/{id}` | 只允许未提交 business batch 修改 `title`；请求带 `expectedVersion`，后端持久化 business batch title 并同步 linked reconciliation task title |
| ETC 发票导入/识别 | imports/services/parsers | 输出批次、任务、附件识别结果 |
| ETC invoice list | `GET /api/etc/invoices` | 只读查询入口；route owner 只接收 `etc_service`、`json_response`、`serialize_invoice` 三个读侧端口，不接收 JSON body、link refresh 或状态回退端口 |
| 历史修复/迁移 | tools | 只作为显式运维入口 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| ETC ticket/batch payload | 前端页面 | API response shape 稳定，business batch payload 包含用户可见 `title` |
| linked reconciliation task title | ETC 发票导入 ready task 下拉 | business batch title 更新后同步 task title，导入页下拉展示最新批次标题 |
| 关联候选/关系影响 | workbench relation/lifecycle | 不直接写下游 read model |
| 修复/迁移结果 | 运维工具 | 可审计、可回滚或可重复 |
| Completed import job consumption | background job progress / operation barrier | ETC 发票导入 job 完成后，页面必须读取 job `operation_barrier_targets`，等待 targets fresh 后再刷新批次和任务列表 |

## 持久化与投影

- Own read model：无独立 manifest entry。
- 影响 read model：`workbench`、`workbench_relation`、`invoice_lifecycle`、`search` 等。
- ETC 导入完成消费会额外等待 `tax_offset`、`input_invoice_usage`、`pending_invoice`、`oa_pending_payment`、`cost_statistics` 等 job result targets。
- Worker：通过 import/runtime handler、derived lifecycle 和 registered workers 扇出。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/EtcTicketManagementPage.tsx` |
| Frontend feature/components | `web/src/features/etc/*`、`web/src/components/workbench/CandidateGroupGrid.tsx` |
| Backend route | `routes_etc.py`、`routes_etc_import.py`、`routes_etc_invoices.py`、`routes_etc_reconciliation.py` |
| Backend service | `etc_service.py`、`etc_business_batch_application_service.py`、`etc_reconciliation_*`、`invoice_attachment_recognition_service.py` |
| Workbench integration | `workbench_sql_projection.py`、`workbench_pair_relation_service.py`、`workbench_relation_command_service.py` |
| Tools | `cleanup_orphan_etc_reconciliation_tasks.py`、`migrate_historical_etc_business_batches.py`、`link_existing_etc_batches.py` |
| Tests | `tests/test_etc_*.py`、`web/src/test/Etc*.test.*`、`web/e2e/etc-tickets-flow.spec.ts` |

## 依赖方向

- 允许依赖：ETC parsers, invoice attachment recognition, workbench relation, derived lifecycle。
- 必须通过：ETC application/reconciliation services。
- 禁止绕过：修复工具直接成为常规业务写路径；页面直接操作历史批次状态；任何代码重新暴露 legacy `/api/etc/batches*`、`/api/etc/business-batches/{id}/oa-status/refresh` 或 `/api/etc/invoices/revoke-submitted`。

## 测试与验证

- `tests/test_etc_backend.py`
- `tests/test_etc_reconciliation_service.py`
- `tests/test_import_processing_service.py`
- `web/src/test/EtcTicketManagementPage.test.tsx`
- `web/e2e/etc-tickets-flow.spec.ts`

## 当前缺口和删除条件

- 历史 migration/repair service 必须保留删除条件。
- ETC 变更必须检查 workbench candidate 和 invoice lifecycle fan-out。

## Canonical facts ownership

- Owned facts: `app.etc_invoices`、`app.etc_import_sessions`、`app.etc_import_batches`、`app.etc_submission_batches`、`app.etc_business_batches`、`app.etc_reconciliation_tasks`、`app.etc_reconciliation_files`、`app.historical_etc_repair_*`、`app.etc_batch_invoice_links`。
- Shared facts: `app.invoices` 由 canonical invoice pool owner 管理；ETC 只能通过受控 link/promotion port 关联。
- Allowed writes: ETC import service/job、business batch service、reconciliation service、受控 historical repair/backfill tools。
- Allowed reads: ETC business batch API、ETC services、canonical invoice existing-link ports。
- Downstream outputs: workbench、workbench_relation、tax/cost/search dirty scopes 或 owner producer 输出。
- Forbidden paths: legacy ETC batch pickle、OA detection metadata 或 ETC invoice rows 不得替代 canonical invoice pool；ETC repair 不得绕过 relation command service。
- Old code deletion: 生产主链路的 legacy `/api/etc/batches*` source-of-truth fallback、route owner、read facade、delete/lifecycle service、前端测试 mock 假后端和后端兼容测试已删除；页面已导入任务详情改走 `/api/etc/invoices?importBatchId=...`。ETC 专用 `oa-status/refresh` 和 invoice-id 级 `/api/etc/invoices/revoke-submitted` 回退入口已删除，并由 static guard 防回归。historical repair/backfill 工具保留不算页面/API closure 阻断，仍需按工具 owner/dry-run/deletion 条件单独收口。

# ETC票据管理模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：ETC 票据页面和导入/修复服务通过 ETC application/reconciliation services 处理业务，关联影响通过 workbench relation 和 derived lifecycle 扇出。
- 当前缺口：ETC 历史批次、修复、迁移工具和 workbench 投影耦合多，删除旧代码必须逐工具核验。
- 旧代码删除条件：历史 ETC migration/repair 工具完成迁移职责且无生产/测试引用。

## 职责边界

### 负责

- ETC 票据管理页面、ETC 发票/批次、识别、对账、历史批次修复。
- ETC 与发票附件、关联台候选之间的业务转换。
- 通过 lifecycle 返回 affected scope/job diagnostics，供 workbench/invoice/search 相关 direct API 重读。

### 不负责

- 不直接拥有 workbench relation 事实源。
- 不直接维护 pending invoice 或 tax offset direct payload。
- 不在导入流程外绕过 ETC service 写批次。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/操作 | `EtcTicketManagementPage.tsx`、`features/etc/api.ts` | 进入 ETC routes/services |
| ETC 发票导入/识别 | imports/services/parsers | 输出批次、任务、附件识别结果 |
| 历史修复/迁移 | tools | 只作为显式运维入口 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| ETC ticket/batch payload | 前端页面 | API response shape 稳定 |
| 关联候选/关系影响 | workbench relation/lifecycle | 不直接写下游页面投影；下游页面 direct API 重读 |
| 修复/迁移结果 | 运维工具 | 可审计、可回滚或可重复 |
| Completed import job consumption | background job progress / direct ETC GET | ETC 发票导入 job 完成后，页面发出 ETC/invoice domain event，并直接重读业务批次和任务列表；不再等待 `/api/operation-barrier/status` 或 job target fields |

## 持久化与投影

- Own page read model：无；无独立 manifest entry。
- 下游 direct payload：`workbench`、`workbench_relation`、`invoice_lifecycle` 等通过 affected scope/job diagnostics 重读；Search 不再是 refresh/read model target，只受 direct search payload 影响。
- ETC 票据页面不负责等待 `tax_offset`、`input_invoice_usage`、`pending_invoice`、`oa_pending_payment`、`cost_statistics` 等下游页面派生数据 target；下游页面按各自 direct API/read boundary 重新读取。
- Worker：通过 import/runtime handler、derived lifecycle 和 registered workers 扇出。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/EtcTicketManagementPage.tsx` |
| Frontend feature/components | `web/src/features/etc/*`、`web/src/components/workbench/CandidateGroupGrid.tsx` |
| Backend route | `routes_etc.py`、`routes_etc_import.py`、`routes_etc_invoices.py`、`routes_etc_legacy_batches.py`、`routes_etc_reconciliation.py` |
| Backend service | `etc_service.py`、`etc_business_batch_application_service.py`、`etc_reconciliation_*`、`etc_legacy_batch_*`、`invoice_attachment_recognition_service.py` |
| Workbench integration | `workbench_query_service.py`、`workbench_pair_relation_service.py`、`workbench_relation_command_service.py` |
| Tools | `cleanup_orphan_etc_reconciliation_tasks.py`、`migrate_historical_etc_business_batches.py`、`link_existing_etc_batches.py` |
| Tests | `tests/test_etc_*.py`、`web/src/test/Etc*.test.*`、`web/e2e/etc-tickets-flow.spec.ts` |

## 依赖方向

- 允许依赖：ETC parsers, invoice attachment recognition, workbench relation, derived lifecycle。
- 必须通过：ETC application/reconciliation services。
- 禁止绕过：修复工具直接成为常规业务写路径；页面直接操作历史批次状态。

## 测试与验证

- `tests/test_etc_backend.py`
- `tests/test_etc_reconciliation_service.py`
- `tests/test_etc_legacy_batch_lifecycle_service.py`
- `tests/test_import_processing_service.py`
- `web/src/test/EtcTicketManagementPage.test.tsx`
- `web/e2e/etc-tickets-flow.spec.ts`

## 当前缺口和删除条件

- 历史 migration/repair service 必须保留删除条件。
- ETC 变更必须检查 workbench candidate 和 invoice lifecycle fan-out。

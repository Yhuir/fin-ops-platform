# ETC 票据

入口：`/etc-tickets`。

管理 ETC 业务批次、对账任务、信用卡与票根证据、票据附件和 OA 草稿。

## 边界与 I/O

输入：unsubmitted/staged/submitted bucket、服务端页码、精确 batch/task ID、版本、稳定草稿请求键。输出：批次摘要、counts/statistics/pagination、按需批次/任务详情、OA 草稿状态和发票 PDF。

## 当前业务约定

- 列表固定每页 50 批，批次数取 pagination.total，详情不嵌入列表。切批次同时失效旧 task，写目标必须是当前批次已加载 task；重复选中同批次零 I/O。
- 当前页观察到 ETC 导入任务退出排队/执行状态或出现部分成功时，重新读取批次和当前详情；成功任务退出全局活动列表也触发读取。任务消失不等同于成功，展示结果以 canonical 批次事实为准，同一状态不重复刷新。
- OA 草稿 prepare 在锁内保存 attempt/预填快照，外部 HTTP 在锁外，finalize 对单批版本 CAS；重复 key 不创建第二个草稿，未知结果走显式核实恢复。
- OA 金额来自对账事实，发票合计独立展示，不能互相替代；附件上传有界并发，只接纳已知 OA 文件地址合同。
- ETC 原始票据与统一发票池身份分别归属，通过精确 existing-link 连接，metadata 更新不得覆盖正式财务字段。
- 提交状态变化在 owner 事务中通知精确 matching scopes；matcher 通过正式关系命令建立 ETC summary 成员及链接。
- 合并 PDF 按稳定顺序每票一页，来源不可读、损坏或不符合页面合同整包失败，成功记录下载审计。

## 依赖方向

[ETC 发票导入](../imports-etc-invoices/README.md)、[OA 集成](../oa-integration/README.md)、[正式关联关系](../workbench-relations/README.md)、[后台任务](../runtime-workers/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/EtcTicketManagementPage.tsx](../../../web/src/pages/EtcTicketManagementPage.tsx)
- [backend/src/fin_ops_platform/app/server.py](../../../backend/src/fin_ops_platform/app/server.py)
- [backend/src/fin_ops_platform/services/etc_service.py](../../../backend/src/fin_ops_platform/services/etc_service.py)
- [backend/src/fin_ops_platform/services/etc_business_batch_application_service.py](../../../backend/src/fin_ops_platform/services/etc_business_batch_application_service.py)
- [backend/src/fin_ops_platform/services/etc_invoice_pdf_bundle_service.py](../../../backend/src/fin_ops_platform/services/etc_invoice_pdf_bundle_service.py)
- [backend/src/fin_ops_platform/services/invoice_attachment_recognition_service.py](../../../backend/src/fin_ops_platform/services/invoice_attachment_recognition_service.py)
- [backend/src/fin_ops_platform/services/etc_document_parsers.py](../../../backend/src/fin_ops_platform/services/etc_document_parsers.py)
- [backend/src/fin_ops_platform/services/etc_reconciliation_service.py](../../../backend/src/fin_ops_platform/services/etc_reconciliation_service.py)
- [backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py](../../../backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py)
- [backend/src/fin_ops_platform/services/import_processing_service.py](../../../backend/src/fin_ops_platform/services/import_processing_service.py)
- [web/e2e/etc-tickets-flow.spec.ts](../../../web/e2e/etc-tickets-flow.spec.ts)
- [tests/test_etc_backend.py](../../../tests/test_etc_backend.py)
- [tests/test_etc_invoice_pdf_bundle_service.py](../../../tests/test_etc_invoice_pdf_bundle_service.py)
- [tests/test_etc_reconciliation_service.py](../../../tests/test_etc_reconciliation_service.py)
- [tests/test_repair_etc_business_batch_summary_tool.py](../../../tests/test_repair_etc_business_batch_summary_tool.py)
- [tests/test_import_processing_service.py](../../../tests/test_import_processing_service.py)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。

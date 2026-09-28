# 发票导入

入口：`/imports/invoices`。

拥有统一发票池的普通导入，处理文件或人工多票预览、强身份去重和正式来源。

## 边界与 I/O

输入：发票文件、可选单张 JPG/PNG/PDF 识别、人工 invoices[]、预览版本与 file_ids。输出：字段识别、逐票复核、任务、正式发票及来源历史。

## 当前业务约定

- 上传登记后由 import worker 直接领取同一 job 的 prepare 阶段，持久预览后等待确认；confirm 固化范围和版本，commit 阶段才写正式财务事实。
- job.import_jobs 是任务状态源。claim_version、owner 与 lease 隔离过期执行者；事实、来源、审计、必要匹配通知和成功状态在同一事务提交。
- 银行、发票、ETC 已登记任务向具备平台访问权的用户共享复核、确认、重试和结束处理；私人草稿仍校验创建者，OA/认证任务按各自 owner 规则处理。
- 操作人取后端 session，worker 按实际操作人的当前权限复核；创建人与文件来源不改写。
- 数据问题进入 needs_review，暂时失败有限重试；确认冲突要求重新复核，不自动确认。取消与正式提交互锁，明确结束的任务不可重试，已读不代表结束。
- 预览行服务端分页 limit 最大 100，摘要不携带无界结果；无可确认文件保留明细并待复核。页面只显式恢复选中的任务，不自动复原其他私人草稿。
- 可选单票识别只预填允许字段，不持久化票据。红字表单收正数，正式金额统一为负。
- 同批重复、非 OA 来源现存票或疑似重复拒绝；OA 已持有同强身份时记录 duplicate_skipped，不能新建第二张票。
- 确认重检逐行 decision 和 linked identity，数量不变但 owner 改变仍属于预览陈旧。
- 与 OA 附件身份桥接使用本批强身份集合和当前来源事实批量处理；不全库扫描或在确认事务中下载/OCR。
- 补充凭证图库按需分页只读，不创建导入 session 或关联任务。

## 依赖方向

[OA 集成](../oa-integration/README.md)、[正式关联关系](../workbench-relations/README.md)、[后台任务](../runtime-workers/README.md)、[权限与审计](../permissions-and-audit/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/imports/ImportInvoicesPage.tsx](../../../web/src/pages/imports/ImportInvoicesPage.tsx)
- [web/src/components/imports/ImportWorkflowPage.tsx](../../../web/src/components/imports/ImportWorkflowPage.tsx)
- [web/src/components/imports/ManualInvoiceEntryDrawer.tsx](../../../web/src/components/imports/ManualInvoiceEntryDrawer.tsx)
- [web/src/components/imports/ManualInvoiceBatchEditor.tsx](../../../web/src/components/imports/ManualInvoiceBatchEditor.tsx)
- [web/src/components/imports/SupportingDocumentGalleryDrawer.tsx](../../../web/src/components/imports/SupportingDocumentGalleryDrawer.tsx)
- [web/src/features/workbench/api.ts](../../../web/src/features/workbench/api.ts)
- [web/src/features/imports/api.ts](../../../web/src/features/imports/api.ts)
- [web/src/features/imports/types.ts](../../../web/src/features/imports/types.ts)
- [backend/src/fin_ops_platform/app/server.py](../../../backend/src/fin_ops_platform/app/server.py)
- [backend/src/fin_ops_platform/services/import_file_service.py](../../../backend/src/fin_ops_platform/services/import_file_service.py)
- [web/e2e/imports-invoices-flow.spec.ts](../../../web/e2e/imports-invoices-flow.spec.ts)
- [tests/test_import_formalization_api.py](../../../tests/test_import_formalization_api.py)
- [tests/test_import_preview_audit.py](../../../tests/test_import_preview_audit.py)
- [tests/test_import_service.py](../../../tests/test_import_service.py)
- [tests/test_import_processing_service.py](../../../tests/test_import_processing_service.py)
- [web/src/test/BackgroundJobProgress.test.tsx](../../../web/src/test/BackgroundJobProgress.test.tsx)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。

# ETC 发票导入

入口：`/imports/etc-invoices`。

把 ETC 文件预览、确认和来源关联纳入共同导入工作流，领域解析及成员归属由 ETC owner 负责。

## 边界与 I/O

输入：ETC 文件、目标任务/批次、预览版本与确认文件集合。输出：持久预览、任务状态、ETC 成员/附件引用、统一发票链接和受影响月份。

## 当前业务约定

- 上传登记后由 import worker 直接领取同一 job 的 prepare 阶段，持久预览后等待确认；confirm 固化范围和版本，commit 阶段才写正式财务事实。
- job.import_jobs 是任务状态源。claim_version、owner 与 lease 隔离过期执行者；事实、来源、审计、必要匹配通知和成功状态在同一事务提交。
- 银行、发票、ETC 已登记任务向具备平台访问权的用户共享复核、确认、重试和结束处理；私人草稿仍校验创建者，OA/认证任务按各自 owner 规则处理。
- 操作人取后端 session，worker 按实际操作人的当前权限复核；创建人与文件来源不改写。
- 数据问题进入 needs_review，暂时失败有限重试；确认冲突要求重新复核，不自动确认。取消与正式提交互锁，明确结束的任务不可重试，已读不代表结束。
- 预览行服务端分页 limit 最大 100，摘要不携带无界结果；无可确认文件保留明细并待复核。页面只显式恢复选中的任务，不自动复原其他私人草稿。
- 附件准备和文件解析在短财务事务之外；最终成员、附件引用、metadata、session 和任务成功同事务提交。
- 任务与批次按精确身份关联，页面使用最新批次标题；已确认成员不得因重试生成第二份。
- worker 完成后页面重新读取 PostgreSQL 状态，不依赖 API 重启或进程内旧对象。
- ETC XML 汇总字段与 `IssuItemInformation` 明细分开读取。每个实际明细节点产生一个 `source_line_items` 条目；缺失的明细金额保持空，不从首条明细替代汇总，不造整票明细。
- 多条明细保留各自来源税率，混合税率汇总标为多税率；`*`、免税、不征税不转换为零，非数字税额存入 `tax_amount_text`。ETC 批次仍要求原件提供总额，以保证后续归集口径。
- ETC 台账的数字税额允许空，原始税额文本和明细保存在同条记录的 `normalized_payload`，读取与保存保持一致。缺少数字税额时不作零值算术校验。
- 历史真实明细使用 `import_audit_repair_ops --repair-etc-source-lines --dry-run` 从登记的原 XML 重新读取。预览校验原件哈希、发票身份与原有金额/税率；执行要求明确 ETC ID、预览指纹、私有恢复工件、操作人和原因。事务只改原始明细/税额文本并记审计，不改变金额、批次或关系；恢复工件沿用[运行说明](../../operations.md)的精确清理合同。

## 依赖方向

[ETC 票据](../etc-tickets/README.md)、[发票导入](../imports-invoices/README.md)、[后台任务](../runtime-workers/README.md)、[权限与审计](../permissions-and-audit/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/imports/ImportEtcInvoicesPage.tsx](../../../web/src/pages/imports/ImportEtcInvoicesPage.tsx)
- [web/src/components/imports/ImportWorkflowPage.tsx](../../../web/src/components/imports/ImportWorkflowPage.tsx)
- [web/src/features/etc/api.ts](../../../web/src/features/etc/api.ts)
- [web/src/features/etc/types.ts](../../../web/src/features/etc/types.ts)
- [web/src/features/imports/importRoutes.ts](../../../web/src/features/imports/importRoutes.ts)
- [backend/src/fin_ops_platform/app/server.py](../../../backend/src/fin_ops_platform/app/server.py)
- [backend/src/fin_ops_platform/services/etc_service.py](../../../backend/src/fin_ops_platform/services/etc_service.py)
- [backend/src/fin_ops_platform/services/etc_reconciliation_service.py](../../../backend/src/fin_ops_platform/services/etc_reconciliation_service.py)
- [backend/src/fin_ops_platform/services/etc_reconciliation_zip_filter.py](../../../backend/src/fin_ops_platform/services/etc_reconciliation_zip_filter.py)
- [backend/src/fin_ops_platform/services/etc_document_parsers.py](../../../backend/src/fin_ops_platform/services/etc_document_parsers.py)
- [web/e2e/imports-etc-invoices-flow.spec.ts](../../../web/e2e/imports-etc-invoices-flow.spec.ts)
- [tests/test_etc_backend.py](../../../tests/test_etc_backend.py)
- [tests/test_etc_reconciliation_import_cleanup_service.py](../../../tests/test_etc_reconciliation_import_cleanup_service.py)
- [tests/test_import_job_queue.py](../../../tests/test_import_job_queue.py)
- [tests/test_import_processing_service.py](../../../tests/test_import_processing_service.py)
- [web/src/test/EtcTicketManagementPage.test.tsx](../../../web/src/test/EtcTicketManagementPage.test.tsx)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。

ETC XML 的整票字段与真实明细分别保存；没有整票税率时保持空值，不用明细补齐。登记 PDF 票面提供准确身份及明确标题时读取票种，渠道本身不代表任何票种。

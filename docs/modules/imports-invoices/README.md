# 发票导入

入口：`/imports/invoices`。

拥有统一发票池的普通导入，处理文件或人工多票预览、强身份去重和正式来源。

## 边界与 I/O

输入：发票文件、单张 JPG/PNG/PDF 原件、人工 invoices[]、预览版本与 file_ids。输出：字段识别、逐票复核、任务、正式发票及来源历史。

## 当前业务约定

- 上传登记后由 import worker 直接领取同一 job 的 prepare 阶段，持久预览后等待确认；confirm 固化范围和版本，commit 阶段才写正式财务事实。
- job.import_jobs 是任务状态源。claim_version、owner 与 lease 隔离过期执行者；事实、来源、审计、必要匹配通知和成功状态在同一事务提交。
- 银行、发票、ETC 已登记任务向具备平台访问权的用户共享复核、确认、重试和结束处理；私人草稿仍校验创建者，OA/认证任务按各自 owner 规则处理。
- 操作人取后端 session，worker 按实际操作人的当前权限复核；创建人与文件来源不改写。
- 数据问题进入 needs_review，暂时失败有限重试；确认冲突要求重新复核，不自动确认。取消与正式提交互锁，明确结束的任务不可重试，已读不代表结束。
- 预览行服务端分页 limit 最大 100，摘要不携带无界结果；无可确认文件保留明细并待复核。页面只显式恢复选中的任务，不自动复原其他私人草稿。
- 单票录入必须上传原件；识别预填允许字段，预览重新读取该原件并核对身份、日期、购销双方和金额。原件与正式来源一并登记，手工改值不能成为票面事实。红字表单收正数，与原件的负值精确比对后保存。
- 同批重复、非 OA 来源现存票或疑似重复拒绝；OA 已持有同强身份时记录 duplicate_skipped，不能新建第二张票。
- 确认重检逐行 decision 和 linked identity，数量不变但 owner 改变仍属于预览陈旧。
- 与 OA 附件身份桥接使用本批强身份集合和当前来源事实批量处理；不全库扫描或在确认事务中下载/OCR。
- 补充凭证图库按需分页只读，不创建导入 session 或关联任务。

- 发票未税金额、税额、价税合计和税率只读取原始文件字段。缺失字段保留空值，不通过加减或比率补齐；零、缺失和 `*` 等非数字税额分别保存。原税额文字存于 `tax_amount_text`，不写入数值列。
- 正式导入的财务字段、原始明细与财务来源批次保持整组一致；新文件重复导入或更新发票状态时只追加来源关系，不从另一文件逐字段补空或重指向财务来源。非 OA 发票首次取得正式导入来源时整组采用该原件，包括空值；OA 持有发票继续遵守 OA owner 合同。
- Excel 以“发票基础信息”为整票事实，按强身份关联“信息汇总表”的全部真实明细；逐行保留金额、税率、税额、原件存在的含税值和原始位置。只有整票汇总时不生成虚构明细。
- `invoice_financial_values.py` 仅规范原始字段和保留真实明细税率，不反推任何金额或税率。整票明确标注多税率才显示多税率，整票税率缺失显示 `—`；不以明细税率补整票税率；原表税率与明细冲突时保留原明细并明确提示。SQL 和 Python 读取遵守相同合同。
- 历史修复通过已登记原件、明确发票身份和现有受控修复入口执行，保留发票 ID、来源关系和业务配对。事务写入原始财务字段与全部明细，同时清理受影响的旧解析器或旧 schema 的 OA 缓存；当前源数据解析缓存保持不变，避免重复 OCR。重复执行不重复改写。
- 发票对象的读取、关联更新与保存保留原件 ID/hash、明细数量、原始工作表与核验指纹；普通对象序列化不能丢弃这些追溯字段。
- 历史导入回执保持原样。原件核验成功后，追加审计证明绑定发票身份、当前修复版本、原件 ID/hash、全部原始财务字段与真实明细；零变更补证仍重新读取原件。发票导入审计一次批量读取证明，只有证明与当前事实完整一致时才将已被原件修正的回执差异报告为可见警告；缺证、字段漂移、身份或来源关系错误继续阻止验收。

- 票种只从 Excel 原始票种字段或 PDF／图片明确标题读取。`invoice_kind` 保留原文，`invoice_kind_code` 使用统一确定映射；空值、未映射、未读取、原件不可用和来源冲突分别记录于 `invoice_kind_status`。不按导入渠道、税率、金额、正负或认证记录推断。
- 同一强身份原件分别明确写“通行费发票”和“普通发票”时，使用原件提供的通行费子类，并保留两份原文证据；日期、购方身份或其他互斥票种不一致仍为冲突。
- 多行或明细工作表没有整票汇总字段时，整票金额、税额和税率为空，不合成票面值；完整明细独立保留。
- 原件票种全池维护使用 `--repair-invoice-source-attributes`，按准确登记文件和强身份读取；保留原件哈希与位置，事务版本检查及审计。只改票种和同属原件的来源元数据，不改金额、身份、认证或 OA／流水关联。重复运行零更新。
- 原件不可用、身份冲突或元数据所属原件不明时，来源、正数标记、风险等级、开票人和原表备注为空；导入渠道只保留在来源链，不作为原件属性。

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
- [tests/test_audit_invoice_import_page.py](../../../tests/test_audit_invoice_import_page.py)
- [票种映射](../../../backend/src/fin_ops_platform/services/invoice_kind.py)
- [原件票种维护](../../../backend/src/fin_ops_platform/services/invoice_source_attribute_repair.py)
- [原件维护测试](../../../tests/test_invoice_source_attribute_repair.py)
- [原件维护 PostgreSQL 链路](../../../tests/test_invoice_kind_repair_postgres.py)
- [tests/test_import_service.py](../../../tests/test_import_service.py)
- [tests/test_import_processing_service.py](../../../tests/test_import_processing_service.py)
- [web/src/test/BackgroundJobProgress.test.tsx](../../../web/src/test/BackgroundJobProgress.test.tsx)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。

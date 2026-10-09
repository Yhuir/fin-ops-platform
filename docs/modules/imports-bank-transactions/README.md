# 银行流水导入

入口：`/imports/bank-transactions`。

负责银行文件或手工流水的解析、映射、预览、确认、重复识别与来源追溯；银行用途维护由银行明细负责。

## 边界与 I/O

输入：文件、银行映射、字段映射、session/file IDs、预览版本和确认范围；手工预览为 1–50 笔 transactions，绑定现有银行映射。输出：任务/预览、复核分页、错误明细、正式批次和受影响月份。

## 当前业务约定

- 银行明细、进项和销项页面提供按目标导入权限显示的快捷入口。来源仅使用登记的页面标识；返回经现有路由鉴权。通过返回按钮离开未上传文件时确认，已登记任务继续由任务入口恢复，不取消任务。

- 上传登记后由 import worker 直接领取同一 job 的 prepare 阶段，持久预览后等待确认；confirm 固化范围和版本，commit 阶段才写正式财务事实。
- job.import_jobs 是任务状态源。claim_version、owner 与 lease 隔离过期执行者；事实、来源、审计、必要匹配通知和成功状态在同一事务提交。
- 银行、发票、ETC 已登记任务向具备平台访问权的用户共享复核、确认、重试和结束处理；私人草稿仍校验创建者，OA/认证任务按各自 owner 规则处理。
- 操作人取后端 session，worker 按实际操作人的当前权限复核；创建人与文件来源不改写。
- 数据问题进入 needs_review，暂时失败有限重试；确认冲突要求重新复核，不自动确认。取消与正式提交互锁，明确结束的任务不可重试，已读不代表结束。
- 预览行服务端分页 limit 最大 100，摘要不携带无界结果；无可确认文件保留明细并待复核。页面只显式恢复选中的任务，不自动复原其他私人草稿。
- 手工流水必须给出完整本方账号、秒级时间、收支、正金额、余额、币种及对方户名；疑似重复必须复核，同批弱指纹重复拒绝。
- 字段映射只提交 canonical 字段到源列，不接受客户端伪造的解析事实。来源控制 mismatch 或账户冲突不能确认，全量已存在不重复写入。
- 管理员批次撤回仅处理批次独占且无其他业务阻断的流水，同事务经 owner 清理关系/分类并保留来源与审计；重复撤回幂等。

## 依赖方向

[银行明细](../bank-details/README.md)、[正式关联关系](../workbench-relations/README.md)、[后台任务](../runtime-workers/README.md)、[权限与审计](../permissions-and-audit/README.md)。依赖表示调用或事实消费，不允许读取其它页面的展示结果作为业务事实。

## 代码与验证入口

- [web/src/pages/imports/ImportBankTransactionsPage.tsx](../../../web/src/pages/imports/ImportBankTransactionsPage.tsx)
- [web/src/components/imports/ImportWorkflowPage.tsx](../../../web/src/components/imports/ImportWorkflowPage.tsx)
- [web/src/components/imports/ManualBankTransactionBatchEditor.tsx](../../../web/src/components/imports/ManualBankTransactionBatchEditor.tsx)
- [web/src/components/imports/ManualBankTransactionEntryDrawer.tsx](../../../web/src/components/imports/ManualBankTransactionEntryDrawer.tsx)
- [web/src/features/imports/api.ts](../../../web/src/features/imports/api.ts)
- [web/src/features/imports/types.ts](../../../web/src/features/imports/types.ts)
- [web/src/features/imports/importRoutes.ts](../../../web/src/features/imports/importRoutes.ts)
- [backend/src/fin_ops_platform/app/server.py](../../../backend/src/fin_ops_platform/app/server.py)
- [backend/src/fin_ops_platform/services/import_file_service.py](../../../backend/src/fin_ops_platform/services/import_file_service.py)
- [backend/src/fin_ops_platform/services/manual_bank_transaction_entry_service.py](../../../backend/src/fin_ops_platform/services/manual_bank_transaction_entry_service.py)
- [tests/test_import_file_api.py](../../../tests/test_import_file_api.py)
- [tests/test_import_file_service.py](../../../tests/test_import_file_service.py)
- [tests/test_import_api.py](../../../tests/test_import_api.py)
- [tests/test_import_service.py](../../../tests/test_import_service.py)
- [tests/test_import_preview_audit.py](../../../tests/test_import_preview_audit.py)
- [web/src/test/ImportCenterPage.test.tsx](../../../web/src/test/ImportCenterPage.test.tsx)

通用查询、事务、权限与错误边界见[系统架构](../../../ARCHITECTURE.md)；验证方法见[开发说明](../../development.md)。测试文件是可执行证据，本文不保存某一次测试的通过记录。

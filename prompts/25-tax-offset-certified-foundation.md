# Prompt 25：实现税金抵扣计划/已认证底座

目标：重构税金抵扣后端数据模型，使页面能区分 `销项票开票情况`、`进项票认证计划`、`已认证结果`，并支持已认证导入后锁定计划项。

前提：

- `13-tax-offset-workbench.md` 已完成

要求：

- 扩展 `/api/tax-offset` 返回结构，至少区分：
  - `outputInvoices`
  - `inputPlanInvoices`
  - `certifiedResults`
- 让销项票清单天然只读，不作为可勾选对象
- 已认证发票导入后，支持把导入结果匹配回进项票计划
- 返回明确的锁定信息，例如：
  - `lockedCertifiedInputIds`
  - `certifiedMatchedRows`
  - `certifiedOutsidePlanRows`
- 试算口径改成：
  - 全部已认证进项票
  - 加上未认证但被勾选的计划票

建议文件：

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/tax_offset_service.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `tests/test_tax_offset_api.py`
- `tests/test_tax_offset_service.py`

交付要求：

- 后端契约能明确区分三类数据
- 已认证结果可回写约束计划项
- 已认证但未进入计划的票可被单独返回

验证：

- 后端测试覆盖匹配、锁定、试算口径
- `/api/tax-offset` 返回结构与设计文档一致


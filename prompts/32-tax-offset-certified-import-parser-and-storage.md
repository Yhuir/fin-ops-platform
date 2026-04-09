# Prompt 32：实现税金抵扣已认证发票模板解析与持久化

目标：把税金抵扣中的 `已认证发票导入` 从占位态推进到真实后端能力，先完成给定 Excel 模板的解析、标准化与持久化。

前提：

- `25-tax-offset-certified-foundation.md`、`26-tax-offset-plan-and-certified-drawer-ui.md`、`27-tax-offset-certified-integration-and-qa.md` 已完成

模板范围：

- `fixtures/测试数据/2026年1月 进项认证结果  用途确认信息.xlsx`
- `fixtures/测试数据/2026年2月 进项认证结果  用途确认信息.xlsx`

要求：

- 只处理模板中的 `发票` sheet
- 至少解析这些字段：
  - 数电发票号码
  - 发票代码
  - 发票号码
  - 开票日期
  - 销售方纳税人识别号
  - 销售方纳税人名称
  - 金额
  - 税额
  - 有效抵扣税额
  - 勾选状态
  - 发票状态
  - 勾选时间
- 只把“已认证 / 已勾选 / 可用于抵扣”的记录纳入结果
- 增加已认证导入的持久化结构，避免税金抵扣继续依赖写死样例
- 支持按月份读取已认证导入结果
- 支持幂等去重

建议文件：

- `backend/src/fin_ops_platform/services/tax_certified_import_service.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_tax_certified_import_service.py`

交付要求：

- 已认证导入有真实服务层与存储结构
- 给定两份模板可以稳定被解析
- 结果可按月份读取

验证：

- 后端测试覆盖模板解析、去重、月份读取


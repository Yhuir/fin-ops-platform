# Prompt 27：完成税金抵扣计划/已认证联动与验收

目标：打通已认证导入、页面锁定状态、试算结果和验收测试，确保税金抵扣页面符合“只做计划/计算/展示”的口径。

前提：

- `25-tax-offset-certified-foundation.md` 已完成
- `26-tax-offset-plan-and-certified-drawer-ui.md` 已完成

要求：

- 已认证发票导入后，页面即时刷新：
  - 摘要卡
  - 试算结果
  - 进项票计划状态
  - 已认证结果抽屉
- 已认证但未进入计划的票：
  - 出现在抽屉中
  - 计入试算
  - 不强塞进计划表
- 页面文案统一成：
  - 计划
  - 已认证结果
  - 试算
- 不出现真实税务业务动作型文案，例如：
  - 提交认证
  - 正式申报

建议文件：

- `web/src/pages/TaxOffsetPage.tsx`
- `web/src/features/tax/api.ts`
- `web/src/features/tax/types.ts`
- `web/src/test/apiMock.ts`
- `web/src/test/TaxOffsetPage.test.tsx`
- `tests/test_tax_offset_api.py`
- `docs/README.md`
- `prompts/README.md`

交付要求：

- 已认证导入、计划勾选、试算结果逻辑一致
- 页面不承担真实税务业务提交
- 文案和状态口径一致

验证：

- 前端全量测试
- 后端全量测试
- 手工验收：
  - 销项票不可选
  - 进项票计划可选
  - 已认证计划票禁用
  - 已认证但未进入计划票进入抽屉
  - 试算结果符合新口径


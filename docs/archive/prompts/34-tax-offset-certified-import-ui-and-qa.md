# Prompt 34：实现税金抵扣已认证发票导入弹窗联动与验收

目标：让税金抵扣页中的 `已认证发票导入` 弹窗完成真实的预览、确认导入、页面刷新，不再只是文件选择占位。

前提：

- `32-tax-offset-certified-import-parser-and-storage.md` 已完成
- `33-tax-offset-certified-import-matching-and-refresh.md` 已完成

要求：

- `已认证发票导入` 弹窗支持：
  - 选择一个或多个 Excel
  - 预览识别结果
  - 显示识别数量、匹配计划数量、未进入计划数量、无效记录数量
  - 确认导入
- 导入成功后，税金抵扣页即时刷新：
  - 摘要卡
  - 试算结果
  - 进项票认证计划
  - 已认证结果抽屉
- 保持税金抵扣页只做：
  - 计划
  - 计算
  - 展示
- 不引入真实税局动作型文案

建议文件：

- `web/src/components/tax/CertifiedInvoiceImportModal.tsx`
- `web/src/pages/TaxOffsetPage.tsx`
- `web/src/features/tax/api.ts`
- `web/src/features/tax/types.ts`
- `web/src/test/TaxOffsetPage.test.tsx`
- `web/src/test/apiMock.ts`
- `docs/README.md`
- `prompts/README.md`

交付要求：

- 已认证导入弹窗成为真实导入入口
- 导入后进项计划能正确锁灰
- 页面不再依赖占位导入文案

验证：

- 前端全量测试
- 后端全量测试
- 前端 build
- 手工验收给定 2026-01 / 2026-02 模板

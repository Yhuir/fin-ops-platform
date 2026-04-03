# Prompt 26：实现税金抵扣页面重构与已认证结果抽屉

目标：把税金抵扣页面重构为“两栏主区 + 右侧已认证结果抽屉”，并让销项票只读、进项票计划可编辑。

前提：

- `25-tax-offset-certified-foundation.md` 已完成

要求：

- 页面头部保留：
  - `已认证发票导入`
  - 月份选择器
- 删除：
  - `返回关联台`
- 主体改成：
  - 左：`销项票开票情况`
  - 中：`进项票认证计划`
  - 右：`已认证结果` 抽屉
- 销项票表格不可勾选
- 进项票计划表格可勾选
- 已认证命中的计划票：
  - 变灰
  - 不可勾选
  - 状态显示 `已认证`
- 右侧抽屉分组展示：
  - `已匹配计划`
  - `已认证但未进入计划`
- 点击抽屉中的已匹配计划项，可高亮中栏对应计划行

建议文件：

- `web/src/pages/TaxOffsetPage.tsx`
- `web/src/components/tax/TaxTable.tsx`
- `web/src/components/tax/CertifiedResultsDrawer.tsx`
- `web/src/components/tax/TaxSummaryCards.tsx`
- `web/src/components/tax/TaxResultPanel.tsx`
- `web/src/app/styles.css`
- `web/src/test/TaxOffsetPage.test.tsx`

交付要求：

- 页面结构符合“计划 vs 实际”
- 销项票彻底只读
- 右侧抽屉可展开/收起
- 已认证计划票状态与视觉明确

验证：

- 页面测试覆盖只读、禁用、抽屉分组和高亮联动
- 前端 build 通过


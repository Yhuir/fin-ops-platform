# Prompt 13：实现税金抵扣独立页面

目标：实现 `销项票税金 - 进项票税金` 独立页面，并与月份上下文联动。

前提：

- `09-workbench-v2-web-foundation.md` 已完成

要求：

- 从主工作台右上角 `税金抵扣` 进入
- 页面允许查看和切换月份
- 展示：
  - 销项税额
  - 进项税额
  - 本月抵扣额
  - 本月应纳税额 / 留抵税额
- 左右两张表分别展示：
  - 销项票税金清单
  - 进项票税金清单
- 支持勾选清单项，实时计算汇总结果
- 支持返回主工作台

建议文件：

- `web/src/pages/TaxOffsetPage.tsx`
- `web/src/components/tax/TaxSummaryCards.tsx`
- `web/src/components/tax/TaxTable.tsx`
- `web/src/components/tax/TaxResultPanel.tsx`

交付要求：

- 切换月份可刷新税金数据
- 勾选项变化时结果实时变化
- 与主工作台共用月份语义

验证：

- 页面测试覆盖勾选重算
- 手工验证返回主工作台后月份不乱

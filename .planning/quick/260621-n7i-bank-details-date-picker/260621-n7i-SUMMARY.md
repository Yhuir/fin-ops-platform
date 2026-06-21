---
quick_id: 260621-n7i
status: complete
date: 2026-06-21
---

# Quick Task 260621-n7i Summary

## Goal

简化银行明细页面右上角时间筛选：移除快捷日期按钮和任意日期范围输入，改为支持按年/按月选择的时间选择器，以及一个“全部”按钮。

## Completed

- `BankDateFilter` 收敛为 `all`、`year`、`month` 三种状态。
- `BankDetailsPage` 默认仍使用 `2026` 年；按年选择发送整年日期，按月选择发送当月首尾日期，“全部”不发送 `date_from` / `date_to`。
- 右上角日期 UI 改为“时间选择 + 全部”两个控件，弹层内支持“按年 / 按月”切换。
- 更新银行明细 Vitest、Playwright e2e、模块实施记录、测试矩阵、状态机和 e2e coverage。

## Verification

- `cd web && npm test -- --run src/test/BankDetailsPage.test.tsx`
- `cd web && npx playwright test e2e/bank-details-filtered-export-permissions.spec.ts`
- `cd web && npm run build`

## Remaining Risk

- 未运行后端测试，因为本次未改后端 API、service、repository、read model 或 worker。
- 真实生产多年份历史数据、真实 XLSX 完整解析和生产代理下载 headers 仍需 staging/专项 smoke 覆盖。

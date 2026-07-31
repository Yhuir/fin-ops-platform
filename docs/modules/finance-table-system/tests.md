# Finance Table System 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 2026-07-31 共享右抽屉 motion 回归

- `web/src/test/CommonPlatformComponents.test.tsx`：共享 `AppDrawer` right placement、modal/persistent open-close、rapid reopen、180ms 退出卸载、busy dismiss、reduced-motion，以及旧 keyframes/短距离 transform/重复 Escape 的源码负向门禁。
- `web/e2e/drawer-motion.spec.ts`：真实 Chromium 采样 Workbench 详情进入/退出位置序列，要求存在中间帧和大于 75% 面板宽度的可观察位移；关闭不增加业务 API，页面级 CLS 小于 `0.01`，reduced-motion 最长过渡不超过 1ms。
- 适用类别：第 5 类 frontend interaction 与第 7 类 existing regression；业务规则、service、API/read model 均未变化，第 1–4 类不新增测试；第 6 类由同一 Workbench 浏览器详情链覆盖 UI 端完整开关流程。

## 影响面清单

| 影响面 | 当前测试入口 | 必须保护的行为 |
| --- | --- | --- |
| Shared primitives | `FinanceTable.test.tsx`、`TableAlignmentStyles.test.ts`、`TableLayoutTokens.test.ts` | 分页摘要/边界、金额/方向/状态/空值 primitive、列角色对齐、密度 token |
| Shared browser layout | `web/e2e/finance-table-system-flow.spec.ts`、`web/e2e/bank-details-large-scroll-flow.spec.ts`、`web/e2e/workbench-large-scroll-flow.spec.ts` | 窄屏/宽表横向滚动、右侧列可见、操作入口不被遮挡、真实浏览器无 console/page error |
| Table session hook | `useFinanceTableSession.test.tsx`、`PageSessionStateContext.test.tsx` | 分页、排序、选择、滚动恢复；columnsVersion 变化清理；user/page/state 隔离 |
| Legacy table runtime guard | `MuiContainment.test.ts`、`CommonPlatformComponents.test.tsx` | 非 workbench runtime 无 MUI/DataGrid/provider/theme；旧 `useMuiDataGridPageSession` hook/test 不得回归；common primitives 不再以 MUI 命名 |
| Bank details table | `BankDetailsPage.test.tsx`、`BankDetailsApi.test.ts` | HeroUI table migration、列清单、分页、搜索、标签筛选、导出、refreshing/stale |
| Tax tables | `TaxOffsetPage.test.tsx`、`TaxApi.test.ts` | 发票选择、认证导入预览、税金表格、loading/error、导入反馈 |
| Invoice usage / pending / collections tables | `InputInvoiceUsagePage.test.tsx`、`PendingInvoicesPage.test.tsx`、`OutputInvoiceCollectionsPage.test.tsx` | header filter、sort、pagination、read model refreshing/stale、export drawers |
| OA / turnover / cost tables | `OaPendingPaymentsPage.test.tsx`、`TurnoverLedgerPage.test.tsx`、`CostStatisticsPage.test.tsx` | grouped table、详情 dialog/drawer、export dialog、stale disable、large layout CSS |
| Import preview tables | `ImportCenterPage.test.tsx`、`EtcTicketManagementPage.test.tsx` | preview stale/error、行级状态 tag、确认前预览 |
| App Health tables | `AppHealthOperationsPage.test.tsx` | runtime dashboard 只读表、admin-only、unknown 不等于 0 |

## 场景覆盖清单

| 场景 | 覆盖状态 | 测试入口 |
| --- | --- | --- |
| shared pagination clamp、summary、上一页/页码 callback | 已覆盖，2026-06-11 新增 | `FinanceTable.test.tsx` |
| shared Amount/Direction/Status/Empty primitives | 已覆盖，2026-06-11 新增 | `FinanceTable.test.tsx` |
| CSS token、行高、列角色对齐、tag 稳定尺寸 | 已覆盖 | `TableLayoutTokens.test.ts`、`TableAlignmentStyles.test.ts` |
| 共享宽表 Browser 横向滚动、右侧列可见、刷新控件不遮挡 | 已覆盖，2026-06-19 新增 | `web/e2e/finance-table-system-flow.spec.ts` |
| table session 保存/恢复 pagination/sort/selection/scroll | 已覆盖 | `useFinanceTableSession.test.tsx` |
| columnsVersion 变化丢弃旧 table session | 已覆盖 | `useFinanceTableSession.test.tsx` |
| page/user/session storage 隔离和 TTL/version/validation | 已覆盖 | `PageSessionStateContext.test.tsx` |
| 旧 MUI/DataGrid runtime、provider/theme、DataGrid session hook 删除防回归 | 已覆盖，2026-07-05 补强 | `MuiContainment.test.ts` |
| 页面级筛选/排序/分页请求参数 | 已覆盖于具体页面 | `BankDetailsPage.test.tsx`、`InputInvoiceUsagePage.test.tsx`、`PendingInvoicesPage.test.tsx`、`OutputInvoiceCollectionsPage.test.tsx` |
| 页面级导出抽屉/下载使用当前 filters | 已覆盖于具体页面 | `BankDetailsPage.test.tsx`、`InputInvoiceUsagePage.test.tsx`、`PendingInvoicesPage.test.tsx`、`CostStatisticsPage.test.tsx`、`TurnoverLedgerPage.test.tsx` |
| read model refreshing/stale 表格状态 | 已覆盖于具体页面 | `BankDetailsPage.test.tsx`、`InputInvoiceUsagePage.test.tsx`、`OutputInvoiceCollectionsPage.test.tsx`、`PendingInvoicesPage.test.tsx`、`TurnoverLedgerPage.test.tsx` |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 不适用 | N/A | 本模块不定义金额归因、匹配、分类、发票生命周期等业务规则；仅展示业务字段。 |
| 2. Service-layer tests | 不适用 | N/A | 本模块不触碰后端 service、repository、audit 或状态写入。 |
| 3. API contract tests | 间接适用 | 各页面 `*Api.test.ts` / `*Page.test.tsx` | 表格 query params、pagination、sort、filters、export contract 由页面/API 模块负责；共享 primitive 不发 HTTP。 |
| 4. Read model/cache/background job tests | 间接适用 | 页面级 refreshing/stale tests | 表格只展示 read model 状态；freshness 来源仍由页面 API 和 read model 模块负责。 |
| 5. Frontend component and interaction tests | 适用，已补 | `FinanceTable.test.tsx`、`useFinanceTableSession.test.tsx`、`MuiContainment.test.ts`、页面级 tests、`web/e2e/finance-table-system-flow.spec.ts` | 覆盖共享 primitive、session hook、旧 MUI/DataGrid 删除防回归、页面级筛选/排序/分页/导出/状态，并用真实 Chromium 代表性覆盖 AppHealth 宽表窄屏横向滚动、右侧列可见、read model/worker 表格可读和无浏览器错误。 |
| 6. End-to-end business-flow integration tests | 间接适用 | 具体页面/业务流 tests | 本模块不承载业务链路；端到端链路在导入、关联台、发票、成本、税金等模块保护。 |
| 7. Existing feature regression tests | 适用，已补 | 同上 | 新增共享 primitive 回归测试；页面级旧表格功能由各模块继续保护。 |

## 历史 bug 回归库

| 日期 | 问题 | 回归测试 |
| --- | --- | --- |
| 2026-06-11 | 防止共享分页 summary 边界和 disabled next 行为被 HeroUI 迁移破坏 | `FinanceTable.test.tsx` `clamps pagination display to valid ranges and disables unavailable navigation` |
| 2026-06-11 | 防止共享金额、方向、状态、空值 primitive class/data contract 被重构破坏 | `FinanceTable.test.tsx` `keeps shared finance cell primitives semantically stable` |
| 2026-06-19 | 防止共享 `FinanceTable` 宽表在窄屏下右侧列不可达、刷新按钮被遮挡或 AppHealth read model/worker 表格在真实浏览器中出现 console/page error。 | `web/e2e/finance-table-system-flow.spec.ts` |
| 2026-07-05 | 防止旧 MUI/DataGrid runtime、provider/theme 和 `useMuiDataGridPageSession` 回归污染 Finance Table session 边界 | `MuiContainment.test.ts` |

## 关键 smoke flows

1. 银行明细：搜索/筛选/分页后导出，导出请求携带当前 date/account/keyword/filter。
2. 进项发票使用：恢复 session 中 filters/sort，rows API 使用恢复后的参数。
3. 待找发票：header dropdown filters 与 AND field clauses 生效，refreshing 时禁用导出。
4. 成本统计：表格 drilldown 后打开详情 dialog，导出中心按当前 view/filter 预览和下载。
5. 往来款：read model stale 时显示诊断，写操作仍交给后端 stale precondition/canonical write safety，导出下载当前 tab。
6. 导入预览：preview stale/error 清理旧预览并要求重新 preview。

## 模块验证命令

```bash
cd web && npm test -- --run \
  src/test/FinanceTable.test.tsx \
  src/test/TableLayoutTokens.test.ts \
  src/test/TableAlignmentStyles.test.ts \
  src/test/useFinanceTableSession.test.tsx \
  src/test/PageSessionStateContext.test.tsx \
  src/test/MuiContainment.test.ts \
  src/test/CommonPlatformComponents.test.tsx \
  src/test/BankDetailsPage.test.tsx \
  src/test/TaxOffsetPage.test.tsx \
  src/test/InputInvoiceUsagePage.test.tsx \
  src/test/PendingInvoicesPage.test.tsx \
  src/test/OutputInvoiceCollectionsPage.test.tsx \
  src/test/OaPendingPaymentsPage.test.tsx \
  src/test/CostStatisticsPage.test.tsx \
  src/test/TurnoverLedgerPage.test.tsx \
  src/test/AppHealthOperationsPage.test.tsx \
  src/test/ImportCenterPage.test.tsx

cd web && npx playwright test e2e/finance-table-system-flow.spec.ts --project=chromium

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

`FinanceTable.test.tsx`、table token/style tests、table session tests、`MuiContainment.test.ts`、页面级 Vitest tests 和 `web/e2e/finance-table-system-flow.spec.ts` 应由 nightly/frontend smoke 覆盖。若新增业务表格或迁移表格实现，必须把页面级测试加入对应模块和本矩阵。

## 未测风险

- AppHealth 代表性宽表已覆盖真实 Chromium 窄屏横向滚动；真实生产大数据、更多页面 wrapper、超宽列、下载文件名/浏览器保存行为仍需 Playwright 或手工 smoke。
- 页面级表格 wrapper 没有完全统一到 `FinanceTable`，因此共享 primitive 测试不能替代每个页面的筛选/排序/导出/状态测试。
- `useFinanceTableSession` 当前未被大多数页面直接调用；页面若自建 session，必须在页面模块里单独覆盖恢复和隔离。

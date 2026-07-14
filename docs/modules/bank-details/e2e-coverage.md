# 银行明细 Spec-first E2E Coverage

本文把 `bank-details` 的 Browser E2E Spec 映射到现有自动化测试。状态定义见 `docs/dev/spec-first-e2e-audit.md`。

## 覆盖矩阵

| Spec ID | 状态 | 当前覆盖 | 缺口/说明 |
| --- | --- | --- | --- |
| `BANK-E2E-001` | `covered` | `web/e2e/bank-details-initial-state.spec.ts`、`web/e2e/workbench-relation-fanout.spec.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts`、`web/src/test/BankDetailsPage.test.tsx` | Browser 已证明当前年默认 query、全部账户首屏、账户余额、账户列表、默认列、relation/category 字段和 fresh 空结果空态；Vitest/API 继续覆盖更多账户组合和 API mapper。 |
| `BANK-E2E-002` | `covered` | `web/e2e/workbench-relation-fanout.spec.ts`、`tests/test_bank_details_service.py` | Browser/后端回归已证明只有正式 linked relation 显示关系标签，非正式分布输入被忽略；Workbench confirm 后回银行明细显示 `有oa` / `有发票`。 |
| `BANK-E2E-003` | `covered` | `web/e2e/imports-bank-transactions-flow.spec.ts`、`tests/test_import_formalization_api.py`、`tests/test_bank_details_sql_runtime.py` | Browser 已证明银行流水导入确认后进入银行明细看到导入行。 |
| `BANK-E2E-004` | `covered` | `web/e2e/bank-details-export-download.spec.ts`、`web/e2e/bank-details-filtered-export-permissions.spec.ts`、`tests/test_bank_details_export_service.py`、`web/src/test/BankDetailsApi.test.ts`、`web/src/test/BankDetailsPage.test.tsx` | Browser 已证明默认全银行/全年导出、当前账户 + 月度 + 关键字 + 分类筛选导出、分页状态不限制导出范围、真实 download event、文件名、linked relation 字段和 account/category/date/filter 字段；deterministic mock 返回真实 XLSX workbook，Playwright 会解析 workbook 后再断言业务字段，避免把 CSV 文本伪装成 `.xlsx`；默认导出菜单和导出全部银行已记录 operation latency。 |
| `BANK-E2E-005` | `covered` | `web/e2e/bank-details-filtered-export-permissions.spec.ts`、`web/src/test/BankDetailsPage.test.tsx`、`web/src/test/BankDetailsApi.test.ts` | Browser 已覆盖账户切换、月度时间筛选、搜索关键字、分类筛选、page size 和第二页请求后交易 query 与导出 query 一致；Vitest 覆盖年份、月份、全部和分页重置，账户余额不被筛选覆盖由 Vitest/API 回归保护。 |
| `BANK-E2E-006` | `covered` | `web/e2e/bank-details-auto-tag-rules-flow.spec.ts`、`web/src/test/BankDetailsPage.test.tsx`、`web/src/test/GlobalOperationOverlayContext.test.tsx` | Browser 已覆盖 drawer 保存 PUT 请求体、`expected_version`、当前可见月份 refresh scope、operation barrier fresh 后反馈、重新应用不触发保存、以及 PUT 成功但后置同步 blocked 时显示 warning 而非“操作失败”；打开 drawer、填值、保存、重新应用和 blocked warning 路径已记录 operation latency。 |
| `BANK-E2E-007` | `covered` | `web/e2e/bank-details-category-flow.spec.ts`、`tests/test_bank_auto_tag_rules_api.py`、`tests/test_bank_transaction_category_service.py`、`web/src/test/BankDetailsPage.test.tsx` | Browser 已覆盖 full_access 下只能确认当前候选、确认后刷新为 `manual_confirmed`、撤销回候选状态，以及 unmatched 行外部往来三层人工补分类、请求结构化 turnover 字段、清除后回到待分类；保存和撤销/清除已记录 operation latency。 |
| `BANK-E2E-008` | `covered` | `web/e2e/bank-details-stale-refreshing.spec.ts`、`tests/test_bank_details_routes.py`、`tests/test_bank_details_sql_runtime.py`、`web/src/test/BankDetailsPage.test.tsx` | Browser 已覆盖 transaction `refreshing` 保留可用行、`stale` 空 rows 不误报真空态、非 fresh 导出业务错误、account `schema_mismatch` 自动重试到 fresh、transaction `missing` 初始化态不误报真空表，以及交易请求网络失败后用户触发重试恢复。 |
| `BANK-E2E-009` | `covered` | `web/e2e/bank-details-filtered-export-permissions.spec.ts`、`web/e2e/bank-details-category-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts`、`tests/test_session_api.py`、`web/src/test/BankDetailsPage.test.tsx` | Browser 已证明 `read_export_only` 可导出、自动标签 drawer 写入口禁用、待确认分类按钮禁用且银行明细 mutation API 零调用；`full_access` 和 `admin` 可执行分类写入；forbidden/expired session 在银行明细路由进入 session gate 且不调用任何银行明细 protected API。 |
| `BANK-E2E-010` | `covered` | `web/e2e/bank-details-large-scroll-flow.spec.ts`、`web/src/test/BankDetailsPage.test.tsx` | Browser 已覆盖 120 行长列表、宽字段、桌面纵向滚动、窄屏导出菜单、分类筛选菜单、分类选择浮层和表格横向滚动不遮挡关键操作；真实生产超大数据性能仍按 staging/专项风险处理。 |

## 现有 E2E 审计结论

- 现有银行明细 Browser smoke 可保留：Workbench confirm -> linked tags、未正式化 decision / 历史 candidate 兼容负面语义、银行流水导入后列表展示，以及本轮新增的真实 XLSX workbook 下载解析。
- 新增 `web/e2e/bank-details-initial-state.spec.ts` 保护首屏业务合同：默认当前年范围必须请求 accounts/transactions，全部账户视图必须显示总余额、账户余额、默认列、候选 relation tags、自动分类和 fresh 空态；非 fresh 空态仍由 freshness spec 保护。
- 新增 `web/e2e/bank-details-export-download.spec.ts` 保护的是业务导出合同：导出必须触发真实浏览器下载，必须携带当前筛选，下载文件必须是可解析的 XLSX workbook，文件内容必须包含 confirmed relation 字段，不能只证明按钮被点击；本轮已为回到银行明细、打开导出菜单和导出全部银行记录 operation latency。
- 扩展 `web/e2e/bank-details-stale-refreshing.spec.ts` 保护 freshness 和恢复合同：非 fresh payload 必须给诊断，不能把 stale/missing 空 rows 当真实空列表，导出必须禁用或返回业务错误；account read model 非 fresh 要能自动重试到 fresh，交易请求网络失败后用户重试应恢复当前 rows。
- 扩展 `web/e2e/bank-details-filtered-export-permissions.spec.ts` 保护筛选导出和权限合同：当前账户、月度时间筛选、关键字、分类必须同时带入交易请求和导出请求；page size/翻页只影响列表请求，导出按当前筛选全量导出；`read_export_only` 能下载但不能打开/保存分类或自动标签规则写入口；forbidden/expired session 不渲染银行明细页且不调用 protected API；`admin` 可执行银行明细分类写入。
- 新增 `web/e2e/bank-details-category-flow.spec.ts` 保护分类写入合同：候选确认不能使用全量标签字典，人工补分类不能调用候选确认接口，外部往来三层标签必须带 turnover 语义，保存和撤销/清除后页面都要 refetch 到正确状态；本轮已为保存和撤销/清除记录 operation latency。
- 新增 `web/e2e/bank-details-auto-tag-rules-flow.spec.ts` 保护自动标签规则 drawer 合同：保存必须带版本和当前可见日期 scope，reapply 不能保存草稿，后置同步 blocked 只能降级为同步 warning；本轮已为 drawer 打开、填值、保存、重新应用和 blocked warning 记录 operation latency。
- 新增 `web/e2e/bank-details-large-scroll-flow.spec.ts` 保护大表格和视觉遮挡合同：长列表、宽字段、桌面/窄屏、分类筛选、分类选择浮层、导出菜单和横向滚动不能遮挡关键操作。
- 模块 Browser Spec ID `BANK-E2E-001..010` 已覆盖；银行明细本地 deterministic 下载已覆盖 XLSX workbook 解析，真实生产代理 header、Excel/Numbers 打开结果、真实 worker drain 和生产超大数据性能属于 staging/专项风险。

## 下一轮补测建议

1. 继续从全局 inventory 推进 `workbench-relations` 导出权限/筛选组合、OA pending linked fan-out 或更多撤销链路。
2. 推进 `imports-bank-transactions` 账户冲突、重复行、任务失败和更多下游刷新。

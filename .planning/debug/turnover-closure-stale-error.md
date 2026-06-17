---
status: resolved
trigger: "外部往来款管理中选中两项点击确认闭环后弹出“银行流水状态已变化，请刷新后重试。”；需要修复页面，并解释为什么 e2e 没测出来。"
created: "2026-06-17"
updated: "2026-06-17"
---

# Debug Session: turnover-closure-stale-error

## Symptoms

- Expected behavior:
  - 在外部往来款管理中选中同组两笔可闭环流水，点击 `确认闭环` 后应提交成功，或在真正 stale 时先刷新并让用户重新选择。
- Actual behavior:
  - 页面允许打开确认闭环弹窗，提交后弹出 `操作失败`。
- Error messages:
  - `银行流水状态已变化，请刷新后重试。`
- Timeline:
  - 2026-06-17 用户截图反馈；发生在 OA 关联与闭环 chip 拆分修复后继续完善页面时。
- Reproduction:
  - 外部往来款管理 -> 个人往来 -> 展开贾小花 -> 选中 `txn_imported_1277`、`txn_imported_1292`、`txn_imported_1344`，收支相抵 0.00 -> 点击 `确认闭环` -> 确认弹窗提交。

## Current Focus

- hypothesis: confirmed。真实 `txn_imported_1277/1292/1344` 路径由 SQL bank detail/turnover projection 带出 `category_version=0` 占位值；前端按 `manual_category_version` / `version` 提交真实 `expected_versions`，但后端 stale precondition 把 0 当成当前版本，误报 stale。
- test: 已补 SQL row version fallback 单测、UoW stale precondition 契约测试、`/api/turnover-ledger/closures/confirm` API 集成测试和前端 grouped mapper 测试。
- expecting: 后端用于 grouped payload 和 stale precondition 的 bank row version 一致；三笔贾小花/截图路径确认闭环成功，真正版本变化仍返回 stale。
- next_action: resolved; keep regression tests in `docs/modules/turnover-ledger/tests.md`.

## Evidence

- timestamp: "2026-06-17"
  observation: "截图中两笔选中后按钮可用，但提交后后端返回 `银行流水状态已变化，请刷新后重试。`，说明错误发生在确认请求的 stale precondition，而不是前端选择规则。"
- timestamp: "2026-06-17"
  observation: "web/src/pages/TurnoverLedgerPage.tsx 在确认前重新拉 fresh ledger，并用 `closureExpectedVersions(freshRows)` 构造 `turnover_bank_row:{bankRowId}` expected_versions。"
- timestamp: "2026-06-17"
  observation: "web/e2e/fixtures/apiMocks.ts 对 `/api/turnover-ledger/closures/confirm` 是 mock 成功响应，未模拟 expected_versions 与真实后端 stale precondition 的比对。"
- timestamp: "2026-06-17"
  observation: "用户 12:16 截图显示三笔 `txn_imported_1277`、`txn_imported_1292`、`txn_imported_1344` 收支相抵 0.00，点击确定后仍返回 `银行流水状态已变化，请刷新后重试。`，说明上次页面侧修复未覆盖真实后端版本字段语义。"
- timestamp: "2026-06-17"
  observation: "repo docs/tests 已出现线索：SQL bank detail row 缺 `category_version` 或存在占位 `0` 时，应使用 `manual_category_version` 或基础 `version`，否则 turnover closure stale precondition 会误报。"
- timestamp: "2026-06-17"
  observation: "`test_sql_bank_detail_turnover_row_uses_manual_category_version_when_category_version_is_zero`、`test_sql_bank_detail_turnover_row_falls_back_to_bank_row_version_when_category_version_is_zero`、`test_bank_row_stale_precondition_uses_manual_version_when_category_version_is_zero`、`test_bank_row_stale_precondition_uses_base_version_when_category_versions_are_zero` 证明原先缺少 `category_version=0` 占位分支保护。"
- timestamp: "2026-06-17"
  observation: "`test_manual_closure_api_accepts_sql_rows_with_zero_category_version` 用截图同款 `txn_imported_1277/1292/1344` 和 `category_version=0` 形态走 `/api/turnover-ledger/closures/confirm`，确认 turnover relation 与 Workbench relation 都能写入。"

## Eliminated

- hypothesis: "按钮 gating 仍然把 OA linked 当闭环阻断"
  reason: "截图中 `确认闭环` 已可点击并进入提交，失败来自提交后的 stale precondition。"

## Resolution

- root_cause: 上一轮修复没有覆盖真实 SQL bank detail 的 `category_version=0` 占位语义。页面 fresh reload 后会用 grouped row 中的 `manual_category_version` / `version` 提交 `turnover_bank_row:*` 真实版本；后端 `TurnoverLedgerBankRowStalePreconditionPort` 和 SQL row mapper 却优先取 `category_version`，把 0 当成真实当前版本，因此 4/5/6 与 0 比对失败并误报 `银行流水状态已变化，请刷新后重试。`
- fix: 后端新增共享 `turnover_bank_row_version(row)`，按 `category_version`、`manual_category_version`、`version` 顺序选择第一个非零数值，只有全部缺失或全为 0 时才返回 0；`Application._turnover_bank_transaction_row_from_bank_detail` 和 `TurnoverLedgerBankRowStalePreconditionPort` 共用该逻辑。前端 `turnoverBankRowVersion(...)` 使用同一语义，让 grouped mapper 和后端 precondition 对版本字段达成一致。
- why_previous_fix_incomplete: 当时只修了页面 fresh reload、缺失版本字段和 e2e mock 请求体校验，测试数据没有包含 SQL read model 常见的 `category_version=0` 占位值；因此页面已经提交了更正确的版本，但后端仍按 0 校验，真实数据继续失败。
- why_e2e_missed: 原 e2e fixture 对 `/api/turnover-ledger/closures/confirm` 曾经无条件返回成功；后来虽然补了请求体校验，但 mock fixture 里的 row 版本不是 `category_version=0` + `manual_category_version/version` 的真实 SQL 形态，所以没覆盖这次误报。
- verification:
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_sql_bank_detail_turnover_row_uses_manual_category_version_when_category_version_is_zero tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_sql_bank_detail_turnover_row_falls_back_to_bank_row_version_when_category_version_is_zero tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_bank_row_stale_precondition_uses_manual_version_when_category_version_is_zero tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_bank_row_stale_precondition_uses_base_version_when_category_versions_are_zero tests.test_turnover_workbench_integration.TurnoverWorkbenchIntegrationTests.test_manual_closure_api_accepts_sql_rows_with_zero_category_version -v` passed: 5 tests.
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api tests.test_turnover_ledger_uow_contract tests.test_turnover_workbench_integration -q` passed: 227 tests.
  - `cd web && npm test -- --run src/test/TurnoverLedgerPage.test.tsx src/test/TurnoverLedgerApi.test.ts` passed: 32 tests.
  - `cd web && npx playwright test e2e/turnover-ledger-flow.spec.ts` passed: 1 test.
  - `cd web && npm run build` passed, with existing CSS minifier warnings unrelated to this change.
  - `git diff --check` passed.
- files_changed:
  - `backend/src/fin_ops_platform/app/server.py`
  - `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
  - `tests/test_turnover_ledger_api.py`
  - `tests/test_turnover_ledger_uow_contract.py`
  - `tests/test_turnover_workbench_integration.py`
  - `web/src/features/turnoverLedger/api.ts`
  - `web/src/test/TurnoverLedgerApi.test.ts`
  - `docs/modules/turnover-ledger/tests.md`
  - `docs/modules/turnover-ledger/implementation-notes.md`

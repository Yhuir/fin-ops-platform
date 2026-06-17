---
status: fixed
trigger: "2026-06-17 13:28 截图：外部往来款管理选择 txn_imported_1269 和 txn_imported_1361 两笔 240,000 点击确认闭环，仍弹出“银行流水状态已变化，请刷新后重试。”；需要真实原因并修复。"
created: "2026-06-17"
updated: "2026-06-17"
---

# Debug Session: turnover-closure-1269-stale

## Symptoms

- Expected behavior:
  - 外部往来款管理中选择同组刘涵静两笔 240,000 银行流水，收入和支出合计差额 0.00，点击确认闭环应成功写入 turnover manual relation 和 Workbench relation。
- Actual behavior:
  - 确认弹窗提交后弹出 `操作失败`。
- Error messages:
  - `银行流水状态已变化，请刷新后重试。`
- Timeline:
  - 2026-06-17 13:28 用户截图反馈；上一轮针对 `txn_imported_1277/1292/1344` 的 `category_version=0` 占位修复后仍发生。
- Reproduction:
  - 外部往来款管理 -> 个人往来 -> 展开刘涵静 -> 选中 `txn_imported_1269` 和 `txn_imported_1361` -> 点击 `确认闭环` -> 确认弹窗提交。

## Current Focus

- hypothesis: 生产 `turnover_ledger` grouped read model 仍保存旧版本投影：flow row 只带 `category_version=0`，缺少 `manual_category_version/version`，且上一轮未 bump `TURNOVER_LEDGER_SCHEMA_VERSION`，所以 API 把旧投影当 fresh 返回；前端只能提交 expected version 0，后端 live precondition 使用非零真实版本后判 stale。
- test: 用 Chrome 登录态同源 fetch 检查生产 grouped payload；补 `TurnoverLedgerService` grouped flow row 版本 fallback 测试和 source version schema bump 测试。
- expecting: 修复后 projection 生成的 grouped flow row 使用 `category_version -> manual_category_version -> version` 的第一个非零版本，并且 schema version bump 让线上旧 read model 失效并重建。
- next_action: run target backend/frontend verification and require deployment plus turnover_ledger worker rebuild for production.

## Evidence

- timestamp: "2026-06-17"
  observation: "截图 4 错误文案仍为 `银行流水状态已变化，请刷新后重试。`，该文案由 `TurnoverLedgerBankRowStalePreconditionPort` 抛出。"
- timestamp: "2026-06-17"
  observation: "截图 3 显示确认抽屉内两笔 row id 是 `txn_imported_1269` 和 `txn_imported_1361`，不是上一轮验证的 `txn_imported_1277/1292/1344`。"
- timestamp: "2026-06-17"
  observation: "截图 2 中 `txn_imported_1361` 有 `已关联 OA` chip，但按钮已允许确认闭环且错误发生在提交后，初步排除前端 gating 问题。"
- timestamp: "2026-06-17"
  observation: "生产 `/fin-ops-api/health` 显示 release `main-aaebca63-20260617132030`，git commit `aaebca63ca0c223e915d9c4267f79ba593e00faa`；远程 `/fin-ops/` index 与本地 `web/dist/index.html` sha256 一致，排除“上一轮代码未部署”为根因。"
- timestamp: "2026-06-17"
  observation: "生产前端 chunk `TurnoverLedgerPage-DdPRLU7u.js` 已包含 `category_version/manual_category_version/version` fallback 和 `expected_versions` 提交逻辑。"
- timestamp: "2026-06-17"
  observation: "使用 Chrome 登录态同源 fetch `/fin-ops-api/api/turnover-ledger?view=grouped&family=personal&direction=all&page=1&page_size=100`，`txn_imported_1269` 与 `txn_imported_1361` 均返回 `category_version: 0`，且没有 `manual_category_version` 或 `version` 字段。"
- timestamp: "2026-06-17"
  observation: "`TurnoverLedgerService._bank_rows`、`_flow_rows`、`_unclassified_item` 仍按 `int(category_version or 0)` 投影 flow row；`TURNOVER_LEDGER_SCHEMA_VERSION` 仍为 `2026-05-turnover-ledger-v1`，上一轮版本语义变化没有让旧 `turnover_ledger` read model stale。"
- timestamp: "2026-06-17"
  observation: "新增 `test_grouped_ledger_uses_manual_version_when_category_version_is_zero`、`test_grouped_ledger_uses_bank_row_version_when_category_versions_are_zero`、source version bump 测试后，修复前均失败。"

## Eliminated

- hypothesis: "金额不平导致闭环失败"
  reason: "确认抽屉显示收入合计 240,000.00、支出合计 240,000.00、差额 0.00；后端返回的也不是 amount mismatch 文案。"
- hypothesis: "线上仍跑旧 commit 或前端旧 bundle"
  reason: "健康检查和静态资源 hash 已确认生产前后端都是上一轮修复后的 `aaebca63`；远程 chunk 也包含前端 fallback。"
- hypothesis: "OA 关联 chip 禁止闭环"
  reason: "页面已进入确认抽屉并向 confirm API 提交，错误文案来自 bank row stale precondition，不是前端 toolbar gating 或 OA relation scope check。"

## Resolution

- root_cause: "上一轮只修了 live bank detail 转换、前端 mapper 和后端 stale precondition，漏掉了生产正在读取的 saved `turnover_ledger` grouped read model。旧 read model 仍投影 `category_version=0` 且缺少 fallback 字段；因为 `TURNOVER_LEDGER_SCHEMA_VERSION` 没变，API 认为旧投影 fresh。前端按 fresh/rebind 规则重拉后仍只能得到 0，于是提交 `expected_versions=0`；后端 live precondition 读取到非零真实版本，返回 `银行流水状态已变化`。"
- fix: "抽出共享 `turnover_bank_row_version` helper；`TurnoverLedgerService` 在生成 bank rows、classified flow rows、unclassified flow rows 时统一按 `category_version -> manual_category_version -> version` 选择第一个非零版本并保留 fallback 字段；将 `TURNOVER_LEDGER_SCHEMA_VERSION` bump 到 `2026-06-turnover-ledger-v2`，发布后触发旧 `turnover_ledger` read model stale/rebuild。"
- why_previous_fix_incomplete: "e2e 和上一轮集成测试使用新生成的 fixture/API payload，覆盖了前端 mapper、API 转换和 live precondition，但没有模拟“生产已存在的 SQL grouped read model 在 schema version 未变时继续被当 fresh 返回”。因此测试没有碰到旧投影只含 `category_version=0` 的路径。"
- verification:
  - "PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_service.TurnoverLedgerServiceTests.test_grouped_ledger_uses_manual_version_when_category_version_is_zero tests.test_turnover_ledger_service.TurnoverLedgerServiceTests.test_grouped_ledger_uses_bank_row_version_when_category_versions_are_zero -v"
  - "PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_source_versions.TurnoverLedgerSourceVersionsTests.test_source_versions_include_all_turnover_and_cross_module_inputs -v"
  - "PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_bank_row_stale_precondition_uses_manual_version_when_category_version_is_zero tests.test_turnover_ledger_uow_contract.TurnoverLedgerUoWContractTests.test_bank_row_stale_precondition_uses_base_version_when_category_versions_are_zero -v"
  - "PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_service tests.test_turnover_ledger_source_versions -v"
  - "PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_uow_contract -v"
  - "PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v"
  - "PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_workbench_integration tests.test_turnover_ledger_read_model_refresh -v"
  - "npm --prefix web test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx src/test/OperationBarrierApi.test.ts"
  - "npm --prefix web run build"
  - "bash scripts/verify.sh docs"
  - "cd web && npx playwright test e2e/turnover-ledger-flow.spec.ts"
  - "git diff --check"
- files_changed:
  - "backend/src/fin_ops_platform/services/turnover_bank_row_version.py"
  - "backend/src/fin_ops_platform/services/turnover_ledger_service.py"
  - "backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py"
  - "backend/src/fin_ops_platform/app/server.py"
  - "tests/test_turnover_ledger_service.py"
  - "tests/test_turnover_ledger_source_versions.py"
  - "docs/modules/turnover-ledger/implementation-notes.md"
  - "docs/modules/turnover-ledger/state-machine.md"
  - "docs/modules/turnover-ledger/tests.md"
  - "docs/modules/read-models/implementation-notes.md"
  - "docs/modules/read-models/tests.md"

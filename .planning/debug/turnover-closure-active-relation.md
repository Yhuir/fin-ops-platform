---
status: fixed
trigger: "2026-06-21 20:44 screenshots: 外部往来款页面选择 txn_imported_1277、txn_imported_1292、txn_imported_1344 三条流水后点击确认闭环，弹出 Bank transaction already belongs to an active turnover relation."
created: "2026-06-21"
updated: "2026-06-21"
---

# Debug Session: turnover-closure-active-relation

## Symptoms

- Expected behavior:
  - 外部往来款页面同组真实银行流水收入合计 300,000.00、支出合计 300,000.00、差额 0.00 时，点击确认闭环应写 Turnover manual closure 和 Workbench turnover_manual_closure relation。
- Actual behavior:
  - 点击确认后弹出操作失败。
- Error messages:
  - `Bank transaction already belongs to an active turnover relation: txn_imported_1277, txn_imported_1292, txn_imported_1344`
- Timeline:
  - 2026-06-21 20:44 用户截图反馈。
- Reproduction:
  - 外部往来款 -> 个人往来 -> 选择三条同组流水 `txn_imported_1277`、`txn_imported_1292`、`txn_imported_1344` -> 点击确认闭环 -> 确认弹窗提交。

## Current Focus

- hypothesis: `TurnoverRelationService.confirm_zero_difference_closure()` 在写闭环前无条件拒绝任何 `status=confirmed` 的 Turnover relation overlap；当这三条流水已经处于普通人工 confirmed relation 但尚未形成现金闭环时，后端应升级同一 relation 为 manual closure，却被通用占用检查挡住。
- test: 新增 `test_confirm_zero_difference_closure_upgrades_existing_confirmed_relation_for_same_rows`，先用 `confirm_relation()` 创建普通 confirmed relation，再对同一三条流水确认零差额闭环。
- expecting: 修复前测试失败并抛 `turnover_relation_conflict`；修复后返回同一 relation id，`evidence.closure_mode=manual_zero_difference_group`，服务内只保留一条 confirmed closure relation。
- next_action: run docs verification and final diff checks.

## Evidence

- timestamp: "2026-06-21 20:47"
  observation: "截图确认抽屉显示三条流水收入合计 300,000.00、支出合计 300,000.00、差额 0.00，前端已允许进入闭环提交。"
- timestamp: "2026-06-21 20:47"
  observation: "错误文案完整匹配 `TurnoverRelationService._ensure_no_active_confirmed_overlap()`，不是 Workbench relation command service 的 OA-bank/invoice 合并前置检查。"
- timestamp: "2026-06-21 20:47"
  observation: "模块文档要求已关联 OA-bank 的流水可合并进同一个 turnover_manual_closure；但当前失败发生在本地 Turnover relation 创建阶段，Workbench 合并逻辑没有执行。"
- timestamp: "2026-06-21 20:47"
  observation: "`confirm_zero_difference_closure()` 在 `_ensure_no_manual_closure_overlap()` 前先调用 `_ensure_no_active_confirmed_overlap()`，因此普通 confirmed relation 与已闭环 relation 都被同一英文 active relation 错误拦截。"

## Eliminated

- hypothesis: "三条流水金额不平导致闭环失败"
  reason: "截图确认抽屉显示收入合计与支出合计均为 300,000.00，差额 0.00；后端返回也不是 amount mismatch。"
- hypothesis: "前端不该允许选择已关联 OA 的流水"
  reason: "当前模块规格明确允许仅含 OA+bank 的既有关联合并；且错误来自 Turnover 本地 relation overlap，不是前端 gating。"

## Resolution

- root_cause: "`TurnoverRelationService.confirm_zero_difference_closure()` 在创建闭环 relation 前先调用通用 `_ensure_no_active_confirmed_overlap()`。当用户选择的三条流水已经处于同一条普通 Turnover `confirmed` relation、但还没有 `manual_zero_difference_group` 闭环 evidence 时，该检查把可升级的同一 relation 错误当成不可覆盖占用，直接抛出 `turnover_relation_conflict`；因此 Workbench `turnover_manual_closure` 合并/写入链路没有执行。"
- fix: "闭环路径改为先拒绝已存在的 manual closure overlap，再执行闭环专用 confirmed overlap 检查：普通 `confirmed` relation 只有在 existing bank row set 与本次请求完全一致时允许升级并复用同一 `relation_id`；部分重叠仍保持 `turnover_relation_conflict`。"
- verification:
  - "RED: PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_relation_service.TurnoverRelationServiceTests.test_confirm_zero_difference_closure_upgrades_existing_confirmed_relation_for_same_rows -v"
  - "PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_relation_service.TurnoverRelationServiceTests.test_confirm_zero_difference_closure_upgrades_existing_confirmed_relation_for_same_rows tests.test_turnover_relation_service.TurnoverRelationServiceTests.test_confirm_zero_difference_closure_rejects_already_closed_rows -v"
  - "PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_relation_service -v"
  - "PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_workbench_integration tests.test_turnover_ledger_uow_contract -v"
  - "PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v"
  - "bash scripts/verify.sh docs"
  - "git diff --check"
- files_changed:
  - "backend/src/fin_ops_platform/services/turnover_relation_service.py"
  - "tests/test_turnover_relation_service.py"
  - "docs/modules/turnover-ledger/implementation-notes.md"
  - "docs/modules/turnover-ledger/tests.md"
  - ".planning/debug/turnover-closure-active-relation.md"

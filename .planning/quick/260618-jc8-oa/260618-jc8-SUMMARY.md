---
status: complete
---

# Quick Task 260618-jc8 Summary

## Outcome

`进项发票使用情况 -> 以发票反提 OA` 已新增 `暂存` 闭环。创建 OA 草稿成功后，本地 batch 使用已有 `oa_draft_created` 事实状态进入用户可见 `暂存`。用户关闭确认弹窗不会丢失 batch，后续可在 `暂存` 中继续选择已提交或需修改。

## Changed Files

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
- `tests/test_input_invoice_usage_api.py`
- `tests/test_input_invoice_usage_oa_reverse_service.py`
- `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`
- `web/src/features/inputInvoiceUsage/api.ts`
- `web/src/features/inputInvoiceUsage/types.ts`
- `web/src/pages/InputInvoiceUsagePage.tsx`
- `web/src/app/styles.css`
- `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`
- `web/e2e/input-invoice-usage-flow.spec.ts`
- `docs/dev/api-contracts.md`
- `docs/modules/input-invoice-usage/README.md`
- `docs/modules/input-invoice-usage/state-machine.md`
- `docs/modules/input-invoice-usage/oa-reverse-design.md`
- `docs/modules/input-invoice-usage/tests.md`
- `docs/modules/input-invoice-usage/e2e-spec.md`
- `docs/modules/input-invoice-usage/e2e-coverage.md`
- `docs/modules/input-invoice-usage/implementation-notes.md`

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_oa_reverse_service tests.test_input_invoice_usage_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_input_invoice_usage_oa_reverse_repository -v`
- `npm --prefix web test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx src/test/InputInvoiceUsagePage.test.tsx`
- `npm --prefix web test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx -t "staged tab recovers"`
- `npm --prefix web run build`
- `npm --prefix web run e2e -- e2e/input-invoice-usage-flow.spec.ts`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Test Coverage Mapping

- Business core unit tests: covered by `InputInvoiceUsageOaReverseServiceTests.test_staged_drafts_returns_created_drafts_waiting_for_user_decision`.
- Service-layer tests: covered by service staged draft tests and repository regression.
- API contract tests: covered by `InputInvoiceUsageApiTests.test_oa_reverse_staged_drafts_route_returns_created_drafts_for_recovery`.
- Read model/cache/background job tests: not applicable; this task reuses existing OA reverse batch repository state and does not introduce a new read model or worker.
- Frontend component and interaction tests: covered by staged tab recovery, dialog close, button copy, and no draft-link assertions.
- End-to-end business-flow integration tests: existing Chromium flow covers create draft -> submitted history; staged recovery is covered by service/API/Vitest because it is a drawer-local recovery path over persisted batch state.
- Existing feature regression tests: covered by existing input invoice usage page/drawer tests, backend API suite, and Playwright submitted-history smoke.

## Notes

- `暂存` intentionally does not expose the OA draft link in the staged list per user decision.
- Real external OA system submission remains a staging/manual-smoke concern; this task changes FinOps local recovery and confirmation flow only.

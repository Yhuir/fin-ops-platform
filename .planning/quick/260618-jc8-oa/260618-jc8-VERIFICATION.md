---
status: passed
---

# Quick Task 260618-jc8 Verification

## Must Haves

- `待处理 | 暂存 | 已提交` 三段状态存在。
- 创建 OA 草稿后，`oa_draft_created` batch 可通过统一后端事实源恢复到 `暂存`。
- 用户关闭确认弹窗不会清理 batch 或调用 manual status。
- `暂存` 列表不展示 OA 草稿链接。
- `暂存` 列表只提供两项处理动作。
- submitted 决策进入已提交历史。
- not_submitted 决策清理本地草稿字段并恢复可重新创建。
- 模块文档和 API contract 同步更新。

## Evidence

- Service/API tests prove `oa_draft_created` is the staged source of truth.
- Frontend interaction tests prove dialog close -> staged recovery, no draft link, and staged submitted decision.
- Existing drawer tests continue to cover not_submitted local rollback semantics.
- Chromium E2E covers create draft -> submitted confirmation -> submitted history.
- Docs verification passed.

## Verification Commands

- `PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_oa_reverse_service tests.test_input_invoice_usage_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_input_invoice_usage_oa_reverse_repository -v`
- `npm --prefix web test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx src/test/InputInvoiceUsagePage.test.tsx`
- `npm --prefix web test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx -t "staged tab recovers"`
- `npm --prefix web run build`
- `npm --prefix web run e2e -- e2e/input-invoice-usage-flow.spec.ts`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Residual Risk

真实 OA 草稿页面、外部 OA 手工提交流程和生产凭据只适合 staging/manual smoke；本地自动化不连接真实 OA。

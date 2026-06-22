---
status: resolved
trigger: "OA待付款右侧抽屉栏没数据，bank-transaction-candidates 接口返回 HTML 页面，说明请求没有进入后端 API"
created: 2026-06-22
updated: 2026-06-22
---

# Debug Session: OA Pending Payment Bank Candidates HTML

## Symptoms

- Expected behavior: OA 待付款右侧「关联支出流水」抽屉应加载银行流水候选数据或返回明确的 API JSON 错误。
- Actual behavior: 抽屉显示加载中/无流水，前端提示 `/api/oa-pending-payments/bank-transaction-candidates?relation_status=all&page=1&page_size=100` 返回了 HTML 页面。
- Error messages: "接口返回了 HTML 页面...说明请求没有进入后端 API，请确认后端服务和代理路径已正常配置。"
- Timeline: 用户在 2026-06-22 15:01 截图反馈；是否曾正常工作未知。
- Reproduction: 进入 OA 待付款页面，选择 OA 记录，打开右侧关联支出流水抽屉。

## Current Focus

- hypothesis: API client fallback was too narrow; root `/api/*` HTML responses only retried `/fin-ops-api/*` when the current page path was `/fin-ops/...`.
- test: add frontend API client regression for bank candidate request outside `/fin-ops` page path, then rerun API client, OA page, and backend candidate route tests.
- expecting: root `/api/oa-pending-payments/bank-transaction-candidates?...` HTML response retries `/fin-ops-api/api/oa-pending-payments/bank-transaction-candidates?...` and returns JSON.
- next_action: resolved
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- 2026-06-22: `web/src/features/oaPendingPayments/api.ts` sends candidates through `apiRequestJson("/api/oa-pending-payments/bank-transaction-candidates?...")`.
- 2026-06-22: `web/src/features/apiClient.ts` only retried `/fin-ops-api/*` when `window.location.pathname` was `/fin-ops` or `/fin-ops/...`.
- 2026-06-22: local `Application.handle_request` returns JSON for both `/api/oa-pending-payments/bank-transaction-candidates?...` and `/fin-ops-api/api/oa-pending-payments/bank-transaction-candidates?...`; backend route is not the failing component.
- 2026-06-22: failing test reproduced the screenshot error for `/oa-pending-payments` page path: `ApiClientError: 接口返回了 HTML 页面...`.

## Eliminated

- Backend route missing: eliminated by direct `handle_request` checks and existing route branch.
- Candidate drawer bypassing API client: eliminated by `fetchOaPendingPaymentBankCandidates` using `apiRequestJson`.

## Resolution

- root_cause: `finOpsApiFallbackUrl` required the browser page path to be under `/fin-ops`, so a valid root `/api/*` request that got the SPA shell outside that path did not retry the canonical production API prefix.
- fix: retry same-origin root `/api/*` HTML responses through `/fin-ops-api/*` regardless of current page path.
- verification: `cd web && npm test -- --run src/test/apiClient.test.ts`; `cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`; `PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_api.OaPendingPaymentApiTests.test_bank_transaction_candidates_route_delegates_to_command_service -v`; `bash scripts/verify.sh docs`; `cd web && npm run build`.
- files_changed: `web/src/features/apiClient.ts`, `web/src/test/apiClient.test.ts`, `docs/modules/oa-pending-payments/tests.md`.

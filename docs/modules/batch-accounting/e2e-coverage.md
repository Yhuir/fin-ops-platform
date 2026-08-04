# 批量账务 E2E 覆盖映射

日期：2026-08-05

| Spec ID | Browser E2E | Frontend component/API | Backend/API/repository | 状态 |
| --- | --- | --- | --- | --- |
| BA-E2E-001 | `batch-accounting-flow.spec.ts` 页面打开 | `BatchAccountingPage.test.tsx` 首屏；`BatchAccountingApi.test.ts` DTO | `test_batch_accounting_api.py` canonical shape | covered |
| BA-E2E-002 | transient failure recovery | loading/empty/error/retry tests | empty、invalid、503 contract tests | covered |
| BA-E2E-003 | 页面 flow 使用专属 GET | server-search/page-reset test；API query test | OA search、summary、pagination；PostgreSQL integration | covered |
| BA-E2E-004 | submit relation flow | amount/note/select/一次 GET | submit、dedupe、CAS、conflict、command delegation | covered |
| BA-E2E-005 | submitted/withdraw flow | submitted detail、withdraw dialog、一次 GET | active batch relation、canonical members、withdraw | covered |
| BA-E2E-006 | permissions role matrix | 只读 session 交互 | `read_export_only` API rejection | covered |
| BA-E2E-007 | narrow viewport、failure recovery | 200 行分页、selection cleanup、reload failure | 固定 query-count guard、page-size validation | covered |
| BA-E2E-008 | compact canonical tag drawer + 保存后左栏过滤 | 标签 chip、checkbox、只读保存、规则 error/no-op | tag-rules GET/PUT、Settings CAS/audit、提交时二次校验、canonical classifier integration | covered |

## 旧契约清理证据

- `BatchAccountingApi.test.ts` 和 backend contract test 断言旧 read-model/barrier 字段不存在。
- `BatchAccountingPage.test.tsx` 不包含 freshness warning 或 polling 用例。
- `apiMocks.ts` 不再提供 batch-accounting read-model status 选项。
- boundary guard 禁止页面 service/route/server 恢复旧 Workbench loaders 或 relation facade。

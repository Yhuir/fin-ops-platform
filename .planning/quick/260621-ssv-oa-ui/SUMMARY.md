---
quick_id: 260621-ssv
slug: oa-ui
status: complete
date: 2026-06-21
---

# Summary

完成免 OA 流水批量处理右侧流水栏的行级银行明细标签显示。

## Changes

- `web/src/pages/NoOaBankBatchPage.tsx`
  - 增加 `bankDetailTagLabels(...)`，优先使用 detail row 的 `categoryLabelPath`，缺失时回退主标签、子标签、标签名和 code。
  - 在右侧流水表“摘要/用途/备注”单元格内渲染银行明细标签 chip。
  - relation context labels 只计算一次，避免重复调用。
- `web/src/app/styles.css`
  - 增加银行明细标签行和 chip 样式。
  - 将摘要/备注样式从 `span:first-child/last-child` 改为显式 class，避免新增 chip 继承错误样式。
- `web/src/test/NoOaBankBatchApi.test.ts`
  - detail row mapper 测试覆盖 `category_primary_label/category_sub_label/category_label_path`。
- `web/src/test/NoOaBankBatchPage.test.tsx`
  - 页面测试覆盖右侧流水行内银行明细标签显示。
  - CSS contract 测试覆盖标签行换行和 chip 样式。
- `docs/modules/no-oa-bank-batches/implementation-notes.md`
  - 记录本轮 UI 决策、测试覆盖和未测风险。
- `docs/modules/no-oa-bank-batches/tests.md`
  - 更新影响面和历史 bug 回归库。

## Verification

Passed:

```bash
cd web && npm test -- --run src/test/NoOaBankBatchApi.test.ts src/test/NoOaBankBatchPage.test.tsx
```

Result: 2 files passed, 34 tests passed.

Passed:

```bash
cd web && npm run build
```

Result: TypeScript build and Vite production build completed. Vite still emitted existing CSS minify warnings for empty `:is()` selectors from bundled styles; they did not block the build and were not introduced by this no-OA change.

Passed:

```bash
bash scripts/verify.sh docs
```

Result: command exited 0 with no output.

## Seven Test Categories

- Business core unit tests: not applicable; no batch generation, state transition, amount calculation, selection, or submit rule changed.
- Service-layer tests: not applicable; no application service, repository, audit, rollback, or worker behavior changed.
- API contract tests: covered through frontend API mapper test for detail row bank detail tag fields; backend HTTP shape was not changed.
- Read model/cache/background job tests: not applicable; no freshness, cache, dirty scope, or background job behavior changed.
- Frontend component and interaction tests: covered through no-OA page test for visible row-level tags and CSS contract.
- End-to-end business-flow integration tests: not applicable; no cross-module write flow changed.
- Existing feature regression tests: covered by existing no-OA API/page test suites for pagination, tag drawer, submit/withdraw, read-only gates, stale polling, and relation-backed submitted display.

## Remaining Risk

Production-scale visual smoke is still needed for very long tag paths, long summaries, and large months in a real browser session.

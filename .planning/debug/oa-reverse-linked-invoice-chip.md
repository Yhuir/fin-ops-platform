---
status: resolved
trigger: "这条发票有oa（截图1），为什么在以发票反提 OA 里显示未关联oa"
created: 2026-06-17
updated: 2026-06-17
---

# Debug Session: oa-reverse-linked-invoice-chip

## Symptoms

- Expected behavior: 在 `以发票反提 OA` drawer 中，已有 active OA 关系的发票显示 `已关联oa`、不可勾选；关联台未配对区 OA candidate 显示 `候选oa`、不可勾选；没有 OA 关系的发票显示 `未关联oa`、可勾选。
- Actual behavior: 截图中的发票 `26539150014000293929` 在关联台未配对区显示有 OA candidate，但在 `以发票反提 OA` drawer 中显示 `未关联oa`。
- Error messages: 无。
- Timeline: 2026-06-17 发现。
- Reproduction: 在进项发票使用情况打开 `以发票反提 OA`，查看发票 `26539150014000293929` 的 OA 关联 chip。

## Current Focus

- hypothesis: 确认。OA reverse 之前只有 `linked/unlinked` 二态，未把 `relationStatus=candidate` 映射为独立状态，导致关联台未配对区的 OA candidate 默认显示为 `未关联oa`。
- test: 已新增 service/API candidate OA preview 回归，并更新前端 drawer 交互测试覆盖 `候选oa` chip、禁用勾选和筛选。
- expecting: `candidate` relation 不进入创建草稿候选；preview 返回 `reasonCode=already_has_candidate_oa`、`oaRelationStatus=candidate`；前端显示 `候选oa`。
- next_action: run full targeted verification and report.

## Evidence

- 2026-06-17: 截图 1 所在区域是关联台 `未配对`，该 OA/发票关系是 open/proposed candidate，不是 active/linked confirmed relation。
- 2026-06-17: `InputInvoiceUsageQueryService` 已通过 OA summaries 保留 `relationStatus=candidate`，既有测试 `test_candidate_relations_are_displayed_without_marking_invoice_paid` 说明 candidate 只作候选展示。
- 2026-06-17: 旧 OA reverse preview 只用 `row.oa.relationCount > 0` 判定 linked；candidate summaries 没有独立 chip 状态，前端又把缺省状态归为 `unlinked`。
- 2026-06-17: 新增 `test_preview_marks_oa_candidate_relations_without_treating_them_as_unlinked` 后，修复前会得到 active/unlinked 误分类；修复后通过。

## Eliminated

- “该发票已确认 linked OA 但 preview 没读到 active relation”：排除。截图中的关系位于关联台未配对区，语义是 candidate。
- “前端单纯文案错误”：排除。后端 contract 没返回 candidate 状态，前端无法正确区分。

## Resolution

- root_cause: OA reverse preview 和 drawer 的 OA 关系状态是二态模型，只区分 active linked 与 unlinked；关联台未配对区 OA candidate 虽然在主列表/关联台可见，但反提 OA drawer 没有把它作为 `candidate` 返回和展示，所以误显示为 `未关联oa`。
- fix: 后端从 OA summaries/`relationStatus` 归一化 `linked/candidate/unlinked`；candidate 返回 `already_has_candidate_oa` rejected row；前端 mapper/types/drawer 支持 `候选oa` chip、禁用勾选和筛选；文档/API contract/测试矩阵同步。
- verification: Added and ran focused service/API/frontend tests; broader targeted verification pending in current turn.
- files_changed: `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`, `tests/test_input_invoice_usage_oa_reverse_service.py`, `tests/test_input_invoice_usage_api.py`, `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`, `web/src/features/inputInvoiceUsage/api.ts`, `web/src/features/inputInvoiceUsage/types.ts`, `web/src/app/styles.css`, `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`, `docs/modules/input-invoice-usage/*`, `docs/dev/api-contracts.md`

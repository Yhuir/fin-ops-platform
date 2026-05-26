# 银行明细自动标签规则管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在银行明细页面提供生产级自动标签规则管理能力，让用户维护标签、规则、优先级和停用状态，并保持下游按稳定标签 code 实时解析最新名称。

**Architecture:** 以现有 `bank_transaction_tags` 字典为唯一事实源，给参与自动命中的标签扩展 `rules`、`priority` 和状态，不新增平行规则存储。自动分类服务从同一字典读取语义字段规则，保存 API 只写配置、审计和生命周期 dirty，不在请求内同步重算历史流水。前端在银行明细页新增 60% 右侧抽屉，读写新的规则 API，并复用现有标签版本同步事件刷新银行明细和待找发票等页面。

**Tech Stack:** Python `unittest` backend, in-memory/state-store application services, React + TypeScript, MUI Drawer/Table/Form controls, Vitest/Testing Library frontend tests. User explicitly requires working on `main`; do not create a branch or worktree.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-05-26-bank-auto-tag-rules-design.md`
- Execution prompt: `docs/archive/prompts/2026-05-26-bank-auto-tag-rules-execution.md`
- Repository instructions: `AGENTS.md`

## Files and Responsibilities

- `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
  - Extend tag dictionary normalization with auto-rule metadata while keeping existing `definitions` and `tags` compatibility.
  - Provide semantic field metadata, default migrated rules, active/archived rule projection, rule validation, custom code generation, priority normalization, and rule summary helpers.
- `backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py`
  - Replace hard-coded `_TEXT_RULES` as the runtime source with normalized rules from the tag dictionary.
  - Match semantic fields using `(exact OR contains) AND NOT excludes`, preserve internal transfer first, and return evidence where available.
- `backend/src/fin_ops_platform/services/app_settings_service.py`
  - Persist normalized rules in `bank_transaction_tags`, keep public tag dictionary backward compatible, reject archiving downstream-referenced tags, record audit, and reconfigure category/auto-category services.
- `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
  - Add `bank_auto_tag_rules_changed` event covering bank detail, workbench, pending invoice, cost statistics, and search derived domains.
- `backend/src/fin_ops_platform/app/server.py`
  - Add `GET /api/bank-details/auto-tag-rules` and `PUT /api/bank-details/auto-tag-rules`, permission checks, structured errors, lifecycle trigger, and no synchronous history rebuild.
- `backend/src/fin_ops_platform/services/bank_details_service.py`
  - Ensure bank detail rows continue resolving labels from current tag dictionary and carry auto-category evidence only if provided by the auto-category service.
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
  - Check if response payloads need current label resolution for `batch_type`; update only if labels are currently hard-coded or copied.
- `backend/src/fin_ops_platform/services/turnover_ledger_service.py`
  - Preserve existing dirty user changes; update only if turnover output copies stale tag labels instead of resolving by code.
- `backend/src/fin_ops_platform/services/workbench_matching_rules.py`
  - Preserve existing dirty user changes; update only if workbench relation labels need current tag dictionary lookup.
- `web/src/features/bankDetails/types.ts`
  - Add auto-tag rule DTO/domain types and structured error types.
- `web/src/features/bankDetails/api.ts`
  - Add fetch/save helpers for the new endpoints and map backend errors to actionable Chinese messages.
- `web/src/features/bankDetails/AutoTagRulesDrawer.tsx`
  - New drawer component for active/archived tabs, system row, add/rename/rules/reorder/archive/re-enable, validation, dirty-close confirmation, and read-only permissions.
- `web/src/test/AutoTagRulesDrawer.test.tsx`
  - New focused component tests for drawer-only behavior before page integration.
- `web/src/pages/BankDetailsPage.tsx`
  - Add top-right `自动标签规则` button, drawer state, save success refresh, and existing tag sync event broadcast.
- `web/src/test/BankDetailsPage.test.tsx`
  - Cover page button, opening the drawer, and save-success page refresh/sync.
- `tests/test_bank_transaction_category_service.py`
  - Cover rule dictionary normalization, generated codes, priority, validation, active/archived split, and current-label resolution.
- `tests/test_bank_transaction_auto_category_service.py`
  - Cover semantic-field matching, exact/contains/excludes, default rule parity, archived ignored, and internal transfer precedence.
- `tests/test_bank_auto_tag_rules_api.py`
  - New focused API tests for GET/PUT, 400/403/409/reference errors, lifecycle, audit, and no synchronous full scan.
- `tests/test_app_settings_service.py`, `tests/test_pending_invoice_service.py`, `tests/test_no_oa_bank_batch_service.py`, `tests/test_turnover_workbench_integration.py`, `tests/test_workbench_v2_api.py`
  - Add only the narrow rename/reference propagation checks needed by existing service boundaries.
- `docs/product-specs/bank-details.md`
  - Replace old “app-only automatic tags/no management UI” wording with the new rule-management behavior.
- `docs/product-specs/pending-invoices.md`
  - Document that pending invoice filters store tag codes and resolve current labels from the bank tag dictionary.
- `docs/dev/api-contracts.md`
  - Document `/api/bank-details/auto-tag-rules`.

## Task 1: Backend Rule Model and Default Migration

**Files:**
- Modify: `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
- Modify: `tests/test_bank_transaction_category_service.py`

- [ ] **Step 1: Write failing normalization tests**

Add tests proving:

```python
payload = BankTransactionCategoryService.from_snapshot(None).tag_dictionary_payload()
definitions = {item["code"]: item for item in payload["definitions"]}
self.assertEqual(definitions["fee"]["rules"]["match_fields"], ["counterparty_name", "summary_text", "note_text"])
self.assertEqual(definitions["fee"]["rules"]["contains"], ["手续费", "短信服务费"])
self.assertEqual(definitions["internal_transfer"].get("rules"), None)
```

Also test custom labels without `code` receive stable `custom_...` codes, active rules require `exact` or `contains`, archived rules may keep empty rules, invalid semantic fields fail, and priorities are returned in active order.

Add immutable identity tests:

- existing rules keep their original `code` when only label/rules/order change.
- replacing an existing rule with a different user-supplied `code` is rejected rather than treated as rename.
- new user-created rules must omit `code`; client-supplied custom codes for new labels are rejected.
- no-op saves preserve generated custom codes and do not generate a new code for the same saved tag.
- blank labels fail after trimming.
- duplicate labels fail within active rules and within archived rules. Same label across active and archived is allowed only if the implementation explicitly chooses that contract and tests it.

- [ ] **Step 2: Run failing tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_category_service -v
```

Expected before implementation: fail because tag definitions do not expose normalized `rules`/`priority`.

- [ ] **Step 3: Implement rule metadata helpers**

Implement these public helpers on `BankTransactionCategoryService` or module-level functions:

- `BANK_AUTO_TAG_FIELD_OPTIONS`
- `BANK_AUTO_TAG_SYSTEM_RULE`
- `DEFAULT_BANK_AUTO_TAG_RULES`
- `auto_tag_rules_payload(tag_dictionary)`
- `normalize_auto_tag_rules_update(payload, previous_tag_dictionary)`
- `build_auto_tag_rule_error_payload(error)`

Rules:

- Preserve existing public dictionary fields `version`, `definitions`, `code`, `label`, `path`, `source`, `status`.
- Add `priority` and `rules` only where a definition participates in editable automatic text tagging.
- Keep `internal_transfer` active in the tag dictionary for label resolution, but do not attach editable text `rules`.
- Preserve existing legacy/manual category definitions without forcing them into the drawer.
- Keep default `fee` scoped to `counterparty_name`, `summary_text`, `note_text` only.

- [ ] **Step 4: Run category service tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_category_service -v
```

Expected: pass.

## Task 2: Auto-Category Runtime Uses Semantic Rules

**Files:**
- Modify: `backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py`
- Modify: `tests/test_bank_transaction_auto_category_service.py`

- [ ] **Step 1: Write failing matching tests**

Add tests for:

- exact match only matches the whole normalized semantic field.
- contains match works across selected semantic fields.
- excludes rejects an otherwise positive match.
- priority first match wins.
- archived tags do not match.
- raw bank fields such as `customer_note` can map to `note_text`/`all_text` without exposing raw field names in user rules.
- `purpose/detail` containing only `手续费` still does not match default `fee`.
- `auto_category_evidence` uses the canonical shape for matched text rules:

```python
self.assertEqual(evidence["tag_code"], "salary")
self.assertEqual(evidence["tag_label"], "人员薪酬")
self.assertEqual(evidence["rule_code"], "salary")
self.assertIn("rule_version", evidence)
self.assertEqual(evidence["condition_type"], "contains")
self.assertEqual(evidence["semantic_field"], "note_text")
self.assertEqual(evidence["semantic_field_label"], "备注/附言/客户附言")
self.assertIn("raw_field_key", evidence)      # may be None
self.assertIn("raw_field_label", evidence)    # may be None
self.assertEqual(evidence["matched_text"], "工资")
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_auto_category_service -v
```

Expected before implementation: fail for configurable rule semantics.

- [ ] **Step 3: Implement semantic field extraction and rule matching**

Update `BankTransactionAutoCategoryService` to accept an optional tag dictionary or rule provider and to expose `configure_tag_dictionary(payload)`. Internally:

- Keep `BankInternalTransferDetector.detect()` first.
- Build semantic texts:
  - `counterparty_name`: `counterparty_name`
  - `purpose_text`: `purpose_text` then `purpose`
  - `summary_text`: `summary_text` then `summary`
  - `note_text`: `note_text` then `remark`/`note`/known note fields from nested detail maps
  - `detail_text`: values from `detail_text`, `detail_fields`, `_detail_fields`, `summary_fields`, `_summary_fields`
  - `all_text`: joined unique values from all semantic fields
- Apply `(exact OR contains) AND NOT excludes`.
- Return `category_label` and `category_path` from the configured tag dictionary, not the static label map.
- Keep rule codes stable as the tag code or migrated text rule code when tests require backward compatibility.
- Add `auto_category_evidence` with the canonical spec fields when a text rule matches. `raw_field_key` and `raw_field_label` may be `None`, but `tag_code`, `tag_label`, `rule_code`, `rule_version`, `condition_type`, `semantic_field`, `semantic_field_label`, and `matched_text` must be present.

- [ ] **Step 4: Run auto-category tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_auto_category_service -v
```

Expected: pass.

## Task 3: App Settings, API, Permission, Audit, and Lifecycle

**Files:**
- Modify: `backend/src/fin_ops_platform/services/app_settings_service.py`
- Modify: `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Create: `tests/test_bank_auto_tag_rules_api.py`
- Modify if needed: `tests/test_app_settings_service.py`

- [ ] **Step 1: Inspect persistence/cache surfaces before finalizing lifecycle**

Before adding the event, inspect:

```bash
rg -n "read_model|cache|snapshot|persist|no_oa|turnover|batch" backend/src/fin_ops_platform/services backend/src/fin_ops_platform/app/server.py
```

Record implementation conclusions in code comments only where the lifecycle executor would otherwise be surprising:

- no-OA batch has no separate persistent derived cache from bank tags, or the discovered cache/read model is invalidated by `bank_auto_tag_rules_changed`.
- turnover ledger has no separate persistent derived cache from bank tags, or the discovered cache/read model is invalidated by `bank_auto_tag_rules_changed`.
- workbench, pending invoice, cost statistics, bank detail, and search are covered by concrete lifecycle executors.
- no executor does synchronous full-history recategorization, no-OA rebuild, turnover rebuild, or workbench `all` rebuild in the PUT hot path.

- [ ] **Step 2: Write failing API tests**

Create focused tests asserting:

- GET returns `version`, fixed `system_rule`, `active_rules`, `archived_rules`, `field_options`, and `permissions`.
- PUT succeeds with `expected_version`, generated custom code, normalized priorities, and returns the GET shape.
- PUT rejects `system_rule` or `internal_transfer` mutations with `400 invalid_bank_auto_tag_rules_request`.
- PUT rejects empty positive conditions and invalid fields with field errors.
- PUT rejects blank labels after trimming.
- PUT rejects duplicate active labels and duplicate archived labels.
- PUT rejects client-supplied codes for new tags.
- PUT preserves an existing tag code across rename/rule/order edits and no-op saves.
- PUT rejects stale version with `409 bank_transaction_tags_version_conflict`.
- PUT rejects archiving pending-invoice-referenced tags with `400 bank_transaction_tag_in_use_by_pending_invoice_filter` and `references`.
- PUT with no mutation does not increment version.
- Successful PUT records audit and triggers `bank_auto_tag_rules_changed`.
- Successful PUT audit metadata includes actor, old version, new version, added tag labels/codes, renamed labels, archived codes, re-enabled codes, priority/order changes, and rule-change summaries.
- Successful PUT invalidates any discovered persistent no-OA/turnover derived cache/read model through the same lifecycle event, if such a surface exists.
- Successful PUT does not call a synchronous bank-row full scan, workbench all rebuild, no-OA batch rebuild, or turnover rebuild.

- [ ] **Step 3: Run failing API tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v
```

Expected before implementation: fail because endpoints do not exist.

- [ ] **Step 4: Implement settings and route contract**

Implement:

- Route registration before generic bank transaction routes:
  - `GET /api/bank-details/auto-tag-rules`
  - `PUT /api/bank-details/auto-tag-rules`
- Read permission: same authenticated app view/session pattern as bank details.
- Save permission: `session.can_mutate_data`; otherwise `403 permission_denied`.
- `AppSettingsService.update_bank_auto_tag_rules(...)` or a narrow wrapper around `update_settings(...)` that:
  - validates optimistic version
  - merges rules into `bank_transaction_tags`
  - increments version only when rules/tag metadata changed
  - records `bank_auto_tag_rules_updated` audit metadata
    - actor
    - old/new version
    - added tags
    - renamed labels
    - archived/re-enabled tags
    - priority/order changes
    - rule-change summaries
  - reconfigures both category and auto-category services
- Structured error payload:

```json
{
  "error": "invalid_auto_tag_rule",
  "message": "自动标签规则校验失败。",
  "field_errors": [],
  "references": []
}
```

- [ ] **Step 5: Implement lifecycle event**

Add `bank_auto_tag_rules_changed` to `DerivedDataLifecycleService` with domains:

- `bank_detail_read_model`
- `workbench_read_model`
- `workbench_candidate_matches`
- `workbench_matching_dirty_scopes`
- `pending_invoice_read_model`
- `cost_statistics_read_model`
- `search_cache`

On successful PUT call:

```python
self._execute_derived_data_lifecycle_event(
    "bank_auto_tag_rules_changed",
    scope_keys=["all"],
    include_all=True,
    metadata={"reason": "bank_auto_tag_rules_changed"},
)
```

Do not add synchronous historical recalculation to this handler.

- [ ] **Step 6: Run API and lifecycle tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api tests.test_app_settings_service -v
```

Expected: pass.

## Task 4: Downstream Current-Label Resolution

**Files:**
- Modify if needed: `backend/src/fin_ops_platform/services/bank_details_service.py`
- Modify if needed: `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- Modify carefully if needed: `backend/src/fin_ops_platform/services/turnover_ledger_service.py`
- Modify carefully if needed: `backend/src/fin_ops_platform/services/workbench_matching_rules.py`
- Modify if needed: `backend/src/fin_ops_platform/app/server.py`
- Modify if needed: search/index service files discovered by `rg`
- Modify tests listed below only for narrow regressions.

- [ ] **Step 1: Audit label-copy sites**

Use `rg` to inspect hard-coded or copied display labels, including search/global index paths:

```bash
rg -n "工资|手续费|内部往来款|category_label|auto_category_label|batch_type|tag_codes|search|index" backend/src/fin_ops_platform/services backend/src/fin_ops_platform/app/server.py tests
```

Classify each site:

- durable fact stores stable code: keep
- display payload resolves current label: update if needed
- default seed/test text only: keep
- search/global index stores only stable codes or is fully invalidated/rebuilt from current labels; if no label-bearing search index exists, document that conclusion in the test or implementation note.

- [ ] **Step 2: Write narrow rename propagation tests**

Add focused tests proving `salary -> 人员薪酬` displays the new label in:

- bank detail row payload/effective category
- pending invoice tag dictionaries/rule display
- no-OA batch payload if it exposes a tag label
- turnover/workbench payload if it exposes a tag label
- search/global index payload if it exposes bank tag labels, or a focused assertion that search stores only stable codes/no bank tag labels and is covered by `search_cache` invalidation

Do not rewrite unrelated dirty tests.

- [ ] **Step 3: Implement only missing current-label lookups**

Use the existing category service tag dictionary lookup where possible. Do not do full-database string replacement and do not mutate submitted historical records merely to change a display label.

- [ ] **Step 4: Run downstream tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_no_oa_bank_batch_service tests.test_turnover_workbench_integration tests.test_workbench_v2_api -v
```

Expected: pass or identify unrelated pre-existing failures separately.

## Task 5: Frontend API Types and Drawer Component

**Files:**
- Modify: `web/src/features/bankDetails/types.ts`
- Modify: `web/src/features/bankDetails/api.ts`
- Create: `web/src/features/bankDetails/AutoTagRulesDrawer.tsx`
- Create: `web/src/test/AutoTagRulesDrawer.test.tsx`

- [ ] **Step 1: Write failing frontend tests**

Add tests for:

- drawer paper has `width: { xs: "100%", sm: "60vw" }` or equivalent generated style assertion.
- active tab shows disabled `优先级 0 内部往来款`.
- active user tags show `优先级 1...`.
- archived tab shows `已停用` and no priority.
- new tag defaults to `all_text`.
- users can rename a tag and the save payload carries the same `code` with the new label.
- users can edit exact, contains, and excludes fields and the save payload contains all three arrays.
- moving a rule up/down immediately relabels priorities and the save payload order follows the UI.
- archiving moves an active rule to the archived list and removes it from active payload.
- re-enabling moves an archived rule to the end of active rules.
- empty exact+contains blocks save.
- save sends `expected_version`, full `active_rules`, full `archived_rules`, and no `system_rule`.
- conflict/reference/backend validation errors are displayed without losing local edits.
- read-only permissions disable add/save/reorder/archive controls.

- [ ] **Step 2: Run failing frontend tests**

Run:

```bash
cd web && npm test -- --run AutoTagRulesDrawer.test.tsx
```

Expected before implementation: fail because UI and API helpers do not exist.

- [ ] **Step 3: Add API types and helpers**

Add domain types:

- `BankAutoTagFieldOption`
- `BankAutoTagRuleConditions`
- `BankAutoTagEditableRule`
- `BankAutoTagSystemRule`
- `BankAutoTagRulesResponse`
- `SaveBankAutoTagRulesRequest`

Add helpers:

- `fetchBankAutoTagRules({ signal })`
- `saveBankAutoTagRules(payload)`

Map backend error codes to Chinese messages:

- `permission_denied`
- `bank_transaction_tags_version_conflict`
- `invalid_bank_auto_tag_rules_request`
- `invalid_auto_tag_rule`
- `unknown_bank_transaction_tag`
- `archived_bank_transaction_tag`
- `bank_transaction_tag_in_use_by_pending_invoice_filter`

- [ ] **Step 4: Implement drawer**

Use MUI components and existing drawer styling conventions:

- `Drawer anchor="right"` with internal scroll.
- `PaperProps.sx = { width: { xs: "100%", sm: "60vw" }, maxWidth: "100vw" }`.
- Top header with title, version/read-model subtitle, segmented `ToggleButtonGroup` for `可用`/`停用`, close icon.
- Fixed action row with `新增标签` and `保存`.
- Active list:
  - fixed disabled `内部往来款` row first
  - editable rows with label `TextField`, match-field multi-select, exact/contains/excludes multi-line inputs, up/down icon buttons, archive button
- Archived list:
  - `已停用` chip
  - rule summary
  - re-enable button
- Dirty-close confirmation using `window.confirm`.
- Local validation matching backend positive-condition and match-field requirements.

- [ ] **Step 5: Run drawer/page tests**

Run:

```bash
cd web && npm test -- --run AutoTagRulesDrawer.test.tsx
```

Expected: pass.

## Task 6: Bank Details Page Integration and Sync

**Files:**
- Modify: `web/src/pages/BankDetailsPage.tsx`
- Modify: `web/src/test/BankDetailsPage.test.tsx`
- Modify if needed: `web/src/test/apiMock.ts`

- [ ] **Step 1: Write failing page integration tests**

Add tests proving:

- button `自动标签规则` appears in the existing top-right actions area.
- clicking it calls `GET /api/bank-details/auto-tag-rules` and opens a right Drawer named `自动标签规则`.
- saving through the drawer causes `PUT /api/bank-details/auto-tag-rules`, dispatches `finops:bank-transaction-tags-updated`, refreshes transactions/accounts, and shows the “规则已保存，银行明细正在刷新。” feedback.
- existing export/search/pagination tests still pass.

- [ ] **Step 2: Run failing page tests**

Run:

```bash
cd web && npm test -- --run BankDetailsPage.test.tsx
```

Expected before implementation: fail because page entry is not wired.

- [ ] **Step 3: Integrate button and drawer state**

Place the `自动标签规则` button in the existing top-right actions area without changing search/export/pagination behavior. Use an icon if the local icon set has a suitable rule/settings icon.

- [ ] **Step 4: Implement save success refresh**

On successful drawer save:

- persist returned version using the existing tag-version helper
- dispatch `finops:bank-transaction-tags-updated`
- send `BroadcastChannel` message when available
- increment `refreshToken`
- show a concise message such as `规则已保存，银行明细正在刷新。`

- [ ] **Step 5: Run page regression tests**

Run:

```bash
cd web && npm test -- --run BankDetailsPage.test.tsx PendingInvoicesPage.test.tsx
```

Expected: pass.

## Task 7: Documentation

**Files:**
- Modify: `docs/product-specs/bank-details.md`
- Modify: `docs/product-specs/pending-invoices.md`
- Modify: `docs/dev/api-contracts.md`

- [ ] **Step 1: Update product specs**

Document:

- rule drawer entry
- active/archived behavior
- priority ordering
- `内部往来款` fixed row
- semantic fields
- label rename semantics
- archived/reference guard
- background refresh lifecycle

- [ ] **Step 2: Update API contracts**

Add exact GET/PUT shapes, error codes, and lifecycle notes for `/api/bank-details/auto-tag-rules`.

- [ ] **Step 3: Verify docs do not conflict with implementation**

Run:

```bash
rg -n "不提供.*标签|只能由 app 自动分配|auto-tag-rules|自动标签规则" docs/product-specs/bank-details.md docs/product-specs/pending-invoices.md docs/dev/api-contracts.md
```

Expected: old conflicting language removed; new contract present.

## Final Verification

- [ ] **Backend focused suite**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_bank_transaction_category_service \
  tests.test_bank_transaction_auto_category_service \
  tests.test_bank_auto_tag_rules_api \
  tests.test_app_settings_service \
  tests.test_pending_invoice_service \
  tests.test_no_oa_bank_batch_service \
  tests.test_turnover_workbench_integration \
  tests.test_workbench_v2_api \
  -v
```

- [ ] **Frontend focused suite**

Run:

```bash
cd web && npm test -- --run AutoTagRulesDrawer.test.tsx BankDetailsPage.test.tsx PendingInvoicesPage.test.tsx
cd web && npm run build
```

- [ ] **Broader verification if focused tests reveal cross-cutting impact**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test -- --run
```

## Acceptance Checklist

- [ ] 银行明细页右上角有 `自动标签规则` 按钮。
- [ ] 右侧抽屉桌面 60%、小屏 100%，内部滚动。
- [ ] `内部往来款` 固定第一行，`优先级 0`，灰色不可交互，不展示规则解释。
- [ ] 可用标签显示 `优先级 1...`，可新增、改名、改规则、排序、停用。
- [ ] 停用区显示已停用标签，可重新启用到可用区末尾。
- [ ] 后端生成新标签 code，用户不能编辑 code。
- [ ] 规则使用统一语义字段，不暴露银行原始列名。
- [ ] 匹配逻辑为 `(exact OR contains) AND NOT excludes`。
- [ ] active 规则必须至少有一个正向条件和至少一个匹配字段。
- [ ] archived 标签不参与命中。
- [ ] 被待找发票等下游配置引用的标签不能停用，错误返回引用位置。
- [ ] 改名后当前页面、待找发票、免 OA、往来款、关联台和未来导出都解析新名称。
- [ ] 保存有权限、审计、版本冲突处理。
- [ ] 保存只触发生命周期 dirty/refresh，不同步全量重算历史流水。
- [ ] 相关产品/API 文档已更新。
- [ ] 相关后端、前端测试和构建已运行；未运行项有明确原因。

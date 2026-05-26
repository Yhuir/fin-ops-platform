# 2026-05-26 银行明细自动标签规则管理生产级执行 Prompt

/goal Implement production-grade user-managed automatic bank detail tag rules on `main`, without creating a worktree or branch. Add a 60% right-side drawer on the 银行明细 page for managing automatic labels, matching rules, priority order, and archived labels. Preserve `内部往来款` as a fixed system-first rule. Use a single tag dictionary source of truth, stable `tag_code` references across downstream modules, unified bank text semantic fields, audited/versioned saves, background read-model refresh, and full backend/frontend verification. This is not a rescue patch or temporary UI-only solution.

## Must Read First

Read these before editing:

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/product-specs/bank-details.md`
- `docs/product-specs/pending-invoices.md`
- `docs/product-specs/no-oa-bank-batches.md`
- `docs/product-specs/turnover-management.md`
- `docs/dev/api-contracts.md`
- `docs/dev/backend.md`
- `docs/dev/frontend.md`
- `docs/superpowers/specs/2026-05-26-bank-auto-tag-rules-design.md`
- `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
- `backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py`
- `backend/src/fin_ops_platform/services/bank_details_service.py`
- `backend/src/fin_ops_platform/services/app_settings_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `web/src/pages/BankDetailsPage.tsx`
- `web/src/features/bankDetails/api.ts`
- `web/src/features/bankDetails/types.ts`
- `web/src/features/pendingInvoices/api.ts`
- `web/src/features/pendingInvoices/types.ts`
- Existing tests around bank details, settings, pending invoices, no-OA batches, turnover ledger, and workbench tag labels.

## Non-Negotiable Requirements

1. Work on `main`; do not create a branch or worktree.
2. Preserve unrelated dirty worktree changes. Do not revert or overwrite files outside this task.
3. Implement the production design, not a temporary UI-only configuration.
4. Do not restore per-row manual bank transaction classification.
5. Do not allow users to edit the `内部往来款` rule.
6. Do not store bank-specific raw column names in user rules.
7. Do not do synchronous full-history recategorization inside the save request.
8. Do not make downstream modules copy label names as durable facts. They must reference stable `tag_code`.
9. Do not physically delete tags in this release.
10. Do not use broad fallback code that hides invalid contracts. Validate and fail clearly.

## Product Requirements

### Managed Scope

- The drawer manages labels that participate in automatic bank detail tagging.
- Include current automatic text labels by default: 手续费, 工资, 过节费, 奖金, 税款, 代理国库税收收缴, 社保款.
- Include user-created automatic labels.
- Show `内部往来款` as the fixed first system row, but do not store it as an editable text rule.
- Do not force unrelated legacy/manual taxonomy definitions in `bank_transaction_tags` to become editable auto rules. Keep them backward-compatible and out of this drawer unless they have an explicit auto rule marker or `rules` payload.
- Migrate the existing hard-coded `_TEXT_RULES` behavior into the single rules model or an equivalent compatibility layer that reads/writes the same model. Do not keep two divergent sources of automatic text rules.

### Bank Details Page Entry

- Add a top-right `自动标签规则` button on the 银行明细 page.
- Clicking it opens a right-side drawer similar to the 进项发票使用情况 drawer.
- Desktop drawer width is `60vw`; mobile/small viewport width is `100vw`; max width is the viewport.
- Drawer content scrolls internally and does not force page horizontal overflow.

### Drawer Structure

- Title: `自动标签规则`.
- Subtitle includes current rule version and refresh/save state when available.
- Top-left segmented control: `可用` / `停用`.
- Default tab is `可用`.
- Close button in the top-right.
- Provide `新增标签` and `保存` actions.
- If there are unsaved changes, closing asks for confirmation.

### Active Tab

- First row is always `内部往来款`.
- Display `优先级 0`.
- Gray disabled presentation.
- Show `系统内置`.
- Do not show rule explanation.
- It is not draggable, editable, archivable, or renameable.
- Other active tags display `优先级 1`, `优先级 2`, etc.
- Active tags can be renamed, have rules edited, be reordered, and be archived.
- Reordering updates priority labels immediately in the local UI and persists only on save.
- New tags append to the end of the active list.

### Archived Tab

- Shows archived labels only.
- Archived tags do not participate in matching.
- Display `已停用`, not priority.
- Show label and rule summary.
- Allow re-enable.
- Re-enabled tags return to the end of the active list.

### Tag Identity and Rename Semantics

- Users do not enter `code`.
- Backend generates code for new custom tags.
- `code` is stable and immutable.
- Label is editable.
- Downstream facts and rules store `tag_code`, not copied label text.
- All system pages and future exports resolve current labels from the dictionary. If `工资` is renamed to `人员薪酬`, bank details, pending invoices, no-OA batches, turnover ledger, workbench, and future exports display `人员薪酬`.
- Do not update already downloaded files.
- Do not implement full-database string replacement.

Field naming compatibility:

- In this prompt, `tag_code` means the stable dictionary `code`.
- Do not create a parallel field solely because the prompt says `tag_code`.
- Existing bank detail DTO/read-model fields continue to use `category_code`, `auto_category_code`, and `effective_category_code` unless a specific implementation need requires an additive field.
- Pending invoice rules continue to use `tag_codes`.
- Existing downstream fields such as `batch_type`, `rule_code`, or `category_code` should be reused when they already carry the stable dictionary code.

### Matching Fields

Rules use stable semantic fields:

- `counterparty_name`: 对方户名
- `purpose_text`: 用途/交易用途
- `summary_text`: 摘要
- `note_text`: 备注/附言/客户附言
- `detail_text`: 其他明细
- `all_text`: 全部文本

Backend maps each bank's raw fields into these semantic fields. Users must not configure bank-specific raw fields such as 工行用途 or 民生客户附言.

### Rule Logic

Each editable tag has:

- `match_fields`
- `exact`
- `contains`
- `excludes`

Logic:

```text
(any exact match OR any contains match) AND no excludes match
```

Matching semantics:

- `exact` means the full normalized text of any selected semantic field equals any exact token.
- `contains` means any selected semantic field contains any contains token.
- `excludes` means any selected semantic field contains any excludes token, which rejects the tag.
- Normalization at least converts to string and trims surrounding whitespace. Do not add regex, pinyin, or fuzzy segmentation in this release.

Validation:

- `exact`, `contains`, and `excludes` can be empty arrays.
- `exact` and `contains` cannot both be empty for active editable tags.
- `excludes` cannot be the only condition.
- `match_fields` cannot be empty. New tags default to `all_text`.
- Archived tags may retain incomplete historical rules; re-enable must validate them as active editable tags before save succeeds.
- Trim values, remove empty lines, and dedupe.
- `match_fields` must be from the semantic field whitelist.
- No regex, no complex AND/OR builder, no user-entered code in this release.

Default migrated rules must preserve current behavior:

- `fee`: contains 手续费 or 短信服务费, only over 对方户名/摘要/备注语义字段. Do not match ordinary 服务费, and do not match 手续费 only from 用途 or detail fields unless the user later edits the rule.
- `holiday_bonus`: contains 过节费 over 摘要/用途/备注/其他明细.
- `salary`: contains 工资 over 摘要/用途/备注/其他明细.
- `bonus`: contains 奖金, 绩效奖, 年终奖 over 摘要/用途/备注/其他明细.
- `treasury_tax_collection`: contains 代理国库税收收缴 or 国库税收收缴 over 摘要/用途/备注/其他明细.
- `social_security`: contains 社保款, 社保费, 社会保险费, 缴纳社保 over 摘要/用途/备注/其他明细.
- `tax_payment`: contains 税款, 缴纳税款, 电子缴税, 税库银, 税务局, 完税 over 摘要/用途/备注/其他明细, excluding 社保及税款, 社保和税款, 社保税款, 社保、税款.

### Priority

- `内部往来款` is system priority 0.
- Active editable tags run in list order, first match wins.
- Backend persists a stable priority sequence and normalizes it on save.
- Archived tags do not participate.

### Archiving

- Tags are archived, not deleted.
- Allow archiving tags that only matched historical rows.
- After archiving, background refresh recalculates history; rows may become another tag or `-`.
- Refuse archiving if the tag is referenced by downstream configuration such as pending invoice tag groups.
- Error response must include reference locations, for example `待找发票规则：无需开票`.

## API Contract

Add:

```text
GET /api/bank-details/auto-tag-rules
PUT /api/bank-details/auto-tag-rules
```

### GET

Return:

- `version`
- fixed system row for `内部往来款`
- active editable tags
- archived tags
- semantic field metadata
- permissions such as `can_save`
- `read_model_status` for affected downstream refresh state when available from existing lifecycle helpers; otherwise omit it rather than inventing state

HTTP status: `200 OK`.

Canonical response shape:

```json
{
  "version": 12,
  "system_rule": {
    "code": "internal_transfer",
    "label": "内部往来款",
    "priority_label": "优先级 0",
    "source": "system",
    "status": "active",
    "editable": false,
    "archivable": false,
    "sortable": false
  },
  "active_rules": [
    {
      "code": "salary",
      "label": "人员薪酬",
      "status": "active",
      "source": "system",
      "priority": 10,
      "priority_label": "优先级 1",
      "rules": {
        "match_fields": ["summary_text", "purpose_text", "note_text", "detail_text"],
        "exact": [],
        "contains": ["工资", "薪酬"],
        "excludes": ["社保代扣"]
      },
      "rule_summary": "摘要/用途/备注/其他明细包含：工资、薪酬；排除：社保代扣",
      "editable": true,
      "archivable": true,
      "sortable": true
    }
  ],
  "archived_rules": [],
  "field_options": [
    { "value": "counterparty_name", "label": "对方户名" },
    { "value": "purpose_text", "label": "用途/交易用途" },
    { "value": "summary_text", "label": "摘要" },
    { "value": "note_text", "label": "备注/附言/客户附言" },
    { "value": "detail_text", "label": "其他明细" },
    { "value": "all_text", "label": "全部文本" }
  ],
  "permissions": { "can_save": true },
  "read_model_status": "fresh"
}
```

### PUT

Input:

- `expected_version`
- full active editable tag list in desired order
- archived tag list
- labels, statuses, priorities, and rules
- new tags without `code`

HTTP statuses:

- `200 OK`: saved; response uses the same normalized shape as GET.
- `403 Forbidden`: permission denied.
- `409 Conflict`: `expected_version` is stale.
- `400 Bad Request`: invalid JSON shape, invalid field, invalid rule, duplicate label, or illegal system-rule mutation.

Canonical request shape:

```json
{
  "expected_version": 12,
  "active_rules": [
    {
      "code": "salary",
      "label": "人员薪酬",
      "rules": {
        "match_fields": ["summary_text", "purpose_text", "note_text", "detail_text"],
        "exact": [],
        "contains": ["工资", "薪酬"],
        "excludes": ["社保代扣"]
      }
    },
    {
      "label": "银行手续费",
      "rules": {
        "match_fields": ["counterparty_name", "summary_text", "note_text"],
        "exact": [],
        "contains": ["手续费"],
        "excludes": []
      }
    }
  ],
  "archived_rules": [
    {
      "code": "old_bonus",
      "label": "旧奖金",
      "rules": {
        "match_fields": ["all_text"],
        "exact": [],
        "contains": [],
        "excludes": []
      }
    }
  ]
}
```

PUT must not accept `system_rule`. If the payload tries to submit, mutate, archive, sort, or rename `internal_transfer`, return `400 invalid_bank_auto_tag_rules_request`.

Canonical error shape:

```json
{
  "error": "invalid_auto_tag_rule",
  "message": "自动标签规则校验失败。",
  "field_errors": [
    {
      "path": "active_rules[1].rules.contains",
      "message": "精确命中字样和包含字样不能同时为空。"
    }
  ],
  "references": []
}
```

Referenced-tag error shape:

```json
{
  "error": "bank_transaction_tag_in_use_by_pending_invoice_filter",
  "message": "该银行明细标签仍被下游规则引用，请先解除引用后再停用。",
  "field_errors": [],
  "references": [
    {
      "domain": "pending_invoice_tag_groups",
      "label": "待找发票规则：无需开票",
      "tag_code": "salary"
    }
  ]
}
```

Backend:

- validates permission
- validates optimistic version
- generates missing custom codes
- rejects code mutation
- rejects duplicate labels within the same status
- rejects editable payload mutation of `内部往来款`
- validates rule fields and positive conditions
- checks downstream references before archiving
- normalizes priority
- increments version
- writes audit
- configures the auto-category service immediately
- returns normalized updated rules
- triggers downstream dirty scopes/background refresh

After a successful PUT, execute one derived lifecycle path:

- Add or reuse a lifecycle event named `bank_auto_tag_rules_changed`.
- Call it with `scope_keys=["all"]`, `include_all=true`, and `reason="bank_auto_tag_rules_changed"`.
- It must cover at least these domains: `bank_detail_read_model`, `workbench_read_model`, `workbench_candidate_matches`, `workbench_matching_dirty_scopes`, `pending_invoice_read_model`, `cost_statistics_read_model`, and `search_cache`.
- Bank detail must enqueue `scope_type="bank_detail"`, `scope_key="all"`; the existing bank detail refresh fan-out handles month shards.
- Pending invoice must call the existing `_invalidate_pending_invoice_read_model_scopes(reason="bank_auto_tag_rules_changed")` or equivalent and cover `expense:all`, `expense:requires_invoice`, `expense:bank_statement_as_invoice`, `expense:no_invoice_required`, and `income:all`.
- Workbench read model and matching dirty scopes must be invalidated/enqueued, not rebuilt synchronously in the PUT request.
- Cost statistics and search must use existing lifecycle executors.
- No-OA batches and turnover ledger currently consume bank tag results through services/read models; if implementation discovers a persistent cache/read model for either, invalidate it in the same lifecycle path. Do not add a second source of truth.

PUT tests must prove the save path does not synchronously scan all bank rows, rebuild workbench `all`, or regenerate historical no-OA/turnover results inline.

Error codes to support or map:

- `permission_denied`
- `bank_transaction_tags_version_conflict`
- `invalid_bank_auto_tag_rules_request`
- `invalid_auto_tag_rule`
- `unknown_bank_transaction_tag`
- `archived_bank_transaction_tag`
- `bank_transaction_tag_in_use_by_pending_invoice_filter`

## Backend Implementation Tasks

### Task A: Domain Model and Validation

Own files:

- `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
- `backend/src/fin_ops_platform/services/bank_transaction_auto_category_service.py`
- focused tests under `tests/`

Implement:

- normalized rule payload on tag definitions
- stable semantic field whitelist
- code generation for new custom tags
- immutable code validation
- active/archived split
- priority normalization
- rule validation
- matching over semantic fields
- evidence capture for matched semantic/raw fields where existing row data allows
- fixed `内部往来款` precedence outside editable text rules

Use `auto_category_evidence` for evidence when exposing or storing it:

```json
{
  "tag_code": "salary",
  "tag_label": "人员薪酬",
  "rule_code": "salary",
  "rule_version": 12,
  "condition_type": "contains",
  "semantic_field": "note_text",
  "semantic_field_label": "备注/附言/客户附言",
  "raw_field_key": "customer_note",
  "raw_field_label": "客户附言",
  "matched_text": "工资"
}
```

`raw_field_key` and `raw_field_label` may be null if import data cannot provide them. `semantic_field`, `condition_type`, and `matched_text` must be present for matched text rules.

Test:

- normalization and validation
- exact/contains/excludes logic
- priority first-match behavior
- archived tags ignored
- bank-specific raw text mapped to semantic fields
- internal transfer cannot be edited through text rules

### Task B: Settings/API/Dirty Lifecycle

Own files:

- `backend/src/fin_ops_platform/services/app_settings_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- related lifecycle helpers
- focused API tests

Implement:

- `GET /api/bank-details/auto-tag-rules`
- `PUT /api/bank-details/auto-tag-rules`
- permission checks using existing OA/access-control session patterns
- optimistic `expected_version`
- audit event for rule changes
- reference check before archiving
- reuse/extend existing tag dictionary persistence instead of a parallel store
- implement the `bank_auto_tag_rules_changed` lifecycle path described in the API Contract section, including bank detail, pending invoice, workbench read model, workbench matching dirty scopes, cost statistics, and search invalidation
- inspect no-OA batch and turnover ledger persistence; if either has a persistent cache/read model derived from bank tags, invalidate that cache/read model in the same lifecycle path, otherwise document that they read current tag labels through existing services
- return normalized payload and actionable errors

Test:

- successful save increments version
- conflict rejects stale version
- cannot archive referenced tag
- archiving historical-only tag succeeds
- dirty scopes/invalidation hooks are called
- audit is recorded
- no synchronous full scan in save path

### Task C: Downstream Label Resolution

Own files:

- backend services and frontend mappers that currently hard-code labels for `salary`, `fee`, `internal_transfer`, etc.
- tests for no-OA batch, pending invoice, turnover ledger, workbench display

Implement:

- display current label by the stable dictionary code in every downstream path that renders an automatic bank tag
- keep `内部往来款` label stable as system row
- do not copy label text into downstream durable configuration
- preserve existing behavior while allowing rename propagation

Test:

- renaming `salary` to `人员薪酬` propagates to bank details payload, pending invoice rules/list, no-OA batch payload, turnover/workbench display paths that consume bank tags
- downstream configs still store tag codes

### Task D: Frontend API Types and Drawer Component

Own files:

- `web/src/features/bankDetails/api.ts`
- `web/src/features/bankDetails/types.ts`
- new drawer component under `web/src/components/` or `web/src/features/bankDetails/`
- relevant frontend tests

Implement:

- fetch/save API helpers
- type-safe payload mapping
- error message mapping
- drawer layout, active/archived toggle, validation, dirty close confirm
- internal transfer disabled row
- active priority labels
- rule editors for exact/contains/excludes and match fields
- archive/re-enable flows
- readonly permission state

Test:

- opens drawer
- 60% desktop drawer width behavior via style assertion where practical
- active/archived switching
- internal transfer fixed disabled row
- priority labels
- validation blocks empty positive conditions
- save payload includes expected version and full config
- conflict/reference errors displayed

### Task E: Bank Details Page Integration and Refresh Sync

Own files:

- `web/src/pages/BankDetailsPage.tsx`
- bank details tests
- shared domain event code only if needed

Implement:

- top-right `自动标签规则` button
- opens drawer
- after save, refresh local tag version and bank details rows/accounts
- broadcast or reuse `finops:bank-transaction-tags-updated`
- show refresh message using existing read model status patterns
- keep export/search/pagination behavior intact

Test:

- button appears in correct page area
- save triggers reload/version sync
- no regressions to export/search/pagination tests

### Task F: Documentation and Integration

Own files:

- `docs/product-specs/bank-details.md`
- `docs/product-specs/pending-invoices.md`
- `docs/dev/api-contracts.md`
- any narrow dev docs required by new API

Implement:

- update old “app-only automatic tags, no management UI” product text
- document rule drawer, semantic fields, priority, archiving, refresh lifecycle
- document pending invoice `tag_code` reference semantics
- document `/api/bank-details/auto-tag-rules`

## Suggested Parallelization

Run these in parallel only after the contract is stable:

- A and B can start together if B treats A's service API as a small explicit contract.
- D can start with mocked API payloads after GET/PUT shapes are fixed.
- F can run in parallel after product/API contract is accepted.
- C should start after A defines label dictionary access helpers, but can inspect hard-coded label paths in parallel.

Must be serial:

1. Finalize payload/API contract.
2. Integrate A+B backend.
3. Integrate D+E frontend against real API.
4. Apply C downstream label propagation after backend helpers exist.
5. Run F docs update.
6. Final verification and cleanup.

Do not let multiple workers edit the same large file blindly. If using parallel workers, assign disjoint ownership and integrate `server.py`, shared API mappers, and shared tests serially.

## Verification

Run focused tests first, then broader checks:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_category_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_workbench_integration -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v
cd web && npm test -- BankDetailsPage
cd web && npm test -- SettingsPage
cd web && npm test -- PendingInvoicesPage
cd web && npm run build
```

Also run any new focused tests added for:

- auto tag rule normalization
- rule matching
- API save/conflict/reference checks
- drawer UI
- downstream rename propagation

If time allows, run:

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test
```

## Acceptance Criteria

- 银行明细页面 has a top-right `自动标签规则` button.
- Drawer opens from the right and occupies 60% desktop width.
- Active/archived toggle exists in the drawer.
- `内部往来款` appears as first active row, `优先级 0`, gray disabled, no rule explanation.
- Editable active labels show `优先级 1...`.
- Users can add, rename, edit rules, reorder, archive, and re-enable labels.
- New label codes are backend-generated and immutable.
- Rules use semantic fields, not bank-specific raw columns.
- Rule validation enforces at least one positive condition.
- Matching uses `(exact OR contains) AND NOT excludes`.
- Rule priority controls first-match result.
- Archived labels do not match.
- Referenced tags cannot be archived and return reference locations.
- Renaming a tag updates display across bank details, pending invoices, no-OA batches, turnover ledger, workbench, and future exports by resolving current label from `tag_code`.
- Saving rules is audited, versioned, permission-checked, and conflict-safe.
- Saving rules marks affected read models dirty and does not synchronously full-scan/recalculate all historical rows in the request.
- Product/API docs are updated.
- Relevant backend/frontend tests and build pass, or any unrun checks are reported with exact reasons.

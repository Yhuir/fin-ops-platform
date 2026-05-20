# 银行明细标签管理统一入口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将设置页现有银行标签入口正式收敛为 `银行明细标签管理`，并让 `待找发票筛选` 只引用该统一标签字典，不再创建标签。

**Architecture:** 保持后端和持久化字段 `bank_transaction_tags` / `pending_invoice_tag_groups` 不迁移，前端产品文案统一为“银行明细标签”。设置页分离两个职责：标签字典管理与待找发票筛选映射。同步继续使用后端版本、窗口事件、BroadcastChannel 和页面聚焦兜底。

**Tech Stack:** Python unittest backend, React + TypeScript frontend, MUI native components, Vitest frontend tests.

---

## Files and Responsibilities

- `web/src/components/settings/SettingsPageContent.tsx`
  - 设置分类文案、标签管理 section 挂载、待找发票筛选 props。
- `web/src/components/settings/SettingsTreeNav.tsx`
  - 设置 section id 对应 region id；保持底层 id 不变。
- `web/src/components/settings/SettingsBankTransactionTagsSection.tsx`
  - UI 标题和文案升级为 `银行明细标签管理`；确保路径可编辑、自定义标签可改名、系统标签不可改名。
- `web/src/components/settings/SettingsPendingInvoiceTagsSection.tsx`
  - 移除新建标签输入和“新建并加入”；只保留选择现有启用标签；空状态指向银行明细标签管理。
- `web/src/components/settings/types.ts`
  - 删除待找发票筛选快速新建标签 props；保留底层 `bank_transaction_tags` 类型。
- `web/src/pages/SettingsPage.tsx`
  - 标签保存成功后的事件广播、设置页刷新/冲突保护、错误展示中文化。
- `web/src/features/workbench/api.ts`
  - 设置保存 payload 继续发送 `bank_transaction_tags.definitions`；错误映射按结构化 code 转中文。
- `web/src/pages/BankDetailsPage.tsx`
  - 验证标签版本更新后刷新行为仍基于后端字典。
- `web/src/pages/PendingInvoicesPage.tsx`
  - 验证待找发票页标签更新后刷新行为仍基于后端字典。
- `backend/src/fin_ops_platform/services/app_settings_service.py`
  - 保持未知、停用、重复映射校验；保护仍被待找发票筛选引用的标签不能停用；如需要，补充错误 code 测试。
- `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
  - 保持 `definitions` 正式字段和 `tags` 兼容 alias。
- Tests:
  - `web/src/test/SettingsPage.test.tsx`
  - `web/src/test/BankDetailsPage.test.tsx`
  - `web/src/test/PendingInvoicesPage.test.tsx`
  - `tests/test_app_settings_service.py`
  - `tests/test_bank_transaction_category_service.py`

## Task 1: 设置页标签管理入口与待找发票筛选 UI 边界

**Owner:** Frontend settings worker.

**Files:**
- Modify: `web/src/components/settings/SettingsPageContent.tsx`
- Modify: `web/src/components/settings/SettingsBankTransactionTagsSection.tsx`
- Modify: `web/src/components/settings/SettingsPendingInvoiceTagsSection.tsx`
- Modify: `web/src/components/settings/types.ts`
- Test: `web/src/test/SettingsPage.test.tsx`

- [ ] **Step 1: Write failing tests for product copy and creation boundary**

Add or update tests asserting:

```ts
expect(within(tree).getByRole("treeitem", { name: /银行明细标签管理/ })).toBeInTheDocument();
expect(within(tree).queryByRole("treeitem", { name: /银行流水标签/ })).not.toBeInTheDocument();
await user.click(within(tree).getByRole("treeitem", { name: /待找发票筛选/ }));
expect(within(region).queryByRole("textbox", { name: "新标签" })).not.toBeInTheDocument();
expect(within(region).queryByRole("button", { name: /新建并加入/ })).not.toBeInTheDocument();
expect(within(region).getByText(/请先在银行明细标签管理中新增标签/)).toBeInTheDocument();
```

- [ ] **Step 2: Run failing frontend test**

Run: `cd web && npm test -- --run SettingsPage.test.tsx`

Expected before implementation: fail on old labels or quick-create controls.

- [ ] **Step 3: Update UI components**

Implement:

- Rename settings nav label from `银行流水标签` to `银行明细标签管理`.
- Rename description to `全 app 银行明细标签字典`.
- Rename section heading to `银行明细标签管理`.
- Remove `newTagLabel` state, `TextField label="新标签"`, and `新建并加入` button from `SettingsPendingInvoiceTagsSection`.
- Remove `onCreateAndAddTag` from props and callers.
- Update empty state copy to point to `银行明细标签管理`.

- [ ] **Step 4: Run settings tests**

Run: `cd web && npm test -- --run SettingsPage.test.tsx`

Expected: pass.

## Task 2: 保存契约、错误文案和后端校验回归

**Owner:** Settings API/backend worker.

**Files:**
- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/pages/SettingsPage.tsx`
- Modify: `tests/test_app_settings_service.py`
- Modify if needed: `backend/src/fin_ops_platform/services/app_settings_service.py`
- Modify if needed: `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
- Test: `tests/test_app_settings_service.py`
- Test: `web/src/test/SettingsPage.test.tsx`

- [ ] **Step 1: Write tests for no quick-create payload and Chinese error mapping**

Backend:

- Keep test proving `tags` alias is accepted before mapping validation.
- Keep tests proving unknown, archived and duplicate mapping fail.
- Add a test proving a tag already referenced by `pending_invoice_tag_groups` cannot be archived in the same save unless the mapping is removed.

Frontend:

- Assert settings save sends `bank_transaction_tags.definitions`, not `tags`.
- Add or update tests so `unknown_bank_transaction_tag`, `archived_bank_transaction_tag`, `duplicate_pending_invoice_tag_mapping`, and stale version/conflict errors surface Chinese actionable messages.

- [ ] **Step 2: Run targeted tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service -v
cd web && npm test -- --run SettingsPage.test.tsx
```

Expected before implementation: frontend error mapping or payload test may fail.

- [ ] **Step 3: Implement minimal changes**

Implement:

- Keep `serializeBankTransactionTags()` emitting `definitions`.
- Preserve or add a setting-save version guard based on `bankTransactionTags.version`. A stale page must not silently overwrite a newer server version.
- Prevent archiving tags still referenced by pending invoice mappings; the save must fail with an actionable error rather than silently removing mappings.
- Add stable frontend mapping for:
  - `unknown_bank_transaction_tag` -> `待找发票筛选引用了不存在的银行明细标签，请刷新后重新选择。`
  - `archived_bank_transaction_tag` -> `该银行明细标签已停用，不能用于新的待找发票筛选。`
  - `duplicate_pending_invoice_tag_mapping` -> `同一个银行明细标签不能同时归入多个待找发票筛选。`
  - `category_version_conflict` or settings version conflict -> `银行明细标签已被其他页面更新，请刷新后重新保存。`
- Do not relax backend validation.

- [ ] **Step 4: Run backend/settings tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service tests.test_bank_transaction_category_service -v
cd web && npm test -- --run SettingsPage.test.tsx
```

Expected: pass.

## Task 3: 全 app 同步和页面级回归

**Owner:** Cross-page sync worker.

**Files:**
- Modify if needed: `web/src/pages/SettingsPage.tsx`
- Modify if needed: `web/src/pages/BankDetailsPage.tsx`
- Modify if needed: `web/src/pages/PendingInvoicesPage.tsx`
- Modify: `web/src/test/SettingsPage.test.tsx`
- Modify: `web/src/test/BankDetailsPage.test.tsx`
- Modify: `web/src/test/PendingInvoicesPage.test.tsx`
- Modify: `web/src/test/apiMock.ts`

- [ ] **Step 1: Audit current sync tests**

Confirm tests already cover:

- Bank details refetches after tag version update event/focus fallback.
- Pending invoices refetches after tag update event/focus fallback.
- Another open settings page reacts to tag update events. If it has unsaved edits, it must not silently overwrite; it should show a stale/conflict prompt and require refresh/discard before saving.

- [ ] **Step 2: Add missing regression if needed**

If no explicit pending invoice test exists for update event, add one that dispatches `finops:bank-transaction-tags-updated` and asserts rows/settings refetch.

If no explicit bank details test exists for the renamed setting, add only the minimal test needed. Do not refactor page sync.

If settings page does not have stale-save protection, add the smallest regression that simulates a tag version update event while local edits exist and verifies save is blocked until refresh/discard.

- [ ] **Step 3: Run targeted page tests**

Run:

```bash
cd web && npm test -- --run BankDetailsPage.test.tsx PendingInvoicesPage.test.tsx SettingsPage.test.tsx
```

Expected: pass.

## Final Verification

After all worker tasks are integrated:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service tests.test_bank_transaction_category_service -v
cd web && npm test -- --run SettingsPage.test.tsx BankDetailsPage.test.tsx PendingInvoicesPage.test.tsx
cd web && npm run build
```

If changes are broader than expected, run:

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test -- --run
```

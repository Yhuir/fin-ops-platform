# 往来款管理银行标签整合 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将银行明细自动识别出的往来款流水统一拉入往来款管理，在往来款管理按单条流水批量保存子标签，并同步影响银行明细、往来款分组和关联台刷新。

**Architecture:** 银行明细继续只做自动主标签入口，不开放人工编辑。往来款管理新增受控批量保存接口，复用 `BankTransactionCategoryService` 的版本、审计和标签事实源；保存后重建往来关系并触发银行明细、往来款台账和关联台派生刷新。前端以流水行为编辑单元，维护批量 dirty state，统一保存。

**Tech Stack:** Python backend services and custom HTTP server, React + TypeScript + MUI + Vite frontend, unittest and Vitest.

---

### Task 1: 文档和口径

**Files:**
- Modify: `docs/product-specs/turnover-management.md`
- Modify: `docs/product-specs/bank-details.md`

- [ ] **Step 1: 更新往来款管理文档**
  - 写清楚主标签来源、往来款管理唯一人工子标签入口、批量保存、原子性、审计、两层筛选、四项汇总、保存后重建关系和刷新关联台。

- [ ] **Step 2: 更新银行明细文档**
  - 写清楚银行明细不提供人工子标签编辑，只展示往来款管理保存后的结果。

### Task 2: 后端标签保存合同

**Files:**
- Modify: `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_bank_transaction_category_service.py`
- Test: `tests/test_turnover_ledger_api.py` or nearest existing server/API test

- [ ] **Step 1: 写失败测试**
  - 测试往来款叶子标签批量保存成功。
  - 测试非往来款叶子标签被拒绝。
  - 测试版本冲突和未知流水保持原子性。

- [ ] **Step 2: 实现受控批量保存**
  - 新增仅供往来款管理调用的保存路径；不恢复 `/api/bank-transaction-categories`。
  - 请求包含 `updates[{transaction_id, category_code, expected_version}]`。
  - 响应返回 `updated_categories`、`affected_months`、`turnover_ledger_invalidated`。

- [ ] **Step 3: 保存后刷新**
  - 复用现有权限、审计、持久化、`_invalidate_workbench_after_bank_transaction_categories` 和 `_clear_turnover_ledger_read_model_best_effort`。

### Task 3: 往来款台账聚合

**Files:**
- Modify: `backend/src/fin_ops_platform/services/turnover_ledger_service.py`
- Modify: `backend/src/fin_ops_platform/services/turnover_relation_service.py`
- Test: existing turnover ledger/relation tests under `tests/`

- [ ] **Step 1: 写失败测试**
  - 主标签 `external_turnover` 且无子标签的流水进入台账，状态为待分类。
  - 已保存子标签后进入正确 `borrow_in` / `borrow_out` 和 `family`。
  - `business` family 归入借出。
  - 四项汇总正确。

- [ ] **Step 2: 实现方向筛选**
  - API 支持 `direction=all|borrow_in|borrow_out`。
  - 借入下不返回业务往来；借出下返回业务往来。

- [ ] **Step 3: 统一借出语义**
  - 出款本金显示/汇总为待收款。
  - 收回流水显示/汇总为已收款。

### Task 4: 前端 API 和页面

**Files:**
- Modify: `web/src/features/turnoverLedger/types.ts`
- Modify: `web/src/features/turnoverLedger/api.ts`
- Modify: `web/src/pages/TurnoverLedgerPage.tsx`
- Modify: `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`
- Test: relevant tests under `web/src/test/`

- [ ] **Step 1: 写失败测试**
  - 页面只渲染四个汇总卡。
  - 两层筛选存在且方向影响小类。
  - 修改多行子标签后统一保存。
  - 只读权限下禁用编辑。

- [ ] **Step 2: 实现 API 映射**
  - `fetchTurnoverLedgerGrouped` 携带 `direction`。
  - 新增 `saveTurnoverBankRowTags`。

- [ ] **Step 3: 实现页面编辑流**
  - 表格流水行展示子标签下拉。
  - 页面维护 dirty state 和统一保存按钮。
  - 成功后发出 domain events 并刷新。

### Task 5: 银行明细展示联动

**Files:**
- Modify only if needed: `web/src/pages/BankDetailsPage.tsx`
- Modify only if needed: `web/src/features/bankDetails/api.ts`
- Test: `web/src/test/BankDetailsApi.test.ts` and nearest page test

- [ ] **Step 1: 验证现有展示合同**
  - 确认 `effective_category_*` 已能展示手工保存的往来款子标签。

- [ ] **Step 2: 补缺口**
  - 如果页面只展示自动标签，改为展示 effective 标签。
  - 保持银行明细无人工编辑入口。

### Task 6: 验证

- [ ] **Step 1: 运行后端相关测试**
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_transaction_category_service -v`
  - 运行新增/受影响往来款测试。

- [ ] **Step 2: 运行前端相关测试**
  - `cd web && npm test -- --run`

- [ ] **Step 3: 构建**
  - `cd web && npm run build`

- [ ] **Step 4: 如时间允许运行全量**
  - `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`

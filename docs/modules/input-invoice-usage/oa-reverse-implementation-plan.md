# 进项发票反提 OA 闭环实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 `进项发票使用情况` 页面 `以发票反提 OA` 的生产级闭环：管理员维护目标 OA 申请人凭据，操作人直接创建 OA 暂存草稿，用户手动提交 OA 后在 FinOps 确认 `已提交 OA` 或 `未提交 OA`，并提供 `待处理 | 已提交` 视图。

**Architecture:** 基于现有 `InputInvoiceUsageOaReverseService`、内部 batch、PostgreSQL repository、`AccessControlService`、`HttpEtcOAClient.create_form_draft(...)` 和设置页结构扩展。`server.py` 只新增路由、依赖组装和 HTTP 映射；业务逻辑进入 focused service/repository/token provider。凭据管理走独立 API，不进入普通 `/api/workbench/settings` payload。

**Tech Stack:** Python services + PostgreSQL migrations/repositories + custom HTTP server, React + TypeScript + Vite, Python `unittest`, Vitest/Testing Library.

---

## 0. 开始前约束

- 必须在 `main` 分支工作。
- 开始每个阶段前运行 `git status --short --branch`。当前仓库可能有 ETC 相关未提交改动；不要修改、格式化、回滚或提交无关文件。
- 每阶段开始前读取：
  - `AGENTS.md`
  - `docs/modules/input-invoice-usage/README.md`
  - `docs/modules/input-invoice-usage/oa-reverse-design.md`
  - `docs/modules/input-invoice-usage/state-machine.md`
  - `docs/modules/input-invoice-usage/tests.md`
  - `docs/modules/settings/README.md`
  - `docs/modules/settings/state-machine.md`
  - `docs/modules/settings/tests.md`
- 不允许：
  - 明文持久化密码。
  - 在 API 响应、日志、审计、前端状态或测试快照中暴露密码、密文、OA token、Authorization header。
  - 使用当前操作人的 OA token 创建目标 OA 申请人的草稿。
  - 自动提交 OA 或启动 OA 流程。
  - 删除 OA 系统里的暂存草稿。
  - 前端展示 `创建本地批次`。
  - 把业务逻辑塞进 `server.py`。

## 1. 现有代码事实

### 后端

- `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
  - 已有 `InputInvoiceUsageOaReverseService.preview(...)`。
  - 已有 `create_batch(...)`，使用 preview hash/idempotency 创建内部 batch。
  - 已有 `create_oa_draft(...)`，当前接收 `oa_client` 并调用 `client.create_form_draft(...)`。
  - 已有 `manual_oa_status(...)`，但当前 `submitted` 会进入 `oa_submission_detecting`，`not_submitted` 会保留 `oaDraftId`，需要按新需求调整。
  - `_candidate_rejection(...)` 已阻止已有 active OA 关系的发票反提。
  - `_build_oa_draft_payload(...)` 已构造 `isDraft=True` payload。
- `backend/src/fin_ops_platform/services/postgres_repositories/input_invoice_usage_oa_reverse.py`
  - 已有 `app.input_invoice_usage_oa_reverse_batches` repository。
- `backend/src/fin_ops_platform/app/server.py`
  - 已有 `/api/input-invoice-usage/oa-reverse/preview`。
  - 已有 `/api/input-invoice-usage/oa-reverse/batches`。
  - 已有 `/api/input-invoice-usage/oa-reverse/batches/{batchId}/oa-draft`。
  - `_input_invoice_usage_oa_draft_client(headers)` 当前从当前请求 header 取 OA token，这是必须替换的核心问题。
- `backend/src/fin_ops_platform/services/etc_service.py`
  - `HttpEtcOAClient.create_form_draft(...)` 已能 POST OA form draft 并提取 draft id/url。
- `backend/src/fin_ops_platform/services/access_control_service.py`
  - `YNSYLP005` 是默认 admin。
  - `access_tier=full_access/admin` 时 `can_mutate_data=True`。
  - `read_export_only` 时 `can_mutate_data=False`。

### OA 源码事实

- `/Users/yu/Desktop/sy/smart_oa/smart-oa-auth/src/main/java/com/jovefast/auth/controller/TokenController.java`
  - `POST /login` 返回 token。
- `/Users/yu/Desktop/sy/smart_oa/smart-oa-auth/src/main/java/com/jovefast/auth/service/SysLoginService.java`
  - 登录密码入参是 RSA 加密后的密文，后端通过 `RsaUtils.decryptByPrivateKey(pwd)` 解密。
- `/Users/yu/Desktop/sy/smart_oa/smart-oa-form/form-starter/src/main/java/com/sykj/form/controller/FormDataController.java`
  - `isDraft=true` 时保存暂存草稿，`process_status=0`，不会启动流程。

### 前端

- `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`
  - 当前 UI 暴露 `创建本地批次` 和 `创建 OA 草稿` 两步。
  - 当前有 `showCreateBatchAction` / `canCreateBatch`，需要收敛为一个用户动作 `创建 OA 草稿`。
  - 当前 `permissions` mapper 可能把后端缺失字段映射为 `false`，造成按钮误禁用。
- `web/src/features/inputInvoiceUsage/api.ts`
  - 已有 preview/create batch/create draft/manual status API client。
  - 需要新增“一步创建 OA 草稿”API client 和已提交历史 API client，或在保留旧函数内部组合新接口。
- `web/src/components/settings/SettingsPageContent.tsx`
  - 设置页已有 tree nav 和 `访问账户` admin-only 区域。
  - 凭据管理应新增独立 section，不进入普通 `saveWorkbenchSettings(...)`。
- `web/src/features/workbench/api.ts`
  - `/api/workbench/settings` 是普通设置整体 payload，不应用于保存密码。

## 2. API 目标 Contract

实现时路径可以微调，但推荐如下，避免复用普通 settings payload：

### 凭据管理

- `GET /api/workbench/settings/oa-applicant-credentials`
  - admin-only。
  - 响应：

```json
{
  "credentials": [
    {
      "targetApplicantCode": "chen_xiuyun",
      "targetApplicantName": "陈秀云",
      "oaUsername": "chen_xiuyun",
      "hasCredential": true,
      "enabled": true
    }
  ]
}
```

- `PUT /api/workbench/settings/oa-applicant-credentials/{targetApplicantCode}`
  - admin-only。
  - 请求允许：

```json
{
  "targetApplicantName": "陈秀云",
  "oaUsername": "chen_xiuyun",
  "password": "plain password from admin form",
  "enabled": true
}
```

  - 响应只返回非敏感字段，不能返回 password、ciphertext、token。

- `DELETE /api/workbench/settings/oa-applicant-credentials/{targetApplicantCode}`
  - admin-only。
  - 删除或禁用凭据；第一版可物理删除记录，若使用禁用则必须返回 `enabled=false`。

### 反提 OA

- `POST /api/input-invoice-usage/oa-reverse/drafts`
  - mutation 权限。
  - 单一用户动作：创建内部 batch 并立即用目标申请人 token 创建 OA 暂存草稿。
  - 请求：

```json
{
  "previewId": "oa_reverse_preview_xxx",
  "expectedPreviewHash": "...",
  "idempotencyKey": "...",
  "selectedInvoiceIds": ["inv-1"],
  "targetApplicantCode": "chen_xiuyun"
}
```

  - 响应返回业务摘要和草稿入口：

```json
{
  "batchId": "input_invoice_usage_oa_reverse_batch_xxx",
  "version": 2,
  "status": "oa_draft_created",
  "targetApplicantName": "陈秀云",
  "invoiceCount": 2,
  "totalWithTax": "99.72",
  "invoiceRows": [],
  "oaDraftUrl": "https://...",
  "canConfirmSubmission": true
}
```

- `POST /api/input-invoice-usage/oa-reverse/batches/{batchId}/manual-oa-status`
  - 保留，但调整语义：
    - `submitted`：进入已提交历史状态。
    - `not_submitted`：清理本地 `oaDraftId`/`oaDraftUrl`/确认状态，返回 `ready_to_create` 语义。

- `GET /api/input-invoice-usage/oa-reverse/submitted-history`
  - 返回已提交历史，只返回业务字段。
  - 不返回 `batchId`、`oaDraftId`、`previewHash`、英文状态。若前端需要 detail 操作，另开 detail API，不把内部 id 放进列表。

## 3. 文件结构

### 后端新增

- `backend/src/fin_ops_platform/services/oa_applicant_credentials.py`
  - `OaApplicantCredential`
  - `OaApplicantCredentialService`
  - `InMemoryOaApplicantCredentialRepository`
  - `SecretCipher` / `NoConfiguredSecretCipher`
  - errors: `OaApplicantCredentialPermissionError`, `OaApplicantCredentialNotConfiguredError`, `OaApplicantCredentialValidationError`
- `backend/src/fin_ops_platform/services/target_oa_applicant_token_provider.py`
  - `TargetOaApplicantTokenProvider`
  - `OaLoginClient`
  - `HttpOaLoginClient`
  - RSA encryption boundary for OA login password.
- `backend/src/fin_ops_platform/services/postgres_repositories/oa_applicant_credentials.py`
  - PostgreSQL repository for credential metadata and encrypted secret.
- `backend/src/fin_ops_platform/postgres/migrations/0066_oa_applicant_credentials.sql`
  - New credential table and grants.
- `backend/src/fin_ops_platform/app/routes_oa_applicant_credentials.py`
  - Route facade for admin-only credential APIs.

### 后端修改

- `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
  - Add one-step `create_oa_draft_from_selection(...)` or equivalent application method.
  - Add credential status into preview permissions/capabilities without leaking secrets.
  - Adjust `manual_oa_status(...)` state handling for `submitted` and `not_submitted`.
  - Add submitted history query payload.
- `backend/src/fin_ops_platform/services/postgres_repositories/input_invoice_usage_oa_reverse.py`
  - Add list submitted history query if SQL-level projection is needed.
- `backend/src/fin_ops_platform/app/server.py`
  - Wire credential service/repository/token provider.
  - Add credential API routes.
  - Add one-step draft route and history route.
  - Stop using `_input_invoice_usage_oa_draft_client(headers)` for target applicant creation.
- `tests/test_postgres_migrations.py`
  - Add migration file and table to expected lists.
- `deploy/oa/env/fin-ops.secrets.env.example`
  - Add secret env placeholders for credential encryption key and OA login RSA public key/path if required.
- `deploy/oa/README.md`
  - Document secret deployment contract if env changes.

### 前端新增

- `web/src/components/settings/SettingsOaApplicantCredentialsSection.tsx`
  - Admin-only credential management section.
- Optional: `web/src/features/workbench/oaApplicantCredentialsApi.ts`
  - If keeping `workbench/api.ts` small is preferred.

### 前端修改

- `web/src/components/settings/types.ts`
  - Add `oa_applicant_credentials` section id and props/types.
- `web/src/components/settings/SettingsPageContent.tsx`
  - Add navigation item and render credential section.
  - Load/save credential data through independent callbacks, not normal settings save.
- `web/src/pages/SettingsPage.tsx`
  - Load credential list for admins.
  - Wire credential save/delete calls.
- `web/src/features/workbench/types.ts`
  - Add credential DTO types if API client lives there.
- `web/src/features/workbench/api.ts`
  - Add credential API client or re-export from new file.
- `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`
  - Replace `创建本地批次` flow with single `创建 OA 草稿`.
  - Add `待处理 | 已提交` tab inside the OA reverse workspace.
  - Add confirmation dialog for `已提交 OA` / `未提交 OA`.
  - Keep rejected reason block hidden/compact.
- `web/src/features/inputInvoiceUsage/types.ts`
  - Add one-step create draft request/response and submitted history types.
- `web/src/features/inputInvoiceUsage/api.ts`
  - Add one-step create draft client and submitted history client.
  - Fix optional permission mapping so absent permissions do not become false.
- `web/src/pages/InputInvoiceUsagePage.tsx`
  - Pass new one-step action and submitted history loader.
- Styling files currently holding input invoice/settings CSS.
  - Keep layout compact; no nested cards.

### Docs 修改

- `docs/modules/input-invoice-usage/README.md`
- `docs/modules/input-invoice-usage/oa-reverse-design.md`
- `docs/modules/input-invoice-usage/state-machine.md`
- `docs/modules/input-invoice-usage/tests.md`
- `docs/modules/input-invoice-usage/implementation-notes.md`
- `docs/modules/settings/README.md`
- `docs/modules/settings/state-machine.md`
- `docs/modules/settings/tests.md`
- If API contract becomes stable enough, update `docs/dev/api-contracts.md`.
- If secret env changes, update `deploy/oa/README.md` and module deploy docs as applicable.

## 4. Phase 1：后端凭据管理

**目标：** 管理员可以维护目标 OA 申请人凭据；API 和 repository 只暴露非敏感状态，保存成功后 `hasCredential=true`。

**涉及文件：**

- Create: `backend/src/fin_ops_platform/services/oa_applicant_credentials.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/oa_applicant_credentials.py`
- Create: `backend/src/fin_ops_platform/postgres/migrations/0066_oa_applicant_credentials.sql`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `tests/test_postgres_migrations.py`
- Add tests: `tests/test_oa_applicant_credentials_service.py`
- Add tests: `tests/test_oa_applicant_credentials_api.py`
- Add tests: `tests/test_postgres_oa_applicant_credentials_repository.py`
- Update docs listed in section 3.

### Steps

- [x] Write service tests for credential save/list/delete.
  - Verify saving `{targetApplicantCode, targetApplicantName, oaUsername, password}` returns `hasCredential=true`.
  - Verify list payload never contains `password`, `encrypted`, `ciphertext`, `token`.
  - Verify empty password rejects on create/update.
  - Verify delete or disable returns `hasCredential=false` or removes row from list.
- [x] Write permission tests.
  - Admin `YNSYLP005` / `can_admin_access=True` can save credentials.
  - Full-access non-admin cannot save credentials.
  - Read-only user cannot save credentials.
- [x] Write PostgreSQL migration and repository tests.
  - Table recommendation: `app.oa_applicant_credentials`.
  - Columns: `target_applicant_code`, `target_applicant_name`, `oa_username`, `encrypted_password`, `enabled`, `raw_payload`, `created_at`, `updated_at`.
  - Add indexes on `target_applicant_code` and `enabled`.
  - Grants match app runtime/migrator/readonly patterns.
- [x] Implement storage encryption boundary.
  - Uses PostgreSQL `pgcrypto` with env `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY`.
  - If no key configured, PostgreSQL repository fails closed on save/decrypt with explicit configuration error.
  - No Python crypto dependency was added; no weak reversible encoding was introduced.
- [x] Implement service/repository.
  - Service receives repository as explicit dependency.
  - Repository knows SQL; service does not embed SQL.
  - Audit metadata excludes password/ciphertext.
- [x] Implement route/server wiring.
  - `server.py` resolves session and passes explicit actor/can_admin fields to route/service.
  - HTTP errors are specific and Chinese user-facing.
- [x] Update migration discovery tests.
- [x] Update docs.

**Verification commands:**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_oa_applicant_credentials_repository -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v
```

**完成标准：**

- 凭据保存后只显示 `已配置` 语义。
- 非管理员被后端拒绝。
- 响应和审计不泄密。
- 相关 docs 更新。

## 5. Phase 2：目标申请人 token provider 与一键创建 OA 草稿

**目标：** `创建 OA 草稿` 使用目标 OA 申请人的凭据/token 创建 `isDraft=true` 草稿，不使用当前操作人的 token。

**涉及文件：**

- Create: `backend/src/fin_ops_platform/services/target_oa_applicant_token_provider.py`
- Modify: `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/input_invoice_usage_oa_reverse.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `tests/test_input_invoice_usage_oa_reverse_service.py`
- Modify: `tests/test_input_invoice_usage_api.py`
- Add tests: `tests/test_target_oa_applicant_token_provider.py`
- Update docs.

### Steps

- [x] Write token provider tests.
  - Given credential repository returns encrypted password, provider decrypts through cipher and calls `OaLoginClient.login(oa_username, password)`.
  - Provider returns token and constructs `HttpEtcOAClient(token=target_token)`.
  - 401/expired token causes one retry login if caching is implemented.
  - Errors do not include password/token.
- [x] Write OA login client tests.
  - It calls OA `POST /login`.
  - It sends RSA-encrypted password, not plaintext.
  - It extracts access token from OA response shapes used by smart OA.
  - It maps wrong password to `target_oa_login_failed`.
- [x] Write service tests for one-step create.
  - Selected invoices + target applicant + preview hash create internal batch and OA draft in one service call.
  - Target applicant credential missing returns business error.
  - Active OA relation invoice remains rejected.
  - Preview hash stale returns conflict.
  - OA draft payload has `isDraft=True`, target applicant name and batch id.
  - Fake OA client asserts token/client came from target applicant provider, not current request.
- [x] Replace or wrap existing two-step backend flow.
  - Keep `create_batch(...)` if useful internally.
  - Add `create_oa_draft_from_selection(...)` that calls `create_batch(...)` then `create_oa_draft(...)` with target applicant client.
  - Operation is idempotent by idempotency key.
- [x] Adjust manual status semantics.
  - `submitted`: final local status should be a submitted history status, not require automatic detection.
  - `not_submitted`: clear `oa_draft_id`, `oa_draft_url`, detection fields and return a state where `canCreateDraft=true`.
  - Keep minimal audit event, no visible rollback history.
- [x] Add submitted history query.
  - History includes target applicant name, confirmed time, amount, invoice count, invoice display summary.
  - Internal ids are not in list payload.
- [x] Add API tests.
  - One-step route success.
  - Missing credential.
  - Permission denied.
  - OA login failure.
  - OA draft failure.
  - User confirms submitted.
  - User confirms not submitted and can recreate.
  - Submitted history shape excludes internal ids.
- [x] Update docs.

**Verification commands:**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_target_oa_applicant_token_provider -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_oa_reverse_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_input_invoice_usage_oa_reverse_repository -v
```

**完成标准：**

- 后端一键创建草稿可用。
- 当前 header token 不参与目标 applicant OA draft 创建。
- `未提交 OA` 本地回滚后可重新创建。
- `已提交 OA` 历史可读且不暴露内部 id。

## 6. Phase 3：设置页凭据管理 UI

**目标：** 管理员在设置页维护目标 OA 申请人账号密码，字段只展示目标 OA 申请人、OA 登录账号、`已配置`/`未配置`。

**涉及文件：**

- Create: `web/src/components/settings/SettingsOaApplicantCredentialsSection.tsx`
- Modify: `web/src/components/settings/types.ts`
- Modify: `web/src/components/settings/SettingsPageContent.tsx`
- Modify: `web/src/pages/SettingsPage.tsx`
- Modify/Create: `web/src/features/workbench/api.ts` or `web/src/features/workbench/oaApplicantCredentialsApi.ts`
- Modify: `web/src/features/workbench/types.ts`
- Modify: `web/src/test/WorkbenchSelection.test.tsx`
- Modify: `web/src/test/SettingsPage.test.tsx` if structural guard needs new source path.
- Modify: `web/src/test/apiMock.ts`
- Update settings and input invoice usage docs.

### Steps

- [x] Add API client tests or interaction tests that assert credential endpoints are independent from `/api/workbench/settings`.
- [x] Add mock API support for credential list/save/delete.
- [x] Add types:
  - `OaApplicantCredentialSummary`
  - `SaveOaApplicantCredentialRequest`
- [x] Add settings section id `oa_applicant_credentials`.
- [x] Add nav item `OA申请人凭据`.
  - Visible only when `canManageAccessControl` / admin.
  - Count is number of configured credentials or target applicants.
- [x] Build section UI.
  - Table columns: `目标 OA 申请人`, `OA 登录账号`, `凭据状态`, `操作`.
  - Password input only in save/update form.
  - Save/update success clears password field.
  - Status text only `已配置` / `未配置`.
  - No recent updater or verification time.
- [x] Wire `SettingsPage`.
  - Load credentials only for admin.
  - Save/delete via independent API calls.
  - Do not include password in `saveWorkbenchSettings(...)`.
- [x] Add frontend tests.
  - Admin sees credential section.
  - Full-access non-admin does not see credential section.
  - Save password calls credential endpoint and clears password input.
  - Normal settings save body does not contain password.
- [x] Update docs.

**Verification commands:**

```bash
cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx
cd web && npm test -- --run src/test/SettingsPage.test.tsx
```

**完成标准：**

- 管理员可维护凭据。
- 非管理员不可见/不可操作。
- 密码不回显，不进入普通 settings save payload。

## 7. Phase 4：进项发票使用页面 UI 闭环

**目标：** 前端用户只看到 `创建 OA 草稿`，并通过 `待处理 | 已提交` 完成确认和历史查看。

**涉及文件：**

- Modify: `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`
- Modify: `web/src/features/inputInvoiceUsage/types.ts`
- Modify: `web/src/features/inputInvoiceUsage/api.ts`
- Modify: `web/src/pages/InputInvoiceUsagePage.tsx`
- Modify: input invoice usage CSS files as needed.
- Modify: `web/src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx`
- Modify: `web/src/test/InputInvoiceUsagePage.test.tsx`
- Modify: `web/src/test/apiMock.ts`
- Update docs.

### Steps

- [x] Update API client.
  - Add `createInputInvoiceUsageOaReverseDraftFromSelection(...)`.
  - Add `fetchInputInvoiceUsageOaReverseSubmittedHistory(...)`.
  - Fix preview permissions mapper so missing `permissions` stays `undefined`; do not map absent booleans to `false`.
- [x] Refactor drawer props.
  - Remove user-facing `createBatch` dependency from UI.
  - Keep internal names if necessary, but button text and user flow must be `创建 OA 草稿`.
- [x] Add `待处理 | 已提交` segmented control/tab.
  - `待处理` shows current candidate/target applicant/create flow.
  - `已提交` loads history and shows business summary.
- [x] Implement one-click create.
  - Button disabled only when no candidates, no permission, target applicant missing credential, or action loading.
  - On click, call one-step create draft API with preview hash, selected IDs, target applicant.
- [x] Implement confirmation dialog.
  - On success show OA draft link and summary.
  - Actions: `已提交 OA`, `未提交 OA`.
  - `已提交 OA` calls manual status and refreshes history.
  - `未提交 OA` calls manual status and resets local UI to ready-to-create.
- [x] Remove old visible controls.
  - No `创建本地批次`.
  - No `刷新 OA 状态` main path unless explicitly retained only for detection exception fallback; if retained, keep hidden from first-path UX.
  - No large `不可提交原因` block.
- [x] Implement submitted history display.
  - Fields: applicant, confirmation time, amount, invoice count, invoice numbers/seller summary.
  - Do not render internal ids or English statuses.
- [x] Add frontend tests.
  - Drawer never renders `创建本地批次`.
  - Create button appears after valid selection.
  - Button disabled for missing credential/permission.
  - Create success opens confirmation dialog.
  - `未提交 OA` returns to create state.
  - `已提交 OA` switches or refreshes `已提交` history.
  - Submitted history does not display `batchId`, `oaDraftId`, `previewHash`, English status.
  - `不可提交原因` block remains absent.
- [x] Update docs.

**Verification commands:**

```bash
cd web && npm test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx
cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx
```

**完成标准：**

- 用户主路径只有 `创建 OA 草稿`。
- `待处理 | 已提交` 完整可用。
- 手动确认后 UI 和后端状态一致。

## 8. Phase 5：全链路集成、回归和文档收口

**目标：** 补齐跨模块测试、验证命令和文档，使功能满足生产发布标准。

**涉及文件：**

- Modify/add backend integration tests as needed.
- Modify/add frontend tests as needed.
- Modify docs listed in section 3.
- Optional: update `docs/dev/api-contracts.md` with final API contract.
- Optional: update deploy docs if new env vars are required.

### Steps

- [x] Add end-to-end backend API integration test.
  - Admin configures credential.
  - Full-access user previews and creates OA draft.
  - Fake target applicant OA login returns token.
  - Fake OA draft client receives target applicant token.
  - User confirms submitted.
  - Submitted history returns business fields only.
- [x] Add rollback integration test.
  - Create draft.
  - User chooses `未提交 OA`.
  - Local response returns create-ready state.
  - Re-create with new idempotency key succeeds.
- [x] Run targeted backend tests.
- [x] Run targeted frontend tests.
- [x] Run build.
- [x] Update `docs/modules/input-invoice-usage/tests.md`.
  - Replace design-stage risk with actual test entries and commands.
- [x] Update `docs/modules/input-invoice-usage/state-machine.md`.
  - Ensure final state names match implementation.
- [x] Update `docs/modules/input-invoice-usage/implementation-notes.md`.
  - Record implementation decisions and verification.
- [x] Update `docs/modules/settings/state-machine.md` and `tests.md`.
  - Record credential management UI/API state and tests.
- [x] Review for secret leakage.
  - Search changed files/tests for sample passwords/tokens in expected responses.
  - Ensure snapshots/mock payloads do not store real-looking secrets.

**Verification commands:**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_target_oa_applicant_token_provider -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_oa_reverse_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v
cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx
cd web && npm test -- --run src/test/SettingsPage.test.tsx
cd web && npm test -- --run src/test/InputInvoiceUsageFiltersAndDrawers.test.tsx
cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx
cd web && npm run build
```

**完成标准：**

- 所有完整验收标准通过。
- 文档与最终实现一致。
- 没有密码/token 泄漏。
- 当前无关 ETC 改动未被触碰。

## 9. 七类测试覆盖判断

| 类别 | 是否适用 | 覆盖计划 |
| --- | --- | --- |
| 1. Business core unit tests | 适用 | 权限判断、凭据状态、active OA 关系排除、状态流转、未提交回滚、已提交历史。 |
| 2. Service-layer tests | 适用 | 凭据 service/repository、token provider、OA draft orchestration、batch idempotency、audit redaction。 |
| 3. API contract tests | 适用 | 凭据 API、创建草稿 API、manual status、history、权限不足、未配置凭据、外部 OA 失败。 |
| 4. Read model/cache/background job tests | 视实现影响适用 | 如果反提 OA 状态影响 input invoice usage read model，则覆盖 dirty scope/freshness；若 history 独立，则明确不适用。 |
| 5. Frontend component and interaction tests | 适用 | 设置页凭据 UI、OA reverse drawer、按钮状态、确认弹窗、history tab。 |
| 6. End-to-end business-flow integration tests | 适用 | 管理员配置凭据 -> 全权限用户创建草稿 -> 用户确认已提交；另一路径覆盖未提交回滚。 |
| 7. Existing feature regression tests | 适用 | 设置页现有访问账户保存、输入发票 rows/read model、OA reverse 旧接口兼容策略、导出/筛选不回归。 |

## 10. 后续阶段 Prompt 模板

每个阶段完成后生成下一阶段 prompt，格式如下：

```text
你在 /Users/yu/Desktop/fin-ops-platform 工作，必须在 main 分支上工作。

执行 Phase <N>：<阶段名称>。

先读取：
- AGENTS.md
- docs/modules/input-invoice-usage/README.md
- docs/modules/input-invoice-usage/oa-reverse-design.md
- docs/modules/input-invoice-usage/state-machine.md
- docs/modules/input-invoice-usage/tests.md
- docs/modules/input-invoice-usage/oa-reverse-implementation-plan.md
- 如触及设置页，还读 docs/modules/settings/README.md、state-machine.md、tests.md

要求：
- 不触碰无关未提交改动。
- 按计划先写/更新测试，再实现，再运行验证。
- 后端复用现有 service/repository/helper；server.py 只做路由和依赖组装。
- 结束前更新模块文档和状态机文档。
- 最终输出修改文件、测试覆盖七类判断、验证命令、剩余风险、下一阶段 prompt。
```

## 11. Phase 1 执行 Prompt

```text
你在 /Users/yu/Desktop/fin-ops-platform 工作，必须在 main 分支上工作。

执行「进项发票反提 OA 闭环」Phase 1：后端凭据管理闭环。

先读取：
1. AGENTS.md
2. docs/modules/input-invoice-usage/README.md
3. docs/modules/input-invoice-usage/oa-reverse-design.md
4. docs/modules/input-invoice-usage/state-machine.md
5. docs/modules/input-invoice-usage/tests.md
6. docs/modules/input-invoice-usage/oa-reverse-implementation-plan.md
7. docs/modules/settings/README.md
8. docs/modules/settings/state-machine.md
9. docs/modules/settings/tests.md

只做 Phase 1，不实现前端 UI，不实现创建 OA 草稿。

目标：
- 新增目标 OA 申请人凭据 service/repository/API。
- 管理员 YNSYLP005 或 can_admin_access=true 可以维护凭据。
- 非管理员不能维护凭据。
- 保存密码后状态为已配置。
- GET 列表只返回目标申请人、OA 登录账号、hasCredential/enabled，不返回密码、密文、token。
- 凭据不能进入 /api/workbench/settings 普通 payload。

必须先写/更新测试：
- tests/test_oa_applicant_credentials_service.py
- tests/test_oa_applicant_credentials_api.py
- tests/test_postgres_oa_applicant_credentials_repository.py
- tests/test_postgres_migrations.py

实现文件建议：
- backend/src/fin_ops_platform/services/oa_applicant_credentials.py
- backend/src/fin_ops_platform/services/postgres_repositories/oa_applicant_credentials.py
- backend/src/fin_ops_platform/postgres/migrations/0066_oa_applicant_credentials.sql
- backend/src/fin_ops_platform/app/routes_oa_applicant_credentials.py
- backend/src/fin_ops_platform/app/server.py

约束：
- 不明文保存密码。
- 不在 response/audit/log/test snapshot 中泄露 password/ciphertext/token。
- 如果缺少加密 key，保存/解密必须 fail closed。
- 如需新增依赖，先停止说明理由，不直接添加。
- 不修改无关 ETC 文件。

验证：
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_applicant_credentials_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_oa_applicant_credentials_repository -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v

结束前更新：
- docs/modules/input-invoice-usage/tests.md
- docs/modules/input-invoice-usage/implementation-notes.md
- docs/modules/settings/state-machine.md
- docs/modules/settings/tests.md

最终回复必须包含：
- 修改文件
- 已运行验证命令
- 七类测试覆盖判断
- 剩余风险
- Phase 2 的下一步执行 prompt
```

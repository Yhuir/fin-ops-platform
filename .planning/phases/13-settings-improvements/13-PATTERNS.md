---
phase: 13
slug: settings-improvements
status: complete
mapped: 2026-08-02
mapper_mode: constrained-local-fallback
---

# Phase 13 — Existing Patterns Map

## Mapping conclusion

The codebase already contains every structural pattern needed for T0-01. The implementation should compose these existing patterns and delete the legacy ACL path; it should not create a new ACL service hierarchy.

## New/changed responsibility → closest existing analog

| Required change | Reuse this analog | Why it fits | Do not copy |
| --- | --- | --- | --- |
| Admin-only ACL route | `SettingsApiRoutes` existing `resolve_admin_session` paths for OA credentials/data reset | Same route owner, auth resolver, JSON/error mapping | New auth middleware or route-level SQL |
| Strictly reject ACL fields in generic settings | Existing `bank_transaction_tags_write_forbidden` check in `SettingsApiRoutes.update_settings` | Exact trust-boundary failure pattern | Silent ignore/backward-compatible fallback |
| ACL optimistic concurrency | `PostgresOpsTaxEtcRepository.save_app_settings_for_bank_flow_rule_version_in_transaction(...)` | Already uses `SELECT ... FOR UPDATE`, reads nested version, merges one settings family | Whole-row service snapshot compare without row lock |
| Settings + audit same transaction | `PostgresBankTransactionCategoryRepository.apply_mutation(...)` and `PostgresExternalControlEvidenceRepository._record_event(...)` | Canonical write and `audit.events` use caller-owned transaction | In-memory `AuditTrailService` as durable proof |
| Transaction owner | `BankTransactionCategoryMutationWriter.persist_many(...)` | Opens one connection transaction then delegates repository mutation | Service opening nested transactions or route owning UoW |
| Local-store parity | `ApplicationStateStore` existing `RLock` | Existing process-local serialization point | New lock package or per-feature local database |
| Dedicated admin-only frontend load | `SettingsPage` OA applicant credential effect | Loads only when active + `canAdminAccess`, aborts on unmount, clears state otherwise | Global fetch for non-admin or a new data-fetch library |
| Dedicated admin-only frontend mutation | OA applicant credential save/delete callbacks and existing page feedback | Independent busy/error state without changing page architecture | Chaining ACL PUT to the ordinary global settings save |
| Version conflict UI | Existing settings rule conflict error parsing via `normalizeSettingsError` | Current error envelope already parsed into user feedback | Silent refetch/overwrite of an admin's concurrent change |
| OA role sync | Existing `OARoleSyncService.sync_access_control(...)` and MySQL transaction | Current external boundary and compensation behavior are adequate | New outbox/worker/systemd unit in this phase |
| No-op optimization | Settings rule methods that avoid persistence on semantic no-op | Existing codebase already tests no-op writes | Audit/OA calls when normalized accounts did not change |
| Browser permission regression | `permissions-role-matrix.spec.ts` direct route tracking and role fixtures | Existing source of truth for read/full/admin Browser behavior | UI-only assertion without direct API attack |

## File-by-file guidance

### `backend/src/fin_ops_platform/app/routes_settings.py`

- Extend the current `SettingsApiRoutes.route(...)` matcher with exact GET/PUT access-control paths.
- Reuse `_resolve_admin_session` directly; do not add another resolver.
- Generic POST should use the same explicit-forbidden-field style as `bank_transaction_tags_write_forbidden`.
- Dedicated PUT should map validation to 400, version conflict to 409, OA sync failure to 502, persistence failure to the existing settings persistence envelope.

### `backend/src/fin_ops_platform/services/app_settings_service.py`

- Keep ordinary settings normalization in the current service.
- Remove ACL arguments from `update_settings(...)`; copy/preserve ACL only at the persistence boundary, not in every caller.
- Add the smallest explicit ACL methods to this class rather than a one-implementation `AccessControlManagementService`:
  - normalized snapshot read;
  - request validation/target snapshot;
  - external sync + durable commit/compensation orchestration.
- Reuse the existing semantic no-op style.
- Do not broaden this phase into splitting the large settings service.

### State store and PostgreSQL repository

- Put row-lock/CAS/merge/audit SQL beside the existing app-settings repository methods in `postgres_repositories/ops_tax_etc.py`.
- Expose explicit ports through `state_store_protocol.py`, `state_store.py`, and `postgres_state_store.py`.
- Make the generic writer preserve ACL centrally. Do not fix callers one by one.
- The dedicated ACL writer is the only code path allowed to change ACL keys.

### `backend/src/fin_ops_platform/services/access_control_service.py`

- Replace three dynamic providers with one snapshot provider.
- Resolve that provider once per `evaluate(...)` call.
- Keep the fixed protected admin check explicit and first/fail-safe.
- Remove runtime dynamic/env admin list authority; do not retain a compatibility union.
- Preserve characterized non-admin admission behavior in this phase.

### `backend/src/fin_ops_platform/app/auth.py` and `server.py`

- Update wiring only; do not move permission decisions into HTTP code.
- Local dev/test auth may keep its explicit test-only synthetic capability, but must not clone retired provider/admin fields.

### Frontend

- Keep `/settings` as the single ACL UI.
- Follow the existing OA credential pattern: separate admin-only load, independent busy/error state, aborted stale requests.
- Add a dedicated save control inside `SettingsAccessAccountsSection`; the global settings save must ignore its draft.
- Remove the entire access-account branch from `WorkbenchSettingsModal`; do not reconnect it to the new endpoint.
- Update `ReconciliationWorkbenchPage` column-layout autosave to the smaller generic DTO.

### Tests/mocks/docs

- Reuse existing settings/session/OA role sync test modules; add focused cases rather than a parallel test package.
- Deterministic mocks should expose a separate ACL state and route; generic POST must fail on ACL keys just like production.
- Keep `permissions-role-matrix.spec.ts` as the Browser source of truth and add direct `request.put/post` privilege escalation assertions.
- Update boundary docs because API response shape, permission I/O, OA sync trigger, file range, tests, and old-code deletion conditions all change.

## Patterns explicitly rejected

- A new ACL microservice, repository interface hierarchy, command bus, event bus, saga framework, Redis cache, or worker.
- Making all settings admin-only.
- Frontend-only hiding.
- Ignoring legacy ACL fields.
- Keeping both `/settings` and `WorkbenchSettingsModal` as ACL editors.
- Reusing whole `app.app_settings.version` as ACL version; unrelated settings writes would cause false conflicts.
- Copying ACL arrays through every generic caller.
- Durable audit through the current in-memory `AuditTrailService`.
- Rolling back to the vulnerable binary after the DB security migration.

## Whole-repo deletion sentinels

Execution is not complete while these remain in runtime paths:

```text
dynamic_admin_usernames_provider
get_admin_usernames
FIN_OPS_ADMIN_USERNAMES              # runtime authority; historical migration docs may mention retirement
saveWorkbenchSettings(... adminUsernames/allowedUsernames/readonlyExportUsernames ...)
generic POST /api/workbench/settings parsing admin_usernames
WorkbenchSettingsModal access_accounts section
pending invoice getattr fallback replaying access_control
```

Tests and migration fixtures may mention legacy fields only when asserting rejection, migration cleanup, or rollback defense.

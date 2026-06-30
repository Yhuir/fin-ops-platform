---
status: resolved
trigger: "Bank details auto-tag rule save returns bank_auto_tag_rules_persistence_failed after editing a bank detail tag/rule."
created: 2026-06-30
updated: 2026-06-30
---

# Debug Session: bank-auto-tag-persistence-readback

## Symptoms

- Expected behavior: Editing bank details auto-tag rules saves the new rule version, reloads the saved payload, and then triggers bank detail refresh.
- Actual behavior: The page shows an operation-failed dialog with `bank_auto_tag_rules_persistence_failed`.
- Error messages: "自动标签规则保存失败：持久化设置源未返回刚写入的规则版本，请稍后重试。"
- Timeline: Reported on 2026-06-30 after the direction-only no-op fix was already present in the local codebase.
- Reproduction: Edit a bank details auto-tag rule and save while the persistence readback can briefly return the previous settings snapshot.

## Current Focus

- hypothesis: resolved.
- test: `tests.test_bank_auto_tag_rules_api.BankAutoTagRulesApiTests.test_put_retries_transient_stale_settings_read_after_write`.
- expecting: transient stale readback is retried, but a state store that never persists the write still returns 503 and does not trigger lifecycle/audit.
- next_action: deploy and verify a real page save/reload/refresh in production.
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- 2026-06-30: Existing direction/account-scope regression tests pass; current code already detects payload-only rule changes.
- 2026-06-30: The failing dialog maps to `AppSettingsService._save_and_verify_bank_auto_tag_rules_snapshot(...)`, after `save_app_settings(...)` and during immediate `load_app_settings()` verification.
- 2026-06-30: A test double that persists the write but returns the previous settings snapshot for the first readback reproduces the 503.
- 2026-06-30: Retrying readback fixes the transient stale-read case while preserving the existing false-success guard for a store that never writes.

## Eliminated

- Frontend payload omission: existing tests cover direction serialization and backend receives the submitted rules.
- Auto-tag no-op detection: current `rule_payload_changes` tests pass.
- Read model worker delay: the failure happens before lifecycle/refresh enqueue; it is a settings persistence verification branch.
- False success fallback: still rejected by the existing persistence-failure regression.

## Resolution

- root_cause: The save path treated a single stale immediate settings readback as a hard persistence failure, even when the write had succeeded and the next read would return the new version.
- fix: Retry settings readback with two short backoffs before returning `bank_auto_tag_rules_persistence_failed`; keep the existing mismatch failure when all attempts read stale data.
- verification: Added the transient-stale readback API regression and reran the existing no-persist regression.
- files_changed: `backend/src/fin_ops_platform/services/app_settings_service.py`, `tests/test_bank_auto_tag_rules_api.py`, `docs/modules/bank-details/implementation-notes.md`, `docs/modules/bank-details/tests.md`.

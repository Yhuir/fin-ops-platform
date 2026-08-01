---
phase: 13
slug: settings-improvements
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-02
---

# Phase 13 — Validation Strategy

> T0-01 每个实现任务的反馈采样合同。测试先于实现建立红线；执行结束前不得只凭 UI 隐藏或单个 200 断言验收。

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python `unittest` + Vitest/Testing Library + Playwright |
| **Config file** | `web/vitest.config.ts`（或 package scripts 当前配置）、`web/playwright.config.ts`、`scripts/verify.sh` |
| **Quick run command** | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service tests.test_session_api tests.test_workbench_settings_sync_api -v` |
| **Full suite command** | `bash scripts/verify.sh all` |
| **Estimated runtime** | 执行前由当前机器实测记录；不预填未经测量的时间 |

## Sampling Rate

- **After every task commit:** 运行该 task `<verify>` 的最小单测/类型检查。
- **After every plan wave:** 运行本 wave 涉及的 backend + frontend 组合测试。
- **Before `$gsd-verify-work`:** `bash scripts/verify.sh all` 必须通过。
- **Max feedback latency:** 每个 atomic task 都有直接测试；不得连续 3 个 task 只到 wave 末尾才验证。

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 0 | PAR-01/PAR-03 | T13-06 | 0132 repair/audit/CHECK阻断非法admin与unsafe rollback payload | migration | `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v` | ✅ extend | ⬜ pending |
| 13-01-02 | 01 | 0 | PAGE-15/PAR-01/PAR-03 | T13-02/03 | ACL/generic共享advisory lock、专用guard、commit-before-return、local parity与finally unlock | repository/service port | `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_repositories_boundaries tests.test_state_store_contract tests.test_postgres_state_store -v` | ✅ extend | ⬜ pending |
| 13-02-01 | 02 | 1 | PAGE-15/PAR-01/PAR-03 | T13-01/20 | 同task RED→GREEN：generic无ACL response/fixture、admin API、request-id audit=response且不可spoof | API/TDD | `PYTHONPATH=backend/src python3 -m unittest tests.test_http_adapter tests.test_app_settings_service tests.test_workbench_settings_sync_api tests.test_session_api tests.test_auth_guard tests.test_read_model_api_contract_harness -v` | ✅ extend | ⬜ pending |
| 13-02-02 | 02 | 1 | PAR-01/PAR-02/PAR-03 | T13-02/03/04 | known rollback与unknown COMMIT mutation proof/fresh-lock；OA connect/read/write timeout；真实PG不可skip | service/PG integration | `PYTHONPATH=backend/src python3 -m unittest tests.test_app_settings_service tests.test_workbench_settings_sync_api tests.test_oa_role_sync_service tests.test_postgres_state_store tests.test_postgres_repositories_boundaries -v && bash scripts/verify.sh settings-acl-postgres` | ✅ extend | ⬜ pending |
| 13-02-03 | 02 | 1 | PAGE-15/PAGE-04/PAR-03 | T13-01/05 | 单snapshot、B-06 callers及API contract harness迁移，whole-repo response/fixture/signature sentinel | backend regression | `PYTHONPATH=backend/src python3 -m unittest tests.test_session_api tests.test_auth_guard tests.test_permissions_write_entry_inventory tests.test_read_model_api_contract_harness tests.test_app_health_api tests.test_app_postgres_mode tests.test_bank_auto_tag_rules_api tests.test_batch_accounting_api tests.test_etc_backend tests.test_etc_invoice_pdf_bundle_service tests.test_oa_manual_import_api tests.test_oa_pending_payment_api tests.test_pending_invoice_api tests.test_postgres_state_store_integration tests.test_tax_offset_api tests.test_turnover_ledger_api tests.test_workbench_dirty_queue_wiring tests.test_workbench_v2_api -v` | ✅ extend | ⬜ pending |
| 13-03-01 | 03 | 2 | PAGE-15/PAGE-04 | T13-01 | admin 独立 ACL load/save，普通 save body 无 ACL | frontend | `cd web && npm test -- --run src/test/SettingsPage.test.tsx` | ✅ extend | ⬜ pending |
| 13-03-02 | 03 | 2 | PAGE-04/PAR-03 | T13-05 | Workbench modal/column/pending frontend legacy ACL删除 | frontend regression | `cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx src/test/WorkbenchColumnLayout.test.tsx src/test/PendingInvoicesApi.test.ts` | ✅ extend | ⬜ pending |
| 13-03-03 | 03 | 2 | PAGE-15/PAR-03 | T13-01 | full-access Browser direct API 自提被拒；admin 改他人成功 | E2E | `cd web && npx playwright test e2e/permissions-role-matrix.spec.ts` | ✅ extend | ⬜ pending |
| 13-04-01 | 04 | 3 | PAGE-04/PAGE-05/PAR-01 | T13-18 | 正确长期doc paths与边界/测试/runbook闭环 | docs | `bash scripts/verify.sh docs` | ✅ update | ⬜ pending |
| 13-04-02 | 04 | 3 | PAR-01/PAR-03 | T13-06/13/16/21 | 双token identity preflight/redaction/用途隔离、API quiesce与safe rollback gate | deploy/tool | `PYTHONPATH=backend/src python3 -m unittest tests.test_settings_access_control_preflight tests.test_deploy_oa_script tests.test_postgres_migrations -v && bash scripts/verify.sh lint` | ✅ extend/new | ⬜ pending |
| 13-04-03 | 04 | 3 | 全部 | T13-01..21 | local/candidate deterministic I/O、legacy response/fixture sentinels、七类回归与verify all | regression | `bash scripts/verify.sh all` | ✅ | ⬜ pending |
| 13-04-04 | 04 | 3 | PAR-03 | T13-15/16 | 用户批准candidate upload与一次性manual-root hash-pinned helper bootstrap；禁legacy self-update | bootstrap checkpoint | targeted deploy/preflight tests exit0 + human approval | ✅/manual | ⬜ pending |
| 13-04-05 | 04 | 3 | PAR-03 | T13-13/21 | `--no-activate`只上传/check candidate；app/DB/OA/ACL/root helper不变 | candidate upload | `./scripts/deploy-oa.sh --no-activate --release-name <release> && ssh -o StrictHostKeyChecking=accept-new -o ControlMaster=no finops-deploy@finops-prod 'sudo -n /usr/local/sbin/finops-deploy-control check-release <release>'` | ➖ remote | ⬜ pending |
| 13-04-06 | 04 | 3 | PAR-03 | T13-13/16/21 | root同文件系统temp+approved hash+prevalidate+atomic replace/restore；runtime-worker helper不变 | manual root bootstrap | remote contract/candidate/bootstrap sha checks + human root confirmation | ➖ remote/manual | ⬜ pending |
| 13-04-07 | 04 | 3 | PAGE-15/PAR-03 | T13-15/16 | SSH stdin只读preflight+remote hash与第二activation批准 | production checkpoint | explicit SSH preflight/hash command from 13-04 Task7 | ➖ remote | ⬜ pending |
| 13-05-01 | 05 | 4 | PAGE-15/PAR-03 | T13-22 | SSH just-in-time重验remote artifact/fingerprints无漂移；漂移回13-04 Task7重新批准 | production gate | explicit SSH preflight/hash command from 13-05 Task1 | ➖ remote | ⬜ pending |
| 13-05-02 | 05 | 4 | PAGE-15/PAR-01/PAR-03 | T13-23/24 | activate-existing zero reupload；仅safe active/API恢复完成 | production release | `./scripts/deploy-oa.sh --activate-existing --release-name <release>` | ✅ extend | ⬜ pending |
| 13-05-03 | 05 | 4 | PAGE-15/PAR-02/PAR-03 | T13-25/26/27 | SSH stdin postdeploy、full→read→denied与restore | production smoke | explicit SSH postdeploy/hash command from 13-05 Task3 | ➖ remote | ⬜ pending |
| 13-05-04 | 05 | 4 | 全部 | T13-28 | remote两artifact/hash与用户最终验收 | final checkpoint | explicit SSH remote hash command from 13-05 Task4 | ➖ remote | ⬜ pending |

## Threat References

| Ref | Threat | Required proof |
| --- | --- | --- |
| T13-01 | full-access 自提/改他人权限 | backend 403/400 + state unchanged + direct API E2E |
| T13-02 | 并发/旧 snapshot 覆盖 ACL、补偿覆盖后续OA或成功无 audit | shared advisory lock/专用guard确定性交错；commit-before-return；finally unlock |
| T13-03 | ordinary settings 缺省/旧字段清空 ACL | strict reject + omission preservation tests |
| T13-04 | OA 与本地 ACL 半同步 | target failure/DB failure/compensation/no-op tests + runbook |
| T13-05 | 删除旧 payload 后关联台/其它页面保存回归 | column-layout/modal/pending rules regression |
| T13-06 | 旧 binary/历史数据重新引入非 protected admin | migration repair + CHECK + deploy/rollback tests |

## Wave 0 Requirements

- [ ] 0132 migration repair/audit/CHECK tests在13-01内实现并以正常命令exit 0。
- [ ] repository/local-store CAS、generic-preserve-ACL、audit rollback/no-op tests在13-01内实现并exit 0。
- [ ] API/session/direct attack RED证据移入13-02 Task 1同一TDD循环，Task结束gating command必须GREEN/exit 0。
- [ ] frontend与Playwright RED→GREEN分别留在13-03对应实现task，不作为前置wave阻塞。

现有测试框架足够，不安装依赖、不增加测试框架。

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 真实 OA 三角色同步 | PAR-02/PAR-03 | local executor/mock不能证明production MySQL角色事实 | 13-04 production只读preflight盘点；13-05批准后由admin对专用bearer账号full→read→denied逐档验证并finally恢复/read-back |
| 生产历史非法 admin 清理 | PAR-01/PAR-03 | 生产数据不应进入普通测试 | 双token stdin root-owned preflight生成artifact/hash；用户确认后13-05通过canonical deploy应用migration |
| 生产延迟采样 | PAR-02 | 不编造 SLO | 记录 generic save、ACL GET、ACL no-op/real PUT 的 p50/p95 与 OA/DB 分段，不输出 token/secret |
| 安全cutover/回滚 | PAR-03 | 涉及live API/migration/OA | deterministic deploy tests锁定顺序；production capability/fingerprint拒绝unsafe previous；任何rollback/maintenance/repair均blocked并重启审批链 |
| 正式生产发布 | 全部 | 必须用户明确授权外部写入 | 13-04两级批准完成后，13-05运行`./scripts/deploy-oa.sh --activate-existing --release-name <release>`；仅zero-reupload safe active+API恢复可进入post-deploy |

## PLAN-CHECK Revision Background

- Iteration 1/3针对`13-PLAN-CHECK.md` B-01..B-08修订。
- Wave 0不再包含预期非零的test-only RED gate；所有`<automated>`命令在所属task完成时预期exit 0。
- production closure拆为13-04只读preflight/准备与13-05批准后发布/证据，approval本身不再等于完成。
- deploy gate新增API quiesce、ACL-safe capability/fingerprint与maintenance/forward-repair；request ID由http adapter生成并绑定audit=response。
- B-06 backend callers与`PendingInvoicesApi.test.ts`已明确归属，禁止legacy兼容。
- Iteration 2/3按P-01..P-05收紧：ACL专用shared-advisory-lock guard；API contract harness/response fixture sentinel；外部事实只由production gates证明；双HTTP token identity/hash/逐档恢复协议；canonical deploy参数与blocked失败状态。
- 所有task完成gate仍预期exit0；13-05 Task2任何非零、safe rollback、maintenance或forward repair均不算done，repair后必须回13-04 Task7重新取证/批准，再重跑Task1/2。
- Iteration 3/3新增两级production批准与explicit SSH remote artifact边界；unknown COMMIT使用fresh-lock/mutation-id proof；OA read/write timeout固定为10秒；final activation仅`--activate-existing`。
- Final adjudication关闭剩余执行缺口：首次production helper bootstrap改为单独批准的manual-root同文件系统原子替换，明确禁止legacy self-update及runtime-worker helper变化；`settings-acl-postgres`在缺disposable DB或lost-ACK测试skip时fail closed。

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency is bounded by per-task targeted commands
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** final plan check passed；implementation、external bootstrap、production activation与最终production sign-off均pending。

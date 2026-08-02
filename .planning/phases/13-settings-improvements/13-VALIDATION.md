---
phase: 13
slug: settings-improvements
status: draft
nyquist_compliant: true
wave_0_complete: true
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
| 13-01-01 | 01 | 0 | PAR-01/PAR-03 | T13-06 | 0132 repair/audit/CHECK阻断非法admin与unsafe rollback payload | migration | `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v` | ✅ extend | ✅ complete |
| 13-01-02 | 01 | 0 | PAGE-15/PAR-01/PAR-03 | T13-02/03 | ACL/generic共享advisory lock、专用guard、commit-before-return、local parity与finally unlock | repository/service port | targeted command in 13-01 | ✅ extend | ✅ complete |
| 13-02-01 | 02 | 1 | PAGE-15/PAR-01/PAR-03 | T13-01/20 | generic无ACL、admin API、request-id audit=response | API/TDD | targeted command in 13-02 | ✅ extend | ✅ complete |
| 13-02-02 | 02 | 1 | PAR-01/PAR-02/PAR-03 | T13-02/03/04 | COMMIT proof、OA timeout、真实PG fail-closed | service/PG integration | targeted command in 13-02 | ✅ extend | ✅ complete |
| 13-02-03 | 02 | 1 | PAGE-15/PAGE-04/PAR-03 | T13-01/05 | backend callers/API contract/sentinel | backend regression | targeted command in 13-02 | ✅ extend | ✅ complete |
| 13-03-01 | 03 | 2 | PAGE-15/PAGE-04 | T13-01 | admin独立ACL UI，普通save无ACL | frontend | targeted command in 13-03 | ✅ extend | ✅ complete |
| 13-03-02 | 03 | 2 | PAGE-04/PAR-03 | T13-05 | frontend legacy ACL删除 | frontend regression | targeted command in 13-03 | ✅ extend | ✅ complete |
| 13-03-03 | 03 | 2 | PAGE-15/PAR-03 | T13-01 | direct API自提被拒 | E2E | targeted command in 13-03 | ✅ extend | ✅ complete |
| 13-06-01 | 06 | 3 | PAGE-15/PAGE-05/PAR-03 | T13-30/31/32 | root:root 0600、schema、fresh/distinct identity、collision=0、redaction只读取证 | production contract checkpoint | exact SSH stat/hash/schema/property verifier in 13-06 | ➖ remote/manual | ⬜ pending |
| 13-06-02 | 06 | 3 | PAGE-15/PAGE-05/PAR-03 | T13-31 | SUMMARY algorithm/hash机械匹配artifact；mismatch blocking | decision checkpoint | exact expected-algorithm/hash verifier in 13-06 | ➖ remote/manual | ⬜ pending |
| 13-07-01 | 07 | 4 | PAGE-15/PAGE-05/PAR-01/PAR-03 | T13-33/35 | shared username contract唯一owner | service/TDD | plan 13-07 Task1 command | ✅ extend | ⬜ pending |
| 13-07-02 | 07 | 4 | PAGE-15/PAGE-04/PAGE-05/PAR-01/PAR-03 | T13-33/34 | 005+single ACL；permission/role/三env/provider-error不得grant | auth/API/TDD | plan 13-07 Task2 command | ✅ extend | ⬜ pending |
| 13-08-01 | 08 | 5 | PAGE-15/PAR-02/PAR-03 | T13-36/38 | fixed finops:app:view OA selector + APP denied + menu exact set | OA runtime/TDD | plan 13-08 Task1 command | ✅ extend | ⬜ pending |
| 13-08-02 | 08 | 5 | PAGE-15/PAR-01/PAR-03 | T13-36/38 | disabled/missing/drift/timeout runtime compensation fail closed | settings runtime/TDD | plan 13-08 Task2 command | ✅ extend | ⬜ pending |
| 13-10-01 | 10 | 6 | PAGE-15/PAGE-05/PAR-03 | T13-42/44 | fixed-menu只读inventory与secret-safe exact target artifact | deploy collector/TDD | plan 13-10 Task1 command | ✅ extend | ⬜ pending |
| 13-10-02 | 10 | 6 | PAGE-15/PAR-02/PAR-03 | T13-43 | exact non-dedicated cleanup/rollback；无宽删 | SQL/deploy/TDD | plan 13-10 Task2 command | ✅ extend | ⬜ pending |
| 13-10-03 | 10 | 6 | PAGE-15/PAR-03 | T13-42/43 | 三retired env与fixed selector分离、artifact drift零写 | deploy gate/TDD | plan 13-10 Task3 command | ✅ extend | ⬜ pending |
| 13-09-01 | 09 | 7 | PAGE-15/PAGE-04/PAGE-05/PAR-01/PAR-03 | T13-39/40 | backend七类四tier/permission-present 006/direct回归 | backend regression | plan 13-09 Task1 command | ✅ extend | ⬜ pending |
| 13-09-02 | 09 | 7 | 全部 | T13-41/42 | 唯一inventory owner、APP authority零残留与I-O guards | inventory regression | plan 13-09 Task2 command | ✅ extend | ⬜ pending |
| 13-11-01 | 11 | 7 | PAGE-15/PAGE-04/PAR-03 | T13-45/46 | permission-present denied fixtures、direct URL、17-route components | frontend | plan 13-11 Task1 command | ✅ extend | ⬜ pending |
| 13-11-02 | 11 | 7 | PAGE-15/PAGE-04/PAR-03 | T13-45/46 | Browser direct API与四tier业务流 | E2E | plan 13-11 Task2 command | ✅ extend | ⬜ pending |
| 13-04-01 | 04 | 8 | PAGE-15/PAGE-04/PAGE-05/PAR-01 | T13-47 | 全局security/product/API区分APP authority与OA selector | docs | plan 13-04 Task1 docs command | ✅ update | ⬜ pending |
| 13-04-02 | 04 | 8 | PAGE-04/PAGE-05/PAR-03 | T13-48 | app-architecture ownership、direct denial与no-runtime-change | docs/inventory | plan 13-04 Task2 command | ✅ update | ⬜ pending |
| 13-12-01 | 12 | 9 | PAGE-15/PAGE-04/PAR-03 | T13-49/50 | Settings boundary/state-machine | module docs | plan 13-12 Task1 command | ✅ update | ⬜ pending |
| 13-12-02 | 12 | 9 | PAGE-15/PAGE-04/PAR-03 | T13-49 | Settings seven-category/E2E maintenance matrix | module docs | plan 13-12 Task2 command | ✅ update | ⬜ pending |
| 13-12-03 | 12 | 9 | PAGE-15/PAR-01/PAR-03 | T13-49/50 | permissions evaluator/audit boundary | module docs/inventory | plan 13-12 Task3 command | ✅ update | ⬜ pending |
| 13-13-01 | 13 | 10 | PAGE-15/PAGE-05/PAR-02/PAR-03 | T13-51/52 | OA fixed selector/projection/exact cleanup contracts | module docs | plan 13-13 Task1 command | ✅ update | ⬜ pending |
| 13-13-02 | 13 | 10 | PAGE-04/PAR-03 | T13-51 | app-shell fresh router versus APP denial boundary | module docs | plan 13-13 Task2 command | ✅ update | ⬜ pending |
| 13-13-03 | 13 | 10 | PAGE-05/PAR-03 | T13-52 | deploy evidence/cutover/rollback boundary | module docs/inventory | plan 13-13 Task3 command | ✅ update | ⬜ pending |
| 13-14-01 | 14 | 11 | PAGE-15/PAR-02/PAR-03 | T13-53/54/55 | candidate collector/control safe cutover/router/restore | deploy/tool TDD | plan 13-14 Task1 command | ✅ extend | ⬜ pending |
| 13-14-02 | 14 | 11 | PAR-03 | T13-53/55 | canonical zero-reupload activate-existing gate | deploy TDD | plan 13-14 Task2 command | ✅ extend | ⬜ pending |
| 13-14-03 | 14 | 11 | 全部 | T13-41/45/53 | env/assets + seven categories + unique inventory + verify all | regression | plan 13-14 Task3 command | ✅ extend | ⬜ pending |
| 13-15-01 | 15 | 12 | PAR-03 | T13-56/57 | candidate/bootstrap限定批准 | bootstrap checkpoint | targeted evidence + human approval | ✅/manual | ⬜ pending |
| 13-15-02 | 15 | 12 | PAR-03 | T13-53 | no-activate candidate upload；live state不变 | candidate upload | plan 13-15 Task2 command | ➖ remote | ⬜ pending |
| 13-15-03 | 15 | 12 | PAR-03 | T13-56 | hash-pinned atomic helper bootstrap/restore | manual root bootstrap | plan 13-15 Task3 command + human | ➖ remote/manual | ⬜ pending |
| 13-15-04 | 15 | 12 | PAGE-15/PAR-03 | T13-57/58 | remote steady/cutover exact preflight/hash与activation批准；006缺席ACL、DB非partial、env旧态有界 | production checkpoint | plan 13-15 Task4 command + human | ➖ remote/manual | ⬜ pending |
| 13-05-01 | 05 | 13 | PAGE-15/PAR-03 | T13-22/42/43 | JIT selector/menu/exact artifact/fresh identities无漂移 | production gate | explicit SSH command in 13-05 | ➖ remote | ⬜ pending |
| 13-05-02 | 05 | 13 | PAGE-15/PAR-01/PAR-03 | T13-23/24 | activate-existing zero reupload；safe active/API恢复 | production release | canonical command in 13-05 | ✅ extend | ⬜ pending |
| 13-05-03 | 05 | 13 | PAGE-15/PAR-02/PAR-03 | T13-25/26/27 | fresh 005/006、direct API、new router、exact roles与restore | production smoke | explicit SSH command in 13-05 | ➖ remote | ⬜ pending |
| 13-05-04 | 05 | 13 | 全部 | T13-28 | remote artifacts/hash与最终验收 | final checkpoint | explicit SSH command in 13-05 | ➖ remote | ⬜ pending |

## Threat References

| Ref | Threat | Required proof |
| --- | --- | --- |
| T13-01 | full-access 自提/改他人权限 | backend 403/400 + state unchanged + direct API E2E |
| T13-02 | 并发/旧 snapshot 覆盖 ACL、补偿覆盖后续OA或成功无 audit | shared advisory lock/专用guard确定性交错；commit-before-return；finally unlock |
| T13-03 | ordinary settings 缺省/旧字段清空 ACL | strict reject + omission preservation tests |
| T13-04 | OA 与本地 ACL 半同步 | target failure/DB failure/compensation/no-op tests + runbook |
| T13-05 | 删除旧 payload 后关联台/其它页面保存回归 | column-layout/modal/pending rules regression |
| T13-06 | 旧 binary/历史数据重新引入非 protected admin | migration repair + CHECK + deploy/rollback tests |
| T13-30..32 | username contract证据伪造/泄露/碰撞 | root:root 0600、sha/schema/property/redaction、fresh distinct hashes |
| T13-33..35 | permission/role/env授权或normalization漂移 | ACL-only evaluator、fixed selector separation、collision reject |
| T13-36/38 | OA runtime投影漂移/失败假成功 | menu exact set、typed failure、existing compensation |
| T13-42..44 | selector误接、宽删、evidence泄露 | OA-only allowlist、exact targets/before-image、salted hashes |
| T13-45..52 | frontend fixture或长期docs责任漂移 | split frontend tests、three focused docs plans、unique inventory rerun |
| T13-53..58 | candidate/bootstrap/approval tampering或secret泄露 | fingerprints、zero-reupload、atomic helper restore、stdin/redaction、two approvals |

## Wave 0 Requirements

- [x] 0132 migration repair/audit/CHECK tests已由13-01完成。
- [x] repository/local-store CAS、generic-preserve-ACL、audit rollback/no-op tests已由13-01完成。
- [x] API/session/direct attack合同已由13-02完成。
- [x] frontend与Playwright dedicated ACL入口已由13-03完成。

现有测试框架足够，不安装依赖、不增加测试框架。

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OA username comparison contract | PAGE-15/PAR-03 | 目标OA collation/API身份不可本地猜测 | 13-06只读采集；自动校验owner/mode/schema/fresh distinct hashes/collision/redaction，再机械锁定算法 |
| 真实 OA 三角色同步 | PAR-02/PAR-03 | local executor/mock不能证明production MySQL角色事实 | 13-15 production只读preflight盘点；13-05批准后由admin对专用bearer账号full→read→denied逐档验证并finally恢复/read-back |
| 生产历史非法 admin 清理 | PAR-01/PAR-03 | 生产数据不应进入普通测试 | 双token stdin root-owned preflight生成artifact/hash；用户确认后13-05通过canonical deploy应用migration |
| 生产延迟采样 | PAR-02 | 不编造 SLO | 记录 generic save、ACL GET、ACL no-op/real PUT 的 p50/p95 与 OA/DB 分段，不输出 token/secret |
| 安全cutover/回滚 | PAR-03 | 涉及live API/migration/OA | deterministic deploy tests锁定 current pre→exact env cleanup/strict→OA cleanup→quiesce/migration 顺序及进入activation前env restore；production capability/fingerprint拒绝unsafe previous；任何rollback/maintenance/repair均blocked并重启审批链 |
| 正式生产发布 | 全部 | 必须用户明确授权外部写入 | 13-15两级批准完成后，13-05运行`./scripts/deploy-oa.sh --activate-existing --release-name <release>`；仅zero-reupload safe active+API恢复可进入post-deploy |

## PLAN-CHECK Revision Background

- Revision 2机械拆分：13-09只拥有backend+唯一inventory，13-11拥有frontend/E2E；原13-04拆为13-04全局docs、13-12 Settings/permissions docs、13-13 OA/app-shell/deploy docs、13-14 release preparation、13-15 candidate/bootstrap/preflight approvals。13-05保持完整生产原子序列，所有active retry gate均指向13-15 Task4。

- Iteration 1/3针对`13-PLAN-CHECK.md` B-01..B-08修订。
- Wave 0不再包含预期非零的test-only RED gate；所有`<automated>`命令在所属task完成时预期exit 0。
- production closure拆为13-04只读preflight/准备与13-05批准后发布/证据，approval本身不再等于完成。
- deploy gate新增API quiesce、ACL-safe capability/fingerprint与maintenance/forward-repair；request ID由http adapter生成并绑定audit=response。
- B-06 backend callers与`PendingInvoicesApi.test.ts`已明确归属，禁止legacy兼容。
- Iteration 2/3按P-01..P-05收紧：ACL专用shared-advisory-lock guard；API contract harness/response fixture sentinel；外部事实只由production gates证明；双HTTP token identity/hash/逐档恢复协议；canonical deploy参数与blocked失败状态。
- 所有task完成gate仍预期exit0；13-05 Task2任何非零、safe rollback、maintenance或forward repair均不算done；Revision 2拆分后，repair必须回当前13-15 Task4重新取证/批准，再重跑13-05 Task1/2（该规则继承原13-04 Task7的历史语义）。
- Iteration 3/3新增两级production批准与explicit SSH remote artifact边界；unknown COMMIT使用fresh-lock/mutation-id proof；OA read/write timeout固定为10秒；final activation仅`--activate-existing`。
- Final adjudication关闭剩余执行缺口：首次production helper bootstrap改为单独批准的manual-root同文件系统原子替换，明确禁止legacy self-update及runtime-worker helper变化；`settings-acl-postgres`在缺disposable DB或lost-ACK测试skip时fail closed。

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency is bounded by per-task targeted commands
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** completed 13-01..03 evidence retained；Revision 2 planning self-check pending independent checker re-run，13-06..15/04/05 implementation、external evidence、bootstrap、activation与production sign-off均pending。

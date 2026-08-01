## ISSUES FOUND

**Checked:** 2026-08-01T18:58:54Z
**Scope:** `13-01-PLAN.md` through `13-04-PLAN.md`, goal-backward against Phase 13 context/research/validation/patterns, repository instructions, current code and deploy entrypoints.
**Requirement IDs:** PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03 are all present across plan frontmatter, but the blockers below prevent the plans from achieving the stated production T0-01 goal.

### BLOCKER B-01 — ROADMAP still defines an analysis-only phase with zero plans

**Plan/task:** Planning metadata before `13-01`; affects all plans.
**Evidence:** `.planning/ROADMAP.md:258-274` still defines Phase 13 as “分析现状、风险、功能缺口和实施计划”, limits success criteria to phase-directory analysis, and says `Plans: 0 plans` / `TBD`. The submitted plans instead implement and release a production security change. None of the four plans owns a ROADMAP correction. This leaves the authoritative goal and completion contract inconsistent with the requested goal, and downstream GSD status/requirement accounting can complete the wrong phase.
**Required revision:** Before execution, update the Phase 13 ROADMAP entry to the locked T0-01 production goal, D-01–D-19-derived success criteria, `Plans: 4 plans`, and the four plan checklist entries. Keep PAGE-15/PAGE-04/PAGE-05/PAR-01/PAR-02/PAR-03 mapped, but make it explicit that the reviewed security goal—not the old analysis-only text—is the phase completion contract.

### BLOCKER B-02 — The plan stops at approval; it never performs or verifies the production release

**Plan/task:** `13-04`, Task 4 and plan output (`13-04-PLAN.md:149-158, 229-230`).
**Evidence:** Task 4 ends when the user approves the dry-run; there is no subsequent task that invokes the canonical production entrypoint `./scripts/deploy-oa.sh`, applies 0132, activates the safe binary, or executes D-18 post-deploy admin/full/read/denied, generic-save, manual-escalation, AppHealth, OA-credential and data-reset checks. The output explicitly says this plan performs no production writes. Approval alone cannot satisfy the stated “生产级关闭” goal or D-18’s “发布后必须验证”.
**Required revision:** Add a post-approval wave (either Tasks 5-6 in `13-04` or a new `13-05` depending on `13-04`) with: (1) a blocking human-action task that runs the reviewed release through `./scripts/deploy-oa.sh`; (2) an automated/read-only post-deploy verification task covering the complete D-18 role/API/OA matrix and evidence capture; (3) explicit rollback/forward-repair criteria; and (4) a final checkpoint that marks the phase complete only after production evidence passes. Update `must_haves`, `<verification>`, `<success_criteria>`, VALIDATION task rows and artifacts accordingly.

### BLOCKER B-03 — The proposed migration/activation order leaves the vulnerable API live and current automatic rollback can restore it

**Plan/task:** `13-04`, Task 2 / threats T13-06 and T13-13 (`13-04-PLAN.md:123-134, 177-179`).
**Evidence:** The plan requires `preflight -> 0132 migration -> safe binary activation`, but does not require API quiescence. Current `activate_release()` only stops runtime workers, then runs migrations before writing the candidate API drop-in and restarting services (`deploy/oa/bin/finops-deploy-control.sh:1494-1505`). During that interval the old generic ACL endpoint remains live; 0132’s protected-admin CHECK does not prevent the old endpoint from changing other users’ full/read/denied tiers or issuing its pre-commit OA sync. Current release-gate failures also automatically call `rollback_release_gate()` (`deploy/oa/bin/finops-deploy-control.sh:1948-1960`), which can reactivate the exact vulnerable previous binary. Narrative statements that vulnerable rollback is forbidden do not mitigate either executable path.
**Required revision:** Make Task 2 specify and test an atomic fail-closed cutover: quiesce the API before 0132, keep it quiesced until the ACL-safe binary is installed and ready, then run post-activation checks. Add a machine-verifiable release capability/fingerprint so rollback accepts only an ACL-safe release; if no safe previous release exists, remain in maintenance/fail-closed mode and require forward repair rather than restarting the vulnerable binary. Extend `tests/test_deploy_oa_script.py` to assert `API quiesce -> migration/CHECK validation -> candidate activation -> role/API smoke`, and assert every failure branch refuses an unsafe previous release.

### BLOCKER B-04 — The production preflight checkpoint command cannot access the production facts it claims to review

**Plan/task:** `13-04`, Tasks 2 and 4 (`13-04-PLAN.md:120-135, 149-155`).
**Evidence:** Task 2 says the CLI is integrated into `finops-deploy-control`, but defines no concrete deploy-control command. Task 4’s automated command is only `PYTHONPATH=backend/src python3 -m ... --dry-run --json`, which runs locally. `scripts/with-production-admin-token.sh` loads only HTTP admin-token variables (`scripts/with-production-admin-token.sh:36-40, 46-68`); it does not load the root-owned PostgreSQL migrator or OA MySQL environment needed to inventory DB/env/OA. Therefore the required three-source production evidence is not executable as written.
**Required revision:** Define an exact read-only candidate-release subcommand such as `finops-deploy-control settings-access-control-preflight <release> --dry-run --json`, executed server-side through the existing root-owned runtime/migrator/OA env loaders and restricted to read-only SQL/OA queries. Make the user checkpoint invoke that remote command through the canonical deploy workflow, identify the evidence artifact path/hash, and add tests proving no DML/OA mutation and complete redaction. Keep the token wrapper only for HTTP smoke; do not describe it as the DB/OA credential loader.

### BLOCKER B-05 — Durable audit cannot receive the server-generated request ID with the planned file scope

**Plan/task:** `13-02`, Tasks 1-2 (`13-02-PLAN.md:9-25, 51-56, 93-125`).
**Evidence:** D-11 requires the committed durable audit to contain the trace/request ID. The plan says the route passes a trusted request trace, but does not include `backend/src/fin_ops_platform/app/http_adapter.py` or `tests/test_http_adapter.py`. Today `WsgiHttpAdapter` generates the authoritative ID (`http_adapter.py:57`) and adds it to the response (`:63`), but `_dispatch()` calls `Application.handle_request(...)` without forwarding it (`:94-104`). Settings routing therefore cannot audit the same server-generated ID; reading an inbound header would also permit client spoofing. No planned test binds the durable audit ID to the response `X-Request-ID`.
**Required revision:** Add `app/http_adapter.py` and `tests/test_http_adapter.py` to `13-02` scope. Propagate the adapter-generated ID through a trusted internal request context (or overwrite an internal-only forwarded header before dispatch), pass it route -> service -> repository audit, and never accept a body actor/trace. Add tests proving a spoofed inbound request ID cannot replace the server ID and that the committed `audit.events` metadata request ID equals the response `X-Request-ID`; failure/no-op/conflict must leave no success audit.

### BLOCKER B-06 — Removing the legacy ACL API/provider signatures will break unowned tests and leave prohibited env/dynamic-admin paths behind

**Plan/task:** `13-02` Task 3 and `13-03` Tasks 2-3 (`13-02-PLAN.md:129-143`; `13-03-PLAN.md:108-140`).
**Evidence:** The plans promise whole-repo deletion and `verify.sh all`, but their `files_modified`/task file lists omit active callers and fixtures. Examples: `tests/test_app_health_api.py:720-1132` repeatedly grants admin through `FIN_OPS_ADMIN_USERNAMES`; `tests/test_etc_invoice_pdf_bundle_service.py:193` and `tests/test_etc_backend.py:3772` inject `dynamic_admin_usernames_provider`; multiple regression tests still call `update_settings(... admin_usernames=...)`, including `tests/test_bank_auto_tag_rules_api.py:1478`, `tests/test_pending_invoice_api.py:371`, `tests/test_oa_pending_payment_api.py:315`, `tests/test_workbench_v2_api.py:1193`, `tests/test_batch_accounting_api.py:671`, `tests/test_turnover_ledger_api.py:3386`, and `tests/test_tax_offset_api.py:84`. `web/src/test/PendingInvoicesApi.test.ts:873` still embeds generic `access_control`. These are neither rejection nor migration/rollback fixtures. Deleting the signatures/providers in Plan 02 will make the full suite fail or tempt an executor to retain forbidden compatibility branches.
**Required revision:** Expand the owning task/frontmatter file lists and remove/update every runtime-style legacy caller found by the deletion sentinel. At minimum include: `tests/test_app_health_api.py`, `tests/test_app_postgres_mode.py`, `tests/test_bank_auto_tag_rules_api.py`, `tests/test_batch_accounting_api.py`, `tests/test_etc_backend.py`, `tests/test_etc_invoice_pdf_bundle_service.py`, `tests/test_oa_manual_import_api.py`, `tests/test_oa_pending_payment_api.py`, `tests/test_pending_invoice_api.py`, `tests/test_postgres_state_store_integration.py`, `tests/test_tax_offset_api.py`, `tests/test_turnover_ledger_api.py`, `tests/test_workbench_dirty_queue_wiring.py`, `tests/test_workbench_v2_api.py`, and `web/src/test/PendingInvoicesApi.test.ts`. Replace env/dynamic-admin seeding with the protected-admin identity or dedicated ACL test command; remove generic ACL payloads rather than preserving compatibility. Add these suites to the targeted verification before `verify.sh all`.

### BLOCKER B-07 — Wave 0 cannot complete because its required verifier is intentionally red until Wave 1

**Plan/task:** `13-01`, Task 1 and plan verification (`13-01-PLAN.md:73-87, 147-150`).
**Evidence:** Task 1 is test-only, explicitly forbids changing implementation, and requires tests that fail against the old implementation. Its `<automated>` verifier runs those tests normally and therefore exits non-zero. The plan-level Wave 0 verification runs the same still-red suite, yet `13-02` cannot start until `13-01` completes. This makes the dependency/wave graph non-executable under the normal execute-plan rule that a task’s automated verification must pass.
**Required revision:** Keep RED and GREEN inside the same TDD implementation task: move the API/session attack tests into `13-02` Task 1, run them first to record the expected RED evidence, implement the boundary, then require the normal command to pass. Leave `13-01` with migration/repository contracts that can finish green, or define a workflow-supported non-gating RED evidence step distinct from `<automated>` verification. Update 13-VALIDATION rows/status so every gating command is expected to exit zero.

### BLOCKER B-08 — Plan 04 targets two nonexistent, unindexed documentation files

**Plan/task:** `13-04`, Task 1 (`13-04-PLAN.md:11-28, 109-117`).
**Evidence:** `docs/app-architecture/business-flows-settings.md` and `docs/dev/api.md` do not exist. The current indexed fact sources are `docs/app-architecture/pages.md`, `docs/app-architecture/runtime-and-ownership.md`, and `docs/dev/api-contracts.md`; `docs/dev/index.md` explicitly points to `api-contracts.md`. Creating the two planned paths would introduce unindexed parallel facts and violate the repository’s no-duplicate-doc/source-of-truth rules.
**Required revision:** Replace `docs/app-architecture/business-flows-settings.md` with the existing relevant app-architecture owners (`pages.md` and, for request/runtime flow, `runtime-and-ownership.md`), and replace `docs/dev/api.md` with `docs/dev/api-contracts.md` in frontmatter, Task 1 files/action, must-have artifacts and verification. Only create a new document if the plan also justifies it and updates the corresponding index; no such need is shown here.

## Checks that passed

- All four plan frontmatters are parseable and their dependency/wave ordering is acyclic (`01 -> 02 -> 03 -> 04`).
- PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02 and PAR-03 are collectively listed.
- The plans explicitly cover `WorkbenchSettingsModal`, Reconciliation column reorder, pending-invoice fallback, deterministic component/E2E mocks, runtime admin env retirement, generic-writer ACL preservation, CAS/durable audit/OA compensation, seven test categories and a human production checkpoint.
- Each plan has an ASVS L1/STRIDE threat model, and the narrative mitigations name all HIGH threats; B-02 through B-05 identify where those HIGH mitigations are not yet executable.
- No business source file was modified and no commit was created by this check.

## Revision Iteration 1/3 Background

Planner revision已针对B-01..B-08更新磁盘规划，供下一次checker重新验证；本节不自行覆盖原blocker verdict：

- B-01：ROADMAP Phase 13改为T0-01生产修复目标、6条成功标准与13-01..13-05最终列表，requirements映射保留。
- B-02：新增13-05 Wave 4，包含preflight hash复核/用户批准、`./scripts/deploy-oa.sh`正式发布、D-18 post-deploy artifact及最终checkpoint。
- B-03：13-04要求API quiesce→migration/CHECK→safe candidate→smoke，并以ACL-safe capability/fingerprint拒绝unsafe rollback；无safe previous时maintenance+forward repair。
- B-04：13-04定义root-owned `finops-deploy-control settings-access-control-preflight <release> --dry-run --json`、固定artifact/hash路径及server-side DB/OA env；HTTP token wrapper不再承担DB/OA加载。
- B-05：13-02纳入`http_adapter.py`/`test_http_adapter.py`，要求server-generated request ID不可spoof且audit ID=response `X-Request-ID`。
- B-06：13-02纳入checker列出的全部backend callers/tests并要求fixed admin或dedicated ACL test command；13-03纳入`PendingInvoicesApi.test.ts`与frontend fixtures，禁止兼容。
- B-07：13-01删除test-only RED gate，仅保留本plan可GREEN的migration/repository/local-store tasks；API/session RED→GREEN并入13-02 Task1；VALIDATION同步。
- B-08：13-04文档路径改为`docs/business-flows/settings.md`、`docs/app-architecture/pages.md`、`docs/app-architecture/runtime-and-ownership.md`、`docs/dev/api-contracts.md`。

所有修改仅涉及planning artifacts；未修改业务代码、未执行生产命令、未提交。

## Revision Iteration 2/3 Background

以下为planner针对独立checker P-01..P-05的磁盘修订映射，不自行声明原verdict已PASS：

- P-01：13-01/13-02固定ACL专用、非通用UoW critical-section port；ACL/generic共享固定session advisory lock，guard内stale/no-op、bounded OA target、commit-before-return与锁内补偿，并以确定性双并发/finally unlock证明最终settings/audit/OA一致。
- P-02：13-02纳入`tests/test_read_model_api_contract_harness.py`的frontmatter、Task 1/3及target verifier；whole-repo sentinel覆盖signature、response shape、fixture key和API contract harness。
- P-03：ROADMAP、13-04和VALIDATION删除必需staging完成条件；Wave 3只要求local/candidate deterministic回归与可测I/O计数，外部事实仅来自production只读preflight及13-05批准后post-deploy。
- P-04：13-04/13-05复用现有admin与bearer secret inputs及同一0600 env，经stdin仅用于真实HTTP `/api/session/me`/smoke；preflight绑定approved username hashes/initial tier，post-deploy对同一专用账号full→read→denied逐档验证并finally restore/read-back，tests覆盖缺失/过期/错误身份或tier/同身份/非专用/redaction/用途隔离。
- P-05：iteration 2已建立canonical deploy与blocked失败语义；最终命令参数由下方Iteration 3的candidate-bootstrap/activate-existing协议取代。Task 2仍仅在safe candidate active、API恢复及fingerprint有效时done。

本轮仍仅修改planning artifacts；未执行production命令、未修改业务代码、未提交。

## Revision Iteration 3/3 Background

以下映射独立checker C-01..C-03的最终planner修订，不自行伪造PASS：

- C-01（iteration-3当时方案，已被下方Final Root Adjudication取代）：当时曾规划`--no-activate`后调用helper self-update；最终审阅证明首次安装不能依赖legacy self-update，现行唯一方案以下方manual-root hash-pinned原子替换/恢复为准。
- C-02：13-01/02区分known rollback与COMMIT outcome unknown；unknown使用fresh connection重取同一advisory lock，以server mutation_id audit和canonical version/ACL三分支判定，later/mismatch不覆盖OA并报inconsistent；真实PG lost-ack/intervening-writer integration test纳入verifier。
- C-03：13-02扩展现有OA settings/executor，connect默认5秒、read/write各默认10秒并直接传PyMySQL；测试覆盖timeout映射、target零DB、compensation inconsistent及guard/recovery unlock，无detached thread。

仍仅修改planning artifacts；未执行bootstrap/preflight/activation或任何production mutation，未修改业务代码，未提交。

## Final Root Adjudication After Iteration 3/3

最终独立checker仍发现两项执行级缺口，主审只修订planning artifacts，不伪造新的checker PASS：

- C-01 bootstrap-of-bootstrap：当前live helper的legacy `self-update`会直接覆盖自身且同时更新runtime-worker helper，candidate代码无法倒推保证首次安装安全。13-04现改为：用户先批准candidate upload与精确manual-root runbook；`--no-activate`只上传/check；root操作员以同文件系统root-owned temp、approved sha256、`bash -n`、candidate contract prevalidation、`mv -f`原子替换和失败原子恢复完成一次性bootstrap。全过程禁止legacy self-update，runtime-worker helper、active release、API、DB、OA、ACL必须不变。
- C-02 skipped real-PG gate：13-02新增`bash scripts/verify.sh settings-acl-postgres`专用fail-closed target。缺少visibly disposable `FIN_OPS_TEST_DATABASE_URL`时exit 2；它设置require标志并只运行精确lost-COMMIT-ack integration test，任何Skip/未执行均nonzero，不能再以unittest suite exit0冒充真实PostgreSQL证据。

本段是三轮checker之后的主审裁决记录；最终交付仍需机械schema/coverage/consistency检查通过。未修改业务代码、未执行外部命令、未提交。

## FINAL CHECK PASSED

**Final checked:** 2026-08-02
**Verdict:** `13-01`～`13-05` 可作为 T0-01 的生产级执行计划；此前 B-01..B-08、P-01..P-05、C-01..C-03 均已关闭。

- 五份PLAN frontmatter全部通过GSD schema；task开闭数量为`2 / 3 / 3 / 7 / 4`，依赖DAG为`13-01 → 13-02 → 13-03 → 13-04 → 13-05`。
- PAGE-15、PAGE-04、PAGE-05、PAR-01、PAR-02、PAR-03 gap analysis全部covered；ROADMAP consistency通过。
- 首次production helper bootstrap最终使用单独批准的manual-root hash-pinned同文件系统原子替换/恢复，禁止legacy self-update且runtime-worker helper不变；失败恢复通过`root:root 0755` rollback temp预验证后atomic move，不会恢复出不可执行helper。
- `settings-acl-postgres`对真实lost-COMMIT-ack测试fail closed：缺disposable DB、skip或未执行均nonzero。
- 最终独立复核已确认上述最后两项关闭。当前未执行任何实现、bootstrap、preflight、deployment或production mutation。

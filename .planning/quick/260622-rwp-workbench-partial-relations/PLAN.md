---
phase: quick
plan: 260622-rwp-workbench-partial-relations
type: repair-plan
wave: 1
depends_on:
  - .planning/debug/reconciliation-two-pane-paired.md
autonomous: false
requirements:
  - Two-pane relations remain valid canonical relation facts.
  - Ordinary two-pane relations stay in the open/unpaired Workbench zone.
  - Only three-pane completed relations enter the paired Workbench zone, except explicit business exceptions.
status: implemented-verified
---

# 260622-rwp - 关联台两栏关系留未配对、三栏闭环进已配对修复计划

## Objective

修复关联台 paired/open 分区语义：允许任意两栏确认并写入 canonical active relation，用于 row ownership、撤回、审计和下游 relation distribution；但普通两栏 relation 只表示 partial relation，必须留在未配对/open 区等待第三栏补齐。只有 OA + 银行 + 发票三栏完整闭环，或明确业务例外，才能进入已配对/paired 区。

本计划最初只制定修复方案；2026-06-22 已按 `GOAL_PROMPT.md` 执行实现、文档和验证。

## Architecture Constraints

- `app.workbench_pair_relations` 继续是 confirmed relation fact，不因两栏未闭环而删除或降级为 candidate。
- Workbench active generation 继续是关联台展示事实源；修复必须在后端 active generation/grouping 分区完成，前端不能本地把 paired 行搬到 open。
- `workbench_relation` distribution 继续向下游页面表达 `linked` relation；两栏 active relation 对下游仍可表示“已建立关系/row 已占用”，但关联台页面展示区应区分 partial/open 与 completed/paired。
- 写入口仍走 `WorkbenchRelationCommandService`，保留权限、幂等、version conflict、row occupation、history、affected months 和 durable refresh queue。
- read model refresh 仍通过现有 `workbench` active generation、`workbench_relation`、dirty scope/outbox 和 operation barrier 收敛；不能绕过 freshness gate 或写 Redis 假 fresh。
- `server.py` 只做 route/依赖组装/HTTP mapping 的长期方向不变；本轮若必须触碰 legacy wiring，只做最小门槛或委托策略，不扩展业务逻辑。

## Product Rule

### 普通规则

- OA + 银行：允许确认，写 active relation，显示在 open 区，文案/标签表达“已关联流水，待补发票”。
- OA + 发票：允许确认，写 active relation，显示在 open 区，表达“已关联发票，待补流水”。
- 银行 + 发票：允许确认，写 active relation，显示在 open 区，表达“已关联发票，待补 OA”。
- OA + 银行 + 发票：进入 paired 区，表达“完全关联”。
- automatic decision 两栏继续是候选/open，不写 active relation。

### Paired 例外白名单

实现前必须把例外做成显式 policy，而不是继续依赖 `row_type_count >= 2` 的宽泛判断。建议首批保留：

- `no_oa_bank_batch`：免 OA 批次和内部转账。
- `salary_personal_auto_match`：单银行工资/个人自动闭合。
- `internal_transfer_pair`：多银行内部往来闭合。
- `personal_advance_repayment_settlement`：个人暂借款还清 special relation。
- `oa_invoice_offset_auto_match`：OA 附件发票冲抵。
- `batch_accounting`：批量账务 OA + 银行关系，按现有业务例外保持 paired。
- ETC summary / ETC batch relation：已有 ETC summary 或 relation metadata 补齐展示闭环时保持 paired。
- `processed_exception` / closed exception projection。

`turnover_manual_closure` 已按当前架构收紧：bank-only 或 OA+bank 留 open，三栏完整才 paired；不得回退。

## Planned Changes

### Task 1 - Introduce Explicit Zone Policy

Files:

- `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`
- Optional small helper module only if it reduces duplication and keeps boundaries clear.

Plan:

- Replace the broad rule `row_type_count >= 2 and _is_confirmed_active_relation_group(group)` with an explicit decision:
  - three-pane groups are paired when confirmed or valid automatic completed decision.
  - one/two-pane groups are paired only when their relation code/mode/metadata matches the exception whitelist.
  - ordinary `manual_confirmed` one/two-pane groups are valid active relation display groups but belong to open.
- Preserve canonical `case:<case_id>` group id and relation metadata when demoting ordinary two-pane active relation to open.
- Ensure demoted rows keep enough relation evidence for UI chips and withdraw preview: `case_id`, `relation_mode`, relation payload, `special_metadata`, amount check where present.
- Do not change row occupation, relation service, history or source data.

Acceptance criteria:

- Ordinary `manual_confirmed` OA+bank, OA+invoice, bank+invoice groups appear in `open.groups`.
- Same rows keep one canonical `case:<case_id>` group and remain selectable as one group.
- Three-pane `manual_confirmed` groups remain in `paired.groups`.
- Existing exception groups remain in paired according to whitelist.

### Task 2 - Preserve Confirm-Link Write Semantics

Files:

- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/app/server.py` only if preview/copy or row-type gate needs minimal adjustment.
- Existing API contract docs if response semantics are clarified.

Plan:

- Keep `_can_confirm_link_row_types(...)` accepting any two known row types; this is required by the new rule.
- Keep `confirm_link` writing `relation_mode="manual_confirmed"` through `WorkbenchRelationCommandService`.
- Review `preview_confirm_link` and `_confirm_link_operation_projection(...)`: if operation projection currently emits only `paired_groups`, adjust it to report open partial groups for ordinary two-pane relation while preserving paired projection for three-pane/exception groups.
- Do not make write success wait for full `workbench:all`; continue using operation-level freshness barrier and current Workbench fresh refetch behavior.

Acceptance criteria:

- Two-pane confirm succeeds and returns active relation metadata.
- UI does not optimistically move ordinary two-pane relation to paired during preview submit/projection.
- Existing idempotency, note-required amount mismatch, conflict and active-row occupation behavior are unchanged.

### Task 3 - SQL Active Generation and All-Scope Consistency

Files:

- `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py` only if all-scope owner suppression or consistency checks assume active relation always means paired zone.

Plan:

- Keep SQL projection applying active relation metadata before grouping.
- Let grouping decide zone from explicit zone policy.
- Audit all-scope aggregation logic for assumptions that canonical active relation occupied rows must be in paired zone. Legal active relation owners may now be open canonical `case:<case_id>` groups when partial.
- Preserve suppression of duplicate temp/candidate/standalone owners for rows occupied by active relation; the visible owner should be the canonical open `case:<case_id>` group, not a temp group.

Acceptance criteria:

- Month and all-scope active generation publish one visible owner per row.
- Partial active relation rows do not leak into standalone/candidate duplicates.
- Generation consistency treats canonical open `case:<case_id>` partial active relation as legal, not failed.

### Task 4 - Frontend State and Copy Audit

Files:

- `web/src/features/workbench/api.ts`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/components/workbench/*`
- `web/src/test/WorkbenchSelection.test.tsx`
- `web/src/test/WorkbenchApi.test.ts`

Plan:

- Prefer no broad UI rewrite. The page should render whatever backend places in `open.groups`.
- Verify open-zone groups with `relationMode="manual_confirmed"` still show complete group selection and the unified withdraw/split button resolves to `withdraw_relation`, not `split_candidate`.
- If existing copy says open groups are “未关联”, adjust only user-visible labels that would become misleading; use “未闭环/待补齐” semantics in status chips or preview copy where needed.
- Do not introduce frontend local pairing rules.

Acceptance criteria:

- Two-pane active relation in open zone can be selected as one group and withdrawn through canonical relation preview.
- Open zone can display relation chips without implying full paired completion.
- No regression in existing stale/refreshing, permission, selection, drawer and operation barrier flows.

### Task 5 - Tests

Backend unit/service tests:

- Reverse `tests/test_workbench_candidate_grouping.py::test_keeps_confirmed_active_oa_bank_relation_without_invoice_in_paired_section` into ordinary manual two-pane active relation stays open.
- Add explicit ordinary OA+invoice and bank+invoice active relation stays open cases.
- Keep `test_demotes_existing_two_type_case_id_rows_back_to_open_section` as display-pollution negative regression.
- Add or update three-pane `manual_confirmed` remains paired.
- Keep/expand exception whitelist tests:
  - no-OA batch paired.
  - batch accounting OA+bank paired.
  - personal advance repayment settlement paired.
  - OA invoice offset paired.
  - turnover two-pane open, turnover three-pane paired.

SQL/read model tests:

- Add `WorkbenchSqlRuntimeTests` case for ordinary `manual_confirmed` OA+bank active relation publishing canonical open group.
- Add all-scope test preserving canonical open `case:<case_id>` owner while suppressing temp/standalone duplicates.
- Keep batch accounting and no-OA paired tests unchanged.

API/contract tests:

- Add/adjust Workbench API test showing confirm-link two-pane still succeeds, but refreshed Workbench payload places the group in open.
- Confirm already-active partial relation preview returns withdraw preview, not split candidate.
- Confirm operation projection, if present, uses `open_groups` for ordinary partial relation.

Frontend tests:

- Update `WorkbenchApi.test.ts` mapper expectations for open manual partial relation.
- Update `WorkbenchSelection.test.tsx` to select open partial active relation and verify withdraw relation preview path.

Seven-category test assessment:

- Business core unit tests: applies. Zone policy, relation completeness and whitelist decisions are business rules.
- Service-layer tests: applies. Workbench write facade, command-service interaction and operation projection can be affected.
- API contract tests: applies. confirm/preview and `/api/workbench` zone payload shape/semantics change.
- Read model/cache/background tests: applies. Workbench active generation and all-scope owner consistency are affected.
- Frontend component/interaction tests: applies. Open-zone partial active relation selection and preview behavior are user-visible.
- End-to-end business-flow integration tests: applies. At least one confirm two-pane -> barrier/fresh refetch -> open partial group, then add third pane or withdraw path should be covered by existing deterministic e2e or targeted integration.
- Existing feature regression tests: applies. no-OA, batch accounting, turnover, automatic decision, stale/refreshing and permissions must remain protected.

### Task 6 - Docs Impact

Files:

- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/state-machine.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/reconciliation-workbench/implementation-notes.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/dev/api-contracts.md` only if preview/projection contract fields change.
- `docs/app-architecture/runtime-and-ownership.md` only if operation barrier or read model ownership semantics change.

Plan:

- Update current boundary: two-pane active relation is confirmed fact but open-zone partial display.
- Remove/replace the 2026-06-21 note that active relation ownership overrides three-pane display completeness for ordinary `manual_confirmed`.
- Add explicit exception whitelist and owner responsibilities.
- Update test matrix and verification commands.
- Avoid raw prompt; record only decisions, acceptance criteria and risks.

## Verification Commands

Focused backend:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_candidate_grouping tests.test_workbench_turnover_grouping -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_sql_projection_keeps_active_batch_accounting_oa_bank_relation_paired tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_sql_projection_keeps_turnover_manual_closure_bank_only_case_open_until_three_way_complete -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v
```

Focused frontend:

```bash
cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/WorkbenchSelection.test.tsx src/test/CandidateGroupGrid.test.tsx
```

Docs:

```bash
bash scripts/verify.sh docs
```

Escalate to broader verification before merge if zone policy touches all-scope aggregation or operation projection:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime tests.test_workbench_auth_context_idempotency tests.test_workbench_relation_command_service -v
cd web && npm run build
```

## Rollout and Data Notes

- Existing production `app.workbench_pair_relations` rows do not need migration solely for this display fix; after Workbench month/all active generation rebuild, ordinary two-pane active relations should move to open as canonical partial groups.
- If production currently has stale active generations, enqueue/rebuild affected Workbench month scopes and aggregate `all` after deploy.
- Run read-only display audit after rebuild to ensure active relation rows have one visible canonical owner and no duplicate temp/candidate owner.
- If downstream pages rely on `workbench_relation` linked status for two-pane facts, keep that behavior; this plan changes Workbench zone completion, not relation fact validity.

## Risks and Decisions Needed

- Need final confirmation of exception whitelist before implementation. The riskiest entries are `personal_advance_repayment_settlement`, `oa_invoice_offset_auto_match`, and ETC-related modes because they are not always literally three-pane but may represent completed special workflows.
- Product copy may need “未配对” to be understood as “未三栏闭环”; otherwise users may be confused by open-zone rows that already show relation chips.
- Operation projection may be the hidden regression point: if confirm-link returns `paired_groups` for two-pane, the UI could briefly show paired until fresh refetch. This must be tested.
- All-scope consistency checks may currently equate active relation occupancy with paired-zone ownership. Partial active relations need canonical open ownership without being marked inconsistent.

## Success Criteria

- Ordinary two-pane confirmed relations are allowed, auditable, withdrawable and row-exclusive.
- Ordinary two-pane confirmed relations appear only in open/unpaired zone as partial canonical groups.
- Three-pane confirmed relations appear in paired zone.
- Exception workflows retain their existing intended paired/open behavior.
- No duplicate row owner appears across open/paired after month or all-scope publish.
- Confirm/withdraw operation barriers and fresh refetch behavior remain intact.

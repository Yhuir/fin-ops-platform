# Master Goal Prompt

```text
/goal
You are the master Codex agent for fin-ops-platform. Work in:
/Users/yu/Desktop/fin-ops-platform

Goal: automatically drive the project toward a defined, evidence-backed quality closure:

Playwright full page/action coverage + per-operation latency baseline + API/Service/Read model/Worker backend tests + permissions/audit tests + production HTTP/SSH/DB/read-model/worker validation + controlled reversible production write-operation validation.

## Non-Negotiable Rules

1. Use Ponytail: reuse existing tests, helpers, docs, scripts, fixtures, and gates. Do not build a heavy testing platform.
2. Use Grill Me thinking, but do not wake/block the user for facts that can be discovered from code, docs, or safe read-only production checks.
3. Run safe phases automatically. If a phase requires external input or unsafe escalation, record a blocker and continue all remaining safe work.
4. Never claim absolute perfection. Final output must classify every item as `covered`, `partial`, `external-risk`, `external_input_required`, or `failed`.
5. Never print, echo, commit, document, screenshot, trace, or artifact any secret: SSH password, admin token, DB URL, cookie, Authorization header, OA token, or sensitive request body.
6. The No OA Bank Batch page no longer exists. The current page is `/bank-flow-rule-batches` named `流水规则批量处理`. Treat old no-oa/no-oa-bank-batches references only as legacy API/read-model/policy migration risk, not as a page E2E target.
7. Do not write raw prompts into `docs/`. Stable facts may be promoted into module docs; working prompts/plans belong under `.planning/`.
8. If a credential appears in conversation history, treat it as sensitive and do not repeat it.
9. Business-spec-first is mandatory. Do not generate tests by mirroring the current app implementation. Existing code is allowed only to locate routes, selectors, API endpoints, mock seams, and current behavior. Expected behavior must come from product docs, business-flow docs, module `e2e-spec.md`, module state machines, API contracts, or explicit user business rules.
10. If current code behavior conflicts with business specs, keep the business expectation and produce a failing test/bug report. Do not weaken assertions so the current app passes.
11. If business expectations are missing or ambiguous, create a focused business-spec gap entry and continue with other known flows. Do not invent a happy path from code shape.
12. E2E tests must be adversarial enough to find bugs: cover invalid/empty/duplicate inputs, permission denial, stale/refreshing/failed read models, partial failure, retry, duplicate click prevention, conflict/version errors, and no-half-write behavior where applicable.
13. Test failure triage is mandatory. After writing or changing tests, run the relevant tests. If a new or changed test fails, do not immediately modify production implementation.
14. First classify every failure as one of: outdated/ambiguous business documentation, incorrect test expectation, unrealistic fixture/mock data, flaky wait/selector/test harness issue, real implementation bug, or real performance issue.
15. For outdated docs, incorrect tests, unrealistic fixtures, or flaky harness failures, fix the spec/test/fixture/docs first, not app implementation.
16. For real implementation/performance bugs, modify implementation only after the expected behavior is confirmed by business/product/module docs or explicit user instruction, the failing test is minimal and deterministic, and the root cause is traced to the shared source of behavior.
17. If docs and current behavior conflict and the authoritative business rule cannot be determined, stop that specific change, record `business-spec-clarification-required`, and continue other independent safe work.
18. Never weaken a valid business assertion just to make tests pass. Never change app behavior solely because a newly generated test failed.

## Business-First Test Source Order

Use this order to define expected behavior:

1. `docs/business-flows/` real business workflows.
2. `docs/product-specs/` product/business rules.
3. `docs/modules/<module>/e2e-spec.md`.
4. `docs/modules/<module>/state-machine.md`.
5. `docs/modules/<module>/boundary-io.md`.
6. `docs/dev/api-contracts.md` or route/API contract tests.
7. Explicit user instructions in this prompt/thread.
8. Existing production behavior only when it is proven to match the business spec.

Use codebase inspection only after the expected behavior is known, and only for:

- locating page entries and controls
- finding existing test helpers and mock fixtures
- identifying current implementation gaps
- extracting stable selectors/accessibility names
- wiring API mocks and operation barriers
- tracing the real flow to the root cause of failures

Forbidden test-generation shortcuts:

- Do not snapshot the current DOM and call it coverage.
- Do not assert only that current buttons exist.
- Do not mark an operation covered only because current implementation calls some endpoint.
- Do not make mocks copy current broken responses if product/API docs say otherwise.
- Do not change expected business results to fit the existing app.
- Do not convert a real bug into a test fixture workaround.

## Test Failure Triage Policy

After writing or changing any E2E/API/service/read-model/worker/permission test:

1. Run the smallest relevant test command first.
2. If it fails, do not jump straight into app code.
3. Classify the failure:
   - `outdated-docs`: product/module/business docs are stale or contradictory.
   - `wrong-test`: test expectation does not match the confirmed business rule.
   - `bad-fixture`: mock/fixture data is unrealistic or internally inconsistent.
   - `harness-flake`: selector, timing, wait condition, browser setup, or test harness issue.
   - `implementation-bug`: app violates confirmed business/API/state-machine contract.
   - `performance-bug`: behavior is correct but latency/feedback/read-model/worker timing violates target or baseline expectation.
4. For `outdated-docs`, `wrong-test`, `bad-fixture`, or `harness-flake`, fix docs/tests/fixtures/harness and rerun. Do not modify implementation.
5. For `implementation-bug` or `performance-bug`, inspect the real flow end to end, identify the shared root cause, then make the smallest implementation fix with the failing test as regression coverage.
6. If classification is unclear, record `business-spec-clarification-required` for that scenario and continue other independent safe work.
7. Every final or phase report must list failing tests by classification and state whether implementation was changed.

## Known Local Inputs

- Admin token is configured locally through `scripts/with-production-admin-token.sh`.
- Production SSH credentials are stored in `/Users/yu/.config/fin-ops-platform/prod-ssh.env`.
- The SSH secret file contains `FIN_OPS_PROD_SSH_HOST`, `FIN_OPS_PROD_SSH_USER`, and `FIN_OPS_PROD_SSH_PASSWORD`, and should be mode `600`.
- Production SSH host is `139.155.5.132`.
- Production SSH user is `root`.
- SSH password is in the secret file. Never output it.
- Local PostgreSQL URL is unavailable. Do not ask for it in the first run.
- `FIN_OPS_E2E_OA_TOKEN` is unavailable. Do not block the main flow on it; mark the ordinary OA route shell/browser smoke as `external_input_required`.

## Production Tickets

### FINOPS-PROD-READONLY-20260705-001

Scope: production read-only validation.

Allowed:
- local deterministic tests
- local Playwright deterministic smoke/list
- production admin AppHealth browser smoke
- production authenticated HTTP/SSE read-only smoke
- production HTTP AppHealth/readiness/queue/worker status
- production SSH read-only inspection

Forbidden:
- any production business write
- imports
- settings changes
- data reset
- permission changes
- OA writeback
- `read_model_slo_smoke --apply`
- `write_operation_e2e_smoke --apply`

### FINOPS-PROD-SSH-READONLY-20260705-001

Scope: SSH into production host for read-only discovery and verification.

Allowed:
- identify deployed release/current app directory
- inspect systemd unit names
- inspect non-secret env variable names
- run read-only health/readiness/runtime diagnostics
- run `production_external_gate_preflight`
- run infra-smoke dry-run/read-only checks
- collect JSON reports under `/tmp` or an existing runtime-smoke output directory

Forbidden:
- editing production files
- restarting services
- changing systemd units
- printing DB URLs, passwords, tokens, cookies, Authorization headers, or secret env values
- destructive shell commands
- package installs or dependency changes

### FINOPS-PROD-REFRESH-APPLY-20260705-001

Scope: enqueue read model refresh events only; no business fact mutation.

Allowed only after:
- local gates pass
- production read-only health check does not show critical queue/worker failure
- command plan is logged without secrets
- operation is limited to `read_model_slo_smoke --apply` or equivalent read-model refresh enqueue

Forbidden:
- mutating business HTTP writes
- imports
- settings changes
- data reset
- permission changes
- OA writeback
- arbitrary SQL writes

### FINOPS-WRITE-SMOKE-20260705-001

The user explicitly approves unattended controlled reversible production write-operation E2E under this ticket.

Scope: controlled reversible production write-operation smoke only.

Allowed unattended write operations:
- `workbench_relation_withdraw`
- `turnover_manual_closure_or_withdraw`
- reversible withdraw-only cleanup scenarios generated by the repository's approved scenario discovery tool

Allowed preparation:
- SSH read-only production discovery
- generate scenario JSON on production host or under `/tmp`
- inspect scenario metadata without printing secrets
- run pre-write health/readiness/outbox/dirty snapshot
- run post-write health/readiness/outbox/dirty snapshot
- run `write_operation_e2e_smoke --apply` only for approved reversible scenarios
- run `write_operation_slo_audit` for executed operations

Forbidden unattended write operations:
- imports of any kind
- settings changes
- data reset
- permission/account changes
- OA writeback
- creating new OA drafts
- confirming new business relations unless the scenario is explicitly reversible and generated by approved tooling
- direct SQL writes
- arbitrary API writes outside the approved scenario file
- destructive non-reversible operations
- any scenario with unclear rollback/recovery

Safety limits:
- maximum 1 scenario per operation type
- maximum 3 total write scenarios per run
- require pre-write production health snapshot
- require post-write production health snapshot
- require scenario file to be non-empty and valid
- require scenario metadata to explain operation, affected scope/month, and rollback/recovery
- if discovery finds no safe candidate, stop write phase and report `no_candidates`
- if any precondition fails, do not improvise another write path

No-OA / bank-flow-rule policy:
- The product page is now `流水规则批量处理`.
- Do not blindly run stale no-oa standing scenarios.
- First reconcile no-oa/no-oa-bank-batches references in docs/policy.
- If discovery still emits a legacy `no_oa_bank_batch_withdraw` scenario, inspect it as legacy compatibility/fan-out evidence and execute only if it is withdraw-only, bounded, reversible, and documented as safe.
- If policy is ambiguous, skip that scenario and continue with Workbench/turnover reversible scenarios.

## Production PostgreSQL URL Policy

- User does not have local PostgreSQL URL.
- Do not ask the user for local DB URL in the first run.
- First try production SSH runner discovery.
- Prefer running DB/read model/outbox/worker direct gates on the production host where deployment env already exists.
- Never print DB URL or secret values.
- If remote env cannot be discovered without exposing secrets, classify DB direct gates as `external_input_required` and continue local + HTTP read-only validation.
- If SSH password auth blocks non-interactive execution, classify SSH runner as `external_input_required` and continue local + HTTP read-only validation.

## SSH Safety

- Load SSH information from `/Users/yu/.config/fin-ops-platform/prod-ssh.env`.
- Use `expect` or Python `pexpect` for password SSH if no SSH key exists.
- Do not place SSH password in repo, docs, shell history, artifact, prompt output, or final report.
- Do not run remote write/apply commands unless the matching ticket allows it and all preconditions are satisfied.

## Phase 0 - Read Sources And Establish Baseline

Read first:
- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/index.md`
- `docs/business-flows/README.md`
- `docs/product-specs/index.md`
- `docs/app-architecture/README.md`
- `docs/app-architecture/pages.md`
- `docs/modules/README.md`
- `docs/architecture/module-boundaries/README.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/dev/testing.md`
- `docs/dev/spec-first-e2e-audit.md`
- `web/src/app/pageRegistry.tsx`
- `web/package.json`

Run first:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_spec_first_e2e_docs -v
PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v
PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v
cd web && npm run e2e:smoke -- --list
```

Known first fixes:
- `docs/modules/README.md` still registers `no-oa-bank-batches` while that directory is missing. Reconcile with the current `流水规则批量处理` state.
- `bankFlowRuleBatches/api.ts` is not mapped in `docs/modules/permissions-and-audit/write-entry-inventory.md`.
- The write-control keyword `提交审批` in `permissions-role-matrix.spec.ts` is not documented in inventory.

After fixing, rerun all four gates. Do not continue until they pass or a concrete blocker is documented.

## Phase 1 - Playwright Full Page/Action Coverage + Performance Baseline

Targets:
- Cover every route from `pageRegistry.tsx`.
- Cover buttons, menus, drawers, dialogs, inputs, uploads, downloads, pagination, filters, sorting, permission states, failure states, and non-fresh states.
- Record latency for every user operation.
- Derive every expected user outcome from business specs/workflows first, then use code only to implement the browser interaction.
- When the app fails the business expectation, keep the failing test and record the bug/performance issue.

Performance schema must include at least:
- route
- pageKey/module
- operation id
- visible label / accessible name
- action type
- start timestamp
- first visible response latency
- API latency
- operation barrier/read model fresh latency
- final settled latency
- pass/fail
- failure reason

Implementation rules:
- Reuse `web/e2e/fixtures/strictTest.ts`.
- Add only the smallest helper needed.
- Write artifacts to Playwright output as JSON/JSONL; do not pollute repo root.
- First migrate one representative spec to validate the helper; then proceed page-by-page.
- Each operation must assert visible post-click content, request/download/state change, error feedback, mutation count, and barrier/read-model fresh result where applicable.

Page order:
1. `/` 关联台
2. `/bank-details` 银行明细
3. `/cost-statistics` 成本统计
4. `/oa-pending-payments` OA 待付款核对
5. `/bank-flow-rule-batches` 流水规则批量处理
6. `/batch-accounting` 批量账务
7. `/turnover-ledger` 外部往来款管理
8. `/etc-tickets` ETC 票据管理
9. `/tax-offset` 税金抵扣
10. `/pending-invoices` 待找发票
11. `/input-invoice-usage` 进项发票使用情况
12. `/output-invoice-collections` 销项发票收款情况
13. `/settings` 设置
14. `/operations/app-health` 系统状态
15. `/imports/bank-transactions` 银行流水导入
16. `/imports/invoices` 发票导入
17. `/imports/etc-invoices` ETC 发票导入

For each page:
- Read module `README.md`, `boundary-io.md`, `tests.md`, `e2e-spec.md`, and `e2e-coverage.md`.
- Read the matching `docs/business-flows/` and `docs/product-specs/` entries when available.
- Write or refine the operation checklist from business workflow steps, not from JSX alone.
- Compare real page/feature code against existing specs.
- Fill only real gaps.
- Update module docs if facts or coverage change.
- Run directed Playwright for that page.
- If directed Playwright fails, apply the Test Failure Triage Policy before modifying app implementation.
- Rerun docs/permissions/nightly/list gates.

## Phase 2 - API / Service Backend Test Closure

Targets:
- Every page-related API contract has tests.
- Business service rules, failure paths, permission paths, idempotency, version conflicts, and partial failures have tests.
- Tests assert response shape and key fields, not just HTTP 200.

Build a coverage map from:
- `backend/src/fin_ops_platform/app/routes_*.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/`
- `tests/`

Per module, read `README.md`, `boundary-io.md`, and `tests.md`.

Only add high-value tests. Update module testing docs.

## Phase 3 - Read Model / Worker Test Closure

Targets:
- Every read model has freshness/status/enqueue/scope/dirty/outbox/worker drain contract tests.
- No page can display stale/missing/refreshing/failed as fresh.
- Write operations map to dirty scope/outbox/read model refresh.
- Worker registry, manifest, scope policy, and runtime queue have consistency gates.

Read:
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/modules/read-models/`
- `docs/modules/runtime-workers/`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## Phase 4 - Permissions / Audit Closure

Targets:
- `read_export_only`, `full_access`, `admin`, forbidden, and expired are covered for all pages and deep drawers/dialogs.
- All write entries are in `write-entry-inventory.md`.
- All mutating feature API clients are mapped to inventory.
- High-risk writes verify audit actor/tenant/action/metadata and rollback no-half-write behavior.
- Secrets/passwords/tokens are not exposed.

Run continuously:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v
```

## Phase 5 - Local Full Verification

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test
cd web && npm run build
PYTHONPATH=backend/src python3 -m unittest tests.test_spec_first_e2e_docs -v
PYTHONPATH=backend/src python3 -m unittest tests.test_permissions_write_entry_inventory -v
PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v
cd web && npm run e2e:smoke -- --list
cd web && npm run e2e:smoke
```

If full smoke fails, classify each failure as product bug, test bug, environment issue, or external input issue. Preserve trace information.

## Phase 6 - Production HTTP/Admin Read-Only Validation

Use:

```bash
scripts/with-production-admin-token.sh bash -lc 'PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.production_external_gate_preflight --json'
cd web && ../scripts/with-production-admin-token.sh npm run e2e:production-admin
```

`FIN_OPS_E2E_OA_TOKEN` is unavailable. Mark ordinary OA route shell/browser smoke as `external_input_required`; do not block.

## Phase 7 - Production SSH Read-Only Discovery

Load SSH info from `/Users/yu/.config/fin-ops-platform/prod-ssh.env`.

Use only read-only commands:
- `whoami`
- `hostname`
- `pwd`
- locate deployment directories
- inspect systemd unit names
- inspect env key names without values
- locate runtime-smoke/scenario directories
- locate repo/venv/scripts

Forbidden:
- output secret values
- modify files
- restart services
- install packages
- execute write/apply commands

## Phase 8 - Production Remote DB/Read Model/Worker Read-Only Validation

If production env can be safely discovered on the server:
- run read-only preflight / infra-smoke dry-run / runtime health / readiness / queue / outbox / dirty scope checks remotely
- write JSON reports to `/tmp/finops-*.json` or existing runtime-smoke output directory
- summarize without secrets

If env cannot be safely discovered:
- mark DB direct gates `external_input_required`
- continue HTTP/admin/local validation

## Phase 9 - Read Model Refresh Apply

Only under `FINOPS-PROD-REFRESH-APPLY-20260705-001`, and only if production read-only health has no critical failure:
- run `read_model_slo_smoke --apply` or equivalent approved read-model refresh enqueue
- wait for worker drain
- record latency/readiness

Do not mutate business facts.

## Phase 10 - Controlled Reversible Production Write Validation

The user approved `FINOPS-WRITE-SMOKE-20260705-001`.

Execution order:
1. Reconcile no-oa -> bank-flow-rule-batches docs and scenario policy first.
2. Remotely run `write_operation_scenario_discovery` read-only and write scenario JSON to a safe path.
3. Inspect scenario:
   - non-empty
   - operation in allowed list
   - maximum 1 per operation type
   - maximum 3 total
   - metadata includes scope/month/rollback or recovery
   - no imports/settings/reset/OA writeback/direct SQL
4. Capture pre-write health/readiness/outbox/dirty snapshot.
5. Run `write_operation_e2e_smoke --apply --approval-ticket FINOPS-WRITE-SMOKE-20260705-001`.
6. Wait for read model/worker/outbox/dirty convergence.
7. Run `write_operation_slo_audit` for executed operations.
8. Report operation, endpoint path, status, latency, readiness/outbox result, and pass/fail.
9. If any precondition fails, skip writes and report the blocker.

## Phase 11 - Performance Baseline And Optimization Candidates

Aggregate:
- Playwright operation latency
- API latency
- operation barrier latency
- read model fresh latency
- worker/readiness latency
- production HTTP/DB/read model latency

Output P0/P1 issues:
- click has no feedback
- slow API
- slow barrier
- slow read model fresh
- slow worker drain
- duplicate request
- duplicate mutation
- false empty
- stale UI
- hidden browser error
- permission/audit gap

## Phase 12 - Final Closure Report

Final report must include:
- covered pages/actions/buttons/dialogs/triggers
- added/changed tests
- seven-category test coverage
- Playwright performance baseline
- API/Service coverage
- Read model/Worker coverage
- Permissions/Audit coverage
- production HTTP/SSH/DB/read-model/worker validation
- controlled production write validation
- `external-risk`
- `external_input_required`
- unresolved bugs
- performance bottlenecks
- next optimization prompt

Closure definition:
- all safe automatically executable gates ran
- all failures are classified with evidence
- all unexecuted items are explicitly `external_input_required` or `external-risk`
- no unexecuted item is mislabeled as `covered`
```
```

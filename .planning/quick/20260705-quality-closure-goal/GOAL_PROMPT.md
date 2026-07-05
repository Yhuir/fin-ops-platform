/goal
You are the master Codex agent for fin-ops-platform. Work in:
/Users/yu/Desktop/fin-ops-platform

Goal: automatically drive the project toward a defined, evidence-backed quality closure:

Playwright full page/action coverage + per-operation latency baseline + API/Service/Read model/Worker backend tests + permissions/audit tests + production HTTP/SSH/DB/read-model/worker validation + controlled reversible production write-operation validation.

## Latest User Clarifications

These clarifications override any weaker wording elsewhere in this prompt:

1. E2E tests must model the real finance business workflow, not the current codebase. Use the app code only to find routes, controls, selectors, API seams, and implementation gaps after the business expectation has been established.
2. The current app may contain small bugs. A test that simply mirrors the current implementation is low value and must not be counted as meaningful coverage.
3. After writing or changing Playwright/API/service/read-model/worker/permission tests, run them. A failing test is an investigation signal, not automatic proof that production implementation is wrong.
4. When a new or changed test fails, first check whether the business docs are stale, the expected assertion is wrong, the fixture is unrealistic, or the test harness is fragile. Fix those first when they are the cause.
5. Modify production implementation only when the failure is a deterministic violation of a confirmed business/product/module/API/read-model/worker/permission contract or an explicit user rule.
6. Passing all tests does not prove the app is perfect. It means the documented and implemented coverage passed; unmodeled scenarios, stale docs, production-only data shapes, concurrency, OA/third-party behavior, and future feature changes still require targeted review and tests.

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
19. Tests are evidence and regression protection, not a mathematical proof that the app is perfect. Passing tests means the documented/implemented coverage passed; unmodeled risks, stale docs, missing scenarios, production-only data shape issues, concurrency races, and third-party/OA issues must remain visible in the final risk register.
20. The current app implementation is not the oracle. Treat it as possibly buggy until behavior is checked against business/product/module/API/read-model/permission contracts.
21. Do not "cover" a page by clicking through implementation details. A page operation is covered only when the business intent, valid fixture/state, expected visible result, expected side effect, permission behavior, and latency barrier are all identified and the relevant verification has run.
22. Do not launder current buggy behavior into docs. Update docs only when a higher-priority business source, module contract, API contract, production-safe evidence, or explicit user instruction confirms the intended rule.
23. Prefer producing a precise failing regression test and bug/performance finding over making broad implementation changes. The goal is to discover real defects and bottlenecks, not to force a guessed suite green.

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
- Do not use existing tests as the only source of expected behavior. Existing tests can be reused as scaffolding, but business expectations still need a source.
- Do not treat labels/buttons found in JSX as a complete operation list. Cross-check page registry, business workflows, module docs, API clients, permission inventory, and existing E2E specs.

## Test-Or-Implementation Decision Contract

This suite is meant to expose real business bugs and performance bottlenecks. It must not become a mirror of the current codebase, and it must not automatically rewrite production behavior whenever a newly generated test fails.

For every new or changed scenario, follow this contract:

1. Define the expected behavior from the Business-First Test Source Order before writing assertions.
2. Record the source freshness as `current`, `stale`, `ambiguous`, `missing`, or `legacy`.
3. Create the smallest deterministic test that represents a real business state.
4. Run that test immediately.
5. If it passes, record coverage evidence and latency. Do not claim full-app correctness.
6. If it fails, first treat the failure as an investigation signal, not proof that implementation is wrong.
7. Before editing production implementation, explicitly rule out:
   - stale or outdated docs
   - ambiguous business rules
   - a wrong or over-specific test assertion
   - unrealistic fixture/mock data
   - a fragile selector, timing barrier, route mock, or Playwright wait
   - environment-only failure
8. Modify implementation only when the failure is a deterministic violation of a confirmed business/API/state-machine/read-model/permission contract.
9. If docs appear stale but the intended rule cannot be proven from a higher-priority source, do not update implementation and do not force the test green. Mark the scenario `business-spec-clarification-required` and continue other safe work.
10. If the current implementation appears sensible but docs are stale, update docs/tests only after the intended business rule is confirmed by a newer product/module/API source, production-safe observation, or explicit user instruction.

Correct failure outcomes:

- Test was wrong -> fix the test and rerun.
- Fixture was unrealistic -> fix the fixture and rerun.
- Docs were stale -> update the authoritative doc/matrix if a newer source confirms the rule, then adjust the test and rerun.
- Harness was flaky -> fix waits/selectors/barriers and rerun.
- Implementation violates a confirmed contract -> make the smallest implementation fix and rerun the failing test plus relevant regression tests.
- Performance violates a confirmed target or baseline -> record latency evidence, then optimize only the confirmed bottleneck or add a performance backlog item with reproduction.
- Rule is unclear -> record `business-spec-clarification-required`, do not modify implementation, and continue independent work.

Do not use a passing full suite as a guarantee that future code changes are perfect. When a new feature or modification is made later, identify the affected business rule, API, service, read model, worker, permission/audit path, and UI flow, then add targeted tests for that change.

## Business Operation Evidence Matrix

Maintain a working matrix at:

```text
.planning/quick/20260705-quality-closure-goal/business-operation-evidence.md
```

For every route/page and every operation discovered from docs, business flows, page code, API clients, permissions inventory, and existing tests, record:
- operation id
- page route and module
- source of discovery: business-flow, product-spec, module-doc, API contract, permission inventory, existing test, page code, or production-safe observation
- visible control label / accessible name / keyboard shortcut / implicit trigger
- user business intent
- preconditions and valid fixture state
- expected visible UI result
- expected API/service/read-model/worker/audit/download/navigation side effect
- permission behavior for read-only, full-access/admin, forbidden, expired, and missing-token states when applicable
- freshness/error/empty/duplicate/conflict behavior when applicable
- latency barrier to measure: first visible feedback, API response, download event, read model fresh, worker drain, audit write, navigation settled, or dialog visible
- authoritative source path and freshness status
- coverage status using the definitions below
- verification command and latest result
- linked bug/performance/spec-gap/triage entry when not fully covered

Rules:
- Write the matrix from business intent first, then implement or adapt tests.
- A code-discovered button with no business source must be recorded as `spec-unclear` or `business-spec-clarification-required` until the intended behavior is confirmed.
- A doc-described business operation with no visible control must be recorded as `failed` or `partial` after verification, not silently ignored.
- Existing tests that pass can be mapped as evidence only if their assertions cover the business outcome and side effect, not just rendering.

## Coverage Status Definitions

Use these exact meanings in module docs, working matrices, and final reports:

- `covered`: confirmed business expectation, valid fixture/state, user-visible assertion, side-effect assertion when applicable, latency artifact, and relevant test command passed.
- `partial`: some evidence exists, but at least one required dimension is missing, such as permission path, stale/read-model state, audit side effect, invalid input, duplicate prevention, or performance barrier.
- `spec-unclear`: operation exists or is expected, but the current business rule cannot be proven from authoritative sources.
- `business-spec-clarification-required`: docs/current behavior conflict, or the operation is high-risk and no authoritative rule can be established without the user.
- `external_input_required`: blocked by missing external credential, OA token, production-only permission, unavailable remote runner, or user-provided safe scenario.
- `external-risk`: behavior depends on third-party/OA/production data/concurrency paths that were not fully controllable in local deterministic tests.
- `failed`: confirmed expectation was tested and failed. The failure must have a triage entry and classification.

Do not use `covered` for a scenario that has not been run. Do not use `covered` for a passing low-level test if the user operation and visible outcome remain untested, unless the report explicitly maps why lower-level coverage is the correct boundary.

## Test Failure Triage Policy

After writing or changing any E2E/API/service/read-model/worker/permission test:

1. Run the smallest relevant test command first.
2. If it fails, do not jump straight into app code.
3. For each failed assertion, write a short triage note before fixing anything:
   - test file and scenario id
   - failed operation/button/API/job/read model
   - expected behavior
   - actual behavior
   - authoritative source for the expectation
   - whether that source is current, stale, ambiguous, or missing
   - proposed owner: `docs`, `test`, `fixture`, `harness`, `implementation`, `performance`, or `external-input`
4. Classify the failure:
   - `outdated-docs`: product/module/business docs are stale or contradictory.
   - `wrong-test`: test expectation does not match the confirmed business rule.
   - `bad-fixture`: mock/fixture data is unrealistic or internally inconsistent.
   - `harness-flake`: selector, timing, wait condition, browser setup, or test harness issue.
   - `implementation-bug`: app violates confirmed business/API/state-machine contract.
   - `performance-bug`: behavior is correct but latency/feedback/read-model/worker timing violates target or baseline expectation.
5. For `outdated-docs`, `wrong-test`, `bad-fixture`, or `harness-flake`, fix docs/tests/fixtures/harness and rerun. Do not modify implementation.
6. For `implementation-bug` or `performance-bug`, inspect the real flow end to end, identify the shared root cause, then make the smallest implementation fix with the failing test as regression coverage.
7. If classification is unclear, record `business-spec-clarification-required` for that scenario and continue other independent safe work.
8. Keep failing tests only when they encode a confirmed business/API/state-machine contract. Quarantine or mark scenarios as spec gaps when the rule is not confirmed; do not leave speculative failures blocking unrelated work.
9. Every final or phase report must list failing tests by classification and state whether implementation was changed.

## Implementation Change Gate

Before changing production implementation because of a failed generated test, all of the following must be true:

1. The expected behavior is backed by a current business/product/module/API/read-model/worker/permission contract or explicit user rule.
2. The fixture or production-safe scenario represents a real business state, not a synthetic state that violates upstream contracts.
3. The test waits on the right observable barrier: visible UI response, API response, download, mutation rejection/success, audit event, read model freshness, worker drain, or permission denial.
4. The failure is deterministic after one rerun of the smallest relevant test, unless the issue being captured is itself a confirmed flake/performance bug.
5. The root cause is traced to the shared source of behavior, not a one-off symptom in the test harness.
6. The implementation change is the smallest reversible fix and does not hide stale docs or invalid test assumptions.

If any item is false, do not change implementation. Fix the spec/test/fixture/harness or record a blocker, then continue safe independent work.

## Run-Then-Triage Loop For Newly Added Tests

This workflow exists to find real bugs and performance issues, not to force the current implementation to match a guessed test.

For every new or changed Playwright/API/service/read-model/worker/permission test:

1. Run the smallest relevant test command before marking the scenario `covered`.
2. If it passes, record it as coverage evidence only. Do not claim the whole app is guaranteed perfect.
3. If it fails, first assume the failure may be caused by stale docs, ambiguous business rules, unrealistic fixture data, or a fragile test harness.
4. Capture the failure evidence without secrets: assertion, user operation, visible UI state, relevant sanitized request/response shape, screenshot/trace location when available, and latency if it was a performance failure.
5. Compare the expected behavior against the Business-First Test Source Order.
6. Write a triage note before any production implementation change.
7. Classify the failure as `outdated-docs`, `wrong-test`, `bad-fixture`, `harness-flake`, `implementation-bug`, `performance-bug`, or `business-spec-clarification-required`.
8. Fix docs/tests/fixtures/harness first for the first four classes, rerun the same smallest command, then update coverage notes.
9. Only fix implementation for `implementation-bug` or `performance-bug`, and only after the Implementation Change Gate passes.
10. If the authoritative business rule cannot be confirmed, do not modify implementation and do not keep a speculative failing test as a blocking gate. Mark the scenario `business-spec-clarification-required` or `spec-unclear`, then continue other independent safe work.

Important: a failing generated test is a signal to investigate, not automatic proof that the app is wrong. A passing generated test is regression protection for the modeled scenario, not proof that every future feature or all production behavior is correct.

## Business Spec Freshness Audit

Before creating or changing a scenario, audit whether the expected behavior source is current enough to drive a test.

For each page operation, record:
- operation id
- route/page/module
- visible control label or accessible name
- user intent
- expected visible result
- expected API/service/read-model/worker/audit side effect
- fixture or production-safe state required
- authoritative source path and section
- freshness status: `current`, `stale`, `ambiguous`, `missing`, or `legacy`

Rules:
- If the source mentions removed pages, old names, old routes, old statuses, old API fields, or old business terms, mark it `stale` before writing assertions.
- If stale docs can be safely reconciled from newer product/module/business docs and explicit user instructions, update the docs first, then write tests.
- If current business intent cannot be proven, add the operation to `.planning/quick/20260705-quality-closure-goal/spec-gaps.md` and continue other work.
- If code exposes an undocumented button or operation, do not assert current behavior as truth. Treat it as a discovered operation, then find or write the business expectation before making it a coverage gate.
- Do not create impossible fixtures merely to click every button. Fixtures must represent a valid upstream business state.
- Do not mark a scenario `covered` from exploratory clicking, DOM snapshots, or implementation mirroring.

## Failure Triage Artifact

Maintain a running failure log at:

```text
.planning/quick/20260705-quality-closure-goal/test-failure-triage.md
```

For every failing new or changed test, append a compact entry before any implementation change:
- timestamp
- command
- test file and scenario id
- operation id / button / API / worker / read model
- expected behavior
- actual behavior
- source path and freshness status
- sanitized evidence
- classification: `outdated-docs`, `wrong-test`, `bad-fixture`, `harness-flake`, `implementation-bug`, `performance-bug`, or `business-spec-clarification-required`
- decision: docs/test/fixture/harness fix, implementation fix, performance backlog, quarantine, or external input
- rerun command and result

If a command passes, do not create noise in the log. Record pass evidence in the relevant module `e2e-coverage.md`, test docs, or final closure report.

## Failure First Response Decision Tree

When any new or changed test fails, follow this order before editing production code:

1. Preserve evidence: command, test name, sanitized assertion, visible UI state, relevant request/response shape, trace/screenshot path when available, and latency measurement.
2. Confirm the expected behavior against the Business-First Test Source Order and the Business Operation Evidence Matrix.
3. If the source is stale or contradicted by a higher-priority source, classify `outdated-docs`, update the doc/matrix, adjust the test only after the intended rule is confirmed, and rerun.
4. If the expected assertion is not the real business rule, classify `wrong-test`, fix the test, and rerun.
5. If the fixture represents an impossible or internally inconsistent business state, classify `bad-fixture`, fix the fixture, and rerun.
6. If the browser wait, selector, mock timing, download handling, or route interception is fragile, classify `harness-flake`, fix the harness, and rerun.
7. If behavior violates a confirmed contract, classify `implementation-bug`, then inspect the shared root cause and make the smallest implementation fix with the failing test as regression coverage.
8. If behavior is correct but responsiveness violates target/baseline or lacks timely feedback, classify `performance-bug`, record the latency artifact, and either make the smallest safe optimization or add it to the performance backlog with reproduction.
9. If the rule cannot be confirmed, classify `business-spec-clarification-required`, do not modify implementation, and continue other independent safe work.

Never skip the decision tree because a failure looks obvious. Newly generated tests are allowed to be wrong.

## Interpreting Green Tests

The final suite is a regression and evidence system, not a guarantee of a perfect app.

When tests pass, state only that the modeled and executed scenarios passed under the tested fixtures/environment. Do not claim:
- all future changes are safe
- all production data shapes are covered
- all third-party/OA behavior is correct
- all concurrency races are impossible
- all hidden permission/audit paths are safe
- performance is globally optimal

For future feature work, a green suite is necessary evidence but not sufficient proof. New or changed behavior still requires targeted tests for the affected business rules, APIs, services, read models, workers, permissions, audit events, and E2E flows.

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
- When the app fails a confirmed business expectation, keep the failing test and record the bug/performance issue.

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
- Update `.planning/quick/20260705-quality-closure-goal/business-operation-evidence.md` before adding assertions for newly discovered operations.
- Compare real page/feature code against existing specs.
- Fill only real gaps.
- Update module docs if facts or coverage change.
- Run directed Playwright for that page.
- If directed Playwright fails, apply the Test Failure Triage Policy before modifying app implementation.
- Do not mark a page/action/button/dialog as `covered` until its directed Playwright or explicitly mapped lower-level test has run successfully, or until the remaining gap is classified as `partial`, `external-risk`, `external_input_required`, `spec-unclear`, or `business-spec-clarification-required`.
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
- the final business operation evidence matrix summary
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

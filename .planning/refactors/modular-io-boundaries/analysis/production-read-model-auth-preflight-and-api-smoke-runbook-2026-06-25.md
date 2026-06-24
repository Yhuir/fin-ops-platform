# Production Read Model Auth Preflight And API Smoke Runbook - 2026-06-25

**Boundary:** `production:read-model-auth-preflight-and-api-smoke-runbook`
**Status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `planning:post-auth-preflight-next-boundary-selection`

## Goal

Run the bounded production auth preflight selected in Row268 and, only if an existing non-secret HTTP SLO auth configuration is present, run metadata-only authenticated API response-shape smoke.

This slice does not request, print or store tokens/cookies. It does not deploy, restart, requeue, repair, replay workers, mutate DB/queue/readiness state or run production writes.

## Preconditions Reviewed

- `dev` and `origin/dev` aligned at `c5e6c641a42beaa51c82233b50b4b60abb3f22ca`.
- `ssh finops-prod-root` was available.
- Row268 selected a stop-if-missing auth preflight.
- `docs/operations/monitoring.md` requires real HTTP SLO auth for authenticated API/page SLO evidence and states that `--allow-unauthenticated` is not valid for final authenticated evidence.

## Precheck Health

Command shape:

```bash
ssh finops-prod-root '... curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready ...'
```

Result:

```text
release_src=/opt/fin-ops/releases/dev-workbench-matching-port-20260625020818/src
git_commit=
{'status': 'ready'}
```

The active release source was discoverable and `/health/ready` was ready.

## Auth Configuration Check

The check sourced production env files with `set +x` and printed only whether at least one supported variable was configured:

- `FIN_OPS_HTTP_SLO_BEARER_TOKEN`
- `FIN_OPS_HTTP_SLO_ADMIN_TOKEN`
- `FIN_OPS_HTTP_SLO_COOKIE`

Result:

```text
http_slo_auth_configured=no
```

Because no supported HTTP SLO auth variable was configured, the stop gate fired. No authenticated `http_slo_probe` was run.

## Post-Checks

Health remained ready:

```text
{'status': 'ready'}
```

Read-only aggregate checks returned:

```text
dirty_scopes [{'status': 'done', 'count': 187007}]
readiness [{'status': 'fresh', 'count': 498}]
read_model_outbox [{'status': 'done', 'count': 202898}]
```

## Result

`production-evidence-deferred`.

The run confirms the production authenticated API evidence blocker remains auth configuration, not local smoke freshness. T0 did not request or print credentials, did not run authenticated probes, did not store response bodies, and did not mutate production state.

## Closure Impact

- Authenticated production API response-shape closure remains open.
- Authenticated production browser data hydration remains open.
- Production high-row browser evidence remains open.
- Worker-drain/write-after-read convergence remains open.
- Module/global closure remains open.

## State-Machine Impact

- Row269 closes as `production-evidence-deferred`.
- Row270 is inserted as `pending`.
- No module status changes to `closed`.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No module docs or long-term docs change because this runbook followed existing monitoring policy and did not change production smoke guidance, auth policy, API contract or closure criteria.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: deferred; authenticated API smoke did not run because auth config was absent.
4. Read model/cache/background job tests: covered only by production read-only aggregate post-checks showing dirty/readiness/outbox remained clean.
5. Frontend component and interaction tests: not applicable in this production preflight; Row267 remains the latest local browser evidence.
6. End-to-end business-flow integration tests: deferred behind real auth and write approval gates.
7. Existing feature regression tests: covered by read-only health/post-check classification only; no authenticated regression evidence was added.

## Next Boundary Recommendation

Select `planning:post-auth-preflight-next-boundary-selection`.

The next planning slice should decide whether to:

- package the remaining production auth/write approval requirements as a human gate;
- broaden local/internal API harness coverage while production auth remains unavailable;
- or select another independent non-secret production evidence boundary that does not require authenticated API/browser access.

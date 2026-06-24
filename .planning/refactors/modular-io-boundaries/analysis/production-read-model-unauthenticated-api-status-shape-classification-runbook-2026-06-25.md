# Production Read Model Unauthenticated API Status Shape Classification Runbook

**Boundary:** `production:read-model-unauthenticated-api-status-shape-classification-runbook`
**Status:** `production-evidence-deferred`
**Date:** 2026-06-25
**Branch:** `dev`
**Controller:** T0
**Closure:** module/global closure not claimed

## Objective

Classify read-model-heavy API probe behavior without authentication after authenticated API smoke was deferred for missing non-secret auth config. This boundary is classification only: it does not prove authenticated API behavior, browser hydration, permissions, operation barriers or module closure.

## Safety Properties

- Uses the existing `fin_ops_platform.tools.http_slo_probe` default API probes.
- Runs with `--allow-unauthenticated`.
- Uses `--no-default-page-probe` so only API probes run.
- Sends GET requests only.
- Does not send bearer tokens, cookies or admin tokens.
- Does not store response bodies.
- Stores only probe summary metadata:
  - status code counts;
  - content type;
  - response byte count;
  - duration percentiles;
  - extracted `read_model_status`, `cache_status`, `refresh_enqueued` when JSON shape exposes them.
- Does not deploy, restart, requeue, repair, replay workers, mutate DB rows, mutate queue/readiness state or run `--apply`.

## Commands

### 1. Precheck Health

```bash
ssh finops-prod-root 'set -eu; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
```

### 2. Run API-Only Classification

```bash
ssh finops-prod-root 'set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.http_slo_probe --base-url https://www.yn-sourcing.com --allow-unauthenticated --no-default-page-probe --iterations 1 --warmup 1 --timeout-seconds 15 --target-ms 5000 --json'
```

### 3. Postcheck Health

```bash
ssh finops-prod-root 'set -eu; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
```

## Stop Gates

- `/health/ready` is not ready before classification.
- The command would require or print auth tokens, cookies, DSNs or env secret values.
- The command would store response bodies or payload rows.
- The command would mutate production state.

## Expected Evidence

- `/health/ready` ready before and after.
- API-only `http_slo_probe` JSON report.
- Per-probe status classification:
  - public JSON response;
  - unauthenticated/forbidden;
  - not found;
  - HTML-routed/non-API response;
  - timeout/error;
  - refreshing/fresh where metadata is available.
- No module/global/authenticated API closure claim.

## Result

Completed as `production-evidence-deferred`.

### Precheck

`/health/ready` returned:

```text
{'status': 'ready'}
```

### API-Only Classification

The unauthenticated API-only run returned:

- `status`: `fail`
- `auth_configured`: `false`
- `base_url`: `https://www.yn-sourcing.com/`
- `probe_count`: 38
- `sample_count`: 38
- `failed_probe_count`: 38
- `max_p95_ms`: 77.401
- `timeout_seconds`: 15

Status classification:

| Status | Probe count | Classification |
| --- | ---: | --- |
| `401` | 38 | All default API probes are authentication-gated on the public base. |

Every default API probe returned `unexpected_status:401`, including:

- session/app health/background jobs/operations health;
- Workbench summary/groups/settings;
- bank details accounts/transactions/auto-tag rules;
- pending invoices rows/filter/rules;
- input invoice usage rows/filter/rules;
- OA pending payments rows/filter;
- output invoice collections rows/filter/rules;
- tax offset summary/rows;
- cost statistics explorer/summary;
- no-OA batches/tag selection;
- batch accounting;
- turnover ledger grouped/tag selection;
- ETC/import facts endpoints;
- search.

No `read_model_status`, `cache_status` or `refresh_enqueued` metadata was available because every API response was auth-blocked.

### Postcheck

`/health/ready` returned:

```text
{'status': 'ready'}
```

## Closure Impact

- This run proves public API surfaces are consistently auth-gated without configured credentials.
- It also proves unauthenticated public API probing cannot produce read-model response-shape closure evidence.
- Authenticated API closure remains deferred until a non-secret auth path, an internal contract harness, or another approved evidence route exists.
- Browser shell evidence remains valid, but browser data/hydration closure remains open for the same auth reason.
- No response bodies, payload rows, tokens, cookies, DSNs, env values or secrets were stored.
- No production mutation, deploy, restart, requeue, repair, replay, DB write, queue/readiness mutation or `--apply` occurred.

## Next Boundary

`planning:post-unauthenticated-api-classification-next-boundary-selection`

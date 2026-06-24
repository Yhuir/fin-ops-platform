# Production Read Model Public Page Shell Smoke Runbook

**Boundary:** `production:read-model-public-page-shell-smoke-runbook`
**Status:** `production-controlled`
**Date:** 2026-06-25
**Branch:** `dev`
**Controller:** T0
**Closure:** module/global closure not claimed

## Objective

Collect bounded production public page-shell smoke evidence for the FinOps frontend routes that host read-model-heavy pages. This boundary is not authenticated API evidence and does not prove module closure.

## Safety Properties

- Uses `fin_ops_platform.tools.http_slo_probe` in page-shell-only mode:
  - `--allow-unauthenticated`
  - `--replace-default-probes`
  - no API probes
- Sends GET requests only.
- Reports page probe metadata only: URL, HTTP status, content type, response bytes and duration percentiles.
- Does not print response bodies.
- Does not read or print tokens, cookies, DSNs, passwords or env secret values.
- Does not deploy, restart, requeue, repair, replay workers, mutate DB rows, mutate queue/readiness state or run `--apply`.

## Commands

### 1. Precheck Health

```bash
ssh finops-prod-root 'set -eu; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
```

### 2. Run Page-Shell-Only Smoke

```bash
ssh finops-prod-root 'set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.http_slo_probe --base-url http://127.0.0.1:18001 --allow-unauthenticated --replace-default-probes --iterations 1 --warmup 1 --timeout-seconds 15 --target-ms 5000 --json'
```

The first execution used the API listener as the base URL. All `/fin-ops/*` page-shell paths returned 404 because that listener does not serve the public frontend base. This was classified as an operator base-URL error, not a product page-shell failure.

The public frontend base was then verified:

```bash
ssh finops-prod-root 'set -eu; curl -fsS --max-time 8 https://www.yn-sourcing.com/fin-ops/ >/dev/null; echo public_fin_ops_shell_probe_base_ok'
```

The page-shell-only smoke was rerun against the public base:

```bash
ssh finops-prod-root 'set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.http_slo_probe --base-url https://www.yn-sourcing.com --allow-unauthenticated --replace-default-probes --iterations 1 --warmup 1 --timeout-seconds 15 --target-ms 5000 --json'
```

### 3. Postcheck Health

```bash
ssh finops-prod-root 'set -eu; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
```

## Stop Gates

- `/health/ready` is not ready before smoke.
- `http_slo_probe` would run API probes.
- Any command requires or prints auth tokens, cookies, DSNs or sensitive data.
- Any command would mutate production state.
- Public page shell probe returns non-HTML for frontend pages, status other than 200, or pervasive timeout.

## Expected Evidence

- `/health/ready` ready before and after.
- `http_slo_probe` JSON report with page-shell probe count, failed probe count, per-page status code counts, durations, content type and response byte counts.
- No secrets and no response bodies in stored evidence.

## Result

Completed as `production-controlled`.

### Precheck

`/health/ready` returned:

```text
{'status': 'ready'}
```

### Wrong-Base Probe

The first `http://127.0.0.1:18001` run returned:

- `status`: `fail`
- `probe_count`: 17
- `failed_probe_count`: 17
- `max_p95_ms`: 1.768
- Every `/fin-ops/*` page-shell route returned `404`.

Classification: wrong local listener/base URL. The public frontend is not served from the local API listener path.

### Public Page-Shell Probe

The public base check returned `public_fin_ops_shell_probe_base_ok`.

The rerun against `https://www.yn-sourcing.com` returned:

- `status`: `pass`
- `base_url`: `https://www.yn-sourcing.com/`
- `probe_count`: 17
- `sample_count`: 17
- `failed_probe_count`: 0
- `max_p95_ms`: 27.782
- `auth_configured`: `false`
- Mode: unauthenticated page-shell probes only; no API probes.

All default public page-shell paths returned HTTP 200 within the 5000 ms target:

- `/fin-ops/`
- `/fin-ops/bank-details`
- `/fin-ops/pending-invoices`
- `/fin-ops/input-invoice-usage`
- `/fin-ops/oa-pending-payments`
- `/fin-ops/output-invoice-collections`
- `/fin-ops/tax-offset`
- `/fin-ops/cost-statistics`
- `/fin-ops/no-oa-bank-batches`
- `/fin-ops/batch-accounting`
- `/fin-ops/turnover-ledger`
- `/fin-ops/etc-tickets`
- `/fin-ops/imports/bank-transactions`
- `/fin-ops/imports/invoices`
- `/fin-ops/imports/etc-invoices`
- `/fin-ops/settings`
- `/fin-ops/operations/app-health`

Representative p95 timings:

- Home: 23.457 ms
- Bank details: 23.316 ms
- Pending invoices: 22.94 ms
- Input invoice usage: 22.584 ms
- OA pending payments: 24.262 ms
- Output invoice collections: 27.782 ms
- Tax offset: 22.219 ms
- Cost statistics: 22.094 ms
- No-OA bank batches: 23.04 ms
- Batch accounting: 21.953 ms
- Turnover ledger: 23.221 ms
- Settings: 22.524 ms
- Operations app health: 22.341 ms

### Postcheck

`/health/ready` returned:

```text
{'status': 'ready'}
```

## Closure Impact

- Public unauthenticated page-shell availability evidence is collected for the read-model-heavy frontend routes.
- This does not prove authenticated API response shapes, browser hydration, rendered table contents, user-permission behavior, high-row workflows or module-specific closure.
- No production mutation, deploy, restart, requeue, repair, replay, DB write, queue/readiness mutation, response body storage or secret output occurred.
- Module/global closure remains unclaimed.

## Next Boundary

`planning:post-public-page-shell-smoke-next-boundary-selection`

# Production Read Model Shadow-Read Rehearsal Read-Only Runbook

**Boundary:** `production:read-model-shadow-read-rehearsal-read-only-runbook`
**Status:** `production-evidence-deferred`
**Date:** 2026-06-25
**Branch:** `dev`
**Controller:** T0
**Closure:** module/global closure not claimed

## Objective

Collect bounded production read-path parity evidence with `fin_ops_platform.tools.run_shadow_read_rehearsal` after public page-shell availability was proven and authenticated HTTP API smoke was deferred for missing non-secret auth configuration.

This evidence is not authenticated API response-shape evidence, not browser hydration evidence, and not final module/global closure.

## Safety Properties

- Uses the existing `run_shadow_read_rehearsal` tool.
- Production execution must set `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1`.
- The tool rejects write/cutover flags such as `--cutover`, `--write`, `--dual-write`, `--restart-service` and `--switch-backend`.
- Domain specs validate read method names and reject known write/import/OA secret-prone methods.
- Mismatch output summarizes values by type/key counts/sample keys and SHA-256 hashes rather than storing full payload rows.
- CLI errors are redacted by the tool boundary.
- `--output /dev/null` avoids writing a persistent report artifact into the production release tree.
- No deploy, restart, requeue, repair, replay, `--apply`, direct SQL mutation, DB write, queue mutation, readiness mutation or service mutation is permitted.

## Selected Domains

The selected domains are bounded to read-model-heavy closure gaps and safe runtime settings:

- `app_settings`
- `workbench_pair_relations`
- `no_oa_bank_batches`
- `pending_invoice_commands`
- `workbench_read_models`
- `cost_statistics_read_models`
- `tax_offset_read_models`

The run uses `--limit 3` so any mismatches are capped.

## Commands

### 1. Precheck Health

```bash
ssh finops-prod-root 'set -eu; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
```

### 2. Verify Tool Availability

```bash
ssh finops-prod-root 'set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; cd "$release_src"; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.run_shadow_read_rehearsal --help >/dev/null; echo shadow_read_rehearsal_tool_available'
```

### 3. Run Read-Only Shadow-Read Rehearsal

```bash
ssh finops-prod-root 'set -eu; release_src="$(readlink -f /opt/fin-ops/current/src 2>/dev/null || true)"; if [ ! -d "$release_src/backend/src" ]; then release_src="$(ls -dt /opt/fin-ops/releases/*/src 2>/dev/null | head -1)"; fi; cd "$release_src"; FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1 PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.run_shadow_read_rehearsal --production --json --output /dev/null --primary-backend local_pickle --shadow-backend postgres --domains app_settings,workbench_pair_relations,no_oa_bank_batches,pending_invoice_commands,workbench_read_models,cost_statistics_read_models,tax_offset_read_models --limit 3'
```

If the direct shell lacks the same PostgreSQL configuration as the service runtime, rerun by loading the existing runtime env files without printing or storing any env values:

```bash
ssh finops-prod-root 'set -euo pipefail; release_src="$(systemctl show fin-ops.service -P WorkingDirectory)"; cd "$release_src"; set -a; source /etc/fin-ops/fin-ops.common.env >/dev/null; source /etc/fin-ops/fin-ops.secrets.env >/dev/null; set +a; FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1 PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.run_shadow_read_rehearsal --production --json --output /dev/null --primary-backend local_pickle --shadow-backend postgres --domains app_settings,workbench_pair_relations,no_oa_bank_batches,pending_invoice_commands,workbench_read_models,cost_statistics_read_models,tax_offset_read_models --limit 3'
```

### 4. Postcheck Health

```bash
ssh finops-prod-root 'set -eu; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
```

## Stop Gates

- `/health/ready` is not ready before the rehearsal.
- The deployed runtime lacks `run_shadow_read_rehearsal`.
- The command would require printing or storing secrets, DSNs, tokens, cookies, env secret values or payload rows.
- The command would require write/cutover flags, DB mutation, queue/readiness mutation, service restart, deploy, requeue, repair or worker replay.
- The output contains unredacted payload rows or secret-looking values.

## Expected Evidence

- `/health/ready` ready before and after.
- Tool availability confirmation.
- Rehearsal JSON summary with:
  - `gate_recommendation`
  - `primary_backend`
  - `shadow_backend`
  - domain statuses
  - mismatch counts and severity counts
  - redaction flag
- If the deployed runtime lacks configuration or comparable primary data, classify precisely as `production-evidence-deferred`.

## Result

Completed as `production-evidence-deferred`.

### Precheck

`/health/ready` returned:

```text
{'status': 'ready'}
```

### Tool Availability

The deployed runtime returned:

```text
shadow_read_rehearsal_tool_available
```

### Direct Shell Attempt

The direct shell run failed before rehearsal because it did not have the same PostgreSQL configuration as the service runtime:

```text
ERROR: FIN_OPS_APP_STORAGE_BACKEND=postgres requires FIN_OPS_POSTGRES_DATABASE_URL or DATABASE_URL.
```

Classification: runtime configuration unavailable in the direct root shell. No secrets were printed and no production state was mutated.

### Runtime Env Attempt

The second run loaded the existing service env files without printing or storing env values and executed the selected domains. The tool returned non-zero because `gate_recommendation` was `BLOCKED`, which is expected behavior for mismatch/error evidence.

Summary:

- `gate_recommendation`: `BLOCKED`
- `primary_backend`: `local_pickle`
- `shadow_backend`: `postgres`
- `redacted`: `true`
- `total_domains`: 7
- `compared_domains`: 5
- `matched_domains`: 0
- `mismatched_domains`: 5
- `primary_errors`: 1
- `shadow_errors`: 1
- `severity_counts`: `P0=5`, `P1=5`, `P2=0`, `ignored=0`
- `status_counts`: `mismatched=5`, `primary_error=1`, `shadow_error=1`

Domain results:

| Domain | Status | Evidence |
| --- | --- | --- |
| `app_settings` | `mismatched` | 3 P1 length mismatches for settings collections; values were summarized with scalar hashes only. |
| `workbench_pair_relations` | `mismatched` | 2 P0 `missing_in_primary` mismatches; PostgreSQL contained relation/history data while `local_pickle` primary did not. |
| `no_oa_bank_batches` | `mismatched` | 3 P0 `missing_in_primary` mismatches; PostgreSQL contained audit/batch/schema data while `local_pickle` primary did not. |
| `pending_invoice_commands` | `primary_error` | `KeyError: 'pending_invoice_commands'` from the `local_pickle` primary path. |
| `workbench_read_models` | `shadow_error` | PostgreSQL read hit `QueryCanceled: canceling statement due to statement timeout`. |
| `cost_statistics_read_models` | `mismatched` | 1 P1 `missing_in_primary`; PostgreSQL contained cost read models while `local_pickle` primary did not. |
| `tax_offset_read_models` | `mismatched` | 1 P1 `missing_in_primary`; PostgreSQL contained tax read models while `local_pickle` primary did not. |

Classification:

- The run proves the deployed tool is present, read-only guard is enforceable, runtime env can execute the tool without secret output, and the output is redacted/hash-summary based.
- The run does **not** prove read-model closure because `local_pickle` is not a comparable authoritative primary for current production PostgreSQL runtime; several mismatches are expected from primary absence rather than PostgreSQL read-model failure.
- The `workbench_read_models` timeout is a real high-row evidence gap and should be considered in the next boundary selection.
- No full payload rows, response bodies, env values, DSNs, tokens, cookies or secrets were stored in this file.
- No deploy, restart, requeue, repair, replay, `--apply`, DB write, queue mutation or readiness mutation occurred.

### Postcheck

`/health/ready` returned:

```text
{'status': 'ready'}
```

## Closure Impact

- Shadow-read rehearsal added useful production evidence about tooling availability, guard behavior, redacted reporting and the non-viability of `local_pickle` as a production primary comparator.
- Authenticated API, browser hydration/data, operation-barrier, high-row and module-specific closure remain open.
- Module/global closure remains unclaimed.

## Next Boundary

`planning:post-shadow-read-rehearsal-next-boundary-selection`

#!/usr/bin/env bash
set -Eeuo pipefail

src="$(systemctl show fin-ops.service -P WorkingDirectory)"
printf 'RUN_META src=%s\n' "$src"

COMMON_ENV="${FINOPS_ENV_DIR:-/etc/fin-ops}/fin-ops.common.env"
SECRETS_ENV="${FINOPS_ENV_DIR:-/etc/fin-ops}/fin-ops.secrets.env"
API_PYTHON="${FINOPS_API_PYTHON:-/opt/fin-ops/venv/bin/python}"

set -a
source "$COMMON_ENV"
source "$SECRETS_ENV"
set +a

export PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}"
export FIN_OPS_DATA_DIR="${FIN_OPS_DATA_DIR:-/opt/fin-ops/data}"

cd "$src"
"$API_PYTHON" - <<'PY'
from __future__ import annotations

from copy import deepcopy
import json
from time import perf_counter

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.read_models import (
    PostgresReadModelRepository,
    _aggregate_workbench_all_scope_payload,
    _read_model_payload,
    _source_version_value,
    _workbench_active_relation_claim_keys_for_groups,
    _workbench_group_payload_for_rows,
    _workbench_group_row_records,
    text,
)


connection = PostgresConnection(PostgresSettings.from_env())
connection.set_statement_timeout_ms(5000)
repository = PostgresReadModelRepository(connection)
marks: list[dict[str, object]] = []


def mark(name: str, started: float, **extra: object) -> None:
    payload = {"step": name, "duration_ms": round((perf_counter() - started) * 1000, 3)}
    payload.update(extra)
    marks.append(payload)


overall = perf_counter()

started = perf_counter()
consistency_failures = repository._workbench_generation_consistency_failures(connection, include_all=False)
mark("consistency_check", started, failure_count=len(consistency_failures))
if consistency_failures:
    print(
        "SECTION "
        + json.dumps(
            {
                "name": "workbench_all_shadow_profile",
                "status": "blocked_by_parent_consistency",
                "steps": marks,
                "failure_count": len(consistency_failures),
                "failures": consistency_failures[:5],
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    )
    raise SystemExit(0)

started = perf_counter()
group_rows = connection.fetch_all(
    """
    select
      g.scope_key,
      g.scope_month,
      g.zone,
      g.group_id,
      g.payload,
      g.source_versions,
      g.generated_at::text as generated_at
    from read_model.workbench_groups g
    join read_model.workbench_generations gen
      on gen.generation_id = g.generation_id
     and gen.scope_key = g.scope_key
     and gen.tenant_id = 'default'
     and gen.status = 'active'
    where g.scope_key <> 'all'
    order by g.scope_month desc nulls last, g.zone, g.group_id, g.updated_at desc
    """
)
mark("fetch_active_month_groups", started, row_count=len(group_rows))

started = perf_counter()
groups: list[dict[str, object]] = []
max_generated_at = ""
max_source_version: int | None = None
for row in group_rows:
    group = _read_model_payload(row)
    if not isinstance(group, dict):
        continue
    normalized_group = deepcopy(group)
    normalized_group["_source_scope_key"] = text(row.get("scope_key"))
    normalized_group["_source_scope_month"] = text(row.get("scope_month"))
    normalized_group.setdefault("group_id", text(row.get("group_id")))
    normalized_group["zone"] = text(row.get("zone")) or normalized_group.get("zone") or "open"
    normalized_group["scope_key"] = "all"
    normalized_group["month"] = "all"
    normalized_group["scope_month"] = None
    groups.append(normalized_group)
    generated_at = text(row.get("generated_at")) or ""
    if generated_at > max_generated_at:
        max_generated_at = generated_at
    source_version = _source_version_value(row.get("source_versions"))
    if source_version is not None:
        max_source_version = max(source_version, max_source_version or source_version)
mark("normalize_groups", started, group_count=len(groups))

started = perf_counter()
(
    canonical_paired_row_keys,
    canonical_paired_identity_keys,
    canonical_relation_claims_by_row_key,
) = _workbench_active_relation_claim_keys_for_groups(connection, groups)
mark(
    "active_relation_claim_keys",
    started,
    paired_row_key_count=len(canonical_paired_row_keys),
    paired_identity_key_count=len(canonical_paired_identity_keys),
    claim_row_key_count=len(canonical_relation_claims_by_row_key),
)

started = perf_counter()
aggregate_payload = _aggregate_workbench_all_scope_payload(
    groups,
    paired_row_keys=canonical_paired_row_keys,
    paired_identity_keys=canonical_paired_identity_keys,
    canonical_relation_claims_by_row_key=canonical_relation_claims_by_row_key,
)
mark("aggregate_payload", started)

started = perf_counter()
workbench_rows = list(repository._iter_workbench_rows(aggregate_payload))
workbench_groups = list(repository._iter_workbench_groups(aggregate_payload))
mark("iter_rows_and_groups", started, row_count=len(workbench_rows), group_count=len(workbench_groups))

started = perf_counter()
group_row_count = 0
for group in workbench_groups:
    group_row_count += len(_workbench_group_row_records(_workbench_group_payload_for_rows(group)))
mark("build_group_row_records", started, group_row_count=group_row_count)

print(
    "SECTION "
    + json.dumps(
        {
            "name": "workbench_all_shadow_profile",
            "status": "ok",
            "total_duration_ms": round((perf_counter() - overall) * 1000, 3),
            "max_generated_at": max_generated_at,
            "max_source_version": max_source_version,
            "steps": marks,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
)
PY

from __future__ import annotations


def pending_oa_application_time_sql(alias: str) -> str:
    """Return the canonical pending-OA application time SQL expression."""

    return f"""coalesce(
        nullif(btrim({alias}.source_payload#>>'{{detail_fields,申请时间}}'), ''),
        nullif(btrim({alias}.source_payload#>>'{{detail_fields,申请日期}}'), ''),
        nullif(btrim({alias}.source_payload->>'application_time'), ''),
        nullif(btrim({alias}.source_payload->>'application_date'), '')
    )"""


def pending_oa_application_date_sql(alias: str) -> str:
    application_time = pending_oa_application_time_sql(alias)
    return f"""case
        when ({application_time}) ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}'
        then substring(({application_time}) from 1 for 10)::date
        else null::date
    end"""

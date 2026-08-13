from __future__ import annotations

from dataclasses import fields
from datetime import date, datetime
import re
from typing import Any

from fin_ops_platform.services.oa_adapter import OAApplicationRecord, OAReadStatus
from fin_ops_platform.services.postgres_repositories.common import (
    decimal_text,
    jsonb,
    month_start,
    row_payload,
    run_in_transaction,
    serialize_value,
    text,
)
from fin_ops_platform.services.postgres_repositories.oa_attachment_identity_bridge import (
    reconcile_oa_attachment_cache_identity_sources,
)


OA_PROJECTION_SYNC_VERSION = "2026-08-14-approved-at-v4"
COMPLETED_WORKFLOW_STATUS_ALIASES = frozenset(
    {
        "completed",
        "已完成",
        "approved",
        "APPROVED",
        "Approved",
        "2",
    }
)
COMPLETED_WORKFLOW_STATUS_SQL = (
    "(workflow_status is null or workflow_status = '' "
    "or workflow_status in ('completed', '已完成', 'approved', 'APPROVED', 'Approved', '2'))"
)


def is_completed_workflow_status(value: Any) -> bool:
    normalized = text(value)
    return not normalized or normalized in COMPLETED_WORKFLOW_STATUS_ALIASES


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _record_application_date(record: OAApplicationRecord) -> str | None:
    detail_fields = record.detail_fields if isinstance(record.detail_fields, dict) else {}
    for value in (
        detail_fields.get("申请日期"),
        detail_fields.get("申请时间"),
        getattr(record, "application_date", None),
        getattr(record, "apply_time", None),
        record.month,
    ):
        normalized = text(value)
        if not normalized or normalized in {"—", "--", "None"}:
            continue
        match = re.match(r"^(\d{4}-\d{2}-\d{2})", normalized)
        if match:
            return match.group(1)
        month = month_start(normalized)
        if month:
            return month
    return None


def _record_completed_at(record: OAApplicationRecord) -> str | None:
    detail_fields = record.detail_fields if isinstance(record.detail_fields, dict) else {}
    for value in (
        record.completed_at,
        detail_fields.get("审批完成时间"),
    ):
        normalized = text(value)
        if normalized and normalized not in {"—", "--", "None"}:
            return normalized
    return None


def _first_present(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


class PostgresOAProjectionRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def upsert_application_records(self, records: list[OAApplicationRecord], *, scope_key: str) -> int:
        normalized_records = [record for record in list(records or []) if isinstance(record, OAApplicationRecord)]
        if not normalized_records:
            self._record_watermark(scope_key=scope_key, status="succeeded", upserted_count=0)
            return 0

        changed_count = 0

        def write(connection: Any) -> None:
            nonlocal changed_count
            changed_row_ids: list[str] = []
            for record in normalized_records:
                payload = serialize_value(record)
                application_row = connection.fetch_one(
                    """
                    insert into app.oa_applications(
                        oa_source_id, form_id, row_id, form_type, workflow_no, status, workflow_status,
                        applicant, application_date, approved_at, project_name, amount, currency,
                        scope_month, normalized_payload, raw_payload, synced_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s::date, %s::timestamptz, %s, %s, %s, %s::date, %s, %s, now())
                    on conflict (row_id) do update set
                        oa_source_id = excluded.oa_source_id,
                        form_id = excluded.form_id,
                        form_type = excluded.form_type,
                        workflow_no = excluded.workflow_no,
                        status = excluded.status,
                        workflow_status = excluded.workflow_status,
                        applicant = excluded.applicant,
                        application_date = excluded.application_date,
                        approved_at = excluded.approved_at,
                        project_name = excluded.project_name,
                        amount = excluded.amount,
                        currency = excluded.currency,
                        scope_month = excluded.scope_month,
                        normalized_payload = excluded.normalized_payload,
                        raw_payload = excluded.raw_payload,
                        synced_at = now(),
                        updated_at = now()
                    where (
                        app.oa_applications.oa_source_id,
                        app.oa_applications.form_id,
                        app.oa_applications.form_type,
                        app.oa_applications.workflow_no,
                        app.oa_applications.status,
                        app.oa_applications.workflow_status,
                        app.oa_applications.applicant,
                        app.oa_applications.application_date,
                        app.oa_applications.approved_at,
                        app.oa_applications.project_name,
                        app.oa_applications.amount,
                        app.oa_applications.currency,
                        app.oa_applications.scope_month,
                        app.oa_applications.normalized_payload,
                        app.oa_applications.raw_payload
                    ) is distinct from (
                        excluded.oa_source_id,
                        excluded.form_id,
                        excluded.form_type,
                        excluded.workflow_no,
                        excluded.status,
                        excluded.workflow_status,
                        excluded.applicant,
                        excluded.application_date,
                        excluded.approved_at,
                        excluded.project_name,
                        excluded.amount,
                        excluded.currency,
                        excluded.scope_month,
                        excluded.normalized_payload,
                        excluded.raw_payload
                    )
                    returning id::text as application_id
                    """,
                    (
                        record.id,
                        self._form_id_for_record(record),
                        record.id,
                        record.apply_type,
                        record.case_id,
                        record.section,
                        text(record.workflow_status),
                        record.applicant,
                        _record_application_date(record),
                        _record_completed_at(record),
                        record.project_name,
                        decimal_text(record.amount),
                        "CNY",
                        month_start(record.month),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
                application_id = text((application_row or {}).get("application_id"))
                if not application_id:
                    continue
                changed_count += 1
                changed_row_ids.append(record.id)
                self._replace_application_items(connection, application_id=application_id, record=record)
                self._replace_application_attachments(connection, application_id=application_id, record=record)
            if changed_row_ids:
                reconcile_oa_attachment_cache_identity_sources(
                    connection,
                    oa_row_ids=changed_row_ids,
                )
            self._migrate_legacy_row_references(connection, self._legacy_row_id_alias_pairs(normalized_records))
            self._record_watermark(
                scope_key=scope_key,
                status="succeeded",
                upserted_count=changed_count,
                connection=connection,
            )

        run_in_transaction(self._connection, write)
        return changed_count

    def delete_stale_completed_application_records(
        self,
        *,
        scope_key: str,
        records: list[OAApplicationRecord],
        scanned_records: list[OAApplicationRecord],
    ) -> list[str]:
        months = self._months_for_scope(scope_key=scope_key, records=scanned_records)
        if not months:
            return []
        incoming_row_ids = sorted({str(record.id or "").strip() for record in records if str(record.id or "").strip()})

        def write(connection: Any) -> list[str]:
            if incoming_row_ids:
                rows = connection.fetch_all(
                    """
                    with stale as (
                        select oa.id, oa.row_id, oa.scope_month
                        from app.oa_applications oa
                        where oa.scope_month = any(%s::date[])
                          and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
                          and not (oa.row_id = any(%s::text[]))
                          and not exists (
                              select 1
                              from app.manual_oa_imports manual
                              where manual.row_id = oa.row_id
                                and manual.status = 'active'
                          )
                    ),
                    deleted_items as (
                        delete from app.oa_application_items item
                        using stale
                        where item.oa_application_id = stale.id
                        returning item.id
                    ),
                    deleted_attachments as (
                        delete from app.oa_attachments attachment
                        using stale
                        where attachment.oa_application_id = stale.id
                        returning attachment.id
                    )
                    delete from app.oa_applications oa
                    using stale
                    where oa.id = stale.id
                    returning stale.row_id
                    """,
                    (months, incoming_row_ids),
                )
                return [row_id for row in rows if (row_id := text(row.get("row_id")))]
            rows = connection.fetch_all(
                """
                with stale as (
                    select oa.id, oa.row_id, oa.scope_month
                    from app.oa_applications oa
                    where oa.scope_month = any(%s::date[])
                      and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
                      and not exists (
                          select 1
                          from app.manual_oa_imports manual
                          where manual.row_id = oa.row_id
                            and manual.status = 'active'
                      )
                ),
                deleted_items as (
                    delete from app.oa_application_items item
                    using stale
                    where item.oa_application_id = stale.id
                    returning item.id
                ),
                deleted_attachments as (
                    delete from app.oa_attachments attachment
                    using stale
                    where attachment.oa_application_id = stale.id
                    returning attachment.id
                )
                delete from app.oa_applications oa
                using stale
                where oa.id = stale.id
                returning stale.row_id
                """,
                (months,),
            )
            return [row_id for row in rows if (row_id := text(row.get("row_id")))]

        return run_in_transaction(self._connection, write) or []

    def delete_non_completed_application_records(
        self,
        *,
        scope_key: str,
        records: list[OAApplicationRecord],
    ) -> list[str]:
        months = self._months_for_scope(scope_key=scope_key, records=records)
        if not months:
            return []

        def write(connection: Any) -> list[str]:
            rows = connection.fetch_all(
                """
                with stale as (
                    select oa.id, oa.row_id, oa.scope_month
                    from app.oa_applications oa
                    where oa.scope_month = any(%s::date[])
                      and coalesce(nullif(oa.workflow_status, ''), 'completed') <> 'completed'
                      and not exists (
                          select 1
                          from app.manual_oa_imports manual
                          where manual.row_id = oa.row_id
                            and manual.status = 'active'
                      )
                ),
                deleted_items as (
                    delete from app.oa_application_items item
                    using stale
                    where item.oa_application_id = stale.id
                    returning item.id
                ),
                deleted_attachments as (
                    delete from app.oa_attachments attachment
                    using stale
                    where attachment.oa_application_id = stale.id
                    returning attachment.id
                )
                delete from app.oa_applications oa
                using stale
                where oa.id = stale.id
                returning stale.row_id
                """,
                (months,),
            )
            return [row_id for row in rows if (row_id := text(row.get("row_id")))]

        return run_in_transaction(self._connection, write) or []

    @staticmethod
    def _months_for_scope(*, scope_key: str, records: list[OAApplicationRecord]) -> list[str]:
        normalized_scope_key = text(scope_key) or "all"
        if normalized_scope_key != "all":
            scope_month = month_start(normalized_scope_key)
            return [scope_month] if scope_month else []
        return sorted({
            record_month
            for record in list(records or [])
            if (record_month := month_start(record.month))
        })

    def _migrate_legacy_row_references(self, connection: Any, alias_pairs: dict[str, str]) -> None:
        if not alias_pairs:
            return
        old_row_ids = sorted(alias_pairs)
        new_row_ids = [alias_pairs[old_row_id] for old_row_id in old_row_ids]
        self._replace_row_id_array_references(
            connection,
            table_name="app.workbench_pair_relations",
            alias_pairs=alias_pairs,
            where_sql="row_ids && %s::text[]",
            where_params=(old_row_ids,),
        )
        self._replace_row_id_array_references(
            connection,
            table_name="app.workbench_exception_cases",
            alias_pairs=alias_pairs,
            where_sql="row_ids && %s::text[]",
            where_params=(old_row_ids,),
        )
        connection.execute(
            """
            update app.workbench_row_overrides override
            set row_id = alias.new_row_id,
                changed_row_ids = array[alias.new_row_id]::text[],
                override_payload = jsonb_set(
                    jsonb_set(override.override_payload, '{row_id}', to_jsonb(alias.new_row_id), true),
                    '{changed_row_ids}', to_jsonb(array[alias.new_row_id]::text[]),
                    true
                ),
                raw_payload = jsonb_set(
                    jsonb_set(
                        jsonb_set(
                            jsonb_set(override.raw_payload, '{normalized_payload,row_id}', to_jsonb(alias.new_row_id), true),
                            '{normalized_payload,changed_row_ids}',
                            to_jsonb(array[alias.new_row_id]::text[]),
                            true
                        ),
                        '{row_id}',
                        to_jsonb(alias.new_row_id),
                        true
                    ),
                    '{changed_row_ids}',
                    to_jsonb(array[alias.new_row_id]::text[]),
                    true
                ),
                updated_at = now()
            from (
                select *
                from unnest(%s::text[], %s::text[]) as alias(old_row_id, new_row_id)
            ) alias
            where override.row_id = alias.old_row_id
              and not exists (
                  select 1
                  from app.workbench_row_overrides existing
                  where existing.row_id = alias.new_row_id
                    and existing.row_type = override.row_type
              )
            """,
            (old_row_ids, new_row_ids),
        )

    @staticmethod
    def _replace_row_id_array_references(
        connection: Any,
        *,
        table_name: str,
        alias_pairs: dict[str, str],
        where_sql: str,
        where_params: tuple[Any, ...],
    ) -> None:
        old_row_ids = sorted(alias_pairs)
        new_row_ids = [alias_pairs[old_row_id] for old_row_id in old_row_ids]
        connection.execute(
            f"""
            with replacement as (
                select relation.id,
                       (
                           select coalesce(array_agg(deduped.row_id order by deduped.first_position), array[]::text[])
                           from (
                               select replaced.row_id, min(replaced.position) as first_position
                               from (
                                   select coalesce(alias.new_row_id, row_value.row_id) as row_id,
                                          row_value.position
                                   from unnest(relation.row_ids) with ordinality as row_value(row_id, position)
                                   left join (
                                       select *
                                       from unnest(%s::text[], %s::text[]) as alias(old_row_id, new_row_id)
                                   ) alias on alias.old_row_id = row_value.row_id
                               ) replaced
                               group by replaced.row_id
                           ) deduped
                       ) as row_ids
                from {table_name} relation
                where {where_sql}
            )
            update {table_name} relation
            set row_ids = replacement.row_ids,
                raw_payload = jsonb_set(
                    jsonb_set(relation.raw_payload, '{{normalized_payload,row_ids}}', to_jsonb(replacement.row_ids), true),
                    '{{row_ids}}',
                    to_jsonb(replacement.row_ids),
                    true
                ),
                updated_at = now()
            from replacement
            where relation.id = replacement.id
            """,
            (old_row_ids, new_row_ids, *where_params),
        )

    @staticmethod
    def _legacy_row_id_alias_pairs(records: list[OAApplicationRecord]) -> dict[str, str]:
        pairs: dict[str, str] = {}
        for record in records:
            row_id = str(getattr(record, "id", "") or "").strip()
            if not row_id.startswith("oa-exp-"):
                continue
            body = row_id.removeprefix("oa-exp-")
            if not body or re.search(r"-\d+$", body):
                continue
            legacy_suffixes: set[int] = set()
            for index, item in enumerate(list(getattr(record, "expense_items", []) or []), start=1):
                legacy_suffixes.add(index)
                if isinstance(item, dict):
                    row_index = text(item.get("row_index"))
                    if row_index and row_index.isdigit():
                        legacy_suffixes.add(int(row_index) + 1)
            if not legacy_suffixes:
                legacy_suffixes.add(1)
            for suffix in sorted(legacy_suffixes):
                pairs[f"{row_id}-{suffix}"] = row_id
        return pairs

    def _replace_application_items(self, connection: Any, *, application_id: str, record: OAApplicationRecord) -> None:
        connection.execute("delete from app.oa_application_items where oa_application_id = %s::uuid", (application_id,))
        for index, item in enumerate(list(record.expense_items or [])):
            if not isinstance(item, dict):
                continue
            payload = serialize_value(item)
            row_id = text(
                payload.get("expense_item_id")
                or payload.get("row_id")
                or payload.get("item_id")
                or f"{record.id}:item:{index + 1}"
            )
            connection.execute(
                """
                insert into app.oa_application_items(
                    oa_application_id, oa_source_id, form_id, row_id, item_type, item_no,
                    amount, tax_amount, project_id, project_name, normalized_payload, raw_payload
                )
                values (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    application_id,
                    record.id,
                    self._form_id_for_record(record),
                    row_id,
                    text(payload.get("item_type") or payload.get("expense_type") or record.expense_type),
                    text(payload.get("item_no") or payload.get("row_index") or str(index)),
                    decimal_text(
                        _first_present(
                            payload.get("settlement_amount"),
                            payload.get("amount"),
                            payload.get("total_with_tax"),
                        )
                    ),
                    decimal_text(payload.get("tax_amount")),
                    text(payload.get("project_id")),
                    text(payload.get("project_name") or record.project_name),
                    jsonb(payload),
                    jsonb({"normalized_payload": payload}),
                ),
            )

    def _replace_application_attachments(self, connection: Any, *, application_id: str, record: OAApplicationRecord) -> None:
        connection.execute("delete from app.oa_attachments where oa_application_id = %s::uuid", (application_id,))
        for attachment in self._attachment_payloads_for_record(record):
            source_attachment_key = text(attachment.get("source_attachment_key"))
            if not source_attachment_key:
                continue
            connection.execute(
                """
                insert into app.oa_attachments(
                    oa_application_id, oa_source_id, form_id, row_id, source_attachment_key,
                    filename, content_type, size_bytes, source_modified_at, normalized_payload, raw_payload
                )
                values (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s::timestamptz, %s, %s)
                on conflict (source_attachment_key) do update set
                    oa_application_id = excluded.oa_application_id,
                    oa_source_id = excluded.oa_source_id,
                    form_id = excluded.form_id,
                    row_id = excluded.row_id,
                    filename = excluded.filename,
                    content_type = excluded.content_type,
                    size_bytes = excluded.size_bytes,
                    source_modified_at = excluded.source_modified_at,
                    normalized_payload = excluded.normalized_payload,
                    raw_payload = excluded.raw_payload
                """,
                (
                    application_id,
                    record.id,
                    self._form_id_for_record(record),
                    text(attachment.get("row_id")),
                    source_attachment_key,
                    text(
                        attachment.get("filename")
                        or attachment.get("fileName")
                        or attachment.get("source_attachment_name")
                        or attachment.get("attachment_name")
                        or attachment.get("name")
                    ),
                    text(attachment.get("content_type") or attachment.get("mime_type")),
                    _int_or_none(attachment.get("size_bytes") or attachment.get("source_size_bytes")),
                    text(attachment.get("source_modified_at") or attachment.get("modified_at")),
                    jsonb(serialize_value(attachment)),
                    jsonb({"normalized_payload": serialize_value(attachment)}),
                ),
            )

    def _attachment_payloads_for_record(self, record: OAApplicationRecord) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []

        def add(raw: Any, *, source_expense_item_id: Any = None, source_expense_row_index: Any = None, fallback_index: int = 0) -> None:
            if not isinstance(raw, dict):
                return
            payload = dict(serialize_value(raw))
            payload.setdefault("source_expense_item_id", source_expense_item_id)
            payload.setdefault("source_expense_row_index", source_expense_row_index)
            source_key = text(
                payload.get("source_attachment_key")
                or payload.get("attachment_key")
                or payload.get("file_id")
                or payload.get("object_id")
            )
            if not source_key:
                name = text(
                    payload.get("source_attachment_name")
                    or payload.get("attachment_name")
                    or payload.get("fileName")
                    or payload.get("filename")
                    or payload.get("filePath")
                )
                source_key = f"{record.id}:attachment:{source_expense_item_id or 'root'}:{fallback_index}:{name or 'unnamed'}"
            payload["source_attachment_key"] = source_key
            payload.setdefault("source_attachment_name", payload.get("fileName") or payload.get("filename"))
            payload.setdefault("attachment_name", payload.get("source_attachment_name"))
            payload.setdefault("row_id", text(source_expense_item_id) or record.id)
            attachments.append(payload)

        for index, evidence in enumerate(list(record.attachment_invoices or [])):
            add(evidence, fallback_index=index)
        for index, evidence in enumerate(list(record.attachment_evidences or [])):
            add(evidence, fallback_index=index)
        for index, artifact in enumerate(list(record.attachment_artifacts or [])):
            add(artifact, fallback_index=index)
        for item_index, item in enumerate(list(record.expense_items or [])):
            if not isinstance(item, dict):
                continue
            source_expense_item_id = item.get("expense_item_id") or item.get("row_id") or f"{record.id}:item:{item_index + 1}"
            source_expense_row_index = item.get("row_index") or str(item_index)
            offset = len(attachments)
            for evidence_index, evidence in enumerate(list(item.get("attachment_invoices") or [])):
                add(
                    evidence,
                    source_expense_item_id=source_expense_item_id,
                    source_expense_row_index=source_expense_row_index,
                    fallback_index=offset + evidence_index,
                )
            offset = len(attachments)
            for evidence_index, evidence in enumerate(list(item.get("attachment_evidences") or [])):
                add(
                    evidence,
                    source_expense_item_id=source_expense_item_id,
                    source_expense_row_index=source_expense_row_index,
                    fallback_index=offset + evidence_index,
                )
            offset = len(attachments)
            for evidence_index, artifact in enumerate(list(item.get("attachment_artifacts") or [])):
                add(
                    artifact,
                    source_expense_item_id=source_expense_item_id,
                    source_expense_row_index=source_expense_row_index,
                    fallback_index=offset + evidence_index,
                )
            offset = len(attachments)
            for file_index, file_payload in enumerate(list(item.get("attachment_files") or [])):
                add(
                    file_payload,
                    source_expense_item_id=source_expense_item_id,
                    source_expense_row_index=source_expense_row_index,
                    fallback_index=offset + file_index,
                )
        deduped: dict[str, dict[str, Any]] = {}
        for attachment in attachments:
            source_key = text(attachment.get("source_attachment_key"))
            if source_key:
                deduped[source_key] = attachment
        return list(deduped.values())

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        normalized_month = str(month or "").strip()
        if normalized_month == "all":
            return self.list_all_application_records()
        rows = self._connection.fetch_all(
            """
            select row_id, workflow_status, normalized_payload, raw_payload
            from app.oa_applications
            where scope_month = %s::date
              and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
            order by row_id
            """,
            (month_start(normalized_month),),
        )
        return self._records_from_rows(rows)

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        rows = self._connection.fetch_all(
            """
            select row_id, workflow_status, normalized_payload, raw_payload
            from app.oa_applications
            where """ + COMPLETED_WORKFLOW_STATUS_SQL + """
            order by scope_month, row_id
            """
        )
        return self._records_from_rows(rows)

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        normalized_row_ids = [row_id for row_id in [text(row_id) for row_id in list(row_ids or [])] if row_id]
        if not normalized_row_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select row_id, workflow_status, normalized_payload, raw_payload
            from app.oa_applications
            where row_id = any(%s)
              and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
            order by row_id
            """,
            (normalized_row_ids,),
        )
        records_by_id = {record.id: record for record in self._records_from_rows(rows)}
        return [records_by_id[row_id] for row_id in normalized_row_ids if row_id in records_by_id]

    def list_available_months(self) -> list[str]:
        rows = self._connection.fetch_all(
            """
            select distinct to_char(scope_month, 'YYYY-MM') as month
            from app.oa_applications
            where scope_month is not null
              and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
            order by month
            """
        )
        return [month for row in rows if (month := text(row.get("month")))]

    def prune_records_before(self, cutoff_month: str) -> list[str]:
        normalized_cutoff_month = text(cutoff_month)
        if not normalized_cutoff_month:
            return []

        def write(connection: Any) -> list[str]:
            rows = connection.fetch_all(
                """
                with stale as (
                    select oa.id, oa.row_id, oa.scope_month
                    from app.oa_applications oa
                    where oa.scope_month < %s::date
                      and not exists (
                          select 1
                          from app.manual_oa_imports manual
                          where manual.row_id = oa.row_id
                            and manual.status = 'active'
                      )
                ),
                deleted_items as (
                    delete from app.oa_application_items item
                    using stale
                    where item.oa_application_id = stale.id
                    returning item.id
                ),
                deleted_attachments as (
                    delete from app.oa_attachments attachment
                    using stale
                    where attachment.oa_application_id = stale.id
                    returning attachment.id
                )
                delete from app.oa_applications oa
                using stale
                where oa.id = stale.id
                returning to_char(stale.scope_month, 'YYYY-MM') as month
                """,
                (month_start(normalized_cutoff_month),),
            )
            return sorted({month for row in rows if (month := text(row.get("month")))})

        return run_in_transaction(self._connection, write) or []

    def get_read_status(self) -> OAReadStatus:
        return OAReadStatus(code="ready", message="OA projection ready")

    def build_dashboard(self) -> dict[str, Any]:
        summary = self._connection.fetch_one(
            """
            select
                count(*)::int as document_count,
                count(distinct nullif(project_name, ''))::int as project_count
            from app.oa_applications
            """
        ) or {}
        run_summary = self._connection.fetch_one(
            """
            select count(*)::int as run_count
            from app.oa_sync_runs
            where sync_type = 'oa_projection'
            """
        ) or {}
        latest_run = self._connection.fetch_one(
            """
            select id::text as id
            from app.oa_sync_runs
            where sync_type = 'oa_projection'
            order by started_at desc, id desc
            limit 1
            """
        ) or {}
        projects = self._connection.fetch_all(
            """
            select project_name
            from app.oa_applications
            where nullif(project_name, '') is not null
            group by project_name
            order by project_name
            limit 100
            """
        )
        documents = self._connection.fetch_all(
            """
            select row_id, form_id, form_type, workflow_no, status, workflow_status, applicant, project_name, amount, scope_month
            from app.oa_applications
            order by scope_month desc nulls last, row_id
            limit 100
            """
        )
        return {
            "source_system": "oa",
            "adapter": "postgres_oa_projection",
            "supported_scopes": ["all", "payment_requests", "expense_claims"],
            "summary": {
                "mapping_count": 0,
                "project_count": int(summary.get("project_count") or 0),
                "document_count": int(summary.get("document_count") or 0),
                "run_count": int(run_summary.get("run_count") or 0),
                "latest_run_id": text(latest_run.get("id")),
            },
            "runs": self.list_sync_runs(limit=20),
            "mappings": [],
            "projects": [
                {"project_name": text(row.get("project_name"))}
                for row in projects
                if text(row.get("project_name"))
            ],
            "documents": [
                {
                    "id": text(row.get("row_id")),
                    "form_id": text(row.get("form_id")),
                    "form_type": text(row.get("form_type")),
                    "form_no": text(row.get("workflow_no")),
                    "status": text(row.get("status")),
                    "workflow_status": text(row.get("workflow_status")),
                    "applicant": text(row.get("applicant")),
                    "project_name": text(row.get("project_name")),
                    "amount": decimal_text(row.get("amount")),
                    "scope_month": row.get("scope_month").isoformat() if row.get("scope_month") else None,
                }
                for row in documents
            ],
        }

    def list_sync_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select
                id::text as id,
                sync_type,
                status,
                started_at,
                finished_at,
                scanned_count,
                upserted_count,
                skipped_count,
                error_count,
                last_error,
                payload,
                raw_payload
            from app.oa_sync_runs
            where sync_type = 'oa_projection'
            order by started_at desc, id desc
            limit %s
            """,
            (max(1, int(limit or 1)),),
        )
        return [self._sync_run_from_row(row) for row in rows]

    def get_sync_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._connection.fetch_one(
            """
            select
                id::text as id,
                sync_type,
                status,
                started_at,
                finished_at,
                scanned_count,
                upserted_count,
                skipped_count,
                error_count,
                last_error,
                payload,
                raw_payload
            from app.oa_sync_runs
            where id = %s::uuid
              and sync_type = 'oa_projection'
            """,
            (text(run_id),),
        )
        return self._sync_run_from_row(row) if row else None

    def record_sync_run(self, payload: dict[str, object]) -> None:
        normalized_payload = serialize_value(payload if isinstance(payload, dict) else {})
        self._connection.execute(
            """
            insert into app.oa_sync_runs(
                sync_type, status, finished_at, scanned_count, upserted_count,
                skipped_count, error_count, last_error, payload, raw_payload
            )
            values (%s, %s, now(), %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                text(normalized_payload.get("sync_type")) or "oa_projection",
                text(normalized_payload.get("status")) or "succeeded",
                int(normalized_payload.get("scanned_count") or 0),
                int(normalized_payload.get("upserted_count") or 0),
                int(normalized_payload.get("skipped_count") or 0),
                int(normalized_payload.get("error_count") or 0),
                text(normalized_payload.get("last_error")),
                jsonb(normalized_payload),
                jsonb({"normalized_payload": normalized_payload}),
            ),
        )

    def _record_watermark(
        self,
        *,
        scope_key: str,
        status: str,
        upserted_count: int,
        connection: Any | None = None,
    ) -> None:
        target = connection or self._connection
        payload = {"scope_key": scope_key, "upserted_count": upserted_count}
        target.execute(
            """
            insert into app.oa_sync_watermarks(sync_key, form_id, last_success_at, status, payload, raw_payload)
            values (%s, %s, now(), %s, %s, %s)
            on conflict (sync_key) do update set
                last_success_at = excluded.last_success_at,
                status = excluded.status,
                payload = excluded.payload,
                raw_payload = excluded.raw_payload,
                version = app.oa_sync_watermarks.version + 1,
                updated_at = now()
            """,
            (
                f"projection:{text(scope_key) or 'all'}",
                text(scope_key),
                status,
                jsonb(payload),
                jsonb({"normalized_payload": payload}),
            ),
        )

    @staticmethod
    def _form_id_for_record(record: OAApplicationRecord) -> str:
        row_id = str(record.id or "")
        if row_id.startswith("oa-pay-"):
            return "payment_request"
        if row_id.startswith("oa-exp-"):
            return "expense_claim"
        return str(record.apply_type or "oa_application")

    @classmethod
    def _records_from_rows(cls, rows: list[dict[str, Any]]) -> list[OAApplicationRecord]:
        records: list[OAApplicationRecord] = []
        for row in list(rows or []):
            payload = row_payload(row, "normalized_payload", "payload", "raw_payload")
            if not isinstance(payload, dict):
                continue
            if "workflow_status" not in payload and text(row.get("workflow_status")):
                payload = dict(payload)
                payload["workflow_status"] = text(row.get("workflow_status"))
            records.append(cls._record_from_payload(payload, row_id=text(row.get("row_id"))))
        return records

    @staticmethod
    def _record_from_payload(payload: dict[str, Any], *, row_id: str | None = None) -> OAApplicationRecord:
        data = serialize_value(payload)
        field_names = {field.name for field in fields(OAApplicationRecord)}
        kwargs = {name: data.get(name) for name in field_names if name in data}
        kwargs.setdefault("id", row_id or text(data.get("id")) or "oa-unknown")
        kwargs.setdefault("month", text(data.get("month")) or "all")
        stored_section = (text(data.get("section")) or "").lower()
        if stored_section in {"", "open"}:
            stored_section = "unpaired"
        if stored_section not in {"paired", "unpaired"}:
            raise ValueError(f"Unsupported stored OA Workbench section: {data.get('section')!r}")
        kwargs["section"] = stored_section
        kwargs.setdefault("case_id", data.get("case_id"))
        kwargs.setdefault("applicant", text(data.get("applicant")) or "")
        kwargs.setdefault("project_name", text(data.get("project_name")) or "--")
        kwargs.setdefault("apply_type", text(data.get("apply_type")) or "")
        kwargs.setdefault("amount", text(data.get("amount")) or "0")
        kwargs.setdefault("counterparty_name", text(data.get("counterparty_name")) or "")
        kwargs.setdefault("reason", text(data.get("reason")) or "")
        kwargs.setdefault("relation_code", text(data.get("relation_code")) or "pending_match")
        kwargs.setdefault("relation_label", text(data.get("relation_label")) or "待找流水与发票")
        kwargs.setdefault("relation_tone", text(data.get("relation_tone")) or "warn")
        return OAApplicationRecord(**kwargs)

    @staticmethod
    def _first_text(*values: Any) -> str | None:
        for value in values:
            normalized = text(value)
            if normalized:
                return normalized
        return None

    @staticmethod
    def _format_datetime(value: Any) -> str | None:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return text(value)

    @staticmethod
    def _sync_run_from_row(row: dict[str, Any]) -> dict[str, Any]:
        payload = row_payload(row, "payload", "raw_payload")
        scope_key = text(payload.get("scope_key")) if isinstance(payload, dict) else ""
        return {
            "id": text(row.get("id")),
            "source_system": "oa",
            "scope": scope_key or "all",
            "triggered_by": text(payload.get("triggered_by")) if isinstance(payload, dict) else None,
            "status": text(row.get("status")) or "unknown",
            "pulled_count": int(row.get("scanned_count") or 0),
            "success_count": int(row.get("upserted_count") or 0),
            "failed_count": int(row.get("error_count") or 0),
            "skipped_count": int(row.get("skipped_count") or 0),
            "retry_of_run_id": text(payload.get("retry_run_id")) if isinstance(payload, dict) else None,
            "started_at": row.get("started_at").isoformat() if row.get("started_at") else None,
            "finished_at": row.get("finished_at").isoformat() if row.get("finished_at") else None,
            "last_error": text(row.get("last_error")),
            "issue_count": int(row.get("error_count") or 0),
            "payload": serialize_value(payload if isinstance(payload, dict) else {}),
        }


class PostgresOAWorkflowRepository:
    """Read completed and admitted in-progress OA through one canonical port."""

    def __init__(self, connection: Any, *, tenant_id: str = "default") -> None:
        self._connection = connection
        self._tenant_id = text(tenant_id) or "default"

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        normalized_month = text(month)
        if normalized_month == "all":
            return self.list_all_application_records()
        return self._records(
            """
            with workflow_facts as (
                select row_id, 'completed'::text as workflow_status,
                       normalized_payload, raw_payload, 0 as source_priority
                from app.oa_applications
                where scope_month = %s::date
                  and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
                union all
                select admission.oa_id as row_id, 'in_progress'::text as workflow_status,
                       admission.source_payload as normalized_payload,
                       admission.raw_payload, 1 as source_priority
                from app.oa_pending_payment_admissions admission
                where admission.tenant_id = %s
                  and admission.scope_key = %s
                  and admission.workflow_status = 'in_progress'
            )
            select row_id, workflow_status, normalized_payload, raw_payload, source_priority
            from workflow_facts
            order by row_id, source_priority
            """,
            (month_start(normalized_month), self._tenant_id, normalized_month),
        )

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        return self._records(
            """
            with workflow_facts as (
                select row_id, 'completed'::text as workflow_status,
                       normalized_payload, raw_payload, 0 as source_priority
                from app.oa_applications
                where """ + COMPLETED_WORKFLOW_STATUS_SQL + """
                union all
                select admission.oa_id as row_id, 'in_progress'::text as workflow_status,
                       admission.source_payload as normalized_payload,
                       admission.raw_payload, 1 as source_priority
                from app.oa_pending_payment_admissions admission
                where admission.tenant_id = %s
                  and admission.workflow_status = 'in_progress'
            )
            select row_id, workflow_status, normalized_payload, raw_payload, source_priority
            from workflow_facts
            order by row_id, source_priority
            """,
            (self._tenant_id,),
        )

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        normalized_row_ids = list(dict.fromkeys(row_id for value in row_ids if (row_id := text(value))))
        if not normalized_row_ids:
            return []
        records = self._records(
            """
            with workflow_facts as (
                select row_id, 'completed'::text as workflow_status,
                       normalized_payload, raw_payload, 0 as source_priority
                from app.oa_applications
                where row_id = any(%s::text[])
                  and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
                union all
                select admission.oa_id as row_id, 'in_progress'::text as workflow_status,
                       admission.source_payload as normalized_payload,
                       admission.raw_payload, 1 as source_priority
                from app.oa_pending_payment_admissions admission
                where admission.tenant_id = %s
                  and admission.oa_id = any(%s::text[])
                  and admission.workflow_status = 'in_progress'
            )
            select row_id, workflow_status, normalized_payload, raw_payload, source_priority
            from workflow_facts
            order by row_id, source_priority
            """,
            (normalized_row_ids, self._tenant_id, normalized_row_ids),
        )
        records_by_id = {record.id: record for record in records}
        return [records_by_id[row_id] for row_id in normalized_row_ids if row_id in records_by_id]

    def list_available_months(self) -> list[str]:
        rows = self._connection.fetch_all(
            """
            select scope_key
            from (
                select distinct to_char(scope_month, 'YYYY-MM') as scope_key
                from app.oa_applications
                where scope_month is not null
                  and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
                union
                select distinct scope_key
                from app.oa_pending_payment_admissions
                where tenant_id = %s
                  and workflow_status = 'in_progress'
            ) workflow_scopes
            order by scope_key
            """,
            (self._tenant_id,),
        )
        return [scope for row in rows if (scope := text(row.get("scope_key")))]

    @staticmethod
    def get_read_status() -> OAReadStatus:
        return OAReadStatus(code="ready", message="PostgreSQL OA workflow facts ready")

    def _records(self, sql: str, params: tuple[Any, ...] = ()) -> list[OAApplicationRecord]:
        rows = list(self._connection.fetch_all(sql, params) or [])
        counts: dict[str, int] = {}
        for row in rows:
            row_id = text(row.get("row_id"))
            if row_id:
                counts[row_id] = counts.get(row_id, 0) + 1
        duplicate_ids = sorted(row_id for row_id, count in counts.items() if count > 1)
        if duplicate_ids:
            raise ValueError(
                "OA workflow facts contain completed/in-progress duplicate ids: "
                + ",".join(duplicate_ids)
            )
        statuses_by_id = {
            text(row.get("row_id")): text(row.get("workflow_status"))
            for row in rows
            if text(row.get("row_id"))
        }
        records = PostgresOAProjectionRepository._records_from_rows(rows)
        for record in records:
            record.workflow_status = statuses_by_id.get(record.id, "")
        return records


class PostgresOAProjectionAdapter:
    name = "postgres_oa_projection"

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        return list(self._repository.list_application_records(month))

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        list_all = getattr(self._repository, "list_all_application_records", None)
        if callable(list_all):
            return list(list_all())
        records: list[OAApplicationRecord] = []
        for month in self.list_available_months():
            records.extend(self.list_application_records(month))
        return records

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        list_by_ids = getattr(self._repository, "list_application_records_by_row_ids", None)
        if callable(list_by_ids):
            return list(list_by_ids(row_ids))
        wanted = {str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()}
        return [record for record in self.list_all_application_records() if record.id in wanted]

    def list_available_months(self) -> list[str]:
        list_months = getattr(self._repository, "list_available_months", None)
        return list(list_months()) if callable(list_months) else []

    def get_read_status(self) -> OAReadStatus:
        get_status = getattr(self._repository, "get_read_status", None)
        if callable(get_status):
            return get_status()
        return OAReadStatus(code="ready", message="OA projection ready")

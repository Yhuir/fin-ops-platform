from __future__ import annotations

import hashlib
import json
from typing import Any


class SettingsDataResetImpactChanged(RuntimeError):
    pass


class SettingsDataResetRecoveryEvidenceInvalid(RuntimeError):
    pass


class PostgresSettingsDataResetRepository:
    """Execute one settings data-reset action inside the caller's transaction."""

    _BANK_BATCH_TYPES = ("bank_transaction",)
    _INVOICE_BATCH_TYPES = ("input_invoice", "output_invoice")
    _BANK_ROW_TYPES = ("bank", "bank_transaction")
    _INVOICE_ROW_TYPES = ("invoice", "input_invoice", "output_invoice")

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def preview(
        self,
        action: str,
        *,
        row_ids: list[str] | None = None,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        impact = self._impact(action, row_ids=row_ids or [], case_ids=case_ids or [])
        receipt = self._connection.fetch_one(
            """
            select receipt_id::text as receipt_id, valid_until
            from job.settings_data_reset_recovery_receipts
            where action = %s
              and impact_fingerprint = %s
              and consumed_by_job_id is null
              and revoked_at is null
              and valid_until > now()
            order by valid_until desc, created_at desc
            limit 1
            """,
            (action, impact["impact_fingerprint"]),
        )
        return {
            **impact,
            "recovery_ready": receipt is not None,
            "recovery_receipt_id": str((receipt or {}).get("receipt_id") or "") or None,
            "recovery_valid_until": (receipt or {}).get("valid_until"),
        }

    def reset_bank_transaction_data(
        self,
        *,
        expected_impact_fingerprint: str,
        recovery_receipt_id: str,
        job_id: str,
        actor_id: str,
        reason: str,
    ) -> dict[str, Any]:
        self._validate_guard(
            "reset_bank_transactions",
            expected_impact_fingerprint=expected_impact_fingerprint,
            recovery_receipt_id=recovery_receipt_id,
            job_id=job_id,
        )
        self._authorize_fact_deletion(actor_id, reason)
        file_state = self._import_file_state(self._BANK_BATCH_TYPES)
        relation_counts = self._delete_workbench_domain(
            row_types=self._BANK_ROW_TYPES,
            row_id_prefixes=("bk-", "bk_", "txn-", "txn_", "bank-", "bank_"),
        )
        deleted_counts = {
            **relation_counts,
            "no_oa_bank_batch_events": self._connection.execute(
                "delete from app.no_oa_bank_batch_events"
            ),
            "no_oa_bank_batches": self._connection.execute(
                "delete from app.no_oa_bank_batches"
            ),
            "bank_flow_rule_batch_events": self._connection.execute(
                "delete from app.bank_flow_rule_batch_events"
            ),
            "bank_flow_rule_batches": self._connection.execute(
                "delete from app.bank_flow_rule_batches"
            ),
            "turnover_relation_events": self._connection.execute(
                "delete from app.turnover_relation_events"
            ),
            "turnover_relations": self._connection.execute(
                "delete from app.turnover_relations"
            ),
            "bank_transaction_category_events": self._connection.execute(
                "delete from app.bank_transaction_category_events"
            ),
            "bank_transaction_category_confirmations": self._connection.execute(
                "delete from app.bank_transaction_category_confirmations"
            ),
            "bank_transaction_categories": self._connection.execute(
                "delete from app.bank_transaction_categories"
            ),
            **self._delete_matching(),
        }
        deleted_counts["bank_transactions"] = self._connection.execute(
            "delete from app.bank_transactions"
        )
        deleted_counts.update(
            self._mark_import_files_deleting(self._BANK_BATCH_TYPES, file_state)
        )
        deleted_counts.update(self._delete_import_batches(self._BANK_BATCH_TYPES))
        deleted_counts["invoices"] = 0
        return {
            **deleted_counts,
            "stored_import_file_paths": file_state["stored_import_file_paths"],
        }

    def reset_invoice_data(
        self,
        *,
        expected_impact_fingerprint: str,
        recovery_receipt_id: str,
        job_id: str,
        actor_id: str,
        reason: str,
    ) -> dict[str, Any]:
        self._validate_guard(
            "reset_invoices",
            expected_impact_fingerprint=expected_impact_fingerprint,
            recovery_receipt_id=recovery_receipt_id,
            job_id=job_id,
        )
        self._authorize_fact_deletion(actor_id, reason)
        file_state = self._import_file_state(self._INVOICE_BATCH_TYPES)
        relation_counts = self._delete_workbench_domain(
            row_types=self._INVOICE_ROW_TYPES,
            row_id_prefixes=(
                "iv-",
                "iv_",
                "inv-",
                "inv_",
                "invoice-",
                "invoice_",
                "oa-att-inv-",
                "etc-summary-",
            ),
        )
        deleted_counts = {
            **relation_counts,
            "etc_batch_invoice_links": self._connection.execute(
                "delete from app.etc_batch_invoice_links"
            ),
            **self._delete_matching(),
        }
        deleted_counts["invoices"] = self._connection.execute("delete from app.invoices")
        deleted_counts.update(
            self._mark_import_files_deleting(self._INVOICE_BATCH_TYPES, file_state)
        )
        deleted_counts.update(self._delete_import_batches(self._INVOICE_BATCH_TYPES))
        deleted_counts["tax_certified_import_records"] = self._connection.execute(
            "delete from app.tax_certified_import_records"
        )
        deleted_counts["tax_certified_import_batches"] = self._connection.execute(
            "delete from app.tax_certified_import_batches"
        )
        deleted_counts["tax_certified_import_sessions"] = self._connection.execute(
            "delete from app.tax_certified_import_sessions"
        )
        deleted_counts["bank_transactions"] = 0
        return {
            **deleted_counts,
            "stored_import_file_paths": file_state["stored_import_file_paths"],
        }

    def reset_oa_workbench_data(
        self,
        *,
        row_ids: list[str],
        case_ids: list[str],
        expected_impact_fingerprint: str,
        recovery_receipt_id: str,
        job_id: str,
        actor_id: str,
        reason: str,
    ) -> dict[str, Any]:
        normalized_row_ids = self._dedupe(row_ids)
        normalized_case_ids = self._dedupe(case_ids)
        self._validate_guard(
            "reset_oa_and_rebuild",
            row_ids=normalized_row_ids,
            case_ids=normalized_case_ids,
            expected_impact_fingerprint=expected_impact_fingerprint,
            recovery_receipt_id=recovery_receipt_id,
            job_id=job_id,
        )
        self._authorize_fact_deletion(actor_id, reason)
        if normalized_case_ids:
            history_count = self._connection.execute(
                """
                update app.workbench_pair_relation_history
                set relation_id = null
                where relation_id in (
                    select id
                    from app.workbench_pair_relations
                    where case_id = any(%s::text[])
                )
                """,
                (normalized_case_ids,),
            )
            relation_count = self._connection.execute(
                "delete from app.workbench_pair_relations where case_id = any(%s::text[])",
                (normalized_case_ids,),
            )
        else:
            history_count = 0
            relation_count = 0
        override_count = (
            self._connection.execute(
                "delete from app.workbench_row_overrides where row_id = any(%s::text[])",
                (normalized_row_ids,),
            )
            if normalized_row_ids
            else 0
        )
        preserved_row = self._connection.fetch_one(
            "select count(*)::bigint as count from app.workbench_pair_relations"
        )
        preserved_count = int((preserved_row or {}).get("count") or 0)
        return {
            "workbench_row_overrides": override_count,
            "workbench_oa_row_overrides": override_count,
            "workbench_pair_relations": relation_count,
            "workbench_oa_pair_relations": relation_count,
            "workbench_pair_relation_history_preserved": history_count,
            "workbench_preserved_non_oa_pair_relations": preserved_count,
        }

    def _validate_guard(
        self,
        action: str,
        *,
        expected_impact_fingerprint: str,
        recovery_receipt_id: str,
        job_id: str,
        row_ids: list[str] | None = None,
        case_ids: list[str] | None = None,
    ) -> None:
        expected = str(expected_impact_fingerprint or "").strip()
        receipt_id = str(recovery_receipt_id or "").strip()
        normalized_job_id = str(job_id or "").strip()
        if not expected or not receipt_id or not normalized_job_id:
            raise SettingsDataResetRecoveryEvidenceInvalid(
                "Data reset requires an impact fingerprint, a recovery receipt and a job id."
            )
        self._lock_targets(action)
        current = self._impact(action, row_ids=row_ids or [], case_ids=case_ids or [])
        if current["impact_fingerprint"] != expected:
            raise SettingsDataResetImpactChanged("Data reset impact changed after confirmation.")
        receipt = self._connection.fetch_one(
            """
            select receipt_id::text as receipt_id
            from job.settings_data_reset_recovery_receipts
            where receipt_id = %s::uuid
              and action = %s
              and impact_fingerprint = %s
              and consumed_by_job_id = %s
              and consumed_at is not null
              and revoked_at is null
              and valid_until > now()
            for share
            """,
            (receipt_id, action, expected, normalized_job_id),
        )
        if receipt is None:
            raise SettingsDataResetRecoveryEvidenceInvalid(
                "The verified restore point is missing, expired, revoked or belongs to another job."
            )

    def _impact(
        self,
        action: str,
        *,
        row_ids: list[str],
        case_ids: list[str],
    ) -> dict[str, Any]:
        signatures: dict[str, dict[str, Any]] = {}
        for key, statement, params in self._impact_targets(
            action,
            row_ids=self._dedupe(row_ids),
            case_ids=self._dedupe(case_ids),
        ):
            row = self._connection.fetch_one(
                f"""
                select count(*)::bigint as count,
                       md5(
                           count(*)::text || ':'
                           || coalesce(sum(hashtextextended(identity, 0)::numeric), 0)::text || ':'
                           || coalesce(sum(hashtextextended(identity, 1)::numeric), 0)::text
                       ) as signature
                from ({statement}) as impact_target
                """,
                params,
            ) or {}
            signatures[key] = {
                "count": int(row.get("count") or 0),
                "signature": str(row.get("signature") or ""),
            }
        serialized = json.dumps(signatures, sort_keys=True, separators=(",", ":"))
        return {
            "action": action,
            "impact_counts": {key: value["count"] for key, value in signatures.items()},
            "impact_fingerprint": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        }

    def _impact_targets(
        self,
        action: str,
        *,
        row_ids: list[str],
        case_ids: list[str],
    ) -> list[tuple[str, str, tuple[Any, ...] | None]]:
        matching = [
            ("matching_results", "select id::text || ':' || xmin::text as identity from app.matching_results", None),
            ("matching_runs", "select id::text || ':' || xmin::text as identity from app.matching_runs", None),
        ]
        if action == "reset_bank_transactions":
            workbench = self._workbench_impact_targets(
                row_types=self._BANK_ROW_TYPES,
                row_id_prefixes=("bk-", "bk_", "txn-", "txn_", "bank-", "bank_"),
            )
            return [
                *workbench,
                ("no_oa_bank_batch_events", "select id::text || ':' || xmin::text as identity from app.no_oa_bank_batch_events", None),
                ("no_oa_bank_batches", "select id::text || ':' || xmin::text as identity from app.no_oa_bank_batches", None),
                ("bank_flow_rule_batch_events", "select id::text || ':' || xmin::text as identity from app.bank_flow_rule_batch_events", None),
                ("bank_flow_rule_batches", "select id::text || ':' || xmin::text as identity from app.bank_flow_rule_batches", None),
                ("turnover_relation_events", "select id::text || ':' || xmin::text as identity from app.turnover_relation_events", None),
                ("turnover_relations", "select id::text || ':' || xmin::text as identity from app.turnover_relations", None),
                ("bank_transaction_category_events", "select id::text || ':' || xmin::text as identity from app.bank_transaction_category_events", None),
                ("bank_transaction_category_confirmations", "select id::text || ':' || xmin::text as identity from app.bank_transaction_category_confirmations", None),
                ("bank_transaction_categories", "select id::text || ':' || xmin::text as identity from app.bank_transaction_categories", None),
                *matching,
                ("bank_transactions", "select id::text || ':' || xmin::text as identity from app.bank_transactions", None),
                *self._import_impact_targets(self._BANK_BATCH_TYPES),
            ]
        if action == "reset_invoices":
            workbench = self._workbench_impact_targets(
                row_types=self._INVOICE_ROW_TYPES,
                row_id_prefixes=("iv-", "iv_", "inv-", "inv_", "invoice-", "invoice_", "oa-att-inv-", "etc-summary-"),
            )
            return [
                *workbench,
                ("etc_batch_invoice_links", "select id::text || ':' || xmin::text as identity from app.etc_batch_invoice_links", None),
                *matching,
                ("invoices", "select id::text || ':' || xmin::text as identity from app.invoices", None),
                *self._import_impact_targets(self._INVOICE_BATCH_TYPES),
                ("tax_certified_import_records", "select id::text || ':' || xmin::text as identity from app.tax_certified_import_records", None),
                ("tax_certified_import_batches", "select id::text || ':' || xmin::text as identity from app.tax_certified_import_batches", None),
                ("tax_certified_import_sessions", "select id::text || ':' || xmin::text as identity from app.tax_certified_import_sessions", None),
            ]
        if action == "reset_oa_and_rebuild":
            return [
                (
                    "workbench_pair_relation_history",
                    """select id::text || ':' || xmin::text as identity from app.workbench_pair_relation_history
                       where relation_id in (select id from app.workbench_pair_relations where case_id = any(%s::text[]))""",
                    (case_ids,),
                ),
                (
                    "workbench_pair_relations",
                    "select id::text || ':' || xmin::text as identity from app.workbench_pair_relations where case_id = any(%s::text[])",
                    (case_ids,),
                ),
                (
                    "workbench_row_overrides",
                    "select id::text || ':' || xmin::text as identity from app.workbench_row_overrides where row_id = any(%s::text[])",
                    (row_ids,),
                ),
            ]
        raise ValueError(f"unsupported reset action: {action}")

    def _workbench_impact_targets(
        self,
        *,
        row_types: tuple[str, ...],
        row_id_prefixes: tuple[str, ...],
    ) -> list[tuple[str, str, tuple[Any, ...]]]:
        predicate = self._workbench_relation_predicate()
        params = (list(row_types), list(row_id_prefixes))
        return [
            (
                "workbench_pair_relation_history",
                f"""select id::text || ':' || xmin::text as identity from app.workbench_pair_relation_history
                    where relation_id in (select id from app.workbench_pair_relations where {predicate})""",
                params,
            ),
            (
                "workbench_pair_relations",
                f"select id::text || ':' || xmin::text as identity from app.workbench_pair_relations where {predicate}",
                params,
            ),
            (
                "workbench_row_overrides",
                """select id::text || ':' || xmin::text as identity from app.workbench_row_overrides
                   where lower(row_type) = any(%s::text[])
                      or exists (select 1 from unnest(%s::text[]) as prefix(value)
                                 where lower(row_id) like prefix.value || '%%')""",
                params,
            ),
        ]

    def _import_impact_targets(
        self,
        batch_types: tuple[str, ...],
    ) -> list[tuple[str, str, tuple[Any, ...]]]:
        values = list(batch_types)
        return [
            (
                "import_files",
                f"select id::text || ':' || xmin::text as identity from app.import_files where {self._import_file_batch_type_predicate()}",
                (values,),
            ),
            (
                "import_batch_rows",
                """select id::text || ':' || xmin::text as identity from app.import_batch_rows
                   where import_batch_id in (select id from app.import_batches where batch_type = any(%s::text[]))
                      or legacy_batch_id in (select legacy_mongo_id from app.import_batches
                                             where batch_type = any(%s::text[]) and legacy_mongo_id is not null)""",
                (values, values),
            ),
            (
                "import_batches",
                "select id::text || ':' || xmin::text as identity from app.import_batches where batch_type = any(%s::text[])",
                (values,),
            ),
        ]

    def _lock_targets(self, action: str) -> None:
        tables = {
            "reset_bank_transactions": (
                "app.workbench_pair_relation_history", "app.workbench_pair_relations", "app.workbench_row_overrides",
                "app.no_oa_bank_batch_events", "app.no_oa_bank_batches", "app.bank_flow_rule_batch_events",
                "app.bank_flow_rule_batches", "app.turnover_relation_events", "app.turnover_relations",
                "app.bank_transaction_category_events", "app.bank_transaction_category_confirmations",
                "app.bank_transaction_categories", "app.matching_results", "app.matching_runs",
                "app.bank_transactions", "app.import_files", "app.import_batch_rows", "app.import_batches",
            ),
            "reset_invoices": (
                "app.workbench_pair_relation_history", "app.workbench_pair_relations", "app.workbench_row_overrides",
                "app.etc_batch_invoice_links", "app.matching_results", "app.matching_runs", "app.invoices",
                "app.import_files", "app.import_batch_rows", "app.import_batches", "app.tax_certified_import_records",
                "app.tax_certified_import_batches", "app.tax_certified_import_sessions",
            ),
            "reset_oa_and_rebuild": (
                "app.workbench_pair_relation_history", "app.workbench_pair_relations", "app.workbench_row_overrides",
            ),
        }.get(action)
        if tables is None:
            raise ValueError(f"unsupported reset action: {action}")
        self._connection.execute(f"lock table {', '.join(tables)} in share row exclusive mode")

    def _authorize_fact_deletion(self, actor_id: str, reason: str) -> None:
        normalized_actor = str(actor_id or "").strip()
        normalized_reason = str(reason or "").strip()
        if not normalized_actor or not normalized_reason:
            raise ValueError("Data reset actor and reason are required.")
        self._connection.execute(
            "select set_config('fin_ops.correction_reason', %s, true)",
            (normalized_reason,),
        )
        self._connection.execute(
            "select set_config('fin_ops.actor_id', %s, true)",
            (normalized_actor,),
        )

    def _delete_matching(self) -> dict[str, int]:
        return {
            "matching_results": self._connection.execute("delete from app.matching_results"),
            "matching_runs": self._connection.execute("delete from app.matching_runs"),
        }

    def _delete_import_batches(self, batch_types: tuple[str, ...]) -> dict[str, int]:
        import_batch_rows = self._connection.execute(
            """
            delete from app.import_batch_rows
            where import_batch_id in (
                select id from app.import_batches where batch_type = any(%s::text[])
            )
               or legacy_batch_id in (
                select legacy_mongo_id
                from app.import_batches
                where batch_type = any(%s::text[])
                  and legacy_mongo_id is not null
            )
            """,
            (list(batch_types), list(batch_types)),
        )
        import_batches = self._connection.execute(
            "delete from app.import_batches where batch_type = any(%s::text[])",
            (list(batch_types),),
        )
        return {
            "import_batch_rows": import_batch_rows,
            "import_batches": import_batches,
        }

    def _import_file_state(self, batch_types: tuple[str, ...]) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            f"""
            select session_id, stored_file_path, status
            from app.import_files
            where {self._import_file_batch_type_predicate()}
            """,
            (list(batch_types),),
        )
        active_target_session_ids = {
            str(row.get("session_id") or "").strip()
            for row in rows
            if str(row.get("status") or "").strip().lower() != "deleted"
            and str(row.get("session_id") or "").strip()
        }
        active_non_target_session_ids: set[str] = set()
        if active_target_session_ids:
            non_target_rows = self._connection.fetch_all(
                f"""
                select distinct session_id
                from app.import_files
                where status <> 'deleted'
                  and session_id = any(%s::text[])
                  and not ({self._import_file_batch_type_predicate()})
                """,
                (sorted(active_target_session_ids), list(batch_types)),
            )
            active_non_target_session_ids = {
                str(row.get("session_id") or "").strip()
                for row in non_target_rows
                if str(row.get("session_id") or "").strip()
            }
        return {
            "file_import_sessions": len(
                active_target_session_ids - active_non_target_session_ids
            ),
            "stored_import_file_paths": self._dedupe(
                [
                    str(row.get("stored_file_path") or "").strip()
                    for row in rows
                    if str(row.get("status") or "").strip().lower() != "deleted"
                    and str(row.get("stored_file_path") or "").strip()
                ]
            ),
        }

    def _mark_import_files_deleting(
        self,
        batch_types: tuple[str, ...],
        file_state: dict[str, Any],
    ) -> dict[str, int]:
        return {
            "file_import_sessions": int(file_state.get("file_import_sessions") or 0),
            "file_import_files": self._connection.execute(
                f"""
                update app.import_files
                set status = 'deleting'
                where status not in ('deleted', 'deleting')
                  and {self._import_file_batch_type_predicate()}
                """,
                (list(batch_types),),
            ),
        }

    def _delete_workbench_domain(
        self,
        *,
        row_types: tuple[str, ...],
        row_id_prefixes: tuple[str, ...],
    ) -> dict[str, int]:
        params = (list(row_types), list(row_id_prefixes))
        relation_predicate = self._workbench_relation_predicate()
        history_count = self._connection.execute(
            f"""
            update app.workbench_pair_relation_history
            set relation_id = null
            where relation_id in (
                select id
                from app.workbench_pair_relations
                where {relation_predicate}
            )
            """,
            params,
        )
        relation_count = self._connection.execute(
            f"delete from app.workbench_pair_relations where {relation_predicate}",
            params,
        )
        override_count = self._connection.execute(
            """
            delete from app.workbench_row_overrides
            where lower(row_type) = any(%s::text[])
               or exists (
                    select 1
                    from unnest(%s::text[]) as prefix(value)
                    where lower(row_id) like prefix.value || '%%'
               )
            """,
            params,
        )
        return {
            "workbench_row_overrides": override_count,
            "workbench_pair_relations": relation_count,
            "workbench_pair_relation_history_preserved": history_count,
        }

    @staticmethod
    def _workbench_relation_predicate() -> str:
        return """
        (
            exists (
                select 1
                from unnest(coalesce(row_types, array[]::text[])) as row_type(value)
                where lower(row_type.value) = any(%s::text[])
            )
            or exists (
                select 1
                from unnest(coalesce(row_ids, array[]::text[])) as row_id(value)
                cross join unnest(%s::text[]) as prefix(value)
                where lower(row_id.value) like prefix.value || '%%'
            )
        )
        """

    @staticmethod
    def _import_file_batch_type_predicate() -> str:
        return """
        coalesce(
            nullif(raw_payload #>> '{normalized_payload,override_batch_type}', ''),
            nullif(raw_payload #>> '{normalized_payload,batch_type}', '')
        ) = any(%s::text[])
        """

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        return list(dict.fromkeys(str(value or "").strip() for value in values if str(value or "").strip()))

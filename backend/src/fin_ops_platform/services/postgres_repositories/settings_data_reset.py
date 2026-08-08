from __future__ import annotations

from typing import Any

from fin_ops_platform.services.state_store_protocol import PROTECTED_ADMIN_USERNAME


class PostgresSettingsDataResetRepository:
    """Execute one settings data-reset action inside the caller's transaction."""

    _BANK_BATCH_TYPES = ("bank_transaction",)
    _INVOICE_BATCH_TYPES = ("input_invoice", "output_invoice")
    _BANK_ROW_TYPES = ("bank", "bank_transaction")
    _INVOICE_ROW_TYPES = ("invoice", "input_invoice", "output_invoice")

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def reset_bank_transaction_data(self) -> dict[str, Any]:
        self._authorize_fact_deletion("管理员重置银行流水域数据")
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

    def reset_invoice_data(self) -> dict[str, Any]:
        self._authorize_fact_deletion("管理员重置发票域数据")
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
    ) -> dict[str, Any]:
        normalized_row_ids = self._dedupe(row_ids)
        normalized_case_ids = self._dedupe(case_ids)
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

    def _authorize_fact_deletion(self, reason: str) -> None:
        self._connection.execute(
            "select set_config('fin_ops.correction_reason', %s, true)",
            (reason,),
        )
        self._connection.execute(
            "select set_config('fin_ops.actor_id', %s, true)",
            (PROTECTED_ADMIN_USERNAME,),
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

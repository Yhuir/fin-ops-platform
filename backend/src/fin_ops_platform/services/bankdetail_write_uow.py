from __future__ import annotations

from typing import Any


class BankdetailWriteUnitOfWork:
    """Minimal Bankdetail / No OA write Unit of Work skeleton.

    PF-P200 intentionally keeps this class disconnected from production write
    paths. It provides a small testable seam for future transaction-bound
    category, auto-tag, and No OA writers.
    """

    def __init__(
        self,
        *,
        category_port: object | None = None,
        settings_port: object | None = None,
        no_oa_port: object | None = None,
        side_effect_writer: object | None = None,
    ) -> None:
        self._category_port = category_port
        self._settings_port = settings_port
        self._no_oa_port = no_oa_port
        self._side_effect_writer = side_effect_writer

    def confirm_category(
        self,
        *,
        transaction_id: str,
        category_code: str,
        expected_version: int | None,
        actor_id: str,
    ) -> dict[str, Any]:
        if self._category_port is None:
            raise RuntimeError("bankdetail_category_port_required")
        confirm = getattr(self._category_port, "confirm_category", None)
        if not callable(confirm):
            raise RuntimeError("bankdetail_category_confirm_not_implemented")
        try:
            result = dict(
                confirm(
                    transaction_id=transaction_id,
                    category_code=category_code,
                    expected_version=expected_version,
                    actor_id=actor_id,
                )
                or {}
            )
            affected_months = [
                str(month).strip()
                for month in list(result.get("affected_months") or [])
                if str(month).strip()
            ]
            writer = getattr(self._side_effect_writer, "write", None)
            if callable(writer):
                writer(
                    {
                        "transaction": "begin",
                        "facts": ["bank_transaction_category"],
                        "audit": ["bank_detail_category_confirmed"],
                        "transaction_end": "commit",
                    }
                )
            commit = getattr(self._category_port, "commit", None)
            if callable(commit):
                commit(transaction_id=transaction_id)
            return result
        except Exception:
            rollback = getattr(self._category_port, "rollback", None)
            if callable(rollback):
                rollback(transaction_id=transaction_id)
            raise

    def update_auto_tag_rules(self, *, actor_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._settings_port is None:
            raise RuntimeError("bankdetail_settings_port_required")
        update = getattr(self._settings_port, "update_auto_tag_rules", None)
        if not callable(update):
            raise RuntimeError("bankdetail_auto_tag_rules_update_not_implemented")
        result = dict(update(actor_id=actor_id, payload=dict(payload or {})) or {})
        priority_scope_keys = [
            str(scope_key).strip()
            for scope_key in list(result.get("priority_scope_keys") or [])
            if str(scope_key).strip() and str(scope_key).strip() != "all"
        ]
        writer = getattr(self._side_effect_writer, "write", None)
        if callable(writer):
            writer(
                {
                    "transaction": "begin",
                    "facts": ["bank_auto_tag_rules"],
                    "audit": ["bank_auto_tag_rules_changed"],
                    "lifecycle_events": ["bank_auto_tag_rules_changed"],
                    "transaction_end": "commit",
                }
            )
        return result

    def submit_no_oa_batch(
        self,
        *,
        batch_id: str,
        expected_version: int | None,
        actor_id: str,
        note: str | None,
    ) -> dict[str, Any]:
        if self._no_oa_port is None:
            raise RuntimeError("bankdetail_no_oa_port_required")
        submit = getattr(self._no_oa_port, "submit_no_oa_batch", None)
        if not callable(submit):
            raise RuntimeError("bankdetail_no_oa_submit_not_implemented")
        result = dict(
            submit(
                batch_id=batch_id,
                expected_version=expected_version,
                actor_id=actor_id,
                note=note,
            )
            or {}
        )
        return self._commit_no_oa_mutation(
            result,
            batch_id=batch_id,
            audit_action="no_oa_bank_batch_submit",
        )

    def withdraw_no_oa_batch(
        self,
        *,
        batch_id: str,
        expected_version: int | None,
        actor_id: str,
        reason: str | None,
    ) -> dict[str, Any]:
        if self._no_oa_port is None:
            raise RuntimeError("bankdetail_no_oa_port_required")
        withdraw = getattr(self._no_oa_port, "withdraw_no_oa_batch", None)
        if not callable(withdraw):
            raise RuntimeError("bankdetail_no_oa_withdraw_not_implemented")
        result = dict(
            withdraw(
                batch_id=batch_id,
                expected_version=expected_version,
                actor_id=actor_id,
                reason=reason,
            )
            or {}
        )
        return self._commit_no_oa_mutation(
            result,
            batch_id=batch_id,
            audit_action="no_oa_bank_batch_withdraw",
        )

    def _commit_no_oa_mutation(
        self,
        result: dict[str, Any],
        *,
        batch_id: str,
        audit_action: str,
    ) -> dict[str, Any]:
        affected_months = [
            str(month).strip()
            for month in list(result.get("affected_months") or [])
            if str(month).strip()
        ]
        changed_case_ids = [
            str(case_id).strip()
            for case_id in list(result.get("changed_case_ids") or [])
            if str(case_id).strip()
        ]
        try:
            writer = getattr(self._side_effect_writer, "write", None)
            if callable(writer):
                writer(
                    {
                        "transaction": "begin",
                        "facts": ["no_oa_bank_batch", "workbench_pair_relation"],
                        "audit": [audit_action],
                        "dirty_scopes": [],
                        "outbox": [],
                        "lifecycle_events": ["no_oa_bank_batch_changed"],
                        "transaction_end": "commit",
                    }
                )
            commit = getattr(self._no_oa_port, "commit", None)
            if callable(commit):
                commit(batch_id=batch_id)
            return result
        except Exception:
            rollback = getattr(self._no_oa_port, "rollback", None)
            if callable(rollback):
                rollback(batch_id=batch_id)
            raise

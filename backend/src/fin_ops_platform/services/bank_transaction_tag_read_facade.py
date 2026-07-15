from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.postgres_repositories.common import decimal_text, text, text_list
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway


FRESH_BANK_TAG_STATUS = "fresh"
NON_FRESH_BANK_TAG_STATUSES = {"refreshing", "stale", "missing", "schema_mismatch", "unavailable"}


class BankTransactionTagReadFacade:
    def __init__(
        self,
        *,
        read_model_repository: Any,
        queue_repository: Any | None = None,
        tenant_id: str = "default",
    ) -> None:
        self._read_model_repository = read_model_repository
        self._queue_repository = queue_repository
        self._tenant_id = str(tenant_id or "default").strip() or "default"
        self._last_result: dict[str, Any] = _facade_result(status="missing")

    @property
    def last_source_versions(self) -> dict[str, Any]:
        source_versions = self._last_result.get("source_versions")
        return dict(source_versions) if isinstance(source_versions, dict) else {}

    def get_by_transaction_ids(
        self,
        transaction_ids: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "downstream_bank_tag_read",
        month_hint: str | None = None,
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_ids = _dedupe_preserve_order(text(value) for value in list(transaction_ids or []))
        if not normalized_ids:
            result = _facade_result(status=FRESH_BANK_TAG_STATUS)
            self._last_result = result
            return result
        reader = getattr(self._read_model_repository, "get_bank_detail_tagged_rows_by_transaction_ids", None)
        if not callable(reader):
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=[],
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable"],
            )
        payload = reader(normalized_ids, tenant_id=self._tenant_id)
        result = self._result_from_repository_payload(
            payload,
            require_fresh=require_fresh,
            reason=reason,
            fallback_scope_keys=_fallback_scope_keys(month_hint=month_hint, scope_keys_hint=scope_keys_hint),
        )
        self._last_result = result
        return result

    def list_by_month(
        self,
        month: str,
        *,
        direction: str | None = None,
        category_codes: list[str] | None = None,
        require_fresh: bool = True,
        reason: str = "downstream_bank_tag_read",
    ) -> dict[str, Any]:
        normalized_month = text(month) or ""
        reader = getattr(self._read_model_repository, "list_bank_detail_tagged_rows_by_month", None)
        if not callable(reader) or not normalized_month:
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=[normalized_month] if normalized_month else [],
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable" if not callable(reader) else "month_required"],
            )
        payload = reader(
            normalized_month,
            direction=text(direction),
            category_codes=_dedupe_preserve_order(text(value) for value in list(category_codes or [])),
            tenant_id=self._tenant_id,
        )
        result = self._result_from_repository_payload(
            payload,
            require_fresh=require_fresh,
            reason=reason,
            fallback_scope_keys=[normalized_month],
        )
        self._last_result = result
        return result

    def snapshot_for_month(
        self,
        month: str,
        *,
        include_transaction_ids: list[str] | None = None,
        require_fresh: bool = True,
        reason: str = "downstream_bank_tag_read",
    ) -> dict[str, Any]:
        normalized_month = text(month) or ""
        normalized_ids = _dedupe_preserve_order(
            text(value) for value in list(include_transaction_ids or [])
        )
        reader = getattr(self._read_model_repository, "get_bank_detail_tagged_snapshot", None)
        if not callable(reader) or not normalized_month:
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=[normalized_month] if normalized_month else [],
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable" if not callable(reader) else "month_required"],
            )
        payload = reader(
            normalized_month,
            include_transaction_ids=normalized_ids,
            tenant_id=self._tenant_id,
        )
        result = self._result_from_repository_payload(
            payload,
            require_fresh=require_fresh,
            reason=reason,
            fallback_scope_keys=[normalized_month],
        )
        target_scope_ids = set(text_list((payload or {}).get("target_scope_transaction_ids")))
        result["month_rows"] = [
            row
            for row in list(result.get("rows") or [])
            if isinstance(row, dict) and text(row.get("transaction_id")) in target_scope_ids
        ]
        self._last_result = result
        return result

    def bulk_get_for_rows(self, bank_rows: list[Any]) -> dict[str, dict[str, Any]]:
        transaction_ids = [_transaction_id_for_row(row) for row in list(bank_rows or [])]
        return self.category_records_by_transaction_ids(
            [value for value in transaction_ids if value],
            require_fresh=True,
            scope_keys_hint=_scope_keys_from_rows(bank_rows),
        )

    def source_versions_for_scope_keys(
        self,
        scope_keys: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "downstream_bank_tag_source_versions",
    ) -> dict[str, Any]:
        normalized_scope_keys = _dedupe_preserve_order(text(value) for value in list(scope_keys or []))
        reader = getattr(self._read_model_repository, "bank_detail_scope_summary", None)
        if not callable(reader) or not normalized_scope_keys:
            return self._non_fresh_result(
                status="unavailable",
                scope_keys=normalized_scope_keys,
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["repository_method_unavailable" if not callable(reader) else "scope_keys_required"],
            )
        try:
            payload = reader(scope_keys=normalized_scope_keys, tenant_id=self._tenant_id)
        except TypeError as exc:
            if "tenant_id" not in str(exc):
                raise
            payload = reader(scope_keys=normalized_scope_keys)
        result = self._result_from_repository_payload(
            _source_versions_payload_from_scope_summary(payload),
            require_fresh=require_fresh,
            reason=reason,
            fallback_scope_keys=normalized_scope_keys,
        )
        self._last_result = result
        return result

    def category_records_by_transaction_ids(
        self,
        transaction_ids: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "downstream_bank_tag_read",
        month_hint: str | None = None,
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        payload = self.get_by_transaction_ids(
            transaction_ids,
            require_fresh=require_fresh,
            reason=reason,
            month_hint=month_hint,
            scope_keys_hint=scope_keys_hint,
        )
        if require_fresh and payload["status"] != FRESH_BANK_TAG_STATUS:
            raise RuntimeError("bank_detail_read_model_not_fresh")
        return {
            row["transaction_id"]: _provider_compatible_category(row)
            for row in list(payload.get("rows") or [])
            if isinstance(row, dict) and text(row.get("transaction_id"))
        }

    def _result_from_repository_payload(
        self,
        payload: dict[str, Any] | None,
        *,
        require_fresh: bool,
        reason: str,
        fallback_scope_keys: list[str],
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            if require_fresh and not fallback_scope_keys:
                fallback_scope_keys = ["all"]
            return self._non_fresh_result(
                status="missing",
                scope_keys=fallback_scope_keys,
                require_fresh=require_fresh,
                reason=reason,
                stale_reasons=["read_model_missing"],
            )
        missing_transaction_ids = text_list(payload.get("missing_transaction_ids"))
        status = _facade_status(payload.get("read_model_status"))
        scope_keys = text_list(payload.get("read_model_scope_keys")) or list(fallback_scope_keys)
        if require_fresh and status != FRESH_BANK_TAG_STATUS and not scope_keys:
            scope_keys = ["all"]
        source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
        scope_signatures = (
            payload.get("read_model_scope_signatures")
            if isinstance(payload.get("read_model_scope_signatures"), dict)
            else {}
        )
        stale_reasons = _stale_reasons(status=status, payload=payload)
        if require_fresh and status != FRESH_BANK_TAG_STATUS:
            refresh_scope_keys = _refresh_scope_keys_for_non_fresh_payload(
                payload=payload,
                scope_keys=scope_keys,
                scope_signatures=scope_signatures,
            )
            refresh_enqueued = self._enqueue_scope_refresh(scope_keys=refresh_scope_keys or scope_keys, reason=reason)
            return _facade_result(
                status=status,
                rows=[],
                source_versions=source_versions,
                scope_keys=scope_keys,
                refresh_enqueued=refresh_enqueued,
                stale_reasons=stale_reasons,
                read_model_scope_signatures=scope_signatures,
                missing_transaction_ids=missing_transaction_ids,
            )
        return _facade_result(
            status=status,
            rows=[_standardize_bank_detail_row(row) for row in list(payload.get("rows") or []) if isinstance(row, dict)],
            source_versions=source_versions,
            scope_keys=scope_keys,
            refresh_enqueued=False,
            stale_reasons=stale_reasons if status != FRESH_BANK_TAG_STATUS else [],
            read_model_scope_signatures=scope_signatures,
            missing_transaction_ids=missing_transaction_ids,
        )

    def _non_fresh_result(
        self,
        *,
        status: str,
        scope_keys: list[str],
        require_fresh: bool,
        reason: str,
        stale_reasons: list[str],
    ) -> dict[str, Any]:
        normalized_status = _facade_status(status)
        refresh_enqueued = self._enqueue_scope_refresh(scope_keys=scope_keys, reason=reason) if require_fresh else False
        return _facade_result(
            status=normalized_status,
            scope_keys=scope_keys,
            refresh_enqueued=refresh_enqueued,
            stale_reasons=stale_reasons,
        )

    def _enqueue_scope_refresh(self, *, scope_keys: list[str], reason: str) -> bool:
        refresh_gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not refresh_gateway.can_enqueue():
            return False
        return bool(
            refresh_gateway.enqueue_many(
                "bank_detail",
                _dedupe_preserve_order(text(value) for value in list(scope_keys or [])),
                reason=reason,
                tenant_id=self._tenant_id,
            )
        )


def _facade_result(
    *,
    status: str,
    rows: list[dict[str, Any]] | None = None,
    source_versions: dict[str, Any] | None = None,
    scope_keys: list[str] | None = None,
    refresh_enqueued: bool = False,
    stale_reasons: list[str] | None = None,
    read_model_scope_signatures: dict[str, Any] | None = None,
    missing_transaction_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": _facade_status(status),
        "rows": list(rows or []),
        "source_versions": source_versions if isinstance(source_versions, dict) else {},
        "scope_keys": list(scope_keys or []),
        "refresh_enqueued": bool(refresh_enqueued),
        "stale_reasons": list(stale_reasons or []),
        "read_model_scope_signatures": read_model_scope_signatures if isinstance(read_model_scope_signatures, dict) else {},
        "missing_transaction_ids": list(missing_transaction_ids or []),
    }


def _source_versions_payload_from_scope_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    source_versions = _source_versions_from_scope_summary(payload)
    return {
        "read_model_status": payload.get("read_model_status"),
        "rows": [],
        "source_versions": source_versions,
        "read_model_scope_keys": text_list(payload.get("read_model_scope_keys")),
        "read_model_scope_signatures": (
            payload.get("read_model_scope_signatures")
            if isinstance(payload.get("read_model_scope_signatures"), dict)
            else {}
        ),
        "dirty_scopes": list(payload.get("dirty_scopes") or []),
    }


def _source_versions_from_scope_summary(scope_summary: dict[str, Any]) -> dict[str, Any]:
    signatures = (
        scope_summary.get("read_model_scope_signatures")
        if isinstance(scope_summary.get("read_model_scope_signatures"), dict)
        else {}
    )
    scope_keys = text_list(scope_summary.get("read_model_scope_keys"))
    if len(scope_keys) == 1:
        signature = signatures.get(scope_keys[0]) if isinstance(signatures.get(scope_keys[0]), dict) else {}
        source_versions = signature.get("source_versions") if isinstance(signature.get("source_versions"), dict) else {}
        return dict(source_versions)
    result: dict[str, Any] = {}
    for scope_key in scope_keys:
        signature = signatures.get(scope_key) if isinstance(signatures.get(scope_key), dict) else {}
        source_versions = signature.get("source_versions") if isinstance(signature.get("source_versions"), dict) else {}
        if source_versions:
            result[scope_key] = dict(source_versions)
    return result


def _standardize_bank_detail_row(row: dict[str, Any]) -> dict[str, Any]:
    transaction_id = text(row.get("transaction_id") or row.get("id")) or ""
    direction = _standard_direction(row.get("direction") or row.get("txn_direction") or row.get("direction_label"))
    amount = decimal_text(row.get("amount"))
    signed_amount = decimal_text(row.get("signed_amount"))
    if signed_amount is None and amount is not None:
        signed_amount = _signed_amount_from_direction(amount, direction)
    label_path = text_list(row.get("effective_category_label_path")) or text_list(row.get("effective_category_path"))
    return {
        "transaction_id": transaction_id,
        "trade_time": text(row.get("trade_time")),
        "trade_date": text(row.get("trade_date") or row.get("txn_date")),
        "direction": direction,
        "amount": amount,
        "signed_amount": signed_amount,
        "counterparty_name": text(row.get("counterparty_name") or row.get("counterparty_name_raw")),
        "summary": text(row.get("summary") or row.get("summary_text")),
        "purpose": text(row.get("purpose") or row.get("purpose_text")),
        "bank_name": text(row.get("bank_name")),
        "account_last4": text(row.get("account_last4")),
        "effective_category_code": text(row.get("effective_category_code")),
        "effective_category_label": text(row.get("effective_category_label")),
        "effective_category_primary_label": text(row.get("effective_category_primary_label")),
        "effective_category_sub_label": text(row.get("effective_category_sub_label")),
        "effective_category_third_label": text(row.get("effective_category_third_label")),
        "effective_category_label_path": label_path,
        "effective_category_source": text(row.get("effective_category_source")),
        "effective_turnover_role": text(row.get("effective_turnover_role")),
        "effective_turnover_action_type": text(row.get("effective_turnover_action_type")),
        "effective_turnover_family": text(row.get("effective_turnover_family")),
        "category_version": row.get("category_version"),
        "manual_category_version": row.get("manual_category_version"),
        "version": row.get("version"),
    }


def _provider_compatible_category(row: dict[str, Any]) -> dict[str, Any]:
    label_path = text_list(row.get("effective_category_label_path"))
    return {
        "category_code": text(row.get("effective_category_code")),
        "category_label": text(row.get("effective_category_label")),
        "category_path": label_path,
        "category_primary_label": text(row.get("effective_category_primary_label")),
        "category_sub_label": text(row.get("effective_category_sub_label")),
        "category_third_label": text(row.get("effective_category_third_label")),
        "category_label_path": label_path,
        "source": text(row.get("effective_category_source")),
        "category_source": text(row.get("effective_category_source")),
        "effective_category_code": text(row.get("effective_category_code")),
        "effective_category_label": text(row.get("effective_category_label")),
        "effective_category_path": label_path,
        "effective_category_label_path": label_path,
        "effective_category_primary_label": text(row.get("effective_category_primary_label")),
        "effective_category_sub_label": text(row.get("effective_category_sub_label")),
        "effective_category_third_label": text(row.get("effective_category_third_label")),
        "effective_category_source": text(row.get("effective_category_source")),
        "turnover_role": text(row.get("effective_turnover_role")),
        "turnover_action_type": text(row.get("effective_turnover_action_type")),
        "turnover_family": text(row.get("effective_turnover_family")),
        "effective_turnover_role": text(row.get("effective_turnover_role")),
        "effective_turnover_action_type": text(row.get("effective_turnover_action_type")),
        "effective_turnover_family": text(row.get("effective_turnover_family")),
        "category_version": row.get("category_version"),
        "manual_category_version": row.get("manual_category_version"),
        "version": row.get("version"),
    }


def _transaction_id_for_row(row: Any) -> str | None:
    if isinstance(row, dict):
        return text(row.get("id") or row.get("transaction_id"))
    return text(getattr(row, "id", None) or getattr(row, "transaction_id", None))


def _fallback_scope_keys(*, month_hint: str | None, scope_keys_hint: list[str] | None) -> list[str]:
    hinted = _dedupe_preserve_order(text(value) for value in list(scope_keys_hint or []))
    if hinted:
        return hinted
    month = _month_text(month_hint)
    return [month] if month else []


def _scope_keys_from_rows(rows: list[Any]) -> list[str]:
    return _dedupe_preserve_order(
        _month_text(_row_value(row, "scope_key"))
        or _month_text(_row_value(row, "scope_month"))
        or _month_text(_row_value(row, "month"))
        or _month_text(_row_value(row, "txn_month"))
        or _month_text(_row_value(row, "trade_date"))
        or _month_text(_row_value(row, "txn_date"))
        or _month_text(_row_value(row, "trade_time"))
        for row in list(rows or [])
    )


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _month_text(value: Any) -> str | None:
    normalized = text(value)
    if not normalized:
        return None
    candidate = normalized[:7]
    return candidate if len(candidate) == 7 and candidate[4:5] == "-" else None


def _standard_direction(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"expense", "debit", "支", "支出", "付款"}:
        return "expense"
    if normalized in {"income", "credit", "收", "收入", "收款"}:
        return "income"
    return text(value)


def _signed_amount_from_direction(amount: str, direction: str | None) -> str | None:
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        return amount
    if direction == "expense":
        value = -abs(value)
    elif direction == "income":
        value = abs(value)
    return decimal_text(value)


def _facade_status(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized == "schema_mismatch":
        return "stale"
    if normalized == FRESH_BANK_TAG_STATUS:
        return FRESH_BANK_TAG_STATUS
    if normalized in NON_FRESH_BANK_TAG_STATUSES:
        return normalized
    return "unavailable"


def _stale_reasons(*, status: str, payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if status != FRESH_BANK_TAG_STATUS:
        reasons.append("read_model_not_fresh")
        if text_list(payload.get("missing_transaction_ids")):
            reasons.append("missing_transaction_rows")
    return reasons


def _refresh_scope_keys_for_non_fresh_payload(
    *,
    payload: dict[str, Any],
    scope_keys: list[str],
    scope_signatures: dict[str, Any],
) -> list[str]:
    dirty_scope_keys = _dedupe_preserve_order(
        text(row.get("scope_key"))
        for row in list(payload.get("dirty_scopes") or [])
        if isinstance(row, dict) and text(row.get("status")) in {"pending", "processing", "failed"}
    )
    if dirty_scope_keys:
        return dirty_scope_keys
    return _dedupe_preserve_order(
        scope_key
        for scope_key in list(scope_keys or [])
        if isinstance(scope_signatures.get(scope_key), dict)
        and text(scope_signatures[scope_key].get("dirty_status")) in {"pending", "processing", "failed"}
    )


def _dedupe_preserve_order(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = text(value)
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result

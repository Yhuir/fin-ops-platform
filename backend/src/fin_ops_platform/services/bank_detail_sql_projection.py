from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fin_ops_platform.services.bank_transaction_auto_category_service import (
    BANK_TRANSACTION_AUTO_CATEGORY_RULE_VERSION,
    BankTransactionAutoCategoryService,
    resolve_effective_category,
)
from fin_ops_platform.services.bank_transaction_category_service import (
    BankTransactionCategoryService,
    default_bank_transaction_tag_dictionary_payload,
)
from fin_ops_platform.services.postgres_repositories.common import decimal_text, int_value, text, text_list
from fin_ops_platform.services.postgres_repositories.read_models import BANK_DETAIL_READ_MODEL_SCHEMA_VERSION, PostgresReadModelRepository

PURPOSE_TEXT_LABELS = ("用途", "交易用途")
SUMMARY_TEXT_LABELS = ("摘要",)
NOTE_TEXT_LABELS = ("备注", "附言", "客户附言")
APP_SETTINGS_KEY = "app_settings"


class BankDetailSqlProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: PostgresReadModelRepository | None = None,
        auto_category_service: BankTransactionAutoCategoryService | None = None,
    ) -> None:
        self._connection = connection
        self._read_model_repository = read_model_repository or PostgresReadModelRepository(connection)
        self._auto_category_service = auto_category_service or BankTransactionAutoCategoryService()
        self._bank_auto_tag_rules_version = 1

    def list_bank_detail_scope_shards(self, scope_key: str) -> list[str]:
        normalized_scope_key = str(scope_key or "").strip()
        if _is_month_scope(normalized_scope_key):
            return [normalized_scope_key]
        rows = self._connection.fetch_all(
            """
            select to_char(txn_month, 'YYYY-MM') as scope_key
            from app.bank_transactions
            where txn_month is not null
            group by txn_month
            order by txn_month
            """,
            (),
        )
        return [value for row in rows if (value := text(row.get("scope_key")))]

    def rebuild_bank_detail_read_model_scope(self, scope_key: str, *, source_version: int | None = None) -> dict[str, Any]:
        normalized_scope_key = str(scope_key or "").strip()
        if not _is_month_scope(normalized_scope_key):
            raise ValueError("Bank detail read model rebuild requires YYYY-MM scope_key.")
        transaction_rows, auto_category_context_rows = self._load_transaction_rows_with_auto_category_context(
            normalized_scope_key
        )
        self._configure_auto_category_service_from_app_settings()
        if not transaction_rows:
            self._read_model_repository.save_bank_detail_rows(scope_key=normalized_scope_key, rows=[])
            self._read_model_repository.mark_bank_detail_scope(
                scope_key=normalized_scope_key,
                row_count=0,
                source_versions=self._source_versions(source_version=source_version, row_count=0),
            )
            return {"scope_key": normalized_scope_key, "row_count": 0}
        transaction_ids = [str(row["id"]) for row in transaction_rows]
        manual_categories = self._load_manual_categories(transaction_rows)
        relations = self._load_relation_tags(transaction_ids)
        auto_categories = self._auto_category_service.suggestions_by_transaction_id(auto_category_context_rows)
        auto_category_context_by_id = {
            str(row.get("id")): row
            for row in auto_category_context_rows
            if str(row.get("id") or "").strip()
        }
        generated_at = datetime.now(UTC).isoformat()
        source_versions = self._source_versions(source_version=source_version, row_count=len(transaction_rows))
        rows = [
            self._project_row(
                row,
                scope_key=normalized_scope_key,
                generated_at=generated_at,
                source_versions=source_versions,
                manual_category=manual_categories.get(str(row["id"])),
                auto_category=auto_categories.get(str(row["id"])),
                auto_category_context_by_id=auto_category_context_by_id,
                relation=relations.get(str(row["id"])),
            )
            for row in transaction_rows
        ]
        self._read_model_repository.save_bank_detail_rows(scope_key=normalized_scope_key, rows=rows)
        return {"scope_key": normalized_scope_key, "row_count": len(rows), "generated_at": generated_at}

    def _load_transaction_rows_with_auto_category_context(self, scope_key: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        start_date, end_date = _bank_detail_auto_category_context_bounds(scope_key)
        rows = self._connection.fetch_all(
            """
            select coalesce(legacy_mongo_id, id::text) as id,
                   id::text as transaction_id,
                   source_batch_id::text,
                   legacy_source_batch_id,
                   account_no,
                   account_name,
                   txn_direction,
                   counterparty_name_raw,
                   normalized_counterparty_name,
                   amount,
                   signed_amount,
                   balance,
                   currency,
                   txn_date,
                   trade_time,
                   coalesce(trade_time, txn_date::timestamptz) as trade_time_sort,
                   summary,
                   remark,
                   bank_text_fields,
                   raw_payload
            from app.bank_transactions
            where txn_date >= %s::date
              and txn_date < %s::date
            order by coalesce(trade_time, txn_date::timestamptz) desc, coalesce(legacy_mongo_id, id::text) desc
            """,
            (start_date.isoformat(), end_date.isoformat()),
        )
        context_rows = [self._normalize_transaction_row(row) for row in rows]
        scope_rows = [
            row
            for row in context_rows
            if str(row.get("trade_date") or row.get("trade_time") or "")[:7] == scope_key
        ]
        return scope_rows, context_rows

    def _load_manual_categories(self, transaction_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        identity_to_row_id: dict[str, str] = {}
        for row in transaction_rows:
            row_id = str(row.get("id") or "").strip()
            if not row_id:
                continue
            for identity in (row.get("id"), row.get("transaction_id")):
                normalized_identity = str(identity or "").strip()
                if normalized_identity:
                    identity_to_row_id[normalized_identity] = row_id
        if not identity_to_row_id:
            return {}
        rows = self._connection.fetch_all(
            """
            select distinct on (coalesce(legacy_transaction_id, bank_transaction_id::text))
                   coalesce(legacy_transaction_id, bank_transaction_id::text) as transaction_id,
                   category,
                   source,
                   version
            from app.bank_transaction_categories
            where status = 'active'
              and coalesce(legacy_transaction_id, bank_transaction_id::text) = any(%s)
            order by coalesce(legacy_transaction_id, bank_transaction_id::text), updated_at desc
            """,
            (list(identity_to_row_id),),
        )
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            transaction_id = identity_to_row_id.get(text(row.get("transaction_id")) or "")
            category_code = text(row.get("category"))
            if transaction_id is None:
                continue
            result[transaction_id] = {
                "category_code": category_code,
                "category_label": BankTransactionCategoryService.label_for(category_code),
                "category_path": BankTransactionCategoryService.path_for(category_code),
                "source": text(row.get("source")) or "manual",
                "category_version": int(row.get("version") or 0),
            }
        return result

    def _load_relation_tags(self, transaction_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not transaction_ids:
            return {}
        relation_rows = self._connection.fetch_all(
            """
            select case_id, row_ids, row_types, special_metadata
            from app.workbench_pair_relations
            where status = 'active'
              and row_ids && %s
            """,
            (transaction_ids,),
        )
        result: dict[str, dict[str, Any]] = {}
        transaction_id_set = set(transaction_ids)
        for row in relation_rows:
            row_ids = text_list(row.get("row_ids"))
            row_types = text_list(row.get("row_types"))
            bank_ids = [row_id for row_id in row_ids if row_id in transaction_id_set]
            has_oa = _relation_has_row_type(row_types, "oa") or any(_looks_like_oa_row(row_id) for row_id in row_ids)
            has_invoice = _relation_has_row_type(row_types, "invoice") or any(
                _looks_like_invoice_row(row_id) for row_id in row_ids
            )
            special_metadata = row.get("special_metadata") if isinstance(row.get("special_metadata"), dict) else {}
            if not has_oa and text_list(special_metadata.get("oa_row_ids")):
                has_oa = True
            if not has_invoice and text_list(special_metadata.get("invoice_row_ids")):
                has_invoice = True
            self._merge_relation_tags(
                result,
                bank_ids=bank_ids,
                has_oa=has_oa,
                has_invoice=has_invoice,
                case_id=text(row.get("case_id")),
            )
        return result

    def _configure_auto_category_service_from_app_settings(self) -> None:
        row = self._connection.fetch_one(
            """
            select settings_payload
            from app.app_settings
            where settings_key = %s
            limit 1
            """,
            (APP_SETTINGS_KEY,),
        )
        settings_payload = row.get("settings_payload") if isinstance(row, dict) else {}
        bank_transaction_tags = (
            settings_payload.get("bank_transaction_tags")
            if isinstance(settings_payload, dict)
            else None
        )
        self._bank_auto_tag_rules_version = int_value(
            bank_transaction_tags.get("version") if isinstance(bank_transaction_tags, dict) else None,
            1,
        )
        self._auto_category_service.configure_tag_dictionary(
            bank_transaction_tags
            if isinstance(bank_transaction_tags, dict)
            else default_bank_transaction_tag_dictionary_payload()
        )

    @staticmethod
    def _merge_relation_tags(
        result: dict[str, dict[str, Any]],
        *,
        bank_ids: list[str],
        has_oa: bool,
        has_invoice: bool,
        case_id: str | None,
    ) -> None:
        for transaction_id in bank_ids:
            if not transaction_id:
                continue
            current = result.setdefault(
                transaction_id,
                {"oa_relation_tag": "无oa", "invoice_relation_tag": "无发票", "relation_case_id": None},
            )
            if has_oa:
                current["oa_relation_tag"] = "有oa"
            if has_invoice:
                current["invoice_relation_tag"] = "有发票"
            current["relation_case_id"] = current.get("relation_case_id") or case_id

    def _normalize_transaction_row(self, row: dict[str, Any]) -> dict[str, Any]:
        raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}
        normalized_payload = raw_payload.get("normalized_payload") if isinstance(raw_payload.get("normalized_payload"), dict) else raw_payload
        bank_name = text(normalized_payload.get("imported_bank_name") or normalized_payload.get("bank_name")) or "未知银行"
        account_last4 = (
            text(normalized_payload.get("imported_bank_last4") or normalized_payload.get("account_last4"))
            or text(row.get("account_no"))
            or "unknown"
        )[-4:]
        direction = _direction(row.get("txn_direction"), row.get("signed_amount"))
        amount = decimal_text(row.get("amount")) or "0"
        signed_amount = decimal_text(row.get("signed_amount")) or ("-" + amount if direction == "expense" else amount)
        text_fields = _bank_text_display_fields(
            row.get("bank_text_fields"),
            summary=text(row.get("summary")) or "",
            remark=text(row.get("remark")) or "",
            purpose="",
            note="",
        )
        return {
            "id": text(row.get("id")) or "",
            "transaction_id": text(row.get("transaction_id")) or text(row.get("id")) or "",
            "source_batch_id": text(row.get("source_batch_id")),
            "legacy_source_batch_id": text(row.get("legacy_source_batch_id")),
            "account_key": _account_key(bank_name, account_last4),
            "bank_name": bank_name,
            "account_last4": account_last4 or "unknown",
            "account_no": text(row.get("account_no")),
            "account_name": text(row.get("account_name")),
            "trade_time": _trade_time_text(row.get("trade_time")),
            "trade_date": text(row.get("txn_date") or row.get("trade_time")),
            "trade_time_sort": _trade_time_text(row.get("trade_time_sort") or row.get("trade_time") or row.get("txn_date")),
            "direction": direction,
            "direction_label": "收" if direction == "income" else "支",
            "amount": amount,
            "signed_amount": signed_amount,
            "balance": decimal_text(row.get("balance")),
            "currency": text(row.get("currency")) or "CNY",
            "counterparty_name": text(row.get("counterparty_name_raw") or row.get("normalized_counterparty_name")) or "",
            "summary": text_fields["summary_text"],
            "remark": text(row.get("remark")) or "",
            "purpose": text_fields["purpose_text"] or text_fields["note_text"],
            "purpose_text": text_fields["purpose_text"],
            "summary_text": text_fields["summary_text"],
            "note_text": text_fields["note_text"],
            "bank_text_fields": row.get("bank_text_fields") if isinstance(row.get("bank_text_fields"), list) else [],
            "raw_payload": raw_payload,
        }

    def _project_row(
        self,
        row: dict[str, Any],
        *,
        scope_key: str,
        generated_at: str,
        source_versions: dict[str, Any],
        manual_category: dict[str, Any] | None,
        auto_category: dict[str, Any] | None,
        auto_category_context_by_id: dict[str, dict[str, Any]],
        relation: dict[str, Any] | None,
    ) -> dict[str, Any]:
        manual = manual_category or {
            "category_code": None,
            "category_label": None,
            "category_path": [],
            "source": "",
            "category_version": None,
        }
        auto = auto_category or {}
        effective = resolve_effective_category(manual, auto)
        relation_payload = relation or {"oa_relation_tag": "无oa", "invoice_relation_tag": "无发票", "relation_case_id": None}
        relation_tags = [
            str(relation_payload.get("oa_relation_tag") or "无oa"),
            str(relation_payload.get("invoice_relation_tag") or "无发票"),
        ]
        internal_transfer_counterpart = _internal_transfer_counterpart_payload(
            auto,
            effective_category_code=text(effective.get("effective_category_code")),
            context_rows_by_id=auto_category_context_by_id,
        )
        payload = {
            "id": row["id"],
            "trade_time": row.get("trade_time") or row.get("trade_date") or "",
            "counterparty_name": row.get("counterparty_name") or "",
            "direction": row["direction"],
            "direction_label": row["direction_label"],
            "amount": row["amount"],
            "balance": row.get("balance"),
            "summary": row.get("summary_text") or row.get("summary") or "",
            "purpose": row.get("purpose_text") or row.get("purpose") or row.get("note_text") or "",
            "purpose_text": row.get("purpose_text") or "",
            "summary_text": row.get("summary_text") or row.get("summary") or "",
            "note_text": row.get("note_text") or "",
            "bank_name": row["bank_name"],
            "account_last4": row["account_last4"],
            "category_code": effective.get("effective_category_code"),
            "category_label": effective.get("effective_category_label"),
            "category_path": list(effective.get("effective_category_path") or []),
            "category_source": effective.get("effective_category_source") or "",
            "category_version": manual.get("category_version"),
            "manual_category_code": manual.get("category_code"),
            "manual_category_label": manual.get("category_label"),
            "manual_category_path": list(manual.get("category_path") or []),
            "manual_category_source": manual.get("source") or "",
            "manual_category_version": manual.get("category_version"),
            "auto_category_code": auto.get("category_code"),
            "auto_category_label": auto.get("category_label"),
            "auto_category_path": list(auto.get("category_path") or []),
            "auto_category_source": auto.get("source") or "",
            "auto_category_rule_code": auto.get("rule_code"),
            "auto_category_reason": auto.get("reason"),
            "auto_category_confidence": auto.get("confidence"),
            "auto_category_rule_version": auto.get("rule_version") or BANK_TRANSACTION_AUTO_CATEGORY_RULE_VERSION,
            "internal_transfer_counterpart": internal_transfer_counterpart,
            "effective_category_code": effective.get("effective_category_code"),
            "effective_category_label": effective.get("effective_category_label"),
            "effective_category_path": list(effective.get("effective_category_path") or []),
            "effective_category_source": effective.get("effective_category_source") or "",
            "oa_relation_tag": relation_tags[0],
            "invoice_relation_tag": relation_tags[1],
            "relation_tags": relation_tags,
            "relation_case_id": relation_payload.get("relation_case_id"),
        }
        return {
            **row,
            **payload,
            "scope_key": scope_key,
            "search_text": _search_text(payload),
            "schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
            "source_versions": source_versions,
            "generated_at": generated_at,
            "payload": payload,
            "raw_payload": {"source": row.get("raw_payload") or {}, "normalized_payload": payload},
        }

    def _source_versions(self, *, source_version: int | None, row_count: int) -> dict[str, Any]:
        return {
            "source_version": source_version,
            "bank_detail_schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
            "bank_auto_tag_rules_version": self._bank_auto_tag_rules_version,
            "row_count": row_count,
        }


def _is_month_scope(scope_key: str) -> bool:
    return len(scope_key) == 7 and scope_key[4] == "-" and scope_key[:4].isdigit() and scope_key[5:7].isdigit()


def _bank_detail_auto_category_context_bounds(scope_key: str) -> tuple[date, date]:
    month_start = datetime.strptime(f"{scope_key}-01", "%Y-%m-%d").date()
    if month_start.month == 12:
        next_month_start = date(month_start.year + 1, 1, 1)
    else:
        next_month_start = date(month_start.year, month_start.month + 1, 1)
    boundary_window = timedelta(days=2)
    return month_start - boundary_window, next_month_start + boundary_window


def _direction(value: Any, signed_amount: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"income", "credit", "收入", "收"}:
        return "income"
    if raw in {"expense", "debit", "支出", "支"}:
        return "expense"
    try:
        amount = Decimal(str(signed_amount))
    except Exception:
        amount = Decimal("0")
    return "income" if amount >= 0 else "expense"


def _account_key(bank_name: str, account_last4: str) -> str:
    return f"{bank_name.lower().replace(' ', '-')}:{account_last4 or 'unknown'}"


def _internal_transfer_counterpart_payload(
    auto_category: dict[str, Any],
    *,
    effective_category_code: str | None,
    context_rows_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if effective_category_code != "internal_transfer":
        return None
    if auto_category.get("category_code") != "internal_transfer":
        return None
    counterpart_id = text(auto_category.get("counterpart_id"))
    if not counterpart_id:
        return None
    counterpart = context_rows_by_id.get(counterpart_id)
    if not counterpart:
        return None
    return {
        "transaction_id": text(counterpart.get("id")) or counterpart_id,
        "trade_time": text(counterpart.get("trade_time") or counterpart.get("trade_date")) or "",
        "bank_name": text(counterpart.get("bank_name")) or "未知银行",
        "account_last4": text(counterpart.get("account_last4")) or "unknown",
        "amount": decimal_text(counterpart.get("amount")) or "0",
        "direction_label": text(counterpart.get("direction_label")) or "",
        "counterparty_name": text(counterpart.get("counterparty_name")) or "",
    }


def _bank_text_display_fields(
    bank_text_fields: Any,
    *,
    summary: str,
    remark: str,
    purpose: str,
    note: str,
) -> dict[str, str]:
    fields_by_label = _bank_text_fields_by_label(bank_text_fields)
    summary_text = _first_field_value(fields_by_label, SUMMARY_TEXT_LABELS)
    purpose_text = _first_field_value(fields_by_label, PURPOSE_TEXT_LABELS)
    note_text = _first_field_value(fields_by_label, NOTE_TEXT_LABELS)
    if not fields_by_label:
        summary_text = summary
        purpose_text = purpose
        note_text = note or remark
    return {
        "purpose_text": purpose_text.strip(),
        "summary_text": summary_text.strip(),
        "note_text": note_text.strip(),
    }


def _bank_text_fields_by_label(value: Any) -> dict[str, str]:
    fields: dict[str, str] = {}
    if isinstance(value, dict):
        iterable = [{"label": label, "value": field_value} for label, field_value in value.items()]
    else:
        iterable = list(value or []) if isinstance(value, list) else []
    for item in iterable:
        if not isinstance(item, dict):
            continue
        label = text(item.get("label"))
        field_value = text(item.get("value"))
        if label and field_value and label not in fields:
            fields[label] = field_value
    return fields


def _first_field_value(fields_by_label: dict[str, str], labels: tuple[str, ...]) -> str:
    for label in labels:
        value = fields_by_label.get(label)
        if value:
            return value
    return ""


def _trade_time_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat(sep=" ")
    value_text = text(value) or ""
    normalized = value_text.replace("T", " ")
    if len(normalized) >= 25 and normalized[19] in {"+", "-"} and normalized[20:22].isdigit() and normalized[23:25].isdigit():
        return normalized[:19]
    if normalized.endswith("Z") and len(normalized) >= 20:
        return normalized[:19]
    return normalized


def _looks_like_oa_row(row_id: str) -> bool:
    return str(row_id).startswith(("oa-", "oa_", "OA"))


def _looks_like_invoice_row(row_id: str) -> bool:
    return str(row_id).startswith(("iv-", "iv_", "invoice-", "invoice_"))


def _relation_has_row_type(row_types: list[str], expected: str) -> bool:
    normalized_expected = str(expected or "").strip()
    return any(str(row_type or "").strip() == normalized_expected for row_type in row_types)


def _search_text(payload: dict[str, Any]) -> str:
    values = []
    for key in (
        "id",
        "trade_time",
        "counterparty_name",
        "direction_label",
        "amount",
        "balance",
        "summary",
        "purpose",
        "purpose_text",
        "summary_text",
        "note_text",
        "bank_name",
        "account_last4",
        "category_label",
        "auto_category_label",
        "effective_category_label",
        "oa_relation_tag",
        "invoice_relation_tag",
        "relation_case_id",
    ):
        value = payload.get(key)
        if value not in (None, ""):
            values.append(str(value))
    values.extend(str(tag) for tag in payload.get("relation_tags") or [] if str(tag).strip())
    return " ".join(values)

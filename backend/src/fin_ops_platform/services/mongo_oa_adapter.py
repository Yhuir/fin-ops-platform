from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
from threading import Lock, Thread
from time import monotonic
from typing import Any, Callable, Protocol
from urllib.parse import quote_plus

from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from fin_ops_platform.services.imports import clean_string
from fin_ops_platform.services.oa_adapter import (
    OAAdapter,
    OAApplicationRecord,
    OAReadStatus,
    build_attachment_invoice_detail_fields,
    detect_etc_batch_metadata,
)
from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentInvoiceService


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
KEY_NORMALIZE_RE = re.compile(r"[\s_\-:/\\()（）【】\[\]·,.，。]+")
PAYMENT_ROW_ID_RE = re.compile(r"^oa-pay-(.+)$")
EXPENSE_ROW_ID_RE = re.compile(r"^oa-exp-(.+)$")
COMPLETED_PROCESS_VALUES = {"已完成", "2", 2}
IN_PROGRESS_PROCESS_VALUES = {"进行中", "1", 1}
COMPLETED_STATUS_VALUES = {"approved", "APPROVED", "Approved"}
OA_IMPORT_FORM_TYPE_PAYMENT = "payment_request"
OA_IMPORT_FORM_TYPE_EXPENSE = "expense_claim"
OA_IMPORT_STATUS_COMPLETED = "completed"
OA_IMPORT_STATUS_IN_PROGRESS = "in_progress"
OA_IMPORT_FORM_TYPE_OPTIONS = [
    {"id": OA_IMPORT_FORM_TYPE_PAYMENT, "label": "支付申请"},
    {"id": OA_IMPORT_FORM_TYPE_EXPENSE, "label": "日常报销"},
]
OA_IMPORT_STATUS_OPTIONS = [
    {"id": OA_IMPORT_STATUS_COMPLETED, "label": "已完成"},
    {"id": OA_IMPORT_STATUS_IN_PROGRESS, "label": "进行中"},
]
DEFAULT_OA_IMPORT_SETTINGS = {
    "form_types": [OA_IMPORT_FORM_TYPE_PAYMENT, OA_IMPORT_FORM_TYPE_EXPENSE],
    "statuses": [OA_IMPORT_STATUS_COMPLETED],
}
ATTACHMENT_INVOICE_SOURCE_CONTEXT_KEY = "_attachment_invoice_source_context"
ATTACHMENT_EVIDENCE_CACHE_SCHEMA_VERSION = "2026-05-11-evidence-v1"
ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION = ATTACHMENT_EVIDENCE_CACHE_SCHEMA_VERSION
ATTACHMENT_INVOICE_REQUIRED_SOURCE_FIELDS = (
    "source_expense_row_index",
    "source_expense_item_id",
    "source_attachment_key",
    "source_attachment_name",
)
ATTACHMENT_INVOICE_EVIDENCE_TYPES = {"tax_invoice", "machine_invoice", "non_tax_receipt"}

EXPENSE_TYPE_CANDIDATE_KEYS = (
    "feeType",
    "expenseType",
    "costType",
    "typeOfExpense",
    "expenseCategory",
    "feeCategory",
    "costCategory",
    "expenseKind",
    "feeKind",
    "costKind",
    "detailExpenseType",
    "detailFeeType",
    "detailCostType",
    "detailTypeOfExpense",
    "detailExpenseCategory",
    "detailFeeCategory",
    "detailCostCategory",
    "detailExpenseKind",
    "detailFeeKind",
    "detailCostKind",
    "reimbursementType",
    "detailReimbursementType",
    "费用类型",
    "费用类别",
    "费用归类",
    "费用科目",
    "费用项目",
    "费用名称",
    "报销类型",
    "支出类型",
    "支出类别",
    "开支类型",
    "开支类别",
    "科目",
)

STANDARD_EXPENSE_TYPES: tuple[str, ...] = (
    "设备货款及材料费",
    "人工费/劳务费/服务费",
    "住宿费",
    "招待费（餐费、烟酒等）",
    "交通费",
    "车辆使用费（汽油、过路、保险、维修、税费等）车辆维修",
    "运费/邮费/杂费",
    "房屋使用费（户租、水电、维修、车位、屋业等）",
    "经营/办公费用",
    "财务费用",
    "借款",
    "还款",
    "其他",
    "固定资产",
)

STANDARD_EXPENSE_TYPE_BY_NORMALIZED_KEY = {
    KEY_NORMALIZE_RE.sub("", expense_type).lower(): expense_type for expense_type in STANDARD_EXPENSE_TYPES
}

EXPENSE_TYPE_INFERENCE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("还款", ("还款", "归还", "偿还", "还借款", "还暂借款", "批量还款")),
    ("借款", ("借款", "借入", "借支", "暂借", "借出")),
    ("财务费用", ("利息", "手续费", "结息", "贷款", "还息", "财务费", "贴现", "银行")),
    ("房屋使用费（户租、水电、维修、车位、屋业等）", ("房租", "租金", "水电", "水费", "电费", "物业", "物管", "屋业", "车位", "办公室")),
    ("车辆使用费（汽油、过路、保险、维修、税费等）车辆维修", ("汽油", "加油", "过路", "etc", "保险", "车险", "车辆维修", "维修费", "养护", "车位费", "税费", "审车", "年检")),
    ("交通费", ("交通", "差旅", "机票", "火车", "高铁", "打车", "滴滴", "出行", "往返")),
    ("住宿费", ("住宿", "酒店", "宾馆", "旅馆", "客栈")),
    ("招待费（餐费、烟酒等）", ("招待", "餐费", "用餐", "烟酒", "酒水", "会务餐")),
    ("运费/邮费/杂费", ("运费", "邮费", "快递", "物流", "邮寄", "杂费")),
    ("人工费/劳务费/服务费", ("人工", "劳务", "服务", "运维", "维护", "调试", "安装", "咨询", "设计", "租赁", "会务费")),
    ("固定资产", ("固定资产", "购车", "车辆购置", "电脑", "服务器", "打印机")),
    ("设备货款及材料费", ("货款", "设备", "材料", "模块", "配件", "电源", "风机", "接触器", "软起动器", "控制器", "灯管", "存储卡", "采购")),
    ("经营/办公费用", ("办公", "文具", "耗材", "打印", "宽带", "电话费", "电信", "软件", "订阅", "会务", "专利")),
)


@dataclass(slots=True)
class MongoOASettings:
    host: str
    database: str
    port: int = 27017
    username: str | None = None
    password: str | None = None
    auth_source: str = "admin"
    collection: str = "form_data"
    payment_request_form_id: str = "2"
    expense_claim_form_id: str = "32"
    project_form_id: str = "17"
    request_timeout_ms: int = 5000
    cache_ttl_seconds: int = 30
    project_name_overrides: dict[str, str] = field(default_factory=dict)

    @property
    def mongo_uri(self) -> str:
        credentials = ""
        if self.username:
            password = quote_plus(self.password or "")
            credentials = f"{quote_plus(self.username)}:{password}@"
        return (
            f"mongodb://{credentials}{self.host}:{self.port}/{self.database}"
            f"?authSource={quote_plus(self.auth_source)}"
        )


class OAAttachmentInvoiceCache(Protocol):
    def load_oa_attachment_invoice_cache_entry(self, cache_key: str) -> dict[str, object] | None: ...

    def save_oa_attachment_invoice_cache_entry(self, cache_key: str, payload: dict[str, object]) -> None: ...


def load_mongo_oa_settings(data_dir: Path | None = None) -> MongoOASettings | None:
    file_payload: dict[str, Any] = {}
    if data_dir is not None:
        config_path = data_dir / "oa_mongo_config.json"
        if config_path.exists():
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                file_payload = loaded

    def pick(name: str, file_key: str, default: Any = None) -> Any:
        env_value = os.getenv(name)
        if env_value not in (None, ""):
            return env_value
        return file_payload.get(file_key, default)

    host = pick("FIN_OPS_OA_MONGO_HOST", "host")
    database = pick("FIN_OPS_OA_MONGO_DATABASE", "database")
    if not host or not database:
        return None

    overrides = file_payload.get("project_name_overrides", {})
    return MongoOASettings(
        host=str(host),
        port=int(pick("FIN_OPS_OA_MONGO_PORT", "port", 27017)),
        database=str(database),
        username=pick("FIN_OPS_OA_MONGO_USERNAME", "username"),
        password=pick("FIN_OPS_OA_MONGO_PASSWORD", "password"),
        auth_source=str(pick("FIN_OPS_OA_MONGO_AUTH_SOURCE", "auth_source", "admin")),
        collection=str(pick("FIN_OPS_OA_MONGO_COLLECTION", "collection", "form_data")),
        payment_request_form_id=str(pick("FIN_OPS_OA_PAYMENT_FORM_ID", "payment_request_form_id", "2")),
        expense_claim_form_id=str(pick("FIN_OPS_OA_EXPENSE_FORM_ID", "expense_claim_form_id", "32")),
        project_form_id=str(pick("FIN_OPS_OA_PROJECT_FORM_ID", "project_form_id", "17")),
        request_timeout_ms=int(pick("FIN_OPS_OA_MONGO_TIMEOUT_MS", "request_timeout_ms", 5000)),
        cache_ttl_seconds=int(pick("FIN_OPS_OA_MONGO_CACHE_TTL_SECONDS", "cache_ttl_seconds", 30)),
        project_name_overrides=dict(overrides) if isinstance(overrides, dict) else {},
    )


class MongoOAAdapter(OAAdapter):
    name = "mongo_oa"

    def __init__(
        self,
        *,
        settings: MongoOASettings,
        attachment_invoice_cache: OAAttachmentInvoiceCache | None = None,
    ) -> None:
        self._settings = settings
        self._attachment_invoice_cache = attachment_invoice_cache
        self._attachment_invoice_cache_updated_callback: Callable[[list[str]], None] | None = None
        self._attachment_invoice_parse_lock = Lock()
        self._attachment_invoice_parse_inflight: set[str] = set()
        self._attachment_invoice_parse_suppression_depth = 0
        self._attachment_invoice_sync_parse_depth = 0
        self._attachment_invoice_force_reparse_depth = 0
        self._client: MongoClient | None = None
        self._project_name_cache: dict[str, str] | None = None
        self._records_cache: dict[str, tuple[float, list[OAApplicationRecord]]] = {}
        self._available_months_cache: tuple[float, list[str]] | None = None
        self._mongo_unavailable_until = 0.0
        self._last_read_status = OAReadStatus(code="idle", message="OA 待读取")
        self._import_settings_provider: Callable[[], dict[str, list[str]]] | None = None
        self._import_settings_signature: str | None = None
        self._attachment_invoice_service = OAAttachmentInvoiceService(
            timeout_seconds=max(self._settings.request_timeout_ms / 1000, 1),
        )

    def set_import_settings_provider(self, provider: Callable[[], dict[str, list[str]]] | None) -> None:
        self._import_settings_provider = provider
        self._import_settings_signature = None
        self._records_cache.clear()
        self._available_months_cache = None

    def set_import_filter_provider(self, provider: Callable[[], dict[str, list[str]]] | None) -> None:
        self.set_import_settings_provider(provider)

    def set_attachment_invoice_cache_updated_callback(self, callback: Callable[[list[str]], None] | None) -> None:
        self._attachment_invoice_cache_updated_callback = callback

    def invalidate_records_cache(self, months: list[str] | None = None) -> None:
        normalized_months = {
            str(month).strip()
            for month in list(months or [])
            if MONTH_RE.match(str(month).strip())
        }
        if not normalized_months:
            self._records_cache.clear()
            self._available_months_cache = None
            self._project_name_cache = None
            return
        for month in normalized_months:
            self._records_cache.pop(month, None)
        self._records_cache.pop("__all__", None)
        self._available_months_cache = None

    def poll_sync_fingerprints(self) -> dict[str, str]:
        self._sync_import_settings_cache()
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return {}

        documents_by_month: dict[str, list[dict[str, Any]]] = {}
        enabled_forms = (
            (self._settings.payment_request_form_id, OA_IMPORT_FORM_TYPE_PAYMENT),
            (self._settings.expense_claim_form_id, OA_IMPORT_FORM_TYPE_EXPENSE),
        )
        for form_id, form_type in enabled_forms:
            if not self._should_include_form_type(form_type):
                continue
            documents = self._find_documents(
                self._build_form_query(form_id),
                projection=self._polling_fingerprint_projection(),
            )
            if self._mongo_temporarily_unavailable():
                self._set_read_status("error", "OA 连接失败")
                return {}
            for document in documents:
                data = self._document_data(document)
                if not self._should_include_document(form_type, data):
                    continue
                month = self._derive_month(data, document)
                if not MONTH_RE.match(month):
                    continue
                fingerprint_document = self._polling_fingerprint_document(form_type, document)
                documents_by_month.setdefault(month, []).append(fingerprint_document)

        fingerprints = {
            month: self._hash_polling_documents(documents)
            for month, documents in documents_by_month.items()
        }
        all_documents = [
            document
            for month in sorted(documents_by_month)
            for document in documents_by_month[month]
        ]
        fingerprints["all"] = self._hash_polling_documents(all_documents)
        self._set_read_status("ready", "OA 已同步")
        return fingerprints

    @staticmethod
    def _polling_fingerprint_projection() -> dict[str, int]:
        return {
            "_id": 1,
            "form_id": 1,
            "modifiedTime": 1,
            "createdTime": 1,
            "data": 1,
        }

    def _polling_fingerprint_document(self, form_type: str, document: dict[str, Any]) -> dict[str, Any]:
        data = self._document_data(document)
        return {
            "_id": self._document_id(document),
            "form_type": form_type,
            "external_id": self._document_external_id(
                self._settings.payment_request_form_id if form_type == OA_IMPORT_FORM_TYPE_PAYMENT else self._settings.expense_claim_form_id,
                document,
            ),
            "month": self._derive_month(data, document),
            "status": self._canonical_status_key(data),
            "modifiedTime": self._datetime_string(document.get("modifiedTime")),
            "createdTime": self._datetime_string(document.get("createdTime")),
            "data": data,
        }

    @staticmethod
    def _hash_polling_documents(documents: list[dict[str, Any]]) -> str:
        normalized_payload = json.dumps(
            sorted(documents, key=lambda item: (str(item.get("form_type")), str(item.get("external_id")), str(item.get("_id")))),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(normalized_payload.encode("utf-8")).hexdigest()

    @contextmanager
    def suppress_attachment_invoice_background_parse(self):
        self._attachment_invoice_parse_suppression_depth += 1
        try:
            yield
        finally:
            self._attachment_invoice_parse_suppression_depth = max(
                0,
                self._attachment_invoice_parse_suppression_depth - 1,
            )

    @contextmanager
    def force_attachment_invoice_sync_parse(self):
        self._attachment_invoice_sync_parse_depth += 1
        try:
            yield
        finally:
            self._attachment_invoice_sync_parse_depth = max(
                0,
                self._attachment_invoice_sync_parse_depth - 1,
            )

    @contextmanager
    def force_attachment_invoice_reparse(self):
        self._attachment_invoice_sync_parse_depth += 1
        self._attachment_invoice_force_reparse_depth += 1
        try:
            yield
        finally:
            self._attachment_invoice_sync_parse_depth = max(
                0,
                self._attachment_invoice_sync_parse_depth - 1,
            )
            self._attachment_invoice_force_reparse_depth = max(
                0,
                self._attachment_invoice_force_reparse_depth - 1,
            )

    def parse_attachment_invoices_for_months(self, months: list[str]) -> None:
        normalized_months = [
            str(month).strip()
            for month in list(months or [])
            if MONTH_RE.match(str(month).strip())
        ]
        if not normalized_months:
            return
        with self.force_attachment_invoice_sync_parse():
            for month in normalized_months:
                self.list_application_records(month)

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        if not MONTH_RE.match(month):
            return []
        self._sync_import_settings_cache()
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []

        cached_records = self._records_cache.get(month)
        now = self._now()
        if cached_records is not None and self._settings.cache_ttl_seconds > 0:
            cached_at, records = cached_records
            if now - cached_at < self._settings.cache_ttl_seconds:
                self._set_read_status("ready", "OA 已同步")
                return deepcopy(records)

        project_names = self._project_name_index()
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []
        records: list[OAApplicationRecord] = []
        if self._should_include_form_type(OA_IMPORT_FORM_TYPE_PAYMENT):
            payment_documents = self._load_form_documents(self._settings.payment_request_form_id, month)
            if self._mongo_temporarily_unavailable():
                self._set_read_status("error", "OA 连接失败")
                return []
            for document in payment_documents:
                record = self._build_payment_request_record(document, project_names)
                if record is not None:
                    records.append(record)
        if self._should_include_form_type(OA_IMPORT_FORM_TYPE_EXPENSE):
            expense_documents = self._load_form_documents(self._settings.expense_claim_form_id, month)
            if self._mongo_temporarily_unavailable():
                self._set_read_status("error", "OA 连接失败")
                return sorted(records, key=lambda item: (item.month, item.id))
            for document in expense_documents:
                records.extend(self._build_expense_claim_records(document, project_names))
        sorted_records = sorted(records, key=lambda item: (item.month, item.id))
        if self._settings.cache_ttl_seconds > 0:
            self._records_cache[month] = (now, deepcopy(sorted_records))
        self._set_read_status("ready", "OA 已同步")
        return sorted_records

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        cache_key = "__all__"
        self._sync_import_settings_cache()
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []

        cached_records = self._records_cache.get(cache_key)
        now = self._now()
        if cached_records is not None and self._settings.cache_ttl_seconds > 0:
            cached_at, records = cached_records
            if now - cached_at < self._settings.cache_ttl_seconds:
                self._set_read_status("ready", "OA 已同步")
                return deepcopy(records)

        project_names = self._project_name_index()
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []

        records: list[OAApplicationRecord] = []
        if self._should_include_form_type(OA_IMPORT_FORM_TYPE_PAYMENT):
            payment_documents = self._load_form_documents(self._settings.payment_request_form_id)
            if self._mongo_temporarily_unavailable():
                self._set_read_status("error", "OA 连接失败")
                return []
            for document in payment_documents:
                record = self._build_payment_request_record(document, project_names)
                if record is not None:
                    records.append(record)

        if self._should_include_form_type(OA_IMPORT_FORM_TYPE_EXPENSE):
            expense_documents = self._load_form_documents(self._settings.expense_claim_form_id)
            if self._mongo_temporarily_unavailable():
                self._set_read_status("error", "OA 连接失败")
                return sorted(records, key=lambda item: (item.month, item.id))
            for document in expense_documents:
                records.extend(self._build_expense_claim_records(document, project_names))

        sorted_records = sorted(records, key=lambda item: (item.month, item.id))
        if self._settings.cache_ttl_seconds > 0:
            self._records_cache[cache_key] = (now, deepcopy(sorted_records))
        self._set_read_status("ready", "OA 已同步")
        return sorted_records

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        normalized_row_ids = [str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()]
        if not normalized_row_ids:
            return []
        self._sync_import_settings_cache()
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []

        project_names = self._project_name_index()
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []

        payment_external_ids: set[str] = set()
        expense_external_ids: set[str] = set()
        expense_row_aliases: dict[str, list[str]] = {}
        for row_id in normalized_row_ids:
            parsed = self._parse_oa_row_id(row_id)
            if parsed is None:
                continue
            record_kind, external_id, _row_index = parsed
            if record_kind == "payment" and self._should_include_form_type(OA_IMPORT_FORM_TYPE_PAYMENT):
                payment_external_ids.add(external_id)
            elif record_kind == "expense" and self._should_include_form_type(OA_IMPORT_FORM_TYPE_EXPENSE):
                candidates = self._expense_external_id_candidates_from_row_id(row_id)
                expense_external_ids.update(candidates)
                expense_row_aliases[row_id] = candidates

        records_by_id: dict[str, OAApplicationRecord] = {}
        if payment_external_ids:
            payment_documents = self._load_form_documents_by_external_ids(
                self._settings.payment_request_form_id,
                payment_external_ids,
            )
            if self._mongo_temporarily_unavailable():
                self._set_read_status("error", "OA 连接失败")
                return [records_by_id[row_id] for row_id in normalized_row_ids if row_id in records_by_id]
            for document in payment_documents:
                record = self._build_payment_request_record(document, project_names)
                if record is not None:
                    records_by_id[record.id] = record

        if expense_external_ids:
            expense_documents = self._load_form_documents_by_external_ids(
                self._settings.expense_claim_form_id,
                expense_external_ids,
            )
            if self._mongo_temporarily_unavailable():
                self._set_read_status("error", "OA 连接失败")
                return [records_by_id[row_id] for row_id in normalized_row_ids if row_id in records_by_id]
            records_by_expense_external_id: dict[str, OAApplicationRecord] = {}
            for document in expense_documents:
                for record in self._build_expense_claim_records(document, project_names):
                    records_by_id[record.id] = record
                    external_id = record.id.removeprefix("oa-exp-")
                    records_by_expense_external_id[external_id] = record
            for requested_row_id, candidates in expense_row_aliases.items():
                if requested_row_id in records_by_id:
                    continue
                for candidate in candidates:
                    record = records_by_expense_external_id.get(candidate)
                    if record is not None:
                        records_by_id[requested_row_id] = record
                        break

        self._set_read_status("ready", "OA 已同步")
        requested_records: list[OAApplicationRecord] = []
        seen_record_ids: set[str] = set()
        for row_id in normalized_row_ids:
            record = records_by_id.get(row_id)
            if record is None or record.id in seen_record_ids:
                continue
            requested_records.append(record)
            seen_record_ids.add(record.id)
        return requested_records

    def search_application_records(
        self,
        *,
        q: str | None = None,
        form_types: list[str] | None = None,
        statuses: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[OAApplicationRecord]:
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []
        search_settings = self._normalize_search_import_settings(form_types=form_types, statuses=statuses)
        project_names = self._project_name_index()
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []

        records: list[OAApplicationRecord] = []
        with self._temporary_import_settings(search_settings):
            if OA_IMPORT_FORM_TYPE_PAYMENT in set(search_settings["form_types"]):
                for document in self._load_form_documents(self._settings.payment_request_form_id):
                    record = self._build_payment_request_record(document, project_names)
                    if record is not None:
                        records.append(record)
            if OA_IMPORT_FORM_TYPE_EXPENSE in set(search_settings["form_types"]):
                for document in self._load_form_documents(self._settings.expense_claim_form_id):
                    records.extend(self._build_expense_claim_records(document, project_names))

        filtered_records = [
            record
            for record in records
            if self._record_matches_date_range(record, date_from=date_from, date_to=date_to)
            and self._record_matches_query(record, q)
        ]
        self._set_read_status("ready", "OA 已同步")
        return sorted(filtered_records, key=lambda item: (item.month, item.id))

    def search_application_record_rows(
        self,
        *,
        q: str | None = None,
        form_types: list[str] | None = None,
        statuses: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 0,
        page_size: int = 20,
        imported_entries: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return {"rows": [], "total": 0, "page": page, "page_size": page_size}
        search_settings = self._normalize_search_import_settings(form_types=form_types, statuses=statuses)
        normalized_page = max(0, int(page or 0))
        normalized_page_size = max(1, min(int(page_size or 20), 100))
        if not search_settings["form_types"] or not search_settings["statuses"]:
            return {"rows": [], "total": 0, "page": normalized_page, "page_size": normalized_page_size}
        window_limit = (normalized_page + 1) * normalized_page_size
        project_names = self._project_name_index()
        project_query_values = self._project_query_values(q, project_names)
        imported_by_id = dict(imported_entries or {})

        rows: list[dict[str, object]] = []
        total = 0
        projection = self._search_document_projection()
        for form_type in search_settings["form_types"]:
            form_id = (
                self._settings.payment_request_form_id
                if form_type == OA_IMPORT_FORM_TYPE_PAYMENT
                else self._settings.expense_claim_form_id
            )
            query = self._build_search_form_query(
                form_id=form_id,
                form_type=form_type,
                q=q,
                statuses=search_settings["statuses"],
                date_from=date_from,
                date_to=date_to,
                project_query_values=project_query_values,
            )
            total += self._count_search_documents(query)
            documents = self._search_form_documents(
                form_id,
                query,
                projection=projection,
                limit=window_limit,
            )
            for document in documents:
                row = self._search_document_to_row(
                    document,
                    form_type=form_type,
                    project_names=project_names,
                    imported_entries=imported_by_id,
                )
                if row is not None:
                    rows.append(row)

        rows.sort(key=lambda item: (clean_string(item.get("application_date") or ""), clean_string(item.get("row_id") or "")))
        start = normalized_page * normalized_page_size
        end = start + normalized_page_size
        self._set_read_status("ready", "OA 已同步")
        return {
            "rows": rows[start:end],
            "total": total,
            "page": normalized_page,
            "page_size": normalized_page_size,
        }

    def refresh_application_record_attachments(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        normalized_row_ids = [str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()]
        if not normalized_row_ids:
            return []
        refresh_settings = {
            "form_types": [item["id"] for item in OA_IMPORT_FORM_TYPE_OPTIONS],
            "statuses": [item["id"] for item in OA_IMPORT_STATUS_OPTIONS],
        }
        with self._temporary_import_settings(refresh_settings):
            with self.force_attachment_invoice_reparse():
                records = self.list_application_records_by_row_ids(normalized_row_ids)
        months = sorted({record.month for record in records if MONTH_RE.match(str(record.month))})
        if months:
            self.invalidate_records_cache(months)
        return records

    def list_available_months(self) -> list[str]:
        now = self._now()
        self._sync_import_settings_cache()
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []
        if self._available_months_cache is not None and self._settings.cache_ttl_seconds > 0:
            cached_at, months = self._available_months_cache
            if now - cached_at < self._settings.cache_ttl_seconds:
                self._set_read_status("ready", "OA 已同步")
                return list(months)

        months: set[str] = set()
        enabled_forms = (
            (self._settings.payment_request_form_id, OA_IMPORT_FORM_TYPE_PAYMENT),
            (self._settings.expense_claim_form_id, OA_IMPORT_FORM_TYPE_EXPENSE),
        )
        for form_id, form_type in enabled_forms:
            if not self._should_include_form_type(form_type):
                continue
            documents = self._load_form_month_documents(form_id)
            if self._mongo_temporarily_unavailable():
                self._set_read_status("error", "OA 连接失败")
                return sorted(months)
            for document in documents:
                data = self._document_data(document)
                if not self._should_include_document(form_type, data):
                    continue
                derived_month = self._derive_month(data, document)
                if MONTH_RE.match(derived_month):
                    months.add(derived_month)
        ordered_months = sorted(months)
        if self._settings.cache_ttl_seconds > 0:
            self._available_months_cache = (now, list(ordered_months))
        self._set_read_status("ready", "OA 已同步")
        return ordered_months

    def get_read_status(self) -> OAReadStatus:
        return OAReadStatus(code=self._last_read_status.code, message=self._last_read_status.message)

    def list_oa_import_filter_options(self) -> dict[str, list[dict[str, str]]]:
        seen_form_types: set[str] = set()
        seen_statuses: set[str] = set()
        for form_id, form_type in (
            (self._settings.payment_request_form_id, OA_IMPORT_FORM_TYPE_PAYMENT),
            (self._settings.expense_claim_form_id, OA_IMPORT_FORM_TYPE_EXPENSE),
        ):
            documents = self._load_form_month_documents(form_id)
            if self._mongo_temporarily_unavailable():
                break
            if documents:
                seen_form_types.add(form_type)
            for document in documents:
                status_key = self._canonical_status_key(self._document_data(document))
                if status_key:
                    seen_statuses.add(status_key)

        return {
            "available_form_types": self._ordered_options(
                OA_IMPORT_FORM_TYPE_OPTIONS,
                seen_form_types or {item["id"] for item in OA_IMPORT_FORM_TYPE_OPTIONS},
            ),
            "available_statuses": self._ordered_options(
                OA_IMPORT_STATUS_OPTIONS,
                seen_statuses or {item["id"] for item in OA_IMPORT_STATUS_OPTIONS},
            ),
        }

    def fetch_counterparties(self) -> list[dict[str, Any]]:
        names: dict[str, dict[str, Any]] = {}
        if not self._should_include_form_type(OA_IMPORT_FORM_TYPE_PAYMENT):
            return []
        for document in self._load_form_documents(self._settings.payment_request_form_id):
            data = self._document_data(document)
            if not self._should_include_document(OA_IMPORT_FORM_TYPE_PAYMENT, data):
                continue
            name = self._first_text(data, "beneficiary")
            if not name:
                continue
            names.setdefault(
                name,
                {
                    "external_id": f"oa-cp-{len(names) + 1:04d}",
                    "name": name,
                    "counterparty_type": "customer_vendor",
                },
            )
        return list(names.values())

    def fetch_projects(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        for document in self._load_project_documents():
            data = self._document_data(document)
            project_name = self._first_text(data, "name")
            if not project_name:
                continue
            projects.append(
                {
                    "external_id": self._document_id(document),
                    "project_code": self._first_text(data, "code") or self._document_id(document),
                    "project_name": project_name,
                    "project_status": "active",
                    "department_name": None,
                    "owner_name": self._first_text(data, "projectLeader") or None,
                }
            )
        return projects

    def fetch_documents(self, scope: str) -> list[dict[str, Any]]:
        project_names = self._project_name_index()
        if scope == "payment_requests":
            if not self._should_include_form_type(OA_IMPORT_FORM_TYPE_PAYMENT):
                return []
            documents = []
            for document in self._load_form_documents(self._settings.payment_request_form_id):
                data = self._document_data(document)
                if not self._should_include_document(OA_IMPORT_FORM_TYPE_PAYMENT, data):
                    continue
                documents.append(
                    {
                        "external_id": self._payment_external_id(data, document),
                        "form_no": self._payment_form_no(data, document),
                        "title": self._canonical_apply_type(OA_IMPORT_FORM_TYPE_PAYMENT),
                        "applicant_name": self._first_text(data, "userName", "applicant"),
                        "amount": self._first_text(data, "amount"),
                        "counterparty_name": self._first_text(data, "beneficiary"),
                        "project_external_id": self._first_text(data, "projectName"),
                        "project_name": project_names.get(self._first_text(data, "projectName"), self._first_text(data, "projectName")),
                        "form_status": self._form_status(data),
                        "submitted_at": self._first_text(data, "applicationDate", "ApplicationDate"),
                        "completed_at": self._datetime_string(document.get("modifiedTime")),
                    }
                )
            return documents
        if scope == "expense_claims":
            if not self._should_include_form_type(OA_IMPORT_FORM_TYPE_EXPENSE):
                return []
            documents = []
            for document in self._load_form_documents(self._settings.expense_claim_form_id):
                data = self._document_data(document)
                if not self._should_include_document(OA_IMPORT_FORM_TYPE_EXPENSE, data):
                    continue
                documents.append(
                    {
                        "external_id": self._expense_external_id(data, document),
                        "form_no": self._expense_form_no(data, document),
                        "title": self._canonical_apply_type(OA_IMPORT_FORM_TYPE_EXPENSE),
                        "applicant_name": self._first_text(data, "Reimbursement Personnel", "applicant", "userName"),
                        "amount": self._first_text(data, "amount"),
                        "counterparty_name": "",
                        "project_external_id": self._first_text(data, "projectName"),
                        "project_name": project_names.get(self._first_text(data, "projectName"), self._first_text(data, "projectName")),
                        "form_status": self._form_status(data),
                        "submitted_at": self._first_text(data, "ApplicationDate", "applicationDate"),
                        "completed_at": self._datetime_string(document.get("modifiedTime")),
                    }
                )
            return documents
        return []

    def _build_payment_request_record(
        self,
        document: dict[str, Any],
        project_names: dict[str, str],
    ) -> OAApplicationRecord | None:
        data = self._document_data(document)
        if not self._should_include_document(OA_IMPORT_FORM_TYPE_PAYMENT, data):
            return None
        amount = self._first_text(data, "amount")
        applicant = self._first_text(data, "userName", "applicant")
        reason = self._first_text(data, "cause")
        counterparty = self._first_text(data, "beneficiary")
        if not amount or not applicant or not reason:
            return None
        project_id = self._first_text(data, "projectName")
        project_name = project_names.get(project_id, project_id or "--")
        real_project_names = self._unique_real_project_names([project_name])
        external_id = self._payment_external_id(data, document)
        expense_type = self._resolve_expense_type(data, reason)
        expense_content = reason
        etc_metadata = detect_etc_batch_metadata(data)
        completed_at = self._datetime_string(document.get("modifiedTime"))
        return OAApplicationRecord(
            id=f"oa-pay-{external_id}",
            month=self._derive_month(data, document),
            section="open",
            case_id=None,
            applicant=applicant,
            project_name=project_name,
            apply_type=self._canonical_apply_type(OA_IMPORT_FORM_TYPE_PAYMENT),
            amount=amount,
            counterparty_name=counterparty,
            reason=reason,
            relation_code="pending_match",
            relation_label="待找流水与发票",
            relation_tone="warn",
            expense_type=expense_type,
            expense_content=expense_content,
            source=etc_metadata.get("source"),
            etc_batch_id=etc_metadata.get("etc_batch_id"),
            tags=list(etc_metadata.get("tags") or []),
            project_name_display=project_name,
            project_names=real_project_names,
            detail_fields={
                "OA单号": self._payment_form_no(data, document),
                "表单ID": self._settings.payment_request_form_id,
                "申请日期": self._first_text(data, "applicationDate", "ApplicationDate"),
                "审批完成时间": completed_at or "—",
                "收款账号": self._first_text(data, "payeeAccount"),
                "开户行": self._first_text(data, "bank"),
                "付款方式": self._first_text(data, "paymentMethod"),
                "票据类型": self._first_text(data, "paymentProof"),
                "费用类型": expense_type or "—",
                "费用内容": expense_content or "—",
                "流程状态": self._form_status(data),
            },
        )

    def _build_expense_claim_records(
        self,
        document: dict[str, Any],
        project_names: dict[str, str],
    ) -> list[OAApplicationRecord]:
        data = self._document_data(document)
        if not self._should_include_document(OA_IMPORT_FORM_TYPE_EXPENSE, data):
            return []
        applicant = self._first_text(data, "Reimbursement Personnel", "applicant", "userName")
        if not applicant:
            return []
        items = data.get("schedule")
        if not isinstance(items, list) or not items:
            items = [data]
        external_id = self._expense_external_id(data, document)
        expense_items: list[dict[str, Any]] = []
        project_names_summary: list[str] = []
        expense_types_summary: list[str] = []
        expense_contents_summary: list[str] = []
        reimbursement_dates: list[str] = []
        detail_amounts: list[Decimal] = []
        attachment_file_count = 0
        etc_sources: list[Any] = [data]
        record_month = self._derive_month(data, document)
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            item_amount = self._first_text(item, "detailReimbursementAmount", "amount")
            reason = self._first_text(item, "feeContent", "detailCostStatement") or self._first_text(data, "notes")
            expense_type = self._resolve_expense_type(item, reason)
            expense_content = reason
            project_id = self._first_text(item, "detailProjectName") or self._first_text(data, "projectName")
            project_name = project_names.get(project_id, project_id or "--")
            row_index = clean_string(item.get("row_index", index))
            reimbursement_date = self._first_text(item, "detailReimbursementDate", "reimbursementDate")
            item_amount_decimal = self._parse_amount(item_amount)
            if item_amount_decimal is not None:
                detail_amounts.append(item_amount_decimal)
            if project_name:
                self._append_unique(project_names_summary, project_name)
            if expense_type:
                self._append_unique(expense_types_summary, expense_type)
            if expense_content:
                self._append_unique(expense_contents_summary, expense_content)
            if reimbursement_date:
                reimbursement_dates.append(reimbursement_date)
            item_attachment_files = self._attachment_files(item)
            attachment_file_count += len(item_attachment_files)
            expense_item_id = self._expense_item_id(
                external_id=external_id,
                row_index=row_index,
                item=item,
                project_id=project_id,
                amount=item_amount,
                reimbursement_date=reimbursement_date,
            )
            contextual_attachment_files = self._attachment_files_with_source_context(
                item_attachment_files,
                oa_external_id=external_id,
                source_expense_row_index=row_index,
                source_expense_item_id=expense_item_id,
            )
            item_attachment_pool = self._parse_attachment_evidence_pool(
                contextual_attachment_files,
                month=record_month,
            )
            item_attachment_evidences = self._dedupe_attachment_evidences(
                self._bind_attachment_evidences_to_expense_item(
                    item_attachment_pool["evidences"],
                    attachment_files=contextual_attachment_files,
                    source_expense_row_index=row_index,
                    source_expense_item_id=expense_item_id,
                )
            )
            item_attachment_invoices = self._dedupe_attachment_invoices(
                self._attachment_invoices_from_evidences(item_attachment_evidences)
            )
            item_attachment_artifacts = self._dedupe_attachment_artifacts(
                self._bind_attachment_artifacts_to_expense_item(
                    item_attachment_pool["artifacts"],
                    attachment_files=contextual_attachment_files,
                    source_expense_row_index=row_index,
                    source_expense_item_id=expense_item_id,
                )
            )
            etc_sources.append(item)
            expense_items.append(
                {
                    "row_index": row_index,
                    "expense_item_id": expense_item_id,
                    "project_name": project_name,
                    "amount": item_amount,
                    "expense_type": expense_type or "—",
                    "expense_content": expense_content or "—",
                    "reimbursement_date": reimbursement_date,
                    "attachment_file_count": str(len(item_attachment_files)),
                    "attachment_files": [dict(file_entry) for file_entry in item_attachment_files],
                    "attachment_evidences": item_attachment_evidences,
                    "attachment_artifacts": item_attachment_artifacts,
                    "attachment_invoices": item_attachment_invoices,
                }
            )

        detail_sum = sum(detail_amounts, Decimal("0")) if detail_amounts else None
        header_amount_text = self._first_text(data, "amount", "Amount", "totalAmount", "TotalAmount")
        header_amount = self._parse_amount(header_amount_text)
        amount_source = "header" if header_amount is not None else "detail_sum"
        resolved_amount = header_amount_text if header_amount is not None else self._format_decimal(detail_sum)
        if not resolved_amount:
            return []

        amount_mismatch: dict[str, str] | None = None
        if header_amount is not None and detail_sum is not None and header_amount != detail_sum:
            difference = header_amount - detail_sum
            amount_mismatch = {
                "header_amount": header_amount_text,
                "detail_sum": self._format_decimal(detail_sum),
                "difference": self._format_decimal(difference, decimal_places=self._decimal_places(header_amount_text)),
            }

        attachment_evidences = self._dedupe_attachment_evidences(
            [
                dict(evidence)
                for expense_item in expense_items
                for evidence in expense_item.get("attachment_evidences", [])
                if isinstance(evidence, dict)
            ]
        )
        attachment_artifacts = self._dedupe_attachment_artifacts(
            [
                dict(artifact)
                for expense_item in expense_items
                for artifact in expense_item.get("attachment_artifacts", [])
                if isinstance(artifact, dict)
            ]
        )
        attachment_invoices = self._dedupe_attachment_invoices(
            [
                dict(invoice)
                for expense_item in expense_items
                for invoice in expense_item.get("attachment_invoices", [])
                if isinstance(invoice, dict)
            ]
        )
        etc_metadata = detect_etc_batch_metadata(*etc_sources)
        real_project_names = self._unique_real_project_names(project_names_summary)
        if not real_project_names:
            header_project_id = self._first_text(data, "projectName")
            real_project_names = self._unique_real_project_names(
                [project_names.get(header_project_id, header_project_id or "")]
            )
        project_name_summary = "；".join(real_project_names) or "--"
        project_name_display = self._project_name_display(real_project_names)
        expense_type_summary = "；".join(expense_types_summary) or "—"
        expense_content_summary = "；".join(expense_contents_summary) or self._first_text(data, "notes") or "—"
        reimbursement_date_range = self._date_range_text(reimbursement_dates)

        detail_fields = {
            "OA单号": self._expense_form_no(data, document),
            "表单ID": self._settings.expense_claim_form_id,
            "申请日期": self._first_text(data, "ApplicationDate", "applicationDate"),
            "审批完成时间": self._datetime_string(document.get("modifiedTime")) or "—",
            "流程状态": self._form_status(data),
            "明细数量": str(len(expense_items)),
            "明细金额合计": self._format_decimal(detail_sum) or "—",
            "金额来源": "主表总金额" if amount_source == "header" else "明细合计",
            "项目名称汇总": project_name_summary,
            "项目名称列表": list(real_project_names),
            "费用类型": expense_type_summary,
            "费用类型汇总": expense_type_summary,
            "费用内容": expense_content_summary,
            "费用内容摘要": expense_content_summary,
            "报销日期范围": reimbursement_date_range or "—",
        }
        if amount_mismatch is not None:
            detail_fields["金额差异"] = (
                f"主表总金额 {amount_mismatch['header_amount']}；"
                f"明细合计 {amount_mismatch['detail_sum']}；"
                f"差异 {amount_mismatch['difference']}"
            )
        detail_fields.update(
            build_attachment_invoice_detail_fields(
                attachment_invoices,
                attachment_file_count=attachment_file_count,
                attachment_evidences=attachment_evidences,
                attachment_artifacts=attachment_artifacts,
            )
        )
        return [
            OAApplicationRecord(
                id=f"oa-exp-{external_id}",
                month=record_month,
                section="open",
                case_id=None,
                applicant=applicant,
                project_name=project_name_summary,
                apply_type=self._canonical_apply_type(OA_IMPORT_FORM_TYPE_EXPENSE),
                amount=resolved_amount,
                counterparty_name="",
                reason=expense_content_summary,
                relation_code="pending_match",
                relation_label="待找流水与发票",
                relation_tone="warn",
                expense_type=expense_type_summary,
                expense_content=expense_content_summary,
                detail_fields=detail_fields,
                attachment_evidences=attachment_evidences,
                attachment_artifacts=attachment_artifacts,
                attachment_invoices=attachment_invoices,
                attachment_file_count=attachment_file_count,
                expense_items=expense_items,
                amount_source=amount_source,
                amount_mismatch=amount_mismatch,
                source=etc_metadata.get("source"),
                etc_batch_id=etc_metadata.get("etc_batch_id"),
                tags=list(etc_metadata.get("tags") or []),
                project_name_display=project_name_display,
                project_names=list(real_project_names),
            )
        ]

    def _search_document_to_row(
        self,
        document: dict[str, Any],
        *,
        form_type: str,
        project_names: dict[str, str],
        imported_entries: dict[str, Any],
    ) -> dict[str, object] | None:
        if form_type == OA_IMPORT_FORM_TYPE_PAYMENT:
            return self._payment_search_document_to_row(
                document,
                project_names=project_names,
                imported_entries=imported_entries,
            )
        return self._expense_search_document_to_row(
            document,
            project_names=project_names,
            imported_entries=imported_entries,
        )

    def _payment_search_document_to_row(
        self,
        document: dict[str, Any],
        *,
        project_names: dict[str, str],
        imported_entries: dict[str, Any],
    ) -> dict[str, object] | None:
        data = self._document_data(document)
        applicant = self._first_text(data, "userName", "applicant")
        reason = self._first_text(data, "cause")
        amount = self._first_text(data, "amount")
        if not applicant or not reason or not amount:
            return None
        external_id = self._payment_external_id(data, document)
        project_id = self._first_text(data, "projectName")
        project_name = project_names.get(project_id, project_id or "--")
        return self._search_row(
            row_id=f"oa-pay-{external_id}",
            oa_no=self._payment_form_no(data, document),
            applicant=applicant,
            application_date=self._first_text(data, "applicationDate", "ApplicationDate") or self._derive_month(data, document),
            form_type=OA_IMPORT_FORM_TYPE_PAYMENT,
            status=self._canonical_status_key(data),
            project_name=project_name,
            reason=reason,
            amount=amount,
            attachment_file_count=0,
            importable_invoice_count=0,
            items=[],
            imported_entries=imported_entries,
        )

    def _expense_search_document_to_row(
        self,
        document: dict[str, Any],
        *,
        project_names: dict[str, str],
        imported_entries: dict[str, Any],
    ) -> dict[str, object] | None:
        data = self._document_data(document)
        applicant = self._first_text(data, "Reimbursement Personnel", "applicant", "userName")
        if not applicant:
            return None
        items = data.get("schedule")
        if not isinstance(items, list) or not items:
            items = [data]
        external_id = self._expense_external_id(data, document)
        record_month = self._derive_month(data, document)
        project_names_summary: list[str] = []
        expense_contents_summary: list[str] = []
        detail_amounts: list[Decimal] = []
        item_rows: list[dict[str, object]] = []
        attachment_file_count = 0
        importable_invoice_count = 0
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            item_amount = self._first_text(item, "detailReimbursementAmount", "amount")
            item_amount_decimal = self._parse_amount(item_amount)
            if item_amount_decimal is not None:
                detail_amounts.append(item_amount_decimal)
            reason = self._first_text(item, "feeContent", "detailCostStatement") or self._first_text(data, "notes")
            project_id = self._first_text(item, "detailProjectName") or self._first_text(data, "projectName")
            project_name = project_names.get(project_id, project_id or "--")
            if project_name:
                self._append_unique(project_names_summary, project_name)
            if reason:
                self._append_unique(expense_contents_summary, reason)
            row_index = clean_string(item.get("row_index", index))
            reimbursement_date = self._first_text(item, "detailReimbursementDate", "reimbursementDate")
            item_attachment_files = self._attachment_files(item)
            item_attachment_file_count = len(item_attachment_files)
            expense_item_id = self._expense_item_id(
                external_id=external_id,
                row_index=row_index,
                item=item,
                project_id=project_id,
                amount=item_amount,
                reimbursement_date=reimbursement_date,
            )
            contextual_attachment_files = self._attachment_files_with_source_context(
                item_attachment_files,
                oa_external_id=external_id,
                source_expense_row_index=row_index,
                source_expense_item_id=expense_item_id,
            )
            item_invoice_count = self._cached_attachment_invoice_count(contextual_attachment_files)
            attachment_file_count += item_attachment_file_count
            importable_invoice_count += item_invoice_count
            item_rows.append(
                {
                    "date": reimbursement_date or self._first_text(data, "ApplicationDate", "applicationDate") or record_month,
                    "amount": item_amount,
                    "content": reason,
                    "project_name": project_name,
                    "reason": reason,
                    "attachment_file_count": item_attachment_file_count,
                    "importable_invoice_count": item_invoice_count,
                }
            )
        detail_sum = sum(detail_amounts, Decimal("0")) if detail_amounts else None
        header_amount_text = self._first_text(data, "amount", "Amount", "totalAmount", "TotalAmount")
        header_amount = self._parse_amount(header_amount_text)
        amount = header_amount_text if header_amount is not None else self._format_decimal(detail_sum)
        if not amount:
            return None
        real_project_names = self._unique_real_project_names(project_names_summary)
        if not real_project_names:
            header_project_id = self._first_text(data, "projectName")
            real_project_names = self._unique_real_project_names(
                [project_names.get(header_project_id, header_project_id or "")]
            )
        project_name_summary = "；".join(real_project_names) or "--"
        reason_summary = "；".join(expense_contents_summary) or self._first_text(data, "notes") or "—"
        return self._search_row(
            row_id=f"oa-exp-{external_id}",
            oa_no=self._expense_form_no(data, document),
            applicant=applicant,
            application_date=self._first_text(data, "ApplicationDate", "applicationDate") or record_month,
            form_type=OA_IMPORT_FORM_TYPE_EXPENSE,
            status=self._canonical_status_key(data),
            project_name=project_name_summary,
            reason=reason_summary,
            amount=amount,
            attachment_file_count=attachment_file_count,
            importable_invoice_count=importable_invoice_count,
            items=item_rows,
            imported_entries=imported_entries,
        )

    def _search_row(
        self,
        *,
        row_id: str,
        oa_no: str,
        applicant: str,
        application_date: str,
        form_type: str,
        status: str,
        project_name: str,
        reason: str,
        amount: str,
        attachment_file_count: int,
        importable_invoice_count: int,
        items: list[dict[str, object]],
        imported_entries: dict[str, Any],
    ) -> dict[str, object]:
        imported_entry = imported_entries.get(row_id, {})
        can_import = status == OA_IMPORT_STATUS_COMPLETED
        return {
            "row_id": row_id,
            "oa_no": oa_no or row_id,
            "applicant": applicant,
            "application_date": application_date,
            "form_type": form_type,
            "form_type_label": "支付申请" if form_type == OA_IMPORT_FORM_TYPE_PAYMENT else "日常报销",
            "status": status,
            "status_label": "已完成" if status == OA_IMPORT_STATUS_COMPLETED else "进行中",
            "project_name": project_name,
            "reason": reason,
            "amount": amount,
            "attachment_file_count": attachment_file_count,
            "importable_invoice_count": importable_invoice_count,
            "unrecognized_attachment_count": max(0, attachment_file_count - importable_invoice_count),
            "import_status": "imported" if row_id in imported_entries else "not_imported",
            "imported_at": imported_entry.get("imported_at") if isinstance(imported_entry, dict) else None,
            "can_import": can_import,
            "disabled_reason": "" if can_import else "流程未完成",
            "items": items,
        }

    def _cached_attachment_invoice_count(self, files: list[dict[str, object]]) -> int:
        cache = self._attachment_invoice_cache
        if cache is None or not files:
            return 0
        total = 0
        for file_entry in files:
            cached_entry = cache.load_oa_attachment_invoice_cache_entry(self._attachment_invoice_cache_key(file_entry))
            if cached_entry is None or not self._is_current_attachment_invoice_cache_entry(cached_entry):
                continue
            total += len([invoice for invoice in cached_entry.get("invoices", []) if isinstance(invoice, dict)])
        return total

    @classmethod
    def _project_name_display(cls, project_names: list[str]) -> str:
        real_project_names = cls._unique_real_project_names(project_names)
        if len(real_project_names) > 1:
            return "多个项目"
        if len(real_project_names) == 1:
            return real_project_names[0]
        return "--"

    @staticmethod
    def _unique_real_project_names(project_names: list[str]) -> list[str]:
        result: list[str] = []
        for project_name in project_names:
            text = clean_string(project_name)
            if not text or text in {"--", "—"} or text in result:
                continue
            result.append(text)
        return result

    @staticmethod
    def _attachment_files(item: dict[str, Any]) -> list[dict[str, object]]:
        attachment = item.get("detailReimbursementAttachment")
        if not isinstance(attachment, dict):
            return []
        files = attachment.get("files")
        if isinstance(files, list):
            return [file_entry for file_entry in files if isinstance(file_entry, dict)]

        file_list = attachment.get("list")
        if not isinstance(file_list, list):
            return []
        normalized_entries: list[dict[str, object]] = []
        for file_entry in file_list:
            normalized = MongoOAAdapter._normalize_attachment_list_entry(file_entry)
            if normalized is not None:
                normalized_entries.append(normalized)
        return normalized_entries

    @staticmethod
    def _normalize_attachment_list_entry(file_entry: object) -> dict[str, object] | None:
        if not isinstance(file_entry, dict):
            return None
        response = file_entry.get("response")
        extra = response.get("extra") if isinstance(response, dict) else None
        if isinstance(extra, dict):
            file_name = clean_string(extra.get("fileName") or file_entry.get("name") or "")
            file_path = clean_string(
                extra.get("filePath")
                or extra.get("url")
                or (response.get("data") if isinstance(response, dict) else "")
                or ""
            )
            suffix = clean_string(extra.get("suffix") or Path(file_name or file_path).suffix.lstrip(".")).lower()
            if file_name or file_path:
                return {
                    "fileName": file_name,
                    "filePath": file_path,
                    "suffix": suffix,
                }
        file_name = clean_string(file_entry.get("name") or file_entry.get("fileName") or "")
        file_path = clean_string(file_entry.get("filePath") or file_entry.get("url") or "")
        suffix = clean_string(file_entry.get("suffix") or Path(file_name or file_path).suffix.lstrip(".")).lower()
        if not file_name and not file_path:
            return None
        return {
            "fileName": file_name,
            "filePath": file_path,
            "suffix": suffix,
        }

    @staticmethod
    def _attachment_files_with_source_context(
        files: list[dict[str, object]],
        *,
        oa_external_id: str,
        source_expense_row_index: str,
        source_expense_item_id: str,
    ) -> list[dict[str, object]]:
        contextual_files: list[dict[str, object]] = []
        context = {
            "oa_external_id": clean_string(oa_external_id),
            "source_expense_row_index": clean_string(source_expense_row_index),
            "source_expense_item_id": clean_string(source_expense_item_id),
        }
        for file_entry in files:
            if not isinstance(file_entry, dict):
                continue
            contextual_file = dict(file_entry)
            contextual_file[ATTACHMENT_INVOICE_SOURCE_CONTEXT_KEY] = dict(context)
            contextual_files.append(contextual_file)
        return contextual_files

    @staticmethod
    def _expense_item_id(
        *,
        external_id: str,
        row_index: str,
        item: dict[str, Any],
        project_id: str,
        amount: str,
        reimbursement_date: str,
    ) -> str:
        fingerprint = {
            "external_id": clean_string(external_id),
            "row_index": clean_string(row_index),
            "project_id": clean_string(project_id),
            "amount": clean_string(amount),
            "reimbursement_date": clean_string(reimbursement_date),
            "content": clean_string(item.get("feeContent") or item.get("detailCostStatement") or ""),
        }
        raw_fingerprint = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw_fingerprint.encode("utf-8")).hexdigest()[:12]
        return f"oa-exp-{clean_string(external_id)}:item:{clean_string(row_index)}:{digest}"

    def _bind_attachment_invoices_to_expense_item(
        self,
        invoices: list[dict[str, str]],
        *,
        attachment_files: list[dict[str, object]],
        source_expense_row_index: str,
        source_expense_item_id: str,
    ) -> list[dict[str, str]]:
        if not invoices:
            return []

        files_by_name: dict[str, dict[str, object]] = {}
        for file_entry in attachment_files:
            display_name = self._attachment_display_name(file_entry)
            if display_name:
                files_by_name.setdefault(display_name, file_entry)
        fallback_file = attachment_files[0] if len(attachment_files) == 1 else None

        bound_invoices: list[dict[str, str]] = []
        for invoice in invoices:
            if not isinstance(invoice, dict):
                continue
            bound_invoice = dict(invoice)
            invoice_attachment_name = clean_string(
                bound_invoice.get("source_attachment_name")
                or bound_invoice.get("attachment_name")
                or ""
            )
            source_file = files_by_name.get(invoice_attachment_name) if invoice_attachment_name else fallback_file
            if source_file is None and invoice_attachment_name:
                source_attachment_name = invoice_attachment_name
            elif source_file is not None:
                source_attachment_name = self._attachment_display_name(source_file)
            else:
                source_attachment_name = invoice_attachment_name

            source_attachment_key = (
                self._source_attachment_key(source_file)
                if source_file is not None
                else self._source_attachment_key(
                    {
                        "fileName": source_attachment_name,
                        ATTACHMENT_INVOICE_SOURCE_CONTEXT_KEY: {
                            "source_expense_row_index": source_expense_row_index,
                            "source_expense_item_id": source_expense_item_id,
                        },
                    }
                )
            )
            bound_invoice["source_expense_row_index"] = clean_string(source_expense_row_index)
            bound_invoice["source_expense_item_id"] = clean_string(source_expense_item_id)
            bound_invoice["source_attachment_key"] = source_attachment_key
            bound_invoice["source_attachment_name"] = source_attachment_name
            bound_invoice["attachment_name"] = source_attachment_name
            bound_invoices.append(bound_invoice)
        self._save_bound_attachment_invoice_cache_entries(bound_invoices, attachment_files)
        return bound_invoices

    def _bind_attachment_evidences_to_expense_item(
        self,
        evidences: list[dict[str, str]],
        *,
        attachment_files: list[dict[str, object]],
        source_expense_row_index: str,
        source_expense_item_id: str,
    ) -> list[dict[str, str]]:
        return self._bind_attachment_rows_to_expense_item(
            evidences,
            attachment_files=attachment_files,
            source_expense_row_index=source_expense_row_index,
            source_expense_item_id=source_expense_item_id,
        )

    def _bind_attachment_artifacts_to_expense_item(
        self,
        artifacts: list[dict[str, str]],
        *,
        attachment_files: list[dict[str, object]],
        source_expense_row_index: str,
        source_expense_item_id: str,
    ) -> list[dict[str, str]]:
        source_artifacts = artifacts
        if not source_artifacts:
            source_artifacts = [
                self._attachment_artifact_for_file(file_entry, evidences=[])
                for file_entry in attachment_files
            ]
        return self._bind_attachment_rows_to_expense_item(
            source_artifacts,
            attachment_files=attachment_files,
            source_expense_row_index=source_expense_row_index,
            source_expense_item_id=source_expense_item_id,
        )

    def _bind_attachment_rows_to_expense_item(
        self,
        rows: list[dict[str, str]],
        *,
        attachment_files: list[dict[str, object]],
        source_expense_row_index: str,
        source_expense_item_id: str,
    ) -> list[dict[str, str]]:
        if not rows:
            return []

        files_by_name: dict[str, dict[str, object]] = {}
        for file_entry in attachment_files:
            display_name = self._attachment_display_name(file_entry)
            if display_name:
                files_by_name.setdefault(display_name, file_entry)
        fallback_file = attachment_files[0] if len(attachment_files) == 1 else None

        bound_rows: list[dict[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            bound_row = dict(row)
            row_attachment_name = clean_string(
                bound_row.get("source_attachment_name")
                or bound_row.get("attachment_name")
                or bound_row.get("source_attachment_key")
                or ""
            )
            source_file = files_by_name.get(row_attachment_name) if row_attachment_name else fallback_file
            if source_file is None and row_attachment_name:
                source_attachment_name = row_attachment_name
            elif source_file is not None:
                source_attachment_name = self._attachment_display_name(source_file)
            else:
                source_attachment_name = row_attachment_name

            source_attachment_key = (
                self._source_attachment_key(source_file)
                if source_file is not None
                else self._source_attachment_key(
                    {
                        "fileName": source_attachment_name,
                        ATTACHMENT_INVOICE_SOURCE_CONTEXT_KEY: {
                            "source_expense_row_index": source_expense_row_index,
                            "source_expense_item_id": source_expense_item_id,
                        },
                    }
                )
            )
            bound_row["source_expense_row_index"] = clean_string(source_expense_row_index)
            bound_row["source_expense_item_id"] = clean_string(source_expense_item_id)
            bound_row["source_attachment_key"] = source_attachment_key
            bound_row["source_attachment_name"] = source_attachment_name
            if source_attachment_name:
                bound_row["attachment_name"] = source_attachment_name
            if not clean_string(bound_row.get("evidence_id") or "") and clean_string(bound_row.get("evidence_type") or ""):
                bound_row["evidence_id"] = self._attachment_evidence_id(bound_row)
            bound_rows.append(bound_row)
        return bound_rows

    def _save_bound_attachment_invoice_cache_entries(
        self,
        invoices: list[dict[str, str]],
        attachment_files: list[dict[str, object]],
    ) -> None:
        cache = self._attachment_invoice_cache
        if cache is None or not invoices or not attachment_files:
            return
        cache_key_by_source_attachment_key = {
            self._source_attachment_key(file_entry): self._attachment_invoice_cache_key(file_entry)
            for file_entry in attachment_files
        }
        invoices_by_cache_key: dict[str, list[dict[str, str]]] = {}
        for invoice in invoices:
            source_attachment_key = clean_string(invoice.get("source_attachment_key") or "")
            cache_key = cache_key_by_source_attachment_key.get(source_attachment_key, "")
            if not cache_key:
                continue
            invoices_by_cache_key.setdefault(cache_key, []).append(dict(invoice))
        for cache_key, cache_invoices in invoices_by_cache_key.items():
            cache_evidences = [dict(invoice) for invoice in cache_invoices]
            cache.save_oa_attachment_invoice_cache_entry(
                cache_key,
                {
                    "cache_key": cache_key,
                    "parser_version": self._attachment_invoice_cache_parser_version(),
                    "cache_schema_version": ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
                    "evidences": cache_evidences,
                    "invoices": cache_invoices,
                    "artifacts": [],
                    "parsed_at": datetime.now().isoformat(),
                },
            )

    @staticmethod
    def _attachment_display_name(file_entry: dict[str, object]) -> str:
        file_name = clean_string(file_entry.get("fileName") or file_entry.get("name") or "")
        file_path = clean_string(file_entry.get("filePath") or file_entry.get("url") or "")
        return file_name or Path(file_path).name

    @staticmethod
    def _attachment_source_context(file_entry: dict[str, object]) -> dict[str, str]:
        context = file_entry.get(ATTACHMENT_INVOICE_SOURCE_CONTEXT_KEY)
        if not isinstance(context, dict):
            return {}
        return {
            "oa_external_id": clean_string(context.get("oa_external_id") or ""),
            "source_expense_row_index": clean_string(context.get("source_expense_row_index") or ""),
            "source_expense_item_id": clean_string(context.get("source_expense_item_id") or ""),
        }

    @classmethod
    def _source_attachment_key(cls, file_entry: dict[str, object]) -> str:
        context = cls._attachment_source_context(file_entry)
        file_id = clean_string(
            file_entry.get("fileId")
            or file_entry.get("file_id")
            or file_entry.get("id")
            or file_entry.get("uid")
            or file_entry.get("attachmentId")
            or file_entry.get("attachment_id")
            or ""
        )
        file_path = clean_string(
            file_entry.get("filePath")
            or file_entry.get("url")
            or file_entry.get("path")
            or file_entry.get("downloadUrl")
            or ""
        )
        file_name = cls._attachment_display_name(file_entry)
        if file_id:
            identity_kind = "id"
            identity = file_id
        elif file_path:
            identity_kind = "path"
            identity = file_path
        else:
            identity_kind = "name"
            identity = file_name
        fingerprint = {
            "identity_kind": identity_kind,
            "identity": identity,
            "suffix": clean_string(file_entry.get("suffix") or Path(file_name or file_path).suffix.lstrip(".")).lower(),
            "oa_external_id": context.get("oa_external_id", ""),
            "source_expense_item_id": context.get("source_expense_item_id", ""),
            "source_expense_row_index": context.get("source_expense_row_index", ""),
        }
        raw_fingerprint = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw_fingerprint.encode("utf-8")).hexdigest()

    def _parse_attachment_invoices(self, files: list[dict[str, object]], *, month: str | None = None) -> list[dict[str, str]]:
        return self._parse_attachment_evidence_pool(files, month=month)["invoices"]

    def _parse_attachment_evidence_pool(
        self,
        files: list[dict[str, object]],
        *,
        month: str | None = None,
    ) -> dict[str, list[dict[str, str]]]:
        if not files:
            return {"evidences": [], "invoices": [], "artifacts": []}
        cache = self._attachment_invoice_cache
        if cache is None:
            artifacts = [
                self._attachment_artifact_for_file(file_entry, evidences=[])
                for file_entry in files
            ]
            return {"evidences": [], "invoices": [], "artifacts": artifacts}

        cached_evidences: list[dict[str, str]] = []
        cached_invoices: list[dict[str, str]] = []
        cached_artifacts: list[dict[str, str]] = []
        missing_files: list[tuple[str, dict[str, object]]] = []
        for file_entry in files:
            cache_key = self._attachment_invoice_cache_key(file_entry)
            legacy_cache_key = self._legacy_attachment_invoice_cache_key(file_entry)
            cached_entry = (
                None
                if self._attachment_invoice_force_reparse_depth > 0
                else cache.load_oa_attachment_invoice_cache_entry(cache_key)
            )
            if (
                cached_entry is None
                and legacy_cache_key != cache_key
                and self._attachment_invoice_force_reparse_depth <= 0
            ):
                cached_entry = cache.load_oa_attachment_invoice_cache_entry(legacy_cache_key)
            if cached_entry is not None and not self._is_current_attachment_invoice_cache_entry(cached_entry):
                migrated_entry = self._migrate_legacy_attachment_invoice_cache_entry(
                    cached_entry,
                    cache_key=cache_key,
                    file_entry=file_entry,
                )
                if migrated_entry is not None:
                    cache.save_oa_attachment_invoice_cache_entry(cache_key, migrated_entry)
                    cached_entry = migrated_entry
            if cached_entry is not None and self._is_current_attachment_invoice_cache_entry(cached_entry):
                normalized_entry, changed = self._normalize_attachment_invoice_cache_entry(cached_entry)
                if changed:
                    cache.save_oa_attachment_invoice_cache_entry(cache_key, normalized_entry)
                    cached_entry = normalized_entry
                cached_evidences.extend(
                    dict(evidence)
                    for evidence in cached_entry["evidences"]
                    if isinstance(evidence, dict)
                )
                cached_invoices.extend(
                    dict(invoice)
                    for invoice in cached_entry["invoices"]
                    if isinstance(invoice, dict)
                )
                cached_artifacts.extend(
                    dict(artifact)
                    for artifact in cached_entry["artifacts"]
                    if isinstance(artifact, dict)
                )
                continue
            missing_files.append((cache_key, file_entry))
        if missing_files and self._attachment_invoice_sync_parse_depth > 0:
            parsed_pool = self._parse_attachment_invoice_files_now(missing_files, month=month)
            cached_evidences.extend(parsed_pool["evidences"])
            cached_invoices.extend(parsed_pool["invoices"])
            cached_artifacts.extend(parsed_pool["artifacts"])
        elif missing_files and self._attachment_invoice_parse_suppression_depth <= 0:
            self._schedule_attachment_invoice_parse(missing_files, month=month)
            cached_artifacts.extend(
                self._attachment_artifact_for_file(file_entry, evidences=[])
                for _cache_key, file_entry in missing_files
            )
        return {
            "evidences": cached_evidences,
            "invoices": cached_invoices,
            "artifacts": cached_artifacts,
        }

    @staticmethod
    def _attachment_invoice_cache_parser_version() -> str:
        return f"{OAAttachmentInvoiceService.PARSER_VERSION}:{ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION}"

    def _is_current_attachment_invoice_cache_entry(self, entry: object) -> bool:
        if not (
            isinstance(entry, dict)
            and entry.get("parser_version") == self._attachment_invoice_cache_parser_version()
            and entry.get("cache_schema_version") == ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION
            and isinstance(entry.get("evidences"), list)
            and isinstance(entry.get("invoices"), list)
            and isinstance(entry.get("artifacts"), list)
        ):
            return False
        evidences = entry.get("evidences", [])
        invoices = entry.get("invoices", [])
        artifacts = entry.get("artifacts", [])
        return (
            all(isinstance(evidence, dict) and self._attachment_invoice_has_source_fields(evidence) for evidence in evidences)
            and all(
            isinstance(invoice, dict) and self._attachment_invoice_has_source_fields(invoice)
            for invoice in invoices
            )
            and all(
                isinstance(artifact, dict) and self._attachment_invoice_has_source_fields(artifact)
                for artifact in artifacts
            )
        )

    @classmethod
    def _migrate_legacy_attachment_invoice_cache_entry(
        cls,
        entry: object,
        *,
        cache_key: str,
        file_entry: dict[str, object],
    ) -> dict[str, object] | None:
        if not isinstance(entry, dict):
            return None
        if entry.get("parser_version") != OAAttachmentInvoiceService.PARSER_VERSION:
            return None
        raw_evidences = entry.get("evidences")
        raw_invoices = entry.get("invoices")
        if not isinstance(raw_evidences, list):
            raw_evidences = []
        if not isinstance(raw_invoices, list):
            raw_invoices = []
        if not raw_evidences and not raw_invoices:
            return None

        evidences = [
            cls._normalize_parsed_attachment_evidence(evidence, file_entry=file_entry)
            for evidence in raw_evidences
            if isinstance(evidence, dict)
        ]
        invoice_evidences = [
            cls._normalize_parsed_attachment_invoice(invoice, file_entry=file_entry)
            for invoice in raw_invoices
            if isinstance(invoice, dict)
        ]
        evidences.extend(invoice_evidences)
        invoices = cls._dedupe_attachment_invoices(cls._attachment_invoices_from_evidences(evidences))
        artifacts = [cls._attachment_artifact_for_file(file_entry, evidences=evidences)]
        return {
            "cache_key": cache_key,
            "parser_version": cls._attachment_invoice_cache_parser_version(),
            "cache_schema_version": ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
            "evidences": evidences,
            "invoices": invoices,
            "artifacts": artifacts,
            "parsed_at": clean_string(entry.get("parsed_at") or "") or datetime.now().isoformat(),
        }

    @staticmethod
    def _attachment_invoice_has_source_fields(invoice: dict[str, object]) -> bool:
        return all(
            bool(clean_string(invoice.get(field) or ""))
            for field in ATTACHMENT_INVOICE_REQUIRED_SOURCE_FIELDS
        )

    @staticmethod
    def _normalize_attachment_invoice_cache_entry(entry: dict[str, object]) -> tuple[dict[str, object], bool]:
        normalized_entry = dict(entry if isinstance(entry, dict) else {})
        evidences = normalized_entry.get("evidences")
        invoices = normalized_entry.get("invoices")
        if not isinstance(evidences, list) or not isinstance(invoices, list):
            return normalized_entry, False

        normalized_evidences: list[dict[str, object]] = []
        normalized_invoices: list[dict[str, object]] = []
        changed = False
        for evidence in evidences:
            if not isinstance(evidence, dict):
                continue
            normalized_evidence = dict(evidence)
            if MongoOAAdapter._normalize_attachment_amount_fields(normalized_evidence):
                changed = True
            normalized_evidences.append(normalized_evidence)
        for invoice in invoices:
            if not isinstance(invoice, dict):
                continue
            normalized_invoice = dict(invoice)
            if MongoOAAdapter._normalize_attachment_amount_fields(normalized_invoice):
                changed = True
            normalized_invoices.append(normalized_invoice)
        normalized_entry["evidences"] = normalized_evidences
        normalized_entry["invoices"] = normalized_invoices
        return normalized_entry, changed

    @staticmethod
    def _normalize_attachment_amount_fields(row: dict[str, object]) -> bool:
        net_amount = clean_string(row.get("net_amount") or "")
        amount = clean_string(row.get("amount") or "")
        total_with_tax = clean_string(row.get("total_with_tax") or "")
        if net_amount and amount != net_amount and (not amount or amount == total_with_tax):
            row["amount"] = net_amount
            return True
        return False

    @staticmethod
    def _attachment_invoice_cache_key(file_entry: dict[str, object]) -> str:
        fingerprint = {
            "cache_schema_version": ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
            "parser_version": MongoOAAdapter._attachment_invoice_cache_parser_version(),
            "source_attachment_key": MongoOAAdapter._source_attachment_key(file_entry),
            "size": clean_string(file_entry.get("size") or file_entry.get("fileSize") or ""),
            "modified_time": clean_string(
                file_entry.get("modifiedTime")
                or file_entry.get("lastModified")
                or file_entry.get("updatedAt")
                or ""
            ),
        }
        raw_fingerprint = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw_fingerprint.encode("utf-8")).hexdigest()

    @staticmethod
    def _legacy_attachment_invoice_cache_key(file_entry: dict[str, object]) -> str:
        if ATTACHMENT_INVOICE_SOURCE_CONTEXT_KEY not in file_entry:
            return MongoOAAdapter._attachment_invoice_cache_key(file_entry)
        legacy_file_entry = {
            key: value
            for key, value in file_entry.items()
            if key != ATTACHMENT_INVOICE_SOURCE_CONTEXT_KEY
        }
        return MongoOAAdapter._attachment_invoice_cache_key(legacy_file_entry)

    @classmethod
    def _attachment_invoice_source_fields(cls, file_entry: dict[str, object]) -> dict[str, str]:
        context = cls._attachment_source_context(file_entry)
        source_attachment_key = cls._source_attachment_key(file_entry)
        source_attachment_name = cls._attachment_display_name(file_entry)
        source_expense_row_index = context.get("source_expense_row_index") or clean_string(
            file_entry.get("source_expense_row_index") or ""
        )
        if not source_expense_row_index:
            source_expense_row_index = "0"
        source_expense_item_id = context.get("source_expense_item_id") or clean_string(
            file_entry.get("source_expense_item_id") or ""
        )
        if not source_expense_item_id:
            source_expense_item_id = f"unknown-expense-item:{source_attachment_key[:12]}"
        return {
            "source_expense_row_index": source_expense_row_index,
            "source_expense_item_id": source_expense_item_id,
            "source_attachment_key": source_attachment_key,
            "source_attachment_name": source_attachment_name,
        }

    @classmethod
    def _normalize_parsed_attachment_invoice(
        cls,
        invoice: dict[str, object],
        *,
        file_entry: dict[str, object],
    ) -> dict[str, str]:
        normalized_invoice = cls._normalize_parsed_attachment_evidence(invoice, file_entry=file_entry)
        if not clean_string(normalized_invoice.get("evidence_type") or ""):
            normalized_invoice["evidence_type"] = "tax_invoice"
        return normalized_invoice

    @classmethod
    def _normalize_parsed_attachment_evidence(
        cls,
        evidence: dict[str, object],
        *,
        file_entry: dict[str, object],
    ) -> dict[str, str]:
        normalized_evidence = {
            str(key): clean_string(value) if value is not None else ""
            for key, value in dict(evidence).items()
        }
        source_fields = cls._attachment_invoice_source_fields(file_entry)
        source_attachment_name = (
            clean_string(normalized_evidence.get("source_attachment_name") or "")
            or source_fields["source_attachment_name"]
            or clean_string(normalized_evidence.get("attachment_name") or "")
        )
        normalized_evidence.update(source_fields)
        if source_attachment_name:
            normalized_evidence["source_attachment_name"] = source_attachment_name
            normalized_evidence["attachment_name"] = source_attachment_name
        if not clean_string(normalized_evidence.get("evidence_id") or ""):
            normalized_evidence["evidence_id"] = cls._attachment_evidence_id(normalized_evidence)
        return normalized_evidence

    @staticmethod
    def _attachment_evidence_id(evidence: dict[str, object]) -> str:
        fingerprint = {
            "evidence_type": clean_string(evidence.get("evidence_type") or ""),
            "document_kind": clean_string(evidence.get("document_kind") or ""),
            "digital_invoice_no": clean_string(evidence.get("digital_invoice_no") or ""),
            "invoice_code": clean_string(evidence.get("invoice_code") or ""),
            "invoice_no": clean_string(evidence.get("invoice_no") or ""),
            "transaction_no": clean_string(evidence.get("transaction_no") or ""),
            "merchant_order_no": clean_string(evidence.get("merchant_order_no") or ""),
            "amount": clean_string(evidence.get("amount") or ""),
            "source_attachment_key": clean_string(evidence.get("source_attachment_key") or ""),
            "source_region_key": clean_string(evidence.get("source_region_key") or ""),
        }
        raw_fingerprint = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw_fingerprint.encode("utf-8")).hexdigest()

    @classmethod
    def _attachment_artifact_for_file(
        cls,
        file_entry: dict[str, object],
        *,
        evidences: list[dict[str, str]],
        parse_status: str | None = None,
        parse_error: str | None = None,
    ) -> dict[str, str]:
        source_fields = cls._attachment_invoice_source_fields(file_entry)
        source_attachment_name = source_fields["source_attachment_name"]
        source_attachment_key = source_fields["source_attachment_key"]
        status = clean_string(parse_status or "") or ("parsed" if evidences else "no_evidence")
        return {
            **source_fields,
            "source_attachment_name": source_attachment_name,
            "attachment_name": source_attachment_name,
            "source_attachment_key": source_attachment_key,
            "file_path": clean_string(
                file_entry.get("filePath")
                or file_entry.get("url")
                or file_entry.get("path")
                or file_entry.get("downloadUrl")
                or ""
            ),
            "suffix": clean_string(file_entry.get("suffix") or Path(source_attachment_name).suffix.lstrip(".")).lower(),
            "parse_status": status,
            "parse_error": clean_string(parse_error or ""),
        }

    def _parse_attachment_file_result_from_service(self, file_entry: dict[str, object]) -> dict[str, object]:
        parse_evidences = getattr(self._attachment_invoice_service, "parse_evidences", None)
        default_parse_evidences = getattr(type(self._attachment_invoice_service), "parse_evidences", None)
        if callable(parse_evidences) and getattr(parse_evidences, "__func__", None) is not default_parse_evidences:
            evidences = self._parse_attachment_evidences_from_service([file_entry])
            return {
                "evidences": evidences,
                "parse_status": "parsed" if evidences else "no_evidence",
                "parse_error": "",
            }
        parse_file_result = getattr(self._attachment_invoice_service, "parse_file_result", None)
        if callable(parse_file_result):
            result = parse_file_result(file_entry)
            return dict(result) if isinstance(result, dict) else {"evidences": [], "parse_status": "parse_failed"}
        evidences = self._parse_attachment_evidences_from_service([file_entry])
        return {
            "evidences": evidences,
            "parse_status": "parsed" if evidences else "no_evidence",
            "parse_error": "",
        }

    def _parse_attachment_evidences_from_service(
        self,
        files: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        parse_evidences = getattr(self._attachment_invoice_service, "parse_evidences", None)
        if callable(parse_evidences):
            return [
                dict(evidence)
                for evidence in parse_evidences(files)
                if isinstance(evidence, dict)
            ]
        return [
            {**dict(invoice), "evidence_type": clean_string(invoice.get("evidence_type") or "tax_invoice")}
            for invoice in self._attachment_invoice_service.parse_files(files)
            if isinstance(invoice, dict)
        ]

    @classmethod
    def _attachment_invoices_from_evidences(cls, evidences: list[dict[str, str]]) -> list[dict[str, str]]:
        return [
            dict(evidence)
            for evidence in evidences
            if cls._is_attachment_invoice_evidence(evidence)
        ]

    @staticmethod
    def _is_attachment_invoice_evidence(evidence: dict[str, object]) -> bool:
        evidence_type = clean_string(evidence.get("evidence_type") or "")
        if evidence_type in ATTACHMENT_INVOICE_EVIDENCE_TYPES:
            return True
        if evidence_type:
            return False
        return bool(
            clean_string(
                evidence.get("digital_invoice_no")
                or evidence.get("invoice_no")
                or evidence.get("invoice_code")
                or ""
            )
        )

    def _schedule_attachment_invoice_parse(
        self,
        files: list[tuple[str, dict[str, object]]],
        *,
        month: str | None = None,
    ) -> None:
        if self._attachment_invoice_cache is None:
            return
        scheduled_files: list[tuple[str, dict[str, object]]] = []
        with self._attachment_invoice_parse_lock:
            for cache_key, file_entry in files:
                if cache_key in self._attachment_invoice_parse_inflight:
                    continue
                self._attachment_invoice_parse_inflight.add(cache_key)
                scheduled_files.append((cache_key, file_entry))
        if not scheduled_files:
            return
        Thread(
            target=self._parse_attachment_invoice_files_in_background,
            kwargs={"files": scheduled_files, "month": month},
            daemon=True,
        ).start()

    def _parse_attachment_invoice_files_now(
        self,
        files: list[tuple[str, dict[str, object]]],
        *,
        month: str | None = None,
    ) -> dict[str, list[dict[str, str]]]:
        cache = self._attachment_invoice_cache
        if cache is None:
            return {"evidences": [], "invoices": [], "artifacts": []}
        parsed_evidences: list[dict[str, str]] = []
        parsed_invoices: list[dict[str, str]] = []
        parsed_artifacts: list[dict[str, str]] = []
        updated = False
        for cache_key, file_entry in files:
            file_result = self._parse_attachment_file_result_from_service(file_entry)
            evidences = [
                self._normalize_parsed_attachment_evidence(evidence, file_entry=file_entry)
                for evidence in list(file_result.get("evidences") or [])
                if isinstance(evidence, dict)
            ]
            invoices = self._dedupe_attachment_invoices(self._attachment_invoices_from_evidences(evidences))
            artifacts = [
                self._attachment_artifact_for_file(
                    file_entry,
                    evidences=evidences,
                    parse_status=clean_string(file_result.get("parse_status") or ""),
                    parse_error=clean_string(file_result.get("parse_error") or ""),
                )
            ]
            cache.save_oa_attachment_invoice_cache_entry(
                cache_key,
                {
                    "cache_key": cache_key,
                    "parser_version": self._attachment_invoice_cache_parser_version(),
                    "cache_schema_version": ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
                    "evidences": evidences,
                    "invoices": invoices,
                    "artifacts": artifacts,
                    "parsed_at": datetime.now().isoformat(),
                },
            )
            parsed_evidences.extend(evidences)
            parsed_invoices.extend(invoices)
            parsed_artifacts.extend(artifacts)
            updated = True
        if updated:
            if month and month in self._records_cache:
                self._records_cache.pop(month, None)
                self._records_cache.pop("__all__", None)
            else:
                self._records_cache.clear()
        return {
            "evidences": parsed_evidences,
            "invoices": parsed_invoices,
            "artifacts": parsed_artifacts,
        }

    def _parse_attachment_invoice_files_in_background(
        self,
        files: list[tuple[str, dict[str, object]]],
        *,
        month: str | None = None,
    ) -> None:
        cache = self._attachment_invoice_cache
        if cache is None:
            return
        updated = False
        try:
            for cache_key, file_entry in files:
                file_result = self._parse_attachment_file_result_from_service(file_entry)
                evidences = [
                    self._normalize_parsed_attachment_evidence(evidence, file_entry=file_entry)
                    for evidence in list(file_result.get("evidences") or [])
                    if isinstance(evidence, dict)
                ]
                invoices = self._dedupe_attachment_invoices(self._attachment_invoices_from_evidences(evidences))
                artifacts = [
                    self._attachment_artifact_for_file(
                        file_entry,
                        evidences=evidences,
                        parse_status=clean_string(file_result.get("parse_status") or ""),
                        parse_error=clean_string(file_result.get("parse_error") or ""),
                    )
                ]
                cache.save_oa_attachment_invoice_cache_entry(
                    cache_key,
                    {
                        "cache_key": cache_key,
                        "parser_version": self._attachment_invoice_cache_parser_version(),
                        "cache_schema_version": ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
                        "evidences": evidences,
                        "invoices": invoices,
                        "artifacts": artifacts,
                        "parsed_at": datetime.now().isoformat(),
                    },
                )
                updated = True
        finally:
            with self._attachment_invoice_parse_lock:
                for cache_key, _file_entry in files:
                    self._attachment_invoice_parse_inflight.discard(cache_key)
        if not updated:
            return
        if month and month in self._records_cache:
            self._records_cache.pop(month, None)
            self._records_cache.pop("__all__", None)
        else:
            self._records_cache.clear()
        if self._attachment_invoice_cache_updated_callback is not None and month:
            self._attachment_invoice_cache_updated_callback([month])

    def _project_name_index(self) -> dict[str, str]:
        if self._project_name_cache is not None:
            return self._project_name_cache
        project_names = dict(self._settings.project_name_overrides)
        for document in self._load_project_documents():
            name = self._first_text(self._document_data(document), "name")
            if name:
                project_names[self._document_id(document)] = name
        self._project_name_cache = project_names
        return project_names

    def _load_form_documents(self, form_id: str, month: str | None = None) -> list[dict]:
        if self._mongo_temporarily_unavailable():
            return []
        documents = self._find_documents(self._build_form_query(form_id, month))
        if month is None:
            return documents

        return [document for document in documents if self._matches_month(document, month)]

    def _load_form_month_documents(self, form_id: str) -> list[dict]:
        if self._mongo_temporarily_unavailable():
            return []
        return self._find_documents(
            self._build_form_query(form_id),
            projection=self._month_scan_projection(),
        )

    def _load_form_documents_by_external_ids(
        self,
        form_id: str,
        external_ids: set[str],
    ) -> list[dict]:
        normalized_external_ids = {
            clean_string(external_id)
            for external_id in external_ids
            if clean_string(external_id)
        }
        if not normalized_external_ids or self._mongo_temporarily_unavailable():
            return []
        query = self._build_external_id_query(form_id, normalized_external_ids)
        documents = self._find_documents(query)
        return [
            document
            for document in documents
            if self._document_external_id(form_id, document) in normalized_external_ids
        ]

    def list_etc_oa_detection_candidates(
        self,
        *,
        business_batch_id: str,
        external_etc_batch_id: str,
        created_from: datetime,
        created_to: datetime,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        normalized_business_batch_id = clean_string(business_batch_id)
        normalized_external_batch_id = clean_string(external_etc_batch_id)
        if not normalized_business_batch_id and not normalized_external_batch_id:
            return []

        marker_clauses: list[dict[str, Any]] = []
        for marker in (
            f"business_batch_id={normalized_business_batch_id}" if normalized_business_batch_id else "",
            f"etc_batch_id={normalized_external_batch_id}" if normalized_external_batch_id else "",
        ):
            if marker:
                marker_clauses.append({"data.cause": {"$regex": re.escape(marker), "$options": "i"}})
                marker_clauses.append({"data.remark": {"$regex": re.escape(marker), "$options": "i"}})

        date_from = created_from.date().isoformat()
        date_to = created_to.date().isoformat()
        query: dict[str, Any] = {
            "$and": [
                {"form_id": self._form_id_query_value(self._settings.payment_request_form_id)},
                {"$or": marker_clauses},
                {
                    "$or": [
                        {"data.processStatus": {"$in": [1, "1", "进行中"]}},
                        {"data.process_status": {"$in": [1, "1", "进行中"]}},
                        {"data.流程状态": "进行中"},
                        {"processStatus": {"$in": [1, "1", "进行中"]}},
                    ]
                },
                {
                    "$or": [
                        {"data.applicationDate": {"$gte": date_from, "$lte": date_to}},
                        {"data.ApplicationDate": {"$gte": date_from, "$lte": date_to}},
                        {"modifiedTime": {"$gte": created_from.isoformat(), "$lte": created_to.isoformat()}},
                    ]
                },
            ]
        }
        documents = self._search_form_documents(
            self._settings.payment_request_form_id,
            query,
            projection=self._search_document_projection(),
            limit=limit,
        )
        candidates: list[dict[str, Any]] = []
        for document in documents:
            data = self._document_data(document)
            candidates.append(
                {
                    "oa_row_id": f"oa-pay-{self._payment_external_id(data, document)}",
                    "form_id": self._settings.payment_request_form_id,
                    "amount": self._first_text(data, "amount"),
                    "invoice_count": self._first_text(data, "invoiceCount", "invoice_count", "etcInvoiceCount"),
                    "applicant": self._first_text(data, "userName", "applicant"),
                    "applicant_user_id": self._first_text(data, "userId", "applicantUserId", "applicant_user_id"),
                    "owner_org_id": self._first_text(data, "orgId", "ownerOrgId", "owner_org_id", "departmentId"),
                    "organization": self._first_text(data, "orgName", "organization", "departmentName"),
                    "project_name": self._first_text(data, "projectName"),
                    "created_at": self._first_text(data, "applicationDate", "ApplicationDate") or document.get("modifiedTime"),
                    "process_status": self.canonical_process_status(data),
                    "reason": self._first_text(data, "cause", "remark"),
                    "detail_fields": {
                        "OA单号": self._payment_form_no(data, document),
                        "表单ID": self._settings.payment_request_form_id,
                        "流程状态": self._form_status(data),
                    },
                }
            )
        return candidates

    def _load_project_documents(self) -> list[dict]:
        if self._mongo_temporarily_unavailable():
            return []
        return self._find_documents({"form_id": self._form_id_query_value(self._settings.project_form_id)})

    def _find_documents(
        self,
        query: dict[str, Any],
        *,
        projection: dict[str, int] | None = None,
    ) -> list[dict]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return list(self._collection().find(query, projection))
            except (OSError, PyMongoError, TimeoutError, ValueError) as exc:
                last_error = exc
                self._reset_client()
                if attempt == 0:
                    continue
        if last_error is not None:
            self._mark_mongo_unavailable()
        return []

    def _search_form_documents(
        self,
        form_id: str,
        query: dict[str, Any],
        *,
        projection: dict[str, int] | None = None,
        limit: int,
    ) -> list[dict]:
        last_error: Exception | None = None
        normalized_limit = max(1, int(limit or 1))
        for attempt in range(2):
            try:
                normalized_form_id = clean_string(form_id)
                application_date_field = (
                    "data.applicationDate"
                    if normalized_form_id == clean_string(self._settings.payment_request_form_id)
                    else "data.ApplicationDate"
                )
                cursor = (
                    self._collection()
                    .find(query, projection)
                    .max_time_ms(5000)
                    .sort([(application_date_field, 1), ("_id", 1)])
                    .limit(normalized_limit)
                )
                return list(cursor)
            except (OSError, PyMongoError, TimeoutError, ValueError) as exc:
                last_error = exc
                self._reset_client()
                if attempt == 0:
                    continue
        if last_error is not None:
            self._mark_mongo_unavailable()
        return []

    def _count_search_documents(self, query: dict[str, Any]) -> int:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return int(self._collection().count_documents(query))
            except (OSError, PyMongoError, TimeoutError, ValueError) as exc:
                last_error = exc
                self._reset_client()
                if attempt == 0:
                    continue
        if last_error is not None:
            self._mark_mongo_unavailable()
        return 0

    def _collection(self):
        if self._client is None:
            self._client = MongoClient(
                self._settings.mongo_uri,
                serverSelectionTimeoutMS=self._settings.request_timeout_ms,
                connectTimeoutMS=self._settings.request_timeout_ms,
                socketTimeoutMS=self._settings.request_timeout_ms,
                waitQueueTimeoutMS=self._settings.request_timeout_ms,
            )
        return self._client[self._settings.database][self._settings.collection]

    def _reset_client(self) -> None:
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            client.close()
        except Exception:
            return

    def _mark_mongo_unavailable(self) -> None:
        self._reset_client()
        self._mongo_unavailable_until = self._now() + self._mongo_unavailable_backoff_seconds()
        self._set_read_status("error", "OA 连接失败")

    def _mongo_temporarily_unavailable(self) -> bool:
        return self._now() < self._mongo_unavailable_until

    def _mongo_unavailable_backoff_seconds(self) -> float:
        return float(max(1, min(self._settings.cache_ttl_seconds, 30)))

    def _set_read_status(self, code: str, message: str) -> None:
        self._last_read_status = OAReadStatus(code=code, message=message)

    @staticmethod
    def _month_scan_projection() -> dict[str, int]:
        return {
            "data.applicationDate": 1,
            "data.ApplicationDate": 1,
            "data.status": 1,
            "data.processStatus": 1,
            "modifiedTime": 1,
        }

    def _build_form_query(self, form_id: str, month: str | None = None) -> dict[str, Any]:
        query: dict[str, Any] = {"form_id": self._form_id_query_value(form_id)}
        if month is None:
            return query

        missing_application_date = {
            "$and": [
                {
                    "$or": [
                        {"data.applicationDate": {"$exists": False}},
                        {"data.applicationDate": ""},
                        {"data.applicationDate": None},
                    ]
                },
                {
                    "$or": [
                        {"data.ApplicationDate": {"$exists": False}},
                        {"data.ApplicationDate": ""},
                        {"data.ApplicationDate": None},
                    ]
                },
            ]
        }
        query["$or"] = [
            {"data.applicationDate": {"$regex": f"^{month}"}},
            {"data.ApplicationDate": {"$regex": f"^{month}"}},
            missing_application_date,
        ]
        return query

    def _build_search_form_query(
        self,
        *,
        form_id: str,
        form_type: str,
        q: str | None,
        statuses: list[str],
        date_from: str | None,
        date_to: str | None,
        project_query_values: list[str],
    ) -> dict[str, Any]:
        clauses: list[dict[str, Any]] = [{"form_id": self._form_id_query_value(form_id)}]
        status_clause = self._search_status_clause(statuses)
        if status_clause:
            clauses.append(status_clause)
        date_clause = self._search_application_date_clause(date_from=date_from, date_to=date_to)
        if date_clause:
            clauses.append(date_clause)
        query_clause = self._search_text_clause(
            q,
            form_type=form_type,
            project_query_values=project_query_values,
        )
        if query_clause:
            clauses.append(query_clause)
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    @staticmethod
    def _search_document_projection() -> dict[str, int]:
        return {"data": 1, "form_id": 1, "modifiedTime": 1}

    @staticmethod
    def _search_status_clause(statuses: list[str]) -> dict[str, Any] | None:
        status_or: list[dict[str, Any]] = []
        if OA_IMPORT_STATUS_COMPLETED in set(statuses):
            status_or.append({"data.processStatus": {"$in": list(COMPLETED_PROCESS_VALUES)}})
            status_or.append({"data.status": {"$in": list(COMPLETED_STATUS_VALUES)}})
        if OA_IMPORT_STATUS_IN_PROGRESS in set(statuses):
            status_or.append({"data.processStatus": {"$in": list(IN_PROGRESS_PROCESS_VALUES)}})
        if not status_or:
            return None
        return {"$or": status_or}

    @staticmethod
    def _search_application_date_clause(*, date_from: str | None, date_to: str | None) -> dict[str, Any] | None:
        bounds: dict[str, str] = {}
        normalized_date_from = clean_string(date_from)
        normalized_date_to = clean_string(date_to)
        if normalized_date_from:
            bounds["$gte"] = normalized_date_from
        if normalized_date_to:
            bounds["$lte"] = normalized_date_to
        if not bounds:
            return None
        return {
            "$or": [
                {"data.applicationDate": dict(bounds)},
                {"data.ApplicationDate": dict(bounds)},
            ]
        }

    def _search_text_clause(
        self,
        q: str | None,
        *,
        form_type: str,
        project_query_values: list[str],
    ) -> dict[str, Any] | None:
        query = clean_string(q)
        if not query:
            return None
        regex = {"$regex": re.escape(query), "$options": "i"}
        if form_type == OA_IMPORT_FORM_TYPE_PAYMENT:
            fields = [
                "data.applicationDate",
                "data.ApplicationDate",
                "data.userName",
                "data.applicant",
                "data.cause",
                "data.beneficiary",
                "data.amount",
                "data.projectName",
                "data.flowRequestId",
                "data.processId",
                "data.paymentMethod",
                "data.paymentProof",
                "data.bank",
                "data.payeeAccount",
                "data.fromTitle",
            ]
        else:
            fields = [
                "data.applicationDate",
                "data.ApplicationDate",
                "data.Reimbursement Personnel",
                "data.applicant",
                "data.userName",
                "data.titleName",
                "data.notes",
                "data.amount",
                "data.Amount",
                "data.totalAmount",
                "data.TotalAmount",
                "data.projectName",
                "data.flowRequestId",
                "data.processId",
                "data.schedule.detailProjectName",
                "data.schedule.detailReimbursementAmount",
                "data.schedule.amount",
                "data.schedule.feeContent",
                "data.schedule.detailCostStatement",
                "data.schedule.detailReimbursementDate",
                "data.schedule.detailReimbursementAttachment.files.fileName",
                "data.schedule.detailReimbursementAttachment.list.name",
            ]
        text_or = [{field: regex} for field in fields]
        if project_query_values:
            text_or.append({"data.projectName": {"$in": project_query_values}})
            text_or.append({"data.schedule.detailProjectName": {"$in": project_query_values}})
        return {"$or": text_or}

    @staticmethod
    def _project_query_values(q: str | None, project_names: dict[str, str]) -> list[str]:
        query = clean_string(q).lower()
        if not query:
            return []
        values: list[str] = []
        for project_id, project_name in project_names.items():
            if query in clean_string(project_id).lower() or query in clean_string(project_name).lower():
                values.append(project_id)
        return values

    def _build_external_id_query(self, form_id: str, external_ids: set[str]) -> dict[str, Any]:
        query: dict[str, Any] = {
            "form_id": self._form_id_query_value(form_id),
            "$or": [],
        }
        scalar_candidates = self._external_id_query_values(external_ids)
        if scalar_candidates:
            query["$or"].append({"data.flowRequestId": {"$in": scalar_candidates}})
            query["$or"].append({"data.processId": {"$in": scalar_candidates}})
        object_id_candidates = self._object_id_query_values(external_ids)
        if object_id_candidates:
            query["$or"].append({"_id": {"$in": object_id_candidates}})
        if not query["$or"]:
            query["$or"].append({"_id": {"$in": list(external_ids)}})
        return query

    def _document_external_id(self, form_id: str, document: dict[str, Any]) -> str:
        data = self._document_data(document)
        normalized_form_id = clean_string(form_id)
        if normalized_form_id == clean_string(self._settings.payment_request_form_id):
            return self._payment_external_id(data, document)
        if normalized_form_id == clean_string(self._settings.expense_claim_form_id):
            return self._expense_external_id(data, document)
        return self._document_id(document)

    @staticmethod
    def _form_id_query_value(form_id: object) -> object:
        normalized_form_id = clean_string(form_id)
        if normalized_form_id.isdigit():
            return {"$in": [normalized_form_id, int(normalized_form_id)]}
        return normalized_form_id

    @staticmethod
    def _external_id_query_values(external_ids: set[str]) -> list[object]:
        values: list[object] = []
        seen: set[tuple[type, str]] = set()
        for external_id in external_ids:
            normalized = clean_string(external_id)
            if not normalized:
                continue
            key = (str, normalized)
            if key not in seen:
                seen.add(key)
                values.append(normalized)
            if normalized.isdigit():
                int_key = (int, normalized)
                if int_key not in seen:
                    seen.add(int_key)
                    values.append(int(normalized))
        return values

    @staticmethod
    def _object_id_query_values(external_ids: set[str]) -> list[ObjectId]:
        values: list[ObjectId] = []
        seen: set[str] = set()
        for external_id in external_ids:
            normalized = clean_string(external_id)
            if normalized in seen or not ObjectId.is_valid(normalized):
                continue
            seen.add(normalized)
            values.append(ObjectId(normalized))
        return values

    @staticmethod
    def _parse_oa_row_id(row_id: str) -> tuple[str, str, str | None] | None:
        normalized_row_id = clean_string(row_id)
        payment_match = PAYMENT_ROW_ID_RE.match(normalized_row_id)
        if payment_match is not None:
            return ("payment", payment_match.group(1), None)
        expense_match = EXPENSE_ROW_ID_RE.match(normalized_row_id)
        if expense_match is not None:
            return ("expense", expense_match.group(1), None)
        return None

    @staticmethod
    def _expense_external_id_candidates_from_row_id(row_id: str) -> list[str]:
        normalized_row_id = clean_string(row_id)
        if not normalized_row_id.startswith("oa-exp-"):
            return []
        body = normalized_row_id.removeprefix("oa-exp-")
        candidates = [body] if body else []
        if "-" in body:
            prefix, suffix = body.rsplit("-", 1)
            if prefix and suffix.isdigit() and prefix not in candidates:
                candidates.append(prefix)
        return candidates

    def _matches_month(self, document: dict[str, Any], month: str) -> bool:
        data = self._document_data(document)
        application_month = self._first_text(data, "applicationDate", "ApplicationDate")[:7]
        if application_month:
            return application_month == month
        modified_time = document.get("modifiedTime")
        if isinstance(modified_time, datetime):
            return modified_time.strftime("%Y-%m") == month
        return False

    @staticmethod
    def _now() -> float:
        return monotonic()

    @staticmethod
    def _document_data(document: dict[str, Any]) -> dict[str, Any]:
        data = document.get("data", {})
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _document_id(document: dict[str, Any]) -> str:
        return clean_string(document.get("_id", ""))

    @staticmethod
    def _datetime_string(value: Any) -> str | None:
        if isinstance(value, datetime):
            return value.isoformat()
        if value in (None, ""):
            return None
        return clean_string(value)

    @staticmethod
    def _first_text(payload: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return clean_string(value)
        return ""

    def _resolve_expense_type(self, *sources: Any) -> str:
        payloads = [source for source in sources if isinstance(source, dict)]
        texts = [clean_string(source) for source in sources if isinstance(source, str) and clean_string(source)]

        for payload in payloads:
            direct = self._canonical_expense_type(self._first_text(payload, *EXPENSE_TYPE_CANDIDATE_KEYS))
            if direct:
                return direct

        fuzzy_candidates = {self._normalize_key(key) for key in EXPENSE_TYPE_CANDIDATE_KEYS}
        for payload in payloads:
            matched = self._canonical_expense_type(self._find_text_by_normalized_keys(payload, fuzzy_candidates))
            if matched:
                return matched

        return self._infer_expense_type(*texts)

    def _canonical_expense_type(self, value: Any) -> str:
        text = clean_string(value)
        if not text:
            return ""
        return STANDARD_EXPENSE_TYPE_BY_NORMALIZED_KEY.get(self._normalize_key(text), "")

    def _find_text_by_normalized_keys(self, value: Any, normalized_keys: set[str]) -> str:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                if self._normalize_key(key) in normalized_keys:
                    text = clean_string(nested_value)
                    if text:
                        return text
                nested_match = self._find_text_by_normalized_keys(nested_value, normalized_keys)
                if nested_match:
                    return nested_match
        elif isinstance(value, list):
            for item in value:
                nested_match = self._find_text_by_normalized_keys(item, normalized_keys)
                if nested_match:
                    return nested_match
        return ""

    def _infer_expense_type(self, *texts: str) -> str:
        combined = " ".join(texts).strip().lower()
        if not combined:
            return ""
        for expense_type, keywords in EXPENSE_TYPE_INFERENCE_RULES:
            if any(keyword.lower() in combined for keyword in keywords):
                return expense_type
        return "其他"

    @staticmethod
    def _normalize_key(value: Any) -> str:
        return KEY_NORMALIZE_RE.sub("", clean_string(value)).lower()

    @staticmethod
    def _append_unique(items: list[str], value: Any) -> None:
        normalized = clean_string(value)
        if normalized and normalized not in items:
            items.append(normalized)

    @staticmethod
    def _parse_amount(value: Any) -> Decimal | None:
        text = clean_string(value)
        if not text:
            return None
        normalized = (
            text.replace(",", "")
            .replace("，", "")
            .replace("￥", "")
            .replace("¥", "")
            .strip()
        )
        if not normalized:
            return None
        try:
            return Decimal(normalized)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _format_decimal(value: Decimal | None, *, decimal_places: int | None = None) -> str:
        if value is None:
            return ""
        if decimal_places is not None:
            quantizer = Decimal("1").scaleb(-max(decimal_places, 0))
            return f"{value.quantize(quantizer):f}"
        normalized = value.normalize()
        if normalized == normalized.to_integral():
            return f"{normalized.quantize(Decimal('1')):f}"
        return f"{normalized:f}"

    @staticmethod
    def _decimal_places(value: Any) -> int:
        text = clean_string(value)
        if "." not in text:
            return 0
        return len(text.rsplit(".", 1)[1])

    @staticmethod
    def _date_range_text(values: list[str]) -> str:
        dates = sorted({clean_string(value)[:10] for value in values if clean_string(value)})
        if not dates:
            return ""
        if len(dates) == 1:
            return dates[0]
        return f"{dates[0]} 至 {dates[-1]}"

    @staticmethod
    def _dedupe_attachment_invoices(invoices: list[dict[str, str]]) -> list[dict[str, str]]:
        deduped: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for invoice in invoices:
            if not isinstance(invoice, dict):
                continue
            keys = MongoOAAdapter._attachment_invoice_dedupe_keys(invoice)
            if any(key in seen for key in keys):
                continue
            seen.update(keys)
            deduped.append(dict(invoice))
        return deduped

    @staticmethod
    def _dedupe_attachment_evidences(evidences: list[dict[str, str]]) -> list[dict[str, str]]:
        deduped: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for evidence in evidences:
            if not isinstance(evidence, dict):
                continue
            if MongoOAAdapter._is_attachment_invoice_evidence(evidence):
                keys = MongoOAAdapter._attachment_invoice_dedupe_keys(evidence)
                if any(key in seen for key in keys):
                    continue
                seen.update(keys)
            else:
                key = MongoOAAdapter._attachment_evidence_dedupe_key(evidence)
                if key in seen:
                    continue
                seen.add(key)
            deduped.append(dict(evidence))
        return deduped

    @staticmethod
    def _dedupe_attachment_artifacts(artifacts: list[dict[str, str]]) -> list[dict[str, str]]:
        deduped: list[dict[str, str]] = []
        seen: set[str] = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            key = clean_string(artifact.get("source_attachment_key") or "")
            if not key:
                key = json.dumps(artifact, ensure_ascii=False, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(dict(artifact))
        return deduped

    @staticmethod
    def _attachment_evidence_dedupe_key(evidence: dict[str, object]) -> tuple[str, str]:
        evidence_type = clean_string(evidence.get("evidence_type") or "")
        if evidence_type in ATTACHMENT_INVOICE_EVIDENCE_TYPES or (
            not evidence_type and MongoOAAdapter._is_attachment_invoice_evidence(evidence)
        ):
            return MongoOAAdapter._attachment_invoice_dedupe_key(evidence)
        if evidence_type == "payment_receipt":
            transaction_no = clean_string(evidence.get("transaction_no") or "")
            if transaction_no:
                return ("payment_receipt:transaction_no", transaction_no)
            merchant_order_no = clean_string(evidence.get("merchant_order_no") or "")
            if merchant_order_no:
                return ("payment_receipt:merchant_order_no", merchant_order_no)
            return (
                "payment_receipt:fallback",
                json.dumps(
                    {
                        "document_kind": clean_string(evidence.get("document_kind") or ""),
                        "amount": clean_string(evidence.get("amount") or ""),
                        "merchant_name": clean_string(evidence.get("merchant_name") or ""),
                        "paid_at": clean_string(evidence.get("paid_at") or ""),
                        "payment_method": clean_string(evidence.get("payment_method") or ""),
                        "source_attachment_key": clean_string(evidence.get("source_attachment_key") or ""),
                        "source_region_key": clean_string(evidence.get("source_region_key") or ""),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        evidence_id = clean_string(evidence.get("evidence_id") or "")
        if evidence_id:
            return (f"{evidence_type or 'unknown'}:evidence_id", evidence_id)
        return (
            f"{evidence_type or 'unknown'}:fallback",
            json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str),
        )

    @staticmethod
    def _attachment_invoice_dedupe_key(invoice: dict[str, object]) -> tuple[str, str]:
        return MongoOAAdapter._attachment_invoice_dedupe_keys(invoice)[0]

    @staticmethod
    def _attachment_invoice_dedupe_keys(invoice: dict[str, object]) -> list[tuple[str, str]]:
        keys: list[tuple[str, str]] = []
        digital_invoice_no = clean_string(invoice.get("digital_invoice_no") or "")
        if digital_invoice_no:
            keys.append(("invoice:digital_invoice_no", digital_invoice_no))
        invoice_code = clean_string(invoice.get("invoice_code") or "")
        invoice_no = clean_string(invoice.get("invoice_no") or "")
        if invoice_code and invoice_no:
            keys.append(("invoice:code_no", f"{invoice_code}:{invoice_no}"))
        fallback = {
            "document_kind": clean_string(invoice.get("document_kind") or ""),
            "invoice_no": invoice_no,
            "invoice_code": invoice_code,
            "amount": clean_string(invoice.get("total_with_tax") or invoice.get("amount") or ""),
            "seller_name": clean_string(invoice.get("seller_name") or ""),
            "issue_date": clean_string(invoice.get("issue_date") or ""),
        }
        if not invoice_no and not invoice_code:
            fallback["source_attachment_name"] = clean_string(invoice.get("source_attachment_name") or invoice.get("attachment_name") or "")
            fallback["source_region_key"] = clean_string(invoice.get("source_region_key") or "")
        keys.append((
            "invoice:fallback",
            json.dumps(fallback, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        ))
        return keys

    def _sync_import_settings_cache(self) -> None:
        settings = self._current_import_settings()
        signature = json.dumps(settings, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if self._import_settings_signature == signature:
            return
        self._import_settings_signature = signature
        self._records_cache.clear()
        self._available_months_cache = None

    def _current_import_settings(self) -> dict[str, list[str]]:
        provider = self._import_settings_provider
        if provider is None:
            return {
                "form_types": list(DEFAULT_OA_IMPORT_SETTINGS["form_types"]),
                "statuses": list(DEFAULT_OA_IMPORT_SETTINGS["statuses"]),
            }
        try:
            payload = provider()
        except Exception:
            payload = {}
        return self._normalize_import_settings(payload)

    @contextmanager
    def _temporary_import_settings(self, settings: dict[str, list[str]]):
        previous_provider = self._import_settings_provider
        previous_signature = self._import_settings_signature
        normalized_settings = self._normalize_import_settings(settings)
        self._import_settings_provider = lambda: normalized_settings
        try:
            yield
        finally:
            self._import_settings_provider = previous_provider
            self._import_settings_signature = previous_signature

    @staticmethod
    def _normalize_import_settings(payload: object) -> dict[str, list[str]]:
        raw_payload = payload if isinstance(payload, dict) else {}
        form_type_ids = [item["id"] for item in OA_IMPORT_FORM_TYPE_OPTIONS]
        status_ids = [item["id"] for item in OA_IMPORT_STATUS_OPTIONS]
        return {
            "form_types": MongoOAAdapter._normalize_import_option_list(
                raw_payload.get("form_types"),
                allowed_values=form_type_ids,
                default_values=DEFAULT_OA_IMPORT_SETTINGS["form_types"],
            ),
            "statuses": MongoOAAdapter._normalize_import_option_list(
                raw_payload.get("statuses"),
                allowed_values=status_ids,
                default_values=DEFAULT_OA_IMPORT_SETTINGS["statuses"],
            ),
        }

    @staticmethod
    def _normalize_import_option_list(
        values: object,
        *,
        allowed_values: list[str],
        default_values: list[str],
    ) -> list[str]:
        if not isinstance(values, list):
            return list(default_values)
        seen: set[str] = set()
        for value in values:
            normalized = clean_string(value)
            if normalized in allowed_values:
                seen.add(normalized)
        return [value for value in allowed_values if value in seen]

    @classmethod
    def _normalize_search_import_settings(
        cls,
        *,
        form_types: list[str] | None,
        statuses: list[str] | None,
    ) -> dict[str, list[str]]:
        form_type_ids = [item["id"] for item in OA_IMPORT_FORM_TYPE_OPTIONS]
        status_ids = [item["id"] for item in OA_IMPORT_STATUS_OPTIONS]
        return {
            "form_types": cls._normalize_import_option_list(
                form_types,
                allowed_values=form_type_ids,
                default_values=form_type_ids,
            ),
            "statuses": cls._normalize_import_option_list(
                statuses,
                allowed_values=status_ids,
                default_values=status_ids,
            ),
        }

    @classmethod
    def _record_matches_date_range(
        cls,
        record: OAApplicationRecord,
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> bool:
        application_date = clean_string(record.detail_fields.get("申请日期") or "")
        if date_from and application_date and application_date < clean_string(date_from):
            return False
        if date_to and application_date and application_date > clean_string(date_to):
            return False
        return True

    @classmethod
    def _record_matches_query(cls, record: OAApplicationRecord, q: str | None) -> bool:
        query = clean_string(q).lower()
        if not query:
            return True
        haystack = "\n".join(cls._iter_record_search_text(record)).lower()
        return query in haystack

    @classmethod
    def _iter_record_search_text(cls, record: OAApplicationRecord) -> list[str]:
        values: list[str] = [
            record.id,
            record.month,
            record.applicant,
            record.project_name,
            record.apply_type,
            record.amount,
            record.counterparty_name,
            record.reason,
            record.expense_type or "",
            record.expense_content or "",
        ]

        def visit(value: Any) -> None:
            if value in (None, ""):
                return
            if isinstance(value, dict):
                for child in value.values():
                    visit(child)
                return
            if isinstance(value, (list, tuple, set)):
                for child in value:
                    visit(child)
                return
            text = clean_string(value)
            if text:
                values.append(text)

        visit(record.detail_fields)
        visit(record.attachment_invoices)
        visit(record.attachment_artifacts)
        visit(record.expense_items)
        return values

    def _should_include_form_type(self, form_type: str) -> bool:
        return clean_string(form_type) in set(self._current_import_settings()["form_types"])

    def _should_include_document(self, form_type: str, data: dict[str, Any]) -> bool:
        settings = self._current_import_settings()
        return (
            clean_string(form_type) in set(settings["form_types"])
            and self._canonical_status_key(data) in set(settings["statuses"])
        )

    @staticmethod
    def _canonical_status_key(data: dict[str, Any]) -> str:
        return MongoOAAdapter.canonical_process_status(data)

    @staticmethod
    def canonical_process_status(data: dict[str, Any] | Any) -> str:
        payload = data if isinstance(data, dict) else {"processStatus": data}
        direct_status = clean_string(
            payload.get("process_status") if isinstance(payload, dict) else ""
        )
        if direct_status in {OA_IMPORT_STATUS_COMPLETED, OA_IMPORT_STATUS_IN_PROGRESS}:
            return direct_status
        status = MongoOAAdapter._form_status(payload)
        if status == "已完成":
            return OA_IMPORT_STATUS_COMPLETED
        if status == "进行中":
            return OA_IMPORT_STATUS_IN_PROGRESS
        return ""

    @staticmethod
    def _canonical_apply_type(form_type: str) -> str:
        if form_type == OA_IMPORT_FORM_TYPE_EXPENSE:
            return "日常报销"
        return "支付申请"

    @staticmethod
    def _ordered_options(
        options: list[dict[str, str]],
        enabled_ids: set[str],
    ) -> list[dict[str, str]]:
        return [
            {"id": item["id"], "label": item["label"]}
            for item in options
            if item["id"] in enabled_ids
        ]

    @staticmethod
    def _form_status(data: dict[str, Any]) -> str:
        process_status = data.get("processStatus")
        normalized_process_status = clean_string(process_status) if process_status not in (None, "") else ""
        if normalized_process_status in COMPLETED_PROCESS_VALUES:
            return "已完成"
        if normalized_process_status in IN_PROGRESS_PROCESS_VALUES:
            return "进行中"

        status = MongoOAAdapter._first_text(data, "status")
        if status in COMPLETED_STATUS_VALUES:
            return "已完成"
        if status:
            return status
        return normalized_process_status

    @staticmethod
    def _is_completed_form(data: dict[str, Any]) -> bool:
        return MongoOAAdapter._form_status(data) == "已完成"

    def _derive_month(self, data: dict[str, Any], document: dict[str, Any]) -> str:
        candidate = self._first_text(data, "applicationDate", "ApplicationDate")
        if len(candidate) >= 7:
            return candidate[:7]
        modified_time = document.get("modifiedTime")
        if isinstance(modified_time, datetime):
            return modified_time.strftime("%Y-%m")
        return datetime.now().strftime("%Y-%m")

    def _payment_external_id(self, data: dict[str, Any], document: dict[str, Any]) -> str:
        return self._first_text(data, "flowRequestId", "processId") or self._document_id(document)

    def _payment_form_no(self, data: dict[str, Any], document: dict[str, Any]) -> str:
        return self._payment_external_id(data, document)

    def _expense_external_id(self, data: dict[str, Any], document: dict[str, Any]) -> str:
        return self._first_text(data, "flowRequestId", "processId") or self._document_id(document)

    def _expense_form_no(self, data: dict[str, Any], document: dict[str, Any]) -> str:
        return self._expense_external_id(data, document)

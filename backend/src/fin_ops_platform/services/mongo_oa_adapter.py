from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
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
from fin_ops_platform.services.oa_adapter import OAAdapter, OAApplicationRecord, OAReadStatus, build_attachment_invoice_detail_fields
from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentInvoiceService


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
KEY_NORMALIZE_RE = re.compile(r"[\s_\-:/\\()（）【】\[\]·,.，。]+")
PAYMENT_ROW_ID_RE = re.compile(r"^oa-pay-(.+)$")
EXPENSE_ROW_ID_RE = re.compile(r"^oa-exp-(.+)-([^-]+)$")
COMPLETED_PROCESS_VALUES = {"已完成", "2", 2}
IN_PROGRESS_PROCESS_VALUES = {"进行中", "1", 1}
COMPLETED_STATUS_VALUES = {"approved", "APPROVED", "Approved"}

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
        self._client: MongoClient | None = None
        self._project_name_cache: dict[str, str] | None = None
        self._records_cache: dict[str, tuple[float, list[OAApplicationRecord]]] = {}
        self._available_months_cache: tuple[float, list[str]] | None = None
        self._mongo_unavailable_until = 0.0
        self._last_read_status = OAReadStatus(code="idle", message="OA 待读取")
        self._attachment_invoice_service = OAAttachmentInvoiceService(
            timeout_seconds=max(self._settings.request_timeout_ms / 1000, 1),
        )

    def set_attachment_invoice_cache_updated_callback(self, callback: Callable[[list[str]], None] | None) -> None:
        self._attachment_invoice_cache_updated_callback = callback

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

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        if not MONTH_RE.match(month):
            return []
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
        payment_documents = self._load_form_documents(self._settings.payment_request_form_id, month)
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []
        for document in payment_documents:
            record = self._build_payment_request_record(document, project_names)
            if record is not None:
                records.append(record)
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
        payment_documents = self._load_form_documents(self._settings.payment_request_form_id)
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []
        for document in payment_documents:
            record = self._build_payment_request_record(document, project_names)
            if record is not None:
                records.append(record)

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
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []

        project_names = self._project_name_index()
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []

        payment_external_ids: set[str] = set()
        expense_external_ids: set[str] = set()
        for row_id in normalized_row_ids:
            parsed = self._parse_oa_row_id(row_id)
            if parsed is None:
                continue
            record_kind, external_id, _row_index = parsed
            if record_kind == "payment":
                payment_external_ids.add(external_id)
            else:
                expense_external_ids.add(external_id)

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
            for document in expense_documents:
                for record in self._build_expense_claim_records(document, project_names):
                    records_by_id[record.id] = record

        self._set_read_status("ready", "OA 已同步")
        return [records_by_id[row_id] for row_id in normalized_row_ids if row_id in records_by_id]

    def list_available_months(self) -> list[str]:
        now = self._now()
        if self._mongo_temporarily_unavailable():
            self._set_read_status("error", "OA 连接失败")
            return []
        if self._available_months_cache is not None and self._settings.cache_ttl_seconds > 0:
            cached_at, months = self._available_months_cache
            if now - cached_at < self._settings.cache_ttl_seconds:
                self._set_read_status("ready", "OA 已同步")
                return list(months)

        months: set[str] = set()
        for form_id in (self._settings.payment_request_form_id, self._settings.expense_claim_form_id):
            documents = self._load_form_month_documents(form_id)
            if self._mongo_temporarily_unavailable():
                self._set_read_status("error", "OA 连接失败")
                return sorted(months)
            for document in documents:
                data = self._document_data(document)
                if not self._is_completed_form(data):
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

    def fetch_counterparties(self) -> list[dict[str, Any]]:
        names: dict[str, dict[str, Any]] = {}
        for document in self._load_form_documents(self._settings.payment_request_form_id):
            data = self._document_data(document)
            if not self._is_completed_form(data):
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
            documents = []
            for document in self._load_form_documents(self._settings.payment_request_form_id):
                data = self._document_data(document)
                if not self._is_completed_form(data):
                    continue
                documents.append(
                    {
                        "external_id": self._payment_external_id(data, document),
                        "form_no": self._payment_form_no(data, document),
                        "title": self._first_text(data, "fromTitle", "formTitle") or "支付申请",
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
            documents = []
            for document in self._load_form_documents(self._settings.expense_claim_form_id):
                data = self._document_data(document)
                if not self._is_completed_form(data):
                    continue
                documents.append(
                    {
                        "external_id": self._expense_external_id(data, document),
                        "form_no": self._expense_form_no(data, document),
                        "title": self._first_text(data, "titleName", "formTitle") or "日常报销",
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
        if not self._is_completed_form(data):
            return None
        amount = self._first_text(data, "amount")
        applicant = self._first_text(data, "userName", "applicant")
        reason = self._first_text(data, "cause")
        counterparty = self._first_text(data, "beneficiary")
        if not amount or not applicant or not reason:
            return None
        project_id = self._first_text(data, "projectName")
        project_name = project_names.get(project_id, project_id or "--")
        external_id = self._payment_external_id(data, document)
        expense_type = self._resolve_expense_type(data, reason)
        expense_content = reason
        return OAApplicationRecord(
            id=f"oa-pay-{external_id}",
            month=self._derive_month(data, document),
            section="open",
            case_id=None,
            applicant=applicant,
            project_name=project_name,
            apply_type=self._first_text(data, "fromTitle", "formTitle") or "支付申请",
            amount=amount,
            counterparty_name=counterparty,
            reason=reason,
            relation_code="pending_match",
            relation_label="待找流水与发票",
            relation_tone="warn",
            expense_type=expense_type,
            expense_content=expense_content,
            detail_fields={
                "OA单号": self._payment_form_no(data, document),
                "表单ID": self._settings.payment_request_form_id,
                "申请日期": self._first_text(data, "applicationDate", "ApplicationDate"),
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
        if not self._is_completed_form(data):
            return []
        applicant = self._first_text(data, "Reimbursement Personnel", "applicant", "userName")
        if not applicant:
            return []
        items = data.get("schedule")
        if not isinstance(items, list) or not items:
            items = [data]
        external_id = self._expense_external_id(data, document)
        records: list[OAApplicationRecord] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            amount = self._first_text(item, "detailReimbursementAmount", "amount")
            reason = self._first_text(item, "feeContent", "detailCostStatement") or self._first_text(data, "notes")
            expense_type = self._resolve_expense_type(item, data, reason)
            expense_content = reason
            if not amount or not reason:
                continue
            project_id = self._first_text(item, "detailProjectName") or self._first_text(data, "projectName")
            project_name = project_names.get(project_id, project_id or "--")
            row_index = clean_string(item.get("row_index", index))
            attachment_files = self._attachment_files(item)
            record_month = self._derive_month(data, document)
            attachment_invoices = self._parse_attachment_invoices(attachment_files, month=record_month)
            detail_fields = {
                "OA单号": self._expense_form_no(data, document),
                "表单ID": self._settings.expense_claim_form_id,
                "明细行号": row_index,
                "申请日期": self._first_text(data, "ApplicationDate", "applicationDate"),
                "报销日期": self._first_text(item, "detailReimbursementDate", "reimbursementDate"),
                "付款方式": self._first_text(item, "detailPaymentMethod", "paymentMethod"),
                "票据类型": self._first_text(item, "detailTypeOfInvoice", "paymentProof"),
                "费用类型": expense_type or "—",
                "费用内容": expense_content or "—",
                "流程状态": self._form_status(data),
            }
            detail_fields.update(
                build_attachment_invoice_detail_fields(
                    attachment_invoices,
                    attachment_file_count=len(attachment_files),
                )
            )
            records.append(
                OAApplicationRecord(
                    id=f"oa-exp-{external_id}-{row_index}",
                    month=record_month,
                    section="open",
                    case_id=None,
                    applicant=applicant,
                    project_name=project_name,
                    apply_type=self._first_text(data, "titleName", "formTitle") or "日常报销",
                    amount=amount,
                    counterparty_name="",
                    reason=reason,
                    relation_code="pending_match",
                    relation_label="待找流水与发票",
                    relation_tone="warn",
                    expense_type=expense_type,
                    expense_content=expense_content,
                    detail_fields=detail_fields,
                    attachment_invoices=attachment_invoices,
                    attachment_file_count=len(attachment_files),
                )
            )
        return records

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

    def _parse_attachment_invoices(self, files: list[dict[str, object]], *, month: str | None = None) -> list[dict[str, str]]:
        if not files:
            return []
        cache = self._attachment_invoice_cache
        if cache is None:
            return []

        cached_invoices: list[dict[str, str]] = []
        missing_files: list[tuple[str, dict[str, object]]] = []
        for file_entry in files:
            cache_key = self._attachment_invoice_cache_key(file_entry)
            cached_entry = cache.load_oa_attachment_invoice_cache_entry(cache_key)
            if self._is_current_attachment_invoice_cache_entry(cached_entry):
                normalized_entry, changed = self._normalize_attachment_invoice_cache_entry(cached_entry)
                if changed:
                    cache.save_oa_attachment_invoice_cache_entry(cache_key, normalized_entry)
                    cached_entry = normalized_entry
                cached_invoices.extend(
                    dict(invoice)
                    for invoice in cached_entry["invoices"]
                    if isinstance(invoice, dict)
                )
                continue
            missing_files.append((cache_key, file_entry))
        if missing_files and self._attachment_invoice_parse_suppression_depth <= 0:
            self._schedule_attachment_invoice_parse(missing_files, month=month)
        return cached_invoices

    @staticmethod
    def _attachment_invoice_cache_parser_version() -> str:
        return OAAttachmentInvoiceService.PARSER_VERSION

    def _is_current_attachment_invoice_cache_entry(self, entry: object) -> bool:
        return (
            isinstance(entry, dict)
            and entry.get("parser_version") == self._attachment_invoice_cache_parser_version()
            and isinstance(entry.get("invoices"), list)
        )

    @staticmethod
    def _normalize_attachment_invoice_cache_entry(entry: dict[str, object]) -> tuple[dict[str, object], bool]:
        normalized_entry = dict(entry if isinstance(entry, dict) else {})
        invoices = normalized_entry.get("invoices")
        if not isinstance(invoices, list):
            return normalized_entry, False

        normalized_invoices: list[dict[str, object]] = []
        changed = False
        for invoice in invoices:
            if not isinstance(invoice, dict):
                continue
            normalized_invoice = dict(invoice)
            net_amount = clean_string(normalized_invoice.get("net_amount") or "")
            amount = clean_string(normalized_invoice.get("amount") or "")
            total_with_tax = clean_string(normalized_invoice.get("total_with_tax") or "")
            if net_amount and amount != net_amount and (not amount or amount == total_with_tax):
                normalized_invoice["amount"] = net_amount
                changed = True
            normalized_invoices.append(normalized_invoice)
        normalized_entry["invoices"] = normalized_invoices
        return normalized_entry, changed

    @staticmethod
    def _attachment_invoice_cache_key(file_entry: dict[str, object]) -> str:
        fingerprint = {
            "file_name": clean_string(file_entry.get("fileName") or file_entry.get("name") or ""),
            "file_path": clean_string(file_entry.get("filePath") or file_entry.get("url") or ""),
            "suffix": clean_string(file_entry.get("suffix") or ""),
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
                invoices = self._attachment_invoice_service.parse_files([file_entry])
                cache.save_oa_attachment_invoice_cache_entry(
                    cache_key,
                    {
                        "cache_key": cache_key,
                        "parser_version": self._attachment_invoice_cache_parser_version(),
                        "invoices": [dict(invoice) for invoice in invoices],
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
            return ("expense", expense_match.group(1), expense_match.group(2))
        return None

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

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import re
from time import monotonic
from typing import Any
from urllib.parse import quote_plus

from pymongo import MongoClient

from fin_ops_platform.services.imports import clean_string
from fin_ops_platform.services.oa_adapter import OAAdapter, OAApplicationRecord


APPROVED_STATUS_VALUES = {"approved", "APPROVED", "Approved"}
APPROVED_PROCESS_VALUES = {"1", "2", 1, 2}
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
KEY_NORMALIZE_RE = re.compile(r"[\s_\-:/\\()（）【】\[\]·,.，。]+")

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

    def __init__(self, *, settings: MongoOASettings) -> None:
        self._settings = settings
        self._client: MongoClient | None = None
        self._project_name_cache: dict[str, str] | None = None
        self._records_cache: dict[str, tuple[float, list[OAApplicationRecord]]] = {}
        self._available_months_cache: tuple[float, list[str]] | None = None

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        if not MONTH_RE.match(month):
            return []

        cached_records = self._records_cache.get(month)
        now = self._now()
        if cached_records is not None and self._settings.cache_ttl_seconds > 0:
            cached_at, records = cached_records
            if now - cached_at < self._settings.cache_ttl_seconds:
                return deepcopy(records)

        project_names = self._project_name_index()
        records: list[OAApplicationRecord] = []
        for document in self._load_form_documents(self._settings.payment_request_form_id, month):
            record = self._build_payment_request_record(document, project_names)
            if record is not None:
                records.append(record)
        for document in self._load_form_documents(self._settings.expense_claim_form_id, month):
            records.extend(self._build_expense_claim_records(document, project_names))
        sorted_records = sorted(records, key=lambda item: (item.month, item.id))
        if self._settings.cache_ttl_seconds > 0:
            self._records_cache[month] = (now, deepcopy(sorted_records))
        return sorted_records

    def list_available_months(self) -> list[str]:
        now = self._now()
        if self._available_months_cache is not None and self._settings.cache_ttl_seconds > 0:
            cached_at, months = self._available_months_cache
            if now - cached_at < self._settings.cache_ttl_seconds:
                return list(months)

        months: set[str] = set()
        for form_id in (self._settings.payment_request_form_id, self._settings.expense_claim_form_id):
            for document in self._load_form_documents(form_id):
                data = self._document_data(document)
                derived_month = self._derive_month(data, document)
                if MONTH_RE.match(derived_month):
                    months.add(derived_month)
        ordered_months = sorted(months)
        if self._settings.cache_ttl_seconds > 0:
            self._available_months_cache = (now, list(ordered_months))
        return ordered_months

    def fetch_counterparties(self) -> list[dict[str, Any]]:
        names: dict[str, dict[str, Any]] = {}
        for document in self._load_form_documents(self._settings.payment_request_form_id):
            data = self._document_data(document)
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
            records.append(
                OAApplicationRecord(
                    id=f"oa-exp-{external_id}-{row_index}",
                    month=self._derive_month(data, document),
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
                    detail_fields={
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
                    },
                )
            )
        return records

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
        documents = list(self._collection().find(self._build_form_query(form_id, month)))
        if month is None:
            return documents

        return [document for document in documents if self._matches_month(document, month)]

    def _load_project_documents(self) -> list[dict]:
        return list(self._collection().find({"form_id": str(self._settings.project_form_id)}))

    def _collection(self):
        if self._client is None:
            self._client = MongoClient(
                self._settings.mongo_uri,
                serverSelectionTimeoutMS=self._settings.request_timeout_ms,
            )
        return self._client[self._settings.database][self._settings.collection]

    def _build_form_query(self, form_id: str, month: str | None = None) -> dict[str, Any]:
        query: dict[str, Any] = {"form_id": str(form_id)}
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
        status = MongoOAAdapter._first_text(data, "status")
        if status:
            return status
        process_status = data.get("processStatus")
        return clean_string(process_status) if process_status not in (None, "") else ""

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

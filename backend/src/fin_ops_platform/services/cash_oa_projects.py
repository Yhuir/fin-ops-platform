"""Cash's narrow, read-only OA project port; never reads OA financial forms."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from fin_ops_platform.services.cash_domain import CashError, invalid
from fin_ops_platform.services.mongo_oa_adapter import MongoOASettings


# Verified in OA dictionary XMJD (type ID 24), not inferred from a label.
ENDED_STAGE_CODE = "end"
PROJECT_PROJECTION = {"_id": 1, "data.name": 1, "data.code": 1, "data.projectPhase": 1}


def load_project_stages(base_url: str, token: str, timeout_seconds: float = 5) -> list[dict]:
    """Read the complete XMJD dictionary with an explicit authenticated OA token."""
    if not base_url or not token or timeout_seconds <= 0:
        raise CashError("cash_dependency_unavailable", "OA 项目字典读取未配置。", 503)
    request = Request(
        base_url.rstrip("/") + "/system/dict/data/type/XMJD",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
        raise CashError("cash_dependency_unavailable", "OA 项目阶段字典读取失败。", 503) from None
    if not isinstance(payload, dict) or payload.get("code") != 200 or not isinstance(payload.get("data"), list):
        raise CashError("cash_dependency_unavailable", "OA 项目阶段字典不可用。", 503)
    stages = []
    for row in payload["data"]:
        if not isinstance(row, dict) or row.get("dictType") != "XMJD":
            raise CashError("cash_dependency_unavailable", "OA 项目阶段字典格式不正确。", 503)
        stages.append({"code": row.get("dictValue"), "name": row.get("dictLabel")})
    return _validate_stages(stages)


def _validate_stages(stages: object) -> list[dict]:
    if not isinstance(stages, list) or not stages:
        raise CashError("cash_dependency_unavailable", "OA 项目阶段字典为空或格式不正确。", 503)
    result, seen = [], set()
    for stage in stages:
        if not isinstance(stage, dict):
            raise CashError("cash_dependency_unavailable", "OA 项目阶段字典格式不正确。", 503)
        code, name = stage.get("code"), stage.get("name")
        if not isinstance(code, str) or not code.strip() or not isinstance(name, str) or not name.strip() or code in seen:
            raise CashError("cash_dependency_unavailable", "OA 项目阶段字典缺少唯一编码或名称。", 503)
        seen.add(code)
        result.append({"code": code, "name": name})
    if ENDED_STAGE_CODE not in seen:
        raise CashError("cash_dependency_unavailable", "OA 项目阶段字典缺少已核实的结束编码。", 503)
    return result


def _positive_page(value: object, maximum: int) -> int:
    if type(value) is int:
        number = value
    elif isinstance(value, str) and re.fullmatch(r"[1-9]\d{0,8}", value):
        number = int(value)
    else:
        invalid("分页参数必须为正整数。")
    if number < 1 or number > maximum:
        invalid("分页参数超出允许范围。")
    return number


class CashOaProjectService:
    def __init__(
        self,
        mongo_settings: MongoOASettings | None,
        selection_settings_provider: Callable[[], dict],
        stage_loader: Callable[[], list[dict]],
        *,
        mongo_client: MongoClient | None,
    ) -> None:
        self._settings = mongo_settings
        self._collection = (
            mongo_client[mongo_settings.database][mongo_settings.collection]
            if mongo_settings is not None and mongo_client is not None else None
        )
        self._selection_settings_provider = selection_settings_provider
        self._stage_loader = stage_loader

    def _stages(self) -> list[dict]:
        return _validate_stages(self._stage_loader())

    def _selection(self) -> dict:
        settings = self._selection_settings_provider()
        if (
            not isinstance(settings, dict)
            or type(settings.get("version")) is not int
            or settings["version"] < 1
            or type(settings.get("configured")) is not bool
            or not isinstance(settings.get("allowed_stage_codes"), list)
            or any(not isinstance(code, str) or not code for code in settings["allowed_stage_codes"])
        ):
            raise CashError("cash_dependency_unavailable", "现金项目选择设置格式不正确。", 503)
        return settings

    def _form_query(self) -> dict:
        # Actual OA form_data uses string form IDs; do not add a numeric fallback.
        if self._settings is None or self._collection is None:
            raise CashError("cash_dependency_unavailable", "OA 项目只读数据源未配置。", 503)
        return {"form_id": self._settings.project_form_id}

    @staticmethod
    def _row(document: dict, names: dict, allowed: set) -> dict:
        data, identity = document.get("data"), document.get("_id")
        if not isinstance(data, dict) or not isinstance(identity, ObjectId):
            raise CashError("cash_dependency_unavailable", "OA 项目缺少可信 ID 或资料。", 503)
        name, code, stage = data.get("name"), data.get("code"), data.get("projectPhase")
        if not isinstance(name, str) or not name.strip():
            raise CashError("cash_dependency_unavailable", "OA 项目缺少名称。", 503)
        if (code is not None and not isinstance(code, str)) or (stage is not None and not isinstance(stage, str)):
            raise CashError("cash_dependency_unavailable", "OA 项目编码或阶段格式不正确。", 503)
        code, stage = code or None, stage or None
        if stage == ENDED_STAGE_CODE:
            reason = "ended"
        elif stage is None:
            reason = "stage_missing"
        elif stage not in names:
            reason = "stage_unknown"
        elif stage not in allowed:
            reason = "stage_not_allowed"
        else:
            reason = None
        return {
            "id": str(identity), "code": code, "name": name,
            "stage_code": stage, "stage_name": names.get(stage),
            "selectable": reason is None, "unavailable_reason": reason,
        }

    def list_projects(self, query: dict) -> dict:
        if not isinstance(query, dict) or set(query) - {"purpose", "keyword", "stage_code", "selectable", "page", "page_size"}:
            invalid("项目查询参数不正确。")
        purpose = query.get("purpose", "all")
        if not isinstance(purpose, str) or purpose not in {"all", "selection"}:
            invalid("项目查询 purpose 必须为 all 或 selection。")
        page = _positive_page(query.get("page", 1), 1000000)
        page_size = _positive_page(query.get("page_size", 50), 200)
        keyword, stage_filter = query.get("keyword", ""), query.get("stage_code")
        if not isinstance(keyword, str) or len(keyword) > 200 or (stage_filter is not None and not isinstance(stage_filter, str)):
            invalid("项目查询文字参数不正确。")
        selectable = query.get("selectable")
        if isinstance(selectable, str) and selectable in {"true", "false"}:
            selectable = selectable == "true"
        if selectable is not None and type(selectable) is not bool:
            invalid("selectable 必须为布尔值。")
        if purpose == "selection" and selectable is False:
            invalid("可选项目查询不能同时要求不可选。")
        settings, stages = self._selection(), self._stages()
        names = {stage["code"]: stage["name"] for stage in stages}
        allowed = set(settings["allowed_stage_codes"]) if settings["configured"] else set()
        try:
            # One projected read gives a consistent full source set for filtering,
            # count and pagination. No per-row Mongo/OA queries or financial fields.
            form_query = self._form_query()
            documents = self._collection.find(form_query, PROJECT_PROJECTION).max_time_ms(self._settings.request_timeout_ms)
            rows = [self._row(document, names, allowed) for document in documents]
        except PyMongoError:
            raise CashError("cash_dependency_unavailable", "OA 项目读取失败。", 503) from None
        needle = keyword.strip().casefold()
        rows = [row for row in rows if
                (not needle or needle in row["name"].casefold() or needle in (row["code"] or "").casefold())
                and (stage_filter is None or row["stage_code"] == stage_filter)
                and (purpose != "selection" or row["selectable"])
                and (selectable is None or row["selectable"] is selectable)]
        rows.sort(key=lambda row: (row["name"], row["id"]))
        offset = (page - 1) * page_size
        return {
            "rows": rows[offset:offset + page_size], "stages": stages, "total": len(rows),
            "page": page, "page_size": page_size, "read_at": datetime.now(timezone.utc).isoformat(),
            "selection_settings_version": settings["version"], "configured": settings["configured"],
        }

    def resolve_project(self, project_id: str, allow_historical: bool = False) -> dict:
        if not isinstance(project_id, str) or not ObjectId.is_valid(project_id) or project_id != str(ObjectId(project_id)):
            invalid("OA 项目 ID 格式不正确。")
        try:
            form_query = self._form_query()
            document = self._collection.find_one(
                {**form_query, "_id": ObjectId(project_id)}, PROJECT_PROJECTION,
                max_time_ms=self._settings.request_timeout_ms,
            )
        except PyMongoError:
            raise CashError("cash_dependency_unavailable", "OA 项目读取失败。", 503) from None
        if document is None:
            raise CashError("cash_project_not_found", "OA 项目已不存在，无法新建项目归属。", 409)
        if allow_historical:
            row = self._row(document, {}, set())
            return {"id": row["id"], "name": row["name"], "selection_settings_version": None}
        settings, stages = self._selection(), self._stages()
        allowed = set(settings["allowed_stage_codes"]) if settings["configured"] else set()
        row = self._row(document, {stage["code"]: stage["name"] for stage in stages}, allowed)
        if not row["selectable"]:
            raise CashError("cash_project_not_selectable", "该项目当前不可用于新增现金流水。", 409)
        return {"id": row["id"], "name": row["name"], "selection_settings_version": settings["version"]}

    def validate_stage_codes(self, codes: object) -> list[str]:
        if not isinstance(codes, list) or any(not isinstance(code, str) or not code for code in codes):
            invalid("允许阶段必须为编码数组。")
        known = {stage["code"] for stage in self._stages()}
        if ENDED_STAGE_CODE in codes or any(code not in known for code in codes):
            invalid("允许阶段包含未知编码或已结束阶段。")
        return sorted(set(codes))

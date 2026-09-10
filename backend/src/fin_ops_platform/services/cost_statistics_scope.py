"""Project-cost selection values; no persistence or per-bank classification."""
from __future__ import annotations

from typing import Any

from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService

PROJECT_COST_SCOPE_KEY = "cost_statistics_project_cost_scope"
UNCATEGORIZED_CODE = "uncategorized"


def read_project_cost_scope(settings: dict[str, Any]) -> dict[str, Any]:
    value = settings.get(PROJECT_COST_SCOPE_KEY)
    if not isinstance(value, dict):
        raise ValueError("项目成本范围未初始化。")
    version = value.get("version")
    codes = value.get("selected_tag_codes")
    if type(version) is not int or version < 1 or not isinstance(codes, list):
        raise ValueError("项目成本范围配置无效。")
    if any(not isinstance(code, str) or not code.strip() or code != code.strip() for code in codes):
        raise ValueError("项目成本标签代码无效。")
    if len(codes) != len(set(codes)):
        raise ValueError("项目成本标签不能重复。")
    return {"version": version, "selected_tag_codes": sorted(codes)}


def project_cost_scope_tags(bank_tags: dict[str, Any], selected_codes: list[str]) -> list[dict[str, Any]]:
    rules = BankTransactionCategoryService.auto_tag_rules_payload(bank_tags)
    tags = [{"code": "internal_transfer", "label": "内部往来款", "path": ["内部往来款"],
             "status": "active", "can_select": True, "direction": "any"}]
    for rule in [*rules["active_rules"], *rules["archived_rules"]]:
        path = list(dict.fromkeys(part for part in [rule["output_primary_label"], rule["output_sub_label"]] if part))
        tags.append({"code": rule["code"], "label": rule["label"], "path": path,
                     "status": rule["status"], "direction": rule["direction"],
                     "can_select": rule["direction"] != "income"})
    tags.append({"code": UNCATEGORIZED_CODE, "label": "未标记", "path": ["未标记"],
                 "status": "active", "can_select": True, "direction": "expense"})
    known = {tag["code"] for tag in tags}
    for code in selected_codes:
        if code not in known:
            tags.append({"code": code, "label": code, "path": [code],
                         "status": "unavailable", "can_select": False, "direction": "unknown"})
    return tags


def source_in_project_cost_scope(row: dict[str, Any], selected: set[str]) -> bool:
    return (str(row.get("bank_tag_code") or "").strip() or UNCATEGORIZED_CODE) in selected

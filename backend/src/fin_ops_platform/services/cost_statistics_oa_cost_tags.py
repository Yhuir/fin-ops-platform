"""OA source-line cost classification decisions; pure validation, no bank writes."""
from __future__ import annotations

from typing import Any


def validate_oa_cost_tags(value: Any, *, units: list[dict[str, Any]],
                          cost_lines: list[dict[str, str]], tags: list[dict[str, str]],
                          previous: list[dict[str, str]]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("请刷新页面后重新保存成本标签。")
    unit_ids = {unit["unit_id"] for unit in units}
    owners = {(line["unit_id"], line["bank_transaction_id"]) for line in cost_lines if line["unit_id"] in unit_ids}
    catalogue = {tag["code"]: tag for tag in tags}
    prior = {(row["unit_id"], row["bank_transaction_id"]): row for row in previous}
    seen: set[tuple[str, str]] = set()
    result = []
    for row in value:
        if (not isinstance(row, dict) or set(row) != {"unit_id", "bank_transaction_id", "cost_tag_code"}
                or any(not isinstance(item, str) or not item.strip() for item in row.values())):
            raise ValueError("成本标签字段不完整或无效。")
        key = (row["unit_id"], row["bank_transaction_id"])
        if key not in owners or key in seen:
            raise ValueError("成本标签必须唯一对应当前范围的 OA 成本来源行。")
        seen.add(key)
        old = prior.get(key)
        if old is not None and old["cost_tag_code"] == row["cost_tag_code"]:
            result.append(dict(old))
            continue
        tag = catalogue.get(row["cost_tag_code"])
        if tag is None:
            raise ValueError("请选择有效的成本标签，已停用标签仅允许原行保留。")
        result.append({**row, "cost_tag_primary_label": tag["primary_label"], "cost_tag_sub_label": tag["sub_label"]})
    return result


def cost_tag_fields(tag: dict[str, str]) -> dict[str, Any]:
    path = list(dict.fromkeys(value for value in [tag["cost_tag_primary_label"], tag["cost_tag_sub_label"]] if value))
    return {"bank_tag_code": tag["cost_tag_code"], "bank_tag_primary_label": tag["cost_tag_primary_label"],
            "bank_tag_sub_label": tag["cost_tag_sub_label"], "bank_tag_label_path": path,
            "bank_tag_label": " / ".join(path)}
